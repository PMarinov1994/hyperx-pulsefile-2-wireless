# HyperX NGENUITY "universal" HID protocol — Pulsefire Haste 2 Wireless (03f0:0f98)

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

## 3. Command map (all request kinds the universal protocol knows)

`idx` = internal Rust request-kind index (the tables in §1). **Bold** = command ID that exists
in the Haste 2 Wireless report descriptor. Payload offsets are byte offsets in the 64-byte packet.
The names come from the matching FlatBuffers messages, so they are best guesses until the probe confirms them.

| cmd | sub | dispatcher case → handler | Request payload (from handler) | Probable meaning |
|---|---|---|---|---|
| **10** | 01 | 0x00 → `1401791c0` | none | Get DeviceInformation |
| **10** | 02 | 0x01 → `140178ec0` | none | Get DeviceSerialNumber |
| **12** | 01 | 0x02 → `140154e80` | [2]=u8 | **DeviceFactoryReset — never send in probing** |
| **14** | 01 | 0x03 → `140153460` | [2..3]=u16 profile, [4]=u8, [5]=u8 | CurrentProfileSetup (reset_profile, reset_state, switching_profile) |
| **14** | 02 | 0x04 → `140154800` | none | Get CurrentProfileInformation |
| **20** | 01 | 0x05/0x06 → `140153510`/`140154890` | [2..3]=u16 profile, [4]=page count, [5]=u8, [6]=n entries | DPISettings header |
| **20** | 02 | 0x06 → `140154890` | [2]=page idx, [3]=0, [4..63]=up to 15 × 4-byte entries | DPISettings data pages (see §4) |
| **20** | 03 | 0x07 → `140154f20` | [2],[3] = u16 (profile) | Get DPISettingsInformation |
| **20** | 04 | 0x08 → `1401559a0` | [2]=u8, [3]=page idx (one packet per page) | Get DPI data pages |
| **20** | 05 | 0x09 → `140155b90` | [2..3]=u16 profile, [4]=u8 | DPI/sensor single setting (polling rate?) |
| **22** | 01..03 | 0x0a–0x0c → `1401535e0`… | paged: [2]=page,[3]=pages,[4]=n, entries 4 B `(key, type, u16 code)` | GeneralKeyAssignment (button remap) |
| **22** | 04 | 0x0d → `140155af0` | [2],[3] | GeneralKeyAssignment GetTotalDataPages |
| **22** | 05 | 0x0e → `140155c30` | [2],[3] | GeneralKeyAssignment SettingsInformation request |
| **22** | 06 | 0x0f → `140155cd0` | [2],[3],[4] | Reset key assignment |
| **22** | 07 | 0x10 → `140155d80` | [2..3]=u16, [4]=u8 | key-assignment related |
| 24 | 01/02 | 0x11/0x12 | paged | (not in this mouse's descriptor) |
| 26 | 01/02 | 0x13–0x16 | | (not in this mouse's descriptor) |
| **32** | 01 (capture; static map said 02) | 0x17 → `1400c9120` | see §5.5 | **DPI table** (stages, DPI, colours, current stage). Confirmed by capture |
| **32** | 03 | 0x18 → `1400c4970` | u32 arg | Lighting: brightness info request |
| **36** | 06 / 01 / 02 / 03 | 0x19–0x1c | | Lighting effect control (preset / direct / frame data) |
| **40** | 04 / 05 | 0x1d / 0x1e | | macro / key data |
| **42** | 01 / 02 | 0x1f / 0x20 | | macro |
| **44** | 01 / 02 | 0x21 / 0x22 | | macro / SOCD |
| 46 | 01..04 | 0x24–0x27 | | (not in descriptor) |
| **50** | 02 | 0x28 → `14016e810` | args | WirelessRFBatteryConfiguration (low-battery threshold, save) |
| **50** | 03 | 0x29 → `14017a300` | none | Get WirelessRFBatteryInformation |
| **52** | 01 | 0x2a → `14017a000` | none | Get WirelessRFConnectionStatus |
| 54 | 02 / 05 | 0x2b / 0x2c | (u32 profile, u32 time) / (u32) | Sleep-time config / info (0x54 not in descriptor) |
| **60** | 04 / 01 | 0x49 / 0x4a | | |
| **62** | 02 / 01 | 0x4b / 0x4c | | |
| 66 | 01 / 02 | 0x4d / 0x4e | | |
| 70 | 02/04/07 | 0x4f–0x51 | | three-in-one dongle (not in descriptor) |
| 80 | ff | 0x54 | | |

Dispatcher cases 0x2d–0x48 are audio requests. In this protocol they only log "Universal Audio Coming Soon".

## 4. DPI settings encoding (request side)

Header `20 01`:
```
[0]=0x20 [1]=0x01 [2..3]=profile (u16 LE) [4]=ceil(n/15) [5]=u8 (current_dpi_index or polling rate, TBD) [6]=n
```
Data pages `20 02` (one per 15 entries):
```
[0]=0x20 [1]=0x02 [2]=page index [3]=0x00 [4..] = entries of 4 bytes: [kind][a][b][c]
```
Entry kinds produced by the encoder (`FUN_140154890`):

| kind | bytes a,b,c | notes |
|---|---|---|
| 1 | idx, v1, v2 | |
| 2 | idx, v, 0 | probably enable flag |
| 3 | idx, lo, hi | **u16 resolution** (DPI, 200–26000 step 50 for Haste 2) |
| 4 | idx, v, 0 | |
| 5 | idx, v1, v2 | |
| 6 | idx, v, 0 | |

Value ranges from the .NET side:
* DPI: 200–26000, step 50 (`PulsefireHaste2DPIResolutionSettings`)
* Polling rate enum (`UniversalPollingRate`): 125 Hz=`0x40`, 250=`0x20`, 500=`0x10`, 1000=`0x08` (2K=`0x04`, 4K=`0x02`, 8K=`0x01` not supported on this mouse)
* Lift distance: 1 mm=`0`, 2 mm=`2`; angle tune: 0, +15, +30, −30 (`0xE2`), −10 (`0xF6`)
* Charge status: 0 none, 1 charging, 2 full, 3 error, `0xFF` unknown
* Haste 2 Wireless UI: 1 LED zone (`CustomLed1`); buttons Left/Right/Middle/Forward/Back/DPI;
  software RGB effects only (no hardware effects); motion sync not supported.

## 5. Confirmed on the device (2026-10-12, `/dev/hidraw4`, NGENUITY/Wine stopped)

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

### 5.3 Replies

| Request | Reply |
|---|---|
| `10 01` DeviceInformation | `11 01` + data, see below |
| `10 02` SerialNumber | only the ACK from A; no data within 2 s |
| `14 02` CurrentProfileInformation | `15 02` all zeros (profile 0?) |
| `20 03 00 00` DPISettingsInformation | `21 03` all zeros |
| `50 03` | ACK from B with status 01, no data. **Not the battery query**: NGENUITY uses `50 02` (§5.4) |
| `52 01` RFConnectionStatus | `53 01 01` → **connected = 1**, followed by an unsolicited `fb 07` report |

DeviceInformation `11 01` layout (tentative field names, taken from the FlatBuffers `DeviceInformation` field order):
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

### 5.4 NGENUITY capture (`captures/ngenuity1.pcapng`, VM via VirtualBox, no settings changed)

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

### 5.5 DPI table and save sequence (`captures/ngenuity2.pcapng`: new 6400 DPI stage, save, DPI-button presses)

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

The cmd→meaning labels in §3 came from the static mapping, and they are wrong for at least `32` and `50`. Trust §5.4/§5.5 over §3.

### 5.6 Sensor settings `36 01` (`captures/ngenuity5.pcapng`, lift-off Low/High, no Save)

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

### 5.7 Lighting (`captures/ngenuity6.pcapng`, brightness low → high, no Save)

**`40 01`: LED brightness**: `40 01 <slot u16 LE> <brightness>`. The value is NGENUITY's slider value passed straight through as a byte
(`LightsSWControlViewModel.OnGlobalBrightnessChanged` → `SetBrightness(BaseId, (byte)value)`).
The UI slider is a 0–100 % value (`GlobalBrightness`, default 100). On the wire it is scaled to 0–255, **byte = floor(percent × 255 / 100)**:
1 % → `02`, 51 % → `82`, 100 % → `ff` (all three seen in captures). Confirmed from Linux 2026-10-13: `02` dims and `ff` restores (live slot 0). The full range was verified with a solid `44 02` colour streamed: 0 % (`00`) = LED off, 25/50/75/100 % visibly brighter at each step. Brightness also applies to live-streamed colours. The colours streamed in `44 02` stay at full intensity, so the mouse applies the brightness itself.

**`44 02`: live colour frame**: `44 02 00 00 R G B`, streamed about 15 times per second while NGENUITY runs (software lighting effect, here a rainbow).
The mouse replies `45 02` (zeros). The startup `44 02 00 00 f2` from capture 1 was just a colour frame (R=f2) too.
**Confirmed from Linux (2026-10-13):** single `44 02 00 00 R G B` frames (red, green, blue, 4 s apart) and a 10 s stream of red at about 15 Hz
were all ACKed with status 00, and the LED showed solid red. When the stream stops, the mouse goes back to its stored onboard effect by itself.
Nothing is written to flash.

**`44 03` / `44 04`: stored effect for onboard use** (sent only on Save, §5.5): header `44 03 50 50 00 01`, then 80 frames `44 04 <frame u16 LE> R G B`.
This is presumably what the mouse plays on its own when NGENUITY is not running. The header bytes still need decoding:
0x50 = 80 frames; the second 0x50 is speed?; `00 01` = slot 1?

## 6. Open items
1. ~~Battery query~~. Done: it is `50 02` (§5.4). My static sub mapping for cmd 0x50 was off by one, so the other static sub numbers in §3 also need checking against captures.
5. Meaning of B-ACK status `01`. For `32 01` it looks like "done" rather than "rejected" (§5.4), so the §5.1 reading may be wrong.
6. Startup commands with unknown meaning: `40 01 00 00 82` / `40 01 00 00 ff`, `32 01 00 00 08 01 01 1f 00 ff ff`, `36 01`, `20 05`, `22 07`, and `44 02 00 00 f2` (polled about 15×/s, mouse replies `45 02` all zeros). Some of these may be writes of NGENUITY's stored profile, so don't replay them until they are understood.
2. ~~Which ID is dongle/mouse~~. Done: A = dongle, B = mouse (§5.1).
3. Exact meaning of the DPI entry kinds 1, 2, 4, 5, 6 and header byte [5]. Compare a device readback (`20 04`) with what NGENUITY sends.
4. Lighting (`44 03`/`44 04` colour table, `36`) and macro (`40`–`44`, `60`/`62`) payloads. Decode these after the basics work.
