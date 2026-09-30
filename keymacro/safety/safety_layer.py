"""
keymacro/safety/safety_layer.py
─────────────────────────────────
Safety layer — risk assessment, path blocking, file backup, and the
confirmation dialog shown before any HIGH-risk macro runs.

Rules
─────
1. Any macro whose aggregate risk is HIGH must be previewed and confirmed
   before replay.  This is enforced by ``run_allowed()``.

2. Any file-system action (FILE_DELETE, FILE_MOVE, FILE_COPY) that targets
   a path under BLOCKED_PATHS is hard-blocked — ``run_allowed()`` raises
   ``BlockedPathError`` and replay does NOT proceed.

3. Before any high-risk file-system action executes, ``backup_file()``
   creates a timestamped copy of the target.

4. Dry-run mode bypasses (2) and (3) entirely — it always returns True so the
   preview dialog can show what *would* happen.

Public API
──────────
SafetyLayer(root_window: tk.Tk | None)
    .assess_risk(macro)       → RiskLevel
    .is_path_blocked(path)    → bool
    .backup_file(path)        → Path  (path of backup copy)
    .run_allowed(macro, dry_run) → bool
         Returns True  → safe to proceed (user confirmed if needed)
         Returns False → user cancelled in the confirmation dialog
         Raises BlockedPathError → hard-blocked path detected

Exceptions
──────────
SafetyError      – base class
BlockedPathError – a file-system action targets a protected path
"""

from __future__ import annotations

import os
import shutil
import tkinter as tk
from datetime import datetime, timezone
from pathlib import Path
from tkinter import messagebox, scrolledtext
from typing import TYPE_CHECKING

from keymacro.models.action import ActionType, Macro, RiskLevel

if TYPE_CHECKING:
    pass


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────

class SafetyError(Exception):
    """Base class for all safety-layer exceptions."""


class BlockedPathError(SafetyError):
    """Raised when an action targets a hard-blocked system path."""

    def __init__(self, path: str, blocked_by: str) -> None:
        super().__init__(
            f"Hard-blocked: {path!r} is inside protected path {blocked_by!r}"
        )
        self.path = path
        self.blocked_by = blocked_by


# ──────────────────────────────────────────────
# Protected path prefixes (normalised, lowercase)
# ──────────────────────────────────────────────

_RAW_BLOCKED = [
    r"C:\Windows",
    r"C:\Program Files",
    r"C:\Program Files (x86)",
    r"C:\ProgramData\Microsoft",
    r"C:\Users\Default",
    r"C:\Users\All Users",
]

# Build normalised set at import time
BLOCKED_PATHS: frozenset[str] = frozenset(
    os.path.normcase(os.path.normpath(p)) for p in _RAW_BLOCKED
)

# File-system action types (always HIGH risk)
_FS_TYPES = frozenset({ActionType.FILE_DELETE, ActionType.FILE_MOVE, ActionType.FILE_COPY})

# Paths extracted per action type (which param keys hold paths)
_FS_PATHS: dict[ActionType, list[str]] = {
    ActionType.FILE_DELETE: ["path"],
    ActionType.FILE_MOVE:   ["src", "dst"],
    ActionType.FILE_COPY:   ["src", "dst"],
}


# ──────────────────────────────────────────────
# SafetyLayer
# ──────────────────────────────────────────────

class SafetyLayer:
    """Evaluates macros for risk and enforces safety policies.

    Parameters
    ----------
    root_window : tk.Tk | None
        The main Tk window, used as the parent for modal dialogs.
        Pass None in headless / test environments — dialogs will raise
        ``RuntimeError`` instead of showing.
    """

    def __init__(self, root_window: "tk.Tk | None" = None) -> None:
        self._root = root_window

    # ── risk assessment ────────────────────────────

    def assess_risk(self, macro: Macro) -> RiskLevel:
        """Return the aggregate risk level of *macro* (worst-case action)."""
        return macro.risk_level

    # ── path blocking ──────────────────────────────

    def is_path_blocked(self, path: str) -> bool:
        """Return True if *path* falls inside any of the BLOCKED_PATHS."""
        normalised = os.path.normcase(os.path.normpath(path))
        for blocked in BLOCKED_PATHS:
            if normalised == blocked or normalised.startswith(blocked + os.sep):
                return True
        return False

    # ── file backup ────────────────────────────────

    def backup_file(self, path: str) -> Path:
        """Create a timestamped backup of *path* next to the original.

        Returns the Path of the backup file.
        Raises FileNotFoundError if *path* does not exist.
        """
        src = Path(path)
        if not src.exists():
            raise FileNotFoundError(f"Cannot back up non-existent file: {path!r}")
        ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
        backup = src.with_suffix(f".keymacro_backup_{ts}{src.suffix}")
        shutil.copy2(src, backup)
        return backup

    # ── main gate ──────────────────────────────────

    def run_allowed(self, macro: Macro, dry_run: bool = False) -> bool:
        """Determine whether *macro* is allowed to run.

        Steps
        ─────
        1. If dry_run, always return True (no real changes will happen).
        2. Check all file-system actions for blocked paths → BlockedPathError.
        3. If macro risk is HIGH, show preview + confirmation dialog.
           Returns True if user confirms, False if user cancels.
        4. Back up any files targeted by destructive actions.
        5. Return True for LOW/MEDIUM without dialog.

        Raises
        ──────
        BlockedPathError  – hard-blocked path found (even in non-dry-run)
        """
        if dry_run:
            return True

        # Step 2: blocked path check (always, regardless of risk level)
        self._check_blocked_paths(macro)

        risk = self.assess_risk(macro)

        if risk == RiskLevel.HIGH:
            # Show preview dialog — returns True if user clicked "Run Anyway"
            confirmed = self._show_confirmation_dialog(macro)
            if not confirmed:
                return False
            # Step 4: back up targeted files before destructive actions
            self._backup_targets(macro)

        return True

    # ── internals ──────────────────────────────────

    def _check_blocked_paths(self, macro: Macro) -> None:
        """Raise BlockedPathError if any FS action targets a blocked path."""
        for action in macro.actions:
            if action.action_type not in _FS_PATHS:
                continue
            for param_key in _FS_PATHS[action.action_type]:
                path = action.params.get(param_key, "")
                if path and self.is_path_blocked(path):
                    raise BlockedPathError(path, self._blocked_root(path))

    def _blocked_root(self, path: str) -> str:
        """Return the BLOCKED_PATHS entry that covers *path*."""
        normalised = os.path.normcase(os.path.normpath(path))
        for blocked in BLOCKED_PATHS:
            if normalised == blocked or normalised.startswith(blocked + os.sep):
                return blocked
        return "<unknown>"

    def _backup_targets(self, macro: Macro) -> None:
        """Back up files that destructive actions will touch."""
        for action in macro.actions:
            if action.action_type not in {ActionType.FILE_DELETE, ActionType.FILE_MOVE}:
                continue
            src_key = "path" if action.action_type == ActionType.FILE_DELETE else "src"
            src = action.params.get(src_key, "")
            if src and Path(src).exists():
                try:
                    backup = self.backup_file(src)
                    print(f"[Safety] Backed up: {src!r} → {backup}")
                except Exception as exc:  # noqa: BLE001
                    print(f"[Safety] WARNING — could not back up {src!r}: {exc}")

    def _show_confirmation_dialog(self, macro: Macro) -> bool:
        """Show a modal dialog summarising high-risk actions.

        Returns True if the user clicks "Run Anyway", False otherwise.
        """
        if self._root is None:
            raise RuntimeError(
                "SafetyLayer has no root_window — cannot show confirmation dialog"
            )

        preview = self.preview_actions(macro)

        # Build a custom dialog
        dialog = tk.Toplevel(self._root)
        dialog.title("⚠  High-Risk Macro — Confirm")
        dialog.resizable(False, False)
        dialog.grab_set()           # modal
        dialog.lift()
        dialog.attributes("-topmost", True)

        # Icon + header
        header_frame = tk.Frame(dialog, bg="#2b2b2b")
        header_frame.pack(fill="x", padx=0, pady=0)

        tk.Label(
            header_frame,
            text="⚠  HIGH-RISK MACRO",
            fg="#ff6b6b", bg="#2b2b2b",
            font=("Segoe UI", 13, "bold"),
            padx=16, pady=10,
        ).pack(side="left")

        tk.Label(
            header_frame,
            text=f"Macro: {macro.name}",
            fg="#cccccc", bg="#2b2b2b",
            font=("Segoe UI", 10),
            padx=16,
        ).pack(side="left")

        # Warning text
        warn_text = (
            "This macro contains file-system actions (delete / move / copy).\n"
            "Target files will be backed up before execution.\n"
            "Review the action list below before proceeding."
        )
        tk.Label(
            dialog,
            text=warn_text,
            fg="#e0e0e0", bg="#1e1e1e",
            font=("Segoe UI", 9),
            justify="left",
            padx=16, pady=8,
        ).pack(fill="x")

        # Scrollable action list
        list_frame = tk.Frame(dialog, bg="#1e1e1e", padx=16, pady=4)
        list_frame.pack(fill="both", expand=True)

        txt = scrolledtext.ScrolledText(
            list_frame,
            height=12, width=72,
            bg="#252526", fg="#d4d4d4",
            font=("Consolas", 9),
            state="normal",
            wrap="word",
        )
        txt.insert("1.0", preview)
        txt.config(state="disabled")
        txt.pack(fill="both", expand=True)

        # Button row
        btn_frame = tk.Frame(dialog, bg="#1e1e1e", pady=10)
        btn_frame.pack(fill="x")

        confirmed = tk.BooleanVar(value=False)

        def _run() -> None:
            confirmed.set(True)
            dialog.destroy()

        def _cancel() -> None:
            confirmed.set(False)
            dialog.destroy()

        tk.Button(
            btn_frame, text="Cancel", command=_cancel,
            bg="#3c3c3c", fg="#cccccc",
            font=("Segoe UI", 10),
            relief="flat", padx=16, pady=6,
        ).pack(side="right", padx=(4, 16))

        tk.Button(
            btn_frame, text="⚠  Run Anyway", command=_run,
            bg="#c0392b", fg="white",
            font=("Segoe UI", 10, "bold"),
            relief="flat", padx=16, pady=6,
        ).pack(side="right", padx=4)

        dialog.protocol("WM_DELETE_WINDOW", _cancel)

        # Centre dialog over root window
        self._root.update_idletasks()
        rx = self._root.winfo_x() + self._root.winfo_width() // 2
        ry = self._root.winfo_y() + self._root.winfo_height() // 2
        dialog.update_idletasks()
        dw, dh = dialog.winfo_width(), dialog.winfo_height()
        dialog.geometry(f"+{rx - dw // 2}+{ry - dh // 2}")

        self._root.wait_window(dialog)
        return confirmed.get()

    # ── preview ────────────────────────────────────

    def preview_actions(self, macro: Macro) -> str:
        """Return a human-readable multi-line action preview string."""
        lines: list[str] = [
            f"Macro : {macro.name}",
            f"Hotkey: {macro.hotkey or '(none)'}",
            f"Risk  : {macro.risk_level.value.upper()}",
            f"Steps : {macro.action_count}",
            "",
        ]
        for i, action in enumerate(macro.actions, 1):
            risk_tag = ""
            if action.risk_level == RiskLevel.HIGH:
                risk_tag = " [HIGH RISK]"
            elif action.risk_level == RiskLevel.MEDIUM:
                risk_tag = " [medium]"
            lines.append(f"  {i:>3}. {action.description}{risk_tag}")
        return "\n".join(lines)
