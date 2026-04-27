from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any, Callable

import requests

from src.agent.schemas import ActionStep
from src.infra.errors import LLMResponseError, ValidationError


@dataclass
class LLMResponse:
    content: str
    thinking: str = ""
    eval_count: int = 0
    prompt_eval_count: int = 0
    done_reason: str = "stop"


class OllamaClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        timeout_seconds: int | None,
        num_ctx: int = 32768,
        api_key: str | None = None,
        keep_alive: str = "10m",
        think: bool = False,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.think = think
        self._headers: dict[str, str] = {"Content-Type": "application/json"}
        if api_key:
            self._headers["Authorization"] = f"Bearer {api_key}"

    def _action_step_format_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
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
                "done": {"type": "boolean"},
                "summary": {
                    "anyOf": [
                        {"type": "string"},
                        {"type": "null"},
                    ]
                },
            },
            "required": ["action", "args", "done"],
        }

    def _build_request_body(
        self,
        messages: list[dict[str, object]],
        stream: bool,
        response_format: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": stream,
            "keep_alive": self.keep_alive,
            "options": {"num_ctx": self.num_ctx},
        }
        if response_format is not None:
            body["format"] = response_format
        if self.think:
            body["think"] = True
        return body

    def plan_next_step(
        self,
        messages: list[dict[str, object]],
        on_stream_content: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        on_retry_error: Callable[[int, int, str], None] | None = None,
        max_retries: int = 3,
    ) -> ActionStep:
        response_format = self._action_step_format_schema()
        last_exc: Exception | None = None
        retry_messages = list(messages)
        bad_content = ""
        for attempt in range(1, max_retries + 1):
            try:
                if on_stream_content is None:
                    llm_resp = self._call(retry_messages, response_format=response_format)
                    if on_thinking and llm_resp.thinking:
                        on_thinking(llm_resp.thinking)
                else:
                    llm_resp = self._stream(retry_messages, on_stream_content, on_thinking=on_thinking)
                content = self._clean_markdown_code_blocks(llm_resp.content)
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    # Модель вернула текст вместо JSON — пробуем обернуть в finish_task
                    text = content.strip()
                    if text and not text.startswith("{"):
                        parsed = {"action": "finish_task", "args": {"summary": text}, "done": True}
                    else:
                        raise LLMResponseError(f"Невалидный JSON: {text[:200]}") from None
                # Ollama иногда вставляет "text\n" как placeholder для string-полей в JSON Schema
                args = parsed.get("args")
                if isinstance(args, dict):
                    for key in ("summary", "message", "task"):
                        val = args.get(key)
                        if isinstance(val, str) and re.match(r"^text[\s\n]", val):
                            args[key] = val[4:].lstrip("\n").lstrip()
                step = ActionStep.from_dict(parsed)
                step._llm_response = llm_resp
                return step
            except (LLMResponseError, ValidationError) as exc:
                last_exc = exc
                bad_content = ""
                try:
                    bad_content = llm_resp.content
                except Exception:
                    pass
                if on_retry_error:
                    on_retry_error(attempt, max_retries, str(exc))
                if attempt < max_retries:
                    retry_messages = list(messages) + [
                        {"role": "assistant", "content": bad_content},
                        {"role": "user", "content": f"ОШИБКА ФОРМАТА: {exc}\nОтветь ТОЛЬКО валидным JSON с полями: action, args, done. Никакого текста вне JSON. Ответ должен быть коротким."},
                    ]
                    time.sleep(1.5 * attempt)
            except Exception:
                raise
        # Попробуем извлечь частичный ответ из последнего контента
        if last_exc is not None:
            try:
                raw = bad_content if bad_content else ""
                # Пробуем починить обрезанный JSON
                if '"finish_task"' in raw or '"done":true' in raw or '"done": true' in raw:
                    return ActionStep(action="finish_task", args={"summary": "Задача завершена"}, done=True)
            except Exception:
                pass
        raise last_exc  # type: ignore[misc]

    def chat(self, messages: list[dict[str, object]]) -> str:
        """Простой текстовый запрос без JSON-формата. Возвращает сырой текст ответа."""
        return self._call(messages).content

    def _call(
        self,
        messages: list[dict[str, object]],
        response_format: dict[str, Any] | None = None,
    ) -> LLMResponse:
        """Синхронный не-потоковый запрос. Возвращает LLMResponse."""
        body = self._build_request_body(messages, stream=False, response_format=response_format)
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=body,
            headers=self._headers,
            timeout=self.timeout_seconds,
        )
        response.raise_for_status()
        response.encoding = "utf-8"
        return self._parse_response(response.json())

    def _stream(
        self,
        messages: list[dict[str, object]],
        on_content: Callable[[str], None],
        on_thinking: Callable[[str], None] | None = None,
    ) -> LLMResponse:
        """Потоковый запрос. Вызывает on_content по мере генерации, возвращает полный LLMResponse."""
        body = self._build_request_body(
            messages, stream=True, response_format=self._action_step_format_schema()
        )
        response = requests.post(
            f"{self.base_url}/api/chat",
            json=body,
            headers=self._headers,
            timeout=self.timeout_seconds,
            stream=True,
        )
        response.raise_for_status()
        response.encoding = "utf-8"

        content_parts: list[str] = []
        thinking_parts: list[str] = []
        eval_count = 0
        prompt_eval_count = 0
        done_reason = "stop"

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
                    on_content("".join(content_parts))
                thinking_chunk = message.get("thinking")
                if isinstance(thinking_chunk, str) and thinking_chunk:
                    thinking_parts.append(thinking_chunk)
                    if on_thinking:
                        on_thinking("".join(thinking_parts))

            if payload.get("done"):
                eval_count = payload.get("eval_count", 0)
                prompt_eval_count = payload.get("prompt_eval_count", 0)
                done_reason = payload.get("done_reason", "stop")

        return LLMResponse(
            content="".join(content_parts),
            thinking="".join(thinking_parts),
            eval_count=eval_count,
            prompt_eval_count=prompt_eval_count,
            done_reason=done_reason,
        )

    def _parse_response(self, payload: dict[str, Any]) -> LLMResponse:
        """Разбирает не-потоковый ответ Ollama в LLMResponse."""
        message = payload.get("message")
        if not isinstance(message, dict):
            raise LLMResponseError("В ответе Ollama отсутствует message")
        content = message.get("content")
        if not isinstance(content, str) or not content.strip():
            raise LLMResponseError("В ответе Ollama отсутствует content")
        return LLMResponse(
            content=content.strip(),
            thinking=message.get("thinking") or "",
            eval_count=payload.get("eval_count", 0),
            prompt_eval_count=payload.get("prompt_eval_count", 0),
            done_reason=payload.get("done_reason", "stop"),
        )

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
