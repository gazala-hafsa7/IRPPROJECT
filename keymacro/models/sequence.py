"""
keymacro/models/sequence.py
───────────────────────────
Concise macro sequence parser and serializer.

Translates human-readable, line-by-line instruction sequences into Action objects
(and vice versa), eliminating the need to capture raw timing delays or write
cryptic AutoHotkey scripts.

Syntax Rules
────────────
- Blank lines and lines starting with '#' are ignored.
- Keystrokes & Combos:
    combo: ctrl+shift+esc      (or simply: ctrl+c, alt+f4, etc.)
    press: enter               (or: key: enter)
    release: shift
- Text:
    type: Hello, World!        (types text directly)
- Mouse:
    click: 500, 300            (left click at coordinates)
    click: right, 500, 300     (right click)
    double_click: 500, 300     (double click)
    move: 500, 300             (move mouse)
    drag: 100, 200 -> 500, 400 (drag cursor)
    scroll: up                 (or: scroll: 5, scroll: -5, scroll: down)
- App Launch:
    launch: notepad.exe        (or: launch: chrome, open: calc)
- Plugins:
    plugin: browser.open_url url=https://example.com
    plugin: system.volume_mute
- Optional Wait / Delay:
    wait: 300ms                (or: delay: 1s, sleep: 500ms)
"""

from __future__ import annotations

import re
import shlex
from typing import Any

from keymacro.models.action import Action, ActionType, RiskLevel


class SequenceParseError(Exception):
    """Raised when a sequence line cannot be parsed."""

    def __init__(self, line_num: int, line_text: str, message: str) -> None:
        super().__init__(f"Line {line_num}: {message} -> '{line_text}'")
        self.line_num = line_num
        self.line_text = line_text
        self.message = message


# Standard special key names recognised in shortcuts
_KNOWN_KEYS = {
    "enter", "return", "tab", "space", "backspace", "delete", "esc", "escape",
    "home", "end", "page_up", "page_down", "pageup", "pagedown", "up", "down",
    "left", "right", "insert", "print_screen", "pause", "caps_lock",
    "ctrl", "ctrl_l", "ctrl_r", "shift", "shift_l", "shift_r", "alt", "alt_l",
    "alt_r", "win", "cmd", "cmd_l", "cmd_r",
    *(f"f{i}" for i in range(1, 25)),
}


def parse_sequence_with_metadata(text: str) -> tuple[list[Action], dict[str, str]]:
    """Parse concise sequence text into (actions, metadata_dict).

    Metadata directives supported at line start:
    - `# target_app: chrome.exe` or `target_app: chrome.exe`
    - `# hotkey: ctrl+o+g` or `hotkey: ctrl+o+g`
    """
    actions: list[Action] = []
    metadata: dict[str, str] = {}
    lines = text.splitlines()

    for idx, raw_line in enumerate(lines, 1):
        line = raw_line.strip()
        if not line:
            continue

        clean_comment = line.lstrip("#").strip()
        if ":" in clean_comment:
            k, _, v = clean_comment.partition(":")
            k_clean = k.strip().lower()
            if k_clean in ("target_app", "targetapp", "target_application"):
                metadata["target_app"] = v.strip()
                continue
            if k_clean in ("hotkey", "shortcut"):
                metadata["hotkey"] = v.strip()
                continue

        if line.startswith("#"):
            continue

        try:
            action = _parse_line(line)
            if action:
                actions.append(action)
        except Exception as exc:
            if isinstance(exc, SequenceParseError):
                raise
            raise SequenceParseError(idx, raw_line, str(exc)) from exc

    # If hotkey wasn't set explicitly via metadata directive, but first action is KEY_COMBO, record it in metadata
    if "hotkey" not in metadata and actions and actions[0].action_type == ActionType.KEY_COMBO:
        metadata["hotkey"] = " + ".join(actions[0].params.get("keys", []))

    return actions, metadata


def parse_sequence(text: str) -> list[Action]:
    """Parse concise sequence text into a list of Action objects.

    Raises
    ------
    SequenceParseError: if any non-empty line has invalid syntax.
    """
    actions, _ = parse_sequence_with_metadata(text)
    return actions


def _parse_line(line: str) -> Action:
    # 1. Check for command prefixes: <cmd>: <args>
    if ":" in line:
        cmd, _, rest = line.partition(":")
        cmd = cmd.strip().lower()
        args = rest.strip()
    else:
        cmd = ""
        args = line

    # ── KEY COMBOS ──────────────────────────────
    if cmd in ("combo", "hotkey", "keys"):
        return _make_combo_action(args)

    # Bare combo detection, e.g. "ctrl+c", "ctrl+shift+f5", "alt+tab"
    if "+" in line and not cmd:
        return _make_combo_action(line)

    # ── SINGLE KEYS ─────────────────────────────
    if cmd in ("press", "key", "keydown"):
        return _make_key_action(ActionType.KEY_PRESS, args)

    if cmd in ("release", "keyup"):
        return _make_key_action(ActionType.KEY_RELEASE, args)

    # Bare single key match if it's a known standalone key (e.g. "enter", "f5", "esc")
    if not cmd and line.lower() in _KNOWN_KEYS:
        return _make_key_action(ActionType.KEY_PRESS, line.lower())

    # ── TEXT TYPING ─────────────────────────────
    if cmd in ("type", "text", "write", "input"):
        # Strip surrounding quotes if present
        text_val = args
        if (text_val.startswith('"') and text_val.endswith('"')) or \
           (text_val.startswith("'") and text_val.endswith("'")):
            text_val = text_val[1:-1]
        return Action(
            action_type=ActionType.TYPE_TEXT,
            params={"text": text_val},
            description=f'Type: "{text_val}"',
        )

    # ── APPLICATION LAUNCH ──────────────────────
    if cmd in ("launch", "open", "app", "run"):
        target = args.strip().strip('"\'')
        if not target:
            raise ValueError("Launch target cannot be empty")
        return Action(
            action_type=ActionType.LAUNCH_APP,
            params={"target": target},
            description=f"Launch: {target}",
        )

    # ── PLUGIN ACTIONS ──────────────────────────
    if cmd == "plugin":
        return _parse_plugin_action(args)

    # ── MOUSE CLICKS ────────────────────────────
    if cmd in ("click", "mouse_click", "mouse"):
        return _parse_click(args, default_button="left", clicks=1)

    if cmd in ("right_click", "rclick"):
        return _parse_click(args, default_button="right", clicks=1)

    if cmd in ("double_click", "dblclick"):
        return _parse_click(args, default_button="left", clicks=2)

    if cmd in ("middle_click", "middleclick", "mclick"):
        return _parse_click(args, default_button="middle", clicks=1)

    # ── MOUSE MOVES ─────────────────────────────
    if cmd in ("move", "mouse_move"):
        x, y = _parse_xy(args)
        return Action(
            action_type=ActionType.MOUSE_MOVE,
            params={"x": x, "y": y},
            description=f"Move mouse to ({x}, {y})",
        )

    # ── MOUSE DRAG ──────────────────────────────
    if cmd in ("drag", "mouse_drag"):
        return _parse_drag(args)

    # ── MOUSE SCROLL ────────────────────────────
    if cmd in ("scroll", "mouse_scroll"):
        return _parse_scroll(args)

    # ── DELAY / WAIT ────────────────────────────
    if cmd in ("wait", "delay", "sleep", "pause"):
        ms = _parse_duration_ms(args)
        return Action(
            action_type=ActionType.DELAY,
            params={"ms": ms},
            description=f"Wait {ms} ms",
        )

    # If nothing matched
    raise ValueError(f"Unrecognised command or syntax: '{line}'")


# ── Internal parsing helpers ──────────────────────────────────────────────────

def _make_combo_action(keys_str: str) -> Action:
    parts = [k.strip().lower() for k in keys_str.split("+") if k.strip()]
    if not parts:
        raise ValueError("Key combo cannot be empty")
    return Action(
        action_type=ActionType.KEY_COMBO,
        params={"keys": parts},
        description=f"Key combo: {' + '.join(parts)}",
    )


def _make_key_action(action_type: ActionType, key_str: str) -> Action:
    key_name = key_str.strip().lower()
    if not key_name:
        raise ValueError("Key name cannot be empty")
    verb = "Press" if action_type == ActionType.KEY_PRESS else "Release"
    return Action(
        action_type=action_type,
        params={"key": key_name},
        description=f"{verb} key: {key_name}",
    )


def _parse_plugin_action(args: str) -> Action:
    """Parse 'plugin_id.action_id key1=val1 key2=val2'."""
    parts = shlex.split(args)
    if not parts:
        raise ValueError("Plugin action identifier required (e.g. browser.open_url)")

    target = parts[0]
    if "." not in target:
        raise ValueError(
            f"Plugin target must be 'plugin_id.action_id', got '{target}'"
        )
    plugin_id, _, action_id = target.partition(".")

    params: dict[str, Any] = {}
    for item in parts[1:]:
        if "=" in item:
            k, _, v = item.partition("=")
            params[k.strip()] = v.strip()
        else:
            params["arg"] = item

    return Action(
        action_type=ActionType.PLUGIN_ACTION,
        params={
            "plugin_id": plugin_id.strip(),
            "action_id": action_id.strip(),
            "params": params,
        },
    )


def _parse_click(args: str, default_button: str = "left", clicks: int = 1) -> Action:
    """Parse click arguments: e.g. '500, 300' or 'right, 500, 300'."""
    button = default_button
    tokens = [t.strip() for t in args.replace(" ", ",").split(",") if t.strip()]

    # check if first token is a button name
    if tokens and tokens[0].lower() in ("left", "right", "middle"):
        button = tokens.pop(0).lower()

    if len(tokens) >= 2:
        x, y = int(tokens[0]), int(tokens[1])
    elif len(tokens) == 0:
        # Default or current cursor position: 0, 0
        x, y = 0, 0
    else:
        raise ValueError(f"Expected x, y coordinates for click, got '{args}'")

    verb = "Double-click" if clicks == 2 else "Click"
    return Action(
        action_type=ActionType.MOUSE_CLICK,
        params={"x": x, "y": y, "button": button, "clicks": clicks},
        description=f"{verb} {button} at ({x}, {y})",
    )


def _parse_xy(args: str) -> tuple[int, int]:
    tokens = [t.strip() for t in args.replace(" ", ",").split(",") if t.strip()]
    if len(tokens) < 2:
        raise ValueError(f"Expected 'x, y' coordinates, got '{args}'")
    return int(tokens[0]), int(tokens[1])


def _parse_drag(args: str) -> Action:
    # Syntax: "100, 200 -> 300, 400" or "100, 200, 300, 400"
    if "->" in args:
        src, _, dst = args.partition("->")
        x1, y1 = _parse_xy(src)
        x2, y2 = _parse_xy(dst)
    else:
        tokens = [int(t.strip()) for t in args.replace(" ", ",").split(",") if t.strip()]
        if len(tokens) < 4:
            raise ValueError(f"Expected 'x1, y1 -> x2, y2' for drag, got '{args}'")
        x1, y1, x2, y2 = tokens[:4]

    return Action(
        action_type=ActionType.MOUSE_DRAG,
        params={"x1": x1, "y1": y1, "x2": x2, "y2": y2, "button": "left", "duration": 0.3},
        description=f"Drag from ({x1}, {y1}) to ({x2}, {y2})",
    )


def _parse_scroll(args: str) -> Action:
    val = args.strip().lower()
    dy = 3
    if val in ("up", "+"):
        dy = 5
    elif val in ("down", "-"):
        dy = -5
    else:
        try:
            dy = int(val)
        except ValueError:
            raise ValueError(f"Invalid scroll value: '{args}' (use 'up', 'down', or number)") from None

    return Action(
        action_type=ActionType.MOUSE_SCROLL,
        params={"x": 0, "y": 0, "dx": 0, "dy": dy},
        description=f"Scroll {'up' if dy > 0 else 'down'} ({dy})",
    )


def _parse_duration_ms(args: str) -> int:
    val = args.strip().lower()
    match = re.match(r"^([\d.]+)\s*(ms|s|m|sec|secs|second|seconds|millis)?$", val)
    if not match:
        raise ValueError(f"Invalid wait/delay duration: '{args}' (e.g. 500ms, 1.5s)")

    num = float(match.group(1))
    unit = match.group(2) or "ms"

    if unit.startswith("s"):
        return int(num * 1000)
    if unit.startswith("m") and not unit.startswith("ms"):
        return int(num * 60000)
    return int(num)


# ── Serializer ────────────────────────────────────────────────────────────────

def serialize_sequence(actions: list[Action], target_app: str = "", hotkey: str = "") -> str:
    """Convert a list of Action objects back to concise sequence text."""
    lines: list[str] = []
    if hotkey.strip():
        lines.append(f"# hotkey: {hotkey.strip()}")
    if target_app.strip():
        lines.append(f"# target_app: {target_app.strip()}")

    for action in actions:
        p = action.params
        match action.action_type:
            case ActionType.KEY_COMBO:
                keys = " + ".join(p.get("keys", []))
                lines.append(f"combo: {keys}")

            case ActionType.KEY_PRESS:
                lines.append(f"press: {p.get('key', '')}")

            case ActionType.KEY_RELEASE:
                lines.append(f"release: {p.get('key', '')}")

            case ActionType.TYPE_TEXT:
                lines.append(f"type: {p.get('text', '')}")

            case ActionType.MOUSE_CLICK:
                btn = p.get("button", "left")
                clicks = p.get("clicks", 1)
                x = p.get("x", 0)
                y = p.get("y", 0)
                if clicks == 2:
                    lines.append(f"double_click: {x}, {y}")
                elif btn == "right":
                    lines.append(f"right_click: {x}, {y}")
                elif btn == "middle":
                    lines.append(f"middle_click: {x}, {y}")
                else:
                    lines.append(f"click: {x}, {y}")

            case ActionType.MOUSE_MOVE:
                lines.append(f"move: {p.get('x', 0)}, {p.get('y', 0)}")

            case ActionType.MOUSE_DRAG:
                lines.append(
                    f"drag: {p.get('x1', 0)}, {p.get('y1', 0)} -> "
                    f"{p.get('x2', 0)}, {p.get('y2', 0)}"
                )

            case ActionType.MOUSE_SCROLL:
                dy = p.get("dy", 0)
                lines.append(f"scroll: {'up' if dy > 0 else 'down'}")

            case ActionType.DELAY:
                lines.append(f"wait: {p.get('ms', 0)}ms")

            case ActionType.LAUNCH_APP:
                lines.append(f"launch: {p.get('target', '')}")

            case ActionType.PLUGIN_ACTION:
                plug = p.get("plugin_id", "")
                act = p.get("action_id", "")
                args_dict = p.get("params", {})
                arg_str = " ".join(f'{k}="{v}"' if " " in str(v) else f"{k}={v}"
                                   for k, v in args_dict.items())
                if arg_str:
                    lines.append(f"plugin: {plug}.{act} {arg_str}")
                else:
                    lines.append(f"plugin: {plug}.{act}")

            case _:
                # Fallback for file-system or other actions
                lines.append(f"# {action.description}")

    return "\n".join(lines)


# ── Delay Utilities ───────────────────────────────────────────────────────────

def strip_delays(actions: list[Action]) -> list[Action]:
    """Remove all DELAY actions from an action list for instant execution."""
    return [a for a in actions if a.action_type != ActionType.DELAY]


def normalize_delays(actions: list[Action], fixed_ms: int = 50) -> list[Action]:
    """Replace recording delays with a fixed, consistent delay duration."""
    result: list[Action] = []
    for a in actions:
        if a.action_type == ActionType.DELAY:
            result.append(Action(
                action_type=ActionType.DELAY,
                params={"ms": fixed_ms},
                description=f"Wait {fixed_ms} ms",
            ))
        else:
            result.append(a)
    return result
