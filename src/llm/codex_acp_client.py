from __future__ import annotations

import json
import re
from typing import Any

from src.llm.acp_base import AcpClient

# modelId из ACP session/new выглядит как "gpt-5.6-terra[medium]" — базовая
# модель + уровень reasoning-effort в квадратных скобках.
_MODEL_ID_RE = re.compile(r"^(?P<base>[^\[]+)(\[(?P<effort>[a-zA-Z]+)\])?$")

CODEX_ACP_MODEL_PREFIX = "codex:"

# Реальный размер контекстного окна, который отдаёт сам ACP-мост через
# session/update -> usage_update.size (см. AcpClient._prompt) — проверено
# эмпирически одинаковым для всех моделей аккаунта (gpt-5.4-mini/gpt-5.5/
# gpt-5.6-terra), это, судя по всему, потолок уровня ChatGPT-подписки, а не
# модели. Используется как запасное значение, пока клиент ещё не сделал ни
# одного реального запроса.
DEFAULT_CODEX_NUM_CTX = 258400


def is_codex_model(model: str) -> bool:
    return model.startswith(CODEX_ACP_MODEL_PREFIX)


def strip_codex_prefix(model: str) -> str:
    return model[len(CODEX_ACP_MODEL_PREFIX):] if is_codex_model(model) else model


class CodexAcpClient(AcpClient):
    """Клиент к моделям Codex/ChatGPT через локальный ACP-мост
    (@agentclientprotocol/codex-acp): переиспользует уже существующий
    ChatGPT-логин из ~/.codex (тот же, что у официального Codex CLI и
    десктоп-приложения) вместо отдельного API-ключа/биллинга.

    Модель выбирается через переменную окружения CODEX_CONFIG при старте
    подпроцесса (см. _extra_env) — в отличие от OpenCode, где это делается
    RPC-вызовом после создания сессии (см. opencode_acp_client.py).
    """

    def __init__(
        self,
        model: str,
        timeout_seconds: int | None = None,
        cwd: str | None = None,
        command: list[str] | None = None,
    ) -> None:
        super().__init__(
            model=model,
            command=command or ["npx", "-y", "@agentclientprotocol/codex-acp"],
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            default_num_ctx=DEFAULT_CODEX_NUM_CTX,
            error_label="Codex ACP",
        )

    @staticmethod
    def _parse_model(model: str) -> tuple[str, str | None]:
        match = _MODEL_ID_RE.match(strip_codex_prefix(model))
        if not match:
            return model, None
        return match.group("base"), match.group("effort")

    def _extra_env(self) -> dict[str, str]:
        base_model, effort = self._parse_model(self.model)
        config: dict[str, Any] = {
            # Клиент используется только для текстовых ответов (single-shot
            # chat / JSON action-step), поэтому собственные инструменты
            # Codex (shell, apply_patch, ...) отключены на уровне sandbox —
            # модель не должна трогать файловую систему пользователя.
            "sandbox_mode": "read-only",
            "approval_policy": "never",
            "model": base_model,
        }
        if effort:
            config["model_reasoning_effort"] = effort
        return {"CODEX_CONFIG": json.dumps(config)}
