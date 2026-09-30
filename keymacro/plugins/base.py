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
