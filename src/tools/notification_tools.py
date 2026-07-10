from __future__ import annotations

import base64
import subprocess
from typing import Any

from src.infra.errors import ToolExecutionError


class NotificationTools:
    """Инструменты для Windows-уведомлений."""

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
