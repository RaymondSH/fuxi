"""M4 连接器、凭据与审批执行边界测试。"""
from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from cryptography.fernet import Fernet
from fastapi import HTTPException

from routers import agent as agent_router
from services import connector_crypto
from services.connector_providers.base import RemoteItem
from services.connector_providers import providers
from services.connector_providers.providers import ConfluenceProvider, GoogleDriveProvider
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

    def test_google_drive_initial_sync_follows_all_pages(self) -> None:
        first, second, token = MagicMock(), MagicMock(), MagicMock()
        first.json.return_value = {
            "files": [{"id": "1", "name": "A", "mimeType": "text/plain"}],
            "nextPageToken": "page-2",
        }
        second.json.return_value = {
            "files": [{"id": "2", "name": "B", "mimeType": "text/plain"}],
        }
        token.json.return_value = {"startPageToken": "cursor"}
        provider = GoogleDriveProvider({}, {
            "client_id": "id", "client_secret": "secret", "refresh_token": "refresh",
        })
        with (
            patch.object(provider, "_token", return_value="access"),
            patch.object(providers, "_request", side_effect=[first, second, token]) as request,
        ):
            items, cursor = provider.list_changes(None)
        self.assertEqual([item.external_id for item in items], ["1", "2"])
        self.assertEqual(cursor, "cursor")
        self.assertEqual(request.call_args_list[1].kwargs["params"]["pageToken"], "page-2")


class AgentBoundaryTests(unittest.TestCase):
    def test_missing_tags_only_creates_whitelisted_action(self) -> None:
        analysis = SimpleNamespace(tags=["RAG", "检索"])
        with patch.object(agent_worker.llm, "analyze", return_value=analysis):
            action, payload, _ = agent_worker._proposal(
                "missing_tags", "title", "content", [], {}
            )
        self.assertEqual(action, "add_tags")
        self.assertEqual(payload["tags"], ["RAG", "检索"])

    def test_stale_url_refreshes_source_but_manual_source_is_not_cosmetically_rewritten(self) -> None:
        action, _, _ = agent_worker._proposal(
            "stale", "title", "content", [], {}, "url",
        )
        self.assertEqual(action, "refresh_source")
        action, _, _ = agent_worker._proposal(
            "stale", "title", "content", [], {}, "manual",
        )
        self.assertIsNone(action)

    def test_review_uses_conditional_update_to_prevent_duplicate_jobs(self) -> None:
        space_id = uuid.uuid4()
        first_conn = MagicMock()
        first_conn.execute.return_value.fetchone.return_value = (space_id,)
        second_conn = MagicMock()
        second_conn.execute.return_value.fetchone.return_value = None
        first_cm, second_cm = MagicMock(), MagicMock()
        first_cm.__enter__.return_value = first_conn
        second_cm.__enter__.return_value = second_conn
        with (
            patch.object(agent_router.pool, "connection", side_effect=[first_cm, second_cm]),
            patch.object(agent_router.spaces, "assert_space_role"),
            self.assertRaises(HTTPException) as ctx,
        ):
            agent_router._review(uuid.uuid4(), True, SimpleNamespace(id=uuid.uuid4()), None)
        self.assertEqual(ctx.exception.status_code, 409)
        update_sql = second_conn.execute.call_args.args[0]
        self.assertIn("status='pending'", update_sql)

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
