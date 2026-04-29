from __future__ import annotations

import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.infra.config import (
    AGENTS_FILE,
    AVAILABLE_MODELS_FILE,
    DIRECTOR_REQUIRED_TOOLS,
    MODELS_FILE,
    TOOLS_CONFIG_FILE,
    USER_PROFILE_FILE,
    Settings,
    _load_agents_config,
    load_available_models,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]


@dataclass(slots=True)
class DiagnosticCheck:
    id: str
    title: str
    status: str
    severity: str
    summary: str
    action: str = ""
    details: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "severity": self.severity,
            "summary": self.summary,
            "action": self.action,
            "fix": self._fix_suggestion(),
        }
        if self.details:
            data["details"] = self.details
        return data

    def _fix_suggestion(self) -> dict[str, Any] | None:
        fixes: dict[str, dict[str, Any]] = {
            "director-tools": {
                "fix_id": "protect_director_tools",
                "risk": "low",
                "can_auto_apply": True,
                "steps": [
                    "Mark director run-control tools as enabled",
                    "Mark director run-control tools as required",
                    "Restart backend runtime",
                ],
            },
            "prompt-contract": {
                "fix_id": "sync_director_prompt_tools",
                "risk": "low",
                "can_auto_apply": False,
                "steps": [
                    "Add missing tool descriptions to prompts/system_prompt.txt",
                    "Restart backend runtime",
                ],
            },
            "sensitive-files": {
                "fix_id": "remove_sensitive_files_from_git",
                "risk": "medium",
                "can_auto_apply": False,
                "steps": [
                    "Add runtime/session patterns to .gitignore",
                    "Remove sensitive files from git index without deleting local files",
                ],
            },
            "workspace-root": {
                "fix_id": "align_workspace_root",
                "risk": "low",
                "can_auto_apply": False,
                "steps": [
                    "Set AGENT_WORKSPACE to project root or update default Settings.workspace_root",
                    "Restart backend runtime",
                ],
            },
            "python-deps": {
                "fix_id": "sync_requirements",
                "risk": "low",
                "can_auto_apply": False,
                "steps": [
                    "Add missing backend packages to requirements.txt",
                    "Recreate or update virtual environment",
                ],
            },
            "ollama": {
                "fix_id": "restore_ollama",
                "risk": "manual",
                "can_auto_apply": False,
                "steps": [
                    "Start Ollama",
                    "Verify OLLAMA_BASE_URL",
                    "Pull configured models if missing",
                ],
            },
            "entrypoints": {
                "fix_id": "normalize_entrypoints",
                "risk": "low",
                "can_auto_apply": False,
                "steps": [
                    "Make main.py start the backend",
                    "Move demos/examples out of root entrypoint",
                ],
            },
        }
        if self.status not in {"fail", "warn"}:
            return None
        return fixes.get(self.id)


class DiagnosticsService:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def run(self, ctx: Any | None = None) -> dict[str, Any]:
        checks = [
            self._check_json_files(),
            self._check_director_tools(),
            self._check_prompt_tool_contract(),
            self._check_sensitive_files(),
            self._check_workspace_root(),
            self._check_python_dependencies(),
            self._check_ollama(),
            self._check_models(),
            self._check_runtime_state(ctx),
            self._check_crash_reports(ctx),
            self._check_entrypoints(),
        ]
        counts = self._count_by_status(checks)
        score = self._score(checks)
        return {
            "generated_at": time.time(),
            "score": score,
            "status": self._overall_status(checks),
            "counts": counts,
            "summary": self._summary(checks, score),
            "checks": [check.to_dict() for check in checks],
            "facts": self._facts(ctx),
        }

    def _check_json_files(self) -> DiagnosticCheck:
        files = [AGENTS_FILE, MODELS_FILE, AVAILABLE_MODELS_FILE, TOOLS_CONFIG_FILE, USER_PROFILE_FILE]
        broken: list[str] = []
        present = 0
        for path in files:
            if not path.exists():
                continue
            present += 1
            try:
                json.loads(path.read_text(encoding="utf-8"))
            except Exception as exc:
                broken.append(f"{path.name}: {exc}")
        if broken:
            return DiagnosticCheck(
                "json-config",
                "JSON конфиги",
                "fail",
                "critical",
                "Некоторые JSON-конфиги не читаются как UTF-8 JSON.",
                "Исправить синтаксис файлов из details, иначе настройки могут молча откатываться.",
                {"broken": broken},
            )
        return DiagnosticCheck(
            "json-config",
            "JSON конфиги",
            "pass",
            "info",
            f"Проверено конфигов: {present}. Ошибок парсинга нет.",
        )

    def _check_director_tools(self) -> DiagnosticCheck:
        cfg = _load_agents_config().get("director", {})
        raw_tools = cfg.get("tools", []) if isinstance(cfg, dict) else []
        tools: dict[str, dict[str, Any]] = {}
        if isinstance(raw_tools, list):
            for entry in raw_tools:
                if isinstance(entry, dict):
                    name = str(entry.get("name", ""))
                    if name:
                        tools[name] = entry
                elif isinstance(entry, str):
                    tools[entry] = {"name": entry, "enabled": True}
        missing = sorted(DIRECTOR_REQUIRED_TOOLS - set(tools))
        disabled = sorted(
            name
            for name in DIRECTOR_REQUIRED_TOOLS
            if name in tools and not bool(tools[name].get("enabled", True)) and not bool(tools[name].get("required", False))
        )
        not_required = sorted(name for name in DIRECTOR_REQUIRED_TOOLS if name in tools and not bool(tools[name].get("required", False)))
        if missing or disabled:
            return DiagnosticCheck(
                "director-tools",
                "Инструменты директора",
                "fail",
                "critical",
                "Директор может вызвать инструмент, которого нет в runtime registry.",
                "Вернуть отсутствующие tools и перезапустить backend.",
                {"missing": missing, "disabled": disabled, "not_required": not_required},
            )
        if not_required:
            return DiagnosticCheck(
                "director-tools",
                "Инструменты директора",
                "warn",
                "high",
                "Обязательные tools включены, но часть не защищена флагом required.",
                "Пометить tools из details как required, чтобы UI не мог их выключить.",
                {"not_required": not_required},
            )
        return DiagnosticCheck(
            "director-tools",
            "Инструменты директора",
            "pass",
            "info",
            f"Все обязательные tools директора доступны: {len(DIRECTOR_REQUIRED_TOOLS)}.",
        )

    def _check_prompt_tool_contract(self) -> DiagnosticCheck:
        prompt = PROJECT_ROOT / "prompts" / "system_prompt.txt"
        if not prompt.exists():
            return DiagnosticCheck(
                "prompt-contract",
                "Контракт prompt/tools",
                "fail",
                "critical",
                "Системный prompt директора не найден.",
                "Восстановить prompts/system_prompt.txt.",
            )
        text = prompt.read_text(encoding="utf-8", errors="replace")
        mentioned = sorted(name for name in DIRECTOR_REQUIRED_TOOLS if name in text)
        unmentioned = sorted(DIRECTOR_REQUIRED_TOOLS - set(mentioned))
        if unmentioned:
            return DiagnosticCheck(
                "prompt-contract",
                "Контракт prompt/tools",
                "warn",
                "medium",
                "Часть обязательных tools есть в registry, но не описана в prompt.",
                "Добавить краткое описание tools из details в системный prompt.",
                {"unmentioned": unmentioned},
            )
        return DiagnosticCheck(
            "prompt-contract",
            "Контракт prompt/tools",
            "pass",
            "info",
            "Prompt директора синхронизирован с обязательными runtime tools.",
        )

    def _check_sensitive_files(self) -> DiagnosticCheck:
        tracked = self._git_ls_files()
        sensitive_patterns = (".env", ".session", "telegram_session", "pending_confirm.json")
        sensitive = sorted(
            path
            for path in tracked
            if any(pattern in path.replace("\\", "/") for pattern in sensitive_patterns)
        )
        if sensitive:
            return DiagnosticCheck(
                "sensitive-files",
                "Секреты и runtime-файлы",
                "fail",
                "critical",
                "В git отслеживаются файлы, которые могут содержать секреты или живые сессии.",
                "Убрать эти файлы из индекса git и добавить правила в .gitignore.",
                {"tracked": sensitive},
            )
        return DiagnosticCheck(
            "sensitive-files",
            "Секреты и runtime-файлы",
            "pass",
            "info",
            "Явных секретов и session-файлов в tracked files не найдено.",
        )

    def _check_workspace_root(self) -> DiagnosticCheck:
        root = self.settings.workspace_root.resolve()
        project = PROJECT_ROOT.resolve()
        if root != project:
            return DiagnosticCheck(
                "workspace-root",
                "Workspace root",
                "warn",
                "high",
                f"AGENT_WORKSPACE указывает на {root}, а проект находится в {project}.",
                "Если это не намеренно, выставить AGENT_WORKSPACE на корень проекта, чтобы runs/artifacts/crashes писались ожидаемо.",
                {"workspace_root": str(root), "project_root": str(project)},
            )
        return DiagnosticCheck(
            "workspace-root",
            "Workspace root",
            "pass",
            "info",
            "Workspace root совпадает с корнем проекта.",
            details={"workspace_root": str(root)},
        )

    def _check_python_dependencies(self) -> DiagnosticCheck:
        requirements = PROJECT_ROOT / "requirements.txt"
        declared = set()
        if requirements.exists():
            declared = {
                line.strip().split("==", 1)[0].split(">=", 1)[0].split("~=", 1)[0].lower()
                for line in requirements.read_text(encoding="utf-8", errors="replace").splitlines()
                if line.strip() and not line.strip().startswith("#")
            }
        expected = {"requests", "websockets", "telethon", "tiktoken"}
        missing = sorted(expected - declared)
        if missing:
            return DiagnosticCheck(
                "python-deps",
                "Python зависимости",
                "warn",
                "high",
                "requirements.txt не описывает зависимости, которые используются backend-кодом.",
                "Добавить зависимости из details, иначе чистая установка проекта не поднимется.",
                {"missing": missing, "declared": sorted(declared)},
            )
        return DiagnosticCheck(
            "python-deps",
            "Python зависимости",
            "pass",
            "info",
            "Ключевые backend-зависимости отражены в requirements.txt.",
            details={"declared": sorted(declared)},
        )

    def _check_ollama(self) -> DiagnosticCheck:
        base_url = self.settings.ollama_base_url.rstrip("/")
        try:
            with urllib.request.urlopen(f"{base_url}/api/tags", timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            count = len(data.get("models", [])) if isinstance(data, dict) else 0
            return DiagnosticCheck(
                "ollama",
                "Ollama",
                "pass",
                "info",
                f"Ollama отвечает, скачанных моделей: {count}.",
                details={"base_url": base_url, "models": count},
            )
        except (OSError, urllib.error.URLError, TimeoutError, json.JSONDecodeError) as exc:
            return DiagnosticCheck(
                "ollama",
                "Ollama",
                "warn",
                "high",
                "Ollama сейчас недоступна или вернула некорректный ответ.",
                "Запустить Ollama или проверить OLLAMA_BASE_URL.",
                {"base_url": base_url, "error": str(exc)},
            )

    def _check_models(self) -> DiagnosticCheck:
        models = {}
        if MODELS_FILE.exists():
            try:
                raw = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    models = {str(k): str(v) for k, v in raw.items() if str(v).strip()}
            except Exception:
                pass
        available = set(load_available_models())
        unknown = sorted({model for model in models.values() if available and model not in available})
        if unknown:
            return DiagnosticCheck(
                "model-config",
                "Конфиг моделей",
                "warn",
                "medium",
                "В data/models.json есть модели вне списка available_models.json.",
                "Проверить, скачаны ли эти модели в Ollama, или добавить их в available_models.json.",
                {"unknown": unknown, "configured": models},
            )
        return DiagnosticCheck(
            "model-config",
            "Конфиг моделей",
            "pass",
            "info",
            f"Настройки моделей читаются, назначений: {len(models)}.",
            details={"configured": models},
        )

    def _check_runtime_state(self, ctx: Any | None) -> DiagnosticCheck:
        if ctx is None:
            return DiagnosticCheck("runtime-state", "Runtime", "skip", "info", "ServerContext недоступен.")
        active = ctx.get_active_runs()
        risky = [run for run in active if run.get("status") in {"blocked", "interrupted", "error", "waiting_user"}]
        if risky:
            return DiagnosticCheck(
                "runtime-state",
                "Runtime",
                "warn",
                "medium",
                f"Есть run, требующие внимания: {len(risky)}.",
                "Открыть Runs Dashboard и закрыть/перезапустить проблемные run.",
                {"runs": risky[:10]},
            )
        return DiagnosticCheck(
            "runtime-state",
            "Runtime",
            "pass",
            "info",
            f"Активных run: {len(active)}. Критичных статусов нет.",
        )

    def _check_crash_reports(self, ctx: Any | None) -> DiagnosticCheck:
        if ctx is None:
            return DiagnosticCheck("crashes", "Crash reports", "skip", "info", "ServerContext недоступен.")
        reports = ctx.crash_reporter.list_reports()
        if reports:
            return DiagnosticCheck(
                "crashes",
                "Crash reports",
                "warn",
                "medium",
                f"Найдено crash-отчётов: {len(reports)}.",
                "Открыть страницу Crash Reports и разобрать последние ошибки.",
                {"latest": reports[:5]},
            )
        return DiagnosticCheck("crashes", "Crash reports", "pass", "info", "Crash-отчётов нет.")

    def _check_entrypoints(self) -> DiagnosticCheck:
        main = PROJECT_ROOT / "main.py"
        run = PROJECT_ROOT / "run.py"
        if main.exists() and run.exists():
            text = main.read_text(encoding="utf-8", errors="replace").lower()
            if "start_server" not in text and "app.run()" in text:
                return DiagnosticCheck(
                    "entrypoints",
                    "Entrypoints",
                    "warn",
                    "medium",
                    "main.py выглядит как посторонний demo-entrypoint, а backend запускается через run.py.",
                    "Переименовать demo-файл или явно описать запуск backend в README/start.bat.",
                    {"main": str(main), "run": str(run)},
                )
        return DiagnosticCheck("entrypoints", "Entrypoints", "pass", "info", "Конфликтующих entrypoints не найдено.")

    def _facts(self, ctx: Any | None) -> dict[str, Any]:
        return {
            "project_root": str(PROJECT_ROOT),
            "workspace_root": str(self.settings.workspace_root),
            "python": sys.version.split()[0],
            "default_model": self.settings.model,
            "ollama_base_url": self.settings.ollama_base_url,
            "active_runs": len(ctx.get_active_runs()) if ctx is not None else 0,
            "required_director_tools": sorted(DIRECTOR_REQUIRED_TOOLS),
        }

    def _git_ls_files(self) -> list[str]:
        try:
            proc = subprocess.run(
                ["git", "ls-files"],
                cwd=PROJECT_ROOT,
                check=False,
                capture_output=True,
                text=True,
                encoding="utf-8",
                timeout=5,
            )
        except Exception:
            return []
        if proc.returncode != 0:
            return []
        return [line.strip() for line in proc.stdout.splitlines() if line.strip()]

    def _count_by_status(self, checks: list[DiagnosticCheck]) -> dict[str, int]:
        counts = {"pass": 0, "warn": 0, "fail": 0, "skip": 0}
        for check in checks:
            counts[check.status] = counts.get(check.status, 0) + 1
        return counts

    def _score(self, checks: list[DiagnosticCheck]) -> int:
        penalty = 0
        for check in checks:
            if check.status == "fail":
                penalty += 22 if check.severity == "critical" else 16
            elif check.status == "warn":
                penalty += {"high": 12, "medium": 7}.get(check.severity, 4)
        return max(0, min(100, 100 - penalty))

    def _overall_status(self, checks: list[DiagnosticCheck]) -> str:
        if any(check.status == "fail" for check in checks):
            return "critical"
        if any(check.status == "warn" for check in checks):
            return "attention"
        return "healthy"

    def _summary(self, checks: list[DiagnosticCheck], score: int) -> str:
        critical = [check for check in checks if check.status == "fail"]
        warnings = [check for check in checks if check.status == "warn"]
        if critical:
            return f"Health score {score}/100. Критичных проблем: {len(critical)}, предупреждений: {len(warnings)}."
        if warnings:
            return f"Health score {score}/100. Система работает, но есть предупреждения: {len(warnings)}."
        return f"Health score {score}/100. Критичных проблем не найдено."
