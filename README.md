# ngenuity-linux-cli

HyperX only provides its configuration software, NGENUITY, for Windows. This project
reverse-engineers how NGENUITY talks to HyperX devices and provides `ngenuity`, a command-line tool
that configures them from Linux.

The first device, the **Pulsefire Haste 2 Wireless**, is fully supported and tested. The other
mice NGENUITY supports share its protocol and are implemented from NGENUITY's decompiled code,
but are **untested**: if you own one, see [Testing untested hardware](#testing-untested-hardware).

- Protocols: [docs/protocol](https://github.com/PMarinov1994/ngenuity-linux-cli/blob/master/docs/protocol/README.md), with the full
  [universal protocol](https://github.com/PMarinov1994/ngenuity-linux-cli/blob/master/docs/protocol/universal.md) specification
- Devices: [docs/devices](https://github.com/PMarinov1994/ngenuity-linux-cli/blob/master/docs/devices/README.md), with one page per device listing its
  capabilities and commands

## Installation

You need [uv](https://docs.astral.sh/uv/) and Python 3.12 or newer.

```
uv sync
uv run ngenuity --help
```

Your user needs access to the device's vendor HID interface. For the Pulsefire Haste 2 Wireless,
install the udev rule from this folder:

```
sudo cp 70-hyperx-pulsefire-haste2.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

For another device, copy the rule and change `ID_USB_MODEL_ID` to its USB product ID (shown by
`lsusb`, e.g. `03f0:0f98`) and `ID_USB_INTERFACE_NUM` to its vendor interface. Until then you can
run `ngenuity` with `sudo`.

## Usage

`ngenuity` detects the connected HyperX device. If several are connected it asks which one to
use; `-d NAME` selects one up front (`ngenuity devices --all` lists the names), `-d /dev/hidrawN`
selects an interface, and `-d NAME` also forces a model when detection does not recognise the device.

Settings are read from the device, so a wireless device has to be awake: if a command says it is
asleep, move it and run the command again. Every change reads the current value first, changes only
what you asked for, writes it, and reads it back to check it.

Changes are applied live. Add `--save` to any command that changes a setting to also store the
change in the device's onboard memory (the profile NGENUITY's *Save* writes), so it survives a power
cycle. `show --saved`, `button --saved` and `lighting --saved` display what is stored there.

| Command | What it does |
|---|---|
| `ngenuity devices [--all]` | List the connected devices, or every model ngenuity knows |
| `ngenuity status` | Device, connection state and battery level, charging state, voltage, temperature |
| `ngenuity show [--saved]` | All settings: DPI stages, polling rate, lift-off, brightness, lighting effect, remapped buttons |
| `ngenuity dpi` | Show the DPI stages (the active one is marked with `*`) |
| `ngenuity dpi set STAGE DPI` | Set a stage's DPI, e.g. `ngenuity dpi set 3 1600` (range depends on the model) |
| `ngenuity dpi color STAGE COLOUR` | Set a stage's indicator colour |
| `ngenuity dpi select STAGE` | Make a stage active |
| `ngenuity dpi add DPI [COLOUR]` | Add a stage at the end (up to 5 stages) |
| `ngenuity dpi remove STAGE` | Remove a stage |
| `ngenuity polling [RATE]` | Show or set the polling rate: 125 up to 8000 Hz, depending on the model |
| `ngenuity liftoff [low\|high]` | Show or set the lift-off distance: low = 1 mm, high = 2 mm |
| `ngenuity battery-alert PERCENT` | Set the low-battery warning level, 5–25 % (NGENUITY default 10 %); write-only |
| `ngenuity brightness [PERCENT]` | Show or set the LED brightness, 0–100 (0 = off) |
| `ngenuity button [--saved]` | List the remapped buttons |
| `ngenuity button BUTTON ACTION` | Remap a button, e.g. `ngenuity button forward volume-up`; `ACTION` `default` restores it (see `ngenuity button --help`) |
| `ngenuity lighting [--saved]` | Show the lighting effect |
| `ngenuity lighting EFFECT …` | Set the effect the device plays by itself: `solid`, `breathing`, `alternating`, `confetti`, `spectrum`, `wave`, `sunrise`, `rainbow` (see `ngenuity lighting EFFECT --help`); `--speed 0-100` |
| `ngenuity color COLOUR [-s SECONDS]` | Show a solid LED colour until Ctrl+C (or for SECONDS); the saved effect returns afterwards |
| `ngenuity watch` | Print wake/sleep, DPI-button and battery events as they happen |

Put `-v` / `--verbose` before any command to print every packet sent (`->`) and received (`<-`)
on stderr, e.g. `ngenuity -v show`. ACKs are annotated with the command, status and sender ID.

Buttons: `left`, `right`, `middle`, `back`, `forward`, `dpi` (depending on the model). Remapping
`left` needs `--force`. Stages are numbered from 1. `COLOUR` is a name (`red`, `green`, `blue`,
`yellow`, `cyan`, `magenta`, `orange`, `purple`, `pink`, `white`, `off`) or a hex value such as
`#ff8000`.

## Status

### Done

Tested on the Pulsefire Haste 2 Wireless; the other mice are implemented but untested
([device list](https://github.com/PMarinov1994/ngenuity-linux-cli/blob/master/docs/devices/README.md)).

- **Status:** battery level, charging state, voltage, temperature; connection / sleep state.
- **DPI:** up to 5 stages with DPI and indicator colour, active stage.
- **Sensor:** polling rate; lift-off distance (1 mm / 2 mm).
- **Lighting:**
  - every software effect NGENUITY offers: Solid, Breathing, Alternating, Confetti, Spectrum Wave,
    Wave and Sunrise, rendered with the formulas from NGENUITY's light engine;
  - an exact restore of NGENUITY's stored colour cycle;
  - brightness 0–100 %;
  - a temporary live colour.
- **Buttons:** remapping (the "Keys & Buttons" action type) to mouse buttons, keyboard keys, media
  keys and DPI / special functions.
- **Low-battery alert** level, 5–25 %. Write-only: the device does not report it.
- **Reading the current settings back**, both live and stored.
- **Saving to onboard memory** (`--save`), confirmed to survive a power cycle.
- **Events:** DPI-button presses, wake/sleep, battery reports (`ngenuity watch`).
- **Devices:** automatic detection through the device-information reply, a selection prompt for
  several devices, manual selection with `-d`.
- **Debugging:** `ngenuity -v …` prints every packet sent and received.

### Missing

| Feature | State | What is needed |
|---|---|---|
| **Other mice** (Haste 2, 2 S, 2 Pro, 3, 3 Pro, 3 Wireless, Saga, Saga Pro) | Implemented from NGENUITY's configurations, untested; USB product IDs unknown | An owner running the tests below |
| **Macros** (button action type "Macro") | Commands identified (`22 01`–`22 07`), data format not decoded | A USB capture of NGENUITY assigning a short macro to a button and saving |
| **Text** (button types a text string) | Probably stored as a macro | Same capture as macros |
| **Game Mode** (button action type) | Not investigated | A capture of NGENUITY assigning it |
| **Launcher** (button starts a program) | Handled by NGENUITY on the PC, not by the device | A background service on Linux; not planned |
| **Firmware version** in the device panel | Device ID shown; firmware version field in the device-info reply not located | A capture of NGENUITY's device panel |
| **Keyboards, Clutch Talon** | Detected; commands for per-key lighting, layers, SOCD and calibration not implemented | Implementation from the [protocol](https://github.com/PMarinov1994/ngenuity-linux-cli/blob/master/docs/protocol/universal.md), plus testing |
| **Headsets, microphones, Clutch Tachi** | Use other protocols ([list](https://github.com/PMarinov1994/ngenuity-linux-cli/blob/master/docs/protocol/README.md)) | Reverse engineering of those protocols |
| **Firmware update** | Report IDs `F0`/`FA`/`FC` exist but are not decoded | Not planned: risk of bricking the device; use NGENUITY on Windows |
| **Factory reset** | Decoded (`12 01`) | Deliberately not exposed; could be added behind a confirmation prompt |

## Testing untested hardware

The untested mice are built from NGENUITY's decompiled configuration and the protocol confirmed
on the Haste 2 Wireless. Testing them on real hardware is the only way to confirm them. The steps
go from completely safe to changes that are easy to undo; nothing is written to the onboard
memory unless you add `--save`.

1. **Identify the device (read-only).** Run `ngenuity -v devices` and note the line for your
   device and its USB ID. If it says "HyperX mouse (unknown model)", the product ID is not in the
   model list yet: select your model by hand with `-d` in the following steps, e.g.
   `ngenuity -d pulsefire-saga-pro …`.
2. **Read everything (read-only).** Run `ngenuity -v status` and `ngenuity -v show`. Check that
   the battery, DPI stages, polling rate, lift-off, brightness and lighting match what NGENUITY
   or the device shows.
3. **Change one live setting and undo it.** Each of these is applied live and read back
   automatically, and a warning is printed if the device reports something different:
   - `ngenuity dpi set 1 800`, then set it back to the old value;
   - `ngenuity polling 500`, then back;
   - `ngenuity liftoff high`, then back;
   - `ngenuity brightness 20`, then back;
   - `ngenuity color red -s 5` (the LED should be red for 5 seconds);
   - `ngenuity lighting solid purple`, then `ngenuity lighting rainbow`;
   - `ngenuity button back forward`, test it in a browser, then `ngenuity button back default`.
4. **Test saving** (optional): repeat one change with `--save`, switch the device off and on, check
   it kept the change, then restore it with `--save`.
5. **Report the results** in an issue: the device name, the output of `ngenuity -v devices`, and
   for each step whether it worked. Include the `-v` packet output of any step that failed or
   printed a warning.

If a command misbehaves, unplug the device (or switch it off) to return to the onboard profile,
which is only changed by `--save`. NGENUITY on Windows can also restore everything.

To capture what NGENUITY itself sends (needed for macros and for new devices), run NGENUITY in a
Windows VM with the device passed through, and record the USB traffic on the Linux host with
`usbmon` and `dumpcap`; the udev rule `50-usbmon-wireshark.rules` lets the `wireshark` group do this
without root. Change one setting at a time and note the time of each change.

## Releasing

Releases are published to [PyPI](https://pypi.org/project/ngenuity-linux-cli/) by the GitHub workflow
`.github/workflows/release.yml`, using PyPI's trusted publishing (no API token is stored anywhere).

1. Set the new version in `pyproject.toml` (e.g. `uv version 0.2.0`) and commit it.
2. Tag the commit with the same version and push the tag:
   ```
   git tag v0.2.0
   git push origin v0.2.0
   ```
3. The workflow checks that the tag matches the version, runs ruff and mypy, builds the package and
   publishes it. If a reviewer is required for the `pypi` environment, approve the run in the
   repository's *Actions* tab.

## How it was done

1. **Extracted NGENUITY** from the installer and decompiled it:
   - the .NET UI with ILSpy;
   - the Rust service that talks to the devices (`hxn-srv-communication-hub.exe`) and the light
     engine (`hxn-srv-light-engine.exe`) with Ghidra.
2. **Probed the dongle from Linux** with read-only queries (`probe_readonly.py`) to learn the
   report format, the ACK packets, and which replies come from the dongle and which from the mouse.
3. **Captured USB traffic** with `usbmon` while NGENUITY ran in a VirtualBox VM, one setting per
   capture (`captures/`), and decoded each command.
4. **Extracted the complete command map** from the hub's lookup tables, and the lighting effects'
   formulas from the light engine.
5. **Verified every command from Linux** on the Pulsefire Haste 2 Wireless.

## Repository layout

| Path | What it is |
|---|---|
| `src/ngenuity_linux_cli/` | The `ngenuity` command-line tool |
| [docs/protocol/](https://github.com/PMarinov1994/ngenuity-linux-cli/blob/master/docs/protocol/README.md) | Protocol specifications |
| [docs/devices/](https://github.com/PMarinov1994/ngenuity-linux-cli/blob/master/docs/devices/README.md) | Supported devices, one page per device |
| `probe_readonly.py` | The read-only probe script used for the first tests |
| `70-hyperx-pulsefire-haste2.rules` | udev rule that gives the logged-in user access to the Haste 2 Wireless dongle |
| `50-usbmon-wireshark.rules` | udev rule that lets the `wireshark` group capture USB traffic |
| `captures/` | USB captures of NGENUITY, filtered to the device: `<device>_<number>_<what it records>.pcapng` |
| `extracted/`, `decompiled/`, `ghidra_targets/`, `hyperx.*` | Extracted NGENUITY files, decompiled sources and the Ghidra project (not in version control) |
