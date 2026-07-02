"""M3 治理巡检：过期、近重、冲突、坏链和缺标签。"""
from __future__ import annotations

import datetime
import hashlib
import json
import uuid

from db import pool
from services import guardrails, llm, quota, usage
from services.logging import get_logger

log = get_logger("governance")


def _fp(kind: str, *parts) -> str:
    raw = ":".join([kind, *(str(p) for p in parts)])
    return hashlib.sha256(raw.encode()).hexdigest()


def _upsert(conn, space_id, note_id, kind, severity, title, evidence, fingerprint) -> None:
    conn.execute(
        """
        INSERT INTO governance_issues
            (space_id,note_id,issue_type,severity,title,evidence,fingerprint)
        VALUES (%s,%s,%s,%s,%s,%s::jsonb,%s)
        ON CONFLICT (space_id,fingerprint) DO UPDATE SET
            severity=EXCLUDED.severity,title=EXCLUDED.title,evidence=EXCLUDED.evidence,
            last_seen_at=NOW(),
            status=CASE WHEN governance_issues.status='resolved' THEN 'open'
                        ELSE governance_issues.status END,
            resolved_at=CASE WHEN governance_issues.status='resolved' THEN NULL
                             ELSE governance_issues.resolved_at END
        """,
        (space_id, note_id, kind, severity, title,
         json.dumps(evidence, ensure_ascii=False, default=str), fingerprint),
    )


def run(run_id: uuid.UUID, space_id: uuid.UUID, actor_id=None) -> None:
    if run_id is None or space_id is None:
        raise ValueError("governance_scan 缺少 run_id/space_id")
    seen: set[str] = set()
    stats = {k: 0 for k in ("stale", "duplicate", "conflict", "broken_link", "missing_tags")}
    with pool.connection() as conn:
        conn.execute(
            "UPDATE governance_runs SET status='running',started_at=NOW() WHERE id=%s",
            (run_id,),
        )
    try:
        with usage.collect() as collected, pool.connection() as conn:
            notes = conn.execute(
                """
                SELECT id,title,COALESCE(summary,''),COALESCE(content,''),tags,
                       published_date,updated_at
                FROM notes
                WHERE space_id=%s AND ingest_status='done' AND deleted_at IS NULL
                """,
                (space_id,),
            ).fetchall()
            for nid, title, _summary, _content, tags, pub, updated in notes:
                if not tags:
                    fp = _fp("missing_tags", nid); seen.add(fp); stats["missing_tags"] += 1
                    _upsert(conn, space_id, nid, "missing_tags", "medium",
                            f"「{title}」缺少标签", {}, fp)
                basis = pub or updated.date()
                if (datetime.date.today() - basis).days >= 180:
                    fp = _fp("stale", nid); seen.add(fp); stats["stale"] += 1
                    _upsert(conn, space_id, nid, "stale", "low",
                            f"「{title}」可能已过期", {"date": basis.isoformat()}, fp)

            broken = conn.execute(
                """
                SELECT n.id,n.title,s.error_msg FROM notes n
                JOIN source_documents s ON s.id=n.source_document_id
                WHERE n.space_id=%s AND n.deleted_at IS NULL AND s.status='broken'
                """,
                (space_id,),
            ).fetchall()
            for nid, title, error in broken:
                fp = _fp("broken_link", nid); seen.add(fp); stats["broken_link"] += 1
                _upsert(conn, space_id, nid, "broken_link", "high",
                        f"「{title}」来源不可用", {"error": error}, fp)

            pairs = conn.execute(
                """
                SELECT a.id,a.title,COALESCE(a.summary,''),COALESCE(a.content,''),
                       b.id,b.title,COALESCE(b.summary,''),COALESCE(b.content,''),
                       1-(a.embedding <=> b.embedding) similarity
                FROM notes a JOIN notes b ON a.id < b.id AND a.space_id=b.space_id
                WHERE a.space_id=%s AND a.deleted_at IS NULL AND b.deleted_at IS NULL
                  AND a.ingest_status='done' AND b.ingest_status='done'
                  AND a.embedding IS NOT NULL AND b.embedding IS NOT NULL
                  AND (1-(a.embedding <=> b.embedding)) >= 0.72
                ORDER BY similarity DESC LIMIT 50
                """,
                (space_id,),
            ).fetchall()
            for a_id, a_title, a_sum, a_content, b_id, b_title, b_sum, b_content, similarity in pairs:
                ordered = sorted((str(a_id), str(b_id)))
                if similarity >= 0.92:
                    fp = _fp("duplicate", *ordered); seen.add(fp); stats["duplicate"] += 1
                    _upsert(conn, space_id, a_id, "duplicate", "medium",
                            f"「{a_title}」与「{b_title}」高度相似",
                            {"other_note_id": str(b_id), "similarity": float(similarity)}, fp)
                try:
                    left, _ = guardrails.mask_pii(
                        f"{a_title}\n{a_sum}\n{a_content[:1500]}",
                    )
                    right, _ = guardrails.mask_pii(
                        f"{b_title}\n{b_sum}\n{b_content[:1500]}",
                    )
                    assessment = llm.detect_conflict(left, right)
                except Exception:
                    continue
                if assessment.conflict:
                    fp = _fp("conflict", *ordered); seen.add(fp); stats["conflict"] += 1
                    _upsert(conn, space_id, a_id, "conflict", "high",
                            assessment.topic or f"「{a_title}」与「{b_title}」存在冲突",
                            {"other_note_id": str(b_id), "explanation": assessment.explanation}, fp)

            if seen:
                conn.execute(
                    """
                    UPDATE governance_issues SET status='resolved',resolved_at=NOW(),
                        resolution_note='后续扫描未再发现'
                    WHERE space_id=%s AND status='open' AND NOT (fingerprint=ANY(%s))
                    """,
                    (space_id, list(seen)),
                )
            else:
                conn.execute(
                    "UPDATE governance_issues SET status='resolved',resolved_at=NOW(),"
                    "resolution_note='后续扫描未再发现' WHERE space_id=%s AND status='open'",
                    (space_id,),
                )
            conn.execute(
                "UPDATE governance_runs SET status='done',stats=%s::jsonb,finished_at=NOW() WHERE id=%s",
                (json.dumps(stats), run_id),
            )
        if actor_id is not None:
            quota.record_usage(actor_id, "governance_scan", collected)
    except Exception as exc:
        with pool.connection() as conn:
            conn.execute(
                "UPDATE governance_runs SET status='failed',error_msg=%s,finished_at=NOW() WHERE id=%s",
                (str(exc)[:2000], run_id),
            )
        log.exception("governance scan failed", extra={"run_id": str(run_id)})
        raise
