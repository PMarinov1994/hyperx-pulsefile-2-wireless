import re
from typing import NamedTuple, Self

_HEX_PATTERN = re.compile(r"#?([0-9a-fA-F]{6})")


class Rgb(NamedTuple):
    red: int
    green: int
    blue: int

    @classmethod
    def parse(cls, text: str) -> Self:
        name = text.strip().lower()
        if name in NAMED_COLORS:
            red, green, blue = NAMED_COLORS[name]
            return cls(red, green, blue)
        match = _HEX_PATTERN.fullmatch(name)
        if match is None:
            msg = f"unknown colour {text!r}, use a name or #rrggbb"
            raise ValueError(msg)
        value = bytes.fromhex(match.group(1))
        return cls(value[0], value[1], value[2])

    @property
    def hex(self) -> str:
        return f"#{self.red:02x}{self.green:02x}{self.blue:02x}"

    def name(self) -> str | None:
        for name, rgb in NAMED_COLORS.items():
            if rgb == self:
                return name
        return None

    def describe(self) -> str:
        name = self.name()
        return f"{self.hex} ({name})" if name else self.hex

    def to_bytes(self) -> bytes:
        return bytes(self)


NAMED_COLORS: dict[str, Rgb] = {
    "red": Rgb(0xFF, 0x00, 0x00),
    "green": Rgb(0x00, 0xFF, 0x00),
    "blue": Rgb(0x00, 0x00, 0xFF),
    "yellow": Rgb(0xFF, 0xFF, 0x00),
    "cyan": Rgb(0x00, 0xFF, 0xFF),
    "magenta": Rgb(0xFF, 0x00, 0xFF),
    "orange": Rgb(0xFF, 0x80, 0x00),
    "purple": Rgb(0x80, 0x00, 0xFF),
    "pink": Rgb(0xFF, 0x40, 0x80),
    "white": Rgb(0xFF, 0xFF, 0xFF),
    "off": Rgb(0x00, 0x00, 0x00),
}
