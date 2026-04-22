from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from src.app_factory import describe_all_tools
from src.infra.config import MODELS_FILE
from src.web.confirmation import ConfirmationManager
from src.web.context import ServerContext
from src.web.sse_stream import SSEStream


class Routes:
    """Обработчики маршрутов API. Получают ServerContext, возвращают данные."""

    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx
        self.confirmation = ConfirmationManager(ctx)
        self.sse = SSEStream(ctx, self.confirmation)

    def get_tools(self) -> dict[str, Any]:
        return {"tools": describe_all_tools(self.ctx.settings)}

    def get_models(self) -> dict[str, Any]:
        default = self.ctx.settings.model
        data: dict[str, str] = {}
        if MODELS_FILE.exists():
            try:
                data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass
        agents = ["director", "file", "system", "telegram", "web"]
        return {
            "default": default,
            "models": {a: data.get(a, "") for a in agents},
        }

    def set_models(self, body: dict[str, Any]) -> dict[str, Any]:
        models: dict[str, str] = body.get("models", {})
        cleaned = {k: v for k, v in models.items() if isinstance(v, str)}
        MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MODELS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": True, "models": cleaned}

    def get_agents_history(self) -> dict[str, Any]:
        memory_dir = self.ctx.settings.sub_agent_memory_dir
        agents: list[dict[str, Any]] = []
        if memory_dir.exists():
            for f in sorted(memory_dir.glob("*-memory.json")):
                agent_name = f.stem.replace("-memory", "")
                try:
                    import json as _json

                    data = _json.loads(f.read_text(encoding="utf-8"))
                    chat_history = data.get("chat_history", [])
                    updated_at = data.get("updated_at")
                except Exception:
                    chat_history = []
                    updated_at = None
                agents.append({
                    "name": agent_name,
                    "chat_history": chat_history,
                    "updated_at": updated_at,
                })
        return {"agents": agents}

    def clear_agent_memory(self, agent_name: str) -> dict[str, Any]:
        memory_dir = self.ctx.settings.sub_agent_memory_dir
        f = memory_dir / f"{agent_name}-memory.json"
        if not f.exists():
            return {"cleared": False, "error": "Файл не найден"}
        from src.infra.chat_memory import ChatMemoryStore

        ChatMemoryStore(f).clear()
        return {"cleared": True, "agent": agent_name}

    def clear_all_agents_memory(self) -> dict[str, Any]:
        memory_dir = self.ctx.settings.sub_agent_memory_dir
        cleared: list[str] = []
        if memory_dir.exists():
            from src.infra.chat_memory import ChatMemoryStore

            for f in memory_dir.glob("*-memory.json"):
                ChatMemoryStore(f).clear()
                cleared.append(f.stem.replace("-memory", ""))
        return {"cleared": True, "agents": cleared}

    def get_history(self) -> dict[str, Any]:
        memory = self.ctx.memory_store.load()
        return {
            "chat_history": memory.get("chat_history", []),
            "actions": memory.get("actions", []),
        }

    def get_active_runs(self) -> dict[str, Any]:
        return {"runs": self.ctx.get_active_runs()}

    def clear_history(self) -> dict[str, Any]:
        self.ctx.memory_store.clear()
        return {"cleared": True, "target": "history"}

    def clear_logs(self) -> dict[str, Any]:
        log_dir = self.ctx.settings.log_dir
        removed = 0
        if log_dir.exists():
            for item in log_dir.glob("session-*.json"):
                try:
                    item.unlink()
                    removed += 1
                except OSError:
                    continue
        return {"cleared": True, "target": "logs", "removed": removed}

    def open_path(self, body: dict[str, Any]) -> dict[str, Any]:
        import subprocess

        path = str(body.get("path", "")).strip()
        if not path:
            return {"ok": False, "error": "path is empty"}
        try:
            subprocess.Popen(["explorer", path])
            return {"ok": True, "path": path}
        except Exception as e:
            return {"ok": False, "error": str(e)}

    def cancel(self) -> dict[str, Any]:
        cancelled = self.ctx.cancel_runtime()
        if cancelled:
            return {"cancelled": True}
        return {"cancelled": False, "error": "Нет активной задачи"}

    def cancel_run(self, run_id: str) -> dict[str, Any]:
        cancelled = self.ctx.cancel_run(run_id)
        if cancelled:
            return {"cancelled": True, "run_id": run_id}
        return {"cancelled": False, "run_id": run_id, "error": "Активный run не найден"}

    def pause_run(self, run_id: str) -> dict[str, Any]:
        paused = self.ctx.pause_run(run_id)
        if paused:
            return {"paused": True, "run_id": run_id}
        return {"paused": False, "run_id": run_id, "error": "Активный run не найден"}

    def resume_run(self, run_id: str) -> dict[str, Any]:
        resumed = self.ctx.resume_run(run_id)
        if resumed:
            return {"resumed": True, "run_id": run_id}
        return {"resumed": False, "run_id": run_id, "error": "Активный run не найден"}

    def confirm(self, request_id: str, approved: bool) -> dict[str, Any] | tuple[dict[str, Any], HTTPStatus]:
        found = self.confirmation.handle_confirm_request(request_id, approved)
        if not found:
            return {"error": "Подтверждение не найдено или уже не актуально"}, HTTPStatus.CONFLICT
        return {"ok": True, "request_id": request_id, "approved": approved}

    def run_task(
        self,
        task: str,
        chat_history: list[dict[str, str]],
        write_callback,
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        return self.sse.run_and_stream(task, chat_history, write_callback, images=images)
