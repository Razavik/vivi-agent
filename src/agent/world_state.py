"""WorldState — структурированный снимок состояния системы для директора.

Собирает данные из RunRegistry, ArtifactStore и MessageBus в единый объект,
который директор получает в каждом шаге (через get_active_runs / supervisor_observations).
"""
from __future__ import annotations

import time
from typing import Any


class WorldState:
    """Агрегирует состояние всей системы в читаемый снимок."""

    def __init__(self, run_registry: Any, artifact_store: Any | None = None) -> None:
        self._registry = run_registry
        self._artifact_store = artifact_store

    def snapshot(self) -> dict[str, Any]:
        """Возвращает полный снимок состояния системы."""
        runs = self._registry.list_all()
        active = [r for r in runs if r["status"] in {"queued", "running", "waiting_input", "paused", "cancelling"}]
        finished = [r for r in runs if r["status"] in {"finished", "cancelled", "error", "interrupted"}]

        blocked: list[dict[str, Any]] = []
        open_questions: list[dict[str, Any]] = []
        for run in active:
            if run["status"] == "waiting_input" and run.get("question"):
                open_questions.append({"run_id": run["run_id"], "agent": run["agent_name"], "question": run["question"]})
            if run["status"] == "paused":
                blocked.append({"run_id": run["run_id"], "agent": run["agent_name"], "task": run["task"]})

        return {
            "timestamp": time.time(),
            "active_runs": len(active),
            "finished_runs": len(finished),
            "blocked_runs": blocked,
            "open_questions": open_questions,
            "runs": active,
        }

    def summarize(self) -> str:
        """Краткое текстовое описание состояния для промпта директора."""
        snap = self.snapshot()
        lines = [
            f"Активных run: {snap['active_runs']}, завершённых: {snap['finished_runs']}.",
        ]
        if snap["blocked_runs"]:
            lines.append(f"Заблокировано: {len(snap['blocked_runs'])} run.")
        if snap["open_questions"]:
            lines.append(f"Открытых вопросов: {len(snap['open_questions'])}.")
        return " ".join(lines)
