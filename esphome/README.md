# ESPHome devices

Unlike everything else in this repository, **these files are deployable as-is.** They are
verbatim copies of what runs on the instance, not sanitised snapshots — they contain no
secrets to sanitise, because every secret is a `!secret` reference.

## Deploying

1. Copy the `.yaml` files into the ESPHome app's config directory
   (`/config/esphome/` as the app sees it).
2. Create `secrets.yaml` beside them from `secrets.yaml.example` and fill it in.
3. Install from the ESPHome dashboard.

**If you are restoring an existing device, reuse its existing API encryption key** rather than
generating a new one — Home Assistant stores the key per device, and a new one means removing
and re-adding the device.

## The devices

| file | what it is |
|---|---|
| `lr-bt-proxy.yaml` | Bluetooth proxy. Three rooms read their SwitchBot meters through it |
| `geiger-counter-ble-proxy.yaml` | Bluetooth proxy **and** a J305 Geiger-Müller tube on GPIO13 |

Both use the upstream `esphome/bluetooth-proxies` package, so the proxy half is not configured
here — only what is added on top.

Installing either takes that proxy offline for the duration of the flash. For
`geiger-counter-ble-proxy` that matters more than it looks: the living room, office and Kids
room 1 resolve their temperature through BLE first, and fall back to the Matter bridge while it
is down. See `docs/climate-control-design.md`.

## The Geiger counter

`docs/radiation-monitoring-design.md` has the full reasoning. The short version:

- It publishes **counts per minute only**. Converting to µSv/h needs a per-tube sensitivity
  factor, which lives in a Home Assistant helper so that confirming a tube is a slider move
  rather than a reflash — and so the count history survives changing it.
- `use_pcnt: false` and `internal_filter: 180us` are copied from a configuration known to work
  on this hardware. The hardware pulse counter cannot do a filter above 12.8 µs, and counted
  nothing here.
