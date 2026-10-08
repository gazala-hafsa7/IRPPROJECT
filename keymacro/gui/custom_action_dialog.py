"""
keymacro/gui/custom_action_dialog.py
────────────────────────────────────
Modal dialog for visually building and saving user-defined Custom Plug-in Actions.
Example: Open spreadsheet file/URL, wait, and write current timestamp into a log-in column.
"""

from __future__ import annotations

import tkinter as tk
from datetime import datetime
from tkinter import filedialog, messagebox, ttk
from typing import TYPE_CHECKING, Any, Callable

from keymacro.gui.widget_helpers import attach_context_menu, get_clipboard_text, is_url, sanitize_url

if TYPE_CHECKING:
    from keymacro.plugins.manager import PluginManager


_C = {
    "bg":           "#1e1e1e",
    "panel":        "#252526",
    "border":       "#3c3c3c",
    "accent":       "#0078d4",
    "accent_hover": "#1084d8",
    "success":      "#27ae60",
    "text":         "#d4d4d4",
    "text_dim":     "#888888",
    "text_bright":  "#ffffff",
}

_FONT_UI   = ("Segoe UI", 10)
_FONT_BOLD = ("Segoe UI", 10, "bold")
_FONT_MONO = ("Consolas", 10)
_FONT_H1   = ("Segoe UI", 12, "bold")


class CustomActionBuilderDialog(tk.Toplevel):
    """Modal dialog for creating, testing, and saving custom plugin actions."""

    def __init__(
        self,
        parent: tk.Widget,
        plugin_manager: PluginManager,
        on_created_callback: Callable[[str, str], None] | None = None,
    ) -> None:
        super().__init__(parent)
        self.title("✨ Create Custom Plug-in Action")
        self.configure(bg=_C["bg"])
        self.geometry("640x620")
        self.minsize(580, 560)
        self.grab_set()

        self._parent = parent
        self._plugin_mgr = plugin_manager
        self._callback = on_created_callback

        self._build_ui()

        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_rootx() + parent.winfo_width() // 2
        py = parent.winfo_rooty() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"+{px - w // 2}+{py - h // 2}")

    def _build_ui(self) -> None:
        # Header
        hdr = tk.Frame(self, bg=_C["panel"], padx=16, pady=10)
        hdr.pack(fill="x")

        tk.Label(
            hdr, text="✨ Custom Plug-in Action Builder",
            bg=_C["panel"], fg=_C["text_bright"], font=_FONT_H1, anchor="w",
        ).pack(fill="x")

        tk.Label(
            hdr,
            text="Assign your own automation task (e.g. open a spreadsheet & write current time in a log-in column).",
            bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 9), anchor="w",
        ).pack(fill="x", pady=(2, 0))

        tk.Frame(self, bg=_C["border"], height=1).pack(fill="x")

        # Form body
        body = tk.Frame(self, bg=_C["bg"], padx=16, pady=12)
        body.pack(fill="both", expand=True)

        # Action Display Name
        tk.Label(body, text="Action Name:", bg=_C["bg"], fg=_C["text_bright"], font=_FONT_BOLD).grid(row=0, column=0, sticky="w", pady=6)
        self._var_name = tk.StringVar(value="Sheet Log-in Timestamp")
        e_name = tk.Entry(body, textvariable=self._var_name, width=38, bg=_C["panel"], fg="white", font=_FONT_UI, relief="flat", bd=3)
        e_name.grid(row=0, column=1, columnspan=2, sticky="we", padx=8, pady=6)
        attach_context_menu(e_name)

        # Action ID
        tk.Label(body, text="Action ID (syntax key):", bg=_C["bg"], fg=_C["text"], font=_FONT_UI).grid(row=1, column=0, sticky="w", pady=4)
        self._var_id = tk.StringVar(value="sheet_login")
        e_id = tk.Entry(body, textvariable=self._var_id, width=38, bg=_C["panel"], fg=_C["text_bright"], font=_FONT_MONO, relief="flat", bd=3)
        e_id.grid(row=1, column=1, columnspan=2, sticky="we", padx=8, pady=4)
        attach_context_menu(e_id)

        # Target File / Sheet / URL
        tk.Label(body, text="Target File / Sheet / URL:", bg=_C["bg"], fg=_C["text_bright"], font=_FONT_BOLD).grid(row=2, column=0, sticky="w", pady=6)
        self._var_target = tk.StringVar(value="")
        e_target = tk.Entry(body, textvariable=self._var_target, width=28, bg=_C["panel"], fg="white", font=_FONT_MONO, relief="flat", bd=3)
        e_target.grid(row=2, column=1, sticky="we", padx=(8, 4), pady=6)
        attach_context_menu(e_target)

        # Target helper buttons
        target_btns = tk.Frame(body, bg=_C["bg"])
        target_btns.grid(row=2, column=2, sticky="w")

        tk.Button(
            target_btns, text="📂 Browse", command=self._browse_file,
            bg=_C["border"], fg="white", font=("Segoe UI", 8), relief="flat", padx=6, pady=2, cursor="hand2",
        ).pack(side="left", padx=2)

        tk.Button(
            target_btns, text="📋 Paste", command=self._paste_target,
            bg=_C["border"], fg="white", font=("Segoe UI", 8), relief="flat", padx=6, pady=2, cursor="hand2",
        ).pack(side="left", padx=2)

        # Text or Timestamp Pattern
        tk.Label(body, text="Text or Timestamp Pattern:", bg=_C["bg"], fg=_C["text_bright"], font=_FONT_BOLD).grid(row=3, column=0, sticky="w", pady=6)
        self._var_text = tk.StringVar(value="Log-in: {time}")
        e_text = tk.Entry(body, textvariable=self._var_text, width=38, bg=_C["panel"], fg="white", font=_FONT_MONO, relief="flat", bd=3)
        e_text.grid(row=3, column=1, columnspan=2, sticky="we", padx=8, pady=6)
        attach_context_menu(e_text)
        self._var_text.trace_add("write", lambda *_: self._update_preview())

        # Quick Template Preset Chips
        preset_frame = tk.Frame(body, bg=_C["bg"])
        preset_frame.grid(row=4, column=1, columnspan=2, sticky="w", padx=8, pady=(0, 6))

        tk.Label(preset_frame, text="Quick Presets:", bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 8)).pack(side="left", padx=(0, 4))
        self._preset_chip(preset_frame, "🕒 {time}", "Log-in: {time}")
        self._preset_chip(preset_frame, "📅 {timestamp}", "{timestamp}")
        self._preset_chip(preset_frame, "Checked-in", "Checked in at {time}")

        # Live Text Preview
        tk.Label(body, text="Live Type Preview:", bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 9, "italic")).grid(row=5, column=0, sticky="w", pady=4)
        self._lbl_preview = tk.Label(body, text="", bg=_C["panel"], fg="#2ecc71", font=_FONT_MONO, anchor="w", padx=8, pady=4)
        self._lbl_preview.grid(row=5, column=1, columnspan=2, sticky="we", padx=8, pady=4)
        self._update_preview()

        # Delay before typing
        tk.Label(body, text="Delay before typing (sec):", bg=_C["bg"], fg=_C["text"], font=_FONT_UI).grid(row=6, column=0, sticky="w", pady=6)
        self._var_delay = tk.StringVar(value="1.5")
        e_delay = tk.Entry(body, textvariable=self._var_delay, width=12, bg=_C["panel"], fg="white", font=_FONT_MONO, relief="flat", bd=3)
        e_delay.grid(row=6, column=1, sticky="w", padx=8, pady=6)

        # Suffix key
        tk.Label(body, text="After typing key:", bg=_C["bg"], fg=_C["text"], font=_FONT_UI).grid(row=7, column=0, sticky="w", pady=6)
        self._var_suffix = tk.StringVar(value="enter")
        cb_suffix = ttk.Combobox(body, textvariable=self._var_suffix, values=["enter", "tab", "none"], width=14, font=_FONT_UI)
        cb_suffix.grid(row=7, column=1, sticky="w", padx=8, pady=6)

        # Syntax preview
        tk.Label(body, text="Macro Syntax Command:", bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 9, "bold")).grid(row=8, column=0, sticky="w", pady=(12, 4))
        self._lbl_cmd_preview = tk.Label(body, text="", bg=_C["panel"], fg=_C["accent"], font=_FONT_MONO, anchor="w", padx=8, pady=4, wraplength=420)
        self._lbl_cmd_preview.grid(row=8, column=1, columnspan=2, sticky="we", padx=8, pady=(12, 4))

        self._var_name.trace_add("write", lambda *_: self._on_name_change())
        self._var_id.trace_add("write", lambda *_: self._update_cmd_preview())
        self._var_target.trace_add("write", lambda *_: self._update_cmd_preview())

        body.columnconfigure(1, weight=1)
        self._update_cmd_preview()

        # Bottom buttons bar
        tk.Frame(self, bg=_C["border"], height=1).pack(fill="x")
        btn_bar = tk.Frame(self, bg=_C["panel"], padx=16, pady=10)
        btn_bar.pack(fill="x")

        tk.Button(
            btn_bar, text="Cancel", command=self.destroy,
            bg=_C["border"], fg="white", font=_FONT_UI, relief="flat", padx=14, pady=4, cursor="hand2",
        ).pack(side="right", padx=(4, 0))

        tk.Button(
            btn_bar, text="💾 Save Plug-in Action", command=self._cmd_save,
            bg=_C["accent"], fg="white", font=_FONT_BOLD, relief="flat", padx=16, pady=4, cursor="hand2",
            activebackground=_C["accent_hover"], activeforeground="white",
        ).pack(side="right", padx=4)

        tk.Button(
            btn_bar, text="⚡ Test Action Now", command=self._cmd_test,
            bg=_C["success"], fg="white", font=_FONT_BOLD, relief="flat", padx=14, pady=4, cursor="hand2",
        ).pack(side="left")

    def _preset_chip(self, parent: tk.Widget, label: str, pattern: str) -> None:
        def _set():
            self._var_text.set(pattern)
        tk.Button(
            parent, text=label, command=_set,
            bg=_C["border"], fg=_C["text_bright"], font=("Segoe UI", 8),
            relief="flat", padx=6, pady=1, cursor="hand2",
        ).pack(side="left", padx=2)

    def _browse_file(self) -> None:
        fn = filedialog.askopenfilename(
            title="Select Target File or Spreadsheet",
            filetypes=[
                ("All Supported Files", "*.xlsx;*.xls;*.csv;*.txt;*.docx;*.exe"),
                ("Excel / Spreadsheets", "*.xlsx;*.xls;*.csv"),
                ("Text Files", "*.txt;*.csv;*.log"),
                ("Applications", "*.exe"),
                ("All Files", "*.*"),
            ],
            parent=self,
        )
        if fn:
            self._var_target.set(fn)

    def _paste_target(self) -> None:
        txt = get_clipboard_text(self)
        if txt:
            if is_url(txt):
                txt = sanitize_url(txt)
            self._var_target.set(txt)

    def _on_name_change(self) -> None:
        name = self._var_name.get().strip()
        if name:
            aid = name.lower().replace(" ", "_").replace("-", "_")
            aid = "".join(c for c in aid if c.isalnum() or c == "_")
            self._var_id.set(aid)
        self._update_cmd_preview()

    def _update_preview(self) -> None:
        raw = self._var_text.get()
        now = datetime.now()
        out = (
            raw.replace("{timestamp}", now.strftime("%Y-%m-%d %H:%M:%S"))
            .replace("{time}", now.strftime("%H:%M:%S"))
            .replace("{date}", now.strftime("%Y-%m-%d"))
            .replace("{datetime}", now.strftime("%Y-%m-%d %H:%M:%S"))
        )
        self._lbl_preview.config(text=f'"{out}"')

    def _update_cmd_preview(self) -> None:
        aid = self._var_id.get().strip() or "action_id"
        target = self._var_target.get().strip()
        text = self._var_text.get().strip()
        cmd = f"plugin: custom.{aid}"
        if target:
            cmd += f' target="{target}"' if " " in target else f" target={target}"
        if text and text != "{time}":
            cmd += f' text="{text}"' if " " in text else f" text={text}"
        self._lbl_cmd_preview.config(text=cmd)

    def _cmd_test(self) -> None:
        target = self._var_target.get().strip()
        text = self._var_text.get().strip() or "{time}"
        delay = self._var_delay.get().strip() or "1.5"
        suffix = self._var_suffix.get().strip()

        try:
            res = self._plugin_mgr.execute(
                "custom",
                "open_and_type",
                {"target": target, "text": text, "delay": delay, "suffix": suffix},
            )
            messagebox.showinfo("Action Test Success", f"Test Result:\n\n{res}", parent=self)
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("Action Test Failed", f"Execution error:\n\n{exc}", parent=self)

    def _cmd_save(self) -> None:
        aid = self._var_id.get().strip()
        name = self._var_name.get().strip()
        target = self._var_target.get().strip()
        text = self._var_text.get().strip() or "{time}"
        delay_str = self._var_delay.get().strip() or "1.5"
        suffix = self._var_suffix.get().strip()

        if not aid or not name:
            messagebox.showwarning("Input Required", "Please specify Action Name and Action ID.", parent=self)
            return

        try:
            delay_sec = float(delay_str)
        except ValueError:
            delay_sec = 1.5

        # Fetch custom plugin instance
        custom_plugin = self._plugin_mgr.get_plugin("custom")
        if custom_plugin and hasattr(custom_plugin, "save_user_action"):
            custom_plugin.save_user_action(
                action_id=aid,
                name=name,
                description=f"Custom task: open {target or 'active app'} & type {text}",
                target=target,
                text_template=text,
                delay_sec=delay_sec,
                suffix_key=suffix,
            )

        # Reload plugins
        self._plugin_mgr.load_all()

        cmd = self._lbl_cmd_preview.cget("text")
        if self._callback:
            self._callback(aid, cmd)

        messagebox.showinfo("Custom Action Saved", f"Custom action '{name}' saved successfully!\n\nCommand: {cmd}", parent=self)
        self.destroy()
