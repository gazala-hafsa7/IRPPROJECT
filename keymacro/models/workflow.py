"""
keymacro/models/workflow.py
───────────────────────────
Workflow data model — a directed graph of macro steps with conditional edges.

A Workflow chains multiple saved Macros together with pass/fail conditions:

    [Node A: macro_id] --on_success--> [Node B: macro_id]
                       --on_failure--> [Node C: macro_id]

Serialisation: JSON files in %APPDATA%\\KeyMacro\\workflows\\
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class WorkflowNode:
    """A single step in a workflow — wraps one saved Macro by ID."""

    node_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    macro_id: str = ""                   # references MacroStore
    macro_name: str = ""                 # cached for display without store lookup
    # Edges — node_id of next node, or "" to terminate
    next_on_success: str = ""
    next_on_failure: str = ""
    # Visual position on the canvas (pixels)
    x: float = 0.0
    y: float = 0.0

    def to_dict(self) -> dict[str, Any]:
        return {
            "node_id":         self.node_id,
            "macro_id":        self.macro_id,
            "macro_name":      self.macro_name,
            "next_on_success": self.next_on_success,
            "next_on_failure": self.next_on_failure,
            "x":               self.x,
            "y":               self.y,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "WorkflowNode":
        return cls(
            node_id=d.get("node_id", str(uuid.uuid4())),
            macro_id=d.get("macro_id", ""),
            macro_name=d.get("macro_name", ""),
            next_on_success=d.get("next_on_success", ""),
            next_on_failure=d.get("next_on_failure", ""),
            x=d.get("x", 0.0),
            y=d.get("y", 0.0),
        )


@dataclass
class Workflow:
    """Ordered, conditional chain of KeyMacro macros."""

    name: str
    nodes: list[WorkflowNode] = field(default_factory=list)
    entry_node_id: str = ""              # ID of the first node to execute
    description: str = ""
    hotkey: str = ""                     # Global shortcut, e.g. "ctrl + shift + w"
    workflow_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    created_at: str = field(default_factory=_now_iso)
    modified_at: str = field(default_factory=_now_iso)

    # ── Convenience ──────────────────────────────────────────────────────────

    def node_by_id(self, node_id: str) -> WorkflowNode | None:
        for n in self.nodes:
            if n.node_id == node_id:
                return n
        return None

    def add_node(self, node: WorkflowNode) -> None:
        self.nodes.append(node)
        if not self.entry_node_id:
            self.entry_node_id = node.node_id
        self.touch()

    def remove_node(self, node_id: str) -> None:
        self.nodes = [n for n in self.nodes if n.node_id != node_id]
        # Patch dangling edges
        for n in self.nodes:
            if n.next_on_success == node_id:
                n.next_on_success = ""
            if n.next_on_failure == node_id:
                n.next_on_failure = ""
        if self.entry_node_id == node_id:
            self.entry_node_id = self.nodes[0].node_id if self.nodes else ""
        self.touch()

    def touch(self) -> None:
        self.modified_at = _now_iso()

    # ── Serialisation ────────────────────────────────────────────────────────

    def to_dict(self) -> dict[str, Any]:
        return {
            "workflow_id":   self.workflow_id,
            "name":          self.name,
            "description":   self.description,
            "hotkey":        self.hotkey,
            "entry_node_id": self.entry_node_id,
            "created_at":    self.created_at,
            "modified_at":   self.modified_at,
            "nodes":         [n.to_dict() for n in self.nodes],
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Workflow":
        return cls(
            workflow_id=d.get("workflow_id", str(uuid.uuid4())),
            name=d["name"],
            description=d.get("description", ""),
            hotkey=d.get("hotkey", ""),
            entry_node_id=d.get("entry_node_id", ""),
            created_at=d.get("created_at", _now_iso()),
            modified_at=d.get("modified_at", _now_iso()),
            nodes=[WorkflowNode.from_dict(n) for n in d.get("nodes", [])],
        )
