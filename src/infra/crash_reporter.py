"""CrashReporter — сохраняет диагностику при падении агента.

Записывает crash-файл с:
- временем падения
- трассировкой стека
- состоянием run (шаг, задача, статус)
- последними наблюдениями

Файлы хранятся в data/crashes/ и не ротируются автоматически.
"""
from __future__ import annotations

import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any


class CrashReporter:
    def __init__(self, crash_dir: Path | str) -> None:
        self.crash_dir = Path(crash_dir)
        self.crash_dir.mkdir(parents=True, exist_ok=True)

    def report(
        self,
        exc: BaseException,
        context: dict[str, Any] | None = None,
    ) -> Path:
        """Сохраняет crash-отчёт и возвращает путь к файлу."""
        import uuid as _uuid
        ts = int(time.time())
        uid = _uuid.uuid4().hex[:8]
        filename = f"crash_{ts}_{uid}.json"
        path = self.crash_dir / filename

        payload = {
            "timestamp": ts,
            "exception_type": type(exc).__name__,
            "exception_message": str(exc),
            "traceback": traceback.format_exc(),
            "python_version": sys.version,
            "context": context or {},
        }

        try:
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            pass

        return path

    def list_reports(self, limit: int = 20) -> list[dict[str, Any]]:
        """Возвращает список последних crash-отчётов."""
        files = sorted(self.crash_dir.glob("crash_*.json"), reverse=True)
        result = []
        for f in files[:limit]:
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
                result.append({
                    "file": f.name,
                    "timestamp": data.get("timestamp"),
                    "exception_type": data.get("exception_type"),
                    "exception_message": data.get("exception_message", "")[:200],
                })
            except Exception:
                pass
        return result

    def read_report(self, filename: str) -> dict[str, Any]:
        """Читает полный crash-отчёт по имени файла."""
        path = self.crash_dir / filename
        if not path.exists():
            return {"error": f"Отчёт {filename!r} не найден"}
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            return {"error": str(exc)}
