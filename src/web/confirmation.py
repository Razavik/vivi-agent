from __future__ import annotations

import threading
from typing import Any
from uuid import uuid4

from src.web.context import ServerContext


class ConfirmationManager:
    """Управление запросами на подтверждение от агента к пользователю."""

    def __init__(self, ctx: ServerContext) -> None:
        self.ctx = ctx

    def create_request(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Создать запрос на подтверждение, возвращает обновлённый payload с request_id."""
        request_id = uuid4().hex
        pending_event = threading.Event()
        pending = {
            "request_id": request_id,
            "approved": None,
            "event": pending_event,
        }
        self.ctx.set_pending_confirmation(pending)
        return {**payload, "request_id": request_id}

    def wait_confirmation(self, timeout: float = 900) -> bool:
        """Ждёт подтверждения от пользователя. Возвращает True если одобрено."""
        pending = self.ctx.get_pending_confirmation()
        if not pending:
            return False
        event: threading.Event = pending["event"]
        if not event.wait(timeout=timeout):
            self.ctx.clear_confirmation()
            return False
        pending = self.ctx.get_pending_confirmation()
        if pending:
            result = bool(pending.get("approved"))
            self.ctx.clear_confirmation()
            return result
        return False

    def handle_confirm_request(self, request_id: str, approved: bool) -> bool:
        """Обработать входящий запрос подтверждения от клиента. Возвращает True если найдено."""
        return self.ctx.confirm_pending(request_id, approved)
