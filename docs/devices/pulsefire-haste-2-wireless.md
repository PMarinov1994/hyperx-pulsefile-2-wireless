# Pulsefire Haste 2 Wireless

| | |
|---|---|
| USB | dongle `03f0:0f98`, vendor interface 2 (usage page `0xFF00`) |
| Protocol | [universal](../protocol/universal.md) |
| ngenuity-linux-cli status | **tested**: every command marked ✔ was confirmed on the real mouse |
| ngenuity name | `pulsefire-haste-2-wireless` |

## Capabilities (from NGENUITY's `PulsefireHaste2WirelessConfiguration`)

- DPI 200–26000 in steps of 50, up to 5 stages, stage colours
- polling rate 125 / 250 / 500 / 1000 Hz; lift-off 1 mm / 2 mm; no motion sync, no angle snapping
- buttons: left, right, middle, back, forward, DPI; action types Keys & Buttons, Macro, Text, Launcher, Game Mode
- one RGB LED; software effects Alternating, Breathing, Confetti, Solid, Spectrum Wave, Sunrise, Wave; no hardware effects
  in NGENUITY (the firmware does implement Off, Solid, Breathing and Color Cycle presets, see the lighting tests below)
- wireless: battery, charging, sleep / wake, low-battery alert 5–25 %

## Supported commands

| Command | Use | Status |
|---|---|---|
| `10 01` → `11 01` | device information | ✔ |
| `52 01` → `53 01` | connected / asleep | ✔ |
| `50 02` → `51 02` | battery, charging, voltage, temperature | ✔ |
| `50 01` | low-battery alert | packet identical to NGENUITY's; the value cannot be read back |
| `32 01` / `32 02` | DPI table and polling rate, write / read | ✔ |
| `36 01` / `36 02` | sensor settings (lift-off), write / read | ✔ |
| `40 01` / `40 02` | brightness, write / read | ✔ |
| `42 03` | lighting effect read | ✔ |
| `44 02` | live colour (holds about 1.5–2 s per frame) | ✔ |
| `44 03`, `44 04`, `42 02` | FrameLight effect upload, 1 to 80 frames | ✔ (live and saved) |
| `42 02` modes 0, 1, 2, 4 | firmware presets Off, Solid, Breathing, Color Cycle | ✔ live; saved not tested; not used by ngenuity |
| `20 05`, `20 01`, `20 02`, `20 03`, `20 04` | button remapping: reset, write, read | ✔ |
| profile slot `1` of the commands above (`--save`) | onboard profile | ✔ (survives a power cycle) |
| `22 xx` | macros | not decoded |
| `12 01` | factory reset | decoded, deliberately not used |

## Device information reply

`11 01` layout (tentative field names, taken from the FlatBuffers `DeviceInformation` field order):
```
off  bytes                               value / guess
 2   04 b0 ae 51 2a 79 26 36 e6 ad 30 58 device_id (12 B)
14   00 x16                              firmware version strings? (empty)
31   02                                  category = Mouse (ProductCategory 2)
35   f0 03                               usb_vendor_id 0x03F0
37   97 0e                               0x0E97  (bootloader PID?)
39   99 01                               0x0199  (version / PID?)
41   97 0d                               0x0D97  (PID?)
43   09 11                               0x1109  (version?)
45   98 0f                               0x0F98  primary_usb_product_id (dongle PID)
50   01                                  current_mode?
52   ff                                  country_code = Unknown
53   82 01 07 eb 1e 00 00 06             mcu_vendor / support_features?
```


## Capture and test log

USB captures of NGENUITY 3.1.0 in a VirtualBox VM, recorded on the Linux host with `usbmon` and
filtered to the dongle's traffic (`captures/`):

| File | What NGENUITY did |
|---|---|
| `pulsefire-haste-2-wireless_01_startup-battery-sleep-wake.pcapng` | start-up, battery reading, mouse going to sleep and waking up; no settings changed |
| `pulsefire-haste-2-wireless_02_dpi-stage-add-save-dpi-button.pcapng` | new 6400 DPI stage, Save to the mouse, DPI-button presses |
| `pulsefire-haste-2-wireless_03_polling-rate-1000-250-1000-first-try.pcapng` | two start-ups, polling rate 1000 → 250 → 1000 |
| `pulsefire-haste-2-wireless_04_polling-rate-1000-250-1000.pcapng` | polling rate 1000 → 250 → 1000 |
| `pulsefire-haste-2-wireless_05_lift-off-low-high.pcapng` | lift-off Low ↔ High, no Save |
| `pulsefire-haste-2-wireless_06_brightness-low-high.pcapng` | brightness low → high, no Save |
| `pulsefire-haste-2-wireless_07_button-remap-forward-back.pcapng` | Forward button → Back → Forward, twice, no Save |

### First Linux probe (2026-10-12)

| Request | Reply |
|---|---|
| `10 01` DeviceInformation | `11 01` + data, see below |
| `10 02` SerialNumber | only the ACK from A; no data within 2 s |
| `14 02` CurrentProfileInformation | `15 02` all zeros (profile 0?) |
| `20 03 00 00` DPISettingsInformation | `21 03` all zeros |
| `50 03` | ACK from B with status 01, no data. **Not the battery query**: NGENUITY uses `50 02` (see the first NGENUITY capture below) |
| `52 01` RFConnectionStatus | `53 01 01` → **connected = 1**, followed by an unsolicited `fb 07` report |

### NGENUITY capture (`captures/pulsefire-haste-2-wireless_01_startup-battery-sleep-wake.pcapng`, VM via VirtualBox, no settings changed)

Commands NGENUITY sends at startup and after every reconnect, in this order:
`10 01`, `14 02` (startup only), `52 01`, `50 02` ×3, `40 01 00 00 82`, `36 01`, `32 01 …`, `20 05`, `22 07`.
After that it polls `52 01` every 5 s and `44 02 00 00 f2` about 15 times per second.

**Battery: request `50 02`** (no payload) → reply `51 02` from the mouse. Field order is the same as FlatBuffers `WirelessRFBatteryInformation`:
```
off  example  field
 2   36       battery_level  = 54 %
 3   00       charge_status  0 NoCharging, 1 Charging, 2 FullyCharged, 3 ChargerError, FF Unknown
                              (confirmed from Linux 2026-10-13: 00 → 01 after plugging in USB, voltage 3838 → 3996 mV)
 4   1a 00    temperature    i16 LE = 26 °C
 6   00 0f    voltage        u16 LE = 0x0F00 = 3840 mV (later 0x0F01 = 3841 mV)
 8   01       gauge_ic_type  1 = Cellwise
 9   00       charger_ic_type 0 = TI
10   00       low_battery_warning_threshold
```
The mouse also sends `51 02` unsolicited right after it wakes up. While the mouse sleeps, `50 02` gets only the dongle ACK.

**Connection status: `52 01` → `53 01 <connected>`** (confirmed, polled every 5 s by NGENUITY).

**Unsolicited link event `fb 0a <state>`**: `01` = mouse linked (woke up / switched on), `00` = link lost (sleep / off).
Timeline in the capture: `fb 0a 00` at 29.5 s (mouse asleep) → `53 01 00` replies → mouse moved: `fb 0a 01` at 143.4 s plus unsolicited battery → `53 01 01` → asleep `fb 0a 00` at 228.8 s → `fb 0a 01` at 232.0 s.
On every `fb 0a 01`, NGENUITY re-runs the startup sequence above.

**Queued commands:** a command sent while the mouse sleeps is delivered after wake-up. The mouse ACK for the `32 01` sent at 94.0 s arrived at 143.45 s, right after the wake event.

### DPI table and save sequence (`captures/pulsefire-haste-2-wireless_02_dpi-stage-add-save-dpi-button.pcapng`: new 6400 DPI stage, save, DPI-button presses)

**`32 01`: full DPI table** (built by `FUN_1400c9120`, confirmed by capture):
```
[0]=32 [1]=01
[2..3]  profile slot u16 LE (0 = live/active, 1 = onboard slot written on Save)
[4]     polling rate (UniversalPollingRate): 08 = 1000 Hz, 10 = 500 Hz, 20 = 250 Hz, 40 = 125 Hz  (confirmed 08<->20 in ngenuity4)
[5]     enabled-stage bitmask, bit i = stage i   (0x0f = 4 stages, 0x1f = 5 stages)
[6]     current stage index (0-based)
[7+5i .. 11+5i]  stage i, i = 0..10:  u16 LE code = DPI/50 - 1,  then R, G, B (stage indicator colour)
```
Example after adding the stage: `400 #ff0000, 800 #0000ff, 1600 #ffff00, 3200 #00ff00, 6400 #ffffff`, mask `1f`.
NGENUITY sends `32 01` (slot 0) live on every UI edit, before Save.
**Confirmed from Linux (2026-10-13):** the slot-0 table with stage 2 set to code `01` (100 DPI, below NGENUITY's 200 minimum) and then `47` (3600 DPI) changed the cursor speed noticeably each time.
Restoring it with the original table (code `1f`, 1600) worked. Only the dongle ACK comes back; the mouse sends no reply of its own. While the user was editing, stage 2 briefly passed through 12000, 3500 and 1650 before going back to 1600.

**DPI-button events (unsolicited, from the mouse):**
* `fb 01 20 00 01` / `fb 01 20 00 00`: button 0x20 (the DPI button) pressed / released.
* `fb 08 <stage> <code lo> <code hi>`: active DPI stage changed. DPI = (code+1)*50. Seen: `fb 08 03 3f 00` = stage 3, 3200 DPI, etc.

**Save to onboard slot 1** (all with [2..3] = slot 1):
```
44 03 50 50 00 01            lighting effect header? (0x50 = 80 frames)
44 04 <frame u16> R G B      × 80: a colour-cycle table (red→green→blue→red), one frame per packet, mouse replies 45 04 <frame>
42 02 01 00 06 32            ? (reply 43 02 01)
40 01 01 00 ff               ?
36 01 01                     ?
32 01 01 00 …                DPI table (above)
20 05 01 00 01               ?
22 07 01 00 01               ?
50 01 0a 01                  battery config: low-battery warning 10 %? [3]=01 ?
```
After the save, NGENUITY re-sends the slot-0 set (`40 01 00 00 ff`, `36 01`, `32 01 00 …`, `20 05`, `22 07`).
The startup `20 05` / `22 07` without arguments are probably "apply slot 0" or a sync; still unknown.


### Sensor settings `36 01` (`captures/pulsefire-haste-2-wireless_05_lift-off-low-high.pcapng`, lift-off Low/High, no Save)

```
[0]=36 [1]=01
[2..3] profile slot u16 LE
[4]    angle_snap_enable       (bool)          \
[5]    angle_tune_config       (0, 15, 30, E2=-30, F6=-10)  |  field order from FlatBuffers
[6]    angle_tune_enable       (bool)           |  SensorAdditionalCustomization;
[7]    lift_distance_config    00 = 1 mm (Low), 02 = 2 mm (High)   <- confirmed
[8]    motion_sync_enable      (bool)          /
```
Only [7] has been seen to change (`36 01 00 00 00 00 00 02` = High, `36 01` with zero payload = Low).
Every change in the UI makes NGENUITY re-send the whole slot-0 set `40 01, 36 01, 32 01, 20 05, 22 07`.
Changing the polling rate sent only `32 01` with the new [4]. Both changes are live and need no Save.

### Lighting (`captures/pulsefire-haste-2-wireless_06_brightness-low-high.pcapng`, brightness low → high, no Save)

**`40 01`: LED brightness**: `40 01 <slot u16 LE> <brightness>`. The value is NGENUITY's slider value passed straight through as a byte
(`LightsSWControlViewModel.OnGlobalBrightnessChanged` → `SetBrightness(BaseId, (byte)value)`).
The UI slider is a 0–100 % value (`GlobalBrightness`, default 100). On the wire it is scaled to 0–255, **byte = floor(percent × 255 / 100)**:
1 % → `02`, 51 % → `82`, 100 % → `ff` (all three seen in captures). Confirmed from Linux 2026-10-13: `02` dims and `ff` restores (live slot 0). The full range was verified with a solid `44 02` colour streamed: 0 % (`00`) = LED off, 25/50/75/100 % visibly brighter at each step. Brightness also applies to live-streamed colours. The colours streamed in `44 02` stay at full intensity, so the mouse applies the brightness itself.

**`44 02`: live colour frame**: `44 02 00 00 R G B`, streamed about 15 times per second while NGENUITY runs (software lighting effect, here a rainbow).
The mouse replies `45 02` (zeros). The startup `44 02 00 00 f2` from capture 1 was just a colour frame (R=f2) too.
**Confirmed from Linux (2026-10-13):** single `44 02 00 00 R G B` frames (red, green, blue, 4 s apart) and a 10 s stream of red at about 15 Hz
were all ACKed with status 00, and the LED showed solid red. When the stream stops, the mouse goes back to its stored onboard effect by itself.
Nothing is written to flash.

**`44 03` / `44 04`: stored effect for onboard use** (sent only on Save, see the DPI table and save sequence above): header `44 03 50 50 00 01`, then 80 frames `44 04 <frame u16 LE> R G B`.
This is what the mouse plays on its own when NGENUITY is not running. The header is
`<frames> <total packets u16> <profile u16>` (0x50 = 80 frames, 0x0050 = 80 packets, profile 1), see
[universal §3.2](../protocol/universal.md).

### Live lighting tests (2026-10-14, slot 0 only, nothing saved)

Run from Linux with throw-away scripts writing raw hidraw reports; the user watched the LED. Starting state read
back first: brightness `ff` and FrameLight duration 50 in both slots. Afterwards a power cycle of the mouse restored
the stored colour cycle, so it reloads slot 1 into slot 0.

**`44 02` hold time.** The same red frame streamed for 10 s with a fixed gap between frames:

| Gap | LED |
|---|---|
| 0.5 s | solid red |
| 1.0 s | solid red |
| 1.5 s | solid red |
| 2.0 s | flickers back to the stored effect between frames |

A single frame holds for about 1.5–2 s. To keep a live colour up without NGENUITY's 15 Hz stream, resend it every
0.5 s or faster.

**`42 02` firmware presets.** Off, Solid and Breathing work as sent; Wave, Confetti and Alternating are stored and
shown as Color Cycle. The duration is one byte (the high byte is dropped) and lower values are faster. Full table
in [universal §3.1](../protocol/universal.md).

**Short FrameLight tables.** A 1-frame upload (`44 03 01 01 00 00 00`, one `44 04`, `42 02 00 00 06 32 00`) and a
2-frame upload both held their colour for the whole 10 s with nothing streaming.

