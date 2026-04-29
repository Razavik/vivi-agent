from __future__ import annotations

from typing import Any

from src.infra.config import DIRECTOR_REQUIRED_TOOLS


class SettingsService:
    def sanitize_agents_config(self, config: dict[str, Any]) -> dict[str, Any]:
        cleaned = {k: v for k, v in config.items() if isinstance(v, (str, dict, list, bool, int, float))}
        director_cfg = cleaned.get("director")
        if isinstance(director_cfg, dict):
            director_cfg["tools"] = self._protect_director_tools(director_cfg.get("tools"))
        return cleaned

    def _protect_director_tools(self, raw_tools: object) -> list[dict[str, Any]]:
        tools_by_name: dict[str, dict[str, Any]] = {}
        if isinstance(raw_tools, list):
            for entry in raw_tools:
                if isinstance(entry, dict):
                    name = str(entry.get("name", ""))
                    if name:
                        tools_by_name[name] = dict(entry)
                elif isinstance(entry, str):
                    tools_by_name[entry] = {"name": entry, "enabled": True}
        for tool_name in DIRECTOR_REQUIRED_TOOLS:
            current = tools_by_name.get(tool_name, {"name": tool_name})
            current["enabled"] = True
            current["required"] = True
            tools_by_name[tool_name] = current
        return list(tools_by_name.values())
