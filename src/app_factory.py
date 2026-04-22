from __future__ import annotations

from typing import Callable

from src.agent.agent_registry import AgentRegistry
from src.agent.runtime import AgentRuntime
from src.agent.sub_agent import SubAgent
from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import Settings, get_settings
from src.infra.logging import SessionLogger
from src.llm.ollama_client import OllamaClient
from src.safety.path_guard import PathGuard
from src.safety.policy import SafetyPolicy
from src.safety.validator import ActionValidator
from src.tools.clipboard_tools import ClipboardTools
from src.tools.confirmation_tools import finish_task, send_message
from src.tools.delegate_tools import DelegateTools
from src.tools.file_tools import FileTools
from src.tools.memory_tools import MemoryTools
from src.tools.model_tools import ModelTools
from src.tools.notification_tools import NotificationTools
from src.tools.process_tools import ProcessTools
from src.tools.registry import ToolRegistry, ToolSpec
from src.tools.run_tools import RunTools
from src.tools.system_tools import SystemTools
from src.tools.telegram_tools import TelegramTools
from src.tools.web_tools import WebTools


def describe_all_tools(settings: Settings | None = None) -> list[dict[str, object]]:
    """Возвращает описания всех инструментов всех агентов + директора для UI."""
    settings = settings or get_settings()

    # Инструменты директора — описываем статически, без создания реального AgentRegistry
    _director_specs = [
        ToolSpec("delegate_task", "Делегировать задачу одному специализированному агенту", 0, lambda a: None, {"agent_name": "str", "task": "str"}),
        ToolSpec("delegate_parallel", "Выполнить задачи у нескольких агентов одновременно (параллельно)", 0, lambda a: None, {"tasks": "list"}),
        ToolSpec("send_message", "Отправить промежуточное сообщение пользователю в чат", 0, lambda a: None, {"message": "str"}),
        ToolSpec("finish_task", "Завершить задачу и вернуть summary", 0, lambda a: None, {}),
        ToolSpec("set_agent_model", "Установить модель Ollama для агента (director/file/system/telegram/web)", 0, lambda a: None, {"agent": "str", "model": "str"}),
        ToolSpec("get_agent_memory", "Просмотреть долгосрочную память саб-агента", 0, lambda a: None, {"agent": "str?", "limit": "int?"}),
        ToolSpec("view_runs", "Показать активные запуски саб-агентов", 0, lambda a: None, {"limit": "int?"}),
        ToolSpec("cancel_run", "Отменить активный запуск саб-агента по run_id", 0, lambda a: None, {"run_id": "str"}),
        ToolSpec("pause_run", "Приостановить активный запуск саб-агента по run_id", 0, lambda a: None, {"run_id": "str"}),
        ToolSpec("resume_run", "Возобновить приостановленный запуск саб-агента по run_id", 0, lambda a: None, {"run_id": "str"}),
        ToolSpec("message_run", "Отправить сообщение в inbox активного запуска саб-агента по run_id", 0, lambda a: None, {"run_id": "str", "message": "str"}),
        ToolSpec("replace_task_run", "Заменить задачу у активного запуска саб-агента по run_id", 0, lambda a: None, {"run_id": "str", "task": "str"}),
    ]
    director_tools: list[dict[str, object]] = []
    for spec in _director_specs:
        d = spec.describe()
        d["agent"] = "director"
        director_tools.append(d)

    # Инструменты сабагентов — строим напрямую без LLM-клиента
    path_guard = PathGuard(settings.allowed_roots)
    file_tools = FileTools(path_guard)
    process_tools = ProcessTools()
    system_tools = SystemTools()
    web_tools = WebTools()
    telegram_tools = TelegramTools(settings)
    clipboard_tools = ClipboardTools()
    notification_tools = NotificationTools()

    sub_agent_specs: list[tuple[str, list[ToolSpec]]] = [
        ("telegram", [
            ToolSpec("configure_telegram", "Сохранить API данные (api_id и api_hash) для Telegram", 0, telegram_tools.configure_telegram, {"api_id": "str", "api_hash": "str"}),
            ToolSpec("telegram_auth_start", "Начать авторизацию в Telegram — отправляет код на номер", 1, telegram_tools.telegram_auth_start, {"phone_number": "str"}),
            ToolSpec("telegram_auth_code", "Подтвердить авторизацию кодом (и паролем 2FA)", 1, telegram_tools.telegram_auth_code, {"phone_number": "str", "code": "str", "password": "str?"}),
            ToolSpec("send_telegram_message", "Отправить сообщение в Telegram", 1, telegram_tools.send_message, {"recipient": "str", "message": "str"}),
            ToolSpec("get_chats", "Получить список чатов", 0, telegram_tools.get_chats, {"limit": "int?", "offset": "int?", "chat_type": "str?"}),
            ToolSpec("get_messages", "Получить сообщения из чата", 0, telegram_tools.get_messages, {"chat_id": "str", "limit": "int?", "offset": "int?"}),
            ToolSpec("get_contacts", "Получить список контактов", 0, telegram_tools.get_contacts, {"limit": "int?", "offset": "int?"}),
        ]),
        ("file", [
            ToolSpec("read_text_file", "Прочитать текстовый файл целиком", 0, file_tools.read_text_file, {"path": "str"}),
            ToolSpec("read_multiple_files", "Прочитать несколько файлов за раз", 0, file_tools.read_multiple_files, {"paths": "list"}),
            ToolSpec("list_directory", "Показать содержимое директории", 0, file_tools.list_directory, {"path": "str"}),
            ToolSpec("find_files", "Найти файлы по glob-паттерну в директории", 0, file_tools.find_files, {"path": "str", "glob": "str", "max_results": "int?"}),
            ToolSpec("search_in_file", "Найти паттерн в файле с контекстом строк", 0, file_tools.search_in_file, {"path": "str", "pattern": "str", "use_regex": "bool?", "context_lines": "int?"}),
            ToolSpec("search_in_directory", "Grep-поиск паттерна по всем файлам директории", 0, file_tools.search_in_directory, {"path": "str", "pattern": "str", "use_regex": "bool?", "file_glob": "str?", "max_results": "int?"}),
            ToolSpec("file_exists", "Проверить существование файла или директории", 0, file_tools.file_exists, {"path": "str"}),
            ToolSpec("get_file_info", "Получить информацию о файле: размер, тип", 0, file_tools.get_file_info, {"path": "str"}),
            ToolSpec("create_file", "Создать новый файл с содержимым (или перезаписать)", 1, file_tools.create_file, {"path": "str", "content": "str?", "overwrite": "bool?"}),
            ToolSpec("patch_file", "Точечно заменить блок текста в файле: old_str → new_str", 1, file_tools.patch_file, {"path": "str", "old_str": "str", "new_str": "str"}),
            ToolSpec("insert_lines", "Вставить текст после указанной строки (after_line=0 — в начало)", 1, file_tools.insert_lines, {"path": "str", "after_line": "int", "text": "str"}),
            ToolSpec("delete_lines", "Удалить строки from_line..to_line включительно (1-based)", 1, file_tools.delete_lines, {"path": "str", "from_line": "int", "to_line": "int"}),
            ToolSpec("create_directory", "Создать директорию (включая промежуточные)", 1, file_tools.create_directory, {"path": "str"}),
            ToolSpec("rename", "Переименовать файл или директорию", 1, file_tools.rename, {"source": "str", "destination": "str"}),
            ToolSpec("copy_file", "Скопировать файл", 1, file_tools.copy_file, {"source": "str", "destination": "str"}),
            ToolSpec("move_file", "Переместить файл", 1, file_tools.move_file, {"source": "str", "destination": "str"}),
            ToolSpec("delete_file", "Удалить файл", 2, file_tools.delete_file, {"path": "str"}),
        ]),
        ("system", [
            ToolSpec("run_powershell", "Выполнить PowerShell-скрипт. detach=true для GUI/бесконечных процессов, timeout — максимум секунд ожидания (по умолчанию 60)", 0, system_tools.run_powershell, {"script": "str", "cwd": "str?", "timeout": "int?", "detach": "bool?"}),
            ToolSpec("get_system_info", "Получить системную информацию", 0, system_tools.get_system_info, {}),
            ToolSpec("get_installed_programs", "Список установленных программ", 0, system_tools.get_installed_programs, {}),
            ToolSpec("disk_free_space", "Свободное место на диске", 0, system_tools.disk_free_space, {"drive": "str?"}),
            ToolSpec("list_network_adapters", "Список сетевых адаптеров", 0, system_tools.list_network_adapters, {}),
            ToolSpec("list_temp_files", "Список временных файлов", 0, system_tools.list_temp_files, {}),
            ToolSpec("list_processes", "Список процессов", 0, process_tools.list_processes, {"limit": "int?", "offset": "int?"}),
            ToolSpec("launch_app", "Запустить приложение", 1, process_tools.launch_app, {"app_name": "str"}),
            ToolSpec("close_app", "Закрыть процесс по имени", 0, process_tools.close_app, {"process_name": "str"}),
            ToolSpec("open_url", "Открыть URL в браузере", 0, system_tools.open_url, {"url": "str"}),
            ToolSpec("get_clipboard", "Прочитать текущее содержимое буфера обмена", 0, clipboard_tools.get_clipboard, {}),
            ToolSpec("set_clipboard", "Записать текст в буфер обмена", 1, clipboard_tools.set_clipboard, {"text": "str"}),
            ToolSpec("show_notification", "Показать Windows-уведомление", 0, notification_tools.show_notification, {"title": "str?", "message": "str"}),
            ToolSpec("take_screenshot", "Сделать скриншот экрана и сохранить PNG", 0, notification_tools.take_screenshot, {"path": "str?"}),
        ]),
        ("web", [
            ToolSpec("fetch_url", "Прочитать содержимое веб-страницы (parse_text=true → чистый текст)", 0, web_tools.fetch_url, {"url": "str", "parse_text": "bool?"}),
            ToolSpec("search_web", "Поиск в интернете через DuckDuckGo (query, max_results?)", 0, web_tools.search_web, {"query": "str", "max_results": "int?"}),
            ToolSpec("open_url", "Открыть URL в браузере", 0, system_tools.open_url, {"url": "str"}),
        ]),
    ]

    result: list[dict[str, object]] = list(director_tools)
    for agent_name, specs in sub_agent_specs:
        for spec in specs:
            desc = spec.describe()
            desc["agent"] = agent_name
            result.append(desc)

    return result


def _make_memory_store(settings: Settings, agent_name: str) -> ChatMemoryStore:
    """Создаёт отдельный ChatMemoryStore для сабагента."""
    memory_dir = settings.sub_agent_memory_dir
    memory_dir.mkdir(parents=True, exist_ok=True)
    return ChatMemoryStore(memory_dir / f"{agent_name}-memory.json")


def _make_ask_director_callback(
    llm_client: OllamaClient,
    event_sink: Callable[[str, object], None] | None,
) -> Callable[[str], str]:
    """
    Возвращает callback, который делает один текстовый LLM-вызов директора
    и возвращает ответ на вопрос сабагента.
    """
    director_system = (
        "Ты — директор-управляющий Vivi. Один из твоих сабагентов задаёт тебе уточняющий вопрос. "
        "Ответь коротко и конкретно на русском языке. Если не знаешь — скажи честно."
    )

    def ask_director(question: str) -> str:
        messages = [
            {"role": "system", "content": director_system},
            {"role": "user", "content": question},
        ]
        try:
            answer = llm_client.chat(messages)
        except Exception as exc:
            answer = f"Директор не смог ответить: {exc}"
        return answer

    return ask_director


def _build_sub_agents(
    client: OllamaClient,
    settings: Settings,
    event_sink: Callable[[str, object], None] | None = None,
) -> AgentRegistry:
    """Создаёт и регистрирует всех сабагентов."""
    path_guard = PathGuard(settings.allowed_roots)
    file_tools = FileTools(path_guard)
    process_tools = ProcessTools()
    system_tools = SystemTools()
    web_tools = WebTools()
    telegram_tools = TelegramTools(settings)
    clipboard_tools = ClipboardTools()
    notification_tools = NotificationTools()
    artifact_tools = ArtifactTools()

    def _make_client(agent_key: str) -> OllamaClient:
        return OllamaClient(
            settings.ollama_base_url,
            settings.get_model(agent_key),
            None,  # без таймаута — сабагенты могут генерировать большие ответы
            num_ctx=settings.num_ctx,
        )

    # Telegram-агент
    telegram_agent = SubAgent(
        name="telegram",
        display_name="Telegram-агент",
        prompt_path="prompts/agents/telegram.txt",
        tools=[
            ToolSpec("configure_telegram", "Сохранить API данные (api_id и api_hash) для Telegram", 0, telegram_tools.configure_telegram, {"api_id": "str", "api_hash": "str"}),
            ToolSpec("telegram_auth_start", "Начать авторизацию в Telegram - отправляет код на номер", 1, telegram_tools.telegram_auth_start, {"phone_number": "str"}),
            ToolSpec("telegram_auth_code", "Подтвердить авторизацию кодом из Telegram (и паролем 2FA)", 1, telegram_tools.telegram_auth_code, {"phone_number": "str", "code": "str", "password": "str?"}),
            ToolSpec("send_telegram_message", "Отправить сообщение в Telegram от имени пользователя", 1, telegram_tools.send_message, {"recipient": "str", "message": "str"}),
            ToolSpec("get_chats", "Получить список чатов (limit до 100, offset, chat_type: all/unknown(user)/channel)", 0, telegram_tools.get_chats, {"limit": "int?", "offset": "int?", "chat_type": "str?"}),
            ToolSpec("get_messages", "Получить сообщения из чата (chat_id, limit до 500, offset)", 0, telegram_tools.get_messages, {"chat_id": "str", "limit": "int?", "offset": "int?"}),
            ToolSpec("get_contacts", "Получить список контактов (limit, offset)", 0, telegram_tools.get_contacts, {"limit": "int?", "offset": "int?"}),
        ] + extra_tools,
        client=_make_client("telegram"),
        memory_store=_make_memory_store(settings, "telegram"),
        max_steps=settings.sub_agent_max_steps,
        user_name=settings.user_name,
    )

    # Файловый агент
    file_agent = SubAgent(
        name="file",
        display_name="Файловый агент",
        prompt_path="prompts/agents/file.txt",
        tools=[
            ToolSpec("read_text_file", "Прочитать текстовый файл целиком", 0, file_tools.read_text_file, {"path": "str"}),
            ToolSpec("read_multiple_files", "Прочитать несколько файлов за раз", 0, file_tools.read_multiple_files, {"paths": "list"}),
            ToolSpec("list_directory", "Показать содержимое директории", 0, file_tools.list_directory, {"path": "str"}),
            ToolSpec("find_files", "Найти файлы по glob-паттерну в директории", 0, file_tools.find_files, {"path": "str", "glob": "str", "max_results": "int?"}),
            ToolSpec("search_in_file", "Найти паттерн в файле с контекстом строк", 0, file_tools.search_in_file, {"path": "str", "pattern": "str", "use_regex": "bool?", "context_lines": "int?"}),
            ToolSpec("search_in_directory", "Grep-поиск паттерна по всем файлам директории", 0, file_tools.search_in_directory, {"path": "str", "pattern": "str", "use_regex": "bool?", "file_glob": "str?", "max_results": "int?"}),
            ToolSpec("file_exists", "Проверить существование файла или директории", 0, file_tools.file_exists, {"path": "str"}),
            ToolSpec("get_file_info", "Получить информацию о файле: размер, тип", 0, file_tools.get_file_info, {"path": "str"}),
            ToolSpec("create_file", "Создать новый файл с содержимым (или перезаписать)", 1, file_tools.create_file, {"path": "str", "content": "str?", "overwrite": "bool?"}),
            ToolSpec("patch_file", "Точечно заменить блок текста в файле: old_str → new_str", 1, file_tools.patch_file, {"path": "str", "old_str": "str", "new_str": "str"}),
            ToolSpec("insert_lines", "Вставить текст после указанной строки (after_line=0 — в начало)", 1, file_tools.insert_lines, {"path": "str", "after_line": "int", "text": "str"}),
            ToolSpec("delete_lines", "Удалить строки from_line..to_line включительно (1-based)", 1, file_tools.delete_lines, {"path": "str", "from_line": "int", "to_line": "int"}),
            ToolSpec("create_directory", "Создать директорию (включая промежуточные)", 1, file_tools.create_directory, {"path": "str"}),
            ToolSpec("rename", "Переименовать файл или директорию", 1, file_tools.rename, {"source": "str", "destination": "str"}),
            ToolSpec("copy_file", "Скопировать файл", 1, file_tools.copy_file, {"source": "str", "destination": "str"}),
            ToolSpec("move_file", "Переместить файл", 1, file_tools.move_file, {"source": "str", "destination": "str"}),
            ToolSpec("delete_file", "Удалить файл", 2, file_tools.delete_file, {"path": "str"}),
        ] + extra_tools,
        client=_make_client("file"),
        memory_store=_make_memory_store(settings, "file"),
        max_steps=settings.sub_agent_max_steps,
        user_name=settings.user_name,
    )

    # Системный агент
    system_agent = SubAgent(
        name="system",
        display_name="Системный агент",
        prompt_path="prompts/agents/system.txt",
        tools=[
            ToolSpec("run_powershell", "Выполнить произвольный скрипт PowerShell. detach=true для GUI/бесконечных процессов, timeout — максимум секунд ожидания (по умолчанию 60)", 0, system_tools.run_powershell, {"script": "str", "cwd": "str?", "timeout": "int?", "detach": "bool?"}),
            ToolSpec("get_system_info", "Получить базовую системную информацию", 0, system_tools.get_system_info, {}),
            ToolSpec("get_installed_programs", "Получить список установленных программ", 0, system_tools.get_installed_programs, {}),
            ToolSpec("disk_free_space", "Свободное место на диске", 0, system_tools.disk_free_space, {"drive": "str?"}),
            ToolSpec("list_network_adapters", "Список сетевых адаптеров", 0, system_tools.list_network_adapters, {}),
            ToolSpec("list_temp_files", "Список временных файлов", 0, system_tools.list_temp_files, {}),
            ToolSpec("list_processes", "Список процессов (limit, offset)", 0, process_tools.list_processes, {"limit": "int?", "offset": "int?"}),
            ToolSpec("launch_app", "Запустить приложение", 1, process_tools.launch_app, {"app_name": "str"}),
            ToolSpec("close_app", "Закрыть процесс по имени", 0, process_tools.close_app, {"process_name": "str"}),
            ToolSpec("open_url", "Открыть веб-сайт в браузере", 0, system_tools.open_url, {"url": "str"}),
            ToolSpec("get_clipboard", "Прочитать текущее содержимое буфера обмена", 0, clipboard_tools.get_clipboard, {}),
            ToolSpec("set_clipboard", "Записать текст в буфер обмена", 1, clipboard_tools.set_clipboard, {"text": "str"}),
            ToolSpec("show_notification", "Показать Windows toast-уведомление", 0, notification_tools.show_notification, {"title": "str?", "message": "str"}),
            ToolSpec("take_screenshot", "Сделать скриншот экрана и сохранить PNG", 0, notification_tools.take_screenshot, {"path": "str?"}),
        ] + extra_tools,
        client=_make_client("system"),
        memory_store=_make_memory_store(settings, "system"),
        max_steps=settings.sub_agent_max_steps,
        user_name=settings.user_name,
    )

    # Веб-агент
    web_agent = SubAgent(
        name="web",
        display_name="Веб-агент",
        prompt_path="prompts/agents/web.txt",
        tools=[
            ToolSpec("fetch_url", "Прочитать содержимое веб-страницы (parse_text=true → чистый текст без HTML)", 0, web_tools.fetch_url, {"url": "str", "parse_text": "bool?"}),
            ToolSpec("search_web", "Поиск в интернете через DuckDuckGo — возвращает список результатов с заголовком, URL и сниппетом", 0, web_tools.search_web, {"query": "str", "max_results": "int?"}),
            ToolSpec("open_url", "Открыть URL в браузере", 0, system_tools.open_url, {"url": "str"}),
        ] + extra_tools,
        client=_make_client("web"),
        memory_store=_make_memory_store(settings, "web"),
        max_steps=settings.sub_agent_max_steps,
        user_name=settings.user_name,
    )

    registry = AgentRegistry()
    registry.register(telegram_agent)
    registry.register(file_agent)
    registry.register(system_agent)
    registry.register(web_agent)
    return registry


def build_director_registry(
    delegate_tools: DelegateTools,
    run_tools: RunTools | None = None,
) -> ToolRegistry:
    """Создаёт реестр инструментов директора."""
    registry = ToolRegistry()
    specs: list[ToolSpec] = [
        ToolSpec(
            "delegate_task",
            "Делегировать задачу одному специализированному агенту. Агенты: telegram, file, system, web. Параметры: agent_name (имя), task (задача), images (опционально — список base64-строк изображений для передаче агенту)",
            0,
            delegate_tools.delegate_task,
            {"agent_name": "str", "task": "str", "images": "list?"},
        ),
        ToolSpec(
            "delegate_parallel",
            "Выполнить задачи у нескольких агентов одновременно (параллельно). tasks — список объектов {agent_name, task, images?}. Результаты возвращаются вместе.",
            0,
            delegate_tools.delegate_parallel,
            {"tasks": "list"},
        ),
        ToolSpec("send_message", "Отправить промежуточное сообщение пользователю в чат", 0, send_message, {"message": "str"}),
        ToolSpec("finish_task", "Завершить задачу и вернуть итоговый ответ пользователю", 0, finish_task, {"summary": "str"}),
        ToolSpec(
            "set_agent_model",
            "Установить модель Ollama для агента. agent: director/file/system/telegram/web. model: точное название модели из Ollama (напр. qwen2.5-coder:7b). Изменения вступают в силу при следующем запуске задачи.",
            0,
            ModelTools().set_agent_model,
            {"agent": "str", "model": "str"},
        ),
        ToolSpec(
            "get_agent_memory",
            "Просмотреть долгосрочную память саб-агента. Без agent — сводка по всем агентам. С agent — полная история (file/system/telegram/web). limit — кол-во последних записей (по умолчанию 10).",
            0,
            MemoryTools().get_agent_memory,
            {"agent": "str?", "limit": "int?"},
        ),
    ]
    if run_tools is not None:
        specs.extend([
            ToolSpec(
                "view_runs",
                "Показать активные запуски саб-агентов. limit — максимальное количество записей.",
                0,
                run_tools.view_runs,
                {"limit": "int?"},
            ),
            ToolSpec(
                "cancel_run",
                "Отменить активный запуск саб-агента по run_id.",
                0,
                run_tools.cancel_run,
                {"run_id": "str"},
            ),
            ToolSpec(
                "pause_run",
                "Приостановить активный запуск саб-агента по run_id.",
                0,
                run_tools.pause_run,
                {"run_id": "str"},
            ),
            ToolSpec(
                "resume_run",
                "Возобновить приостановленный запуск саб-агента по run_id.",
                0,
                run_tools.resume_run,
                {"run_id": "str"},
            ),
            ToolSpec(
                "message_run",
                "Отправить сообщение в inbox активного запуска саб-агента по run_id.",
                0,
                run_tools.message_run,
                {"run_id": "str", "message": "str"},
            ),
            ToolSpec(
                "replace_task_run",
                "Заменить задачу (user_goal) у активного запуска саб-агента по run_id.",
                0,
                run_tools.replace_task_run,
                {"run_id": "str", "task": "str"},
            ),
        ])
    for spec in specs:
        registry.register(spec)
    return registry


def build_runtime(
    confirm: Callable[[str], bool],
    logger: SessionLogger,
    event_sink: Callable[[str, object], None] | None = None,
    create_run_controller: Callable[[str, str, str], object] | None = None,
    settings: Settings | None = None,
    server_context: object | None = None,
) -> tuple[AgentRuntime, ToolRegistry, Settings]:
    settings = settings or get_settings()

    director_client = OllamaClient(
        settings.ollama_base_url,
        settings.get_model("director"),
        settings.request_timeout_seconds,
        num_ctx=settings.num_ctx,
    )

    # Создаём сабагентов
    # ask_director callback — один LLM-вызов директора для ответа на вопросы сабагентов
    ask_director_callback = _make_ask_director_callback(director_client, event_sink)

    # Создаём инструменты директора
    artifact_tools = ArtifactTools(server_context) if server_context else None
    agent_registry = build_agent_registry(
        path_guard,
        settings,
        event_sink=event_sink,
        ask_director_callback=ask_director_callback,
        create_run_controller=create_run_controller,
        artifact_tools=artifact_tools,
    )
    delegate_tools = DelegateTools(
        agent_registry,
        event_sink=event_sink,
        ask_director_callback=ask_director_callback,
        create_run_controller=create_run_controller,
    )
    run_tools = RunTools(server_context) if server_context else None
    director_registry = build_director_registry(delegate_tools, run_tools)

    # Описания агентов для промпта директора
    available_agents = agent_registry.describe_all()

    memory_store = ChatMemoryStore(settings.memory_file)
    runtime = AgentRuntime(
        client=director_client,
        registry=director_registry,
        validator=ActionValidator(director_registry),
        policy=SafetyPolicy(),
        logger=logger,
        memory_store=memory_store,
        confirm=confirm,
        max_steps=settings.max_steps,
        max_consecutive_errors=settings.max_consecutive_errors,
        workspace_root=str(settings.workspace_root),
        event_sink=event_sink,
        user_name=settings.user_name,
        available_agents=available_agents,
        get_active_runs=lambda: server_context.run_registry.list_active() if server_context else [],
    )
    return runtime, director_registry, settings
