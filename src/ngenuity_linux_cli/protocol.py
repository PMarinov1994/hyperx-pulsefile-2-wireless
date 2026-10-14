import enum
from collections.abc import Callable
from dataclasses import dataclass, replace

from ngenuity_linux_cli.buttons import ENTRIES_PER_PAGE, ENTRY_SIZE, Assignment
from ngenuity_linux_cli.colors import Rgb

REPORT_SIZE = 64
LIVE_SLOT = 0
SAVED_SLOT = 1
BASE_LAYER = 1
KEY_PAGE_HEADER = 4

DPI_MIN = 50
DPI_MAX = 42000
DPI_STEP = 50
MAX_STAGES = 5
MAX_STAGE_SLOTS = 11
STAGE_SIZE = 5
BRIGHTNESS_MAX = 100
BRIGHTNESS_RAW_MAX = 0xFF
MIN_EVENT_LENGTH = 3
MAX_FRAMES = 255
CATEGORY_OFFSET = 31
PRODUCT_IDS_START = 37
PRODUCT_IDS_END = 47
FRAME_DATA_SIZE = REPORT_SIZE - 4
BATTERY_ALERT_MIN = 5
BATTERY_ALERT_MAX = 25

ACK_REPORT = 0xFF
ACK_SUB = 0x01
ACK_COMMAND_OFFSET = 14
ACK_STATUS_OFFSET = 16

EVENT_REPORT = 0xFB
EVENT_BUTTON = 0x01
EVENT_DPI_STAGE = 0x08
EVENT_LINK = 0x0A


class Command(enum.Enum):
    DEVICE_INFO = (0x10, 0x01)
    KEY_HEADER = (0x20, 0x01)
    KEY_PAGE = (0x20, 0x02)
    KEY_PAGES_READ = (0x20, 0x03)
    KEY_PAGE_READ = (0x20, 0x04)
    KEY_RESET = (0x20, 0x05)
    DPI_TABLE = (0x32, 0x01)
    DPI_TABLE_READ = (0x32, 0x02)
    SENSOR = (0x36, 0x01)
    SENSOR_READ = (0x36, 0x02)
    BRIGHTNESS = (0x40, 0x01)
    BRIGHTNESS_READ = (0x40, 0x02)
    LIGHTING_PRESET = (0x42, 0x02)
    LIGHTING_READ = (0x42, 0x03)
    FRAME_HEADER = (0x44, 0x03)
    FRAME_DATA = (0x44, 0x04)
    LIVE_COLOR = (0x44, 0x02)
    BATTERY_ALERT = (0x50, 0x01)
    BATTERY = (0x50, 0x02)
    CONNECTION = (0x52, 0x01)

    @property
    def report_id(self) -> int:
        return self.value[0]

    @property
    def sub(self) -> int:
        return self.value[1]

    @property
    def reply_id(self) -> int:
        return self.value[0] + 1

    def packet(self, payload: bytes = b"") -> bytes:
        return bytes([self.report_id, self.sub, *payload]).ljust(REPORT_SIZE, b"\x00")


class PollingRate(enum.IntEnum):
    HZ_125 = 125
    HZ_250 = 250
    HZ_500 = 500
    HZ_1000 = 1000
    HZ_2000 = 2000
    HZ_4000 = 4000
    HZ_8000 = 8000

    @property
    def code(self) -> int:
        return _POLLING_CODES[self]

    @classmethod
    def from_code(cls, code: int) -> "PollingRate":
        for rate, value in _POLLING_CODES.items():
            if value == code:
                return rate
        msg = f"unknown polling-rate code {code:#04x}"
        raise ValueError(msg)


_POLLING_CODES: dict[PollingRate, int] = {
    PollingRate.HZ_125: 0x40,
    PollingRate.HZ_250: 0x20,
    PollingRate.HZ_500: 0x10,
    PollingRate.HZ_1000: 0x08,
    PollingRate.HZ_2000: 0x04,
    PollingRate.HZ_4000: 0x02,
    PollingRate.HZ_8000: 0x01,
}


class LiftOff(enum.Enum):
    LOW = 0x00
    HIGH = 0x02

    @property
    def label(self) -> str:
        return "low (1 mm)" if self is LiftOff.LOW else "high (2 mm)"


class LightingMode(enum.IntEnum):
    OFF = 0
    SOLID = 1
    BREATH = 2
    WAVE = 3
    COLOR_CYCLE = 4
    CONFETTI = 5
    FRAME_LIGHT = 6
    VU_METER = 7
    MIRROR_WAVE = 8
    ALTERNATING = 9


class ChargeStatus(enum.IntEnum):
    NOT_CHARGING = 0x00
    CHARGING = 0x01
    FULLY_CHARGED = 0x02
    CHARGER_ERROR = 0x03
    UNKNOWN = 0xFF

    @classmethod
    def from_byte(cls, value: int) -> "ChargeStatus":
        try:
            return cls(value)
        except ValueError:
            return cls.UNKNOWN

    @property
    def label(self) -> str:
        return self.name.replace("_", " ").lower()


@dataclass(frozen=True)
class DpiStage:
    dpi: int
    color: Rgb


@dataclass(frozen=True)
class DpiTable:
    polling_rate: PollingRate
    active_stage: int
    stages: tuple[DpiStage, ...]

    def replace_stage(self, index: int, stage: DpiStage) -> "DpiTable":
        stages = list(self.stages)
        stages[index] = stage
        return replace(self, stages=tuple(stages))


@dataclass(frozen=True)
class SensorSettings:
    angle_snap: int
    angle_tune: int
    angle_tune_enable: int
    lift_off: LiftOff
    motion_sync: int


@dataclass(frozen=True)
class LightingEffect:
    mode: int
    duration: int

    @property
    def label(self) -> str:
        try:
            name = LightingMode(self.mode).name.replace("_", " ").title()
        except ValueError:
            name = f"unknown mode {self.mode:#04x}"
        return f"{name} (speed {self.duration})"


@dataclass(frozen=True)
class Battery:
    level: int
    charge: ChargeStatus
    temperature_c: int
    voltage_mv: int


@dataclass(frozen=True)
class DeviceInfo:
    device_id: str
    category: int
    vendor_id: int
    product_ids: tuple[int, ...]


@dataclass(frozen=True)
class LinkEvent:
    connected: bool


@dataclass(frozen=True)
class DpiStageEvent:
    stage: int
    dpi: int


@dataclass(frozen=True)
class ButtonEvent:
    button: int
    pressed: bool


@dataclass(frozen=True)
class BatteryEvent:
    battery: Battery


type Event = LinkEvent | DpiStageEvent | ButtonEvent | BatteryEvent


def dpi_to_code(dpi: int) -> int:
    return dpi // DPI_STEP - 1


def code_to_dpi(code: int) -> int:
    return (code + 1) * DPI_STEP


def validate_dpi(dpi: int) -> None:
    if not DPI_MIN <= dpi <= DPI_MAX or dpi % DPI_STEP:
        msg = f"DPI must be {DPI_MIN}-{DPI_MAX} in steps of {DPI_STEP}, got {dpi}"
        raise ValueError(msg)


def profile_query(command: Command, slot: int = LIVE_SLOT) -> bytes:
    return command.packet(bytes([slot]))


def encode_dpi_table(table: DpiTable, slot: int = LIVE_SLOT) -> bytes:
    if not 1 <= len(table.stages) <= MAX_STAGES:
        msg = f"between 1 and {MAX_STAGES} DPI stages are supported"
        raise ValueError(msg)
    if not 0 <= table.active_stage < len(table.stages):
        msg = f"active stage {table.active_stage + 1} does not exist"
        raise ValueError(msg)
    enabled_mask = (1 << len(table.stages)) - 1
    payload = bytearray(slot.to_bytes(2, "little"))
    payload += bytes([table.polling_rate.code, enabled_mask, table.active_stage])
    for stage in table.stages:
        validate_dpi(stage.dpi)
        payload += dpi_to_code(stage.dpi).to_bytes(2, "little")
        payload += stage.color.to_bytes()
    return Command.DPI_TABLE.packet(bytes(payload))


def parse_dpi_table(report: bytes) -> DpiTable:
    mask = report[3]
    raw_active = report[4]
    enabled = [index for index in range(MAX_STAGE_SLOTS) if mask >> index & 1]
    stages: list[DpiStage] = []
    for index in enabled:
        offset = 5 + index * STAGE_SIZE
        code = int.from_bytes(report[offset : offset + 2], "little")
        color = Rgb(report[offset + 2], report[offset + 3], report[offset + 4])
        stages.append(DpiStage(code_to_dpi(code), color))
    active = enabled.index(raw_active) if raw_active in enabled else 0
    return DpiTable(PollingRate.from_code(report[2]), active, tuple(stages))


def encode_sensor(settings: SensorSettings, slot: int = LIVE_SLOT) -> bytes:
    payload = slot.to_bytes(2, "little") + bytes(
        [
            settings.angle_snap,
            settings.angle_tune,
            settings.angle_tune_enable,
            settings.lift_off.value,
            settings.motion_sync,
        ]
    )
    return Command.SENSOR.packet(payload)


def parse_sensor(report: bytes) -> SensorSettings:
    return SensorSettings(
        angle_snap=report[2],
        angle_tune=report[3],
        angle_tune_enable=report[4],
        lift_off=LiftOff(report[5]),
        motion_sync=report[6],
    )


def percent_to_brightness(percent: int) -> int:
    return percent * BRIGHTNESS_RAW_MAX // BRIGHTNESS_MAX


def brightness_to_percent(raw: int) -> int:
    return round(raw * BRIGHTNESS_MAX / BRIGHTNESS_RAW_MAX)


def encode_brightness(percent: int, slot: int = LIVE_SLOT) -> bytes:
    if not 0 <= percent <= BRIGHTNESS_MAX:
        msg = f"brightness must be 0-100 %, got {percent}"
        raise ValueError(msg)
    payload = slot.to_bytes(2, "little") + bytes([percent_to_brightness(percent)])
    return Command.BRIGHTNESS.packet(payload)


def parse_brightness(report: bytes) -> int:
    return report[2]


def parse_lighting(report: bytes) -> LightingEffect:
    return LightingEffect(mode=report[2], duration=int.from_bytes(report[3:5], "little"))


def encode_key_reset(slot: int, *, reset_mcu: bool) -> bytes:
    return Command.KEY_RESET.packet(slot.to_bytes(2, "little") + bytes([int(reset_mcu)]))


def encode_key_assignments(assignments: list[Assignment], slot: int) -> list[bytes]:
    pages = [
        assignments[start : start + ENTRIES_PER_PAGE]
        for start in range(0, len(assignments), ENTRIES_PER_PAGE)
    ]
    header = slot.to_bytes(2, "little") + bytes([len(pages), BASE_LAYER, len(assignments)])
    packets = [Command.KEY_HEADER.packet(header)]
    for index, page in enumerate(pages):
        entries = b"".join(assignment.to_bytes() for assignment in page)
        packets.append(Command.KEY_PAGE.packet(bytes([index, 0]) + entries))
    return packets


def encode_key_pages_query(slot: int) -> bytes:
    return Command.KEY_PAGES_READ.packet(bytes([slot, BASE_LAYER]))


def encode_key_page_query(slot: int, page: int) -> bytes:
    return Command.KEY_PAGE_READ.packet(bytes([slot, page]))


def parse_key_page_count(report: bytes) -> int:
    return report[2]


def parse_key_page(report: bytes) -> list[Assignment]:
    assignments: list[Assignment] = []
    for index in range(ENTRIES_PER_PAGE):
        offset = KEY_PAGE_HEADER + index * ENTRY_SIZE
        entry = report[offset : offset + ENTRY_SIZE]
        if len(entry) < ENTRY_SIZE or entry[0] == 0:
            break
        assignments.append(Assignment.from_bytes(entry))
    return assignments


def encode_frame_light(colors: list[Rgb], speed: int, slot: int, leds: int = 1) -> list[bytes]:
    if not 1 <= len(colors) <= MAX_FRAMES:
        msg = f"between 1 and {MAX_FRAMES} frames are supported"
        raise ValueError(msg)
    chunks: list[bytes] = []
    for color in colors:
        frame = color.to_bytes() * leds
        chunks += [
            frame[start : start + FRAME_DATA_SIZE]
            for start in range(0, len(frame), FRAME_DATA_SIZE)
        ]
    header = bytes([len(colors)]) + len(chunks).to_bytes(2, "little") + slot.to_bytes(2, "little")
    packets = [Command.FRAME_HEADER.packet(header)]
    packets += [
        Command.FRAME_DATA.packet(index.to_bytes(2, "little") + chunk)
        for index, chunk in enumerate(chunks)
    ]
    mode = slot.to_bytes(2, "little") + bytes([LightingMode.FRAME_LIGHT])
    packets.append(Command.LIGHTING_PRESET.packet(mode + speed.to_bytes(2, "little")))
    return packets


def encode_battery_alert(threshold: int, *, save: bool) -> bytes:
    if not BATTERY_ALERT_MIN <= threshold <= BATTERY_ALERT_MAX:
        msg = (
            f"low-battery alert must be {BATTERY_ALERT_MIN}-{BATTERY_ALERT_MAX} %, got {threshold}"
        )
        raise ValueError(msg)
    return Command.BATTERY_ALERT.packet(bytes([threshold, int(save)]))


def encode_live_color(color: Rgb, leds: int = 1) -> bytes:
    return Command.LIVE_COLOR.packet(b"\x00\x00" + color.to_bytes() * leds)


def is_ack_for(report: bytes, command: Command) -> bool:
    return (
        len(report) > ACK_STATUS_OFFSET
        and report[0] == ACK_REPORT
        and report[1] == ACK_SUB
        and report[ACK_COMMAND_OFFSET] == command.report_id
        and report[ACK_COMMAND_OFFSET + 1] == command.sub
    )


def is_reply_for(report: bytes, command: Command) -> bool:
    return len(report) > 1 and report[0] == command.reply_id and report[1] == command.sub


def parse_battery(report: bytes) -> Battery:
    return Battery(
        level=report[2],
        charge=ChargeStatus.from_byte(report[3]),
        temperature_c=int.from_bytes(report[4:6], "little", signed=True),
        voltage_mv=int.from_bytes(report[6:8], "little"),
    )


def parse_connection(report: bytes) -> bool:
    return report[2] == 1


def parse_device_info(report: bytes) -> DeviceInfo:
    ids = (
        int.from_bytes(report[offset : offset + 2], "little")
        for offset in range(PRODUCT_IDS_START, PRODUCT_IDS_END, 2)
    )
    return DeviceInfo(
        device_id=report[2:14].hex(),
        category=report[CATEGORY_OFFSET],
        vendor_id=int.from_bytes(report[35:37], "little"),
        product_ids=tuple(value for value in ids if value),
    )


def _link_event(report: bytes) -> Event:
    return LinkEvent(connected=report[2] == 1)


def _dpi_stage_event(report: bytes) -> Event:
    return DpiStageEvent(stage=report[2], dpi=code_to_dpi(int.from_bytes(report[3:5], "little")))


def _button_event(report: bytes) -> Event:
    return ButtonEvent(button=report[2], pressed=report[4] == 1)


_EVENT_PARSERS: dict[int, Callable[[bytes], Event]] = {
    EVENT_LINK: _link_event,
    EVENT_DPI_STAGE: _dpi_stage_event,
    EVENT_BUTTON: _button_event,
}


def parse_event(report: bytes) -> Event | None:
    if len(report) < MIN_EVENT_LENGTH:
        return None
    if is_reply_for(report, Command.BATTERY):
        return BatteryEvent(parse_battery(report))
    if report[0] != EVENT_REPORT or report[1] not in _EVENT_PARSERS:
        return None
    return _EVENT_PARSERS[report[1]](report)
