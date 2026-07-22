from __future__ import annotations

import pytest

from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import Settings
from src.web.context import ServerContext
from src.web.routes import Routes


@pytest.fixture()
def ctx(tmp_path, monkeypatch):
    # settings.get_model("operator") читает data/models.json через
    # захардкоженный src.infra.config.MODELS_FILE, а не workspace_root —
    # без этого monkeypatch тест зависел бы от того, какая модель реально
    # выбрана оператору на диске (Ollama или Codex), и падал бы, например,
    # если пользователь через UI переключил оператора на codex:... модель.
    monkeypatch.setattr("src.infra.config.MODELS_FILE", tmp_path / "models.json")
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


class _StubOllamaClient:
    """Заглушка OllamaClient.chat() — не ходит в сеть, отдаёт заранее заданный ответ."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def chat(self, messages: list[dict]) -> str:
        return _StubOllamaClient.response


def _seed_history(ctx, count: int) -> None:
    history = [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"сообщение {i}"}
        for i in range(count)
    ]
    store = ChatMemoryStore(ctx.settings.memory_file)
    store.replace_chat_history(history)


def test_compress_memory_short_history_not_compressed(ctx) -> None:
    _seed_history(ctx, count=4)
    routes = Routes(ctx)

    result = routes.compress_memory()

    assert result == {"compressed": False, "reason": "История слишком короткая для сжатия"}


def test_compress_memory_refuses_while_runtime_active(ctx) -> None:
    _seed_history(ctx, count=20)
    ctx.set_runtime(object())
    routes = Routes(ctx)

    result = routes.compress_memory()

    assert result["compressed"] is False
    assert "занят" in result["error"]


def test_compress_memory_summarizes_older_and_keeps_recent(ctx, monkeypatch) -> None:
    """Регрессия: сжатие должно оставить последние KEEP_RECENT сообщений
    дословно (свежий контекст важен), а всё более старое заменить одной
    сводкой от LLM — не должно быть простой обрезки без вызова модели."""
    import src.llm.ollama_client as ollama_module

    _StubOllamaClient.response = "Ключевые факты: пользователь просил X, договорились о Y."
    monkeypatch.setattr(ollama_module, "OllamaClient", _StubOllamaClient)

    _seed_history(ctx, count=20)
    routes = Routes(ctx)

    result = routes.compress_memory()

    assert result["compressed"] is True
    assert result["before_count"] == 20
    assert result["after_count"] == 7  # 1 сжатая запись + 6 последних нетронутых

    store = ChatMemoryStore(ctx.settings.memory_file)
    new_history = store.load()["chat_history"]
    assert len(new_history) == 7
    assert "Ключевые факты" in new_history[0]["content"]
    # последние 6 исходных сообщений должны остаться дословно, без изменений
    assert new_history[1:] == [
        {"role": "user" if i % 2 == 0 else "assistant", "content": f"сообщение {i}"}
        for i in range(14, 20)
    ]


def test_compress_memory_handles_llm_failure_without_corrupting_history(ctx, monkeypatch) -> None:
    import src.llm.ollama_client as ollama_module

    class _FailingClient:
        def __init__(self, *args, **kwargs) -> None:
            pass

        def chat(self, messages: list[dict]) -> str:
            raise RuntimeError("llm недоступна")

    monkeypatch.setattr(ollama_module, "OllamaClient", _FailingClient)
    _seed_history(ctx, count=20)
    routes = Routes(ctx)

    result = routes.compress_memory()

    assert result["compressed"] is False
    assert "не удалось сжать" in result["error"].lower()

    store = ChatMemoryStore(ctx.settings.memory_file)
    # история не должна быть тронута/потеряна при ошибке
    assert len(store.load()["chat_history"]) == 20
