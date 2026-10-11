"""
run_qt.py
─────────
Root launcher for KeyMacro PySide6 GUI.

Usage:
    python run_qt.py
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# If PySide6 is not in current environment, auto-delegate to .venv
try:
    import PySide6  # noqa: F401
except ModuleNotFoundError:
    venv_python = ROOT / ".venv" / "Scripts" / "python.exe"
    if venv_python.exists():
        sys.exit(subprocess.call([str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:]))
    else:
        print("[KeyMacro] PySide6 not found. Please activate .venv: source .venv/Scripts/activate", file=sys.stderr)
        sys.exit(1)

from gui_qt.app import KeyMacroQtApp


def main() -> None:
    app = KeyMacroQtApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
