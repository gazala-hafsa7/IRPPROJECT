"""
keymacro/voice/voice_trigger.py
───────────────────────────────
Voice Command Trigger — listens for "Hey KeyMacro, run <name>" in a
background daemon thread and fires a callback when a macro or workflow is matched.

Dependencies (optional — graceful degradation if absent):
    pip install SpeechRecognition sounddevice soundfile numpy

Uses sounddevice for native microphone streaming (Python 3.10 through 3.14+ compatible).
Continuous phrase detection via SpeechRecognition prevents audio loss and only contacts
speech recognition services when speech is actively detected.
"""

from __future__ import annotations

import difflib
import queue
import re
import threading
import time
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from typing import Any
    from keymacro.models.action import Macro
    from keymacro.models.workflow import Workflow
    from keymacro.storage.macro_store import MacroStore
    from keymacro.storage.workflow_store import WorkflowStore

# ── Optional imports ──────────────────────────────────────────────────────────
try:
    import speech_recognition as sr
    _SR_AVAILABLE = True
except ImportError:
    sr = None  # type: ignore[assignment]
    _SR_AVAILABLE = False

try:
    import sounddevice as sd
    _SD_AVAILABLE = True
except ImportError:
    sd = None  # type: ignore[assignment]
    _SD_AVAILABLE = False

try:
    import pyaudio
    _PYAUDIO_AVAILABLE = True
except ImportError:
    pyaudio = None
    _PYAUDIO_AVAILABLE = False


_WAKE_PHRASES = (
    "hey keymacro",
    "hey key macro",
    "hey key marco",
    "hey kmacro",
    "hey k macro",
    "hey macro",
    "hi keymacro",
    "hi key macro",
    "hi kmacro",
    "hi macro",
    "ok keymacro",
    "ok key macro",
    "ok kmacro",
    "ok macro",
    "hey key marker",
    "hey key maker",
    "hey q macro",
    "keymacro",
    "key macro",
    "kmacro",
)

_RUN_KEYWORDS = (
    "run",
    "start",
    "execute",
    "play",
    "trigger",
    "launch",
    "open",
    "please",
    "the",
    "task",
    "tasks",
    "macro",
    "macros",
    "a",
    "my",
    "to",
)

_DEFAULT_SAMPLE_RATE = 16000


# ── SoundDevice AudioSource for SpeechRecognition ────────────────────────────

if _SR_AVAILABLE:
    class SoundDeviceMicrophone(sr.AudioSource):
        """
        Microphone audio source powered by sounddevice for robust, cross-platform,
        pyaudio-free audio capture compatible with Python 3.10 through 3.14+.
        """

        def __init__(
            self,
            device: int | str | None = None,
            sample_rate: int = _DEFAULT_SAMPLE_RATE,
            chunk_size: int = 1024,
            stop_event: threading.Event | None = None,
        ) -> None:
            # Do NOT call super().__init__() as sr.AudioSource.__init__ raises NotImplementedError
            self.device = device
            self.SAMPLE_RATE = sample_rate
            self.SAMPLE_WIDTH = 2  # 16-bit PCM (2 bytes per sample)
            self.CHUNK = chunk_size
            self._stop_event = stop_event
            self.stream: _SoundDeviceStreamWrapper | None = None
            self._sd_stream: Any | None = None
            self._queue: queue.Queue[bytes] = queue.Queue()

        def __enter__(self) -> "SoundDeviceMicrophone":
            self._queue = queue.Queue()

            def _audio_callback(indata, frames, time_info, status):
                if status:
                    pass  # Ignore overflow/underflow warnings
                self._queue.put(bytes(indata))

            try:
                self._sd_stream = sd.RawInputStream(
                    samplerate=self.SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=self.CHUNK,
                    device=self.device,
                    callback=_audio_callback,
                )
                self._sd_stream.start()
            except Exception:
                # Hardware fallback: if 16000 Hz is unsupported, query device default rate
                try:
                    dev_info = sd.query_devices(self.device, kind="input")
                    native_rate = int(dev_info.get("default_samplerate", 44100))
                    self.SAMPLE_RATE = native_rate
                except Exception:
                    self.SAMPLE_RATE = 44100

                self._sd_stream = sd.RawInputStream(
                    samplerate=self.SAMPLE_RATE,
                    channels=1,
                    dtype="int16",
                    blocksize=self.CHUNK,
                    device=self.device,
                    callback=_audio_callback,
                )
                self._sd_stream.start()

            self.stream = _SoundDeviceStreamWrapper(self._queue, self._stop_event)
            return self

        def __exit__(self, exc_type, exc_val, exc_tb) -> None:
            if self._sd_stream is not None:
                try:
                    self._sd_stream.stop()
                    self._sd_stream.close()
                except Exception:
                    pass
                self._sd_stream = None
            self.stream = None

    class _SoundDeviceStreamWrapper:
        """Stream wrapper delivering audio bytes with responsive shutdown."""

        def __init__(
            self,
            audio_queue: queue.Queue[bytes],
            stop_event: threading.Event | None = None,
        ) -> None:
            self._queue = audio_queue
            self._stop_event = stop_event

        def read(self, size: int) -> bytes:
            while True:
                if self._stop_event and self._stop_event.is_set():
                    return b""
                try:
                    return self._queue.get(timeout=0.15)
                except queue.Empty:
                    continue

        def close(self) -> None:
            pass

else:
    SoundDeviceMicrophone = None  # type: ignore[assignment, misc]


# ── String and Matching Helpers ──────────────────────────────────────────────

def _normalize_name(name: str) -> str:
    """Strip all non-alphanumeric characters and lowercase."""
    return re.sub(r"[^a-z0-9]", "", name.lower())


def _clean_utterance(text: str) -> str:
    """Remove punctuation, wake phrases, and introductory command words."""
    cleaned = text.lower()
    cleaned = re.sub(r"[,.!?\"\'\(\)\[\];:/\-_]", " ", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 1. Strip wake phrase if present (sorted longest first)
    for wp in sorted(_WAKE_PHRASES, key=len, reverse=True):
        if wp in cleaned:
            cleaned = cleaned.split(wp, 1)[1].strip()
            break

    # 2. Strip leading action verbs/keywords
    words = cleaned.split()
    while words and words[0] in _RUN_KEYWORDS:
        words = words[1:]
    cleaned = " ".join(words).strip()
    return cleaned


def _fuzzy_find(query: str, items: list[Any]) -> Any | None:
    """Return best-matching item for *query* by .name or None if nothing close enough."""
    if not items or not query:
        return None
    query_clean = query.lower().strip()
    query_norm = _normalize_name(query_clean)
    names = [getattr(m, "name", "").strip() for m in items]
    names_clean = [n.lower() for n in names]
    names_norm = [_normalize_name(n) for n in names]

    # 1. Exact match (case-insensitive)
    for idx, nc in enumerate(names_clean):
        if nc and nc == query_clean:
            return items[idx]

    # 2. Normalized match (ignoring spaces, dashes, underscores)
    if query_norm:
        for idx, nn in enumerate(names_norm):
            if nn and nn == query_norm:
                return items[idx]

    # 3. Substring match
    for idx, nc in enumerate(names_clean):
        if nc and (nc in query_clean or query_clean in nc):
            return items[idx]

    if query_norm:
        for idx, nn in enumerate(names_norm):
            if nn and (nn in query_norm or query_norm in nn):
                return items[idx]

    # 4. Fuzzy match with difflib (cutoff 0.60 ensures close similarity)
    matches = difflib.get_close_matches(query_clean, names_clean, n=1, cutoff=0.60)
    if matches:
        idx = names_clean.index(matches[0])
        return items[idx]

    return None


# ── Voice Trigger Engine ─────────────────────────────────────────────────────

class VoiceTrigger:
    """
    Background voice command listener.

    Parameters
    ----------
    macro_store : MacroStore
        Used to resolve macro names at match-time.
    on_match : Callable[[Macro], None]
        Called (from the listener thread!) when a voice command matches a macro.
    on_status : Callable[[str], None] | None
        Optional status callback.
        Messages: "listening", "processing", "matched:<name>:<text>",
                  "matched_workflow:<name>:<text>", "no_match:<text>",
                  "stopped", "unavailable", "calibrating", "error:<msg>"
    workflow_store : WorkflowStore | None
        Optional workflow store to resolve workflow names at match-time.
    on_workflow_match : Callable[[Workflow], None] | None
        Called when a voice command matches a saved workflow.
    energy_threshold : int
        Microphone sensitivity (default 300). Lower is more sensitive.
    phrase_time_limit : float
        Max seconds to listen per utterance (default 6.0).
    """

    def __init__(
        self,
        macro_store: "MacroStore",
        on_match: "Callable[[Macro], None]",
        on_status: "Callable[[str], None] | None" = None,
        workflow_store: "WorkflowStore | None" = None,
        on_workflow_match: "Callable[[Workflow], None] | None" = None,
        energy_threshold: int = 300,
        phrase_time_limit: float = 6.0,
    ) -> None:
        self._store = macro_store
        self._on_match = on_match
        self._on_status = on_status
        self._wf_store = workflow_store
        self._on_workflow_match = on_workflow_match
        self._energy_threshold = energy_threshold
        self._phrase_time_limit = phrase_time_limit

        self._enabled = True
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    # ── Public API ────────────────────────────────────────────────────────────

    @property
    def is_available(self) -> bool:
        """True if SpeechRecognition and an audio capture backend (sounddevice or pyaudio) are available."""
        return _SR_AVAILABLE and (_SD_AVAILABLE or _PYAUDIO_AVAILABLE)

    @property
    def is_running(self) -> bool:
        """True if the background listener thread is currently active."""
        return self._thread is not None and self._thread.is_alive()

    @property
    def is_enabled(self) -> bool:
        """True if voice triggering is enabled."""
        return self._enabled

    @is_enabled.setter
    def is_enabled(self, value: bool) -> None:
        self._enabled = bool(value)
        if not self._enabled and self.is_running:
            self.stop()
        elif self._enabled and not self.is_running and self.is_available:
            self.start()

    @property
    def energy_threshold(self) -> int:
        return self._energy_threshold

    @energy_threshold.setter
    def energy_threshold(self, value: int) -> None:
        self._energy_threshold = max(50, min(4000, int(value)))

    def start(self) -> bool:
        """Start the listener daemon thread. Returns False if unavailable."""
        if not self.is_available:
            self._emit_status("unavailable")
            return False
        if not self._enabled:
            return False
        if self.is_running:
            return True

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._listen_loop,
            daemon=True,
            name="VoiceTriggerThread",
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Request the listener thread to stop."""
        self._stop_event.set()
        # Thread will exit promptly as _SoundDeviceStreamWrapper responds to stop_event

    def test_listen(self, timeout: float = 4.0, phrase_time_limit: float = 4.0) -> tuple[bool, str]:
        """
        Record a single utterance synchronously and attempt recognition.
        Useful for UI microphone test dialogs. Returns (success, text_or_error).
        """
        if not self.is_available:
            return False, "Speech recognition backend not installed."

        recognizer = sr.Recognizer()
        recognizer.energy_threshold = self._energy_threshold
        recognizer.dynamic_energy_threshold = True

        stop_ev = threading.Event()
        if _SD_AVAILABLE:
            source_ctx = SoundDeviceMicrophone(stop_event=stop_ev)
        else:
            source_ctx = sr.Microphone()

        try:
            with source_ctx as source:
                recognizer.adjust_for_ambient_noise(source, duration=0.5)
                audio = recognizer.listen(
                    source,
                    timeout=timeout,
                    phrase_time_limit=phrase_time_limit,
                )
            text = recognizer.recognize_google(audio).strip()
            return True, text
        except sr.WaitTimeoutError:
            return False, "No speech detected (timed out)."
        except sr.UnknownValueError:
            return False, "Audio received, but words were not clear enough to recognize."
        except sr.RequestError as exc:
            return False, f"Speech recognition service network error: {exc}"
        except Exception as exc:
            return False, f"Microphone error: {exc}"

    # ── Internal ──────────────────────────────────────────────────────────────

    def _emit_status(self, msg: str) -> None:
        if self._on_status:
            try:
                self._on_status(msg)
            except Exception:
                pass

    def _listen_loop(self) -> None:
        """Continuously listen for spoken commands using SpeechRecognition with sounddevice."""
        try:
            recognizer = sr.Recognizer()
            recognizer.energy_threshold = self._energy_threshold
            recognizer.dynamic_energy_threshold = True
            recognizer.pause_threshold = 0.8
            recognizer.phrase_threshold = 0.3
            recognizer.non_speaking_duration = 0.5

            if _SD_AVAILABLE:
                source_ctx = SoundDeviceMicrophone(stop_event=self._stop_event)
            else:
                source_ctx = sr.Microphone()

            with source_ctx as source:
                self._emit_status("calibrating")
                try:
                    recognizer.adjust_for_ambient_noise(source, duration=0.8)
                except Exception:
                    pass

                while not self._stop_event.is_set():
                    self._emit_status("listening")
                    try:
                        # Blocks until speech is detected, or timeout occurs
                        audio = recognizer.listen(
                            source,
                            timeout=2.0,
                            phrase_time_limit=self._phrase_time_limit,
                        )
                    except sr.WaitTimeoutError:
                        continue
                    except Exception:
                        if self._stop_event.is_set():
                            break
                        time.sleep(0.2)
                        continue

                    if self._stop_event.is_set():
                        break

                    # Audio phrase captured! Recognize with Google STT
                    self._emit_status("processing")
                    try:
                        text = recognizer.recognize_google(audio).lower().strip()
                    except sr.UnknownValueError:
                        # Background noise or unintelligible sound
                        self._emit_status("listening")
                        continue
                    except sr.RequestError as exc:
                        self._emit_status(f"error:Network error — {exc}")
                        time.sleep(1.5)
                        continue
                    except Exception as exc:
                        self._emit_status(f"error:{exc}")
                        time.sleep(1.0)
                        continue

                    self._process_text(text)

        except Exception as exc:
            self._emit_status(f"error:{exc}")

        self._emit_status("stopped")

    def _process_text(self, text: str) -> None:
        """Parse the recognised text and fire on_match or on_workflow_match if a macro/workflow is found."""
        print(f"[VoiceTrigger] Transcribed audio: {text!r}")
        raw = text.lower().strip()
        cleaned = _clean_utterance(text)

        # Check if user specifically requested a workflow, e.g. "workflow daily report"
        is_workflow_explicit = "workflow" in raw or "work flow" in raw
        wf_candidate = cleaned.replace("workflow", "").replace("work flow", "").strip()
        candidate = cleaned if cleaned else raw

        # 1. If "workflow" was explicitly spoken, look up in workflow store first
        if is_workflow_explicit and self._wf_store and self._on_workflow_match:
            workflows = self._wf_store.list_all()
            wf = _fuzzy_find(wf_candidate, workflows) or _fuzzy_find(candidate, workflows) or _fuzzy_find(raw, workflows)
            if wf:
                print(f"[VoiceTrigger] Matched workflow '{wf.name}' from '{text}'")
                self._emit_status(f"matched_workflow:{wf.name}:{text}")
                try:
                    self._on_workflow_match(wf)
                except Exception as exc:
                    print(f"[VoiceTrigger] Error in workflow callback: {exc}")
                return

        # 2. Check macros in macro store
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
                print(f"[VoiceTrigger] Error in macro callback: {exc}")
            return

        # 3. Fallback: check workflows even if "workflow" wasn't explicitly spoken
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
