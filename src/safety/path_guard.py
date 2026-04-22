from __future__ import annotations

from pathlib import Path

from src.infra.errors import PolicyError


class PathGuard:
    def __init__(self, allowed_roots: list[Path]) -> None:
        self.allowed_roots = [path.expanduser().resolve() for path in allowed_roots]

    def normalize(self, raw_path: str) -> Path:
        candidate = Path(raw_path).expanduser().resolve()
        self.ensure_allowed(candidate)
        return candidate

    def ensure_allowed(self, path: Path) -> None:
        normalized = path.resolve()
        if any(root == normalized or root in normalized.parents for root in self.allowed_roots):
            return
        raise PolicyError(f"Путь запрещён политикой безопасности: {normalized}")
