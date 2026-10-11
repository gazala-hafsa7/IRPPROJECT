"""
gui_qt/pages/macros_page.py
───────────────────────────
Complete Macro Library management page with table browser, live search,
action step inspector, recording triggers, and execution buttons.
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
    QMessageBox,
    QPushButton,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from keymacro.models.action import Macro, RiskLevel
from keymacro.models.sequence import strip_delays
from gui_qt.dialogs.dry_run_dialog import DryRunDialog
from gui_qt.dialogs.record_dialog import RecordSetupDialog

if TYPE_CHECKING:
    from gui_qt.bridge import EngineBridge
    from keymacro.storage.macro_store import MacroStore


class MacrosPage(QWidget):
    """Macro library browser and action inspector."""

    edit_macro_requested = Signal(object)  # Macro to edit in Sequence Builder

    def __init__(
        self,
        store: "MacroStore",
        bridge: "EngineBridge",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._bridge = bridge
        self._macros: list[Macro] = []
        self._selected_macro: Macro | None = None

        self._build_ui()
        self.refresh()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # ── Toolbar ───────────────────────────────────────────────────────────
        toolbar_frame = QFrame()
        toolbar_frame.setObjectName("Card")
        toolbar_layout = QHBoxLayout(toolbar_frame)
        toolbar_layout.setContentsMargins(16, 10, 16, 10)
        toolbar_layout.setSpacing(10)

        self._btn_record = QPushButton("●  Record")
        self._btn_record.setObjectName("RecordBtn")
        self._btn_record.setCursor(Qt.PointingHandCursor)
        self._btn_record.clicked.connect(self._on_start_record)
        toolbar_layout.addWidget(self._btn_record)

        self._btn_stop = QPushButton("■  Stop")
        self._btn_stop.setObjectName("StopBtn")
        self._btn_stop.setCursor(Qt.PointingHandCursor)
        self._btn_stop.setEnabled(False)
        self._btn_stop.clicked.connect(self._on_stop)
        toolbar_layout.addWidget(self._btn_stop)

        toolbar_layout.addSpacing(12)

        # Search box
        self._search_input = QLineEdit()
        self._search_input.setPlaceholderText("🔍  Search macros by name, hotkey, or app…")
        self._search_input.textChanged.connect(self._filter_macros)
        self._search_input.setMinimumWidth(260)
        toolbar_layout.addWidget(self._search_input)

        toolbar_layout.addStretch()

        self._btn_refresh = QPushButton("⟳ Refresh")
        self._btn_refresh.clicked.connect(self.refresh)
        toolbar_layout.addWidget(self._btn_refresh)

        main_layout.addWidget(toolbar_frame)

        # ── Splitter: Macro List | Action Detail ──────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        # Left: Macro Table
        left_card = QFrame()
        left_card.setObjectName("Card")
        left_layout = QVBoxLayout(left_card)
        left_layout.setContentsMargins(14, 14, 14, 14)
        left_layout.setSpacing(10)

        left_title = QLabel("Saved Macros")
        left_title.setStyleSheet("font-size: 14px; font-weight: bold;")
        left_layout.addWidget(left_title)

        self._macro_table = QTableWidget()
        self._macro_table.setColumnCount(3)
        self._macro_table.setHorizontalHeaderLabels(["Name", "Hotkey", "Risk"])
        self._macro_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        self._macro_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._macro_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        self._macro_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._macro_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._macro_table.setAlternatingRowColors(True)
        self._macro_table.verticalHeader().setVisible(False)
        self._macro_table.itemSelectionChanged.connect(self._on_macro_selected)
        self._macro_table.doubleClicked.connect(lambda: self._on_run_macro())
        left_layout.addWidget(self._macro_table)

        splitter.addWidget(left_card)

        # Right: Detail & Inspector
        right_card = QFrame()
        right_card.setObjectName("Card")
        self._right_layout = QVBoxLayout(right_card)
        self._right_layout.setContentsMargins(18, 16, 18, 16)
        self._right_layout.setSpacing(14)

        # Detail Header
        self._lbl_name = QLabel("Select a Macro")
        self._lbl_name.setStyleSheet("font-size: 18px; font-weight: bold;")
        self._right_layout.addWidget(self._lbl_name)

        meta_layout = QHBoxLayout()
        meta_layout.setSpacing(16)
        self._lbl_hotkey = QLabel("Hotkey: —")
        self._lbl_target = QLabel("Target: —")
        self._lbl_risk = QLabel("Risk: —")
        self._lbl_desc = QLabel("")
        self._lbl_desc.setStyleSheet("color: #9CA3AF; font-size: 12px;")

        meta_layout.addWidget(self._lbl_hotkey)
        meta_layout.addWidget(self._lbl_target)
        meta_layout.addWidget(self._lbl_risk)
        meta_layout.addWidget(self._lbl_desc)
        meta_layout.addStretch()
        self._right_layout.addLayout(meta_layout)

        # Action Steps Table
        steps_lbl = QLabel("Macro Steps & Recorded Actions")
        steps_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #9CA3AF;")
        self._right_layout.addWidget(steps_lbl)

        self._action_table = QTableWidget()
        self._action_table.setColumnCount(4)
        self._action_table.setHorizontalHeaderLabels(["#", "Type", "Description", "Risk"])
        self._action_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._action_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._action_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._action_table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeToContents)
        self._action_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._action_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._action_table.setAlternatingRowColors(True)
        self._action_table.verticalHeader().setVisible(False)
        self._right_layout.addWidget(self._action_table, stretch=1)

        # Inspector Buttons
        btn_bar = QHBoxLayout()
        btn_bar.setSpacing(10)

        self._btn_run = QPushButton("▶  Run Macro")
        self._btn_run.setObjectName("SuccessBtn")
        self._btn_run.setCursor(Qt.PointingHandCursor)
        self._btn_run.clicked.connect(self._on_run_macro)
        btn_bar.addWidget(self._btn_run)

        self._btn_dryrun = QPushButton("⚙  Dry Run")
        self._btn_dryrun.setCursor(Qt.PointingHandCursor)
        self._btn_dryrun.clicked.connect(self._on_dry_run)
        btn_bar.addWidget(self._btn_dryrun)

        self._btn_edit = QPushButton("✎  Edit Sequence")
        self._btn_edit.setCursor(Qt.PointingHandCursor)
        self._btn_edit.clicked.connect(self._on_edit)
        btn_bar.addWidget(self._btn_edit)

        self._btn_strip = QPushButton("🧹 Strip Delays")
        self._btn_strip.setToolTip("Remove artificial pauses for instant execution")
        self._btn_strip.clicked.connect(self._on_strip_delays)
        btn_bar.addWidget(self._btn_strip)

        btn_bar.addStretch()

        self._btn_delete = QPushButton("🗑  Delete")
        self._btn_delete.setObjectName("DangerBtn")
        self._btn_delete.setCursor(Qt.PointingHandCursor)
        self._btn_delete.clicked.connect(self._on_delete)
        btn_bar.addWidget(self._btn_delete)

        self._right_layout.addLayout(btn_bar)

        splitter.addWidget(right_card)
        splitter.setSizes([340, 600])

        main_layout.addWidget(splitter, stretch=1)

        # Sync buttons initial state
        self._update_action_buttons()

    # ── Refresh & Filtering ───────────────────────────────────────────────────

    def refresh(self) -> None:
        """Fetch all macros and repopulate table."""
        self._macros = self._store.list_all()
        self._bridge.refresh_hotkeys(self._macros)
        self._filter_macros(self._search_input.text())

    def _filter_macros(self, query: str = "") -> None:
        q = query.strip().lower()
        if not q:
            visible_macros = self._macros
        else:
            visible_macros = [
                m for m in self._macros
                if q in m.name.lower()
                or (m.hotkey and q in m.hotkey.lower())
                or (m.target_app and q in m.target_app.lower())
            ]

        self._macro_table.setRowCount(0)
        self._macro_table.setRowCount(len(visible_macros))

        for row, macro in enumerate(visible_macros):
            name_item = QTableWidgetItem(macro.name)
            name_item.setData(Qt.UserRole, macro)

            hotkey_item = QTableWidgetItem(macro.hotkey or "—")
            hotkey_item.setTextAlignment(Qt.AlignCenter)

            risk_item = QTableWidgetItem(macro.risk_level.value.upper())
            risk_item.setTextAlignment(Qt.AlignCenter)

            self._macro_table.setItem(row, 0, name_item)
            self._macro_table.setItem(row, 1, hotkey_item)
            self._macro_table.setItem(row, 2, risk_item)

        if visible_macros and self._selected_macro is None:
            self._macro_table.selectRow(0)

    # ── Selection & Detail ────────────────────────────────────────────────────

    def _on_macro_selected(self) -> None:
        row = self._macro_table.currentRow()
        if row < 0:
            self._clear_detail()
            return

        item = self._macro_table.item(row, 0)
        if not item:
            self._clear_detail()
            return

        macro: Macro = item.data(Qt.UserRole)
        self._selected_macro = macro
        self._show_detail(macro)

    def _show_detail(self, macro: Macro) -> None:
        self._lbl_name.setText(macro.name)
        self._lbl_hotkey.setText(f"<b>Hotkey:</b> {macro.hotkey or '—'}")
        self._lbl_target.setText(f"<b>Target:</b> {macro.target_app or 'Global'}")
        self._lbl_risk.setText(f"<b>Risk:</b> {macro.risk_level.value.upper()}")
        self._lbl_desc.setText(macro.description or "")

        self._action_table.setRowCount(0)
        self._action_table.setRowCount(len(macro.actions))

        for idx, action in enumerate(macro.actions, 1):
            idx_item = QTableWidgetItem(str(idx))
            idx_item.setTextAlignment(Qt.AlignCenter)

            type_item = QTableWidgetItem(action.action_type.value.replace("_", " ").title())
            desc_item = QTableWidgetItem(action.description)
            risk_item = QTableWidgetItem(action.risk_level.value.upper())
            risk_item.setTextAlignment(Qt.AlignCenter)

            self._action_table.setItem(idx - 1, 0, idx_item)
            self._action_table.setItem(idx - 1, 1, type_item)
            self._action_table.setItem(idx - 1, 2, desc_item)
            self._action_table.setItem(idx - 1, 3, risk_item)

        self._update_action_buttons()

    def _clear_detail(self) -> None:
        self._selected_macro = None
        self._lbl_name.setText("Select a Macro")
        self._lbl_hotkey.setText("Hotkey: —")
        self._lbl_target.setText("Target: —")
        self._lbl_risk.setText("Risk: —")
        self._lbl_desc.setText("")
        self._action_table.setRowCount(0)
        self._update_action_buttons()

    def _update_action_buttons(self) -> None:
        has_sel = self._selected_macro is not None
        is_idle = self._bridge.state == "idle"

        self._btn_run.setEnabled(has_sel and is_idle)
        self._btn_dryrun.setEnabled(has_sel and is_idle)
        self._btn_edit.setEnabled(has_sel and is_idle)
        self._btn_strip.setEnabled(has_sel and is_idle)
        self._btn_delete.setEnabled(has_sel and is_idle)

    # ── Command Handlers ──────────────────────────────────────────────────────

    def _on_start_record(self) -> None:
        dlg = RecordSetupDialog(self)
        if dlg.exec():
            self._bridge.start_recording(dlg.macro_name, dlg.record_mouse_path)
            self._btn_record.setEnabled(False)
            self._btn_stop.setEnabled(True)

    def _on_stop(self) -> None:
        if self._bridge.state == "recording":
            macro = self._bridge.stop_recording()
            self._btn_record.setEnabled(True)
            self._btn_stop.setEnabled(False)

            if macro and macro.action_count > 0:
                self._store.save(macro)
                self.refresh()
                QMessageBox.information(
                    self,
                    "Recording Saved",
                    f"Macro '<b>{macro.name}</b>' saved successfully with {macro.action_count} actions!",
                )
            else:
                QMessageBox.warning(self, "Recording Empty", "No actions were captured.")
        elif self._bridge.state == "replaying":
            self._bridge.stop_execution()
            self._btn_stop.setEnabled(False)

    def _on_run_macro(self, target_macro: Macro | None = None) -> None:
        macro = target_macro or self._selected_macro
        if not macro:
            return

        self._btn_stop.setEnabled(True)
        self._bridge.run_macro(macro)

    def _on_dry_run(self) -> None:
        if not self._selected_macro:
            return

        def _display(output: str) -> None:
            dlg = DryRunDialog(self, self._selected_macro.name, output)
            dlg.exec()

        self._bridge.dry_run(self._selected_macro, _display)

    def _on_strip_delays(self) -> None:
        if not self._selected_macro:
            return

        macro = self._selected_macro
        old_count = macro.action_count
        macro.actions = strip_delays(macro.actions)
        diff = old_count - macro.action_count

        self._store.save(macro)
        self.refresh()
        self._show_detail(macro)

        QMessageBox.information(
            self,
            "Delays Removed",
            f"Removed {diff} delay steps from '{macro.name}'. Execution is now instantaneous.",
        )

    def _on_edit(self) -> None:
        if self._selected_macro:
            self.edit_macro_requested.emit(self._selected_macro)

    def _on_delete(self) -> None:
        if not self._selected_macro:
            return

        res = QMessageBox.question(
            self,
            "Delete Macro",
            f"Are you sure you want to delete '<b>{self._selected_macro.name}</b>'? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if res == QMessageBox.Yes:
            self._store.delete(self._selected_macro.macro_id)
            self._clear_detail()
            self.refresh()
