"""
keymacro/hotkey/context.py
──────────────────────────
Detects the currently active / focused application on Windows.
Enables app-specific shortcuts where the same shortcut (e.g. `ctrl+o+a`) can do
different actions in Chrome, Spotify, Notepad, or globally.
"""

from __future__ import annotations

import os
import sys
from typing import Tuple

if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
else:
    user32 = None  # type: ignore[assignment]
    kernel32 = None  # type: ignore[assignment]


def get_active_window_info() -> Tuple[str, str]:
    """Return (process_name_or_exe, window_title) for the current foreground window."""
    if sys.platform != "win32" or user32 is None:
        return ("", "")

    try:
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return ("", "")

        # 1. Window Title
        length = user32.GetWindowTextLengthW(hwnd)
        title = ""
        if length > 0:
            buff = ctypes.create_unicode_buffer(length + 1)
            user32.GetWindowTextW(hwnd, buff, length + 1)
            title = buff.value

        # 2. Process ID & Name
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return ("", title)

        exe_name = ""
        h_proc = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if h_proc:
            try:
                exe_buf = ctypes.create_unicode_buffer(1024)
                size = wintypes.DWORD(1024)
                if kernel32.QueryFullProcessImageNameW(h_proc, 0, exe_buf, ctypes.byref(size)):
                    exe_name = os.path.basename(exe_buf.value)
            finally:
                kernel32.CloseHandle(h_proc)

        return (exe_name.lower(), title)
    except Exception:  # noqa: BLE001
        return ("", "")


def matches_app(target_app: str, active_exe: str, active_title: str) -> bool:
    """Determine whether the active foreground app matches target_app.

    If target_app is empty or 'global', it matches any application.
    Otherwise, checks whether target_app (case-insensitive) is contained
    in the executable name or the window title.
    """
    clean_target = target_app.strip().lower()
    if not clean_target or clean_target in ("global", "all", "*"):
        return True

    clean_exe = active_exe.strip().lower()
    clean_title = active_title.strip().lower()

    # Direct match on exe stem or full name
    target_stem = clean_target.removesuffix(".exe")
    if target_stem in clean_exe or clean_target in clean_exe:
        return True

    # Match in window title (e.g. 'Spotify', 'Google Chrome', 'Visual Studio Code')
    if clean_target in clean_title or target_stem in clean_title:
        return True

    return False
