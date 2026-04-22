from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from datetime import datetime, UTC
from pathlib import Path
from typing import Any


class SessionLogger:
    def __init__(self, log_dir: Path) -> None:
        log_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
        self.log_file = log_dir / f"session-{timestamp}.json"
        self.records: list[dict[str, Any]] = []

    def write(self, event: str, payload: Any) -> None:
        record = {
            "timestamp": datetime.now(UTC).isoformat(),
            "event": event,
            "payload": self._normalize(payload),
        }
        self.records.append(record)
        self._save()

    def _save(self) -> None:
        with self.log_file.open("w", encoding="utf-8") as handle:
            json.dump(self.records, handle, ensure_ascii=False, indent=2)

    def _normalize(self, value: Any) -> Any:
        if is_dataclass(value):
            return asdict(value)
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._normalize(item) for item in value]
        return value
