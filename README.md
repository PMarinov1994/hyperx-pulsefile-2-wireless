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
4. **Decompiled the light engine** (`hxn-srv-light-engine.exe`) to reproduce NGENUITY's lighting effects.
5. **Verified the commands from Linux**: battery and charging status, connection status, live LED
   colour, brightness, DPI, polling rate, lift-off, button remapping, lighting effects and saving.

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

Compared with what NGENUITY offers for this mouse. Every item marked done has been tested on the
real mouse from Linux with `pulsefire`.

### Done

- **Status:** battery level, charging state, voltage, temperature; connection / sleep state.
- **DPI:** up to 5 stages with DPI and indicator colour, active stage.
- **Sensor:** polling rate (125/250/500/1000 Hz); lift-off distance (1 mm / 2 mm).
- **Lighting:**
  - every software effect NGENUITY offers for this mouse: Solid, Breathing, Alternating,
    Confetti, Spectrum Wave, Wave and Sunrise, rendered with the formulas from NGENUITY's light
    engine;
  - an exact restore of NGENUITY's stored colour cycle;
  - brightness 0–100 %;
  - a temporary live colour.
- **Buttons:** remapping (the "Keys & Buttons" action type) to mouse buttons, keyboard keys, media
  keys and DPI / special functions.
- **Low-battery alert** level, 5–25 %. Write-only: the mouse does not report it.
- **Reading the current settings back** from the mouse, both live and stored.
- **Saving to onboard memory** (`--save`), confirmed to survive a power cycle.
- **Events:** DPI-button presses, wake/sleep, battery reports (`pulsefire watch`).
- **Debugging:** `pulsefire -v …` prints every packet sent and received.

### Missing

| Feature (NGENUITY) | State | What is needed |
|---|---|---|
| **Macros** (button action type "Macro") | Commands identified (`22 01`–`22 07`), data format not decoded | A USB capture of NGENUITY assigning a short macro to a button and saving |
| **Text** (button types a text string) | Probably stored as a macro | Same capture as macros |
| **Game Mode** (button action type) | Not investigated | A capture of NGENUITY assigning it |
| **Launcher** (button starts a program) | Handled by NGENUITY on the PC, not by the mouse | A background service on Linux; not planned |
| **Firmware version** in the device panel | Device ID shown; firmware version field in the device-info reply not located | A capture of NGENUITY's device panel |
| **Firmware update** | Report IDs `F0`/`FA`/`FC` exist but are not decoded | Not planned: risk of bricking the mouse; use NGENUITY on Windows |
| **Factory reset** | Decoded (`12 01`) | Deliberately not exposed; could be added behind a confirmation prompt |

See the open items in [PROTOCOL.md](PROTOCOL.md).
