"""Wiki 空间 ACL SQL 别名回归测试。"""
from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from routers import wiki
from services.auth import CurrentUser


def _user() -> CurrentUser:
    return CurrentUser(
        id=uuid.uuid4(),
        username="member",
        email="member@example.com",
        display_name=None,
        role="member",
        daily_token_limit=None,
        is_active=True,
    )


class WikiAclTests(unittest.TestCase):
    def test_list_uses_wiki_pages_alias(self) -> None:
        conn = MagicMock()
        conn.execute.return_value.fetchall.return_value = []
        cm = MagicMock()
        cm.__enter__.return_value = conn
        space_id = uuid.uuid4()
        with (
            patch.object(wiki.pool, "connection", return_value=cm),
            patch.object(wiki.spaces, "visible_space_ids", return_value=[space_id]),
        ):
            wiki.list_wiki(_user())
        sql = conn.execute.call_args.args[0]
        self.assertIn("wiki_pages.space_id", sql)
        self.assertNotIn("AND notes.space_id", sql)

    def test_detail_uses_separate_alias_for_source_notes(self) -> None:
        space_id, note_id = uuid.uuid4(), uuid.uuid4()
        wiki_cursor = MagicMock()
        wiki_cursor.fetchone.return_value = (
            "topic", "Topic", datetime.now(timezone.utc), [note_id], [], None, space_id,
        )
        note_cursor = MagicMock()
        note_cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.execute.side_effect = [wiki_cursor, note_cursor]
        cm = MagicMock()
        cm.__enter__.return_value = conn
        with (
            patch.object(wiki.pool, "connection", return_value=cm),
            patch.object(wiki.spaces, "visible_space_ids", return_value=[space_id]),
        ):
            wiki.get_wiki("topic", _user())
        wiki_sql = conn.execute.call_args_list[0].args[0]
        note_sql = conn.execute.call_args_list[1].args[0]
        self.assertIn("wiki_pages.space_id", wiki_sql)
        self.assertIn("notes.space_id", note_sql)
        self.assertNotIn("wiki_pages.space_id", note_sql)


if __name__ == "__main__":
    unittest.main()
