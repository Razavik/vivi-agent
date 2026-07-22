from __future__ import annotations

import pytest

from src.agent.core.schemas import ActionStep, SubAgentResult
from src.infra.errors import ValidationError


def test_from_dict_minimal() -> None:
    step = ActionStep.from_dict({"action": "noop", "args": {}, "done": False})
    assert step.action == "noop"
    assert step.args == {}
    assert step.done is False


def test_from_dict_requires_action() -> None:
    with pytest.raises(ValidationError):
        ActionStep.from_dict({"action": "", "args": {}, "done": False})


def test_from_dict_done_requires_finish_task() -> None:
    with pytest.raises(ValidationError):
        ActionStep.from_dict({"action": "noop", "args": {}, "done": True})


def test_from_dict_rejects_non_object() -> None:
    with pytest.raises(ValidationError):
        ActionStep.from_dict([])  # type: ignore[arg-type]


def test_from_dict_args_must_be_object() -> None:
    with pytest.raises(ValidationError):
        ActionStep.from_dict({"action": "noop", "args": [], "done": False})


def test_from_dict_normalizes_plan() -> None:
    step = ActionStep.from_dict(
        {
            "action": "noop",
            "args": {},
            "done": False,
            "plan": [
                {"content": "do it", "status": "weird"},  # missing id, bad status
                {"id": "t2", "content": "second", "status": "completed"},
                "not-a-dict",
            ],
        }
    )
    assert len(step.plan) == 2
    assert step.plan[0].id == "task_1"
    assert step.plan[0].status == "pending"  # invalid status coerced
    assert step.plan[1].status == "completed"


def test_subagent_result_from_raw_success() -> None:
    res = SubAgentResult.from_raw({"run_id": "r1", "agent": "file", "success": True})
    assert res.status == "done"
    assert res.success is True


def test_subagent_result_from_raw_failure() -> None:
    res = SubAgentResult.from_raw({"run_id": "r1", "agent": "file", "success": False})
    assert res.status == "failed"
    assert res.success is False


def test_subagent_result_parses_json_result_payload() -> None:
    res = SubAgentResult.from_raw(
        {
            "run_id": "r1",
            "agent": "file",
            "success": True,
            "result": '{"summary": "did the thing", "changed_files": ["a.txt"]}',
        }
    )
    assert res.summary == "did the thing"
    assert res.changed_files == ["a.txt"]


def test_subagent_result_blocked_needs_input() -> None:
    res = SubAgentResult.from_raw(
        {"run_id": "r1", "agent": "file", "success": False, "status": "blocked"}
    )
    assert res.needs_user_input is True
