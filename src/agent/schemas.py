from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from src.infra.errors import ValidationError


@dataclass(slots=True)
class PlanTask:
    id: str
    content: str
    status: str


@dataclass(slots=True)
class ActionStep:
    thought: str = ""
    action: str = ""
    args: dict[str, Any] = field(default_factory=dict)
    requires_confirmation: bool = False
    done: bool = False
    summary: str | None = None
    plan: list[PlanTask] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionStep":
        if not isinstance(data, dict):
            raise ValidationError("Ответ модели должен быть JSON-объектом")
        thought = data.get("thought")
        action = data.get("action")
        args = data.get("args", {})
        requires_confirmation = data.get("requires_confirmation", False)
        done = data.get("done", False)
        summary = data.get("summary")
        raw_plan = data.get("plan", [])
        if not isinstance(thought, str):
            thought = ""
        if not isinstance(action, str) or not action.strip():
            raise ValidationError("Поле action должно быть непустой строкой")
        if not isinstance(args, dict):
            raise ValidationError("Поле args должно быть объектом")
        if not isinstance(requires_confirmation, bool):
            raise ValidationError("Поле requires_confirmation должно быть bool")
        if not isinstance(done, bool):
            raise ValidationError("Поле done должно быть bool")
        if summary is not None and not isinstance(summary, str):
            raise ValidationError("Поле summary должно быть строкой")
        if not isinstance(raw_plan, list):
            raise ValidationError("Поле plan должно быть списком")

        allowed_statuses = {"pending", "in_progress", "completed"}
        plan: list[PlanTask] = []
        for index, item in enumerate(raw_plan, start=1):
            if not isinstance(item, dict):
                continue
            item_id = item.get("id")
            content = item.get("content")
            status = item.get("status")
            if item_id is None:
                item_id = f"task_{index}"
            if not isinstance(item_id, str) or not item_id.strip():
                continue
            if not isinstance(content, str) or not content.strip():
                continue
            if not isinstance(status, str) or status not in allowed_statuses:
                status = "pending"
            plan.append(PlanTask(id=item_id.strip(), content=content.strip(), status=status))

        return cls(
            thought=thought.strip(),
            action=action.strip(),
            args=args,
            requires_confirmation=requires_confirmation,
            done=done,
            summary=summary.strip() if isinstance(summary, str) else None,
            plan=plan,
        )
