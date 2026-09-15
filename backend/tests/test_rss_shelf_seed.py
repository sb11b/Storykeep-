from __future__ import annotations

import unittest

from app.services.rss_shelves import INBOX_STARTER_CATEGORIES, UNCATEGORIZED


class RssShelfSeedTests(unittest.TestCase):
    """A new account 500'd on /rss-shelves: Uncategorized was seeded twice."""

    def test_starter_categories_leave_uncategorized_to_the_shelf_helper(self):
        names = [name for name, _ in INBOX_STARTER_CATEGORIES]
        self.assertNotIn(UNCATEGORIZED, names)
        self.assertEqual(names, ["News", "Science"])

    def test_starter_category_names_are_unique(self):
        names = [name for name, _ in INBOX_STARTER_CATEGORIES]
        self.assertEqual(len(names), len(set(names)))


if __name__ == "__main__":
    unittest.main()
