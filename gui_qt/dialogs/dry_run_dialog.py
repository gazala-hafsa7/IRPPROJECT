"""
gui_qt/dialogs/dry_run_dialog.py
────────────────────────────────
PySide6 modal dialog displaying Dry-Run simulation logs.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class DryRunDialog(QDialog):
    """Displays simulated execution steps for a macro."""

    def __init__(self, parent: QWidget | None, macro_name: str, log_output: str) -> None:
        super().__init__(parent)
        self.setWindowTitle(f"Dry Run Simulation — {macro_name}")
        self.resize(680, 500)
        self.setMinimumSize(500, 360)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        header_lbl = QLabel(f"⚙  Dry Run Simulation: <b>{macro_name}</b>")
        header_lbl.setStyleSheet("font-size: 15px; font-weight: bold;")
        layout.addWidget(header_lbl)

        info_lbl = QLabel(
            "Dry-run verifies macro instructions without sending real keystrokes, mouse events, "
            "or filesystem modifications."
        )
        info_lbl.setWordWrap(True)
        info_lbl.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        layout.addWidget(info_lbl)

        self._log_edit = QPlainTextEdit()
        self._log_edit.setReadOnly(True)
        self._log_edit.setPlainText(log_output or "(No output generated during simulation)")
        self._log_edit.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px;"
        )
        layout.addWidget(self._log_edit)

        btn_layout = QHBoxLayout()
        btn_copy = QPushButton("Copy Output")
        btn_copy.clicked.connect(self._copy_to_clipboard)
        btn_layout.addWidget(btn_copy)

        btn_layout.addStretch()

        btn_close = QPushButton("Close")
        btn_close.setObjectName("PrimaryBtn")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)

        layout.addLayout(btn_layout)

    def _copy_to_clipboard(self) -> None:
        clipboard = QApplication.clipboard()
        if clipboard:
            clipboard.setText(self._log_edit.toPlainText())
