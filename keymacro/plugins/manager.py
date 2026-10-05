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
import json
import os
import sys
from pathlib import Path
from typing import Any

from keymacro.plugins.base import AppPlugin, BasePlugin, PluginActionSpec


# Default app profiles connected out-of-the-box
_DEFAULT_APP_PLUGINS = [
    {"name": "Notepad", "target_app": "notepad.exe", "description": "Notes & Text Editor Application Profile"},
    {"name": "Google Chrome", "target_app": "chrome.exe", "description": "Web Browser Application Profile"},
    {"name": "Spotify", "target_app": "spotify.exe", "description": "Music & Audio Player Application Profile"},
    {"name": "VS Code", "target_app": "code.exe", "description": "Code Editor Application Profile"},
    {"name": "Calculator", "target_app": "calc.exe", "description": "Utility Calculator Application Profile"},
]


class PluginManager:
    """Manages plugin discovery, lifecycle, action dispatch, and connected App Plugins."""

    _instance: PluginManager | None = None

    def __init__(self, user_plugins_dir: Path | None = None) -> None:
        if user_plugins_dir is None:
            appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            user_plugins_dir = appdata / "KeyMacro" / "plugins"
        self._user_dir = Path(user_plugins_dir)
        self._user_dir.mkdir(parents=True, exist_ok=True)
        self._config_file = self._user_dir.parent / "connected_apps.json"
        self._plugins: dict[str, BasePlugin] = {}
        self._app_plugins: dict[str, AppPlugin] = {}
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
        if isinstance(plugin, AppPlugin):
            self._app_plugins[plugin.plugin_id] = plugin

    def get_plugin(self, plugin_id: str) -> BasePlugin | None:
        return self._plugins.get(plugin_id)

    def list_plugins(self) -> list[BasePlugin]:
        return list(self._plugins.values())

    def list_app_plugins(self) -> list[AppPlugin]:
        """Return list of registered connected App Plugins."""
        return list(self._app_plugins.values())

    def connect_app(self, name: str, target_app: str, description: str = "") -> AppPlugin:
        """Connect an entire application as an App Plugin profile."""
        pid = f"app_{target_app.lower().removesuffix('.exe').replace(' ', '_')}"
        app_plugin = AppPlugin(
            plugin_id=pid,
            name=name,
            target_app=target_app,
            description=description,
        )
        self.register(app_plugin)
        self.save_connected_apps()
        return app_plugin

    def disconnect_app(self, plugin_id: str) -> None:
        """Remove a connected App Plugin profile."""
        if plugin_id in self._plugins:
            del self._plugins[plugin_id]
        if plugin_id in self._app_plugins:
            del self._app_plugins[plugin_id]
        self.save_connected_apps()

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
        """Discover and load built-in plugins, connected App Plugins, and external user plugins."""
        self._plugins.clear()
        self._app_plugins.clear()
        self._load_builtins()
        self._load_connected_apps()
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

    def _load_connected_apps(self) -> None:
        """Scan system for all desktop applications and register them as App Plugins, plus custom connected apps."""
        try:
            from keymacro.launcher.app_scanner import AppScanner
            scanner = AppScanner()
            scanned_apps = scanner.scan()

            for app in scanned_apps:
                target_exe = os.path.basename(app.target) if app.target.lower().endswith(".exe") else app.target
                pid = f"app_{target_exe.lower().removesuffix('.exe').replace(' ', '_')}"
                if pid not in self._app_plugins:
                    inst = AppPlugin(
                        plugin_id=pid,
                        name=app.name,
                        target_app=target_exe,
                        description=f"Scanned Desktop Application Profile ({app.category})",
                    )
                    self.register(inst)
        except Exception as exc:  # noqa: BLE001
            print(f"[PluginManager] Error scanning desktop apps: {exc}")

        # Also load custom user-connected apps from JSON if present
        if self._config_file.exists():
            try:
                user_apps = json.loads(self._config_file.read_text(encoding="utf-8"))
                for item in user_apps:
                    name = item.get("name", "Application")
                    target_app = item.get("target_app", "")
                    desc = item.get("description", "")
                    if target_app:
                        pid = f"app_{target_app.lower().removesuffix('.exe').replace(' ', '_')}"
                        if pid not in self._app_plugins:
                            inst = AppPlugin(plugin_id=pid, name=name, target_app=target_app, description=desc)
                            self.register(inst)
            except Exception as exc:  # noqa: BLE001
                print(f"[PluginManager] Could not read connected_apps.json: {exc}")

    def save_connected_apps(self) -> None:
        """Save user-connected App Plugins to JSON."""
        data = [
            {
                "name": app.name,
                "target_app": app.target_app,
                "description": app.description,
            }
            for app in self._app_plugins.values()
        ]
        try:
            self._config_file.write_text(json.dumps(data, indent=2), encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            print(f"[PluginManager] Error saving connected_apps.json: {exc}")

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
                    if issubclass(obj, BasePlugin) and obj is not BasePlugin and obj is not AppPlugin:
                        inst = obj()
                        self.register(inst)
                        print(f"[PluginManager] Loaded user plugin: {inst.name} ({inst.plugin_id})")
            except Exception as exc:  # noqa: BLE001
                print(f"[PluginManager] Failed to load plugin from {py_file}: {exc}")

