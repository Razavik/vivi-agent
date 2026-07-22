from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from src.infra.errors import ToolExecutionError
from src.tools.communication.telegram_tools import (
    TelegramTools,
    _format_user_status,
    _message_media_type,
    _save_telegram_profile,
    _save_telegram_style,
    load_telegram_profile,
    load_telegram_style,
)


def _msg(**overrides) -> SimpleNamespace:
    base = {"photo": None, "document": None, "video": None, "voice": None, "audio": None}
    base.update(overrides)
    return SimpleNamespace(**base)


class TestMessageMediaType:
    def test_photo(self) -> None:
        assert _message_media_type(_msg(photo=object())) == "photo"

    def test_image_document(self) -> None:
        doc = SimpleNamespace(mime_type="image/png")
        assert _message_media_type(_msg(document=doc)) == "photo"

    def test_video_document(self) -> None:
        doc = SimpleNamespace(mime_type="video/mp4")
        assert _message_media_type(_msg(document=doc)) == "video"

    def test_audio_document(self) -> None:
        doc = SimpleNamespace(mime_type="audio/mpeg")
        assert _message_media_type(_msg(document=doc)) == "audio"

    def test_generic_document(self) -> None:
        doc = SimpleNamespace(mime_type="application/pdf")
        assert _message_media_type(_msg(document=doc)) == "document"

    def test_video_field(self) -> None:
        assert _message_media_type(_msg(video=object())) == "video"

    def test_voice_field(self) -> None:
        assert _message_media_type(_msg(voice=object())) == "audio"

    def test_no_media(self) -> None:
        assert _message_media_type(_msg()) is None


class TestResolvePeerArg:
    def test_numeric_string_becomes_int(self) -> None:
        assert TelegramTools._resolve_peer_arg("123456") == 123456

    def test_username_with_at_prefix_stripped(self) -> None:
        assert TelegramTools._resolve_peer_arg("@myhandle") == "myhandle"

    def test_username_without_prefix_unchanged(self) -> None:
        assert TelegramTools._resolve_peer_arg("myhandle") == "myhandle"


class TestFormatUserStatus:
    def test_none_is_unknown(self) -> None:
        assert _format_user_status(None) == {"status": "unknown", "last_seen": None}

    def test_online(self) -> None:
        from datetime import datetime, timezone
        from telethon.tl.types import UserStatusOnline

        expires = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _format_user_status(UserStatusOnline(expires=expires))
        assert result["status"] == "online"
        assert result["last_seen"] == expires.isoformat()

    def test_offline_with_was_online(self) -> None:
        from datetime import datetime, timezone
        from telethon.tl.types import UserStatusOffline

        was_online = datetime(2026, 1, 1, tzinfo=timezone.utc)
        result = _format_user_status(UserStatusOffline(was_online=was_online))
        assert result["status"] == "offline"
        assert result["last_seen"] == was_online.isoformat()

    def test_recently(self) -> None:
        from telethon.tl.types import UserStatusRecently

        assert _format_user_status(UserStatusRecently()) == {"status": "recently", "last_seen": None}

    def test_last_week(self) -> None:
        from telethon.tl.types import UserStatusLastWeek

        assert _format_user_status(UserStatusLastWeek()) == {"status": "last_week", "last_seen": None}

    def test_last_month(self) -> None:
        from telethon.tl.types import UserStatusLastMonth

        assert _format_user_status(UserStatusLastMonth()) == {"status": "last_month", "last_seen": None}

    def test_empty_status(self) -> None:
        from telethon.tl.types import UserStatusEmpty

        assert _format_user_status(UserStatusEmpty()) == {"status": "unknown", "last_seen": None}


class TestProfilePersistence:
    def test_load_returns_none_when_missing(self, tmp_path, monkeypatch) -> None:
        import src.tools.communication.telegram_tools as tg

        monkeypatch.setattr(tg, "PROFILE_FILE", tmp_path / "nope.json")
        assert load_telegram_profile() is None

    def test_save_then_load_roundtrip(self, tmp_path, monkeypatch) -> None:
        import src.tools.communication.telegram_tools as tg

        profile_file = tmp_path / "telegram_profile.json"
        monkeypatch.setattr(tg, "PROFILE_FILE", profile_file)

        profile = {"id": 42, "username": "myhandle", "first_name": "Иван", "last_name": "", "phone": "+70000000000"}
        _save_telegram_profile(profile)

        loaded = load_telegram_profile()
        assert loaded == profile
        assert json.loads(profile_file.read_text(encoding="utf-8")) == profile

    def test_load_returns_none_on_corrupt_json(self, tmp_path, monkeypatch) -> None:
        import src.tools.communication.telegram_tools as tg

        profile_file = tmp_path / "telegram_profile.json"
        profile_file.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(tg, "PROFILE_FILE", profile_file)

        assert load_telegram_profile() is None


class TestStylePersistence:
    def test_load_returns_none_when_missing(self, tmp_path, monkeypatch) -> None:
        import src.tools.communication.telegram_tools as tg

        monkeypatch.setattr(tg, "STYLE_FILE", tmp_path / "nope.json")
        assert load_telegram_style() is None

    def test_save_then_load_roundtrip(self, tmp_path, monkeypatch) -> None:
        import src.tools.communication.telegram_tools as tg

        style_file = tmp_path / "telegram_style.json"
        monkeypatch.setattr(tg, "STYLE_FILE", style_file)

        _save_telegram_style("Пишет коротко, без эмодзи, на ты.")
        assert load_telegram_style() == "Пишет коротко, без эмодзи, на ты."

    def test_load_returns_none_on_blank_style(self, tmp_path, monkeypatch) -> None:
        import src.tools.communication.telegram_tools as tg

        style_file = tmp_path / "telegram_style.json"
        style_file.write_text(json.dumps({"style_guide": "   "}), encoding="utf-8")
        monkeypatch.setattr(tg, "STYLE_FILE", style_file)

        assert load_telegram_style() is None

    def test_save_my_style_rejects_empty(self) -> None:
        tools = TelegramTools.__new__(TelegramTools)
        with pytest.raises(ToolExecutionError):
            tools.save_my_style({"style_guide": "   "})

    def test_save_my_style_rejects_too_long(self) -> None:
        tools = TelegramTools.__new__(TelegramTools)
        with pytest.raises(ToolExecutionError):
            tools.save_my_style({"style_guide": "x" * 2001})

    def test_save_my_style_persists(self, tmp_path, monkeypatch) -> None:
        import src.tools.communication.telegram_tools as tg

        monkeypatch.setattr(tg, "STYLE_FILE", tmp_path / "telegram_style.json")
        tools = TelegramTools.__new__(TelegramTools)
        result = tools.save_my_style({"style_guide": "Коротко и по делу."})
        assert result["success"] is True
        assert load_telegram_style() == "Коротко и по делу."


class TestCollectMyMessagesSkipsSavedMessages:
    """Регрессия: чат "Избранное" (Saved Messages) — это диалог с самим собой
    (entity.id == me.id), в нём лежат заметки/пересылки, а не переписка с другим
    человеком, поэтому его нужно исключать из выборки для анализа стиля."""

    def _make_tools_with_fake_client(self, dialogs, get_messages_by_entity_id) -> TelegramTools:
        import asyncio

        class FakeClient:
            def is_connected(self) -> bool:
                return True

            async def connect(self) -> None:
                return None

            async def is_user_authorized(self) -> bool:
                return True

            async def get_me(self) -> SimpleNamespace:
                return SimpleNamespace(id=999)

            async def get_dialogs(self, limit: int | None = None):
                return dialogs

            async def get_messages(self, entity, limit=None, from_user=None):
                return get_messages_by_entity_id.get(getattr(entity, "id", None), [])

            async def disconnect(self) -> None:
                return None

        tools = TelegramTools.__new__(TelegramTools)
        fake_client = FakeClient()
        tools._create_loop = lambda: asyncio.new_event_loop()  # type: ignore[method-assign]
        tools._create_client = lambda loop: fake_client  # type: ignore[method-assign]
        return tools

    def test_saved_messages_dialog_excluded(self) -> None:
        me_entity = SimpleNamespace(id=999, first_name="Я", last_name="")
        alice_entity = SimpleNamespace(id=111, title="Alice")
        dialogs = [SimpleNamespace(entity=me_entity), SimpleNamespace(entity=alice_entity)]
        get_messages_by_entity_id = {
            999: [SimpleNamespace(text="Заметка себе")],
            111: [SimpleNamespace(text="Привет, как дела?")],
        }

        tools = self._make_tools_with_fake_client(dialogs, get_messages_by_entity_id)
        result = tools.collect_my_messages({})

        chats = {m["chat"] for m in result["messages"]}
        texts = {m["text"] for m in result["messages"]}
        assert "Заметка себе" not in texts
        assert "Привет, как дела?" in texts
        assert "Я" not in chats


class TestCollectMyMessagesDefaults:
    def test_default_pulls_up_to_500_messages_from_up_to_30_chats(self) -> None:
        import asyncio

        me_id = 999
        # 40 разных личных чатов, в каждом по 20 своих сообщений — с запасом
        # больше дефолтных лимитов (30 чатов / 500 сообщений), чтобы проверить,
        # что дефолт реально их применяет, а не выгребает всё подряд.
        dialogs = [SimpleNamespace(entity=SimpleNamespace(id=i, title=f"Chat {i}")) for i in range(40)]
        get_dialogs_calls: list[int | None] = []

        class FakeClient:
            def is_connected(self) -> bool:
                return True

            async def connect(self) -> None:
                return None

            async def is_user_authorized(self) -> bool:
                return True

            async def get_me(self) -> SimpleNamespace:
                return SimpleNamespace(id=me_id)

            async def get_dialogs(self, limit: int | None = None):
                get_dialogs_calls.append(limit)
                return dialogs

            async def get_messages(self, entity, limit=None, from_user=None):
                return [SimpleNamespace(text=f"msg {j}") for j in range(20)]

            async def disconnect(self) -> None:
                return None

        tools = TelegramTools.__new__(TelegramTools)
        fake_client = FakeClient()
        tools._create_loop = lambda: asyncio.new_event_loop()  # type: ignore[method-assign]
        tools._create_client = lambda loop: fake_client  # type: ignore[method-assign]

        result = tools.collect_my_messages({})

        assert result["total"] <= 500
        assert len({m["chat"] for m in result["messages"]}) <= 30
        # get_dialogs запрошен с лимитом, производным от max_chats=30 по умолчанию
        assert get_dialogs_calls == [90]

    def test_max_messages_upper_bound_is_1000(self) -> None:
        tools = TelegramTools.__new__(TelegramTools)
        with pytest.raises(ToolExecutionError):
            tools.collect_my_messages({"max_messages": 1001})

    def test_max_messages_1000_passes_validation(self) -> None:
        import asyncio

        class FakeClient:
            def is_connected(self) -> bool:
                return True

            async def connect(self) -> None:
                return None

            async def is_user_authorized(self) -> bool:
                return True

            async def get_me(self) -> SimpleNamespace:
                return SimpleNamespace(id=999)

            async def get_dialogs(self, limit: int | None = None):
                return []

            async def get_messages(self, entity, limit=None, from_user=None):
                return []

            async def disconnect(self) -> None:
                return None

        tools = TelegramTools.__new__(TelegramTools)
        fake_client = FakeClient()
        tools._create_loop = lambda: asyncio.new_event_loop()  # type: ignore[method-assign]
        tools._create_client = lambda loop: fake_client  # type: ignore[method-assign]
        result = tools.collect_my_messages({"max_messages": 1000})
        assert result["success"] is True


class TestTelegramWaitMessagePoll:
    """Хук для досрочного выхода из wait() (см. SubAgent.wait_message_poll),
    который app_factory собирает поверх зарегистрированного get_messages."""

    def test_returns_none_without_get_messages_spec(self) -> None:
        from src.app_factory import _make_telegram_wait_message_poll

        assert _make_telegram_wait_message_poll({}) is None

    def test_filters_to_messages_newer_than_since_id(self) -> None:
        from src.app_factory import _make_telegram_wait_message_poll
        from src.tools.core.registry import ToolSpec

        captured_args: list[dict] = []

        def fake_get_messages(args: dict) -> dict:
            captured_args.append(args)
            return {
                "messages": [
                    {"id": 5, "text": "старое"},
                    {"id": 11, "text": "новое"},
                    {"id": 12, "text": "ещё новее"},
                ]
            }

        specs = {"get_messages": ToolSpec("get_messages", "desc", 0, fake_get_messages, {})}
        poll = _make_telegram_wait_message_poll(specs)
        assert poll is not None

        result = poll("123", 10, "alice")

        assert captured_args == [{"chat_id": "123", "limit": 10, "from_user": "alice"}]
        assert {m["id"] for m in result} == {11, 12}

    def test_returns_empty_without_since_id(self) -> None:
        from src.app_factory import _make_telegram_wait_message_poll
        from src.tools.core.registry import ToolSpec

        def fake_get_messages(args: dict) -> dict:
            raise AssertionError("не должен вызываться без since_id")

        specs = {"get_messages": ToolSpec("get_messages", "desc", 0, fake_get_messages, {})}
        poll = _make_telegram_wait_message_poll(specs)
        assert poll is not None

        assert poll("123", None, None) == []

    def test_swallows_handler_errors(self) -> None:
        from src.app_factory import _make_telegram_wait_message_poll
        from src.tools.core.registry import ToolSpec

        def fake_get_messages(args: dict) -> dict:
            raise RuntimeError("boom")

        specs = {"get_messages": ToolSpec("get_messages", "desc", 0, fake_get_messages, {})}
        poll = _make_telegram_wait_message_poll(specs)
        assert poll is not None

        assert poll("123", 10, None) == []


class TestTelegramToolsEnabledInAgentsConfig:
    """Регрессия: инструмент, зарегистрированный в каталоге app_factory, не
    появляется у реального саб-агента, если его нет в списке tools конкретного
    агента в data/agents.json — это отдельный, легко забываемый шаг."""

    def test_new_telegram_tools_are_enabled(self) -> None:
        from src.infra.config import _load_agents_config

        cfg = _load_agents_config()
        telegram_tools = {
            entry.get("name") if isinstance(entry, dict) else entry
            for entry in cfg.get("telegram", {}).get("tools", [])
        }
        assert "read_chat_image" in telegram_tools
        assert "get_own_telegram_profile" in telegram_tools
        assert "get_messages" in telegram_tools
        assert "get_user_status" in telegram_tools
        assert "collect_my_messages" in telegram_tools
        assert "save_my_style" in telegram_tools

    def test_new_telegram_tools_reach_ui_catalog(self, monkeypatch) -> None:
        # В pc_control_mode сабагентов (в т.ч. telegram) вообще нет — тест
        # проверяет каталог именно режима оркестратора, форсируем его явно,
        # а не полагаемся на реальный data/app_settings.json.
        import src.app_factory as af

        monkeypatch.setattr(af, "is_pc_control_mode", lambda: False)
        from src.app_factory import describe_all_tools
        from src.infra.config import get_settings

        tools = describe_all_tools(get_settings())
        telegram_names = {t["name"] for t in tools if t["agent"] == "telegram"}
        assert "read_chat_image" in telegram_names
        assert "get_own_telegram_profile" in telegram_names
        assert "get_user_status" in telegram_names
        assert "collect_my_messages" in telegram_names
        assert "save_my_style" in telegram_names


class TestBuildPromptVars:
    def test_non_telegram_agent_returns_empty(self) -> None:
        from src.app_factory import _build_prompt_vars

        assert _build_prompt_vars("file") == {}
        assert _build_prompt_vars("web") == {}

    def test_telegram_without_profile_has_fallback(self, tmp_path, monkeypatch) -> None:
        import src.app_factory as af
        import src.tools.communication.telegram_tools as tg

        monkeypatch.setattr(tg, "PROFILE_FILE", tmp_path / "missing.json")
        result = af._build_prompt_vars("telegram")
        assert "tg_username" in result and "tg_display_name" in result
        assert "не синхронизирован" in result["tg_username"]

    def test_telegram_with_profile_fills_placeholders(self, tmp_path, monkeypatch) -> None:
        import src.app_factory as af
        import src.tools.communication.telegram_tools as tg

        profile_file = tmp_path / "telegram_profile.json"
        monkeypatch.setattr(tg, "PROFILE_FILE", profile_file)
        _save_telegram_profile({"id": 1, "username": "myhandle", "first_name": "Иван", "last_name": "Иванов", "phone": None})

        result = af._build_prompt_vars("telegram")
        assert result["tg_username"] == "myhandle"
        assert result["tg_display_name"] == "Иван Иванов"

    def test_telegram_profile_without_username_falls_back(self, tmp_path, monkeypatch) -> None:
        import src.app_factory as af
        import src.tools.communication.telegram_tools as tg

        profile_file = tmp_path / "telegram_profile.json"
        monkeypatch.setattr(tg, "PROFILE_FILE", profile_file)
        _save_telegram_profile({"id": 1, "username": None, "first_name": "", "last_name": "", "phone": None})

        result = af._build_prompt_vars("telegram")
        assert result["tg_username"] == "без username"
        assert result["tg_display_name"] == "не указано"

    def test_telegram_style_fallback_when_not_learned(self, tmp_path, monkeypatch) -> None:
        import src.app_factory as af
        import src.tools.communication.telegram_tools as tg

        monkeypatch.setattr(tg, "STYLE_FILE", tmp_path / "missing_style.json")
        result = af._build_prompt_vars("telegram")
        assert "не определён" in result["tg_style_guide"]

    def test_telegram_style_fills_placeholder_when_learned(self, tmp_path, monkeypatch) -> None:
        import src.app_factory as af
        import src.tools.communication.telegram_tools as tg

        monkeypatch.setattr(tg, "STYLE_FILE", tmp_path / "telegram_style.json")
        _save_telegram_style("Пишет коротко, с юмором, часто на ты.")

        result = af._build_prompt_vars("telegram")
        assert result["tg_style_guide"] == "Пишет коротко, с юмором, часто на ты."
