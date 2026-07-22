from __future__ import annotations

from src.agent.core.runtime import AgentRuntime
from src.llm.prompt_builder import _build_delegation_block, build_dynamic_system_prompt


_AGENTS = [
    {"name": "file", "description": "работает с файлами"},
    {"name": "web", "description": "ищет в интернете"},
    {"name": "telegram", "description": "работает с telegram"},
]


class TestDelegationBlockPreferredAgents:
    def test_no_preferred_agents_no_hint(self) -> None:
        block = _build_delegation_block({"delegate_task"}, _AGENTS, None)
        assert "приоритет" not in block.lower()

    def test_empty_preferred_agents_no_hint(self) -> None:
        block = _build_delegation_block({"delegate_task"}, _AGENTS, [])
        assert "приоритет" not in block.lower()

    def test_preferred_agents_produce_soft_hint(self) -> None:
        block = _build_delegation_block({"delegate_task"}, _AGENTS, ["web", "telegram"])
        assert "web, telegram" in block
        assert "мягкая подсказка" in block

    def test_hint_does_not_override_capability_rule(self) -> None:
        """Регрессия: подсказка о приоритете не должна заменять или идти раньше
        правила "не делегируй без нужных возможностей" — это мягкий хинт, а не
        жёсткое переопределение выбора агента."""
        block = _build_delegation_block({"delegate_task"}, _AGENTS, ["web"])
        capability_rule_pos = block.index("нет нужных возможностей")
        hint_pos = block.index("приоритетные для этой сессии")
        assert capability_rule_pos < hint_pos


class TestBuildDynamicSystemPromptPassthrough:
    def test_preferred_agents_reach_delegation_block(self) -> None:
        tool_descriptions = [{"name": "delegate_task"}]
        prompt = build_dynamic_system_prompt(
            "base prompt", tool_descriptions, _AGENTS, preferred_agents=["telegram"]
        )
        assert "приоритетные для этой сессии: telegram" in prompt

    def test_no_delegation_tool_no_delegation_block_even_with_preference(self) -> None:
        tool_descriptions = [{"name": "read_text_file"}]
        prompt = build_dynamic_system_prompt(
            "base prompt", tool_descriptions, _AGENTS, preferred_agents=["telegram"]
        )
        assert "ДЕЛЕГИРОВАНИЕ" not in prompt


class TestFilterPreferredAgents:
    def test_none_returns_empty(self) -> None:
        assert AgentRuntime._filter_preferred_agents(None, _AGENTS) == []

    def test_empty_list_returns_empty(self) -> None:
        assert AgentRuntime._filter_preferred_agents([], _AGENTS) == []

    def test_keeps_only_known_agents(self) -> None:
        result = AgentRuntime._filter_preferred_agents(
            ["web", "not-a-real-agent", "telegram"], _AGENTS
        )
        assert result == ["web", "telegram"]

    def test_all_unknown_returns_empty(self) -> None:
        """Регрессия: имя из чужого/устаревшего клиента (например агент, которого
        отключили в data/agents.json) не должно просочиться в промпт модели —
        это защита от рассинхрона между тем, что помнит UI, и что реально
        доступно оператору прямо сейчас."""
        result = AgentRuntime._filter_preferred_agents(["ghost_agent"], _AGENTS)
        assert result == []
