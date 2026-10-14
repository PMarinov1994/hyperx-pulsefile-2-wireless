# Devices

The devices NGENUITY 3.1.0 has a configuration for, the protocol each one uses, and its state in
ngenuity-linux-cli.

The protocol column comes from the hub's protocol modules (see [protocols](../protocol/README.md)).
"Universal (assumed)" means the device has no dedicated module, so it most likely uses the universal
protocol; this has only been proven for the Pulsefire Haste 2 Wireless.

## Mice

All mice use the [universal protocol](../protocol/universal.md).

| Device | Status | Notes | Details |
|---|---|---|---|
| Pulsefire Haste 2 Wireless | **tested** | every command confirmed on the device | [notes](pulsefire-haste-2-wireless.md) |
| Pulsefire Haste 2 | untested | polling up to 8 kHz | [notes](pulsefire-haste-2.md) |
| Pulsefire Haste 2 S | untested | | [notes](pulsefire-haste-2-s.md) |
| Pulsefire Haste 2 Pro | untested | polling up to 4 kHz; also an "Instant Pair" variant | [notes](pulsefire-haste-2-pro.md) |
| Pulsefire Haste 3 | untested | no RGB; DPI 100–16000 in steps of 100 | [notes](pulsefire-haste-3.md) |
| Pulsefire Haste 3 Pro | untested | no RGB; DPI up to 42000; polling up to 8 kHz | [notes](pulsefire-haste-3-pro.md) |
| Pulsefire Haste 3 Wireless | untested | no RGB; DPI up to 42000; polling up to 8 kHz | [notes](pulsefire-haste-3-wireless.md) |
| Pulsefire Saga | untested | 5 LEDs; no DPI button | [notes](pulsefire-saga.md) |
| Pulsefire Saga Pro | untested | no DPI button; also an "Instant Pair" variant | [notes](pulsefire-saga-pro.md) |

## Other devices

These are detected by `ngenuity devices` when they use the universal protocol, but no command
supports them yet.

| Device | Protocol | What NGENUITY configures |
|---|---|---|
| Alloy Rise, Alloy Rise 75, Alloy Rise 75 Wireless | universal (assumed) | keys, per-key lighting |
| Alloy Origins 2 65, Origins 2 1800, Eve 1800 | universal (assumed) | keys, per-key lighting |
| Alloy Origins 2 Pro 65 | universal (assumed) | keys, per-key lighting, analog-key calibration |
| Clutch Talon (gamepad) | universal (assumed) | buttons, calibration |
| Clutch Tachi (gamepad) | Xbox GIP (handled by NGENUITY itself, not the hub) | buttons, lighting, calibration |
| Cloud III Wireless | dedicated hub module `cloud_3_wireless` | audio, settings |
| Cloud Stinger 3 Wireless (PC / PS / Xbox) | dedicated hub module `stinger_3_wireless` | audio, settings |
| Cloud III, Cloud III S Wireless, Cloud Alpha 2 Wireless, Cloud Alpha Air, Cloud Flight 2 (PC/PS, Xbox) | to be determined (`realtek` module or universal) | audio, lighting on some, Instant Pair |
| QuadCast 2 S, SoloCast 2, SoloCast 2 Pro, FlipCast (microphones) | to be determined | lighting, audio through NGENUITY's audio engine |

Firmware updates for all devices use vendor libraries (Airoha, Sonix, Realtek) that are Windows-only;
ngenuity-linux-cli does not do firmware updates.
