"""ConfirmationStore — персистентное хранилище pending confirmations.

При рестарте сервера ожидающие подтверждения восстанавливаются и
возвращаются в UI как незакрытые запросы.

Формат файла: {"schema_version": 1, "pending": [...]}
"""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any


class ConfirmationStore:
    SCHEMA_VERSION = 1

    def __init__(self, file_path: Path | str) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def save(self, pending: dict[str, Any] | None) -> None:
        """Сохраняет текущий pending-запрос (None — очищает)."""
        payload = {
            "schema_version": self.SCHEMA_VERSION,
            "saved_at": time.time(),
            "pending": pending,
        }
        fd, temp_path = tempfile.mkstemp(
            prefix="confirm-", suffix=".json", dir=str(self.file_path.parent)
        )
        try:
            with open(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
            Path(temp_path).replace(self.file_path)
        except Exception:
            Path(temp_path).unlink(missing_ok=True)

    def load(self) -> dict[str, Any] | None:
        """Загружает сохранённый pending-запрос (или None если нет/устарел)."""
        if not self.file_path.exists():
            return None
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return None
        if not isinstance(raw, dict):
            return None
        pending = raw.get("pending")
        if not isinstance(pending, dict):
            return None
        # Считаем pending устаревшим если старше 1 часа
        saved_at = float(raw.get("saved_at", 0))
        if time.time() - saved_at > 3600:
            return None
        return pending

    def clear(self) -> None:
        self.save(None)
