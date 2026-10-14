# Pulsefire Haste 3 Wireless

| | |
|---|---|
| USB | product ID not known yet (please report it, see the README) |
| Protocol | [universal](../protocol/universal.md) (assumed: same NGENUITY configuration interfaces as the Haste 2 Wireless) |
| ngenuity-linux status | **untested**, built from NGENUITY's decompiled configuration |
| ngenuity name | `pulsefire-haste-3-wireless` (select it with `ngenuity -d pulsefire-haste-3-wireless …` until the product ID is known) |

## Capabilities (from NGENUITY's configuration)

- DPI 50–42000 in steps of 50, up to 5 stages
- polling rate 125 / 250 / 500 / 1000 / 2000 / 4000 / 8000 Hz; lift-off 1 mm / 2 mm
- buttons: left, right, middle, back, forward, dpi
- no RGB lighting

## Supported commands

| Command | Use | Status |
|---|---|---|
| `10 01` → `11 01` | device information | untested |
| `52 01` → `53 01` | connected / asleep (wireless models) | untested |
| `50 02` → `51 02` | battery (wireless models) | untested |
| `32 01` / `32 02` | DPI table and polling rate | untested |
| `36 01` / `36 02` | lift-off | untested |
| `20 01`–`20 05` | button remapping | untested |

To test this model, follow "Testing untested hardware" in the [README](../../README.md).
