from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any


class ArtifactStore:
    """Потокобезопасное хранилище артефактов агентов на диске."""

    def __init__(self, base_dir: Path | str) -> None:
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()

    def _run_dir(self, run_id: str) -> Path:
        return self.base_dir / run_id

    def create(
        self,
        run_id: str,
        name: str,
        content: str | bytes,
        mime_type: str = "text/plain",
    ) -> dict[str, Any]:
        run_dir = self._run_dir(run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        file_path = run_dir / name

        if isinstance(content, str):
            data = content.encode("utf-8")
        else:
            data = content

        with self._lock:
            file_path.write_bytes(data)
            meta_path = run_dir / f"{name}.meta.json"
            meta = {
                "name": name,
                "mime_type": mime_type,
                "size": len(data),
                "created_at": time.time(),
            }
            meta_path.write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")

        return {"name": name, "mime_type": mime_type, "size": len(data), "path": str(file_path)}

    def read(self, run_id: str, name: str) -> dict[str, Any]:
        run_dir = self._run_dir(run_id)
        file_path = run_dir / name
        meta_path = run_dir / f"{name}.meta.json"

        if not file_path.exists():
            return {"error": f"Артефакт '{name}' не найден для run_id={run_id}"}

        data = file_path.read_bytes()
        mime_type = "text/plain"
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                mime_type = meta.get("mime_type", "text/plain")
            except Exception:
                pass

        return {
            "name": name,
            "mime_type": mime_type,
            "size": len(data),
            "content": data.decode("utf-8") if mime_type.startswith("text/") else data.hex(),
        }

    def list(self, run_id: str) -> list[dict[str, Any]]:
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            return []

        result = []
        for meta_path in run_dir.glob("*.meta.json"):
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                result.append(meta)
            except Exception:
                pass
        return result

    def delete(self, run_id: str, name: str) -> bool:
        run_dir = self._run_dir(run_id)
        file_path = run_dir / name
        meta_path = run_dir / f"{name}.meta.json"
        with self._lock:
            removed = False
            if file_path.exists():
                file_path.unlink()
                removed = True
            if meta_path.exists():
                meta_path.unlink()
                removed = True
            return removed

    def gc_run(self, run_id: str, older_than_seconds: float = 0.0) -> int:
        """Удаляет все артефакты run (опционально только старше N секунд). Возвращает кол-во удалённых."""
        run_dir = self._run_dir(run_id)
        if not run_dir.exists():
            return 0
        cutoff = time.time() - older_than_seconds
        count = 0
        artifacts = self.list(run_id)
        for meta in artifacts:
            name = meta.get("name", "")
            if older_than_seconds > 0:
                created_at = float(meta.get("created_at", 0))
                if created_at > cutoff:
                    continue
            if name and self.delete(run_id, name):
                count += 1
        with self._lock:
            try:
                run_dir.rmdir()
            except OSError:
                pass
        return count

    def copy_artifact(self, src_run_id: str, src_name: str, dst_run_id: str, dst_name: str | None = None) -> dict[str, Any]:
        """Копирует артефакт из одного run в другой (для handoff)."""
        src_data = self.read(src_run_id, src_name)
        if "error" in src_data:
            return src_data
        target_name = dst_name or src_name
        if src_data["mime_type"].startswith("text/"):
            content: str | bytes = src_data["content"]
        else:
            content = bytes.fromhex(src_data["content"])
        return self.create(dst_run_id, target_name, content, src_data["mime_type"])
