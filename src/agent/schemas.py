from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from src.llm.ollama_client import LLMResponse

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
    done: bool = False
    summary: str | None = None
    plan: list[PlanTask] = field(default_factory=list)
    _llm_response: "LLMResponse | None" = field(default=None, repr=False, compare=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ActionStep":
        if not isinstance(data, dict):
            raise ValidationError("Ответ модели должен быть JSON-объектом")
        thought = data.get("thought")
        action = data.get("action")
        args = data.get("args", {})
        done = data.get("done", False)
        summary = data.get("summary")
        raw_plan = data.get("plan", [])
        if not isinstance(thought, str):
            thought = ""
        if not isinstance(action, str) or not action.strip():
            raise ValidationError("Поле action должно быть непустой строкой")
        if not isinstance(args, dict):
            raise ValidationError("Поле args должно быть объектом")
        if not isinstance(done, bool):
            done = False
        if summary is not None and not isinstance(summary, str):
            summary = str(summary)
        if not isinstance(raw_plan, list):
            raw_plan = []

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
            done=done,
            summary=summary.strip() if isinstance(summary, str) else None,
            plan=plan,
        )


@dataclass(slots=True)
class SubAgentResult:
    run_id: str
    agent_name: str
    status: str
    success: bool
    summary: str
    steps: int | None = None
    changed_files: list[str] = field(default_factory=list)
    created_artifacts: list[str] = field(default_factory=list)
    verification: list[str] = field(default_factory=list)
    risks: list[str] = field(default_factory=list)
    needs_user_input: bool = False
    question: str = ""
    error: str = ""
    cancelled: bool = False
    raw_result: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_raw(cls, raw: dict[str, Any]) -> "SubAgentResult":
        run_id = str(raw.get("run_id", ""))
        agent_name = str(raw.get("agent_name", raw.get("agent", "")))
        success = bool(raw.get("success", False))
        cancelled = bool(raw.get("cancelled", False))
        parsed = cls._parse_result_payload(raw.get("result"))

        explicit_status = raw.get("status") or parsed.get("status")
        status = cls._normalize_status(explicit_status, success=success, cancelled=cancelled)

        summary = cls._first_text(
            parsed.get("summary"),
            raw.get("summary"),
            raw.get("result"),
            raw.get("error"),
        )
        error = cls._first_text(raw.get("error"), parsed.get("error"))
        question = cls._first_text(raw.get("question"), parsed.get("question"))
        needs_user_input = bool(raw.get("needs_user_input", parsed.get("needs_user_input", False)))
        if status in {"blocked", "waiting_user"}:
            needs_user_input = True

        return cls(
            run_id=run_id,
            agent_name=agent_name,
            status=status,
            success=success and status == "done",
            summary=summary,
            steps=cls._optional_int(raw.get("steps")),
            changed_files=cls._string_list(raw.get("changed_files", parsed.get("changed_files", []))),
            created_artifacts=cls._string_list(raw.get("created_artifacts", parsed.get("created_artifacts", []))),
            verification=cls._string_list(raw.get("verification", parsed.get("verification", []))),
            risks=cls._string_list(raw.get("risks", parsed.get("risks", []))),
            needs_user_input=needs_user_input,
            question=question,
            error=error,
            cancelled=cancelled,
            raw_result=raw.get("result"),
        )

    @staticmethod
    def _parse_result_payload(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value
        if not isinstance(value, str):
            return {}
        text = value.strip()
        if not text.startswith("{"):
            return {}
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}

    @staticmethod
    def _normalize_status(value: Any, *, success: bool, cancelled: bool) -> str:
        allowed = {"done", "blocked", "failed", "cancelled", "waiting_user"}
        if isinstance(value, str):
            cleaned = value.strip().lower()
            if cleaned in allowed:
                return cleaned
            if cleaned in {"finished", "success", "completed"}:
                return "done"
            if cleaned in {"error", "failure"}:
                return "failed"
        if cancelled:
            return "cancelled"
        return "done" if success else "failed"

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    @staticmethod
    def _string_list(value: Any) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _optional_int(value: Any) -> int | None:
        try:
            return int(value)
        except (TypeError, ValueError):
            return None
