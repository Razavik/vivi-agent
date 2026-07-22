from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable
from uuid import uuid4

from src.agent.core.schemas import SubAgentResult
from src.agent.lifecycle.agent_registry import AgentRegistry
from src.agent.lifecycle.run_control import RunController
from src.infra.errors import ToolExecutionError


class DelegateTools:
    """Tools used by the operator to run specialized sub-agents."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        event_sink: Callable[[str, object], None] | None = None,
        ask_operator_callback: Callable[[str], str] | None = None,
        create_run_controller: Callable[[str, str, str], RunController] | None = None,
    ) -> None:
        self.agent_registry = agent_registry
        self.event_sink = event_sink
        self.ask_operator_callback = ask_operator_callback
        self.create_run_controller = create_run_controller

    def delegate_task(self, args: dict[str, Any]) -> dict[str, Any]:
        agent_name = str(args.get("agent_name", ""))
        task = str(args.get("task", ""))
        images: list[str] = args.get("images") or []

        if not agent_name:
            raise ToolExecutionError("Параметр agent_name обязателен")
        if not task:
            raise ToolExecutionError("Параметр task обязателен")

        agent = self.agent_registry.get(agent_name)
        if agent is None:
            available = ", ".join(self.agent_registry.agents.keys())
            raise ToolExecutionError(f"Неизвестный агент: {agent_name}. Доступные агенты: {available}")

        run_id = str(args.get("run_id", "")).strip() or str(uuid4())
        controller = self._make_run_controller(run_id, agent_name, task)
        raw_result = agent.run(
            task,
            run_id=run_id,
            event_sink=self.event_sink,
            ask_operator=self.ask_operator_callback,
            controller=controller,
            images=images,
        )
        return self._normalize_result(raw_result)

    def delegate_parallel(self, args: dict[str, Any]) -> dict[str, Any]:
        tasks: list[dict[str, str]] = args.get("tasks", [])
        if not tasks:
            raise ToolExecutionError("Параметр tasks не может быть пустым")

        results: list[dict[str, Any]] = []

        def run_one(item: dict[str, str], index: int) -> dict[str, Any]:
            agent_name = str(item.get("agent_name", ""))
            task = str(item.get("task", ""))
            images: list[str] = item.get("images") or []  # type: ignore[assignment]
            run_id = str(item.get("run_id", "")).strip() or str(uuid4())

            agent = self.agent_registry.get(agent_name)
            if agent is None:
                result = self._normalize_result({
                    "run_id": run_id,
                    "agent_name": agent_name,
                    "status": "failed",
                    "success": False,
                    "result": f"Неизвестный агент: {agent_name}",
                })
                result["index"] = index
                return result

            controller = self._make_run_controller(run_id, agent_name, task)
            raw_result = agent.run(
                task,
                run_id=run_id,
                event_sink=self.event_sink,
                ask_operator=self.ask_operator_callback,
                controller=controller,
                images=images,
            )
            result = self._normalize_result(raw_result)
            result["index"] = index
            return result

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {
                executor.submit(run_one, item, index): item
                for index, item in enumerate(tasks)
            }
            for future in as_completed(futures):
                results.append(future.result())

        results.sort(key=lambda item: int(item.get("index", 0)))
        return {"results": results, "completed": len(results)}

    def get_ask_operator_tool(self) -> Callable[[dict[str, Any]], dict[str, Any]]:
        def ask_operator(args: dict[str, Any]) -> dict[str, Any]:
            question = str(args.get("question", ""))
            if not question:
                raise ToolExecutionError("Параметр question обязателен")
            if self.ask_operator_callback is None:
                return {"answer": "Оператор недоступен. Действуй по своему усмотрению."}
            answer = self.ask_operator_callback(question)
            return {"answer": answer}

        return ask_operator

    def _make_run_controller(self, run_id: str, agent_name: str, task: str) -> RunController | None:
        if self.create_run_controller is None:
            return None
        return self.create_run_controller(run_id, agent_name, task)

    def _normalize_result(self, raw_result: dict[str, Any]) -> dict[str, Any]:
        structured = SubAgentResult.from_raw(raw_result).to_dict()
        compact: dict[str, Any] = {
            "run_id": structured.get("run_id", ""),
            "agent_name": structured.get("agent_name", ""),
            "status": structured.get("status", "failed"),
            "success": bool(structured.get("success", False)),
            "summary": structured.get("summary", ""),
            "steps": structured.get("steps"),
        }
        for key in ("changed_files", "created_artifacts", "verification", "risks", "image_urls"):
            value = structured.get(key)
            if isinstance(value, list) and value:
                compact[key] = value
        if structured.get("needs_user_input"):
            compact["needs_user_input"] = True
        if structured.get("question"):
            compact["question"] = structured["question"]
        if structured.get("error"):
            compact["error"] = structured["error"]
        if structured.get("cancelled"):
            compact["cancelled"] = True
        return compact
