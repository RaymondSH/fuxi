"""M0/M2 安全边界回归测试。"""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from starlette.requests import Request

from routers.auth import _lock_active
from routers import search as search_router
from services import audit, auth, es, spaces
from services.auth import CurrentUser


def _request(*, cookies: str = "") -> Request:
    headers = []
    if cookies:
        headers.append((b"cookie", cookies.encode()))
    return Request({
        "type": "http",
        "method": "GET",
        "path": "/api/notes",
        "headers": headers,
        "query_string": b"",
        "server": ("test", 80),
        "client": ("127.0.0.1", 1234),
        "scheme": "http",
    })


class AuthBoundaryTests(unittest.TestCase):
    def test_refresh_token_cannot_authenticate_business_request(self) -> None:
        cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="refresh-token")
        with patch.object(auth, "_decode", return_value={
            "type": "refresh", "sub": str(uuid.uuid4()), "jti": "refresh-jti",
        }):
            with self.assertRaises(HTTPException) as ctx:
                auth.get_current_user(_request(), cred)
        self.assertEqual(ctx.exception.status_code, 401)

    def test_access_cookie_authenticates_when_valid(self) -> None:
        user = CurrentUser(
            id=uuid.uuid4(), username="u", email="u@example.com",
            display_name=None, role="member", daily_token_limit=None, is_active=True,
        )
        with (
            patch.object(auth, "_decode", return_value={
                "type": "access", "sub": str(user.id), "jti": "access-jti",
            }),
            patch.object(auth, "_is_revoked", return_value=False),
            patch.object(auth, "_load_user", return_value=user),
        ):
            actual = auth.get_current_user(_request(cookies="fuxi_access=cookie-token"), None)
        self.assertEqual(actual.id, user.id)

    def test_expired_lock_is_not_active(self) -> None:
        now = datetime.now(timezone.utc)
        self.assertFalse(_lock_active(now - timedelta(seconds=1), now=now))
        self.assertTrue(_lock_active(now + timedelta(seconds=1), now=now))


class SpaceBoundaryTests(unittest.TestCase):
    def test_empty_membership_generates_match_nothing_filter(self) -> None:
        fragment, params = spaces.space_filter_from([])
        self.assertIn("space_id = ANY", fragment)
        self.assertEqual(params, [[]])

    def test_es_empty_membership_never_queries_global_index(self) -> None:
        with (
            patch.object(es, "_is_enabled", return_value=True),
            patch.object(es, "_get_client") as client,
        ):
            self.assertEqual(es.search("secret", space_ids=[]), [])
        client.assert_not_called()

    def test_chunk_semantic_search_binds_space_before_order_vector(self) -> None:
        space_id = uuid.uuid4()
        fragment, params = spaces.space_filter_from([space_id])
        conn = Mock()
        conn.execute.return_value.fetchall.return_value = []
        vector = [0.1, 0.2]
        with patch.object(search_router, "_semantic_search_doc", return_value=[]):
            search_router._semantic_search(
                conn, vector, [], "all", fragment, params
            )
        self.assertEqual(
            conn.execute.call_args.args[1],
            [vector, [space_id], vector, [space_id]],
        )


class AuditTests(unittest.TestCase):
    def test_audit_logger_is_not_shadowed_by_log_function(self) -> None:
        with (
            patch.object(audit._logger, "info") as info,
            patch.object(audit.pool, "connection", side_effect=RuntimeError("db unavailable")),
            patch.object(audit._logger, "error") as error,
        ):
            audit.log("test_event")
        info.assert_called_once()
        error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
