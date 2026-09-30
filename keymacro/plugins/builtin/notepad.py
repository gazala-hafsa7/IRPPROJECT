"""
keymacro/plugins/builtin/notepad.py
───────────────────────────────────
Notepad plugin — create quick notes, open files, and insert timestamps.
"""

from __future__ import annotations

import os
import subprocess
import tempfile
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pyautogui

from keymacro.plugins.base import BasePlugin, PluginActionSpec


class NotepadPlugin(BasePlugin):
    plugin_id = "notepad"
    name = "Notepad & Notes"
    description = "Quickly create notes, open text files, or write timestamps."
    target_apps = ["notepad.exe"]

    def get_actions(self) -> dict[str, PluginActionSpec]:
        return {
            "new_note": PluginActionSpec(
                action_id="new_note",
                name="New Note",
                description="Open Notepad with optional initial text.",
                params_schema={"content": "Text content to initialize the note with"},
                example='plugin: notepad.new_note content="Meeting notes for today"',
            ),
            "open_file": PluginActionSpec(
                action_id="open_file",
                name="Open File",
                description="Open a specified file in Notepad.",
                params_schema={"path": "Path to the text file"},
                example='plugin: notepad.open_file path="C:\\notes.txt"',
            ),
            "insert_timestamp": PluginActionSpec(
                action_id="insert_timestamp",
                name="Insert Timestamp",
                description="Types the current date and time at cursor.",
                params_schema={"format": "Date format string (default: %Y-%m-%d %H:%M:%S)"},
                example="plugin: notepad.insert_timestamp",
            ),
        }

    def execute(self, action_id: str, params: dict[str, Any]) -> Any:
        if action_id == "new_note":
            content = params.get("content") or params.get("arg", "")
            if content:
                fd, tmp_path = tempfile.mkstemp(suffix=".txt", prefix="note_")
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                subprocess.Popen(["notepad.exe", tmp_path])
            else:
                subprocess.Popen(["notepad.exe"])
            return "Launched Notepad"

        if action_id == "open_file":
            path = params.get("path") or params.get("arg", "")
            if not path or not Path(path).exists():
                raise FileNotFoundError(f"File not found: {path}")
            subprocess.Popen(["notepad.exe", path])
            return f"Opened file: {path}"

        if action_id == "insert_timestamp":
            fmt = params.get("format", "%Y-%m-%d %H:%M:%S")
            ts_str = datetime.now().strftime(fmt)
            pyautogui.typewrite(ts_str, interval=0.01)
            return f"Typed timestamp: {ts_str}"

        raise ValueError(f"Unknown notepad action: '{action_id}'")
