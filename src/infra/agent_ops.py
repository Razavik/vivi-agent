from __future__ import annotations

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import Settings, _load_agents_config
from src.infra.diagnostics import DiagnosticsService


@dataclass(slots=True)
class PreflightResult:
    allowed: bool
    status: str
    summary: str
    blocking: list[dict[str, Any]]
    warnings: list[dict[str, Any]]
    report: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "status": self.status,
            "summary": self.summary,
            "blocking": self.blocking,
            "warnings": self.warnings,
            "report": self.report,
        }


class AgentOpsService:
    def __init__(self, settings: Settings, ctx: Any | None = None) -> None:
        self.settings = settings
        self.ctx = ctx
        self.project_root = Path(__file__).resolve().parents[2]
        self.review_file = self.settings.workspace_root / "data" / "post_run_reviews.json"

    def preflight(self, task: str = "") -> dict[str, Any]:
        report = DiagnosticsService(self.settings).run(self.ctx)
        blocking = [
            check
            for check in report.get("checks", [])
            if check.get("status") == "fail" and check.get("severity") == "critical"
        ]
        warnings = [
            check
            for check in report.get("checks", [])
            if check.get("status") == "warn"
        ]
        allowed = not blocking
        summary = (
            "Preflight пройден. Критичных блокеров нет."
            if allowed
            else f"Preflight заблокировал запуск: {len(blocking)} критичных проблем."
        )
        return PreflightResult(
            allowed=allowed,
            status="passed" if allowed else "blocked",
            summary=summary,
            blocking=blocking,
            warnings=warnings,
            report=report,
        ).to_dict() | {"task": task}

    def create_post_run_review(
        self,
        task: str,
        result: dict[str, Any],
        preflight: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        post = DiagnosticsService(self.settings).run(self.ctx)
        checks = post.get("checks", [])
        failed = [c for c in checks if c.get("status") == "fail"]
        warnings = [c for c in checks if c.get("status") == "warn"]
        review = {
            "id": f"review-{int(time.time() * 1000)}",
            "created_at": time.time(),
            "task": task,
            "status": "needs_attention" if failed or warnings else "clean",
            "summary": self._review_summary(result, failed, warnings),
            "result_error": result.get("error"),
            "result_summary": result.get("summary"),
            "log_file": result.get("log_file"),
            "diagnostics_score": post.get("score"),
            "diagnostics_status": post.get("status"),
            "preflight_status": (preflight or {}).get("status"),
            "failed_checks": failed,
            "warning_checks": warnings,
        }
        reviews = self.list_post_run_reviews(limit=200).get("reviews", [])
        reviews.insert(0, review)
        self._write_reviews(reviews[:200])
        return review

    def list_post_run_reviews(self, limit: int = 50) -> dict[str, Any]:
        if not self.review_file.exists():
            return {"reviews": []}
        try:
            raw = json.loads(self.review_file.read_text(encoding="utf-8"))
        except Exception:
            return {"reviews": []}
        reviews = raw.get("reviews", []) if isinstance(raw, dict) else []
        return {"reviews": [r for r in reviews if isinstance(r, dict)][:limit]}

    def scorecard(self) -> dict[str, Any]:
        runs = self.ctx.run_registry.list_all() if self.ctx is not None else []
        by_agent: dict[str, dict[str, Any]] = {}
        for run in runs:
            agent = str(run.get("agent_name") or "unknown")
            item = by_agent.setdefault(
                agent,
                {
                    "agent": agent,
                    "total": 0,
                    "finished": 0,
                    "failed": 0,
                    "cancelled": 0,
                    "blocked": 0,
                    "retries": 0,
                    "interrupts": 0,
                    "avg_steps": 0.0,
                },
            )
            item["total"] += 1
            status = str(run.get("status") or "")
            if status == "finished":
                item["finished"] += 1
            elif status in {"error", "interrupted"}:
                item["failed"] += 1
            elif status == "cancelled":
                item["cancelled"] += 1
            elif status in {"blocked", "waiting_user"}:
                item["blocked"] += 1
            item["retries"] += int(run.get("retries") or 0)
            item["interrupts"] += int(run.get("interrupt_count") or 0)
            item["avg_steps"] += int(run.get("step") or 0)
        for item in by_agent.values():
            total = max(1, int(item["total"]))
            item["success_rate"] = round((item["finished"] / total) * 100, 1)
            item["avg_steps"] = round(float(item["avg_steps"]) / total, 1)
        return {
            "generated_at": time.time(),
            "agents": sorted(by_agent.values(), key=lambda x: (-x["total"], x["agent"])),
            "totals": {
                "runs": len(runs),
                "active": len(self.ctx.get_active_runs()) if self.ctx is not None else 0,
            },
        }

    def memory_inspector(self) -> dict[str, Any]:
        agents_cfg = _load_agents_config()
        memory_dir = self.settings.sub_agent_memory_dir
        items: list[dict[str, Any]] = []
        names = sorted(name for name in agents_cfg if name != "director")
        for name in names:
            file_path = memory_dir / f"{name}-memory.json"
            data = ChatMemoryStore(file_path).load()
            history = data.get("chat_history", [])
            facts = self._extract_memory_facts(history)
            items.append(
                {
                    "agent": name,
                    "display_name": (agents_cfg.get(name, {}) or {}).get("display_name", name),
                    "file": str(file_path),
                    "exists": file_path.exists(),
                    "updated_at": data.get("updated_at"),
                    "messages": len(history),
                    "assistant_messages": sum(1 for m in history if isinstance(m, dict) and m.get("role") == "assistant"),
                    "user_messages": sum(1 for m in history if isinstance(m, dict) and m.get("role") == "user"),
                    "actions": sum(len(m.get("actions", [])) for m in history if isinstance(m, dict)),
                    "facts": facts,
                    "stale": self._is_memory_stale(data.get("updated_at")),
                }
            )
        return {"generated_at": time.time(), "agents": items}

    def task_templates(self) -> dict[str, Any]:
        templates = [
            {
                "id": "project_audit",
                "title": "Проверить проект",
                "prompt": "Проведи аудит проекта: найди критичные баги, проверь сборку, диагностику, конфиги и предложи исправления.",
                "quality_gates": ["diagnostics", "python_compile", "typescript", "build_if_frontend_changed"],
            },
            {
                "id": "bugfix",
                "title": "Исправить баг",
                "prompt": "Найди причину бага, исправь минимально необходимым изменением, проверь регрессию и опиши результат.",
                "quality_gates": ["reproduce_or_explain", "targeted_fix", "relevant_tests"],
            },
            {
                "id": "frontend_feature",
                "title": "Добавить frontend-фичу",
                "prompt": "Добавь frontend-фичу в существующем стиле, проверь TypeScript и production build.",
                "quality_gates": ["typescript", "build", "responsive_ui"],
            },
            {
                "id": "crash_triage",
                "title": "Разобрать crash",
                "prompt": "Открой crash reports, сгруппируй ошибки, найди корневую причину и исправь самую критичную.",
                "quality_gates": ["crash_reports", "root_cause", "post_fix_diagnostics"],
            },
            {
                "id": "prompt_improvement",
                "title": "Улучшить prompts",
                "prompt": "Проверь prompts агентов, синхронизируй их с tools и добавь правила для структурированного результата.",
                "quality_gates": ["prompt_tool_contract", "no_tool_drift"],
            },
        ]
        return {"templates": templates}

    def run_replays(self, limit: int = 50) -> dict[str, Any]:
        log_dir = self.settings.log_dir
        sessions: list[dict[str, Any]] = []
        if log_dir.exists():
            for path in sorted(log_dir.glob("session-*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:limit]:
                try:
                    records = json.loads(path.read_text(encoding="utf-8"))
                except Exception:
                    records = []
                if not isinstance(records, list):
                    records = []
                events = [r for r in records if isinstance(r, dict)]
                sessions.append(
                    {
                        "id": path.stem,
                        "file": str(path),
                        "updated_at": path.stat().st_mtime,
                        "events": len(events),
                        "tool_calls": sum(1 for r in events if r.get("event") in {"llm_step", "tool_result"}),
                        "errors": [
                            r.get("payload")
                            for r in events
                            if r.get("event") in {"agent_error", "sub_agent_error"}
                        ][:5],
                        "timeline": events[-40:],
                    }
                )
        return {"sessions": sessions}

    def safe_command_preview(self, command: str) -> dict[str, Any]:
        text = command.strip()
        lowered = text.lower()
        risk = "low"
        reasons: list[str] = []
        touched_paths: list[str] = []
        destructive_markers = [
            "remove-item",
            "del ",
            "erase ",
            "rmdir",
            "rd ",
            "git reset",
            "git clean",
            "format ",
            "stop-process",
            "taskkill",
        ]
        write_markers = [">", ">>", "set-content", "add-content", "move-item", "copy-item", "new-item", "git rm"]
        if any(marker in lowered for marker in destructive_markers):
            risk = "high"
            reasons.append("Команда похожа на удаление, остановку процесса или необратимое изменение.")
        elif any(marker in lowered for marker in write_markers):
            risk = "medium"
            reasons.append("Команда может изменить файлы или состояние git.")
        if "-recurse" in lowered or "/s" in lowered:
            risk = "high" if risk != "critical" else risk
            reasons.append("Есть рекурсивный режим, нужен явный контроль пути.")
        for token in text.replace('"', " ").replace("'", " ").split():
            if ":\\" in token or token.startswith(".\\") or token.startswith("..\\"):
                touched_paths.append(token.rstrip(",;"))
        if not reasons:
            reasons.append("Явных опасных маркеров не найдено.")
        return {
            "command": command,
            "risk": risk,
            "reversible": risk in {"low", "medium"},
            "requires_confirmation": risk in {"medium", "high", "critical"},
            "touched_paths": touched_paths,
            "reasons": reasons,
            "recommendation": self._command_recommendation(risk),
        }

    def maintenance(self) -> dict[str, Any]:
        preflight = self.preflight("autonomous maintenance")
        scorecard = self.scorecard()
        memory = self.memory_inspector()
        recommendations = []
        for check in preflight["warnings"] + preflight["blocking"]:
            fix = check.get("fix")
            if fix:
                recommendations.append({"check_id": check.get("id"), "title": check.get("title"), "fix": fix})
        stale_memory = [m for m in memory.get("agents", []) if m.get("stale")]
        if stale_memory:
            recommendations.append(
                {
                    "check_id": "stale_memory",
                    "title": "Устаревшая память агентов",
                    "fix": {
                        "fix_id": "review_stale_memory",
                        "risk": "low",
                        "can_auto_apply": False,
                        "steps": ["Open Memory Inspector", "Review or clear stale agent memory"],
                    },
                }
            )
        return {
            "generated_at": time.time(),
            "status": "ok" if preflight["allowed"] else "blocked",
            "preflight": preflight,
            "scorecard": scorecard,
            "recommendations": recommendations,
        }

    def tool_contract_tests(self) -> dict[str, Any]:
        report = DiagnosticsService(self.settings).run(self.ctx)
        tests = [
            check
            for check in report.get("checks", [])
            if check.get("id") in {"director-tools", "prompt-contract"}
        ]
        return {
            "passed": all(check.get("status") == "pass" for check in tests),
            "tests": tests,
        }

    def _write_reviews(self, reviews: list[dict[str, Any]]) -> None:
        self.review_file.parent.mkdir(parents=True, exist_ok=True)
        self.review_file.write_text(
            json.dumps({"schema_version": 1, "reviews": reviews}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def _review_summary(self, result: dict[str, Any], failed: list[dict[str, Any]], warnings: list[dict[str, Any]]) -> str:
        if result.get("error"):
            return f"Run завершился ошибкой: {result.get('error')}"
        if failed:
            return f"Run завершён, но диагностика нашла критичные проблемы: {len(failed)}."
        if warnings:
            return f"Run завершён, остались предупреждения диагностики: {len(warnings)}."
        return "Run завершён, post-run диагностика чистая."

    def _extract_memory_facts(self, history: list[Any]) -> list[str]:
        facts: list[str] = []
        for item in history[-12:]:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or "").strip().replace("\n", " ")
            if content:
                facts.append(content[:160])
        return facts[-5:]

    def _is_memory_stale(self, updated_at: Any) -> bool:
        if not isinstance(updated_at, str) or not updated_at:
            return False
        try:
            from datetime import datetime

            dt = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            return (time.time() - dt.timestamp()) > 60 * 60 * 24 * 30
        except Exception:
            return False

    def _command_recommendation(self, risk: str) -> str:
        if risk == "high":
            return "РџРѕРєР°Р·Р°С‚СЊ РїРѕР»СЊР·РѕРІР°С‚РµР»СЋ preview, РїСЂРѕРІРµСЂРёС‚СЊ resolved paths Рё РІС‹РїРѕР»РЅРёС‚СЊ С‚РѕР»СЊРєРѕ РїРѕСЃР»Рµ РїРѕРґС‚РІРµСЂР¶РґРµРЅРёСЏ."
        if risk == "medium":
            return "РџСЂРѕРІРµСЂРёС‚СЊ Р·Р°С‚СЂРѕРЅСѓС‚С‹Рµ С„Р°Р№Р»С‹ Рё СѓР±РµРґРёС‚СЊСЃСЏ, С‡С‚Рѕ РёР·РјРµРЅРµРЅРёРµ РѕРіСЂР°РЅРёС‡РµРЅРѕ СЂР°Р±РѕС‡РµР№ РґРёСЂРµРєС‚РѕСЂРёРµР№."
        return "РњРѕР¶РЅРѕ РІС‹РїРѕР»РЅСЏС‚СЊ РєР°Рє low-risk РєРѕРјР°РЅРґСѓ, РµСЃР»Рё РѕРЅР° СЃРѕРѕС‚РІРµС‚СЃС‚РІСѓРµС‚ Р·Р°РґР°С‡Рµ."
