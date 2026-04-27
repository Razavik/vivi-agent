from __future__ import annotations

import json
import queue
import threading
from http import HTTPStatus
from typing import Any, Callable

from src.app_factory import build_runtime
from src.infra.logging import SessionLogger
from src.web.confirmation import ConfirmationManager
from src.web.context import ServerContext


class SSEStream:
    """Управление SSE-потоком для запуска агента и стриминга событий."""

    def __init__(self, ctx: ServerContext, confirmation: ConfirmationManager) -> None:
        self.ctx = ctx
        self.confirmation = confirmation
        # Регистрируем себя как провайдер автономных запусков директора
        ctx.set_autonomous_run_callback(self._run_autonomous)

    def run_and_stream(
        self,
        task: str,
        chat_history: list[dict[str, str]],
        write_callback: Callable[[bytes], None],
        images: list[str] | None = None,
    ) -> dict[str, Any]:
        """Запускает агента в отдельном потоке и стримит SSE-события через write_callback."""
        return self._run_agent(task, chat_history, write_callback, images=images)

    def _run_autonomous(self, message: str) -> None:
        """Автономный запуск директора без подключённого клиента (triggered by supervisor)."""
        def _noop(_data: bytes) -> None:
            pass

        threading.Thread(
            target=self._run_agent,
            args=(message, [], _noop),
            kwargs={"autonomous": True},
            daemon=True,
            name="director-autonomous",
        ).start()

    def _run_agent(
        self,
        task: str,
        chat_history: list[dict[str, str]],
        write_callback: Callable[[bytes], None],
        images: list[str] | None = None,
        autonomous: bool = False,
    ) -> dict[str, Any]:
        """Общий метод запуска агента: обычный (с write_callback) или автономный."""
        import time as _time

        logger = SessionLogger(self.ctx.settings.log_dir)
        event_queue: queue.Queue[dict[str, Any] | None] = queue.Queue()
        result_holder: dict[str, Any] = {}

        def event_sink(event: str, data: object) -> None:
            payload = data if isinstance(data, dict) else {"value": data}
            self.ctx.handle_run_event(event, payload)
            if event == "confirmation_requested":
                payload = self.confirmation.create_request(payload)
            event_queue.put({"event": event, "payload": payload})

        def confirm_callback(message: str) -> bool:
            if autonomous:
                return False
            return self.confirmation.wait_confirmation()

        def run_agent() -> None:
            try:
                runtime, registry, _ = build_runtime(
                    confirm_callback,
                    logger,
                    event_sink=event_sink,
                    create_run_controller=self.ctx.create_run_controller,
                    settings=self.ctx.settings,
                    server_context=self.ctx,
                )
                self.ctx.set_runtime(runtime)
                summary = runtime.run(task, chat_history=chat_history, images=images or [])
                result_holder["summary"] = summary
                result_holder["tools"] = registry.describe_all()
                result_holder["log_file"] = str(logger.log_file)
                result_holder["autonomous"] = autonomous
            except Exception as e:
                result_holder["error"] = str(e)
            finally:
                self.ctx.clear_confirmation()
                self.ctx.set_runtime(None)
                event_queue.put(None)

        agent_thread = threading.Thread(target=run_agent)
        agent_thread.start()

        agent_finished = False
        while True:
            try:
                event = event_queue.get(timeout=0.1)
                if event is None:
                    agent_finished = True
                    break
                data = json.dumps(event, ensure_ascii=False)
                try:
                    write_callback(f"data: {data}\n\n".encode("utf-8"))
                    _time.sleep(0.01)
                except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                    pass
            except queue.Empty:
                if not agent_thread.is_alive():
                    agent_finished = True
                    break
                continue

        agent_thread.join(timeout=180)
        if agent_thread.is_alive():
            result_holder["error"] = "Агент не ответил в течение 180 секунд"

        if not autonomous:
            final_event = {"event": "__final__", "payload": result_holder}
            data = json.dumps(final_event, ensure_ascii=False)
            try:
                write_callback(f"data: {data}\n\n".encode("utf-8"))
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError, OSError):
                pass

        return result_holder
