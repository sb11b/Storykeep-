from __future__ import annotations

import unittest

from app.services import chat, junior_model, tts as tts_service


class JuniorVoiceReplyTests(unittest.TestCase):
    def test_voice_turn_detected(self):
        self.assertTrue(tts_service.wants_voice_info("Show the current xAI voice list for Junior."))
        self.assertFalse(tts_service.wants_voice_info("hello"))

    def test_voice_turn_uses_xhigh_on_auto(self):
        msg = "List xAI TTS voices so I can pick one for Listen."
        self.assertTrue(tts_service.wants_voice_info(msg))
        self.assertTrue(chat.pick_xhigh_for_auto(msg))
        self.assertEqual(chat.resolve_reasoning_for_request(chat.MODEL_AUTO, "auto", msg, []), "xhigh")

    def test_junior_feedback_uses_xhigh_on_auto(self):
        msg = "Junior is confusing — why are you not finishing your thought?"
        self.assertTrue(junior_model.is_junior_feedback_turn(msg))
        self.assertTrue(chat.pick_xhigh_for_auto(msg))
        self.assertEqual(chat.resolve_reasoning_for_request(chat.MODEL_AUTO, "auto", msg, []), "xhigh")

    def test_summarize_voices_for_user(self):
        text = tts_service.summarize_voices_for_user(
            [{"voice_id": "eve", "name": "Eve"}, {"voice_id": "ara", "name": "Ara"}]
        )
        self.assertIn("eve", text)
        self.assertIn("Ara", text)
        self.assertIn("Default is castor", text)


if __name__ == "__main__":
    unittest.main()
