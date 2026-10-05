"""
keymacro/gui/app.py
─────────────────────
KeyMacro main GUI — tkinter list-based interface.

Layout
──────
┌──────────────────────────────────────────────────────┐
│  Toolbar  [● Record] [■ Stop] [▶ Run] [⚙ Dry Run]    │
│           [✎ Edit]  [🗑 Delete]  [+ Import]            │
├─────────────────────┬────────────────────────────────┤
│  Macro List         │  Action Detail Panel            │
│  (Treeview)         │  (scrolled list + metadata)     │
│                     │                                 │
├─────────────────────┴────────────────────────────────┤
│  Status Bar                                           │
└──────────────────────────────────────────────────────┘

Threading model
───────────────
Recording and replay run in daemon threads (Recorder / ReplayEngine).
The GUI uses ``root.after()`` to poll for state changes without blocking
the main Tk event loop.

All module interactions go through the four service objects passed in
from main.py: MacroStore, Recorder, ReplayEngine, SafetyLayer, HotkeyListener.
"""

from __future__ import annotations

import threading
import tkinter as tk
from tkinter import messagebox, simpledialog, ttk
from typing import TYPE_CHECKING

from keymacro.models.action import Macro, RiskLevel
from keymacro.safety.safety_layer import BlockedPathError

if TYPE_CHECKING:
    from keymacro.engine.replay import ReplayEngine
    from keymacro.hotkey.listener import HotkeyListener
    from keymacro.recorder.recorder import Recorder
    from keymacro.safety.safety_layer import SafetyLayer
    from keymacro.storage.macro_store import MacroStore


# ──────────────────────────────────────────────
# Colour palette (dark theme)
# ──────────────────────────────────────────────

_C = {
    "bg":           "#1e1e1e",
    "panel":        "#252526",
    "border":       "#3c3c3c",
    "accent":       "#0078d4",
    "accent_hover": "#1084d8",
    "danger":       "#c0392b",
    "success":      "#27ae60",
    "warning":      "#e67e22",
    "text":         "#d4d4d4",
    "text_dim":     "#888888",
    "text_bright":  "#ffffff",
    "risk_low":     "#27ae60",
    "risk_medium":  "#e67e22",
    "risk_high":    "#c0392b",
    "rec_active":   "#e74c3c",
    "row_sel":      "#094771",
    "row_alt":      "#2a2a2a",
}

_FONT_UI   = ("Segoe UI", 10)
_FONT_BOLD = ("Segoe UI", 10, "bold")
_FONT_MONO = ("Consolas", 9)
_FONT_H1   = ("Segoe UI", 14, "bold")


# ──────────────────────────────────────────────
# App States
# ──────────────────────────────────────────────

class _State:
    IDLE      = "idle"
    RECORDING = "recording"
    REPLAYING = "replaying"


# ──────────────────────────────────────────────
# KeyMacroApp
# ──────────────────────────────────────────────

class KeyMacroApp(tk.Tk):
    """Main application window for KeyMacro."""

    # Polling interval (ms) for background thread state updates
    _POLL_MS = 150

    def __init__(
        self,
        store: "MacroStore",
        recorder: "Recorder",
        engine: "ReplayEngine",
        safety: "SafetyLayer",
        hotkey_listener: "HotkeyListener",
        plugin_manager: "PluginManager | None" = None,
        app_scanner: "AppScanner | None" = None,
    ) -> None:
        super().__init__()

        self._store   = store
        self._recorder = recorder
        self._engine  = engine
        self._safety  = safety
        self._hotkeys = hotkey_listener

        if plugin_manager is None:
            from keymacro.plugins.manager import PluginManager
            plugin_manager = PluginManager.get_instance()
        self._plugin_mgr = plugin_manager

        if app_scanner is None:
            from keymacro.launcher.app_scanner import AppScanner
            app_scanner = AppScanner()
        self._scanner = app_scanner

        # runtime state
        self._state    = _State.IDLE
        self._macros:  list[Macro] = []
        self._selected: Macro | None = None

        # wire safety layer to use this window for dialogs
        self._safety._root = self

        self._build_window()
        self._apply_styles()
        self._build_toolbar()
        self._build_main_pane()
        self._build_statusbar()

        self._refresh_macro_list()
        self._poll_state()       # start background polling

    # ──────────────────────────────────────────
    # Window setup
    # ──────────────────────────────────────────

    def _build_window(self) -> None:
        self.title("KeyMacro")
        self.configure(bg=_C["bg"])
        self.minsize(860, 520)
        self.geometry("1040x620")
        # Centre on screen
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        x = (sw - 1040) // 2
        y = (sh - 620) // 2
        self.geometry(f"1040x620+{x}+{y}")
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    def _apply_styles(self) -> None:
        style = ttk.Style(self)
        style.theme_use("clam")

        # Treeview
        style.configure(
            "Macro.Treeview",
            background=_C["panel"],
            foreground=_C["text"],
            fieldbackground=_C["panel"],
            bordercolor=_C["border"],
            rowheight=26,
            font=_FONT_UI,
        )
        style.configure(
            "Macro.Treeview.Heading",
            background=_C["border"],
            foreground=_C["text_bright"],
            font=_FONT_BOLD,
            relief="flat",
        )
        style.map(
            "Macro.Treeview",
            background=[("selected", _C["row_sel"])],
            foreground=[("selected", _C["text_bright"])],
        )

        # Scrollbar
        style.configure(
            "Dark.Vertical.TScrollbar",
            troughcolor=_C["panel"],
            background=_C["border"],
            bordercolor=_C["panel"],
            arrowcolor=_C["text_dim"],
        )

        # Separator
        style.configure("TSeparator", background=_C["border"])

    # ──────────────────────────────────────────
    # Toolbar
    # ──────────────────────────────────────────

    def _build_toolbar(self) -> None:
        bar = tk.Frame(self, bg=_C["panel"], pady=6)
        bar.pack(fill="x", side="top")

        # App title
        tk.Label(
            bar, text="⌨  KeyMacro",
            bg=_C["panel"], fg=_C["text_bright"],
            font=_FONT_H1, padx=16,
        ).pack(side="left")

        sep = tk.Frame(bar, bg=_C["border"], width=1)
        sep.pack(side="left", fill="y", pady=4)

        # Buttons
        self._btn_new     = self._tb_btn(bar, "➕  New Macro", self._cmd_new_sequence_macro, _C["accent"])
        self._btn_record  = self._tb_btn(bar, "●  Record",  self._cmd_record,  _C["rec_active"])
        self._btn_stop    = self._tb_btn(bar, "■  Stop",    self._cmd_stop,    _C["border"])
        self._btn_run     = self._tb_btn(bar, "▶  Run",     self._cmd_run,     _C["success"])
        self._btn_dryrun  = self._tb_btn(bar, "⚙  Dry Run", self._cmd_dry_run, _C["border"])
        self._btn_edit    = self._tb_btn(bar, "✎  Edit",    self._cmd_edit_sequence, _C["border"])
        self._btn_clean   = self._tb_btn(bar, "🧹  Strip Delays", self._cmd_strip_delays, _C["border"])
        self._btn_delete  = self._tb_btn(bar, "🗑  Delete",  self._cmd_delete,  _C["border"])
        self._btn_launch  = self._tb_btn(bar, "🔌  App Plugins & Hub", self._cmd_open_launcher, _C["panel"])

        # Mouse-path toggle (right-aligned)
        self._mouse_path_var = tk.BooleanVar(value=True)
        chk = tk.Checkbutton(
            bar,
            text="Record Mouse Path",
            variable=self._mouse_path_var,
            bg=_C["panel"], fg=_C["text_dim"],
            selectcolor=_C["panel"],
            activebackground=_C["panel"],
            font=("Segoe UI", 9),
        )
        chk.pack(side="right", padx=16)

        self._update_toolbar_state()

    def _tb_btn(
        self, parent: tk.Frame, label: str, cmd, bg: str
    ) -> tk.Button:
        btn = tk.Button(
            parent, text=label, command=cmd,
            bg=bg, fg=_C["text_bright"],
            font=_FONT_UI, relief="flat",
            padx=12, pady=5, cursor="hand2",
            activebackground=_C["accent_hover"],
            activeforeground=_C["text_bright"],
        )
        btn.pack(side="left", padx=3)
        return btn

    # ──────────────────────────────────────────
    # Main pane (macro list + detail)
    # ──────────────────────────────────────────

    def _build_main_pane(self) -> None:
        pane = tk.PanedWindow(
            self, orient="horizontal",
            bg=_C["bg"], sashwidth=4, sashrelief="flat",
        )
        pane.pack(fill="both", expand=True, padx=0, pady=0)

        # ── Left: macro list ──────────────────
        left = tk.Frame(pane, bg=_C["panel"])
        pane.add(left, minsize=280, width=340)

        tk.Label(
            left, text="Saved Macros",
            bg=_C["panel"], fg=_C["text_dim"],
            font=("Segoe UI", 9, "bold"),
            anchor="w", padx=12, pady=6,
        ).pack(fill="x")

        cols = ("name", "hotkey", "target_app", "steps", "risk")
        self._tree = ttk.Treeview(
            left, columns=cols, show="headings",
            style="Macro.Treeview", selectmode="browse",
        )
        self._tree.heading("name",       text="Name",       anchor="w")
        self._tree.heading("hotkey",     text="Hotkey",     anchor="w")
        self._tree.heading("target_app", text="Target App", anchor="w")
        self._tree.heading("steps",      text="Steps",      anchor="center")
        self._tree.heading("risk",       text="Risk",       anchor="center")
        self._tree.column("name",       width=120, anchor="w")
        self._tree.column("hotkey",     width=80,  anchor="w")
        self._tree.column("target_app", width=80,  anchor="w")
        self._tree.column("steps",      width=40,  anchor="center")
        self._tree.column("risk",       width=60,  anchor="center")

        vsb = ttk.Scrollbar(left, orient="vertical", command=self._tree.yview,
                            style="Dark.Vertical.TScrollbar")
        self._tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._tree.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))
        self._tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree.bind("<Double-1>", lambda _e: self._cmd_run())

        # ── Right: detail panel ───────────────
        right = tk.Frame(pane, bg=_C["bg"])
        pane.add(right, minsize=400)

        # Macro metadata header
        self._detail_header = tk.Frame(right, bg=_C["panel"], pady=10)
        self._detail_header.pack(fill="x", padx=0)

        self._lbl_name = tk.Label(
            self._detail_header, text="Select a macro",
            bg=_C["panel"], fg=_C["text_bright"],
            font=_FONT_H1, anchor="w", padx=16,
        )
        self._lbl_name.pack(fill="x")

        meta_row = tk.Frame(self._detail_header, bg=_C["panel"])
        meta_row.pack(fill="x", padx=16, pady=(4, 0))

        self._lbl_hotkey     = self._meta_label(meta_row, "Hotkey: —")
        self._lbl_target_app = self._meta_label(meta_row, "Target App: —")
        self._lbl_risk       = self._meta_label(meta_row, "Risk: —")
        self._lbl_desc       = self._meta_label(meta_row, "")

        # Divider
        tk.Frame(right, bg=_C["border"], height=1).pack(fill="x")

        # Action list heading
        tk.Label(
            right, text="Actions",
            bg=_C["bg"], fg=_C["text_dim"],
            font=("Segoe UI", 9, "bold"),
            anchor="w", padx=16, pady=6,
        ).pack(fill="x")

        # Action Treeview
        a_cols = ("idx", "type", "description", "risk")
        self._action_tree = ttk.Treeview(
            right, columns=a_cols, show="headings",
            style="Macro.Treeview", selectmode="browse",
        )
        self._action_tree.heading("idx",         text="#",           anchor="center")
        self._action_tree.heading("type",        text="Type",        anchor="w")
        self._action_tree.heading("description", text="Description", anchor="w")
        self._action_tree.heading("risk",        text="Risk",        anchor="center")
        self._action_tree.column("idx",         width=36,  anchor="center")
        self._action_tree.column("type",        width=120, anchor="w")
        self._action_tree.column("description", width=340, anchor="w")
        self._action_tree.column("risk",        width=70,  anchor="center")

        avsb = ttk.Scrollbar(right, orient="vertical",
                             command=self._action_tree.yview,
                             style="Dark.Vertical.TScrollbar")
        self._action_tree.configure(yscrollcommand=avsb.set)
        avsb.pack(side="right", fill="y", padx=(0, 8), pady=(0, 8))
        self._action_tree.pack(fill="both", expand=True, padx=(16, 0), pady=(0, 8))

        # Tag colours for risk levels in action tree
        self._action_tree.tag_configure("high",   foreground=_C["risk_high"])
        self._action_tree.tag_configure("medium", foreground=_C["risk_medium"])
        self._action_tree.tag_configure("low",    foreground=_C["risk_low"])

    def _meta_label(self, parent: tk.Frame, text: str) -> tk.Label:
        lbl = tk.Label(
            parent, text=text,
            bg=_C["panel"], fg=_C["text_dim"],
            font=("Segoe UI", 9), padx=0, pady=0, anchor="w",
        )
        lbl.pack(side="left", padx=(0, 16))
        return lbl

    # ──────────────────────────────────────────
    # Status bar
    # ──────────────────────────────────────────

    def _build_statusbar(self) -> None:
        bar = tk.Frame(self, bg=_C["border"], height=28)
        bar.pack(fill="x", side="bottom")
        bar.pack_propagate(False)

        self._lbl_status = tk.Label(
            bar, text="Idle",
            bg=_C["border"], fg=_C["text_dim"],
            font=("Segoe UI", 9), anchor="w", padx=12,
        )
        self._lbl_status.pack(side="left", fill="y")

        self._lbl_active_app = tk.Label(
            bar, text="Active App: System Focus",
            bg=_C["border"], fg=_C["text_dim"],
            font=("Segoe UI", 9, "italic"), anchor="w", padx=16,
        )
        self._lbl_active_app.pack(side="left", fill="y")

        self._lbl_store = tk.Label(
            bar, text=f"Storage: {self._store.macros_dir}",
            bg=_C["border"], fg=_C["text_dim"],
            font=("Segoe UI", 9), anchor="e", padx=12,
        )
        self._lbl_store.pack(side="right", fill="y")

    # ──────────────────────────────────────────
    # Toolbar commands
    # ──────────────────────────────────────────

    def _cmd_record(self) -> None:
        if self._state != _State.IDLE:
            return
        name = simpledialog.askstring(
            "New Recording",
            "Name for this macro:",
            initialvalue="My Macro",
            parent=self,
        )
        if not name:
            return
        self._recorder._name            = name
        self._recorder._record_path     = self._mouse_path_var.get()
        self._recorder._mouse_only       = True
        self._recorder.start()
        self._set_state(_State.RECORDING)

    def _cmd_stop(self) -> None:
        if self._state == _State.RECORDING:
            macro = self._recorder.stop()
            if macro.action_count == 0:
                messagebox.showinfo("Empty Recording",
                                    "No actions were captured.", parent=self)
            else:
                self._store.save(macro)
                self._refresh_macro_list()
                self._select_macro_by_id(macro.macro_id)
                messagebox.showinfo(
                    "Recording Saved",
                    f"Macro '{macro.name}' saved with "
                    f"{macro.action_count} action(s).",
                    parent=self,
                )
            self._set_state(_State.IDLE)

        elif self._state == _State.REPLAYING:
            self._engine.stop()
            self._set_state(_State.IDLE)

    def _cmd_run(self) -> None:
        self._run_selected_macro()

    def _run_selected_macro(self) -> None:
        """Core replay launcher — safe to call from hotkey callbacks."""
        macro = self._selected
        if macro is None or self._state != _State.IDLE:
            return
        try:
            allowed = self._safety.run_allowed(macro, dry_run=False)
        except BlockedPathError as exc:
            messagebox.showerror(
                "Blocked Path",
                f"This macro targets a protected system path and cannot run:\n\n{exc}",
                parent=self,
            )
            return
        if not allowed:
            return

        self._set_state(_State.REPLAYING)
        self._engine.replay(
            macro,
            dry_run=False,
            on_done=lambda: self.after(0, self._set_state, _State.IDLE),
            on_error=lambda e: self.after(0, self._on_replay_error, e),
        )

    def _cmd_dry_run(self) -> None:
        macro = self._selected
        if macro is None or self._state != _State.IDLE:
            return
        # Show a progress window while dry-run output is printed to console
        self._set_state(_State.REPLAYING)

        # Capture dry-run output into a string for display
        import io, contextlib
        buf = io.StringIO()

        def _do_dry_run() -> None:
            with contextlib.redirect_stdout(buf):
                import threading as _t
                done = _t.Event()
                self._engine.replay(
                    macro, dry_run=True,
                    on_done=done.set,
                    on_error=lambda _: done.set(),
                )
                done.wait(timeout=30)
            self.after(0, _show_output)

        def _show_output() -> None:
            self._set_state(_State.IDLE)
            output = buf.getvalue()
            self._show_dry_run_window(macro.name, output)

        threading.Thread(target=_do_dry_run, daemon=True).start()

    def _cmd_new_sequence_macro(self, initial_sequence: str = "") -> None:
        if self._state != _State.IDLE:
            return
        from keymacro.gui.sequence_dialog import SequenceEditorDialog
        dlg = SequenceEditorDialog(
            self,
            macro=None,
            initial_sequence=initial_sequence,
            plugin_manager=self._plugin_mgr,
            app_scanner=self._scanner,
        )
        self.wait_window(dlg)
        if dlg.result_macro:
            self._store.save(dlg.result_macro)
            # Reload list AND immediately re-register all hotkeys so the new
            # macro's hotkey fires without needing a restart.
            self._refresh_macro_list()   # calls _refresh_hotkeys() internally
            self._select_macro_by_id(dlg.result_macro.macro_id)
            hotkey_hint = (f" or press '{dlg.result_macro.hotkey}' anywhere on your keyboard"
                          if dlg.result_macro.hotkey else "")
            messagebox.showinfo(
                "Macro Saved",
                f"Macro '{dlg.result_macro.name}' saved with {dlg.result_macro.action_count} action(s)!\n\n"
                f"How to use it:\n"
                f"• It is now selected in the 'Saved Macros' list on the left.\n"
                f"• Click '▶ Run' on the toolbar to execute it.\n"
                f"• Double-click it in the list.\n"
                f"• Or use its global hotkey{hotkey_hint}.",
                parent=self,
            )

    def _cmd_edit_sequence(self) -> None:
        macro = self._selected
        if macro is None or self._state != _State.IDLE:
            return
        from keymacro.gui.sequence_dialog import SequenceEditorDialog
        dlg = SequenceEditorDialog(
            self,
            macro=macro,
            plugin_manager=self._plugin_mgr,
            app_scanner=self._scanner,
        )
        self.wait_window(dlg)
        if dlg.result_macro:
            self._store.save(dlg.result_macro)
            # Re-register hotkeys immediately so the edited hotkey takes effect
            self._refresh_macro_list()   # calls _refresh_hotkeys() internally
            self._select_macro_by_id(dlg.result_macro.macro_id)
            self._show_detail(dlg.result_macro)

    def _cmd_strip_delays(self) -> None:
        macro = self._selected
        if macro is None or self._state != _State.IDLE:
            return
        from keymacro.models.sequence import strip_delays
        old_count = macro.action_count
        macro.actions = strip_delays(macro.actions)
        diff = old_count - macro.action_count
        self._store.save(macro)
        self._refresh_macro_list()
        self._select_macro_by_id(macro.macro_id)
        self._show_detail(macro)
        messagebox.showinfo(
            "Delays Removed",
            f"Removed {diff} delay action(s) from '{macro.name}'. Macro will now run with instant execution.",
            parent=self,
        )

    def _cmd_open_launcher(self) -> None:
        from keymacro.gui.launcher_dialog import AppLauncherDialog

        def _on_create_macro_with_app(app):
            initial_seq = (
                f"# Macro for {app.name}\n"
                f'launch: "{app.target}"\n'
                f"wait: 500ms\n"
            )
            self.after(100, lambda: self._cmd_new_sequence_macro(initial_sequence=initial_seq))

        dlg = AppLauncherDialog(
            self,
            scanner=self._scanner,
            plugin_manager=self._plugin_mgr,
            on_create_macro_with_app=_on_create_macro_with_app,
        )

    def _cmd_edit(self) -> None:
        self._cmd_edit_sequence()

    def _cmd_delete(self) -> None:
        macro = self._selected
        if macro is None:
            return
        if not messagebox.askyesno(
            "Delete Macro",
            f"Delete macro '{macro.name}'? This cannot be undone.",
            parent=self,
        ):
            return
        # Remove hotkey binding first
        if macro.hotkey:
            self._hotkeys.unregister(macro.hotkey)
        self._store.delete(macro.macro_id)
        self._selected = None
        self._refresh_macro_list()
        self._clear_detail()

    # ──────────────────────────────────────────
    # List management
    # ──────────────────────────────────────────

    def _refresh_macro_list(self) -> None:
        self._macros = self._store.list_all()
        self._tree.delete(*self._tree.get_children())
        for macro in self._macros:
            risk_color = {
                RiskLevel.LOW:    _C["risk_low"],
                RiskLevel.MEDIUM: _C["risk_medium"],
                RiskLevel.HIGH:   _C["risk_high"],
            }[macro.risk_level]
            iid = self._tree.insert(
                "", "end",
                iid=macro.macro_id,
                values=(
                    macro.name,
                    macro.hotkey or "—",
                    macro.target_app or "Global",
                    macro.action_count,
                    macro.risk_level.value.upper(),
                ),
                tags=(macro.risk_level.value,),
            )
        self._tree.tag_configure("low",    foreground=_C["risk_low"])
        self._tree.tag_configure("medium", foreground=_C["risk_medium"])
        self._tree.tag_configure("high",   foreground=_C["risk_high"])
        self._refresh_hotkeys()

    def _refresh_hotkeys(self) -> None:
        """Re-register all macro hotkeys with the listener."""
        self._hotkeys.clear()
        for macro in self._macros:
            if macro.hotkey:
                # capture macro reference in closure
                def _make_cb(m: Macro) -> callable:
                    def _cb() -> None:
                        # Schedule trigger on GUI thread
                        self.after(0, self._hotkey_triggered, m)
                    return _cb
                try:
                    self._hotkeys.register(
                        macro.hotkey,
                        _make_cb(macro),
                        target_app=macro.target_app,
                        macro_id=macro.macro_id,
                    )
                    print(f"[Hotkeys] Registered '{macro.hotkey}' → '{macro.name}'")
                except Exception as exc:  # noqa: BLE001
                    print(f"[GUI] Could not register hotkey {macro.hotkey!r}: {exc}")

    def _hotkey_triggered(self, macro: Macro) -> None:
        """Called on the main thread when a global hotkey fires.

        A 250 ms delay is inserted before replay so the trigger keys are
        physically released before pyautogui starts sending input — otherwise
        the hotkey combo itself gets injected as the first input of the macro.
        """
        if self._state != _State.IDLE:
            return
        self._selected = macro
        self._show_detail(macro)
        self._update_toolbar_state()
        # Give OS time to process the key-release events
        self.after(250, self._run_selected_macro)

    def _select_macro_by_id(self, macro_id: str) -> None:
        if self._tree.exists(macro_id):
            self._tree.selection_set(macro_id)
            self._tree.see(macro_id)
            # Manually trigger select handler
            self._on_tree_select(None)

    # ──────────────────────────────────────────
    # Detail panel
    # ──────────────────────────────────────────

    def _on_tree_select(self, _event) -> None:  # noqa: ANN001
        sel = self._tree.selection()
        if not sel:
            return
        macro_id = sel[0]
        macro = next((m for m in self._macros if m.macro_id == macro_id), None)
        if macro:
            self._selected = macro
            self._show_detail(macro)
            self._update_toolbar_state()

    def _show_detail(self, macro: Macro) -> None:
        self._lbl_name.config(text=macro.name)
        self._lbl_hotkey.config(text=f"Hotkey: {macro.hotkey or '—'}")
        self._lbl_target_app.config(text=f"Target App: {macro.target_app or 'Global'}")

        risk_colors = {
            RiskLevel.LOW:    _C["risk_low"],
            RiskLevel.MEDIUM: _C["risk_medium"],
            RiskLevel.HIGH:   _C["risk_high"],
        }
        self._lbl_risk.config(
            text=f"Risk: {macro.risk_level.value.upper()}",
            fg=risk_colors[macro.risk_level],
        )
        self._lbl_desc.config(
            text=macro.description if macro.description else "",
            fg=_C["text_dim"],
        )

        # Populate action tree
        self._action_tree.delete(*self._action_tree.get_children())
        for i, action in enumerate(macro.actions, 1):
            tag = action.risk_level.value
            self._action_tree.insert(
                "", "end",
                values=(
                    i,
                    action.action_type.value.replace("_", " ").title(),
                    action.description,
                    action.risk_level.value.upper(),
                ),
                tags=(tag,),
            )

    def _clear_detail(self) -> None:
        self._lbl_name.config(text="Select a macro")
        self._lbl_hotkey.config(text="Hotkey: —")
        self._lbl_target_app.config(text="Target App: —")
        self._lbl_risk.config(text="Risk: —", fg=_C["text_dim"])
        self._lbl_desc.config(text="")
        self._action_tree.delete(*self._action_tree.get_children())

    # ──────────────────────────────────────────
    # State machine
    # ──────────────────────────────────────────

    def _set_state(self, new_state: str) -> None:
        self._state = new_state
        self._update_toolbar_state()
        status_map = {
            _State.IDLE:      ("Idle",       _C["text_dim"]),
            _State.RECORDING: ("● Recording — press Stop when done",
                               _C["rec_active"]),
            _State.REPLAYING: ("▶ Replaying…", _C["accent"]),
        }
        text, color = status_map[new_state]
        self._lbl_status.config(text=text, fg=color)

    def _update_toolbar_state(self) -> None:
        idle      = self._state == _State.IDLE
        recording = self._state == _State.RECORDING
        replaying = self._state == _State.REPLAYING
        has_sel   = self._selected is not None

        def _state_btn(btn: tk.Button, enabled: bool) -> None:
            btn.config(state="normal" if enabled else "disabled",
                       cursor="hand2" if enabled else "arrow")

        _state_btn(self._btn_new,    idle)
        _state_btn(self._btn_record, idle)
        _state_btn(self._btn_stop,   recording or replaying)
        _state_btn(self._btn_run,    idle and has_sel)
        _state_btn(self._btn_dryrun, idle and has_sel)
        _state_btn(self._btn_edit,   idle and has_sel)
        _state_btn(self._btn_clean,  idle and has_sel)
        _state_btn(self._btn_delete, idle and has_sel)
        _state_btn(self._btn_launch, idle)

    # ──────────────────────────────────────────
    # Background polling
    # ──────────────────────────────────────────

    def _poll_state(self) -> None:
        """Periodically sync GUI state with background thread state and active window context."""
        if self._state == _State.REPLAYING and not self._engine.is_running:
            self._set_state(_State.IDLE)

        # Update active app context indicator
        from keymacro.hotkey.context import get_active_window_info
        exe_name, _ = get_active_window_info()
        if exe_name:
            self._lbl_active_app.config(text=f"🎯 Active App: {exe_name}", fg=_C["text_bright"])
        else:
            self._lbl_active_app.config(text="Active App: Global Focus", fg=_C["text_dim"])

        self.after(self._POLL_MS, self._poll_state)

    # ──────────────────────────────────────────
    # Error handling
    # ──────────────────────────────────────────

    def _on_replay_error(self, exc: Exception) -> None:
        self._set_state(_State.IDLE)
        messagebox.showerror(
            "Replay Error",
            f"An error occurred during replay:\n\n{type(exc).__name__}: {exc}",
            parent=self,
        )

    # ──────────────────────────────────────────
    # Dry-run output window
    # ──────────────────────────────────────────

    def _show_dry_run_window(self, macro_name: str, output: str) -> None:
        from tkinter import scrolledtext as st
        win = tk.Toplevel(self)
        win.title(f"Dry Run — {macro_name}")
        win.configure(bg=_C["bg"])
        win.geometry("640x420")
        win.grab_set()

        tk.Label(
            win, text=f"Dry Run: {macro_name}",
            bg=_C["bg"], fg=_C["text_bright"],
            font=_FONT_H1, anchor="w", padx=16, pady=10,
        ).pack(fill="x")

        txt = st.ScrolledText(
            win,
            bg=_C["panel"], fg=_C["text"],
            font=_FONT_MONO, wrap="word",
        )
        txt.insert("1.0", output or "(no output)")
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True, padx=16, pady=(0, 8))

        tk.Button(
            win, text="Close", command=win.destroy,
            bg=_C["accent"], fg="white",
            font=_FONT_BOLD, relief="flat", padx=16, pady=6,
        ).pack(pady=(0, 12))

    # ──────────────────────────────────────────
    # Close
    # ──────────────────────────────────────────

    def _on_close(self) -> None:
        if self._state == _State.RECORDING:
            self._recorder.stop()
        if self._state == _State.REPLAYING:
            self._engine.stop()
        self._hotkeys.stop()
        self.destroy()


# ──────────────────────────────────────────────
# Edit Dialog
# ──────────────────────────────────────────────

class _EditDialog(tk.Toplevel):
    """Modal dialog for editing a macro's name, hotkey, and description."""

    def __init__(self, parent: tk.Tk, macro: Macro) -> None:
        super().__init__(parent)
        self.title("Edit Macro")
        self.configure(bg=_C["bg"])
        self.resizable(False, False)
        self.grab_set()
        self.result: dict | None = None

        self._build(macro)

        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width() // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px - w // 2}+{py - h // 2}")

    def _build(self, macro: Macro) -> None:
        pad = {"padx": 20, "pady": 6}

        tk.Label(
            self, text="Edit Macro",
            bg=_C["bg"], fg=_C["text_bright"],
            font=_FONT_H1,
        ).pack(**pad, anchor="w")

        tk.Frame(self, bg=_C["border"], height=1).pack(fill="x")

        # Name
        tk.Label(self, text="Name:", bg=_C["bg"], fg=_C["text"], font=_FONT_UI).pack(**pad, anchor="w")
        self._name_var = tk.StringVar(value=macro.name)
        tk.Entry(self, textvariable=self._name_var, width=42,
                 bg=_C["panel"], fg=_C["text_bright"], insertbackground=_C["text"],
                 font=_FONT_UI, relief="flat", bd=4).pack(**pad)

        # Hotkey
        tk.Label(self, text="Hotkey (pynput format, e.g. <ctrl>+<shift>+f5):",
                 bg=_C["bg"], fg=_C["text"], font=_FONT_UI).pack(**pad, anchor="w")
        self._hotkey_var = tk.StringVar(value=macro.hotkey)
        tk.Entry(self, textvariable=self._hotkey_var, width=42,
                 bg=_C["panel"], fg=_C["text_bright"], insertbackground=_C["text"],
                 font=_FONT_MONO, relief="flat", bd=4).pack(**pad)

        # Target App
        tk.Label(self, text="Target App (e.g. chrome.exe, spotify, notepad, or blank for Global):",
                 bg=_C["bg"], fg=_C["text"], font=_FONT_UI).pack(**pad, anchor="w")
        self._target_app_var = tk.StringVar(value=macro.target_app)
        tk.Entry(self, textvariable=self._target_app_var, width=42,
                 bg=_C["panel"], fg=_C["text_bright"], insertbackground=_C["text"],
                 font=_FONT_MONO, relief="flat", bd=4).pack(**pad)

        # Description
        tk.Label(self, text="Description (optional):",
                 bg=_C["bg"], fg=_C["text"], font=_FONT_UI).pack(**pad, anchor="w")
        self._desc_var = tk.StringVar(value=macro.description)
        tk.Entry(self, textvariable=self._desc_var, width=42,
                 bg=_C["panel"], fg=_C["text_bright"], insertbackground=_C["text"],
                 font=_FONT_UI, relief="flat", bd=4).pack(**pad)

        # Buttons
        tk.Frame(self, bg=_C["border"], height=1).pack(fill="x", pady=(12, 0))
        btn_row = tk.Frame(self, bg=_C["bg"])
        btn_row.pack(fill="x", padx=20, pady=10)

        tk.Button(
            btn_row, text="Cancel", command=self.destroy,
            bg=_C["border"], fg=_C["text"],
            font=_FONT_UI, relief="flat", padx=14, pady=5,
        ).pack(side="right", padx=(4, 0))

        tk.Button(
            btn_row, text="Save", command=self._save,
            bg=_C["accent"], fg="white",
            font=_FONT_BOLD, relief="flat", padx=14, pady=5,
        ).pack(side="right")

    def _save(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing Name", "Macro name cannot be empty.", parent=self)
            return
        self.result = {
            "name":        name,
            "hotkey":      self._hotkey_var.get().strip(),
            "target_app":  self._target_app_var.get().strip(),
            "description": self._desc_var.get().strip(),
        }
        self.destroy()
