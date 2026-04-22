from __future__ import annotations

from dataclasses import dataclass, field
from threading import Event, Lock
from typing import Any


@dataclass(slots=True)
class RunController:
    run_id: str
    cancel_event: Event
    pause_event: Event
    _inbox_lock: Lock = field(default_factory=Lock)
    _inbox: list[dict[str, Any]] = field(default_factory=list)

    def cancel(self) -> None:
        self.cancel_event.set()

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()

    def pause(self) -> None:
        self.pause_event.set()

    def resume(self) -> None:
        self.pause_event.clear()

    def is_paused(self) -> bool:
        return self.pause_event.is_set()

    def post_message(self, message: str, sender: str = "director") -> None:
        with self._inbox_lock:
            self._inbox.append({"sender": sender, "message": message, "type": "message"})

    def replace_task(self, new_task: str) -> None:
        with self._inbox_lock:
            self._inbox.append({"sender": "director", "message": new_task, "type": "replace_task"})

    def drain_inbox(self) -> list[dict[str, Any]]:
        with self._inbox_lock:
            messages = self._inbox[:]
            self._inbox.clear()
            return messages
