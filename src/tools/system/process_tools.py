from __future__ import annotations

import base64
import csv
import io
import json
import subprocess
from pathlib import Path

from src.infra.errors import ToolExecutionError


class ProcessTools:
    @staticmethod
    def _utf8_powershell_preamble() -> str:
        return (
            "[Console]::InputEncoding = [Console]::OutputEncoding = "
            "[System.Text.UTF8Encoding]::new($false); "
            "$OutputEncoding = [System.Text.UTF8Encoding]::new($false); "
            "chcp 65001 > $null; "
        )

    @classmethod
    def _powershell_args(cls, script: str) -> list[str]:
        command = cls._utf8_powershell_preamble() + script
        encoded = base64.b64encode(command.encode("utf-16le")).decode("ascii")
        return ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded]

    @staticmethod
    def _coerce_non_negative_int(value: object, default: int = 0) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed >= 0 else default

    def list_processes(self, args: dict[str, object]) -> dict[str, object]:
        # limit=0 или не указан означает "показать все"
        limit = self._coerce_non_negative_int(args.get("limit"), 0)
        offset = self._coerce_non_negative_int(args.get("offset"), 0)
        items = self._collect_processes()
        items.sort(key=lambda value: str(value.get("name", "")).lower())
        total = len(items)
        if offset:
            items = items[offset:]
        if limit > 0:
            items = items[:limit]
        return {
            "items": items,
            "total": total,
            "returned": len(items),
            "offset": offset,
            "limit": limit,
        }

    def _collect_processes(self) -> list[dict[str, object]]:
        # Сначала пробуем PowerShell: UTF-8 и без зависимости от code page tasklist
        completed = subprocess.run(
            self._powershell_args(
                "Get-CimInstance Win32_Process | "
                "Select-Object @{Name='Name';Expression={$_.Name}}, "
                "@{Name='Pid';Expression={$_.ProcessId}} | "
                "ConvertTo-Json -Depth 3"
            ),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        if completed.returncode == 0:
            stdout = completed.stdout.strip()
            if stdout:
                try:
                    payload = json.loads(stdout)
                    if isinstance(payload, dict):
                        payload = [payload]
                    if isinstance(payload, list):
                        items: list[dict[str, object]] = []
                        for row in payload:
                            if not isinstance(row, dict):
                                continue
                            name = row.get("Name")
                            pid = row.get("Pid")
                            if name is None or pid is None:
                                continue
                            items.append({"name": str(name), "pid": str(pid)})
                        if items:
                            return items
                except json.JSONDecodeError:
                    pass

        # Fallback на tasklist, если PowerShell-способ недоступен
        completed = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            capture_output=True,
        )
        if completed.returncode != 0:
            raise ToolExecutionError(
                completed.stderr.decode("cp1251", errors="replace").strip()
                or "Не удалось получить список процессов"
            )

        stdout = completed.stdout.decode("cp1251", errors="replace")
        reader = csv.reader(io.StringIO(stdout))
        items = []
        for row in reader:
            if len(row) < 2:
                continue
            items.append({"name": row[0], "pid": row[1]})
        return items

    def launch_app(self, args: dict[str, object]) -> dict[str, object]:
        app_name = str(args["app_name"])
        raw_args = args.get("args", [])
        if not isinstance(raw_args, list):
            raise ToolExecutionError("Аргумент args должен быть списком")

        # Проверяем, передан ли полный путь к файлу (.exe или .lnk)
        app_path = Path(app_name)
        if app_path.exists():
            # Если это ярлык Windows (.lnk), используем explorer для запуска
            if app_path.suffix.lower() == ".lnk":
                try:
                    process = subprocess.Popen(["explorer", str(app_path)])
                    return {"pid": process.pid, "command": f"explorer \"{app_path}\"", "path": str(app_path)}
                except Exception as e:
                    raise ToolExecutionError(f"Не удалось запустить ярлык {app_name}: {str(e)}")
            # Если это .exe или другой исполняемый файл
            elif app_path.suffix.lower() in [".exe", ".bat", ".cmd", ".ps1"]:
                try:
                    process = subprocess.Popen([str(app_path), *[str(item) for item in raw_args]])
                    return {"pid": process.pid, "command": str(app_path), "args": raw_args}
                except Exception as e:
                    raise ToolExecutionError(f"Не удалось запустить приложение {app_name}: {str(e)}")

        # Стандартный запуск по имени (PATH)
        command = [app_name, *[str(item) for item in raw_args]]
        try:
            process = subprocess.Popen(command)
            return {"pid": process.pid, "command": command}
        except FileNotFoundError:
            raise ToolExecutionError(
                f"Приложение не найдено: {app_name}. Убедитесь, что оно установлено и добавлено в PATH."
            )
        except Exception as e:
            raise ToolExecutionError(f"Не удалось запустить приложение {app_name}: {str(e)}")

    def close_app(self, args: dict[str, object]) -> dict[str, object]:
        process_name = str(args["process_name"])
        completed = subprocess.run(
            ["taskkill", "/IM", process_name, "/F"],
            capture_output=True,
            text=True,
            encoding="cp866",
            errors="replace",
        )
        stderr = completed.stderr.strip()
        stdout = completed.stdout.strip()
        if completed.returncode != 0:
            raise ToolExecutionError(stderr or stdout or f"Процесс не найден: {process_name}")
        return {"process_name": process_name, "closed": True, "output": stdout}
