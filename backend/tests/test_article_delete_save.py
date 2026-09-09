from __future__ import annotations

import unittest
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock

from app.models import Article, Feed, OverlayAddition, User
from app.routers.articles import delete_article, patch_article
from app.schemas import ArticlePatch


class ArticleDeleteSaveTests(unittest.TestCase):
    def test_patch_save_storykeep_note_without_http_fetch(self):
        user = User(id=uuid.uuid4(), email="test@example.com", password_hash="x")
        feed = Feed(id=uuid.uuid4(), user_id=user.id, url="storykeep://notes", title="Notes")
        article = Article(
            id=uuid.uuid4(),
            feed_id=feed.id,
            guid="storykeep-note:abc",
            url="storykeep://pending",
            title="Vault note",
            content_text="Body",
            content_html="<p>Body</p>",
            is_read=False,
            is_saved=False,
            is_starred=False,
            created_at=datetime.now(timezone.utc),
            source_kind="obsidian",
        )
        article.feed = feed
        db = MagicMock()
        db.scalar.return_value = article
        db.scalars.return_value.all.return_value = []

        out = patch_article(article.id, ArticlePatch(is_saved=True), db=db, user=user)

        self.assertTrue(out.is_saved)
        db.commit.assert_called()

    def test_delete_article_removes_overlay_addition(self):
        user = User(id=uuid.uuid4(), email="test@example.com", password_hash="x")
        feed = Feed(id=uuid.uuid4(), user_id=user.id, url="storykeep://notes", title="Notes")
        article = Article(
            id=uuid.uuid4(),
            feed_id=feed.id,
            guid="storykeep-note:abc",
            url="storykeep://pending",
            title="Note",
            content_text="Body",
            is_saved=True,
            saved_at=datetime.now(timezone.utc),
            source_kind="obsidian",
        )
        addition = OverlayAddition(
            id=uuid.uuid4(),
            user_id=user.id,
            article_id=article.id,
            title="Note",
            markdown="Body",
        )
        db = MagicMock()
        db.scalar.return_value = article
        child_rows = MagicMock()
        child_rows.all.return_value = []
        db.scalars.side_effect = [child_rows, iter([addition])]

        result = delete_article(article.id, db=db, user=user)

        self.assertTrue(result["ok"])
        db.delete.assert_any_call(addition)
        db.delete.assert_any_call(article)
        db.commit.assert_called_once()


if __name__ == "__main__":
    unittest.main()
