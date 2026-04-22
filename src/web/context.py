from __future__ import annotations

import threading
from typing import Any

from src.agent.runtime import AgentRuntime
from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import Settings, get_settings


class ServerContext:
    """Разделяемый контекст сервера: настройки, сервисы, состояние сессии."""

    def __init__(self, settings: Settings | None = None) -> None:
        self.settings = settings or get_settings()
        self.memory_store = ChatMemoryStore(self.settings.memory_file)

        # Состояние текущей сессии (защищено локом)
        self._lock = threading.Lock()
        self._current_runtime: AgentRuntime | None = None
        self._pending_confirmation: dict[str, Any] | None = None

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
        """Подтвердить или отклонить pending-запрос. Возвращает True если найдено."""
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
