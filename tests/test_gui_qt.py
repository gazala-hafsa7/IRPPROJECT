"""
tests/test_gui_qt.py
────────────────────
Unit tests for PySide6 GUI components, theme manager, and engine bridge.
"""

import os
os.environ["QT_QPA_PLATFORM"] = "offscreen"

import pytest
from PySide6.QtWidgets import QApplication

from gui_qt.app import KeyMacroQtApp
from gui_qt.theme.theme_manager import THEME_DARK_PURPLE, THEME_LIGHT_PASTEL, ThemeManager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_theme_manager(qapp):
    theme_mgr = ThemeManager(qapp)
    theme_mgr.set_theme(THEME_DARK_PURPLE)
    assert theme_mgr.current_theme == THEME_DARK_PURPLE
    assert theme_mgr.is_dark is True

    next_theme = theme_mgr.toggle_theme()
    assert next_theme == THEME_LIGHT_PASTEL
    assert theme_mgr.is_dark is False

    next_theme = theme_mgr.toggle_theme()
    assert next_theme == THEME_DARK_PURPLE


def test_gui_qt_app_startup(qapp):
    qt_app = KeyMacroQtApp()
    assert qt_app.main_window is not None
    assert "KeyMacro" in qt_app.main_window.windowTitle()

    # Verify pages
    assert qt_app.main_window._page_dashboard is not None
    assert qt_app.main_window._page_macros is not None
    assert qt_app.main_window._page_builder is not None
    assert qt_app.main_window._page_hub is not None
    assert qt_app.main_window._page_settings is not None

    # Stop hotkeys
    qt_app.hotkeys.stop()
