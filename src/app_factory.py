from __future__ import annotations

from typing import Callable

from src.agent.agent_registry import AgentRegistry
from src.agent.runtime import AgentRuntime
from src.agent.sub_agent import SubAgent
from src.infra.chat_memory import ChatMemoryStore
from src.infra.config import OPERATOR_REQUIRED_TOOLS, OPERATOR_RUN_TOOLS, Settings, get_settings, _load_agents_config, is_pc_control_mode
from src.infra.logging import SessionLogger
from src.llm.ollama_client import OllamaClient
from src.safety.path_guard import PathGuard
from src.safety.policy import SafetyPolicy
from src.safety.validator import ActionValidator
from src.tools.artifact_tools import ArtifactTools
from src.tools.catalog import operator_tool_specs, unavailable_run_tools
from src.tools.clipboard_tools import ClipboardTools
from src.tools.delegate_tools import DelegateTools
from src.tools.file_tools import FileTools
from src.tools.notification_tools import NotificationTools
from src.tools.process_tools import ProcessTools
from src.tools.registry import ToolRegistry, ToolSpec
from src.tools.run_tools import RunTools
from src.tools.screen_tools import ScreenTools
from src.tools.system_keyboard_tools import SystemKeyboardTools
from src.tools.system_mouse_tools import SystemMouseTools
from src.tools.system_tools import SystemTools
from src.tools.telegram_tools import TelegramTools
from src.tools.web_tools import WebTools


# Инструменты оркестрации, скрытые в режиме управления ПК (pc_control_mode).
_OPERATOR_ORCHESTRATION_TOOLS = {
    "delegate_task",
    "delegate_parallel",
    "get_agent_memory",
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

# Инструменты управления ПК/экраном, скрытые в режиме оркестратора (не pc_control_mode).
_OPERATOR_PC_TOOLS = {
    "take_screenshot",
    "read_image",
    "get_screen_info",
    "system_mouse_move",
    "system_mouse_nudge",
    "system_mouse_click",
    "system_mouse_double_click",
    "system_mouse_scroll",
    "system_mouse_drag",
    "system_type_text",
    "system_key_press",
    "list_ui_elements",
    "click_ui_element",
    "focus_ui_element",
}


def describe_all_tools(settings: Settings | None = None) -> list[dict[str, object]]:
    """Возвращает описания всех инструментов всех агентов + оператора для UI."""
    settings = settings or get_settings()
    pc_mode = is_pc_control_mode()
    agents_config = _load_agents_config()

    def enabled_tool_names(agent_name: str, required_names: set[str] | None = None) -> set[str] | None:
        agent_cfg = agents_config.get(agent_name)
        if not isinstance(agent_cfg, dict):
            return None
        raw_tools = agent_cfg.get("tools")
        if not isinstance(raw_tools, list):
            return None
        names: set[str] = set(required_names or set())
        for entry in raw_tools:
            if isinstance(entry, dict):
                name = str(entry.get("name", ""))
                required = bool(entry.get("required", False)) or name in names
                if name and (required or bool(entry.get("enabled", True))):
                    names.add(name)
            else:
                names.add(str(entry))
        return names

    # Инструменты оператора — единый источник (src.tools.catalog), тот же список,
    # что регистрируется в build_operator_registry. Обработчики здесь не вызываются,
    # поэтому передаём заглушки. В UI показываем полный набор инструментов режима;
    # ограничение по enabled применяется в runtime (build_operator_registry).
    operator_tools: list[dict[str, object]] = []
    _stub_delegate = DelegateTools(AgentRegistry())
    for spec in operator_tool_specs(_stub_delegate, unavailable_run_tools()):
        if pc_mode and spec.name in _OPERATOR_ORCHESTRATION_TOOLS:
            continue
        if (not pc_mode) and spec.name in (OPERATOR_RUN_TOOLS | _OPERATOR_PC_TOOLS):
            continue
        d = spec.describe()
        d["agent"] = "operator"
        operator_tools.append(d)

    # Инструменты сабагентов — строим напрямую без LLM-клиента
    path_guard = PathGuard(settings.allowed_roots)
    file_tools = FileTools(path_guard)
    process_tools = ProcessTools()
    system_tools = SystemTools()
    web_tools = WebTools()
    telegram_tools = TelegramTools(settings)
    clipboard_tools = ClipboardTools()
    notification_tools = NotificationTools()
    keyboard_tools = SystemKeyboardTools()

    sub_agent_specs: list[tuple[str, list[ToolSpec]]] = [
        ("telegram", [
            ToolSpec("configure_telegram", "Сохранить API данные (api_id и api_hash) для Telegram", 0, telegram_tools.configure_telegram, {"api_id": "str", "api_hash": "str"}),
            ToolSpec("telegram_auth_start", "Начать авторизацию в Telegram — отправляет код на номер", 1, telegram_tools.telegram_auth_start, {"phone_number": "str"}),
            ToolSpec("telegram_auth_code", "Подтвердить авторизацию кодом (и паролем 2FA)", 1, telegram_tools.telegram_auth_code, {"phone_number": "str", "code": "str", "password": "str?"}),
            ToolSpec("send_telegram_message", "Отправить сообщение в Telegram", 1, telegram_tools.send_message, {"recipient": "str", "message": "str"}),
            ToolSpec("get_chats", "Получить список чатов", 0, telegram_tools.get_chats, {"limit": "int?", "offset": "int?", "chat_type": "str?"}),
            ToolSpec("get_messages", "Получить сообщения из чата, опционально только от одного отправителя (from_user). Каждое сообщение содержит media_type (photo/document/video/audio/None) — используй read_chat_image для media_type=photo", 0, telegram_tools.get_messages, {"chat_id": "str", "limit": "int?", "offset": "int?", "from_user": "str?"}),
            ToolSpec("read_chat_image", "Скачать фото из конкретного сообщения чата (id из get_messages, media_type=photo) и увидеть его как изображение", 0, telegram_tools.read_chat_image, {"chat_id": "str", "message_id": "str"}),
            ToolSpec("get_contacts", "Получить список контактов", 0, telegram_tools.get_contacts, {"limit": "int?", "offset": "int?"}),
            ToolSpec("get_own_telegram_profile", "Обновить и получить свой закреплённый профиль в Telegram (username, имя, id)", 0, telegram_tools.get_own_profile, {}),
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
            ToolSpec("get_screen_info", "Получить геометрию экранов, позицию курсора и активное окно Windows", 0, ScreenTools().get_screen_info, {}),
            ToolSpec("take_screenshot", "Сделать скриншот экрана (весь экран или область x/y/width/height) и вернуть PNG", 0, ScreenTools().take_screenshot, {"x": "int?", "y": "int?", "width": "int?", "height": "int?"}),
            ToolSpec("system_mouse_move", "Реально переместить системный курсор Windows по координатам экрана", 0, SystemMouseTools().move, {"x": "int", "y": "int"}),
            ToolSpec("system_mouse_nudge", "Сместить системный курсор относительно текущей позиции и вернуть crop вокруг курсора", 0, SystemMouseTools().nudge, {"dx": "int", "dy": "int"}),
            ToolSpec("system_mouse_click", "Выполнить системный клик Windows в текущей позиции курсора. Для позиционирования сначала используй system_mouse_move", 0, SystemMouseTools().click, {"button": "str?"}),
            ToolSpec("system_mouse_double_click", "Выполнить двойной левый клик Windows в текущей позиции курсора", 0, SystemMouseTools().double_click, {}),
            ToolSpec("system_mouse_scroll", "Прокрутить колесо мыши Windows. clicks < 0 вниз, clicks > 0 вверх", 0, SystemMouseTools().scroll, {"clicks": "int", "x": "int?", "y": "int?"}),
            ToolSpec("system_mouse_drag", "Перетащить мышью от from_x/from_y до to_x/to_y", 0, SystemMouseTools().drag, {"from_x": "int", "from_y": "int", "to_x": "int", "to_y": "int", "duration_ms": "int?"}),
            ToolSpec("system_type_text", "Ввести текст в активное поле через системную клавиатуру Windows", 0, keyboard_tools.type_text, {"text": "str", "interval_ms": "int?"}),
            ToolSpec("system_key_press", "Нажать клавишу или сочетание клавиш Windows: enter, tab, esc, win+r, alt+tab, ctrl+shift+esc, printscreen, vk:0x5b.", 0, keyboard_tools.press_key, {"key": "str", "repeats": "int?"}),
        ]),
        ("web", [
            ToolSpec("fetch_url", "Прочитать содержимое веб-страницы (parse_text=true → чистый текст)", 0, web_tools.fetch_url, {"url": "str", "parse_text": "bool?"}),
            ToolSpec("search_web", "Поиск в интернете через DuckDuckGo (query, max_results?)", 0, web_tools.search_web, {"query": "str", "max_results": "int?"}),
            ToolSpec("open_url", "Открыть URL в браузере", 0, system_tools.open_url, {"url": "str"}),
        ]),
    ]

    result: list[dict[str, object]] = list(operator_tools)
    if pc_mode:
        sub_agent_specs = []
    for agent_name, specs in sub_agent_specs:
        agent_cfg = agents_config.get(agent_name)
        if isinstance(agent_cfg, dict) and not bool(agent_cfg.get("enabled", True)):
            continue
        agent_enabled = enabled_tool_names(agent_name)
        for spec in specs:
            if agent_enabled is not None and spec.name not in agent_enabled:
                continue
            desc = spec.describe()
            desc["agent"] = agent_name
            result.append(desc)
    return result


def _make_memory_store(settings: Settings, agent_name: str) -> ChatMemoryStore:
    """Создаёт отдельный ChatMemoryStore для сабагента."""
    memory_dir = settings.sub_agent_memory_dir
    memory_dir.mkdir(parents=True, exist_ok=True)
    return ChatMemoryStore(memory_dir / f"{agent_name}-memory.json")


def _make_ask_operator_callback(
    llm_client: OllamaClient,
    event_sink: Callable[[str, object], None] | None,
    memory_store: "ChatMemoryStore | None" = None,
    get_runtime_state: "Callable[[], object | None] | None" = None,
) -> Callable[[str], str]:
    """
    Возвращает callback, который делает один текстовый LLM-вызов оператора
    с полным контекстом: история из chat-memory + текущая сессия в реалтайме.
    """
    import json as _json

    operator_system = (
        "Ты — оператор-управляющий Vivi. Один из твоих сабагентов задаёт тебе уточняющий вопрос. "
        "Ответь коротко и конкретно на русском языке. Если не знаешь — скажи честно."
    )

    def ask_operator(question: str) -> str:
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
            {"role": "system", "content": operator_system},
            {"role": "user", "content": user_content},
        ]
        try:
            answer = llm_client.chat(messages)
        except Exception as exc:
            answer = f"Оператор не смог ответить: {exc}"
        return answer

    return ask_operator


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
    keyboard_tools = SystemKeyboardTools()
    system_mouse_tools = SystemMouseTools()

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
        ToolSpec("get_screen_info", "Получить геометрию экранов, позицию курсора и активное окно Windows", 0, ScreenTools().get_screen_info, {}),
        ToolSpec("take_screenshot", "Сделать скриншот экрана (весь экран или область x/y/width/height) и вернуть PNG", 0, ScreenTools().take_screenshot, {"x": "int?", "y": "int?", "width": "int?", "height": "int?"}),
        ToolSpec("system_mouse_move", "Реально переместить системный курсор Windows по координатам экрана", 0, system_mouse_tools.move, {"x": "int", "y": "int"}),
        ToolSpec("system_mouse_click", "Выполнить системный клик Windows в текущей позиции курсора. Для позиционирования сначала используй system_mouse_move", 0, system_mouse_tools.click, {"button": "str?"}),
        ToolSpec("system_mouse_double_click", "Выполнить двойной левый клик Windows в текущей позиции курсора", 0, system_mouse_tools.double_click, {}),
        ToolSpec("system_mouse_scroll", "Прокрутить колесо мыши Windows. clicks < 0 вниз, clicks > 0 вверх", 0, system_mouse_tools.scroll, {"clicks": "int", "x": "int?", "y": "int?"}),
        ToolSpec("system_mouse_drag", "Перетащить мышью от from_x/from_y до to_x/to_y", 0, system_mouse_tools.drag, {"from_x": "int", "from_y": "int", "to_x": "int", "to_y": "int", "duration_ms": "int?"}),
        ToolSpec("system_type_text", "Ввести текст в активное поле через системную клавиатуру Windows", 0, keyboard_tools.type_text, {"text": "str", "interval_ms": "int?"}),
        ToolSpec("system_key_press", "Нажать клавишу или сочетание клавиш Windows: enter, tab, esc, win+r, alt+tab, ctrl+shift+esc, printscreen, vk:0x5b.", 0, keyboard_tools.press_key, {"key": "str", "repeats": "int?"}),
        # --- веб ---
        ToolSpec("fetch_url", "Прочитать содержимое веб-страницы (parse_text=true → чистый текст без HTML)", 0, web_tools.fetch_url, {"url": "str", "parse_text": "bool?"}),
        ToolSpec("search_web", "Поиск в интернете через DuckDuckGo — возвращает список результатов с заголовком, URL и сниппетом", 0, web_tools.search_web, {"query": "str", "max_results": "int?"}),
        # --- telegram ---
        ToolSpec("configure_telegram", "Сохранить API данные (api_id и api_hash) для Telegram", 0, telegram_tools.configure_telegram, {"api_id": "str", "api_hash": "str"}),
        ToolSpec("telegram_auth_start", "Начать авторизацию в Telegram - отправляет код на номер", 1, telegram_tools.telegram_auth_start, {"phone_number": "str"}),
        ToolSpec("telegram_auth_code", "Подтвердить авторизацию кодом из Telegram (и паролем 2FA)", 1, telegram_tools.telegram_auth_code, {"phone_number": "str", "code": "str", "password": "str?"}),
        ToolSpec("send_telegram_message", "Отправить сообщение в Telegram от имени пользователя", 1, telegram_tools.send_message, {"recipient": "str", "message": "str"}),
        ToolSpec("get_chats", "Получить список чатов (limit до 100, offset, chat_type: all/unknown(user)/channel)", 0, telegram_tools.get_chats, {"limit": "int?", "offset": "int?", "chat_type": "str?"}),
        ToolSpec("get_messages", "Получить сообщения из чата (chat_id, limit до 500, offset), опционально только от одного отправителя (from_user). Каждое сообщение содержит media_type (photo/document/video/audio/None)", 0, telegram_tools.get_messages, {"chat_id": "str", "limit": "int?", "offset": "int?", "from_user": "str?"}),
        ToolSpec("read_chat_image", "Скачать фото из конкретного сообщения чата (id из get_messages, media_type=photo) и увидеть его как изображение", 0, telegram_tools.read_chat_image, {"chat_id": "str", "message_id": "str"}),
        ToolSpec("get_contacts", "Получить список контактов (limit, offset)", 0, telegram_tools.get_contacts, {"limit": "int?", "offset": "int?"}),
        ToolSpec("get_own_telegram_profile", "Обновить и получить свой закреплённый профиль в Telegram (username, имя, id)", 0, telegram_tools.get_own_profile, {}),
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


def _build_prompt_vars(agent_name: str) -> dict[str, str]:
    """Готовит дополнительные плейсхолдеры системного промпта конкретного
    саб-агента. Сейчас используется только для telegram — "закреплённый" профиль
    пользователя (username/имя), сохранённый после успешной авторизации, чтобы
    агент знал, от чьего имени он действует, без похода в сеть на каждый запуск."""
    if agent_name != "telegram":
        return {}
    from src.tools.telegram_tools import load_telegram_profile

    profile = load_telegram_profile()
    if not profile:
        return {
            "tg_username": "не указан (профиль ещё не синхронизирован)",
            "tg_display_name": "неизвестно",
        }
    username = profile.get("username") or "без username"
    full_name = " ".join(
        part for part in [profile.get("first_name", ""), profile.get("last_name", "")] if part
    ).strip() or "не указано"
    return {"tg_username": str(username), "tg_display_name": full_name}


def _build_sub_agents(
    client: OllamaClient,
    settings: Settings,
    event_sink: Callable[[str, object], None] | None = None,
    server_context: object | None = None,
) -> AgentRegistry:
    """Создаёт и регистрирует всех сабагентов на основе data/agents.json."""
    if is_pc_control_mode():
        return AgentRegistry()
    all_specs = _build_all_tool_specs(settings, server_context)
    agents_config = _load_agents_config()

    def _make_client(agent_key: str) -> OllamaClient:
        # timeout_seconds=None означает requests без таймаута вообще: если Ollama
        # зависнет и не ответит, блокирующий вызов саб-агента не завершится никогда
        # (и не будет прерван даже отменой — см. RunController cancel-колбэк).
        return OllamaClient(
            settings.ollama_base_url,
            settings.get_model(agent_key),
            settings.request_timeout_seconds,
            num_ctx=settings.num_ctx,
            api_key=settings.ollama_api_key,
            keep_alive=settings.ollama_keep_alive,
            think=settings.ollama_think,
        )

    registry = AgentRegistry()

    for agent_name, agent_cfg in agents_config.items():
        if agent_name == "operator":
            continue  # оператор строится отдельно
        if isinstance(agent_cfg, dict) and not bool(agent_cfg.get("enabled", True)):
            continue
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

        sub = SubAgent(
            name=agent_name,
            display_name=display_name,
            prompt_path=prompt_path,
            tools=agent_tools,
            client=_make_client(agent_name),
            memory_store=_make_memory_store(settings, agent_name),
            max_steps=settings.sub_agent_max_steps,
            user_name=settings.user_name,
            prompt_vars=_build_prompt_vars(agent_name),
            server_context=server_context,
        )
        registry.register(sub)

    return registry


def build_operator_registry(
    delegate_tools: DelegateTools,
    run_tools: RunTools | None = None,
) -> ToolRegistry:
    """Создаёт реестр инструментов оператора."""
    run_tool_impl = run_tools or unavailable_run_tools()

    registry = ToolRegistry()
    pc_mode = is_pc_control_mode()
    specs = operator_tool_specs(delegate_tools, run_tool_impl)
    # Фильтруем по полю enabled из agents.json
    agents_config = _load_agents_config()
    operator_cfg = agents_config.get("operator")
    enabled_names: set[str] | None = None
    if operator_cfg and isinstance(operator_cfg, dict):
        raw_tools = operator_cfg.get("tools")
        if isinstance(raw_tools, list):
            enabled_names = set()
            for entry in raw_tools:
                if isinstance(entry, dict):
                    name = str(entry.get("name", ""))
                    required = bool(entry.get("required", False)) or name in OPERATOR_REQUIRED_TOOLS
                    if required or entry.get("enabled", True):
                        enabled_names.add(name)
                else:
                    enabled_names.add(str(entry))
            enabled_names.update(OPERATOR_REQUIRED_TOOLS)

    for spec in specs:
        if pc_mode and spec.name in _OPERATOR_ORCHESTRATION_TOOLS:
            continue
        if (not pc_mode) and spec.name in (OPERATOR_RUN_TOOLS | _OPERATOR_PC_TOOLS):
            continue
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

    operator_client = OllamaClient(
        settings.ollama_base_url,
        settings.get_model("operator"),
        settings.request_timeout_seconds,
        num_ctx=settings.num_ctx,
        api_key=settings.ollama_api_key,
        keep_alive=settings.ollama_keep_alive,
        think=settings.ollama_think,
    )

    memory_store = ChatMemoryStore(settings.memory_file)

    # Создаём сабагентов
    # ask_operator callback — один LLM-вызов оператора для ответа на вопросы сабагентов
    _runtime_ref: list[AgentRuntime] = []
    ask_operator_callback = _make_ask_operator_callback(
        operator_client,
        event_sink,
        memory_store=memory_store,
        get_runtime_state=lambda: _runtime_ref[0]._current_state if _runtime_ref else None,
    )

    agent_registry = _build_sub_agents(
        operator_client,
        settings,
        event_sink=event_sink,
        server_context=server_context,
    )
    delegate_tools = DelegateTools(
        agent_registry,
        event_sink=event_sink,
        ask_operator_callback=ask_operator_callback,
        create_run_controller=create_run_controller,
    )
    run_tools = RunTools(server_context) if server_context else None
    operator_registry = build_operator_registry(delegate_tools, run_tools)

    # Описания агентов для промпта оператора
    available_agents = agent_registry.describe_all()

    runtime = AgentRuntime(
        client=operator_client,
        registry=operator_registry,
        validator=ActionValidator(operator_registry),
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
        get_active_runs=lambda: [],
        get_supervisor_observations=lambda: [],
        settings=settings,
        server_context=server_context,
    )
    return runtime, operator_registry, settings
