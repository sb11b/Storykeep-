from __future__ import annotations

import base64
import unittest
import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

VALID_IV = base64.b64encode(b"\x00" * 12).decode("ascii")
VALID_CT = base64.b64encode(b"\x00" * 16).decode("ascii")

from fastapi import HTTPException

from app.services import message_crypto
from app.services.grok_conversations import append_encrypted_message, migrate_message_to_encrypted


class MessageCryptoTests(unittest.TestCase):
    def test_validate_ciphertext_rejects_short_iv(self):
        with self.assertRaises(ValueError):
            message_crypto.validate_ciphertext("AAAA", VALID_CT)

    def test_is_enabled_reads_preferences(self):
        user = SimpleNamespace(preferences={"message_crypto_enabled": True})
        self.assertTrue(message_crypto.is_enabled(user))
        user.preferences = {}
        self.assertFalse(message_crypto.is_enabled(user))

    def test_message_body_out_encrypted_is_opaque(self):
        row = SimpleNamespace(encrypted=True, body_iv="iv", body_ct="ct", content=None)
        out = message_crypto.message_body_out(row, crypto_enabled=True)
        self.assertTrue(out["encrypted"])
        self.assertEqual(out["iv"], "iv")
        self.assertEqual(out["ct"], "ct")
        self.assertIsNone(out["content"])

    def test_append_encrypted_message_stores_blobs(self):
        db = MagicMock()
        conversation = SimpleNamespace(id=uuid.uuid4(), title="New chat", updated_at=None)
        row = append_encrypted_message(
            db,
            conversation,
            role="user",
            iv=VALID_IV,
            ct=VALID_CT,
            title="Hello",
        )
        self.assertTrue(row.encrypted)
        self.assertIsNone(row.content)
        self.assertEqual(row.body_iv, VALID_IV)
        db.add.assert_called()

    def test_migrate_message_to_encrypted_clears_plaintext(self):
        db = MagicMock()
        user_id = uuid.uuid4()
        message_id = uuid.uuid4()
        row = SimpleNamespace(
            id=message_id,
            encrypted=False,
            content="plain",
            body_iv=None,
            body_ct=None,
        )
        db.scalar.return_value = row
        migrate_message_to_encrypted(db, user_id, message_id, iv=VALID_IV, ct=VALID_CT)
        self.assertTrue(row.encrypted)
        self.assertIsNone(row.content)
        self.assertEqual(row.body_iv, VALID_IV)

    def test_migrate_missing_message_raises(self):
        db = MagicMock()
        db.scalar.return_value = None
        with self.assertRaises(HTTPException) as ctx:
            migrate_message_to_encrypted(db, uuid.uuid4(), uuid.uuid4(), iv=VALID_IV, ct=VALID_CT)
        self.assertEqual(ctx.exception.status_code, 404)


class ChatIndexCryptoTests(unittest.TestCase):
    def test_can_use_false_when_crypto_enabled(self):
        from app.services import chat_index

        user = SimpleNamespace(
            email="reader@example.com",
            is_demo_locked=False,
            preferences={"message_crypto_enabled": True},
        )
        self.assertFalse(chat_index.can_use(user))

    def test_can_use_true_when_crypto_disabled(self):
        from app.services import chat_index

        user = SimpleNamespace(email="reader@example.com", is_demo_locked=False, preferences={})
        self.assertTrue(chat_index.can_use(user))
