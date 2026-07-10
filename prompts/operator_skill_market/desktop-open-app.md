modes: pc

requires: system_key_press, system_type_text
tags: windows, apps, launch

# Открытие приложения Windows

Цель: запустить приложение устойчиво через системный поиск.

1. Нажми `system_key_press("win")`.
2. Введи название приложения.
3. Подожди коротко и нажми `system_key_press("enter")`.
4. Проверь активное окно через screenshot или `get_screen_info`.

Если открылось не то приложение, не продолжай задачу в неверном окне.
