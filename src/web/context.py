from __future__ import annotations

import threading
import time
from threading import Event
from typing import Any

from src.agent.dependency_graph import DependencyGraph
from src.agent.message_bus import MessageBus
from src.agent.run_control import RunController
from src.agent.run_registry import AgentRun, RunRegistry
from src.agent.runtime import AgentRuntime
from src.agent.supervisor import SupervisorLoop
from src.agent.supervisor_trigger import SupervisorTrigger
from src.infra.artifact_store import ArtifactStore
from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import Settings, get_settings
from src.infra.confirmation_store import ConfirmationStore
from src.infra.crash_reporter import CrashReporter
from src.infra.run_state_store import RunStateStore


class ServerContext:
    """Разделяемый контекст сервера: настройки, сервисы и состояние сессии."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.memory_store = ChatMemoryStore(self.settings.memory_file)
        self.run_state_store = RunStateStore(self.settings.workspace_root / "data" / "runs.json")
        self.run_registry = RunRegistry(on_change=self._persist_runs)
        self.artifact_store = ArtifactStore(self.settings.workspace_root / "data" / "artifacts")

        self.message_bus = MessageBus(max_history=1000)
        self.dependency_graph = DependencyGraph(on_ready=self._on_dependency_ready)
        self.crash_reporter = CrashReporter(self.settings.workspace_root / "data" / "crashes")
        self.confirmation_store = ConfirmationStore(self.settings.workspace_root / "data" / "pending_confirm.json")
        self._lock = threading.Lock()
        self._current_runtime: AgentRuntime | None = None
        self._pending_confirmation: dict[str, Any] | None = self.confirmation_store.load()
        self._run_controllers: dict[str, RunController] = {}
        self._restore_runs()

        self._supervisor_alerts: list[dict[str, Any]] = []
        self._supervisor_lock = threading.Lock()
        self.supervisor = SupervisorLoop(
            get_active_runs=lambda: self.run_registry.list_active(),
            event_sink=self._on_supervisor_alert,
            tick_interval=10.0,
            hang_threshold=60.0,
            stale_paused_threshold=300.0,
            alert_cooldown=30.0,
            dependency_graph=self.dependency_graph,
        )
        self.supervisor.start()

        # Триггер автономного запуска директора при алертах
        self._supervisor_trigger = SupervisorTrigger(
            is_director_busy=lambda: self.get_runtime() is not None,
            run_director=self._run_director_autonomous,
            cooldown=90.0,
        )
        self._supervisor_trigger.start()
        self._autonomous_run_callback: Any = None

    def set_autonomous_run_callback(self, callback: Any) -> None:
        """Устанавливает колбэк для автономного запуска директора (задаётся из SSEStream)."""
        self._autonomous_run_callback = callback

    def _run_director_autonomous(self, message: str) -> None:
        """Запускает директора автономно — вызывается SupervisorTrigger."""
        if self._autonomous_run_callback is not None:
            try:
                self._autonomous_run_callback(message)
            except Exception:
                pass

    def _on_supervisor_alert(self, event: str, payload: dict[str, Any]) -> None:
        alert = {
            "event": event,
            "payload": payload,
            "timestamp": time.time(),
        }
        with self._supervisor_lock:
            self._supervisor_alerts.append(alert)
        # Передаём алерт триггеру для автономного запуска директора
        self._supervisor_trigger.on_alert(alert)
        # Рассылаем в реальном времени всем WS-подписчикам
        try:
            from src.web.ws_server import broadcast_supervisor_alert
            broadcast_supervisor_alert(alert)
        except Exception:
            pass

    def get_supervisor_alerts(self, limit: int = 10) -> list[dict[str, Any]]:
        with self._supervisor_lock:
            alerts = self._supervisor_alerts[-limit:]
            self._supervisor_alerts = []
            return alerts

    def _persist_runs(self, runs: list[dict[str, Any]]) -> None:
        self.run_state_store.save(runs)

    def _restore_runs(self) -> None:
        snapshot = self.run_state_store.load()
        if not snapshot:
            return
        now = time.time()
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
        restored: list[dict[str, Any]] = []
        for item in snapshot:
            payload = dict(item)
            status = str(payload.get("status", ""))
            if status in active_statuses:
                payload["status"] = "interrupted"
                payload["error"] = "Сервер был перезапущен во время выполнения run"
                payload["updated_at"] = now
            restored.append(payload)
        self.run_registry.load_snapshot(restored)

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
        self.confirmation_store.save(pending)

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
        self.confirmation_store.clear()

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

    def handoff_artifact(self, src_run_id: str, src_name: str, dst_run_id: str, dst_name: str | None = None) -> dict[str, Any]:
        """Копирует артефакт из одного run в другой и помечает его готовым в DependencyGraph."""
        result = self.artifact_store.copy_artifact(src_run_id, src_name, dst_run_id, dst_name or src_name)
        if "error" not in result:
            self.dependency_graph.mark_artifact_ready(src_name, src_run_id)
        return result

    def gc_run_artifacts(self, run_id: str, older_than_seconds: float = 0.0) -> int:
        """Удаляет артефакты завершённого run."""
        return self.artifact_store.gc_run(run_id, older_than_seconds)

    def _on_dependency_ready(self, waiting_run_id: str, artifact_name: str, provider_run_id: str) -> None:
        """Вызывается когда артефакт готов — посылаем inbox-сообщение ждущему run."""
        msg = f"[dependency_ready] Артефакт '{artifact_name}' от run {provider_run_id} готов."
        self.message_run(waiting_run_id, msg)
        self.message_bus.publish(
            msg_type="dependency_ready",
            sender="system",
            payload={"artifact_name": artifact_name, "provider_run_id": provider_run_id},
            run_id=waiting_run_id,
        )

    def remove_run_controller(self, run_id: str) -> None:
        with self._lock:
            self._run_controllers.pop(run_id, None)

    # --- Реестр активных run ---

    def post_outbox_message(self, run_id: str, message: str, sender: str = "") -> None:
        """Саб-агент отправляет произвольное сообщение директору через шину."""
        self.message_bus.publish(
            msg_type="outbox_message",
            sender=sender or run_id,
            payload={"message": message},
            run_id=run_id,
        )

    def get_bus_history(self, run_id: str | None = None, msg_type: str | None = None, limit: int = 100) -> list[dict[str, Any]]:
        """Возвращает историю шины сообщений."""
        return [m.to_dict() for m in self.message_bus.get_history(run_id=run_id, msg_type=msg_type, limit=limit)]

    def handle_run_event(self, event: str, payload: dict[str, Any]) -> None:
        run_id = payload.get("run_id")
        if not isinstance(run_id, str) or not run_id:
            return

        now = time.time()

        # Публикуем ключевые события в MessageBus
        _bus_events = {
            "sub_agent_started": "run_started",
            "sub_agent_finished": "run_finished",
            "sub_agent_question": "question_to_director",
            "sub_agent_answer": "answer_from_director",
            "sub_agent_task_replaced": "task_replaced",
            "sub_agent_policy_violation": "system_event",
        }
        if event in _bus_events:
            self.message_bus.publish(
                msg_type=_bus_events[event],
                sender=str(payload.get("agent", run_id)),
                payload=payload,
                run_id=run_id,
            )

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

        if event == "sub_agent_paused":
            run = self.run_registry.get(run_id)
            ic = (run.interrupt_count if run else 0) + 1
            self.run_registry.update(run_id, interrupt_count=ic, updated_at=now)
            return

        if event == "sub_agent_error":
            message = str(payload.get("message", ""))
            is_cancel = "run_id=" in message or "прерван" in message.lower()
            status = "cancelled" if is_cancel else "error"
            run = self.run_registry.get(run_id)
            retries = (run.retries if run else 0) + (0 if is_cancel else 1)
            self.run_registry.update(
                run_id,
                status=status,
                error=message,
                step=payload.get("step"),
                retries=retries,
                updated_at=now,
            )
            if status == "cancelled":
                self.remove_run_controller(run_id)
            return

        if event == "sub_agent_finished":
            success = bool(payload.get("success", False))
            cancelled = bool(payload.get("cancelled", False))
            result_status = str(payload.get("status", "")).strip().lower()
            if result_status in {"blocked", "waiting_user"}:
                status = result_status
            elif cancelled or result_status == "cancelled":
                status = "cancelled"
            elif success or result_status == "done":
                status = "finished"
            else:
                status = "error"
            metadata = {
                "result_status": result_status or ("done" if success else "failed"),
                "needs_user_input": bool(payload.get("needs_user_input", False)),
            }
            if payload.get("created_artifacts") is not None:
                metadata["created_artifacts"] = payload.get("created_artifacts")
            self.run_registry.update(
                run_id,
                status=status,
                result=str(payload.get("result", "")),
                changed_files=[str(item) for item in payload.get("changed_files", []) if str(item).strip()],
                verification=[str(item) for item in payload.get("verification", []) if str(item).strip()],
                risks=[str(item) for item in payload.get("risks", []) if str(item).strip()],
                question=str(payload.get("question", "")),
                metadata=metadata,
                updated_at=now,
            )
            if status not in {"blocked", "waiting_user"}:
                self.remove_run_controller(run_id)

    def get_active_runs(self) -> list[dict[str, Any]]:
        return self.run_registry.list_active()
