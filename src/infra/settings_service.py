from __future__ import annotations

from typing import Any

from src.infra.config import OPERATOR_REQUIRED_TOOLS


class SettingsService:
    def sanitize_agents_config(self, config: dict[str, Any]) -> dict[str, Any]:
        cleaned = {k: v for k, v in config.items() if isinstance(v, (str, dict, list, bool, int, float))}
        operator_cfg = cleaned.get("operator")
        if isinstance(operator_cfg, dict):
            operator_cfg["tools"] = self._protect_operator_tools(operator_cfg.get("tools"))
        return cleaned

    def _protect_operator_tools(self, raw_tools: object) -> list[dict[str, Any]]:
        tools_by_name: dict[str, dict[str, Any]] = {}
        if isinstance(raw_tools, list):
            for entry in raw_tools:
                if isinstance(entry, dict):
                    name = str(entry.get("name", ""))
                    if name:
                        normalized = dict(entry)
                        if name not in OPERATOR_REQUIRED_TOOLS:
                            normalized["required"] = False
                        tools_by_name[name] = normalized
                elif isinstance(entry, str):
                    tools_by_name[entry] = {"name": entry, "enabled": True}
        for tool_name in OPERATOR_REQUIRED_TOOLS:
            current = tools_by_name.get(tool_name, {"name": tool_name})
            current["enabled"] = True
            current["required"] = True
            tools_by_name[tool_name] = current
        return list(tools_by_name.values())
