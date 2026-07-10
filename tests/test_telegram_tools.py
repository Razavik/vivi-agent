from __future__ import annotations

import json
from types import SimpleNamespace

from src.tools.telegram_tools import (
    TelegramTools,
    _message_media_type,
    _save_telegram_profile,
    load_telegram_profile,
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


class TestProfilePersistence:
    def test_load_returns_none_when_missing(self, tmp_path, monkeypatch) -> None:
        import src.tools.telegram_tools as tg

        monkeypatch.setattr(tg, "PROFILE_FILE", tmp_path / "nope.json")
        assert load_telegram_profile() is None

    def test_save_then_load_roundtrip(self, tmp_path, monkeypatch) -> None:
        import src.tools.telegram_tools as tg

        profile_file = tmp_path / "telegram_profile.json"
        monkeypatch.setattr(tg, "PROFILE_FILE", profile_file)

        profile = {"id": 42, "username": "myhandle", "first_name": "Иван", "last_name": "", "phone": "+70000000000"}
        _save_telegram_profile(profile)

        loaded = load_telegram_profile()
        assert loaded == profile
        assert json.loads(profile_file.read_text(encoding="utf-8")) == profile

    def test_load_returns_none_on_corrupt_json(self, tmp_path, monkeypatch) -> None:
        import src.tools.telegram_tools as tg

        profile_file = tmp_path / "telegram_profile.json"
        profile_file.write_text("{not valid json", encoding="utf-8")
        monkeypatch.setattr(tg, "PROFILE_FILE", profile_file)

        assert load_telegram_profile() is None


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

    def test_new_telegram_tools_reach_ui_catalog(self) -> None:
        from src.app_factory import describe_all_tools
        from src.infra.config import get_settings

        tools = describe_all_tools(get_settings())
        telegram_names = {t["name"] for t in tools if t["agent"] == "telegram"}
        assert "read_chat_image" in telegram_names
        assert "get_own_telegram_profile" in telegram_names


class TestBuildPromptVars:
    def test_non_telegram_agent_returns_empty(self) -> None:
        from src.app_factory import _build_prompt_vars

        assert _build_prompt_vars("file") == {}
        assert _build_prompt_vars("web") == {}

    def test_telegram_without_profile_has_fallback(self, tmp_path, monkeypatch) -> None:
        import src.app_factory as af
        import src.tools.telegram_tools as tg

        monkeypatch.setattr(tg, "PROFILE_FILE", tmp_path / "missing.json")
        result = af._build_prompt_vars("telegram")
        assert "tg_username" in result and "tg_display_name" in result
        assert "не синхронизирован" in result["tg_username"]

    def test_telegram_with_profile_fills_placeholders(self, tmp_path, monkeypatch) -> None:
        import src.app_factory as af
        import src.tools.telegram_tools as tg

        profile_file = tmp_path / "telegram_profile.json"
        monkeypatch.setattr(tg, "PROFILE_FILE", profile_file)
        _save_telegram_profile({"id": 1, "username": "myhandle", "first_name": "Иван", "last_name": "Иванов", "phone": None})

        result = af._build_prompt_vars("telegram")
        assert result["tg_username"] == "myhandle"
        assert result["tg_display_name"] == "Иван Иванов"

    def test_telegram_profile_without_username_falls_back(self, tmp_path, monkeypatch) -> None:
        import src.app_factory as af
        import src.tools.telegram_tools as tg

        profile_file = tmp_path / "telegram_profile.json"
        monkeypatch.setattr(tg, "PROFILE_FILE", profile_file)
        _save_telegram_profile({"id": 1, "username": None, "first_name": "", "last_name": "", "phone": None})

        result = af._build_prompt_vars("telegram")
        assert result["tg_username"] == "без username"
        assert result["tg_display_name"] == "не указано"
