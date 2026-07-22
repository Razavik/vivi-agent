from __future__ import annotations

from src.tools.core.registry import result_indicates_failure


def test_ok_false_is_failure() -> None:
    assert result_indicates_failure({"ok": False, "error": "run не найден"}) is True


def test_success_false_is_failure() -> None:
    assert result_indicates_failure({"success": False}) is True


def test_truthy_error_string_is_failure() -> None:
    assert result_indicates_failure({"installed_programs": [], "error": "PowerShell failed"}) is True


def test_empty_error_is_not_failure() -> None:
    assert result_indicates_failure({"error": ""}) is False
    assert result_indicates_failure({"error": None}) is False


def test_plain_success_dict_is_not_failure() -> None:
    assert result_indicates_failure({"summary": "готово", "status": "done"}) is False
    assert result_indicates_failure({"ok": True}) is False


def test_non_dict_is_not_failure() -> None:
    assert result_indicates_failure("just text") is False
    assert result_indicates_failure(None) is False
    assert result_indicates_failure(["a", "b"]) is False


def test_finish_task_payload_is_not_failure() -> None:
    from src.tools.core.confirmation_tools import finish_task

    payload = finish_task({"summary": "sub-agent done", "status": "done"})
    assert result_indicates_failure(payload) is False


def test_failed_delegation_payload_is_failure() -> None:
    """Проваленное делегирование (compact result из DelegateTools) должно
    распознаваться как ошибка на странице оператора."""
    from src.agent.lifecycle.agent_registry import AgentRegistry
    from src.tools.agent_ops.delegate_tools import DelegateTools

    dt = DelegateTools(AgentRegistry())
    compact = dt._normalize_result(
        {"run_id": "r1", "agent_name": "web", "success": False, "result": "достиг лимита шагов", "error": "достиг лимита шагов"}
    )
    assert result_indicates_failure(compact) is True
