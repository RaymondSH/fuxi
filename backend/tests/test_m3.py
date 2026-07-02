"""M3 生命周期、护栏与重排降级回归测试。"""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from services import guardrails, reranker
from workers import job_runner


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


if __name__ == "__main__":
    unittest.main()
