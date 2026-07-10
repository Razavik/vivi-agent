from __future__ import annotations

import asyncio
import base64
import inspect
import json
from io import BytesIO
from pathlib import Path
from typing import Any
from telethon import TelegramClient
from telethon.errors import SessionPasswordNeededError, PhoneNumberInvalidError

from src.infra.config import Settings, get_settings
from src.infra.errors import ToolExecutionError


PROFILE_FILE = Path("data/telegram_profile.json")
# Скачанные фото редко превышают пару МБ (Telegram сжимает при отправке как "фото");
# документы-картинки могут быть крупнее — этот потолок защищает от раздувания base64
# в контексте LLM одним огромным файлом.
_MAX_IMAGE_BYTES = 8_000_000


def load_telegram_profile() -> dict[str, Any] | None:
    """Читает закреплённый профиль пользователя в Telegram (username, имя, id).

    Отдельная функция уровня модуля (а не метод TelegramTools), чтобы её можно было
    вызывать без API-креденшелов — например, при построении системного промпта
    саб-агента в app_factory, где создавать полноценный TelegramTools избыточно.
    """
    if not PROFILE_FILE.exists():
        return None
    try:
        data = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _save_telegram_profile(profile: dict[str, Any]) -> None:
    PROFILE_FILE.parent.mkdir(parents=True, exist_ok=True)
    PROFILE_FILE.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")


def _message_media_type(msg: Any) -> str | None:
    """Классифицирует медиа сообщения: photo/document-image/video/audio/document/None.

    Чистая функция без обращений к сети — принимает уже полученный объект message.
    """
    if getattr(msg, "photo", None) is not None:
        return "photo"
    document = getattr(msg, "document", None)
    if document is not None:
        mime_type = str(getattr(document, "mime_type", "") or "")
        if mime_type.startswith("image/"):
            return "photo"
        if mime_type.startswith("video/"):
            return "video"
        if mime_type.startswith("audio/"):
            return "audio"
        return "document"
    if getattr(msg, "video", None) is not None:
        return "video"
    if getattr(msg, "voice", None) is not None or getattr(msg, "audio", None) is not None:
        return "audio"
    return None


class TelegramTools:
    def __init__(self, settings: Settings | None = None) -> None:
        settings = settings or get_settings()
        self.api_id = settings.telegram_api_id
        self.api_hash = settings.telegram_api_hash
        self.session_path = settings.telegram_session_path
        self.config_file = Path("data/telegram_config.json")
        self.auth_state_file = Path("data/telegram_auth_state.json")
        self.is_configured = False

        # Загружаем конфигурацию из файла, если нет env переменных
        if not self.api_id or not self.api_hash:
            if self.config_file.exists():
                try:
                    with open(self.config_file, "r", encoding="utf-8") as f:
                        config = json.load(f)
                        self.api_id = config.get("api_id")
                        self.api_hash = config.get("api_hash")
                except Exception:
                    pass

        if self.api_id and self.api_hash:
            self.is_configured = True

    def _create_loop(self) -> asyncio.AbstractEventLoop:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop

    def _create_client(self, loop: asyncio.AbstractEventLoop) -> TelegramClient:
        """Создаёт клиент Telegram с привязкой к выделенному event loop."""
        if not self.is_configured:
            raise ToolExecutionError("Сначала настройте API данные через configure_telegram")
        return TelegramClient(self.session_path, int(self.api_id), self.api_hash, loop=loop)

    def _resolve_entity(self, client: TelegramClient, loop: asyncio.AbstractEventLoop, chat_id: str) -> Any:
        """Резолвит chat_id (числовой id или @username) в Telethon entity.
        Общий хелпер для get_messages/send_message/read_chat_image — раньше эта
        логика была продублирована в каждом методе по отдельности."""
        normalized = chat_id.removeprefix("@")
        if normalized.isdigit():
            dialogs = self._run_telethon(loop, client.get_dialogs(limit=200))
            target_id = int(normalized)
            for dialog in dialogs:
                dialog_entity = getattr(dialog, "entity", None)
                if dialog_entity and getattr(dialog_entity, "id", None) == target_id:
                    return dialog_entity
            return None
        return self._run_telethon(loop, client.get_entity(chat_id))

    @staticmethod
    def _resolve_peer_arg(value: str) -> str | int:
        """Готовит значение from_user/recipient для передачи в Telethon: числовые
        id — как int, остальное (username) — как строку без ведущего @."""
        normalized = value.removeprefix("@")
        return int(normalized) if normalized.isdigit() else normalized

    def _run_telethon(self, loop: asyncio.AbstractEventLoop, value: Any) -> Any:
        """Выполняет awaitable через loop или возвращает готовый синхронный результат."""
        if inspect.isawaitable(value):
            return loop.run_until_complete(value)
        return value

    def _save_auth_state(self, phone_number: str, phone_code_hash: str) -> None:
        self.auth_state_file.parent.mkdir(parents=True, exist_ok=True)
        with open(self.auth_state_file, "w", encoding="utf-8") as f:
            json.dump(
                {"phone_number": phone_number, "phone_code_hash": phone_code_hash},
                f,
                indent=2,
            )

    def _load_auth_state(self) -> dict[str, str]:
        if not self.auth_state_file.exists():
            raise ToolExecutionError("Сначала вызовите telegram_auth_start, чтобы запросить код подтверждения")
        try:
            with open(self.auth_state_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            raise ToolExecutionError(f"Не удалось прочитать состояние авторизации: {str(e)}")
        return {
            "phone_number": str(data.get("phone_number", "")),
            "phone_code_hash": str(data.get("phone_code_hash", "")),
        }

    def _clear_auth_state(self) -> None:
        if self.auth_state_file.exists():
            self.auth_state_file.unlink(missing_ok=True)

    def configure_telegram(self, args: dict[str, Any]) -> dict[str, Any]:
        """Сохраняет API данные для Telegram в файл конфигурации."""
        api_id = str(args.get("api_id", ""))
        api_hash = str(args.get("api_hash", ""))

        if not api_id or not api_hash:
            raise ToolExecutionError("Не указаны api_id или api_hash")

        # Создаём директорию если нужно
        self.config_file.parent.mkdir(parents=True, exist_ok=True)

        # Сохраняем конфигурацию
        config = {"api_id": api_id, "api_hash": api_hash}
        with open(self.config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)

        self.api_id = api_id
        self.api_hash = api_hash
        self.is_configured = True

        return {
            "success": True,
            "message": "API данные сохранены. Теперь можно начать авторизацию через telegram_auth_start.",
        }

    def telegram_auth_start(self, args: dict[str, Any]) -> dict[str, Any]:
        """Начинает авторизацию в Telegram. Запрашивает номер телефона."""
        phone_number = str(args.get("phone_number", ""))

        if not phone_number:
            raise ToolExecutionError("Не указан номер телефона (phone_number)")

        loop = self._create_loop()
        client = self._create_client(loop)

        try:
            self._run_telethon(loop, client.connect())
            result = self._run_telethon(loop, client.send_code_request(phone_number))
            self._save_auth_state(phone_number, result.phone_code_hash)
            return {
                "success": True,
                "phone_number": phone_number,
                "message": f"Код отправлен на номер {phone_number}. Используйте telegram_auth_code для подтверждения.",
            }
        except Exception as e:
            raise ToolExecutionError(f"Ошибка начала авторизации: {str(e)}")
        finally:
            if client.is_connected():
                self._run_telethon(loop, client.disconnect())
            loop.close()

    def telegram_auth_code(self, args: dict[str, Any]) -> dict[str, Any]:
        """Подтверждает авторизацию кодом из Telegram."""
        code = str(args.get("code", ""))
        password = str(args.get("password", ""))  # Для 2FA

        if not code:
            raise ToolExecutionError("Не указан code")

        auth_state = self._load_auth_state()
        phone_number = auth_state["phone_number"]
        phone_code_hash = auth_state["phone_code_hash"]

        if not phone_number or not phone_code_hash:
            raise ToolExecutionError("Состояние авторизации повреждено. Повторите telegram_auth_start")

        loop = self._create_loop()
        client = self._create_client(loop)

        try:
            self._run_telethon(loop, client.connect())
            if self._run_telethon(loop, client.is_user_authorized()):
                self._clear_auth_state()
                profile = self._sync_profile(client, loop)
                return {
                    "success": True,
                    "message": "Авторизация уже активна. Можно отправлять сообщения через send_telegram_message.",
                    "profile": profile,
                }

            try:
                self._run_telethon(
                    loop,
                    client.sign_in(phone=phone_number, code=code, phone_code_hash=phone_code_hash),
                )
            except SessionPasswordNeededError:
                if not password:
                    raise ToolExecutionError(
                        "Требуется пароль двухфакторной аутентификации. Укажите параметр password."
                    )
                self._run_telethon(loop, client.sign_in(password=password))

            self._clear_auth_state()
            profile = self._sync_profile(client, loop)
            return {
                "success": True,
                "message": "Авторизация успешна! Теперь можно отправлять сообщения через send_telegram_message.",
                "profile": profile,
            }
        except PhoneNumberInvalidError:
            raise ToolExecutionError("Некорректный номер телефона")
        except Exception as e:
            raise ToolExecutionError(f"Ошибка подтверждения кода: {str(e)}")
        finally:
            if client.is_connected():
                self._run_telethon(loop, client.disconnect())
            loop.close()

    def _sync_profile(self, client: TelegramClient, loop: asyncio.AbstractEventLoop) -> dict[str, Any]:
        """Читает свой профиль (get_me) и сохраняет в data/telegram_profile.json,
        чтобы он был "закреплён" для агента через prompt_vars — без похода в сеть
        на каждый запуск саб-агента."""
        me = self._run_telethon(loop, client.get_me())
        profile = {
            "id": me.id,
            "username": getattr(me, "username", None),
            "first_name": getattr(me, "first_name", "") or "",
            "last_name": getattr(me, "last_name", "") or "",
            "phone": getattr(me, "phone", None),
        }
        _save_telegram_profile(profile)
        return profile

    def get_own_profile(self, args: dict[str, Any]) -> dict[str, Any]:
        """Инструмент get_own_telegram_profile: принудительно обновляет и
        возвращает закреплённый профиль пользователя (self-healing на случай,
        если файл потерялся или пользователь сменил аккаунт)."""
        loop = self._create_loop()
        client = self._create_client(loop)
        try:
            self._run_telethon(loop, client.connect())
            if not self._run_telethon(loop, client.is_user_authorized()):
                raise ToolExecutionError("Сначала завершите авторизацию через telegram_auth_start и telegram_auth_code")
            profile = self._sync_profile(client, loop)
            return {"success": True, **profile}
        except Exception as e:
            raise ToolExecutionError(f"Ошибка получения профиля: {str(e)}")
        finally:
            if client.is_connected():
                self._run_telethon(loop, client.disconnect())
            loop.close()

    def get_chats(self, args: dict[str, Any]) -> dict[str, Any]:
        """Получает список чатов с пагинацией и фильтрацией по типу."""
        limit = int(args.get("limit", 20))
        offset = int(args.get("offset", 0))
        chat_type = str(args.get("chat_type", "all"))

        if limit <= 0 or limit > 100:
            raise ToolExecutionError("limit должен быть от 1 до 100")
        if offset < 0:
            raise ToolExecutionError("offset должен быть >= 0")
        if chat_type not in ["all", "unknown", "channel"]:
            raise ToolExecutionError("chat_type должен быть одним из: all, unknown, channel")

        loop = self._create_loop()
        client = self._create_client(loop)

        try:
            self._run_telethon(loop, client.connect())
            if not self._run_telethon(loop, client.is_user_authorized()):
                raise ToolExecutionError("Сначала завершите авторизацию через telegram_auth_start и telegram_auth_code")

            # Получаем диалоги
            dialogs = self._run_telethon(loop, client.get_dialogs(limit=limit + offset))

            # Применяем offset и собираем данные с фильтрацией по типу
            chats_data = []
            for dialog in dialogs[offset:]:
                if hasattr(dialog, 'entity'):
                    entity = dialog.entity

                    # Определяем тип чата
                    entity_type = "channel" if hasattr(entity, 'broadcast') else "group" if hasattr(entity, 'megagroup') else "user" if hasattr(entity, 'user_id') else "unknown"

                    # Фильтруем по типу если указан
                    if chat_type != "all" and entity_type != chat_type:
                        continue

                    chat_info = {
                        "id": entity.id,
                        "title": getattr(entity, 'title', None),
                        "username": getattr(entity, 'username', None),
                        "type": entity_type
                    }
                    if hasattr(entity, 'first_name'):
                        chat_info["first_name"] = entity.first_name
                    if hasattr(entity, 'last_name'):
                        chat_info["last_name"] = entity.last_name
                    chats_data.append(chat_info)

            return {
                "success": True,
                "chats": chats_data,
                "total": len(chats_data),
                "limit": limit,
                "offset": offset,
                "chat_type": chat_type
            }
        except Exception as e:
            raise ToolExecutionError(f"Ошибка получения чатов: {str(e)}")
        finally:
            if client.is_connected():
                self._run_telethon(loop, client.disconnect())
            loop.close()

    def get_messages(self, args: dict[str, Any]) -> dict[str, Any]:
        """Получает сообщения из чата с пагинацией и опциональной фильтрацией по отправителю."""
        chat_id = str(args.get("chat_id", ""))
        limit = int(args.get("limit", 20))
        offset = int(args.get("offset", 0))
        from_user_raw = str(args.get("from_user", "")).strip()

        if not chat_id:
            raise ToolExecutionError("Не указан chat_id")
        if limit <= 0:
            raise ToolExecutionError("limit должен быть от 1")
        if offset < 0:
            raise ToolExecutionError("offset должен быть >= 0")

        loop = self._create_loop()
        client = self._create_client(loop)

        try:
            self._run_telethon(loop, client.connect())
            if not self._run_telethon(loop, client.is_user_authorized()):
                raise ToolExecutionError("Сначала завершите авторизацию через telegram_auth_start и telegram_auth_code")

            entity = self._resolve_entity(client, loop, chat_id)
            if entity is None:
                raise ToolExecutionError(f"Чат не найден: {chat_id}")

            # from_user — нативный фильтр Telethon: сервер Telegram сам отдаёт только
            # сообщения нужного отправителя внутри группового чата, без постобработки.
            get_messages_kwargs: dict[str, Any] = {"limit": limit + offset}
            if from_user_raw:
                get_messages_kwargs["from_user"] = self._resolve_peer_arg(from_user_raw)

            messages = self._run_telethon(loop, client.get_messages(entity, **get_messages_kwargs))

            # Применяем offset и собираем данные
            messages_data = []
            for msg in messages[offset:]:
                if msg:
                    sender_id = getattr(msg, 'sender_id', None)
                    if sender_id is None:
                        from_id = getattr(msg, 'from_id', None)
                        sender_id = getattr(from_id, 'user_id', None) or getattr(from_id, 'channel_id', None) or getattr(from_id, 'chat_id', None)
                    msg_info = {
                        "id": msg.id,
                        "text": msg.text or "",
                        "date": msg.date.isoformat() if msg.date else None,
                        "from_id": sender_id,
                        "media_type": _message_media_type(msg),
                    }
                    if hasattr(msg, 'sender') and msg.sender:
                        if hasattr(msg.sender, 'username'):
                            msg_info["sender_username"] = msg.sender.username
                        if hasattr(msg.sender, 'first_name'):
                            msg_info["sender_first_name"] = msg.sender.first_name
                    messages_data.append(msg_info)

            return {
                "success": True,
                "messages": messages_data,
                "total": len(messages_data),
                "limit": limit,
                "offset": offset,
                "chat_id": chat_id,
                "from_user": from_user_raw or None,
            }
        except Exception as e:
            raise ToolExecutionError(f"Ошибка получения сообщений: {str(e)}")
        finally:
            if client.is_connected():
                self._run_telethon(loop, client.disconnect())
            loop.close()

    def read_chat_image(self, args: dict[str, Any]) -> dict[str, Any]:
        """Скачивает фото/изображение из конкретного сообщения чата и возвращает
        его в формате, который SubAgent распознаёт как изображение для LLM
        (_type="image") — см. get_messages(media_type="photo") чтобы найти
        message_id сообщений с фото."""
        chat_id = str(args.get("chat_id", ""))
        message_id_raw = args.get("message_id")

        if not chat_id:
            raise ToolExecutionError("Не указан chat_id")
        try:
            message_id = int(message_id_raw)
        except (TypeError, ValueError):
            raise ToolExecutionError("message_id должен быть числом (см. поле id из get_messages)")

        loop = self._create_loop()
        client = self._create_client(loop)

        try:
            self._run_telethon(loop, client.connect())
            if not self._run_telethon(loop, client.is_user_authorized()):
                raise ToolExecutionError("Сначала завершите авторизацию через telegram_auth_start и telegram_auth_code")

            entity = self._resolve_entity(client, loop, chat_id)
            if entity is None:
                raise ToolExecutionError(f"Чат не найден: {chat_id}")

            msg = self._run_telethon(loop, client.get_messages(entity, ids=message_id))
            if msg is None:
                raise ToolExecutionError(f"Сообщение не найдено: {message_id}")

            media_type = _message_media_type(msg)
            if media_type not in ("photo",):
                raise ToolExecutionError(
                    f"Сообщение {message_id} не содержит изображение (media_type={media_type or 'нет медиа'})"
                )

            buffer = BytesIO()
            self._run_telethon(loop, client.download_media(msg, file=buffer))
            image_bytes = buffer.getvalue()
            if not image_bytes:
                raise ToolExecutionError("Не удалось скачать изображение: пустой файл")
            if len(image_bytes) > _MAX_IMAGE_BYTES:
                raise ToolExecutionError(
                    f"Изображение слишком большое ({len(image_bytes)} байт, лимит {_MAX_IMAGE_BYTES}): "
                    "не могу передать его в контекст модели"
                )

            document = getattr(msg, "document", None)
            mime_type = str(getattr(document, "mime_type", "") or "image/jpeg") if document else "image/jpeg"

            return {
                "image": base64.b64encode(image_bytes).decode("ascii"),
                "format": mime_type,
                "_type": "image",
                "chat_id": chat_id,
                "message_id": message_id,
                "caption": msg.text or "",
                "size": len(image_bytes),
            }
        except ToolExecutionError:
            raise
        except Exception as e:
            raise ToolExecutionError(f"Ошибка скачивания изображения: {str(e)}")
        finally:
            if client.is_connected():
                self._run_telethon(loop, client.disconnect())
            loop.close()

    def get_contacts(self, args: dict[str, Any]) -> dict[str, Any]:
        """Получает список контактов с пагинацией."""
        limit = int(args.get("limit", 20))
        offset = int(args.get("offset", 0))

        if limit <= 0 or limit > 100:
            raise ToolExecutionError("limit должен быть от 1 до 100")
        if offset < 0:
            raise ToolExecutionError("offset должен быть >= 0")

        loop = self._create_loop()
        client = self._create_client(loop)

        try:
            self._run_telethon(loop, client.connect())
            if not self._run_telethon(loop, client.is_user_authorized()):
                raise ToolExecutionError("Сначала завершите авторизацию через telegram_auth_start и telegram_auth_code")

            # Получаем диалоги и фильтруем только пользователей
            dialogs = self._run_telethon(loop, client.get_dialogs(limit=limit + offset))

            # Фильтруем только пользователей (не каналы и не группы)
            contacts_data = []
            for dialog in dialogs[offset:]:
                if hasattr(dialog, 'entity'):
                    entity = dialog.entity
                    # Проверяем, что это пользователь (есть user_id или это User тип)
                    if hasattr(entity, 'user_id') or (hasattr(entity, 'first_name') and not hasattr(entity, 'broadcast') and not hasattr(entity, 'megagroup')):
                        contact_info = {
                            "id": entity.id,
                            "first_name": getattr(entity, 'first_name', ''),
                            "last_name": getattr(entity, 'last_name', ''),
                            "username": getattr(entity, 'username', ''),
                            "phone": getattr(entity, 'phone', '')
                        }
                        contacts_data.append(contact_info)

            return {
                "success": True,
                "contacts": contacts_data,
                "total": len(contacts_data),
                "limit": limit,
                "offset": offset
            }
        except Exception as e:
            raise ToolExecutionError(f"Ошибка получения контактов: {str(e)}")
        finally:
            if client.is_connected():
                self._run_telethon(loop, client.disconnect())
            loop.close()

    def send_message(self, args: dict[str, Any]) -> dict[str, Any]:
        """Отправляет сообщение в Telegram от имени пользователя."""
        recipient = str(args.get("recipient", ""))
        message = str(args.get("message", ""))

        if not recipient:
            raise ToolExecutionError("Не указан получатель сообщения (recipient)")
        if not message:
            raise ToolExecutionError("Не указан текст сообщения (message)")

        loop = self._create_loop()
        client = self._create_client(loop)

        try:
            self._run_telethon(loop, client.connect())
            if not self._run_telethon(loop, client.is_user_authorized()):
                raise ToolExecutionError("Сначала завершите авторизацию через telegram_auth_start и telegram_auth_code")

            entity = self._resolve_entity(client, loop, recipient)
            if entity is None:
                raise ToolExecutionError(f"Получатель не найден: {recipient}")

            self._run_telethon(loop, client.send_message(entity, message))

            return {
                "success": True,
                "recipient": recipient,
                "message": message,
                "status": "Отправлено"
            }
        except SessionPasswordNeededError:
            raise ToolExecutionError("Требуется двухфакторная аутентификация. Введите пароль.")
        except PhoneNumberInvalidError:
            raise ToolExecutionError("Некорректный номер телефона или username")
        except Exception as e:
            raise ToolExecutionError(f"Ошибка отправки сообщения: {str(e)}")
        finally:
            if client.is_connected():
                self._run_telethon(loop, client.disconnect())
            loop.close()
