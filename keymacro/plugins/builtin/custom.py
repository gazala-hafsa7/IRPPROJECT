"""
keymacro/plugins/builtin/custom.py
───────────────────────────────────
Custom Automation Tasks plugin — allows user-defined custom tasks such as
opening spreadsheets/apps, typing current timestamps into log-in columns,
appending log entries, running scripts, and custom user-configured actions.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
import webbrowser
from datetime import datetime
from pathlib import Path
from typing import Any

import pyautogui

from keymacro.plugins.base import BasePlugin, PluginActionSpec


class CustomPlugin(BasePlugin):
    plugin_id = "custom"
    name = "Custom Tasks & Automation"
    description = "Create and run custom tasks: open spreadsheets, type timestamps into log-in columns, append files, and run custom scripts."
    target_apps = ["excel.exe", "chrome.exe", "msedge.exe", "notepad.exe", "code.exe"]

    def __init__(self) -> None:
        appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
        self._user_custom_file = appdata / "KeyMacro" / "user_custom_actions.json"
        self._user_actions: dict[str, dict[str, Any]] = self._load_user_custom_actions()

    def _load_user_custom_actions(self) -> dict[str, dict[str, Any]]:
        if self._user_custom_file.exists():
            try:
                return json.loads(self._user_custom_file.read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001
                print(f"[CustomPlugin] Failed to read user custom actions: {exc}")
        return {}

    def save_user_action(
        self,
        action_id: str,
        name: str,
        description: str,
        target: str,
        text_template: str,
        delay_sec: float = 1.5,
        suffix_key: str = "enter",
    ) -> None:
        """Save a new user-defined custom plug-in action."""
        aid = action_id.lower().replace(" ", "_").strip()
        self._user_actions[aid] = {
            "name": name,
            "description": description,
            "target": target,
            "text_template": text_template,
            "delay_sec": delay_sec,
            "suffix_key": suffix_key,
        }
        self._user_custom_file.parent.mkdir(parents=True, exist_ok=True)
        self._user_custom_file.write_text(json.dumps(self._user_actions, indent=2), encoding="utf-8")

    def get_actions(self) -> dict[str, PluginActionSpec]:
        actions = {
            "open_and_type": PluginActionSpec(
                action_id="open_and_type",
                name="Open File/Sheet & Type Text/Time",
                description="Open a spreadsheet, document, or URL, wait for it to focus, and type text or timestamp (e.g. into a log-in column).",
                params_schema={
                    "target": "Path to file, sheet, or URL (e.g. C:\\Docs\\Timesheet.xlsx)",
                    "text": "Text or pattern ({time}, {date}, {timestamp}) to type",
                    "delay": "Wait time before typing (e.g. 1.5s or 2s)",
                    "suffix": "Key to press after typing (enter, tab, none)",
                },
                example='plugin: custom.open_and_type target="C:\\Timesheet.xlsx" text="Log-in: {time}" delay=1.5s suffix=enter',
            ),
            "type_timestamp": PluginActionSpec(
                action_id="type_timestamp",
                name="Type Current Timestamp",
                description="Type the current date/time into the currently active window or sheet column.",
                params_schema={
                    "format": "Datetime format (default: %Y-%m-%d %H:%M:%S or %H:%M:%S)",
                    "prefix": "Optional text prefix (e.g. Log-in: )",
                    "suffix": "Key to press after typing (enter, tab, none)",
                },
                example='plugin: custom.type_timestamp format="%H:%M:%S" prefix="Log-in: " suffix=enter',
            ),
            "sheet_login": PluginActionSpec(
                action_id="sheet_login",
                name="Open Sheet & Log-in Time",
                description="Open a spreadsheet/log file and write current timestamp into log-in column.",
                params_schema={
                    "target": "Path to spreadsheet file or web sheet URL",
                    "column_label": "Optional column or note prefix (default: Log-in: )",
                    "delay": "Delay before typing (default: 2s)",
                },
                example='plugin: custom.sheet_login target="C:\\Work\\Log.xlsx" column_label="Log-in: "',
            ),
            "append_log": PluginActionSpec(
                action_id="append_log",
                name="Append Timestamped File Log",
                description="Append a timestamped log line directly to a file (txt, csv, log).",
                params_schema={
                    "file_path": "Path to log or csv file",
                    "message": "Message to record (default: User Log-in)",
                },
                example='plugin: custom.append_log file_path="C:\\Logs\\attendance.txt" message="Checked in"',
            ),
            "run_script": PluginActionSpec(
                action_id="run_script",
                name="Run Custom Script / Command",
                description="Execute a custom command or script in background.",
                params_schema={
                    "command": "Command line to execute (e.g. python script.py)",
                },
                example='plugin: custom.run_script command="python C:\\scripts\\task.py"',
            ),
        }

        # Dynamically expose user-configured custom actions
        for aid, data in self._user_actions.items():
            actions[aid] = PluginActionSpec(
                action_id=aid,
                name=data.get("name", aid.title()),
                description=data.get("description", "User-defined custom task"),
                params_schema={
                    "target": f"Optional override target (default: {data.get('target', '')})",
                    "text": f"Optional override text (default: {data.get('text_template', '{time}')})",
                },
                example=f"plugin: custom.{aid}",
            )

        return actions

    def execute(self, action_id: str, params: dict[str, Any]) -> Any:
        now = datetime.now()

        # Handle user-configured custom action if registered
        if action_id in self._user_actions:
            user_act = self._user_actions[action_id]
            target = params.get("target") or user_act.get("target", "")
            text_tmpl = params.get("text") or user_act.get("text_template", "{time}")
            delay_sec = float(user_act.get("delay_sec", 1.5))
            suffix_key = user_act.get("suffix_key", "enter")

            return self._exec_open_and_type(target=target, text=text_tmpl, delay=f"{delay_sec}s", suffix=suffix_key)

        if action_id == "open_and_type":
            target = params.get("target") or params.get("arg", "")
            text = params.get("text", "{time}")
            delay = params.get("delay", "1.5s")
            suffix = params.get("suffix", "enter")
            return self._exec_open_and_type(target, text, delay, suffix)

        if action_id == "type_timestamp":
            fmt = params.get("format", "%Y-%m-%d %H:%M:%S")
            prefix = params.get("prefix", "")
            suffix = params.get("suffix", "enter")
            ts_str = now.strftime(fmt)
            out_str = f"{prefix}{ts_str}"
            pyautogui.write(out_str, interval=0.02)
            if suffix.lower() in ("enter", "\n"):
                pyautogui.press("enter")
            elif suffix.lower() in ("tab", "\t"):
                pyautogui.press("tab")
            return f"Typed timestamp: '{out_str}'"

        if action_id == "sheet_login":
            target = params.get("target") or params.get("arg", "")
            label = params.get("column_label", "Log-in: ")
            delay = params.get("delay", "2s")
            return self._exec_open_and_type(target=target, text=f"{label}{{time}}", delay=delay, suffix="enter")

        if action_id == "append_log":
            file_path = params.get("file_path") or params.get("path", "")
            msg = params.get("message", "User Log-in")
            if not file_path:
                raise ValueError("file_path parameter is required for append_log")
            p = Path(file_path)
            p.parent.mkdir(parents=True, exist_ok=True)
            ts = now.strftime("%Y-%m-%d %H:%M:%S")
            line = f"[{ts}] {msg}\n"
            with p.open("a", encoding="utf-8") as f:
                f.write(line)
            return f"Appended log to {file_path}: {line.strip()}"

        if action_id == "run_script":
            cmd = params.get("command") or params.get("arg", "")
            if not cmd:
                raise ValueError("command parameter is required for run_script")
            proc = subprocess.Popen(cmd, shell=True)
            return f"Executed command (PID {proc.pid}): {cmd}"

        raise ValueError(f"Unknown custom action: '{action_id}'")

    def _exec_open_and_type(self, target: str, text: str, delay: str, suffix: str) -> str:
        now = datetime.now()
        # Parse delay
        d_val = 1.5
        d_str = str(delay).lower().replace("s", "").strip()
        try:
            d_val = float(d_str)
        except ValueError:
            pass

        opened_msg = "No target application specified"
        if target:
            if target.startswith(("http://", "https://")):
                webbrowser.open(target)
                opened_msg = f"Opened URL '{target}'"
            elif os.path.exists(target) or any(target.lower().endswith(ext) for ext in (".xlsx", ".xls", ".csv", ".txt", ".ods", ".docx")):
                os.startfile(target)
                opened_msg = f"Opened file '{target}'"
            else:
                subprocess.Popen(target, shell=True)
                opened_msg = f"Launched process '{target}'"

            # Wait for app/sheet to load and focus
            time.sleep(d_val)

        # Replace timestamp placeholders in text
        formatted_text = (
            text.replace("{timestamp}", now.strftime("%Y-%m-%d %H:%M:%S"))
            .replace("{time}", now.strftime("%H:%M:%S"))
            .replace("{date}", now.strftime("%Y-%m-%d"))
            .replace("{datetime}", now.strftime("%Y-%m-%d %H:%M:%S"))
        )

        pyautogui.write(formatted_text, interval=0.02)

        suf = str(suffix).lower().strip()
        if suf in ("enter", "\n"):
            pyautogui.press("enter")
        elif suf in ("tab", "\t"):
            pyautogui.press("tab")

        return f"{opened_msg} and typed '{formatted_text}'"
