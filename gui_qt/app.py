"""
gui_qt/app.py
─────────────
KeyMacro Qt Application bootstrap and lifecycle controller.
"""

from __future__ import annotations

import sys
from PySide6.QtWidgets import QApplication

from gui_qt.main_window import KeyMacroMainWindow
from gui_qt.theme.theme_manager import ThemeManager
from keymacro.engine.replay import ReplayEngine
from keymacro.engine.workflow_runner import WorkflowRunner
from keymacro.hotkey.listener import HotkeyListener
from keymacro.launcher.app_scanner import AppScanner
from keymacro.plugins.manager import PluginManager
from keymacro.recorder.recorder import Recorder
from keymacro.safety.safety_layer import SafetyLayer
from keymacro.storage.macro_store import MacroStore
from keymacro.storage.workflow_store import WorkflowStore


class KeyMacroQtApp:
    """Manages application initialization, services, and main event loop."""

    def __init__(
        self,
        store: MacroStore | None = None,
        recorder: Recorder | None = None,
        engine: ReplayEngine | None = None,
        safety: SafetyLayer | None = None,
        hotkey_listener: HotkeyListener | None = None,
        plugin_manager: PluginManager | None = None,
        app_scanner: AppScanner | None = None,
        workflow_store: WorkflowStore | None = None,
    ) -> None:
        self.app = QApplication.instance() or QApplication(sys.argv)
        self.app.setApplicationName("KeyMacro")
        self.app.setOrganizationName("KeyMacro")

        # Initialize backend services
        self.store = store or MacroStore()
        self.recorder = recorder or Recorder()
        self.engine = engine or ReplayEngine()
        self.safety = safety or SafetyLayer()
        self.hotkeys = hotkey_listener or HotkeyListener()
        self.plugins = plugin_manager or PluginManager.get_instance()
        self.scanner = app_scanner or AppScanner()
        self.workflow_store = workflow_store or WorkflowStore()

        # Workflow runner — inject replay engine reference for WorkflowPage
        self.workflow_runner = WorkflowRunner()
        self.workflow_runner._replay_engine = self.engine  # type: ignore[attr-defined]

        # Theme manager
        self.theme_manager = ThemeManager(self.app)
        self.theme_manager.apply_current_theme()

        # Start hotkey listener
        self.hotkeys.start()

        # Create main window
        self.main_window = KeyMacroMainWindow(
            store=self.store,
            recorder=self.recorder,
            engine=self.engine,
            safety=self.safety,
            hotkeys=self.hotkeys,
            plugins=self.plugins,
            scanner=self.scanner,
            workflow_store=self.workflow_store,
            workflow_runner=self.workflow_runner,
            theme_manager=self.theme_manager,
        )

    def run(self) -> int:
        """Display window and start Qt event loop."""
        self.main_window.show()
        exit_code = self.app.exec()

        # Cleanup upon exit
        self.hotkeys.stop()
        return exit_code
