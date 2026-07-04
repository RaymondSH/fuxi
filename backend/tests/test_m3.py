"""M3 生命周期、护栏与重排降级回归测试。"""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from services import guardrails, reranker
from workers import governance_worker, job_runner


class GuardrailTests(unittest.TestCase):
    def test_masks_common_pii_before_provider_call(self) -> None:
        text, changed = guardrails.mask_pii(
            "联系 13812345678 或 ray@example.com，身份证 110101199001011234"
        )
        self.assertTrue(changed)
        self.assertNotIn("13812345678", text)
        self.assertNotIn("ray@example.com", text)
        self.assertNotIn("110101199001011234", text)

    def test_citation_verification_rejects_out_of_range(self) -> None:
        result = guardrails.verify_citations("结论见 [1] 和 [9]", 2)
        self.assertEqual(result["status"], "warning")
        self.assertEqual(result["invalid_citations"], [9])


class RerankTests(unittest.TestCase):
    def test_rerank_failure_keeps_rrf_order(self) -> None:
        rows = [
            (uuid.uuid4(), "url", "A", "", None, [], "a", "a", 0.1),
            (uuid.uuid4(), "url", "B", "", None, [], "b", "b", 0.05),
        ]
        with (
            patch.object(reranker, "settings", SimpleNamespace(
                rerank_enabled=True, ai_api_key="key",
                ai_base_url="https://example.invalid/v4", rerank_model="rerank",
            )),
            patch.object(reranker.httpx, "post", side_effect=RuntimeError("offline")),
        ):
            self.assertEqual(reranker.rerank_rows("q", rows, object()), rows)


class LifecycleDispatchTests(unittest.TestCase):
    def test_note_reindex_is_durable_worker_job(self) -> None:
        job_id, note_id = uuid.uuid4(), uuid.uuid4()
        with (
            patch.object(job_runner.lifecycle, "reindex") as reindex,
            patch.object(job_runner, "_mark_done") as done,
        ):
            job_runner.dispatch((job_id, "note_reindex", note_id, {}))
        reindex.assert_called_once_with(note_id)
        done.assert_called_once_with(job_id)


class GovernanceBudgetTests(unittest.TestCase):
    def test_conflict_detection_is_capped_by_call_count(self) -> None:
        pairs = [
            (
                uuid.uuid4(), f"A{i}", "", "left",
                uuid.uuid4(), f"B{i}", "", "right", 0.8,
            )
            for i in range(50)
        ]
        conn = MagicMock()

        def execute(sql, _params=None):
            cursor = MagicMock()
            if "FROM notes a JOIN notes b" in sql:
                cursor.fetchall.return_value = pairs
            elif "SELECT id,title" in sql or "SELECT n.id,n.title" in sql:
                cursor.fetchall.return_value = []
            return cursor

        conn.execute.side_effect = execute
        cm = MagicMock()
        cm.__enter__.return_value = conn
        assessment = SimpleNamespace(conflict=False, topic="", explanation="")
        with (
            patch.object(governance_worker.pool, "connection", return_value=cm),
            patch.object(governance_worker.llm, "detect_conflict", return_value=assessment) as detect,
        ):
            governance_worker.run(uuid.uuid4(), uuid.uuid4())
        self.assertEqual(detect.call_count, governance_worker._CONFLICT_LLM_CAP)


if __name__ == "__main__":
    unittest.main()
