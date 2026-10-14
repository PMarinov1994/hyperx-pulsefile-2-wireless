import enum
from dataclasses import dataclass
from pathlib import Path

from ngenuity_linux_cli.buttons import Button
from ngenuity_linux_cli.protocol import PollingRate

VENDOR_ID = 0x03F0
VENDOR_USAGE_PAGE = b"\x06\x00\xff"
HID_DEVICES = Path("/sys/bus/hid/devices")
HID_ID_PARTS = 3


class Category(enum.IntEnum):
    KEYBOARD = 1
    MOUSE = 2
    HEADSET = 3
    MICROPHONE = 4
    MOUSE_PAD = 5
    GAMEPAD = 6
    STREAMING_DECK = 7
    WEBCAM = 8
    MONITOR = 9
    AUDIO_DAC = 10
    AUDIO_MIXER = 11
    DONGLE_3IN1 = 12
    UNKNOWN = 0xFF

    @classmethod
    def from_byte(cls, value: int) -> "Category":
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").lower()


class Effect(enum.StrEnum):
    SOLID = "solid"
    BREATHING = "breathing"
    ALTERNATING = "alternating"
    CONFETTI = "confetti"
    SPECTRUM = "spectrum"
    WAVE = "wave"
    SUNRISE = "sunrise"


ALL_EFFECTS = tuple(Effect)
NO_SPECTRUM = tuple(effect for effect in Effect if effect is not Effect.SPECTRUM)
RATES_1K = (PollingRate.HZ_1000, PollingRate.HZ_500, PollingRate.HZ_250, PollingRate.HZ_125)
RATES_4K = (PollingRate.HZ_4000, PollingRate.HZ_2000, *RATES_1K)
RATES_8K = (PollingRate.HZ_8000, *RATES_4K)
MOUSE_BUTTONS = (Button.LEFT, Button.RIGHT, Button.MIDDLE, Button.BACK, Button.FORWARD, Button.DPI)
SAGA_BUTTONS = MOUSE_BUTTONS[:-1]


@dataclass(frozen=True)
class Model:
    key: str
    name: str
    category: Category
    product_ids: tuple[int, ...] = ()
    tested: bool = False
    polling_rates: tuple[PollingRate, ...] = RATES_1K
    dpi_min: int = 200
    dpi_max: int = 26000
    dpi_step: int = 50
    buttons: tuple[Button, ...] = MOUSE_BUTTONS
    leds: int = 1
    effects: tuple[Effect, ...] = ALL_EFFECTS
    configurable: bool = True

    @property
    def has_lighting(self) -> bool:
        return self.leds > 0

    @property
    def status_label(self) -> str:
        if not self.configurable:
            return "detected only"
        return "tested" if self.tested else "untested"


MODELS: tuple[Model, ...] = (
    Model(
        "pulsefire-haste-2-wireless",
        "Pulsefire Haste 2 Wireless",
        Category.MOUSE,
        product_ids=(0x0F98,),
        tested=True,
    ),
    Model(
        "pulsefire-haste-2",
        "Pulsefire Haste 2",
        Category.MOUSE,
        polling_rates=RATES_8K,
        effects=NO_SPECTRUM,
    ),
    Model("pulsefire-haste-2-s", "Pulsefire Haste 2 S", Category.MOUSE),
    Model("pulsefire-haste-2-pro", "Pulsefire Haste 2 Pro", Category.MOUSE, polling_rates=RATES_4K),
    Model(
        "pulsefire-haste-3",
        "Pulsefire Haste 3",
        Category.MOUSE,
        dpi_min=100,
        dpi_max=16000,
        dpi_step=100,
        leds=0,
        effects=(),
    ),
    Model(
        "pulsefire-haste-3-pro",
        "Pulsefire Haste 3 Pro",
        Category.MOUSE,
        polling_rates=RATES_8K,
        dpi_min=50,
        dpi_max=42000,
        leds=0,
        effects=(),
    ),
    Model(
        "pulsefire-haste-3-wireless",
        "Pulsefire Haste 3 Wireless",
        Category.MOUSE,
        polling_rates=RATES_8K,
        dpi_min=50,
        dpi_max=42000,
        leds=0,
        effects=(),
    ),
    Model(
        "pulsefire-saga",
        "Pulsefire Saga",
        Category.MOUSE,
        polling_rates=RATES_8K,
        buttons=SAGA_BUTTONS,
        leds=5,
        effects=(Effect.BREATHING, Effect.SOLID, Effect.SPECTRUM, Effect.WAVE),
    ),
    Model(
        "pulsefire-saga-pro",
        "Pulsefire Saga Pro",
        Category.MOUSE,
        polling_rates=RATES_4K,
        buttons=SAGA_BUTTONS,
    ),
)

GENERIC_MOUSE = Model("generic-mouse", "HyperX mouse (unknown model)", Category.MOUSE)


def generic_model(category: Category) -> Model:
    if category is Category.MOUSE:
        return GENERIC_MOUSE
    return Model(
        f"generic-{category.name.lower().replace('_', '-')}",
        f"HyperX {category.label} (not supported yet)",
        category,
        buttons=(),
        leds=0,
        effects=(),
        configurable=False,
    )


def find_model(key: str) -> Model | None:
    for model in (*MODELS, GENERIC_MOUSE):
        if model.key == key:
            return model
    return None


def match_model(product_ids: set[int], category: Category) -> Model:
    for model in MODELS:
        if product_ids & set(model.product_ids):
            return model
    return generic_model(category)


@dataclass(frozen=True)
class Interface:
    path: Path
    product_id: int
    name: str


def hid_name(device: Path) -> str:
    for line in (device / "uevent").read_text().splitlines():
        if line.startswith("HID_NAME="):
            return line.removeprefix("HID_NAME=")
    return device.name


def list_interfaces() -> list[Interface]:
    interfaces: list[Interface] = []
    for device in sorted(HID_DEVICES.glob(f"*:{VENDOR_ID:04X}:*")):
        parts = device.name.split(":")
        if len(parts) != HID_ID_PARTS:
            continue
        try:
            descriptor = (device / "report_descriptor").read_bytes()
            nodes = sorted((device / "hidraw").iterdir())
        except OSError:
            continue
        if not descriptor.startswith(VENDOR_USAGE_PAGE) or not nodes:
            continue
        product_id = int(parts[2].split(".")[0], 16)
        interfaces.append(Interface(Path("/dev") / nodes[0].name, product_id, hid_name(device)))
    return interfaces
