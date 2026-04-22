from __future__ import annotations

from dataclasses import dataclass
from threading import Event


@dataclass(slots=True)
class RunController:
    run_id: str
    cancel_event: Event

    def cancel(self) -> None:
        self.cancel_event.set()

    def is_cancelled(self) -> bool:
        return self.cancel_event.is_set()
