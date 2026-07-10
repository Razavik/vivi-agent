from __future__ import annotations

import ctypes
import ctypes.wintypes
import platform
import time
from typing import Any

from src.infra.errors import ToolExecutionError


INPUT_KEYBOARD = 1
KEYEVENTF_EXTENDEDKEY = 0x0001
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
MAPVK_VK_TO_VSC = 0


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.wintypes.WORD),
        ("wScan", ctypes.wintypes.WORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.wintypes.LONG),
        ("dy", ctypes.wintypes.LONG),
        ("mouseData", ctypes.wintypes.DWORD),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("time", ctypes.wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.wintypes.DWORD),
        ("wParamL", ctypes.wintypes.WORD),
        ("wParamH", ctypes.wintypes.WORD),
    ]


class INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("ki", KEYBDINPUT),
        ("mi", MOUSEINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.wintypes.DWORD),
        ("u", INPUT_UNION),
    ]


class SystemKeyboardTools:
    """Инструменты для имитации клавиатуры Windows."""

    _EXTENDED_KEYS = {
        0x21,  # PageUp
        0x22,  # PageDown
        0x23,  # End
        0x24,  # Home
        0x25,  # Left
        0x26,  # Up
        0x27,  # Right
        0x28,  # Down
        0x2D,  # Insert
        0x2E,  # Delete
        0x5B,  # Left Windows
        0x5C,  # Right Windows
        0x5D,  # Applications
        0x6F,  # Numpad Divide
        0xA3,  # Right Ctrl
        0xA5,  # Right Alt / AltGr
    }

    _KEYS: dict[str, int] = {
        "backspace": 0x08,
        "tab": 0x09,
        "cancel": 0x03,
        "clear": 0x0C,
        "enter": 0x0D,
        "return": 0x0D,
        "shift": 0x10,
        "ctrl": 0x11,
        "control": 0x11,
        "alt": 0x12,
        "menu": 0x12,
        "pause": 0x13,
        "break": 0x13,
        "capslock": 0x14,
        "caps": 0x14,
        "kana": 0x15,
        "hangul": 0x15,
        "junja": 0x17,
        "final": 0x18,
        "hanja": 0x19,
        "kanji": 0x19,
        "escape": 0x1B,
        "esc": 0x1B,
        "convert": 0x1C,
        "nonconvert": 0x1D,
        "accept": 0x1E,
        "modechange": 0x1F,
        "space": 0x20,
        "pageup": 0x21,
        "pgup": 0x21,
        "pagedown": 0x22,
        "pgdn": 0x22,
        "end": 0x23,
        "home": 0x24,
        "left": 0x25,
        "arrowleft": 0x25,
        "leftarrow": 0x25,
        "up": 0x26,
        "arrowup": 0x26,
        "uparrow": 0x26,
        "right": 0x27,
        "arrowright": 0x27,
        "rightarrow": 0x27,
        "down": 0x28,
        "arrowdown": 0x28,
        "downarrow": 0x28,
        "select": 0x29,
        "print": 0x2A,
        "execute": 0x2B,
        "printscreen": 0x2C,
        "prtsc": 0x2C,
        "prtscr": 0x2C,
        "sysrq": 0x2C,
        "snapshot": 0x2C,
        "insert": 0x2D,
        "ins": 0x2D,
        "delete": 0x2E,
        "del": 0x2E,
        "help": 0x2F,
        "win": 0x5B,
        "windows": 0x5B,
        "super": 0x5B,
        "meta": 0x5B,
        "cmd": 0x5B,
        "command": 0x5B,
        "lwin": 0x5B,
        "leftwin": 0x5B,
        "rwin": 0x5C,
        "rightwin": 0x5C,
        "apps": 0x5D,
        "app": 0x5D,
        "context": 0x5D,
        "contextmenu": 0x5D,
        "sleep": 0x5F,
        "num0": 0x60,
        "numpad0": 0x60,
        "num1": 0x61,
        "numpad1": 0x61,
        "num2": 0x62,
        "numpad2": 0x62,
        "num3": 0x63,
        "numpad3": 0x63,
        "num4": 0x64,
        "numpad4": 0x64,
        "num5": 0x65,
        "numpad5": 0x65,
        "num6": 0x66,
        "numpad6": 0x66,
        "num7": 0x67,
        "numpad7": 0x67,
        "num8": 0x68,
        "numpad8": 0x68,
        "num9": 0x69,
        "numpad9": 0x69,
        "multiply": 0x6A,
        "numpadmultiply": 0x6A,
        "add": 0x6B,
        "numpadadd": 0x6B,
        "numpadplus": 0x6B,
        "separator": 0x6C,
        "subtract": 0x6D,
        "numpadsubtract": 0x6D,
        "numpadminus": 0x6D,
        "decimal": 0x6E,
        "numpaddecimal": 0x6E,
        "divide": 0x6F,
        "numpaddivide": 0x6F,
        "numlock": 0x90,
        "scrolllock": 0x91,
        "scroll": 0x91,
        "lshift": 0xA0,
        "leftshift": 0xA0,
        "rshift": 0xA1,
        "rightshift": 0xA1,
        "lctrl": 0xA2,
        "leftctrl": 0xA2,
        "lcontrol": 0xA2,
        "leftcontrol": 0xA2,
        "rctrl": 0xA3,
        "rightctrl": 0xA3,
        "rcontrol": 0xA3,
        "rightcontrol": 0xA3,
        "lalt": 0xA4,
        "leftalt": 0xA4,
        "ralt": 0xA5,
        "rightalt": 0xA5,
        "altgr": 0xA5,
        "browserback": 0xA6,
        "browser_back": 0xA6,
        "browserforward": 0xA7,
        "browser_forward": 0xA7,
        "browserrefresh": 0xA8,
        "browser_refresh": 0xA8,
        "browserstop": 0xA9,
        "browser_stop": 0xA9,
        "browsersearch": 0xAA,
        "browser_search": 0xAA,
        "browserfavorites": 0xAB,
        "browser_favorites": 0xAB,
        "browserhome": 0xAC,
        "browser_home": 0xAC,
        "volumemute": 0xAD,
        "volume_mute": 0xAD,
        "mute": 0xAD,
        "volumedown": 0xAE,
        "volume_down": 0xAE,
        "volumeup": 0xAF,
        "volume_up": 0xAF,
        "medianext": 0xB0,
        "media_next": 0xB0,
        "mediaprev": 0xB1,
        "media_previous": 0xB1,
        "mediaprevious": 0xB1,
        "media_prev": 0xB1,
        "mediastop": 0xB2,
        "media_stop": 0xB2,
        "mediaplaypause": 0xB3,
        "media_play_pause": 0xB3,
        "playpause": 0xB3,
        "launchmail": 0xB4,
        "launch_mail": 0xB4,
        "launchmedia": 0xB5,
        "launch_media": 0xB5,
        "launchapp1": 0xB6,
        "launch_app1": 0xB6,
        "launchapp2": 0xB7,
        "launch_app2": 0xB7,
        "semicolon": 0xBA,
        ";": 0xBA,
        "equals": 0xBB,
        "=": 0xBB,
        "plus": 0xBB,
        "oemplus": 0xBB,
        "oem_plus": 0xBB,
        "comma": 0xBC,
        ",": 0xBC,
        "dash": 0xBD,
        "minus": 0xBD,
        "oemminus": 0xBD,
        "oem_minus": 0xBD,
        "-": 0xBD,
        "period": 0xBE,
        ".": 0xBE,
        "slash": 0xBF,
        "/": 0xBF,
        "backtick": 0xC0,
        "grave": 0xC0,
        "`": 0xC0,
        "bracketleft": 0xDB,
        "leftbracket": 0xDB,
        "[": 0xDB,
        "backslash": 0xDC,
        "\\": 0xDC,
        "bracketright": 0xDD,
        "rightbracket": 0xDD,
        "]": 0xDD,
        "quote": 0xDE,
        "apostrophe": 0xDE,
        "'": 0xDE,
    }

    def type_text(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        text = str(args.get("text", ""))
        if not text:
            raise ToolExecutionError("Параметр text не может быть пустым")
        interval_ms = self._read_interval(args)
        for code_unit in self._utf16_code_units(text):
            self._send_unicode_code_unit(code_unit)
            if interval_ms:
                time.sleep(interval_ms / 1000)
        return {
            "ok": True,
            "action": "type_text",
            "chars": len(text),
            "_type": "keyboard",
        }

    def press_key(self, args: dict[str, Any]) -> dict[str, Any]:
        self._ensure_windows()
        raw_key = str(args.get("key", "")).strip()
        if not raw_key:
            raise ToolExecutionError("Параметр key не может быть пустым")
        repeats = self._read_repeats(args)
        keys = self._parse_key_combo(raw_key)
        for _ in range(repeats):
            self._press_combo(keys)
            time.sleep(0.04)
        return {
            "ok": True,
            "action": "press_key",
            "key": raw_key,
            "repeats": repeats,
            "_type": "keyboard",
        }

    def _ensure_windows(self) -> None:
        if platform.system().lower() != "windows":
            raise ToolExecutionError("Системный ввод клавиатуры сейчас поддерживается только на Windows")

    def _read_interval(self, args: dict[str, Any]) -> int:
        raw = args.get("interval_ms", 0)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректный interval_ms: {raw}") from exc
        return max(0, min(value, 1000))

    def _read_repeats(self, args: dict[str, Any]) -> int:
        raw = args.get("repeats", 1)
        try:
            value = int(raw)
        except (TypeError, ValueError) as exc:
            raise ToolExecutionError(f"Некорректный repeats: {raw}") from exc
        return max(1, min(value, 100))

    def _parse_key_combo(self, value: str) -> list[int]:
        keys = []
        for raw_part in value.split("+"):
            part = raw_part.strip().lower().replace(" ", "")
            if not part:
                continue
            keys.append(self._parse_single_key(part))
        if not keys:
            raise ToolExecutionError(f"Не удалось распознать клавишу: {value}")
        return keys

    def _parse_single_key(self, part: str) -> int:
        key = self._resolve_named_key(part)
        if key is not None:
            return key
        if part.startswith("vk:"):
            return self._parse_virtual_key_code(part)
        if len(part) == 1:
            return ord(part.upper())
        if part.startswith("f") and part[1:].isdigit():
            number = int(part[1:])
            if 1 <= number <= 24:
                return 0x70 + number - 1
            raise ToolExecutionError(f"Неподдерживаемая функциональная клавиша: {part}")
        raise ToolExecutionError(
            "Неподдерживаемая клавиша: "
            f"{part}. Примеры: win+r, ctrl+shift+esc, alt+tab, printscreen, numpad1, vk:0x5b"
        )

    def _resolve_named_key(self, part: str) -> int | None:
        if part in self._KEYS:
            return self._KEYS[part]
        compact = part.replace("_", "").replace("-", "")
        if compact in self._KEYS:
            return self._KEYS[compact]
        return None

    def _parse_virtual_key_code(self, part: str) -> int:
        raw = part[3:]
        try:
            value = int(raw, 0)
        except ValueError as exc:
            raise ToolExecutionError(f"Некорректный virtual-key код: {part}") from exc
        if not 0 <= value <= 0xFF:
            raise ToolExecutionError(f"Virtual-key код вне диапазона 0..255: {part}")
        return value

    def _press_combo(self, keys: list[int]) -> None:
        for key in keys:
            self._send_virtual_key(key, key_up=False)
        for key in reversed(keys):
            self._send_virtual_key(key, key_up=True)

    def _send_virtual_key(self, vk: int, *, key_up: bool) -> None:
        flags = self._virtual_key_flags(vk, key_up=key_up)
        scan = self._map_virtual_key(vk)
        try:
            self._send_input(INPUT_KEYBOARD, KEYBDINPUT(vk, scan, flags, 0, 0))
        except ToolExecutionError:
            self._send_virtual_key_fallback(vk, scan, flags)

    def _utf16_code_units(self, text: str) -> list[int]:
        raw = text.encode("utf-16le", errors="surrogatepass")
        return [raw[i] | (raw[i + 1] << 8) for i in range(0, len(raw), 2)]

    def _send_unicode_code_unit(self, code: int) -> None:
        self._send_input(INPUT_KEYBOARD, KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0))
        self._send_input(INPUT_KEYBOARD, KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))

    def _send_input(self, input_type: int, keyboard_input: KEYBDINPUT) -> None:
        command = INPUT(type=input_type, u=INPUT_UNION(ki=keyboard_input))
        user32 = self._user32()
        sent = user32.SendInput(1, ctypes.byref(command), ctypes.sizeof(command))
        if sent != 1:
            raise ToolExecutionError(self._last_windows_error("Не удалось отправить клавиатурный ввод"))

    def _send_virtual_key_fallback(self, vk: int, scan: int, flags: int) -> None:
        try:
            self._user32().keybd_event(vk, scan, flags, 0)
        except OSError as exc:
            raise ToolExecutionError(self._last_windows_error("Не удалось отправить клавиатурный ввод")) from exc

    def _virtual_key_flags(self, vk: int, *, key_up: bool) -> int:
        flags = KEYEVENTF_KEYUP if key_up else 0
        if vk in self._EXTENDED_KEYS:
            flags |= KEYEVENTF_EXTENDEDKEY
        return flags

    def _map_virtual_key(self, vk: int) -> int:
        try:
            return int(self._user32().MapVirtualKeyW(vk, MAPVK_VK_TO_VSC))
        except OSError:
            return 0

    def _user32(self):
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SendInput.argtypes = [ctypes.wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
        user32.SendInput.restype = ctypes.wintypes.UINT
        user32.MapVirtualKeyW.argtypes = [ctypes.wintypes.UINT, ctypes.wintypes.UINT]
        user32.MapVirtualKeyW.restype = ctypes.wintypes.UINT
        user32.keybd_event.argtypes = [
            ctypes.wintypes.BYTE,
            ctypes.wintypes.BYTE,
            ctypes.wintypes.DWORD,
            ctypes.c_size_t,
        ]
        user32.keybd_event.restype = None
        return user32

    def _last_windows_error(self, prefix: str) -> str:
        code = ctypes.get_last_error()
        if not code:
            return prefix
        return f"{prefix}: Windows error {code}: {ctypes.FormatError(code)}"
