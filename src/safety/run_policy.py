"""Run-level permissions и квоты для саб-агентов.

RunPolicy задаётся при создании run (через DelegateTools) и ограничивает:
- какие инструменты допустимы (permission_level)
- сколько шагов, tool-вызовов и секунд runtime разрешено

Уровни доступа (permission_level):
  0 — read-only    : только инструменты с risk_level == 0
  1 — file-write   : risk_level <= 1 (чтение + запись файлов, без опасных)
  2 — standard     : risk_level <= 2 (всё кроме risk_level >= 3)
  3 — unrestricted : без ограничений по уровню
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

from src.infra.errors import PolicyError
from src.tools.registry import ToolSpec


@dataclass
class RunQuota:
    max_steps: int = 0            # 0 — без лимита
    max_tool_calls: int = 0       # 0 — без лимита
    max_runtime_seconds: float = 0.0  # 0 — без лимита


@dataclass
class RunPolicy:
    """Политика безопасности для одного run."""

    permission_level: int = 2      # 0-read-only, 1-file-write, 2-standard, 3-unrestricted
    quota: RunQuota = field(default_factory=RunQuota)

    # Внутренние счётчики (заполняются в процессе выполнения)
    _steps_done: int = field(default=0, init=False, repr=False)
    _tool_calls_done: int = field(default=0, init=False, repr=False)
    _started_at: float = field(default_factory=time.monotonic, init=False, repr=False)

    def enforce_tool(self, tool: ToolSpec) -> None:
        """Проверяет, разрешён ли инструмент для этого run."""
        if self.permission_level >= 3:
            return
        if tool.risk_level > self.permission_level:
            level_name = {0: "read-only", 1: "file-write", 2: "standard"}.get(self.permission_level, str(self.permission_level))
            raise PolicyError(
                f"Инструмент '{tool.name}' (risk_level={tool.risk_level}) "
                f"запрещён для этого run (permission_level={level_name})"
            )

    def tick_step(self) -> None:
        """Вызывается перед каждым шагом агента. Проверяет квоты."""
        self._steps_done += 1
        if self.quota.max_steps > 0 and self._steps_done > self.quota.max_steps:
            raise PolicyError(
                f"Превышена квота шагов: {self._steps_done} > {self.quota.max_steps}"
            )

    def tick_tool_call(self) -> None:
        """Вызывается при каждом вызове инструмента."""
        self._tool_calls_done += 1
        if self.quota.max_tool_calls > 0 and self._tool_calls_done > self.quota.max_tool_calls:
            raise PolicyError(
                f"Превышена квота tool-вызовов: {self._tool_calls_done} > {self.quota.max_tool_calls}"
            )

    def check_runtime(self) -> None:
        """Проверяет, не вышел ли run за лимит времени."""
        if self.quota.max_runtime_seconds <= 0:
            return
        elapsed = time.monotonic() - self._started_at
        if elapsed > self.quota.max_runtime_seconds:
            raise PolicyError(
                f"Превышен лимит времени run: {elapsed:.0f}s > {self.quota.max_runtime_seconds:.0f}s"
            )

    def stats(self) -> dict[str, Any]:
        """Текущие счётчики для логирования."""
        return {
            "steps_done": self._steps_done,
            "tool_calls_done": self._tool_calls_done,
            "runtime_seconds": round(time.monotonic() - self._started_at, 1),
            "permission_level": self.permission_level,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "RunPolicy":
        """Создаёт RunPolicy из словаря (передаётся от директора через delegate_task)."""
        level = int(data.get("permission_level", 2))
        quota_data = data.get("quota", {})
        quota = RunQuota(
            max_steps=int(quota_data.get("max_steps", 0)),
            max_tool_calls=int(quota_data.get("max_tool_calls", 0)),
            max_runtime_seconds=float(quota_data.get("max_runtime_seconds", 0.0)),
        )
        return cls(permission_level=level, quota=quota)
