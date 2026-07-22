from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from src.agent.core.state import ChatMessage, Observation


class ChatMemoryStore:
    _locks_guard: ClassVar[threading.Lock] = threading.Lock()
    _locks: ClassVar[dict[str, threading.RLock]] = {}

    def __init__(self, file_path: Path) -> None:
        self.file_path = file_path
        self.file_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = self._get_lock(file_path)

    @classmethod
    def _get_lock(cls, file_path: Path) -> threading.RLock:
        key = str(file_path.resolve())
        with cls._locks_guard:
            existing = cls._locks.get(key)
            if existing is not None:
                return existing
            lock = threading.RLock()
            cls._locks[key] = lock
            return lock

    def load(self) -> dict[str, Any]:
        with self._lock:
            return self._load_unlocked()

    def append_session(
        self,
        session_chat_history: list[ChatMessage],
        session_observations: list[Observation],
        model: str | None = None,
    ) -> dict[str, Any]:
        with self._lock:
            data = self._load_unlocked()
            chat_history = data["chat_history"]

            session_actions = []
            for observation in session_observations:
                if observation.action == "finish_task":
                    continue
                record = {
                    "step": observation.step,
                    "action": observation.action,
                    "success": observation.success,
                    "result": self._normalize(observation.result),
                }
                if observation.thought:
                    record["thought"] = observation.thought
                session_actions.append(record)

            for i, item in enumerate(session_chat_history):
                record = {"role": item.role, "content": item.content}
                if item.interrupted_by_user:
                    record["interrupted_by_user"] = True
                if item.thought:
                    record["thought"] = item.thought
                if item.plan:
                    record["plan"] = [
                        {
                            "id": plan_item.id,
                            "content": plan_item.content,
                            "status": plan_item.status,
                        }
                        for plan_item in item.plan
                    ]
                if item.role == "assistant" and i == len(session_chat_history) - 1:
                    if session_actions:
                        record["actions"] = session_actions
                    if model:
                        record["model"] = model
                chat_history.append(record)

            session_record: dict[str, Any] = {
                "task": session_chat_history[0].content
                if session_chat_history and session_chat_history[0].role == "user"
                else "",
                "model": model or "",
                "result": session_chat_history[-1].content
                if session_chat_history and session_chat_history[-1].role == "assistant"
                else "",
                "steps": session_actions,
                "plan": [
                    {"id": p.id, "content": p.content, "status": p.status}
                    for p in (session_chat_history[-1].plan if session_chat_history else [])
                ],
            }
            sessions = data.get("sessions")
            if not isinstance(sessions, list):
                sessions = []
            sessions.append(session_record)

            data["chat_history"] = chat_history[-200:]
            data["sessions"] = sessions[-200:]
            data["updated_at"] = datetime.now(UTC).isoformat()
            self._write_unlocked(data)
            return data

    def write_snapshot(
        self,
        base_history: list[dict[str, Any]],
        session_chat_history: list[ChatMessage],
        session_observations: list[Observation],
        model: str | None = None,
    ) -> None:
        """Записывает текущее состояние сессии поверх файла (промежуточный снапшот).
        base_history — история ДО начала текущей сессии, не накапливает дубли."""
        with self._lock:
            data = self._load_unlocked()
            session_actions = []
            for observation in session_observations:
                if observation.action == "finish_task":
                    continue
                record: dict[str, Any] = {
                    "step": observation.step,
                    "action": observation.action,
                    "success": observation.success,
                    "result": self._normalize(observation.result),
                }
                if observation.thought:
                    record["thought"] = observation.thought
                session_actions.append(record)

            chat_history = list(base_history)
            for i, item in enumerate(session_chat_history):
                record = {"role": item.role, "content": item.content}
                if item.interrupted_by_user:
                    record["interrupted_by_user"] = True
                if item.thought:
                    record["thought"] = item.thought
                if item.plan:
                    record["plan"] = [
                        {"id": p.id, "content": p.content, "status": p.status}
                        for p in item.plan
                    ]
                if item.role == "assistant" and i == len(session_chat_history) - 1:
                    if session_actions:
                        record["actions"] = session_actions
                    if model:
                        record["model"] = model
                chat_history.append(record)

            sessions = data.get("sessions")
            if not isinstance(sessions, list):
                sessions = []
            sessions.append({
                "task": session_chat_history[0].content
                if session_chat_history and session_chat_history[0].role == "user"
                else "",
                "model": model or "",
                "result": session_chat_history[-1].content
                if session_chat_history and session_chat_history[-1].role == "assistant"
                else "",
                "steps": session_actions,
                "plan": [
                    {"id": p.id, "content": p.content, "status": p.status}
                    for p in (session_chat_history[-1].plan if session_chat_history else [])
                ],
            })

            data: dict[str, Any] = {
                "chat_history": chat_history[-200:],
                "sessions": sessions[-200:],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._write_unlocked(data)

    def replace_chat_history(self, chat_history: list[dict[str, Any]]) -> None:
        """Полностью заменяет chat_history — например, после сжатия истории
        через LLM (см. Routes.compress_memory). sessions и остальные поля
        файла сохраняются как есть, трогается только chat_history."""
        with self._lock:
            data = self._load_unlocked()
            data["chat_history"] = chat_history
            data["updated_at"] = datetime.now(UTC).isoformat()
            self._write_unlocked(data)

    def clear(self) -> dict[str, Any]:
        with self._lock:
            data = {
                "chat_history": [],
                "sessions": [],
                "updated_at": datetime.now(UTC).isoformat(),
            }
            self._write_unlocked(data)
            return data

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.file_path.exists():
            return {"chat_history": [], "sessions": [], "updated_at": None}
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"chat_history": [], "sessions": [], "updated_at": None}
        if not isinstance(data, dict):
            return {"chat_history": [], "sessions": [], "updated_at": None}
        chat_history = data.get("chat_history")
        sessions = data.get("sessions")
        updated_at = data.get("updated_at")
        return {
            "chat_history": chat_history if isinstance(chat_history, list) else [],
            "sessions": sessions if isinstance(sessions, list) else [],
            "updated_at": updated_at if isinstance(updated_at, str) else None,
        }

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        serialized = json.dumps(data, ensure_ascii=False, indent=2)
        parent = self.file_path.parent.resolve()
        target = self.file_path.resolve()
        fd, temp_path = tempfile.mkstemp(
            prefix=f"{self.file_path.name}.",
            suffix=".tmp",
            dir=str(parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as temp_file:
                temp_file.write(serialized)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            last_error: OSError | None = None
            for attempt in range(20):
                try:
                    os.replace(temp_path, target)
                    last_error = None
                    break
                except PermissionError as exc:
                    last_error = exc
                    time.sleep(0.05 * (attempt + 1))
            if last_error is not None:
                raise last_error
        finally:
            try:
                if os.path.exists(temp_path):
                    os.unlink(temp_path)
            except OSError:
                pass

    def _normalize(self, value: Any) -> Any:
        if isinstance(value, Path):
            return str(value)
        if isinstance(value, dict):
            return {str(key): self._normalize(item) for key, item in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._normalize(item) for item in value]
        return value
