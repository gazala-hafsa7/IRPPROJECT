"""
keymacro/plugins/manager.py
───────────────────────────
Plugin Manager — discovers, loads, and executes KeyMacro plugins.

Loads plugins from two places:
1. Built-in plugins in `keymacro.plugins.builtin`
2. User-created plugins in `%APPDATA%\\KeyMacro\\plugins\\*.py`
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import os
import sys
from pathlib import Path
from typing import Any

from keymacro.plugins.base import BasePlugin, PluginActionSpec


class PluginManager:
    """Manages plugin discovery, lifecycle, and action dispatch."""

    _instance: PluginManager | None = None

    def __init__(self, user_plugins_dir: Path | None = None) -> None:
        if user_plugins_dir is None:
            appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            user_plugins_dir = appdata / "KeyMacro" / "plugins"
        self._user_dir = Path(user_plugins_dir)
        self._user_dir.mkdir(parents=True, exist_ok=True)
        self._plugins: dict[str, BasePlugin] = {}
        self.load_all()

    @classmethod
    def get_instance(cls) -> PluginManager:
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def user_plugins_dir(self) -> Path:
        return self._user_dir

    def register(self, plugin: BasePlugin) -> None:
        """Register a plugin instance."""
        if not plugin.plugin_id:
            raise ValueError(f"Plugin {plugin} has no plugin_id")
        self._plugins[plugin.plugin_id] = plugin

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[BasePlugin]:
        return list(self._plugins.values())

    def get_all_actions(self) -> list[tuple[BasePlugin, PluginActionSpec]]:
        """Return a flattened list of (plugin, action_spec) pairs."""
        res: list[tuple[BasePlugin, PluginActionSpec]] = []
        for plugin in self.list_plugins():
            for spec in plugin.get_actions().values():
                res.append((plugin, spec))
        return res

    def execute(self, plugin_id: str, action_id: str, params: dict[str, Any]) -> Any:
        """Dispatch execution to the appropriate plugin."""
        plugin = self.get_plugin(plugin_id)
        if not plugin:
            raise KeyError(f"Plugin '{plugin_id}' is not loaded or registered")
        return plugin.execute(action_id, params)

    def load_all(self) -> None:
        """Discover and load both built-in and external user plugins."""
        self._plugins.clear()
        self._load_builtins()
        self._load_user_plugins()

    def _load_builtins(self) -> None:
        """Instantiate and register built-in plugins."""
        from keymacro.plugins.builtin.browser import BrowserPlugin
        from keymacro.plugins.builtin.media import MediaPlugin
        from keymacro.plugins.builtin.notepad import NotepadPlugin
        from keymacro.plugins.builtin.system import SystemPlugin

        for cls in (BrowserPlugin, SystemPlugin, MediaPlugin, NotepadPlugin):
            try:
                inst = cls()
                self.register(inst)
            except Exception as exc:  # noqa: BLE001
                print(f"[PluginManager] Error registering builtin {cls}: {exc}")

    def _load_user_plugins(self) -> None:
        """Scan `%APPDATA%\\KeyMacro\\plugins\\*.py` and import BasePlugin subclasses."""
        if not self._user_dir.exists():
            return

        for py_file in self._user_dir.glob("*.py"):
            if py_file.name.startswith(("_", ".")):
                continue
            module_name = f"keymacro_user_plugin_{py_file.stem}"
            try:
                spec = importlib.util.spec_from_file_location(module_name, py_file)
                if spec is None or spec.loader is None:
                    continue
                mod = importlib.util.module_from_spec(spec)
                sys.modules[module_name] = mod
                spec.loader.exec_module(mod)

                # Look for BasePlugin classes defined in the module
                for _, obj in inspect.getmembers(mod, inspect.isclass):
                    if issubclass(obj, BasePlugin) and obj is not BasePlugin:
                        inst = obj()
                        self.register(inst)
                        print(f"[PluginManager] Loaded user plugin: {inst.name} ({inst.plugin_id})")
            except Exception as exc:  # noqa: BLE001
                print(f"[PluginManager] Failed to load plugin from {py_file}: {exc}")
