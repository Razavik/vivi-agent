from __future__ import annotations

import time
from dataclasses import asdict, dataclass
from typing import Any

from src.infra.errors import ToolExecutionError


@dataclass
class VirtualMouseState:
    x: int = 640
    y: int = 360
    visible: bool = True
    clicking: bool = False
    updated_at: float = 0.0


class VirtualMouseTools:
    def __init__(self) -> None:
        self.state = VirtualMouseState(updated_at=time.time())

    def move(self, args: dict[str, Any]) -> dict[str, Any]:
        x = self._read_coordinate(args, "x")
        y = self._read_coordinate(args, "y")
        self.state.x = x
        self.state.y = y
        self.state.clicking = False
        self.state.visible = bool(args.get("visible", True))
        self.state.updated_at = time.time()
        return self._result("move")

    def click_preview(self, args: dict[str, Any]) -> dict[str, Any]:
        x = self._read_coordinate(args, "x", fallback=self.state.x)
        y = self._read_coordinate(args, "y", fallback=self.state.y)
        self.state.x = x
        self.state.y = y
        self.state.clicking = True
        self.state.visible = True
        self.state.updated_at = time.time()
        return self._result("click_preview")

    def _result(self, action: str) -> dict[str, Any]:
        return {
            "_type": "virtual_mouse",
            "action": action,
            "cursor": asdict(self.state),
        }

    def _read_coordinate(self, args: dict[str, Any], name: str, fallback: int | None = None) -> int:
        raw = args.get(name, fallback)
        if raw is None:
            raise ToolExecutionError(f"Не указана координата {name}")
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректная координата {name}: {raw}") from exc
        return max(0, value)
