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
from keymacro.gui.widget_helpers import (
    attach_context_menu,
    create_paste_button,
    get_clipboard_text,
    is_url,
    sanitize_url,
)

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
        attach_context_menu(self._search_entry)
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
            top_bar, text="🔌 Connected App Plugins & Hub", bg=_C["panel"], fg=_C["text_bright"], font=_FONT_H1
        ).pack(side="left")

        # Top Action buttons
        tk.Button(
            top_bar, text="➕ Connect App as Plugin", command=self._cmd_connect_new_app,
            bg=_C["accent"], fg="white", font=_FONT_BOLD,
            relief="flat", padx=10, pady=4, cursor="hand2",
        ).pack(side="left", padx=6)

        tk.Button(
            top_bar, text="✨ + Custom Action", command=self._cmd_create_custom_action,
            bg="#27ae60", fg="white", font=_FONT_BOLD,
            relief="flat", padx=10, pady=4, cursor="hand2",
        ).pack(side="left", padx=6)

        tk.Button(
            top_bar, text="🗑 Disconnect App", command=self._cmd_disconnect_app,
            bg=_C["panel"], fg=_C["warning"], font=_FONT_UI,
            relief="flat", padx=8, pady=4, cursor="hand2",
            highlightbackground=_C["border"], highlightthickness=1,
        ).pack(side="left", padx=4)

        tk.Button(
            top_bar, text="📂 Open Plugins Folder", command=self._cmd_open_plugins_folder,
            bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            relief="flat", padx=8, pady=4, cursor="hand2",
            highlightbackground=_C["border"], highlightthickness=1,
        ).pack(side="left", padx=4)

        tk.Button(
            top_bar, text="🔄 Reload Plugins", command=self._cmd_reload_plugins,
            bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            relief="flat", padx=8, pady=4, cursor="hand2",
            highlightbackground=_C["border"], highlightthickness=1,
        ).pack(side="left", padx=4)

        # Main horizontal split: Left (App Plugins & Builtin Plugins list), Right (App Details & App Macros)
        pane = tk.PanedWindow(parent, orient="horizontal", bg=_C["bg"], sashwidth=4, sashrelief="flat")
        pane.pack(fill="both", expand=True, padx=16, pady=6)

        # Left list: Plugins & Connected Apps
        left_f = tk.Frame(pane, bg=_C["panel"])
        pane.add(left_f, minsize=260, width=300)

        tk.Label(
            left_f, text="Connected Apps & Plugins", bg=_C["panel"], fg=_C["text_dim"],
            font=("Segoe UI", 9, "bold"), padx=10, pady=4, anchor="w",
        ).pack(fill="x")

        # Search filter for desktop app plugins
        p_search_f = tk.Frame(left_f, bg=_C["panel"], padx=8, pady=2)
        p_search_f.pack(fill="x")
        self._plugin_search_var = tk.StringVar()
        self._plugin_search_var.trace_add("write", lambda *_: self._refresh_plugins())
        e_psearch = tk.Entry(
            p_search_f, textvariable=self._plugin_search_var,
            bg=_C["bg"], fg="white", font=_FONT_UI,
            relief="flat", bd=3, insertbackground="white",
        )
        e_psearch.pack(fill="x")

        self._plugin_listbox = tk.Listbox(
            left_f, bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            selectbackground=_C["row_sel"], relief="flat", bd=4,
        )
        self._plugin_listbox.pack(fill="both", expand=True, padx=8, pady=(4, 8))
        self._plugin_listbox.bind("<<ListboxSelect>>", self._on_plugin_select)

        # Right frame: Details + App Macros + Actions
        right_f = tk.Frame(pane, bg=_C["panel"])
        pane.add(right_f, minsize=460)

        hdr_frame = tk.Frame(right_f, bg=_C["panel"], pady=4)
        hdr_frame.pack(fill="x")

        self._lbl_plugin_name = tk.Label(
            hdr_frame, text="Select an App Plugin", bg=_C["panel"], fg=_C["text_bright"],
            font=_FONT_H1, padx=12, anchor="w",
        )
        self._lbl_plugin_name.pack(fill="x")

        self._lbl_plugin_desc = tk.Label(
            hdr_frame, text="", bg=_C["panel"], fg=_C["text_dim"],
            font=("Segoe UI", 9), padx=12, anchor="w",
        )
        self._lbl_plugin_desc.pack(fill="x")

        tk.Frame(right_f, bg=_C["border"], height=1).pack(fill="x", pady=4)

        # ── Section 1: Macros Configured for this Connected App ─────────────
        macro_hdr = tk.Frame(right_f, bg=_C["panel"], padx=12, pady=2)
        macro_hdr.pack(fill="x")

        tk.Label(
            macro_hdr, text="App-Specific Macros (Active when this app is in use):",
            bg=_C["panel"], fg=_C["text_bright"], font=_FONT_BOLD, anchor="w"
        ).pack(side="left")

        # Action buttons for App Macros
        tk.Button(
            macro_hdr, text="➕ Add Macro for App", command=self._cmd_create_macro_for_selected_plugin,
            bg=_C["accent"], fg="white", font=("Segoe UI", 8, "bold"),
            relief="flat", padx=8, pady=2, cursor="hand2",
        ).pack(side="right", padx=2)

        tk.Button(
            macro_hdr, text="▶ Run Macro", command=self._cmd_run_app_macro,
            bg=_C["success"], fg="white", font=("Segoe UI", 8, "bold"),
            relief="flat", padx=8, pady=2, cursor="hand2",
        ).pack(side="right", padx=2)

        tk.Button(
            macro_hdr, text="✎ Edit Macro", command=self._cmd_edit_app_macro,
            bg=_C["panel"], fg=_C["text_bright"], font=("Segoe UI", 8),
            relief="flat", padx=6, pady=2, cursor="hand2",
            highlightbackground=_C["border"], highlightthickness=1,
        ).pack(side="right", padx=2)

        m_cols = ("name", "hotkey", "steps", "risk")
        self._app_macros_tree = ttk.Treeview(
            right_f, columns=m_cols, show="headings",
            style="Macro.Treeview", selectmode="browse", height=5,
        )
        self._app_macros_tree.heading("name",   text="Macro Name", anchor="w")
        self._app_macros_tree.heading("hotkey", text="Hotkey",     anchor="w")
        self._app_macros_tree.heading("steps",  text="Steps",      anchor="center")
        self._app_macros_tree.heading("risk",   text="Risk",       anchor="center")

        self._app_macros_tree.column("name",   width=180, anchor="w")
        self._app_macros_tree.column("hotkey", width=110, anchor="w")
        self._app_macros_tree.column("steps",  width=50,  anchor="center")
        self._app_macros_tree.column("risk",   width=60,  anchor="center")

        m_vsb = ttk.Scrollbar(right_f, orient="vertical", command=self._app_macros_tree.yview,
                              style="Dark.Vertical.TScrollbar")
        self._app_macros_tree.configure(yscrollcommand=m_vsb.set)
        m_vsb.pack(side="right", fill="y", padx=(0, 8))
        self._app_macros_tree.pack(fill="x", padx=(8, 0), pady=(0, 6))

        tk.Frame(right_f, bg=_C["border"], height=1).pack(fill="x", pady=4)

        # ── Section 2: Built-in Actions & Launchers ─────────────────────────
        tk.Label(
            right_f, text="Built-in Plugin Actions & Launchers:", bg=_C["panel"], fg=_C["text_bright"],
            font=_FONT_BOLD, padx=12, anchor="w",
        ).pack(fill="x")

        act_hdr = tk.Frame(right_f, bg=_C["panel"], padx=12, pady=2)
        act_hdr.pack(fill="x")

        tk.Button(
            act_hdr, text="⚡ Test Plugin Action", command=self._cmd_test_plugin_action,
            bg=_C["panel"], fg=_C["text_bright"], font=("Segoe UI", 8),
            relief="flat", padx=8, pady=2, cursor="hand2",
            highlightbackground=_C["border"], highlightthickness=1,
        ).pack(side="left")

        p_cols = ("action", "desc", "syntax")
        self._actions_tree = ttk.Treeview(
            right_f, columns=p_cols, show="headings",
            style="Macro.Treeview", selectmode="browse", height=4,
        )
        self._actions_tree.heading("action", text="Action ID",   anchor="w")
        self._actions_tree.heading("desc",   text="Description", anchor="w")
        self._actions_tree.heading("syntax", text="Example Sequence Syntax", anchor="w")

        self._actions_tree.column("action", width=110, anchor="w")
        self._actions_tree.column("desc",   width=180, anchor="w")
        self._actions_tree.column("syntax", width=220, anchor="w")

        act_vsb = ttk.Scrollbar(right_f, orient="vertical", command=self._actions_tree.yview,
                                style="Dark.Vertical.TScrollbar")
        self._actions_tree.configure(yscrollcommand=act_vsb.set)
        act_vsb.pack(side="right", fill="y", padx=(0, 8))
        self._actions_tree.pack(fill="both", expand=True, padx=(8, 0), pady=(0, 6))

        # ── Live Active Window Monitor Footer ─────────────────────────────────
        self._lbl_context_status = tk.Label(
            parent, text="Active App Context: Detecting...", bg=_C["bg"], fg=_C["accent"],
            font=("Segoe UI", 9, "italic"), padx=16, pady=4, anchor="w"
        )
        self._lbl_context_status.pack(fill="x", side="bottom")

        # Start live window context monitoring
        self._poll_active_window()

    def _poll_active_window(self) -> None:
        """Periodically update active window info to show context awareness."""
        from keymacro.hotkey.context import get_active_window_info
        exe_name, title = get_active_window_info()
        if exe_name:
            t_short = (title[:35] + "…") if len(title) > 35 else title
            self._lbl_context_status.config(
                text=f"🟢 Active App Context: '{exe_name}' ({t_short or 'active window'}) — macros matching '{exe_name}' fire on focus!",
                fg=_C["success"],
            )
        else:
            self._lbl_context_status.config(
                text="⚪ Active App Context: Global System Focus",
                fg=_C["text_dim"],
            )
        if self.winfo_exists():
            self.after(1200, self._poll_active_window)

    def _refresh_plugins(self) -> None:
        self._plugin_listbox.delete(0, "end")
        all_plugins = self._plugin_mgr.list_plugins()
        q = getattr(self, "_plugin_search_var", None)
        query = q.get().strip().lower() if q else ""

        from keymacro.plugins.base import AppPlugin
        self._filtered_plugins = []
        for p in all_plugins:
            if query:
                match_name = query in p.name.lower()
                match_id = query in p.plugin_id.lower()
                match_target = any(query in t.lower() for t in p.target_apps) if p.target_apps else False
                if not (match_name or match_id or match_target):
                    continue
            self._filtered_plugins.append(p)
            if isinstance(p, AppPlugin):
                self._plugin_listbox.insert("end", f"📱 {p.name} [{p.target_app}]")
            else:
                self._plugin_listbox.insert("end", f"⚡ Plugin: {p.name} [{p.plugin_id}]")

        if self._filtered_plugins:
            self._plugin_listbox.selection_set(0)
            self._show_plugin_details(self._filtered_plugins[0])

    def _on_plugin_select(self, _event=None) -> None:
        sel = self._plugin_listbox.curselection()
        if not sel:
            return
        filtered = getattr(self, "_filtered_plugins", self._plugin_mgr.list_plugins())
        if 0 <= sel[0] < len(filtered):
            self._show_plugin_details(filtered[sel[0]])

    def _show_plugin_details(self, plugin: Any) -> None:
        from keymacro.plugins.base import AppPlugin
        if isinstance(plugin, AppPlugin):
            self._lbl_plugin_name.config(text=f"Connected App: {plugin.name} ({plugin.target_app})")
        else:
            self._lbl_plugin_name.config(text=f"Plugin: {plugin.name} (id: {plugin.plugin_id})")

        target_str = f" | Target App: {', '.join(plugin.target_apps)}" if plugin.target_apps else ""
        self._lbl_plugin_desc.config(text=f"{plugin.description}{target_str}")

        # Populate App-Specific Macros
        self._app_macros_tree.delete(*self._app_macros_tree.get_children())
        store = getattr(self._parent, "_store", None)
        if store and plugin.target_apps:
            all_macros = store.list_all()
            from keymacro.hotkey.context import matches_app
            target = plugin.target_apps[0]
            app_macros = [
                m for m in all_macros
                if m.target_app and matches_app(target, m.target_app, m.target_app)
            ]
            for m in app_macros:
                self._app_macros_tree.insert(
                    "", "end", iid=m.macro_id,
                    values=(m.name, m.hotkey or "—", m.action_count, m.risk_level.value.upper())
                )

        # Populate Plugin Actions
        self._actions_tree.delete(*self._actions_tree.get_children())
        for action_id, spec in plugin.get_actions().items():
            example = spec.example or f"plugin: {plugin.plugin_id}.{action_id}"
            self._actions_tree.insert("", "end", iid=action_id, values=(action_id, spec.description, example))

    def _get_selected_plugin(self) -> Any | None:
        sel = self._plugin_listbox.curselection()
        if not sel:
            return None
        filtered = getattr(self, "_filtered_plugins", self._plugin_mgr.list_plugins())
        if 0 <= sel[0] < len(filtered):
            return filtered[sel[0]]
        return None

    def _cmd_create_custom_action(self) -> None:
        """Show modal dialog to visually create and save custom plugin actions."""
        from keymacro.gui.custom_action_dialog import CustomActionBuilderDialog
        CustomActionBuilderDialog(self, self._plugin_mgr, on_created_callback=lambda *_: self._refresh_plugins())

    def _cmd_connect_new_app(self) -> None:
        """Show dialog to pick an installed application or enter custom app to connect as an App Plugin."""
        apps = self._scanner.scan()
        win = tk.Toplevel(self)
        win.title("Connect Application as Plugin")
        win.configure(bg=_C["bg"])
        win.geometry("540x480")
        win.grab_set()

        tk.Label(
            win, text="Connect Application Profile",
            bg=_C["bg"], fg=_C["text_bright"], font=_FONT_H1, padx=16, pady=10, anchor="w",
        ).pack(fill="x")

        tk.Label(
            win, text="Select an installed app or enter its executable name to create an App Plugin profile:",
            bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 9), padx=16, anchor="w",
        ).pack(fill="x")

        tk.Frame(win, bg=_C["border"], height=1).pack(fill="x", pady=8)

        # Form fields
        form = tk.Frame(win, bg=_C["bg"], padx=16)
        form.pack(fill="x")

        tk.Label(form, text="App Name:", bg=_C["bg"], fg=_C["text_bright"], font=_FONT_UI).grid(row=0, column=0, sticky="w", pady=4)
        var_name = tk.StringVar(value="")
        e_name = tk.Entry(form, textvariable=var_name, width=32, bg=_C["panel"], fg="white", font=_FONT_UI, relief="flat", bd=3)
        e_name.grid(row=0, column=1, sticky="w", padx=8, pady=4)

        tk.Label(form, text="Executable / Target:", bg=_C["bg"], fg=_C["text_bright"], font=_FONT_UI).grid(row=1, column=0, sticky="w", pady=4)
        var_target = tk.StringVar(value="")
        e_target = tk.Entry(form, textvariable=var_target, width=32, bg=_C["panel"], fg="white", font=_FONT_MONO, relief="flat", bd=3)
        e_target.grid(row=1, column=1, sticky="w", padx=8, pady=4)

        tk.Label(
            win, text="Quick Select Installed Application:",
            bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 9, "bold"), padx=16, pady=(10, 4), anchor="w",
        ).pack(fill="x")

        listbox = tk.Listbox(
            win, bg=_C["panel"], fg=_C["text_bright"], font=_FONT_UI,
            selectbackground=_C["row_sel"], relief="flat", bd=4,
        )
        listbox.pack(fill="both", expand=True, padx=16, pady=4)
        for app in apps:
            listbox.insert("end", f"{app.name} ({app.target})")

        def _on_app_select(_e=None):
            sel = listbox.curselection()
            if sel:
                app = apps[sel[0]]
                var_name.set(app.name)
                # Use target or executable name
                target_exe = os.path.basename(app.target) if app.target.lower().endswith(".exe") else app.target
                var_target.set(target_exe)

        listbox.bind("<<ListboxSelect>>", _on_app_select)

        def _save_connection():
            name = var_name.get().strip()
            target = var_target.get().strip()
            if not name or not target:
                messagebox.showwarning("Missing Info", "Please enter both Application Name and Executable Target.", parent=win)
                return
            self._plugin_mgr.connect_app(name=name, target_app=target)
            win.destroy()
            self._refresh_plugins()
            messagebox.showinfo("Connected", f"Connected application profile '{name}' ({target}) successfully!", parent=self)

        btn_row = tk.Frame(win, bg=_C["bg"], pady=10, padx=16)
        btn_row.pack(fill="x")

        tk.Button(btn_row, text="Cancel", command=win.destroy, bg=_C["border"], fg=_C["text"], font=_FONT_UI, relief="flat", padx=12, pady=4).pack(side="right", padx=4)
        tk.Button(btn_row, text="🔗 Connect App", command=_save_connection, bg=_C["accent"], fg="white", font=_FONT_BOLD, relief="flat", padx=14, pady=4).pack(side="right", padx=4)

    def _cmd_disconnect_app(self) -> None:
        plugin = self._get_selected_plugin()
        if not plugin:
            messagebox.showinfo("No Selection", "Please select an App Plugin to disconnect.", parent=self)
            return
        from keymacro.plugins.base import AppPlugin
        if not isinstance(plugin, AppPlugin):
            messagebox.showwarning("Built-in Plugin", f"'{plugin.name}' is a core python plugin and cannot be disconnected.", parent=self)
            return
        if messagebox.askyesno("Disconnect App Plugin", f"Disconnect '{plugin.name}' profile?", parent=self):
            self._plugin_mgr.disconnect_app(plugin.plugin_id)
            self._refresh_plugins()

    def _cmd_create_macro_for_selected_plugin(self) -> None:
        plugin = self._get_selected_plugin()
        if not plugin or not plugin.target_apps:
            messagebox.showinfo("Select App", "Please select a connected App Plugin first.", parent=self)
            return
        target_app = plugin.target_apps[0]
        initial_seq = f"# target_app: {target_app}\n# Add your sequence of actions for {plugin.name} below:\n"
        self.destroy()
        if hasattr(self._parent, "_cmd_new_sequence_macro"):
            self._parent._cmd_new_sequence_macro(initial_sequence=initial_seq)

    def _cmd_run_app_macro(self) -> None:
        sel = self._app_macros_tree.selection()
        if not sel:
            messagebox.showinfo("Select Macro", "Please select an app macro to run.", parent=self)
            return
        macro_id = sel[0]
        store = getattr(self._parent, "_store", None)
        if store and store.exists(macro_id):
            macro = store.load(macro_id)
            self._parent._selected = macro
            self._parent._cmd_run()

    def _cmd_edit_app_macro(self) -> None:
        sel = self._app_macros_tree.selection()
        if not sel:
            messagebox.showinfo("Select Macro", "Please select an app macro to edit.", parent=self)
            return
        macro_id = sel[0]
        store = getattr(self._parent, "_store", None)
        if store and store.exists(macro_id):
            macro = store.load(macro_id)
            self._parent._selected = macro
            self._parent._cmd_edit_sequence()

    def _cmd_test_plugin_action(self) -> None:
        plugin = self._get_selected_plugin()
        sel_action = self._actions_tree.selection()
        if not plugin or not sel_action:
            messagebox.showinfo("Select Action", "Please select a plugin and an action to test.", parent=self)
            return

        action_id = sel_action[0]
        spec = plugin.get_actions().get(action_id)

        if spec and spec.params_schema:
            params = self._collect_params(plugin, spec)
            if params is None:
                return
        else:
            params = {}

        try:
            res = self._plugin_mgr.execute(plugin.plugin_id, action_id, params)
            messagebox.showinfo("Action Test Success", f"Result:\n\n{res}", parent=self)
        except Exception as exc:
            messagebox.showerror("Action Test Failed", f"Execution error:\n\n{exc}", parent=self)

    def _collect_params(self, plugin: Any, spec: Any) -> dict | None:
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

        entries: dict[str, tk.StringVar] = {}
        first_entry = None
        for param_name, param_help in spec.params_schema.items():
            is_url_field = any(k in param_name.lower() for k in ("url", "link", "address", "web"))
            row = tk.Frame(win, bg=_C["bg"])
            row.pack(fill="x", padx=16, pady=4)
            tk.Label(
                row, text=f"{param_name}:",
                bg=_C["bg"], fg=_C["text_bright"], font=_FONT_UI, width=14, anchor="w",
            ).pack(side="left")
            var = tk.StringVar()

            # Pre-fill clipboard URL if available
            clip_txt = get_clipboard_text(win)
            if is_url_field and clip_txt and is_url(clip_txt):
                var.set(sanitize_url(clip_txt))

            e = tk.Entry(
                row, textvariable=var, width=28,
                bg=_C["panel"], fg=_C["text_bright"], font=_FONT_MONO,
                relief="flat", bd=3, insertbackground="white",
            )
            e.pack(side="left", fill="x", expand=True)

            btn_p = create_paste_button(
                row, e, var, is_url_field=is_url_field,
                bg=_C["border"], fg=_C["text_bright"]
            )
            btn_p.pack(side="left", padx=(4, 2))

            tk.Label(
                row, text=f"  ({param_help})",
                bg=_C["bg"], fg=_C["text_dim"], font=("Segoe UI", 8), anchor="w",
            ).pack(side="left")
            attach_context_menu(e, is_url_field=is_url_field)
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

