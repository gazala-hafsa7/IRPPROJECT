"""
keymacro/gui/sequence_dialog.py
───────────────────────────────
Modal editor for creating and editing macros via the concise sequence syntax.
Includes real-time syntax validation, live action preview, and quick-insert helpers.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from keymacro.models.action import Action, ActionType, Macro, RiskLevel
from keymacro.models.sequence import (
    SequenceParseError,
    normalize_delays,
    parse_sequence,
    parse_sequence_with_metadata,
    serialize_sequence,
    strip_delays,
)

if TYPE_CHECKING:
    from keymacro.launcher.app_scanner import AppScanner
    from keymacro.plugins.manager import PluginManager


# Theme colors matching KeyMacroApp
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
    "row_sel":      "#094771",
}

_FONT_UI   = ("Segoe UI", 10)
_FONT_BOLD = ("Segoe UI", 10, "bold")
_FONT_MONO = ("Consolas", 10)
_FONT_H1   = ("Segoe UI", 13, "bold")


class SequenceEditorDialog(tk.Toplevel):
    """Modal dialog for writing and previewing concise macro sequences."""

    def __init__(
        self,
        parent: tk.Tk,
        macro: Macro | None = None,
        initial_sequence: str = "",
        plugin_manager: PluginManager | None = None,
        app_scanner: AppScanner | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("Macro Sequence Builder" if macro is None else f"Edit Sequence — {macro.name}")
        self.configure(bg=_C["bg"])
        self.minsize(860, 620)
        self.geometry("980x680")
        self.grab_set()

        self._parent = parent
        self._macro = macro
        self._plugin_mgr = plugin_manager
        self._scanner = app_scanner

        self.result_macro: Macro | None = None
        self._parsed_actions: list[Action] = []

        self._build_ui(initial_sequence)

        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width() // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"{w}x{h}+{px - w // 2}+{py - h // 2}")

        self.protocol("WM_DELETE_WINDOW", self._on_close)

        # Initial parse
        self._on_text_change()

    def _build_ui(self, initial_sequence: str) -> None:
        # ── Top: Macro Metadata Row ──────────────────────
        top_bar = tk.Frame(self, bg=_C["panel"], padx=16, pady=10)
        top_bar.pack(fill="x")

        # Title and Top Action Buttons
        title_row = tk.Frame(top_bar, bg=_C["panel"])
        title_row.pack(fill="x", pady=(0, 8))

        title_text = "➕ Create New Macro" if self._macro is None else f"✎ Edit Macro: {self._macro.name}"
        tk.Label(
            title_row, text=title_text, bg=_C["panel"], fg=_C["text_bright"], font=_FONT_H1
        ).pack(side="left")

        # Prominent top Save & Cancel buttons
        top_btn_bar = tk.Frame(title_row, bg=_C["panel"])
        top_btn_bar.pack(side="right")

        tk.Button(
            top_btn_bar, text="Cancel", command=self.destroy,
            bg=_C["border"], fg=_C["text"], font=_FONT_UI,
            relief="flat", padx=14, pady=4, cursor="hand2",
        ).pack(side="left", padx=4)

        tk.Button(
            top_btn_bar, text="💾 Save Macro (Ctrl+S)", command=self._cmd_save,
            bg=_C["accent"], fg="white", font=_FONT_BOLD,
            relief="flat", padx=16, pady=4, cursor="hand2",
            activebackground=_C["accent_hover"], activeforeground="white",
        ).pack(side="left", padx=4)

        # Bind Ctrl+S for instant saving
        self.bind("<Control-s>", lambda _: self._cmd_save())

        fields_row = tk.Frame(top_bar, bg=_C["panel"])
        fields_row.pack(fill="x")

        # Name
        tk.Label(fields_row, text="Name:", bg=_C["panel"], fg=_C["text"], font=_FONT_UI).pack(side="left")
        self._name_var = tk.StringVar(value=self._macro.name if self._macro else "My Macro")
        e_name = tk.Entry(
            fields_row, textvariable=self._name_var, width=24,
            bg=_C["bg"], fg=_C["text_bright"], font=_FONT_UI,
            relief="flat", bd=3, insertbackground=_C["text"],
        )
        e_name.pack(side="left", padx=(6, 16))
        e_name.bind("<Return>", lambda _: self._cmd_save())

        # Hotkey
        tk.Label(fields_row, text="Hotkey:", bg=_C["panel"], fg=_C["text"], font=_FONT_UI).pack(side="left")
        self._hotkey_var = tk.StringVar(value=self._macro.hotkey if self._macro else "")
        e_hk = tk.Entry(
            fields_row, textvariable=self._hotkey_var, width=16,
            bg=_C["bg"], fg=_C["text_bright"], font=_FONT_MONO,
            relief="flat", bd=3, insertbackground=_C["text"],
        )
        e_hk.pack(side="left", padx=(6, 12))
        e_hk.bind("<Return>", lambda _: self._cmd_save())

        # Target App
        tk.Label(fields_row, text="Target App:", bg=_C["panel"], fg=_C["text"], font=_FONT_UI).pack(side="left")
        self._target_app_var = tk.StringVar(value=self._macro.target_app if self._macro else "")
        e_app = tk.Entry(
            fields_row, textvariable=self._target_app_var, width=16,
            bg=_C["bg"], fg=_C["text_bright"], font=_FONT_MONO,
            relief="flat", bd=3, insertbackground=_C["text"],
        )
        e_app.pack(side="left", padx=(6, 12))
        e_app.bind("<Return>", lambda _: self._cmd_save())

        # Description
        tk.Label(fields_row, text="Description:", bg=_C["panel"], fg=_C["text"], font=_FONT_UI).pack(side="left")
        self._desc_var = tk.StringVar(value=self._macro.description if self._macro else "")
        tk.Entry(
            fields_row, textvariable=self._desc_var,
            bg=_C["bg"], fg=_C["text_bright"], font=_FONT_UI,
            relief="flat", bd=3, insertbackground=_C["text"],
        ).pack(side="left", fill="x", expand=True, padx=(6, 0))

        # ── Quick Insert Helper Toolbar ──────────────────
        helper_bar = tk.Frame(self, bg=_C["border"], padx=12, pady=4)
        helper_bar.pack(fill="x")

        tk.Label(
            helper_bar, text="Quick Insert:", bg=_C["border"], fg=_C["text_bright"], font=("Segoe UI", 9, "bold")
        ).pack(side="left", padx=(0, 6))

        self._helper_btn(helper_bar, "+ Shortcut", self._insert_combo)
        self._helper_btn(helper_bar, "+ Type Text", self._insert_text)
        self._helper_btn(helper_bar, "+ Click", self._insert_click)
        self._helper_btn(helper_bar, "+ Launch App", self._insert_launch)
        self._helper_btn(helper_bar, "+ Plugin Action", self._insert_plugin)
        self._helper_btn(helper_bar, "+ Wait", self._insert_wait)

        # Delays cleanup buttons (right-aligned)
        tk.Button(
            helper_bar, text="🧹 Strip Delays", command=self._cmd_strip_delays,
            bg=_C["panel"], fg=_C["warning"], font=("Segoe UI", 9),
            relief="flat", padx=8, pady=2, cursor="hand2",
        ).pack(side="right", padx=3)

        # ── Status and Error Banner (pinned to bottom) ──────────────────────
        self._status_bar = tk.Frame(self, bg=_C["panel"], padx=16, pady=8)
        self._status_bar.pack(side="bottom", fill="x")

        self._lbl_status = tk.Label(
            self._status_bar, text="Ready", bg=_C["panel"], fg=_C["success"], font=("Segoe UI", 9)
        )
        self._lbl_status.pack(side="left")

        # Bottom buttons
        btn_bar = tk.Frame(self._status_bar, bg=_C["panel"])
        btn_bar.pack(side="right")

        tk.Button(
            btn_bar, text="Cancel", command=self.destroy,
            bg=_C["border"], fg=_C["text"], font=_FONT_UI,
            relief="flat", padx=14, pady=5, cursor="hand2",
        ).pack(side="left", padx=4)

        tk.Button(
            btn_bar, text="💾 Save Macro", command=self._cmd_save,
            bg=_C["accent"], fg="white", font=_FONT_BOLD,
            relief="flat", padx=18, pady=5, cursor="hand2",
            activebackground=_C["accent_hover"], activeforeground="white",
        ).pack(side="left", padx=4)

        # ── Main Body: Paned (Left: Text Editor, Right: Live Action Preview) ──
        paned = tk.PanedWindow(self, orient="horizontal", bg=_C["bg"], sashwidth=4, sashrelief="flat")
        paned.pack(fill="both", expand=True, padx=8, pady=8)

        # Left pane: Editor
        left_frame = tk.Frame(paned, bg=_C["panel"])
        paned.add(left_frame, minsize=380, width=480)

        editor_hdr = tk.Frame(left_frame, bg=_C["panel"], pady=4, padx=8)
        editor_hdr.pack(fill="x")
        tk.Label(
            editor_hdr, text="Sequence Script (one action per line)",
            bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 9, "bold")
        ).pack(side="left")

        # Text widget
        from tkinter import scrolledtext
        self._txt_seq = scrolledtext.ScrolledText(
            left_frame, bg=_C["bg"], fg=_C["text_bright"],
            insertbackground="white", font=_FONT_MONO,
            relief="flat", bd=4, wrap="none", undo=True,
        )
        self._txt_seq.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        # Initial text content
        if initial_sequence:
            content = initial_sequence
        elif self._macro and self._macro.actions:
            content = serialize_sequence(self._macro.actions, target_app=self._macro.target_app, hotkey=self._macro.hotkey)
        else:
            content = (
                "# Enter your sequence of shortcuts and operations below:\n"
                "# Examples:\n"
                "#   # hotkey: ctrl+o+g\n"
                "#   # target_app: chrome.exe\n"
                "#   launch: notepad.exe\n"
                "#   wait: 300ms\n"
                "#   type: Hello, World!\n"
                "#   combo: ctrl+s\n"
                "#   press: enter\n"
                "#   plugin: browser.open_url url=https://google.com\n\n"
            )
        self._txt_seq.insert("1.0", content)
        self._txt_seq.bind("<<Modified>>", self._on_text_modified)

        # Right pane: Live Action Preview
        right_frame = tk.Frame(paned, bg=_C["panel"])
        paned.add(right_frame, minsize=320)

        preview_hdr = tk.Frame(right_frame, bg=_C["panel"], pady=4, padx=8)
        preview_hdr.pack(fill="x")
        self._lbl_preview_title = tk.Label(
            preview_hdr, text="Parsed Steps Preview (0 actions)",
            bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 9, "bold")
        )
        self._lbl_preview_title.pack(side="left")

        cols = ("idx", "type", "desc")
        self._preview_tree = ttk.Treeview(
            right_frame, columns=cols, show="headings",
            style="Macro.Treeview", selectmode="browse",
        )
        self._preview_tree.heading("idx",  text="#",    anchor="center")
        self._preview_tree.heading("type", text="Type", anchor="w")
        self._preview_tree.heading("desc", text="Step Summary", anchor="w")
        self._preview_tree.column("idx",  width=36,  anchor="center")
        self._preview_tree.column("type", width=110, anchor="w")
        self._preview_tree.column("desc", width=260, anchor="w")

        p_vsb = ttk.Scrollbar(right_frame, orient="vertical", command=self._preview_tree.yview,
                              style="Dark.Vertical.TScrollbar")
        self._preview_tree.configure(yscrollcommand=p_vsb.set)
        p_vsb.pack(side="right", fill="y", padx=(0, 6), pady=(0, 6))
        self._preview_tree.pack(fill="both", expand=True, padx=(6, 0), pady=(0, 6))

    def _helper_btn(self, parent: tk.Frame, label: str, cmd) -> tk.Button:
        btn = tk.Button(
            parent, text=label, command=cmd,
            bg=_C["panel"], fg=_C["text_bright"], font=("Segoe UI", 9),
            relief="flat", padx=8, pady=2, cursor="hand2",
            activebackground=_C["accent"], activeforeground="white",
        )
        btn.pack(side="left", padx=2)
        return btn

    # ── Text update & validation ─────────────────────────

    def _on_text_modified(self, _event=None) -> None:
        # Reset the modified flag so Tkinter continues sending events
        self._txt_seq.tk.call(self._txt_seq._w, "edit", "modified", 0)
        self._on_text_change()

    def _on_text_change(self) -> None:
        text = self._txt_seq.get("1.0", "end-1c")
        try:
            actions, meta = parse_sequence_with_metadata(text)
            self._parsed_actions = actions
            if meta.get("target_app") and not self._target_app_var.get().strip():
                self._target_app_var.set(meta["target_app"])
            if meta.get("hotkey") and not self._hotkey_var.get().strip():
                self._hotkey_var.set(meta["hotkey"])
            self._lbl_status.config(
                text=f"✓ Valid: {len(actions)} action(s) defined", fg=_C["success"]
            )
            self._lbl_preview_title.config(text=f"Parsed Steps Preview ({len(actions)} actions)")
            self._update_preview(actions)
        except SequenceParseError as err:
            self._lbl_status.config(
                text=f"⚠ Syntax Error on Line {err.line_num}: {err.message}", fg=_C["danger"]
            )
        except Exception as exc:
            self._lbl_status.config(text=f"⚠ Error: {exc}", fg=_C["danger"])

    def _update_preview(self, actions: list[Action]) -> None:
        self._preview_tree.delete(*self._preview_tree.get_children())
        for i, a in enumerate(actions, 1):
            type_str = a.action_type.value.replace("_", " ").title()
            self._preview_tree.insert("", "end", values=(i, type_str, a.description))

    def _append_line(self, line: str) -> None:
        curr = self._txt_seq.get("1.0", "end-1c")
        if curr and not curr.endswith("\n"):
            self._txt_seq.insert("end", "\n")
        self._txt_seq.insert("end", line + "\n")
        self._txt_seq.see("end")
        self._on_text_change()

    # ── Quick Insert Handlers ────────────────────────────

    def _insert_combo(self) -> None:
        from tkinter import simpledialog
        val = simpledialog.askstring(
            "Insert Shortcut / Combo",
            "Enter shortcut combination (e.g. ctrl+c, alt+f4, ctrl+shift+esc):",
            parent=self,
            initialvalue="ctrl+c",
        )
        if val:
            self._append_line(f"combo: {val.strip().lower()}")

    def _insert_text(self) -> None:
        from tkinter import simpledialog
        val = simpledialog.askstring(
            "Insert Text to Type",
            "Enter text string to type:",
            parent=self,
        )
        if val is not None:
            self._append_line(f'type: "{val}"')

    def _insert_click(self) -> None:
        from tkinter import simpledialog
        import pyautogui
        cx, cy = pyautogui.position()
        val = simpledialog.askstring(
            "Insert Mouse Click",
            f"Enter coordinates (default: current cursor position {cx}, {cy}):\nFormat: [button], x, y",
            parent=self,
            initialvalue=f"{cx}, {cy}",
        )
        if val:
            self._append_line(f"click: {val.strip()}")

    def _insert_launch(self) -> None:
        # If scanner is available, show quick dropdown selection
        if self._scanner:
            apps = self._scanner.scan()
            win = tk.Toplevel(self)
            win.title("Choose Installed App to Launch")
            win.configure(bg=_C["bg"])
            win.geometry("450x400")
            win.grab_set()

            tk.Label(
                win, text="Select application to launch:",
                bg=_C["bg"], fg=_C["text_bright"], font=_FONT_BOLD, padx=12, pady=8, anchor="w",
            ).pack(fill="x")

            listbox = tk.Listbox(
                win, bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
                selectbackground=_C["row_sel"], relief="flat", bd=4,
            )
            listbox.pack(fill="both", expand=True, padx=12, pady=6)
            for app in apps:
                listbox.insert("end", f"{app.name} ({app.category})")

            def _choose():
                sel = listbox.curselection()
                if sel:
                    app = apps[sel[0]]
                    self._append_line(f'launch: "{app.target}"')
                    win.destroy()

            tk.Button(
                win, text="Insert Launch Command", command=_choose,
                bg=_C["accent"], fg="white", font=_FONT_BOLD, relief="flat", padx=12, pady=4,
            ).pack(pady=8)
        else:
            from tkinter import simpledialog
            val = simpledialog.askstring(
                "Launch Application", "Enter program name or executable path (e.g. notepad, chrome.exe):", parent=self
            )
            if val:
                self._append_line(f"launch: {val.strip()}")

    def _insert_plugin(self) -> None:
        if not self._plugin_mgr:
            messagebox.showinfo("Plugins", "Plugin manager not available.", parent=self)
            return

        actions = self._plugin_mgr.get_all_actions()
        if not actions:
            messagebox.showinfo("Plugins", "No plugin actions registered.", parent=self)
            return

        win = tk.Toplevel(self)
        win.title("Insert Plugin Action")
        win.configure(bg=_C["bg"])
        win.geometry("640x520")
        win.grab_set()
        win.resizable(True, True)

        # ── Title ──────────────────────────────────────────────────
        tk.Label(
            win, text="Choose a Plugin Action:",
            bg=_C["bg"], fg=_C["text_bright"], font=_FONT_BOLD, padx=12, pady=8, anchor="w",
        ).pack(fill="x")

        tk.Frame(win, bg=_C["border"], height=1).pack(fill="x")

        # ── Horizontal split: list (left) + params (right) ─────────
        body = tk.PanedWindow(win, orient="horizontal", bg=_C["bg"], sashwidth=4, sashrelief="flat")
        body.pack(fill="both", expand=True, padx=8, pady=8)

        # Left: action list
        left = tk.Frame(body, bg=_C["panel"])
        body.add(left, minsize=240, width=280)

        tk.Label(
            left, text="Actions", bg=_C["panel"], fg=_C["text_dim"],
            font=("Segoe UI", 9, "bold"), anchor="w", padx=8, pady=4,
        ).pack(fill="x")

        listbox = tk.Listbox(
            left, bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            selectbackground=_C["row_sel"], relief="flat", bd=4,
        )
        listbox.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        for plugin, spec in actions:
            listbox.insert("end", f"[{plugin.name}] {spec.name}")

        # Right: description + dynamic parameter form
        right = tk.Frame(body, bg=_C["panel"])
        body.add(right, minsize=300)

        self._lbl_action_name = tk.Label(
            right, text="← Select an action",
            bg=_C["panel"], fg=_C["text_bright"], font=_FONT_BOLD, padx=12, pady=6, anchor="w",
        )
        self._lbl_action_name.pack(fill="x")

        self._lbl_action_desc = tk.Label(
            right, text="",
            bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 9),
            padx=12, pady=2, anchor="w", wraplength=320, justify="left",
        )
        self._lbl_action_desc.pack(fill="x")

        tk.Label(
            right, text="Example syntax:",
            bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 9, "italic"),
            padx=12, anchor="w",
        ).pack(fill="x", pady=(4, 0))

        self._lbl_example = tk.Label(
            right, text="",
            bg=_C["bg"], fg=_C["accent"], font=_FONT_MONO,
            padx=12, pady=4, anchor="w", wraplength=320, justify="left",
        )
        self._lbl_example.pack(fill="x", padx=8)

        tk.Frame(right, bg=_C["border"], height=1).pack(fill="x", pady=6)

        tk.Label(
            right, text="Parameters (fill in values):",
            bg=_C["panel"], fg=_C["text_bright"], font=("Segoe UI", 9, "bold"),
            padx=12, anchor="w",
        ).pack(fill="x")

        # Scrollable frame for parameter entries
        params_canvas = tk.Canvas(right, bg=_C["panel"], highlightthickness=0, height=150)
        params_canvas.pack(fill="both", expand=True, padx=8, pady=4)
        params_frame = tk.Frame(params_canvas, bg=_C["panel"])
        params_canvas.create_window((0, 0), window=params_frame, anchor="nw")
        params_frame.bind("<Configure>", lambda e: params_canvas.configure(
            scrollregion=params_canvas.bbox("all")
        ))

        # Storage for the current action + its entry widgets
        _state = {"plugin": None, "spec": None, "entries": {}}

        def _on_select(_event=None):
            sel = listbox.curselection()
            if not sel:
                return
            plugin, spec = actions[sel[0]]
            _state["plugin"] = plugin
            _state["spec"] = spec
            _state["entries"] = {}

            self._lbl_action_name.config(text=f"{plugin.name} → {spec.name}")
            self._lbl_action_desc.config(text=spec.description)
            example = spec.example or f"plugin: {plugin.plugin_id}.{spec.action_id}"
            self._lbl_example.config(text=example)

            # Rebuild parameter entry widgets
            for w in params_frame.winfo_children():
                w.destroy()

            if spec.params_schema:
                for i, (param_name, param_help) in enumerate(spec.params_schema.items()):
                    row = tk.Frame(params_frame, bg=_C["panel"])
                    row.pack(fill="x", pady=3, padx=4)
                    tk.Label(
                        row, text=f"{param_name}:",
                        bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI, width=14, anchor="w",
                    ).pack(side="left")
                    var = tk.StringVar()
                    entry = tk.Entry(
                        row, textvariable=var, width=22,
                        bg=_C["bg"], fg=_C["text_bright"], font=_FONT_MONO,
                        relief="flat", bd=3, insertbackground="white",
                    )
                    entry.pack(side="left", fill="x", expand=True)
                    tk.Label(
                        row, text=f"  ({param_help})",
                        bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 8), anchor="w",
                    ).pack(side="left")
                    _state["entries"][param_name] = var
                    if i == 0:
                        entry.focus_set()
            else:
                tk.Label(
                    params_frame, text="(No parameters required)",
                    bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 9), anchor="w", padx=4,
                ).pack(fill="x")

        listbox.bind("<<ListboxSelect>>", _on_select)
        if actions:
            listbox.selection_set(0)
            _on_select()

        # ── Bottom: Insert button ───────────────────────────────────
        tk.Frame(win, bg=_C["border"], height=1).pack(fill="x")
        btn_row = tk.Frame(win, bg=_C["panel"], pady=8)
        btn_row.pack(fill="x")

        def _do_insert():
            plugin = _state["plugin"]
            spec = _state["spec"]
            if not plugin or not spec:
                messagebox.showwarning("No Selection", "Please select an action first.", parent=win)
                return
            # Build the sequence line: plugin: id.action key=value key2=value2
            parts = [f"plugin: {plugin.plugin_id}.{spec.action_id}"]
            for param_name, var in _state["entries"].items():
                val = var.get().strip()
                if val:
                    # Quote values that contain spaces
                    parts.append(f'{param_name}="{val}"' if " " in val else f"{param_name}={val}")
            line = " ".join(parts)
            self._append_line(line)
            win.destroy()

        tk.Button(
            btn_row, text="Cancel", command=win.destroy,
            bg=_C["border"], fg=_C["text"], font=_FONT_UI, relief="flat", padx=12, pady=4,
        ).pack(side="right", padx=(4, 12))

        tk.Button(
            btn_row, text="➕ Insert Plugin Action", command=_do_insert,
            bg=_C["accent"], fg="white", font=_FONT_BOLD, relief="flat", padx=14, pady=4,
        ).pack(side="right", padx=4)

        win.bind("<Return>", lambda _: _do_insert())
        win.bind("<Escape>", lambda _: win.destroy())

    def _insert_wait(self) -> None:
        from tkinter import simpledialog
        val = simpledialog.askstring(
            "Insert Wait / Pause", "Enter duration (e.g. 200ms, 1s, 500ms):", parent=self, initialvalue="300ms"
        )
        if val:
            self._append_line(f"wait: {val.strip()}")

    def _cmd_strip_delays(self) -> None:
        if not self._parsed_actions:
            return
        cleaned = strip_delays(self._parsed_actions)
        self._parsed_actions = cleaned
        new_text = serialize_sequence(cleaned)
        self._txt_seq.delete("1.0", "end")
        self._txt_seq.insert("1.0", new_text)
        self._on_text_change()
        messagebox.showinfo("Delays Stripped", "All delay pauses have been removed from the sequence.", parent=self)

    # ── Save ─────────────────────────────────────────────

    def _cmd_save(self) -> None:
        name = self._name_var.get().strip()
        if not name:
            messagebox.showwarning("Missing Name", "Please specify a name for this macro.", parent=self)
            return

        text = self._txt_seq.get("1.0", "end-1c")
        try:
            actions, meta = parse_sequence_with_metadata(text)
        except Exception as exc:
            messagebox.showerror("Invalid Sequence", f"Cannot save with errors:\n\n{exc}", parent=self)
            return

        hotkey = self._hotkey_var.get().strip() or meta.get("hotkey", "").strip()
        target_app = self._target_app_var.get().strip() or meta.get("target_app", "").strip()

        # If hotkey matches first action's KEY_COMBO, remove redundant leading action when other actions exist
        if hotkey and actions and actions[0].action_type == ActionType.KEY_COMBO and len(actions) > 1:
            from keymacro.hotkey.listener import parse_hotkey_tokens
            combo_str = " + ".join(actions[0].params.get("keys", []))
            if parse_hotkey_tokens(combo_str) == parse_hotkey_tokens(hotkey):
                actions = actions[1:]

        if not actions:
            messagebox.showwarning("Empty Macro", "Please add at least one action to the macro.", parent=self)
            return

        description = self._desc_var.get().strip()

        if self._macro:
            self._macro.name = name
            self._macro.hotkey = hotkey
            self._macro.target_app = target_app
            self._macro.description = description
            self._macro.actions = actions
            self.result_macro = self._macro
        else:
            self.result_macro = Macro(
                name=name,
                hotkey=hotkey,
                target_app=target_app,
                description=description,
                actions=actions,
            )
        self.destroy()

    def _on_close(self) -> None:
        text = self._txt_seq.get("1.0", "end-1c").strip()
        name = self._name_var.get().strip()
        if (text or name) and self.result_macro is None:
            ans = messagebox.askyesnocancel(
                "Save Macro?",
                "Do you want to save this macro before closing?",
                parent=self,
            )
            if ans is True:
                self._cmd_save()
                return
            elif ans is None:
                return
        self.destroy()
