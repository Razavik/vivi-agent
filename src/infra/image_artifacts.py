"""Сохранение изображений, возвращённых инструментами (_type=="image"), как
артефактов на диске и построение публичного HTTP-URL для встраивания в текст
ответа (markdown ![...](url)) — вместо раздувания base64 в JSON-истории.
"""

from __future__ import annotations

import base64
from typing import Any
from uuid import uuid4

IMAGE_ARTIFACT_URL_PREFIX = "/api/artifact-image"

_MIME_EXTENSIONS = {
    "image/png": "png",
    "image/jpeg": "jpeg",
    "image/jpg": "jpeg",
    "image/gif": "gif",
    "image/webp": "webp",
    "image/bmp": "bmp",
}


def save_image_artifact(
    server_context: Any | None,
    run_id: str,
    image_b64: str,
    mime_type: str = "image/png",
) -> str | None:
    """Декодирует base64-картинку и сохраняет как артефакт run_id, возвращает
    публичный URL для встраивания в markdown. None, если server_context
    недоступен (например при автономном запуске без веб-сервера) или base64
    невалиден — в этом случае картинка просто не будет отправлена пользователю
    напрямую (но по-прежнему видна модели через images в LLM-запросе)."""
    if server_context is None or not run_id:
        return None
    try:
        raw = base64.b64decode(image_b64, validate=False)
    except Exception:
        return None
    if not raw:
        return None

    extension = _MIME_EXTENSIONS.get(mime_type.lower(), "png")
    name = f"image-{uuid4().hex}.{extension}"
    try:
        server_context.create_artifact(run_id, name, raw, mime_type)
    except Exception:
        return None
    return f"{IMAGE_ARTIFACT_URL_PREFIX}/{run_id}/{name}"
