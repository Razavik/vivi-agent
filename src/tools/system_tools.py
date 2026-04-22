from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import time
import tempfile

from src.infra.errors import ToolExecutionError


class SystemTools:
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

    def open_url(self, args: dict[str, object]) -> dict[str, object]:
        url = str(args.get("url", ""))
        if not url.startswith(("http://", "https://")):
            if "." in url:
                url = "https://" + url
            else:
                raise ToolExecutionError(f"Некорректный URL: {url}")

        try:
            os.startfile(url)
            return {"url": url, "status": "opened"}
        except Exception as e:
            raise ToolExecutionError(f"Не удалось открыть URL: {str(e)}")

    def run_powershell(self, args: dict[str, object]) -> dict[str, object]:
        script = str(args.get("script", "")).strip()
        if not script:
            raise ToolExecutionError("Поле script должно быть непустой строкой")

        cwd_value = args.get("cwd")
        cwd = None if cwd_value in (None, "") else str(cwd_value)
        event_sink = args.get("__event_sink__")
        timeout = args.get("timeout")
        timeout_sec: float | None = float(timeout) if timeout is not None else 60.0
        detach = bool(args.get("detach", False))

        started_at = time.perf_counter()
        temp_path = None
        stdout_lines: list[str] = []
        stderr_lines: list[str] = []
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".ps1", encoding="utf-8-sig", delete=False) as temp_file:
                temp_file.write(self._utf8_powershell_preamble())
                temp_file.write(script)
                temp_path = temp_file.name

            if detach:
                # Запускаем без ожидания — для GUI-приложений и долгих фоновых процессов
                proc = subprocess.Popen(
                    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", temp_path],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                    cwd=cwd,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
                )
                # Даём 2 сек — если процесс уже завершился, значит упал с ошибкой
                try:
                    proc.wait(timeout=2)
                    crashed = True
                except subprocess.TimeoutExpired:
                    crashed = False

                duration_ms = int((time.perf_counter() - started_at) * 1000)
                if crashed:
                    stderr_out = (proc.stderr.read() if proc.stderr else "").strip()
                    stdout_out = (proc.stdout.read() if proc.stdout else "").strip()
                    return {
                        "script": script,
                        "cwd": cwd,
                        "detach": True,
                        "returncode": proc.returncode,
                        "stdout": stdout_out,
                        "stderr": stderr_out,
                        "success": False,
                        "message": f"Процесс завершился сразу с ошибкой (код {proc.returncode}): {stderr_out or stdout_out}",
                        "duration_ms": duration_ms,
                    }
                return {
                    "script": script,
                    "cwd": cwd,
                    "detach": True,
                    "success": True,
                    "message": "Процесс запущен в фоне (detach=true). Завершение не ожидается.",
                    "duration_ms": duration_ms,
                }

            process = subprocess.Popen(
                ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", temp_path],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                cwd=cwd,
            )

            import threading

            def _read_stderr() -> None:
                assert process.stderr is not None
                for line in process.stderr:
                    stderr_lines.append(line.rstrip("\n"))

            stderr_thread = threading.Thread(target=_read_stderr, daemon=True)
            stderr_thread.start()

            timed_out = False
            assert process.stdout is not None
            deadline = time.perf_counter() + timeout_sec if timeout_sec else None
            for line in process.stdout:
                line = line.rstrip("\n")
                stdout_lines.append(line)
                if callable(event_sink):
                    event_sink("powershell_output", {"line": line, "stream": "stdout"})
                if deadline and time.perf_counter() > deadline:
                    timed_out = True
                    process.kill()
                    break

            process.wait()
            stderr_thread.join(timeout=5)
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    pass

        duration_ms = int((time.perf_counter() - started_at) * 1000)
        stdout = "\n".join(stdout_lines).strip()
        stderr = "\n".join(stderr_lines).strip()
        if timed_out:
            return {
                "script": script,
                "cwd": cwd,
                "timed_out": True,
                "stdout": stdout,
                "stderr": stderr,
                "success": False,
                "message": f"Процесс прерван по таймауту ({timeout_sec:.0f}с). Для долгих/GUI процессов используй detach=true.",
                "duration_ms": duration_ms,
            }
        success = process.returncode == 0
        return {
            "script": script,
            "cwd": cwd,
            "returncode": process.returncode,
            "stdout": stdout,
            "stderr": stderr,
            "success": success,
            "message": "Команда выполнена" if success else "Команда завершилась с ошибкой",
            "duration_ms": duration_ms,
        }

    def get_system_info(self, args: dict[str, object]) -> dict[str, object]:
        return {
            "python": shutil.which("python"),
            "powershell": shutil.which("powershell"),
        }

    def disk_free_space(self, params: dict[str, object]) -> dict[str, object]:
        drive = str(params.get("drive", "C")).rstrip(":") + ":"
        command = f"Get-PSDrive -Name {drive[0]} | Select-Object Name,Free,Used"
        return self._run_powershell(command)

    def list_network_adapters(self, params: dict[str, object]) -> dict[str, object]:
        command = "Get-NetAdapter | Select-Object Name,Status,MacAddress | ConvertTo-Json"
        return self._run_powershell(command)

    def list_temp_files(self, params: dict[str, object]) -> dict[str, object]:
        command = "Get-ChildItem $env:TEMP | Select-Object Name,Length,LastWriteTime | ConvertTo-Json"
        return self._run_powershell(command)

    def get_installed_programs(self, args: dict[str, object]) -> dict[str, object]:
        import os

        script_path = os.path.join(os.path.dirname(__file__), "get_programs.ps1")

        if not os.path.exists(script_path):
            return {"installed_programs": [], "count": 0, "error": f"Файл скрипта не найден: {script_path}"}

        escaped_script_path = script_path.replace("'", "''")
        command = f"& '{escaped_script_path}'"
        completed = subprocess.run(
            self._powershell_args(command),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()

        print(f"[DEBUG] Return code: {completed.returncode}")
        print(f"[DEBUG] Stderr: {stderr}")
        print(f"[DEBUG] Stdout length: {len(stdout)}")

        if completed.returncode != 0:
            return {"installed_programs": [], "count": 0, "error": stderr or "PowerShell завершился с ошибкой"}

        try:
            programs = json.loads(stdout) if stdout else []
            if not isinstance(programs, list):
                programs = []
            return {"installed_programs": programs, "count": len(programs)}
        except json.JSONDecodeError as e:
            return {"installed_programs": [], "count": 0, "raw_output": stdout[:500], "error": f"Не удалось распарсить JSON: {e}"}

    def _run_powershell(self, script: str) -> dict[str, object]:
        completed = subprocess.run(
            self._powershell_args(script),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        if completed.returncode != 0:
            raise ToolExecutionError(stderr or "PowerShell завершился с ошибкой")
        return {"stdout": stdout}
