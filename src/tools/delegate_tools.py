from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from src.agent.agent_registry import AgentRegistry
from src.infra.errors import ToolExecutionError


class DelegateTools:
    """Инструменты для делегирования задач сабагентам."""

    def __init__(
        self,
        agent_registry: AgentRegistry,
        event_sink: Callable[[str, object], None] | None = None,
        ask_director_callback: Callable[[str], str] | None = None,
    ) -> None:
        self.agent_registry = agent_registry
        self.event_sink = event_sink
        self.ask_director_callback = ask_director_callback

    def delegate_task(self, args: dict[str, Any]) -> dict[str, Any]:
        """Делегировать задачу специализированному агенту."""
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

        result = agent.run(task, event_sink=self.event_sink, ask_director=self.ask_director_callback, images=images)
        return result

    def delegate_parallel(self, args: dict[str, Any]) -> dict[str, Any]:
        """Выполнить задачи у нескольких агентов параллельно.

        args.tasks — список объектов {agent_name: str, task: str}.
        Возвращает словарь {agent_name: result}.
        """
        tasks: list[dict[str, str]] = args.get("tasks", [])
        if not tasks:
            raise ToolExecutionError("Параметр tasks не может быть пустым")

        results: dict[str, Any] = {}

        def run_one(item: dict[str, str]) -> tuple[str, dict[str, Any]]:
            agent_name = str(item.get("agent_name", ""))
            task = str(item.get("task", ""))
            images: list[str] = item.get("images") or []  # type: ignore[assignment]
            agent = self.agent_registry.get(agent_name)
            if agent is None:
                return agent_name, {"success": False, "result": f"Неизвестный агент: {agent_name}"}
            result = agent.run(task, event_sink=self.event_sink, ask_director=self.ask_director_callback, images=images)
            return agent_name, result

        with ThreadPoolExecutor(max_workers=len(tasks)) as executor:
            futures = {executor.submit(run_one, item): item for item in tasks}
            for future in as_completed(futures):
                agent_name, result = future.result()
                results[agent_name] = result

        return {"results": results, "completed": len(results)}

    def get_ask_director_tool(self) -> Callable[[dict[str, Any]], dict[str, Any]]:
        """Возвращает функцию-инструмент ask_director для регистрации в реестре сабагента."""
        def ask_director(args: dict[str, Any]) -> dict[str, Any]:
            question = str(args.get("question", ""))
            if not question:
                raise ToolExecutionError("Параметр question обязателен")
            if self.ask_director_callback is None:
                return {"answer": "Директор недоступен. Действуй по своему усмотрению."}
            answer = self.ask_director_callback(question)
            return {"answer": answer}
        return ask_director
