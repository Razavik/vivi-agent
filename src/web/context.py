from __future__ import annotations

import threading
import time
from threading import Event
from typing import Any

from src.agent.run_control import RunController
from src.agent.run_registry import AgentRun, RunRegistry
from src.agent.runtime import AgentRuntime
from src.infra.artifact_store import ArtifactStore
from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import Settings, get_settings


class ServerContext:
    """Разделяемый контекст сервера: настройки, сервисы и состояние сессии."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.memory_store = ChatMemoryStore(self.settings.memory_file)
        self.run_registry = RunRegistry()
        self.artifact_store = ArtifactStore(self.settings.workspace_root / "data" / "artifacts")

        self._lock = threading.Lock()
        self._current_runtime: AgentRuntime | None = None
        self._pending_confirmation: dict[str, Any] | None = None
        self._run_controllers: dict[str, RunController] = {}

    # --- Управление runtime ---

    def set_runtime(self, runtime: AgentRuntime | None) -> None:
        with self._lock:
            self._current_runtime = runtime

    def get_runtime(self) -> AgentRuntime | None:
        with self._lock:
            return self._current_runtime

    def cancel_runtime(self) -> bool:
        with self._lock:
            if self._current_runtime is not None:
                self._current_runtime.cancel()
                self._current_runtime = None
                return True
            return False

    # --- Управление подтверждениями ---

    def set_pending_confirmation(self, pending: dict[str, Any] | None) -> None:
        with self._lock:
            self._pending_confirmation = pending

    def get_pending_confirmation(self) -> dict[str, Any] | None:
        with self._lock:
            return self._pending_confirmation

    def confirm_pending(self, request_id: str, approved: bool) -> bool:
        with self._lock:
            pending = self._pending_confirmation
            if not pending or pending.get("request_id") != request_id:
                return False
            pending["approved"] = approved
            event: threading.Event = pending["event"]
        event.set()
        return True

    def clear_confirmation(self) -> None:
        with self._lock:
            self._pending_confirmation = None

    # --- Управление run controllers ---

    def create_run_controller(self, run_id: str, agent_name: str, task: str) -> RunController:
        controller = RunController(run_id=run_id, cancel_event=Event(), pause_event=Event())
        with self._lock:
            self._run_controllers[run_id] = controller
        self.run_registry.upsert(
            AgentRun(
                run_id=run_id,
                agent_name=agent_name,
                task=task,
                status="queued",
                created_at=time.time(),
                updated_at=time.time(),
            )
        )
        return controller

    def cancel_run(self, run_id: str) -> bool:
        with self._lock:
            controller = self._run_controllers.get(run_id)
        if controller is None:
            return False
        controller.cancel()
        self.run_registry.update(run_id, status="cancelling", updated_at=time.time())
        return True

    def pause_run(self, run_id: str) -> bool:
        with self._lock:
            controller = self._run_controllers.get(run_id)
        if controller is None:
            return False
        controller.pause()
        self.run_registry.update(run_id, status="paused", updated_at=time.time())
        return True

    def resume_run(self, run_id: str) -> bool:
        with self._lock:
            controller = self._run_controllers.get(run_id)
        if controller is None:
            return False
        controller.resume()
        self.run_registry.update(run_id, status="running", updated_at=time.time())
        return True

    def message_run(self, run_id: str, message: str) -> bool:
        with self._lock:
            controller = self._run_controllers.get(run_id)
        if controller is None:
            return False
        controller.post_message(message)
        return True

    def replace_task(self, run_id: str, new_task: str) -> bool:
        with self._lock:
            controller = self._run_controllers.get(run_id)
        if controller is None:
            return False
        controller.replace_task(new_task)
        self.run_registry.update(run_id, task=new_task, updated_at=time.time())
        return True

    def create_artifact(self, run_id: str, name: str, content: str | bytes, mime_type: str = "text/plain") -> dict[str, Any]:
        info = self.artifact_store.create(run_id, name, content, mime_type)
        run = self.run_registry.get(run_id)
        if run is not None:
            artifacts = dict(run.artifacts)
            artifacts[name] = {"mime_type": mime_type, "size": info.get("size", 0)}
            self.run_registry.update(run_id, artifacts=artifacts, updated_at=time.time())
        return info

    def read_artifact(self, run_id: str, name: str) -> dict[str, Any]:
        return self.artifact_store.read(run_id, name)

    def list_artifacts(self, run_id: str) -> list[dict[str, Any]]:
        return self.artifact_store.list(run_id)

    def remove_run_controller(self, run_id: str) -> None:
        with self._lock:
            self._run_controllers.pop(run_id, None)

    # --- Реестр активных run ---

    def handle_run_event(self, event: str, payload: dict[str, Any]) -> None:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return

        now = time.time()

        if event == "sub_agent_started":
            existing = self.run_registry.get(run_id)
            created_at = existing.created_at if existing else now
            self.run_registry.upsert(
                AgentRun(
                    run_id=run_id,
                    agent_name=str(payload.get("agent", "")),
                    task=str(payload.get("task", "")),
                    status="running",
                    model=str(payload.get("model", "")) or None,
                    created_at=created_at,
                    updated_at=now,
                )
            )
            return

        if event == "sub_agent_step":
            self.run_registry.update(run_id, step=payload.get("step"), status="running", updated_at=now)
            return

        if event == "sub_agent_question":
            self.run_registry.update(
                run_id,
                status="waiting_input",
                question=str(payload.get("question", "")),
                updated_at=now,
            )
            return

        if event == "sub_agent_answer":
            self.run_registry.update(
                run_id,
                status="running",
                answer=str(payload.get("answer", "")),
                updated_at=now,
            )
            return

        if event == "sub_agent_error":
            message = str(payload.get("message", ""))
            status = "cancelled" if "run_id=" in message or "прерван" in message.lower() else "error"
            self.run_registry.update(
                run_id,
                status=status,
                error=message,
                step=payload.get("step"),
                updated_at=now,
            )
            if status == "cancelled":
                self.remove_run_controller(run_id)
            return

        if event == "sub_agent_finished":
            success = bool(payload.get("success", False))
            cancelled = bool(payload.get("cancelled", False))
            self.run_registry.update(
                run_id,
                status="cancelled" if cancelled else ("finished" if success else "error"),
                result=str(payload.get("result", "")),
                updated_at=now,
            )
            self.remove_run_controller(run_id)

    def get_active_runs(self) -> list[dict[str, Any]]:
        return self.run_registry.list_active()
