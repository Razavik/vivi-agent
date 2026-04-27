from __future__ import annotations

import json
import re
from dataclasses import asdict
from typing import Any, Callable

from src.agent.schemas import ActionStep
from src.agent.state import ChatMessage, Observation, PlanItem, SessionState
from src.infra.chat_memory import ChatMemoryStore
from src.infra.errors import AgentError, ToolExecutionError
from src.infra.logging import SessionLogger
from src.llm.ollama_client import OllamaClient
from src.llm.prompt_builder import build_messages
from src.safety.policy import SafetyPolicy
from src.safety.validator import ActionValidator
from src.tools.registry import ToolRegistry


class AgentRuntime:
    def __init__(
        self,
        client: OllamaClient,
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
    ) -> None:
        from src.infra.config import Settings
        self.client = client
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
        self.settings = settings

    def cancel(self) -> None:
        self.cancelled = True

    def run(self, user_goal: str, chat_history: list[dict[str, str]] | None = None, images: list[str] | None = None) -> str:
        state = SessionState(user_goal=user_goal)
        self._current_state = state
        current_step: ActionStep | None = None
        memory = self.memory_store.load()
        for item in memory.get("chat_history", []):
            role = item.get("role")
            content = item.get("content")
            thought = item.get("thought")
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
                state.memory_chat_history.append(
                    ChatMessage(
                        role=role,
                        content=content,
                        thought=thought if isinstance(thought, str) else None,
                        plan=plan_items,
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
        base_history: list[dict] = self.memory_store.load().get("chat_history", [])
        self.logger.write("session_started", {"goal": user_goal})
        self._emit("session_started", {"goal": user_goal})
        last_actions: list[tuple[str, str]] = []  # для loop detection директора
        for step_number in range(1, self.max_steps + 1):
            # Если finish_task уже был вызван — принудительно завершаем
            for obs in reversed(state.observations):
                if obs.action == "finish_task" and obs.success:
                    final = str(obs.result.get("summary") or "Задача завершена")
                    self._emit("session_finished", {"summary": final})
                    return final
            if self.cancelled:
                self.logger.write("cancelled", {"step": step_number})
                self._emit("cancelled", {"step": step_number})
                raise AgentError("Задача была прервана пользователем")
            try:
                active_runs = self.get_active_runs() if self.get_active_runs else []
                supervisor_obs = self.get_supervisor_observations() if self.get_supervisor_observations else []
                messages, token_count = build_messages(state, self.registry.describe_all(), self.workspace_root, self.user_name, self.available_agents, images=images if step_number == 1 else None, active_runs=active_runs, supervisor_observations=supervisor_obs, user_profile=self.settings.user_profile)
                self._emit("context_tokens", {"count": token_count})
                streamed_text = ""

                def on_stream_content(raw_content: str) -> None:
                    nonlocal streamed_text
                    action = self._extract_complete_json_string_field(raw_content, "action")
                    if action != "finish_task":
                        return
                    # summary лежит внутри args.summary
                    args_match = re.search(r'"args"\s*:\s*\{.*?"summary"\s*:\s*"((?:\\.|[^"\\])*)', raw_content, re.DOTALL)
                    summary = self._decode_json_string_fragment(args_match.group(1)) if args_match else None
                    if not summary or summary == streamed_text:
                        return
                    streamed_text = summary
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
                        f"Зацикливание директора: действие '{current_step.action}' повторилось 3 раза подряд. "
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

                summary = self._execute_step(current_step, step_number, state)
                if summary is not None:
                    state.add_chat_message(
                        "assistant",
                        summary,
                        thought=native_thought or current_step.thought,
                        plan=state.plan,
                    )
                    self.memory_store.append_session(state.chat_history, state.observations)
                    self.logger.write("session_finished", {"summary": summary})
                    self._emit("session_finished", {"summary": summary})
                    return summary
                self.memory_store.write_snapshot(base_history, state.chat_history, state.observations)
                state.consecutive_errors = 0
                current_step = None
            except AgentError as exc:
                state.consecutive_errors += 1
                self.logger.write("agent_error", {"step": step_number, "message": str(exc)})
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
                self.memory_store.write_snapshot(base_history, state.chat_history, state.observations)
                if state.consecutive_errors > self.max_consecutive_errors:
                    summary = f"Сессия остановлена после повторяющихся ошибок: {exc}"
                    state.add_chat_message(
                        "assistant",
                        summary,
                        thought=current_step.thought if current_step else None,
                        plan=state.plan,
                    )
                    self.memory_store.append_session(state.chat_history, state.observations)
                    self._emit("session_finished", {"summary": summary})
                    return summary
                current_step = None
        summary = "Сессия остановлена: достигнут лимит шагов"
        state.add_chat_message("assistant", summary, plan=state.plan)
        self.memory_store.append_session(state.chat_history, state.observations)
        self._emit("session_finished", {"summary": summary})
        return summary

    def _execute_step(self, step: ActionStep, step_number: int, state: SessionState) -> str | None:
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
        observation = Observation(step=step_number, action=tool.name, result=result, success=True, thought=step.thought)
        state.add_observation(observation)
        self.logger.write("tool_result", asdict(observation))
        self._emit("tool_result", asdict(observation))

        if tool.name == "send_message":
            msg_text = str(result.get("message") or "")
            if msg_text:
                state.add_chat_message("assistant", msg_text, thought=step.thought)
                self._emit("intermediate_message", {"role": "assistant", "content": msg_text, "thought": step.thought})

        if tool.name == "finish_task" or step.done:
            return str(result.get("summary") or step.summary or "Задача завершена")
        return None

    def _emit(self, event: str, payload: dict[str, Any]) -> None:
        if self.event_sink is not None:
            self.event_sink(event, payload)

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
