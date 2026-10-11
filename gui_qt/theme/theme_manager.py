"""
gui_qt/theme/theme_manager.py
──────────────────────────────
Theme manager supporting Light & Pastel and Dark & Purple themes
with QSettings persistence and runtime hot-switching.
"""

from __future__ import annotations

from pathlib import Path
from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication


THEME_DIR = Path(__file__).resolve().parent

THEME_LIGHT_PASTEL = "light_pastel"
THEME_DARK_PURPLE = "dark_purple"


class ThemeManager(QObject):
    """Manages application stylesheet switching and persistence."""

    theme_changed = Signal(str)

    def __init__(self, app: QApplication | None = None) -> None:
        super().__init__()
        self._app = app or QApplication.instance()
        self._settings = QSettings("KeyMacro", "KeyMacroQt")
        self._current_theme = self._settings.value("theme", THEME_DARK_PURPLE)

    @property
    def current_theme(self) -> str:
        return self._current_theme

    @property
    def is_dark(self) -> bool:
        return self._current_theme == THEME_DARK_PURPLE

    def apply_current_theme(self) -> None:
        """Apply the currently active theme to the QApplication."""
        self.set_theme(self._current_theme)

    def toggle_theme(self) -> str:
        """Switch between Light & Pastel and Dark & Purple."""
        next_theme = (
            THEME_LIGHT_PASTEL
            if self._current_theme == THEME_DARK_PURPLE
            else THEME_DARK_PURPLE
        )
        self.set_theme(next_theme)
        return next_theme

    def set_theme(self, theme_name: str) -> None:
        """Load and apply stylesheet for the given theme name."""
        if theme_name not in (THEME_LIGHT_PASTEL, THEME_DARK_PURPLE):
            theme_name = THEME_DARK_PURPLE

        qss_file = THEME_DIR / f"{theme_name}.qss"
        if qss_file.exists():
            stylesheet = qss_file.read_text(encoding="utf-8")
        else:
            stylesheet = ""

        if self._app:
            self._app.setStyleSheet(stylesheet)

        self._current_theme = theme_name
        self._settings.setValue("theme", theme_name)
        self.theme_changed.emit(theme_name)
