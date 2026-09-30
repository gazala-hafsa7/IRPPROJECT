"""
keymacro/launcher/app_scanner.py
────────────────────────────────
Discovers installed applications on Windows and provides search & launch utilities.

Scans:
1. Standard Windows desktop utilities (Calculator, Notepad, PowerShell, etc.)
2. Windows Start Menu programs (%APPDATA% & %ProgramData%)
3. Windows Registry App Paths (HKLM & HKCU)
"""

from __future__ import annotations

import os
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

if sys.platform == "win32":
    import winreg
else:
    winreg = None  # type: ignore[assignment]


@dataclass
class InstalledApp:
    """Represents an installed application on the system."""

    name: str
    target: str
    category: str = "Application"
    is_system: bool = False

    def launch(self) -> None:
        """Launch the application."""
        if sys.platform == "win32":
            os.startfile(self.target)
        else:
            subprocess.Popen([self.target])


# Common Windows system utilities available on virtually all installations
_SYSTEM_APPS: list[tuple[str, str, str]] = [
    ("Notepad", "notepad.exe", "Utility"),
    ("Calculator", "calc.exe", "Utility"),
    ("Command Prompt", "cmd.exe", "System"),
    ("Windows PowerShell", "powershell.exe", "System"),
    ("File Explorer", "explorer.exe", "System"),
    ("Task Manager", "taskmgr.exe", "System"),
    ("Paint", "mspaint.exe", "Graphics"),
    ("Snipping Tool", "snippingtool.exe", "Utility"),
    ("Remote Desktop Connection", "mstsc.exe", "Network"),
    ("Registry Editor", "regedit.exe", "System"),
    ("Control Panel", "control.exe", "System"),
]


class AppScanner:
    """Scans and indexes installed Windows applications."""

    def __init__(self) -> None:
        self._apps: list[InstalledApp] = []
        self._scanned = False

    def scan(self, force_refresh: bool = False) -> list[InstalledApp]:
        """Scan system for installed applications and return unique list."""
        if self._scanned and not force_refresh:
            return self._apps

        discovered: dict[str, InstalledApp] = {}

        # 1. System apps
        for name, cmd, cat in _SYSTEM_APPS:
            discovered[name.lower()] = InstalledApp(
                name=name, target=cmd, category=cat, is_system=True
            )

        # 2. Windows Start Menu shortcuts
        for folder in self._start_menu_dirs():
            if folder.exists():
                for lnk in folder.rglob("*.lnk"):
                    # Ignore uninstallers or help shortcuts
                    low_name = lnk.stem.lower()
                    if any(x in low_name for x in ("uninstall", "help", "documentation", "readme")):
                        continue
                    if low_name not in discovered:
                        discovered[low_name] = InstalledApp(
                            name=lnk.stem,
                            target=str(lnk),
                            category="Desktop App",
                            is_system=False,
                        )

        # 3. Registry App Paths
        if winreg is not None:
            self._scan_registry_app_paths(discovered)

        # Sort alphabetically by app name
        self._apps = sorted(discovered.values(), key=lambda a: a.name.lower())
        self._scanned = True
        return self._apps

    def search(self, query: str) -> list[InstalledApp]:
        """Search apps by name (substring, case-insensitive)."""
        if not self._scanned:
            self.scan()
        q = query.strip().lower()
        if not q:
            return self._apps
        return [app for app in self._apps if q in app.name.lower()]

    def launch(self, target: str) -> None:
        """Launch an application by executable name or path."""
        if sys.platform == "win32":
            os.startfile(target)
        else:
            subprocess.Popen([target])

    # ── Internals ─────────────────────────────────────────────────────────────

    def _start_menu_dirs(self) -> list[Path]:
        dirs: list[Path] = []
        user_appdata = os.environ.get("APPDATA")
        if user_appdata:
            dirs.append(Path(user_appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs")

        all_users = os.environ.get("ProgramData")
        if all_users:
            dirs.append(Path(all_users) / "Microsoft" / "Windows" / "Start Menu" / "Programs")
        return dirs

    def _scan_registry_app_paths(self, discovered: dict[str, InstalledApp]) -> None:
        """Enumerate HKLM and HKCU App Paths keys for registered exe paths."""
        hives = [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]
        sub_key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"

        for hive in hives:
            try:
                with winreg.OpenKey(hive, sub_key_path) as root_key:
                    num_subkeys, _, _ = winreg.QueryInfoKey(root_key)
                    for i in range(num_subkeys):
                        try:
                            subkey_name = winreg.EnumKey(root_key, i)
                            with winreg.OpenKey(root_key, subkey_name) as app_key:
                                exe_path, _ = winreg.QueryValueEx(app_key, "")
                                if exe_path and os.path.exists(exe_path):
                                    stem = Path(exe_path).stem
                                    low_stem = stem.lower()
                                    if low_stem not in discovered:
                                        discovered[low_stem] = InstalledApp(
                                            name=stem.title() if stem.islower() else stem,
                                            target=exe_path,
                                            category="Installed App",
                                            is_system=False,
                                        )
                        except OSError:
                            continue
            except OSError:
                continue
