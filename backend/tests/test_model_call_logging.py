from __future__ import annotations

import inspect
import unittest
from unittest.mock import patch
from uuid import uuid4

from app.http_limits import log_model_call
from app.services import chat as chat_service
from app.services import include_chunk


class ModelCallLoggingTests(unittest.TestCase):
    def test_log_model_call_format(self) -> None:
        with patch("app.http_limits.logger") as mock_logger:
            chat_id = uuid4()
            log_model_call(chat_id=chat_id, slice_id="chunk 1/3", n_chars=4200)
            mock_logger.info.assert_called_once_with(
                "model_call chat_id=%s slice=%s n_chars=%s",
                chat_id,
                "chunk 1/3",
                4200,
            )

    def test_log_model_call_omits_slice_when_none(self) -> None:
        with patch("app.http_limits.logger") as mock_logger:
            log_model_call(chat_id="abc", slice_id=None, n_chars=12)
            mock_logger.info.assert_called_once_with(
                "model_call chat_id=%s slice=%s n_chars=%s",
                "abc",
                "-",
                12,
            )

    def test_stream_completion_logs_metadata_not_body(self) -> None:
        source = inspect.getsource(chat_service.stream_completion)
        self.assertIn("log_model_call(", source)
        self.assertNotIn('logger.info("prompt', source)
        self.assertNotIn("logger.info(body", source)

    def test_complete_once_logs_metadata_not_body(self) -> None:
        source = inspect.getsource(chat_service.complete_once)
        self.assertIn("log_model_call(", source)
        self.assertNotIn('logger.info("prompt', source)

    def test_slice_id_from_meta_uses_chip(self) -> None:
        self.assertEqual(
            include_chunk.slice_id_from_meta({"include_chip": "heading: Intro"}),
            "heading: Intro",
        )
        self.assertIsNone(include_chunk.slice_id_from_meta({}))


if __name__ == "__main__":
    unittest.main()
