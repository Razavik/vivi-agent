from __future__ import annotations

import json
from pathlib import Path

import tiktoken
from src.agent.state import SessionState


def load_system_prompt() -> str:
    prompt_path = Path(__file__).resolve().parents[2] / "prompts" / "system_prompt.txt"
    return prompt_path.read_text(encoding="utf-8")




def count_tokens(messages: list[dict[str, str]], model: str = "gemma4:31b-cloud") -> int:
    """Подсчитывает количество токенов в сообщениях."""
    try:
        # Используем cl100k_base как универсальный токенизатор (для большинства моделей)
        encoding = tiktoken.get_encoding("cl100k_base")
        total_tokens = 0
        for message in messages:
            total_tokens += len(encoding.encode(message.get("content", "")))
        return total_tokens
    except Exception:
        # Если tiktoken недоступен, возвращаем оценку (примерно 4 символа = 1 токен)
        total_chars = sum(len(m.get("content", "")) for m in messages)
        return total_chars // 4


def build_messages(state: SessionState, tool_descriptions: list[dict[str, object]], workspace_root: str, user_name: str = "Пользователь", available_agents: list[dict[str, str]] | None = None, images: list[str] | None = None) -> tuple[list[dict[str, object]], int]:
    system_prompt = load_system_prompt()

    # Добавляем критические инструкции в payload
    critical_instructions = """
КРИТИЧЕСКИ ВАЖНО:
1. Если инструмент вернул ОШИБКУ, объясни пользователю причину простым языком и попробуй ДРУГОЙ подход. Измени аргументы (например, другое название приложения) или используй другой инструмент.
2. Не повторяй тот же самый вызов после ошибки - сразу меняй тактику.
3. Если данные успешно получены, в следующем шаге используй finish_task (или send_message, если работа продолжается).
4. Параметр summary (или message) должен содержать ПОЛНЫЙ ответ с конкретными данными из observations.
5. Summary (и message в send_message) можно оформлять markdown-подобно для UI: использовать заголовки #, ##, списки -, 1., **жирный текст**, `inline code` и блоки кода ``` ```.
6. Форматируй только текст для пользователя. Сам JSON-ответ модели должен оставаться строго валидным JSON.
7. ЗАПРЕЩЕНО упоминать инструменты которых нет в списке "tools" - даже в summary или message. Используй только те инструменты, что реально доступны в списке tools.
8. При записи текста в файл через PowerShell не используй `Set-Content` или `Add-Content` с `-Encoding UTF8`.
9. Для записи текста через PowerShell предпочитай `[System.IO.File]::WriteAllText(...)` и `[System.IO.File]::AppendAllText(...)` с `[System.Text.UTF8Encoding]::new($false)`.
10. Для переносов строк в строках PowerShell не используй буквальные `\n`. Используй PowerShell-последовательности `` `n `` или `` `r`n ``.
11. Если ответ содержит код, команды, конфигурацию или пример разметки, оформляй их в fenced code blocks через ```...```; для коротких вставок используй inline-code через `...`.
"""

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
        "available_agents": available_agents or [],
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
