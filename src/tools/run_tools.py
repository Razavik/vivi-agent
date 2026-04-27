from __future__ import annotations

import time
from typing import Any

from src.infra.errors import ToolExecutionError


class RunTools:
    """Инструменты для управления активными run'ами саб-агентов."""

    def __init__(self, server_context: Any) -> None:
        self.ctx = server_context

    def view_runs(self, args: dict[str, Any]) -> dict[str, Any]:
        """Показать активные запуски саб-агентов."""
        limit = int(args.get("limit", 10))
        runs = self.ctx.run_registry.list_active()
        snapshot = []
        for run in runs[:limit]:
            snapshot.append({
                "run_id": run["run_id"],
                "agent_name": run["agent_name"],
                "task": run["task"],
                "status": run["status"],
                "step": run.get("step"),
                "priority": run.get("metadata", {}).get("priority", 5),
                "result_status": run.get("metadata", {}).get("result_status"),
                "verification": run.get("verification", []),
                "risks": run.get("risks", []),
                "changed_files": run.get("changed_files", []),
                "created_at": run.get("created_at"),
                "updated_at": run.get("updated_at"),
            })
        return {"runs": snapshot, "count": len(snapshot)}

    def reprioritize_run(self, args: dict[str, Any]) -> dict[str, Any]:
        """Изменить приоритет активного run (1=высший, 10=низший)."""
        run_id = str(args.get("run_id", ""))
        priority = int(args.get("priority", 5))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        if not 1 <= priority <= 10:
            raise ToolExecutionError("priority должен быть от 1 до 10")
        updated = self.ctx.run_registry.update(run_id, priority=priority, updated_at=time.time())
        if updated is None:
            return {"ok": False, "run_id": run_id, "error": "run не найден"}
        return {"ok": True, "run_id": run_id, "priority": priority}

    def get_world_state(self, args: dict[str, Any]) -> dict[str, Any]:
        """Получить структурированный снимок состояния всей системы."""
        from src.agent.world_state import WorldState
        ws = WorldState(self.ctx.run_registry)
        return ws.snapshot()

    def wait_for_event(self, args: dict[str, Any]) -> dict[str, Any]:
        """Ждать завершения run или конкретного события (timeout_seconds, run_id)."""
        run_id = str(args.get("run_id", ""))
        timeout = float(args.get("timeout_seconds", 30.0))
        target_statuses = {"finished", "blocked", "waiting_user", "cancelled", "error", "interrupted"}

        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")

        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            run = self.ctx.run_registry.get(run_id)
            if run is None:
                return {"timed_out": False, "run_id": run_id, "status": "not_found"}
            if run.status in target_statuses:
                return {"timed_out": False, "run_id": run_id, "status": run.status, "result": run.result}
            time.sleep(1.0)

        run = self.ctx.run_registry.get(run_id)
        return {
            "timed_out": True,
            "run_id": run_id,
            "status": run.status if run else "unknown",
        }

    def cancel_run(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = str(args.get("run_id", ""))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        ok = self.ctx.cancel_run(run_id)
        return {"cancelled": ok, "run_id": run_id}

    def pause_run(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = str(args.get("run_id", ""))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        ok = self.ctx.pause_run(run_id)
        return {"paused": ok, "run_id": run_id}

    def resume_run(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = str(args.get("run_id", ""))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        ok = self.ctx.resume_run(run_id)
        return {"resumed": ok, "run_id": run_id}

    def message_run(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = str(args.get("run_id", ""))
        message = str(args.get("message", ""))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        if not message:
            raise ToolExecutionError("Параметр message обязателен")
        ok = self.ctx.message_run(run_id, message)
        return {"sent": ok, "run_id": run_id}

    def replace_task_run(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = str(args.get("run_id", ""))
        task = str(args.get("task", ""))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        if not task:
            raise ToolExecutionError("Параметр task обязателен")
        ok = self.ctx.replace_task(run_id, task)
        return {"replaced": ok, "run_id": run_id}
