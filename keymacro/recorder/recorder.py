"""
keymacro/recorder/recorder.py
──────────────────────────────
Input recorder — converts live keyboard/mouse events into Action objects.

Mouse move strategy (as agreed in design)
------------------------------------------
Default: **clicks/scroll only** — mouse moves between clicks are NOT recorded.
If ``record_mouse_path=True``, moves are sampled at most every
``mouse_throttle_ms`` milliseconds (default 50 ms) to limit event volume.

Key tracking
------------
pynput delivers separate press and release events.  The recorder accumulates
consecutive presses/releases of *modifier* keys (ctrl, shift, alt, win) and
tracks when they are held while a regular key is pressed so it can emit a
KEY_COMBO rather than separate KEY_PRESS + KEY_RELEASE events.

DELAY actions
-------------
Wall-clock time between consecutive events is measured and emitted as a DELAY
action when the gap exceeds ``min_delay_ms`` (default 50 ms). This faithfully
reproduces human timing during replay.

Public API
----------
Recorder(name, record_mouse_path, mouse_throttle_ms, min_delay_ms)
    .start()                        – begin recording (non-blocking)
    .stop()  → Macro                – stop and return the completed Macro
    .is_recording  → bool
"""

from __future__ import annotations

import threading
import time
from typing import Any

from pynput import keyboard, mouse
from pynput.keyboard import Key, KeyCode

from keymacro.models.action import Action, ActionType, Macro


# ──────────────────────────────────────────────
# Modifier key set
# ──────────────────────────────────────────────

_MODIFIERS: frozenset[Key] = frozenset({
    Key.ctrl, Key.ctrl_l, Key.ctrl_r,
    Key.shift, Key.shift_l, Key.shift_r,
    Key.alt, Key.alt_l, Key.alt_r, Key.alt_gr,
    Key.cmd, Key.cmd_l, Key.cmd_r,
})

def _is_modifier(key: Key | KeyCode) -> bool:
    return key in _MODIFIERS


def _key_name(key: Key | KeyCode) -> str:
    """Return a stable string representation of a pynput key."""
    if isinstance(key, Key):
        return key.name          # e.g. "ctrl_l", "shift", "f5"
    if key.char is not None:
        return key.char          # e.g. "a", "A", "!"
    return f"vk_{key.vk}"       # fallback for keys with no char


# ──────────────────────────────────────────────
# Recorder
# ──────────────────────────────────────────────

class Recorder:
    """Records keyboard and mouse events and converts them to a Macro.

    Parameters
    ----------
    name : str
        Name for the resulting Macro.
    record_mouse_path : bool
        If True, mouse movement events are recorded (throttled).
        If False (default), only clicks and scrolls are recorded.
    mouse_throttle_ms : int
        Minimum gap between successive MOUSE_MOVE events (ms).  Only used when
        record_mouse_path is True.
    min_delay_ms : int
        Minimum inter-event gap to record as a DELAY action.  Gaps shorter
        than this are silently dropped.
    """

    def __init__(
        self,
        name: str = "New Macro",
        record_mouse_path: bool = False,
        mouse_throttle_ms: int = 50,
        min_delay_ms: int = 50,
        mouse_only: bool = True,
    ) -> None:
        self._name             = name
        self._record_path      = record_mouse_path
        self._throttle_ms      = mouse_throttle_ms
        self._min_delay_ms     = min_delay_ms
        self._mouse_only       = mouse_only

        self._actions: list[Action]   = []
        self._lock = threading.Lock()

        self._last_event_time: float  = 0.0
        self._last_move_time: float   = 0.0
        self._held_modifiers: set[Key | KeyCode] = set()

        self._kb_listener: keyboard.Listener | None = None
        self._ms_listener: mouse.Listener   | None = None
        self._recording = False

    # ── public ─────────────────────────────────────

    @property
    def is_recording(self) -> bool:
        return self._recording

    def start(self) -> None:
        """Begin capturing input events (non-blocking)."""
        if self._recording:
            return
        self._actions.clear()
        self._held_modifiers.clear()
        self._last_event_time = time.perf_counter()
        self._last_move_time  = 0.0
        self._recording = True

        if not self._mouse_only:
            self._kb_listener = keyboard.Listener(
                on_press=self._on_key_press,
                on_release=self._on_key_release,
            )
            self._kb_listener.start()

        self._ms_listener = mouse.Listener(
            on_move=self._on_mouse_move,
            on_click=self._on_mouse_click,
            on_scroll=self._on_mouse_scroll,
        )
        self._ms_listener.start()

    def stop(self) -> Macro:
        """Stop recording and return the captured Macro."""
        if not self._recording:
            raise RuntimeError("Recorder is not running")
        self._recording = False

        if self._kb_listener:
            self._kb_listener.stop()
        if self._ms_listener:
            self._ms_listener.stop()

        self._kb_listener = None
        self._ms_listener = None

        with self._lock:
            actions = list(self._actions)

        return Macro(name=self._name, actions=actions)

    # ── keyboard handlers ──────────────────────────

    def _on_key_press(self, key: Key | KeyCode) -> None:
        if not self._recording or self._mouse_only:
            return
        with self._lock:
            self._emit_delay()
            if _is_modifier(key):
                self._held_modifiers.add(key)
                return  # don't record modifier presses alone
            if self._held_modifiers:
                # Emit a KEY_COMBO (modifiers + this key)
                combo_keys = [_key_name(m) for m in sorted(
                    self._held_modifiers, key=_key_name
                )] + [_key_name(key)]
                self._append(ActionType.KEY_COMBO, {"keys": combo_keys})
            else:
                self._append(ActionType.KEY_PRESS, {"key": _key_name(key)})

    def _on_key_release(self, key: Key | KeyCode) -> None:
        if not self._recording or self._mouse_only:
            return
        with self._lock:
            if _is_modifier(key):
                self._held_modifiers.discard(key)
                return
            if not self._held_modifiers:
                self._emit_delay()
                self._append(ActionType.KEY_RELEASE, {"key": _key_name(key)})

    # ── mouse handlers ─────────────────────────────

    def _on_mouse_move(self, x: int, y: int) -> None:
        if not self._recording or not self._record_path:
            return
        now = time.perf_counter()
        elapsed_ms = (now - self._last_move_time) * 1000
        if elapsed_ms < self._throttle_ms:
            return
        with self._lock:
            self._emit_delay()
            self._append(ActionType.MOUSE_MOVE, {"x": x, "y": y})
            self._last_move_time = now

    def _on_mouse_click(self, x: int, y: int, button: mouse.Button, pressed: bool) -> None:
        if not self._recording or not pressed:
            return  # ignore release events; only record clicks on press
        with self._lock:
            self._emit_delay()
            self._append(ActionType.MOUSE_CLICK, {
                "x": x,
                "y": y,
                "button": button.name,
                "clicks": 1,
            })

    def _on_mouse_scroll(self, x: int, y: int, dx: int, dy: int) -> None:
        if not self._recording:
            return
        with self._lock:
            self._emit_delay()
            self._append(ActionType.MOUSE_SCROLL, {
                "x": x, "y": y,
                "dx": dx, "dy": dy,
            })

    # ── internal helpers ───────────────────────────

    def _emit_delay(self) -> None:
        """Record a DELAY action if enough time has passed since last event.
        Must be called while self._lock is held.
        """
        now = time.perf_counter()
        gap_ms = int((now - self._last_event_time) * 1000)
        self._last_event_time = now
        if gap_ms >= self._min_delay_ms:
            self._actions.append(Action(
                action_type=ActionType.DELAY,
                params={"ms": gap_ms},
                timestamp_ms=now * 1000,
            ))

    def _append(self, action_type: ActionType, params: dict[str, Any]) -> None:
        """Append a new Action; called while self._lock is held."""
        self._actions.append(Action(
            action_type=action_type,
            params=params,
            timestamp_ms=time.perf_counter() * 1000,
        ))
