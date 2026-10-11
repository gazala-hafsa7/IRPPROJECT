"""
gui_qt/pages/builder_page.py
────────────────────────────
Full in-app Sequence Builder page with live syntax parsing,
metadata configuration, quick snippet helpers, and storage integration.
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from keymacro.models.action import Macro
from keymacro.models.sequence import (
    SequenceParseError,
    parse_sequence_with_metadata,
    serialize_sequence,
)

if TYPE_CHECKING:
    from keymacro.storage.macro_store import MacroStore


_DEFAULT_TEMPLATE = """# Macro Sequence Script
# Example instructions:
# combo: ctrl+c
# wait: 300ms
# type: Hello from KeyMacro!
# click: 400, 300

launch: "notepad.exe"
wait: 500ms
type: KeyMacro Automated Text
"""


class BuilderPage(QWidget):
    """Interactive visual code builder for KeyMacro sequences."""

    macro_saved = Signal(object)  # Emits saved Macro

    def __init__(
        self,
        store: "MacroStore",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._editing_macro_id: str | None = None

        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(24, 20, 24, 20)
        main_layout.setSpacing(16)

        # ── Header & Title ────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        title_lbl = QLabel("Sequence Builder & Editor")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)

        header_layout.addStretch()

        self._btn_new = QPushButton("＋ New Blank Sequence")
        self._btn_new.clicked.connect(self.clear_form)
        header_layout.addWidget(self._btn_new)

        main_layout.addLayout(header_layout)

        # ── Metadata Inputs Form ──────────────────────────────────────────────
        meta_card = QFrame()
        meta_card.setObjectName("Card")
        meta_grid = QGridLayout(meta_card)
        meta_grid.setContentsMargins(18, 14, 18, 14)
        meta_grid.setSpacing(12)

        meta_grid.addWidget(QLabel("Macro Name:"), 0, 0)
        self._name_input = QLineEdit("New Custom Macro")
        meta_grid.addWidget(self._name_input, 0, 1)

        meta_grid.addWidget(QLabel("Global Hotkey:"), 0, 2)
        self._hotkey_input = QLineEdit()
        self._hotkey_input.setPlaceholderText("e.g. ctrl+alt+k")
        meta_grid.addWidget(self._hotkey_input, 0, 3)

        meta_grid.addWidget(QLabel("Target Application:"), 1, 0)
        self._target_input = QLineEdit()
        self._target_input.setPlaceholderText("e.g. notepad.exe or leave empty for Global")
        meta_grid.addWidget(self._target_input, 1, 1)

        meta_grid.addWidget(QLabel("Description:"), 1, 2)
        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("Brief description of macro purpose")
        meta_grid.addWidget(self._desc_input, 1, 3)

        main_layout.addWidget(meta_card)

        # ── Editor Area (Script + Helper Snippets) ────────────────────────────
        editor_container = QHBoxLayout()
        editor_container.setSpacing(14)

        # Left: Script text editor
        editor_card = QFrame()
        editor_card.setObjectName("Card")
        editor_layout = QVBoxLayout(editor_card)
        editor_layout.setContentsMargins(14, 14, 14, 14)

        script_lbl = QLabel("Macro Instructions (Line-by-Line):")
        script_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        editor_layout.addWidget(script_lbl)

        self._script_edit = QPlainTextEdit()
        self._script_edit.setPlainText(_DEFAULT_TEMPLATE)
        self._script_edit.setStyleSheet(
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 13px; line-height: 1.4;"
        )
        self._script_edit.textChanged.connect(self._validate_syntax)
        editor_layout.addWidget(self._script_edit)

        editor_container.addWidget(editor_card, stretch=3)

        # Right: Snippet Helpers
        helpers_card = QFrame()
        helpers_card.setObjectName("Card")
        helpers_layout = QVBoxLayout(helpers_card)
        helpers_layout.setContentsMargins(14, 14, 14, 14)
        helpers_layout.setSpacing(8)

        helpers_title = QLabel("Insert Snippet")
        helpers_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        helpers_layout.addWidget(helpers_title)

        snippets = [
            ("⌨ Key Combo", "combo: ctrl+c\n"),
            ("🔤 Type Text", 'type: "Hello World"\n'),
            ("🖱 Left Click", "click: 500, 300\n"),
            ("🖱 Right Click", "click: right, 500, 300\n"),
            ("⏱ Wait Delay", "wait: 500ms\n"),
            ("🚀 Launch App", 'launch: "notepad.exe"\n'),
            ("🌐 Open URL", "plugin: browser.open_url url=https://google.com\n"),
            ("🔊 Mute Sound", "plugin: system.volume_mute\n"),
        ]

        for label, snippet in snippets:
            btn = QPushButton(f"＋ {label}")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _, s=snippet: self._insert_snippet(s))
            helpers_layout.addWidget(btn)

        helpers_layout.addStretch()
        editor_container.addWidget(helpers_card, stretch=1)

        main_layout.addLayout(editor_container, stretch=1)

        # ── Bottom Bar: Validation Status & Save ──────────────────────────────
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(12)

        self._status_lbl = QLabel("Ready to validate")
        self._status_lbl.setStyleSheet("font-size: 12px; color: #9CA3AF;")
        bottom_bar.addWidget(self._status_lbl)

        bottom_bar.addStretch()

        self._btn_validate = QPushButton("✓  Validate Syntax")
        self._btn_validate.clicked.connect(self._validate_syntax)
        bottom_bar.addWidget(self._btn_validate)

        self._btn_save = QPushButton("💾  Save Macro")
        self._btn_save.setObjectName("PrimaryBtn")
        self._btn_save.setCursor(Qt.PointingHandCursor)
        self._btn_save.clicked.connect(self._on_save_macro)
        bottom_bar.addWidget(self._btn_save)

        main_layout.addLayout(bottom_bar)

    def _insert_snippet(self, text: str) -> None:
        cursor = self._script_edit.textCursor()
        cursor.insertText(text)
        self._script_edit.setFocus()

    def _validate_syntax(self) -> bool:
        content = self._script_edit.toPlainText().strip()
        if not content:
            self._status_lbl.setText("Sequence is empty.")
            self._status_lbl.setStyleSheet("color: #9CA3AF;")
            return False

        try:
            actions, meta = parse_sequence_with_metadata(content)
            count = len(actions)
            self._status_lbl.setText(f"✓ Valid: {count} actions parsed successfully.")
            self._status_lbl.setStyleSheet("color: #10B981; font-weight: bold;")
            return True
        except SequenceParseError as err:
            self._status_lbl.setText(f"⚠ Syntax Error: {err.message} (Line {err.line_num})")
            self._status_lbl.setStyleSheet("color: #EF4444; font-weight: bold;")
            return False
        except Exception as exc:
            self._status_lbl.setText(f"⚠ Parse Error: {exc}")
            self._status_lbl.setStyleSheet("color: #EF4444;")
            return False

    def load_macro(self, macro: Macro) -> None:
        """Populate builder inputs to edit an existing macro."""
        self._editing_macro_id = macro.macro_id
        self._name_input.setText(macro.name)
        self._hotkey_input.setText(macro.hotkey or "")
        self._target_input.setText(macro.target_app or "")
        self._desc_input.setText(macro.description or "")

        seq_text = serialize_sequence(
            macro.actions,
            target_app=macro.target_app or "",
            hotkey=macro.hotkey or "",
        )
        self._script_edit.setPlainText(seq_text)
        self._validate_syntax()

    def clear_form(self) -> None:
        """Reset builder form."""
        self._editing_macro_id = None
        self._name_input.setText("New Custom Macro")
        self._hotkey_input.clear()
        self._target_input.clear()
        self._desc_input.clear()
        self._script_edit.setPlainText(_DEFAULT_TEMPLATE)
        self._validate_syntax()

    def _on_save_macro(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for the macro.")
            return

        content = self._script_edit.toPlainText().strip()
        try:
            actions, meta = parse_sequence_with_metadata(content)
        except Exception as exc:
            QMessageBox.critical(self, "Syntax Error", f"Cannot save macro with syntax errors:\n\n{exc}")
            return

        if not actions:
            QMessageBox.warning(self, "No Actions", "Sequence contains no executable actions.")
            return

        macro_id = self._editing_macro_id or str(uuid.uuid4())
        hotkey = self._hotkey_input.text().strip() or meta.get("hotkey")
        target_app = self._target_input.text().strip() or meta.get("target_app")
        desc = self._desc_input.text().strip()

        macro = Macro(
            macro_id=macro_id,
            name=name,
            actions=actions,
            hotkey=hotkey,
            target_app=target_app,
            description=desc,
        )

        self._store.save(macro)
        self._editing_macro_id = macro.macro_id

        QMessageBox.information(
            self,
            "Macro Saved",
            f"Macro '<b>{macro.name}</b>' saved successfully with {len(actions)} actions!\n\n"
            f"• Available immediately in your Macro Library\n"
            f"• Global hotkey: {hotkey or 'None'}",
        )
        self.macro_saved.emit(macro)
