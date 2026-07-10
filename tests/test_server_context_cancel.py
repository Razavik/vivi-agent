from __future__ import annotations

from threading import Event

import pytest

from src.agent.run_control import RunController
from src.infra.config import Settings
from src.web.context import ServerContext


@pytest.fixture()
def ctx(tmp_path):
    settings = Settings(
        workspace_root=tmp_path,
        log_dir=tmp_path / "logs",
        memory_file=tmp_path / "data" / "chat-memory.json",
        sub_agent_memory_dir=tmp_path / "data" / "agents",
    )
    context = ServerContext(settings)
    try:
        yield context
    finally:
        context.supervisor.stop()
        context._supervisor_trigger.stop()


def test_cancel_runtime_cascades_to_active_run_controllers(ctx) -> None:
    """Регрессия: раньше cancel_runtime() отменял только клиент оператора, а
    активные run саб-агентов (запущенные через delegate_task) не получали cancel
    вообще — сессия не могла завершиться, пока оператор ждал их синхронно."""
    calls: list[str] = []
    controller1 = RunController(run_id="r1", cancel_event=Event(), pause_event=Event())
    controller1.register_cancel_callback(lambda: calls.append("r1"))
    controller2 = RunController(run_id="r2", cancel_event=Event(), pause_event=Event())
    controller2.register_cancel_callback(lambda: calls.append("r2"))

    ctx._run_controllers["r1"] = controller1
    ctx._run_controllers["r2"] = controller2

    cancelled = ctx.cancel_runtime()

    assert cancelled is True
    assert controller1.is_cancelled() is True
    assert controller2.is_cancelled() is True
    assert sorted(calls) == ["r1", "r2"]


def test_cancel_runtime_without_runtime_still_cancels_runs(ctx) -> None:
    """Даже если runtime уже завершился (self._current_runtime is None), активные
    run саб-агентов всё равно должны получить cancel."""
    controller = RunController(run_id="r1", cancel_event=Event(), pause_event=Event())
    ctx._run_controllers["r1"] = controller
    assert ctx.get_runtime() is None

    cancelled = ctx.cancel_runtime()

    assert cancelled is True
    assert controller.is_cancelled() is True


def test_cancel_runtime_false_when_nothing_active(ctx) -> None:
    assert ctx.cancel_runtime() is False
