# KeyMacro Plugin System Guide: Connecting Installed Applications

KeyMacro features a modular, drop-in plugin system that allows you to easily connect to any application installed on your Windows system and control it using concise macro commands.

---

## 1. Where Plugins Live

KeyMacro loads plugins from two locations:

1. **Built-in Plugins**: Located in `keymacro/plugins/builtin/` (shipped with KeyMacro).
2. **User Plugins**: Located in `%APPDATA%\KeyMacro\plugins\`. Any `.py` file placed here is automatically discovered and loaded when KeyMacro starts (or when clicking **Reload Plugins** in the App Launcher & Plugin Hub).

---

## 2. How the Plugin Architecture Works

Every plugin inherits from `BasePlugin` in `keymacro.plugins.base`:

```python
from keymacro.plugins.base import BasePlugin, PluginActionSpec
from typing import Any

class MyCustomPlugin(BasePlugin):
    plugin_id   = "myapp"              # Unique identifier used in macros (e.g. plugin: myapp.action_name)
    name        = "My Installed App"   # Display name shown in GUI
    description = "Control and automate My Installed App."
    target_apps = ["myapp.exe"]        # Target process or executable name

    def is_installed(self) -> bool:
        """Optional: check if the app is installed on the machine."""
        import shutil
        return shutil.which("myapp.exe") is not None

    def get_actions(self) -> dict[str, PluginActionSpec]:
        """Declare callable actions with parameter descriptions and syntax examples."""
        return {
            "do_something": PluginActionSpec(
                action_id="do_something",
                name="Do Something",
                description="Executes a specific operation in the app.",
                params_schema={"param1": "Description of param1"},
                example="plugin: myapp.do_something param1=hello",
            )
        }

    def execute(self, action_id: str, params: dict[str, Any]) -> Any:
        """Implement the action logic."""
        if action_id == "do_something":
            val = params.get("param1", "default")
            # Run code, launch app, send hotkeys, call CLI/API, etc.
            return f"Executed with {val}"
        raise ValueError(f"Unknown action: {action_id}")
```

---

## 3. Step-by-Step: Connecting to an Installed App

Here are the 3 common ways to connect to an installed application:

### Method A: Via CLI or App Arguments (e.g., VS Code, Git, VLC)

Many installed apps accept command-line flags, file paths, or commands.

```python
import subprocess
from keymacro.plugins.base import BasePlugin, PluginActionSpec

class VSCodePlugin(BasePlugin):
    plugin_id = "vscode"
    name = "Visual Studio Code"
    description = "Open folders, files, or new workspaces in VS Code."
    target_apps = ["Code.exe"]

    def get_actions(self) -> dict[str, PluginActionSpec]:
        return {
            "open_folder": PluginActionSpec(
                action_id="open_folder",
                name="Open Folder in VS Code",
                description="Opens a directory in VS Code.",
                params_schema={"path": "Path to workspace or directory"},
                example='plugin: vscode.open_folder path="C:\\Projects\\my_app"',
            ),
            "new_window": PluginActionSpec(
                action_id="new_window",
                name="New VS Code Window",
                description="Opens a fresh VS Code window.",
                example="plugin: vscode.new_window",
            ),
        }

    def execute(self, action_id: str, params: dict) -> str:
        if action_id == "open_folder":
            folder = params.get("path", ".")
            subprocess.Popen(["code", folder])
            return f"Opened folder: {folder}"
        if action_id == "new_window":
            subprocess.Popen(["code", "-n"])
            return "Opened new VS Code window"
        raise ValueError(f"Unknown action: {action_id}")
```

### Method B: Via URL Schemes / Deep Links (e.g., Spotify, Discord, Slack, Zoom)

Many Windows apps register custom URI schemes (e.g. `spotify:`, `discord:`, `slack:`, `zoommtg:`):

```python
import os
from keymacro.plugins.base import BasePlugin, PluginActionSpec

class SpotifyPlugin(BasePlugin):
    plugin_id = "spotify"
    name = "Spotify"
    description = "Control Spotify playback and jump to artists/playlists."
    target_apps = ["Spotify.exe"]

    def get_actions(self) -> dict[str, PluginActionSpec]:
        return {
            "play_uri": PluginActionSpec(
                action_id="play_uri",
                name="Play Spotify URI",
                description="Play an album, artist, or track by Spotify URI.",
                params_schema={"uri": "Spotify URI (e.g. spotify:playlist:...)"},
                example="plugin: spotify.play_uri uri=spotify:track:...",
            ),
            "search": PluginActionSpec(
                action_id="search",
                name="Search in Spotify",
                description="Open Spotify search for an artist or song.",
                params_schema={"query": "Search query"},
                example='plugin: spotify.search query="Hans Zimmer"',
            ),
        }

    def execute(self, action_id: str, params: dict) -> str:
        if action_id == "play_uri":
            uri = params.get("uri", "")
            os.startfile(uri)
            return f"Opened Spotify URI: {uri}"
        if action_id == "search":
            q = params.get("query", "")
            os.startfile(f"spotify:search:{q}")
            return f"Searched Spotify for: {q}"
        raise ValueError(f"Unknown action: {action_id}")
```

### Method C: Via Keyboard Shortcuts / Window Focus (e.g., Discord Mute, OBS Stream)

```python
import pyautogui
from keymacro.plugins.base import BasePlugin, PluginActionSpec

class OBSPlugin(BasePlugin):
    plugin_id = "obs"
    name = "OBS Studio"
    description = "Control OBS recordings and stream status."
    target_apps = ["obs64.exe"]

    def get_actions(self) -> dict[str, PluginActionSpec]:
        return {
            "toggle_recording": PluginActionSpec(
                action_id="toggle_recording",
                name="Toggle Recording",
                description="Send the hotkey to start/stop OBS recording.",
                example="plugin: obs.toggle_recording",
            ),
        }

    def execute(self, action_id: str, params: dict) -> str:
        if action_id == "toggle_recording":
            # Sends Ctrl+F9 (configured as OBS recording hotkey)
            pyautogui.hotkey("ctrl", "f9")
            return "Toggled OBS recording"
        raise ValueError(f"Unknown action: {action_id}")
```

---

## 4. How to Use Plugins in Concise Macros

Once a plugin is saved in `%APPDATA%\KeyMacro\plugins\`:

1. Open KeyMacro.
2. In the **Macro Sequence Editor**, simply write:
   ```
   launch: spotify.exe
   wait: 1s
   plugin: media.play_pause
   plugin: system.volume_up steps=4
   ```
3. Or in the **🚀 App Launcher & Plugin Hub**, navigate to the **Plugins** tab to preview all available plugins, click **Test Action**, or insert them directly into any macro.
