from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from src.agent.core.schemas import ActionStep
from src.agent.core.state import ChatMessage, Observation, PlanItem, SessionState
from src.agent.lifecycle.run_control import RunController
from src.infra.chat_memory import ChatMemoryStore
from src.infra.errors import AgentError, PolicyError, ToolExecutionError
from src.llm.client_factory import LLMClient
from src.safety.policy import SafetyPolicy
from src.safety.run_policy import RunPolicy
from src.safety.validator import ActionValidator
from src.tools.core.confirmation_tools import finish_task
from src.tools.core.registry import ToolRegistry, ToolSpec, result_indicates_failure


_MIN_WAIT_SECONDS = 1.0
_MAX_WAIT_SECONDS = 120.0
_DEFAULT_WAIT_SECONDS = 20.0
_WAIT_POLL_INTERVAL = 1.0
# Отдельный, более редкий интервал для опроса внешнего состояния (например
# новых сообщений в чате) внутри wait — в отличие от проверки отмены, это
# сетевой запрос, и дёргать его так же часто, как is_cancelled(), избыточно.
_MESSAGE_POLL_INTERVAL = 5.0
# Порог (в символах сериализованного result), выше которого наблюдение считается
# "тяжёлым" и перед сохранением в долгосрочную память прогоняется через LLM для
# сжатия — вместо того чтобы копить сырые дампы (например fetch_url до 20000
# символов) в data/agents/*-memory.json и истории в UI.
_MEMORY_CLEAN_THRESHOLD = 800
_MEMORY_SUMMARY_MAX_CHARS = 400


class SubAgent:
    """Специализированный агент с собственным LLM-циклом, промптом, памятью и инструментами."""

    def __init__(
        self,
        name: str,
        display_name: str,
        prompt_path: str,
        tools: list,  # list[ToolSpec]
        client: LLMClient,
        memory_store: ChatMemoryStore,
        max_steps: int = 50,
        user_name: str = "Пользователь",
        prompt_vars: dict[str, str] | None = None,
        server_context: Any | None = None,
        wait_message_poll: Callable[[str, int | None, str | None], list[dict[str, Any]]] | None = None,
    ) -> None:
        self.name = name
        self.display_name = display_name
        self.prompt_path = prompt_path
        self.tools = tools
        self.client = client
        self.memory_store = memory_store
        self.max_steps = max_steps
        self.user_name = user_name
        # Дополнительные плейсхолдеры для системного промпта конкретного агента
        # (например {tg_username}/{tg_display_name} у telegram) — подставляются
        # поверх {user_name} при построении system_prompt в run().
        self.prompt_vars = prompt_vars or {}
        # Нужен для сохранения картинок инструментов как артефактов (см.
        # src.infra.image_artifacts) — без него картинки остаются видны только
        # модели (через images в LLM-запросе), но не превращаются в URL для
        # прямой отдачи оператору/пользователю.
        self.server_context = server_context
        # Опциональный хук для досрочного выхода из wait, если во время ожидания
        # появилось новое сообщение (chat_id, since_message_id, from_user) -> список
        # новых сообщений. Сейчас реально подключается только для telegram-агента
        # (см. app_factory._build_sub_agents); для остальных агентов None, и wait
        # ведёт себя как раньше — просто таймер с проверкой отмены.
        self.wait_message_poll = wait_message_poll

        # Реестр собственных инструментов (без ask_operator — добавляется при run())
        self._base_tools = list(tools)

        self.validator: ActionValidator | None = None
        self.policy = SafetyPolicy()

    def _build_registry(
        self,
        ask_operator: Callable[[str], str] | None,
        controller: RunController | None = None,
    ) -> ToolRegistry:
        """Собирает реестр инструментов с опциональным ask_operator."""
        registry = ToolRegistry()
        for spec in self._base_tools:
            registry.register(spec)
        registry.register(ToolSpec(
            "finish_task",
            (
                "Завершить задачу и вернуть структурированный результат. attach_images=true "
                "встроит в summary картинки, увиденные за этот запуск (markdown-изображения), "
                "чтобы оператор мог напрямую передать их пользователю."
            ),
            0,
            finish_task,
            {
                "summary": "str?",
                "status": "str?",
                "changed_files": "list?",
                "created_artifacts": "list?",
                "verification": "list?",
                "risks": "list?",
                "needs_user_input": "bool?",
                "question": "str?",
                "attach_images": "bool?",
            },
        ))
        registry.register(ToolSpec(
            "wait",
            (
                "Приостановить свою работу на seconds секунд (1-120, по умолчанию 20), чтобы выждать "
                "внешнее событие — например, ответ собеседника в переписке. Не завершает задачу. "
                "Для многошагового ожидания вызывай wait несколько раз подряд, проверяя результат "
                "между вызовами (например get_messages для Telegram). Если передать chat_id и "
                "since_message_id (максимальный id уже увиденного сообщения в этом чате, опционально "
                "from_user), wait сам периодически проверяет чат и досрочно вернётся, как только "
                "появится новое сообщение (new_message_detected=true, new_messages=[...]) — не нужно "
                "ждать полный таймер и вручную гонять wait+get_messages в цикле."
            ),
            0,
            self._make_wait_handler(controller),
            {"seconds": "float?", "reason": "str?", "chat_id": "str?", "since_message_id": "int?", "from_user": "str?"},
        ))
        if ask_operator is not None:
            def _ask_operator_handler(args: dict[str, Any]) -> dict[str, Any]:
                question = str(args.get("question", ""))
                if not question:
                    raise ToolExecutionError("Параметр question обязателен")
                answer = ask_operator(question)
                return {"answer": answer}
            registry.register(ToolSpec(
                "ask_operator",
                "Задать вопрос оператору, если нужна уточняющая информация для выполнения задачи",
                0,
                _ask_operator_handler,
                {"question": "str"},
            ))
        return registry

    def _make_wait_handler(self, controller: RunController | None) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def _wait_handler(args: dict[str, Any]) -> dict[str, Any]:
            try:
                requested = float(args.get("seconds", _DEFAULT_WAIT_SECONDS))
            except (TypeError, ValueError):
                requested = _DEFAULT_WAIT_SECONDS
            seconds = max(_MIN_WAIT_SECONDS, min(requested, _MAX_WAIT_SECONDS))
            reason = str(args.get("reason", "")).strip()

            chat_id = str(args.get("chat_id", "")).strip()
            from_user = str(args.get("from_user", "")).strip() or None
            since_id_raw = args.get("since_message_id")
            try:
                since_id = int(since_id_raw) if since_id_raw is not None else None
            except (TypeError, ValueError):
                since_id = None
            # Без since_message_id нечего сравнивать с "новым" — опрос включаем только
            # когда явно есть и chat_id, и точка отсчёта.
            poll = self.wait_message_poll if (chat_id and since_id is not None) else None

            deadline = time.monotonic() + seconds
            next_poll_at = time.monotonic()
            while True:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                if controller is not None and controller.is_cancelled():
                    return {
                        "waited_seconds": round(seconds - remaining, 1),
                        "interrupted": True,
                        "reason": reason,
                    }
                if poll is not None and time.monotonic() >= next_poll_at:
                    next_poll_at = time.monotonic() + _MESSAGE_POLL_INTERVAL
                    try:
                        new_messages = poll(chat_id, since_id, from_user)
                    except Exception:
                        new_messages = []
                    if new_messages:
                        return {
                            "waited_seconds": round(seconds - remaining, 1),
                            "interrupted": False,
                            "new_message_detected": True,
                            "new_messages": new_messages,
                            "reason": reason,
                        }
                time.sleep(min(_WAIT_POLL_INTERVAL, remaining))

            return {"waited_seconds": seconds, "interrupted": False, "new_message_detected": False, "reason": reason}

        return _wait_handler

    def _clean_observations_for_memory(self, observations: list[Observation]) -> list[Observation]:
        """Сжимает "тяжёлые" результаты наблюдений (сериализация длиннее
        _MEMORY_CLEAN_THRESHOLD — типично fetch_url/search_web) через отдельный
        LLM-вызов перед сохранением в долгосрочную память, вместо простой обрезки:
        модель оставляет ключевые факты, а не первые N символов текста. Внутри
        текущего запуска (compact_observations, следующий шаг LLM) наблюдения
        остаются полными — эта чистка применяется только к копии, которая уйдёт
        в memory_store.append_session/write_snapshot."""
        heavy_indices: list[int] = []
        for i, obs in enumerate(observations):
            try:
                size = len(obs.result) if isinstance(obs.result, str) else len(json.dumps(obs.result, ensure_ascii=False))
            except (TypeError, ValueError):
                continue
            if size > _MEMORY_CLEAN_THRESHOLD:
                heavy_indices.append(i)

        if not heavy_indices:
            return observations

        payload = [
            {"index": i, "action": observations[i].action, "result": observations[i].result}
            for i in heavy_indices
        ]
        prompt = (
            "Ниже результаты вызовов инструментов агента, слишком длинные для "
            "хранения в памяти как есть. Для каждого элемента напиши краткое "
            f"резюме (до {_MEMORY_SUMMARY_MAX_CHARS} символов) — только реальные "
            "факты и данные из result, которые могут понадобиться в будущем "
            "(конкретные цифры, ссылки, выводы), без домыслов. Верни строго JSON "
            "вида {\"summaries\": [{\"index\": <int>, \"summary\": <str>}, ...]} "
            "той же длины и с теми же index, без пояснений вне JSON.\n\n"
            f"{json.dumps(payload, ensure_ascii=False)}"
        )

        try:
            raw = self.client.chat([{"role": "user", "content": prompt}])
            parsed = json.loads(raw)
            summaries = {
                int(item["index"]): str(item["summary"])
                for item in parsed["summaries"]
                if isinstance(item, dict) and "index" in item and "summary" in item
            }
        except Exception:
            summaries = {}

        cleaned = list(observations)
        for i in heavy_indices:
            summary = summaries.get(i)
            if not summary:
                # LLM недоступна/вернула мусор — safety net: простая обрезка вместо
                # полной потери данных или падения сохранения памяти.
                raw_text = (
                    observations[i].result
                    if isinstance(observations[i].result, str)
                    else json.dumps(observations[i].result, ensure_ascii=False)
                )
                summary = raw_text[:_MEMORY_SUMMARY_MAX_CHARS] + "... (не удалось сжать через LLM, обрезано)"
            cleaned[i] = Observation(
                step=observations[i].step,
                action=observations[i].action,
                result={"summary": summary, "cleaned_for_memory": True},
                success=observations[i].success,
                thought=observations[i].thought,
            )
        return cleaned

    def _persist_memory(self, state: SessionState) -> None:
        """Сохраняет сессию в долгосрочную память, предварительно сжимая тяжёлые
        результаты наблюдений (см. _clean_observations_for_memory)."""
        try:
            cleaned = self._clean_observations_for_memory(state.observations)
        except Exception:
            cleaned = state.observations
        self.memory_store.append_session(state.chat_history, cleaned, self.client.model)

    def _load_prompt(self) -> str:
        path = Path(self.prompt_path)
        if not path.is_absolute():
            # prompts/... лежит в корне проекта, а не в src/
            path = Path(__file__).resolve().parents[3] / self.prompt_path
        prompt = path.read_text(encoding="utf-8")
        shared_path = path.parent / "_shared.txt"
        if shared_path.exists():
            prompt = prompt.rstrip() + "\n\n" + shared_path.read_text(encoding="utf-8")
        return prompt

    def run(
        self,
        task: str,
        run_id: str,
        event_sink: Callable[[str, object], None] | None = None,
        ask_operator: Callable[[str], str] | None = None,
        controller: RunController | None = None,
        images: list[str] | None = None,
        run_policy: RunPolicy | None = None,
    ) -> dict[str, Any]:
        """Запускает LLM-цикл сабагента и возвращает структурированный результат."""
        state = SessionState(user_goal=task)

        # Загружаем долгосрочную память агента
        memory = self.memory_store.load()
        last_plan: list[PlanItem] | None = None
        for item in memory.get("chat_history", []):
            role = item.get("role")
            content = item.get("content")
            raw_plan = item.get("plan")
            if isinstance(role, str) and isinstance(content, str):
                plan_items: list[PlanItem] = []
                if isinstance(raw_plan, list):
                    for plan_item in raw_plan:
                        if not isinstance(plan_item, dict):
                            continue
                        item_id = plan_item.get("id")
                        item_content = plan_item.get("content")
                        item_status = plan_item.get("status")
                        if isinstance(item_id, str) and isinstance(item_content, str) and isinstance(item_status, str):
                            plan_items.append(PlanItem(id=item_id, content=item_content, status=item_status))
                state.memory_chat_history.append(ChatMessage(role=role, content=content, plan=plan_items))
                if role == "assistant" and plan_items:
                    last_plan = plan_items
        if last_plan:
            state.set_plan(last_plan)

        state.add_chat_message("user", task)
        self._emit(event_sink, "sub_agent_started", {
            "agent": self.name,
            "run_id": run_id,
            "task": task,
            "model": self.client.model,
        })

        wrapped_ask_operator: Callable[[str], str] | None = None
        if ask_operator is not None:
            def _wrapped_ask_operator(question: str) -> str:
                self._emit(event_sink, "sub_agent_question", {
                    "agent": self.name,
                    "run_id": run_id,
                    "question": question,
                })
                answer = ask_operator(question)
                self._emit(event_sink, "sub_agent_answer", {
                    "agent": self.name,
                    "run_id": run_id,
                    "question": question,
                    "answer": answer,
                })
                return answer

            wrapped_ask_operator = _wrapped_ask_operator

        if controller is not None:
            # Без этого cancel() саб-агента только выставляет флаг, но не прерывает
            # уже идущий блокирующий HTTP-запрос к LLM — сессия зависает до его
            # естественного завершения (или навсегда, если Ollama не отвечает).
            controller.register_cancel_callback(self.client.cancel_active_request)

        registry = self._build_registry(wrapped_ask_operator, controller)
        validator = ActionValidator(registry)

        system_prompt = self._load_prompt()
        system_prompt = system_prompt.replace("{user_name}", self.user_name)
        for key, value in self.prompt_vars.items():
            system_prompt = system_prompt.replace("{" + key + "}", value)

        last_actions: list[tuple[str, str]] = []  # (action, args_repr)
        policy = run_policy or RunPolicy()  # по умолчанию — standard без квот
        # Изображения, переданные оператором при делегировании (images) плюс те, что
        # вернут инструменты по ходу выполнения (_type=="image") — накапливаются здесь
        # и отправляются в следующий LLM-запрос, затем список очищается (не дублируем
        # одну и ту же картинку в каждом последующем сообщении).
        extracted_images: list[str] = list(images) if images else []
        # Все картинки, увиденные за этот run (сохранённые как артефакты, URL) —
        # не очищается между шагами (в отличие от extracted_images), чтобы
        # finish_task(attach_images=true) мог встроить их в итоговый summary,
        # а оператор — увидеть полный список через delegate_task-результат.
        image_urls: list[str] = []

        for step_number in range(1, self.max_steps + 1):
            try:
                # Проверка квоты времени
                policy.check_runtime()
                # Проверка квоты шагов
                policy.tick_step()

                if controller is not None and controller.is_cancelled():
                    raise AgentError(f"Агент {self.display_name} прерван по run_id={run_id}")
                if controller is not None and controller.is_paused():
                    self._emit(event_sink, "sub_agent_paused", {"agent": self.name, "run_id": run_id})
                    while controller.is_paused() and not controller.is_cancelled():
                        time.sleep(0.5)
                    if controller.is_cancelled():
                        raise AgentError(f"Агент {self.display_name} прерван по run_id={run_id}")
                    self._emit(event_sink, "sub_agent_resumed", {"agent": self.name, "run_id": run_id})
                if controller is not None:
                    for msg in controller.drain_inbox():
                        if msg.get("type") == "replace_task":
                            new_task = str(msg.get("message", ""))
                            state.user_goal = new_task
                            self._emit(event_sink, "sub_agent_task_replaced", {
                                "agent": self.name, "run_id": run_id, "task": new_task,
                            })
                        else:
                            content = str(msg.get("message", ""))
                            state.add_chat_message("user", content)
                            self._emit(event_sink, "sub_agent_message_received", {
                                "agent": self.name, "run_id": run_id, "message": content,
                            })
                images_for_step = extracted_images if extracted_images else None
                messages = self._build_messages(system_prompt, state, registry, images=images_for_step)
                if images_for_step:
                    extracted_images = []
                from src.llm.prompt_builder import count_tokens
                token_count = count_tokens(messages)
                self._emit(event_sink, "context_tokens", {"agent": self.name, "run_id": run_id, "count": token_count})
                def on_retry_error(attempt: int, max_retries: int, error_msg: str) -> None:
                    self._emit(event_sink, "sub_agent_warning", {
                        "agent": self.name, "run_id": run_id, "step": step_number,
                        "message": f"Retry {attempt}/{max_retries}: {error_msg}",
                    })

                current_step = self.client.plan_next_step(messages, on_retry_error=on_retry_error)

                llm_resp = getattr(current_step, "_llm_response", None)
                if llm_resp is not None:
                    if llm_resp.eval_count:
                        actual_tokens = llm_resp.prompt_eval_count + llm_resp.eval_count
                        self._emit(event_sink, "context_tokens", {"agent": self.name, "run_id": run_id, "count": actual_tokens})
                    if llm_resp.done_reason == "length":
                        self._emit(event_sink, "sub_agent_warning", {
                            "agent": self.name, "run_id": run_id, "step": step_number,
                            "message": f"Ответ обрезан: достигнут лимит контекста ({self.client.num_ctx} токенов). Увеличь OLLAMA_NUM_CTX.",
                        })

                if current_step.plan:
                    plan_items = [
                        PlanItem(id=item.id, content=item.content, status=item.status)
                        for item in current_step.plan
                    ]
                    state.set_plan(plan_items)
                    self._emit(event_sink, "sub_agent_plan_updated", {
                        "agent": self.name,
                        "run_id": run_id,
                        "step": step_number,
                        "plan": state.compact_plan(),
                    })
                step_dict = {k: v for k, v in asdict(current_step).items() if not k.startswith("_")}
                if llm_resp is not None and llm_resp.thinking:
                    step_dict["thought"] = llm_resp.thinking
                    step_dict["thought_source"] = "native"
                elif step_dict.get("thought"):
                    # Модель без отдельного канала reasoning — показываем её
                    # собственное поле thought из JSON-ответа как блок размышления.
                    step_dict["thought_source"] = "self"
                else:
                    step_dict.pop("thought", None)
                self._emit(event_sink, "sub_agent_step", {
                    "agent": self.name, "run_id": run_id, "step": step_number, **step_dict
                })

                # Защита от зацикливания: одно и то же действие с теми же аргументами 3 раза подряд
                action_key = (current_step.action, json.dumps(current_step.args, sort_keys=True))
                last_actions.append(action_key)
                if len(last_actions) > 3:
                    last_actions.pop(0)
                if len(last_actions) == 3 and len(set(last_actions)) == 1:
                    loop_msg = (
                        f"Зацикливание: действие '{current_step.action}' повторилось 3 раза подряд "
                        f"с одинаковыми аргументами. Используй другой инструмент или другие аргументы."
                    )
                    self._emit(event_sink, "sub_agent_warning", {
                        "agent": self.name, "run_id": run_id, "step": step_number, "message": loop_msg
                    })
                    state.add_observation(Observation(
                        step=step_number,
                        action="error",
                        result={"error": loop_msg},
                        success=False,
                    ))
                    last_actions.clear()
                    continue

                result = self._execute_step(current_step, step_number, state, event_sink, validator, run_id, policy, extracted_images, image_urls)

                if result is not None:
                    state.add_chat_message("assistant", result, plan=state.plan)
                    self._persist_memory(state)
                    final_payload = self._build_final_payload(run_id, result, step_number, state, success=True, image_urls=image_urls)
                    self._emit(event_sink, "sub_agent_finished", {
                        "agent": self.name,
                        "run_id": run_id,
                        **final_payload,
                    })
                    return final_payload

                state.consecutive_errors = 0
            except PolicyError as exc:
                policy_msg = f"Агент {self.display_name} остановлен политикой: {exc}"
                self._emit(event_sink, "sub_agent_policy_violation", {
                    "agent": self.name, "run_id": run_id, "message": str(exc), **policy.stats()
                })
                self._emit(event_sink, "sub_agent_error", {
                    "agent": self.name, "run_id": run_id, "step": step_number, "message": policy_msg
                })
                state.add_chat_message("assistant", policy_msg, plan=state.plan)
                self._persist_memory(state)
                self._emit(event_sink, "sub_agent_finished", {
                    "agent": self.name, "run_id": run_id, "result": policy_msg, "success": False
                })
                return {"run_id": run_id, "agent_name": self.name, "success": False, "result": policy_msg, "steps": step_number}
            except AgentError as exc:
                if controller is not None and controller.is_cancelled():
                    cancelled_msg = f"Агент {self.display_name} прерван"
                    state.add_chat_message("assistant", cancelled_msg, plan=state.plan)
                    self._persist_memory(state)
                    self._emit(event_sink, "sub_agent_finished", {
                        "agent": self.name, "run_id": run_id, "result": cancelled_msg, "success": False, "cancelled": True
                    })
                    return {"run_id": run_id, "agent_name": self.name, "success": False, "cancelled": True, "result": cancelled_msg, "steps": step_number}
                state.consecutive_errors += 1
                self._emit(event_sink, "sub_agent_error", {
                    "agent": self.name, "run_id": run_id, "step": step_number, "message": str(exc)
                })
                state.add_observation(Observation(
                    step=step_number,
                    action="error",
                    result={"error": str(exc)},
                    success=False,
                ))
                if state.consecutive_errors > 4:
                    error_msg = f"Агент {self.display_name} остановлен: {exc}"
                    state.add_chat_message("assistant", error_msg, plan=state.plan)
                    self._persist_memory(state)
                    self._emit(event_sink, "sub_agent_finished", {
                        "agent": self.name, "run_id": run_id, "result": error_msg, "success": False
                    })
                    return {"run_id": run_id, "agent_name": self.name, "success": False, "result": error_msg, "steps": step_number}

        # Лимит шагов
        limit_msg = f"Агент {self.display_name} достиг лимита шагов ({self.max_steps})"
        self._persist_memory(state)
        self._emit(event_sink, "sub_agent_error", {
            "agent": self.name, "run_id": run_id, "step": self.max_steps, "message": limit_msg
        })
        self._emit(event_sink, "sub_agent_finished", {
            "agent": self.name, "run_id": run_id, "result": limit_msg, "success": False
        })
        return {"run_id": run_id, "agent_name": self.name, "success": False, "result": limit_msg, "steps": self.max_steps}

    def _build_final_payload(
        self,
        run_id: str,
        summary: str,
        steps: int,
        state: SessionState,
        *,
        success: bool,
        image_urls: list[str] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "agent_name": self.name,
            "success": success,
            "status": "done" if success else "failed",
            "summary": summary,
            "steps": steps,
            "changed_files": [],
            "created_artifacts": [],
            "verification": [],
            "risks": [],
            "image_urls": list(image_urls) if image_urls else [],
        }
        for observation in reversed(state.observations):
            if observation.action != "finish_task" or not isinstance(observation.result, dict):
                continue
            finish_payload = observation.result
            status = finish_payload.get("status")
            if isinstance(status, str) and status.strip():
                payload["status"] = status.strip()
                payload["success"] = status.strip() in {"done", "finished", "completed", "success"}
            for key in ("changed_files", "created_artifacts", "verification", "risks"):
                value = finish_payload.get(key)
                if isinstance(value, list):
                    payload[key] = [str(item) for item in value if str(item).strip()]
            for key in ("needs_user_input", "question"):
                if key in finish_payload:
                    payload[key] = finish_payload[key]
            break
        return payload

    def _build_messages(self, system_prompt: str, state: SessionState, registry: ToolRegistry, images: list[str] | None = None) -> list[dict[str, object]]:
        user_payload = {
            "goal": state.user_goal,
            "persistent_memory": state.compact_memory(),
            "chat_history": state.compact_chat_history(),
            "current_plan": state.compact_plan(),
            "tools": registry.describe_all(),
            "recent_observations": state.compact_observations(),
        }
        user_message: dict[str, object] = {
            "role": "user",
            "content": json.dumps(user_payload, ensure_ascii=False, indent=2),
        }
        if images:
            user_message["images"] = images
        return [
            {"role": "system", "content": system_prompt},
            user_message,
        ]

    def _execute_step(
        self,
        step: ActionStep,
        step_number: int,
        state: SessionState,
        event_sink: Callable[[str, object], None] | None,
        validator: ActionValidator,
        run_id: str,
        run_policy: RunPolicy | None = None,
        extracted_images: list[str] | None = None,
        image_urls: list[str] | None = None,
    ) -> str | None:
        tool = validator.validate(step)
        self.policy.enforce(step, tool)
        if run_policy is not None:
            run_policy.enforce_tool(tool)
            run_policy.tick_tool_call()

        handler_args = dict(step.args)
        if step.summary and "summary" not in handler_args:
            handler_args["summary"] = step.summary
        handler_args["__run_id__"] = run_id
        if event_sink is not None:
            handler_args["__event_sink__"] = lambda event, payload: self._emit(event_sink, event, {"agent": self.name, "run_id": run_id, **payload})

        try:
            result = tool.handler(handler_args)
        except AgentError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Сбой инструмента {tool.name}: {exc}") from exc

        # Инструмент мог вернуть ошибку словарём вместо исключения — не выдаём это
        # за успешный шаг, иначе ошибка не видна ни агенту, ни на странице саб-агента.
        success = not result_indicates_failure(result)

        # Инструмент может вернуть изображение (_type=="image", конвенция screen_tools/
        # telegram_tools) — извлекаем base64 в extracted_images для СЛЕДУЮЩЕГО шага LLM,
        # иначе саб-агент физически не может "увидеть" картинку. В наблюдение и память
        # кладём результат БЕЗ base64 (redacted), чтобы не раздувать chat_history/JSON.
        # Дополнительно сохраняем картинку как артефакт и копим её URL в image_urls —
        # это то, что finish_task(attach_images=true) встроит в итоговый ответ, и что
        # получит оператор через результат delegate_task для передачи пользователю.
        observation_result = result
        if isinstance(result, dict) and result.get("_type") == "image" and isinstance(result.get("image"), str):
            if extracted_images is not None:
                extracted_images.append(result["image"])
            image_url = None
            if self.server_context is not None:
                from src.infra.image_artifacts import save_image_artifact
                image_url = save_image_artifact(
                    self.server_context, run_id, result["image"], str(result.get("format", "image/png"))
                )
                if image_url and image_urls is not None:
                    image_urls.append(image_url)
            observation_result = dict(result)
            observation_result.pop("image", None)
            observation_result["image_attached"] = True
            if image_url:
                observation_result["image_url"] = image_url

        observation = Observation(
            step=step_number, action=tool.name, result=observation_result,
            success=success, thought=step.thought
        )
        state.add_observation(observation)
        self._emit(event_sink, "sub_agent_tool_result", {"agent": self.name, "run_id": run_id, **asdict(observation)})
        if not success and tool.name != "finish_task":
            error_text = ""
            if isinstance(result, dict):
                error_text = str(result.get("error") or "").strip()
            self._emit(event_sink, "sub_agent_warning", {
                "agent": self.name, "run_id": run_id, "step": step_number,
                "message": f"Инструмент {tool.name} вернул ошибку: {error_text or 'см. результат'}",
            })

        # Обновляем статус задач в плане после успешного выполнения шага
        if success and state.plan and step_number <= len(state.plan):
            updated_plan = []
            for i, item in enumerate(state.plan):
                if i < step_number:
                    # Предыдущие задачи - выполнены
                    updated_plan.append(PlanItem(id=item.id, content=item.content, status="completed"))
                elif i == step_number - 1:
                    # Текущая задача - в работе (только что выполнена)
                    updated_plan.append(PlanItem(id=item.id, content=item.content, status="completed"))
                else:
                    # Следующие задачи - в ожидании
                    updated_plan.append(PlanItem(id=item.id, content=item.content, status="pending"))
            state.set_plan(updated_plan)
            self._emit(event_sink, "sub_agent_plan_updated", {
                "agent": self.name,
                "run_id": run_id,
                "step": step_number,
                "plan": state.compact_plan(),
            })

        if tool.name == "finish_task" or step.done:
            summary = str(result.get("summary") or step.summary or "Задача завершена")
            if tool.name == "finish_task" and result.get("attach_images") and image_urls:
                summary = summary.rstrip() + "\n\n" + "\n".join(f"![image]({url})" for url in image_urls)
            return summary
        return None

    def _emit(self, event_sink: Callable[[str, object], None] | None, event: str, payload: dict[str, Any]) -> None:
        if event_sink is not None:
            event_sink(event, payload)

    def describe(self) -> dict[str, str]:
        return {
            "name": self.name,
            "display_name": self.display_name,
            "description": self._get_description(),
        }

    def _get_description(self) -> str:
        """Извлекает краткое описание из промпта (первая строка после заголовка)."""
        try:
            content = self._load_prompt()
            lines = [line.strip() for line in content.split("\n") if line.strip()]
            for line in lines:
                if not line.startswith("#"):
                    return line[:200]
        except Exception:
            pass
        return f"Специализированный агент: {self.display_name}"
