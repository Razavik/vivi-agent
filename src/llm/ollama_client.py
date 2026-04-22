from __future__ import annotations

import json
import re
import time
from typing import Any, Callable

import requests

from src.agent.schemas import ActionStep
from src.infra.errors import LLMResponseError


class OllamaClient:
    def __init__(self, base_url: str, model: str, timeout_seconds: int | None, num_ctx: int = 32768) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx

    def _action_step_format_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "thought": {"type": "string"},
                "action": {"type": "string"},
                "args": {
                    "type": "object",
                    "additionalProperties": True,
                },
                "plan": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "string"},
                            "content": {"type": "string"},
                            "status": {"type": "string"},
                        },
                        "required": ["id", "content", "status"],
                    },
                },
                "requires_confirmation": {"type": "boolean"},
                "done": {"type": "boolean"},
                "summary": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "null"},
                    ]
                },
            },
            "required": ["action", "args", "requires_confirmation", "done"],
        }

    def plan_next_step(
        self,
        messages: list[dict[str, object]],
        on_stream_content: Callable[[str], None] | None = None,
        max_retries: int = 3,
    ) -> ActionStep:
        response_format = self._action_step_format_schema()
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                if on_stream_content is None:
                    response = requests.post(
                        f"{self.base_url}/api/chat",
                        json={
                            "model": self.model,
                            "messages": messages,
                            "stream": False,
                            "format": response_format,
                            "options": {"num_ctx": self.num_ctx},
                        },
                        timeout=self.timeout_seconds,
                    )
                    response.raise_for_status()
                    response.encoding = "utf-8"
                    data = response.json()
                    content = self._extract_content(data)
                else:
                    content = self._stream_content(messages, on_stream_content)
                content = self._clean_markdown_code_blocks(content)
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError as exc:
                    raise LLMResponseError(f"Модель вернула невалидный JSON: {content}") from exc
                return ActionStep.from_dict(parsed)
            except LLMResponseError as exc:
                last_exc = exc
                if attempt < max_retries:
                    time.sleep(1.5 * attempt)
            except Exception:
                raise
        raise last_exc  # type: ignore[misc]

    def chat(self, messages: list[dict[str, object]]) -> str:
        """Простой текстовый запрос без JSON-формата. Возвращает сырой текст ответа."""
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": False,
                "options": {"num_ctx": self.num_ctx},
            },
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        data = response.json()
        return self._extract_content(data)

    def _stream_content(
        self,
        messages: list[dict[str, object]],
        on_stream_content: Callable[[str], None],
    ) -> str:
        response = requests.post(
            f"{self.base_url}/api/chat",
            json={
                "model": self.model,
                "messages": messages,
                "stream": True,
                "format": self._action_step_format_schema(),
                "options": {"num_ctx": self.num_ctx},
            },
            timeout=self.timeout_seconds,
            stream=True,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        content_parts: list[str] = []
        for raw_line in response.iter_lines(decode_unicode=False):
            if not raw_line:
                continue
            try:
                line = raw_line.decode("utf-8")
            except UnicodeDecodeError as exc:
                raise LLMResponseError("Модель вернула поток не в UTF-8") from exc
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LLMResponseError(f"Модель вернула невалидный поток JSON: {line}") from exc
            message = payload.get("message")
            if isinstance(message, dict):
                chunk = message.get("content")
                if isinstance(chunk, str) and chunk:
                    content_parts.append(chunk)
                    on_stream_content("".join(content_parts))
        return "".join(content_parts)

    def _extract_content(self, payload: dict[str, Any]) -> str:
        message = payload.get("message")
        if not isinstance(message, dict):
            raise LLMResponseError("В ответе Ollama отсутствует message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("В ответе Ollama отсутствует content")
        return content.strip()

    def _clean_markdown_code_blocks(self, content: str) -> str:
        # Убираем markdown кодовые блокки вида ```json ... ``` или ``` ... ```
        pattern = r"```(?:json)?\s*([\s\S]*?)\s*```"
        matches = re.findall(pattern, content)
        if matches:
            content = matches[-1].strip()
        # Обрезаем любой текст до первого { и после последнего }
        # Это убирает "думает вслух", <function_call>, === заголовки === и прочее
        start = content.find("{")
        end = content.rfind("}")
        if start != -1 and end != -1 and end >= start:
            content = content[start:end + 1]
        # Заменяем реальные переносы строк внутри JSON-строк на \n
        # Модели иногда вставляют буквальный \n в строковое поле, ломая JSON
        content = self._fix_literal_newlines_in_json(content)
        # Пробуем починить обрезанный JSON (незакрытая строка / объект)
        content = self._try_repair_json(content)
        return content

    def _try_repair_json(self, content: str) -> str:
        """Пробует починить обрезанный JSON: закрывает незакрытые строки, объекты и массивы."""
        try:
            json.loads(content)
            return content  # уже валидный
        except json.JSONDecodeError:
            pass

        # Проходим посимвольно, отслеживая стек вложенности и строковое состояние
        stack: list[str] = []  # '{' или '['
        in_string = False
        escape_next = False
        for ch in content:
            if escape_next:
                escape_next = False
                continue
            if ch == "\\":
                escape_next = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch in ("{", "["):
                stack.append(ch)
            elif ch == "}":
                if stack and stack[-1] == "{":
                    stack.pop()
            elif ch == "]":
                if stack and stack[-1] == "[":
                    stack.pop()

        # Строим суффикс: закрываем незакрытую строку, затем стек в обратном порядке
        suffix = ""
        if in_string:
            suffix += '"'
        for opener in reversed(stack):
            suffix += "}" if opener == "{" else "]"

        if not suffix:
            return content  # ничего не исправить

        # Перед закрытием объекта убираем висячую запятую или незакрытый ключ
        trimmed = (content + suffix).rstrip()
        # Удаляем trailing запятую перед закрывающими скобками
        trimmed = re.sub(r",\s*([}\]])", r"\1", trimmed)

        try:
            json.loads(trimmed)
            return trimmed
        except json.JSONDecodeError:
            return content  # не смогли починить — вернём оригинал

    def _fix_literal_newlines_in_json(self, content: str) -> str:
        """Заменяет буквальные переносы строк внутри JSON-строковых значений на \\n."""
        result = []
        in_string = False
        escape_next = False
        for ch in content:
            if escape_next:
                result.append(ch)
                escape_next = False
            elif ch == "\\":
                result.append(ch)
                escape_next = True
            elif ch == '"':
                result.append(ch)
                in_string = not in_string
            elif in_string and ch == "\n":
                result.append("\\n")
            elif in_string and ch == "\r":
                result.append("\\r")
            elif in_string and ch == "\t":
                result.append("\\t")
            else:
                result.append(ch)
        return "".join(result)
