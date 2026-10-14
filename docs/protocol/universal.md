# NGENUITY "universal" HID protocol

Status: **draft from static analysis** of NGENUITY 3.1.0. The request side is decoded from
the binary. Response layouts still have to be confirmed on the device with `probe_readonly.py`.

## 1. Software architecture (where the protocol lives)

| Component | Role |
|---|---|
| `NGENUITY.dll` / `NGENUITY.Common.dll` (.NET, Avalonia) | UI only. Sends high-level **FlatBuffers** messages (`CommunicationHub.CommandData` union: `DPISettings`, `SensorAdditionalCustomization`, `WirelessRFBatteryInformation`, ...) to the hub over NetMQ/ZeroMQ. |
| `Assets/Services/hxn-srv-communication-hub.exe` (Rust, x64) | Converts those messages into 64-byte HID reports. Mice use the module `src\protocol\universal.rs`. Uses statically linked C `hidapi`. |

Key functions in the hub (Ghidra, image base 0x140000000):

| Address | Meaning |
|---|---|
| `0x1400bf770` | universal protocol request dispatcher (`switch` over ~0x5d request kinds) |
| `0x1400fdc60` | `request_kind -> cmd byte` lookup, table `0x14048bb70` (58 entries) |
| `0x140104560` | `request_kind -> sub byte` lookup, table `0x14048bbaa` (58 entries) |
| `0x140079cc0` | out-engine: writes each 64-byte packet, ≥10 ms pacing, optional target bits |
| `0x140104570` | waits for the 64-byte reply (crossbeam channel `recv_timeout`) |

## 2. Transport

* USB interface **2** of the dongle: vendor usage page `0xFF00`, interrupt EP `0x83` IN, `0x04` OUT, 64 bytes.
  On Linux it is the hidraw node whose report descriptor starts with `06 00 ff` (currently `/dev/hidraw4`).
* Every packet is **64 bytes: `[report_id][63 bytes]`**, and **report_id == command byte**.
  The report descriptor declares each ID as both an Output and a Feature report (63 bytes):
  `10 12 14 20 22 30 32 36 40 42 44 50 52 60 62 F0 FA FC`
* Replies and events arrive as **Input reports with ID = command + 1**:
  `11 13 15 21 23 31 33 37 41 43 45 51 53 61 F1 FB FD FF`
* Packet layout: `byte0 = cmd`, `byte1 = sub`, `byte2.. = payload`, zero padded to 64.
* NGENUITY waits at least **10 ms** between packets.
* **Target addressing (wireless):** if a per-device flag is set, the out-engine rewrites byte 1 as
  `(target << 6) | (sub & 0x3F)`. This is probably dongle (0) vs. mouse (1). Not yet confirmed.
* Multi-packet transfers use pages of 15 entries × 4 bytes. Page count = `ceil(n/15)`, computed as `(n+14)/15`.

## 3. Command map (complete, extracted from the hub binary)

**How it was extracted.**
- Every request handler gets its report ID from `universal_kind_to_cmd` (table at `0x14048bb70`) and its sub-command from `universal_kind_to_sub` (table at `0x14048bbaa`).
- Each lookup takes its **own** index byte. Some handlers pass the same index to both lookups and some pass two different ones (the DPI handler uses `0x11`/`0x19` → `32 01`). The first version of this table assumed one index for both, which is why it was wrong.
- A capstone sweep of the whole `.text` section records the actual argument of every lookup call. Each call site was then matched to its dispatcher case.
- The frame-upload handler (case `0x23`) writes `44 03`/`44 04`/`42 02` as literal constants and was read from its decompiled code.
- Names come from the order of the dispatcher cases. That order follows the FlatBuffers `CommandData` request types, and the payload shapes match the fields of each type.
- ✔ = confirmed in a capture or from Linux.

The Haste 2 report descriptor only declares report IDs `10 12 14 20 22 30 32 36 40 42 44 50 52 60 62 F0 FA FC`. **Bold** rows are the mouse-relevant ones.
`60`/`62` are declared, but in the hub they are audio commands; `30`/`F0`/`FA`/`FC` are not in the hub's tables (probably firmware update).

| cmd sub | case | Request (FlatBuffers type) | Payload (byte offsets) |
|---|---|---|---|
| **10 01** ✔ | 00 | DeviceInformation | – (reply `11 01`, see the [device notes](../devices/pulsefire-haste-2-wireless.md)) |
| **10 02** | 01 | DeviceSerialNumberRequest | – |
| **12 01** | 02 | DeviceFactoryReset | [2] u8. **Never send** |
| **14 01** | 03 | CurrentProfileSetup | [2..3] reset_profile u16, [4] reset_profile_state, [5] switching_profile |
| **14 02** ✔ | 04 | CurrentProfileInformationRequest | – |
| **20 01** | 05 | GeneralKeyDefinitionSetup (header only) | [2..3] profile, [4] pages = ceil(n/15), [5] u8, [6] n |
| **20 01 + 20 02** | 06 | GeneralKeyAssignmentEvent | header as above, then pages `20 02 <page> 00` + 15 × 4-byte entries (§4) |
| **20 03** | 07 | GeneralKeyAssignmentGetTotalDataPagesRequest | [2] profile, [3] layer |
| **20 04** | 08 | GeneralKeyAssignmentSettingsInformationRequest | one packet per page: [2] profile, [3] page index |
| **20 05** ✔ | 09 | ResetGeneralKeyAssignmentSettings | [2..3] profile, [4] reset_mcu (sent at startup with 0 and on Save with `01 00 01`) |
| **22 01** | 0a | MacroSetup | paged, see `build_key_assignment` |
| **22 02** | 0b | MacroGroupConfiguration | |
| **22 03** | 0c | MacroActionDataEventConfiguration | |
| **22 04** | 0d | MacroGetTotalGroupRequest | [2] profile, [3] switch_layer |
| **22 05** | 0e | MacroGetGroupInformationRequest | [2] profile, [3] group_id |
| **22 06** | 0f | MacroActionDataInformationRequest | [2] profile, [3] group_id, [4] data_pages_sequence_number |
| **22 07** ✔ | 10 | ResetMacroKeyAssignmentSettings | [2..3] profile, [4] reset_mcu |
| 24 02/03, 24 06 | 11, 12 | KeyPressAndReleaseSetup / ResetKeyPressAndRelease | |
| 26 01/03/04/05 | 13–16 | SOCDSetup / GetTotalDataPages / SettingsInformation / ResetSOCD | |
| **32 01** ✔ | 17 | DPISettings | §3.3 |
| **32 02** | 18 | DPISettings information request | [2] profile |
| **36 01** ✔ | 19 | SensorAdditionalCustomization | §3.3 |
| **36 02** | 1a | SensorAdditionalCustomization information request | [2] profile |
| **36 03** | 1b | MouseSensorLiftCalibrationRequest | [2..3] profile, [4] state, [5] lift_calibration_parameter |
| **36 04** | 1c | MouseSensorLiftCalibrationStatusRequest | [2] profile |
| **40 01** ✔ | 1d | LightingEffectControlLEDBrightnessConfiguration | [2..3] profile, [4] brightness 0–255 |
| **40 02** | 1e | LightingEffectControlLEDBrightnessInformationRequest | [2] profile |
| **42 02** ✔ | 1f | LightingEffectControlPresetModeSetup | §3.1 |
| **42 03** | 20 | LightingEffectControlPresetModeInformationRequest | [2] profile |
| **44 01** | 21 | LightingEffectControlDirectModePerKeyLightConfiguration | [2] total_pages |
| **44 02** ✔ | 22 | LightingEffectControlDirectModePerKeyLightData | [2..3] page/seq, [4..] RGB per LED (one LED: `44 02 00 00 R G B`) |
| **44 03 / 44 04** ✔ | 23 | LightingEffectControlDirectModeFrameLightData | §3.2 |
| 46 03..06 | 24–27 | Ambient light config/status, light-enable config/status | |
| **50 01** ✔ | 28 | WirelessRFBatteryConfiguration | [2] low_battery_warning_threshold (%, NGENUITY slider 5–25, default 10), [3] save_threshold_to_device. Not reported back: byte [10] of `51 02` stays 0 |
| **50 02** ✔ | 29 | WirelessRFBatteryInformation | – (reply `51 02`, §3.3) |
| **52 01** ✔ | 2a | WirelessRFConnectionStatus | – (reply `53 01 <connected>`) |
| 54 01 / 54 02 | 2b, 2c | WirelessRFDeviceSleepTimeConfiguration (u32 profile, u32 time) / information request | not declared by this mouse |
| – | 2d–48 | audio (input/output level, mute, EQ, monitoring, chat-mix, …) | log "Universal Audio Coming Soon" |
| 60 01 / 60 02 | 49, 4a | GenericAudioSettingsConfiguration / InformationRequest | audio |
| 62 01 / 62 02 | 4b, 4c | AdvancedAudioPromptSoundSwitching / InformationRequest | audio |
| 66 01 / 66 02 | 4d, 4e | OnboardEQConfiguration / InformationRequest | audio |
| 70 02 / 04 / 07 | 4f–51 | ThreeInOneDongle mode status / enter pairing / clear pairing | other dongle type |
| 80 ff | 54 | InputNotificationEnableConfiguration (probably) | |
| – | 52, 53, 55–5c | gamepad (info, trigger dead-zone, thumbstick, vibration) | no packet in this protocol |

### 3.1 `42 02` LightingEffectControlPresetModeSetup
```
[2..3]   profile u16
[4]      layer-1 mode      0 TurnOff, 1 Solid, 2 Breath, 3 Wave, 4 ColorCycle, 5 Confetti,
                           6 FrameLight, 7 VUMeter, 8 MirrorWave, 9 Alternating
[5..6]   layer-1 duration u16 (speed / frame time)
[7]      layer-1 direction 0 Unknown, 1 Left, 2 Right, 3 Up, 4 Down, 5 CenterOut, 6 CenterIn
[8]      layer-1 colour type 0 Unknown, 1/2/3 = one/two/three colours, FE Spectrum, FF Random
[9..17]  layer-1 colours, 3 × RGB
[18]     layer-2 trigger mode 0 TurnOff, 80 Fade, 81 Explosion, 82 HyperXFlame
[19..20] layer-2 duration, [21] direction, [22] colour type, [23..31] 3 × RGB
```
The Save in capture 2 sent `42 02 01 00 06 32 00`: profile 1, FrameLight, duration 50.

`42 03 <profile>` reads the layer-1 setup back as `43 03 <mode> <duration u16> <direction> <colour type> <colours>`,
i.e. the `42 02` payload from [4] on, without the profile bytes.

**Firmware preset modes, tested on the Pulsefire Haste 2 Wireless (2026-10-14, live slot 0).**
NGENUITY never sends these for this mouse (§5.5), but the firmware implements some of them. Each `42 02` below was
ACKed with status 00 and answered with `43 02`; the "stored" column is what `42 03 00` read back right after, and
"seen" is what the LED did.

| Sent | Stored | Seen |
|---|---|---|
| `42 02 00 00 00` Off | mode 0 | LED off |
| `42 02 00 00 01 00 00 00 01 ff 00 00` Solid, one colour | mode 1, `ff 00 00` | solid red |
| `42 02 00 00 02 32 00 00 01 00 ff 00` Breath, one colour, duration 50 | mode 2, duration 50 | breathing green |
| `42 02 00 00 02 d0 07 00 01 00 ff 00` Breath, duration 2000 | mode 2, duration **`d0 00`** = 208 | breathing green |
| `42 02 00 00 03 32 00 00 fe` Wave, spectrum | **mode 4** | colour cycle |
| `42 02 00 00 04 32 00 00 fe` ColorCycle, spectrum | mode 4 | colour cycle |
| `42 02 00 00 05 32 00 00 ff` Confetti, random | **mode 4** | colour cycle |
| `42 02 00 00 09 32 00 00 02 ff 00 00 00 00 ff` Alternating, two colours | **mode 4**, colours kept | colour cycle |

* Usable hardware modes on this mouse: **0 Off, 1 Solid, 2 Breath, 4 ColorCycle**. Wave, Confetti and Alternating
  are stored as ColorCycle.
* **The duration is effectively one byte**: the high byte of the u16 is dropped (`d0 07` is stored as `d0 00`).
* **Lower duration = faster** (Breath and ColorCycle at 10 vs. 255, judged by eye). The time unit is not measured yet.
* The preset replaces the live effect and stays until something else is written or the mouse is power-cycled
  (§5.3). Whether a preset written to profile 1 survives a power cycle is not tested yet; FrameLight does.

### 3.2 FrameLight upload (`DirectModeFrameLightData`, case `0x23`)
```
44 03 <frames u8> <total packets u16> <profile u16> <u8>     header
44 04 <packet index u16> <colour data>                     × total packets (one RGB per LED)
42 02 <profile u16> 06 <duration u16> 00 …                 switch the profile to FrameLight
```
Capture 2: `44 03 50 50 00 01 00` = 80 frames, 80 packets, profile 1. Then `44 04 0000 ff0000` … `44 04 004f …`, then `42 02 01 00 06 32 00`.

**Short tables work (confirmed on the Haste 2 Wireless, 2026-10-14, live slot 0).** A single frame holds a static
colour with nothing streaming, so a solid colour needs 3 packets instead of NGENUITY's 82:
```
44 03 01 01 00 00 00      1 frame, 1 packet, profile 0
44 04 00 00 ff 00 ff      frame 0 = magenta          (mouse replies 45 04 00 00)
42 02 00 00 06 32 00      FrameLight, duration 50    (mouse replies 43 02)
```
A 2-frame table (`44 03 02 02 00 00 00`, two `44 04` frames) also played steadily. Both colours stayed on for the
whole 10 s observation.

### 3.3 Payloads decoded from captures

First decoded on the Pulsefire Haste 2 Wireless; the capture logs are in its
[device notes](../devices/pulsefire-haste-2-wireless.md).

**`32 01` DPI table** (`32 02 <profile>` reads it back as `33 02` without the two profile bytes):
```
[2..3]  profile slot u16 LE (0 = live, 1 = onboard profile written on Save)
[4]     polling rate: 01 = 8000, 02 = 4000, 04 = 2000, 08 = 1000, 10 = 500, 20 = 250, 40 = 125 Hz
[5]     enabled-stage bitmask, bit i = stage i
[6]     active stage (0-based)
[7+5i]  stage i: u16 LE code = DPI/50 - 1, then R, G, B (stage indicator colour)
```

**`36 01` sensor settings** (`36 02 <profile>` reads them back as `37 02` without the profile bytes):
`[2..3]` profile, `[4]` angle snap, `[5]` angle tune, `[6]` angle tune enable,
**`[7]` lift-off: 00 = 1 mm, 02 = 2 mm**, `[8]` motion sync.

**`40 01` brightness:** `[2..3]` profile, `[4]` brightness 0–255 (NGENUITY sends percent × 255 / 100).
`40 02 <profile>` → `41 02 <brightness>`.

**`44 02` live colour:** `44 02 00 00` then R, G, B per LED. The device shows it only while it keeps
arriving (NGENUITY sends about 15 per second), then returns to its stored effect.
**Hold time, measured on the Haste 2 Wireless (2026-10-14):** a stream of the same colour for 10 s with a fixed gap
between frames stayed solid with gaps of 0.5, 1.0 and 1.5 s, and started flickering back to the stored effect at 2.0 s.
A frame therefore holds for about 1.5–2 s; a tool that keeps a static live colour should resend it at least every
0.5 s to have margin for packets lost over RF.

**`51 02` battery reply** (to `50 02`): `[2]` level %, `[3]` charge status (0 not charging,
1 charging, 2 full, 3 charger error, FF unknown), `[4..5]` temperature °C (i16 LE),
`[6..7]` voltage mV (u16 LE), `[8]` gauge chip type, `[9]` charger chip type.

**`53 01` connection** (to `52 01`): `[2]` = 1 connected, 0 asleep or off.

## 4. Button remapping (`20 xx`, GeneralKeyAssignment)

Encoder `FUN_140154890` (case 06), confirmed by `pulsefire-haste-2-wireless_07_button-remap-forward-back.pcapng`.

**Sequence NGENUITY sends for every remap** (live, profile 0):
```
20 05 00 00 00                      ResetGeneralKeyAssignmentSettings: profile 0, reset_mcu 0 (back to defaults)
20 01 00 00 <pages> 01 <n>          header: [2..3] profile, [4] pages = ceil(n/15), [5] layer (1 = Base), [6] n entries
20 02 <page> 00 <entries…>          one per page, up to 15 × 4-byte entries; the mouse replies 21 02
22 07 00 00 00                      ResetMacroKeyAssignmentSettings: profile 0, reset_mcu 0
```
Only buttons that differ from the default are sent; the reset first restores the defaults.

**Entry `[type][button][a][b]`.** `button` is the physical button's `MouseKeyCode`:
1 Left, 2 Right, 4 Middle, 8 Back, 0x10 Forward, 0x20 DPI.

| type | Action | a | b |
|---|---|---|---|
| 01 | Mouse button | MouseKeyCode (1 Left, 2 Right, 4 Middle, 8 Back, 10 Forward, 20 DPI) | MouseKeyAction (1 SingleClick, 2 DoubleClick, 3 Wheel, 8 SinglePress, 9 DoublePress, 10 TriplePress, 11 LongPress) |
| 02 | Keyboard key | HID usage ID (`KeyboardKeyCode`: A = 4 … Z = 29, 1 = 30 …, Enter 40, ESC 41, …) | 00 |
| 03 | Consumer / media | ConsumerKeyCode u16 LE: MediaNext 181, MediaPrev 182, MediaStop 183, MediaPlay 205, VolumeMute 226, VolumeUp 233, VolumeDown 234, Calculator 402, WebBack 548, WebForward 549, … ||
| 04 | Extra function | ExtraKeyCode: 0 Disable, 1 DpiAdd, 2 DpiSub, 3 DpiCycleUp, 4 DpiCycleDown, 5 DpiClutch, 6 ForwardSwitchApps, 7 BackwardSwitchApps | 00 |
| 05 | MediaDAC | code | trigger (0 SinglePress, 1 DoublePress, 2 TriplePress, 3 LongPress) |
| 06 | GamePad | code | 00 |

**Captured** (Forward side button → Back, then back to Forward, twice):
```
20 02 00 00 01 10 08 01     Mouse, button Forward (10) → BackButton (08), SingleClick
20 02 00 00 01 10 10 01     Mouse, button Forward (10) → ForwardButton (10) = default
```

Read-back: `20 03 <profile> <layer>` = total pages, then `20 04 <profile> <page>` per page.
With the Forward button back on its default (2026-10-13), `20 03 00 01` → `21 03 00` (0 pages) and `20 04 00 00` → `21 04` (empty).
So with no remap active, the mouse reports nothing. The reply layout with an active remap is still unconfirmed.
`22 04 00 01` (macro total groups) → `23 04 01`; its meaning is unknown.

**Confirmed from Linux (2026-10-14):** remapped Back → Forward live (`20 05 00 00 00`, `20 01 00 00 01 01 01`, `20 02 00 00 01 08 10 01`, `22 07 00 00 00`).
The user confirmed in a browser that the back button went forward.
Read-back: `20 03 00 01` → `21 03 01 01` (1 page, 1 entry); `20 04 00 00` → `21 04 01 00 01 08 10 01` (entries from [4], same 4-byte format).
Restored with entry `01 08 08 01`; afterwards both reads came back empty, so the mouse does not store default assignments.

**Saving (NGENUITY `ApplyAndSaveKeyAssignment`):** the same sequence with profile `1` and `reset_mcu = 1`, i.e. `20 05 01 00 01`, then `20 01 01 00 …` / `20 02 …`.

## 5. Protocol behaviour

These rules were established on the Pulsefire Haste 2 Wireless
([device notes](../devices/pulsefire-haste-2-wireless.md)). They are expected to hold for every
device that uses this protocol.

### 5.1 ACK report `0xFF` (sent for every command)
```
ff 01 <12-byte device id> <echoed cmd> <echoed byte1> <status> 00...
```
Two different device IDs answer:

| ID | Behaviour |
|---|---|
| `bf b4 c7 20 22 98 5e f9 75 cf 11 76` ("A") | ACKs **every** packet first, always status `00` |
| `04 b0 ae 51 2a 79 26 36 e6 ad 30 58` ("B") | either sends the real reply (`cmd+1` report) **or** an ACK with status `01` (= rejected / not supported) |

ID B is also the `device_id` inside DeviceInformation.

**Mouse-off test (same day):** with the mouse switched off and the dongle still plugged in:
* A still ACKs every packet → **A = dongle** (local ACK on receipt).
* B no longer sends anything except the `11 01` DeviceInformation reply → **B = mouse** (answers over RF).
  The dongle answers DeviceInformation itself from a cached copy, without the A-ACK.
* `52 01` → `53 01 00`: byte 2 of `53 01` is the **connected flag** (1 = mouse linked, 0 = off/out of range).
* `50 03` → only the A-ACK. With the mouse on, the mouse answers status 01. So the battery query does reach the mouse but is refused in this form.

### 5.2 Target bits in byte 1
With byte 1 = `0x40|sub`, `0x80|sub` or `0xC0|sub`, B either rejects the packet (status 01) or returns an all-zero reply.
**Use target 0 (plain sub) for this dongle.**

### 5.3 Events, sleep and pacing

* Unsolicited reports (report ID `0xFB`): `fb 0a <0|1>` link lost / restored (wireless sleep and wake),
  `fb 08 <stage> <dpi code u16>` active DPI stage changed, `fb 01 <button> 00 <0|1>` button released / pressed.
  The mouse also sends `51 02` (battery) by itself right after waking.
* A command sent while a wireless device sleeps is queued by the dongle and delivered on wake-up.
  Tools should check `52 01` first and wait for `fb 0a 01`.
* Some commands are answered by the device itself with a `cmd+1, sub` report after the dongle ACK
  (`45 04` per FrameLight frame, `43 02` after `42 02`, `21 02` after a key page).
  **Wait for that reply before sending the next packet**: sending faster makes the device drop packets over RF.
* Power-cycling the mouse (its switch) reloads the onboard profile 1 into the live profile 0. This undoes any live
  lighting change (`42 02`, FrameLight, `44 02`) that was not saved, which makes it the recovery step after tests.

### 5.4 Reading settings back (confirmed from Linux 2026-10-13, mouse awake)

These queries were found by the binary extraction (§3). The mouse answers each one with `cmd+1, sub`.

| Request | Reply | Layout |
|---|---|---|
| `32 02 <profile>` | `33 02 08 1f 02 07 00 ff 00 00 0f 00 00 00 ff 1f 00 ff ff 00 3f 00 00 ff 00 7f 00 ff ff ff` | the `32 01` payload without the profile: [2] polling-rate code, [3] enabled-stage mask, [4] active stage, [5+5i..] stage i = u16 DPI code + RGB |
| `36 02 <profile>` | `37 02 00 …` | [2] angle_snap, [3] angle_tune, [4] angle_tune_enable, **[5] lift-off** (00 = 1 mm, 02 = 2 mm; confirmed: `37 02 00 00 00 02` after `36 01 … 02`), [6] motion_sync. Same layout as the `36 01` payload without the profile |
| `40 02 <profile>` | `41 02 ff` | [2] brightness 0–255 |
| `42 03 <profile>` | `43 03 06 32 00` | [2] layer-1 mode (6 = FrameLight), [3..4] duration (50), [5] direction, [6] colour type, [7..] colours (§3.1) |

Profile 0 and profile 1 returned identical data. While the mouse sleeps, only the dongle ACK comes back.

### 5.5 Software lighting effects (light engine `hxn-srv-light-engine.exe`)

`PulsefireHaste2WirelessConfiguration` lists only **software** effects: Alternating, Breathing, Confetti, Solid, SpectrumWave, Sunrise and Wave.
`GetSupportHWEffects` throws NotImplemented, so the firmware's built-in preset modes (Breath, Wave, ColorCycle, …) are not used for this mouse.
The firmware still implements Off, Solid, Breath and ColorCycle; see the test in §3.1.
NGENUITY sends the effect description to the Rust light engine, which renders colours in real time. They are streamed live as `44 02`, and on Save one cycle is uploaded as FrameLight (§3.2).

Speed: `period_ms = max − speed% × (max − min)`.
- Breathing 800–4800 ms
- Alternating 1200–4800 ms
- Confetti 100–1200 ms
- SpectrumWave 200–2000 ms
- Sunrise 400–2400 ms
- Wave 500–4500 ms

Default speed 50 %. The FrameLight `42 02` speed field carries the speed % itself (`0x32` = 50).

Per-LED render formulas (progress `t` = elapsed / period, 0 → 1; channels clamped to 0–255 and truncated):

| Effect | Function | Formula for one LED at (0,0) |
|---|---|---|
| Breathing | `0x14002df60` | colour × sin(π·t) |
| Alternating | `0x14002a9c0` | toggles colour every 0.2 period (5 toggles per period); gradient mode blends linearly inside each 0.2 slot |
| Confetti | `0x140025f00` | each period: previous ← current, new ← random RGB (3 random bytes); blends between them |
| SpectrumWave | `0x14002be20` | colour list index advances every period; blends colour[i] → colour[i+1] by t |
| Wave | `0x14002ae60` | gradient(fmod(−t + 1, 1)) over (offset, colour) stops, wrapping last → first |
| Sunrise | `0x14002a2a0` | per LED a random one of 3 built-in gradients (table built in `0x140029b70`) plus closing stop 1.0 → first colour |
| Twilight | `0x14002d150` | random twinkling particles (not offered for this mouse) |

Sunrise gradients:
- A: 0 `FFB200`, 0.5 `FF6100`
- B: 0 `FFB200`, 0.25 `FF6100`, 0.5 `FF1400`, 0.75 `FFB700`
- C: 0 `FF8200`, 0.2 `FF9900`, 0.4 `FFA100`, 0.6 `FFA800`, 0.8 `FF6100`

**The stored colour cycle in capture 2** is SpectrumWave through `FF0000, CCFF00, 00FF66, 0066FF, CC00FF`, sampled as 80 frames at t = i/79 (first frame = last frame).
Re-rendering it with the formula above reproduces every frame within ±2 per channel.

**Confirmed from Linux (2026-10-14):** FrameLight upload to the **live slot 0** works.
`pulsefire lighting solid purple` sends 80 × `44 04 <i> 80 00 FF` plus the header and `42 02 00 00 06 32 00`, and the LED turned solid purple.
**Wait for the mouse's `45 04 <i>` reply after every frame**, and for `43 02` after `42 02`. On the first try only the dongle ACK was awaited.
80 frames were sent in about 1 s, the mouse dropped most of them over RF, and only a few frames of the playing table changed (a short purple flash in every cycle).

**Saving confirmed (2026-10-14):** `pulsefire lighting solid purple --save` (the same upload to slot 1) survived a power cycle; the user confirmed the LED came back solid purple.
`pulsefire lighting rainbow --save` then restored the original stored cycle (byte-identical to NGENUITY's Save).

## 6. Open items
1. ~~Battery query~~. Done: it is `50 02`. My static sub mapping for cmd 0x50 was off by one, so the other static sub numbers in §3 also need checking against captures.
5. Meaning of B-ACK status `01`. For `32 01` it looks like "done" rather than "rejected", so the §5.1 reading may be wrong.
6. Startup commands with unknown meaning: `40 01 00 00 82` / `40 01 00 00 ff`, `32 01 00 00 08 01 01 1f 00 ff ff`, `36 01`, `20 05`, `22 07`, and `44 02 00 00 f2` (polled about 15×/s, mouse replies `45 02` all zeros). Some of these may be writes of NGENUITY's stored profile, so don't replay them until they are understood.
2. ~~Which ID is dongle/mouse~~. Done: A = dongle, B = mouse (§5.1).
3. Exact meaning of the DPI entry kinds 1, 2, 4, 5, 6 and header byte [5]. Compare a device readback (`20 04`) with what NGENUITY sends.
4. Lighting (`44 03`/`44 04` colour table, `36`) and macro (`40`–`44`, `60`/`62`) payloads. Decode these after the basics work.
