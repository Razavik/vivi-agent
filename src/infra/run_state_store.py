from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path
from typing import Any

SCHEMA_VERSION = 2


class RunStateStore:
    def __init__(self, file_path: Path | str) -> None:
        self.file_path = Path(file_path)
        self.file_path.parent.mkdir(parents=True, exist_ok=True)

    def load(self) -> list[dict[str, Any]]:
        if not self.file_path.exists():
            return []
        try:
            raw = json.loads(self.file_path.read_text(encoding="utf-8"))
        except Exception:
            return []
        # Формат v2: {"schema_version": 2, "runs": [...], "saved_at": ...}
        if isinstance(raw, dict):
            version = raw.get("schema_version", 1)
            runs = raw.get("runs", [])
            if version < SCHEMA_VERSION:
                runs = self._migrate(runs, from_version=version)
        elif isinstance(raw, list):
            # Старый формат v1 — просто список
            runs = self._migrate(raw, from_version=1)
        else:
            return []
        return [item for item in runs if isinstance(item, dict)]

    def save(self, runs: list[dict[str, Any]]) -> None:
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": SCHEMA_VERSION,
            "saved_at": time.time(),
            "runs": runs,
        }
        fd, temp_path = tempfile.mkstemp(prefix="run-state-", suffix=".json", dir=str(self.file_path.parent))
        try:
            with open(fd, "w", encoding="utf-8") as handle:
                json.dump(payload, handle, ensure_ascii=False, indent=2)
            Path(temp_path).replace(self.file_path)
        except Exception:
            try:
                Path(temp_path).unlink(missing_ok=True)
            except Exception:
                pass
            raise

    def _migrate(self, runs: list[Any], from_version: int) -> list[dict[str, Any]]:
        """Применяет миграции схемы. from_version — текущая версия файла."""
        result = [r for r in runs if isinstance(r, dict)]
        if from_version < 2:
            # v1→v2: добавляем поле metadata если отсутствует
            for run in result:
                run.setdefault("metadata", {})
        return result
