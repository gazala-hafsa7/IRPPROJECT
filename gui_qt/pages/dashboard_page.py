"""
gui_qt/pages/dashboard_page.py
──────────────────────────────
Dashboard overview page showing summary metrics, quick actions,
and recent macros.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from keymacro.models.action import Macro, RiskLevel

if TYPE_CHECKING:
    from gui_qt.bridge import EngineBridge
    from keymacro.storage.macro_store import MacroStore


class DashboardPage(QWidget):
    """Overview dashboard with metrics, quick actions, and macro highlights."""

    navigate_to_page = Signal(str)  # 'macros', 'builder', 'hub', 'settings'
    macro_run_requested = Signal(object)

    def __init__(
        self,
        store: "MacroStore",
        bridge: "EngineBridge",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._bridge = bridge

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 20, 24, 20)
        layout.setSpacing(20)

        # ── Welcome & Status Banner ───────────────────────────────────────────
        banner_frame = QFrame()
        banner_frame.setObjectName("Card")
        banner_layout = QHBoxLayout(banner_frame)
        banner_layout.setContentsMargins(20, 16, 20, 16)

        welcome_text_layout = QVBoxLayout()
        title_lbl = QLabel("Welcome to KeyMacro")
        title_lbl.setStyleSheet("font-size: 20px; font-weight: bold; color: inherit;")
        subtitle_lbl = QLabel(
            "High-performance automation engine with intelligent safety protection."
        )
        subtitle_lbl.setStyleSheet("color: #9CA3AF; font-size: 13px;")
        welcome_text_layout.addWidget(title_lbl)
        welcome_text_layout.addWidget(subtitle_lbl)
        banner_layout.addLayout(welcome_text_layout)

        banner_layout.addStretch()

        self._btn_quick_record = QPushButton("●  Start Recording")
        self._btn_quick_record.setObjectName("RecordBtn")
        self._btn_quick_record.setCursor(Qt.PointingHandCursor)
        self._btn_quick_record.clicked.connect(lambda: self.navigate_to_page.emit("macros"))
        banner_layout.addWidget(self._btn_quick_record)

        layout.addWidget(banner_frame)

        # ── Summary Metric Cards ──────────────────────────────────────────────
        metrics_grid = QGridLayout()
        metrics_grid.setSpacing(14)

        self._card_total_macros = self._create_metric_card("Total Macros", "0")
        self._card_active_hotkeys = self._create_metric_card("Active Hotkeys", "0")
        self._card_safety_status = self._create_metric_card("Safety Shield", "ACTIVE")
        self._card_engine_state = self._create_metric_card("Engine Status", "IDLE")

        metrics_grid.addWidget(self._card_total_macros["frame"], 0, 0)
        metrics_grid.addWidget(self._card_active_hotkeys["frame"], 0, 1)
        metrics_grid.addWidget(self._card_safety_status["frame"], 0, 2)
        metrics_grid.addWidget(self._card_engine_state["frame"], 0, 3)

        layout.addLayout(metrics_grid)

        # ── Quick Nav Actions ─────────────────────────────────────────────────
        actions_frame = QFrame()
        actions_frame.setObjectName("Card")
        actions_layout = QHBoxLayout(actions_frame)
        actions_layout.setContentsMargins(16, 12, 16, 12)

        lbl_quick = QLabel("Quick Access:")
        lbl_quick.setStyleSheet("font-weight: bold; font-size: 13px;")
        actions_layout.addWidget(lbl_quick)

        btn_go_builder = QPushButton("⚡ Sequence Builder")
        btn_go_builder.clicked.connect(lambda: self.navigate_to_page.emit("builder"))
        actions_layout.addWidget(btn_go_builder)

        btn_go_hub = QPushButton("🔌 App Launcher & Hub")
        btn_go_hub.clicked.connect(lambda: self.navigate_to_page.emit("hub"))
        actions_layout.addWidget(btn_go_hub)

        btn_go_settings = QPushButton("⚙ Themes & Settings")
        btn_go_settings.clicked.connect(lambda: self.navigate_to_page.emit("settings"))
        actions_layout.addWidget(btn_go_settings)

        actions_layout.addStretch()
        layout.addWidget(actions_frame)

        # ── Recent Macros Table ───────────────────────────────────────────────
        recent_card = QFrame()
        recent_card.setObjectName("Card")
        recent_layout = QVBoxLayout(recent_card)
        recent_layout.setContentsMargins(18, 16, 18, 16)
        recent_layout.setSpacing(12)

        recent_header = QHBoxLayout()
        recent_title = QLabel("Recent Automation Macros")
        recent_title.setStyleSheet("font-size: 15px; font-weight: bold;")
        recent_header.addWidget(recent_title)

        recent_header.addStretch()

        btn_view_all = QPushButton("View Full Library →")
        btn_view_all.setCursor(Qt.PointingHandCursor)
        btn_view_all.clicked.connect(lambda: self.navigate_to_page.emit("macros"))
        recent_header.addWidget(btn_view_all)

        recent_layout.addLayout(recent_header)

        self._table = QTableWidget()
        self._table.setColumnCount(5)
        self._table.setHorizontalHeaderLabels(["Name", "Hotkey", "Target App", "Steps", "Risk Level"])
        self._table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._table.horizontalHeader().setSectionResizeMode(4, QHeaderView.ResizeToContents)
        self._table.setSelectionBehavior(QTableWidget.SelectRows)
        self._table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._table.setAlternatingRowColors(True)
        self._table.verticalHeader().setVisible(False)
        self._table.doubleClicked.connect(self._on_table_double_clicked)
        recent_layout.addWidget(self._table)

        layout.addWidget(recent_card, stretch=1)

    def _create_metric_card(self, label_text: str, default_value: str) -> dict:
        frame = QFrame()
        frame.setObjectName("MetricCard")
        card_layout = QVBoxLayout(frame)
        card_layout.setContentsMargins(16, 14, 16, 14)
        card_layout.setSpacing(4)

        val_lbl = QLabel(default_value)
        val_lbl.setObjectName("MetricValue")
        card_layout.addWidget(val_lbl)

        lbl = QLabel(label_text)
        lbl.setObjectName("MetricLabel")
        card_layout.addWidget(lbl)

        return {"frame": frame, "value_label": val_lbl}

    def refresh(self) -> None:
        """Reload metrics and table rows from MacroStore."""
        macros = self._store.list_all()

        # Update metrics
        self._card_total_macros["value_label"].setText(str(len(macros)))
        hotkey_count = sum(1 for m in macros if m.hotkey)
        self._card_active_hotkeys["value_label"].setText(str(hotkey_count))

        state_text = self._bridge.state.upper()
        self._card_engine_state["value_label"].setText(state_text)

        # Populate table
        self._table.setRowCount(0)
        recent_list = macros[:8]  # Show up to 8
        self._table.setRowCount(len(recent_list))

        for row, macro in enumerate(recent_list):
            name_item = QTableWidgetItem(macro.name)
            name_item.setData(Qt.UserRole, macro)

            hotkey_item = QTableWidgetItem(macro.hotkey or "—")
            target_item = QTableWidgetItem(macro.target_app or "Global")
            steps_item = QTableWidgetItem(f"{macro.action_count} actions")
            risk_item = QTableWidgetItem(macro.risk_level.value.upper())

            # Text alignment
            hotkey_item.setTextAlignment(Qt.AlignCenter)
            steps_item.setTextAlignment(Qt.AlignCenter)
            risk_item.setTextAlignment(Qt.AlignCenter)

            self._table.setItem(row, 0, name_item)
            self._table.setItem(row, 1, hotkey_item)
            self._table.setItem(row, 2, target_item)
            self._table.setItem(row, 3, steps_item)
            self._table.setItem(row, 4, risk_item)

    def _on_table_double_clicked(self) -> None:
        row = self._table.currentRow()
        if row >= 0:
            item = self._table.item(row, 0)
            if item:
                macro = item.data(Qt.UserRole)
                if macro:
                    self.macro_run_requested.emit(macro)
