from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

import tiktoken
from src.agent.state import SessionState
from src.infra.config import is_pc_control_mode
from src.infra.operator_skills import build_operator_skills_block


RUN_TOOL_NAMES = {
    "view_runs",
    "cancel_run",
    "pause_run",
    "resume_run",
    "message_run",
    "replace_task_run",
    "reprioritize_run",
    "get_world_state",
    "wait_for_event",
}

DELEGATION_TOOL_NAMES = {"delegate_task", "delegate_parallel"}
SCREEN_TOOL_NAMES = {"get_screen_info", "take_screenshot", "read_image"}
MOUSE_TOOL_NAMES = {
    "system_mouse_move",
    "system_mouse_nudge",
    "system_mouse_click",
    "system_mouse_double_click",
    "system_mouse_scroll",
    "system_mouse_drag",
}
UI_AUTOMATION_TOOL_NAMES = {"list_ui_elements", "click_ui_element", "focus_ui_element"}
KEYBOARD_TOOL_NAMES = {"system_type_text", "system_key_press"}
PC_TOOL_NAMES = SCREEN_TOOL_NAMES | MOUSE_TOOL_NAMES | UI_AUTOMATION_TOOL_NAMES | KEYBOARD_TOOL_NAMES
MEMORY_TOOL_NAMES = {"get_agent_memory"}


@lru_cache(maxsize=8)
def _read_prompt_template(prompt_name: str, mtime_ns: int) -> str:
    """Читает шаблон системного промпта. mtime_ns в ключе кэша обеспечивает
    перечитывание при изменении файла."""
    prompt_path = Path(__file__).resolve().parents[2] / "prompts" / prompt_name
    return prompt_path.read_text(encoding="utf-8")


def load_system_prompt(
    user_name: str = "Пользователь",
    user_role: str = "",
    user_preferences: str = "",
    user_context: str = "",
    pc_control_mode: bool = False,
) -> str:
    prompt_name = "system_prompt_pc.txt" if pc_control_mode else "system_prompt_orchestrator.txt"
    prompt_path = Path(__file__).resolve().parents[2] / "prompts" / prompt_name
    try:
        mtime_ns = prompt_path.stat().st_mtime_ns
    except OSError:
        mtime_ns = 0
    prompt = _read_prompt_template(prompt_name, mtime_ns)
    prompt = prompt.replace("{user_name}", user_name)
    prompt = prompt.replace("{user_role}", user_role)
    prompt = prompt.replace("{user_preferences}", user_preferences)
    prompt = prompt.replace("{user_context}", user_context)
    return prompt


def build_dynamic_system_prompt(
    base_prompt: str,
    tool_descriptions: list[dict[str, object]],
    available_agents: list[dict[str, str]] | None,
) -> str:
    tool_names = {str(tool.get("name", "")) for tool in tool_descriptions if tool.get("name")}
    blocks = [_build_available_actions_block(tool_names)]
    skills_block = build_operator_skills_block(tool_names)
    if skills_block:
        blocks.append(skills_block)
    if tool_names & DELEGATION_TOOL_NAMES:
        blocks.append(_build_delegation_block(tool_names, available_agents or []))
    if tool_names & RUN_TOOL_NAMES:
        blocks.append(_build_run_tools_block(tool_names))
    if tool_names & PC_TOOL_NAMES:
        blocks.append(_build_pc_tools_block(tool_names))
    if tool_names & MEMORY_TOOL_NAMES:
        blocks.append(_build_memory_tools_block())
    return "\n\n".join([base_prompt.strip(), *blocks]).strip()


def _build_available_actions_block(tool_names: set[str]) -> str:
    names = ", ".join(sorted(tool_names)) if tool_names else "нет доступных инструментов"
    return (
        "== ДОСТУПНЫЕ ACTION ==\n"
        f"- В этом запуске доступны только эти action: {names}.\n"
        "- Любой action вне этого списка запрещён.\n"
        "- Если finish_task доступен, используй его для финального ответа или честной остановки."
    )


def _build_delegation_block(tool_names: set[str], available_agents: list[dict[str, str]]) -> str:
    agents = ", ".join(str(agent.get("name", "")) for agent in available_agents if agent.get("name"))
    lines = [
        "== ДЕЛЕГИРОВАНИЕ ==",
        "- Делегирование доступно только через action, перечисленные ниже.",
    ]
    if "delegate_task" in tool_names:
        lines.append("- delegate_task(agent_name, task, images?): поручить задачу одному доступному саб-агенту.")
    if "delegate_parallel" in tool_names:
        lines.append("- delegate_parallel(tasks): запустить несколько независимых поручений.")
    lines.extend(
        [
            f"- Доступные саб-агенты: {agents or 'нет доступных саб-агентов'}.",
            "- Делегируй только агентам из available_agents.",
            "- Не делегируй задачу агенту, у которого по описанию нет нужных возможностей.",
            "- Каждая делегация должна содержать цель, границы ответственности, что проверить и формат результата.",
        ]
    )
    return "\n".join(lines)


def _build_run_tools_block(tool_names: set[str]) -> str:
    descriptions = {
        "view_runs": "посмотреть активные запуски саб-агентов",
        "cancel_run": "отменить активный запуск",
        "pause_run": "поставить запуск на паузу",
        "resume_run": "продолжить запуск",
        "message_run": "передать сообщение в активный запуск",
        "replace_task_run": "заменить задачу активного запуска",
        "reprioritize_run": "изменить приоритет запуска",
        "get_world_state": "посмотреть состояние запусков, ожиданий и зависимостей",
        "wait_for_event": "дождаться события или завершения",
    }
    lines = ["== УПРАВЛЕНИЕ ЗАПУСКАМИ =="]
    for name in sorted(tool_names & RUN_TOOL_NAMES):
        lines.append(f"- {name}: {descriptions[name]}.")
    lines.extend(
        [
            "- Используй эти action только для реально существующих active_runs из payload.",
            "- Если нужного run-action нет в списке, не обещай управлять запуском этим способом.",
        ]
    )
    return "\n".join(lines)


def _build_pc_tools_block(tool_names: set[str]) -> str:
    lines = ["== РАБОТА С ПК И ЭКРАНОМ =="]
    if tool_names & SCREEN_TOOL_NAMES:
        lines.append("- Доступен визуальный анализ через screen/image tools. Перед точным действием наблюдай экран и при необходимости уточняй область.")
        if "get_screen_info" in tool_names:
            lines.append("- get_screen_info(): получить размеры экранов, активное окно и текущую позицию курсора.")
        if "take_screenshot" in tool_names:
            lines.append("- take_screenshot(x?, y?, width?, height?): получить текущий экран целиком или конкретную область для точности.")
        if "read_image" in tool_names:
            lines.append("- read_image(path): прочитать изображение по пути.")
    if tool_names & MOUSE_TOOL_NAMES:
        lines.append("- Доступны действия мышью. Предпочитай маленькие обратимые шаги и проверку результата.")
        if "system_mouse_move" in tool_names:
            lines.append("- system_mouse_move(x, y): реально переместить системный курсор Windows; после move автоматически будет приложен свежий crop вокруг курсора.")
        if "system_mouse_nudge" in tool_names:
            lines.append("- system_mouse_nudge(dx, dy): чуть сдвинуть курсор относительно текущей позиции; используй для точной коррекции по crop.")
        if "system_mouse_click" in tool_names:
            lines.append("- system_mouse_click(button?): выполнить клик в текущей позиции курсора. Не передавай x/y; сначала используй system_mouse_move. После click будет приложен crop вокруг курсора.")
        if "system_mouse_double_click" in tool_names:
            lines.append("- system_mouse_double_click(): выполнить двойной левый клик в текущей позиции курсора. Не передавай x/y; сначала используй system_mouse_move.")
        if "system_mouse_scroll" in tool_names:
            lines.append("- system_mouse_scroll(clicks, x?, y?): прокрутить колесо; отрицательные clicks вниз.")
        if "system_mouse_drag" in tool_names:
            lines.append("- system_mouse_drag(from_x, from_y, to_x, to_y, duration_ms?): перетащить элемент.")
    if tool_names & UI_AUTOMATION_TOOL_NAMES:
        lines.append("- Доступна Windows UI Automation. Это предпочтительный способ выбирать кнопки, поля ввода и пункты меню.")
        if "list_ui_elements" in tool_names:
            lines.append("- list_ui_elements(query?, max_results?, include_offscreen?): получить структурированные элементы активного окна с id, name, control_type, rect и clickable_point.")
        if "focus_ui_element" in tool_names:
            lines.append("- focus_ui_element(id): сфокусировать элемент из последнего list_ui_elements, особенно поле ввода перед набором текста.")
        if "click_ui_element" in tool_names:
            lines.append("- click_ui_element(id, button?): кликнуть элемент из последнего list_ui_elements без ручного подбора координат.")
    if tool_names & KEYBOARD_TOOL_NAMES:
        lines.append("- Доступен системный ввод с клавиатуры. Сначала убедись, что нужное поле в фокусе.")
        if "system_type_text" in tool_names:
            lines.append("- system_type_text(text, interval_ms?): ввести текст в активное поле.")
        if "system_key_press" in tool_names:
            lines.append("- system_key_press(key, repeats?): нажать клавишу или сочетание, например enter, tab, win+r, alt+tab.")
    lines.extend(
        [
            "- Не делай вид, что видишь экран, если screen tools недоступны.",
            "- Для клика используй цикл: get_screen_info/take_screenshot → system_mouse_move(x,y) → анализ crop после move → system_mouse_click(button?) → анализ crop после click.",
            "- Если доступны list_ui_elements/click_ui_element/focus_ui_element, сначала попробуй выбрать элемент структурно через UI Automation, а не по пикселям.",
            "- В crop центр фиолетового прицела показывает hotspot: именно центр прицела должен быть на поле ввода/кнопке.",
            "- Если прицел почти попал, используй system_mouse_nudge(dx,dy), а не новый абсолютный прыжок.",
            "- Не передавай координаты в system_mouse_click/system_mouse_double_click; эти actions нажимают только в текущей позиции курсора.",
            "- Не кликай вслепую: если цель не видна или координаты сомнительны, сначала сделай скриншот области.",
            "- После ввода текста, клика, drag или scroll всегда проверь результат отдельным наблюдением.",
            "- Рискованные действия требуют явного поручения пользователя или подтверждения.",
        ]
    )
    return "\n".join(lines)


def _build_memory_tools_block() -> str:
    return (
        "== ПАМЯТЬ АГЕНТОВ ==\n"
        "- get_agent_memory(agent?, limit?): посмотреть память доступного агента или сводку.\n"
        "- Используй память как справочный контекст, но текущие tools/available_agents важнее старых записей."
    )


def build_critical_instructions(tool_names: set[str]) -> str:
    lines = [
        "КРИТИЧЕСКИ ВАЖНО:",
        "1. Если инструмент вернул ОШИБКУ, объясни пользователю причину простым языком и попробуй ДРУГОЙ подход.",
        "2. Не повторяй тот же самый вызов после ошибки - сразу меняй тактику.",
        "3. Если данные успешно получены или нужно ответить пользователю, используй finish_task.",
        "4. Параметр summary должен содержать ПОЛНЫЙ, РАЗВЁРНУТЫЙ ответ. Не пиши короткий placeholder вместо реального ответа.",
        "5. Summary можно оформлять markdown-подобно для UI: заголовки, списки, inline-code и fenced code blocks.",
        "6. Форматируй только текст для пользователя. Сам JSON-ответ модели должен оставаться строго валидным JSON.",
        "7. ЗАПРЕЩЕНО упоминать инструменты которых нет в списке tools. Используй только реально доступные tools.",
        "8. Перед каждым action проверь, что action.name есть в текущем payload.tools.",
    ]
    next_number = 9
    if tool_names & DELEGATION_TOOL_NAMES:
        lines.append(
            f"{next_number}. Перед делегированием проверь сразу два условия: action делегирования есть в tools, а целевой агент есть в available_agents."
        )
        next_number += 1
    lines.extend(
        [
            f'{next_number}. Если возможности нет, используй finish_task со status="blocked" или status="done" и честно объясни ограничение.',
            f"{next_number + 1}. При записи текста в файл через PowerShell не используй `Set-Content` или `Add-Content` с `-Encoding UTF8`.",
            f"{next_number + 2}. Для записи текста через PowerShell предпочитай `[System.IO.File]::WriteAllText(...)` и `[System.IO.File]::AppendAllText(...)` с `[System.Text.UTF8Encoding]::new($false)`.",
            f"{next_number + 3}. Для переносов строк в строках PowerShell не используй буквальные `\\n`. Используй PowerShell-последовательности `` `n `` или `` `r`n ``.",
            f"{next_number + 4}. Если ответ содержит код, команды, конфигурацию или пример разметки, оформляй их в fenced code blocks через ```...```.",
            f"{next_number + 5}. Если в persistent_memory или chat_history у сообщения assistant есть interrupted_by_user=true, значит пользователь вручную оборвал генерацию; не считай такой ответ завершённым.",
        ]
    )
    return "\n".join(lines)



@lru_cache(maxsize=1)
def _token_encoding() -> "tiktoken.Encoding":
    # Используем cl100k_base как универсальный токенизатор (для большинства моделей).
    # Кэшируем — построение encoding относительно дорогое, а вызывается на каждом шаге.
    return tiktoken.get_encoding("cl100k_base")


def count_tokens(messages: list[dict[str, str]], model: str = "gemma4:31b-cloud") -> int:
    """Подсчитывает количество токенов в сообщениях."""
    try:
        encoding = _token_encoding()
        total_tokens = 0
        for message in messages:
            total_tokens += len(encoding.encode(message.get("content", "")))
        return total_tokens
    except Exception:
        # Если tiktoken недоступен, возвращаем оценку (примерно 4 символа = 1 токен)
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4


def build_messages(state: SessionState, tool_descriptions: list[dict[str, object]], workspace_root: str, user_name: str = "Пользователь", available_agents: list[dict[str, str]] | None = None, images: list[str] | None = None, active_runs: list[dict[str, Any]] | None = None, supervisor_observations: list[dict[str, Any]] | None = None, user_profile: dict[str, str] | None = None) -> tuple[list[dict[str, object]], int]:
    profile = user_profile or {}
    tool_names = {str(tool.get("name", "")) for tool in tool_descriptions if tool.get("name")}
    pc_mode = is_pc_control_mode()
    system_prompt = load_system_prompt(
        user_name=profile.get("name", user_name),
        user_role=profile.get("role", ""),
        user_preferences=profile.get("preferences", ""),
        user_context=profile.get("context", ""),
        pc_control_mode=pc_mode,
    )
    system_prompt = build_dynamic_system_prompt(system_prompt, tool_descriptions, available_agents)

    critical_instructions = build_critical_instructions(tool_names)
    visible_available_agents = (available_agents or []) if tool_names & DELEGATION_TOOL_NAMES else []
    visible_active_runs = (active_runs or []) if tool_names & RUN_TOOL_NAMES else []
    visible_supervisor_observations = (supervisor_observations or []) if tool_names & RUN_TOOL_NAMES else []

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).astimezone()
    current_date = now.strftime("%d.%m.%Y %H:%M (%A)")

    user_payload = {
        "current_datetime": current_date,
        "goal": state.user_goal,
        "persistent_memory": state.compact_memory(),
        "chat_history": state.compact_chat_history(),
        "current_plan": state.compact_plan(),
        "tools": tool_descriptions,
        "recent_observations": state.compact_observations(),
        "critical_instructions": critical_instructions,
        "workspace_root": workspace_root,
        "user_name": user_name,
        "available_agents": visible_available_agents,
        "active_runs": visible_active_runs,
        "supervisor_observations": visible_supervisor_observations,
    }
    user_message: dict[str, object] = {
        "role": "user",
        "content": json.dumps(user_payload, ensure_ascii=False, indent=2),
    }
    if images:
        user_message["images"] = images
    messages = [
        {"role": "system", "content": system_prompt},
        user_message,
    ]
    token_count = count_tokens(messages)
    return messages, token_count
