import itertools
import math
import secrets
from collections.abc import Callable, Sequence

from pulsefire.colors import Rgb

FRAME_COUNT = 80
DEFAULT_SPEED = 50
ALTERNATING_SLOTS = 10
CONFETTI_COLORS = 8
CHANNEL_MAX = 255.0

type Stop = tuple[float, Rgb]

GRADIENT: tuple[Stop, ...] = (
    (0.0, Rgb(0xFF, 0x00, 0x00)),
    (0.1667, Rgb(0xFF, 0x66, 0x00)),
    (0.333, Rgb(0xF7, 0xB5, 0x00)),
    (0.5, Rgb(0x6D, 0xD4, 0x00)),
    (0.6667, Rgb(0x00, 0x9D, 0xFF)),
    (0.8333, Rgb(0x62, 0x36, 0xFF)),
    (1.0, Rgb(0xB6, 0x20, 0xE0)),
)

SUNRISE_GRADIENTS: tuple[tuple[Stop, ...], ...] = (
    ((0.0, Rgb(0xFF, 0xB2, 0x00)), (0.5, Rgb(0xFF, 0x61, 0x00))),
    (
        (0.0, Rgb(0xFF, 0xB2, 0x00)),
        (0.25, Rgb(0xFF, 0x61, 0x00)),
        (0.5, Rgb(0xFF, 0x14, 0x00)),
        (0.75, Rgb(0xFF, 0xB7, 0x00)),
    ),
    (
        (0.0, Rgb(0xFF, 0x82, 0x00)),
        (0.2, Rgb(0xFF, 0x99, 0x00)),
        (0.4, Rgb(0xFF, 0xA1, 0x00)),
        (0.6, Rgb(0xFF, 0xA8, 0x00)),
        (0.8, Rgb(0xFF, 0x61, 0x00)),
    ),
)

RAINBOW_HEX = (
    "ff0000 fb1000 f82000 f53000 f24000 ef5000 ec6000 e97000 "
    "e68100 e39100 dfa100 dcb100 d9c100 d6d100 d3e100 d0f200 "
    "cbff01 beff07 b1ff0e a4ff14 97ff1b 8aff21 7dff28 70ff2e "
    "63ff35 56ff3b 49ff42 3bff49 2eff4f 21ff56 14ff5c 07ff63 "
    "00fb6a 00f174 00e87e 00de87 00d491 00cb9a 00c1a4 00b8ae "
    "00aeb7 00a5c1 009bcb 0092d4 0088de 007ee7 0075f1 006bfb "
    "0764ff 145dff 2156ff 2e50ff 3b49ff 4843ff 553cff 6235ff "
    "6f2fff 7c28ff 8922ff 961bff a315ff b00eff bd07ff ca01ff "
    "cf00f2 d200e1 d500d1 d900c1 dc00b1 df00a1 e20091 e50081 "
    "e80070 ec0060 ef0050 f20040 f50030 f80020 fb0010 ff0000"
)


def channel(start: int, end: int, weight: float) -> int:
    return int(min(max((end - start) * weight + start, 0.0), CHANNEL_MAX))


def mix(start: Rgb, end: Rgb, weight: float) -> Rgb:
    return Rgb(
        channel(start.red, end.red, weight),
        channel(start.green, end.green, weight),
        channel(start.blue, end.blue, weight),
    )


def scale(color: Rgb, factor: float) -> Rgb:
    return mix(Rgb(0, 0, 0), color, factor)


def even_stops(colors: Sequence[Rgb]) -> tuple[Stop, ...]:
    if len(colors) == 1:
        return ((0.0, colors[0]),)
    return tuple((index / (len(colors) - 1), color) for index, color in enumerate(colors))


def gradient_at(stops: Sequence[Stop], position: float) -> Rgb:
    first_offset, first_color = stops[0]
    last_offset, last_color = stops[-1]
    if position < first_offset or position > last_offset:
        span = 1.0 - last_offset + first_offset
        weight = ((position - last_offset) % 1.0) / span if span else 0.0
        return mix(last_color, first_color, weight)
    for (start, start_color), (end, end_color) in itertools.pairwise(stops):
        if start <= position <= end:
            return mix(start_color, end_color, (position - start) / (end - start))
    return last_color


def frames(render: Callable[[float], Rgb]) -> list[Rgb]:
    return [render(index / (FRAME_COUNT - 1)) for index in range(FRAME_COUNT)]


def solid(color: Rgb) -> list[Rgb]:
    return [color] * FRAME_COUNT


def breathing(color: Rgb) -> list[Rgb]:
    return frames(lambda progress: scale(color, math.sin(progress * math.pi)))


def alternating(first: Rgb, second: Rgb, *, gradient: bool) -> list[Rgb]:
    def render(progress: float) -> Rgb:
        position = progress * ALTERNATING_SLOTS
        slot = int(position)
        current, other = (first, second) if slot % 2 == 0 else (second, first)
        if not gradient:
            return current
        return mix(current, other, position - slot)

    return frames(render)


def random_color() -> Rgb:
    return Rgb(secrets.randbelow(256), secrets.randbelow(256), secrets.randbelow(256))


def confetti() -> list[Rgb]:
    return spectrum([random_color() for _ in range(CONFETTI_COLORS)])


def spectrum(colors: Sequence[Rgb]) -> list[Rgb]:
    def render(progress: float) -> Rgb:
        position = progress * len(colors)
        index = int(position) % len(colors)
        return mix(colors[index], colors[(index + 1) % len(colors)], position - int(position))

    return frames(render)


def wave(stops: Sequence[Stop] = GRADIENT) -> list[Rgb]:
    return frames(lambda progress: gradient_at(stops, (1.0 - progress) % 1.0))


def sunrise() -> list[Rgb]:
    chosen = secrets.choice(SUNRISE_GRADIENTS)
    closed = (*chosen, (1.0, chosen[0][1]))
    return frames(lambda progress: gradient_at(closed, progress))


def rainbow() -> list[Rgb]:
    return [Rgb.parse(value) for value in RAINBOW_HEX.split()]
