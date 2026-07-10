modes: pc

requires: list_ui_elements, focus_ui_element, system_type_text

# Навык: ввод текста в поле

Цель: сфокусировать поле ввода и ввести текст без угадывания координат.

1. Вызови `list_ui_elements(query?, max_results?)`.
2. Выбери элемент типа `Edit`, `Document`, `ComboBox` или другой focusable элемент, имя которого похоже на нужное поле.
3. Вызови `focus_ui_element(id)`.
4. Проверь crop после фокуса: должна быть каретка, выделение, активная рамка или другое подтверждение фокуса.
5. Если фокус корректный, вызови `system_type_text(text)`.
6. Проверь результат через screenshot/crop или UI Automation.

Если UI Automation не нашла поле:
- сделай `take_screenshot` или crop;
- наведи `system_mouse_move`;
- если hotspot почти попал, исправь через `system_mouse_nudge`;
- только потом кликай и вводи.
