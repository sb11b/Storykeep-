from __future__ import annotations

import unittest

from app.services import chat
from app.services.cursor_agent_tool import CURSOR_START_TOOL, is_cursor_tool
from app.services.web_search import WEB_SEARCH_TOOL, is_web_search_tool


class CursorDelegateToolAttachTests(unittest.TestCase):
    def test_short_delegate_turn_keeps_cursor_tool_in_attach_filter(self):
        msg = "Start a cursor agent to verify delegate works."
        self.assertTrue(chat.is_short_chat(msg))
        tools = [CURSOR_START_TOOL, WEB_SEARCH_TOOL]
        kept = [
            item
            for item in tools
            if is_web_search_tool(item)
            or is_cursor_tool(item)
        ]
        self.assertEqual(len(kept), 2)
        self.assertTrue(is_cursor_tool(kept[0]))

    def test_delegate_turn_uses_xhigh_reasoning_on_auto(self):
        msg = "Start a cursor agent to add a README note."
        self.assertTrue(chat.pick_xhigh_for_auto(msg))
        self.assertEqual(chat.resolve_reasoning_for_request(chat.MODEL_AUTO, "auto", msg, []), "xhigh")


if __name__ == "__main__":
    unittest.main()
