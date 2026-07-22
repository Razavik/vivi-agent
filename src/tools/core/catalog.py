"""Единый источник истины для инструментов оператора.

Ранее список ToolSpec оператора дублировался в двух местах: в
``describe_all_tools`` (для UI, с заглушками-обработчиками) и в
``build_operator_registry`` (с реальными обработчиками). Копии со временем
разошлись — например, ``get_screen_info`` рекламировался в промпте и UI, но не
регистрировался в реальном реестре оператора. Этот модуль устраняет дублирование.
"""

from __future__ import annotations

from typing import Any, Callable

from src.tools.core.confirmation_tools import finish_task
from src.tools.core.registry import ToolSpec
from src.tools.agent_ops.memory_tools import MemoryTools
from src.tools.pc_control.screen_tools import ScreenTools
from src.tools.pc_control.system_keyboard_tools import SystemKeyboardTools
from src.tools.pc_control.system_mouse_tools import SystemMouseTools
from src.tools.pc_control.ui_automation_tools import UIAutomationTools


# Инструменты управления запусками саб-агентов (предоставляются RunTools).
RUN_TOOL_METHODS = (
    "view_runs",
    "cancel_run",
    "pause_run",
    "resume_run",
    "message_run",
    "replace_task_run",
    "reprioritize_run",
    "get_world_state",
    "wait_for_event",
)


def unavailable_run_tools() -> object:
    """Заглушка RunTools для случая, когда server context недоступен."""

    def make(name: str) -> Callable[..., dict[str, object]]:
        def _handler(*_args: object, **_kwargs: object) -> dict[str, object]:
            return {
                "ok": False,
                "error": f"Инструмент {name} недоступен: отсутствует server context",
                "available": False,
            }

        return _handler

    return type("_UnavailableRunTools", (), {name: make(name) for name in RUN_TOOL_METHODS})()


def operator_tool_specs(delegate_tools: Any, run_tools: Any) -> list[ToolSpec]:
    """Полный упорядоченный список ToolSpec оператора с реальными обработчиками.

    ``delegate_tools`` и ``run_tools`` предоставляют обработчики; для описания
    инструментов в UI можно передать заглушки (обработчики там не вызываются).
    """
    mouse = SystemMouseTools()
    keyboard = SystemKeyboardTools()
    screen = ScreenTools()
    ui = UIAutomationTools()
    memory = MemoryTools()

    return [
        ToolSpec(
            "delegate_task",
            "Делегировать задачу одному доступному специализированному агенту из available_agents. Параметры: agent_name (имя), task (задача), images (опционально — список base64-строк изображений для передачи агенту)",
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
        ToolSpec("finish_task", "Завершить задачу и вернуть итоговый ответ. attach_images=true встроит в summary картинки, увиденные за этот запуск (свои и от делегированных саб-агентов) как markdown-изображения.", 0, finish_task, {"summary": "str?", "status": "str?", "changed_files": "list?", "verification": "list?", "risks": "list?", "attach_images": "bool?"}),
        ToolSpec(
            "get_agent_memory",
            "Просмотреть долгосрочную память доступного саб-агента. Без agent — сводка по агентам. С agent — история указанного агента. limit — кол-во последних записей (по умолчанию 10).",
            0,
            memory.get_agent_memory,
            {"agent": "str?", "limit": "int?"},
        ),
        ToolSpec("view_runs", "Показать активные запуски саб-агентов. limit — максимальное количество записей.", 0, run_tools.view_runs, {"limit": "int?"}),
        ToolSpec("cancel_run", "Отменить активный запуск саб-агента по run_id.", 0, run_tools.cancel_run, {"run_id": "str"}),
        ToolSpec("pause_run", "Приостановить активный запуск саб-агента по run_id.", 0, run_tools.pause_run, {"run_id": "str"}),
        ToolSpec("resume_run", "Возобновить приостановленный запуск саб-агента по run_id.", 0, run_tools.resume_run, {"run_id": "str"}),
        ToolSpec("message_run", "Отправить сообщение в inbox активного запуска саб-агента по run_id.", 0, run_tools.message_run, {"run_id": "str", "message": "str"}),
        ToolSpec("replace_task_run", "Заменить задачу (user_goal) у активного запуска саб-агента по run_id.", 0, run_tools.replace_task_run, {"run_id": "str", "task": "str"}),
        ToolSpec("reprioritize_run", "Изменить приоритет активного run (priority: 1=высший, 10=низший).", 0, run_tools.reprioritize_run, {"run_id": "str", "priority": "int"}),
        ToolSpec("get_world_state", "Получить структурированный снимок состояния всей системы: активные run, вопросы, блокировки.", 0, run_tools.get_world_state, {}),
        ToolSpec("wait_for_event", "Ждать завершения конкретного run. run_id — идентификатор, timeout_seconds — максимальное ожидание.", 0, run_tools.wait_for_event, {"run_id": "str", "timeout_seconds": "float?"}),
        ToolSpec("get_screen_info", "Получить геометрию экранов, позицию курсора и активное окно Windows.", 0, screen.get_screen_info, {}),
        ToolSpec("take_screenshot", "Создать скриншот экрана и вернуть его в формате base64 (PNG). Поддерживает опциональную область: x, y, width, height.", 0, screen.take_screenshot, {"x": "int?", "y": "int?", "width": "int?", "height": "int?"}),
        ToolSpec("read_image", "Прочитать изображение по пути к файлу и вернуть его в формате base64. Аргументы: path (str) - путь к файлу изображения. Возвращает словарь с ключами: image (base64-строка), format (MIME-тип), path (абсолютный путь), size (размер в байтах).", 0, screen.read_image, {"path": "str"}),
        ToolSpec("system_mouse_move", "Реально переместить системный курсор Windows по координатам экрана. После движения возвращает свежий crop вокруг курсора для проверки hotspot.", 0, mouse.move, {"x": "int", "y": "int"}),
        ToolSpec("system_mouse_nudge", "Сместить системный курсор относительно текущей позиции на dx/dy пикселей. После движения возвращает crop вокруг курсора.", 0, mouse.nudge, {"dx": "int", "dy": "int"}),
        ToolSpec("system_mouse_click", "Выполнить системный клик Windows в текущей позиции курсора. Не принимает x/y; после клика возвращает crop вокруг курсора для проверки фокуса.", 0, mouse.click, {"button": "str?"}),
        ToolSpec("system_mouse_double_click", "Выполнить двойной левый клик Windows в текущей позиции курсора. Не принимает x/y; после клика возвращает crop вокруг курсора для проверки результата.", 0, mouse.double_click, {}),
        ToolSpec("system_mouse_scroll", "Прокрутить колесо мыши Windows. clicks < 0 вниз, clicks > 0 вверх.", 0, mouse.scroll, {"clicks": "int", "x": "int?", "y": "int?"}),
        ToolSpec("system_mouse_drag", "Перетащить мышью от from_x/from_y до to_x/to_y.", 0, mouse.drag, {"from_x": "int", "from_y": "int", "to_x": "int", "to_y": "int", "duration_ms": "int?"}),
        ToolSpec("system_type_text", "Ввести текст в активное поле через системную клавиатуру Windows. Перед вводом убедись, что нужное поле в фокусе.", 0, keyboard.type_text, {"text": "str", "interval_ms": "int?"}),
        ToolSpec("system_key_press", "Нажать клавишу или сочетание клавиш Windows: enter, tab, esc, win+r, alt+tab, ctrl+shift+esc, printscreen, numpad1, vk:0x5b.", 0, keyboard.press_key, {"key": "str", "repeats": "int?"}),
        ToolSpec("list_ui_elements", "Получить элементы активного окна через Windows UI Automation. Возвращает id, name, control_type, rect, center, clickable_point и patterns. Используй перед координатной мышью.", 0, ui.list_ui_elements, {"query": "str?", "max_results": "int?", "include_offscreen": "bool?"}),
        ToolSpec("click_ui_element", "Кликнуть элемент из последнего list_ui_elements по id. Используй вместо ручного подбора координат, когда элемент найден структурно.", 0, ui.click_ui_element, {"id": "int", "button": "str?"}),
        ToolSpec("focus_ui_element", "Сфокусировать элемент из последнего list_ui_elements по id. Полезно для полей ввода перед system_type_text.", 0, ui.focus_ui_element, {"id": "int"}),
    ]
