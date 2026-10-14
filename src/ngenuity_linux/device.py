import os
import select
import time
from collections.abc import Callable, Iterator
from pathlib import Path
from types import TracebackType
from typing import Self

from ngenuity_linux.buttons import Assignment
from ngenuity_linux.colors import Rgb
from ngenuity_linux.protocol import (
    ACK_STATUS_OFFSET,
    LIVE_SLOT,
    REPORT_SIZE,
    Battery,
    Command,
    DeviceInfo,
    DpiTable,
    LightingEffect,
    SensorSettings,
    encode_battery_alert,
    encode_brightness,
    encode_dpi_table,
    encode_frame_light,
    encode_key_assignments,
    encode_key_page_query,
    encode_key_pages_query,
    encode_key_reset,
    encode_sensor,
    is_ack_for,
    is_reply_for,
    parse_battery,
    parse_brightness,
    parse_connection,
    parse_device_info,
    parse_dpi_table,
    parse_key_page,
    parse_key_page_count,
    parse_lighting,
    parse_sensor,
    profile_query,
)

MIN_SEND_INTERVAL = 0.010
DEFAULT_TIMEOUT = 0.5
FLUSH_SECONDS = 0.05


class DeviceError(Exception):
    pass


class NoReplyError(DeviceError):
    pass


type Tracer = Callable[[str, bytes], None]


class UniversalDevice:
    def __init__(self, path: Path, trace: Tracer | None = None) -> None:
        self.path = path
        self.trace = trace
        self._fd: int | None = None
        self._last_send = 0.0

    @classmethod
    def open(cls, path: Path, trace: Tracer | None = None) -> Self:
        device = cls(path, trace)
        device.connect()
        return device

    def connect(self) -> None:
        try:
            self._fd = os.open(self.path, os.O_RDWR)
        except PermissionError as error:
            msg = f"no permission to open {self.path}, check the udev rule"
            raise DeviceError(msg) from error
        self.flush()

    def close(self) -> None:
        if self._fd is not None:
            os.close(self._fd)
            self._fd = None

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        self.close()

    @property
    def fd(self) -> int:
        if self._fd is None:
            msg = "device is not open"
            raise DeviceError(msg)
        return self._fd

    def send(self, packet: bytes) -> None:
        wait = self._last_send + MIN_SEND_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        os.write(self.fd, packet)
        self._last_send = time.monotonic()
        if self.trace is not None:
            self.trace("send", packet)

    def read(self, timeout: float) -> bytes | None:
        ready, _, _ = select.select([self.fd], [], [], max(timeout, 0.0))
        if not ready:
            return None
        report = os.read(self.fd, REPORT_SIZE)
        if self.trace is not None:
            self.trace("recv", report)
        return report

    def reports(self, timeout: float) -> Iterator[bytes]:
        deadline = time.monotonic() + timeout
        while (left := deadline - time.monotonic()) > 0:
            report = self.read(left)
            if report is None:
                return
            yield report

    def drain(self, seconds: float) -> None:
        for _ in self.reports(seconds):
            pass

    def flush(self) -> None:
        self.drain(FLUSH_SECONDS)

    def execute(
        self,
        command: Command,
        packet: bytes,
        timeout: float = DEFAULT_TIMEOUT,
        *,
        await_reply: bool = False,
    ) -> None:
        self.send(packet)
        acknowledged = False
        for report in self.reports(timeout):
            if is_ack_for(report, command):
                if report[ACK_STATUS_OFFSET] != 0:
                    msg = (
                        f"device rejected {command.name} (status {report[ACK_STATUS_OFFSET]:#04x})"
                    )
                    raise DeviceError(msg)
                acknowledged = True
            elif await_reply and is_reply_for(report, command):
                return
            if acknowledged and not await_reply:
                return
        what = "reply from the mouse" if acknowledged else "acknowledgement"
        msg = f"no {what} for {command.name}"
        raise NoReplyError(msg)

    def query(
        self,
        command: Command,
        packet: bytes | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> bytes:
        self.send(packet or command.packet())
        for report in self.reports(timeout):
            if is_reply_for(report, command):
                return report
        msg = f"no reply to {command.name}"
        raise NoReplyError(msg)

    def is_awake(self) -> bool:
        try:
            return parse_connection(self.query(Command.CONNECTION))
        except NoReplyError:
            return True

    def battery(self) -> Battery:
        return parse_battery(self.query(Command.BATTERY))

    def device_info(self) -> DeviceInfo:
        return parse_device_info(self.query(Command.DEVICE_INFO))

    def dpi_table(self, slot: int = LIVE_SLOT) -> DpiTable:
        command = Command.DPI_TABLE_READ
        return parse_dpi_table(self.query(command, profile_query(command, slot)))

    def sensor(self, slot: int = LIVE_SLOT) -> SensorSettings:
        command = Command.SENSOR_READ
        return parse_sensor(self.query(command, profile_query(command, slot)))

    def brightness(self, slot: int = LIVE_SLOT) -> int:
        command = Command.BRIGHTNESS_READ
        return parse_brightness(self.query(command, profile_query(command, slot)))

    def lighting(self, slot: int = LIVE_SLOT) -> LightingEffect:
        command = Command.LIGHTING_READ
        return parse_lighting(self.query(command, profile_query(command, slot)))

    def key_assignments(self, slot: int = LIVE_SLOT) -> list[Assignment]:
        pages = parse_key_page_count(
            self.query(Command.KEY_PAGES_READ, encode_key_pages_query(slot))
        )
        assignments: list[Assignment] = []
        for page in range(pages):
            report = self.query(Command.KEY_PAGE_READ, encode_key_page_query(slot, page))
            assignments += parse_key_page(report)
        return assignments

    def set_dpi_table(self, table: DpiTable, slot: int = LIVE_SLOT) -> None:
        self.execute(Command.DPI_TABLE, encode_dpi_table(table, slot))

    def set_sensor(self, settings: SensorSettings, slot: int = LIVE_SLOT) -> None:
        self.execute(Command.SENSOR, encode_sensor(settings, slot))

    def set_brightness(self, percent: int, slot: int = LIVE_SLOT) -> None:
        self.execute(Command.BRIGHTNESS, encode_brightness(percent, slot))

    def set_battery_alert(self, threshold: int, *, save: bool) -> None:
        self.execute(Command.BATTERY_ALERT, encode_battery_alert(threshold, save=save))

    def set_frame_light(
        self, colors: list[Rgb], speed: int, slot: int = LIVE_SLOT, leds: int = 1
    ) -> None:
        header, *data, mode = encode_frame_light(colors, speed, slot, leds)
        self.execute(Command.FRAME_HEADER, header)
        for packet in data:
            self.execute(Command.FRAME_DATA, packet, await_reply=True)
        self.execute(Command.LIGHTING_PRESET, mode, await_reply=True)

    def set_key_assignments(self, assignments: list[Assignment], slot: int = LIVE_SLOT) -> None:
        self.execute(Command.KEY_RESET, encode_key_reset(slot, reset_mcu=slot != LIVE_SLOT))
        if not assignments:
            return
        header, *pages = encode_key_assignments(assignments, slot)
        self.execute(Command.KEY_HEADER, header)
        for page in pages:
            self.execute(Command.KEY_PAGE, page, await_reply=True)
