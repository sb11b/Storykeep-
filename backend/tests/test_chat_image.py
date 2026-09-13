from __future__ import annotations

import unittest
from unittest.mock import patch
from uuid import uuid4

from fastapi import HTTPException

from app.services.chat_image import (
    CLARIFY_EDIT_OR_GENERATE,
    collect_thread_images,
    edit_prompt_for,
    image_tool_intent,
    inspired_prompt_for,
    markdown_for_result,
    produce_chat_image,
    run_intercepted_chat_image,
    ChatImageResult,
)


class ChatImageIntentTests(unittest.TestCase):
    def test_make_me_look_older_with_selfie_is_edit(self):
        self.assertEqual(image_tool_intent("make me look older", True), "edit")
        self.assertEqual(image_tool_intent("age this picture", True), "edit")
        self.assertEqual(image_tool_intent("make this photo older", True), "edit")
        self.assertEqual(image_tool_intent("edit this photo", True), "edit")

    def test_make_me_look_older_without_photo_asks_once(self):
        self.assertEqual(image_tool_intent("make me look older", False), "clarify")
        self.assertEqual(image_tool_intent("make this look older", False), "clarify")
        self.assertEqual(image_tool_intent("make it older", False), "clarify")

    def test_whats_in_this_photo_is_vision_only(self):
        self.assertIsNone(image_tool_intent("what's in this picture?", True))
        self.assertIsNone(image_tool_intent("What is in this photo", True))
        self.assertIsNone(image_tool_intent("describe this selfie", True))
        self.assertIsNone(image_tool_intent("what do you see", True))

    def test_generate_without_image_is_generate(self):
        self.assertEqual(image_tool_intent("generate an image of a red notebook", False), "generate")
        self.assertEqual(image_tool_intent("Generate a red notebook", False), "generate")

    def test_photo_metadata_stays_chat(self):
        self.assertIsNone(image_tool_intent("Tell me about photo metadata", False))
        self.assertIsNone(image_tool_intent("what is a picture element in HTML", False))
        self.assertIsNone(image_tool_intent("older python versions", False))

    def test_generate_with_image_is_edit(self):
        self.assertEqual(image_tool_intent("generate an image in this style", True), "edit")

    def test_recreate_with_photo_is_edit(self):
        self.assertEqual(image_tool_intent("recreating an image", True), "edit")
        self.assertEqual(image_tool_intent("recreate this photo older", True), "edit")
        self.assertEqual(image_tool_intent("from this photo make me older", True), "edit")

    def test_recreate_without_photo_is_generate(self):
        self.assertEqual(image_tool_intent("recreating an image", False), "generate")

    def test_older_with_attached_photo_is_edit(self):
        self.assertEqual(image_tool_intent("older", True), "edit")
        self.assertEqual(image_tool_intent("make them look older", True), "edit")

    def test_how_old_stays_vision(self):
        self.assertIsNone(image_tool_intent("how old is this person", True))
        self.assertIsNone(image_tool_intent("Please look at selfie.jpg.", True))

    def test_recreate_a_function_is_not_image_gen(self):
        self.assertIsNone(image_tool_intent("recreate this function in python", False))

    def test_school_coding_imagine_is_not_image_gen(self):
        self.assertIsNone(image_tool_intent("imagine we have a linked list", False))
        self.assertIsNone(image_tool_intent("debug this python homework", False))

    def test_collects_prior_user_image_not_assistant(self):
        media_id = uuid4()
        history = [
            {
                "role": "user",
                "content": "selfie",
                "files": [{"media_id": media_id, "kind": "image", "filename": "me.jpg"}],
            },
            {"role": "assistant", "content": "ok", "files": [{"media_id": uuid4(), "kind": "image"}]},
            {"role": "user", "content": "make me look older", "files": []},
        ]
        found = collect_thread_images([], history)
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["media_id"], media_id)

    def test_current_turn_image_wins(self):
        older = uuid4()
        newer = uuid4()
        current = [{"media_id": newer, "kind": "image"}]
        history = [
            {"role": "user", "content": "old", "files": [{"media_id": older, "kind": "image"}]},
            {"role": "user", "content": "new", "files": current},
        ]
        found = collect_thread_images(current, history)
        self.assertEqual(found[0]["media_id"], newer)

    def test_edit_prompt_keeps_identity(self):
        prompt = edit_prompt_for("make me look older")
        self.assertIn("THIS exact photograph", prompt)
        self.assertIn("keep identity", prompt)
        self.assertIn("gray in the beard", prompt)
        self.assertNotIn("FaceApp", prompt)

    def test_inspired_markdown_is_not_a_perfect_edit(self):
        media_id = uuid4()
        text = markdown_for_result(
            ChatImageResult(payload=b"x", kind="inspired", prompt="older portrait"),
            media_id,
        )
        self.assertIn("inspired by your photo", text)
        self.assertIn("not a pixel-perfect edit", text)
        self.assertIn(f"/api/v1/media/{media_id}", text)
        self.assertNotIn("FaceApp", text)

    def test_produce_falls_back_to_t2i_when_edits_unsupported(self):
        data_url = "data:image/jpeg;base64,abc"
        with patch("app.services.imagine.edit_image_bytes", side_effect=HTTPException(status_code=400, detail="no edits")):
            with patch("app.services.imagine.describe_image_briefly", return_value="man with a dark beard"):
                with patch("app.services.imagine.generate_image_bytes", return_value=b"img") as generate:
                    result = produce_chat_image("edit", "make me look older", data_url)
        self.assertEqual(result.kind, "inspired")
        self.assertEqual(result.payload, b"img")
        self.assertIn("man with a dark beard", result.prompt)
        generate.assert_called_once()

    def test_produce_falls_back_to_t2i_when_edits_time_out(self):
        data_url = "data:image/jpeg;base64,abc"
        with patch("app.services.imagine.edit_image_bytes", side_effect=HTTPException(status_code=504, detail="Timed out waiting for the image.")):
            with patch("app.services.imagine.describe_image_briefly", return_value="man with a dark beard"):
                with patch("app.services.imagine.generate_image_bytes", return_value=b"img"):
                    result = produce_chat_image("edit", "make me look older", data_url)
        self.assertEqual(result.kind, "inspired")
        self.assertEqual(result.payload, b"img")

    def test_auth_error_does_not_fallback_or_mention_faceapp(self):
        with patch("app.services.imagine.edit_image_bytes", side_effect=HTTPException(status_code=401, detail="xAI auth failed")):
            with self.assertRaises(HTTPException) as raised:
                produce_chat_image("edit", "make me look older", "data:image/jpeg;base64,abc")
        self.assertEqual(raised.exception.status_code, 401)
        self.assertNotIn("FaceApp", str(raised.exception.detail))

    def test_inspired_prompt_does_not_send_people_away(self):
        text = inspired_prompt_for("make me look older", "a man with a beard")
        self.assertNotIn("FaceApp", text)
        self.assertIn("looking older", text)

    def test_intercepted_edit_without_photo_still_guards_the_job(self):
        with patch("app.services.imagine.require_imagine_key", return_value="xai-test"):
            with patch("app.services.imagine.enforce_imagine_rate_limit"):
                with self.assertRaises(HTTPException) as raised:
                    run_intercepted_chat_image(
                        user_id=uuid4(),
                        persist=False,
                        conversation_id=None,
                        user_text="make me look older",
                        intent="edit",
                        thread_images=[],
                    )
        self.assertEqual(raised.exception.status_code, 400)
        self.assertNotIn("FaceApp", str(raised.exception.detail))

    def test_clarify_copy_is_a_choice_not_a_hard_block(self):
        self.assertEqual(
            CLARIFY_EDIT_OR_GENERATE,
            "Generate a new older-looking picture, or attach one to edit?",
        )
        self.assertNotIn("Attach a photo first", CLARIFY_EDIT_OR_GENERATE)


if __name__ == "__main__":
    unittest.main()
