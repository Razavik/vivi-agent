from __future__ import annotations

from src.app_factory import (
    _build_all_tool_specs,
    build_operator_registry,
    describe_all_tools,
)
from src.agent.lifecycle.agent_registry import AgentRegistry
from src.infra.config import get_settings
from src.tools.agent_ops.delegate_tools import DelegateTools


def test_describe_all_tools_shape() -> None:
    tools = describe_all_tools(get_settings())
    assert tools, "expected at least one tool description"
    for t in tools:
        assert set(t) >= {"name", "description", "risk_level", "args_schema", "agent"}
        assert isinstance(t["name"], str) and t["name"]
        assert isinstance(t["args_schema"], dict)


def test_describe_all_tools_unique_per_agent() -> None:
    tools = describe_all_tools(get_settings())
    seen = set()
    for t in tools:
        key = (t["agent"], t["name"])
        assert key not in seen, f"duplicate tool {key}"
        seen.add(key)


def test_build_all_tool_specs_unique_names() -> None:
    specs = _build_all_tool_specs(get_settings(), None)
    assert specs
    for name, spec in specs.items():
        assert spec.name == name
        assert callable(spec.handler)


def test_operator_registry_builds_and_validates() -> None:
    dt = DelegateTools(AgentRegistry())
    reg = build_operator_registry(dt, None)
    described = reg.describe_all()
    assert described
    names = [d["name"] for d in described]
    assert "finish_task" in names  # required operator tool always present
    assert len(names) == len(set(names))


def test_pc_mode_operator_registers_get_screen_info(monkeypatch) -> None:
    """Regression: get_screen_info рекламируется в PC-промпте и UI, поэтому он
    обязан быть зарегистрирован в реестре оператора в режиме управления ПК."""
    import src.app_factory as af

    monkeypatch.setattr(af, "is_pc_control_mode", lambda: True)
    reg = build_operator_registry(DelegateTools(AgentRegistry()), None)
    names = {d["name"] for d in reg.describe_all()}
    assert "get_screen_info" in names


def test_pc_mode_ui_matches_operator_registry(monkeypatch) -> None:
    """UI-описание оператора (без фильтра enabled) должно совпадать с набором,
    который реально регистрируется в реестре оператора в PC-режиме."""
    import src.app_factory as af

    monkeypatch.setattr(af, "is_pc_control_mode", lambda: True)
    ui_names = {t["name"] for t in describe_all_tools(get_settings()) if t["agent"] == "operator"}
    reg_names = {d["name"] for d in build_operator_registry(DelegateTools(AgentRegistry()), None).describe_all()}
    # Реестр может дополнительно фильтроваться по agents.json (enabled), поэтому
    # реестр — подмножество показанного в UI набора.
    assert reg_names <= ui_names
    assert "get_screen_info" in ui_names


def test_orchestrator_mode_operator_registers_run_tools(monkeypatch) -> None:
    """Регрессия: view_runs/cancel_run/message_run/resume_run и т.п. нужны
    именно в режиме оркестратора (там реально идут делегированные run,
    которыми supervisor просит управлять при hang_detected) — а не в
    pc_control_mode, где delegate_task недоступен и управлять нечем.
    Раньше OPERATOR_RUN_TOOLS ошибочно попадал в фильтр "скрыть, если НЕ
    pc_mode" в дополнение к фильтру "скрыть, если pc_mode" — из-за чего эти
    инструменты были недоступны оператору вообще ни в одном режиме.

    monkeypatch форсирует pc_mode=False явно — иначе тест зависел бы от
    реального data/app_settings.json (пользователь мог включить режим ПК
    в самом приложении, и тест ловил бы это как ложный провал)."""
    import src.app_factory as af

    monkeypatch.setattr(af, "is_pc_control_mode", lambda: False)
    reg = build_operator_registry(DelegateTools(AgentRegistry()), None)
    names = {d["name"] for d in reg.describe_all()}
    for tool in ("view_runs", "cancel_run", "pause_run", "resume_run", "message_run"):
        assert tool in names, f"{tool} должен быть доступен оператору в режиме оркестратора"
    assert "delegate_task" in names


def test_pc_mode_operator_hides_run_tools(monkeypatch) -> None:
    """В pc_control_mode делегирования нет, поэтому управлять запусками
    саб-агентов нечем — инструменты run-management там не нужны."""
    import src.app_factory as af

    monkeypatch.setattr(af, "is_pc_control_mode", lambda: True)
    reg = build_operator_registry(DelegateTools(AgentRegistry()), None)
    names = {d["name"] for d in reg.describe_all()}
    for tool in ("view_runs", "cancel_run", "message_run", "delegate_task"):
        assert tool not in names


def test_catalog_consistency_across_builders() -> None:
    """Any tool present in multiple builders must share identical metadata.

    This guards against the historical drift between the three hand-maintained
    copies of the tool catalog.
    """
    settings = get_settings()
    described = {t["name"]: t for t in describe_all_tools(settings)}
    specs = _build_all_tool_specs(settings, None)
    for name, spec in specs.items():
        if name in described:
            d = described[name]
            assert d["risk_level"] == spec.risk_level, f"risk drift for {name}"
            assert d["args_schema"] == spec.args_schema, f"args drift for {name}"
