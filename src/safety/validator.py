from __future__ import annotations

from src.agent.schemas import ActionStep
from src.infra.errors import ValidationError
from src.tools.registry import ToolRegistry, ToolSpec


class ActionValidator:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def validate(self, step: ActionStep) -> ToolSpec:
        tool = self.registry.get(step.action)
        if tool is None:
            raise ValidationError(f"Неизвестный инструмент: {step.action}")

        missing = [
            name
            for name, type_name in tool.args_schema.items()
            if not str(type_name).endswith("?") and name not in step.args
        ]
        if missing:
            raise ValidationError(
                f"Для инструмента {tool.name} не хватает аргументов: {', '.join(missing)}"
            )
        return tool
