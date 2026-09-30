"""
keymacro/gui/launcher_dialog.py
───────────────────────────────
App Launcher & Plugin Hub dialog.
Search and launch installed Windows apps, create macros for apps with 1 click,
and inspect / test / reload plugins.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from tkinter import messagebox, ttk
from typing import TYPE_CHECKING, Any

from keymacro.launcher.app_scanner import AppScanner, InstalledApp
from keymacro.plugins.manager import PluginManager

if TYPE_CHECKING:
    pass

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
_FONT_MONO = ("Consolas", 9)
_FONT_H1   = ("Segoe UI", 13, "bold")


class AppLauncherDialog(tk.Toplevel):
    """Unified modal for Windows App Launcher and Installed Apps Plugin Hub."""

    def __init__(
        self,
        parent: tk.Tk,
        scanner: AppScanner,
        plugin_manager: PluginManager,
        on_create_macro_with_app: Any = None,
    ) -> None:
        super().__init__(parent)
        self.title("App Launcher & Plugin Hub")
        self.configure(bg=_C["bg"])
        self.minsize(860, 580)
        self.geometry("960x640")
        self.grab_set()

        self._parent = parent
        self._scanner = scanner
        self._plugin_mgr = plugin_manager
        self._on_create_macro = on_create_macro_with_app

        self._displayed_apps: list[InstalledApp] = []

        self._build_ui()

        # Centre over parent
        self.update_idletasks()
        px = parent.winfo_x() + parent.winfo_width() // 2
        py = parent.winfo_y() + parent.winfo_height() // 2
        w, h = self.winfo_width(), self.winfo_height()
        self.geometry(f"{w}x{h}+{px - w // 2}+{py - h // 2}")

        self._refresh_apps()
        self._refresh_plugins()

    def _build_ui(self) -> None:
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True)

        # Tab 1: App Launcher
        tab_launcher = tk.Frame(notebook, bg=_C["bg"])
        notebook.add(tab_launcher, text="  🚀 App Launcher  ")

        # Tab 2: Plugins Hub
        tab_plugins = tk.Frame(notebook, bg=_C["bg"])
        notebook.add(tab_plugins, text="  🔌 Installed App Plugins  ")

        self._build_launcher_tab(tab_launcher)
        self._build_plugins_tab(tab_plugins)

    # ──────────────────────────────────────────
    # TAB 1: App Launcher
    # ──────────────────────────────────────────

    def _build_launcher_tab(self, parent: tk.Frame) -> None:
        top_bar = tk.Frame(parent, bg=_C["panel"], padx=16, pady=10)
        top_bar.pack(fill="x")

        # Search bar
        tk.Label(
            top_bar, text="Search Apps:", bg=_C["panel"], fg=_C["text_bright"], font=_FONT_BOLD
        ).pack(side="left", padx=(0, 8))

        self._search_var = tk.StringVar()
        self._search_var.trace_add("write", lambda *_: self._filter_apps())
        self._search_entry = tk.Entry(
            top_bar, textvariable=self._search_var, width=35,
            bg=_C["bg"], fg=_C["text_bright"], font=_FONT_UI,
            relief="flat", bd=4, insertbackground="white",
        )
        self._search_entry.pack(side="left", padx=(0, 16))
        self._search_entry.focus_set()

        # Action buttons
        tk.Button(
            top_bar, text="▶ Launch Selected", command=self._cmd_launch,
            bg=_C["accent"], fg="white", font=_FONT_BOLD,
            relief="flat", padx=12, pady=4, cursor="hand2",
        ).pack(side="left", padx=4)

        tk.Button(
            top_bar, text="➕ Create Macro for App", command=self._cmd_create_macro_for_app,
            bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            relief="flat", padx=10, pady=4, cursor="hand2",
            highlightbackground=_C["border"], highlightthickness=1,
        ).pack(side="left", padx=4)

        tk.Button(
            top_bar, text="🔄 Rescan Apps", command=self._cmd_rescan,
            bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 9),
            relief="flat", padx=8, pady=4, cursor="hand2",
        ).pack(side="right")

        # Treeview for apps
        tree_frame = tk.Frame(parent, bg=_C["bg"])
        tree_frame.pack(fill="both", expand=True, padx=16, pady=10)

        cols = ("name", "category", "target")
        self._app_tree = ttk.Treeview(
            tree_frame, columns=cols, show="headings",
            style="Macro.Treeview", selectmode="browse",
        )
        self._app_tree.heading("name",     text="Application Name", anchor="w")
        self._app_tree.heading("category", text="Category",         anchor="center")
        self._app_tree.heading("target",   text="Target / Executable Path", anchor="w")

        self._app_tree.column("name",     width=220, anchor="w")
        self._app_tree.column("category", width=120, anchor="center")
        self._app_tree.column("target",   width=540, anchor="w")

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self._app_tree.yview,
                            style="Dark.Vertical.TScrollbar")
        self._app_tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        self._app_tree.pack(fill="both", expand=True)

        self._app_tree.bind("<Double-1>", lambda _: self._cmd_launch())
        self._app_tree.bind("<Return>", lambda _: self._cmd_launch())

        # Status footer
        self._lbl_app_status = tk.Label(
            parent, text="Scanning...", bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 9), padx=16, pady=6, anchor="w"
        )
        self._lbl_app_status.pack(fill="x")

    def _refresh_apps(self, force: bool = False) -> None:
        apps = self._scanner.scan(force_refresh=force)
        self._displayed_apps = apps
        self._populate_app_tree(apps)
        self._lbl_app_status.config(text=f"Total {len(apps)} installed application(s) indexed.")

    def _filter_apps(self) -> None:
        q = self._search_var.get().strip()
        results = self._scanner.search(q)
        self._displayed_apps = results
        self._populate_app_tree(results)
        self._lbl_app_status.config(text=f"Showing {len(results)} matching application(s).")

    def _populate_app_tree(self, apps: list[InstalledApp]) -> None:
        self._app_tree.delete(*self._app_tree.get_children())
        for idx, app in enumerate(apps):
            self._app_tree.insert("", "end", iid=str(idx), values=(app.name, app.category, app.target))

    def _get_selected_app(self) -> InstalledApp | None:
        sel = self._app_tree.selection()
        if not sel:
            return None
        idx = int(sel[0])
        if 0 <= idx < len(self._displayed_apps):
            return self._displayed_apps[idx]
        return None

    def _cmd_launch(self) -> None:
        app = self._get_selected_app()
        if not app:
            messagebox.showinfo("No Selection", "Please select an application to launch.", parent=self)
            return
        try:
            app.launch()
            self._lbl_app_status.config(text=f"Launched '{app.name}' successfully.")
        except Exception as exc:
            messagebox.showerror("Launch Error", f"Could not launch '{app.name}':\n\n{exc}", parent=self)

    def _cmd_create_macro_for_app(self) -> None:
        app = self._get_selected_app()
        if not app:
            messagebox.showinfo("No Selection", "Please select an application.", parent=self)
            return
        self.destroy()
        if self._on_create_macro:
            self._on_create_macro(app)

    def _cmd_rescan(self) -> None:
        self._refresh_apps(force=True)

    # ──────────────────────────────────────────
    # TAB 2: Plugins Hub
    # ──────────────────────────────────────────

    def _build_plugins_tab(self, parent: tk.Frame) -> None:
        top_bar = tk.Frame(parent, bg=_C["panel"], padx=16, pady=10)
        top_bar.pack(fill="x")

        tk.Label(
            top_bar, text="Installed App Plugins", bg=_C["panel"], fg=_C["text_bright"], font=_FONT_H1
        ).pack(side="left")

        # Action buttons
        tk.Button(
            top_bar, text="⚡ Test Selected Action", command=self._cmd_test_plugin_action,
            bg=_C["accent"], fg="white", font=_FONT_BOLD,
            relief="flat", padx=10, pady=4, cursor="hand2",
        ).pack(side="left", padx=16)

        tk.Button(
            top_bar, text="📂 Open Plugins Folder", command=self._cmd_open_plugins_folder,
            bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            relief="flat", padx=10, pady=4, cursor="hand2",
            highlightbackground=_C["border"], highlightthickness=1,
        ).pack(side="left", padx=4)

        tk.Button(
            top_bar, text="🔄 Reload Plugins", command=self._cmd_reload_plugins,
            bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            relief="flat", padx=10, pady=4, cursor="hand2",
            highlightbackground=_C["border"], highlightthickness=1,
        ).pack(side="left", padx=4)

        tk.Button(
            top_bar, text="📖 Plugin Guide", command=self._cmd_view_guide,
            bg=_C["panel"], fg=_C["text_dim"], font=("Segoe UI", 9),
            relief="flat", padx=8, pady=4, cursor="hand2",
        ).pack(side="right")

        # Main horizontal split: Left (Plugins list), Right (Actions & Details)
        pane = tk.PanedWindow(parent, orient="horizontal", bg=_C["bg"], sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=16, pady=10)

        # Left list: Plugins
        left_f = tk.Frame(pane, bg=_C["panel"])
        pane.add(left_f, minsize=240, width=280)

        tk.Label(
            left_f, text="Loaded Plugins", bg=_C["panel"], fg=_C["text_dim"],
            font=("Segoe UI", 9, "bold"), padx=10, pady=6, anchor="w",
        ).pack(fill="x")

        self._plugin_listbox = tk.Listbox(
            left_f, bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            selectbackground=_C["row_sel"], relief="flat", bd=4,
        )
        self._plugin_listbox.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._plugin_listbox.bind("<<ListboxSelect>>", self._on_plugin_select)

        # Right frame: Action details
        right_f = tk.Frame(pane, bg=_C["panel"])
        pane.add(right_f, minsize=420)

        self._lbl_plugin_name = tk.Label(
            right_f, text="Select a Plugin", bg=_C["panel"], fg=_C["text_bright"],
            font=_FONT_H1, padx=12, pady=6, anchor="w",
        )
        self._lbl_plugin_name.pack(fill="x")

        self._lbl_plugin_desc = tk.Label(
            right_f, text="", bg=_C["panel"], fg=_C["text_dim"],
            font=("Segoe UI", 9), padx=12, anchor="w",
        )
        self._lbl_plugin_desc.pack(fill="x")

        tk.Frame(right_f, bg=_C["border"], height=1).pack(fill="x", pady=6)

        tk.Label(
            right_f, text="Supported Actions & Macro Syntax:", bg=_C["panel"], fg=_C["text_bright"],
            font=_FONT_BOLD, padx=12, anchor="w",
        ).pack(fill="x")

        p_cols = ("action", "desc", "syntax")
        self._actions_tree = ttk.Treeview(
            right_f, columns=p_cols, show="headings",
            style="Macro.Treeview", selectmode="browse",
        )
        self._actions_tree.heading("action", text="Action ID",   anchor="w")
        self._actions_tree.heading("desc",   text="Description", anchor="w")
        self._actions_tree.heading("syntax", text="Example Sequence Syntax", anchor="w")

        self._actions_tree.column("action", width=120, anchor="w")
        self._actions_tree.column("desc",   width=220, anchor="w")
        self._actions_tree.column("syntax", width=260, anchor="w")

        act_vsb = ttk.Scrollbar(right_f, orient="vertical", command=self._actions_tree.yview,
                                style="Dark.Vertical.TScrollbar")
        self._actions_tree.configure(yscrollcommand=act_vsb.set)
        act_vsb.pack(side="right", fill="y", padx=(0, 8), pady=(0, 8))
        self._actions_tree.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 8))

    def _refresh_plugins(self) -> None:
        self._plugin_listbox.delete(0, "end")
        plugins = self._plugin_mgr.list_plugins()
        for p in plugins:
            self._plugin_listbox.insert("end", f"⚡ {p.name} [{p.plugin_id}]")
        if plugins:
            self._plugin_listbox.selection_set(0)
            self._show_plugin_details(plugins[0])

    def _on_plugin_select(self, _event=None) -> None:
        sel = self._plugin_listbox.curselection()
        if not sel:
            return
        plugins = self._plugin_mgr.list_plugins()
        if 0 <= sel[0] < len(plugins):
            self._show_plugin_details(plugins[sel[0]])

    def _show_plugin_details(self, plugin: Any) -> None:
        self._lbl_plugin_name.config(text=f"Plugin: {plugin.name} (id: {plugin.plugin_id})")
        target_str = f" | Targets: {', '.join(plugin.target_apps)}" if plugin.target_apps else ""
        self._lbl_plugin_desc.config(text=f"{plugin.description}{target_str}")

        self._actions_tree.delete(*self._actions_tree.get_children())
        for action_id, spec in plugin.get_actions().items():
            example = spec.example or f"plugin: {plugin.plugin_id}.{action_id}"
            self._actions_tree.insert("", "end", iid=action_id, values=(action_id, spec.description, example))

    def _cmd_test_plugin_action(self) -> None:
        sel_plugin = self._plugin_listbox.curselection()
        sel_action = self._actions_tree.selection()
        if not sel_plugin or not sel_action:
            messagebox.showinfo("Select Action", "Please select a plugin and an action to test.", parent=self)
            return

        plugin = self._plugin_mgr.list_plugins()[sel_plugin[0]]
        action_id = sel_action[0]
        spec = plugin.get_actions().get(action_id)

        # If the action has parameters, collect them from the user first
        if spec and spec.params_schema:
            params = self._collect_params(plugin, spec)
            if params is None:
                return  # user cancelled
        else:
            params = {}

        try:
            res = self._plugin_mgr.execute(plugin.plugin_id, action_id, params)
            messagebox.showinfo("Action Test Success", f"Result:\n\n{res}", parent=self)
        except Exception as exc:
            messagebox.showerror("Action Test Failed", f"Execution error:\n\n{exc}", parent=self)

    def _collect_params(self, plugin: Any, spec: Any) -> dict | None:
        """Show a small dialog to collect parameter values for a plugin action.

        Returns a dict of {param_name: value} strings, or None if the user cancelled.
        """
        win = tk.Toplevel(self)
        win.title(f"Parameters — {plugin.name} › {spec.name}")
        win.configure(bg=_C["bg"])
        win.resizable(False, False)
        win.grab_set()

        tk.Label(
            win, text=f"{plugin.name}  ›  {spec.name}",
            bg=_C["bg"], fg=_C["text_bright"], font=_FONT_H1, padx=16, pady=10, anchor="w",
        ).pack(fill="x")

        tk.Label(
            win, text=spec.description,
            bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 9),
            padx=16, pady=2, anchor="w", wraplength=380, justify="left",
        ).pack(fill="x")

        tk.Frame(win, bg=_C["border"], height=1).pack(fill="x", pady=8)

        # Build one entry per parameter
        entries: dict[str, tk.StringVar] = {}
        first_entry = None
        for param_name, param_help in spec.params_schema.items():
            row = tk.Frame(win, bg=_C["bg"])
            row.pack(fill="x", padx=16, pady=4)
            tk.Label(
                row, text=f"{param_name}:",
                bg=_C["bg"], fg=_C["text_bright"], font=_FONT_UI, width=14, anchor="w",
            ).pack(side="left")
            var = tk.StringVar()
            e = tk.Entry(
                row, textvariable=var, width=30,
                bg=_C["panel"], fg=_C["text_bright"], font=_FONT_MONO,
                relief="flat", bd=3, insertbackground="white",
            )
            e.pack(side="left", fill="x", expand=True)
            tk.Label(
                row, text=f"  ({param_help})",
                bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 8), anchor="w",
            ).pack(side="left")
            entries[param_name] = var
            if first_entry is None:
                first_entry = e

        if first_entry:
            first_entry.focus_set()

        tk.Frame(win, bg=_C["border"], height=1).pack(fill="x", pady=(8, 0))

        result: dict[str, dict | None] = {"value": None}

        def _run():
            result["value"] = {k: v.get().strip() for k, v in entries.items()}
            win.destroy()

        def _cancel():
            win.destroy()

        btn_row = tk.Frame(win, bg=_C["bg"], pady=10)
        btn_row.pack(fill="x")
        tk.Button(
            btn_row, text="Cancel", command=_cancel,
            bg=_C["border"], fg=_C["text"], font=_FONT_UI, relief="flat", padx=12, pady=4,
        ).pack(side="right", padx=(4, 16))
        tk.Button(
            btn_row, text="⚡ Run Action", command=_run,
            bg=_C["accent"], fg="white", font=_FONT_BOLD, relief="flat", padx=14, pady=4,
        ).pack(side="right", padx=4)

        win.bind("<Return>", lambda _: _run())
        win.bind("<Escape>", lambda _: _cancel())

        # Centre over self
        win.update_idletasks()
        px = self.winfo_x() + self.winfo_width() // 2
        py = self.winfo_y() + self.winfo_height() // 2
        w, h = win.winfo_width(), win.winfo_height()
        win.geometry(f"+{px - w // 2}+{py - h // 2}")

        self.wait_window(win)
        return result["value"]

    def _cmd_open_plugins_folder(self) -> None:
        folder = self._plugin_mgr.user_plugins_dir
        if sys.platform == "win32":
            os.startfile(str(folder))
        else:
            subprocess.Popen(["explorer", str(folder)])

    def _cmd_reload_plugins(self) -> None:
        self._plugin_mgr.load_all()
        self._refresh_plugins()
        messagebox.showinfo("Reload Complete", f"Loaded {len(self._plugin_mgr.list_plugins())} plugin(s).", parent=self)

    def _cmd_view_guide(self) -> None:
        from pathlib import Path
        guide_path = Path(__file__).resolve().parents[2] / "PLUGINS_GUIDE.md"
        if guide_path.exists():
            os.startfile(str(guide_path))
        else:
            messagebox.showinfo("Plugin Guide", "See PLUGINS_GUIDE.md in the project root directory.", parent=self)
