"""
gui_qt/run.py
─────────────
Standalone runner to launch the new PySide6 GUI.

Usage:
    python -m gui_qt.run
    python gui_qt/run.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

# Ensure project root is in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Self-healing launcher: If PySide6 is not found in the current environment,
# automatically delegate to the project's .venv virtual environment
try:
    import PySide6  # noqa: F401
except ModuleNotFoundError:
    venv_python = PROJECT_ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        result = subprocess.call([str(venv_python), "-m", "gui_qt.run"] + sys.argv[1:])
        sys.exit(result)
    else:
        print("[KeyMacro] Error: PySide6 is not installed.", file=sys.stderr)
        print("Please activate your virtual environment: source .venv/Scripts/activate", file=sys.stderr)
        sys.exit(1)

from gui_qt.app import KeyMacroQtApp


def main() -> None:
    app = KeyMacroQtApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
