"""
keymacro/main.py
─────────────────
Entry point — wires all modules together and launches the GUI.

Usage
─────
    python -m keymacro.main
    python keymacro/main.py
"""

from __future__ import annotations

import sys

# ── dependency check ───────────────────────────
def _check_deps() -> None:
    missing = []
    for pkg in ("pynput", "pyautogui"):
        try:
            __import__(pkg)
        except ModuleNotFoundError:
            missing.append(pkg)
    if missing:
        print(
            f"[KeyMacro] Missing required packages: {', '.join(missing)}\n"
            f"Install them with:  pip install {' '.join(missing)}",
            file=sys.stderr,
        )
        sys.exit(1)

_check_deps()

# ── imports (after dep check) ──────────────────
from keymacro.engine.replay         import ReplayEngine
from keymacro.gui.app               import KeyMacroApp
from keymacro.hotkey.listener       import HotkeyListener
from keymacro.launcher.app_scanner  import AppScanner
from keymacro.plugins.manager       import PluginManager
from keymacro.recorder.recorder     import Recorder
from keymacro.safety.safety_layer   import SafetyLayer
from keymacro.storage.macro_store   import MacroStore


def main() -> None:
    # Initialise services
    store    = MacroStore()          # %APPDATA%\KeyMacro\macros\
    recorder = Recorder()
    engine   = ReplayEngine()
    safety   = SafetyLayer()         # root_window set by KeyMacroApp after init
    hotkeys  = HotkeyListener()
    plugins  = PluginManager.get_instance()
    scanner  = AppScanner()
    hotkeys.start()

    # Launch GUI (blocks until window is closed)
    app = KeyMacroApp(
        store=store,
        recorder=recorder,
        engine=engine,
        safety=safety,
        hotkey_listener=hotkeys,
        plugin_manager=plugins,
        app_scanner=scanner,
    )
    app.mainloop()

    # Cleanup
    hotkeys.stop()


if __name__ == "__main__":
    main()
