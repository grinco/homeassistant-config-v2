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
| `on_home_page` | entity | pin it to Home → *Around the house* (sensors get a 7-day trend, buttons press on tap). The cat toilet's visits, weight and *Clean litter box now* carry it |

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

## The family Home (2026-09-25)

Designed for everyone who picks up a phone in this house — grandparents, guests, children — and
rendered at phone and desktop width before it shipped (`tests/dashboards/render.py`).

- **One tab for everyone.** Climate, Energy, Appliances and Security are visible to the two adult
  accounts only (view `visible:`); guests, kids and anyone new see Home and the room pages. Add a
  user to those views' `visible` list to give them the detail tabs.
- **Home** = greeting, date and the outdoor reading in words; *Needs attention* only when something
  does; a **room card** per area, by floor (2 across on phones, 4 on wide screens — one generator
  per width, lint C9 requires every floor to carry both); **Quick actions** (all lights off, Ask,
  alarm, vacuum); the weather forecast; *Now playing* only while something plays.
- **Room card** (`vg_room_card`): big name, the room's resolved temperature and humidity (found by
  the `on_room_page` label, never by entity id), a plain-words status line (lights, heating /
  cooling, someone here, oven on, window open), a round light button when the room has lights, and
  a red border and headline for leak, smoke, gas or CO. Tapping it opens the room.
- **Room page**: light tiles with a brightness slider; the climate heading carries the readings;
  the room's **comfort controls** (day and night temperature with − / +, automatic climate, air
  filter) come next — they are what the climate automation reads, so changing the unit directly is
  left to its tile's more-info dialog; then fans, blinds & locks, media, labelled extras, and a
  low-key Automation row.
- Duplicate media integrations of one device (Cast / HomeKit / HEOS twins) carry
  `not_on_room_pages`, which also keeps them out of *Now playing*.

## Rendering

`python3 tests/dashboards/render.py out.png /lovelace/home 390` renders any page as the guest user
(token in `~/guest.key`, gitignored by living outside the repo) at any width, full page, and prints
broken cards and console errors. It needs `pip install playwright` and
`python -m playwright install chromium-headless-shell`. The ha-mcp screenshot beta (Puppet add-on,
no host port) is the fallback; it cannot render the admin panel, because the guest is not an admin.

## auto-entities gotcha (lint C16)

A rule's `domain` (or any matcher) must be a string or a `/regex/` — **a list matches nothing,
silently**. The labelled-extras block on every room page used a list from its creation until
2026-09-25, so no labelled switch ever appeared; found when the cat toilet's auto-clean switch
did not. Labelled entities also bypass the `entity_category` exclusion (the label is the opt-in),
which is why Tuya's config-category *Clean now* button and *Auto clean* switch now show.

## Theme: Material You (2026-09-25)

The layout is unchanged; only the look is. HACS installs *Material You Theme* and *Material You
Utilities* (loaded through `frontend.extra_module_url`). The theme is the default for light
and dark. The palette is generated in the browser from a seed colour, so every card that uses
theme variables follows it without an edit.

- Settings are helpers named `<domain>.material_you_<setting>` (house-wide; a per-user suffix
  overrides): `input_text.material_you_base_color` = `#D08A2E` (warm amber, matching the
  lamp-on accent the room cards already hard-code), `input_select.material_you_spec` = `2025`.
- **Keep the spec at 2025.** With `2021`, utilities 2.1.25/2.1.26 threw
  `RangeError: Maximum call stack size exceeded` in `toneDeltaPair` and silently fell back to
  the stock blue palette. There was no visible error, only the wrong colours.
- The theme turns the view tabs into a bottom navigation bar. Full-page renders show it
  floating mid-page because it is `position: fixed`. That comes from the screenshot, not a
  layout bug.
- One device often has an entity from each of several integrations (Android TV Remote, Cast,
  Music Assistant, Denon). Keep the one with real controls on the room page and label the
  others `not_on_room_pages`.
