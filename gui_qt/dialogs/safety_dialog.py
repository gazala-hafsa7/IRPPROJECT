"""
gui_qt/dialogs/safety_dialog.py
───────────────────────────────
PySide6 modal confirmation dialog for HIGH-risk macros.
Replaces the legacy Tkinter toplevel dialog while preserving safety rules.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from keymacro.models.action import Macro


class SafetyConfirmDialog(QDialog):
    """Modal confirmation dialog shown before executing any HIGH-risk macro."""

    def __init__(self, parent: QWidget | None, macro: Macro, preview_text: str) -> None:
        super().__init__(parent)
        self.setWindowTitle("⚠ High-Risk Macro — Confirmation Required")
        self.setModal(True)
        self.resize(650, 480)
        self.setMinimumSize(540, 380)

        self._macro = macro
        self._confirmed = False

        self._build_ui(preview_text)

    def _build_ui(self, preview_text: str) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        # Header banner
        header_layout = QHBoxLayout()
        header_lbl = QLabel("⚠  HIGH-RISK MACRO EXECUTION")
        header_lbl.setStyleSheet(
            "font-size: 15px; font-weight: bold; color: #EF4444; padding: 2px 0;"
        )
        header_layout.addWidget(header_lbl)
        header_layout.addStretch()

        macro_name_lbl = QLabel(f"Macro: <b>{self._macro.name}</b>")
        macro_name_lbl.setStyleSheet("font-size: 13px;")
        header_layout.addWidget(macro_name_lbl)
        layout.addLayout(header_layout)

        # Warning explanation
        desc_lbl = QLabel(
            "This macro includes operations that can modify or delete files on your system.\n"
            "Target files will be automatically backed up before destructive actions run.\n"
            "Please carefully review the planned actions below before deciding to proceed:"
        )
        desc_lbl.setWordWrap(True)
        desc_lbl.setStyleSheet("color: #9CA3AF; line-height: 1.4;")
        layout.addWidget(desc_lbl)

        # Action preview text box
        self._preview_box = QPlainTextEdit()
        self._preview_box.setReadOnly(True)
        self._preview_box.setPlainText(preview_text)
        self._preview_box.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 12px; line-height: 1.3;"
        )
        layout.addWidget(self._preview_box)

        # Action buttons
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        self._btn_cancel = QPushButton("Cancel")
        self._btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self._btn_cancel)

        self._btn_run = QPushButton("⚠  Run Anyway")
        self._btn_run.setObjectName("DangerBtn")
        self._btn_run.clicked.connect(self._on_confirm)
        btn_layout.addWidget(self._btn_run)

        layout.addLayout(btn_layout)

    def _on_confirm(self) -> None:
        self._confirmed = True
        self.accept()

    @classmethod
    def confirm(cls, parent: QWidget | None, macro: Macro, preview_text: str) -> bool:
        """Display dialog and return True if user confirmed, False otherwise."""
        dlg = cls(parent, macro, preview_text)
        dlg.exec()
        return dlg._confirmed
