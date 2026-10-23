"""
tests/test_voice_trigger.py
───────────────────────────
Unit tests for VoiceTrigger, utterance normalization, fuzzy matching,
and SettingsPage voice control integration.
"""

import sys
import unittest
from unittest.mock import MagicMock
from PySide6.QtWidgets import QApplication

from keymacro.models.action import Macro
from keymacro.models.workflow import Workflow
from keymacro.voice.voice_trigger import (
    VoiceTrigger,
    _clean_utterance,
    _fuzzy_find,
    _normalize_name,
)
from gui_qt.pages.settings_page import SettingsPage
from gui_qt.theme.theme_manager import ThemeManager

app = QApplication.instance() or QApplication(sys.argv)


class TestVoiceTrigger(unittest.TestCase):
    def test_normalize_name(self):
        self.assertEqual(_normalize_name("Test Macro!"), "testmacro")
        self.assertEqual(_normalize_name("open_chrome-browser"), "openchromebrowser")

    def test_clean_utterance_wake_phrases(self):
        self.assertEqual(_clean_utterance("Hey KeyMacro, run test macro!"), "test macro")
        self.assertEqual(_clean_utterance("hey key macro please start backup"), "backup")
        self.assertEqual(_clean_utterance("hi keymacro open notepad"), "notepad")
        self.assertEqual(_clean_utterance("run daily_report"), "daily report")
        self.assertEqual(_clean_utterance("hey kmacro execute script"), "script")

    def test_fuzzy_find_exact_and_normalized(self):
        m1 = Macro(name="Daily Backup")
        m2 = Macro(name="open_notepad")
        m3 = Macro(name="Run Tests")
        macros = [m1, m2, m3]

        # Exact (case-insensitive)
        self.assertEqual(_fuzzy_find("daily backup", macros), m1)
        # Normalized (underscores/spaces ignored)
        self.assertEqual(_fuzzy_find("open notepad", macros), m2)
        self.assertEqual(_fuzzy_find("open_notepad", macros), m2)
        # Substring
        self.assertEqual(_fuzzy_find("notepad", macros), m2)
        # Fuzzy close match
        self.assertEqual(_fuzzy_find("run test", macros), m3)
        self.assertEqual(_fuzzy_find("nonexistent", macros), None)

    def test_voice_trigger_process_macro_match(self):
        mock_store = MagicMock()
        target_macro = Macro(name="Quick Screenshot")
        mock_store.list_all.return_value = [target_macro]

        matched_macro = None
        statuses = []

        def on_match(m):
            nonlocal matched_macro
            matched_macro = m

        def on_status(s):
            statuses.append(s)

        trigger = VoiceTrigger(
            macro_store=mock_store,
            on_match=on_match,
            on_status=on_status,
        )

        trigger._process_text("Hey KeyMacro, run Quick Screenshot")
        self.assertEqual(matched_macro, target_macro)
        self.assertTrue(any("matched:Quick Screenshot" in s for s in statuses))

    def test_voice_trigger_process_workflow_match(self):
        mock_store = MagicMock()
        mock_store.list_all.return_value = []

        mock_wf_store = MagicMock()
        target_wf = Workflow(name="Morning Setup", nodes=[])
        mock_wf_store.list_all.return_value = [target_wf]

        matched_wf = None
        statuses = []

        def on_wf_match(wf):
            nonlocal matched_wf
            matched_wf = wf

        def on_status(s):
            statuses.append(s)

        trigger = VoiceTrigger(
            macro_store=mock_store,
            on_match=lambda m: None,
            on_status=on_status,
            workflow_store=mock_wf_store,
            on_workflow_match=on_wf_match,
        )

        trigger._process_text("Hey KeyMacro, start workflow Morning Setup")
        self.assertEqual(matched_wf, target_wf)
        self.assertTrue(any("matched_workflow:Morning Setup" in s for s in statuses))

    def test_voice_trigger_settings_page_integration(self):
        mock_store = MagicMock()
        mock_store.macros_dir = "C:/fake/path"
        mock_store.list_all.return_value = []

        theme_mgr = MagicMock()
        theme_mgr.current_theme = "dark_purple"

        trigger = VoiceTrigger(
            macro_store=mock_store,
            on_match=lambda m: None,
        )

        page = SettingsPage(theme_mgr=theme_mgr, store=mock_store, voice_trigger=trigger)
        self.assertTrue(page._chk_voice_enable.isChecked())

        # Test toggling voice in UI
        page._chk_voice_enable.setChecked(False)
        self.assertFalse(trigger.is_enabled)

        # Test sensitivity slider
        page._slider_sens.setValue(450)
        self.assertEqual(trigger.energy_threshold, 450)


if __name__ == "__main__":
    unittest.main()
