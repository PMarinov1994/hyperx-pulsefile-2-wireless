import enum
from dataclasses import dataclass

ENTRY_SIZE = 4
ENTRIES_PER_PAGE = 15


class Button(enum.IntEnum):
    LEFT = 0x01
    RIGHT = 0x02
    MIDDLE = 0x04
    BACK = 0x08
    FORWARD = 0x10
    DPI = 0x20

    @property
    def label(self) -> str:
        return self.name.lower()


class ActionType(enum.IntEnum):
    MOUSE = 0x01
    KEYBOARD = 0x02
    CONSUMER = 0x03
    EXTRA = 0x04
    MEDIA_DAC = 0x05
    GAMEPAD = 0x06


MOUSE_SINGLE_CLICK = 0x01


@dataclass(frozen=True)
class Action:
    kind: int
    first: int
    second: int

    def to_bytes(self) -> bytes:
        return bytes([self.first, self.second])

    @property
    def label(self) -> str:
        for name, action in ACTIONS.items():
            if action == self:
                return name
        for name, code in KEYBOARD_KEYS.items():
            if self == keyboard_action(code):
                return f"key:{name}"
        return f"raw {self.kind:02x} {self.first:02x} {self.second:02x}"


@dataclass(frozen=True)
class Assignment:
    button: int
    action: Action

    @property
    def button_label(self) -> str:
        try:
            return Button(self.button).label
        except ValueError:
            return f"button {self.button:#04x}"

    def to_bytes(self) -> bytes:
        return bytes([self.action.kind, self.button]) + self.action.to_bytes()

    @classmethod
    def from_bytes(cls, entry: bytes) -> "Assignment":
        return cls(entry[1], Action(entry[0], entry[2], entry[3]))


def mouse_action(button: Button) -> Action:
    return Action(ActionType.MOUSE, button, MOUSE_SINGLE_CLICK)


def keyboard_action(code: int) -> Action:
    return Action(ActionType.KEYBOARD, code, 0)


def consumer_action(code: int) -> Action:
    return Action(ActionType.CONSUMER, code & 0xFF, code >> 8)


def extra_action(code: int) -> Action:
    return Action(ActionType.EXTRA, code, 0)


ACTIONS: dict[str, Action] = {
    **{button.label: mouse_action(button) for button in Button if button is not Button.DPI},
    "disable": extra_action(0),
    "dpi-up": extra_action(1),
    "dpi-down": extra_action(2),
    "dpi-next": extra_action(3),
    "dpi-previous": extra_action(4),
    "dpi-clutch": extra_action(5),
    "next-app": extra_action(6),
    "previous-app": extra_action(7),
    "play-pause": consumer_action(205),
    "next-track": consumer_action(181),
    "previous-track": consumer_action(182),
    "stop": consumer_action(183),
    "mute": consumer_action(226),
    "volume-up": consumer_action(233),
    "volume-down": consumer_action(234),
    "calculator": consumer_action(402),
    "mail": consumer_action(394),
    "search": consumer_action(545),
    "browser-home": consumer_action(547),
    "browser-back": consumer_action(548),
    "browser-forward": consumer_action(549),
    "browser-refresh": consumer_action(551),
}

KEYBOARD_KEYS: dict[str, int] = {
    **{chr(ord("a") + offset): 4 + offset for offset in range(26)},
    **{str(digit): 29 + digit for digit in range(1, 10)},
    "0": 39,
    "enter": 40,
    "esc": 41,
    "backspace": 42,
    "tab": 43,
    "space": 44,
    "minus": 45,
    "equal": 46,
    "left-bracket": 47,
    "right-bracket": 48,
    "backslash": 49,
    "semicolon": 51,
    "quote": 52,
    "grave": 53,
    "comma": 54,
    "dot": 55,
    "slash": 56,
    "caps-lock": 57,
    **{f"f{number}": 57 + number for number in range(1, 13)},
    "print-screen": 70,
    "scroll-lock": 71,
    "pause": 72,
    "insert": 73,
    "home": 74,
    "page-up": 75,
    "delete": 76,
    "end": 77,
    "page-down": 78,
    "right": 79,
    "left": 80,
    "down": 81,
    "up": 82,
    "num-lock": 83,
    "num-divide": 84,
    "num-multiply": 85,
    "num-minus": 86,
    "num-plus": 87,
    "num-enter": 88,
    **{f"num-{digit}": 88 + digit for digit in range(1, 10)},
    "num-0": 98,
    "num-dot": 99,
    "menu": 101,
    **{f"f{number}": 91 + number for number in range(13, 25)},
    "left-ctrl": 224,
    "left-shift": 225,
    "left-alt": 226,
    "left-super": 227,
    "right-ctrl": 228,
    "right-shift": 229,
    "right-alt": 230,
    "right-super": 231,
}


def parse_action(text: str) -> Action:
    name = text.strip().lower()
    if name.startswith("key:"):
        key = name.removeprefix("key:")
        if key not in KEYBOARD_KEYS:
            msg = f"unknown key {key!r}, see 'pulsefire button --help' for the key names"
            raise ValueError(msg)
        return keyboard_action(KEYBOARD_KEYS[key])
    if name not in ACTIONS:
        msg = f"unknown action {text!r}, see 'pulsefire button --help' for the action names"
        raise ValueError(msg)
    return ACTIONS[name]


def is_default(assignment: Assignment) -> bool:
    try:
        button = Button(assignment.button)
    except ValueError:
        return False
    return button is not Button.DPI and assignment.action == mouse_action(button)
