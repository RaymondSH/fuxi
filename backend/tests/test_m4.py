"""M4 连接器、凭据与审批执行边界测试。"""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import patch

from cryptography.fernet import Fernet

from services import connector_crypto
from services.connector_providers.base import RemoteItem
from services.connector_providers.providers import ConfluenceProvider
from workers import agent_worker, job_runner


class ConnectorCryptoTests(unittest.TestCase):
    def test_credentials_round_trip_as_ciphertext(self) -> None:
        fake = SimpleNamespace(connector_secret_key=Fernet.generate_key().decode())
        with patch.object(connector_crypto, "settings", fake):
            encrypted = connector_crypto.encrypt({"token": "secret"})
            self.assertNotIn(b"secret", encrypted)
            self.assertEqual(connector_crypto.decrypt(encrypted), {"token": "secret"})


class ProviderTests(unittest.TestCase):
    def test_confluence_body_is_converted_to_plain_text(self) -> None:
        provider = ConfluenceProvider(
            {"base_url": "https://example.atlassian.net"}, {"email": "x", "api_token": "x"}
        )
        item = RemoteItem(
            "1", "Title", "/wiki/x", "1",
            metadata={"body": {"storage": {"value": "<p>Hello <b>world</b></p>"}}},
        )
        self.assertIn("Hello world", provider.fetch_content(item).content)


class AgentBoundaryTests(unittest.TestCase):
    def test_missing_tags_only_creates_whitelisted_action(self) -> None:
        analysis = SimpleNamespace(tags=["RAG", "检索"])
        with patch.object(agent_worker.llm, "analyze", return_value=analysis):
            action, payload, _ = agent_worker._proposal(
                "missing_tags", "title", "content", [], {}
            )
        self.assertEqual(action, "add_tags")
        self.assertEqual(payload["tags"], ["RAG", "检索"])

    def test_connector_sync_is_dispatched_by_durable_worker(self) -> None:
        connector_id, job_id = uuid.uuid4(), uuid.uuid4()
        with (
            patch("workers.connector_worker.run") as run,
            patch.object(job_runner, "_mark_done") as done,
        ):
            job_runner.dispatch((
                job_id, "connector_sync", None, {"connector_id": str(connector_id)}
            ))
        run.assert_called_once_with(connector_id)
        done.assert_called_once_with(job_id)


if __name__ == "__main__":
    unittest.main()
