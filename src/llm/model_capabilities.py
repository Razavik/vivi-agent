from __future__ import annotations

from src.llm.codex_acp_client import is_codex_model
from src.llm.opencode_acp_client import is_opencode_model

# Известные Ollama-теги с подтверждённой (не)поддержкой изображений.
# Ключи — точное совпадение с data/models.json / data/available_models.json.
_OLLAMA_VISION: dict[str, bool] = {
    "gemma4:31b-cloud": True,
    "gemma4:e4b": True,
    # gpt-oss — открытые веса OpenAI, текстовые модели без vision.
    "gpt-oss:120b-cloud": False,
}

# Бесплатные модели самого OpenCode — проверено вживую реальным запросом с
# картинкой (не по документации/названию — она разошлась с фактом для
# hy3-free и deepseek-v4-flash-free: обе честно ответили "не поддерживаю
# изображения", несмотря на то что должны). Единственная, которая реально
# определила цвет тестовой картинки — mimo-v2.5-free.
_OPENCODE_FREE_VISION: dict[str, bool] = {
    "big-pickle": False,
    "deepseek-v4-flash-free": False,
    "hy3-free": False,
    "mimo-v2.5-free": True,
    "nemotron-3-ultra-free": False,
    "north-mini-code-free": False,
}

# Эвристика для неизвестных/пользовательских Ollama-тегов: по частым
# маркерам vision-моделей в имени (vl, vision, llava, pixtral, multimodal).
_VISION_NAME_HINTS = ("vl", "vision", "llava", "pixtral", "multimodal", "omni")


def supports_vision(model: str) -> bool:
    """Определяет, умеет ли модель принимать изображения на вход.

    - Codex (GPT-5.x через ChatGPT) — нативно мультимодальны, всегда True.
    - OpenCode-модели через сам OpenAI-аккаунт — тоже GPT-5.x, True; бесплатные
      opencode/* модели — по списку выше (по умолчанию False, т.к. это в
      основном текстовые reasoning/code-модели).
    - Ollama — по явному списку известных тегов, иначе эвристика по имени.
    """
    if is_codex_model(model):
        return True
    if is_opencode_model(model):
        # "opencode:openai/..." — тот же GPT-5.x, что и в Codex.
        if model.startswith("opencode:openai/"):
            return True
        if model.startswith("opencode:opencode/"):
            model_id = model[len("opencode:opencode/"):]
            return _OPENCODE_FREE_VISION.get(model_id, False)
        return False
    if model in _OLLAMA_VISION:
        return _OLLAMA_VISION[model]
    lowered = model.lower()
    return any(hint in lowered for hint in _VISION_NAME_HINTS)
