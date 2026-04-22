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
