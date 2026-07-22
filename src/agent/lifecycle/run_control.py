from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any, Callable


@dataclass(slots=True)
class RunController:
    run_id: str
    cancel_event: Event
    pause_event: Event
    _inbox_lock: Lock = field(default_factory=Lock)
    _inbox: list[dict[str, Any]] = field(default_factory=list)
    _cancel_callbacks_lock: Lock = field(default_factory=Lock)
    _cancel_callbacks: list[Callable[[], None]] = field(default_factory=list)

    def register_cancel_callback(self, callback: Callable[[], None]) -> None:
        """Регистрирует колбэк, вызываемый при cancel() — например, чтобы прервать
        текущий блокирующий HTTP-запрос к LLM саб-агента, а не только выставить флаг."""
        with self._cancel_callbacks_lock:
            already_cancelled = self.cancel_event.is_set()
            if not already_cancelled:
                self._cancel_callbacks.append(callback)
        if already_cancelled:
            # cancel() уже произошёл — вызываем сразу, иначе колбэк не сработает никогда.
            self._safe_call(callback)

    def cancel(self) -> None:
        self.cancel_event.set()
        with self._cancel_callbacks_lock:
            callbacks = list(self._cancel_callbacks)
            self._cancel_callbacks.clear()
        for callback in callbacks:
            self._safe_call(callback)

    @staticmethod
    def _safe_call(callback: Callable[[], None]) -> None:
        try:
            callback()
        except Exception:
            pass

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def pause(self) -> None:
        self.pause_event.set()

    def resume(self) -> None:
        self.pause_event.clear()

    def is_paused(self) -> bool:
        return self.pause_event.is_set()

    def post_message(self, message: str, sender: str = "operator") -> None:
        with self._inbox_lock:
            self._inbox.append({"sender": sender, "message": message, "type": "message"})

    def replace_task(self, new_task: str) -> None:
        with self._inbox_lock:
            self._inbox.append({"sender": "operator", "message": new_task, "type": "replace_task"})

    def drain_inbox(self) -> list[dict[str, Any]]:
        with self._inbox_lock:
            messages = self._inbox[:]
            self._inbox.clear()
            return messages
