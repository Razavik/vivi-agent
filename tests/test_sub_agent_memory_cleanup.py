from __future__ import annotations

import json

from src.agent.core.schemas import ActionStep
from src.agent.core.state import Observation
from src.agent.core.sub_agent import (
    SubAgent,
    _MEMORY_CLEAN_THRESHOLD,
)
from src.infra.chat_memory import ChatMemoryStore
from src.tools.core.registry import ToolSpec


class _StubClient:
    """Заглушка OllamaClient: выдаёт заранее заданную последовательность шагов
    (plan_next_step) и опционально отвечает на chat() (используется
    _clean_observations_for_memory для сжатия тяжёлых наблюдений)."""

    model = "stub-model"
    num_ctx = 4096

    def __init__(self, steps: list[ActionStep], chat_response: str | None = None, chat_raises: bool = False) -> None:
        self._steps = steps
        self._i = 0
        self.chat_response = chat_response
        self.chat_raises = chat_raises
        self.chat_calls: list[list[dict]] = []

    def plan_next_step(self, messages, on_retry_error=None):  # noqa: ANN001
        step = self._steps[min(self._i, len(self._steps) - 1)]
        self._i += 1
        return step

    def chat(self, messages: list[dict]) -> str:
        self.chat_calls.append(messages)
        if self.chat_raises:
            raise RuntimeError("llm недоступна")
        if self.chat_response is not None:
            return self.chat_response
        raise AssertionError("chat_response не задан для этого теста")


def _make_agent(tmp_path, client, tools: list[ToolSpec]) -> SubAgent:
    prompt = tmp_path / "agent.txt"
    prompt.write_text("# Тестовый агент\nДелай задачу.", encoding="utf-8")
    return SubAgent(
        name="web",
        display_name="Web",
        prompt_path=str(prompt),
        tools=tools,
        client=client,
        memory_store=ChatMemoryStore(tmp_path / "mem.json"),
        max_steps=5,
    )


def test_light_observation_not_sent_to_llm_for_cleanup(tmp_path) -> None:
    """Маленькие результаты не должны стоить лишнего LLM-вызова — очистка
    включается только выше порога."""
    small_tool = ToolSpec("noop", "ничего не делает", 0, lambda args: {"ok": True, "text": "коротко"}, {})
    client = _StubClient([
        ActionStep(action="noop", args={}, done=False),
        ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
    ])
    agent = _make_agent(tmp_path, client, [small_tool])

    agent.run("задача", run_id="r1")

    assert client.chat_calls == []


def test_heavy_observation_summarized_via_llm_before_persisting(tmp_path) -> None:
    """Регрессия для "проработать веб-агента, чтобы память не засорялась":
    тяжёлый результат инструмента (например fetch_url) должен уйти в память в
    виде LLM-резюме, а не сырым текстом на десятки КБ."""
    heavy_text = "содержимое страницы " * 100  # заведомо больше порога
    assert len(heavy_text) > _MEMORY_CLEAN_THRESHOLD
    fetch_tool = ToolSpec("fetch_url", "скачать страницу", 0, lambda args: {"content": heavy_text}, {})
    summary_text = "Страница содержала повторяющийся текст, ключевых фактов нет."
    chat_response = json.dumps({"summaries": [{"index": 0, "summary": summary_text}]})
    client = _StubClient(
        [
            ActionStep(action="fetch_url", args={"url": "http://x"}, done=False),
            ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
        ],
        chat_response=chat_response,
    )
    agent = _make_agent(tmp_path, client, [fetch_tool])

    agent.run("прочитай страницу", run_id="r1")

    assert len(client.chat_calls) == 1
    mem = agent.memory_store.load()
    serialized = json.dumps(mem, ensure_ascii=False)
    assert heavy_text not in serialized
    assert summary_text in serialized


def test_heavy_observation_falls_back_to_truncation_when_llm_fails(tmp_path) -> None:
    """Если LLM-очистка недоступна/падает, сохраняем не сырой текст целиком, а
    безопасный обрезанный фолбэк — сохранение памяти не должно падать."""
    heavy_text = "X" * 5000
    fetch_tool = ToolSpec("fetch_url", "скачать страницу", 0, lambda args: {"content": heavy_text}, {})
    client = _StubClient(
        [
            ActionStep(action="fetch_url", args={"url": "http://x"}, done=False),
            ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
        ],
        chat_raises=True,
    )
    agent = _make_agent(tmp_path, client, [fetch_tool])

    result = agent.run("прочитай страницу", run_id="r1")

    assert result["success"] is True
    mem = agent.memory_store.load()
    serialized = json.dumps(mem, ensure_ascii=False)
    assert heavy_text not in serialized
    assert "не удалось сжать" in serialized


def test_live_reasoning_still_sees_full_heavy_content(tmp_path) -> None:
    """Важный инвариант: очистка касается только того, что уходит на диск.
    В рамках текущего запуска LLM должна по-прежнему видеть полный результат
    инструмента на следующем шаге (иначе саб-агент не сможет резюмировать
    страницу, которую сам же и попросили прочитать)."""
    heavy_text = "важный факт номер 42 " * 60
    fetch_tool = ToolSpec("fetch_url", "скачать страницу", 0, lambda args: {"content": heavy_text}, {})

    seen_user_messages: list[str] = []

    class _CapturingClient(_StubClient):
        def plan_next_step(self, messages, on_retry_error=None):  # noqa: ANN001
            user_msg = next(m for m in messages if m["role"] == "user")
            seen_user_messages.append(user_msg["content"])
            return super().plan_next_step(messages, on_retry_error)

    client = _CapturingClient(
        [
            ActionStep(action="fetch_url", args={"url": "http://x"}, done=False),
            ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
        ],
        chat_response=json.dumps({"summaries": [{"index": 0, "summary": "резюме"}]}),
    )
    agent = _make_agent(tmp_path, client, [fetch_tool])

    agent.run("прочитай страницу", run_id="r1")

    # Второй вызов plan_next_step (после fetch_url) должен получить полный текст
    # в recent_observations, а не резюме, сформированное для памяти.
    assert "важный факт номер 42" in seen_user_messages[1]


def test_clean_observations_for_memory_is_a_pure_helper(tmp_path) -> None:
    """Юнит-уровень: _clean_observations_for_memory не трогает лёгкие
    наблюдения и оставляет step/action/success/thought как есть у тяжёлых."""
    client = _StubClient(
        [ActionStep(action="finish_task", args={"summary": "ok"}, done=True)],
        chat_response=json.dumps({"summaries": [{"index": 1, "summary": "сжато"}]}),
    )
    agent = _make_agent(tmp_path, client, [])

    light = Observation(step=1, action="noop", result={"ok": True}, success=True, thought="думал")
    heavy = Observation(step=2, action="fetch_url", result={"content": "Y" * 2000}, success=True, thought=None)

    cleaned = agent._clean_observations_for_memory([light, heavy])

    assert cleaned[0] is light
    assert cleaned[1].step == 2
    assert cleaned[1].action == "fetch_url"
    assert cleaned[1].success is True
    assert cleaned[1].result == {"summary": "сжато", "cleaned_for_memory": True}
