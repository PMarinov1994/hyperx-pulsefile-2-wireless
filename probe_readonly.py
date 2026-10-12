#!/usr/bin/env python3
"""Read-only probe for the HyperX "universal" HID protocol (Pulsefire Haste 2 Wireless dongle 03f0:0f98).

Sends ONLY query commands (no settings writes, no factory reset) on the vendor interface
(usage page 0xFF00, interface 2) and hex-dumps every input report that comes back.

Usage:  sudo python3 probe_readonly.py [/dev/hidrawN]
If no path is given, the hidraw node of 03f0:0f98 with usage page 0xFF00 is auto-detected.
"""
import glob
import os
import select
import sys
import time

VID, PID = 0x03F0, 0x0F98

# (label, cmd/report-id, sub, payload bytes) -- query commands only, see PROTOCOL.md
QUERIES = [
    ("DeviceInformation",          0x10, 0x01, b""),
    ("DeviceSerialNumber",         0x10, 0x02, b""),
    ("CurrentProfileInformation",  0x14, 0x02, b""),
    ("DPISettingsInformation p0",  0x20, 0x03, b"\x00\x00"),
    ("BatteryInformation",         0x50, 0x03, b""),
    ("RFConnectionStatus",         0x52, 0x01, b""),
]
# Target addressing: NGENUITY may OR a 2-bit target into the top bits of byte 1.
TARGETS = [0, 1]


def find_hidraw():
    for dev in sorted(glob.glob("/sys/bus/hid/devices/*")):
        name = os.path.basename(dev)
        if f"{VID:04X}:{PID:04X}" not in name:
            continue
        desc = open(os.path.join(dev, "report_descriptor"), "rb").read()
        if desc[:3] == b"\x06\x00\xff":
            nodes = os.listdir(os.path.join(dev, "hidraw"))
            if nodes:
                return "/dev/" + nodes[0]
    return None


def drain(fd, timeout=0.3):
    out = []
    end = time.monotonic() + timeout
    while True:
        left = end - time.monotonic()
        if left <= 0:
            break
        r, _, _ = select.select([fd], [], [], left)
        if not r:
            break
        out.append(os.read(fd, 64))
    return out


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else find_hidraw()
    if not path:
        sys.exit("vendor hidraw node for 03f0:0f98 not found")
    print(f"using {path}")
    fd = os.open(path, os.O_RDWR)
    try:
        stale = drain(fd, 0.2)
        if stale:
            print(f"(discarded {len(stale)} unsolicited reports)")
        for target in TARGETS:
            print(f"\n===== target bits = {target} =====")
            for label, cmd, sub, payload in QUERIES:
                pkt = bytes([cmd, (target << 6) | (sub & 0x3F)]) + payload
                pkt = pkt.ljust(64, b"\x00")
                os.write(fd, pkt)
                replies = drain(fd, 0.4)
                print(f"--> {label:28s} {pkt[:8].hex(' ')} ...")
                if not replies:
                    print("    <no reply>")
                for rep in replies:
                    print(f"<-- [{len(rep):2d}] {rep.hex(' ')}")
                time.sleep(0.02)
    finally:
        os.close(fd)


if __name__ == "__main__":
    main()
