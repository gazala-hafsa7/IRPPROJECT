"""
keymacro/hotkey/listener.py
─────────────────────────────
Advanced Global hotkey & shortcut sequence listener with App-Context awareness
and Master ON/OFF toggle.

Features
────────
1. Master Toggle:
   - `enabled = True/False`: seamlessly pause or resume macro triggering.
2. Sequence & Multi-key Combo Support:
   - Supports natural shortcut formats: `ctrl+o+a`, `ctrl+shift+f5`, `alt+1`, `ctrl+k c`.
3. App-Specific Context Routing:
   - Two different macros can use the exact same shortcut (e.g. `ctrl+o+a`).
   - If Chrome is focused, the Chrome macro runs.
   - If Spotify is focused, the Spotify macro runs.
   - If no app-specific macro matches, the Global macro runs (if defined).
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Callable

from pynput import keyboard
from pynput.keyboard import Key, KeyCode

from keymacro.hotkey.context import get_active_window_info, matches_app


@dataclass
class HotkeyBinding:
    raw_hotkey: str
    keys: list[str]          # normalised list of key names, e.g. ['ctrl', 'o', 'a']
    target_app: str          # '' means Global; otherwise executable name or title substring
    callback: Callable[[], None]
    macro_id: str = ""


# Aliases for normalising key representations
_KEY_ALIASES = {
    "control": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "shift_l": "shift",
    "shift_r": "shift",
    "alt_l": "alt",
    "alt_r": "alt",
    "alt_gr": "alt",
    "cmd": "win",
    "cmd_l": "win",
    "cmd_r": "win",
    "windows": "win",
    "return": "enter",
}


def _norm_key(k: str) -> str:
    cleaned = k.strip().lower().strip("<>")
    return _KEY_ALIASES.get(cleaned, cleaned)


def parse_hotkey_tokens(hotkey_str: str) -> list[str]:
    """Convert 'ctrl+o+a' or '<ctrl>+<shift>+f5' or 'ctrl+k c' into a list of normalised keys."""
    # Split by '+' or whitespace
    raw_parts = [p.strip() for p in hotkey_str.replace("+", " ").split() if p.strip()]
    return [_norm_key(p) for p in raw_parts]


class HotkeyListener:
    """System-wide hotkey and sequence detector with active app context routing."""

    def __init__(self) -> None:
        self._bindings: list[HotkeyBinding] = []
        self._lock = threading.Lock()
        self._running = False
        self._enabled = True  # Master ON/OFF toggle

        self._listener: keyboard.Listener | None = None
        self._held_keys: set[str] = set()
        self._recent_events: list[tuple[str, float]] = []  # (key, timestamp)
        self._sequence_timeout_s = 1.2  # Max interval for sequential key chords

    # ── Master Toggle ──────────────────────────────

    @property
    def enabled(self) -> bool:
        """Master toggle state. When False, all hotkeys and sequences are bypassed."""
        return self._enabled

    @enabled.setter
    def enabled(self, value: bool) -> None:
        self._enabled = bool(value)
        if not self._enabled:
            # Clear held keys when disabled
            with self._lock:
                self._held_keys.clear()
                self._recent_events.clear()

    # ── Public API ─────────────────────────────────

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def registered(self) -> list[str]:
        with self._lock:
            return [b.raw_hotkey for b in self._bindings]

    def register(
        self,
        hotkey_str: str,
        callback: Callable[[], None],
        target_app: str = "",
        macro_id: str = "",
    ) -> None:
        """Register a macro shortcut with optional target application context."""
        tokens = parse_hotkey_tokens(hotkey_str)
        if not tokens:
            return

        binding = HotkeyBinding(
            raw_hotkey=hotkey_str,
            keys=tokens,
            target_app=target_app.strip(),
            callback=callback,
            macro_id=macro_id,
        )

        with self._lock:
            # Remove any existing duplicate binding for the exact same macro_id or hotkey+app
            self._bindings = [
                b for b in self._bindings
                if not (b.raw_hotkey == hotkey_str and b.target_app.lower() == target_app.strip().lower())
                and not (macro_id and b.macro_id == macro_id)
            ]
            self._bindings.append(binding)

    def unregister(self, hotkey_str: str) -> None:
        """Remove bindings matching hotkey_str."""
        with self._lock:
            self._bindings = [b for b in self._bindings if b.raw_hotkey != hotkey_str]

    def unregister_by_macro_id(self, macro_id: str) -> None:
        """Remove bindings for a specific macro id."""
        with self._lock:
            self._bindings = [b for b in self._bindings if b.macro_id != macro_id]

    def clear(self) -> None:
        """Remove all registered hotkeys."""
        with self._lock:
            self._bindings.clear()

    def start(self) -> None:
        """Start listening for keyboard events."""
        if self._running:
            return
        self._running = True
        self._listener = keyboard.Listener(
            on_press=self._on_press,
            on_release=self._on_release,
        )
        self._listener.daemon = True
        self._listener.start()

    def stop(self) -> None:
        """Stop listening."""
        self._running = False
        if self._listener is not None:
            self._listener.stop()
            self._listener = None
        with self._lock:
            self._held_keys.clear()
            self._recent_events.clear()

    # ── Keystroke Dispatcher ───────────────────────

    def _key_to_name(self, key: Key | KeyCode) -> str:
        if isinstance(key, Key):
            return _norm_key(key.name)
        if hasattr(key, "char") and key.char:
            c = key.char
            if len(c) == 1 and 1 <= ord(c) <= 26:
                return _norm_key(chr(ord(c) + 96))
            return _norm_key(c)
        if hasattr(key, "vk") and key.vk is not None:
            vk = key.vk
            if 65 <= vk <= 90:
                return _norm_key(chr(vk).lower())
            if 48 <= vk <= 57:
                return _norm_key(chr(vk))
            return f"vk_{vk}"
        return ""

    def _on_press(self, key: Key | KeyCode) -> None:
        if not self._running or not self._enabled:
            return

        name = self._key_to_name(key)
        if not name:
            return

        now = time.perf_counter()

        with self._lock:
            self._held_keys.add(name)

            # Prune expired recent events
            self._recent_events = [
                (k, t) for (k, t) in self._recent_events
                if (now - t) <= self._sequence_timeout_s
            ]
            self._recent_events.append((name, now))

            # Match against registered bindings
            matched_binding = self._find_match()

        if matched_binding:
            # Clear sequence buffer to prevent repeated triggers
            with self._lock:
                self._recent_events.clear()

            # Execute callback on worker thread to avoid blocking keyboard hook
            threading.Thread(target=matched_binding.callback, daemon=True).start()

    def _on_release(self, key: Key | KeyCode) -> None:
        name = self._key_to_name(key)
        if not name:
            return
        with self._lock:
            self._held_keys.discard(name)

    def _find_match(self) -> HotkeyBinding | None:
        """Find the most specific matching binding for current held keys or recent sequence."""
        if not self._bindings:
            return None

        # Detect active foreground window context
        active_exe, active_title = get_active_window_info()

        recent_keys = [k for (k, _) in self._recent_events]

        matching_candidates: list[HotkeyBinding] = []

        for b in self._bindings:
            target_keys = b.keys
            if not target_keys:
                continue

            # Check 1: All target keys currently held simultaneously
            is_combo_held = all(k in self._held_keys for k in target_keys)

            # Check 2: Sequential match in recent keys (e.g. ctrl+o then a)
            is_seq_match = False
            if len(recent_keys) >= len(target_keys):
                if recent_keys[-len(target_keys):] == target_keys:
                    is_seq_match = True

            if is_combo_held or is_seq_match:
                matching_candidates.append(b)

        if not matching_candidates:
            return None

        # Context routing:
        # 1. First priority: Exact match for active target app
        for b in matching_candidates:
            if b.target_app and matches_app(b.target_app, active_exe, active_title):
                return b

        # 2. Second priority: Global macro (target_app is empty or 'global')
        for b in matching_candidates:
            if not b.target_app or b.target_app.lower() in ("global", "all"):
                return b

        return None
