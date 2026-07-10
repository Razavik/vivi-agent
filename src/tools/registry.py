from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], Any]


def result_indicates_failure(result: Any) -> bool:
    """Эвристика: инструмент вернул словарь-ошибку вместо выброса исключения.

    Многие инструменты не бросают исключение, а возвращают ``{"ok": False, ...}``
    или ``{"error": "..."}``. Без этой проверки такой результат записывается как
    успешный шаг, и ошибка не видна ни агенту, ни в UI.
    """
    if not isinstance(result, dict):
        return False
    if result.get("ok") is False or result.get("success") is False:
        return True
    error = result.get("error")
    if isinstance(error, str):
        return bool(error.strip())
    if isinstance(error, (list, dict)):
        return bool(error)
    return error is not None


@dataclass(slots=True)
class ToolSpec:
    name: str
    description: str
    risk_level: int
    handler: ToolHandler
    args_schema: dict[str, str]

    def describe(self) -> dict[str, object]:
        return {
            "name": self.name,
            "description": self.description,
            "risk_level": self.risk_level,
            "args_schema": self.args_schema,
        }


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}

    def register(self, spec: ToolSpec) -> None:
        self._tools[spec.name] = spec

    def get(self, name: str) -> ToolSpec | None:
        return self._tools.get(name)

    def describe_all(self) -> list[dict[str, object]]:
        return [tool.describe() for tool in self._tools.values()]
