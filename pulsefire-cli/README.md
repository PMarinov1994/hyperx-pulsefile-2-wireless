# pulsefire

Command-line tool for the HyperX Pulsefire Haste 2 Wireless mouse (USB dongle `03f0:0f98`) on Linux.

Changes are applied live to the mouse. They are not written to the profile that NGENUITY saves on the mouse.
The mouse cannot report its current settings, so pulsefire remembers the last values it sent
(in `~/.config/pulsefire/settings.json`) and builds every change on top of them.

## Setup

Your user needs access to the dongle's vendor interface. Install the udev rule from the parent folder:

```
sudo cp ../70-hyperx-pulsefire-haste2.rules /etc/udev/rules.d/
sudo udevadm control --reload && sudo udevadm trigger
```

Then, inside this folder:

```
uv sync
uv run pulsefire --help
```

## Commands

| Command | What it does |
|---|---|
| `pulsefire status` | Connection state and battery level, charging state, voltage, temperature |
| `pulsefire show` | All settings pulsefire last sent |
| `pulsefire apply` | Send all remembered settings again |
| `pulsefire dpi` | Show the DPI stages (the active one is marked with `*`) |
| `pulsefire dpi set STAGE DPI` | Set a stage's DPI (100–26000, steps of 50), e.g. `pulsefire dpi set 3 1600` |
| `pulsefire dpi color STAGE COLOUR` | Set a stage's indicator colour |
| `pulsefire dpi select STAGE` | Make a stage active |
| `pulsefire dpi add DPI [COLOUR]` | Add a stage at the end (up to 5 stages) |
| `pulsefire dpi remove STAGE` | Remove a stage |
| `pulsefire polling [RATE]` | Show or set the polling rate: 125, 250, 500 or 1000 Hz |
| `pulsefire liftoff [low\|high]` | Show or set the lift-off distance: low = 1 mm, high = 2 mm |
| `pulsefire brightness [PERCENT]` | Show or set the LED brightness, 0–100 (0 = off) |
| `pulsefire color COLOUR [-s SECONDS]` | Show a solid LED colour until Ctrl+C (or for SECONDS); the saved effect returns afterwards |
| `pulsefire watch` | Print wake/sleep, DPI-button and battery events; keeps the remembered active stage in sync |

Stages are numbered from 1. `COLOUR` is a name (`red`, `green`, `blue`, `yellow`, `cyan`, `magenta`,
`orange`, `purple`, `pink`, `white`, `off`) or a hex value such as `#ff8000`.

If the mouse is asleep, pulsefire warns you, and the change is applied when the mouse wakes up.
