from __future__ import annotations

import json

import pytest

from src.llm.ollama_client import OllamaClient, parse_pseudo_tool_call


@pytest.fixture()
def client() -> OllamaClient:
    return OllamaClient("http://127.0.0.1:11434", "test-model", 10)


def _valid(text: str) -> bool:
    try:
        json.loads(text)
        return True
    except json.JSONDecodeError:
        return False


def test_clean_markdown_fences(client: OllamaClient) -> None:
    raw = '```json\n{"action": "finish_task", "args": {}, "done": true}\n```'
    cleaned = client._clean_markdown_code_blocks(raw)
    assert _valid(cleaned)
    assert json.loads(cleaned)["action"] == "finish_task"


def test_clean_strips_surrounding_prose(client: OllamaClient) -> None:
    raw = 'Вот ответ: {"action": "noop", "args": {}, "done": false} — готово'
    cleaned = client._clean_markdown_code_blocks(raw)
    assert json.loads(cleaned)["action"] == "noop"


def test_repair_truncated_object(client: OllamaClient) -> None:
    raw = '{"action": "finish_task", "args": {"summary": "hi"'
    repaired = client._try_repair_json(raw)
    assert _valid(repaired)


def test_repair_truncated_string(client: OllamaClient) -> None:
    raw = '{"action": "finish_task", "args": {"summary": "unclosed'
    repaired = client._try_repair_json(raw)
    assert _valid(repaired)


def test_repair_trailing_comma(client: OllamaClient) -> None:
    raw = '{"action": "noop", "args": {}, "done": false,'
    repaired = client._try_repair_json(raw)
    assert _valid(repaired)


def test_fix_literal_newlines_inside_strings(client: OllamaClient) -> None:
    raw = '{"summary": "line1\nline2"}'
    fixed = client._fix_literal_newlines_in_json(raw)
    assert _valid(fixed)
    assert json.loads(fixed)["summary"] == "line1\nline2"


def test_fix_literal_newlines_leaves_structure(client: OllamaClient) -> None:
    raw = '{\n  "a": "b"\n}'
    fixed = client._fix_literal_newlines_in_json(raw)
    assert json.loads(fixed) == {"a": "b"}


def test_valid_json_passthrough(client: OllamaClient) -> None:
    raw = '{"action": "x", "args": {}, "done": false}'
    assert client._try_repair_json(raw) == raw


def test_parse_pseudo_tool_call_no_params() -> None:
    # Реальный кейс: MiMo v2.5 через OpenCode ACP вместо JSON action-schema
    # выдала <tool_call><function=take_screenshot></function></tool_call> —
    # легитимный вызов нашего PC-инструмента, просто в заученном на
    # претрейне Hermes/Qwen-style синтаксисе.
    raw = "<tool_call> <function=take_screenshot> </function> </tool_call>"
    result = parse_pseudo_tool_call(raw)
    assert result == {"thought": "", "action": "take_screenshot", "args": {}, "done": False}


def test_parse_pseudo_tool_call_with_params() -> None:
    raw = (
        "<tool_call>\n<function=bash>\n"
        '<parameter=command>echo "test"</parameter>\n'
        "<parameter=description>Run echo test</parameter>\n"
        "</function>\n</tool_call>"
    )
    result = parse_pseudo_tool_call(raw)
    assert result == {
        "thought": "",
        "action": "bash",
        "args": {"command": 'echo "test"', "description": "Run echo test"},
        "done": False,
    }


def test_parse_pseudo_tool_call_returns_none_for_plain_text() -> None:
    assert parse_pseudo_tool_call("Обычный текстовый ответ без вызовов.") is None
