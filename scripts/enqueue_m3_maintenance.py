#!/usr/bin/env python3
"""把到期来源刷新和每日空间治理扫描加入持久化 jobs 队列。"""
from __future__ import annotations

import uuid

from db import pool


def main() -> None:
    refresh_count = scan_count = connector_count = agent_count = 0
    with pool.connection() as conn:
        due = conn.execute(
            """
            SELECT n.id,n.title FROM source_documents s
            JOIN notes n ON n.source_document_id=s.id
            WHERE s.status='active' AND s.refresh_policy<>'manual'
              AND s.next_refresh_at<=NOW() AND n.deleted_at IS NULL
              AND NOT EXISTS (
                SELECT 1 FROM jobs j WHERE j.note_id=n.id
                  AND j.job_type='source_refresh' AND j.status IN ('queued','running')
              )
            """
        ).fetchall()
        for note_id, title in due:
            conn.execute(
                "INSERT INTO jobs(id,job_type,note_id,payload,status,stage,title) "
                "VALUES(%s,'source_refresh',%s,'{}','queued','queued',%s)",
                (uuid.uuid4(), note_id, title),
            )
            refresh_count += 1

        spaces = conn.execute(
            """
            SELECT s.id FROM spaces s
            WHERE NOT EXISTS (
                SELECT 1 FROM governance_runs r
                WHERE r.space_id=s.id AND r.created_at>NOW()-INTERVAL '23 hours'
            )
            """
        ).fetchall()
        for (space_id,) in spaces:
            run_id, job_id = uuid.uuid4(), uuid.uuid4()
            conn.execute(
                "INSERT INTO governance_runs(id,space_id) VALUES(%s,%s)", (run_id, space_id)
            )
            conn.execute(
                """
                INSERT INTO jobs(id,job_type,payload,status,stage,title)
                VALUES(%s,'governance_scan',
                    jsonb_build_object('run_id',%s::text,'space_id',%s::text),
                    'queued','queued','定时知识治理巡检')
                """,
                (job_id, run_id, space_id),
            )
            scan_count += 1
        connectors = conn.execute(
            """
            SELECT c.id,c.name FROM connector_accounts c
            WHERE c.status='active'
              AND (c.last_synced_at IS NULL OR c.last_synced_at<NOW()-INTERVAL '1 hour')
              AND NOT EXISTS (SELECT 1 FROM jobs j WHERE j.job_type='connector_sync'
                  AND j.status IN ('queued','running')
                  AND j.payload->>'connector_id'=c.id::text)
            """
        ).fetchall()
        for connector_id, name in connectors:
            conn.execute(
                "INSERT INTO jobs(id,job_type,payload,status,stage,title) VALUES("
                "%s,'connector_sync',jsonb_build_object('connector_id',%s::text),"
                "'queued','queued',%s)", (uuid.uuid4(), connector_id, f"定时同步 {name}")
            )
            connector_count += 1
        agent_spaces = conn.execute(
            """
            SELECT s.id FROM spaces s WHERE EXISTS (
                SELECT 1 FROM governance_issues gi WHERE gi.space_id=s.id AND gi.status='open'
            ) AND NOT EXISTS (
                SELECT 1 FROM agent_runs ar WHERE ar.space_id=s.id
                  AND ar.created_at>NOW()-INTERVAL '23 hours'
            )
            """
        ).fetchall()
        for (space_id,) in agent_spaces:
            run_id = uuid.uuid4()
            conn.execute("INSERT INTO agent_runs(id,space_id) VALUES(%s,%s)", (run_id, space_id))
            conn.execute(
                "INSERT INTO jobs(id,job_type,payload,status,stage,title) VALUES("
                "%s,'agent_plan',jsonb_build_object('run_id',%s::text,'space_id',%s::text),"
                "'queued','queued','定时治理 Agent 规划')", (uuid.uuid4(), run_id, space_id)
            )
            agent_count += 1
    print(f"queued refresh={refresh_count} governance={scan_count} "
          f"connectors={connector_count} agent={agent_count}")


if __name__ == "__main__":
    main()
