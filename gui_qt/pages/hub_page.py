"""
gui_qt/pages/hub_page.py
────────────────────────
App Launcher and Plugin Hub page: browses Windows installed applications
and loaded KeyMacro plugins with instant launch and macro generator buttons.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from keymacro.launcher.app_scanner import InstalledApp

if TYPE_CHECKING:
    from keymacro.launcher.app_scanner import AppScanner
    from keymacro.plugins.manager import PluginManager


class HubPage(QWidget):
    """Application launcher and plugin integration center."""

    create_macro_for_app = Signal(str, str)  # app_name, app_target

    def __init__(
        self,
        scanner: "AppScanner",
        plugin_manager: "PluginManager",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._scanner = scanner
        self._plugin_mgr = plugin_manager
        self._apps: list[InstalledApp] = []

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # ── Header ────────────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        title_lbl = QLabel("App Launcher & Plugin Hub")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍  Search applications & plugins…")
        self._search_input.textChanged.connect(self._filter_items)
        self._search_input.setMinimumWidth(260)
        header_layout.addWidget(self._search_input)

        btn_rescan = QPushButton("⟳ Rescan System")
        btn_rescan.clicked.connect(lambda: self.refresh(force=True))
        header_layout.addWidget(btn_rescan)

        main_layout.addLayout(header_layout)

        # ── Tabs (Installed Applications / Loaded Plugins) ────────────────────
        self._tabs = QTabWidget()

        # Tab 1: Installed Apps
        apps_widget = QWidget()
        apps_layout = QVBoxLayout(apps_widget)
        apps_layout.setContentsMargins(0, 10, 0, 0)

        self._app_table = QTableWidget()
        self._app_table.setColumnCount(4)
        self._app_table.setHorizontalHeaderLabels(["Application Name", "Category", "Target Executable", "Actions"])
        self._app_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._app_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._app_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._app_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._app_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._app_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._app_table.setAlternatingRowColors(True)
        self._app_table.verticalHeader().setVisible(False)
        apps_layout.addWidget(self._app_table)

        self._tabs.addTab(apps_widget, "Installed Applications")

        # Tab 2: Plugins
        plugins_widget = QWidget()
        plugins_layout = QVBoxLayout(plugins_widget)
        plugins_layout.setContentsMargins(0, 10, 0, 0)

        self._plugin_table = QTableWidget()
        self._plugin_table.setColumnCount(4)
        self._plugin_table.setHorizontalHeaderLabels(["Plugin", "Action ID", "Description", "Parameters"])
        self._plugin_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._plugin_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._plugin_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._plugin_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._plugin_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._plugin_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._plugin_table.setAlternatingRowColors(True)
        self._plugin_table.verticalHeader().setVisible(False)
        plugins_layout.addWidget(self._plugin_table)

        self._tabs.addTab(plugins_widget, "Loaded KeyMacro Plugins")

        main_layout.addWidget(self._tabs, stretch=1)

    def refresh(self, force: bool = False) -> None:
        """Scan applications and plugins."""
        self._apps = self._scanner.scan(force_refresh=force)
        self._filter_items(self._search_input.text())
        self._load_plugins()

    def _filter_items(self, query: str = "") -> None:
        q = query.strip().lower()
        if not q:
            visible_apps = self._apps
        else:
            visible_apps = [a for a in self._apps if q in a.name.lower() or q in a.target.lower()]

        self._app_table.setRowCount(0)
        self._app_table.setRowCount(len(visible_apps))

        for row, app in enumerate(visible_apps):
            name_item = QTableWidgetItem(app.name)
            cat_item = QTableWidgetItem(app.category)
            cat_item.setTextAlignment(Qt.AlignCenter)
            target_item = QTableWidgetItem(app.target)

            self._app_table.setItem(row, 0, name_item)
            self._app_table.setItem(row, 1, cat_item)
            self._app_table.setItem(row, 2, target_item)

            # Action button widget
            action_widget = QWidget()
            action_widget.setStyleSheet("background: transparent;")
            action_layout = QHBoxLayout(action_widget)
            action_layout.setContentsMargins(4, 2, 4, 2)
            action_layout.setSpacing(6)

            btn_launch = QPushButton("Launch")
            btn_launch.setCursor(Qt.PointingHandCursor)
            btn_launch.clicked.connect(lambda _, a=app: a.launch())
            action_layout.addWidget(btn_launch)

            btn_macro = QPushButton("＋ Macro")
            btn_macro.setCursor(Qt.PointingHandCursor)
            btn_macro.setToolTip(f"Generate sequence starter for {app.name}")
            btn_macro.clicked.connect(lambda _, a=app: self.create_macro_for_app.emit(a.name, a.target))
            action_layout.addWidget(btn_macro)

            self._app_table.setCellWidget(row, 3, action_widget)

    def _load_plugins(self) -> None:
        items = self._plugin_mgr.get_all_actions()
        self._plugin_table.setRowCount(0)
        self._plugin_table.setRowCount(len(items))

        for row, (plugin, spec) in enumerate(items):
            plugin_item = QTableWidgetItem(plugin.name)
            action_item = QTableWidgetItem(f"{plugin.plugin_id}.{spec.action_id}")
            desc_item = QTableWidgetItem(spec.description)
            params = ", ".join(f"{k}:{v}" for k, v in spec.params_schema.items()) if spec.params_schema else "none"
            param_item = QTableWidgetItem(params)

            self._plugin_table.setItem(row, 0, plugin_item)
            self._plugin_table.setItem(row, 1, action_item)
            self._plugin_table.setItem(row, 2, desc_item)
            self._plugin_table.setItem(row, 3, param_item)
