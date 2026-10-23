"""
gui_qt/pages/settings_page.py
─────────────────────────────
Settings and preferences page: Theme customization, Speech Recognition & Voice Commands,
storage directory management, and system safety shield information.
"""

from __future__ import annotations

import os
import sys
import threading
from pathlib import Path
from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QSlider,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme.theme_manager import THEME_DARK_PURPLE, THEME_LIGHT_PASTEL

if TYPE_CHECKING:
    from gui_qt.theme.theme_manager import ThemeManager
    from keymacro.storage.macro_store import MacroStore
    from keymacro.voice.voice_trigger import VoiceTrigger


class SettingsPage(QWidget):
    """Configuration interface for visual themes, speech recognition, and storage."""

    voice_toggled = Signal(bool)

    def __init__(
        self,
        theme_mgr: "ThemeManager",
        store: "MacroStore",
        voice_trigger: "VoiceTrigger | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self._store = store
        self._voice_trigger = voice_trigger
        self._is_testing_mic = False

        self._build_ui()
        self._sync_theme_radio()
        self.sync_voice_ui()

    def set_voice_trigger(self, trigger: "VoiceTrigger") -> None:
        """Bind or update the voice trigger instance."""
        self._voice_trigger = trigger
        self.sync_voice_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(18)

        # ── Title ─────────────────────────────────────────────────────────────
        title_lbl = QLabel("Settings & Appearance")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title_lbl)

        # ── 1. Speech Recognition & Voice Commands Card ───────────────────────
        voice_card = QFrame()
        voice_card.setObjectName("Card")
        voice_layout = QVBoxLayout(voice_card)
        voice_layout.setContentsMargins(18, 16, 18, 16)
        voice_layout.setSpacing(14)

        voice_title = QLabel("🎙  Speech Recognition & Voice Commands")
        voice_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #8B5CF6;")
        voice_layout.addWidget(voice_title)

        voice_desc = QLabel(
            "Trigger and run macros hands-free using your voice. Speak phrases like "
            "<b>'Hey KeyMacro, run &lt;macro_name&gt;'</b> into your microphone."
        )
        voice_desc.setStyleSheet("color: #9CA3AF; font-size: 12px; line-height: 1.4;")
        voice_layout.addWidget(voice_desc)

        # Enable / Disable Checkbox Row
        enable_row = QHBoxLayout()
        self._chk_voice_enable = QCheckBox("Enable Voice Command Listener (Microphone Active)")
        self._chk_voice_enable.setStyleSheet("font-size: 13px; font-weight: 600;")
        self._chk_voice_enable.toggled.connect(self._on_voice_enable_toggled)
        enable_row.addWidget(self._chk_voice_enable)

        enable_row.addStretch()

        self._lbl_voice_status = QLabel("● Checking microphone status…")
        self._lbl_voice_status.setStyleSheet("font-size: 12px; font-weight: bold; color: #10B981;")
        enable_row.addWidget(self._lbl_voice_status)
        voice_layout.addLayout(enable_row)

        # Microphone Sensitivity Slider Row
        sens_frame = QFrame()
        sens_frame.setStyleSheet("background-color: rgba(255,255,255,0.03); border-radius: 8px; padding: 6px 10px;")
        sens_layout = QHBoxLayout(sens_frame)
        sens_layout.setContentsMargins(8, 6, 8, 6)
        sens_layout.setSpacing(12)

        lbl_sens = QLabel("Microphone Sensitivity:")
        lbl_sens.setStyleSheet("font-size: 12px; font-weight: bold;")
        sens_layout.addWidget(lbl_sens)

        self._slider_sens = QSlider(Qt.Horizontal)
        self._slider_sens.setRange(50, 1000)
        self._slider_sens.setValue(300)
        self._slider_sens.setSingleStep(25)
        self._slider_sens.setToolTip("Adjust microphone energy threshold (lower = more sensitive to soft voices)")
        self._slider_sens.valueChanged.connect(self._on_sensitivity_changed)
        sens_layout.addWidget(self._slider_sens, stretch=1)

        self._lbl_sens_val = QLabel("Normal (300)")
        self._lbl_sens_val.setFixedWidth(100)
        self._lbl_sens_val.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        sens_layout.addWidget(self._lbl_sens_val)

        voice_layout.addWidget(sens_frame)

        # Test Microphone Row
        test_row = QHBoxLayout()
        test_row.setSpacing(14)

        self._btn_test_mic = QPushButton("🎙  Test Microphone & Recognition")
        self._btn_test_mic.setCursor(Qt.PointingHandCursor)
        self._btn_test_mic.setStyleSheet("padding: 6px 14px; font-weight: bold;")
        self._btn_test_mic.clicked.connect(self._test_microphone)
        test_row.addWidget(self._btn_test_mic)

        self._lbl_test_result = QLabel("Click 'Test Microphone' and speak clearly to verify recognition.")
        self._lbl_test_result.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        test_row.addWidget(self._lbl_test_result, stretch=1)

        voice_layout.addLayout(test_row)

        # Voice Commands Cheat Sheet
        guide_box = QFrame()
        guide_box.setStyleSheet("background-color: rgba(139, 92, 246, 0.07); border: 1px solid rgba(139, 92, 246, 0.25); border-radius: 6px; padding: 10px;")
        guide_layout = QVBoxLayout(guide_box)
        guide_layout.setContentsMargins(10, 8, 10, 8)
        guide_layout.setSpacing(4)

        lbl_guide_title = QLabel("Supported Voice Commands:")
        lbl_guide_title.setStyleSheet("font-weight: bold; font-size: 12px; color: #A78BFA;")
        guide_layout.addWidget(lbl_guide_title)

        guide_text = QLabel(
            "• <b>Run Macro:</b> <i>'Hey KeyMacro, run &lt;name&gt;'</i> or <i>'Run &lt;name&gt;'</i><br>"
            "• <b>Run Workflow:</b> <i>'Hey KeyMacro, start workflow &lt;name&gt;'</i><br>"
            "• <b>Wake Phrases:</b> 'Hey KeyMacro', 'Hi KeyMacro', 'OK KeyMacro', 'Hey Macro'"
        )
        guide_text.setStyleSheet("font-size: 11px; color: #D1D5DB; line-height: 1.4;")
        guide_layout.addWidget(guide_text)

        voice_layout.addWidget(guide_box)
        main_layout.addWidget(voice_card)

        # ── 2. Appearance & Themes Card ───────────────────────────────────────
        theme_card = QFrame()
        theme_card.setObjectName("Card")
        theme_layout = QVBoxLayout(theme_card)
        theme_layout.setContentsMargins(18, 16, 18, 16)
        theme_layout.setSpacing(14)

        theme_title = QLabel("🎨  Visual Theme")
        theme_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        theme_layout.addWidget(theme_title)

        theme_desc = QLabel(
            "Select the application visual palette. Your preference is automatically "
            "saved and restored upon application launch."
        )
        theme_desc.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        theme_layout.addWidget(theme_desc)

        options_layout = QHBoxLayout()
        options_layout.setSpacing(20)

        # Dark & Purple Radio
        self._radio_dark = QRadioButton("Dark & Purple  (Graphite & Electric Violet)")
        self._radio_dark.toggled.connect(self._on_theme_toggled)
        options_layout.addWidget(self._radio_dark)

        # Light & Pastel Radio
        self._radio_light = QRadioButton("Light & Pastel  (Soft Lavender & Blush Accents)")
        self._radio_light.toggled.connect(self._on_theme_toggled)
        options_layout.addWidget(self._radio_light)

        options_layout.addStretch()
        theme_layout.addLayout(options_layout)

        main_layout.addWidget(theme_card)

        # ── 3. Storage & Paths Card ───────────────────────────────────────────
        storage_card = QFrame()
        storage_card.setObjectName("Card")
        storage_layout = QVBoxLayout(storage_card)
        storage_layout.setContentsMargins(18, 16, 18, 16)
        storage_layout.setSpacing(12)

        storage_title = QLabel("📁  Storage & Data Directories")
        storage_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        storage_layout.addWidget(storage_title)

        macros_path = str(self._store.macros_dir)
        path_grid = QGridLayout()
        path_grid.setSpacing(10)

        path_grid.addWidget(QLabel("Macro Definitions:"), 0, 0)
        lbl_macro_path = QLabel(f"<code>{macros_path}</code>")
        lbl_macro_path.setTextInteractionFlags(Qt.TextSelectableByMouse)
        path_grid.addWidget(lbl_macro_path, 0, 1)

        btn_open_store = QPushButton("Open in Explorer")
        btn_open_store.clicked.connect(lambda: self._open_folder(macros_path))
        path_grid.addWidget(btn_open_store, 0, 2)

        storage_layout.addLayout(path_grid)
        main_layout.addWidget(storage_card)

        # ── 4. Safety Shield Information Card ─────────────────────────────────
        safety_card = QFrame()
        safety_card.setObjectName("Card")
        safety_layout = QVBoxLayout(safety_card)
        safety_layout.setContentsMargins(18, 16, 18, 16)
        safety_layout.setSpacing(12)

        safety_title = QLabel("🛡  Safety & Security Shield")
        safety_title.setStyleSheet("font-size: 15px; font-weight: bold; color: #10B981;")
        safety_layout.addWidget(safety_title)

        safety_text = QLabel(
            "• <b>Protected Paths:</b> Hard-blocks automation scripts from touching system roots "
            "(<code>C:\\Windows</code>, <code>C:\\Program Files</code>, etc.).<br>"
            "• <b>Automated Backups:</b> Backs up targeted files with timestamps prior to running destructive operations.<br>"
            "• <b>High-Risk Gate:</b> Replay strictly requires interactive confirmation before high-risk actions execute."
        )
        safety_text.setStyleSheet("color: #9CA3AF; font-size: 12px; line-height: 1.5;")
        safety_layout.addWidget(safety_text)

        main_layout.addWidget(safety_card)

        # ── 5. About Card ─────────────────────────────────────────────────────
        about_card = QFrame()
        about_card.setObjectName("Card")
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(18, 14, 18, 14)
        about_layout.setSpacing(6)

        about_title = QLabel("About KeyMacro")
        about_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        about_layout.addWidget(about_title)

        about_desc = QLabel(
            f"KeyMacro v2.0 • Python {sys.version.split()[0]} • PySide6 UI (Qt6) • SpeechRecognition Enabled"
        )
        about_desc.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        about_layout.addWidget(about_desc)

        main_layout.addWidget(about_card)
        main_layout.addStretch()

    # ── Voice Trigger UI Synchronization ──────────────────────────────────────

    def sync_voice_ui(self) -> None:
        """Sync UI controls with the current voice trigger state."""
        if not self._voice_trigger:
            self._chk_voice_enable.setEnabled(False)
            self._chk_voice_enable.setChecked(False)
            self._lbl_voice_status.setText("● Voice trigger unavailable")
            self._lbl_voice_status.setStyleSheet("color: #9CA3AF; font-size: 12px;")
            self._btn_test_mic.setEnabled(False)
            return

        if not self._voice_trigger.is_available:
            self._chk_voice_enable.setEnabled(False)
            self._chk_voice_enable.setChecked(False)
            self._lbl_voice_status.setText("● Packages missing (pip install SpeechRecognition sounddevice)")
            self._lbl_voice_status.setStyleSheet("color: #F59E0B; font-size: 12px;")
            self._btn_test_mic.setEnabled(False)
            return

        self._chk_voice_enable.setEnabled(True)
        self._chk_voice_enable.blockSignals(True)
        self._chk_voice_enable.setChecked(self._voice_trigger.is_enabled)
        self._chk_voice_enable.blockSignals(False)
        self._btn_test_mic.setEnabled(True)

        # Sync threshold
        self._slider_sens.blockSignals(True)
        self._slider_sens.setValue(self._voice_trigger.energy_threshold)
        self._slider_sens.blockSignals(False)
        self._update_sens_label(self._voice_trigger.energy_threshold)

        if self._voice_trigger.is_enabled:
            self._lbl_voice_status.setText("● Active & Listening (Microphone On)")
            self._lbl_voice_status.setStyleSheet("color: #10B981; font-weight: bold; font-size: 12px;")
        else:
            self._lbl_voice_status.setText("● Paused / Disabled")
            self._lbl_voice_status.setStyleSheet("color: #9CA3AF; font-weight: bold; font-size: 12px;")

    def update_voice_status(self, status: str) -> None:
        """Called live when voice trigger fires status updates."""
        if not self._voice_trigger or not self._voice_trigger.is_enabled:
            return

        if status == "listening":
            self._lbl_voice_status.setText("● Listening (Microphone Active)")
            self._lbl_voice_status.setStyleSheet("color: #10B981; font-weight: bold; font-size: 12px;")
        elif status == "processing":
            self._lbl_voice_status.setText("● Hearing Speech… Processing")
            self._lbl_voice_status.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 12px;")
        elif status.startswith("matched:"):
            parts = status.split(":", 2)
            name = parts[1]
            self._lbl_voice_status.setText(f"● Executing Macro '{name}'")
            self._lbl_voice_status.setStyleSheet("color: #8B5CF6; font-weight: bold; font-size: 12px;")
        elif status.startswith("matched_workflow:"):
            parts = status.split(":", 2)
            name = parts[1]
            self._lbl_voice_status.setText(f"● Executing Workflow '{name}'")
            self._lbl_voice_status.setStyleSheet("color: #8B5CF6; font-weight: bold; font-size: 12px;")
        elif status.startswith("error:"):
            err = status[6:][:40]
            self._lbl_voice_status.setText(f"● Voice Warning: {err}")
            self._lbl_voice_status.setStyleSheet("color: #F59E0B; font-weight: bold; font-size: 12px;")
        elif status == "stopped":
            self._lbl_voice_status.setText("● Paused / Disabled")
            self._lbl_voice_status.setStyleSheet("color: #9CA3AF; font-weight: bold; font-size: 12px;")

    def _on_voice_enable_toggled(self, checked: bool) -> None:
        if not self._voice_trigger:
            return
        self._voice_trigger.is_enabled = checked
        self.sync_voice_ui()
        self.voice_toggled.emit(checked)

    def _on_sensitivity_changed(self, value: int) -> None:
        self._update_sens_label(value)
        if self._voice_trigger:
            self._voice_trigger.energy_threshold = value

    def _update_sens_label(self, val: int) -> None:
        if val <= 150:
            level = "High"
        elif val <= 400:
            level = "Normal"
        else:
            level = "Low"
        self._lbl_sens_val.setText(f"{level} ({val})")

    def _test_microphone(self) -> None:
        """Run a 4-second interactive test of microphone and speech recognition."""
        if not self._voice_trigger or not self._voice_trigger.is_available or self._is_testing_mic:
            return

        self._is_testing_mic = True
        self._btn_test_mic.setEnabled(False)
        self._btn_test_mic.setText("🎙  Listening…")
        self._lbl_test_result.setText("🔴 Listening… Please speak into your microphone now (4s)…")
        self._lbl_test_result.setStyleSheet("color: #38BDF8; font-weight: bold; font-size: 12px;")

        # Temporarily pause background trigger so test owns microphone cleanly
        was_running = self._voice_trigger.is_running
        if was_running:
            self._voice_trigger.stop()

        def _worker():
            # Give background thread a moment to release microphone device
            time.sleep(0.3)
            success, result_text = self._voice_trigger.test_listen(timeout=4.0, phrase_time_limit=4.0)
            QTimer.singleShot(0, lambda: self._on_test_done(success, result_text, was_running))

        import time
        threading.Thread(target=_worker, daemon=True).start()

    def _on_test_done(self, success: bool, result_text: str, resume_background: bool) -> None:
        self._is_testing_mic = False
        self._btn_test_mic.setEnabled(True)
        self._btn_test_mic.setText("🎙  Test Microphone & Recognition")

        if success:
            self._lbl_test_result.setText(f'✅ Heard: "{result_text}" — Speech Recognition working perfectly!')
            self._lbl_test_result.setStyleSheet("color: #10B981; font-weight: bold; font-size: 12px;")
        else:
            self._lbl_test_result.setText(f"⚠️ {result_text}")
            self._lbl_test_result.setStyleSheet("color: #F59E0B; font-weight: bold; font-size: 12px;")

        if resume_background and self._voice_trigger and self._voice_trigger.is_enabled:
            self._voice_trigger.start()
        self.sync_voice_ui()

    # ── Themes & Folders ──────────────────────────────────────────────────────

    def _sync_theme_radio(self) -> None:
        if self._theme_mgr.current_theme == THEME_DARK_PURPLE:
            self._radio_dark.setChecked(True)
        else:
            self._radio_light.setChecked(True)

    def _on_theme_toggled(self) -> None:
        if self._radio_dark.isChecked():
            self._theme_mgr.set_theme(THEME_DARK_PURPLE)
        else:
            self._theme_mgr.set_theme(THEME_LIGHT_PASTEL)

    def _open_folder(self, folder_path: str) -> None:
        path = Path(folder_path)
        path.mkdir(parents=True, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(str(path))
