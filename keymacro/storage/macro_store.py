"""
keymacro/storage/macro_store.py
────────────────────────────────
Persistent JSON storage for Macro objects.

Storage layout
--------------
%APPDATA%\\KeyMacro\\macros\\<macro_id>.json   ← one file per macro

Each file is a pretty-printed JSON dump of Macro.to_dict().

Atomic writes
-------------
All saves use a write-to-temp-then-rename pattern so a crash mid-write never
produces a truncated / corrupt file.

Public API
----------
MacroStore(macros_dir: Path | None)
    .save(macro)                → None
    .load(macro_id)             → Macro
    .list_all()                 → list[Macro]  (sorted by name, case-insensitive)
    .delete(macro_id)           → None
    .exists(macro_id)           → bool
    .macros_dir                 → Path  (for display in GUI)

Exceptions
----------
MacroNotFoundError  – load() / delete() on a missing id
MacroStoreError     – base class for all storage errors
CorruptMacroError   – JSON file exists but cannot be deserialised
"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Iterator

from keymacro.models.action import Macro


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────

class MacroStoreError(Exception):
    """Base exception for all MacroStore failures."""


class MacroNotFoundError(MacroStoreError):
    """Raised when a macro_id does not correspond to a saved file."""

    def __init__(self, macro_id: str) -> None:
        super().__init__(f"Macro not found: {macro_id!r}")
        self.macro_id = macro_id


class CorruptMacroError(MacroStoreError):
    """Raised when a JSON file exists but cannot be deserialised."""

    def __init__(self, path: Path, reason: str) -> None:
        super().__init__(f"Corrupt macro file {path}: {reason}")
        self.path = path


# ──────────────────────────────────────────────
# MacroStore
# ──────────────────────────────────────────────

class MacroStore:
    """Manages reading and writing Macro JSON files.

    Parameters
    ----------
    macros_dir:
        Directory that holds ``<macro_id>.json`` files.
        Defaults to ``%APPDATA%\\KeyMacro\\macros``.
        The directory is created automatically if it does not exist.
    """

    _FILE_SUFFIX = ".json"
    _INDENT      = 2          # pretty-print indent

    def __init__(self, macros_dir: Path | None = None) -> None:
        if macros_dir is None:
            appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
            macros_dir = appdata / "KeyMacro" / "macros"
        self._dir = Path(macros_dir)
        self._dir.mkdir(parents=True, exist_ok=True)

    # ── public properties ──────────────────────────

    @property
    def macros_dir(self) -> Path:
        return self._dir

    # ── CRUD ───────────────────────────────────────

    def save(self, macro: Macro) -> None:
        """Persist *macro* to disk (create or overwrite).

        Uses atomic write: JSON written to a temp file in the same directory,
        then renamed over the target path — safe against mid-write crashes.
        Also calls ``macro.touch()`` to update ``modified_at``.
        """
        macro.touch()
        target = self._path_for(macro.macro_id)
        payload = json.dumps(macro.to_dict(), indent=self._INDENT, ensure_ascii=False)

        # Write to a sibling temp file, then rename atomically
        fd, tmp_path_str = tempfile.mkstemp(
            suffix=".tmp", prefix=".km_", dir=self._dir
        )
        tmp_path = Path(tmp_path_str)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                fh.write(payload)
            # On Windows, replace() handles the case where target already exists
            tmp_path.replace(target)
        except Exception:
            # Clean up temp file if anything went wrong
            try:
                tmp_path.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    def load(self, macro_id: str) -> Macro:
        """Load and return a single Macro by its id.

        Raises
        ------
        MacroNotFoundError  if no file exists for *macro_id*
        CorruptMacroError   if the file cannot be parsed / deserialised
        """
        path = self._path_for(macro_id)
        if not path.exists():
            raise MacroNotFoundError(macro_id)
        return self._load_path(path)

    def list_all(self) -> list[Macro]:
        """Return all saved macros, sorted by name (case-insensitive).

        Files that fail to parse are skipped with a printed warning rather than
        crashing the whole list — the user can still access working macros.
        """
        macros: list[Macro] = []
        for path in self._iter_json_files():
            try:
                macros.append(self._load_path(path))
            except CorruptMacroError as exc:
                print(f"[MacroStore] WARNING — skipping corrupt file: {exc}")
        macros.sort(key=lambda m: m.name.lower())
        return macros

    def delete(self, macro_id: str) -> None:
        """Delete the JSON file for *macro_id*.

        Raises
        ------
        MacroNotFoundError  if no file exists for *macro_id*
        """
        path = self._path_for(macro_id)
        if not path.exists():
            raise MacroNotFoundError(macro_id)
        path.unlink()

    def exists(self, macro_id: str) -> bool:
        """Return True if a saved file exists for *macro_id*."""
        return self._path_for(macro_id).exists()

    # ── internals ──────────────────────────────────

    def _path_for(self, macro_id: str) -> Path:
        # Sanitise to prevent path traversal: keep only safe chars
        safe_id = "".join(c for c in macro_id if c.isalnum() or c in "-_")
        if not safe_id:
            raise MacroStoreError(f"Invalid macro_id: {macro_id!r}")
        return self._dir / (safe_id + self._FILE_SUFFIX)

    def _load_path(self, path: Path) -> Macro:
        try:
            raw = path.read_text(encoding="utf-8")
            data = json.loads(raw)
            return Macro.from_dict(data)
        except json.JSONDecodeError as exc:
            raise CorruptMacroError(path, f"JSON parse error: {exc}") from exc
        except (KeyError, ValueError, TypeError) as exc:
            raise CorruptMacroError(path, f"Schema error: {exc}") from exc

    def _iter_json_files(self) -> Iterator[Path]:
        return self._dir.glob(f"*{self._FILE_SUFFIX}")
