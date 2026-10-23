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

# Look for virtual environment in either 'venv' or '.venv'
venv_python = None
for candidate in [
    ROOT / "venv" / "Scripts" / "python.exe",
    ROOT / ".venv" / "Scripts" / "python.exe",
    ROOT / "venv" / "bin" / "python",
    ROOT / ".venv" / "bin" / "python",
]:
    if candidate.exists():
        venv_python = candidate
        break

# Verify dependencies; auto-delegate to virtual environment if missing
try:
    import PySide6  # noqa: F401
    import speech_recognition  # noqa: F401
    import sounddevice  # noqa: F401
except ModuleNotFoundError:
    if venv_python and Path(sys.executable).resolve() != venv_python.resolve():
        sys.exit(subprocess.call([str(venv_python), str(Path(__file__).resolve())] + sys.argv[1:]))
    try:
        import PySide6  # noqa: F401
    except ModuleNotFoundError:
        print("[KeyMacro] PySide6 not found. Please install requirements: pip install -r requirements.txt", file=sys.stderr)
        sys.exit(1)

from gui_qt.app import KeyMacroQtApp


def main() -> None:
    app = KeyMacroQtApp()
    sys.exit(app.run())


if __name__ == "__main__":
    main()
