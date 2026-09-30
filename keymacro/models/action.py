"""
keymacro/models/action.py
─────────────────────────
Shared data model for KeyMacro.

All modules (recorder, replay engine, safety layer, GUI, storage) import from
here.  Nothing in this file has external dependencies — pure stdlib only.

Classes
-------
ActionType   : enum of every recordable/replayable action kind
RiskLevel    : LOW / MEDIUM / HIGH
Action       : a single step in a macro (type + params + metadata)
Macro        : an ordered sequence of Actions with a name and hotkey
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum, auto
from typing import Any


# ──────────────────────────────────────────────
# Enumerations
# ──────────────────────────────────────────────

class ActionType(str, Enum):
    """Every kind of action that KeyMacro can record or replay."""

    # Keyboard
    KEY_PRESS    = "key_press"     # press a single key down
    KEY_RELEASE  = "key_release"   # release a single key
    KEY_COMBO    = "key_combo"     # hotkey combination (e.g. Ctrl+C)
    TYPE_TEXT    = "type_text"     # type a string of characters

    # Mouse
    MOUSE_MOVE   = "mouse_move"    # absolute screen position
    MOUSE_CLICK  = "mouse_click"   # click at (x, y) with button + count
    MOUSE_SCROLL = "mouse_scroll"  # scroll wheel at (x, y)
    MOUSE_DRAG   = "mouse_drag"    # drag from (x1,y1) to (x2,y2)

    # Timing
    DELAY        = "delay"         # pause for N milliseconds

    # Application launch & Plugins
    LAUNCH_APP    = "launch_app"    # open an exe, file, or URL via os.startfile
    PLUGIN_ACTION = "plugin_action" # invoke an installed app plugin action

    # File-system  ← always HIGH risk
    FILE_DELETE   = "file_delete"
    FILE_MOVE     = "file_move"
    FILE_COPY     = "file_copy"


class RiskLevel(str, Enum):
    """Risk level assigned to an action or a whole macro."""

    LOW    = "low"     # safe to run without confirmation
    MEDIUM = "medium"  # informational warning shown
    HIGH   = "high"    # always requires confirmation + backup


# ──────────────────────────────────────────────
# Inherent risk of each action type
# ──────────────────────────────────────────────

ACTION_RISK: dict[ActionType, RiskLevel] = {
    ActionType.KEY_PRESS:    RiskLevel.LOW,
    ActionType.KEY_RELEASE:  RiskLevel.LOW,
    ActionType.KEY_COMBO:    RiskLevel.MEDIUM,   # could be Ctrl+Z, Win+D, etc.
    ActionType.TYPE_TEXT:    RiskLevel.LOW,
    ActionType.MOUSE_MOVE:   RiskLevel.LOW,
    ActionType.MOUSE_CLICK:  RiskLevel.LOW,
    ActionType.MOUSE_SCROLL: RiskLevel.LOW,
    ActionType.MOUSE_DRAG:   RiskLevel.LOW,
    ActionType.DELAY:        RiskLevel.LOW,
    ActionType.LAUNCH_APP:   RiskLevel.LOW,
    ActionType.PLUGIN_ACTION: RiskLevel.LOW,
    ActionType.FILE_DELETE:  RiskLevel.HIGH,
    ActionType.FILE_MOVE:    RiskLevel.HIGH,
    ActionType.FILE_COPY:    RiskLevel.HIGH,
}

# Params schema (documentation only — not enforced at runtime for speed)
# KEY_PRESS    / KEY_RELEASE : {"key": str}               e.g. "a", "ctrl", "f5"
# KEY_COMBO                  : {"keys": [str, ...]}       e.g. ["ctrl", "c"]
# TYPE_TEXT                  : {"text": str}
# MOUSE_MOVE                 : {"x": int, "y": int}
# MOUSE_CLICK                : {"x": int, "y": int, "button": str, "clicks": int}
# MOUSE_SCROLL               : {"x": int, "y": int, "dx": int, "dy": int}
# MOUSE_DRAG                 : {"x1": int, "y1": int, "x2": int, "y2": int, "button": str, "duration": float}
# DELAY                      : {"ms": int}
# LAUNCH_APP                 : {"target": str}            e.g. "chrome.exe" or "https://google.com"
# PLUGIN_ACTION              : {"plugin_id": str, "action_id": str, "params": dict}
# FILE_DELETE                : {"path": str}
# FILE_MOVE                  : {"src": str, "dst": str}
# FILE_COPY                  : {"src": str, "dst": str}


# ──────────────────────────────────────────────
# Core dataclasses
# ──────────────────────────────────────────────

@dataclass
class Action:
    """A single step in a macro.

    Attributes
    ----------
    action_type : ActionType
        What kind of action this is.
    params : dict[str, Any]
        Action-specific parameters (see schema comment above).
    risk_level : RiskLevel
        Risk assigned at creation time (usually from ACTION_RISK, but can be
        overridden — e.g. safety layer may escalate a KEY_COMBO to HIGH).
    description : str
        Human-readable summary shown in the GUI and confirmation dialogs.
    action_id : str
        Stable UUID for this action (generated automatically).
    timestamp_ms : float
        Wall-clock time (ms since epoch) when the action was recorded.
        0.0 if the action was created manually rather than recorded.
    """

    action_type:  ActionType
    params:       dict[str, Any]
    risk_level:   RiskLevel = RiskLevel.LOW
    description:  str       = ""
    action_id:    str       = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp_ms: float     = 0.0

    def __post_init__(self) -> None:
        # Auto-set risk level from the type table if caller left it as default
        if self.risk_level == RiskLevel.LOW and self.action_type in ACTION_RISK:
            self.risk_level = ACTION_RISK[self.action_type]
        # Auto-generate a human description if caller left it blank
        if not self.description:
            self.description = _describe(self.action_type, self.params)

    # ── serialisation ──────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_id":    self.action_id,
            "action_type":  self.action_type.value,
            "params":       self.params,
            "risk_level":   self.risk_level.value,
            "description":  self.description,
            "timestamp_ms": self.timestamp_ms,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Action":
        return cls(
            action_id    = data.get("action_id", str(uuid.uuid4())),
            action_type  = ActionType(data["action_type"]),
            params       = data.get("params", {}),
            risk_level   = RiskLevel(data.get("risk_level", RiskLevel.LOW.value)),
            description  = data.get("description", ""),
            timestamp_ms = data.get("timestamp_ms", 0.0),
        )


@dataclass
class Macro:
    """An ordered sequence of Actions that can be saved, loaded, and replayed.

    Attributes
    ----------
    name : str
        Display name shown in the GUI macro list.
    actions : list[Action]
        Ordered steps; replayed top-to-bottom.
    hotkey : str
        pynput GlobalHotKeys format, e.g. ``"<ctrl>+<shift>+F5"``.
        Empty string means no hotkey is assigned.
    description : str
        Optional freetext notes.
    macro_id : str
        Stable UUID used as the JSON filename.
    created_at : str
        ISO-8601 UTC timestamp of creation.
    modified_at : str
        ISO-8601 UTC timestamp of last save.
    """

    name:        str
    actions:     list[Action] = field(default_factory=list)
    hotkey:      str          = ""
    target_app:  str          = ""
    description: str          = ""
    macro_id:    str          = field(default_factory=lambda: str(uuid.uuid4()))
    created_at:  str          = field(default_factory=lambda: _now_iso())
    modified_at: str          = field(default_factory=lambda: _now_iso())

    # ── convenience ────────────────────────────────

    @property
    def risk_level(self) -> RiskLevel:
        """Aggregate risk of the macro — worst-case of all its actions."""
        if not self.actions:
            return RiskLevel.LOW
        order = {RiskLevel.LOW: 0, RiskLevel.MEDIUM: 1, RiskLevel.HIGH: 2}
        return max(self.actions, key=lambda a: order[a.risk_level]).risk_level

    @property
    def action_count(self) -> int:
        return len(self.actions)

    def touch(self) -> None:
        """Update modified_at to now."""
        self.modified_at = _now_iso()

    # ── serialisation ──────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro_id":    self.macro_id,
            "name":        self.name,
            "description": self.description,
            "hotkey":      self.hotkey,
            "target_app":  self.target_app,
            "created_at":  self.created_at,
            "modified_at": self.modified_at,
            "actions":     [a.to_dict() for a in self.actions],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Macro":
        return cls(
            macro_id    = data.get("macro_id", str(uuid.uuid4())),
            name        = data["name"],
            description = data.get("description", ""),
            hotkey      = data.get("hotkey", ""),
            target_app  = data.get("target_app", ""),
            created_at  = data.get("created_at", _now_iso()),
            modified_at = data.get("modified_at", _now_iso()),
            actions     = [Action.from_dict(a) for a in data.get("actions", [])],
        )


# ──────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _describe(action_type: ActionType, params: dict[str, Any]) -> str:
    """Generate a short human-readable description for an action."""
    match action_type:
        case ActionType.KEY_PRESS:
            return f"Press key: {params.get('key', '?')}"
        case ActionType.KEY_RELEASE:
            return f"Release key: {params.get('key', '?')}"
        case ActionType.KEY_COMBO:
            keys = " + ".join(params.get("keys", []))
            return f"Key combo: {keys}"
        case ActionType.TYPE_TEXT:
            text = params.get("text", "")
            preview = (text[:30] + "…") if len(text) > 30 else text
            return f'Type: "{preview}"'
        case ActionType.MOUSE_MOVE:
            return f"Move mouse to ({params.get('x')}, {params.get('y')})"
        case ActionType.MOUSE_CLICK:
            btn = params.get("button", "left")
            n   = params.get("clicks", 1)
            x, y = params.get("x"), params.get("y")
            return f"{'Double-click' if n == 2 else 'Click'} {btn} at ({x}, {y})"
        case ActionType.MOUSE_SCROLL:
            dy = params.get("dy", 0)
            return f"Scroll {'up' if dy > 0 else 'down'} at ({params.get('x')}, {params.get('y')})"
        case ActionType.MOUSE_DRAG:
            return (f"Drag from ({params.get('x1')}, {params.get('y1')}) "
                    f"to ({params.get('x2')}, {params.get('y2')})")
        case ActionType.DELAY:
            return f"Wait {params.get('ms', 0)} ms"
        case ActionType.LAUNCH_APP:
            return f"Launch: {params.get('target', '?')}"
        case ActionType.PLUGIN_ACTION:
            plug = params.get('plugin_id', '?')
            act = params.get('action_id', '?')
            p_args = params.get('params', {})
            arg_str = f"({', '.join(f'{k}={v}' for k, v in p_args.items())})" if p_args else "()"
            return f"Plugin: {plug}.{act}{arg_str}"
        case ActionType.FILE_DELETE:
            return f"⚠ DELETE file: {params.get('path', '?')}"
        case ActionType.FILE_MOVE:
            return f"⚠ MOVE {params.get('src', '?')} → {params.get('dst', '?')}"
        case ActionType.FILE_COPY:
            return f"Copy {params.get('src', '?')} → {params.get('dst', '?')}"
        case _:
            return str(action_type)
