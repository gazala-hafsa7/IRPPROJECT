"""
keymacro/ai/macro_generator.py
────────────────────────────────
AI Macro Generator — converts a plain-English description into a valid
KeyMacro sequence script using the Google Gemini API (gemini-1.5-flash, free tier).

No API key required for the free tier when using google-generativeai SDK.
User provides their own GEMINI_API_KEY via Settings or env variable.

Dependencies:
    pip install google-generativeai

Usage
-----
    gen = MacroGenerator(api_key="AIza...")
    script = gen.generate("open chrome, search for python tutorials, wait 2 seconds")
    # Returns a valid sequence script string, ready to paste into the builder.
"""

from __future__ import annotations

import threading
from typing import Callable

# ── optional import ───────────────────────────────────────────────────────────
try:
    import google.generativeai as genai
    _GENAI_AVAILABLE = True
except ImportError:
    _GENAI_AVAILABLE = False

# ── Sequence syntax reference injected into the prompt ───────────────────────
_SYNTAX_GUIDE = """\
KeyMacro Sequence Syntax (one action per line):
  combo: ctrl+c              # key combination
  combo: ctrl+shift+t        # multiple modifiers
  type: Hello World          # type text literally
  wait: 500ms                # pause (ms or s)
  click: 400,300             # left-click at screen coords
  launch: "notepad.exe"      # open an application
  launch: "https://url.com"  # open a URL
  plugin: browser.open_url url=https://example.com
  plugin: browser.search query=python tutorials engine=google
  plugin: system.screenshot
  plugin: system.volume_up steps=3
  plugin: media.play_pause
  plugin: media.next_track
  # This is a comment

Rules:
- Output ONLY the sequence script, no explanation.
- Use 'wait: 1s' after launch actions to let apps load.
- Use 'plugin: browser.open_url' instead of 'launch' for URLs.
- Never use placeholder coords; use realistic values or omit click if coord unknown.
- Comments starting with # are allowed and encouraged for readability.
"""

_SYSTEM_PROMPT = (
    "You are KeyMacro AI, an expert at generating Windows desktop automation scripts. "
    "Given a plain-English task description, output a valid KeyMacro sequence script. "
    "Output ONLY the script — no markdown fences, no explanations, no extra text.\n\n"
    + _SYNTAX_GUIDE
)


class MacroGeneratorError(Exception):
    """Raised when generation fails."""


class MacroGenerator:
    """
    Converts plain-English descriptions to KeyMacro sequence scripts via Gemini.

    Parameters
    ----------
    api_key : str
        Your Google Gemini API key (https://aistudio.google.com/app/apikey).
    model : str
        Gemini model name. Default: "gemini-1.5-flash" (fast, free tier).
    """

    def __init__(self, api_key: str, model: str = "gemini-1.5-flash") -> None:
        self._api_key = api_key
        self._model_name = model
        self._client = None

    @property
    def is_available(self) -> bool:
        return _GENAI_AVAILABLE and bool(self._api_key)

    def _get_client(self):
        """Lazy-init Gemini client."""
        if not _GENAI_AVAILABLE:
            raise MacroGeneratorError(
                "google-generativeai is not installed.\n"
                "Run: pip install google-generativeai"
            )
        if self._client is None:
            genai.configure(api_key=self._api_key)
            self._client = genai.GenerativeModel(
                model_name=self._model_name,
                system_instruction=_SYSTEM_PROMPT,
            )
        return self._client

    def generate(self, description: str) -> str:
        """
        Synchronously generate a sequence script from *description*.

        Returns
        -------
        str
            The generated KeyMacro sequence script.

        Raises
        ------
        MacroGeneratorError
            On any API or network error.
        """
        if not description.strip():
            raise MacroGeneratorError("Description is empty.")

        try:
            client = self._get_client()
            response = client.generate_content(
                f"Task: {description.strip()}",
                generation_config={
                    "temperature": 0.3,
                    "max_output_tokens": 512,
                },
            )
            text = response.text.strip()
            # Strip accidental markdown fences
            if text.startswith("```"):
                lines = text.splitlines()
                # Remove first and last fence lines
                lines = [l for l in lines if not l.startswith("```")]
                text = "\n".join(lines).strip()
            return text
        except MacroGeneratorError:
            raise
        except Exception as exc:
            raise MacroGeneratorError(f"Gemini API error: {exc}") from exc

    def generate_async(
        self,
        description: str,
        on_result: "Callable[[str], None]",
        on_error: "Callable[[str], None]",
    ) -> None:
        """
        Asynchronously generate a script in a daemon thread.

        Parameters
        ----------
        on_result : Callable[[str], None]
            Called with the generated script on success.
        on_error : Callable[[str], None]
            Called with an error message string on failure.
        """
        def _worker():
            try:
                script = self.generate(description)
                on_result(script)
            except MacroGeneratorError as exc:
                on_error(str(exc))
            except Exception as exc:
                on_error(f"Unexpected error: {exc}")

        threading.Thread(target=_worker, daemon=True, name="AIGeneratorThread").start()
