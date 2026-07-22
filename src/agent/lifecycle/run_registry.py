from __future__ import annotations

from dataclasses import asdict, dataclass, field
from threading import Lock
from typing import Any


RunStatus = str


@dataclass(slots=True)
class AgentRun:
    run_id: str
    agent_name: str
    task: str
    status: RunStatus = "running"
    model: str | None = None
    created_at: float | None = None
    updated_at: float | None = None
    step: int | None = None
    result: str | None = None
    error: str | None = None
    question: str | None = None
    answer: str | None = None
    artifacts: dict[str, Any] = field(default_factory=dict)
    metadata: dict[str, Any] = field(default_factory=dict)
    changed_files: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    retries: int = 0
    interrupt_count: int = 0
    avg_step_latency_ms: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunRegistry:
    def __init__(self, on_change: callable | None = None) -> None:
        self._lock = Lock()
        self._runs: dict[str, AgentRun] = {}
        self._on_change = on_change

    def _emit_change(self) -> None:
        if self._on_change is not None:
            self._on_change(self.list_all())

    def upsert(self, run: AgentRun) -> AgentRun:
        with self._lock:
            self._runs[run.run_id] = run
            updated = AgentRun(**run.to_dict())
        self._emit_change()
        return updated

    def get(self, run_id: str) -> AgentRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            return None if run is None else AgentRun(**run.to_dict())

    def update(self, run_id: str, **changes: Any) -> AgentRun | None:
        with self._lock:
            run = self._runs.get(run_id)
            if run is None:
                return None
            for key, value in changes.items():
                if hasattr(run, key):
                    setattr(run, key, value)
                else:
                    run.metadata[key] = value
            updated = AgentRun(**run.to_dict())
        self._emit_change()
        return updated

    def remove(self, run_id: str) -> AgentRun | None:
        with self._lock:
            run = self._runs.pop(run_id, None)
            removed = None if run is None else AgentRun(**run.to_dict())
        self._emit_change()
        return removed

    def load_snapshot(self, runs: list[dict[str, Any]]) -> None:
        restored: dict[str, AgentRun] = {}
        for item in runs:
            try:
                run = AgentRun(**item)
            except TypeError:
                continue
            restored[run.run_id] = run
        with self._lock:
            self._runs = restored
        self._emit_change()

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [run.to_dict() for run in self._runs.values()]

    def list_active(self) -> list[dict[str, Any]]:
        active_statuses = {
            "queued",
            "running",
            "waiting_input",
            "waiting_user",
            "waiting_dependency",
            "waiting_tool",
            "blocked",
            "reviewing",
            "paused",
            "cancelling",
        }
        with self._lock:
            return [
                run.to_dict()
                for run in self._runs.values()
                if run.status in active_statuses
            ]
