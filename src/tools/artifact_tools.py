from __future__ import annotations

from typing import Any

from src.infra.errors import ToolExecutionError


class ArtifactTools:
    """Инструменты для создания и чтения артефактов внутри run'ов."""

    def __init__(self, server_context: Any) -> None:
        self.ctx = server_context

    def create_artifact(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = str(args.get("run_id", ""))
        name = str(args.get("name", ""))
        content = str(args.get("content", ""))
        mime_type = str(args.get("mime_type", "text/plain"))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        if not name:
            raise ToolExecutionError("Параметр name обязателен")
        result = self.ctx.create_artifact(run_id, name, content, mime_type)
        return {"created": True, **result}

    def read_artifact(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = str(args.get("run_id", ""))
        name = str(args.get("name", ""))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        if not name:
            raise ToolExecutionError("Параметр name обязателен")
        return self.ctx.read_artifact(run_id, name)

    def list_artifacts(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = str(args.get("run_id", ""))
        if not run_id:
            raise ToolExecutionError("Параметр run_id обязателен")
        return {"artifacts": self.ctx.list_artifacts(run_id)}
