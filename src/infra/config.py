from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


MODELS_FILE = Path(__file__).resolve().parents[2] / "data" / "models.json"


def _load_models_file() -> dict[str, str]:
    """Загружает data/models.json если существует."""
    if MODELS_FILE.exists():
        try:
            import json
            data = json.loads(MODELS_FILE.read_text(encoding="utf-8"))
            return {k: str(v) for k, v in data.items() if isinstance(v, str)}
        except Exception:
            pass
    return {}


def _agent_model(agent_key: str, default: str) -> str:
    """Возвращает модель для агента: env → models.json → default."""
    env_val = os.getenv(f"AGENT_MODEL_{agent_key.upper()}")
    if env_val:
        return env_val
    return _load_models_file().get(agent_key, default)


@dataclass(slots=True)
class Settings:
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud"))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    request_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT", "120")))
    max_steps: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_STEPS", "100")))
    max_consecutive_errors: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_ERRORS", "2")))
    log_dir: Path = field(default_factory=lambda: Path(os.getenv("AGENT_LOG_DIR", "logs")))
    memory_file: Path = field(default_factory=lambda: Path(os.getenv("AGENT_MEMORY_FILE", "data/chat-memory.json")))
    workspace_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    telegram_api_id: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_API_ID"))
    telegram_api_hash: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH"))
    telegram_session_path: str = field(default_factory=lambda: os.getenv("TELEGRAM_SESSION_PATH", "data/telegram_session"))
    user_name: str = field(default_factory=lambda: os.getenv("USER_NAME", "Пользователь"))
    sub_agent_max_steps: int = field(default_factory=lambda: int(os.getenv("SUB_AGENT_MAX_STEPS", "50")))
    sub_agent_memory_dir: Path = field(default_factory=lambda: Path(os.getenv("SUB_AGENT_MEMORY_DIR", "data/agents")))
    num_ctx: int = field(default_factory=lambda: int(os.getenv("OLLAMA_NUM_CTX", "32768")))

    def get_model(self, agent_key: str) -> str:
        """Возвращает модель для конкретного агента (director/file/system/telegram/web)."""
        return _agent_model(agent_key, self.model)

    @property
    def allowed_roots(self) -> list[Path]:
        user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
        return [
            user_profile / "Desktop",
            user_profile / "Documents",
            user_profile / "Downloads",
            Path("D:/"),
            Path("D:/Programs"),
            Path("D:/Games"),
        ]


def get_settings() -> Settings:
    return Settings()
