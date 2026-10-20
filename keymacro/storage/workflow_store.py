"""
keymacro/storage/workflow_store.py
────────────────────────────────────
JSON persistence for Workflow objects in %APPDATA%\\KeyMacro\\workflows\\
Mirrors the same pattern as MacroStore.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterator

from keymacro.models.workflow import Workflow

log = logging.getLogger(__name__)


class WorkflowStore:
    """Load, save, and enumerate Workflow objects from a local directory."""

    def __init__(self, workflows_dir: Path | None = None) -> None:
        if workflows_dir is None:
            import os
            appdata = os.environ.get("APPDATA", str(Path.home()))
            workflows_dir = Path(appdata) / "KeyMacro" / "workflows"
        self.workflows_dir = Path(workflows_dir)
        self.workflows_dir.mkdir(parents=True, exist_ok=True)

    # ── CRUD ──────────────────────────────────────────────────────────────────

    def save(self, workflow: Workflow) -> None:
        """Persist workflow to <workflow_id>.json."""
        workflow.touch()
        path = self.workflows_dir / f"{workflow.workflow_id}.json"
        with open(path, "w", encoding="utf-8") as f:
            json.dump(workflow.to_dict(), f, indent=2, ensure_ascii=False)
        log.debug("WorkflowStore: saved %s → %s", workflow.name, path)

    def load(self, workflow_id: str) -> Workflow | None:
        """Return a Workflow by ID or None if not found."""
        path = self.workflows_dir / f"{workflow_id}.json"
        if not path.exists():
            return None
        try:
            with open(path, encoding="utf-8") as f:
                return Workflow.from_dict(json.load(f))
        except Exception as exc:
            log.warning("WorkflowStore: failed to load %s — %s", workflow_id, exc)
            return None

    def delete(self, workflow_id: str) -> bool:
        """Delete a workflow JSON file. Returns True if deleted."""
        path = self.workflows_dir / f"{workflow_id}.json"
        if path.exists():
            path.unlink()
            return True
        return False

    def list_all(self) -> list[Workflow]:
        """Return all saved workflows sorted by modified_at descending."""
        results: list[Workflow] = []
        for path in self.workflows_dir.glob("*.json"):
            try:
                with open(path, encoding="utf-8") as f:
                    results.append(Workflow.from_dict(json.load(f)))
            except Exception as exc:
                log.warning("WorkflowStore: skipping %s — %s", path.name, exc)
        results.sort(key=lambda w: w.modified_at, reverse=True)
        return results

    def __iter__(self) -> Iterator[Workflow]:
        return iter(self.list_all())
