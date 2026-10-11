"""
gui_qt/main_window.py
─────────────────────
KeyMacro PySide6 MainWindow with Left Sidebar Navigation,
QStackedWidget multi-page architecture, dynamic theme switching,
and thread-safe automation bridge wiring.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QIcon, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from gui_qt.bridge import EngineBridge
from gui_qt.pages.builder_page import BuilderPage
from gui_qt.pages.dashboard_page import DashboardPage
from gui_qt.pages.hub_page import HubPage
from gui_qt.pages.macros_page import MacrosPage
from gui_qt.pages.settings_page import SettingsPage
from gui_qt.theme.theme_manager import THEME_DARK_PURPLE, THEME_LIGHT_PASTEL, ThemeManager
from keymacro.hotkey.context import get_active_window_info
from keymacro.models.action import Macro

if TYPE_CHECKING:
    from keymacro.engine.replay import ReplayEngine
    from keymacro.hotkey.listener import HotkeyListener
    from keymacro.launcher.app_scanner import AppScanner
    from keymacro.plugins.manager import PluginManager
    from keymacro.recorder.recorder import Recorder
    from keymacro.safety.safety_layer import SafetyLayer
    from keymacro.storage.macro_store import MacroStore


class KeyMacroMainWindow(QMainWindow):
    """Primary application window for the KeyMacro PySide6 interface."""

    def __init__(
        self,
        store: "MacroStore",
        recorder: "Recorder",
        engine: "ReplayEngine",
        safety: "SafetyLayer",
        hotkeys: "HotkeyListener",
        plugins: "PluginManager",
        scanner: "AppScanner",
        theme_manager: "ThemeManager | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        self._store = store
        self._recorder = recorder
        self._engine = engine
        self._safety = safety
        self._hotkeys = hotkeys
        self._plugins = plugins
        self._scanner = scanner
        self._theme_mgr = theme_manager or ThemeManager()

        # Thread bridge
        self._bridge = EngineBridge(
            engine=self._engine,
            recorder=self._recorder,
            safety=self._safety,
            hotkeys=self._hotkeys,
            store=self._store,
            parent_widget=self,
        )

        self._nav_buttons: dict[str, QPushButton] = {}
        self._current_page_key = "dashboard"

        self._init_window()
        self._build_ui()
        self._connect_signals()
        self._start_context_timer()

        # Navigate to Dashboard initially
        self._navigate_to("dashboard")

    def _init_window(self) -> None:
        self.setWindowTitle("KeyMacro — Automation Suite")
        self.setMinimumSize(1040, 640)
        self.resize(1160, 720)

        # Center on screen
        screen = QApplication.primaryScreen()
        if screen:
            screen_geo = screen.availableGeometry()
            x = (screen_geo.width() - 1160) // 2
            y = (screen_geo.height() - 720) // 2
            self.move(max(0, x), max(0, y))

    def _build_ui(self) -> None:
        central = QWidget()
        central.setObjectName("CentralWidget")
        self.setCentralWidget(central)

        root_layout = QHBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        # ── 1. Left Sidebar ───────────────────────────────────────────────────
        sidebar = QFrame()
        sidebar.setObjectName("SidebarFrame")
        sidebar.setFixedWidth(230)
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(10, 16, 10, 16)
        sidebar_layout.setSpacing(4)

        # Branding
        brand_lbl = QLabel("⌨  KeyMacro")
        brand_lbl.setObjectName("SidebarBrand")
        sub_lbl = QLabel("DESKTOP AUTOMATION")
        sub_lbl.setObjectName("SidebarSubtitle")
        sidebar_layout.addWidget(brand_lbl)
        sidebar_layout.addWidget(sub_lbl)
        sidebar_layout.addSpacing(14)

        # Navigation buttons
        nav_items = [
            ("dashboard", "📊  Dashboard"),
            ("macros",    "📁  Macro Library"),
            ("builder",   "⚡  Sequence Builder"),
            ("hub",       "🔌  App Hub & Plugins"),
            ("settings",  "⚙  Settings & Themes"),
        ]

        for key, label in nav_items:
            btn = QPushButton(label)
            btn.setObjectName("NavButton")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, k=key: self._navigate_to(k))
            sidebar_layout.addWidget(btn)
            self._nav_buttons[key] = btn

        sidebar_layout.addStretch()

        # Engine Status Indicator Card in Sidebar
        status_card = QFrame()
        status_card.setObjectName("Card")
        status_card_layout = QVBoxLayout(status_card)
        status_card_layout.setContentsMargins(12, 10, 12, 10)
        status_card_layout.setSpacing(4)

        lbl_engine_title = QLabel("ENGINE STATE")
        lbl_engine_title.setStyleSheet("font-size: 10px; font-weight: bold; color: #9CA3AF;")
        self._lbl_engine_status = QLabel("●  Idle")
        self._lbl_engine_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #10B981;")

        status_card_layout.addWidget(lbl_engine_title)
        status_card_layout.addWidget(self._lbl_engine_status)
        sidebar_layout.addWidget(status_card)

        root_layout.addWidget(sidebar)

        # ── 2. Right Content Area (Header + Stacked Pages) ────────────────────
        right_container = QWidget()
        right_layout = QVBoxLayout(right_container)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Top Header Bar
        header = QFrame()
        header.setObjectName("TopHeader")
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(24, 0, 24, 0)
        header_layout.setSpacing(14)

        self._lbl_page_title = QLabel("Dashboard")
        self._lbl_page_title.setObjectName("PageTitle")
        header_layout.addWidget(self._lbl_page_title)

        header_layout.addSpacing(18)

        # Active App Context pill
        self._lbl_context = QLabel("🎯 Focus: Global")
        self._lbl_context.setObjectName("HotkeyPill")
        header_layout.addWidget(self._lbl_context)

        header_layout.addStretch()

        # Theme toggle button in header
        self._btn_theme_toggle = QPushButton("🌙  Theme")
        self._btn_theme_toggle.setObjectName("ThemeToggleBtn")
        self._btn_theme_toggle.setCursor(Qt.PointingHandCursor)
        self._btn_theme_toggle.clicked.connect(self._toggle_theme)
        header_layout.addWidget(self._btn_theme_toggle)

        right_layout.addWidget(header)

        # Stacked Pages
        self._stack = QStackedWidget()

        # Instantiate Pages
        self._page_dashboard = DashboardPage(self._store, self._bridge, self)
        self._page_macros = MacrosPage(self._store, self._bridge, self)
        self._page_builder = BuilderPage(self._store, self)
        self._page_hub = HubPage(self._scanner, self._plugins, self)
        self._page_settings = SettingsPage(self._theme_mgr, self._store, self)

        self._stack.addWidget(self._page_dashboard)   # Index 0
        self._stack.addWidget(self._page_macros)      # Index 1
        self._stack.addWidget(self._page_builder)     # Index 2
        self._stack.addWidget(self._page_hub)         # Index 3
        self._stack.addWidget(self._page_settings)    # Index 4

        right_layout.addWidget(self._stack, stretch=1)
        root_layout.addWidget(right_container, stretch=1)

        # ── 3. Status Bar ─────────────────────────────────────────────────────
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        self._sb_status = QLabel("Ready")
        self._statusbar.addWidget(self._sb_status)

        self._sb_storage = QLabel(f"Storage: {self._store.macros_dir}")
        self._statusbar.addPermanentWidget(self._sb_storage)

        self._update_theme_button_text()

    # ── Navigation ────────────────────────────────────────────────────────────

    def _navigate_to(self, page_key: str) -> None:
        index_map = {
            "dashboard": (0, "Dashboard Overview"),
            "macros":    (1, "Macro Library"),
            "builder":   (2, "Sequence Builder & Editor"),
            "hub":       (3, "App Launcher & Plugin Hub"),
            "settings":  (4, "Appearance & System Settings"),
        }

        if page_key not in index_map:
            page_key = "dashboard"

        idx, title = index_map[page_key]
        self._stack.setCurrentIndex(idx)
        self._lbl_page_title.setText(title)
        self._current_page_key = page_key

        # Update checked states of nav buttons
        for k, btn in self._nav_buttons.items():
            btn.setChecked(k == page_key)

    # ── Signals & Event Wiring ────────────────────────────────────────────────

    def _connect_signals(self) -> None:
        # Dashboard nav requests
        self._page_dashboard.navigate_to_page.connect(self._navigate_to)
        self._page_dashboard.macro_run_requested.connect(self._on_dashboard_run_macro)

        # Macro page edit request -> sequence builder
        self._page_macros.edit_macro_requested.connect(self._on_edit_macro)

        # Builder save event -> refresh library and dashboard
        self._page_builder.macro_saved.connect(self._on_macro_saved)

        # Hub app macro generation -> seed builder
        self._page_hub.create_macro_for_app.connect(self._on_create_macro_for_app)

        # Engine bridge lifecycle signals
        self._bridge.replay_started.connect(self._on_replay_started)
        self._bridge.replay_finished.connect(self._on_replay_finished)
        self._bridge.replay_error.connect(self._on_replay_error)
        self._bridge.recording_started.connect(self._on_recording_started)
        self._bridge.recording_stopped.connect(self._on_recording_stopped)
        self._bridge.state_changed.connect(self._on_state_changed)
        self._bridge.hotkey_triggered.connect(self._on_hotkey_triggered)

        # Theme changes
        self._theme_mgr.theme_changed.connect(lambda _: self._update_theme_button_text())

    def _on_dashboard_run_macro(self, macro: Macro) -> None:
        self._navigate_to("macros")
        self._page_macros._on_run_macro(macro)

    def _on_edit_macro(self, macro: Macro) -> None:
        self._page_builder.load_macro(macro)
        self._navigate_to("builder")

    def _on_macro_saved(self, macro: Macro) -> None:
        self._page_macros.refresh()
        self._page_dashboard.refresh()

    def _on_create_macro_for_app(self, app_name: str, target: str) -> None:
        self._page_builder.clear_form()
        self._page_builder._name_input.setText(f"Open {app_name}")
        self._page_builder._target_input.setText(target)
        initial_seq = f'# Macro for {app_name}\nlaunch: "{target}"\nwait: 500ms\n'
        self._page_builder._script_edit.setPlainText(initial_seq)
        self._navigate_to("builder")

    # ── Bridge Slots ──────────────────────────────────────────────────────────

    def _on_replay_started(self, macro_name: str) -> None:
        self._sb_status.setText(f"▶ Replaying '{macro_name}'…")
        self._lbl_engine_status.setText("▶  Replaying…")
        self._lbl_engine_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #8B5CF6;")

    def _on_replay_finished(self, macro_name: str) -> None:
        self._sb_status.setText(f"✓ Completed '{macro_name}'")
        self._lbl_engine_status.setText("●  Idle")
        self._lbl_engine_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #10B981;")
        self._page_macros._btn_stop.setEnabled(False)
        self._page_dashboard.refresh()

    def _on_replay_error(self, macro_name: str, error_msg: str) -> None:
        self._sb_status.setText(f"⚠ Error executing '{macro_name}'")
        self._lbl_engine_status.setText("●  Idle")
        self._lbl_engine_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #10B981;")
        self._page_macros._btn_stop.setEnabled(False)
        QMessageBox.critical(
            self,
            "Execution Error",
            f"An error occurred while running '<b>{macro_name}</b>':\n\n{error_msg}",
        )

    def _on_recording_started(self, macro_name: str) -> None:
        self._sb_status.setText(f"● Recording '{macro_name}' (Click Stop when finished)")
        self._lbl_engine_status.setText("●  Recording…")
        self._lbl_engine_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #EF4444;")

    def _on_recording_stopped(self, macro: Macro | None) -> None:
        self._sb_status.setText("Recording stopped")
        self._lbl_engine_status.setText("●  Idle")
        self._lbl_engine_status.setStyleSheet("font-size: 13px; font-weight: bold; color: #10B981;")
        self._page_macros._btn_record.setEnabled(True)
        self._page_macros._btn_stop.setEnabled(False)

    def _on_state_changed(self, new_state: str) -> None:
        self._page_macros._update_action_buttons()

    def _on_hotkey_triggered(self, macro: Macro) -> None:
        """Triggered from background hotkey listener via Qt Signal."""
        if self._bridge.state != "idle":
            return

        # Give OS 200ms time to process key release
        QTimer.singleShot(200, lambda: self._bridge.run_macro(macro))

    # ── Context Polling ───────────────────────────────────────────────────────

    def _start_context_timer(self) -> None:
        self._ctx_timer = QTimer(self)
        self._ctx_timer.setInterval(300)
        self._ctx_timer.timeout.connect(self._poll_active_window)
        self._ctx_timer.start()

    def _poll_active_window(self) -> None:
        exe_name, title = get_active_window_info()
        if exe_name:
            self._lbl_context.setText(f"🎯 Focus: {exe_name}")
        else:
            self._lbl_context.setText("🎯 Focus: Global")

    # ── Themes ────────────────────────────────────────────────────────────────

    def _toggle_theme(self) -> None:
        self._theme_mgr.toggle_theme()

    def _update_theme_button_text(self) -> None:
        if self._theme_mgr.is_dark:
            self._btn_theme_toggle.setText("☀️  Light & Pastel")
        else:
            self._btn_theme_toggle.setText("🌙  Dark & Purple")

    # ── Close Event ───────────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        if self._bridge.state == "recording":
            self._bridge.stop_recording()
        elif self._bridge.state == "replaying":
            self._bridge.stop_execution()
        event.accept()
