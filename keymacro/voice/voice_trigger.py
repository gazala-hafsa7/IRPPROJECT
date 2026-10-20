"""
keymacro/voice/voice_trigger.py
───────────────────────────────
Voice Command Trigger — listens for "Hey KeyMacro, run <name>" in a
background daemon thread and fires a callback when a macro name is matched.

Dependencies (optional — graceful degradation if absent):
    pip install SpeechRecognition sounddevice soundfile

Uses sounddevice instead of pyaudio for Python 3.13+ compatibility.
Wake phrase: "hey keymacro" (case-insensitive)
After the wake phrase, the next word(s) are fuzzy-matched against loaded
macro names using difflib.get_close_matches.

Usage
-----
    trigger = VoiceTrigger(macro_store, on_match=lambda m: bridge.run_macro(m))
    trigger.start()   # spawns daemon thread
    trigger.stop()    # request graceful shutdown
    trigger.is_running  # bool
"""

from __future__ import annotations

import difflib
import threading
import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from typing import Any
    from keymacro.models.action import Macro
    from keymacro.models.workflow import Workflow
    from keymacro.storage.macro_store import MacroStore
    from keymacro.storage.workflow_store import WorkflowStore

# ── optional imports ──────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    _SR_AVAILABLE = True
except ImportError:
    _SR_AVAILABLE = False

# Try sounddevice-based microphone; fall back gracefully if absent
try:
    import sounddevice as sd
    import numpy as np
    _SD_AVAILABLE = True
except ImportError:
    _SD_AVAILABLE = False

_WAKE_PHRASES = (
    "hey keymacro",
    "hey key macro",
    "hey key marco",
    "hey kmacro",
    "hey k macro",
    "hey macro",
    "hi keymacro",
    "hi key macro",
    "ok keymacro",
    "ok key macro",
    "keymacro",
    "key macro",
)
_RUN_KEYWORDS = ("run", "start", "execute", "play", "trigger", "launch", "open")
_SAMPLE_RATE = 16000   # Hz — Google STT works best at 16kHz
_CHUNK_SECS  = 4       # seconds of audio per recognition attempt


def _fuzzy_find(query: str, items: "list[Any]") -> "Any | None":
    """Return best-matching item for *query* by .name or None if nothing close enough."""
    if not items or not query:
        return None
    query_clean = query.lower().strip()
    names = [getattr(m, "name", "").lower().strip() for m in items]

    # 1. Exact match
    for idx, name in enumerate(names):
        if name == query_clean:
            return items[idx]

    # 2. Substring match (name inside query, or query inside name)
    for idx, name in enumerate(names):
        if name and (name in query_clean or query_clean in name):
            return items[idx]

    # 3. Fuzzy match with difflib
    matches = difflib.get_close_matches(query_clean, names, n=1, cutoff=0.35)
    if matches:
        idx = names.index(matches[0])
        return items[idx]

    return None


class VoiceTrigger:
    """
    Background voice command listener.

    Parameters
    ----------
    macro_store : MacroStore
        Used to resolve macro names at match-time.
    on_match : Callable[[Macro], None]
        Called (from the listener thread!) when a voice command is matched.
        Wire this into a thread-safe Qt Signal emit.
    on_status : Callable[[str], None] | None
        Optional status callback.
        Messages: "listening", "processing", "matched:<name>", "no_match",
                  "stopped", "unavailable", "error:<msg>"
    workflow_store : WorkflowStore | None
        Optional workflow store to resolve workflow names at match-time.
    on_workflow_match : Callable[[Workflow], None] | None
        Called when a voice command matches a saved workflow.
    energy_threshold : int
        Microphone sensitivity (default 300).
    phrase_time_limit : float
        Max seconds to listen per utterance (default 5).
    """

    def __init__(
        self,
        macro_store: "MacroStore",
        on_match: "Callable[[Macro], None]",
        on_status: "Callable[[str], None] | None" = None,
        workflow_store: "WorkflowStore | None" = None,
        on_workflow_match: "Callable[[Workflow], None] | None" = None,
        energy_threshold: int = 300,
        phrase_time_limit: float = 5.0,
    ) -> None:
        self._store = macro_store
        self._on_match = on_match
        self._on_status = on_status
        self._wf_store = workflow_store
        self._on_workflow_match = on_workflow_match
        self._energy_threshold = energy_threshold
        self._phrase_time_limit = phrase_time_limit

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """True if SpeechRecognition is installed (pyaudio OR sounddevice)."""
        return _SR_AVAILABLE

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self) -> bool:
        """Start the listener daemon thread. Returns False if unavailable."""
        if not _SR_AVAILABLE:
            self._emit_status("unavailable")
            return False
        if self.is_running:
            return True
        self._stop_event.clear()

        # Choose backend based on what's installed
        if _SD_AVAILABLE:
            target = self._listen_loop_sounddevice
        else:
            target = self._listen_loop_pyaudio

        self._thread = threading.Thread(
            target=target,
            daemon=True,
            name="VoiceTriggerThread",
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Request the listener thread to stop."""
        self._stop_event.set()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit_status(self, msg: str) -> None:
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass

    # ── sounddevice backend (Python 3.13+ compatible) ─────────────────────────

    def _listen_loop_sounddevice(self) -> None:
        """Continuously capture audio via sounddevice and recognise with Google STT."""
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = self._energy_threshold

            while not self._stop_event.is_set():
                self._emit_status("listening")
                try:
                    # Record a fixed-length chunk
                    frames = int(_SAMPLE_RATE * _CHUNK_SECS)
                    audio_np = sd.rec(
                        frames,
                        samplerate=_SAMPLE_RATE,
                        channels=1,
                        dtype="int16",
                    )
                    sd.wait()  # blocks until recording is done

                    if self._stop_event.is_set():
                        break

                    # Convert numpy array → sr.AudioData
                    raw_bytes = audio_np.tobytes()
                    audio_data = sr.AudioData(raw_bytes, _SAMPLE_RATE, 2)  # 2 bytes = int16

                    self._emit_status("processing")
                    try:
                        text = recognizer.recognize_google(audio_data).lower().strip()
                    except sr.UnknownValueError:
                        self._emit_status("listening")
                        continue
                    except sr.RequestError as exc:
                        self._emit_status(f"error:Network error — {exc}")
                        time.sleep(2)
                        continue

                    self._process_text(text)

                except Exception as exc:
                    self._emit_status(f"error:{exc}")
                    time.sleep(1)

        except Exception as exc:
            self._emit_status(f"error:{exc}")

        self._emit_status("stopped")

    # ── pyaudio backend (fallback for older Python) ───────────────────────────

    def _listen_loop_pyaudio(self) -> None:
        """Continuously listen via pyaudio microphone (classic path)."""
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = self._energy_threshold
            recognizer.dynamic_energy_threshold = True

            with sr.Microphone() as source:
                recognizer.adjust_for_ambient_noise(source, duration=1)

                while not self._stop_event.is_set():
                    self._emit_status("listening")
                    try:
                        audio = recognizer.listen(
                            source,
                            timeout=3,
                            phrase_time_limit=self._phrase_time_limit,
                        )
                    except sr.WaitTimeoutError:
                        continue

                    self._emit_status("processing")
                    try:
                        text = recognizer.recognize_google(audio).lower().strip()
                    except sr.UnknownValueError:
                        self._emit_status("listening")
                        continue
                    except sr.RequestError as exc:
                        self._emit_status(f"error:Network error — {exc}")
                        time.sleep(2)
                        continue

                    self._process_text(text)

        except Exception as exc:
            self._emit_status(f"error:{exc}")

        self._emit_status("stopped")

    def _process_text(self, text: str) -> None:
        """Parse the recognised text and fire on_match or on_workflow_match if a macro/workflow is found."""
        print(f"[VoiceTrigger] Transcribed audio: {text!r}")
        raw = text.lower().replace(",", " ").replace(".", " ").strip()
        cleaned = raw

        # 1. Strip wake phrase if present
        for wp in _WAKE_PHRASES:
            if wp in cleaned:
                cleaned = cleaned.split(wp, 1)[1].strip()
                break

        # 2. Strip action verb if at the start
        words = cleaned.split()
        if words and words[0] in _RUN_KEYWORDS:
            cleaned = " ".join(words[1:]).strip()

        # Check if user specifically requested a workflow, e.g. "workflow daily report" or "run workflow backup"
        is_workflow_explicit = "workflow" in cleaned or "work flow" in cleaned
        wf_candidate = cleaned.replace("workflow", "").replace("work flow", "").strip()
        candidate = cleaned if cleaned else raw

        # 3. If "workflow" was explicitly spoken, look up in workflow store first
        if is_workflow_explicit and self._wf_store and self._on_workflow_match:
            workflows = self._wf_store.list_all()
            wf = _fuzzy_find(wf_candidate, workflows) or _fuzzy_find(raw, workflows)
            if wf:
                print(f"[VoiceTrigger] Matched workflow '{wf.name}' from '{text}'")
                self._emit_status(f"matched_workflow:{wf.name}:{text}")
                try:
                    self._on_workflow_match(wf)
                except Exception as exc:
                    print(f"[VoiceTrigger] Error in workflow callback: {exc}")
                return

        # 4. Check macros in macro store
        macros = self._store.list_all()
        macro = _fuzzy_find(candidate, macros)
        if not macro and candidate != raw:
            macro = _fuzzy_find(raw, macros)

        if macro:
            print(f"[VoiceTrigger] Matched macro '{macro.name}' from '{text}'")
            self._emit_status(f"matched:{macro.name}:{text}")
            try:
                self._on_match(macro)
            except Exception as exc:
                print(f"[VoiceTrigger] Error in callback: {exc}")
            return

        # 5. Fallback: check if any workflow matches the query even if "workflow" wasn't spoken
        if self._wf_store and self._on_workflow_match:
            workflows = self._wf_store.list_all()
            wf = _fuzzy_find(candidate, workflows) or _fuzzy_find(raw, workflows)
            if wf:
                print(f"[VoiceTrigger] Matched workflow '{wf.name}' from '{text}'")
                self._emit_status(f"matched_workflow:{wf.name}:{text}")
                try:
                    self._on_workflow_match(wf)
                except Exception as exc:
                    print(f"[VoiceTrigger] Error in workflow callback: {exc}")
                return

        print(f"[VoiceTrigger] No matching macro or workflow found for '{text}'")
        self._emit_status(f"no_match:{text}")
