from __future__ import annotations

import pytest

from src.agent.core.schemas import ActionStep
from src.infra.errors import ValidationError
from src.safety.validator import ActionValidator
from src.tools.core.registry import ToolRegistry, ToolSpec


@pytest.fixture()
def registry() -> ToolRegistry:
    reg = ToolRegistry()
    reg.register(
        ToolSpec(
            name="get_messages",
            description="",
            handler=lambda **kw: None,
            args_schema={"chat_id": "str", "limit": "int?"},
            risk_level="low",
        )
    )
    return reg


def test_string_int_arg_is_coerced(registry: ToolRegistry) -> None:
    # Реальный кейс: модель (замечено на бесплатных через OpenCode ACP)
    # отдала "limit": "20" вместо 20 — раньше это падало с ValidationError.
    step = ActionStep(
        action="get_messages", args={"chat_id": "123", "limit": "20"}, done=False
    )
    ActionValidator(registry).validate(step)
    assert step.args["limit"] == 20
    assert isinstance(step.args["limit"], int)


def test_non_numeric_string_still_rejected(registry: ToolRegistry) -> None:
    step = ActionStep(
        action="get_messages", args={"chat_id": "123", "limit": "many"}, done=False
    )
    with pytest.raises(ValidationError):
        ActionValidator(registry).validate(step)


def test_already_correct_type_untouched(registry: ToolRegistry) -> None:
    step = ActionStep(
        action="get_messages", args={"chat_id": "123", "limit": 20}, done=False
    )
    ActionValidator(registry).validate(step)
    assert step.args["limit"] == 20
