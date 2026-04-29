from __future__ import annotations

import json
from http import HTTPStatus
from typing import Any

from src.app_factory import describe_all_tools
from src.infra.settings_service import SettingsService
from src.infra.config import MODELS_FILE, _load_tools_config, _save_tools_config, get_agent_tools_config, _load_agents_config, _save_agents_config, load_available_models, _load_user_profile, _save_user_profile
from src.web.confirmation import ConfirmationManager
from src.web.context import ServerContext
from src.web.route_modules.ops_routes import OpsRoutes
from src.web.sse_stream import SSEStream


class Routes:
    """Обработчики маршрутов API. Получают ServerContext, возвращают данные."""

    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx
        self.confirmation = ConfirmationManager(ctx)
        self.sse = SSEStream(ctx, self.confirmation)
        self.ops = OpsRoutes(ctx)

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
        agents = list(_load_agents_config().keys())
        return {
            "default": default,
            "models": {a: data.get(a, "") for a in agents},
        }

    def get_available_models(self) -> dict[str, Any]:
        """Возвращает список моделей из data/available_models.json."""
        return {"models": load_available_models()}

    def get_ollama_models(self) -> dict[str, Any]:
        """Получить список моделей доступных в Ollama."""
        import urllib.request
        base_url = self.ctx.settings.ollama_base_url.rstrip("/")
        try:
            with urllib.request.urlopen(f"{base_url}/api/tags", timeout=5) as resp:
                data = json.loads(resp.read().decode())
            models = [m["name"] for m in data.get("models", [])]
            return {"models": models}
        except Exception as e:
            return {"models": [], "error": str(e)}

    def set_models(self, body: dict[str, Any]) -> dict[str, Any]:
        models: dict[str, str] = body.get("models", {})
        cleaned = {k: v for k, v in models.items() if isinstance(v, str)}
        MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MODELS_FILE.write_text(json.dumps(cleaned, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"saved": True, "models": cleaned}

    def get_tools_config(self) -> dict[str, Any]:
        """Возвращает конфигурацию инструментов для всех агентов."""
        return {"config": _load_tools_config()}

    def set_tools_config(self, body: dict[str, Any]) -> dict[str, Any]:
        """Сохраняет конфигурацию инструментов."""
        config = body.get("config", {})
        if not isinstance(config, dict):
            return {"error": "config must be an object"}, HTTPStatus.BAD_REQUEST
        # Валидируем структуру
        cleaned: dict[str, dict[str, bool]] = {}
        for agent, tools in config.items():
            if isinstance(tools, dict):
                cleaned[agent] = {tool: bool(enabled) for tool, enabled in tools.items()}
        _save_tools_config(cleaned)
        return {"saved": True, "config": cleaned}

    def get_agents_config(self) -> dict[str, Any]:
        """Возвращает конфигурацию агентов из data/agents.json."""
        return {"config": _load_agents_config()}

    def set_agents_config(self, body: dict[str, Any]) -> dict[str, Any]:
        """Сохраняет конфигурацию агентов."""
        config = body.get("config", {})
        if not isinstance(config, dict):
            return {"error": "config must be an object"}, HTTPStatus.BAD_REQUEST
        cleaned = SettingsService().sanitize_agents_config(config)
        _save_agents_config(cleaned)
        return {"saved": True, "config": cleaned}

    def get_user_profile(self) -> dict[str, Any]:
        """Возвращает профиль пользователя."""
        return {"profile": _load_user_profile()}

    def set_user_profile(self, body: dict[str, Any]) -> dict[str, Any]:
        """Сохраняет профиль пользователя."""
        profile = body.get("profile", {})
        if not isinstance(profile, dict):
            return {"error": "profile must be an object"}, HTTPStatus.BAD_REQUEST
        cleaned = {k: str(v) if isinstance(v, str) else "" for k, v in profile.items() if isinstance(v, (str, int, float, bool))}
        _save_user_profile(cleaned)
        return {"saved": True, "profile": cleaned}

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

    def clear_agent_runs(self, agent_name: str) -> dict[str, Any]:
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

    def get_run_by_id(self, run_id: str) -> dict[str, Any]:
        run = self.ctx.run_registry.get(run_id)
        if run is None:
            return {"error": f"run {run_id!r} не найден"}
        return run.to_dict()

    def get_bus_history(self, run_id: str | None = None, msg_type: str | None = None, limit: int = 100) -> dict[str, Any]:
        return {"messages": self.ctx.get_bus_history(run_id=run_id, msg_type=msg_type, limit=limit)}

    def get_crash_reports(self) -> dict[str, Any]:
        return {"crashes": self.ctx.crash_reporter.list_reports()}

    def get_crash_report(self, filename: str) -> dict[str, Any]:
        return self.ctx.crash_reporter.read_report(filename)

    def get_supervisor_alerts(self, limit: int = 10) -> dict[str, Any]:
        return {"alerts": self.ctx.get_supervisor_alerts(limit)}

    def get_diagnostics(self) -> dict[str, Any]:
        return self.ops.diagnostics()

    def get_preflight(self) -> dict[str, Any]:
        return self.ops.preflight()

    def get_post_run_reviews(self) -> dict[str, Any]:
        return self.ops.post_run_reviews()

    def get_agent_scorecard(self) -> dict[str, Any]:
        return self.ops.scorecard()

    def get_memory_inspector(self) -> dict[str, Any]:
        return self.ops.memory_inspector()

    def get_task_templates(self) -> dict[str, Any]:
        return self.ops.task_templates()

    def get_run_replays(self) -> dict[str, Any]:
        return self.ops.run_replays()

    def get_tool_contract_tests(self) -> dict[str, Any]:
        return self.ops.tool_contract_tests()

    def run_maintenance(self) -> dict[str, Any]:
        return self.ops.maintenance()

    def preview_command(self, body: dict[str, Any]) -> dict[str, Any]:
        return self.ops.command_preview(body)

    def get_run_artifacts(self, run_id: str) -> dict[str, Any]:
        return {"run_id": run_id, "artifacts": self.ctx.list_artifacts(run_id)}

    def get_run_artifact(self, run_id: str, name: str) -> dict[str, Any]:
        return self.ctx.read_artifact(run_id, name)

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

    def message_run(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        message = str(body.get("message", ""))
        if not message:
            return {"error": "message is empty"}, HTTPStatus.BAD_REQUEST
        sent = self.ctx.message_run(run_id, message)
        if sent:
            return {"sent": True, "run_id": run_id}
        return {"sent": False, "run_id": run_id, "error": "Активный run не найден"}

    def replace_task_run(self, run_id: str, body: dict[str, Any]) -> dict[str, Any]:
        new_task = str(body.get("task", ""))
        if not new_task:
            return {"error": "task is empty"}, HTTPStatus.BAD_REQUEST
        replaced = self.ctx.replace_task(run_id, new_task)
        if replaced:
            return {"replaced": True, "run_id": run_id}
        return {"replaced": False, "run_id": run_id, "error": "Активный run не найден"}

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
