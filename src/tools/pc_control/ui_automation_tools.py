from __future__ import annotations

import base64
import json
import platform
import subprocess
import time
from typing import Any

from src.infra.errors import ToolExecutionError
from src.tools.pc_control.system_mouse_tools import SystemMouseTools


class UIAutomationTools:
    """Windows UI Automation helpers for structured GUI interaction."""

    def __init__(self) -> None:
        self._last_elements: list[dict[str, Any]] = []

    def list_ui_elements(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        max_results = self._read_int(args, "max_results", 80, minimum=1, maximum=200)
        query = str(args.get("query", "") or "").strip().lower()
        include_offscreen = bool(args.get("include_offscreen", False))

        script = """
Add-Type -AssemblyName UIAutomationClient
Add-Type -AssemblyName UIAutomationTypes
Add-Type @"
using System;
using System.Runtime.InteropServices;
public static class Win32 {
  [DllImport("user32.dll")] public static extern bool SetProcessDPIAware();
  [DllImport("user32.dll")] public static extern IntPtr GetForegroundWindow();
}
"@
[Win32]::SetProcessDPIAware() | Out-Null
$hwnd = [Win32]::GetForegroundWindow()
$root = [System.Windows.Automation.AutomationElement]::FromHandle($hwnd)
if ($null -eq $root) {
  [PSCustomObject]@{ ok = $false; error = "active window automation element not found"; elements = @() } | ConvertTo-Json -Depth 8 -Compress
  exit
}
$items = New-Object System.Collections.Generic.List[object]
$all = $root.FindAll([System.Windows.Automation.TreeScope]::Descendants, [System.Windows.Automation.Condition]::TrueCondition)
foreach ($el in $all) {
  try {
    $rect = $el.Current.BoundingRectangle
    if ($rect.Width -le 0 -or $rect.Height -le 0) { continue }
    if (-not __INCLUDE_OFFSCREEN__ -and $el.Current.IsOffscreen) { continue }
    $name = [string]$el.Current.Name
    $automationId = [string]$el.Current.AutomationId
    $className = [string]$el.Current.ClassName
    $controlType = $el.Current.ControlType.ProgrammaticName -replace '^ControlType\\.', ''
    $haystack = (($name + " " + $automationId + " " + $className + " " + $controlType).ToLowerInvariant())
    if ("__QUERY__" -ne "" -and -not $haystack.Contains("__QUERY__")) { continue }
    $clickable = $null
    $point = New-Object System.Windows.Point
    if ($el.TryGetClickablePoint([ref]$point)) {
      $clickable = @{ x = [int][Math]::Round($point.X); y = [int][Math]::Round($point.Y) }
    }
    $patterns = @()
    foreach ($patternName in @("InvokePattern", "ValuePattern", "TextPattern", "SelectionItemPattern", "ExpandCollapsePattern", "TogglePattern")) {
      try {
        $patternField = [System.Windows.Automation.AutomationPattern].Assembly.GetType("System.Windows.Automation.$patternName").GetField("Pattern")
        if ($null -ne $patternField) {
          $pattern = $patternField.GetValue($null)
          $tmp = $null
          if ($el.TryGetCurrentPattern($pattern, [ref]$tmp)) { $patterns += $patternName }
        }
      } catch {}
    }
    $items.Add([PSCustomObject]@{
      name = $name
      automation_id = $automationId
      class_name = $className
      control_type = $controlType
      enabled = $el.Current.IsEnabled
      offscreen = $el.Current.IsOffscreen
      focusable = $el.Current.IsKeyboardFocusable
      has_keyboard_focus = $el.Current.HasKeyboardFocus
      rect = @{
        x = [int][Math]::Round($rect.X)
        y = [int][Math]::Round($rect.Y)
        width = [int][Math]::Round($rect.Width)
        height = [int][Math]::Round($rect.Height)
      }
      center = @{
        x = [int][Math]::Round($rect.X + $rect.Width / 2)
        y = [int][Math]::Round($rect.Y + $rect.Height / 2)
      }
      clickable_point = $clickable
      patterns = $patterns
    }) | Out-Null
    if ($items.Count -ge __MAX_RESULTS__) { break }
  } catch {}
}
[PSCustomObject]@{
  ok = $true
  active_window = @{
    name = [string]$root.Current.Name
    class_name = [string]$root.Current.ClassName
    automation_id = [string]$root.Current.AutomationId
  }
  count = $items.Count
  elements = $items
} | ConvertTo-Json -Depth 8 -Compress
"""
        script = (
            script.replace("__MAX_RESULTS__", str(max_results))
            .replace("__QUERY__", self._escape_ps_literal(query))
            .replace("__INCLUDE_OFFSCREEN__", "$true" if include_offscreen else "$false")
        )
        payload = self._run_json(script)
        elements = payload.get("elements", [])
        if isinstance(elements, dict):
            elements = [elements]
        if not isinstance(elements, list):
            elements = []
        normalized: list[dict[str, Any]] = []
        for index, item in enumerate(elements, start=1):
            if not isinstance(item, dict):
                continue
            item = dict(item)
            item["id"] = index
            normalized.append(item)
        self._last_elements = normalized
        payload["elements"] = normalized
        payload["count"] = len(normalized)
        return payload

    def click_ui_element(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        element_id = self._read_int(args, "id", 0, minimum=1, maximum=10_000)
        button = str(args.get("button", "left")).strip().lower()
        if button not in {"left", "right"}:
            raise ToolExecutionError("button должен быть left или right")
        if not self._last_elements:
            raise ToolExecutionError("Нет сохранённого списка UI элементов. Сначала вызови list_ui_elements().")
        match = next((item for item in self._last_elements if item.get("id") == element_id), None)
        if not match:
            raise ToolExecutionError(f"UI элемент с id={element_id} не найден в последнем list_ui_elements().")

        point = self._point_for_element(match)
        mouse = SystemMouseTools()
        move_result = mouse.move(point)
        click_result = mouse.click({"button": button})
        return {
            "ok": True,
            "action": "click_ui_element",
            "id": element_id,
            "button": button,
            "element": self._compact_element(match),
            "point": point,
            "move": self._strip_image(move_result),
            **click_result,
        }

    def focus_ui_element(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        element_id = self._read_int(args, "id", 0, minimum=1, maximum=10_000)
        if not self._last_elements:
            raise ToolExecutionError("Нет сохранённого списка UI элементов. Сначала вызови list_ui_elements().")
        match = next((item for item in self._last_elements if item.get("id") == element_id), None)
        if not match:
            raise ToolExecutionError(f"UI элемент с id={element_id} не найден в последнем list_ui_elements().")

        point = self._point_for_element(match)
        mouse = SystemMouseTools()
        move_result = mouse.move(point)
        click_result = mouse.click({"button": "left"})
        return {
            "ok": True,
            "action": "focus_ui_element",
            "id": element_id,
            "element": self._compact_element(match),
            "point": point,
            "move": self._strip_image(move_result),
            **click_result,
        }

    def _point_for_element(self, element: dict[str, Any]) -> dict[str, int]:
        raw_point = element.get("clickable_point") or element.get("center")
        if not isinstance(raw_point, dict):
            raise ToolExecutionError("У UI элемента нет координат для клика")
        try:
            return {"x": int(raw_point["x"]), "y": int(raw_point["y"])}
        except (KeyError, TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректные координаты UI элемента: {raw_point}") from exc

    def _compact_element(self, element: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": element.get("id"),
            "name": element.get("name"),
            "control_type": element.get("control_type"),
            "automation_id": element.get("automation_id"),
            "class_name": element.get("class_name"),
            "rect": element.get("rect"),
            "clickable_point": element.get("clickable_point"),
            "patterns": element.get("patterns"),
        }

    def _strip_image(self, result: dict[str, Any]) -> dict[str, Any]:
        copy = dict(result)
        copy.pop("image", None)
        if copy.get("_type") == "image":
            copy["_type"] = "system_mouse"
            copy["image_attached"] = True
        return copy

    def _run_json(self, script: str) -> dict[str, Any]:
        encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
        completed = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-EncodedCommand", encoded],
            capture_output=True,
            text=True,
            check=True,
            timeout=20,
        )
        raw = completed.stdout.strip()
        if not raw:
            return {"ok": False, "error": "empty UI Automation response", "elements": []}
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise ToolExecutionError(f"Некорректный JSON от UI Automation: {raw[:500]}") from exc
        return payload if isinstance(payload, dict) else {"ok": False, "raw": payload, "elements": []}

    def _ensure_windows(self) -> None:
        if platform.system().lower() != "windows":
            raise ToolExecutionError("UI Automation сейчас поддерживается только на Windows")

    def _read_int(self, args: dict[str, Any], name: str, default: int, minimum: int, maximum: int) -> int:
        raw = args.get(name, default)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректный параметр {name}: {raw}") from exc
        return max(minimum, min(maximum, value))

    def _escape_ps_literal(self, value: str) -> str:
        return value.replace("`", "``").replace('"', '`"')
