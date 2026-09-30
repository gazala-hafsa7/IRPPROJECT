"""
keymacro/engine/replay.py
──────────────────────────
Replay engine — executes a Macro's Actions using pyautogui and pynput.

Key design points
-----------------
* Replay runs in a **daemon thread** so the GUI remains responsive.
* A ``threading.Event`` cancel flag lets any thread call ``stop()`` to
  abort mid-replay cleanly between actions.
* ``speed_factor`` scales every DELAY action (and inter-action pauses).
  < 1.0 = faster, > 1.0 = slower, 0 = no delays at all.
* ``dry_run=True`` prints each action to stdout without executing it.
  Safe to call in unit tests and for user previews.

Public API
----------
ReplayEngine()
    .replay(macro, *, dry_run, speed_factor, on_progress, on_done, on_error)
    .stop()
    .is_running  → bool

Callbacks (all optional, called on the replay thread)
------------------------------------------------------
on_progress(index: int, action: Action)   – called before each action
on_done()                                 – called when replay finishes normally
on_error(exc: Exception)                  – called when an unhandled error occurs

Exceptions (raised inside the thread, forwarded to on_error)
-------------------------------------------------------------
ReplayError      – unknown action type or missing params
ReplayCancelled  – stop() was called mid-replay (not an error, but logged)
"""

from __future__ import annotations

import shutil
import threading
import time
from typing import Callable

import pyautogui
from pynput.keyboard import Controller as KeyboardController
from pynput.keyboard import Key, KeyCode

from keymacro.models.action import Action, ActionType, Macro

# Safety: pyautogui PAUSE between calls (seconds).  Set low; DELAY actions
# handle inter-action timing explicitly.
pyautogui.PAUSE = 0.02
pyautogui.FAILSAFE = True   # move mouse to top-left corner to abort


# ──────────────────────────────────────────────
# Exceptions
# ──────────────────────────────────────────────

class ReplayError(Exception):
    """Raised for unknown action types or missing required params."""


class ReplayCancelled(Exception):
    """Raised internally when stop() is called between actions."""


# ──────────────────────────────────────────────
# ReplayEngine
# ──────────────────────────────────────────────

class ReplayEngine:
    """Executes a Macro's action list, optionally in dry-run mode.

    Thread-safety
    -------------
    ``replay()`` spawns a daemon thread.  ``stop()`` and ``is_running`` are
    safe to call from any thread (GUI thread included).
    """

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._kb = KeyboardController()

    # ── public ─────────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        """Signal the running replay to stop after the current action."""
        self._cancel_event.set()

    def replay(
        self,
        macro: Macro,
        *,
        dry_run: bool = False,
        speed_factor: float = 1.0,
        on_progress: Callable[[int, Action], None] | None = None,
        on_done: Callable[[], None] | None = None,
        on_error: Callable[[Exception], None] | None = None,
    ) -> None:
        """Start replaying *macro* in a background daemon thread.

        If another replay is already running it is stopped first.

        Parameters
        ----------
        macro        : the Macro to replay
        dry_run      : if True, print actions instead of executing them
        speed_factor : multiplier for all delay durations
        on_progress  : called before each action with (index, action)
        on_done      : called when all actions complete successfully
        on_error     : called with the exception if something goes wrong
        """
        if self.is_running:
            self.stop()
            if self._thread:
                self._thread.join(timeout=2.0)

        self._cancel_event.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(macro, dry_run, speed_factor, on_progress, on_done, on_error),
            daemon=True,
            name="KeyMacro-Replay",
        )
        self._thread.start()

    # ── internals ──────────────────────────────────

    def _run(
        self,
        macro: Macro,
        dry_run: bool,
        speed_factor: float,
        on_progress: Callable[[int, Action], None] | None,
        on_done: Callable[[], None] | None,
        on_error: Callable[[Exception], None] | None,
    ) -> None:
        try:
            if dry_run:
                print(f"[DRY RUN] Macro: {macro.name!r}  ({len(macro.actions)} actions)")
                print("-" * 60)

            for idx, action in enumerate(macro.actions):
                if self._cancel_event.is_set():
                    raise ReplayCancelled("Replay cancelled by user")

                if on_progress:
                    on_progress(idx, action)

                if dry_run:
                    print(f"  [{idx + 1:>3}] {action.description}")
                else:
                    self._dispatch(action, speed_factor)

            if dry_run:
                print("-" * 60)
                print("[DRY RUN] Complete — no actions were executed.")

            if on_done:
                on_done()

        except ReplayCancelled as exc:
            print(f"[Replay] Cancelled: {exc}")
            # Treat cancellation as a graceful stop — call on_done, not on_error
            if on_done:
                on_done()
        except Exception as exc:  # noqa: BLE001
            print(f"[Replay] Error: {exc}")
            if on_error:
                on_error(exc)

    def _dispatch(self, action: Action, speed_factor: float) -> None:
        """Execute a single Action using pyautogui / pynput."""
        p = action.params

        match action.action_type:

            # ── keyboard ───────────────────────────────

            case ActionType.KEY_PRESS:
                key = _resolve_key(p["key"])
                self._kb.press(key)

            case ActionType.KEY_RELEASE:
                key = _resolve_key(p["key"])
                self._kb.release(key)

            case ActionType.KEY_COMBO:
                keys = [_resolve_key(k) for k in p["keys"]]
                # Press all, then release all in reverse
                for k in keys:
                    self._kb.press(k)
                time.sleep(0.05)
                for k in reversed(keys):
                    self._kb.release(k)

            case ActionType.TYPE_TEXT:
                pyautogui.typewrite(p["text"], interval=0.04)

            # ── mouse ──────────────────────────────────

            case ActionType.MOUSE_MOVE:
                pyautogui.moveTo(p["x"], p["y"], duration=0.1)

            case ActionType.MOUSE_CLICK:
                btn     = p.get("button", "left")
                clicks  = p.get("clicks", 1)
                pyautogui.click(p["x"], p["y"], clicks=clicks, button=btn, interval=0.1)

            case ActionType.MOUSE_SCROLL:
                pyautogui.scroll(p.get("dy", 0), x=p["x"], y=p["y"])

            case ActionType.MOUSE_DRAG:
                dur = p.get("duration", 0.3) * speed_factor
                pyautogui.drag(
                    p["x2"] - p["x1"], p["y2"] - p["y1"],
                    duration=max(0.05, dur),
                    button=p.get("button", "left"),
                    _pause=False,
                    relative=False,
                )
                # pyautogui.drag is relative; use dragTo instead
                pyautogui.moveTo(p["x1"], p["y1"])
                pyautogui.dragTo(p["x2"], p["y2"], duration=max(0.05, dur),
                                 button=p.get("button", "left"))

            # ── timing ─────────────────────────────────

            case ActionType.DELAY:
                ms = p.get("ms", 0)
                secs = (ms / 1000.0) * max(speed_factor, 0.0)
                # Sleep in small chunks so cancel_event is checked regularly
                slept = 0.0
                chunk = 0.05
                while slept < secs:
                    if self._cancel_event.is_set():
                        return
                    sleep_for = min(chunk, secs - slept)
                    time.sleep(sleep_for)
                    slept += sleep_for

            # ── application launch ─────────────────────

            case ActionType.LAUNCH_APP:
                import os, subprocess
                target = p["target"]
                try:
                    os.startfile(target)
                except Exception:
                    # Fallback for CLI commands, PATH executables, or scripts
                    subprocess.Popen(target, shell=True)

            case ActionType.PLUGIN_ACTION:
                from keymacro.plugins.manager import PluginManager
                plug_id = p.get("plugin_id", "")
                act_id  = p.get("action_id", "")
                params  = p.get("params", {})
                PluginManager.get_instance().execute(plug_id, act_id, params)

            # ── file-system (safety layer runs before replay reaches here) ──

            case ActionType.FILE_DELETE:
                path = p["path"]
                import os
                os.remove(path)

            case ActionType.FILE_MOVE:
                shutil.move(p["src"], p["dst"])

            case ActionType.FILE_COPY:
                shutil.copy2(p["src"], p["dst"])

            # ── unknown ────────────────────────────────

            case _:
                raise ReplayError(
                    f"Unknown action type: {action.action_type!r}"
                )


# ──────────────────────────────────────────────
# Key resolution helper
# ──────────────────────────────────────────────

# Map string names → pynput Key constants
_SPECIAL_KEYS: dict[str, Key] = {
    name.lower(): member for name, member in Key.__members__.items()
}

def _resolve_key(key_str: str) -> Key | KeyCode:
    """Convert a string like ``"ctrl"`` or ``"a"`` to a pynput key object."""
    lower = key_str.lower().strip("<>")
    if lower in _SPECIAL_KEYS:
        return _SPECIAL_KEYS[lower]
    if len(key_str) == 1:
        return KeyCode.from_char(key_str)
    # Try vk code (e.g. "vk_65")
    if lower.startswith("vk_"):
        try:
            return KeyCode.from_vk(int(lower[3:]))
        except ValueError:
            pass
    raise ReplayError(f"Cannot resolve key: {key_str!r}")


# ──────────────────────────────────────────────
# CLI entry point: python -m keymacro.engine.replay <macro.json> [--dry-run]
# ──────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    import json
    import sys
    from pathlib import Path

    parser = argparse.ArgumentParser(description="Replay a KeyMacro JSON file")
    parser.add_argument("macro_file", help="Path to the macro JSON file")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without executing")
    parser.add_argument("--speed", type=float, default=1.0, help="Speed factor (0.5 = 2x faster)")
    args = parser.parse_args()

    path = Path(args.macro_file)
    if not path.exists():
        print(f"Error: file not found: {path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    macro = Macro.from_dict(data)

    done_event = threading.Event()

    def _on_done() -> None:
        done_event.set()

    def _on_err(exc: Exception) -> None:
        print(f"Replay error: {exc}", file=sys.stderr)
        done_event.set()

    engine = ReplayEngine()
    engine.replay(macro, dry_run=args.dry_run, speed_factor=args.speed,
                  on_done=_on_done, on_error=_on_err)
    done_event.wait()
