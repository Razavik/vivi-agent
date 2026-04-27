from __future__ import annotations

import json
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any, Callable

from src.agent.run_control import RunController
from src.agent.schemas import ActionStep
from src.agent.state import ChatMessage, Observation, PlanItem, SessionState
from src.infra.chat_memory import ChatMemoryStore
from src.infra.errors import AgentError, PolicyError, ToolExecutionError
from src.llm.ollama_client import OllamaClient
from src.safety.policy import SafetyPolicy
from src.safety.run_policy import RunPolicy
from src.safety.validator import ActionValidator
from src.tools.confirmation_tools import finish_task
from src.tools.registry import ToolRegistry, ToolSpec


class SubAgent:
    """Специализированный агент с собственным LLM-циклом, промптом, памятью и инструментами."""

    def __init__(
        self,
        name: str,
        display_name: str,
        prompt_path: str,
        tools: list,  # list[ToolSpec]
        client: OllamaClient,
        memory_store: ChatMemoryStore,
        max_steps: int = 50,
        user_name: str = "Пользователь",
    ) -> None:
        self.name = name
        self.display_name = display_name
        self.prompt_path = prompt_path
        self.tools = tools
        self.client = client
        self.memory_store = memory_store
        self.max_steps = max_steps
        self.user_name = user_name

        # Реестр собственных инструментов (без ask_director — добавляется при run())
        self._base_tools = list(tools)

        self.validator: ActionValidator | None = None
        self.policy = SafetyPolicy()

    def _build_registry(self, ask_director: Callable[[str], str] | None) -> ToolRegistry:
        """Собирает реестр инструментов с опциональным ask_director."""
        registry = ToolRegistry()
        for spec in self._base_tools:
            registry.register(spec)
        registry.register(ToolSpec(
            "finish_task",
            "Завершить задачу и вернуть структурированный результат",
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
            },
        ))
        if ask_director is not None:
            def _ask_director_handler(args: dict[str, Any]) -> dict[str, Any]:
                question = str(args.get("question", ""))
                if not question:
                    raise ToolExecutionError("Параметр question обязателен")
                answer = ask_director(question)
                return {"answer": answer}
            registry.register(ToolSpec(
                "ask_director",
                "Задать вопрос директору, если нужна уточняющая информация для выполнения задачи",
                0,
                _ask_director_handler,
                {"question": "str"},
            ))
        return registry

    def _load_prompt(self) -> str:
        path = Path(self.prompt_path)
        if not path.is_absolute():
            path = Path(__file__).resolve().parents[2] / self.prompt_path
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
        ask_director: Callable[[str], str] | None = None,
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

        wrapped_ask_director: Callable[[str], str] | None = None
        if ask_director is not None:
            def _wrapped_ask_director(question: str) -> str:
                self._emit(event_sink, "sub_agent_question", {
                    "agent": self.name,
                    "run_id": run_id,
                    "question": question,
                })
                answer = ask_director(question)
                self._emit(event_sink, "sub_agent_answer", {
                    "agent": self.name,
                    "run_id": run_id,
                    "question": question,
                    "answer": answer,
                })
                return answer

            wrapped_ask_director = _wrapped_ask_director

        registry = self._build_registry(wrapped_ask_director)
        validator = ActionValidator(registry)

        system_prompt = self._load_prompt()
        system_prompt = system_prompt.replace("{user_name}", self.user_name)

        last_actions: list[tuple[str, str]] = []  # (action, args_repr)
        policy = run_policy or RunPolicy()  # по умолчанию — standard без квот

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
                messages = self._build_messages(system_prompt, state, registry, images=images if step_number == 1 else None)
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

                result = self._execute_step(current_step, step_number, state, event_sink, validator, run_id, policy)

                if result is not None:
                    state.add_chat_message("assistant", result, plan=state.plan)
                    self.memory_store.append_session(state.chat_history, state.observations, self.client.model)
                    final_payload = self._build_final_payload(run_id, result, step_number, state, success=True)
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
                state.add_chat_message("assistant", policy_msg, plan=state.plan)
                self.memory_store.append_session(state.chat_history, state.observations, self.client.model)
                self._emit(event_sink, "sub_agent_finished", {
                    "agent": self.name, "run_id": run_id, "result": policy_msg, "success": False
                })
                return {"run_id": run_id, "agent_name": self.name, "success": False, "result": policy_msg, "steps": step_number}
            except AgentError as exc:
                if controller is not None and controller.is_cancelled():
                    cancelled_msg = f"Агент {self.display_name} прерван"
                    state.add_chat_message("assistant", cancelled_msg, plan=state.plan)
                    self.memory_store.append_session(state.chat_history, state.observations, self.client.model)
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
                    self.memory_store.append_session(state.chat_history, state.observations, self.client.model)
                    self._emit(event_sink, "sub_agent_finished", {
                        "agent": self.name, "run_id": run_id, "result": error_msg, "success": False
                    })
                    return {"run_id": run_id, "agent_name": self.name, "success": False, "result": error_msg, "steps": step_number}

        # Лимит шагов
        limit_msg = f"Агент {self.display_name} достиг лимита шагов ({self.max_steps})"
        self.memory_store.append_session(state.chat_history, state.observations, self.client.model)
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
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "run_id": run_id,
            "agent_name": self.name,
            "success": success,
            "status": "done" if success else "failed",
            "result": summary,
            "summary": summary,
            "steps": steps,
            "changed_files": [],
            "created_artifacts": [],
            "verification": [],
            "risks": [],
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

        observation = Observation(
            step=step_number, action=tool.name, result=result,
            success=True, thought=step.thought
        )
        state.add_observation(observation)
        self._emit(event_sink, "sub_agent_tool_result", {"agent": self.name, "run_id": run_id, **asdict(observation)})

        if tool.name == "finish_task" or step.done:
            return str(result.get("summary") or step.summary or "Задача завершена")
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
