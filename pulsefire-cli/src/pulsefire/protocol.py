import enum
from collections.abc import Callable, Sequence
from dataclasses import dataclass

from pulsefire.colors import Rgb

REPORT_SIZE = 64
LIVE_SLOT = 0

DPI_MIN = 100
DPI_MAX = 26000
DPI_STEP = 50
MAX_STAGES = 5
BRIGHTNESS_MAX = 100
MIN_EVENT_LENGTH = 3

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
    DPI_TABLE = (0x32, 0x01)
    SENSOR = (0x36, 0x01)
    BRIGHTNESS = (0x40, 0x01)
    LIVE_COLOR = (0x44, 0x02)
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

    @property
    def code(self) -> int:
        return _POLLING_CODES[self]


_POLLING_CODES: dict[PollingRate, int] = {
    PollingRate.HZ_125: 0x40,
    PollingRate.HZ_250: 0x20,
    PollingRate.HZ_500: 0x10,
    PollingRate.HZ_1000: 0x08,
}


class LiftOff(enum.Enum):
    LOW = 0x00
    HIGH = 0x02

    @property
    def label(self) -> str:
        return "low (1 mm)" if self is LiftOff.LOW else "high (2 mm)"


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
class Battery:
    level: int
    charge: ChargeStatus
    temperature_c: int
    voltage_mv: int


@dataclass(frozen=True)
class DeviceInfo:
    device_id: str
    vendor_id: int
    product_id: int


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


def encode_dpi_table(
    stages: Sequence[DpiStage],
    active_stage: int,
    polling_rate: PollingRate,
    slot: int = LIVE_SLOT,
) -> bytes:
    if not 1 <= len(stages) <= MAX_STAGES:
        msg = f"between 1 and {MAX_STAGES} DPI stages are supported"
        raise ValueError(msg)
    if not 0 <= active_stage < len(stages):
        msg = f"active stage {active_stage + 1} does not exist"
        raise ValueError(msg)
    enabled_mask = (1 << len(stages)) - 1
    payload = bytearray(slot.to_bytes(2, "little"))
    payload += bytes([polling_rate.code, enabled_mask, active_stage])
    for stage in stages:
        validate_dpi(stage.dpi)
        payload += dpi_to_code(stage.dpi).to_bytes(2, "little")
        payload += stage.color.to_bytes()
    return Command.DPI_TABLE.packet(bytes(payload))


def encode_sensor(lift_off: LiftOff, slot: int = LIVE_SLOT) -> bytes:
    payload = slot.to_bytes(2, "little") + bytes([0x00, 0x00, 0x00, lift_off.value, 0x00])
    return Command.SENSOR.packet(payload)


def percent_to_brightness(percent: int) -> int:
    return percent * 0xFF // BRIGHTNESS_MAX


def encode_brightness(percent: int, slot: int = LIVE_SLOT) -> bytes:
    if not 0 <= percent <= BRIGHTNESS_MAX:
        msg = f"brightness must be 0-100 %, got {percent}"
        raise ValueError(msg)
    payload = slot.to_bytes(2, "little") + bytes([percent_to_brightness(percent)])
    return Command.BRIGHTNESS.packet(payload)


def encode_live_color(color: Rgb) -> bytes:
    return Command.LIVE_COLOR.packet(b"\x00\x00" + color.to_bytes())


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
    return DeviceInfo(
        device_id=report[2:14].hex(),
        vendor_id=int.from_bytes(report[35:37], "little"),
        product_id=int.from_bytes(report[45:47], "little"),
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
