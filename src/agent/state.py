from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class PlanItem:
    id: str
    content: str
    status: str


@dataclass(slots=True)
class ChatMessage:
    role: str
    content: str
    thought: str | None = None
    plan: list[PlanItem] = field(default_factory=list)


@dataclass(slots=True)
class Observation:
    step: int
    action: str
    result: Any
    success: bool
    thought: str | None = None


@dataclass(slots=True)
class SessionState:
    user_goal: str
    chat_history: list[ChatMessage] = field(default_factory=list)
    observations: list[Observation] = field(default_factory=list)
    memory_chat_history: list[ChatMessage] = field(default_factory=list)
    consecutive_errors: int = 0
    plan: list[PlanItem] = field(default_factory=list)

    def add_observation(self, observation: Observation) -> None:
        self.observations.append(observation)

    def set_plan(self, items: list[PlanItem]) -> None:
        self.plan = items

    def add_chat_message(
        self,
        role: str,
        content: str,
        thought: str | None = None,
        plan: list[PlanItem] | None = None,
    ) -> None:
        self.chat_history.append(
            ChatMessage(role=role, content=content, thought=thought, plan=list(plan or []))
        )

    def compact_observations(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        for observation in self.observations[-5:]:
            items.append(
                {
                    "step": observation.step,
                    "action": observation.action,
                    "success": observation.success,
                    "result": observation.result,
                    "thought": observation.thought,
                }
            )
        return items

    def compact_chat_history(self) -> list[dict[str, str]]:
        items: list[dict[str, Any]] = []
        for item in self.chat_history[-12:]:
            record: dict[str, Any] = {"role": item.role, "content": item.content}
            if item.plan:
                record["plan"] = [
                    {"id": plan_item.id, "content": plan_item.content, "status": plan_item.status}
                    for plan_item in item.plan
                ]
            items.append(record)
        return items

    def compact_plan(self) -> list[dict[str, str]]:
        return [
            {"id": item.id, "content": item.content, "status": item.status}
            for item in self.plan
        ]

    def compact_memory(self) -> dict[str, list[dict[str, Any]]]:
        return {
            "chat_history": [
                {
                    "role": item.role,
                    "content": item.content,
                    **(
                        {
                            "plan": [
                                {
                                    "id": plan_item.id,
                                    "content": plan_item.content,
                                    "status": plan_item.status,
                                }
                                for plan_item in item.plan
                            ]
                        }
                        if item.plan
                        else {}
                    ),
                }
                for item in self.memory_chat_history[-40:]
            ]
        }
