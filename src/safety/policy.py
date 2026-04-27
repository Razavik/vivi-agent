from __future__ import annotations

from src.agent.schemas import ActionStep
from src.infra.errors import PolicyError
from src.tools.registry import ToolSpec


class SafetyPolicy:
    def classify(self, tool: ToolSpec) -> int:
        return tool.risk_level

    def enforce(self, step: ActionStep, tool: ToolSpec) -> None:
        risk_level = self.classify(tool)
        if risk_level >= 3:
            raise PolicyError(f"Инструмент {tool.name} запрещён в MVP")
