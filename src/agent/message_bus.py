"""MessageBus — формальная шина сообщений между компонентами системы.

Каждое сообщение имеет:
- msg_id      : уникальный UUID
- correlation_id : связь с родительским сообщением (опционально)
- msg_type    : тип сообщения (run_started, progress_update, question, ...)
- sender      : кто отправил (director / agent_name / system)
- run_id      : к какому run относится (опционально)
- payload     : произвольный dict с данными
- timestamp   : время создания

Шина потокобезопасна, хранит последние N сообщений и позволяет
подписаться на все или конкретный run.
"""
from __future__ import annotations

import threading
import time
import uuid
from collections import deque
from dataclasses import dataclass, field
from typing import Any, Callable


MSG_TYPES = frozenset({
    "run_started",
    "progress_update",
    "heartbeat",
    "question_to_director",
    "answer_from_director",
    "directive",
    "pause_requested",
    "resume_requested",
    "cancel_requested",
    "task_replaced",
    "artifact_created",
    "dependency_wait",
    "dependency_ready",
    "run_finished",
    "run_failed",
    "outbox_message",       # произвольное сообщение от саб-агента директору
    "system_event",
})


@dataclass
class BusMessage:
    msg_type: str
    sender: str
    payload: dict[str, Any]
    run_id: str = ""
    correlation_id: str = ""
    msg_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "msg_id": self.msg_id,
            "correlation_id": self.correlation_id,
            "msg_type": self.msg_type,
            "sender": self.sender,
            "run_id": self.run_id,
            "payload": self.payload,
            "timestamp": self.timestamp,
        }


Subscriber = Callable[[BusMessage], None]


class MessageBus:
    """Потокобезопасная шина сообщений с историей и подписками."""

    def __init__(self, max_history: int = 500) -> None:
        self._lock = threading.Lock()
        self._history: deque[BusMessage] = deque(maxlen=max_history)
        self._subscribers: list[tuple[str | None, Subscriber]] = []  # (run_id_filter, callback)

    def publish(
        self,
        msg_type: str,
        sender: str,
        payload: dict[str, Any],
        run_id: str = "",
        correlation_id: str = "",
    ) -> BusMessage:
        """Публикует сообщение и рассылает подписчикам."""
        msg = BusMessage(
            msg_type=msg_type,
            sender=sender,
            payload=payload,
            run_id=run_id,
            correlation_id=correlation_id,
        )
        with self._lock:
            self._history.append(msg)
            subscribers = list(self._subscribers)

        for run_filter, callback in subscribers:
            if run_filter is None or run_filter == run_id:
                try:
                    callback(msg)
                except Exception:
                    pass

        return msg

    def subscribe(self, callback: Subscriber, run_id: str | None = None) -> None:
        """Подписывается на все сообщения (run_id=None) или конкретного run."""
        with self._lock:
            self._subscribers.append((run_id, callback))

    def unsubscribe(self, callback: Subscriber) -> None:
        with self._lock:
            self._subscribers = [(r, c) for r, c in self._subscribers if c is not callback]

    def get_history(
        self,
        run_id: str | None = None,
        msg_type: str | None = None,
        limit: int = 100,
    ) -> list[BusMessage]:
        """Возвращает историю сообщений с опциональной фильтрацией."""
        with self._lock:
            msgs = list(self._history)
        if run_id:
            msgs = [m for m in msgs if m.run_id == run_id]
        if msg_type:
            msgs = [m for m in msgs if m.msg_type == msg_type]
        return msgs[-limit:]

    def clear(self) -> None:
        with self._lock:
            self._history.clear()
