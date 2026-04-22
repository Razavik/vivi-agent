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

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class RunRegistry:
    def __init__(self) -> None:
        self._lock = Lock()
        self._runs: dict[str, AgentRun] = {}

    def upsert(self, run: AgentRun) -> AgentRun:
        with self._lock:
            self._runs[run.run_id] = run
            return run

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
            return AgentRun(**run.to_dict())

    def remove(self, run_id: str) -> AgentRun | None:
        with self._lock:
            run = self._runs.pop(run_id, None)
            return None if run is None else AgentRun(**run.to_dict())

    def list_all(self) -> list[dict[str, Any]]:
        with self._lock:
            return [run.to_dict() for run in self._runs.values()]

    def list_active(self) -> list[dict[str, Any]]:
        active_statuses = {"queued", "running", "waiting_input", "paused", "cancelling"}
        with self._lock:
            return [
                run.to_dict()
                for run in self._runs.values()
                if run.status in active_statuses
            ]
