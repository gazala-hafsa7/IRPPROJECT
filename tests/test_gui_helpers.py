"""
tests/test_gui_helpers.py
─────────────────────────
Unit tests for GUI widget helpers and URL pasting functions.
"""

import unittest
from keymacro.gui.widget_helpers import is_url, sanitize_url


class TestGuiWidgetHelpers(unittest.TestCase):
    def test_is_url(self):
        self.assertTrue(is_url("https://google.com"))
        self.assertTrue(is_url("http://example.com/test?a=1"))
        self.assertTrue(is_url("www.github.com"))
        self.assertTrue(is_url("youtube.com"))
        self.assertFalse(is_url(""))
        self.assertFalse(is_url("just a random string"))

    def test_sanitize_url(self):
        self.assertEqual(sanitize_url("  https://google.com  "), "https://google.com")
        self.assertEqual(sanitize_url('"www.github.com"'), "https://www.github.com")
        self.assertEqual(sanitize_url("example.org/path"), "https://example.org/path")
        self.assertEqual(sanitize_url(""), "")


if __name__ == "__main__":
    unittest.main()
