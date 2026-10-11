"""
gui_qt/dialogs/record_dialog.py
───────────────────────────────
Dialog to configure and start a new live input recording.
"""

from __future__ import annotations

from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class RecordSetupDialog(QDialog):
    """Dialog to name and configure recording options before starting."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Start New Recording")
        self.setModal(True)
        self.resize(420, 260)
        self.setFixedSize(420, 260)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(14)

        title_lbl = QLabel("●  New Macro Recording")
        title_lbl.setStyleSheet("font-size: 15px; font-weight: bold; color: #EF4444;")
        layout.addWidget(title_lbl)

        name_layout = QVBoxLayout()
        name_layout.setSpacing(6)
        name_layout.addWidget(QLabel("Macro Name:"))
        self._name_edit = QLineEdit("My Macro")
        name_layout.addWidget(self._name_edit)
        layout.addLayout(name_layout)

        self._chk_mouse = QCheckBox("Record detailed mouse movement paths")
        self._chk_mouse.setChecked(True)
        layout.addWidget(self._chk_mouse)

        hint_lbl = QLabel(
            "Tip: Once recording starts, perform your tasks. "
            "Return to KeyMacro and click 'Stop' when finished."
        )
        hint_lbl.setWordWrap(True)
        hint_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        layout.addWidget(hint_lbl)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_start = QPushButton("● Start Recording")
        btn_start.setObjectName("RecordBtn")
        btn_start.clicked.connect(self._on_start)
        btn_layout.addWidget(btn_start)

        layout.addLayout(btn_layout)

    def _on_start(self) -> None:
        name = self._name_edit.text().strip()
        if not name:
            self._name_edit.setText("My Macro")
        self.accept()

    @property
    def macro_name(self) -> str:
        return self._name_edit.text().strip() or "My Macro"

    @property
    def record_mouse_path(self) -> bool:
        return self._chk_mouse.isChecked()
