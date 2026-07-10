modes: pc

requires: system_key_press, system_type_text
tags: browser, search, navigation

# Поиск в браузере

Цель: выполнить поиск без кликов по адресной строке.

1. Нажми `system_key_press("ctrl+l")`.
2. Введи запрос через `system_type_text`.
3. Нажми `system_key_press("enter")`.
4. Проверь, что страница результатов загрузилась и запрос виден на странице.

Если браузер не активен, сначала определи активное окно через screenshot или screen info.
