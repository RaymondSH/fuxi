"""标签治理 HTTP 接口。

  GET   /tags               标签云：统计 done 笔记各标签次数（受控词表有则用规范名回显）
  GET   /tags/vocab         受控词表全量（admin）
  POST  /tags               新建 / 补别名（admin）
  PATCH /tags/{name}        改描述 / 状态 / 归并目标（admin）
  POST  /tags/merge        归并：把旧名回写进所有 notes.tags 为规范名（admin）

设计：notes.tags 仍是自由 TEXT[]；受控词表(tags 表)只管规范名 + 别名 + 状态 + 归并。
归并走物理回写（array_replace）+ 同步 ES 索引，而非读时映射（查询路径多，读时映射易漏）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from db import pool
from services import audit, es, spaces
from services.auth import CurrentUser, get_current_user, require_admin

router = APIRouter(prefix="/tags", tags=["tags"])


class TagVocab(BaseModel):
    name: str
    aliases: list[str] = []
    description: str | None = None
    status: str = "active"
    merged_into: str | None = None


class CreateTagRequest(BaseModel):
    name: str = Field(min_length=1)
    aliases: list[str] = []
    description: str | None = None


class UpdateTagRequest(BaseModel):
    aliases: list[str] | None = None
    description: str | None = None
    status: str | None = None
    merged_into: str | None = None


class MergeTagRequest(BaseModel):
    from_tag: str = Field(min_length=1, description="被归并的旧标签名")
    to_tag: str = Field(min_length=1, description="归并到的规范名")


@router.get("", response_model=dict)
def list_tags(user: CurrentUser = Depends(get_current_user)) -> dict:
    """标签云：统计 done 笔记里各标签出现次数。

    若某标签在受控词表里是别名，回显其规范名并并入计数；无词表条目则原样。
    """
    with pool.connection() as conn:
        sids = spaces.visible_space_ids(conn, user)
        frag, params = spaces.space_filter_from(sids)
        rows = conn.execute(
            f"""
            SELECT tag, COUNT(*)::int AS cnt
            FROM notes, unnest(tags) AS tag
            WHERE ingest_status = 'done' AND deleted_at IS NULL{frag}
            GROUP BY tag
            ORDER BY cnt DESC, tag
            LIMIT 60
            """,
            params,
        ).fetchall()
        # 载入词表别名映射（别名→规范名），把同义标签并入规范名
        vocab = conn.execute(
            "SELECT name, aliases FROM tags WHERE status = 'active'"
        ).fetchall()
    alias_map: dict[str, str] = {}
    for name, aliases in vocab:
        for a in (aliases or []):
            alias_map[a] = name
    counts: dict[str, int] = {}
    for tag, cnt in rows:
        canonical = alias_map.get(tag, tag)
        counts[canonical] = counts.get(canonical, 0) + cnt
    items = [{"name": n, "count": c} for n, c in counts.items()]
    items.sort(key=lambda x: (-x["count"], x["name"]))
    return {"items": items[:60]}


@router.get("/vocab", response_model=dict)
def list_vocab(_: CurrentUser = Depends(require_admin)) -> dict:
    """受控词表全量（admin）。"""
    with pool.connection() as conn:
        rows = conn.execute(
            "SELECT name, aliases, COALESCE(description,''), status, merged_into FROM tags ORDER BY name"
        ).fetchall()
    return {
        "items": [
            TagVocab(
                name=r[0], aliases=r[1] or [], description=r[2] or None,
                status=r[3], merged_into=r[4],
            ).model_dump()
            for r in rows
        ]
    }


@router.post("", response_model=TagVocab, status_code=201)
def create_tag(
    req: CreateTagRequest,
    request: Request,
    admin: CurrentUser = Depends(require_admin),
) -> TagVocab:
    name = req.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="标签名不能为空")
    with pool.connection() as conn:
        # name 既是 PK 又可能已是某标签的别名 → 冲突
        existing = conn.execute(
            "SELECT name FROM tags WHERE name = %s OR %s = ANY(aliases)", (name, name)
        ).fetchone()
        if existing:
            raise HTTPException(status_code=409, detail="标签名已存在或已是别名")
        conn.execute(
            "INSERT INTO tags (name, aliases, description) VALUES (%s, %s, %s)",
            (name, req.aliases, req.description),
        )
    audit.log("tag_create", request=request, user_id=admin.id, target_type="tag", target_id=name,
              detail={"aliases": req.aliases})
    return TagVocab(name=name, aliases=req.aliases, description=req.description, status="active")


@router.patch("/{name}", response_model=TagVocab)
def update_tag(
    name: str,
    req: UpdateTagRequest,
    request: Request,
    admin: CurrentUser = Depends(require_admin),
) -> TagVocab:
    sets, params = [], []
    if req.aliases is not None:
        sets.append("aliases = %s"); params.append(req.aliases)
    if req.description is not None:
        sets.append("description = %s"); params.append(req.description)
    if req.status is not None:
        if req.status not in ("active", "merged", "deprecated"):
            raise HTTPException(status_code=400, detail="status 只能是 active/merged/deprecated")
        sets.append("status = %s"); params.append(req.status)
    if req.merged_into is not None:
        sets.append("merged_into = %s"); params.append(req.merged_into)
    if not sets:
        raise HTTPException(status_code=400, detail="没有可更新的字段")
    params.append(name)
    with pool.connection() as conn:
        row = conn.execute(
            f"UPDATE tags SET {', '.join(sets)} WHERE name = %s "
            "RETURNING name, aliases, COALESCE(description,''), status, merged_into",
            params,
        ).fetchone()
    if row is None:
        raise HTTPException(status_code=404, detail="标签不存在")
    audit.log("tag_update", request=request, user_id=admin.id, target_type="tag", target_id=name,
              detail={"fields": [s.split(" =")[0] for s in sets]})
    return TagVocab(name=row[0], aliases=row[1] or [], description=row[2] or None,
                    status=row[3], merged_into=row[4])


@router.post("/merge", status_code=200, response_model=dict)
def merge_tag(
    req: MergeTagRequest,
    request: Request,
    admin: CurrentUser = Depends(require_admin),
) -> dict:
    """归并：把所有 notes.tags 里的 from_tag 替换为 to_tag，并同步 ES 索引。

    from_tag 与 to_tag 相同报错；to_tag 无需预先在词表里存在（直接物理回写即可）。
    返回受影响的笔记数。
    """
    if req.from_tag == req.to_tag:
        raise HTTPException(status_code=400, detail="不能归并到自己")
    with pool.connection() as conn:
        # 找含 from_tag 的笔记（done 才索引进 ES，非 done 也回写但不必同步 ES）
        affected = conn.execute(
            "SELECT id, source_type, title, COALESCE(summary,''), COALESCE(content,''), tags, space_id "
            "FROM notes WHERE %s = ANY(tags) AND deleted_at IS NULL",
            (req.from_tag,),
        ).fetchall()
        for r in affected:
            note_id, source_type, title, summary, content, tags, space_id = r
            conn.execute(
                "UPDATE notes SET tags = array_replace(tags, %s, %s) WHERE id = %s",
                (req.from_tag, req.to_tag, note_id),
            )
            # 同步 ES（done 的笔记才在索引里；index_note 内部已按 _is_enabled() 短路）
            # 在 Python 侧把 from_tag 替成 to_tag 并去重，避免 to_tag 已存在时重复
            new_tags: list[str] = []
            for t in (tags or []):
                canonical = req.to_tag if t == req.from_tag else t
                if canonical not in new_tags:
                    new_tags.append(canonical)
            es.index_note(str(note_id), title, summary or "", content or "",
                          new_tags, source_type, space_id=str(space_id))
        # 词表里若 from_tag 存在，标 merged + 指向 to_tag
        conn.execute(
            """
            INSERT INTO tags (name, status, merged_into) VALUES (%s, 'merged', %s)
            ON CONFLICT (name) DO UPDATE SET status = 'merged', merged_into = %s
            """,
            (req.from_tag, req.to_tag, req.to_tag),
        )
    audit.log("tag_merge", request=request, user_id=admin.id, target_type="tag", target_id=req.from_tag,
              detail={"from": req.from_tag, "to": req.to_tag, "affected": len(affected)})
    return {"affected_notes": len(affected), "from": req.from_tag, "to": req.to_tag}
