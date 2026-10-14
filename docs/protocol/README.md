# Protocols

NGENUITY talks to devices through its Rust service `hxn-srv-communication-hub.exe`. The hub has
four device protocols (from its source paths, `src\protocol\*.rs` and `src\device\*.rs`), and
NGENUITY handles two more paths itself.

| Protocol | Used by | State |
|---|---|---|
| **Universal** | mice, and most likely the current keyboards, the Clutch Talon and the three-in-one dongle | [documented](universal.md); implemented in ngenuity-linux-cli for mice |
| `cloud_3_wireless` | Cloud III Wireless | not analysed |
| `stinger_3_wireless` | Cloud Stinger 3 Wireless | not analysed |
| `realtek` | Realtek-based audio devices | not analysed |
| Xbox GIP | Clutch Tachi | handled by NGENUITY's .NET code through Windows; not analysed |
| Audio engine | microphone and headset audio features | Windows audio service; on Linux this is ALSA / PipeWire territory |

In this NGENUITY version the universal protocol's audio requests only log
"Universal Audio Coming Soon", so audio devices do not use it for audio settings yet.

The universal protocol is self-describing: a device answers `10 01` with its category, USB IDs and
feature information, so the hub needs no product list for it. ngenuity-linux-cli uses the same
`10 01` reply to detect what is connected.
