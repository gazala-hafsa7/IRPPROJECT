"""
keymacro/plugins/builtin/media.py
─────────────────────────────────
Media Controls plugin — global play/pause, next, previous, and stop.
Works with Spotify, YouTube, VLC, Apple Music, Groove, etc.
"""

from __future__ import annotations

import ctypes
import sys
from typing import Any

from keymacro.plugins.base import BasePlugin, PluginActionSpec

VK_MEDIA_NEXT_TRACK = 0xB0
VK_MEDIA_PREV_TRACK = 0xB1
VK_MEDIA_STOP       = 0xB2
VK_MEDIA_PLAY_PAUSE = 0xB3


def _press_vk(vk_code: int) -> None:
    if sys.platform == "win32":
        ctypes.windll.user32.keybd_event(vk_code, 0, 0, 0)
        ctypes.windll.user32.keybd_event(vk_code, 0, 2, 0)


class MediaPlugin(BasePlugin):
    plugin_id = "media"
    name = "Media Controls"
    description = "Control music and video playback (Spotify, YouTube, VLC, etc.)."
    target_apps = ["Spotify.exe", "vlc.exe", "chrome.exe", "msedge.exe"]

    def get_actions(self) -> dict[str, PluginActionSpec]:
        return {
            "play_pause": PluginActionSpec(
                action_id="play_pause",
                name="Play / Pause",
                description="Toggle playback on current media player.",
                example="plugin: media.play_pause",
            ),
            "next": PluginActionSpec(
                action_id="next",
                name="Next Track",
                description="Skip to the next song/track.",
                example="plugin: media.next",
            ),
            "prev": PluginActionSpec(
                action_id="prev",
                name="Previous Track",
                description="Go back to the previous track.",
                example="plugin: media.prev",
            ),
            "stop": PluginActionSpec(
                action_id="stop",
                name="Stop",
                description="Stop media playback.",
                example="plugin: media.stop",
            ),
        }

    def execute(self, action_id: str, params: dict[str, Any]) -> Any:
        if action_id == "play_pause":
            _press_vk(VK_MEDIA_PLAY_PAUSE)
            return "Sent media play/pause"

        if action_id == "next":
            _press_vk(VK_MEDIA_NEXT_TRACK)
            return "Sent media next track"

        if action_id == "prev":
            _press_vk(VK_MEDIA_PREV_TRACK)
            return "Sent media previous track"

        if action_id == "stop":
            _press_vk(VK_MEDIA_STOP)
            return "Sent media stop"

        raise ValueError(f"Unknown media action: '{action_id}'")
