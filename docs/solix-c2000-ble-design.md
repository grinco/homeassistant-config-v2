# Anker SOLIX C2000 Gen 2 — local (cloud-free) control

This is the design record for monitoring and controlling the Anker SOLIX C2000
Gen 2 (A1783) power station from Home Assistant **without the Anker cloud**. It
explains why the obvious path (Modbus TCP) does not work on this unit, the BLE
approach that does, and how it is wired through the house's ESPHome Bluetooth
proxies.

The integration code lives in two forks, not in this repository:

- `grinco/HaSolixBLE` — the Home Assistant integration (install via HACS).
- `grinco/SolixBLE` — the Python BLE library it depends on.

Both add C2000 Gen 2 support on top of the upstream `flip-dots` projects, with
upstream pull requests open (`flip-dots/SolixBLE#94`, `flip-dots/HaSolixBLE#57`).

## Why not Modbus TCP

The C2000 firmware contains a Modbus-TCP server, but it is not usable in practice:

- The command that enables it is accepted **only over an authenticated local BLE
  channel** — the cloud/MQTT path returns read-only diagnostics, never the set.
- The comms module is **single-radio**: Bluetooth and Wi-Fi are mutually
  exclusive, never both at once.
- Enabling the server only creates it **in RAM**, immediately, with no
  persistence and no "start on boot / on Wi-Fi up" path.

Put together, the server can only ever be created while the unit is in BLE mode
(Wi-Fi down, no live network interface), so it can never bind to a reachable
address. This matches Anker declining the Modbus feature request upstream.

## The approach that works: BLE control via the proxy mesh

The device speaks a full local BLE protocol (ECDH key agreement + AES-GCM
session) that the community `SolixBLE` library implements. We reuse it:

- The C2000 Gen 2 is **behaviourally identical to the C1000 Gen 2** over BLE
  (same framing, telemetry and AC/DC control commands), so our fork maps it to
  the existing C1000 Gen 2 handling.
- Home Assistant reaches the unit through the **existing ESPHome Bluetooth
  proxies** — no USB dongle, and the host's own (non-functional) on-board
  Bluetooth is not involved. The proxy in the same room as the unit carries the
  connection.
- The integration runs on HA's Bluetooth stack, so the proxy routing is
  automatic.

### Operating mode: BLE-only

Because the unit is single-radio, holding the BLE control session means the unit
stays **off Wi-Fi**. That is the intended steady state here (local control, no
cloud dependency):

- The unit is kept off Wi-Fi at the router. With no network it falls into BLE
  mode and advertises; HA discovers it (service UUID `ff09`) and connects.
- Its Wi-Fi credentials are **left in place** (not wiped), so it can be briefly
  returned to Wi-Fi for firmware updates — see below.
- First connection performs a one-time **bind**: the unit asks for a physical
  confirmation, which is a single press of its power button. After that the
  client is bonded and reconnects need no button.

## Setup

1. Install `grinco/HaSolixBLE` as a HACS custom integration and restart HA.
2. Take the unit off Wi-Fi (block it at the router) so it advertises over BLE.
3. HA discovers it under Settings → Devices & Services; choose **Configure** and
   select the model **"C2000(X) Gen 2"**.
4. On first connect, press the unit's power button once when it waits to confirm.

## Entities

- **Sensors:** battery %, AC input / output power, DC / solar / USB port power and
  status, temperature, charge limits.
- **Switches:** AC output, DC output.

The USB ports are **not** software-controllable (the Anker app cannot toggle them
either), so no USB switch is offered. A "battery health" reading is suppressed on
this model because the byte the C1000 Gen 2 uses for health is not a health
percentage on the A1783 (it reads an out-of-range value).

## Firmware updates (controlled Wi-Fi fallback)

Updates download over Wi-Fi/cloud, which the unit cannot do while a BLE session
is held. The maintenance cycle:

1. Disable / disconnect the HA BLE session (frees the single radio).
2. Unblock the unit on Wi-Fi; it rejoins and performs its normal cloud update.
3. When done, block Wi-Fi again and let HA reconnect over BLE.

This can be automated with the router/UniFi integration driving the block.

## Known limitations and backlog

- **Settings not yet exposed.** The unit has app-configurable settings
  (charge/discharge limits — currently 20–80 %, AC/DC power-saving modes, screen
  brightness/timeout/saver, device timeout, grid-outage alert, output-memory
  switch). Surfacing these as HA entities needs each setting's BLE command
  identified first, which requires a probing session with the integration
  temporarily disabled (single BLE slot).
- **Icon.** An original integration icon ships in the fork; displaying it in the
  HA UI needs a submission to the `home-assistant/brands` repository.
- The reverse-engineered telemetry field map is documented in the `grinco/SolixBLE`
  fork (`docs/c2000_gen2_tlvs.md`).

## Notes for exports / privacy

This document intentionally contains no addresses, no device serial/MAC, no IP
addresses, and no credentials or proxy keys. The Anker account credentials and
the proxy API keys used during development were kept out of this repository.
