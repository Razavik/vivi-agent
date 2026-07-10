from __future__ import annotations

import threading
import time

from src.agent.run_control import RunController
from src.agent.sub_agent import SubAgent, _DEFAULT_WAIT_SECONDS, _MAX_WAIT_SECONDS, _MIN_WAIT_SECONDS
from src.infra.chat_memory import ChatMemoryStore


class _NoopClient:
    model = "stub-model"


def _make_agent(tmp_path) -> SubAgent:
    prompt = tmp_path / "agent.txt"
    prompt.write_text("# Тестовый агент\nДелай задачу.", encoding="utf-8")
    return SubAgent(
        name="telegram",
        display_name="Telegram",
        prompt_path=str(prompt),
        tools=[],
        client=_NoopClient(),
        memory_store=ChatMemoryStore(tmp_path / "mem.json"),
    )


def test_wait_bounds_are_sane() -> None:
    assert _MIN_WAIT_SECONDS == 1.0
    assert _MAX_WAIT_SECONDS == 120.0
    assert _MIN_WAIT_SECONDS <= _DEFAULT_WAIT_SECONDS <= _MAX_WAIT_SECONDS


def test_wait_tool_is_registered_for_every_sub_agent(tmp_path) -> None:
    agent = _make_agent(tmp_path)
    registry = agent._build_registry(ask_operator=None, controller=None)
    tool = registry.get("wait")
    assert tool is not None
    assert tool.risk_level == 0


def test_wait_blocks_for_requested_duration(tmp_path) -> None:
    agent = _make_agent(tmp_path)
    tool = agent._build_registry(None, None).get("wait")

    t0 = time.monotonic()
    result = tool.handler({"seconds": 1.3})
    elapsed = time.monotonic() - t0

    assert elapsed >= 1.2
    assert result["interrupted"] is False
    assert result["waited_seconds"] == 1.3


def test_wait_clamps_to_max_seconds(tmp_path) -> None:
    """Не ждём реальный максимум (120с) — проверяем клэмп через отмену: если бы
    seconds=99999 не урезался до потолка, обнаружение отмены заняло бы дольше
    одного цикла опроса (проверяем, что оно быстрое, независимо от запрошенного)."""
    agent = _make_agent(tmp_path)
    controller = RunController(run_id="r1", cancel_event=threading.Event(), pause_event=threading.Event())
    tool = agent._build_registry(None, controller).get("wait")

    def cancel_soon() -> None:
        time.sleep(0.1)
        controller.cancel()

    threading.Thread(target=cancel_soon, daemon=True).start()
    t0 = time.monotonic()
    result = tool.handler({"seconds": 99999})
    elapsed = time.monotonic() - t0

    assert result["interrupted"] is True
    assert elapsed < 2.0, "отмена обнаружена не сразу — похоже, seconds не был урезан до потолка"


def test_wait_clamps_to_min_seconds(tmp_path) -> None:
    agent = _make_agent(tmp_path)
    tool = agent._build_registry(None, None).get("wait")

    t0 = time.monotonic()
    result = tool.handler({"seconds": 0})
    elapsed = time.monotonic() - t0

    assert result["waited_seconds"] == 1.0  # минимум 1 секунда, даже если попросили 0
    assert elapsed >= 0.9


def test_wait_interrupted_by_cancel(tmp_path) -> None:
    """Регрессия: wait не должен блокировать отмену сессии — саб-агент
    должен быстро прерваться, а не висеть до конца запрошенного ожидания."""
    agent = _make_agent(tmp_path)
    controller = RunController(run_id="r1", cancel_event=threading.Event(), pause_event=threading.Event())
    tool = agent._build_registry(None, controller).get("wait")

    def cancel_soon() -> None:
        time.sleep(0.2)
        controller.cancel()

    threading.Thread(target=cancel_soon, daemon=True).start()
    t0 = time.monotonic()
    result = tool.handler({"seconds": 30})
    elapsed = time.monotonic() - t0

    assert result["interrupted"] is True
    assert elapsed < 2.0, "wait не прервался вовремя после отмены — блокирует завершение сессии"


def test_wait_default_seconds_when_invalid_input(tmp_path) -> None:
    """Некорректный seconds → используется дефолт (20с). Проверяем через отмену,
    не дожидаясь реальных 20 секунд в тесте."""
    agent = _make_agent(tmp_path)
    controller = RunController(run_id="r1", cancel_event=threading.Event(), pause_event=threading.Event())
    tool = agent._build_registry(None, controller).get("wait")

    def cancel_soon() -> None:
        time.sleep(0.1)
        controller.cancel()

    threading.Thread(target=cancel_soon, daemon=True).start()
    t0 = time.monotonic()
    result = tool.handler({"seconds": "not-a-number"})
    elapsed = time.monotonic() - t0

    assert result["interrupted"] is True
    assert elapsed < 2.0
