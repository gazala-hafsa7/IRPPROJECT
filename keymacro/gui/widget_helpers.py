"""
keymacro/gui/widget_helpers.py
───────────────────────────────
Helper utilities for Tkinter widgets, including right-click context menus,
clipboard paste helpers, and URL detection and sanitization.
"""

from __future__ import annotations

import re
import tkinter as tk
from typing import Any, Callable

_URL_REGEX = re.compile(
    r"^(https?://|www\.|[a-zA-Z0-9-]+\.[a-zA-Z]{2,})", re.IGNORECASE
)


def is_url(text: str) -> bool:
    """Return True if text looks like a web URL or domain address."""
    if not text:
        return False
    t = text.strip()
    return bool(_URL_REGEX.match(t))


def sanitize_url(text: str) -> str:
    """Clean up pasted text into a well-formed URL."""
    if not text:
        return ""
    t = text.strip().strip('"\'')
    if t.lower().startswith("www."):
        t = f"https://{t}"
    elif not t.lower().startswith(("http://", "https://")) and "." in t and not " " in t:
        t = f"https://{t}"
    return t


def get_clipboard_text(widget: tk.Widget) -> str:
    """Safely fetch text from the system clipboard."""
    try:
        txt = widget.clipboard_get()
        return txt.strip() if txt else ""
    except Exception:
        return ""


def attach_context_menu(widget: tk.Widget, is_url_field: bool = False) -> tk.Menu:
    """
    Attach a right-click context menu (Cut, Copy, Paste, Paste URL, Clear, Select All)
    and ensure keyboard paste shortcuts (<Control-v>, <Control-V>, <Shift-Insert>)
    work reliably on Tkinter Entry and Text widgets.
    """
    menu = tk.Menu(widget, tearoff=0)

    def _cut():
        try:
            widget.event_generate("<<Cut>>")
        except Exception:
            pass

    def _copy():
        try:
            widget.event_generate("<<Copy>>")
        except Exception:
            pass

    def _paste():
        try:
            if isinstance(widget, tk.Entry):
                txt = get_clipboard_text(widget)
                if txt:
                    if is_url_field:
                        txt = sanitize_url(txt)
                    try:
                        if widget.select_present():
                            first = widget.index("sel.first")
                            last = widget.index("sel.last")
                            widget.delete(first, last)
                            widget.insert(first, txt)
                        else:
                            widget.insert(tk.INSERT, txt)
                    except Exception:
                        widget.delete(0, tk.END)
                        widget.insert(0, txt)
            elif isinstance(widget, tk.Text):
                widget.event_generate("<<Paste>>")
            else:
                widget.event_generate("<<Paste>>")
        except Exception:
            pass

    def _paste_url():
        txt = get_clipboard_text(widget)
        if txt:
            cleaned = sanitize_url(txt)
            if isinstance(widget, tk.Entry):
                try:
                    if widget.select_present():
                        first = widget.index("sel.first")
                        last = widget.index("sel.last")
                        widget.delete(first, last)
                        widget.insert(first, cleaned)
                    else:
                        widget.insert(tk.INSERT, cleaned)
                except Exception:
                    widget.delete(0, tk.END)
                    widget.insert(0, cleaned)
            elif isinstance(widget, tk.Text):
                try:
                    widget.insert(tk.INSERT, cleaned)
                except Exception:
                    pass

    def _clear():
        if isinstance(widget, tk.Entry):
            widget.delete(0, tk.END)
        elif isinstance(widget, tk.Text):
            widget.delete("1.0", tk.END)

    def _select_all():
        if isinstance(widget, tk.Entry):
            widget.select_range(0, tk.END)
            widget.icursor(tk.END)
        elif isinstance(widget, tk.Text):
            widget.tag_add("sel", "1.0", "end")

    menu.add_command(label="✂️ Cut", command=_cut)
    menu.add_command(label="📋 Copy", command=_copy)
    menu.add_command(label="📥 Paste", command=_paste)
    menu.add_command(label="🔗 Paste URL", command=_paste_url)
    menu.add_separator()
    menu.add_command(label="🧹 Clear", command=_clear)
    menu.add_command(label="🔲 Select All", command=_select_all)

    def _show_menu(event):
        try:
            menu.tk_popup(event.x_root, event.y_root)
        finally:
            menu.grab_release()

    widget.bind("<Button-3>", _show_menu)
    widget.bind("<Control-Button-1>", _show_menu)

    # Bind standard shortcuts
    widget.bind("<Control-v>", lambda e: (_paste(), "break")[1])
    widget.bind("<Control-V>", lambda e: (_paste(), "break")[1])
    widget.bind("<Shift-Insert>", lambda e: (_paste(), "break")[1])

    return menu


def create_paste_button(
    parent: tk.Widget,
    entry_widget: tk.Entry,
    variable: tk.StringVar,
    is_url_field: bool = False,
    bg: str = "#3c3c3c",
    fg: str = "#ffffff",
) -> tk.Button:
    """Create a '📋 Paste' button that inserts clipboard text into variable/entry_widget."""

    def _do_paste():
        txt = get_clipboard_text(entry_widget)
        if txt:
            if is_url_field:
                txt = sanitize_url(txt)
            variable.set(txt)

    btn = tk.Button(
        parent,
        text="📋 Paste URL" if is_url_field else "📋 Paste",
        command=_do_paste,
        bg=bg,
        fg=fg,
        font=("Segoe UI", 8),
        relief="flat",
        padx=6,
        pady=1,
        cursor="hand2",
        activebackground="#0078d4",
        activeforeground="white",
    )
    return btn
