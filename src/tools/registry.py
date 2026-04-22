from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[[dict[str, Any]], Any]


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
