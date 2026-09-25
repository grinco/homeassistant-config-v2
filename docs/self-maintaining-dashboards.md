# Self-maintaining dashboards (2026-09-25)

Adding a device should not need a dashboard edit. Everything that lists devices is generated at
render time from the registry; curation is done with **labels in the Home Assistant UI**, never by
adding or removing cards. `tests/dashboards/lint.py` enforces it (C13–C15).

## What happens when you add…

| you add | what appears, with no edit |
|---|---|
| a light, AC, fan, blind, lock or speaker to a room | its room page |
| any other entity you want on a room page | label it **On room page** |
| a metered plug | Energy: graph, meter, kWh charts, *Socket power total*. Mark its switch *Show as: Outlet* — the admin **Devices → To do** list reminds you until you do |
| a battery device | admin **Devices → Batteries** |
| a device with no room yet | admin **Devices → To do**, linked to its device page |
| a new area on a floor | a Home tile; it opens Home Assistant's own area page until a styled page is added |
| a motion / door / window / leak sensor in a room | Security → Sensors |
| a person | Security → Presence, and admin → Phones |

The one step Home Assistant does not allow to be generated: adding a new plug to the built-in
**Energy dashboard** (Settings → Dashboards → Energy → Individual devices).

## Labels

| label | on | meaning |
|---|---|---|
| `on_room_page` | entity | show it on its room page (anything beyond lights/climate/fans/covers/locks/media). The resolved `sensor.climate_*` readings carry it and show as badges under *Climate* |
| `not_on_room_pages` | entity | keep a default-domain entity off its room page (e.g. the members of a light group) |
| `no_area_needed` | device | a device with no room by nature (phone, cloud account, network gear); keeps it off *To do* |
| `offline_ok` | device | a device that is allowed to be unresponsive; keeps it off the health lists |

## Rules the generators use

- **Metered socket:** a device with a switch and its own power sensor (not Powercalc) and no climate
  entity. Its main switch is the shortest switch id on the device. Outlet-class switches that are not
  a main switch are listed as *Outlets without metering*.
- **Room page:** one skeleton for every room, with only the area id different (C14). Lights, climate
  (+ labelled temperature/humidity/CO₂ badges), air, blinds & locks, media, labelled extras, and a
  low-priority *Automation* row (Magic Areas light control and presence).
- **Home tiles:** one `auto-entities` per floor; a `rooms` map in the card config carries only the
  curated name, icon, page and `special` hook per area.
- Curated names, icons and colours for sockets and rooms live as structured data on the generating
  card (`sockets`, `outlets`, `rooms`), which the Jinja reads as `config`. Missing keys fall back to
  the registry name and a default icon.
