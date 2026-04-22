from __future__ import annotations

from typing import Any

from src.agent.sub_agent import SubAgent


class AgentRegistry:
    """Реестр специализированных сабагентов."""

    def __init__(self) -> None:
        self._agents: dict[str, SubAgent] = {}

    def register(self, agent: SubAgent) -> None:
        self._agents[agent.name] = agent

    def get(self, name: str) -> SubAgent | None:
        return self._agents.get(name)

    def describe_all(self) -> list[dict[str, str]]:
        """Возвращает список доступных агентов с описаниями для промпта директора."""
        return [agent.describe() for agent in self._agents.values()]

    @property
    def agents(self) -> dict[str, SubAgent]:
        return dict(self._agents)
