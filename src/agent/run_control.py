from __future__ import annotations

from dataclasses import dataclass
from threading import Event


@dataclass(slots=True)
class RunController:
    run_id: str
    cancel_event: Event
    pause_event: Event

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
