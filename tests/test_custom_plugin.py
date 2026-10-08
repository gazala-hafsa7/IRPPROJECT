"""
tests/test_custom_plugin.py
────────────────────────────
Unit tests for the Custom Tasks Plugin (keymacro.plugins.builtin.custom).
"""

import tempfile
import unittest
from pathlib import Path
from keymacro.plugins.builtin.custom import CustomPlugin
from keymacro.plugins.manager import PluginManager


class TestCustomPlugin(unittest.TestCase):
    def test_custom_plugin_registration(self):
        pm = PluginManager()
        custom = pm.get_plugin("custom")
        self.assertIsNotNone(custom)
        actions = custom.get_actions()
        self.assertIn("open_and_type", actions)
        self.assertIn("type_timestamp", actions)
        self.assertIn("sheet_login", actions)
        self.assertIn("append_log", actions)

    def test_append_log_action(self):
        custom = CustomPlugin()
        with tempfile.TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "test_log.txt"
            res = custom.execute("append_log", {"file_path": str(log_file), "message": "Logged in to shift"})
            self.assertTrue(log_file.exists())
            content = log_file.read_text(encoding="utf-8")
            self.assertIn("Logged in to shift", content)
            self.assertIn("Appended log to", res)

    def test_save_user_custom_action(self):
        custom = CustomPlugin()
        custom.save_user_action(
            action_id="sheet_test_task",
            name="Sheet Test Task",
            description="Testing custom action save",
            target="",
            text_template="Log-in: {time}",
        )
        actions = custom.get_actions()
        self.assertIn("sheet_test_task", actions)
        spec = actions["sheet_test_task"]
        self.assertEqual(spec.name, "Sheet Test Task")


if __name__ == "__main__":
    unittest.main()
