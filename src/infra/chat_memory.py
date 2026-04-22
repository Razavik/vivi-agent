from __future__ import annotations

import json
import os
import tempfile
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, ClassVar

from src.agent.state import ChatMessage, Observation


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

            data["chat_history"] = chat_history[-200:]
            data["updated_at"] = datetime.now(UTC).isoformat()
            self._write_unlocked(data)
            return data

    def clear(self) -> dict[str, Any]:
        with self._lock:
            data = {"chat_history": [], "updated_at": datetime.now(UTC).isoformat()}
            self._write_unlocked(data)
            return data

    def _load_unlocked(self) -> dict[str, Any]:
        if not self.file_path.exists():
            return {"chat_history": [], "updated_at": None}
        try:
            data = json.loads(self.file_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"chat_history": [], "updated_at": None}
        if not isinstance(data, dict):
            return {"chat_history": [], "updated_at": None}
        chat_history = data.get("chat_history")
        updated_at = data.get("updated_at")
        return {
            "chat_history": chat_history if isinstance(chat_history, list) else [],
            "updated_at": updated_at if isinstance(updated_at, str) else None,
        }

    def _write_unlocked(self, data: dict[str, Any]) -> None:
        serialized = json.dumps(data, ensure_ascii=False, indent=2)
        fd, temp_path = tempfile.mkstemp(
            prefix=f"{self.file_path.name}.",
            suffix=".tmp",
            dir=str(self.file_path.parent),
            text=True,
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="") as temp_file:
                temp_file.write(serialized)
                temp_file.flush()
                os.fsync(temp_file.fileno())
            os.replace(temp_path, self.file_path)
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
