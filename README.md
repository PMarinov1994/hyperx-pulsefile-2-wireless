# HyperX Pulsefire Haste 2 Wireless on Linux

HyperX only provides its configuration software, NGENUITY, for Windows. This project
reverse-engineers the USB HID protocol NGENUITY uses to talk to the **Pulsefire Haste 2 Wireless**
through its 2.4 GHz dongle (`03f0:0f98`), so that the mouse can be configured from Linux.

The protocol is documented in **[PROTOCOL.md](PROTOCOL.md)**.

## How it was done

1. **Extracted NGENUITY** from the installer and decompiled it:
   - the .NET UI with ILSpy;
   - the Rust service that talks to the device (`hxn-srv-communication-hub.exe`) with Ghidra.
2. **Probed the dongle from Linux** with read-only queries (`probe_readonly.py`) to learn the
   report format, the ACK packets, and which replies come from the dongle and which from the mouse.
3. **Captured USB traffic** with `usbmon` while NGENUITY ran in a VirtualBox VM. Each capture
   changes one setting (DPI, polling rate, lift-off, brightness, and so on), which made it possible
   to decode each command (`captures/`).
4. **Verified the commands from Linux**: battery and charging status, connection status, live LED
   colour, brightness and DPI.

## Contents

| Path | What it is |
|---|---|
| [PROTOCOL.md](PROTOCOL.md) | The protocol specification: transport, commands, payloads, events |
| [pulsefire-cli/](pulsefire-cli/) | `pulsefire`, a Python CLI tool that configures the mouse using the protocol |
| `probe_readonly.py` | The read-only probe script used for the first tests |
| `70-hyperx-pulsefire-haste2.rules` | udev rule that gives the logged-in user access to the dongle |
| `50-usbmon-wireshark.rules` | udev rule that lets the `wireshark` group capture USB traffic |
| `captures/` | USB captures of NGENUITY (`ngenuityN.pcapng`) |
| `extracted/`, `decompiled/`, `ghidra_targets/`, `hyperx.*` | Extracted NGENUITY files, decompiled sources and the Ghidra project |

## Status

Working from Linux:
- reading battery level, charging state and connection status;
- setting the DPI stages, polling rate, lift-off distance and LED brightness;
- setting a live LED colour;
- printing DPI-button and wake/sleep events.

Not yet decoded:
- button remapping and macros;
- the stored lighting effect;
- the commands NGENUITY uses to save a profile to the mouse's onboard memory.

See the open items in [PROTOCOL.md](PROTOCOL.md).
