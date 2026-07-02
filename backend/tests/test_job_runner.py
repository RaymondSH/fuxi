"""持久化 job runner 分发回归测试。"""
from __future__ import annotations

import unittest
import uuid
from unittest.mock import patch

from workers import job_runner


class JobRunnerTests(unittest.TestCase):
    def test_url_ingest_payload_is_recoverable(self) -> None:
        note_id = uuid.uuid4()
        actor_id = uuid.uuid4()
        space_id = uuid.uuid4()
        job = (
            uuid.uuid4(),
            "ingest",
            note_id,
            {
                "kind": "url",
                "url": "https://example.com",
                "actor_id": str(actor_id),
                "space_id": str(space_id),
            },
        )
        with patch.object(job_runner.ingest_worker, "run") as run:
            job_runner.dispatch(job)
        run.assert_called_once_with(
            note_id,
            actor_id=actor_id,
            space_id=space_id,
            url="https://example.com",
        )

    def test_unbound_mcp_scope_is_not_a_worker_payload_concern(self) -> None:
        self.assertIsNone(job_runner._uuid(None))


if __name__ == "__main__":
    unittest.main()
