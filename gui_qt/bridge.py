"""
gui_qt/bridge.py
────────────────
Thread-safe bridge connecting the KeyMacro engine, recorder, safety layer,
and hotkey listener with PySide6 signals and slots.
"""

from __future__ import annotations

import io
import contextlib
import threading
from typing import TYPE_CHECKING, Callable
from PySide6.QtCore import QObject, Signal, QTimer

from keymacro.models.action import Macro, RiskLevel
from keymacro.safety.safety_layer import BlockedPathError

if TYPE_CHECKING:
    from PySide6.QtWidgets import QWidget
    from keymacro.engine.replay import ReplayEngine
    from keymacro.hotkey.listener import HotkeyListener
    from keymacro.recorder.recorder import Recorder
    from keymacro.safety.safety_layer import SafetyLayer
    from keymacro.storage.macro_store import MacroStore


class EngineBridge(QObject):
    """Bridges background Replay and Recording threads into the Qt event loop."""

    # Replay lifecycle signals (always emitted onto the Qt Main Thread)
    replay_started = Signal(str)          # macro_name
    replay_finished = Signal(str)         # macro_name
    replay_error = Signal(str, str)       # macro_name, error_message

    # Recording lifecycle signals
    recording_started = Signal(str)       # macro_name
    recording_stopped = Signal(object)     # Macro object (or None)

    # Hotkey trigger signal
    hotkey_triggered = Signal(object)     # Macro object

    # State update signal (idle, recording, replaying)
    state_changed = Signal(str)

    def __init__(
        self,
        engine: "ReplayEngine",
        recorder: "Recorder",
        safety: "SafetyLayer",
        hotkeys: "HotkeyListener",
        store: "MacroStore",
        parent_widget: "QWidget | None" = None,
    ) -> None:
        super().__init__()
        self._engine = engine
        self._recorder = recorder
        self._safety = safety
        self._hotkeys = hotkeys
        self._store = store
        self._parent_widget = parent_widget

        self._state = "idle"

    @property
    def state(self) -> str:
        return self._state

    def set_parent_widget(self, widget: "QWidget") -> None:
        self._parent_widget = widget

    # ── Replay Execution ──────────────────────────────────────────────────────

    def run_macro(self, macro: Macro) -> bool:
        """Validate safety and start background replay. Returns False if blocked/cancelled."""
        if self._state != "idle":
            return False

        # 1. Blocked path check
        try:
            self._safety._check_blocked_paths(macro)
        except BlockedPathError as exc:
            from PySide6.QtWidgets import QMessageBox
            QMessageBox.critical(
                self._parent_widget,
                "Protected Path Blocked",
                f"This macro targets a protected system directory and cannot be executed:\n\n{exc}",
            )
            return False

        # 2. Risk check & High-risk confirmation dialog
        risk = self._safety.assess_risk(macro)
        if risk == RiskLevel.HIGH:
            from gui_qt.dialogs.safety_dialog import SafetyConfirmDialog
            preview = self._safety.preview_actions(macro)
            confirmed = SafetyConfirmDialog.confirm(self._parent_widget, macro, preview)
            if not confirmed:
                return False
            # Perform automated backup of targets
            self._safety._backup_targets(macro)

        # 3. Transition to replaying state
        self._set_state("replaying")
        self.replay_started.emit(macro.name)

        def _on_done() -> None:
            self._set_state("idle")
            self.replay_finished.emit(macro.name)

        def _on_error(exc: Exception) -> None:
            self._set_state("idle")
            self.replay_error.emit(macro.name, str(exc))

        self._engine.replay(
            macro,
            dry_run=False,
            on_done=_on_done,
            on_error=_on_error,
        )
        return True

    def stop_execution(self) -> None:
        """Halt running replay or stop active recording."""
        if self._state == "replaying":
            self._engine.stop()
            self._set_state("idle")
        elif self._state == "recording":
            macro = self.stop_recording()
            return macro

    def dry_run(self, macro: Macro, callback_with_output: Callable[[str], None]) -> None:
        """Run dry-run simulation and capture console output in a daemon thread."""
        if self._state != "idle":
            return

        self._set_state("replaying")
        buf = io.StringIO()

        def _worker() -> None:
            with contextlib.redirect_stdout(buf):
                done = threading.Event()
                self._engine.replay(
                    macro,
                    dry_run=True,
                    on_done=done.set,
                    on_error=lambda _: done.set(),
                )
                done.wait(timeout=20)
            
            output = buf.getvalue()
            # Queue output handling back to GUI thread via QTimer
            QTimer.singleShot(0, lambda: self._on_dry_run_complete(output, callback_with_output))

        threading.Thread(target=_worker, daemon=True).start()

    def _on_dry_run_complete(self, output: str, callback: Callable[[str], None]) -> None:
        self._set_state("idle")
        callback(output)

    # ── Recording ─────────────────────────────────────────────────────────────

    def start_recording(self, macro_name: str, record_mouse_path: bool = True) -> None:
        """Start capturing keyboard and mouse actions."""
        if self._state != "idle":
            return

        self._recorder._name = macro_name or "My Macro"
        self._recorder._record_path = record_mouse_path
        self._recorder._mouse_only = True
        self._recorder.start()

        self._set_state("recording")
        self.recording_started.emit(macro_name)

    def stop_recording(self) -> Macro | None:
        """Stop capturing and return the generated Macro."""
        if self._state != "recording":
            return None

        macro = self._recorder.stop()
        self._set_state("idle")
        self.recording_stopped.emit(macro)
        return macro

    # ── Hotkeys ───────────────────────────────────────────────────────────────

    def refresh_hotkeys(self, macros: list[Macro]) -> None:
        """Re-bind global hotkeys with thread-safe trigger emission."""
        self._hotkeys.clear()
        for macro in macros:
            if macro.hotkey:
                def _make_handler(m: Macro):
                    def _handler():
                        # Signal emit is thread-safe across threads in PySide6
                        self.hotkey_triggered.emit(m)
                    return _handler

                try:
                    self._hotkeys.register(
                        macro.hotkey,
                        _make_handler(macro),
                        target_app=macro.target_app,
                        macro_id=macro.macro_id,
                    )
                except Exception as exc:
                    print(f"[QtBridge] Hotkey registration failed for {macro.hotkey}: {exc}")

    # ── State Helper ──────────────────────────────────────────────────────────

    def _set_state(self, new_state: str) -> None:
        self._state = new_state
        self.state_changed.emit(new_state)
