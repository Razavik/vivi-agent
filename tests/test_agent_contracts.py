from __future__ import annotations

import tempfile
import unittest
import sys
import types
from pathlib import Path

if "requests" not in sys.modules:
    fake_requests = types.ModuleType("requests")
    fake_requests.post = lambda *args, **kwargs: None
    sys.modules["requests"] = fake_requests
if "tiktoken" not in sys.modules:
    fake_tiktoken = types.ModuleType("tiktoken")

    class _Encoding:
        def encode(self, text: str) -> list[int]:
            return list(text.encode("utf-8"))

    fake_tiktoken.encoding_for_model = lambda _model: _Encoding()
    fake_tiktoken.get_encoding = lambda _name: _Encoding()
    sys.modules["tiktoken"] = fake_tiktoken
if "telethon" not in sys.modules:
    fake_telethon = types.ModuleType("telethon")
    fake_telethon_errors = types.ModuleType("telethon.errors")

    class _TelegramClient:
        def __init__(self, *args, **kwargs):
            pass

    class _SessionPasswordNeededError(Exception):
        pass

    class _PhoneNumberInvalidError(Exception):
        pass

    fake_telethon.TelegramClient = _TelegramClient
    fake_telethon_errors.SessionPasswordNeededError = _SessionPasswordNeededError
    fake_telethon_errors.PhoneNumberInvalidError = _PhoneNumberInvalidError
    sys.modules["telethon"] = fake_telethon
    sys.modules["telethon.errors"] = fake_telethon_errors

from src.agent.events import normalize_event
from src.agent.schemas import SubAgentResult
from src.app_factory import build_director_registry, describe_all_tools
from src.infra.config import DIRECTOR_REQUIRED_TOOLS, Settings
from src.infra.diagnostics import DiagnosticsService
from src.infra.settings_service import SettingsService
from src.safety.path_guard import PathGuard
from src.tools.file_tools import FileTools


class _DummyDelegateTools:
    def delegate_task(self, args):
        return {}

    def delegate_parallel(self, args):
        return {}


class _DummyRunTools:
    def view_runs(self, args):
        return {}

    def cancel_run(self, args):
        return {}

    def pause_run(self, args):
        return {}

    def resume_run(self, args):
        return {}

    def message_run(self, args):
        return {}

    def replace_task_run(self, args):
        return {}

    def reprioritize_run(self, args):
        return {}

    def get_world_state(self, args):
        return {}

    def wait_for_event(self, args):
        return {}


class AgentContractsTest(unittest.TestCase):
    def test_director_required_tools_are_described_for_ui(self) -> None:
        tools = describe_all_tools(Settings())
        director_names = {item["name"] for item in tools if item.get("agent") == "director"}
        self.assertTrue(DIRECTOR_REQUIRED_TOOLS.issubset(director_names))

    def test_director_required_tools_are_registered(self) -> None:
        registry = build_director_registry(_DummyDelegateTools(), _DummyRunTools())  # type: ignore[arg-type]
        names = {item["name"] for item in registry.describe_all()}
        self.assertTrue(DIRECTOR_REQUIRED_TOOLS.issubset(names))

    def test_director_required_tools_are_registered_without_run_context(self) -> None:
        registry = build_director_registry(_DummyDelegateTools(), None)  # type: ignore[arg-type]
        names = {item["name"] for item in registry.describe_all()}
        self.assertTrue(DIRECTOR_REQUIRED_TOOLS.issubset(names))

    def test_settings_service_protects_required_tools(self) -> None:
        config = {"director": {"tools": [{"name": "message_run", "enabled": False}]}}
        cleaned = SettingsService().sanitize_agents_config(config)
        tools = {item["name"]: item for item in cleaned["director"]["tools"]}
        self.assertTrue(tools["message_run"]["enabled"])
        self.assertTrue(tools["message_run"]["required"])
        self.assertTrue(DIRECTOR_REQUIRED_TOOLS.issubset(set(tools)))

    def test_file_create_uses_path_guard(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            allowed = Path(tmp)
            tools = FileTools(PathGuard([allowed]))
            result = tools.create_file({"path": str(allowed / "ok.txt"), "content": "ok"})
            self.assertTrue(result["created"])
            with self.assertRaises(Exception):
                tools.create_file({"path": str(allowed.parent / "blocked.txt"), "content": "no"})

    def test_sub_agent_result_normalizes_plain_text(self) -> None:
        result = SubAgentResult.from_raw({"agent_name": "file", "run_id": "r1", "result": "done", "success": True})
        self.assertEqual(result.run_id, "r1")
        self.assertIn(result.status, {"done", "failed"})

    def test_event_normalization_adds_payload(self) -> None:
        event = normalize_event("agent_warning", "hello")
        self.assertEqual(event.payload["value"], "hello")
        self.assertGreater(event.timestamp, 0)

    def test_diagnostics_shape(self) -> None:
        report = DiagnosticsService(Settings()).run()
        self.assertIn("checks", report)
        self.assertIn("score", report)


if __name__ == "__main__":
    unittest.main()
