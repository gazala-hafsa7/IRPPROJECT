"""
keymacro/plugins/builtin/system.py
──────────────────────────────────
Windows System Controls plugin — volume, lock screen, screenshot, system tools.
"""

from __future__ import annotations

import ctypes
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import pyautogui

from keymacro.plugins.base import BasePlugin, PluginActionSpec

# Windows Virtual Key codes for media & volume
VK_VOLUME_MUTE = 0xAD
VK_VOLUME_DOWN = 0xAE
VK_VOLUME_UP   = 0xAF


def _press_vk(vk_code: int) -> None:
    """Send a Windows virtual key down + up event."""
    if sys.platform == "win32":
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)  # KEYEVENTF_KEYUP = 2


class SystemPlugin(BasePlugin):
    plugin_id = "system"
    name = "System Controls"
    description = "Control system audio, lock screen, capture screenshots, and launch settings."
    target_apps = ["explorer.exe", "taskmgr.exe", "SystemSettings.exe"]

    def get_actions(self) -> dict[str, PluginActionSpec]:
        return {
            "volume_mute": PluginActionSpec(
                action_id="volume_mute",
                name="Mute / Unmute Volume",
                description="Toggle system audio mute.",
                example="plugin: system.volume_mute",
            ),
            "volume_up": PluginActionSpec(
                action_id="volume_up",
                name="Volume Up",
                description="Increase master audio volume.",
                params_schema={"steps": "Number of volume steps to increase (default: 2)"},
                example="plugin: system.volume_up steps=4",
            ),
            "volume_down": PluginActionSpec(
                action_id="volume_down",
                name="Volume Down",
                description="Decrease master audio volume.",
                params_schema={"steps": "Number of volume steps to decrease (default: 2)"},
                example="plugin: system.volume_down steps=4",
            ),
            "lock": PluginActionSpec(
                action_id="lock",
                name="Lock Workstation",
                description="Lock Windows immediately.",
                example="plugin: system.lock",
            ),
            "screenshot": PluginActionSpec(
                action_id="screenshot",
                name="Take Screenshot",
                description="Capture screen and save image to Pictures/Screenshots.",
                params_schema={"path": "Optional custom file path to save screenshot"},
                example="plugin: system.screenshot",
            ),
            "settings": PluginActionSpec(
                action_id="settings",
                name="Open Settings",
                description="Open Windows Settings.",
                example="plugin: system.settings",
            ),
            "task_manager": PluginActionSpec(
                action_id="task_manager",
                name="Open Task Manager",
                description="Launch Windows Task Manager.",
                example="plugin: system.task_manager",
            ),
        }

    def execute(self, action_id: str, params: dict[str, Any]) -> Any:
        if action_id == "volume_mute":
            _press_vk(VK_VOLUME_MUTE)
            return "Toggled volume mute"

        if action_id == "volume_up":
            steps = int(params.get("steps", 2))
            for _ in range(max(1, steps)):
                _press_vk(VK_VOLUME_UP)
            return f"Increased volume by {steps} steps"

        if action_id == "volume_down":
            steps = int(params.get("steps", 2))
            for _ in range(max(1, steps)):
                _press_vk(VK_VOLUME_DOWN)
            return f"Decreased volume by {steps} steps"

        if action_id == "lock":
            if sys.platform == "win32":
                ctypes.windll.user32.LockWorkStation()
                return "Workstation locked"
            return "Lock is only supported on Windows"

        if action_id == "screenshot":
            save_path = params.get("path")
            if not save_path:
                pics_dir = Path.home() / "Pictures" / "Screenshots"
                pics_dir.mkdir(parents=True, exist_ok=True)
                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                save_path = str(pics_dir / f"KeyMacro_Screenshot_{ts}.png")
            img = pyautogui.screenshot()
            img.save(save_path)
            return f"Screenshot saved to: {save_path}"

        if action_id == "settings":
            os.startfile("ms-settings:")
            return "Opened Windows Settings"

        if action_id == "task_manager":
            os.startfile("taskmgr.exe")
            return "Opened Task Manager"

        raise ValueError(f"Unknown system action: '{action_id}'")
