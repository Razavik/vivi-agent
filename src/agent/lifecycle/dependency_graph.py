"""DependencyGraph — зависимости между run-ами через артефакты.

Позволяет:
- объявить зависимость: run B ждёт артефакт X от run A
- пометить артефакт готовым (mark_ready)
- автоматически уведомить ожидающие run через callback

Потокобезопасен.
"""
from __future__ import annotations

import threading
from typing import Any, Callable


class DependencyGraph:
    def __init__(self, on_ready: Callable[[str, str, str], None] | None = None) -> None:
        """on_ready(waiting_run_id, artifact_name, provider_run_id)"""
        self._lock = threading.Lock()
        # artifact_key → list of (waiting_run_id,)
        self._waiters: dict[str, list[str]] = {}
        # artifact_key → provider info
        self._ready: dict[str, dict[str, Any]] = {}
        self._on_ready = on_ready

    @staticmethod
    def _key(artifact_name: str, provider_run_id: str) -> str:
        return f"{provider_run_id}::{artifact_name}"

    def wait_for_artifact(self, waiting_run_id: str, artifact_name: str, provider_run_id: str) -> bool:
        """Регистрирует ожидание артефакта. Возвращает True если артефакт уже готов."""
        key = self._key(artifact_name, provider_run_id)
        with self._lock:
            if key in self._ready:
                return True
            self._waiters.setdefault(key, [])
            if waiting_run_id not in self._waiters[key]:
                self._waiters[key].append(waiting_run_id)
        return False

    def mark_artifact_ready(self, artifact_name: str, provider_run_id: str, meta: dict[str, Any] | None = None) -> list[str]:
        """Помечает артефакт готовым и возвращает список разблокированных run."""
        key = self._key(artifact_name, provider_run_id)
        with self._lock:
            self._ready[key] = {"artifact_name": artifact_name, "provider_run_id": provider_run_id, **(meta or {})}
            notified = list(self._waiters.pop(key, []))

        if self._on_ready:
            for run_id in notified:
                try:
                    self._on_ready(run_id, artifact_name, provider_run_id)
                except Exception:
                    pass

        return notified

    def is_ready(self, artifact_name: str, provider_run_id: str) -> bool:
        key = self._key(artifact_name, provider_run_id)
        with self._lock:
            return key in self._ready

    def get_waiters(self, artifact_name: str, provider_run_id: str) -> list[str]:
        key = self._key(artifact_name, provider_run_id)
        with self._lock:
            return list(self._waiters.get(key, []))

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "waiters": {k: list(v) for k, v in self._waiters.items()},
                "ready": dict(self._ready),
            }
