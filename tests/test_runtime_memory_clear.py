from __future__ import annotations

import json

from src.agent.core.runtime import AgentRuntime
from src.agent.core.schemas import ActionStep
from src.agent.core.state import ChatMessage
from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import Settings
from src.infra.logging import SessionLogger
from src.safety.policy import SafetyPolicy
from src.safety.validator import ActionValidator
from src.tools.core.confirmation_tools import finish_task
from src.tools.core.registry import ToolRegistry, ToolSpec


class _ClearingStubClient:
    """Клиент-заглушка: на первом же шаге симулирует "очистить память",
    случившуюся ПОКА оператор ещё выполняет текущий запуск (см. routes.py
    Routes.clear_history — оно делает runtime._base_history = [])."""

    model = "stub-model"
    num_ctx = 4096

    def __init__(self, runtime_ref: list[AgentRuntime]) -> None:
        self._runtime_ref = runtime_ref
        self._called = False

    def reset_cancel_request(self) -> None:
        pass

    def plan_next_step(self, messages, on_stream_content=None, on_thinking=None, on_retry_error=None, max_retries=3):  # noqa: ANN001
        if not self._called:
            self._called = True
            # То же самое, что делает Routes.clear_history при активном runtime.
            self._runtime_ref[0].clear_persisted_history()
        return ActionStep(
            action="finish_task",
            args={"summary": "новый ответ"},
            thought="",
            done=True,
        )


def test_clear_during_active_run_is_not_resurrected(tmp_path) -> None:
    """Регрессия: routes.py.clear_history сбрасывал runtime._base_history,
    но run() писал снимки через локальную переменную base_history,
    захваченную один раз в начале — сброс никогда не долетал до уже
    идущего запуска, и следующий снимок молча возвращал старую историю
    обратно в chat-memory.json, будто очистка не сработала."""
    memory_file = tmp_path / "chat-memory.json"
    memory_store = ChatMemoryStore(memory_file)
    memory_store.write_snapshot(
        [],
        [ChatMessage(role="user", content="старое сообщение до очистки")],
        [],
        "old-model",
    )
    assert "старое сообщение до очистки" in memory_file.read_text(encoding="utf-8")

    registry = ToolRegistry()
    registry.register(
        ToolSpec(
            "finish_task",
            "Завершить задачу",
            0,
            finish_task,
            {"summary": "str?", "status": "str?", "changed_files": "list?", "verification": "list?", "risks": "list?", "attach_images": "bool?"},
        )
    )
    validator = ActionValidator(registry)
    policy = SafetyPolicy()
    logger = SessionLogger(tmp_path / "logs")

    runtime_ref: list[AgentRuntime] = []
    client = _ClearingStubClient(runtime_ref)
    runtime = AgentRuntime(
        client=client,
        registry=registry,
        validator=validator,
        policy=policy,
        logger=logger,
        memory_store=memory_store,
        confirm=lambda _msg: False,
        max_steps=5,
        max_consecutive_errors=2,
        workspace_root=str(tmp_path),
        settings=Settings(workspace_root=tmp_path, log_dir=tmp_path / "logs"),
    )
    runtime_ref.append(runtime)

    runtime.run("новая задача после очистки")

    data = json.loads(memory_file.read_text(encoding="utf-8"))
    contents = [item.get("content", "") for item in data.get("chat_history", [])]
    assert not any("старое сообщение до очистки" in c for c in contents), (
        f"Очищенная до запуска история вернулась обратно: {contents}"
    )
    assert any("новая задача после очистки" in c for c in contents)
