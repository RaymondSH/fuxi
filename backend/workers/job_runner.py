"""持久化任务消费者：从 jobs 表领取并执行 ingest / compile / qa_gen。

单个 systemd 进程循环消费；领取使用 FOR UPDATE SKIP LOCKED，未来可安全扩为多实例。
启动时把上次进程中断留下的 running 任务重新排队，保证重启不丢任务。
"""
from __future__ import annotations

import signal
import threading
import uuid

from config import settings
from db import pool
from services import lifecycle, storage
from services.logging import get_logger, setup_logging
from workers import compile_worker, ingest_worker, qa_gen_worker

log = get_logger("job_runner")
_stop = threading.Event()
_SUPPORTED = (
    "ingest", "compile", "qa_gen", "note_reindex", "source_refresh",
    "governance_scan",
    "connector_sync", "agent_plan", "proposal_execute",
)


def _uuid(value) -> uuid.UUID | None:
    return uuid.UUID(str(value)) if value else None


def recover_interrupted() -> int:
    """进程重启后把未完成任务重新排队。当前部署只运行一个 worker 实例。"""
    with pool.connection() as conn:
        cur = conn.execute(
            """
            UPDATE jobs
            SET status = 'queued',
                stage = 'queued',
                started_at = NULL,
                finished_at = NULL,
                retries = retries + 1,
                error_msg = NULL
            WHERE status = 'running' AND job_type = ANY(%s)
            """,
            (list(_SUPPORTED),),
        )
    return cur.rowcount


def claim_next():
    """原子领取最早 queued 任务；无任务返回 None。"""
    with pool.connection() as conn:
        return conn.execute(
            """
            WITH next_job AS (
                SELECT id
                FROM jobs
                WHERE status = 'queued' AND job_type = ANY(%s)
                ORDER BY queued_at
                FOR UPDATE SKIP LOCKED
                LIMIT 1
            )
            UPDATE jobs j
            SET status = 'running',
                started_at = COALESCE(j.started_at, NOW()),
                error_msg = NULL
            FROM next_job
            WHERE j.id = next_job.id
            RETURNING j.id, j.job_type, j.note_id, j.payload
            """,
            (list(_SUPPORTED),),
        ).fetchone()


def _mark_failed(job_id: uuid.UUID, message: str) -> None:
    with pool.connection() as conn:
        conn.execute(
            """
            UPDATE jobs
            SET status = 'failed', error_msg = %s, finished_at = NOW()
            WHERE id = %s AND status = 'running'
            """,
            (message[:2000], job_id),
        )


def dispatch(job) -> None:
    job_id, job_type, note_id, payload = job
    payload = payload or {}
    actor_id = _uuid(payload.get("actor_id"))
    try:
        if job_type == "ingest":
            space_id = _uuid(payload.get("space_id"))
            if payload.get("kind") == "url":
                ingest_worker.run(
                    note_id,
                    actor_id=actor_id,
                    space_id=space_id,
                    url=payload["url"],
                )
            elif payload.get("kind") == "file":
                data = storage.get_store().get(payload["staged_key"])
                ingest_worker.run(
                    note_id,
                    actor_id=actor_id,
                    space_id=space_id,
                    data=data,
                    filename=payload["filename"],
                )
            else:
                raise ValueError("ingest job payload 缺少合法 kind")
        elif job_type == "compile":
            compile_worker.run(payload["slug"], actor_id=actor_id)
        elif job_type == "qa_gen":
            if note_id is None:
                raise ValueError("qa_gen job 缺少 note_id")
            qa_gen_worker.run(note_id, actor_id=actor_id)
        elif job_type == "note_reindex":
            if note_id is None:
                raise ValueError("note_reindex job 缺少 note_id")
            lifecycle.reindex(note_id)
            _mark_done(job_id)
        elif job_type == "source_refresh":
            if note_id is None:
                raise ValueError("source_refresh job 缺少 note_id")
            lifecycle.refresh_source(note_id, actor_id=actor_id)
            _mark_done(job_id)
        elif job_type == "governance_scan":
            from workers import governance_worker
            governance_worker.run(
                _uuid(payload.get("run_id")),
                _uuid(payload.get("space_id")),
                actor_id=actor_id,
            )
            _mark_done(job_id)
        elif job_type == "connector_sync":
            from workers import connector_worker
            connector_worker.run(_uuid(payload.get("connector_id")))
            _mark_done(job_id)
        elif job_type == "agent_plan":
            from workers import agent_worker
            agent_worker.plan(_uuid(payload.get("run_id")), _uuid(payload.get("space_id")))
            _mark_done(job_id)
        elif job_type == "proposal_execute":
            from workers import agent_worker
            agent_worker.execute(_uuid(payload.get("proposal_id")))
            _mark_done(job_id)
        else:
            raise ValueError(f"不支持的 job_type: {job_type}")
    except Exception as exc:  # noqa: BLE001 — 任务失败必须落表，worker 继续消费
        _mark_failed(job_id, str(exc))
        log.exception(
            "job failed",
            extra={"event": "job_failed", "job_id": str(job_id), "job_type": job_type},
        )


def _mark_done(job_id: uuid.UUID) -> None:
    with pool.connection() as conn:
        conn.execute(
            "UPDATE jobs SET status='done',stage='done',progress=100,finished_at=NOW() "
            "WHERE id=%s AND status='running'",
            (job_id,),
        )


def run_forever() -> None:
    recovered = recover_interrupted()
    log.info("job runner started", extra={"event": "worker_start", "recovered": recovered})
    while not _stop.is_set():
        job = claim_next()
        if job is None:
            _stop.wait(1.0)
            continue
        dispatch(job)
    log.info("job runner stopped", extra={"event": "worker_stop"})


def _request_stop(*_args) -> None:
    _stop.set()


def main() -> None:
    setup_logging(level=settings.log_level, fmt=settings.log_format)
    signal.signal(signal.SIGTERM, _request_stop)
    signal.signal(signal.SIGINT, _request_stop)
    run_forever()


if __name__ == "__main__":
    main()
