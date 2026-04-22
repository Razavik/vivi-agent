from __future__ import annotations

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
                "run_id": run.run_id,
                "agent_name": run.agent_name,
                "task": run.task,
                "status": run.status,
                "created_at": run.created_at,
                "updated_at": run.updated_at,
            })
        return {"runs": snapshot, "count": len(snapshot)}

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
