"""Utilities for normalizing recorded keyboard input across the app."""

SPECIAL_KEY_ALIASES = {
    "escape": "esc",
    "esc": "esc",
    "return": "enter",
    "enter": "enter",
    "del": "delete",
    "delete": "delete",
    "backspace": "backspace",
    "tab": "tab",
    "space": "space",
    "arrowup": "up",
    "up": "up",
    "arrowdown": "down",
    "down": "down",
    "arrowleft": "left",
    "left": "left",
    "arrowright": "right",
    "right": "right",
    "home": "home",
    "end": "end",
    "page_up": "pageup",
    "pageup": "pageup",
    "page_down": "pagedown",
    "pagedown": "pagedown",
    "insert": "insert",
    "caps_lock": "capslock",
    "capslock": "capslock",
    "num_lock": "numlock",
    "numlock": "numlock",
    "scroll_lock": "scrolllock",
    "scrolllock": "scrolllock",
    "print_screen": "printscreen",
    "printscreen": "printscreen",
    "pause": "pause",
    "ctrl": "ctrl",
    "control": "ctrl",
    "ctrl_l": "ctrl",
    "ctrl_r": "ctrl",
    "alt": "alt",
    "alt_l": "alt",
    "alt_r": "alt",
    "shift": "shift",
    "shift_l": "shift",
    "shift_r": "shift",
    "cmd": "cmd",
    "command": "cmd",
    "cmd_l": "cmd",
    "cmd_r": "cmd",
}

SPECIAL_KEY_DISPLAY = {
    "esc": "Esc",
    "enter": "Enter",
    "delete": "Delete",
    "backspace": "Backspace",
    "tab": "Tab",
    "space": "Space",
    "up": "Up",
    "down": "Down",
    "left": "Left",
    "right": "Right",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "insert": "Insert",
    "capslock": "CapsLock",
    "numlock": "NumLock",
    "scrolllock": "ScrollLock",
    "pause": "Pause",
    "printscreen": "PrintScreen",
    "ctrl": "Ctrl",
    "alt": "Alt",
    "shift": "Shift",
    "cmd": "Cmd",
}

SPECIAL_KEY_CODES = {
    "esc": "Escape",
    "enter": "Enter",
    "delete": "Delete",
    "backspace": "Backspace",
    "tab": "Tab",
    "space": "Space",
    "up": "ArrowUp",
    "down": "ArrowDown",
    "left": "ArrowLeft",
    "right": "ArrowRight",
    "home": "Home",
    "end": "End",
    "pageup": "PageUp",
    "pagedown": "PageDown",
    "insert": "Insert",
}

CHARACTER_KEY_CODES = {
    "`": "Backquote",
    "-": "Minus",
    "=": "Equal",
    "[": "BracketLeft",
    "]": "BracketRight",
    "\\": "Backslash",
    ";": "Semicolon",
    "'": "Quote",
    ",": "Comma",
    ".": "Period",
    "/": "Slash",
}


def normalize_key_name(value: str) -> str:
    if not value:
        return ""

    normalized = value.strip().lower()
    if len(normalized) == 1 and 1 <= ord(normalized) <= 26:
        normalized = chr(ord("a") + ord(normalized) - 1)
    if normalized.startswith("key."):
        normalized = normalized[4:]

    if normalized.startswith("arrow"):
        normalized = normalized[5:]

    if normalized.startswith("f") and normalized[1:].isdigit():
        return normalized

    return SPECIAL_KEY_ALIASES.get(normalized, normalized)


def is_special_key_name(value: str) -> bool:
    normalized = normalize_key_name(value)
    return bool(normalized) and (
        normalized in SPECIAL_KEY_DISPLAY or
        (normalized.startswith("f") and normalized[1:].isdigit())
    )


def display_key_name(value: str) -> str:
    normalized = normalize_key_name(value)
    if normalized.startswith("f") and normalized[1:].isdigit():
        return normalized.upper()
    if len(normalized) == 1 and normalized.isalpha():
        return normalized.upper()
    return SPECIAL_KEY_DISPLAY.get(normalized, value)


def normalize_key_combo(value: str) -> str:
    if not value:
        return ""

    parts = [normalize_key_name(part) for part in value.split("+") if part.strip()]
    modifiers = []
    main_key = ""
    modifier_order = {"ctrl": 0, "shift": 1, "alt": 2, "cmd": 3, "space": 4}

    for part in parts:
        if part in modifier_order:
            if part not in modifiers:
                modifiers.append(part)
        elif not main_key:
            main_key = part

    modifiers.sort(key=lambda item: modifier_order[item])
    if main_key:
        modifiers.append(main_key)
    return "+".join(modifiers)


def display_key_combo(value: str) -> str:
    normalized = normalize_key_combo(value)
    if not normalized:
        return ""
    return " + ".join(display_key_name(part) for part in normalized.split("+"))


def normalize_key_code(value: str) -> str:
    return (value or "").strip()


def key_code_from_key_name(value: str) -> str:
    normalized = normalize_key_name(value)
    if not normalized:
        return ""
    if normalized in SPECIAL_KEY_CODES:
        return SPECIAL_KEY_CODES[normalized]
    if normalized.startswith("f") and normalized[1:].isdigit():
        return normalized.upper()
    if len(normalized) == 1 and normalized.isalpha():
        return f"Key{normalized.upper()}"
    if len(normalized) == 1 and normalized.isdigit():
        return f"Digit{normalized}"
    return CHARACTER_KEY_CODES.get(normalized, "")


def key_code_from_char(char: str, vk: int | None = None) -> str:
    normalized = normalize_key_name(char)
    if not normalized:
        return ""

    if vk is not None:
        if 96 <= vk <= 105:
            return f"Numpad{vk - 96}"
        keypad_codes = {
            106: "NumpadMultiply",
            107: "NumpadAdd",
            109: "NumpadSubtract",
            110: "NumpadDecimal",
            111: "NumpadDivide",
        }
        if vk in keypad_codes:
            return keypad_codes[vk]

    return key_code_from_key_name(normalized)
