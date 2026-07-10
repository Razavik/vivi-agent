from __future__ import annotations

import base64
import json
import platform
import subprocess
from datetime import datetime
from pathlib import Path
from uuid import uuid4

from src.infra.errors import ToolExecutionError


def get_image_mime_type(file_path: str) -> str:
    """Определяет MIME-тип изображения по расширению файла."""
    ext = Path(file_path).suffix.lower()
    mime_types = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".gif": "image/gif",
        ".bmp": "image/bmp",
        ".webp": "image/webp",
    }
    return mime_types.get(ext, "image/png")


class ScreenTools:
    """Инструменты для работы с экраном."""

    @staticmethod
    def _take_screenshot_windows() -> str:
        """Создаёт скриншот на Windows через PowerShell."""
        script = """
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class CursorInterop {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [StructLayout(LayoutKind.Sequential)] public struct CURSORINFO { public int cbSize; public int flags; public IntPtr hCursor; public POINT ptScreenPos; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetCursorInfo(out CURSORINFO pci);
  [DllImport("user32.dll")] public static extern bool DrawIcon(IntPtr hDC, int X, int Y, IntPtr hIcon);
}
"@
        [CursorInterop]::SetProcessDPIAware() | Out-Null
        $screen = [System.Windows.Forms.SystemInformation]::VirtualScreen
        $bitmap = New-Object System.Drawing.Bitmap $screen.Width, $screen.Height
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
        $cursor = New-Object CursorInterop+CURSORINFO
        $cursor.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf([type] [CursorInterop+CURSORINFO])
        if ([CursorInterop]::GetCursorInfo([ref] $cursor) -and $cursor.flags -eq 1) {
            $cursorX = $cursor.ptScreenPos.X - $screen.Left
            $cursorY = $cursor.ptScreenPos.Y - $screen.Top
            $shadowPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(245, 0, 0, 0)), 7
            $ringPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 214, 77, 255)), 4
            $whitePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 255, 255, 255)), 2
            $hotspotBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 214, 77, 255))
            $graphics.DrawEllipse($shadowPen, $cursorX - 22, $cursorY - 22, 44, 44)
            $graphics.DrawLine($shadowPen, $cursorX - 34, $cursorY, $cursorX + 34, $cursorY)
            $graphics.DrawLine($shadowPen, $cursorX, $cursorY - 34, $cursorX, $cursorY + 34)
            $graphics.DrawEllipse($ringPen, $cursorX - 22, $cursorY - 22, 44, 44)
            $graphics.DrawLine($ringPen, $cursorX - 34, $cursorY, $cursorX + 34, $cursorY)
            $graphics.DrawLine($ringPen, $cursorX, $cursorY - 34, $cursorX, $cursorY + 34)
            $graphics.DrawEllipse($whitePen, $cursorX - 10, $cursorY - 10, 20, 20)
            $graphics.FillEllipse($hotspotBrush, $cursorX - 5, $cursorY - 5, 10, 10)
            $hotspotBrush.Dispose()
            $whitePen.Dispose()
            $ringPen.Dispose()
            $shadowPen.Dispose()
        }
        $graphics.Dispose()
        $ms = New-Object System.IO.MemoryStream
        $bitmap.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $bitmap.Dispose()
        [Convert]::ToBase64String($ms.ToArray())
        """
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _crop_screenshot_windows(x: int, y: int, width: int, height: int) -> str:
        """Создаёт crop экрана на Windows через PowerShell."""
        script = """
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type -AssemblyName System.Drawing
        Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class CursorInterop {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [StructLayout(LayoutKind.Sequential)] public struct CURSORINFO { public int cbSize; public int flags; public IntPtr hCursor; public POINT ptScreenPos; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetCursorInfo(out CURSORINFO pci);
  [DllImport("user32.dll")] public static extern bool DrawIcon(IntPtr hDC, int X, int Y, IntPtr hIcon);
}
"@
        [CursorInterop]::SetProcessDPIAware() | Out-Null
        $screen = [System.Windows.Forms.SystemInformation]::VirtualScreen
        $x = [Math]::Max(__X__, $screen.Left)
        $y = [Math]::Max(__Y__, $screen.Top)
        $right = [Math]::Min($x + __W__, $screen.Right)
        $bottom = [Math]::Min($y + __H__, $screen.Bottom)
        $w = [Math]::Max(1, $right - $x)
        $h = [Math]::Max(1, $bottom - $y)
        $bitmap = New-Object System.Drawing.Bitmap $w, $h
        $graphics = [System.Drawing.Graphics]::FromImage($bitmap)
        $graphics.CopyFromScreen($x, $y, 0, 0, (New-Object System.Drawing.Size $w, $h))
        $cursor = New-Object CursorInterop+CURSORINFO
        $cursor.cbSize = [System.Runtime.InteropServices.Marshal]::SizeOf([type] [CursorInterop+CURSORINFO])
        if ([CursorInterop]::GetCursorInfo([ref] $cursor) -and $cursor.flags -eq 1) {
            $cursorX = $cursor.ptScreenPos.X - $x
            $cursorY = $cursor.ptScreenPos.Y - $y
            if ($cursorX -ge 0 -and $cursorX -lt $w -and $cursorY -ge 0 -and $cursorY -lt $h) {
                $shadowPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(245, 0, 0, 0)), 7
                $ringPen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 214, 77, 255)), 4
                $whitePen = New-Object System.Drawing.Pen ([System.Drawing.Color]::FromArgb(255, 255, 255, 255)), 2
                $hotspotBrush = New-Object System.Drawing.SolidBrush ([System.Drawing.Color]::FromArgb(255, 214, 77, 255))
                $graphics.DrawEllipse($shadowPen, $cursorX - 22, $cursorY - 22, 44, 44)
                $graphics.DrawLine($shadowPen, $cursorX - 34, $cursorY, $cursorX + 34, $cursorY)
                $graphics.DrawLine($shadowPen, $cursorX, $cursorY - 34, $cursorX, $cursorY + 34)
                $graphics.DrawEllipse($ringPen, $cursorX - 22, $cursorY - 22, 44, 44)
                $graphics.DrawLine($ringPen, $cursorX - 34, $cursorY, $cursorX + 34, $cursorY)
                $graphics.DrawLine($ringPen, $cursorX, $cursorY - 34, $cursorX, $cursorY + 34)
                $graphics.DrawEllipse($whitePen, $cursorX - 10, $cursorY - 10, 20, 20)
                $graphics.FillEllipse($hotspotBrush, $cursorX - 5, $cursorY - 5, 10, 10)
                $hotspotBrush.Dispose()
                $whitePen.Dispose()
                $ringPen.Dispose()
                $shadowPen.Dispose()
            }
        }
        $graphics.Dispose()
        $ms = New-Object System.IO.MemoryStream
        $bitmap.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
        $bitmap.Dispose()
        [Convert]::ToBase64String($ms.ToArray())
        """
        script = (
            script.replace("__X__", str(x))
            .replace("__Y__", str(y))
            .replace("__W__", str(width))
            .replace("__H__", str(height))
        )
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout.strip()

    @staticmethod
    def _take_screenshot_linux() -> str:
        """Создаёт скриншот на Linux через scrot или import."""
        # Попробовать scrot
        try:
            result = subprocess.run(
                ["scrot", "-o", "/tmp/screen.png"],
                capture_output=True,
                check=True,
            )
            with open("/tmp/screen.png", "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

        # Попробовать import (ImageMagick)
        try:
            result = subprocess.run(
                ["import", "-window", "root", "/tmp/screen.png"],
                capture_output=True,
                check=True,
            )
            with open("/tmp/screen.png", "rb") as f:
                return base64.b64encode(f.read()).decode("utf-8")
        except (FileNotFoundError, subprocess.CalledProcessError):
            pass

        raise ToolExecutionError("Не удалось сделать скриншот: требуется scrot или ImageMagick")

    @staticmethod
    def _take_screenshot_macos() -> str:
        """Создаёт скриншот на macOS через screencapture."""
        result = subprocess.run(
            ["screencapture", "-i", "/tmp/screen.png"],
            capture_output=True,
            check=True,
        )
        with open("/tmp/screen.png", "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")

    def take_screenshot(self, args: dict[str, object]) -> dict[str, object]:
        """Создаёт скриншот экрана и возвращает его в формате base64.

        Args:
            args: Словарь аргументов. Опционально:
                x, y, width, height — область экрана для crop

        Returns:
            Словарь с ключом 'screenshot' содержащий base64-строку изображения PNG
        """
        system = platform.system().lower()
        x = self._read_optional_int(args, "x")
        y = self._read_optional_int(args, "y")
        width = self._read_optional_int(args, "width")
        height = self._read_optional_int(args, "height")
        use_region = any(value is not None for value in (x, y, width, height))
        if use_region and any(value is None for value in (x, y, width, height)):
            raise ToolExecutionError("Для скриншота области нужны все параметры: x, y, width, height")
        if use_region and (width is not None and width <= 0 or height is not None and height <= 0):
            raise ToolExecutionError("width и height должны быть больше 0")

        try:
            if system == "windows":
                if use_region:
                    screenshot_b64 = self._crop_screenshot_windows(
                        int(x), int(y), int(width), int(height)
                    )
                else:
                    screenshot_b64 = self._take_screenshot_windows()
            elif system == "linux":
                if use_region:
                    raise ToolExecutionError("Скриншот области сейчас поддерживается только на Windows")
                screenshot_b64 = self._take_screenshot_linux()
            elif system == "darwin":
                if use_region:
                    raise ToolExecutionError("Скриншот области сейчас поддерживается только на Windows")
                screenshot_b64 = self._take_screenshot_macos()
            else:
                raise ToolExecutionError(f"Неподдерживаемая операционная система: {system}")

            saved_path, web_path = self._save_screenshot_file(screenshot_b64)
            screen_info = self._safe_screen_info()
            cursor = screen_info.get("cursor") if isinstance(screen_info, dict) else None
            result: dict[str, object] = {
                "image": screenshot_b64,
                "format": "image/png",
                "system": system,
                "path": saved_path,
                "web_path": web_path,
                "cursor": cursor,
                "screen_info": screen_info,
                "_type": "image",
            }
            if use_region:
                cursor_in_crop = False
                crop_cursor = None
                if isinstance(cursor, dict):
                    cursor_x = cursor.get("x")
                    cursor_y = cursor.get("y")
                    if isinstance(cursor_x, int) and isinstance(cursor_y, int):
                        crop_x = cursor_x - int(x)
                        crop_y = cursor_y - int(y)
                        cursor_in_crop = 0 <= crop_x < int(width) and 0 <= crop_y < int(height)
                        crop_cursor = {"x": crop_x, "y": crop_y} if cursor_in_crop else None
                result["crop"] = {
                    "x": int(x),
                    "y": int(y),
                    "width": int(width),
                    "height": int(height),
                    "cursor_visible": cursor_in_crop,
                    "cursor": crop_cursor,
                }
            return result
        except Exception as e:
            raise ToolExecutionError(f"Не удалось создать скриншот: {str(e)}")

    def read_image(self, args: dict[str, object]) -> dict[str, object]:
        """Читает изображение по указанному пути и возвращает его в формате base64.

        Args:
            args: Словарь с ключом 'path' - путь к файлу изображения

        Returns:
            Словарь с ключами:
            - image: base64-строка изображения (для автоматического добавления в images)
            - format: MIME-тип изображения (image/png, image/jpeg, и т.д.)
            - path: путь к файлу
        """
        path = args.get("path")
        if not isinstance(path, str) or not path.strip():
            raise ToolExecutionError("Путь к изображению не указан или пуст")

        file_path = Path(path)
        if not file_path.exists():
            raise ToolExecutionError(f"Файл не найден: {path}")
        if not file_path.is_file():
            raise ToolExecutionError(f"Указанный путь не является файлом: {path}")

        try:
            with open(file_path, "rb") as f:
                image_data = f.read()
                image_b64 = base64.b64encode(image_data).decode("utf-8")

            mime_type = get_image_mime_type(path)

            # Возвращаем в формате, который runtime может распознать как изображение
            return {
                "image": image_b64,
                "format": mime_type,
                "path": str(file_path.absolute()),
                "size": len(image_data),
                "_type": "image",  # Специальный маркер для runtime
            }
        except Exception as e:
            raise ToolExecutionError(f"Не удалось прочитать изображение: {str(e)}")

    def _read_int(self, args: dict[str, object], name: str) -> int:
        raw = args.get(name)
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректный параметр {name}: {raw}") from exc

    def _read_optional_int(self, args: dict[str, object], name: str) -> int | None:
        raw = args.get(name)
        if raw is None:
            return None
        try:
            return int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректный параметр {name}: {raw}") from exc

    def _safe_screen_info(self) -> dict[str, object]:
        try:
            info = self.get_screen_info({})
            return info if isinstance(info, dict) else {}
        except Exception:
            return {}

    @staticmethod
    def _screenshots_dir() -> Path:
        return Path("data") / "screenshots"

    @classmethod
    def _save_screenshot_file(cls, screenshot_b64: str) -> tuple[str, str]:
        target_dir = cls._screenshots_dir()
        target_dir.mkdir(parents=True, exist_ok=True)
        filename = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid4().hex[:8]}.png"
        file_path = target_dir / filename
        file_path.write_bytes(base64.b64decode(screenshot_b64))
        return str(file_path.absolute()), f"/api/screenshots/{filename}"
    def get_screen_info(self, args: dict[str, object]) -> dict[str, object]:
        """Возвращает геометрию экранов, позицию курсора и активное окно."""
        system = platform.system().lower()
        if system != "windows":
            return {"system": system, "available": False}

        script = """
        Add-Type -AssemblyName System.Windows.Forms
        Add-Type @"
using System;
using System.Text;
using System.Runtime.InteropServices;
public static class WinInfo {
  [StructLayout(LayoutKind.Sequential)] public struct POINT { public int X; public int Y; }
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern bool GetCursorPos(out POINT lpPoint);
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
  [DllImport("user32.dll", CharSet=CharSet.Unicode)] public static extern int GetWindowText(IntPtr hWnd, StringBuilder text, int count);
  [DllImport("user32.dll")] public static extern bool GetWindowRect(IntPtr hWnd, out RECT rect);
  [StructLayout(LayoutKind.Sequential)] public struct RECT { public int Left; public int Top; public int Right; public int Bottom; }
}
"@
        [WinInfo]::SetProcessDPIAware() | Out-Null
        $cursor = New-Object WinInfo+POINT
        [WinInfo]::GetCursorPos([ref] $cursor) | Out-Null
        $hwnd = [WinInfo]::GetForegroundWindow()
        $titleBuilder = New-Object System.Text.StringBuilder 512
        [WinInfo]::GetWindowText($hwnd, $titleBuilder, $titleBuilder.Capacity) | Out-Null
        $rect = New-Object WinInfo+RECT
        [WinInfo]::GetWindowRect($hwnd, [ref] $rect) | Out-Null
        $screens = [System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
            [PSCustomObject]@{
                device = $_.DeviceName
                primary = $_.Primary
                x = $_.Bounds.X
                y = $_.Bounds.Y
                width = $_.Bounds.Width
                height = $_.Bounds.Height
                work_x = $_.WorkingArea.X
                work_y = $_.WorkingArea.Y
                work_width = $_.WorkingArea.Width
                work_height = $_.WorkingArea.Height
            }
        }
        [PSCustomObject]@{
            system = "windows"
            cursor = @{ x = $cursor.X; y = $cursor.Y }
            active_window = @{
                title = $titleBuilder.ToString()
                x = $rect.Left
                y = $rect.Top
                width = $rect.Right - $rect.Left
                height = $rect.Bottom - $rect.Top
            }
            screens = $screens
        } | ConvertTo-Json -Depth 5 -Compress
        """
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            check=True,
        )
        payload = json.loads(result.stdout.strip())
        if isinstance(payload, dict) and isinstance(payload.get("screens"), dict):
            payload["screens"] = [payload["screens"]]
        return payload
