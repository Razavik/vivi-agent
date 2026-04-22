from __future__ import annotations

import json
from typing import Any

from src.infra.config import MODELS_FILE

VALID_AGENTS = {"director", "file", "system", "telegram", "web"}


class ModelTools:
    """Инструменты директора для управления моделями агентов."""

    def set_agent_model(self, args: dict[str, Any]) -> dict[str, Any]:
        """Устанавливает модель Ollama для конкретного агента и сохраняет в models.json."""
        agent = str(args.get("agent", "")).strip().lower()
        model = str(args.get("model", "")).strip()

        if not agent:
            return {"success": False, "error": "Параметр agent обязателен"}
        if agent not in VALID_AGENTS:
            return {"success": False, "error": f"Неизвестный агент '{agent}'. Допустимые: {', '.join(sorted(VALID_AGENTS))}"}
        if not model:
            return {"success": False, "error": "Параметр model обязателен"}

        data: dict[str, str] = {}
        if MODELS_FILE.exists():
            try:
                data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
            except Exception:
                pass

        data[agent] = model
        MODELS_FILE.parent.mkdir(parents=True, exist_ok=True)
        MODELS_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

        return {"success": True, "agent": agent, "model": model}
