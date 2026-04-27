from __future__ import annotations

from typing import Any

from src.infra.errors import ToolExecutionError


class ArtifactTools:
    """Инструменты для создания и чтения артефактов внутри run'ов."""

    def __init__(self, server_context: Any) -> None:
        self.ctx = server_context

    def _resolve_run_id(self, args: dict[str, Any]) -> str:
        # Явно переданный run_id имеет приоритет (чужие артефакты),
        # иначе берём контекст текущего запуска через __run_id__.
        run_id = str(args.get("run_id") or args.get("__run_id__") or "")
        if not run_id:
            raise ToolExecutionError("Не удалось определить run_id для артефакта")
        return run_id

    def create_artifact(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = self._resolve_run_id(args)
        name = str(args.get("name", ""))
        content = str(args.get("content", ""))
        mime_type = str(args.get("mime_type", "text/plain"))
        if not name:
            raise ToolExecutionError("Параметр name обязателен")
        result = self.ctx.create_artifact(run_id, name, content, mime_type)
        return {"created": True, **result}

    def read_artifact(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = self._resolve_run_id(args)
        name = str(args.get("name", ""))
        if not name:
            raise ToolExecutionError("Параметр name обязателен")
        return self.ctx.read_artifact(run_id, name)

    def list_artifacts(self, args: dict[str, Any]) -> dict[str, Any]:
        run_id = self._resolve_run_id(args)
        return {"artifacts": self.ctx.list_artifacts(run_id)}

    def handoff_artifact(self, args: dict[str, Any]) -> dict[str, Any]:
        """Передать артефакт из текущего run в другой (handoff)."""
        src_run_id = self._resolve_run_id(args)
        src_name = str(args.get("name", ""))
        dst_run_id = str(args.get("dst_run_id", ""))
        dst_name = args.get("dst_name") or None
        if not src_name:
            raise ToolExecutionError("Параметр name обязателен")
        if not dst_run_id:
            raise ToolExecutionError("Параметр dst_run_id обязателен")
        return self.ctx.handoff_artifact(src_run_id, src_name, dst_run_id, dst_name)

    def gc_artifacts(self, args: dict[str, Any]) -> dict[str, Any]:
        """Удалить артефакты текущего run (older_than_seconds=0 — все)."""
        run_id = self._resolve_run_id(args)
        older_than = float(args.get("older_than_seconds", 0.0))
        count = self.ctx.gc_run_artifacts(run_id, older_than)
        return {"deleted": count, "run_id": run_id}

    def wait_for_artifact(self, args: dict[str, Any]) -> dict[str, Any]:
        """Объявить зависимость от артефакта другого run."""
        waiting_run_id = self._resolve_run_id(args)
        artifact_name = str(args.get("artifact_name", ""))
        provider_run_id = str(args.get("provider_run_id", ""))
        if not artifact_name or not provider_run_id:
            raise ToolExecutionError("Параметры artifact_name и provider_run_id обязательны")
        already_ready = self.ctx.dependency_graph.wait_for_artifact(waiting_run_id, artifact_name, provider_run_id)
        return {"already_ready": already_ready, "artifact_name": artifact_name, "provider_run_id": provider_run_id}

    def mark_artifact_ready(self, args: dict[str, Any]) -> dict[str, Any]:
        """Пометить артефакт готовым и уведомить ждущие run."""
        run_id = self._resolve_run_id(args)
        artifact_name = str(args.get("artifact_name", ""))
        if not artifact_name:
            raise ToolExecutionError("Параметр artifact_name обязателен")
        notified = self.ctx.dependency_graph.mark_artifact_ready(artifact_name, run_id)
        return {"notified_runs": notified, "artifact_name": artifact_name}
