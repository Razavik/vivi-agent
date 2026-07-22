from __future__ import annotations

from src.infra.config import Settings
from src.llm import ollama_client as _ollama_module
from src.llm.codex_acp_client import CodexAcpClient, is_codex_model
from src.llm.ollama_client import OllamaClient
from src.llm.opencode_acp_client import OpenCodeAcpClient, is_opencode_model

LLMClient = OllamaClient | CodexAcpClient | OpenCodeAcpClient


def create_llm_client(settings: Settings, agent_key: str) -> LLMClient:
    """Создаёт клиента для модели, выбранной для agent_key в data/models.json.

    Модели с префиксом "codex:" (например "codex:gpt-5.6-terra[medium]")
    идут через локальный ACP-мост к аккаунту ChatGPT/Codex пользователя;
    "opencode:" (например "opencode:openai/gpt-5.6-sol" или
    "opencode:opencode/deepseek-v4-flash-free") — через нативный ACP-сервер
    OpenCode; всё остальное — через Ollama, как раньше. Выбор совмещён в
    одном и том же списке моделей в UI, а не отдельным переключателем
    провайдера.
    """
    model = settings.get_model(agent_key)
    if is_codex_model(model):
        return CodexAcpClient(
            model=model,
            timeout_seconds=settings.request_timeout_seconds,
            cwd=str(settings.workspace_root),
        )
    if is_opencode_model(model):
        return OpenCodeAcpClient(
            model=model,
            timeout_seconds=settings.request_timeout_seconds,
            cwd=str(settings.workspace_root),
        )
    # Через модуль, а не прямой импорт класса — тесты подменяют
    # src.llm.ollama_client.OllamaClient через monkeypatch, а он должен
    # резолвиться в момент вызова, а не быть захвачен на этапе импорта.
    return _ollama_module.OllamaClient(
        settings.ollama_base_url,
        model,
        settings.request_timeout_seconds,
        num_ctx=settings.num_ctx,
        api_key=settings.ollama_api_key,
        keep_alive=settings.ollama_keep_alive,
        think=settings.ollama_think,
    )
