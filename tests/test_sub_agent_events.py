from __future__ import annotations

from src.agent.schemas import ActionStep
from src.agent.sub_agent import SubAgent
from src.infra.chat_memory import ChatMemoryStore
from src.tools.registry import ToolSpec


class _StubClient:
    """Мини-заглушка OllamaClient: выдаёт заранее заданную последовательность шагов."""

    model = "stub-model"
    num_ctx = 4096

    def __init__(self, steps: list[ActionStep]) -> None:
        self._steps = steps
        self._i = 0

    def plan_next_step(self, messages, on_retry_error=None):  # noqa: ANN001
        step = self._steps[min(self._i, len(self._steps) - 1)]
        self._i += 1
        return step


def _make_sub_agent(tmp_path, client) -> SubAgent:
    prompt = tmp_path / "agent.txt"
    prompt.write_text("# Тестовый агент\nДелай задачу.", encoding="utf-8")
    failing = ToolSpec(
        "search_web",
        "поиск",
        0,
        lambda args: {"ok": False, "error": "нет соединения"},
        {"query": "str?"},
    )
    return SubAgent(
        name="web",
        display_name="Веб",
        prompt_path=str(prompt),
        tools=[failing],
        client=client,
        memory_store=ChatMemoryStore(tmp_path / "mem.json"),
        max_steps=5,
    )


def test_failing_tool_is_reported_as_error(tmp_path) -> None:
    client = _StubClient([
        ActionStep(action="search_web", args={"query": "x"}, done=False),
        ActionStep(action="finish_task", args={"summary": "готово"}, done=True),
    ])
    agent = _make_sub_agent(tmp_path, client)

    events: list[tuple[str, dict]] = []
    agent.run("найди инфо", run_id="r1", event_sink=lambda e, p: events.append((e, p)))

    tool_results = [p for e, p in events if e == "sub_agent_tool_result" and p.get("action") == "search_web"]
    assert tool_results, "ожидался sub_agent_tool_result для search_web"
    assert tool_results[0]["success"] is False, "проваленный инструмент должен иметь success=False"

    warnings = [p for e, p in events if e == "sub_agent_warning"]
    assert any("search_web" in str(p.get("message", "")) for p in warnings), "ожидалось предупреждение об ошибке инструмента"


def test_step_limit_emits_error_event(tmp_path) -> None:
    # Всегда вызывает инструмент, никогда не завершает → упирается в лимит шагов.
    client = _StubClient([ActionStep(action="search_web", args={"query": "x"}, done=False)])
    agent = _make_sub_agent(tmp_path, client)

    events: list[tuple[str, dict]] = []
    result = agent.run("зацикли", run_id="r2", event_sink=lambda e, p: events.append((e, p)))

    assert result["success"] is False
    error_events = [p for e, p in events if e == "sub_agent_error"]
    assert error_events, "при достижении лимита шагов должен эмититься sub_agent_error"
    assert "лимит" in str(error_events[-1].get("message", "")).lower()
