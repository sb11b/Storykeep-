from __future__ import annotations

import unittest

from app.services.user_profile import merge_appearance_preferences


class UserProfileTests(unittest.TestCase):
    def test_merge_appearance_preferences_updates_nested_settings(self):
        prefs = {"theme": "paper", "appearance": {"rail_preset": "dark-oak", "font_family": "sans"}}
        merged = merge_appearance_preferences(prefs, {"rail_preset": "navy", "base_font_size": "lg"})
        self.assertEqual(merged["theme"], "paper")
        self.assertEqual(
            merged["appearance"],
            {"rail_preset": "navy", "font_family": "sans", "base_font_size": "lg"},
        )


if __name__ == "__main__":
    unittest.main()
