from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal


EventName = Literal[
    "agent_error",
    "agent_warning",
    "assistant_stream",
    "cancelled",
    "confirmation_requested",
    "confirmation_result",
    "context_tokens",
    "intermediate_message",
    "llm_step",
    "loop_detected",
    "plan_updated",
    "session_finished",
    "session_started",
    "sub_agent_answer",
    "sub_agent_error",
    "sub_agent_finished",
    "sub_agent_paused",
    "sub_agent_plan_updated",
    "sub_agent_question",
    "sub_agent_resumed",
    "sub_agent_started",
    "sub_agent_step",
    "sub_agent_task_replaced",
    "sub_agent_tool_result",
    "sub_agent_warning",
    "thought_stream",
    "tool_result",
]


@dataclass(slots=True)
class AgentEvent:
    event: str
    payload: dict[str, Any]
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def normalize_event(event: str, payload: object) -> AgentEvent:
    if isinstance(payload, dict):
        data = payload
    else:
        data = {"value": payload}
    return AgentEvent(event=event, payload=data)
