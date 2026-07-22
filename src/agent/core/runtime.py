from __future__ import annotations

import json
import re
import threading
from dataclasses import asdict
from typing import Any, Callable
from uuid import uuid4

from src.agent.core.schemas import ActionStep
from src.agent.core.state import ChatMessage, Observation, PlanItem, SessionState
from src.agent.messaging.events import normalize_event
from src.infra.chat_memory import ChatMemoryStore
from src.infra.errors import AgentError, ToolExecutionError
from src.infra.logging import SessionLogger
from src.llm.client_factory import LLMClient
from src.llm.prompt_builder import build_messages
from src.safety.policy import SafetyPolicy
from src.safety.validator import ActionValidator
from src.tools.core.registry import ToolRegistry, result_indicates_failure


class AgentRuntime:
    def __init__(
        self,
        client: LLMClient,
        registry: ToolRegistry,
        validator: ActionValidator,
        policy: SafetyPolicy,
        logger: SessionLogger,
        memory_store: ChatMemoryStore,
        confirm: Callable[[str], bool],
        max_steps: int,
        max_consecutive_errors: int,
        workspace_root: str,
        event_sink: Callable[[str, object], None] | None = None,
        user_name: str = "Пользователь",
        available_agents: list[dict[str, str]] | None = None,
        get_active_runs: Callable[[], list[dict[str, Any]]] | None = None,
        get_supervisor_observations: Callable[[], list[dict[str, Any]]] | None = None,
        settings: Any | None = None,
        server_context: Any | None = None,
    ) -> None:
        from src.infra.config import Settings
        self.client = client
        # Нужен для сохранения картинок инструментов как артефактов (см.
        # src.infra.image_artifacts), чтобы оператор мог встроить их в текст
        # ответа пользователю через finish_task(attach_images=true).
        self.server_context = server_context
        self.registry = registry
        self.validator = validator
        self.policy = policy
        self.logger = logger
        self.memory_store = memory_store
        self.user_name = user_name
        self.available_agents = available_agents or []
        self.confirm = confirm
        self.workspace_root = workspace_root
        self.max_steps = max_steps
        self.max_consecutive_errors = max_consecutive_errors
        self.event_sink = event_sink
        self.cancelled = False
        self.get_active_runs = get_active_runs
        self.get_supervisor_observations = get_supervisor_observations
        self._current_state: SessionState | None = None
        self._base_history: list[dict[str, Any]] = []
        # Очистка истории может прийти в коротком окне после session_finished,
        # пока поток runtime ещё дописывает финальный снимок. Один lock для
        # смены базы и записи снимка не даёт старому запуску воскресить чат.
        self._memory_lock = threading.RLock()
        self._memory_epoch = 0
        self._preferred_agents: list[str] = []
        self.settings = settings

    def cancel(self) -> None:
        self.cancelled = True
        self._persist_interrupted_snapshot()
        try:
            self.client.cancel_active_request()
        except Exception:
            pass

    def clear_persisted_history(self) -> None:
        """Атомарно очищает память, используемую текущим запуском.

        Недостаточно очистить только файл: между ``memory_store.clear()`` и
        сбросом ``_base_history`` runtime может успеть записать снапшот со
        старым префиксом. Этот метод сериализует оба действия с записью
        снапшотов и также убирает прошлый контекст из уже идущего запуска.
        """
        with self._memory_lock:
            self._memory_epoch += 1
            self._base_history = []
            if self._current_state is not None:
                self._current_state.memory_chat_history.clear()
            self.memory_store.clear()

    def run(
        self,
        user_goal: str,
        chat_history: list[dict[str, str]] | None = None,
        images: list[str] | None = None,
        preferred_agents: list[str] | None = None,
    ) -> str:
        self.cancelled = False
        # Валидируем на входе, а не в промпт-билдере: имена, которых нет среди
        # реально доступных сабагентов, не должны попадать в подсказку модели.
        self._preferred_agents = self._filter_preferred_agents(preferred_agents, self.available_agents)
        try:
            self.client.reset_cancel_request()
        except Exception:
            pass
        state = SessionState(user_goal=user_goal)
        self._current_state = state
        current_step: ActionStep | None = None
        extracted_images: list[str] = images or []
        # Все картинки, увиденные оператором за эту сессию — свои (например
        # take_screenshot в pc_control_mode) и полученные от делегированных
        # саб-агентов через delegate_task — для finish_task(attach_images=true).
        image_urls: list[str] = []
        # Стабильный run_id для сохранения артефактов-картинок оператора (у
        # оператора нет собственного run_id, в отличие от делегированных run).
        operator_run_id = str(uuid4())
        # Запоминаем поколение до чтения: ручная очистка, случившаяся между
        # чтением файла и первым снапшотом, не должна вернуть старый контекст
        # ни в prompt, ни на диск.
        with self._memory_lock:
            memory_epoch = self._memory_epoch
        memory = self.memory_store.load()
        with self._memory_lock:
            if memory_epoch == self._memory_epoch:
                for item in memory.get("chat_history", []):
                    role = item.get("role")
                    content = item.get("content")
                    thought = item.get("thought")
                    raw_plan = item.get("plan")
                    interrupted_by_user = bool(item.get("interrupted_by_user"))
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
                        state.memory_chat_history.append(
                            ChatMessage(
                                role=role,
                                content=content,
                                thought=thought if isinstance(thought, str) else None,
                                plan=plan_items,
                                interrupted_by_user=interrupted_by_user,
                            )
                        )
                        if role == "assistant" and plan_items:
                            state.set_plan(plan_items)
        if chat_history:
            for item in chat_history:
                role = item.get("role")
                content = item.get("content")
                if isinstance(role, str) and isinstance(content, str):
                    state.chat_history.append(ChatMessage(role=role, content=content))
        state.add_chat_message("user", user_goal)
        with self._memory_lock:
            if memory_epoch == self._memory_epoch:
                self._base_history = self.memory_store.load().get("chat_history", [])
            else:
                self._base_history = []
        self._write_memory_snapshot(state.chat_history, state.observations)
        self.logger.write("session_started", {"goal": user_goal})
        self._emit("session_started", {"goal": user_goal})
        last_actions: list[tuple[str, str]] = []  # для loop detection оператора
        for step_number in range(1, self.max_steps + 1):
            streamed_text = ""
            # Если finish_task уже был вызван — принудительно завершаем
            for obs in reversed(state.observations):
                if obs.action == "finish_task" and obs.success:
                    final = str(obs.result.get("summary") or "Задача завершена")
                    self._emit("session_finished", {"summary": final})
                    return final
            if self.cancelled:
                self.logger.write("cancelled", {"step": step_number})
                self._add_assistant_message_once(state, "", interrupted_by_user=True)
                self._write_memory_snapshot(state.chat_history, state.observations)
                self._emit("cancelled", {"step": step_number})
                return ""
            try:
                active_runs = self.get_active_runs() if self.get_active_runs else []
                supervisor_obs = self.get_supervisor_observations() if self.get_supervisor_observations else []
                images_for_step = extracted_images if extracted_images else None
                messages, token_count = build_messages(state, self.registry.describe_all(), self.workspace_root, self.user_name, self.available_agents, images=images_for_step, active_runs=active_runs, supervisor_observations=supervisor_obs, user_profile=self.settings.user_profile, preferred_agents=self._preferred_agents)
                if images_for_step:
                    extracted_images = []
                self._emit("context_tokens", {"count": token_count})
                streamed_text = ""

                def on_stream_content(raw_content: str) -> None:
                    nonlocal streamed_text
                    action = self._extract_complete_json_string_field(raw_content, "action")
                    if action != "finish_task":
                        return
                    # summary может приходить частями, поэтому читаем и частичный фрагмент
                    summary = self._extract_partial_json_string_field(raw_content, "summary")
                    if not summary or summary == streamed_text:
                        return
                    streamed_text = summary
                    state.live_answer = summary
                    live_chat_history = [
                        *state.chat_history,
                        ChatMessage(role="assistant", content=summary, plan=state.plan),
                    ]
                    self._write_memory_snapshot(
                        live_chat_history, state.observations, self.client.model
                    )
                    self._emit("assistant_stream", {"content": summary})

                def on_thinking(thinking_text: str) -> None:
                    self._emit("thought_stream", {"thought": thinking_text, "source": "native"})

                def on_retry_error(attempt: int, max_retries: int, error_msg: str) -> None:
                    self._emit("agent_warning", {
                        "step": step_number,
                        "message": f"Retry {attempt}/{max_retries}: {error_msg}",
                    })

                current_step = self.client.plan_next_step(
                    messages,
                    on_stream_content=on_stream_content,
                    on_thinking=on_thinking,
                    on_retry_error=on_retry_error,
                )

                # Используем точные токены из ответа модели если доступны
                llm_resp = getattr(current_step, "_llm_response", None)
                if llm_resp is not None:
                    if llm_resp.eval_count:
                        actual_tokens = llm_resp.prompt_eval_count + llm_resp.eval_count
                        self._emit("context_tokens", {"count": actual_tokens})
                    if llm_resp.done_reason == "length":
                        self._emit("agent_error", {
                            "step": step_number,
                            "message": f"Ответ обрезан: достигнут лимит контекста ({self.client.num_ctx} токенов). Увеличь OLLAMA_NUM_CTX.",
                        })

                native_thought = llm_resp.thinking if llm_resp is not None else None

                if current_step.plan:
                    plan_items = [
                        PlanItem(id=item.id, content=item.content, status=item.status)
                        for item in current_step.plan
                    ]
                    state.set_plan(plan_items)
                    self._emit("plan_updated", {
                        "plan": state.compact_plan(),
                        "step": step_number,
                    })
                step_dict = {k: v for k, v in asdict(current_step).items() if not k.startswith("_")}
                if native_thought:
                    step_dict["thought"] = native_thought
                    step_dict["thought_source"] = "native"
                elif step_dict.get("thought"):
                    # Модель без отдельного канала reasoning (нет native_thought) —
                    # показываем её собственное поле thought из JSON-ответа как блок
                    # размышления, вместо того чтобы молча его выбрасывать.
                    step_dict["thought_source"] = "self"
                else:
                    step_dict.pop("thought", None)
                self.logger.write("llm_step", step_dict)
                self._emit("llm_step", {"step": step_number, **step_dict})

                # Loop detection: одно и то же действие 3 раза подряд — предупреждение модели
                action_key = (current_step.action, json.dumps(current_step.args, sort_keys=True, default=str))
                last_actions.append(action_key)
                if len(last_actions) > 4:
                    last_actions.pop(0)
                if len(last_actions) >= 3 and len(set(last_actions[-3:])) == 1:
                    loop_msg = (
                        f"Зацикливание оператора: действие '{current_step.action}' повторилось 3 раза подряд. "
                        f"Используй другой инструмент, другие аргументы или заверши задачу через finish_task."
                    )
                    self.logger.write("loop_detected", {"step": step_number, "action": current_step.action})
                    self._emit("loop_detected", {"step": step_number, "action": current_step.action, "message": loop_msg})
                    state.add_observation(Observation(
                        step=step_number,
                        action="error",
                        result={"error": loop_msg},
                        success=False,
                        thought=current_step.thought,
                    ))
                    last_actions.clear()
                    current_step = None
                    continue

                summary = self._execute_step(current_step, step_number, state, extracted_images, image_urls, operator_run_id)
                if summary is not None:
                    state.live_answer = ""
                    self._add_assistant_message_once(
                        state,
                        summary,
                        thought=native_thought or current_step.thought,
                    )
                    self._write_memory_snapshot(state.chat_history, state.observations)
                    self.logger.write("session_finished", {"summary": summary})
                    self._emit("session_finished", {"summary": summary})
                    return summary
                self._write_memory_snapshot(state.chat_history, state.observations)
                state.consecutive_errors = 0
                current_step = None
            except AgentError as exc:
                state.consecutive_errors += 1
                self.logger.write("agent_error", {"step": step_number, "message": str(exc)})
                partial_answer = streamed_text.strip()
                if self.cancelled:
                    self._add_assistant_message_once(
                        state,
                        partial_answer,
                        thought=current_step.thought if current_step else None,
                        interrupted_by_user=True,
                    )
                state.live_answer = ""
                if self.cancelled:
                    self._write_memory_snapshot(state.chat_history, state.observations)
                    self.logger.write("cancelled", {"step": step_number})
                    self._emit("cancelled", {"step": step_number, "summary": partial_answer})
                    return partial_answer
                self._emit("agent_error", {"step": step_number, "message": str(exc)})
                state.add_observation(
                    Observation(
                        step=step_number,
                        action="error",
                        result={"error": str(exc)},
                        success=False,
                        thought=current_step.thought if current_step else None,
                    )
                )
                self._write_memory_snapshot(state.chat_history, state.observations)
                if state.consecutive_errors > self.max_consecutive_errors:
                    summary = f"Сессия остановлена после повторяющихся ошибок: {exc}"
                    state.live_answer = ""
                    self._add_assistant_message_once(
                        state,
                        summary,
                        thought=current_step.thought if current_step else None,
                    )
                    self._write_memory_snapshot(state.chat_history, state.observations)
                    self._emit("session_finished", {"summary": summary})
                    return summary
                current_step = None
        summary = "Сессия остановлена: достигнут лимит шагов"
        state.live_answer = ""
        self._add_assistant_message_once(state, summary)
        self._write_memory_snapshot(state.chat_history, state.observations)
        self._emit("session_finished", {"summary": summary})
        return summary

    def _add_assistant_message_once(
        self,
        state: SessionState,
        content: str,
        thought: str | None = None,
        interrupted_by_user: bool = False,
    ) -> None:
        if state.chat_history:
            last_message = state.chat_history[-1]
            if last_message.role == "assistant" and last_message.content.strip() == content.strip():
                if thought and not last_message.thought:
                    last_message.thought = thought
                if state.plan and not last_message.plan:
                    last_message.plan = list(state.plan)
                if interrupted_by_user:
                    last_message.interrupted_by_user = True
                return
        state.add_chat_message(
            "assistant",
            content,
            thought=thought,
            plan=state.plan,
            interrupted_by_user=interrupted_by_user,
        )

    def _persist_interrupted_snapshot(self) -> None:
        state = self._current_state
        if state is None:
            return
        try:
            live_answer = state.live_answer.strip()
            if live_answer:
                live_chat_history = [
                    *state.chat_history,
                    ChatMessage(
                        role="assistant",
                        content=live_answer,
                        plan=state.plan,
                        interrupted_by_user=True,
                    ),
                ]
            else:
                live_chat_history = list(state.chat_history)
                if not live_chat_history or live_chat_history[-1].role != "assistant":
                    live_chat_history.append(
                        ChatMessage(role="assistant", content="", interrupted_by_user=True)
                    )
                else:
                    live_chat_history[-1].interrupted_by_user = True
            self._write_memory_snapshot(
                live_chat_history, state.observations, self.client.model
            )
        except Exception:
            pass

    def _write_memory_snapshot(
        self,
        chat_history: list[ChatMessage],
        observations: list[Observation],
        model: str | None = None,
    ) -> bool:
        try:
            with self._memory_lock:
                self.memory_store.write_snapshot(
                    list(self._base_history), chat_history, observations, model
                )
            return True
        except Exception as exc:
            try:
                self.logger.write("memory_snapshot_error", {"error": str(exc)})
            except Exception:
                pass
            return False

    def _execute_step(
        self,
        step: ActionStep,
        step_number: int,
        state: SessionState,
        extracted_images: list[str],
        image_urls: list[str],
        operator_run_id: str,
    ) -> str | None:
        tool = self.validator.validate(step)
        self.policy.enforce(step, tool)
        if tool.risk_level >= 2:
            confirmation_message = f"Подтвердить действие {tool.name} с аргументами {step.args}? [y/N]: "
            self._emit(
                "confirmation_requested",
                {"step": step_number, "tool": tool.name, "args": step.args, "message": confirmation_message},
            )
            approved = self.confirm(confirmation_message)
            self._emit("confirmation_result", {"step": step_number, "tool": tool.name, "approved": approved})
            if not approved:
                observation = Observation(step=step_number, action=tool.name, result={"approved": False}, success=False, thought=step.thought)
                state.add_observation(observation)
                self.logger.write("tool_result", asdict(observation))
                self._emit("tool_result", asdict(observation))
                return "Действие отменено пользователем"
        handler_args = dict(step.args)
        if step.summary and "summary" not in handler_args:
            handler_args["summary"] = step.summary
        try:
            result = tool.handler(handler_args)
        except AgentError:
            raise
        except Exception as exc:
            raise ToolExecutionError(f"Сбой инструмента {tool.name}: {exc}") from exc

        observation_result = result
        if isinstance(result, dict) and result.get("_type") == "image" and isinstance(result.get("image"), str):
            extracted_images.append(result["image"])
            image_url = None
            if self.server_context is not None:
                from src.infra.image_artifacts import save_image_artifact
                image_url = save_image_artifact(
                    self.server_context, operator_run_id, result["image"], str(result.get("format", "image/png"))
                )
                if image_url:
                    image_urls.append(image_url)
            observation_result = dict(result)
            observation_result.pop("image", None)
            observation_result["image_attached"] = True
            if image_url:
                observation_result["image_url"] = image_url

        # Делегированный саб-агент мог сам увидеть/скачать картинки (например
        # read_chat_image у telegram) — их URL приходят в результате delegate_task/
        # delegate_parallel. Подхватываем в свой накопитель, чтобы оператор мог
        # переслать их пользователю через finish_task(attach_images=true).
        if tool.name in ("delegate_task", "delegate_parallel") and isinstance(result, dict):
            for url in self._extract_delegated_image_urls(result):
                if url not in image_urls:
                    image_urls.append(url)

        # finish_task всегда считается успешным завершением; для остальных
        # инструментов распознаём ошибку, возвращённую словарём (в т.ч. проваленное
        # делегирование), чтобы она не выдавалась за успешный шаг.
        success = tool.name == "finish_task" or not result_indicates_failure(result)
        observation = Observation(step=step_number, action=tool.name, result=observation_result, success=success, thought=step.thought)
        state.add_observation(observation)
        self.logger.write("tool_result", asdict(observation))
        self._emit("tool_result", asdict(observation))

        if tool.name == "finish_task" or step.done:
            summary = str(result.get("summary") or step.summary or "Задача завершена")
            if tool.name == "finish_task" and result.get("attach_images") and image_urls:
                summary = summary.rstrip() + "\n\n" + "\n".join(f"![image]({url})" for url in image_urls)
            return summary
        return None

    @staticmethod
    def _extract_delegated_image_urls(result: dict[str, Any]) -> list[str]:
        """Достаёт image_urls из compact-результата delegate_task (плоский словарь)
        или delegate_parallel (список результатов в result['results'])."""
        urls: list[str] = []
        direct = result.get("image_urls")
        if isinstance(direct, list):
            urls.extend(str(u) for u in direct if isinstance(u, str) and u.strip())
        nested = result.get("results")
        if isinstance(nested, list):
            for item in nested:
                if isinstance(item, dict):
                    item_urls = item.get("image_urls")
                    if isinstance(item_urls, list):
                        urls.extend(str(u) for u in item_urls if isinstance(u, str) and u.strip())
        return urls

    @staticmethod
    def _filter_preferred_agents(
        preferred_agents: list[str] | None,
        available_agents: list[dict[str, str]],
    ) -> list[str]:
        """Оставляет только реально доступные имена сабагентов из
        preferred_agents (сессионная подсказка от пользователя из UI) — имя,
        которого нет среди available_agents, не должно попасть в промпт модели."""
        if not preferred_agents:
            return []
        available_names = {str(agent.get("name", "")) for agent in available_agents}
        return [name for name in preferred_agents if name in available_names]

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self.event_sink is not None:
            normalized = normalize_event(event, payload)
            self.event_sink(normalized.event, normalized.payload)

    def _extract_complete_json_string_field(self, raw_content: str, field_name: str) -> str | None:
        match = re.search(
            rf'"{re.escape(field_name)}"\s*:\s*"((?:\\.|[^"\\])*)"',
            raw_content,
            re.DOTALL,
        )
        if not match:
            return None
        return self._decode_json_string_fragment(match.group(1))

    def _extract_partial_json_string_field(self, raw_content: str, field_name: str) -> str | None:
        match = re.search(
            rf'"{re.escape(field_name)}"\s*:\s*"((?:\\.|[^"\\])*)',
            raw_content,
            re.DOTALL,
        )
        if not match:
            return None
        return self._decode_json_string_fragment(match.group(1))

    def _decode_json_string_fragment(self, value: str) -> str:
        cleaned = value
        if cleaned.endswith("\\"):
            cleaned = cleaned[:-1]
        try:
            return json.loads(f'"{cleaned}"')
        except json.JSONDecodeError:
            return (
                cleaned.replace("\\n", "\n")
                .replace("\\r", "\r")
                .replace("\\t", "\t")
                .replace('\\"', '"')
                .replace("\\\\", "\\")
            )
