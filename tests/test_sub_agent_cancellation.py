from __future__ import annotations

import threading
import time

from src.agent.core.schemas import ActionStep
from src.agent.core.sub_agent import SubAgent
from src.agent.lifecycle.run_control import RunController
from src.infra.chat_memory import ChatMemoryStore
from src.infra.errors import AgentError


class _HangingStubClient:
    """Имитирует OllamaClient, чей LLM-вызов зависает, пока не будет отменён —
    как реальный запрос без timeout к зависшей Ollama."""

    model = "stub-model"
    num_ctx = 4096

    def __init__(self) -> None:
        self._cancel_event = threading.Event()
        self.cancel_called = False

    def cancel_active_request(self) -> None:
        # Ровно то, что делает реальный OllamaClient.cancel_active_request():
        # прерывает текущий блокирующий сетевой вызов.
        self.cancel_called = True
        self._cancel_event.set()

    def plan_next_step(self, messages, on_retry_error=None):  # noqa: ANN001
        # Блокируется "в сети" до отмены — без внешнего вмешательства висел бы вечно.
        cancelled = self._cancel_event.wait(timeout=10)
        if cancelled:
            raise AgentError("Запрос к Ollama отменён")
        raise AssertionError("cancel_active_request не был вызван за отведённое время")


def _make_sub_agent(tmp_path, client) -> SubAgent:
    prompt = tmp_path / "agent.txt"
    prompt.write_text("# Тестовый агент\nДелай задачу.", encoding="utf-8")
    return SubAgent(
        name="web",
        display_name="Веб",
        prompt_path=str(prompt),
        tools=[],
        client=client,
        memory_store=ChatMemoryStore(tmp_path / "mem.json"),
        max_steps=50,
    )


def test_controller_cancel_interrupts_blocked_llm_call(tmp_path) -> None:
    """Регрессия: без register_cancel_callback отмена никогда не доходила до
    заблокированного внутри delegate_task саб-агента, и сессия не завершалась."""
    client = _HangingStubClient()
    agent = _make_sub_agent(tmp_path, client)
    controller = RunController(run_id="r1", cancel_event=threading.Event(), pause_event=threading.Event())

    result_holder: dict = {}

    def run_agent() -> None:
        result_holder["result"] = agent.run("зависшая задача", run_id="r1", controller=controller)

    thread = threading.Thread(target=run_agent, daemon=True)
    thread.start()
    time.sleep(0.2)  # даём агенту зайти в блокирующий LLM-вызов

    controller.cancel()
    thread.join(timeout=5)

    assert not thread.is_alive(), "саб-агент не завершился после отмены — сессия зависает"
    assert client.cancel_called is True
    result = result_holder["result"]
    assert result["success"] is False
    assert result.get("cancelled") is True
