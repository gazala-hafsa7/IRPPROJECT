"""
gui_qt/__init__.py
──────────────────
KeyMacro PySide6 GUI package.
"""

from __future__ import annotations

try:
    from gui_qt.app import KeyMacroQtApp
    from gui_qt.main_window import KeyMacroMainWindow
    __all__ = ["KeyMacroQtApp", "KeyMacroMainWindow"]
except ModuleNotFoundError:
    # Allows self-healing bootstrap when executed from an unactivated python shell
    __all__ = []
