"""
tests/test_plugins.py
─────────────────────
Unit tests for the PluginManager and built-in plugins.
"""

import tempfile
import unittest
from pathlib import Path
from keymacro.plugins.base import BasePlugin, PluginActionSpec
from keymacro.plugins.manager import PluginManager


class TestPlugins(unittest.TestCase):
    def test_builtin_plugins_loaded(self):
        pm = PluginManager()
        plugins = pm.list_plugins()
        plugin_ids = {p.plugin_id for p in plugins}
        self.assertIn("browser", plugin_ids)
        self.assertIn("system", plugin_ids)
        self.assertIn("media", plugin_ids)
        self.assertIn("notepad", plugin_ids)

    def test_browser_plugin_actions(self):
        pm = PluginManager()
        browser = pm.get_plugin("browser")
        self.assertIsNotNone(browser)
        actions = browser.get_actions()
        self.assertIn("open_url", actions)
        self.assertIn("search", actions)
        self.assertIn("new_tab", actions)

    def test_system_plugin_actions(self):
        pm = PluginManager()
        system = pm.get_plugin("system")
        self.assertIsNotNone(system)
        actions = system.get_actions()
        self.assertIn("volume_mute", actions)
        self.assertIn("volume_up", actions)
        self.assertIn("screenshot", actions)

    def test_custom_user_plugin_loading(self):
        with tempfile.TemporaryDirectory() as tmp_dir:
            plugin_code = '''
from keymacro.plugins.base import BasePlugin, PluginActionSpec

class CustomAppPlugin(BasePlugin):
    plugin_id = "test_custom"
    name = "Test Custom App"
    description = "Testing dynamic user plugins."

    def get_actions(self):
        return {
            "echo": PluginActionSpec(
                action_id="echo",
                name="Echo",
                description="Echo input text",
                params_schema={"msg": "message"},
            )
        }

    def execute(self, action_id, params):
        if action_id == "echo":
            return f"Echo: {params.get('msg', '')}"
        raise ValueError(action_id)
'''
            plugin_file = Path(tmp_dir) / "custom_plugin.py"
            plugin_file.write_text(plugin_code, encoding="utf-8")

            pm = PluginManager(user_plugins_dir=Path(tmp_dir))
            custom = pm.get_plugin("test_custom")
            self.assertIsNotNone(custom)
            self.assertEqual(custom.name, "Test Custom App")

            result = pm.execute("test_custom", "echo", {"msg": "Hello Plugin"})
            self.assertEqual(result, "Echo: Hello Plugin")


if __name__ == "__main__":
    unittest.main()
