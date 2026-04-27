from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


MODELS_FILE = Path(__file__).resolve().parents[2] / "data" / "models.json"
TOOLS_CONFIG_FILE = Path(__file__).resolve().parents[2] / "data" / "tools.json"
AGENTS_FILE = Path(__file__).resolve().parents[2] / "data" / "agents.json"
AVAILABLE_MODELS_FILE = Path(__file__).resolve().parents[2] / "data" / "available_models.json"
USER_PROFILE_FILE = Path(__file__).resolve().parents[2] / "data" / "user_profile.json"

DIRECTOR_REQUIRED_TOOLS = {
    "delegate_task",
    "delegate_parallel",
    "send_message",
    "finish_task",
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


AgentConfig = dict[str, object]  # конфигурация одного агента
AgentsConfig = dict[str, AgentConfig]  # все агенты


def _load_agents_config() -> AgentsConfig:
    """Загружает data/agents.json."""
    if AGENTS_FILE.exists():
        try:
            import json

            data = json.loads(AGENTS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return data
        except Exception:
            pass
    return {}


def _save_agents_config(config: AgentsConfig) -> None:
    """Сохраняет конфигурацию агентов в data/agents.json."""
    try:
        import json

        AGENTS_FILE.parent.mkdir(parents=True, exist_ok=True)
        AGENTS_FILE.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


ToolConfig = dict[str, dict[str, bool]]  # agent_name -> {tool_name: enabled}


def _load_tools_config() -> ToolConfig:
    """Загружает data/tools.json если существует. Возвращает {agent: {tool: enabled}}."""
    if TOOLS_CONFIG_FILE.exists():
        try:
            import json

            data = json.loads(TOOLS_CONFIG_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    agent: {tool: bool(enabled) for tool, enabled in tools.items() if isinstance(enabled, (bool, int))}
                    for agent, tools in data.items()
                    if isinstance(tools, dict)
                }
        except Exception:
            pass
    return {}


def _save_tools_config(config: ToolConfig) -> None:
    """Сохраняет конфигурацию инструментов в data/tools.json."""
    try:
        import json

        TOOLS_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
        TOOLS_CONFIG_FILE.write_text(
            json.dumps(config, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


UserProfile = dict[str, str]  # профиль пользователя


def _load_user_profile() -> UserProfile:
    """Загружает data/user_profile.json."""
    if USER_PROFILE_FILE.exists():
        try:
            import json

            data = json.loads(USER_PROFILE_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                return {
                    key: str(value) if isinstance(value, str) else ""
                    for key, value in data.items()
                    if isinstance(value, (str, int, float, bool))
                }
        except Exception:
            pass
    return {"name": "Пользователь", "role": "", "preferences": "", "context": ""}


def _save_user_profile(profile: UserProfile) -> None:
    """Сохраняет профиль пользователя в data/user_profile.json."""
    try:
        import json

        USER_PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
        USER_PROFILE_FILE.write_text(
            json.dumps(profile, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except Exception:
        pass


def is_tool_enabled(agent: str, tool_name: str, default: bool = True) -> bool:
    """Проверяет включен ли инструмент для агента. По умолчанию True (все включены)."""
    config = _load_tools_config()
    agent_tools = config.get(agent, {})
    return agent_tools.get(tool_name, default)


def set_tool_enabled(agent: str, tool_name: str, enabled: bool) -> None:
    """Включает/выключает инструмент для агента."""
    config = _load_tools_config()
    if agent not in config:
        config[agent] = {}
    config[agent][tool_name] = enabled
    _save_tools_config(config)


def get_agent_tools_config(agent: str) -> dict[str, bool]:
    """Возвращает конфигурацию инструментов для агента."""
    config = _load_tools_config()
    return config.get(agent, {})


def load_available_models() -> list[str]:
    """Загружает data/available_models.json — список моделей для выбора."""
    if AVAILABLE_MODELS_FILE.exists():
        try:
            import json
            data = json.loads(AVAILABLE_MODELS_FILE.read_text(encoding="utf-8"))
            if isinstance(data, list):
                return [str(m) for m in data if isinstance(m, str)]
        except Exception:
            pass
    return []


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
    """Возвращает модель для агента: env → models.json → default. Пустая строка = default."""
    env_val = os.getenv(f"AGENT_MODEL_{agent_key.upper()}")
    if env_val:
        return env_val
    val = _load_models_file().get(agent_key, "")
    return val if val else default


@dataclass(slots=True)
class Settings:
    model: str = field(default_factory=lambda: os.getenv("OLLAMA_MODEL", "gemma4:31b-cloud"))
    ollama_base_url: str = field(default_factory=lambda: os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434"))
    request_timeout_seconds: int = field(default_factory=lambda: int(os.getenv("OLLAMA_TIMEOUT", "120")))
    max_steps: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_STEPS", "100")))
    max_consecutive_errors: int = field(default_factory=lambda: int(os.getenv("AGENT_MAX_ERRORS", "2")))
    log_dir: Path = field(default_factory=lambda: Path(os.getenv("AGENT_LOG_DIR", "logs")))
    memory_file: Path = field(default_factory=lambda: Path(os.getenv("AGENT_MEMORY_FILE", "data/chat-memory.json")))
    workspace_root: Path = field(default_factory=lambda: Path(os.getenv("AGENT_WORKSPACE", "D:/Projects")))
    telegram_api_id: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_API_ID"))
    telegram_api_hash: str | None = field(default_factory=lambda: os.getenv("TELEGRAM_API_HASH"))
    user_profile: UserProfile = field(default_factory=_load_user_profile)
    telegram_session_path: str = field(default_factory=lambda: os.getenv("TELEGRAM_SESSION_PATH", "data/telegram_session"))
    user_name: str = field(default_factory=lambda: os.getenv("USER_NAME", "Пользователь"))
    sub_agent_max_steps: int = field(default_factory=lambda: int(os.getenv("SUB_AGENT_MAX_STEPS", "50")))
    sub_agent_memory_dir: Path = field(default_factory=lambda: Path(os.getenv("SUB_AGENT_MEMORY_DIR", "data/agents")))
    num_ctx: int = field(default_factory=lambda: int(os.getenv("OLLAMA_NUM_CTX", "32768")))
    ollama_api_key: str | None = field(default_factory=lambda: os.getenv("OLLAMA_API_KEY"))
    ollama_keep_alive: str = field(default_factory=lambda: os.getenv("OLLAMA_KEEP_ALIVE", "10m"))
    ollama_think: bool = field(default_factory=lambda: os.getenv("OLLAMA_THINK", "").lower() in ("1", "true", "yes"))

    def get_model(self, agent_key: str) -> str:
        """Возвращает модель для конкретного агента (director/file/system/telegram/web)."""
        return _agent_model(agent_key, self.model)

    @property
    def allowed_roots(self) -> list[Path]:
        user_profile = Path(os.environ.get("USERPROFILE", Path.home()))
        return [
            self.workspace_root,
            user_profile / "Desktop",
            user_profile / "Documents",
            user_profile / "Downloads",
        ]


def get_settings() -> Settings:
    return Settings()
