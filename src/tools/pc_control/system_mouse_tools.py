from __future__ import annotations

import ctypes
import ctypes.wintypes
import base64
import platform
import subprocess
import time
from dataclasses import asdict, dataclass
from typing import Any

from src.infra.errors import ToolExecutionError


@dataclass
class CursorState:
    x: int
    y: int
    visible: bool = True
    clicking: bool = False
    updated_at: float = 0.0


class SystemMouseTools:
    _dpi_awareness_set = False

    def move(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        x = self._read_coordinate(args, "x")
        y = self._read_coordinate(args, "y")
        self._set_cursor_pos(x, y)
        cursor = self._cursor_state(clicking=False)
        screenshot = self._take_cursor_screenshot("move")
        has_screenshot = isinstance(screenshot.get("image"), str) and bool(screenshot.get("image"))
        return {
            "ok": True,
            "action": "move",
            "x": x,
            "y": y,
            "cursor": asdict(cursor),
            **screenshot,
            "_type": "image" if has_screenshot else "system_mouse",
        }

    def nudge(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        dx = self._read_delta(args, "dx")
        dy = self._read_delta(args, "dy")
        cursor_before = self._cursor_state(clicking=False)
        target_x = cursor_before.x + dx
        target_y = cursor_before.y + dy
        self._set_cursor_pos(target_x, target_y)
        cursor = self._cursor_state(clicking=False)
        screenshot = self._take_cursor_screenshot("nudge")
        has_screenshot = isinstance(screenshot.get("image"), str) and bool(screenshot.get("image"))
        return {
            "ok": True,
            "action": "nudge",
            "dx": dx,
            "dy": dy,
            "from": asdict(cursor_before),
            "cursor": asdict(cursor),
            **screenshot,
            "_type": "image" if has_screenshot else "system_mouse",
        }

    def click(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        if "x" in args or "y" in args:
            raise ToolExecutionError("system_mouse_click не принимает координаты. Сначала вызови system_mouse_move(x, y), проверь скриншот, затем system_mouse_click(button?).")
        button = str(args.get("button", "left")).lower().strip()
        if button not in {"left", "right"}:
            raise ToolExecutionError("Поддерживаются только кнопки мыши: left, right")
        self._mouse_click(button)
        time.sleep(0.12)
        cursor = self._cursor_state(clicking=True)
        screenshot = self._take_cursor_screenshot("click")
        has_screenshot = isinstance(screenshot.get("image"), str) and bool(screenshot.get("image"))
        return {
            "ok": True,
            "action": "click",
            "button": button,
            "cursor": asdict(cursor),
            **screenshot,
            "_type": "image" if has_screenshot else "system_mouse",
        }

    def double_click(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        if "x" in args or "y" in args:
            raise ToolExecutionError("system_mouse_double_click не принимает координаты. Сначала вызови system_mouse_move(x, y), проверь скриншот, затем system_mouse_double_click().")
        self._mouse_click("left")
        time.sleep(0.08)
        self._mouse_click("left")
        time.sleep(0.12)
        cursor = self._cursor_state(clicking=True)
        screenshot = self._take_cursor_screenshot("double_click")
        has_screenshot = isinstance(screenshot.get("image"), str) and bool(screenshot.get("image"))
        return {
            "ok": True,
            "action": "double_click",
            "cursor": asdict(cursor),
            **screenshot,
            "_type": "image" if has_screenshot else "system_mouse",
        }

    def scroll(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        clicks = self._read_scroll_clicks(args)
        x = self._read_coordinate(args, "x", fallback=None)
        y = self._read_coordinate(args, "y", fallback=None)
        if x is not None and y is not None:
            self._set_cursor_pos(x, y)
        ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(clicks) * 120, 0)
        time.sleep(0.08)
        cursor = self._cursor_state(clicking=False)
        return {
            "ok": True,
            "action": "scroll",
            "clicks": clicks,
            "x": x,
            "y": y,
            "cursor": asdict(cursor),
            "_type": "system_mouse",
        }

    def drag(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        from_x = self._read_coordinate(args, "from_x")
        from_y = self._read_coordinate(args, "from_y")
        to_x = self._read_coordinate(args, "to_x")
        to_y = self._read_coordinate(args, "to_y")
        duration_ms = self._read_duration(args)
        self._set_cursor_pos(from_x, from_y)
        user32 = ctypes.windll.user32
        user32.mouse_event(0x0002, 0, 0, 0, 0)
        steps = max(3, min(40, duration_ms // 20))
        for i in range(1, steps + 1):
            t = i / steps
            x = round(from_x + (to_x - from_x) * t)
            y = round(from_y + (to_y - from_y) * t)
            self._set_cursor_pos(x, y)
            time.sleep(max(0.005, duration_ms / steps / 1000))
        user32.mouse_event(0x0004, 0, 0, 0, 0)
        cursor = self._cursor_state(clicking=False)
        return {
            "ok": True,
            "action": "drag",
            "from": {"x": from_x, "y": from_y},
            "to": {"x": to_x, "y": to_y},
            "duration_ms": duration_ms,
            "cursor": asdict(cursor),
            "_type": "system_mouse",
        }

    def _ensure_windows(self) -> None:
        if platform.system().lower() != "windows":
            raise ToolExecutionError("Системное управление мышью сейчас поддерживается только на Windows")
        if not SystemMouseTools._dpi_awareness_set:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                try:
                    ctypes.windll.user32.SetProcessDPIAware()
                except Exception:
                    pass
            SystemMouseTools._dpi_awareness_set = True

    def _read_coordinate(self, args: dict[str, Any], name: str, fallback: int | None = None) -> int | None:
        raw = args.get(name, fallback)
        if raw is None:
            return None
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректная координата {name}: {raw}") from exc
        return max(0, value)

    def _read_delta(self, args: dict[str, Any], name: str) -> int:
        raw = args.get(name)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректный параметр {name}: {raw}") from exc
        return max(-250, min(250, value))

    def _set_cursor_pos(self, x: int | None, y: int | None) -> None:
        if x is None or y is None:
            raise ToolExecutionError("Для перемещения мыши нужны координаты x и y")
        script = f"""
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class CursorWin32 {{
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool SetCursorPos(int X, int Y);
}}
"@
[CursorWin32]::SetProcessDPIAware() | Out-Null
if (-not [CursorWin32]::SetCursorPos({int(x)}, {int(y)})) {{ throw "SetCursorPos failed" }}
"""
        self._run_powershell(script)
        time.sleep(0.05)

    def _mouse_click(self, button: str) -> None:
        user32 = ctypes.windll.user32
        if button == "right":
            down = 0x0008
            up = 0x0010
        else:
            down = 0x0002
            up = 0x0004
        user32.mouse_event(down, 0, 0, 0, 0)
        time.sleep(0.04)
        user32.mouse_event(up, 0, 0, 0, 0)

    def _read_scroll_clicks(self, args: dict[str, Any]) -> int:
        raw = args.get("clicks", args.get("amount", -3))
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректный clicks: {raw}") from exc
        if value == 0:
            raise ToolExecutionError("clicks не должен быть 0")
        return max(-20, min(20, value))

    def _read_duration(self, args: dict[str, Any]) -> int:
        raw = args.get("duration_ms", 250)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректный duration_ms: {raw}") from exc
        return max(50, min(3000, value))

    def _cursor_state(self, clicking: bool) -> CursorState:
        script = """
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class CursorWin32 {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT lpPoint);
}
"@
[CursorWin32]::SetProcessDPIAware() | Out-Null
$point = New-Object CursorWin32+POINT
if (-not [CursorWin32]::GetCursorPos([ref]$point)) { throw "GetCursorPos failed" }
[PSCustomObject]@{ x = $point.X; y = $point.Y } | ConvertTo-Json -Compress
"""
        raw = self._run_powershell(script).strip()
        try:
            import json

            payload = json.loads(raw)
            x = int(payload["x"])
            y = int(payload["y"])
        except Exception as exc:
            raise ToolExecutionError(f"Не удалось получить позицию системного курсора: {raw}") from exc
        return CursorState(
            x=x,
            y=y,
            clicking=clicking,
            updated_at=time.time(),
        )

    def _run_powershell(self, script: str) -> str:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            message = result.stderr.strip() or result.stdout.strip() or "PowerShell cursor command failed"
            raise ToolExecutionError(message)
        return result.stdout

    def _take_cursor_screenshot(self, reason: str) -> dict[str, Any]:
        try:
            from src.tools.pc_control.screen_tools import ScreenTools

            cursor = self._cursor_state(clicking=False)
            width = 520
            height = 360
            result = ScreenTools().take_screenshot({
                "x": cursor.x - width // 2,
                "y": cursor.y - height // 2,
                "width": width,
                "height": height,
            })
            return {
                "image": result.get("image"),
                "format": result.get("format"),
                "path": result.get("path"),
                "web_path": result.get("web_path"),
                "screen_info": result.get("screen_info"),
                "crop": result.get("crop"),
                "screenshot_scope": "cursor_crop",
                "screenshot_reason": reason,
                "screenshot_after_move": reason == "move",
                "screenshot_after_click": reason in {"click", "double_click"},
            }
        except Exception as exc:
            return {
                "screenshot_scope": "cursor_crop",
                "screenshot_reason": reason,
                "screenshot_after_move": False,
                "screenshot_after_click": False,
                "screenshot_error": str(exc),
            }
