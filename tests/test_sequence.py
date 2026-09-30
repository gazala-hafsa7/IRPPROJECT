"""
tests/test_sequence.py
──────────────────────
Unit tests for the concise sequence parser, serializer, and delay utilities.
"""

import unittest
from keymacro.models.action import ActionType
from keymacro.models.sequence import (
    SequenceParseError,
    normalize_delays,
    parse_sequence,
    serialize_sequence,
    strip_delays,
)


class TestSequence(unittest.TestCase):
    def test_parse_shortcuts_and_keys(self):
        text = """
        # Comments should be ignored
        combo: ctrl+c
        ctrl+shift+esc
        press: enter
        release: shift
        f5
        """
        actions = parse_sequence(text)
        self.assertEqual(len(actions), 5)
        self.assertEqual(actions[0].action_type, ActionType.KEY_COMBO)
        self.assertEqual(actions[0].params["keys"], ["ctrl", "c"])

        self.assertEqual(actions[1].action_type, ActionType.KEY_COMBO)
        self.assertEqual(actions[1].params["keys"], ["ctrl", "shift", "esc"])

        self.assertEqual(actions[2].action_type, ActionType.KEY_PRESS)
        self.assertEqual(actions[2].params["key"], "enter")

        self.assertEqual(actions[3].action_type, ActionType.KEY_RELEASE)
        self.assertEqual(actions[3].params["key"], "shift")

        self.assertEqual(actions[4].action_type, ActionType.KEY_PRESS)
        self.assertEqual(actions[4].params["key"], "f5")

    def test_parse_text_and_launch(self):
        text = """
        type: "Hello, World!"
        launch: notepad.exe
        """
        actions = parse_sequence(text)
        self.assertEqual(len(actions), 2)
        self.assertEqual(actions[0].action_type, ActionType.TYPE_TEXT)
        self.assertEqual(actions[0].params["text"], "Hello, World!")

        self.assertEqual(actions[1].action_type, ActionType.LAUNCH_APP)
        self.assertEqual(actions[1].params["target"], "notepad.exe")

    def test_parse_mouse_actions(self):
        text = """
        click: 400, 300
        click: right, 200, 150
        double_click: 100, 100
        move: 600, 450
        drag: 100, 200 -> 300, 400
        scroll: up
        scroll: -3
        """
        actions = parse_sequence(text)
        self.assertEqual(len(actions), 7)
        self.assertEqual(actions[0].action_type, ActionType.MOUSE_CLICK)
        self.assertEqual(actions[0].params["x"], 400)
        self.assertEqual(actions[0].params["y"], 300)
        self.assertEqual(actions[0].params["button"], "left")

        self.assertEqual(actions[1].params["button"], "right")
        self.assertEqual(actions[2].params["clicks"], 2)

        self.assertEqual(actions[3].action_type, ActionType.MOUSE_MOVE)
        self.assertEqual(actions[4].action_type, ActionType.MOUSE_DRAG)
        self.assertEqual(actions[4].params["x1"], 100)
        self.assertEqual(actions[4].params["x2"], 300)

        self.assertEqual(actions[5].action_type, ActionType.MOUSE_SCROLL)
        self.assertGreater(actions[5].params["dy"], 0)
        self.assertEqual(actions[6].params["dy"], -3)

    def test_parse_plugins_and_waits(self):
        text = """
        plugin: browser.open_url url=https://google.com
        wait: 500ms
        wait: 1.5s
        """
        actions = parse_sequence(text)
        self.assertEqual(len(actions), 3)

        self.assertEqual(actions[0].action_type, ActionType.PLUGIN_ACTION)
        self.assertEqual(actions[0].params["plugin_id"], "browser")
        self.assertEqual(actions[0].params["action_id"], "open_url")
        self.assertEqual(actions[0].params["params"]["url"], "https://google.com")

        self.assertEqual(actions[1].action_type, ActionType.DELAY)
        self.assertEqual(actions[1].params["ms"], 500)
        self.assertEqual(actions[2].params["ms"], 1500)

    def test_syntax_error_reporting(self):
        with self.assertRaises(SequenceParseError) as ctx:
            parse_sequence("invalid_unknown_directive_without_colon")
        self.assertIn("Line 1", str(ctx.exception))

    def test_strip_and_normalize_delays(self):
        text = """
        type: Test
        wait: 200ms
        press: enter
        wait: 500ms
        """
        actions = parse_sequence(text)
        self.assertEqual(len(actions), 4)

        stripped = strip_delays(actions)
        self.assertEqual(len(stripped), 2)
        self.assertEqual(stripped[0].action_type, ActionType.TYPE_TEXT)
        self.assertEqual(stripped[1].action_type, ActionType.KEY_PRESS)

        normalized = normalize_delays(actions, fixed_ms=40)
        self.assertEqual(len(normalized), 4)
        self.assertEqual(normalized[1].params["ms"], 40)
        self.assertEqual(normalized[3].params["ms"], 40)

    def test_round_trip_serialization(self):
        original = """launch: notepad.exe
wait: 250ms
type: Sample
combo: ctrl + s
click: 150, 200
plugin: media.play_pause"""
        actions = parse_sequence(original)
        serialized = serialize_sequence(actions)
        actions2 = parse_sequence(serialized)
        self.assertEqual(len(actions), len(actions2))
        for a1, a2 in zip(actions, actions2):
            self.assertEqual(a1.action_type, a2.action_type)


if __name__ == "__main__":
    unittest.main()
