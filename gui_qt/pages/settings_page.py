"""
gui_qt/pages/settings_page.py
─────────────────────────────
Settings and preferences page: Theme customization (Light & Pastel vs Dark & Purple),
storage directory management, and system safety shield information.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import TYPE_CHECKING
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from gui_qt.theme.theme_manager import THEME_DARK_PURPLE, THEME_LIGHT_PASTEL

if TYPE_CHECKING:
    from gui_qt.theme.theme_manager import ThemeManager
    from keymacro.storage.macro_store import MacroStore


class SettingsPage(QWidget):
    """Configuration interface for visual themes and storage."""

    def __init__(
        self,
        theme_mgr: "ThemeManager",
        store: "MacroStore",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._theme_mgr = theme_mgr
        self._store = store

        self._build_ui()
        self._sync_theme_radio()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(18)

        # ── Title ─────────────────────────────────────────────────────────────
        title_lbl = QLabel("Settings & Appearance")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        main_layout.addWidget(title_lbl)

        # ── Appearance & Themes Card ──────────────────────────────────────────
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
        self._radio_dark.setStyleSheet("font-weight: 600; font-size: 13px;")
        self._radio_dark.toggled.connect(self._on_theme_toggled)
        options_layout.addWidget(self._radio_dark)

        # Light & Pastel Radio
        self._radio_light = QRadioButton("Light & Pastel  (Soft Lavender & Blush Accents)")
        self._radio_light.setStyleSheet("font-weight: 600; font-size: 13px;")
        self._radio_light.toggled.connect(self._on_theme_toggled)
        options_layout.addWidget(self._radio_light)

        options_layout.addStretch()
        theme_layout.addLayout(options_layout)

        main_layout.addWidget(theme_card)

        # ── Storage & Paths Card ──────────────────────────────────────────────
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

        # ── Safety Shield Information Card ────────────────────────────────────
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

        # ── About Card ────────────────────────────────────────────────────────
        about_card = QFrame()
        about_card.setObjectName("Card")
        about_layout = QVBoxLayout(about_card)
        about_layout.setContentsMargins(18, 14, 18, 14)
        about_layout.setSpacing(6)

        about_title = QLabel("About KeyMacro")
        about_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        about_layout.addWidget(about_title)

        about_desc = QLabel(
            f"KeyMacro v2.0 • Python {sys.version.split()[0]} • PySide6 UI Redesign (Qt6)"
        )
        about_desc.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        about_layout.addWidget(about_desc)

        main_layout.addWidget(about_card)
        main_layout.addStretch()

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
