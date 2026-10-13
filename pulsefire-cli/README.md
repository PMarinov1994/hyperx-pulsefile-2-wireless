# pulsefire

Command-line tool for the HyperX Pulsefire Haste 2 Wireless mouse (USB dongle `03f0:0f98`) on Linux.

Settings are read from the mouse itself. Every change reads the current value first, changes
only what you asked for, writes it, and reads it back to check it. The mouse has to be awake for
this: if a command says it is asleep, move the mouse and run the command again.

Changes are applied live. Add `--save` to any setting command to also store the change in the mouse's
onboard memory (the same profile NGENUITY's *Save* writes), so it survives a power cycle.
`show --saved` and `button --saved` display what is stored there.

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
| `pulsefire show [--saved]` | All settings: DPI stages, polling rate, lift-off, brightness, lighting effect, remapped buttons |
| `pulsefire dpi` | Show the DPI stages (the active one is marked with `*`) |
| `pulsefire dpi set STAGE DPI` | Set a stage's DPI (100–26000, steps of 50), e.g. `pulsefire dpi set 3 1600` |
| `pulsefire dpi color STAGE COLOUR` | Set a stage's indicator colour |
| `pulsefire dpi select STAGE` | Make a stage active |
| `pulsefire dpi add DPI [COLOUR]` | Add a stage at the end (up to 5 stages) |
| `pulsefire dpi remove STAGE` | Remove a stage |
| `pulsefire polling [RATE]` | Show or set the polling rate: 125, 250, 500 or 1000 Hz |
| `pulsefire liftoff [low\|high]` | Show or set the lift-off distance: low = 1 mm, high = 2 mm |
| `pulsefire battery-alert PERCENT` | Set the low-battery warning level, 5–25 % (NGENUITY default 10 %); write-only, the mouse can't report it |
| `pulsefire brightness [PERCENT]` | Show or set the LED brightness, 0–100 (0 = off) |
| `pulsefire button [--saved]` | List the remapped buttons |
| `pulsefire button BUTTON ACTION` | Remap a button, e.g. `pulsefire button forward volume-up`; `ACTION` `default` restores it (see `pulsefire button --help`) |
| `pulsefire lighting [--saved]` | Show the lighting effect |
| `pulsefire lighting EFFECT …` | Set the effect the mouse plays by itself: `solid`, `breathing`, `alternating`, `confetti`, `spectrum`, `wave`, `sunrise`, `rainbow` (see `pulsefire lighting EFFECT --help`); `--speed 0-100` |
| `pulsefire color COLOUR [-s SECONDS]` | Show a solid LED colour until Ctrl+C (or for SECONDS); the saved effect returns afterwards |
| `pulsefire watch` | Print wake/sleep, DPI-button and battery events as they happen |

Put `-v` / `--verbose` before any command to print every packet sent (`->`) and received (`<-`)
on stderr, e.g. `pulsefire -v show`. ACKs are annotated with the command, status and sender ID.

Every command that changes a setting accepts `--save`. Buttons: `left`, `right`, `middle`, `back`,
`forward`, `dpi`. Remapping `left` needs `--force`.

Stages are numbered from 1. `COLOUR` is a name (`red`, `green`, `blue`, `yellow`, `cyan`, `magenta`,
`orange`, `purple`, `pink`, `white`, `off`) or a hex value such as `#ff8000`.
