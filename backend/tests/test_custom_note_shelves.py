import unittest

from app.services.custom_note_shelves import normalize_custom_shelves_payload, slugify_shelf_name
from app.services.destination import normalize_destination


class CustomNoteShelvesTests(unittest.TestCase):
    def test_slugify_shelf_name(self):
        self.assertEqual(slugify_shelf_name("Labs"), "labs")
        self.assertEqual(slugify_shelf_name("Larry (the asparagus)"), "larry-the-aspara")

    def test_normalize_custom_shelves_payload(self):
        rows = normalize_custom_shelves_payload([{"id": "labs", "name": "Labs"}])
        self.assertEqual(rows, [{"id": "labs", "name": "Labs"}])

    def test_normalize_destination_accepts_custom_shelf(self):
        class User:
            preferences = {"custom_note_shelves": [{"id": "labs", "name": "Labs"}]}

        self.assertEqual(normalize_destination("labs", User()), "labs")


if __name__ == "__main__":
    unittest.main()
