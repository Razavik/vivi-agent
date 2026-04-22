from __future__ import annotations

import base64
import subprocess
from typing import Any

from src.infra.errors import ToolExecutionError


class ClipboardTools:
    """Инструменты для работы с буфером обмена Windows через PowerShell."""

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

    def get_clipboard(self, args: dict[str, Any]) -> dict[str, Any]:
        """Прочитать текущее содержимое буфера обмена."""
        rc, stdout, stderr = self._run_ps("Get-Clipboard")
        if rc != 0:
            raise ToolExecutionError(f"Не удалось прочитать буфер обмена: {stderr}")
        return {"text": stdout, "length": len(stdout)}

    def set_clipboard(self, args: dict[str, Any]) -> dict[str, Any]:
        """Записать текст в буфер обмена."""
        text = str(args.get("text", ""))
        # Экранируем одинарные кавычки для PowerShell
        escaped = text.replace("'", "''")
        rc, _, stderr = self._run_ps(f"Set-Clipboard -Value '{escaped}'")
        if rc != 0:
            raise ToolExecutionError(f"Не удалось записать в буфер обмена: {stderr}")
        return {"set": True, "length": len(text)}
