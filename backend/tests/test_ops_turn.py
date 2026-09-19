from __future__ import annotations

import unittest

from app.services import junior_model, railway_tool


class OpsTurnTests(unittest.TestCase):
    def test_is_ops_turn_for_github_then_deploy(self):
        msg = "Show GitHub status, then deploy Storykeep."
        self.assertTrue(junior_model.is_ops_turn(msg))
        self.assertTrue(railway_tool.wants_railway_deploy(msg))

    def test_build_turn_extras_ops_includes_ops_append(self):
        extras = junior_model.build_turn_extras(
            "Show GitHub status, then deploy Storykeep.",
            memory_block=None,
            chats_enabled=False,
            index_block=None,
            read_meta=None,
            unread_catalog=None,
            calendar_connected=False,
            calendar_tools=False,
            mail_connected=False,
            mail_unread=False,
            unread_mail_md=None,
            search_enabled=True,
            will_search=False,
            railway_enabled=True,
            railway_tools=True,
            github_enabled=True,
            github_tools=True,
            ops_turn=True,
        )
        joined = "\n".join(extras)
        self.assertIn("Owner ops twin turn", joined)
        self.assertIn("Storykeep web", joined)


if __name__ == "__main__":
    unittest.main()
