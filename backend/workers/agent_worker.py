"""M4 治理 Agent：生成白名单提案；审批后确定性执行。"""
from __future__ import annotations

import json
import uuid

from db import pool
from services import audit, distribution, lifecycle, llm


def plan(run_id: uuid.UUID, space_id: uuid.UUID) -> None:
    with pool.connection() as conn:
        conn.execute("UPDATE agent_runs SET status='running' WHERE id=%s", (run_id,))
        issues = conn.execute(
            """
            SELECT gi.id,gi.note_id,gi.issue_type,gi.evidence,n.title,
                   COALESCE(n.content,''),n.tags
            FROM governance_issues gi LEFT JOIN notes n ON n.id=gi.note_id
            WHERE gi.space_id=%s AND gi.status='open' AND n.deleted_at IS NULL
            ORDER BY CASE gi.severity WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END
            LIMIT 30
            """,
            (space_id,),
        ).fetchall()
    count = 0
    try:
        for issue_id, note_id, kind, evidence, title, content, tags in issues:
            action, payload, rationale = _proposal(kind, title, content, tags or [], evidence or {})
            if action is None:
                continue
            with pool.connection() as conn:
                exists = conn.execute(
                    "SELECT 1 FROM agent_proposals WHERE issue_id=%s AND status IN "
                    "('pending','approved','executing')", (issue_id,)
                ).fetchone()
                if exists: continue
                conn.execute(
                    """
                    INSERT INTO agent_proposals(run_id,space_id,note_id,issue_id,action,payload,rationale)
                    VALUES(%s,%s,%s,%s,%s,%s::jsonb,%s)
                    """,
                    (run_id, space_id, note_id, issue_id, action,
                     json.dumps(payload, ensure_ascii=False), rationale),
                )
                count += 1
        with pool.connection() as conn:
            conn.execute(
                "UPDATE agent_runs SET status='done',stats=%s::jsonb,finished_at=NOW() WHERE id=%s",
                (json.dumps({"proposals": count}), run_id),
            )
    except Exception as exc:
        with pool.connection() as conn:
            conn.execute("UPDATE agent_runs SET status='failed',error_msg=%s,finished_at=NOW() WHERE id=%s",
                         (str(exc)[:1000], run_id))
        raise


def _proposal(kind, title, content, tags, evidence):
    if kind == "missing_tags":
        analysis = llm.analyze(content, title_hint=title)
        return "add_tags", {"tags": analysis.tags[:5]}, "根据正文补充缺失标签"
    if kind in ("stale", "broken_link"):
        return "refresh_source", {}, "重新检查来源并更新失效或过期内容"
    if kind == "duplicate":
        return "archive_duplicate", {"other_note_id": evidence.get("other_note_id")}, "归档近似重复内容"
    if kind == "conflict":
        return "resolve_issue", {}, "冲突需要人工确认，审批后关闭当前治理待办"
    return None, {}, ""


def execute(proposal_id: uuid.UUID) -> None:
    with pool.connection() as conn:
        row = conn.execute(
            "SELECT space_id,note_id,issue_id,action,payload FROM agent_proposals "
            "WHERE id=%s AND status='approved' FOR UPDATE", (proposal_id,)
        ).fetchone()
        if row is None: raise ValueError("提案不存在或未审批")
        conn.execute("UPDATE agent_proposals SET status='executing' WHERE id=%s", (proposal_id,))
    space_id, note_id, issue_id, action, payload = row
    try:
        with pool.connection() as conn:
            if note_id and conn.execute(
                "SELECT 1 FROM notes WHERE id=%s AND space_id=%s", (note_id, space_id)
            ).fetchone() is None:
                raise ValueError("提案目标不属于指定空间")
        if action == "add_tags":
            with pool.connection() as conn:
                lifecycle.save_version(conn, note_id, "edit")
                conn.execute(
                    "UPDATE notes SET tags=(SELECT ARRAY(SELECT DISTINCT unnest(tags || %s::text[]))) "
                    "WHERE id=%s AND space_id=%s AND deleted_at IS NULL",
                    (payload.get("tags", []), note_id, space_id),
                )
            lifecycle.reindex(note_id)
        elif action == "update_summary":
            with pool.connection() as conn:
                lifecycle.save_version(conn, note_id, "edit")
                conn.execute("UPDATE notes SET summary=%s WHERE id=%s AND space_id=%s",
                             (payload["summary"], note_id, space_id))
            lifecycle.reindex(note_id)
        elif action == "refresh_source":
            lifecycle.refresh_source(note_id)
        elif action == "archive_duplicate":
            with pool.connection() as conn:
                lifecycle.save_version(conn, note_id, "delete")
                conn.execute("UPDATE notes SET deleted_at=NOW() WHERE id=%s AND space_id=%s",
                             (note_id, space_id))
            lifecycle.reindex(note_id)
        elif action == "resolve_issue":
            pass
        else:
            raise ValueError("动作不在执行白名单")
        if issue_id:
            with pool.connection() as conn:
                conn.execute(
                    "UPDATE governance_issues SET status='resolved',resolved_at=NOW(),"
                    "resolution_note='Agent 提案经人工审批执行' WHERE id=%s", (issue_id,)
                )
        with pool.connection() as conn:
            conn.execute("UPDATE agent_proposals SET status='executed',error_msg=NULL WHERE id=%s",
                         (proposal_id,))
        distribution.emit_change(space_id, note_id, "updated", "治理提案已执行",
                                 {"proposal_id": str(proposal_id), "action": action})
        audit.log("agent_proposal_executed", target_type="agent_proposal",
                  target_id=proposal_id, detail={"action": action, "space_id": str(space_id)})
    except Exception as exc:
        with pool.connection() as conn:
            conn.execute("UPDATE agent_proposals SET status='failed',error_msg=%s WHERE id=%s",
                         (str(exc)[:1000], proposal_id))
        raise
