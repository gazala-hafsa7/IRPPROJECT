"""
gui_qt/pages/builder_page.py
────────────────────────────
Full in-app Sequence Builder page with:
  • Live syntax parsing and action preview pane
  • App Picker popup for Launch commands (searchable list of installed apps)
  • Plugin Action Picker popup with per-parameter URL paste support
  • URL paste shortcut button
  • Spacious two-column layout with resizable splitter
"""

from __future__ import annotations

import re
import uuid
from typing import TYPE_CHECKING
from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from keymacro.models.action import Macro
from keymacro.models.sequence import (
    SequenceParseError,
    parse_sequence_with_metadata,
    serialize_sequence,
)
from keymacro.ai.macro_generator import MacroGenerator, MacroGeneratorError

if TYPE_CHECKING:
    from keymacro.launcher.app_scanner import AppScanner
    from keymacro.plugins.manager import PluginManager
    from keymacro.storage.macro_store import MacroStore


_DEFAULT_TEMPLATE = """\
# Macro Sequence Script
# Each line = one action. Examples:
#   combo: ctrl+c
#   wait: 300ms
#   type: Hello from KeyMacro!
#   click: 400, 300
#   launch: "notepad.exe"
#   plugin: browser.open_url url=https://google.com

launch: "notepad.exe"
wait: 500ms
type: KeyMacro Automated Text
"""

_URL_RE = re.compile(
    r"^(https?://|www\.|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})", re.IGNORECASE
)


def _is_url(text: str) -> bool:
    return bool(_URL_RE.match(text.strip())) if text else False


def _sanitize_url(text: str) -> str:
    t = text.strip().strip("\"'")
    if t.lower().startswith("www."):
        t = f"https://{t}"
    elif not t.lower().startswith(("http://", "https://")) and "." in t and " " not in t:
        t = f"https://{t}"
    return t


# ── App Picker Dialog ──────────────────────────────────────────────────────────

class AppPickerDialog(QDialog):
    """Small modal to pick an installed app and return its launch target."""

    def __init__(self, scanner: "AppScanner", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Choose App to Launch")
        self.setMinimumSize(500, 420)
        self.resize(520, 440)
        self.setWindowModality(Qt.ApplicationModal)

        self._scanner = scanner
        self._apps = []
        self.selected_target: str | None = None

        self._build_ui()
        self._load_apps()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(12)

        title = QLabel("Select an installed application to launch:")
        title.setStyleSheet("font-size: 13px; font-weight: bold;")
        layout.addWidget(title)

        self._search = QLineEdit()
        self._search.setPlaceholderText("🔍  Search apps by name or executable…")
        self._search.textChanged.connect(self._filter)
        layout.addWidget(self._search)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.itemDoubleClicked.connect(self._accept)
        layout.addWidget(self._list, stretch=1)

        # Manual entry fallback
        manual_row = QHBoxLayout()
        manual_lbl = QLabel("Or type manually:")
        manual_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px;")
        self._manual_entry = QLineEdit()
        self._manual_entry.setPlaceholderText("e.g. notepad.exe or C:\\path\\to\\app.exe")
        manual_row.addWidget(manual_lbl)
        manual_row.addWidget(self._manual_entry, stretch=1)
        layout.addLayout(manual_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _load_apps(self) -> None:
        self._apps = self._scanner.scan()
        self._populate(self._apps)

    def _populate(self, apps) -> None:
        self._list.clear()
        for app in apps:
            item = QListWidgetItem(f"{app.name}  —  {app.category}  —  {app.target}")
            item.setData(Qt.UserRole, app.target)
            self._list.addItem(item)

    def _filter(self, query: str) -> None:
        q = query.strip().lower()
        if not q:
            self._populate(self._apps)
        else:
            self._populate([a for a in self._apps
                            if q in a.name.lower() or q in a.target.lower()])

    def _accept(self) -> None:
        # Prefer list selection, fall back to manual entry
        items = self._list.selectedItems()
        if items:
            self.selected_target = items[0].data(Qt.UserRole)
        elif self._manual_entry.text().strip():
            self.selected_target = self._manual_entry.text().strip()
        else:
            QMessageBox.warning(self, "No Selection", "Please select an app or type a path.")
            return
        self.accept()


# ── Plugin Action Picker Dialog ────────────────────────────────────────────────

class PluginPickerDialog(QDialog):
    """Modal to pick a plugin action, fill parameters, and return the sequence line."""

    def __init__(self, plugin_manager: "PluginManager", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Insert Plugin Action")
        self.setMinimumSize(740, 520)
        self.resize(800, 560)
        self.setWindowModality(Qt.ApplicationModal)

        self._mgr = plugin_manager
        self._actions = plugin_manager.get_all_actions()  # list[(plugin, spec)]
        self.result_line: str | None = None

        self._param_widgets: dict[str, QLineEdit] = {}
        self._current_idx: int = -1

        self._build_ui()
        self._populate_list()

    def _build_ui(self) -> None:
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(10)

        splitter = QSplitter(Qt.Horizontal)

        # ── Left: action list ─────────────────────────────────────────────────
        left = QFrame()
        left.setObjectName("Card")
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(10, 10, 10, 10)
        left_layout.setSpacing(8)

        lbl = QLabel("Plugin Actions")
        lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        left_layout.addWidget(lbl)

        self._list = QListWidget()
        self._list.setAlternatingRowColors(True)
        self._list.currentRowChanged.connect(self._on_select)
        left_layout.addWidget(self._list)

        splitter.addWidget(left)

        # ── Right: detail + params ────────────────────────────────────────────
        right = QFrame()
        right.setObjectName("Card")
        self._right_layout = QVBoxLayout(right)
        self._right_layout.setContentsMargins(16, 14, 16, 14)
        self._right_layout.setSpacing(10)

        self._lbl_name = QLabel("← Select an action")
        self._lbl_name.setStyleSheet("font-size: 15px; font-weight: bold;")
        self._right_layout.addWidget(self._lbl_name)

        self._lbl_desc = QLabel("")
        self._lbl_desc.setWordWrap(True)
        self._lbl_desc.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        self._right_layout.addWidget(self._lbl_desc)

        self._lbl_example_title = QLabel("Example syntax:")
        self._lbl_example_title.setStyleSheet("font-size: 11px; font-style: italic; color: #9CA3AF;")
        self._right_layout.addWidget(self._lbl_example_title)

        self._lbl_example = QLabel("")
        self._lbl_example.setStyleSheet(
            "font-family: 'Consolas','Courier New',monospace; font-size: 12px; "
            "background-color: #23253B; color: #C084FC; padding: 6px 10px; border-radius: 6px; border: 1px solid #363852;"
        )
        self._lbl_example.setWordWrap(True)
        self._right_layout.addWidget(self._lbl_example)

        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        self._right_layout.addWidget(sep)

        params_lbl = QLabel("Parameters:")
        params_lbl.setStyleSheet("font-weight: bold;")
        self._right_layout.addWidget(params_lbl)

        # Scroll area for params
        self._params_scroll = QScrollArea()
        self._params_scroll.setWidgetResizable(True)
        self._params_scroll.setFrameShape(QFrame.NoFrame)
        self._params_scroll.setStyleSheet("background: transparent; border: none;")
        self._params_container = QWidget()
        self._params_container.setStyleSheet("background: transparent;")
        self._params_form = QVBoxLayout(self._params_container)
        self._params_form.setContentsMargins(0, 4, 0, 4)
        self._params_form.setSpacing(8)
        self._params_form.addStretch()
        self._params_scroll.setWidget(self._params_container)
        self._right_layout.addWidget(self._params_scroll, stretch=1)

        # Bottom buttons
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setMinimumHeight(34)
        cancel_btn.setCursor(Qt.PointingHandCursor)
        cancel_btn.clicked.connect(self.reject)
        btn_row.addWidget(cancel_btn)

        self._insert_btn = QPushButton("➕  Insert Action")
        self._insert_btn.setObjectName("PrimaryBtn")
        self._insert_btn.setMinimumHeight(34)
        self._insert_btn.setCursor(Qt.PointingHandCursor)
        self._insert_btn.setEnabled(False)
        self._insert_btn.clicked.connect(self._do_insert)
        btn_row.addWidget(self._insert_btn)

        self._right_layout.addLayout(btn_row)

        splitter.addWidget(right)
        splitter.setSizes([240, 480])
        root.addWidget(splitter)

    def _populate_list(self) -> None:
        self._list.clear()
        for plugin, spec in self._actions:
            self._list.addItem(f"[{plugin.name}]  {spec.name}")
        if self._actions:
            self._list.setCurrentRow(0)

    def _on_select(self, row: int) -> None:
        if row < 0 or row >= len(self._actions):
            return
        self._current_idx = row
        plugin, spec = self._actions[row]

        self._lbl_name.setText(f"{plugin.name}  ›  {spec.name}")
        self._lbl_desc.setText(spec.description)
        example = spec.example or f"plugin: {plugin.plugin_id}.{spec.action_id}"
        self._lbl_example.setText(example)

        # Rebuild param widgets
        self._param_widgets.clear()
        # Clear old param widgets (remove all except the stretch at end)
        while self._params_form.count() > 1:
            item = self._params_form.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        if spec.params_schema:
            for param_name, param_help in spec.params_schema.items():
                is_url = any(k in param_name.lower() for k in ("url", "link", "address", "web"))

                param_card = QFrame()
                param_card.setObjectName("ParamCard")
                param_card_layout = QVBoxLayout(param_card)
                param_card_layout.setContentsMargins(12, 10, 12, 10)
                param_card_layout.setSpacing(6)

                # Header: Parameter name + help description
                hdr_layout = QHBoxLayout()
                hdr_lbl = QLabel(f"<b>{param_name}</b>")
                hdr_lbl.setStyleSheet("font-size: 13px; font-weight: bold; color: #F3F4F6;")
                hdr_layout.addWidget(hdr_lbl)

                if param_help:
                    help_lbl = QLabel(f"—  {param_help}")
                    help_lbl.setStyleSheet("color: #9CA3AF; font-size: 11px;")
                    help_lbl.setWordWrap(True)
                    hdr_layout.addWidget(help_lbl, stretch=1)
                else:
                    hdr_layout.addStretch()

                param_card_layout.addLayout(hdr_layout)

                # Input Row: Full-width QLineEdit + (if is_url) prominent Paste URL button
                input_row = QHBoxLayout()
                input_row.setSpacing(8)

                entry = QLineEdit()
                entry.setPlaceholderText(f"Enter {param_name}…")
                entry.setMinimumHeight(32)
                if is_url:
                    entry.setPlaceholderText("e.g. https://google.com")
                    try:
                        from PySide6.QtGui import QGuiApplication
                        clip = QGuiApplication.clipboard().text().strip()
                        if _is_url(clip):
                            entry.setText(_sanitize_url(clip))
                    except Exception:
                        pass
                input_row.addWidget(entry, stretch=1)

                if is_url:
                    paste_btn = QPushButton("📋 Paste URL")
                    paste_btn.setCursor(Qt.PointingHandCursor)
                    paste_btn.setMinimumHeight(32)
                    paste_btn.setToolTip("Paste & sanitize URL from clipboard")
                    paste_btn.setStyleSheet(
                        "font-size: 12px; font-weight: bold; padding: 6px 14px; "
                        "border: 1.5px solid #8B5CF6; border-radius: 8px; "
                        "background-color: #2F2447; color: #C084FC;"
                    )
                    paste_btn.clicked.connect(lambda _=False, target=entry: self._paste_to_target(target))
                    input_row.addWidget(paste_btn)

                param_card_layout.addLayout(input_row)

                self._params_form.insertWidget(self._params_form.count() - 1, param_card)
                self._param_widgets[param_name] = entry
        else:
            no_params = QLabel("✓ No parameters required for this action — ready to insert!")
            no_params.setStyleSheet(
                "color: #10B981; font-weight: bold; font-size: 13px; "
                "padding: 14px; background-color: #064E3B; border-radius: 8px;"
            )
            self._params_form.insertWidget(self._params_form.count() - 1, no_params)

        self._insert_btn.setEnabled(True)

    def _paste_to_target(self, target: QLineEdit) -> None:
        from PySide6.QtGui import QGuiApplication
        txt = QGuiApplication.clipboard().text().strip()
        if txt:
            target.setText(_sanitize_url(txt))

    def _do_insert(self) -> None:
        if self._current_idx < 0 or self._current_idx >= len(self._actions):
            return
        plugin, spec = self._actions[self._current_idx]
        parts = [f"plugin: {plugin.plugin_id}.{spec.action_id}"]
        for param_name, entry in self._param_widgets.items():
            val = entry.text().strip()
            if val:
                if " " in val or '"' in val:
                    parts.append(f'{param_name}="{val}"')
                else:
                    parts.append(f"{param_name}={val}")
        self.result_line = " ".join(parts)
        self.accept()


# ── URL Paste Dialog ───────────────────────────────────────────────────────────

class UrlPasteDialog(QDialog):
    """Tiny dialog to enter/paste a URL for a browser.open_url action."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Paste / Open URL")
        self.setFixedSize(480, 160)
        self.setWindowModality(Qt.ApplicationModal)
        self.result_line: str | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        layout.addWidget(QLabel("Enter or paste the URL to open in the browser:"))

        url_row = QHBoxLayout()
        self._entry = QLineEdit()
        self._entry.setPlaceholderText("https://example.com")
        # Pre-fill from clipboard
        try:
            from PySide6.QtGui import QGuiApplication
            clip = QGuiApplication.clipboard().text().strip()
            if _is_url(clip):
                self._entry.setText(_sanitize_url(clip))
        except Exception:
            pass
        url_row.addWidget(self._entry, stretch=1)

        paste_btn = QPushButton("📋 Paste")
        paste_btn.setFixedWidth(70)
        paste_btn.clicked.connect(self._paste)
        url_row.addWidget(paste_btn)
        layout.addLayout(url_row)

        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _paste(self, checked: bool = False) -> None:
        from PySide6.QtGui import QGuiApplication
        txt = QGuiApplication.clipboard().text().strip()
        if txt:
            self._entry.setText(_sanitize_url(txt))

    def _accept(self) -> None:
        url = self._entry.text().strip()
        if not url:
            QMessageBox.warning(self, "Empty URL", "Please enter a URL.")
            return
        url = _sanitize_url(url)
        self.result_line = (
            f'plugin: browser.open_url url="{url}"'
            if " " in url else
            f"plugin: browser.open_url url={url}"
        )
        self.accept()


# ── AI Generate Dialog ────────────────────────────────────────────────────────

class AIGenerateDialog(QDialog):
    """
    AI-powered macro generation dialog.
    Lets the user describe their automation in plain English,
    then calls Gemini to produce a ready-to-use sequence script.
    """

    def __init__(
        self,
        generator: "MacroGenerator | None",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("✨ AI Macro Generator")
        self.setMinimumSize(620, 480)
        self.resize(660, 520)
        self.setWindowModality(Qt.ApplicationModal)
        self._generator = generator
        self.result_script: str | None = None
        self.last_description: str = ""
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(22, 20, 22, 20)
        layout.setSpacing(14)

        # Title
        title = QLabel("✨  Describe your automation task")
        title.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(title)

        subtitle = QLabel(
            "Type what you want to automate in plain English — AI will generate the sequence script."
        )
        subtitle.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        layout.addWidget(subtitle)

        # API Key row (shown if generator not configured)
        self._key_frame = QFrame()
        self._key_frame.setObjectName("Card")
        key_layout = QHBoxLayout(self._key_frame)
        key_layout.setContentsMargins(12, 8, 12, 8)
        key_layout.addWidget(QLabel("Gemini API Key:"))
        self._key_input = QLineEdit()
        self._key_input.setEchoMode(QLineEdit.Password)
        self._key_input.setPlaceholderText("AIza… (get free key at aistudio.google.com)")
        if self._generator and self._generator._api_key:
            self._key_input.setText(self._generator._api_key)
        key_layout.addWidget(self._key_input, stretch=1)
        layout.addWidget(self._key_frame)

        # Description input
        desc_lbl = QLabel("Task description:")
        desc_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(desc_lbl)

        self._desc_edit = QPlainTextEdit()
        self._desc_edit.setFixedHeight(90)
        self._desc_edit.setPlaceholderText(
            "e.g. Open Chrome, go to gmail.com, wait 2 seconds, then type my name and press Enter"
        )
        self._desc_edit.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 13px;"
        )
        layout.addWidget(self._desc_edit)

        # Generate button
        gen_row = QHBoxLayout()
        self._btn_generate = QPushButton("✨  Generate Script")
        self._btn_generate.setObjectName("PrimaryBtn")
        self._btn_generate.setMinimumHeight(36)
        self._btn_generate.setCursor(Qt.PointingHandCursor)
        self._btn_generate.clicked.connect(self._do_generate)
        gen_row.addWidget(self._btn_generate)
        self._lbl_status = QLabel("")
        self._lbl_status.setStyleSheet("color: #9CA3AF; font-size: 12px;")
        gen_row.addWidget(self._lbl_status)
        gen_row.addStretch()
        layout.addLayout(gen_row)

        # Result preview
        result_lbl = QLabel("Generated script (editable):")
        result_lbl.setStyleSheet("font-weight: bold;")
        layout.addWidget(result_lbl)

        self._result_edit = QPlainTextEdit()
        self._result_edit.setStyleSheet(
            "font-family: 'Consolas','Courier New',monospace; font-size: 13px;"
        )
        self._result_edit.setPlaceholderText("Generated script will appear here…")
        layout.addWidget(self._result_edit, stretch=1)

        # Buttons
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.button(QDialogButtonBox.Ok).setText("✅  Use This Script")
        btns.accepted.connect(self._accept)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _do_generate(self) -> None:
        description = self._desc_edit.toPlainText().strip()
        if not description:
            QMessageBox.warning(self, "Empty Description", "Please describe what you want to automate.")
            return

        api_key = self._key_input.text().strip()
        if not api_key:
            QMessageBox.warning(
                self, "No API Key",
                "Please enter your Gemini API key.\n\nGet a free key at: https://aistudio.google.com/app/apikey"
            )
            return

        # Create or update generator with provided key
        from keymacro.ai.macro_generator import MacroGenerator
        generator = MacroGenerator(api_key=api_key)

        self._btn_generate.setEnabled(False)
        self._lbl_status.setText("⏳ Generating…")

        def _on_result(script: str) -> None:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._show_result(script))

        def _on_error(msg: str) -> None:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(0, lambda: self._show_error(msg))

        self.last_description = description
        generator.generate_async(description, on_result=_on_result, on_error=_on_error)

    def _show_result(self, script: str) -> None:
        self._result_edit.setPlainText(script)
        self._lbl_status.setText("✅ Script generated!")
        self._lbl_status.setStyleSheet("color: #10B981; font-size: 12px; font-weight: bold;")
        self._btn_generate.setEnabled(True)

    def _show_error(self, msg: str) -> None:
        self._lbl_status.setText(f"⚠ {msg[:80]}")
        self._lbl_status.setStyleSheet("color: #EF4444; font-size: 12px;")
        self._btn_generate.setEnabled(True)

    def _accept(self) -> None:
        script = self._result_edit.toPlainText().strip()
        if not script:
            QMessageBox.warning(self, "No Script", "Generate a script first before accepting.")
            return
        self.result_script = script
        self.accept()


# ── BuilderPage ───────────────────────────────────────────────────────────────

class BuilderPage(QWidget):
    """Interactive visual code builder for KeyMacro sequences."""

    macro_saved = Signal(object)  # Emits saved Macro

    def __init__(
        self,
        store: "MacroStore",
        scanner: "AppScanner | None" = None,
        plugin_manager: "PluginManager | None" = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._store = store
        self._scanner = scanner
        self._plugin_mgr = plugin_manager
        self._editing_macro_id: str | None = None
        self._action_line_indices: list[int] = []
        self._ai_generator: MacroGenerator | None = None  # set via set_ai_generator()

        self._build_ui()

    def _build_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 16, 20, 16)
        main_layout.setSpacing(12)

        # ── Header ────────────────────────────────────────────────────────────
        header_layout = QHBoxLayout()
        title_lbl = QLabel("Sequence Builder & Editor")
        title_lbl.setStyleSheet("font-size: 18px; font-weight: bold;")
        header_layout.addWidget(title_lbl)
        header_layout.addStretch()

        # ✨ AI Generate button
        self._btn_ai_generate = QPushButton("✨  AI Generate")
        self._btn_ai_generate.setObjectName("PrimaryBtn")
        self._btn_ai_generate.setCursor(Qt.PointingHandCursor)
        self._btn_ai_generate.setToolTip(
            "Describe what you want to automate in plain English\n"
            "and AI will generate the sequence script for you."
        )
        self._btn_ai_generate.clicked.connect(self._on_ai_generate)
        header_layout.addWidget(self._btn_ai_generate)

        self._btn_new = QPushButton("＋  New Blank Sequence")
        self._btn_new.clicked.connect(self.clear_form)
        header_layout.addWidget(self._btn_new)

        main_layout.addLayout(header_layout)

        # ── Metadata Card ─────────────────────────────────────────────────────
        meta_card = QFrame()
        meta_card.setObjectName("Card")
        meta_grid = QGridLayout(meta_card)
        meta_grid.setContentsMargins(16, 12, 16, 12)
        meta_grid.setHorizontalSpacing(12)
        meta_grid.setVerticalSpacing(8)

        meta_grid.addWidget(QLabel("Macro Name:"), 0, 0)
        self._name_input = QLineEdit("New Custom Macro")
        meta_grid.addWidget(self._name_input, 0, 1)

        meta_grid.addWidget(QLabel("Global Hotkey:"), 0, 2)
        self._hotkey_input = QLineEdit()
        self._hotkey_input.setPlaceholderText("e.g. ctrl+alt+k")
        meta_grid.addWidget(self._hotkey_input, 0, 3)

        meta_grid.addWidget(QLabel("Target App:"), 1, 0)
        self._target_input = QLineEdit()
        self._target_input.setPlaceholderText("e.g. notepad.exe  or leave empty for Global")
        meta_grid.addWidget(self._target_input, 1, 1)

        meta_grid.addWidget(QLabel("Description:"), 1, 2)
        self._desc_input = QLineEdit()
        self._desc_input.setPlaceholderText("Brief description")
        meta_grid.addWidget(self._desc_input, 1, 3)

        meta_grid.setColumnStretch(1, 2)
        meta_grid.setColumnStretch(3, 2)

        main_layout.addWidget(meta_card)

        # ── Quick-Insert Toolbar ──────────────────────────────────────────────
        toolbar_card = QFrame()
        toolbar_card.setObjectName("Card")
        toolbar_layout = QHBoxLayout(toolbar_card)
        toolbar_layout.setContentsMargins(14, 8, 14, 8)
        toolbar_layout.setSpacing(6)

        insert_lbl = QLabel("Insert:")
        insert_lbl.setStyleSheet("font-weight: bold; font-size: 12px; color: #9CA3AF;")
        toolbar_layout.addWidget(insert_lbl)

        snippets = [
            ("⌨  Combo",       self._insert_combo),
            ("🔤  Type Text",   self._insert_text),
            ("🖱  Click",       self._insert_click),
            ("🚀  Launch App",  self._insert_launch),
            ("🔌  Plugin Action", self._insert_plugin),
            ("🌐  URL",         self._insert_url),
            ("⏱  Wait",        self._insert_wait),
        ]
        for label, fn in snippets:
            btn = QPushButton(label)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setMinimumHeight(30)
            btn.setFixedHeight(32)
            btn.clicked.connect(fn)
            toolbar_layout.addWidget(btn)

        toolbar_layout.addStretch()

        strip_btn = QPushButton("🧹  Strip Delays")
        strip_btn.setMinimumHeight(30)
        strip_btn.setFixedHeight(32)
        strip_btn.setToolTip("Remove all wait/delay actions for instant execution")
        strip_btn.clicked.connect(self._strip_delays)
        toolbar_layout.addWidget(strip_btn)

        main_layout.addWidget(toolbar_card)

        # ── Main splitter: Editor  |  Live Preview ────────────────────────────
        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(8)

        # Left: editor
        editor_card = QFrame()
        editor_card.setObjectName("Card")
        editor_layout = QVBoxLayout(editor_card)
        editor_layout.setContentsMargins(12, 12, 12, 12)
        editor_layout.setSpacing(8)

        script_hdr = QHBoxLayout()
        script_lbl = QLabel("Macro Instructions (one action per line):")
        script_lbl.setStyleSheet("font-weight: bold; font-size: 13px;")
        script_hdr.addWidget(script_lbl)
        script_hdr.addStretch()

        self._btn_delete_editor_line = QPushButton("🗑  Delete Line")
        self._btn_delete_editor_line.setToolTip("Delete line at current text cursor")
        self._btn_delete_editor_line.setFixedHeight(24)
        self._btn_delete_editor_line.setCursor(Qt.PointingHandCursor)
        self._btn_delete_editor_line.clicked.connect(self._delete_current_editor_line)
        script_hdr.addWidget(self._btn_delete_editor_line)

        self._status_lbl = QLabel("Ready")
        self._status_lbl.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        script_hdr.addWidget(self._status_lbl)
        editor_layout.addLayout(script_hdr)

        self._script_edit = QPlainTextEdit()
        self._script_edit.setPlainText(_DEFAULT_TEMPLATE)
        self._script_edit.setStyleSheet(
            "font-family: 'Consolas','Courier New',monospace; font-size: 13px;"
        )
        self._script_edit.textChanged.connect(self._on_text_changed)
        editor_layout.addWidget(self._script_edit)

        splitter.addWidget(editor_card)

        # Right: live preview
        preview_card = QFrame()
        preview_card.setObjectName("Card")
        preview_layout = QVBoxLayout(preview_card)
        preview_layout.setContentsMargins(12, 12, 12, 12)
        preview_layout.setSpacing(8)

        preview_hdr = QHBoxLayout()
        self._preview_title = QLabel("Live Preview  (0 actions)")
        self._preview_title.setStyleSheet("font-weight: bold; font-size: 13px;")
        preview_hdr.addWidget(self._preview_title)
        preview_hdr.addStretch()

        self._btn_delete_action = QPushButton("🗑  Delete Action")
        self._btn_delete_action.setObjectName("DangerBtn")
        self._btn_delete_action.setEnabled(False)
        self._btn_delete_action.setCursor(Qt.PointingHandCursor)
        self._btn_delete_action.setToolTip("Delete selected action from sequence (Del)")
        self._btn_delete_action.setFixedHeight(26)
        self._btn_delete_action.clicked.connect(self._delete_selected_action)
        preview_hdr.addWidget(self._btn_delete_action)

        preview_layout.addLayout(preview_hdr)

        self._preview_table = QTableWidget()
        self._preview_table.setColumnCount(3)
        self._preview_table.setHorizontalHeaderLabels(["#", "Type", "Step Summary"])
        self._preview_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self._preview_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        self._preview_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.Stretch)
        self._preview_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self._preview_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self._preview_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self._preview_table.setAlternatingRowColors(True)
        self._preview_table.verticalHeader().setVisible(False)
        self._preview_table.setContextMenuPolicy(Qt.CustomContextMenu)
        self._preview_table.customContextMenuRequested.connect(self._show_preview_context_menu)
        self._preview_table.itemSelectionChanged.connect(self._on_preview_selection_changed)
        self._preview_table.installEventFilter(self)
        preview_layout.addWidget(self._preview_table)

        preview_hint = QLabel("💡 Tip: Click any row to highlight it in the editor, or press Del to delete.")
        preview_hint.setStyleSheet("font-size: 11px; color: #9CA3AF;")
        preview_layout.addWidget(preview_hint)

        splitter.addWidget(preview_card)
        splitter.setSizes([560, 320])

        main_layout.addWidget(splitter, stretch=1)

        # ── Bottom bar ────────────────────────────────────────────────────────
        bottom_bar = QHBoxLayout()
        bottom_bar.setSpacing(10)

        self._btn_validate = QPushButton("✓  Validate Syntax")
        self._btn_validate.clicked.connect(self._validate_syntax)
        bottom_bar.addWidget(self._btn_validate)

        bottom_bar.addStretch()

        self._btn_save = QPushButton("💾  Save Macro")
        self._btn_save.setObjectName("PrimaryBtn")
        self._btn_save.setCursor(Qt.PointingHandCursor)
        self._btn_save.clicked.connect(self._on_save_macro)
        bottom_bar.addWidget(self._btn_save)

        main_layout.addLayout(bottom_bar)

        # Populate initial template preview
        self._validate_syntax(silent=True)

    # ── AI Generation ─────────────────────────────────────────────────────────

    def set_ai_generator(self, generator: "MacroGenerator") -> None:
        """Called by main window to inject the configured AI generator."""
        self._ai_generator = generator

    def _on_ai_generate(self) -> None:
        """Open the AI generation dialog and fill the script editor with result."""
        dialog = AIGenerateDialog(self._ai_generator, self)
        if dialog.exec() == QDialog.Accepted and dialog.result_script:
            # Replace current script with generated one
            self._script_edit.setPlainText(dialog.result_script)
            self._validate_syntax(silent=True)
            # Auto-fill macro name if field is default
            if self._name_input.text() in ("New Custom Macro", ""):
                self._name_input.setText(dialog.last_description[:40] if dialog.last_description else "AI Generated Macro")

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _append_line(self, line: str) -> None:
        text = self._script_edit.toPlainText()
        if text and not text.endswith("\n"):
            text += "\n"
        self._script_edit.setPlainText(text + line + "\n")
        # Move cursor to end
        cursor = self._script_edit.textCursor()
        cursor.movePosition(QTextCursor.End)
        self._script_edit.setTextCursor(cursor)

    def _on_text_changed(self) -> None:
        self._validate_syntax(silent=True)

    def _validate_syntax(self, silent: bool = False) -> bool:
        content = self._script_edit.toPlainText().strip()
        if not content:
            self._status_lbl.setText("Sequence is empty.")
            self._status_lbl.setStyleSheet("font-size: 11px; color: #9CA3AF;")
            self._preview_title.setText("Live Preview  (0 actions)")
            self._preview_table.setRowCount(0)
            self._action_line_indices = []
            if hasattr(self, "_btn_delete_action"):
                self._btn_delete_action.setEnabled(False)
            return False

        try:
            # Map each action to its 0-indexed line number in self._script_edit
            lines = self._script_edit.toPlainText().splitlines()
            line_indices: list[int] = []
            for idx, raw_line in enumerate(lines):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue
                clean = line.lstrip("#").strip()
                if ":" in clean:
                    k, _, _ = clean.partition(":")
                    if k.strip().lower() in ("target_app", "targetapp", "target_application", "hotkey", "shortcut"):
                        continue
                line_indices.append(idx)
            self._action_line_indices = line_indices

            actions, meta = parse_sequence_with_metadata(content)
            count = len(actions)
            self._status_lbl.setText(f"✓ Valid — {count} action(s)")
            self._status_lbl.setStyleSheet("font-size: 11px; color: #10B981; font-weight: bold;")
            self._preview_title.setText(f"Live Preview  ({count} actions)")
            self._update_preview(actions)
            return True
        except SequenceParseError as err:
            msg = f"⚠ Line {err.line_num}: {err.message}"
            self._status_lbl.setText(msg)
            self._status_lbl.setStyleSheet("font-size: 11px; color: #EF4444; font-weight: bold;")
            if not silent:
                QMessageBox.warning(self, "Syntax Error", msg)
            return False
        except Exception as exc:
            self._status_lbl.setText(f"⚠ Error: {exc}")
            self._status_lbl.setStyleSheet("font-size: 11px; color: #EF4444;")
            return False

    def _update_preview(self, actions) -> None:
        self._preview_table.setRowCount(0)
        self._preview_table.setRowCount(len(actions))
        for i, action in enumerate(actions):
            idx_item = QTableWidgetItem(str(i + 1))
            idx_item.setTextAlignment(Qt.AlignCenter)
            type_item = QTableWidgetItem(action.action_type.value.replace("_", " ").title())
            desc_item = QTableWidgetItem(action.description)
            self._preview_table.setItem(i, 0, idx_item)
            self._preview_table.setItem(i, 1, type_item)
            self._preview_table.setItem(i, 2, desc_item)

    def _on_preview_selection_changed(self) -> None:
        row = self._preview_table.currentRow()
        has_sel = row >= 0 and self._preview_table.rowCount() > 0
        if hasattr(self, "_btn_delete_action"):
            self._btn_delete_action.setEnabled(has_sel)
        if has_sel and hasattr(self, "_action_line_indices") and 0 <= row < len(self._action_line_indices):
            line_idx = self._action_line_indices[row]
            doc = self._script_edit.document()
            block = doc.findBlockByLineNumber(line_idx)
            if block.isValid():
                cursor = self._script_edit.textCursor()
                cursor.setPosition(block.position())
                cursor.movePosition(QTextCursor.EndOfLine, QTextCursor.KeepAnchor)
                self._script_edit.setTextCursor(cursor)
                self._script_edit.ensureCursorVisible()

    def _show_preview_context_menu(self, pos) -> None:
        row = self._preview_table.currentRow()
        if row < 0:
            return
        menu = QMenu(self)
        del_act = menu.addAction("🗑  Delete Selected Action")
        del_act.triggered.connect(self._delete_selected_action)
        menu.exec(self._preview_table.viewport().mapToGlobal(pos))

    def eventFilter(self, watched, event):
        if watched == getattr(self, "_preview_table", None) and event.type() == QEvent.KeyPress:
            if event.key() in (Qt.Key_Delete, Qt.Key_Backspace):
                if self._preview_table.currentRow() >= 0:
                    self._delete_selected_action()
                    return True
        return super().eventFilter(watched, event)

    def _delete_selected_action(self) -> None:
        row = self._preview_table.currentRow()
        if row < 0:
            return

        lines = self._script_edit.toPlainText().splitlines()
        if hasattr(self, "_action_line_indices") and 0 <= row < len(self._action_line_indices):
            line_idx = self._action_line_indices[row]
            if 0 <= line_idx < len(lines):
                del lines[line_idx]
                new_text = "\n".join(lines)
                if new_text and not new_text.endswith("\n"):
                    new_text += "\n"
                self._script_edit.setPlainText(new_text)
                total = self._preview_table.rowCount()
                if total > 0:
                    next_row = min(row, total - 1)
                    self._preview_table.selectRow(next_row)
                return

        # Fallback using parse & serialize if line mapping is unavailable
        content = self._script_edit.toPlainText().strip()
        try:
            actions, meta = parse_sequence_with_metadata(content)
            if 0 <= row < len(actions):
                del actions[row]
                new_text = serialize_sequence(
                    actions,
                    target_app=meta.get("target_app", ""),
                    hotkey=meta.get("hotkey", ""),
                )
                self._script_edit.setPlainText(new_text)
                total = self._preview_table.rowCount()
                if total > 0:
                    next_row = min(row, total - 1)
                    self._preview_table.selectRow(next_row)
        except Exception:
            pass

    def _delete_current_editor_line(self) -> None:
        cursor = self._script_edit.textCursor()
        block_num = cursor.blockNumber()
        lines = self._script_edit.toPlainText().splitlines()
        if not lines:
            return
        if block_num >= len(lines):
            block_num = len(lines) - 1
        if 0 <= block_num < len(lines):
            del lines[block_num]
            new_text = "\n".join(lines)
            if new_text and not new_text.endswith("\n"):
                new_text += "\n"
            self._script_edit.setPlainText(new_text)
            doc = self._script_edit.document()
            target_block_num = min(block_num, doc.blockCount() - 1)
            target_block = doc.findBlockByLineNumber(max(0, target_block_num))
            if target_block.isValid():
                new_cursor = self._script_edit.textCursor()
                new_cursor.setPosition(target_block.position())
                self._script_edit.setTextCursor(new_cursor)

    def _strip_delays(self) -> None:
        content = self._script_edit.toPlainText().strip()
        if not content:
            return
        try:
            actions, _ = parse_sequence_with_metadata(content)
            from keymacro.models.sequence import strip_delays, serialize_sequence
            cleaned = strip_delays(actions)
            self._script_edit.setPlainText(serialize_sequence(cleaned))
            QMessageBox.information(self, "Delays Stripped",
                                    "All delay/wait actions have been removed.")
        except Exception as exc:
            QMessageBox.critical(self, "Error", str(exc))

    # ── Quick-Insert Handlers ─────────────────────────────────────────────────

    def _insert_combo(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Insert Keyboard Shortcut / Combo")
        dlg.setFixedSize(400, 130)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Enter shortcut combination (e.g. ctrl+c, alt+f4):"))
        entry = QLineEdit("ctrl+c")
        lay.addWidget(entry)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.Accepted and entry.text().strip():
            self._append_line(f"combo: {entry.text().strip().lower()}")

    def _insert_text(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Insert Type Text")
        dlg.setFixedSize(440, 130)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Enter text to type:"))
        entry = QLineEdit()
        entry.setPlaceholderText("Hello World")
        lay.addWidget(entry)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.Accepted and entry.text() is not None:
            self._append_line(f'type: "{entry.text()}"')

    def _insert_click(self) -> None:
        try:
            import pyautogui
            cx, cy = pyautogui.position()
            default = f"{cx}, {cy}"
        except Exception:
            default = "500, 300"

        dlg = QDialog(self)
        dlg.setWindowTitle("Insert Mouse Click")
        dlg.setFixedSize(420, 140)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel(f"Coordinates (current: {default})\nFormat: [button,] x, y"))
        entry = QLineEdit(default)
        lay.addWidget(entry)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.Accepted and entry.text().strip():
            self._append_line(f"click: {entry.text().strip()}")

    def _insert_launch(self) -> None:
        """Show the App Picker popup to choose an installed app."""
        if self._scanner:
            dlg = AppPickerDialog(self._scanner, self)
            if dlg.exec() == QDialog.Accepted and dlg.selected_target:
                target = dlg.selected_target
                self._append_line(
                    f'launch: "{target}"' if (" " in target or target.endswith(".exe")) else f"launch: {target}"
                )
        else:
            # Fallback: simple text input
            dlg = QDialog(self)
            dlg.setWindowTitle("Launch Application")
            dlg.setFixedSize(440, 130)
            lay = QVBoxLayout(dlg)
            lay.addWidget(QLabel("Enter executable name or path:"))
            entry = QLineEdit()
            entry.setPlaceholderText("notepad.exe")
            lay.addWidget(entry)
            btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
            btns.accepted.connect(dlg.accept)
            btns.rejected.connect(dlg.reject)
            lay.addWidget(btns)
            if dlg.exec() == QDialog.Accepted and entry.text().strip():
                target = entry.text().strip()
                self._append_line(f'launch: "{target}"')

    def _insert_plugin(self) -> None:
        """Show the Plugin Action Picker popup."""
        if not self._plugin_mgr:
            QMessageBox.information(self, "Plugins", "Plugin manager not available.")
            return
        actions = self._plugin_mgr.get_all_actions()
        if not actions:
            QMessageBox.information(self, "Plugins", "No plugin actions registered.")
            return
        dlg = PluginPickerDialog(self._plugin_mgr, self)
        if dlg.exec() == QDialog.Accepted and dlg.result_line:
            self._append_line(dlg.result_line)

    def _insert_url(self) -> None:
        """URL paste dialog → browser.open_url plugin action."""
        dlg = UrlPasteDialog(self)
        if dlg.exec() == QDialog.Accepted and dlg.result_line:
            self._append_line(dlg.result_line)

    def _insert_wait(self) -> None:
        dlg = QDialog(self)
        dlg.setWindowTitle("Insert Wait / Pause")
        dlg.setFixedSize(380, 130)
        lay = QVBoxLayout(dlg)
        lay.addWidget(QLabel("Enter duration (e.g. 200ms, 1s, 500ms):"))
        entry = QLineEdit("300ms")
        lay.addWidget(entry)
        btns = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        btns.accepted.connect(dlg.accept)
        btns.rejected.connect(dlg.reject)
        lay.addWidget(btns)
        if dlg.exec() == QDialog.Accepted and entry.text().strip():
            self._append_line(f"wait: {entry.text().strip()}")

    # ── Load / Clear ──────────────────────────────────────────────────────────

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
        self._validate_syntax(silent=True)

    def clear_form(self) -> None:
        """Reset builder to blank state."""
        self._editing_macro_id = None
        self._name_input.setText("New Custom Macro")
        self._hotkey_input.clear()
        self._target_input.clear()
        self._desc_input.clear()
        self._script_edit.setPlainText(_DEFAULT_TEMPLATE)
        self._validate_syntax(silent=True)

    # ── Save ──────────────────────────────────────────────────────────────────

    def _on_save_macro(self) -> None:
        name = self._name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "Missing Name", "Please enter a name for the macro.")
            return

        content = self._script_edit.toPlainText().strip()
        try:
            actions, meta = parse_sequence_with_metadata(content)
        except Exception as exc:
            QMessageBox.critical(self, "Syntax Error",
                                 f"Cannot save macro with syntax errors:\n\n{exc}")
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

        hotkey_hint = f"\n• Global hotkey: {hotkey}" if hotkey else ""
        QMessageBox.information(
            self,
            "Macro Saved",
            f"Macro '<b>{macro.name}</b>' saved with {len(actions)} actions!\n\n"
            f"• Available immediately in your Macro Library\n"
            f"• Double-click it in the library to run it"
            f"{hotkey_hint}",
        )
        self.macro_saved.emit(macro)
