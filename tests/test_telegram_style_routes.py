from __future__ import annotations

import pytest

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


@pytest.fixture()
def style_file(tmp_path, monkeypatch):
    import src.tools.communication.telegram_tools as tg

    path = tmp_path / "telegram_style.json"
    monkeypatch.setattr(tg, "STYLE_FILE", path)
    return path


def test_get_telegram_style_none_when_not_learned(ctx, style_file) -> None:
    routes = Routes(ctx)
    assert routes.get_telegram_style() == {"style_guide": None}


def test_set_telegram_style_persists_and_is_readable(ctx, style_file) -> None:
    routes = Routes(ctx)

    result = routes.set_telegram_style({"style_guide": "Коротко, с юмором, на ты."})

    assert result == {"saved": True, "style_guide": "Коротко, с юмором, на ты."}
    assert routes.get_telegram_style() == {"style_guide": "Коротко, с юмором, на ты."}


def test_set_telegram_style_trims_whitespace(ctx, style_file) -> None:
    routes = Routes(ctx)
    routes.set_telegram_style({"style_guide": "  Пишет коротко.  "})
    assert routes.get_telegram_style() == {"style_guide": "Пишет коротко."}


def test_set_telegram_style_empty_clears_it(ctx, style_file) -> None:
    routes = Routes(ctx)
    routes.set_telegram_style({"style_guide": "Что-то было"})
    assert routes.get_telegram_style()["style_guide"] is not None

    result = routes.set_telegram_style({"style_guide": "   "})

    assert result == {"saved": True, "style_guide": None}
    assert routes.get_telegram_style() == {"style_guide": None}
    assert not style_file.exists()


def test_set_telegram_style_rejects_too_long(ctx, style_file) -> None:
    from http import HTTPStatus

    routes = Routes(ctx)
    result = routes.set_telegram_style({"style_guide": "x" * 2001})

    assert isinstance(result, tuple)
    payload, status = result
    assert status == HTTPStatus.BAD_REQUEST
    assert "error" in payload
    assert not style_file.exists()


def test_manual_edit_shares_file_with_agent_learned_style(ctx, style_file) -> None:
    """Ручное редактирование из UI и автообучение агента (save_my_style) должны
    писать в один и тот же файл — иначе правка из UI не попадёт в промпт
    (см. app_factory._build_prompt_vars -> load_telegram_style)."""
    from src.tools.communication.telegram_tools import TelegramTools, load_telegram_style

    routes = Routes(ctx)
    routes.set_telegram_style({"style_guide": "Ручная правка пользователя."})
    assert load_telegram_style() == "Ручная правка пользователя."

    tools = TelegramTools.__new__(TelegramTools)
    tools.save_my_style({"style_guide": "Стиль, выученный агентом."})
    assert routes.get_telegram_style() == {"style_guide": "Стиль, выученный агентом."}
