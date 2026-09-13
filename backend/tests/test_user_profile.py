from __future__ import annotations

import unittest

from app.services.user_profile import merge_appearance_preferences


class UserProfileTests(unittest.TestCase):
    def test_merge_appearance_preferences_stores_pageBg_and_topBar(self):
        prefs = {"theme": "paper", "appearance": {"rail": {"preset": "dark-oak"}, "font_family": "sans"}}
        merged = merge_appearance_preferences(
            prefs,
            {
                "pageBg": {"preset": "cream"},
                "topBar": {"preset": "slate"},
                "rail": {"preset": "navy"},
                "base_font_size": "lg",
            },
        )
        self.assertEqual(merged["theme"], "paper")
        self.assertEqual(merged["appearance"]["pageBg"], {"preset": "cream"})
        self.assertEqual(merged["appearance"]["topBar"], {"preset": "slate"})
        self.assertEqual(merged["appearance"]["rail"], {"preset": "navy"})
        self.assertEqual(merged["appearance"]["font_family"], "sans")
        self.assertEqual(merged["appearance"]["base_font_size"], "lg")


if __name__ == "__main__":
    unittest.main()
