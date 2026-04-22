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
    ) -> None:
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

    def cancel(self) -> None:
        self.cancelled = True

    def run(self, user_goal: str, chat_history: list[dict[str, str]] | None = None, images: list[str] | None = None) -> str:
        state = SessionState(user_goal=user_goal)
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
        self.logger.write("session_started", {"goal": user_goal})
        self._emit("session_started", {"goal": user_goal})
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
                messages, token_count = build_messages(state, self.registry.describe_all(), self.workspace_root, self.user_name, self.available_agents, images=images if step_number == 1 else None)
                self._emit("context_tokens", {"count": token_count})
                streamed_text = ""
                last_thought = ""

                def on_stream_content(raw_content: str) -> None:
                    nonlocal streamed_text, last_thought
                    # Стримим thought сразу как он появляется
                    partial_thought = self._extract_partial_json_string_field(raw_content, "thought")
                    if partial_thought and partial_thought != last_thought:
                        last_thought = partial_thought
                        self._emit("thought_stream", {"thought": partial_thought})
                    action = self._extract_complete_json_string_field(raw_content, "action")
                    if action != "finish_task":
                        return
                    # summary лежит внутри args.summary
                    args_match = re.search(r'"args"\s*:\s*\{[^}]*"summary"\s*:\s*"((?:\\.|[^"\\])*)', raw_content, re.DOTALL)
                    summary = self._decode_json_string_fragment(args_match.group(1)) if args_match else None
                    if not summary or summary == streamed_text:
                        return
                    streamed_text = summary
                    self._emit("assistant_stream", {"content": summary})

                current_step = self.client.plan_next_step(messages, on_stream_content=on_stream_content)
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
                self.logger.write("llm_step", asdict(current_step))
                self._emit("llm_step", {"step": step_number, **asdict(current_step)})
                summary = self._execute_step(current_step, step_number, state)
                if summary is not None:
                    state.add_chat_message(
                        "assistant",
                        summary,
                        thought=current_step.thought,
                        plan=state.plan,
                    )
                    self.memory_store.append_session(state.chat_history, state.observations)
                    self.logger.write("session_finished", {"summary": summary})
                    self._emit("session_finished", {"summary": summary})
                    return summary
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
