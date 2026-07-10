from __future__ import annotations

import pytest

from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import Settings
from src.web.context import ServerContext
from src.web.routes import Routes


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


class _FakeRuntime:
    """Минимальная заглушка AgentRuntime: нужен только атрибут _base_history,
    который реальный AgentRuntime.run() «замораживает» один раз в начале сессии
    и использует как префикс для каждой последующей записи снапшота."""

    def __init__(self, base_history: list[dict]) -> None:
        self._base_history = base_history


def test_clear_history_resets_active_runtime_base_history(ctx) -> None:
    """Регрессия: очистка истории выглядела рабочей "здесь и сейчас", но старые
    сообщения возвращались после перезагрузки. Причина — AgentRuntime.run()
    пишет снапшот как base_history + текущая сессия, где base_history
    захвачен один раз в начале run(). Если оператор всё ещё активен (или
    дописывает последний шаг в фоне) в момент очистки, следующая запись
    снапшота воскрешала бы только что стёртую историю. clear_history() должен
    сбрасывать _base_history активного runtime, чтобы этого не происходило."""
    stale_history = [{"role": "user", "content": "старое сообщение до очистки"}]
    runtime = _FakeRuntime(base_history=stale_history)
    ctx.set_runtime(runtime)

    routes = Routes(ctx)
    routes.clear_history()

    assert runtime._base_history == []


def test_clear_history_without_active_runtime_does_not_error(ctx) -> None:
    assert ctx.get_runtime() is None
    routes = Routes(ctx)
    result = routes.clear_history()
    assert result == {"cleared": True, "target": "history"}


def test_clear_history_persists_empty_memory(ctx) -> None:
    ctx.memory_store.write_snapshot(
        base_history=[],
        session_chat_history=[],
        session_observations=[],
    )
    # эмулируем непустую историю напрямую через store, как в реальном чате
    store = ChatMemoryStore(ctx.settings.memory_file)
    store._write_unlocked({"chat_history": [{"role": "user", "content": "hi"}], "updated_at": None})
    assert store.load()["chat_history"]

    routes = Routes(ctx)
    routes.clear_history()

    fresh_store = ChatMemoryStore(ctx.settings.memory_file)
    assert fresh_store.load()["chat_history"] == []
