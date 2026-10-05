"""
keymacro/plugins/base.py
────────────────────────
Base interfaces and contracts for KeyMacro plugins.

Every plugin subclasses BasePlugin and registers actions that can be triggered
from macros (e.g. `plugin: browser.open_url url=https://example.com`) or from the
App Launcher UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PluginActionSpec:
    """Metadata describing a specific callable action within a plugin."""

    action_id: str
    name: str
    description: str
    params_schema: dict[str, str] = field(default_factory=dict)
    example: str = ""


class BasePlugin(ABC):
    """Abstract base class for all KeyMacro plugins."""

    plugin_id: str = ""
    name: str = ""
    description: str = ""
    target_apps: list[str] = []

    def is_installed(self) -> bool:
        """Return True if the target application is present on this system.

        Plugins for general system utilities can return True unconditionally.
        """
        return True

    @abstractmethod
    def get_actions(self) -> dict[str, PluginActionSpec]:
        """Return a mapping of action_id -> PluginActionSpec."""
        raise NotImplementedError

    @abstractmethod
    def execute(self, action_id: str, params: dict[str, Any]) -> Any:
        """Execute the specified action with parameters."""
        raise NotImplementedError


class AppPlugin(BasePlugin):
    """Plugin representing an entire desktop application profile connected to KeyMacro.
    
    Enables connecting a whole application (e.g. Chrome, Notepad, Spotify, VS Code) as a plugin profile,
    grouping and executing macros specific to that app context.
    """

    def __init__(
        self,
        plugin_id: str,
        name: str,
        target_app: str,
        description: str = "",
        category: str = "App Plugin",
    ) -> None:
        self.plugin_id = plugin_id.lower().replace(" ", "_")
        self.name = name
        self.target_app = target_app
        self.target_apps = [target_app] if target_app else []
        self.description = description or f"Connected application profile for {name} ({target_app})"
        self.category = category

    def is_installed(self) -> bool:
        return True

    def get_actions(self) -> dict[str, PluginActionSpec]:
        return {
            "launch": PluginActionSpec(
                action_id="launch",
                name=f"Launch {self.name}",
                description=f"Launch target application ({self.target_app})",
                params_schema={},
                example=f"launch: {self.target_app}",
            )
        }

    def execute(self, action_id: str, params: dict[str, Any]) -> Any:
        if action_id == "launch":
            import os
            import subprocess
            import sys
            if sys.platform == "win32":
                os.startfile(self.target_app)
            else:
                subprocess.Popen([self.target_app])
            return f"Launched {self.name}"
        raise ValueError(f"Unknown action '{action_id}' for app plugin '{self.plugin_id}'")

