"""
keymacro/engine/workflow_runner.py
────────────────────────────────────
Workflow Runner — executes a Workflow by traversing its nodes in order,
running each node's macro and following success/failure edges.

Runs in a daemon thread (same pattern as ReplayEngine).

Public API
----------
WorkflowRunner()
    .run(workflow, macro_store, replay_engine, *, on_node, on_done, on_error)
    .stop()
    .is_running  → bool

Callbacks (called on the runner thread)
----------------------------------------
on_node(node_id, macro_name, status)   – "started" | "success" | "failure"
on_done(workflow_name)                 – workflow finished normally
on_error(workflow_name, exc)           – unhandled exception
"""

from __future__ import annotations

import threading
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from keymacro.engine.replay import ReplayEngine
    from keymacro.models.workflow import Workflow
    from keymacro.storage.macro_store import MacroStore


class WorkflowCancelled(Exception):
    """Raised when stop() is called mid-execution."""


class WorkflowRunner:
    """Executes a Workflow node-by-node in a daemon thread."""

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def is_running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def stop(self) -> None:
        self._cancel_event.set()

    def run(
        self,
        workflow: "Workflow",
        macro_store: "MacroStore",
        replay_engine: "ReplayEngine",
        *,
        on_node: "Callable[[str, str, str], None] | None" = None,
        on_done: "Callable[[str], None] | None" = None,
        on_error: "Callable[[str, Exception], None] | None" = None,
    ) -> None:
        """Start workflow execution in a daemon thread."""
        if self.is_running:
            return
        self._cancel_event.clear()
        self._thread = threading.Thread(
            target=self._run_loop,
            args=(workflow, macro_store, replay_engine, on_node, on_done, on_error),
            daemon=True,
            name=f"WorkflowRunner-{workflow.name}",
        )
        self._thread.start()

    # ── Internal ──────────────────────────────────────────────────────────────

    def _run_loop(
        self,
        workflow: "Workflow",
        macro_store: "MacroStore",
        replay_engine: "ReplayEngine",
        on_node,
        on_done,
        on_error,
    ) -> None:
        try:
            current_id = workflow.entry_node_id
            while current_id:
                if self._cancel_event.is_set():
                    raise WorkflowCancelled("Workflow stopped by user")

                node = workflow.node_by_id(current_id)
                if node is None:
                    break

                macro = macro_store.load(node.macro_id)
                if macro is None:
                    # Missing macro — treat as failure
                    _safe_call(on_node, node.node_id, node.macro_name, "failure")
                    current_id = node.next_on_failure
                    continue

                # Notify start
                _safe_call(on_node, node.node_id, macro.name, "started")

                # Execute and wait for completion
                success = self._execute_macro_sync(replay_engine, macro)

                status = "success" if success else "failure"
                _safe_call(on_node, node.node_id, macro.name, status)

                current_id = node.next_on_success if success else node.next_on_failure

            _safe_call(on_done, workflow.name)

        except WorkflowCancelled:
            _safe_call(on_done, workflow.name)
        except Exception as exc:
            _safe_call(on_error, workflow.name, exc)

    def _execute_macro_sync(self, replay_engine: "ReplayEngine", macro) -> bool:
        """Run a macro synchronously and return True on success."""
        done_event = threading.Event()
        result = {"success": True}

        def _on_done():
            done_event.set()

        def _on_error(exc: Exception):
            result["success"] = False
            done_event.set()

        replay_engine.replay(
            macro,
            dry_run=False,
            on_done=_on_done,
            on_error=_on_error,
        )
        # Wait for the replay daemon thread to complete (max 120s per macro)
        done_event.wait(timeout=120)
        return result["success"]


def _safe_call(fn, *args) -> None:
    if fn is not None:
        try:
            fn(*args)
        except Exception:
            pass
