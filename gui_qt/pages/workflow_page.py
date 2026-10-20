"""
gui_qt/pages/workflow_page.py
──────────────────────────────
Macro Workflow Builder page — visual node-based editor for chaining macros
with conditional pass/fail branching.

Layout
------
  Left panel  : Workflow list (saved workflows)
  Right panel : Node canvas + node editor panel
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING

from PySide6.QtCore import Qt, Signal, QRectF, QPointF
from PySide6.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from keymacro.models.workflow import Workflow, WorkflowNode

if TYPE_CHECKING:
    from keymacro.engine.workflow_runner import WorkflowRunner
    from keymacro.storage.macro_store import MacroStore
    from keymacro.storage.workflow_store import WorkflowStore

# ── Colours ───────────────────────────────────────────────────────────────────
_CLR_NODE_BG       = QColor("#1E1F2E")
_CLR_NODE_BORDER   = QColor("#8B5CF6")
_CLR_NODE_ACTIVE   = QColor("#7C3AED")
_CLR_NODE_TEXT     = QColor("#F3F4F6")
_CLR_NODE_SUB      = QColor("#9CA3AF")
_CLR_EDGE_SUCCESS  = QColor("#10B981")   # green
_CLR_EDGE_FAILURE  = QColor("#EF4444")   # red
_CLR_CANVAS_BG     = QColor("#13141F")
_NODE_W, _NODE_H   = 200, 64


# ── WorkflowNodeItem (QGraphicsItem) ─────────────────────────────────────────

class WorkflowNodeItem(QGraphicsItem):
    """Visual representation of a WorkflowNode on the canvas."""

    def __init__(self, node: WorkflowNode, parent=None) -> None:
        super().__init__(parent)
        self.node = node
        self.setFlag(QGraphicsItem.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.ItemSendsGeometryChanges, True)
        self.setPos(node.x, node.y)

    def boundingRect(self) -> QRectF:
        return QRectF(0, 0, _NODE_W, _NODE_H)

    def paint(self, painter: QPainter, option, widget=None) -> None:
        selected = self.isSelected()
        bg = _CLR_NODE_ACTIVE if selected else _CLR_NODE_BG
        border = QColor("#C084FC") if selected else _CLR_NODE_BORDER

        painter.setRenderHint(QPainter.Antialiasing)
        painter.setBrush(QBrush(bg))
        painter.setPen(QPen(border, 2 if selected else 1.5))
        painter.drawRoundedRect(self.boundingRect(), 10, 10)

        # Title
        title_font = QFont("Segoe UI", 10, QFont.Bold)
        painter.setFont(title_font)
        painter.setPen(QPen(_CLR_NODE_TEXT))
        name = self.node.macro_name or "[ No Macro ]"
        if len(name) > 22:
            name = name[:20] + "…"
        painter.drawText(QRectF(12, 8, _NODE_W - 24, 28), Qt.AlignLeft | Qt.AlignVCenter, name)

        # Sub-label
        sub_font = QFont("Segoe UI", 8)
        painter.setFont(sub_font)
        painter.setPen(QPen(_CLR_NODE_SUB))
        success_lbl = "→ " + (self._name_for_id(self.node.next_on_success) or "END") if self.node.next_on_success else "→ END"
        fail_lbl    = "✗ " + (self._name_for_id(self.node.next_on_failure) or "END") if self.node.next_on_failure else "✗ END"
        painter.setPen(QPen(_CLR_EDGE_SUCCESS))
        painter.drawText(QRectF(12, 36, _NODE_W//2 - 12, 20), Qt.AlignLeft, success_lbl)
        painter.setPen(QPen(_CLR_EDGE_FAILURE))
        painter.drawText(QRectF(_NODE_W//2, 36, _NODE_W//2 - 12, 20), Qt.AlignLeft, fail_lbl)

    def _name_for_id(self, node_id: str) -> str:
        # Scene's parent workflow is not directly accessible here — just show short ID
        return node_id[:8] if node_id else ""

    def itemChange(self, change, value):
        if change == QGraphicsItem.ItemPositionHasChanged:
            self.node.x = self.pos().x()
            self.node.y = self.pos().y()
            # Trigger edge redraw in the scene
            if self.scene():
                self.scene().update()
        return super().itemChange(change, value)

    def center(self) -> QPointF:
        return self.pos() + QPointF(_NODE_W / 2, _NODE_H / 2)

    def bottom_center(self) -> QPointF:
        return self.pos() + QPointF(_NODE_W / 2, _NODE_H)


# ── WorkflowCanvas ────────────────────────────────────────────────────────────

class WorkflowCanvas(QGraphicsView):
    """Zoomable, pannable canvas for the node graph."""

    node_selected = Signal(object)   # WorkflowNode or None

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._scene = QGraphicsScene(self)
        self._scene.setBackgroundBrush(QBrush(_CLR_CANVAS_BG))
        self.setScene(self._scene)
        self.setRenderHint(QPainter.Antialiasing)
        self.setDragMode(QGraphicsView.RubberBandDrag)
        self.setTransformationAnchor(QGraphicsView.AnchorUnderMouse)
        self._node_items: dict[str, WorkflowNodeItem] = {}  # node_id → item
        self._workflow: Workflow | None = None

        self._scene.selectionChanged.connect(self._on_selection_changed)

    def load_workflow(self, workflow: Workflow) -> None:
        self._scene.clear()
        self._node_items.clear()
        self._workflow = workflow

        # Create node items
        for node in workflow.nodes:
            item = WorkflowNodeItem(node)
            self._scene.addItem(item)
            self._node_items[node.node_id] = item

        self._draw_edges()
        self.fitInView(self._scene.itemsBoundingRect(), Qt.KeepAspectRatio)

    def _draw_edges(self) -> None:
        """Remove old edge lines and redraw based on current node positions."""
        # Remove old line items
        for item in list(self._scene.items()):
            if isinstance(item, QGraphicsLineItem):
                self._scene.removeItem(item)

        if not self._workflow:
            return

        for node in self._workflow.nodes:
            src_item = self._node_items.get(node.node_id)
            if not src_item:
                continue
            for target_id, color in [
                (node.next_on_success, _CLR_EDGE_SUCCESS),
                (node.next_on_failure, _CLR_EDGE_FAILURE),
            ]:
                if not target_id:
                    continue
                dst_item = self._node_items.get(target_id)
                if not dst_item:
                    continue
                src_pt = src_item.bottom_center()
                dst_pt = dst_item.pos() + QPointF(_NODE_W / 2, 0)
                line = QGraphicsLineItem(src_pt.x(), src_pt.y(), dst_pt.x(), dst_pt.y())
                pen = QPen(color, 2, Qt.SolidLine)
                line.setPen(pen)
                line.setZValue(-1)
                self._scene.addItem(line)

    def add_node(self, node: WorkflowNode) -> None:
        item = WorkflowNodeItem(node)
        self._scene.addItem(item)
        self._node_items[node.node_id] = item
        self._draw_edges()

    def remove_selected_node(self) -> str | None:
        """Remove the selected node item. Returns its node_id or None."""
        items = self._scene.selectedItems()
        if not items:
            return None
        item = items[0]
        if not isinstance(item, WorkflowNodeItem):
            return None
        node_id = item.node.node_id
        self._scene.removeItem(item)
        del self._node_items[node_id]
        self._draw_edges()
        return node_id

    def refresh_edges(self) -> None:
        self._draw_edges()

    def _on_selection_changed(self) -> None:
        items = self._scene.selectedItems()
        if items and isinstance(items[0], WorkflowNodeItem):
            self.node_selected.emit(items[0].node)
        else:
            self.node_selected.emit(None)

    def wheelEvent(self, event) -> None:
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)


# ── WorkflowPage ──────────────────────────────────────────────────────────────

class WorkflowPage(QWidget):
    """
    Full Workflow Builder page:
      - Sidebar: saved workflows list
      - Main canvas: drag-and-drop node graph
      - Bottom: node editor panel (macro picker + edge routing)
    """

    workflow_changed = Signal()

    def __init__(
        self,
        workflow_store: "WorkflowStore",
        macro_store: "MacroStore",
        workflow_runner: "WorkflowRunner",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._wf_store = workflow_store
        self._macro_store = macro_store
        self._runner = workflow_runner
        self._current_wf: Workflow | None = None
        self._selected_node: WorkflowNode | None = None

        self._build_ui()
        self._refresh_list()

    # ── UI Build ──────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(6)

        # ── Left: Workflow library panel ──────────────────────────────────────
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(12, 16, 12, 16)
        left_layout.setSpacing(10)

        lbl = QLabel("⚡  Workflows")
        lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        left_layout.addWidget(lbl)

        self._wf_list = QListWidget()
        self._wf_list.currentRowChanged.connect(self._on_wf_selected)
        left_layout.addWidget(self._wf_list, stretch=1)

        btn_row = QHBoxLayout()
        self._btn_new_wf = QPushButton("＋ New")
        self._btn_new_wf.clicked.connect(self._on_new_workflow)
        self._btn_del_wf = QPushButton("🗑 Delete")
        self._btn_del_wf.clicked.connect(self._on_delete_workflow)
        btn_row.addWidget(self._btn_new_wf)
        btn_row.addWidget(self._btn_del_wf)
        left_layout.addLayout(btn_row)

        splitter.addWidget(left_panel)
        splitter.setStretchFactor(0, 0)

        # ── Right: Canvas + Editor ────────────────────────────────────────────
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(0)

        # Canvas toolbar
        canvas_toolbar = QFrame()
        canvas_toolbar.setObjectName("Card")
        tb_layout = QHBoxLayout(canvas_toolbar)
        tb_layout.setContentsMargins(14, 8, 14, 8)
        tb_layout.setSpacing(8)

        self._lbl_wf_name = QLabel("Select or create a workflow")
        self._lbl_wf_name.setStyleSheet("font-weight: bold; font-size: 14px;")
        tb_layout.addWidget(self._lbl_wf_name)
        tb_layout.addStretch()

        self._btn_add_node = QPushButton("➕ Add Step")
        self._btn_add_node.setEnabled(False)
        self._btn_add_node.clicked.connect(self._on_add_node)
        tb_layout.addWidget(self._btn_add_node)

        self._btn_del_node = QPushButton("🗑 Delete Step")
        self._btn_del_node.setEnabled(False)
        self._btn_del_node.clicked.connect(self._on_delete_node)
        tb_layout.addWidget(self._btn_del_node)

        tb_layout.addWidget(QLabel("⌨️ Hotkey:"))
        self._edit_wf_hotkey = QLineEdit()
        self._edit_wf_hotkey.setPlaceholderText("e.g. ctrl+shift+w")
        self._edit_wf_hotkey.setMaximumWidth(130)
        self._edit_wf_hotkey.setEnabled(False)
        tb_layout.addWidget(self._edit_wf_hotkey)

        self._btn_run_wf = QPushButton("▶  Run Workflow")
        self._btn_run_wf.setObjectName("PrimaryBtn")
        self._btn_run_wf.setEnabled(False)
        self._btn_run_wf.clicked.connect(self._on_run_workflow)
        tb_layout.addWidget(self._btn_run_wf)

        self._btn_save_wf = QPushButton("💾 Save")
        self._btn_save_wf.setEnabled(False)
        self._btn_save_wf.clicked.connect(self._on_save_workflow)
        tb_layout.addWidget(self._btn_save_wf)

        right_layout.addWidget(canvas_toolbar)

        # Canvas
        self._canvas = WorkflowCanvas()
        self._canvas.node_selected.connect(self._on_node_selected)
        right_layout.addWidget(self._canvas, stretch=1)

        # Bottom node editor panel
        self._editor_panel = self._build_editor_panel()
        right_layout.addWidget(self._editor_panel)

        splitter.addWidget(right_panel)
        splitter.setStretchFactor(1, 1)
        splitter.setSizes([220, 800])

        root.addWidget(splitter)

    def _build_editor_panel(self) -> QFrame:
        panel = QFrame()
        panel.setObjectName("Card")
        panel.setMaximumHeight(130)
        layout = QHBoxLayout(panel)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(16)

        # Macro picker
        macro_col = QVBoxLayout()
        macro_col.addWidget(QLabel("Macro for this step:"))
        self._combo_macro = QComboBox()
        self._combo_macro.setMinimumWidth(200)
        self._combo_macro.currentIndexChanged.connect(self._on_node_macro_changed)
        macro_col.addWidget(self._combo_macro)
        layout.addLayout(macro_col)

        # On Success edge
        success_col = QVBoxLayout()
        success_col.addWidget(QLabel("✅ On Success → next step:"))
        self._combo_success = QComboBox()
        self._combo_success.currentIndexChanged.connect(self._on_node_edge_changed)
        success_col.addWidget(self._combo_success)
        layout.addLayout(success_col)

        # On Failure edge
        fail_col = QVBoxLayout()
        fail_col.addWidget(QLabel("❌ On Failure → next step:"))
        self._combo_failure = QComboBox()
        self._combo_failure.currentIndexChanged.connect(self._on_node_edge_changed)
        fail_col.addWidget(self._combo_failure)
        layout.addLayout(fail_col)

        layout.addStretch()

        self._lbl_editor_hint = QLabel("← Select a step node to edit its properties")
        self._lbl_editor_hint.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        layout.addWidget(self._lbl_editor_hint)

        self._set_editor_enabled(False)
        return panel

    def _set_editor_enabled(self, enabled: bool) -> None:
        self._combo_macro.setEnabled(enabled)
        self._combo_success.setEnabled(enabled)
        self._combo_failure.setEnabled(enabled)
        self._lbl_editor_hint.setVisible(not enabled)

    # ── Workflow List ─────────────────────────────────────────────────────────

    def _refresh_list(self) -> None:
        self._wf_list.clear()
        for wf in self._wf_store.list_all():
            item = QListWidgetItem(f"⚡ {wf.name}  ({len(wf.nodes)} steps)")
            item.setData(Qt.UserRole, wf.workflow_id)
            self._wf_list.addItem(item)

    def _on_wf_selected(self, row: int) -> None:
        if row < 0:
            return
        item = self._wf_list.item(row)
        if not item:
            return
        wf_id = item.data(Qt.UserRole)
        wf = self._wf_store.load(wf_id)
        if wf:
            self._load_workflow(wf)

    def _load_workflow(self, wf: Workflow) -> None:
        self._current_wf = wf
        self._selected_node = None
        self._lbl_wf_name.setText(f"⚡  {wf.name}")
        self._edit_wf_hotkey.setText(wf.hotkey or "")
        self._edit_wf_hotkey.setEnabled(True)
        self._canvas.load_workflow(wf)
        self._btn_add_node.setEnabled(True)
        self._btn_run_wf.setEnabled(len(wf.nodes) > 0)
        self._btn_save_wf.setEnabled(True)
        self._set_editor_enabled(False)

    def _on_new_workflow(self) -> None:
        name, ok = QInputDialog.getText(self, "New Workflow", "Workflow name:")
        if not ok or not name.strip():
            return
        wf = Workflow(name=name.strip())
        self._wf_store.save(wf)
        self._refresh_list()
        # Select the new item
        for i in range(self._wf_list.count()):
            if self._wf_list.item(i).data(Qt.UserRole) == wf.workflow_id:
                self._wf_list.setCurrentRow(i)
                break

    def _on_delete_workflow(self) -> None:
        if not self._current_wf:
            return
        answer = QMessageBox.question(
            self, "Delete Workflow",
            f"Delete workflow '{self._current_wf.name}'?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if answer == QMessageBox.Yes:
            self._wf_store.delete(self._current_wf.workflow_id)
            self._current_wf = None
            self._edit_wf_hotkey.setText("")
            self._edit_wf_hotkey.setEnabled(False)
            self._refresh_list()
            self._canvas._scene.clear()
            self._lbl_wf_name.setText("Select or create a workflow")
            self._btn_add_node.setEnabled(False)
            self._btn_run_wf.setEnabled(False)
            self._btn_save_wf.setEnabled(False)
            self.workflow_changed.emit()

    # ── Node Operations ───────────────────────────────────────────────────────

    def _on_add_node(self) -> None:
        if not self._current_wf:
            return
        macros = self._macro_store.list_all()
        if not macros:
            QMessageBox.information(self, "No Macros", "Create some macros first, then add them as workflow steps.")
            return

        # Pick macro via simple dialog
        macro_names = [m.name for m in macros]
        name, ok = QInputDialog.getItem(
            self, "Add Workflow Step", "Choose macro for this step:", macro_names, 0, False
        )
        if not ok:
            return
        macro = next((m for m in macros if m.name == name), None)
        if not macro:
            return

        # Stagger node positions nicely
        offset_x = 80 + len(self._current_wf.nodes) * 20
        offset_y = 80 + len(self._current_wf.nodes) * 90

        node = WorkflowNode(
            macro_id=macro.macro_id,
            macro_name=macro.name,
            x=offset_x,
            y=offset_y,
        )
        self._current_wf.add_node(node)
        self._canvas.add_node(node)
        self._btn_run_wf.setEnabled(True)
        self._btn_del_node.setEnabled(True)

    def _on_delete_node(self) -> None:
        if not self._current_wf:
            return
        node_id = self._canvas.remove_selected_node()
        if node_id:
            self._current_wf.remove_node(node_id)
            self._selected_node = None
            self._set_editor_enabled(False)
            self._btn_run_wf.setEnabled(len(self._current_wf.nodes) > 0)

    def _on_node_selected(self, node: WorkflowNode | None) -> None:
        self._selected_node = node
        self._btn_del_node.setEnabled(node is not None)

        if node is None:
            self._set_editor_enabled(False)
            return

        self._set_editor_enabled(True)
        self._populate_editor(node)

    def _populate_editor(self, node: WorkflowNode) -> None:
        """Fill editor combos for the selected node."""
        wf = self._current_wf
        if not wf:
            return

        macros = self._macro_store.list_all()

        # Block signals while populating
        self._combo_macro.blockSignals(True)
        self._combo_success.blockSignals(True)
        self._combo_failure.blockSignals(True)

        # Macro combo
        self._combo_macro.clear()
        for m in macros:
            self._combo_macro.addItem(m.name, m.macro_id)
        idx = next((i for i, m in enumerate(macros) if m.macro_id == node.macro_id), 0)
        self._combo_macro.setCurrentIndex(idx)

        # Edge combos — other nodes + "(END)"
        other_nodes = [(n.macro_name or n.node_id[:8], n.node_id) for n in wf.nodes if n.node_id != node.node_id]
        for combo, current_edge in [
            (self._combo_success, node.next_on_success),
            (self._combo_failure, node.next_on_failure),
        ]:
            combo.clear()
            combo.addItem("(END — stop workflow)", "")
            for label, nid in other_nodes:
                combo.addItem(f"→ {label}", nid)
            edge_idx = next((i + 1 for i, (_, nid) in enumerate(other_nodes) if nid == current_edge), 0)
            combo.setCurrentIndex(edge_idx)

        self._combo_macro.blockSignals(False)
        self._combo_success.blockSignals(False)
        self._combo_failure.blockSignals(False)

    def _on_node_macro_changed(self, idx: int) -> None:
        if not self._selected_node:
            return
        macro_id = self._combo_macro.currentData()
        macro_name = self._combo_macro.currentText()
        self._selected_node.macro_id = macro_id or ""
        self._selected_node.macro_name = macro_name
        self._canvas._scene.update()

    def _on_node_edge_changed(self, idx: int) -> None:
        if not self._selected_node:
            return
        self._selected_node.next_on_success = self._combo_success.currentData() or ""
        self._selected_node.next_on_failure = self._combo_failure.currentData() or ""
        self._canvas.refresh_edges()

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save_workflow(self) -> None:
        if not self._current_wf:
            return
        # Sync node positions from canvas items
        for node in self._current_wf.nodes:
            item = self._canvas._node_items.get(node.node_id)
            if item:
                node.x = item.pos().x()
                node.y = item.pos().y()
        self._current_wf.hotkey = self._edit_wf_hotkey.text().strip()
        self._wf_store.save(self._current_wf)
        self._refresh_list()
        self.workflow_changed.emit()
        QMessageBox.information(self, "Saved", f"Workflow '{self._current_wf.name}' saved.")

    # ── Run ───────────────────────────────────────────────────────────────────

    def _on_run_workflow(self) -> None:
        if not self._current_wf or not self._current_wf.nodes:
            return
        if self._runner.is_running:
            QMessageBox.warning(self, "Busy", "A workflow is already running.")
            return

        self._btn_run_wf.setEnabled(False)
        self._btn_run_wf.setText("⏳ Running…")

        def _on_node(node_id, macro_name, status):
            # Update node visual (called from runner thread — post to main thread via scene.update)
            self._canvas._scene.update()

        def _on_done(wf_name):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._after_run(wf_name, success=True))

        def _on_error(wf_name, exc):
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._after_run(wf_name, success=False, error=str(exc)))

        self._runner.run(
            self._current_wf,
            self._macro_store,
            # WorkflowRunner needs a ReplayEngine — injected at app level
            self._runner._replay_engine,
            on_node=_on_node,
            on_done=_on_done,
            on_error=_on_error,
        )

    def _after_run(self, wf_name: str, success: bool, error: str = "") -> None:
        self._btn_run_wf.setEnabled(True)
        self._btn_run_wf.setText("▶  Run Workflow")
        if success:
            QMessageBox.information(self, "Workflow Complete", f"'{wf_name}' finished successfully.")
        else:
            QMessageBox.critical(self, "Workflow Error", f"'{wf_name}' failed:\n{error}")
