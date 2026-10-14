# CLAUDE.md

`ngenuity-linux-cli` is a Linux command-line tool (`ngenuity`) for HyperX devices supported by the
Windows-only NGENUITY software, built by reverse-engineering NGENUITY 3.1.0. Start with
`README.md` (status, missing features, testing), `docs/protocol/universal.md` (protocol
specification) and `docs/devices/` (one page per device).

## Working rules

- **Never write to a device without asking first**, even live (profile slot 0) changes. Read-only
  queries are fine. Restore the user's settings after every write test.
- **Never send factory reset `12 01`.** Write the onboard profile (slot 1, `--save`) only when the
  user explicitly asks for that specific write.
- The test device is the user's own Pulsefire Haste 2 Wireless (dongle `03f0:0f98`, usually
  `/dev/hidraw4`). It sleeps after a few seconds idle: check `52 01` → `53 01 01` first and ask the
  user to move the mouse, or wait for `fb 0a 01`.
- Commit only when asked; never tag or push unless asked. Commit message: one short summary line,
  a blank line, then a bullet list of the changes per file, ending with the Co-Authored-By line.
- Never commit NGENUITY's files or anything derived from its binaries (`HyperX_NGENUITY_Installer.exe`,
  `extracted/`, `decompiled/`, `ghidra_targets/`, `hyperx.gpr`, `hyperx.rep/`). They stay untracked.
- USB captures record the whole bus, including the user's keyboard. Before committing a capture,
  filter it to the device's USB address (`tshark -r in.pcapng -Y "usb.device_address==N" -w out.pcapng`),
  keep the original in the git-ignored `captures/unfiltered/`, and name it
  `<device>_<NN>_<content>.pcapng`. The git history before commit `3dff292` contains unfiltered
  captures; the user chose not to rewrite it.

## Code

- uv project, src layout, package `src/ngenuity_linux_cli/`, Python ≥ 3.12, click CLI.
- Checks: `uv run ruff check`, `uv run ruff format --check`, `uv run mypy` (strict). All must pass.
- Fully typed code. No code comments or docstrings, except click command docstrings (they are the
  user documentation). Ruff selects ALL rules except `D`, `CPY`, `COM812`; avoid `noqa`
  (use named constants instead of magic numbers).
- Modules: `protocol.py` (universal protocol encoders/parsers), `device.py` (`UniversalDevice`
  hidraw transport), `devices.py` (model registry and interface discovery), `session.py`
  (detection and selection), `cli.py`, `buttons.py`, `lighting.py` (light-engine effects),
  `colors.py`.
- Every setting command reads the current value from the device, changes it, writes it and reads
  it back. Commands that get a `cmd+1` reply from the device must wait for it (`await_reply`)
  before sending the next packet, or the device drops packets over RF.
- New device models go into `MODELS` in `devices.py` (capabilities from NGENUITY's
  `decompiled/NGENUITY/HXN.Configurations.*/<Name>Configuration.cs`) plus a page in `docs/devices/`.

## Releases

Versions come from `vX.Y.Z` git tags (hatchling + hatch-vcs); other tags are ignored, including
the user's old `v1.0.0-pulsefire2-wireless-mouse` and `v2.0.0-ngenuity`. Pushing a `vX.Y.Z` tag
runs `.github/workflows/release.yml`: ruff, mypy, `uv build`, version check, `uv publish` to PyPI
through trusted publishing (GitHub environment `pypi`).

## Reverse-engineering setup

- `extracted/current/`: NGENUITY 3.1.0 app files. The hub is
  `Assets/Services/hxn-srv-communication-hub.exe`, the light engine
  `Assets/Services/hxn-srv-light-engine.exe`.
- `decompiled/`: ilspycmd output of the .NET assemblies (UI, FlatBuffers message types in
  `NGENUITY.Common/CommunicationHub/`, device configurations, light-engine messages).
- Ghidra project `hyperx.gpr` with both Rust binaries (copies in `ghidra_targets/`). GhidraMCP
  serves the program in the active CodeBrowser tab on port 8080; keep one CodeBrowser window and
  switch tabs. Without Ghidra, capstone (`uv run --with capstone python …`) works for scripted
  disassembly.
- Key hub addresses (image base `0x140000000`): request dispatcher `0x1400bf770`; report-ID table
  `0x14048bb70` and sub-command table `0x14048bbaa`, each read through its own index byte per
  handler (see `docs/protocol/universal.md` §3); key-assignment encoder `0x140154890`; FrameLight
  upload `0x140462320`. Light-engine strategy functions are listed in `docs/protocol/universal.md` §5.5.
- Captures: run NGENUITY in a VirtualBox Windows VM with the device passed through, and record on the
  host with `dumpcap -i usbmonN` (needs `modprobe usbmon` and the `50-usbmon-wireshark.rules` udev
  rule; the user is in the `wireshark` group). Change one setting per capture and note the times.
