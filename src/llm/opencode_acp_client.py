from __future__ import annotations

import json

from src.llm.acp_base import AcpClient

OPENCODE_ACP_MODEL_PREFIX = "opencode:"

# opencode/deepseek-v4-flash-free репортило size=200000 через usage_update —
# запасное значение, пока реальный размер контекста для выбранной модели ещё
# не пришёл (у разных моделей/провайдеров он разный, в отличие от Codex).
DEFAULT_OPENCODE_NUM_CTX = 200_000


def is_opencode_model(model: str) -> bool:
    return model.startswith(OPENCODE_ACP_MODEL_PREFIX)


def strip_opencode_prefix(model: str) -> str:
    return (
        model[len(OPENCODE_ACP_MODEL_PREFIX):]
        if is_opencode_model(model)
        else model
    )


class OpenCodeAcpClient(AcpClient):
    """Клиент к моделям OpenCode через нативный `opencode acp` сервер.

    В отличие от Codex, OpenCode сам говорит по ACP без стороннего моста —
    и даёт доступ не только к моделям через уже залогиненный OpenAI-аккаунт
    (opencode auth login), но и к собственным бесплатным моделям OpenCode
    (opencode/deepseek-v4-flash-free, opencode/hy3-free и т.п. — cost: 0,
    не требуют дополнительного логина).

    Модель здесь — это provider/model напрямую (например
    "opencode:openai/gpt-5.6-sol" или "opencode:opencode/deepseek-v4-flash-free"),
    выбирается RPC-вызовом session/set_config_option после создания сессии
    (см. _after_session_new) — в отличие от Codex, где выбор идёт через
    переменную окружения при старте процесса.
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
            command=command or ["opencode", "acp"],
            timeout_seconds=timeout_seconds,
            cwd=cwd,
            default_num_ctx=DEFAULT_OPENCODE_NUM_CTX,
            error_label="OpenCode ACP",
        )

    def _extra_env(self) -> dict[str, str]:
        # КРИТИЧНО: в отличие от Codex (там sandbox_mode/approval_policy
        # запрещают выполнение), OpenCode по умолчанию реально выполняет
        # свои встроенные инструменты (bash/edit/write/...) — проверено
        # вживую: без этой настройки модель буквально запускала echo test
        # через настоящий bash. Этот клиент используется только для
        # текстовых ответов (chat/plan_next_step), поэтому все permission
        # запрещаем через OPENCODE_CONFIG_CONTENT (аналог CODEX_CONFIG),
        # не трогая глобальный конфиг пользователя (~/.config/opencode).
        return {
            "OPENCODE_CONFIG_CONTENT": json.dumps({"permission": {"*": "deny"}}),
        }

    def _after_session_new(self, session_id: str) -> None:
        provider_model = strip_opencode_prefix(self.model)
        self._rpc(
            "session/set_config_option",
            {"sessionId": session_id, "configId": "model", "value": provider_model},
        )
