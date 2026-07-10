from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.infra.config import is_pc_control_mode


ROOT = Path(__file__).resolve().parents[2]
CORE_SKILLS_DIR = ROOT / "prompts" / "operator_skills"
ORCHESTRATOR_CORE_SKILLS_DIR = ROOT / "prompts" / "orchestrator_skills"
MARKET_SKILLS_DIR = ROOT / "prompts" / "operator_skill_market"
ORCHESTRATOR_MARKET_SKILLS_DIR = ROOT / "prompts" / "orchestrator_skill_market"
USER_SKILLS_DIR = ROOT / "data" / "operator_skills"
STATE_FILE = ROOT / "data" / "operator_skills.json"
MAX_OPERATOR_SKILLS_CHARS = 12000


@dataclass(frozen=True)
class OperatorSkill:
    id: str
    title: str
    body: str
    source: str
    path: Path
    enabled: bool
    installed: bool
    requires: list[str]
    tags: list[str]
    modes: list[str]
    description: str


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9а-яА-ЯёЁ_-]+", "-", value.strip()).strip("-").lower()
    return slug or "skill"


def _read_state() -> dict[str, Any]:
    from src.infra.config import _read_json_cached

    data = _read_json_cached(STATE_FILE)
    return data if isinstance(data, dict) else {"disabled": [], "installed_market": []}


def _active_mode() -> str:
    return "pc" if is_pc_control_mode() else "orchestrator"


def _skill_matches_mode(modes: list[str], active_mode: str) -> bool:
    normalized = {mode.strip().lower() for mode in modes if mode.strip()}
    return not normalized or active_mode in normalized


def _write_state(data: dict[str, Any]) -> None:
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


# Кэш разобранных скиллов по (path, mtime_ns). Инвалидируется при изменении файла.
# Хранит частично заполненный OperatorSkill (без source/enabled/installed —
# эти поля зависят от контекста вызова и подставляются в _parse_skill).
_parsed_skill_cache: dict[Path, tuple[int, dict[str, Any] | None]] = {}


def _parse_skill_fields(path: Path) -> dict[str, Any] | None:
    """Разбирает содержимое скилла в поля (с кэшированием по mtime)."""
    try:
        mtime = path.stat().st_mtime_ns
    except OSError:
        _parsed_skill_cache.pop(path, None)
        return None
    cached = _parsed_skill_cache.get(path)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    fields = _parse_skill_fields_uncached(path)
    _parsed_skill_cache[path] = (mtime, fields)
    return fields


def _parse_skill_fields_uncached(path: Path) -> dict[str, Any] | None:
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None

    lines = raw.splitlines()
    requires: list[str] = []
    tags: list[str] = []
    modes: list[str] = []
    body_start = 0
    for index, line in enumerate(lines[:10]):
        lower = line.lower()
        if lower.startswith("requires:"):
            requires = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
            body_start = max(body_start, index + 1)
        elif lower.startswith("tags:"):
            tags = [part.strip() for part in line.split(":", 1)[1].split(",") if part.strip()]
            body_start = max(body_start, index + 1)
        elif lower.startswith("modes:"):
            modes = [part.strip().lower() for part in line.split(":", 1)[1].split(",") if part.strip()]
            body_start = max(body_start, index + 1)

    body = "\n".join(lines[body_start:]).strip()
    title = path.stem
    title_found = False
    description = ""
    for line in body.splitlines():
        clean = line.strip().lstrip("#").strip()
        if clean:
            if not title_found:
                title = clean
                title_found = True
            elif not description.startswith("Цель:"):
                description = clean
                break
            if clean.startswith("Цель:"):
                description = clean
                break

    return {
        "id": path.stem,
        "title": title,
        "body": body,
        "path": path,
        "requires": requires,
        "tags": tags,
        "modes": modes,
        "description": description,
    }


def _parse_skill(path: Path, source: str, enabled: bool, installed: bool) -> OperatorSkill | None:
    fields = _parse_skill_fields(path)
    if fields is None:
        return None
    return OperatorSkill(
        source=source,
        enabled=enabled,
        installed=installed,
        **fields,
    )


def _load_dir(directory: Path, source: str, disabled: set[str], installed: bool, active_mode: str) -> list[OperatorSkill]:
    if not directory.exists():
        return []
    result: list[OperatorSkill] = []
    for path in sorted(directory.glob("*.md")):
        skill_id = path.stem
        skill = _parse_skill(path, source, skill_id not in disabled, installed)
        if skill is not None and _skill_matches_mode(skill.modes, active_mode):
            result.append(skill)
    return result


def list_operator_skills() -> dict[str, Any]:
    state = _read_state()
    disabled = {str(item) for item in state.get("disabled", []) if isinstance(item, str)}
    installed_market = {str(item) for item in state.get("installed_market", []) if isinstance(item, str)}
    active_mode = _active_mode()
    core_dir = CORE_SKILLS_DIR if active_mode == "pc" else ORCHESTRATOR_CORE_SKILLS_DIR
    market_dir = MARKET_SKILLS_DIR if active_mode == "pc" else ORCHESTRATOR_MARKET_SKILLS_DIR

    installed = [
        *_load_dir(core_dir, "core", disabled, True, active_mode),
        *_load_dir(USER_SKILLS_DIR, "custom", disabled, True, active_mode),
    ]

    market: list[dict[str, Any]] = []
    for skill in _load_dir(market_dir, "market", disabled, False, active_mode):
        market.append(_skill_to_payload(skill, include_body=True) | {"installed": skill.id in installed_market})

    return {
        "skills": [_skill_to_payload(skill, include_body=True) for skill in installed],
        "market": market,
        "limits": {"max_chars": MAX_OPERATOR_SKILLS_CHARS},
        "mode": active_mode,
    }


def _skill_to_payload(skill: OperatorSkill, include_body: bool = False) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "id": skill.id,
        "title": skill.title,
        "description": skill.description,
        "source": skill.source,
        "enabled": skill.enabled,
        "installed": skill.installed,
        "requires": skill.requires,
        "tags": skill.tags,
        "modes": skill.modes,
        "path": str(skill.path),
    }
    if include_body:
        payload["body"] = skill.body
    return payload


def set_operator_skill_enabled(skill_id: str, enabled: bool) -> dict[str, Any]:
    state = _read_state()
    disabled = {str(item) for item in state.get("disabled", []) if isinstance(item, str)}
    if enabled:
        disabled.discard(skill_id)
    else:
        disabled.add(skill_id)
    state["disabled"] = sorted(disabled)
    _write_state(state)
    return list_operator_skills()


def create_custom_operator_skill(title: str, body: str, requires: list[str] | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    clean_title = title.strip()
    clean_body = body.strip()
    if not clean_title or not clean_body:
        return {"error": "title and body are required"}

    USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    base = _slugify(clean_title)
    path = USER_SKILLS_DIR / f"{base}.md"
    index = 2
    while path.exists():
        path = USER_SKILLS_DIR / f"{base}-{index}.md"
        index += 1

    header: list[str] = []
    if requires:
        header.append("requires: " + ", ".join(item.strip() for item in requires if item.strip()))
    if tags:
        header.append("tags: " + ", ".join(item.strip() for item in tags if item.strip()))
    header.append("modes: " + _active_mode())
    content = "\n".join([*header, "", f"# {clean_title}", "", clean_body]).strip() + "\n"
    path.write_text(content, encoding="utf-8")
    return list_operator_skills()


def update_custom_operator_skill(skill_id: str, title: str, body: str, requires: list[str] | None = None, tags: list[str] | None = None) -> dict[str, Any]:
    path = USER_SKILLS_DIR / f"{Path(skill_id).stem}.md"
    if not path.exists():
        return {"error": "custom skill not found"}
    header: list[str] = []
    if requires:
        header.append("requires: " + ", ".join(item.strip() for item in requires if item.strip()))
    if tags:
        header.append("tags: " + ", ".join(item.strip() for item in tags if item.strip()))
    header.append("modes: " + _active_mode())
    content = "\n".join([*header, "", f"# {title.strip() or skill_id}", "", body.strip()]).strip() + "\n"
    path.write_text(content, encoding="utf-8")
    return list_operator_skills()


def delete_custom_operator_skill(skill_id: str) -> dict[str, Any]:
    path = USER_SKILLS_DIR / f"{Path(skill_id).stem}.md"
    if not path.exists():
        return {"error": "custom skill not found"}
    path.unlink()
    return list_operator_skills()


def install_market_operator_skill(skill_id: str) -> dict[str, Any]:
    active_mode = _active_mode()
    market_dir = MARKET_SKILLS_DIR if active_mode == "pc" else ORCHESTRATOR_MARKET_SKILLS_DIR
    source = market_dir / f"{Path(skill_id).stem}.md"
    if not source.exists():
        return {"error": "market skill not found"}
    USER_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    target = USER_SKILLS_DIR / source.name
    index = 2
    while target.exists():
        target = USER_SKILLS_DIR / f"{source.stem}-{index}.md"
        index += 1
    shutil.copyfile(source, target)
    state = _read_state()
    installed = {str(item) for item in state.get("installed_market", []) if isinstance(item, str)}
    installed.add(skill_id)
    state["installed_market"] = sorted(installed)
    _write_state(state)
    return list_operator_skills()


def build_operator_skills_block(tool_names: set[str]) -> str:
    state = list_operator_skills()
    chunks: list[str] = []
    total = 0
    for raw in state.get("skills", []):
        if not raw.get("enabled"):
            continue
        required = [str(item) for item in raw.get("requires", []) if isinstance(item, str)]
        if required and any(name not in tool_names for name in required):
            continue
        body = str(raw.get("body", "")).strip()
        if not body:
            continue
        chunk = f"### {raw.get('id')}\n{body}"
        if total + len(chunk) > MAX_OPERATOR_SKILLS_CHARS:
            break
        chunks.append(chunk)
        total += len(chunk)
    if not chunks:
        return ""
    return "== НАВЫКИ ОПЕРАТОРА ==\n" + "\n\n".join(chunks)
