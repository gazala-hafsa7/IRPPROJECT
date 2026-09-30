"""
tests/test_app_context.py
─────────────────────────
Unit tests for mouse-only recording, multi-app shortcut context routing,
and macro target application metadata persistence.
"""

import unittest
from unittest.mock import MagicMock, patch
from keymacro.hotkey.context import matches_app
from keymacro.hotkey.listener import HotkeyListener
from keymacro.models.action import Action, ActionType, Macro
from keymacro.models.sequence import (
    parse_sequence_with_metadata,
    serialize_sequence,
)
from keymacro.recorder.recorder import Recorder


class TestAppContextRouting(unittest.TestCase):
    def test_matches_app(self):
        self.assertTrue(matches_app("", "chrome.exe", "Google Chrome"))
        self.assertTrue(matches_app("global", "chrome.exe", "Google Chrome"))
        self.assertTrue(matches_app("chrome.exe", "chrome.exe", "Google Chrome"))
        self.assertTrue(matches_app("chrome", "chrome.exe", "New Tab - Google Chrome"))
        self.assertTrue(matches_app("spotify", "spotify.exe", "Spotify Free"))
        self.assertFalse(matches_app("spotify.exe", "chrome.exe", "Google Chrome"))
        self.assertFalse(matches_app("notepad.exe", "spotify.exe", "Spotify"))

    def test_same_shortcut_different_apps(self):
        listener = HotkeyListener()

        chrome_cb = MagicMock()
        spotify_cb = MagicMock()
        global_cb = MagicMock()

        # Register exact same shortcut 'ctrl+q' for 3 different targets
        listener.register("ctrl+q", chrome_cb, target_app="chrome.exe", macro_id="m1")
        listener.register("ctrl+q", spotify_cb, target_app="spotify.exe", macro_id="m2")
        listener.register("ctrl+q", global_cb, target_app="global", macro_id="m3")

        # Simulate keys held: 'ctrl' and 'q'
        listener._held_keys = {"ctrl", "q"}

        # 1. Active app is Chrome
        with patch("keymacro.hotkey.listener.get_active_window_info", return_value=("chrome.exe", "Google Chrome")):
            match = listener._find_match()
            self.assertIsNotNone(match)
            self.assertEqual(match.macro_id, "m1")

        # 2. Active app is Spotify
        with patch("keymacro.hotkey.listener.get_active_window_info", return_value=("spotify.exe", "Spotify Free")):
            match = listener._find_match()
            self.assertIsNotNone(match)
            self.assertEqual(match.macro_id, "m2")

        # 3. Active app is Notepad (fallback to Global)
        with patch("keymacro.hotkey.listener.get_active_window_info", return_value=("notepad.exe", "Untitled - Notepad")):
            match = listener._find_match()
            self.assertIsNotNone(match)
            self.assertEqual(match.macro_id, "m3")

    def test_ctrl_combo_key_normalization(self):
        from pynput.keyboard import KeyCode
        listener = HotkeyListener()

        # Simulate Ctrl + O + G keystrokes where Ctrl converts chars to control codes \x0f and \x07
        ctrl_o_key = KeyCode(char="\x0f", vk=79)
        ctrl_g_key = KeyCode(char="\x07", vk=71)

        self.assertEqual(listener._key_to_name(ctrl_o_key), "o")
        self.assertEqual(listener._key_to_name(ctrl_g_key), "g")


class TestMouseOnlyRecorder(unittest.TestCase):
    def test_mouse_only_ignores_keyboard_events(self):
        import time
        recorder = Recorder(name="Mouse Only Test", mouse_only=True)
        recorder._recording = True
        recorder._last_event_time = time.perf_counter()

        # Trigger keyboard press/release handlers directly
        recorder._on_key_press("a")
        recorder._on_key_release("a")

        # Trigger mouse click handler directly
        from pynput.mouse import Button
        recorder._on_mouse_click(100, 200, Button.left, pressed=True)

        macro = recorder.stop()
        # Verify that only the mouse action was recorded
        self.assertEqual(macro.action_count, 1)
        self.assertEqual(macro.actions[0].action_type, ActionType.MOUSE_CLICK)
        self.assertEqual(macro.actions[0].params["x"], 100)
        self.assertEqual(macro.actions[0].params["y"], 200)


class TestTargetAppSequence(unittest.TestCase):
    def test_parse_and_serialize_target_app(self):
        script = """# target_app: chrome.exe
click: 100, 200
plugin: browser.open_url url=https://example.com
"""
        actions, meta = parse_sequence_with_metadata(script)
        self.assertEqual(len(actions), 2)
        self.assertEqual(meta.get("target_app"), "chrome.exe")

        reserialized = serialize_sequence(actions, target_app=meta["target_app"])
        self.assertIn("# target_app: chrome.exe", reserialized)
        self.assertIn("click: 100, 200", reserialized)


if __name__ == "__main__":
    unittest.main()
