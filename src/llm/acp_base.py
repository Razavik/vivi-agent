from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from queue import Empty, Queue
from typing import Any, Callable

from src.agent.core.schemas import ActionStep
from src.infra.errors import AgentError, LLMResponseError, ValidationError
from src.llm.ollama_client import LLMResponse, clean_markdown_code_blocks, parse_pseudo_tool_call


class AcpClient:
    """Общий клиент к любому агенту, говорящему по Agent Client Protocol
    (JSON-RPC поверх stdio) — используется и Codex (см. codex_acp_client.py),
    и OpenCode (см. opencode_acp_client.py). Оба реализуют один и тот же
    протокол (session/new, session/prompt, session/update-нотификации), но
    расходятся в том, как выбирается модель для сессии — Codex через env
    при старте процесса, OpenCode через session/set_config_option после
    создания сессии. Эти два места вынесены в переопределяемые хуки
    (_extra_env/_after_session_new), остальное — общий код.

    Публичный интерфейс (chat/plan_next_step/cancel_active_request)
    намеренно зеркалит OllamaClient, чтобы вызывающий код (runtime.py,
    sub_agent.py, routes.py) мог получить любой из клиентов взаимозаменяемо
    — см. src.llm.client_factory.
    """

    def __init__(
        self,
        model: str,
        command: list[str],
        timeout_seconds: int | None = None,
        cwd: str | None = None,
        default_num_ctx: int = 200_000,
        error_label: str = "ACP",
    ) -> None:
        self.model = model
        self.timeout_seconds = timeout_seconds or 120
        self.cwd = cwd or os.getcwd()
        # Реальный размер контекстного окна репортится через session/update
        # (usage_update.size), но недоступен до первого запроса — до тех пор
        # используем default_num_ctx, а после первого ответа _prompt()
        # перезаписывает более точным значением.
        self.num_ctx = default_num_ctx
        self._error_label = error_label
        self._command = command
        self._proc: subprocess.Popen[str] | None = None
        self._out_q: Queue[str] = Queue()
        self._start_lock = threading.Lock()
        self._rpc_lock = threading.Lock()
        self._next_id = 1
        self._cancel_requested = False
        self._started = False

    # --- переопределяется в наследниках -----------------------------------
    def _extra_env(self) -> dict[str, str]:
        """Доп. переменные окружения для подпроцесса (напр. CODEX_CONFIG)."""
        return {}

    def _after_session_new(self, session_id: str) -> None:
        """Хук сразу после создания сессии — напр. выбор модели через RPC."""

    # --- lifecycle ---------------------------------------------------------
    def _ensure_started(self) -> None:
        if self._started:
            return
        with self._start_lock:
            if self._started:
                return
            env = dict(os.environ)
            env.update(self._extra_env())
            self._proc = subprocess.Popen(
                self._command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                # errors="replace" — не роняем весь ответ из-за одного
                # неудачного байта на границе чанка; text=True без encoding
                # на Windows декодировал бы UTF-8-вывод дочернего процесса
                # через системную кодовую страницу (обычно cp1251) — отсюда
                # "кракозябры" вместо кириллицы в ответах модели.
                errors="replace",
                bufsize=1,
                env=env,
                shell=(os.name == "nt"),
            )
            threading.Thread(target=self._pump_stdout, daemon=True).start()
            threading.Thread(target=self._drain_stderr, daemon=True).start()
            self._rpc(
                "initialize",
                {
                    "protocolVersion": 1,
                    "clientCapabilities": {"fs": {"readTextFile": False, "writeTextFile": False}},
                },
            )
            self._started = True

    def _pump_stdout(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        for line in proc.stdout:
            self._out_q.put(line)

    def _drain_stderr(self) -> None:
        proc = self._proc
        if proc is None or proc.stderr is None:
            return
        for _ in proc.stderr:
            pass  # логи адаптера не нужны в проде

    def close(self) -> None:
        proc, self._proc = self._proc, None
        self._started = False
        if proc is not None:
            try:
                proc.terminate()
            except Exception:
                pass

    def cancel_active_request(self) -> None:
        self._cancel_requested = True

    def reset_cancel_request(self) -> None:
        self._cancel_requested = False

    # --- JSON-RPC поверх stdio ----------------------------------------------
    def _send(self, obj: dict[str, Any]) -> None:
        proc = self._proc
        if proc is None or proc.stdin is None:
            raise AgentError(f"{self._error_label} процесс не запущен")
        proc.stdin.write(json.dumps(obj) + "\n")
        proc.stdin.flush()

    def _rpc(self, method: str, params: dict[str, Any], timeout: float | None = None) -> Any:
        with self._rpc_lock:
            req_id = self._next_id
            self._next_id += 1
            self._send({"jsonrpc": "2.0", "id": req_id, "method": method, "params": params})
            deadline = time.monotonic() + (timeout or self.timeout_seconds)
            while time.monotonic() < deadline:
                if self._cancel_requested:
                    raise AgentError(f"Запрос к {self._error_label} отменён")
                try:
                    line = self._out_q.get(timeout=max(0.1, deadline - time.monotonic()))
                except Empty:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if msg.get("id") == req_id:
                    if "error" in msg:
                        raise LLMResponseError(f"{self._error_label} error: {msg['error']}")
                    return msg.get("result")
            raise LLMResponseError(f"{self._error_label}: превышен таймаут ожидания ответа на {method}")

    def _new_session(self) -> str:
        result = self._rpc("session/new", {"cwd": self.cwd, "mcpServers": []})
        session_id = result["sessionId"]
        self._after_session_new(session_id)
        return session_id

    def _prompt(
        self,
        session_id: str,
        text: str,
        on_content: Callable[[str], None] | None,
        on_thinking: Callable[[str], None] | None,
        images: list[str] | None = None,
    ) -> LLMResponse:
        # session/prompt не эксклюзивен через _rpc(), т.к. параллельно с
        # ответом на запрос приходит поток session/update-нотификаций без
        # своего id — их нужно перехватывать по мере поступления, а не
        # дожидаться финального ответа с этим же id.
        prompt_blocks: list[dict[str, Any]] = [{"type": "text", "text": text}]
        for image_b64 in images or []:
            # mimeType хардкожен как image/png по тому же соглашению, что и
            # весь остальной проект (см. Composer.tsx: превью вложений всегда
            # рендерится как data:image/png;base64,...) — фронтенд не
            # передаёт исходный MIME-тип загруженного файла.
            prompt_blocks.append({
                "type": "image",
                "data": image_b64,
                "mimeType": "image/png",
            })
        with self._rpc_lock:
            req_id = self._next_id
            self._next_id += 1
            self._send({
                "jsonrpc": "2.0",
                "id": req_id,
                "method": "session/prompt",
                "params": {
                    "sessionId": session_id,
                    "prompt": prompt_blocks,
                },
            })
            content_parts: list[str] = []
            thinking_parts: list[str] = []
            deadline = time.monotonic() + self.timeout_seconds
            while time.monotonic() < deadline:
                if self._cancel_requested:
                    raise AgentError(f"Запрос к {self._error_label} отменён")
                try:
                    line = self._out_q.get(timeout=max(0.1, deadline - time.monotonic()))
                except Empty:
                    break
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if msg.get("method") == "session/update":
                    params = msg.get("params") or {}
                    if params.get("sessionId") != session_id:
                        continue
                    update = params.get("update") or {}
                    kind = update.get("sessionUpdate")
                    if kind == "agent_message_chunk":
                        chunk = (update.get("content") or {}).get("text", "")
                        if chunk:
                            content_parts.append(chunk)
                            if on_content:
                                on_content("".join(content_parts))
                    elif kind == "agent_thought_chunk":
                        chunk = (update.get("content") or {}).get("text", "")
                        if chunk:
                            thinking_parts.append(chunk)
                            if on_thinking:
                                on_thinking("".join(thinking_parts))
                    elif kind == "usage_update":
                        size = update.get("size")
                        if isinstance(size, int) and size > 0:
                            self.num_ctx = size
                    continue

                if msg.get("id") == req_id:
                    if "error" in msg:
                        raise LLMResponseError(f"{self._error_label} error: {msg['error']}")
                    result = msg.get("result") or {}
                    usage = result.get("usage") or {}
                    # usage.inputTokens — только "свежие" (не из кэша) токены
                    # промпта; usage.cachedReadTokens — токены, попавшие в
                    # prompt cache (обычно бОльшая часть — системный промпт и
                    # описания инструментов почти не меняются между ходами).
                    # runtime.py считает реальный размер контекста как
                    # prompt_eval_count + eval_count для индикатора
                    # "Контекстное окно" — без учёта cachedReadTokens он
                    # занижал бы потребление контекста в разы.
                    prompt_tokens = usage.get("inputTokens", 0) + usage.get(
                        "cachedReadTokens", 0
                    )
                    return LLMResponse(
                        content="".join(content_parts).strip(),
                        thinking="".join(thinking_parts),
                        eval_count=usage.get("outputTokens", 0),
                        prompt_eval_count=prompt_tokens,
                        done_reason="length" if result.get("stopReason") == "max_tokens" else "stop",
                    )
            raise LLMResponseError(f"{self._error_label}: превышен таймаут ожидания ответа модели")

    @staticmethod
    def _messages_to_prompt(messages: list[dict[str, object]]) -> str:
        # ACP session/prompt принимает контент как есть, без ролей per-turn —
        # вся история (system+user, а при retry ещё и assistant/user) уже
        # собрана вызывающим кодом в messages, поэтому просто сериализуем её
        # в один текстовый блок с явными метками ролей.
        labels = {"system": "СИСТЕМНАЯ ИНСТРУКЦИЯ", "user": "ПОЛЬЗОВАТЕЛЬ", "assistant": "АССИСТЕНТ"}
        parts = []
        for message in messages:
            role = str(message.get("role", "user"))
            content = str(message.get("content", ""))
            parts.append(f"### {labels.get(role, role.upper())}\n{content}")
        return "\n\n".join(parts)

    @staticmethod
    def _collect_images(messages: list[dict[str, object]]) -> list[str]:
        # prompt_builder.build_messages кладёт вложенные картинки в
        # user_message["images"] (список base64) — тот же формат, что
        # понимает Ollama. Раньше это поле тут просто игнорировалось: модель
        # получала текст промпта, но ни одной картинки, и честно отвечала
        # "изображение не прикреплено", хотя пользователь его прикрепил.
        images: list[str] = []
        for message in messages:
            raw = message.get("images")
            if isinstance(raw, list):
                images.extend(str(item) for item in raw if item)
        return images

    # --- публичный API, совместимый с OllamaClient --------------------------
    def chat(self, messages: list[dict[str, object]]) -> str:
        """Простой текстовый запрос без JSON-формата. Возвращает сырой текст ответа."""
        self._ensure_started()
        session_id = self._new_session()
        response = self._prompt(
            session_id,
            self._messages_to_prompt(messages),
            None,
            None,
            images=self._collect_images(messages),
        )
        return response.content

    def plan_next_step(
        self,
        messages: list[dict[str, object]],
        on_stream_content: Callable[[str], None] | None = None,
        on_thinking: Callable[[str], None] | None = None,
        on_retry_error: Callable[[int, int, str], None] | None = None,
        max_retries: int = 3,
    ) -> ActionStep:
        prompt_text = self._messages_to_prompt(messages)
        # Картинки достаём один раз из исходных messages — при retry
        # prompt_text дополняется текстом об ошибке формата, но вложения
        # пользователя от этого не меняются, отправляем те же самые.
        images = self._collect_images(messages)
        self._ensure_started()
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            llm_resp: LLMResponse | None = None
            try:
                session_id = self._new_session()
                llm_resp = self._prompt(
                    session_id, prompt_text, on_stream_content, on_thinking, images=images
                )
                content = clean_markdown_code_blocks(llm_resp.content)
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    pseudo = parse_pseudo_tool_call(llm_resp.content)
                    if pseudo is not None:
                        parsed = pseudo
                    else:
                        text = content.strip()
                        if text and not text.startswith("{"):
                            parsed = {"action": "finish_task", "args": {"summary": text}, "done": True}
                        else:
                            raise LLMResponseError(f"Невалидный JSON: {text[:200]}") from None
                step = ActionStep.from_dict(parsed)
                step._llm_response = llm_resp
                return step
            except (LLMResponseError, ValidationError) as exc:
                last_exc = exc
                if on_retry_error:
                    on_retry_error(attempt, max_retries, str(exc))
                if attempt < max_retries:
                    bad_content = llm_resp.content if llm_resp is not None else ""
                    prompt_text = (
                        prompt_text
                        + f"\n\n### ПРЕДЫДУЩИЙ ОТВЕТ (некорректный)\n{bad_content}"
                        + f"\n\n### ОШИБКА ФОРМАТА\n{exc}\nОтветь ТОЛЬКО валидным JSON с полями: "
                        + "action, args, done. Никакого текста вне JSON."
                    )
                    time.sleep(1.5 * attempt)
        assert last_exc is not None
        raise last_exc
