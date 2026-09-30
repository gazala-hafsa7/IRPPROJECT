"""
tests/test_launcher.py
──────────────────────
Unit tests for AppScanner (Windows installed applications discovery).
"""

import unittest
from keymacro.launcher.app_scanner import AppScanner


class TestLauncher(unittest.TestCase):
    def test_scanner_finds_system_apps(self):
        scanner = AppScanner()
        apps = scanner.scan()
        self.assertGreater(len(apps), 0)

        names = {a.name.lower() for a in apps}
        self.assertIn("notepad", names)
        self.assertIn("calculator", names)
        self.assertIn("task manager", names)

    def test_scanner_search(self):
        scanner = AppScanner()
        results = scanner.search("calc")
        self.assertGreater(len(results), 0)
        self.assertTrue(any("calc" in a.name.lower() for a in results))


if __name__ == "__main__":
    unittest.main()
