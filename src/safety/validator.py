from __future__ import annotations

import json

from src.agent.core.schemas import ActionStep
from src.infra.errors import ValidationError
from src.tools.core.registry import ToolRegistry, ToolSpec

# Маппинг schema-типов на Python-типы для валидации
_TYPE_MAP: dict[str, type | tuple[type, ...]] = {
    "str": str,
    "int": int,
    "float": (int, float),
    "bool": bool,
    "list": list,
    "dict": dict,
}


def _coerce(value: object, base_type: str) -> object | None:
    """Мягкое приведение типа, когда значение не совпадает с ожидаемым, но
    синтаксически валидно для него. Модели (особенно менее сильные — напр.
    бесплатные через OpenCode ACP) часто отдают числа/булевы как строки в
    JSON (напр. "limit": "20"); вместо жёсткого отказа пробуем привести и
    продолжить. Возвращает None, если привести не получилось."""
    if base_type == "int":
        if isinstance(value, bool):
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if stripped.lstrip("-").isdigit():
                return int(stripped)
            return None
        if isinstance(value, float) and value.is_integer():
            return int(value)
        return None
    if base_type == "float":
        if isinstance(value, bool):
            return None
        if isinstance(value, (str, int)):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None
        return None
    if base_type == "bool":
        if isinstance(value, str):
            lowered = value.strip().lower()
            if lowered in ("true", "1", "yes"):
                return True
            if lowered in ("false", "0", "no"):
                return False
        return None
    if base_type == "str":
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            return str(value)
        return None
    if base_type in ("list", "dict"):
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except (TypeError, ValueError):
                return None
            expected = _TYPE_MAP[base_type]
            if isinstance(parsed, expected):
                return parsed
        return None
    return None


def _parse_spec(raw: str) -> tuple[str, bool, list[str] | None]:
    """Разбирает строку типа из args_schema.

    Форматы:
      "str"                   → base_type=str, optional=False, enum=None
      "str?"                  → base_type=str, optional=True,  enum=None
      "enum:val1|val2"        → base_type=str, optional=False, enum=[val1, val2]
      "enum:val1|val2?"       → base_type=str, optional=True,  enum=[val1, val2]

    Возвращает (base_type, optional, enum_values).
    """
    spec = raw.strip()
    optional = spec.endswith("?")
    if optional:
        spec = spec[:-1].strip()

    if spec.startswith("enum:"):
        values = [v.strip() for v in spec[5:].split("|") if v.strip()]
        return "str", optional, values

    return spec, optional, None


class ActionValidator:
    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def validate(self, step: ActionStep) -> ToolSpec:
        tool = self.registry.get(step.action)
        if tool is None:
            raise ValidationError(f"Неизвестный инструмент: {step.action}")

        known = set(tool.args_schema.keys())

        # Проверяем каждый объявленный аргумент
        for name, type_spec in tool.args_schema.items():
            base_type, optional, enum_values = _parse_spec(str(type_spec))

            if name not in step.args:
                if not optional:
                    raise ValidationError(
                        f"Для инструмента {tool.name} не хватает аргумента: {name}"
                    )
                continue

            value = step.args[name]
            if value is None and optional:
                continue

            # Проверка типа — с мягким приведением перед отказом (см. _coerce)
            expected = _TYPE_MAP.get(base_type)
            if expected is not None and not isinstance(value, expected):
                coerced = _coerce(value, base_type)
                if coerced is None:
                    raise ValidationError(
                        f"Инструмент {tool.name}: аргумент '{name}' должен быть {base_type}, "
                        f"получен {type(value).__name__}"
                    )
                value = coerced
                step.args[name] = value

            # Проверка enum-значений
            if enum_values is not None and str(value) not in enum_values:
                raise ValidationError(
                    f"Инструмент {tool.name}: аргумент '{name}' должен быть одним из "
                    f"{enum_values}, получено '{value}'"
                )

        # Предупреждение о неизвестных полях (не ошибка — модель могла добавить лишнее)
        extra = set(step.args.keys()) - known
        if extra:
            # Неизвестные поля молча игнорируем, но фиксируем для отладки
            step.args = {k: v for k, v in step.args.items() if k in known}

        return tool
