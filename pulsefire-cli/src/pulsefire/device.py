import os
import select
import time
from collections.abc import Iterator
from pathlib import Path
from types import TracebackType
from typing import Self

from pulsefire.protocol import (
    ACK_STATUS_OFFSET,
    REPORT_SIZE,
    Battery,
    Command,
    DeviceInfo,
    is_ack_for,
    is_reply_for,
    parse_battery,
    parse_connection,
    parse_device_info,
)

VENDOR_ID = 0x03F0
PRODUCT_ID = 0x0F98
VENDOR_USAGE_PAGE = b"\x06\x00\xff"
HID_DEVICES = Path("/sys/bus/hid/devices")
MIN_SEND_INTERVAL = 0.010
DEFAULT_TIMEOUT = 0.5
FLUSH_SECONDS = 0.05


class DeviceError(Exception):
    pass


class DeviceNotFoundError(DeviceError):
    pass


class NoReplyError(DeviceError):
    pass


def find_hidraw() -> Path:
    marker = f"{VENDOR_ID:04X}:{PRODUCT_ID:04X}"
    for device in sorted(HID_DEVICES.glob(f"*{marker}*")):
        descriptor = (device / "report_descriptor").read_bytes()
        if not descriptor.startswith(VENDOR_USAGE_PAGE):
            continue
        nodes = sorted((device / "hidraw").iterdir())
        if nodes:
            return Path("/dev") / nodes[0].name
    msg = "HyperX Pulsefire Haste 2 Wireless dongle (03f0:0f98) not found"
    raise DeviceNotFoundError(msg)


class Dongle:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._fd: int | None = None
        self._last_send = 0.0

    @classmethod
    def open(cls, path: Path | None = None) -> Self:
        dongle = cls(path or find_hidraw())
        dongle.connect()
        return dongle

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
            msg = "dongle is not open"
            raise DeviceError(msg)
        return self._fd

    def send(self, packet: bytes) -> None:
        wait = self._last_send + MIN_SEND_INTERVAL - time.monotonic()
        if wait > 0:
            time.sleep(wait)
        os.write(self.fd, packet)
        self._last_send = time.monotonic()

    def read(self, timeout: float) -> bytes | None:
        ready, _, _ = select.select([self.fd], [], [], max(timeout, 0.0))
        if not ready:
            return None
        return os.read(self.fd, REPORT_SIZE)

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

    def execute(self, command: Command, packet: bytes, timeout: float = DEFAULT_TIMEOUT) -> None:
        self.send(packet)
        for report in self.reports(timeout):
            if is_ack_for(report, command):
                if report[ACK_STATUS_OFFSET] != 0:
                    msg = (
                        f"dongle rejected {command.name} (status {report[ACK_STATUS_OFFSET]:#04x})"
                    )
                    raise DeviceError(msg)
                return
        msg = f"no acknowledgement for {command.name}"
        raise NoReplyError(msg)

    def query(self, command: Command, timeout: float = DEFAULT_TIMEOUT) -> bytes:
        self.send(command.packet())
        for report in self.reports(timeout):
            if is_reply_for(report, command):
                return report
        msg = f"no reply to {command.name}"
        raise NoReplyError(msg)

    def is_mouse_connected(self) -> bool:
        return parse_connection(self.query(Command.CONNECTION))

    def battery(self) -> Battery:
        return parse_battery(self.query(Command.BATTERY))

    def device_info(self) -> DeviceInfo:
        return parse_device_info(self.query(Command.DEVICE_INFO))
