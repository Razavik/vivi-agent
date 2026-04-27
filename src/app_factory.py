from __future__ import annotations

from typing import Callable

from src.agent.agent_registry import AgentRegistry
from src.agent.runtime import AgentRuntime
from src.agent.sub_agent import SubAgent
from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import DIRECTOR_REQUIRED_TOOLS, Settings, get_settings, is_tool_enabled, _load_agents_config
from src.infra.logging import SessionLogger
from src.llm.ollama_client import OllamaClient
from src.safety.path_guard import PathGuard
from src.safety.policy import SafetyPolicy
from src.safety.validator import ActionValidator
from src.tools.artifact_tools import ArtifactTools
from src.tools.clipboard_tools import ClipboardTools
from src.tools.confirmation_tools import finish_task, send_message
from src.tools.delegate_tools import DelegateTools
from src.tools.file_tools import FileTools
from src.tools.memory_tools import MemoryTools
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
        ToolSpec("finish_task", "Завершить задачу и вернуть структурированный результат", 0, lambda a: None, {"summary": "str?", "status": "str?", "changed_files": "list?", "verification": "list?", "risks": "list?"}),
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

    # Артефакты — общие инструменты для всех сабагентов
    artifact_specs = [
        ToolSpec("create_artifact", "Создать именованный артефакт текущего run (виден другим сабагентам)", 0, lambda a: None, {"name": "str", "content": "str", "mime_type": "str?", "run_id": "str?"}),
        ToolSpec("read_artifact", "Прочитать артефакт по имени (run_id — опционально)", 0, lambda a: None, {"name": "str", "run_id": "str?"}),
        ToolSpec("list_artifacts", "Список артефактов текущего run", 0, lambda a: None, {"run_id": "str?"}),
    ]

    result: list[dict[str, object]] = list(director_tools)
    for agent_name, specs in sub_agent_specs:
        for spec in specs:
            desc = spec.describe()
            desc["agent"] = agent_name
            result.append(desc)
        for spec in artifact_specs:
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
    memory_store: "ChatMemoryStore | None" = None,
    get_runtime_state: "Callable[[], object | None] | None" = None,
) -> Callable[[str], str]:
    """
    Возвращает callback, который делает один текстовый LLM-вызов директора
    с полным контекстом: история из chat-memory + текущая сессия в реалтайме.
    """
    import json as _json

    director_system = (
        "Ты — директор-управляющий Vivi. Один из твоих сабагентов задаёт тебе уточняющий вопрос. "
        "Ответь коротко и конкретно на русском языке. Если не знаешь — скажи честно."
    )

    def ask_director(question: str) -> str:
        context_parts: list[str] = []

        # Прошлая история из файла
        if memory_store is not None:
            try:
                data = memory_store.load()
                history = data.get("chat_history", [])
                if history:
                    context_parts.append(
                        "Прошлая история диалога:\n" + _json.dumps(history[-20:], ensure_ascii=False, indent=2)
                    )
            except Exception:
                pass

        # Текущая сессия в реалтайме
        if get_runtime_state is not None:
            state = get_runtime_state()
            if state is not None:
                goal = getattr(state, "user_goal", None)
                if goal:
                    context_parts.append(f"Текущая задача: {goal}")
                chat_history = getattr(state, "chat_history", [])
                if chat_history:
                    lines = [
                        f"{getattr(m, 'role', '')}: {getattr(m, 'content', '')}"
                        for m in chat_history[-6:]
                        if getattr(m, "role", "") and getattr(m, "content", "")
                    ]
                    if lines:
                        context_parts.append("Текущий диалог:\n" + "\n".join(lines))
                plan = getattr(state, "plan", [])
                if plan:
                    plan_lines = [
                        f"- [{getattr(p, 'status', '')}] {getattr(p, 'content', '')}"
                        for p in plan
                    ]
                    context_parts.append("Текущий план:\n" + "\n".join(plan_lines))
                observations = getattr(state, "observations", [])
                if observations:
                    obs_lines = [
                        f"- {getattr(o, 'action', '')}: {'OK' if getattr(o, 'success', False) else 'ОШИБКА'} → {_json.dumps(getattr(o, 'result', {}), ensure_ascii=False)[:300]}"
                        for o in observations[-5:]
                    ]
                    context_parts.append("Последние действия:\n" + "\n".join(obs_lines))

        context_str = "\n\n".join(context_parts)
        user_content = f"{context_str}\n\nВопрос от сабагента: {question}" if context_str else question

        messages = [
            {"role": "system", "content": director_system},
            {"role": "user", "content": user_content},
        ]
        try:
            answer = llm_client.chat(messages)
        except Exception as exc:
            answer = f"Директор не смог ответить: {exc}"
        return answer

    return ask_director


def _build_all_tool_specs(
    settings: Settings,
    server_context: object | None,
) -> dict[str, ToolSpec]:
    """Строит словарь всех доступных ToolSpec по имени инструмента."""
    path_guard = PathGuard(settings.allowed_roots)
    file_tools = FileTools(path_guard)
    process_tools = ProcessTools()
    system_tools = SystemTools()
    web_tools = WebTools()
    telegram_tools = TelegramTools(settings)
    clipboard_tools = ClipboardTools()
    notification_tools = NotificationTools()

    specs: list[ToolSpec] = [
        # --- файловые ---
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
        # --- системные ---
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
        # --- веб ---
        ToolSpec("fetch_url", "Прочитать содержимое веб-страницы (parse_text=true → чистый текст без HTML)", 0, web_tools.fetch_url, {"url": "str", "parse_text": "bool?"}),
        ToolSpec("search_web", "Поиск в интернете через DuckDuckGo — возвращает список результатов с заголовком, URL и сниппетом", 0, web_tools.search_web, {"query": "str", "max_results": "int?"}),
        # --- telegram ---
        ToolSpec("configure_telegram", "Сохранить API данные (api_id и api_hash) для Telegram", 0, telegram_tools.configure_telegram, {"api_id": "str", "api_hash": "str"}),
        ToolSpec("telegram_auth_start", "Начать авторизацию в Telegram - отправляет код на номер", 1, telegram_tools.telegram_auth_start, {"phone_number": "str"}),
        ToolSpec("telegram_auth_code", "Подтвердить авторизацию кодом из Telegram (и паролем 2FA)", 1, telegram_tools.telegram_auth_code, {"phone_number": "str", "code": "str", "password": "str?"}),
        ToolSpec("send_telegram_message", "Отправить сообщение в Telegram от имени пользователя", 1, telegram_tools.send_message, {"recipient": "str", "message": "str"}),
        ToolSpec("get_chats", "Получить список чатов (limit до 100, offset, chat_type: all/unknown(user)/channel)", 0, telegram_tools.get_chats, {"limit": "int?", "offset": "int?", "chat_type": "str?"}),
        ToolSpec("get_messages", "Получить сообщения из чата (chat_id, limit до 500, offset)", 0, telegram_tools.get_messages, {"chat_id": "str", "limit": "int?", "offset": "int?"}),
        ToolSpec("get_contacts", "Получить список контактов (limit, offset)", 0, telegram_tools.get_contacts, {"limit": "int?", "offset": "int?"}),
    ]

    # Артефактные инструменты (только если есть server_context)
    if server_context is not None:
        artifact_tools = ArtifactTools(server_context)
        specs += [
            ToolSpec("create_artifact", "Создать именованный артефакт для текущего run (или явно указанного run_id). Артефакт виден другим сабагентам и сохраняется на диске.", 0, artifact_tools.create_artifact, {"name": "str", "content": "str", "mime_type": "str?", "run_id": "str?"}),
            ToolSpec("read_artifact", "Прочитать артефакт по имени (run_id — опционально, по умолчанию текущий run).", 0, artifact_tools.read_artifact, {"name": "str", "run_id": "str?"}),
            ToolSpec("list_artifacts", "Список артефактов текущего run (или явно указанного run_id).", 0, artifact_tools.list_artifacts, {"run_id": "str?"}),
            ToolSpec("handoff_artifact", "Передать (скопировать) артефакт из текущего run в другой run. dst_run_id — получатель.", 0, artifact_tools.handoff_artifact, {"name": "str", "dst_run_id": "str", "dst_name": "str?"}),
            ToolSpec("gc_artifacts", "Удалить артефакты текущего run. older_than_seconds=0 — удалить все.", 0, artifact_tools.gc_artifacts, {"older_than_seconds": "float?"}),
            ToolSpec("wait_for_artifact", "Объявить зависимость: текущий run ждёт артефакт от другого run.", 0, artifact_tools.wait_for_artifact, {"artifact_name": "str", "provider_run_id": "str"}),
            ToolSpec("mark_artifact_ready", "Пометить артефакт готовым и уведомить ждущие run через inbox.", 0, artifact_tools.mark_artifact_ready, {"artifact_name": "str"}),
        ]

    return {s.name: s for s in specs}


def _build_sub_agents(
    client: OllamaClient,
    settings: Settings,
    event_sink: Callable[[str, object], None] | None = None,
    server_context: object | None = None,
) -> AgentRegistry:
    """Создаёт и регистрирует всех сабагентов на основе data/agents.json."""
    all_specs = _build_all_tool_specs(settings, server_context)
    agents_config = _load_agents_config()

    # Артефактные инструменты добавляем всем сабагентам автоматически
    artifact_names = {"create_artifact", "read_artifact", "list_artifacts", "handoff_artifact", "gc_artifacts", "wait_for_artifact", "mark_artifact_ready"}
    extra_tools = [all_specs[n] for n in artifact_names if n in all_specs]

    def _make_client(agent_key: str) -> OllamaClient:
        return OllamaClient(
            settings.ollama_base_url,
            settings.get_model(agent_key),
            None,
            num_ctx=settings.num_ctx,
            api_key=settings.ollama_api_key,
            keep_alive=settings.ollama_keep_alive,
            think=settings.ollama_think,
        )

    registry = AgentRegistry()

    for agent_name, agent_cfg in agents_config.items():
        if agent_name == "director":
            continue  # директор строится отдельно
        display_name = str(agent_cfg.get("display_name", agent_name))
        prompt_path = str(agent_cfg.get("prompt_path", f"prompts/agents/{agent_name}.txt"))
        raw_tools: list[object] = list(agent_cfg.get("tools", []))  # type: ignore[arg-type]

        # tools — список объектов {name, enabled, required?} или строк (обратная совместимость)
        agent_tools: list[ToolSpec] = []
        for entry in raw_tools:
            if isinstance(entry, dict):
                name = str(entry.get("name", ""))
                required = bool(entry.get("required", False))
                enabled = required or bool(entry.get("enabled", True))
            else:
                name = str(entry)
                enabled = True
            if enabled and name in all_specs:
                agent_tools.append(all_specs[name])

        agent_tools += extra_tools

        sub = SubAgent(
            name=agent_name,
            display_name=display_name,
            prompt_path=prompt_path,
            tools=agent_tools,
            client=_make_client(agent_name),
            memory_store=_make_memory_store(settings, agent_name),
            max_steps=settings.sub_agent_max_steps,
            user_name=settings.user_name,
        )
        registry.register(sub)

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
        ToolSpec("finish_task", "Завершить задачу и вернуть итоговый ответ", 0, finish_task, {"summary": "str?", "status": "str?", "changed_files": "list?", "verification": "list?", "risks": "list?"}),
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
            ToolSpec(
                "reprioritize_run",
                "Изменить приоритет активного run (priority: 1=высший, 10=низший).",
                0,
                run_tools.reprioritize_run,
                {"run_id": "str", "priority": "int"},
            ),
            ToolSpec(
                "get_world_state",
                "Получить структурированный снимок состояния всей системы: активные run, вопросы, блокировки.",
                0,
                run_tools.get_world_state,
                {},
            ),
            ToolSpec(
                "wait_for_event",
                "Ждать завершения конкретного run. run_id — идентификатор, timeout_seconds — максимальное ожидание.",
                0,
                run_tools.wait_for_event,
                {"run_id": "str", "timeout_seconds": "float?"},
            ),
        ])
    # Фильтруем по полю enabled из agents.json
    agents_config = _load_agents_config()
    director_cfg = agents_config.get("director")
    enabled_names: set[str] | None = None
    if director_cfg and isinstance(director_cfg, dict):
        raw_tools = director_cfg.get("tools")
        if isinstance(raw_tools, list):
            enabled_names = set()
            for entry in raw_tools:
                if isinstance(entry, dict):
                    name = str(entry.get("name", ""))
                    required = bool(entry.get("required", False)) or name in DIRECTOR_REQUIRED_TOOLS
                    if required or entry.get("enabled", True):
                        enabled_names.add(name)
                else:
                    enabled_names.add(str(entry))
            enabled_names.update(DIRECTOR_REQUIRED_TOOLS)

    for spec in specs:
        if enabled_names is not None and spec.name not in enabled_names:
            continue
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
        api_key=settings.ollama_api_key,
        keep_alive=settings.ollama_keep_alive,
        think=settings.ollama_think,
    )

    memory_store = ChatMemoryStore(settings.memory_file)

    # Создаём сабагентов
    # ask_director callback — один LLM-вызов директора для ответа на вопросы сабагентов
    _runtime_ref: list[AgentRuntime] = []
    ask_director_callback = _make_ask_director_callback(
        director_client,
        event_sink,
        memory_store=memory_store,
        get_runtime_state=lambda: _runtime_ref[0]._current_state if _runtime_ref else None,
    )

    agent_registry = _build_sub_agents(
        director_client,
        settings,
        event_sink=event_sink,
        server_context=server_context,
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
        get_supervisor_observations=lambda: server_context.get_supervisor_alerts() if server_context else [],
        settings=settings,
    )
    return runtime, director_registry, settings
