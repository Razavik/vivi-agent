from __future__ import annotations

import base64
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import Any

from src.infra.errors import ToolExecutionError


class NotificationTools:
    """Инструменты: Windows-уведомления и скриншоты экрана."""

    @staticmethod
    def _utf8_powershell_preamble() -> str:
        return (
            "[Console]::InputEncoding = [Console]::OutputEncoding = "
            "[System.Text.UTF8Encoding]::new($false); "
            "$OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
            "chcp 65001 > $null; "
        )

    @classmethod
    def _run_ps(cls, script: str) -> tuple[int, str, str]:
        command = cls._utf8_powershell_preamble() + script
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        return completed.returncode, completed.stdout.strip(), completed.stderr.strip()

    def show_notification(self, args: dict[str, Any]) -> dict[str, Any]:
        """Показать Windows toast-уведомление (заголовок + текст)."""
        title = str(args.get("title", "Агент")).replace("'", "''")
        message = str(args.get("message", "")).replace("'", "''")
        if not message:
            raise ToolExecutionError("Параметр message не может быть пустым")

        # Используем BurntToast если есть, иначе WScript.Shell popup
        script = f"""
try {{
    $null = Get-Module -ListAvailable BurntToast -ErrorAction Stop
    Import-Module BurntToast -ErrorAction Stop
    New-BurntToastNotification -Text '{title}', '{message}'
}} catch {{
    $wsh = New-Object -ComObject WScript.Shell
    $wsh.Popup('{message}', 5, '{title}', 64) | Out-Null
}}
"""
        rc, _, stderr = self._run_ps(script)
        if rc != 0:
            raise ToolExecutionError(f"Не удалось показать уведомление: {stderr}")
        return {"shown": True, "title": title, "message": message}

    def take_screenshot(self, args: dict[str, Any]) -> dict[str, Any]:
        """Сделать скриншот экрана и сохранить в файл PNG."""
        save_path = str(args.get("path", "")).strip()
        if not save_path:
            # Создаём путь в папке Downloads
            ts = int(time.time())
            downloads = Path(os.environ.get("USERPROFILE", Path.home())) / "Downloads"
            downloads.mkdir(exist_ok=True)
            save_path = str(downloads / f"screenshot_{ts}.png")

        save_path_esc = save_path.replace("'", "''")
        script = f"""
Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
$screen = [System.Windows.Forms.Screen]::PrimaryScreen.Bounds
$bmp = New-Object System.Drawing.Bitmap($screen.Width, $screen.Height)
$gfx = [System.Drawing.Graphics]::FromImage($bmp)
$gfx.CopyFromScreen($screen.Location, [System.Drawing.Point]::Empty, $screen.Size)
$bmp.Save('{save_path_esc}')
$gfx.Dispose()
$bmp.Dispose()
Write-Output $screen.Width
Write-Output $screen.Height
"""
        rc, stdout, stderr = self._run_ps(script)
        if rc != 0:
            raise ToolExecutionError(f"Не удалось сделать скриншот: {stderr}")

        lines = [l for l in stdout.splitlines() if l.strip()]
        width = int(lines[0]) if len(lines) > 0 else 0
        height = int(lines[1]) if len(lines) > 1 else 0

        return {
            "path": save_path,
            "saved": True,
            "width": width,
            "height": height,
        }
