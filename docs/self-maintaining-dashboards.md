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
| a temperature, humidity, light-level, CO₂, particulate, VOC or pressure sensor in a room | its room page → *Environment*, as a tile with a 24 h trend. Label it `not_on_room_pages` if a resolved room sensor already reports the same reading |
| a leak, smoke, gas or CO sensor anywhere | Home → *Needs attention* the moment it trips (via `binary_sensor.any_safety_alarm`, lint C21), named "Smoke — Corridor"; the room card turns red |
| a heating zone (Tado *Zone*) or a water heater | Climate → *Heating & hot water*: zones with target and modes, hot water with its modes, the zone's heating %. Radiator valves (`_trv_`) are listed status-only — the climate automation reads their setpoints and never commands them. Hot water also gets a tile in Home → *Quick actions* |
| a camera in a room | Security → Cameras (live snapshot, tap for the stream). A **battery** camera goes in the section's `exclude` list, as the front door does: the snapshot refreshes every few seconds while the tab is open |
| a motion / door / window / leak / smoke / CO sensor in a room | Security → Sensors (two columns). A device with several (a camera's motion / person / animal) is told apart by its own entity name |
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
- **Environment (2026-10-07):** every room page generates a tile for each sensor in its area whose
  device class is environmental (temperature, humidity, illuminance, CO₂, CO, PM1/2.5/10, VOC, AQI,
  pressure, NO₂, ozone, sound pressure), plus the Zigbee VOC index, which has no class and is
  matched by its `_voc_index` id suffix. Resolved room sensors (label `on_room_page`) show as plain
  *Temperature* / *Humidity* / *CO₂*; device sensors show their reading first, then the device.
  Before this a room page showed only the three resolved readings, as small heading badges, so a
  terrace light level, a purifier's PM2.5 and a bedroom's PM2.5/VOC were on no page (lint C18).
  Rule order matters: with `unique: entity` the first matching rule wins, so the labelled,
  fixed-name rules come before the generic one.
- **Native before template.** A room with one instrument per reading gets Magic Areas'
  *aggregates* (temperature, humidity; min 1 entity) labelled `on_room_page` — the bathroom and
  shower do. An aggregate is a mean of every sensor of its class in the area, so lint **C20**
  requires exactly one: a second thermometer in that room means it needs a resolved template.
  Rooms the climate automation acts on keep their template chains: an aggregate is a plain MEAN of
  every sensor of a class in the area, which would average the AC's own probe and a TRV on a hot
  radiator into the reading the automation regulates.
- **Room card heating/cooling:** taken from what ANY climate device in the room is *doing*
  (`hvac_action`), falling back to its mode only for devices that report no action (the Samsung
  ACs). A Tado zone sits in mode `auto` permanently, so its mode says nothing. Tested by executing
  the card's own JavaScript: `tests/dashboards/roomcard.py`.
  A device that reports `idle` is believed, even in mode `cool`. A heating zone and a cooling AC
  at once read **Heating + cooling** in amber: by design the boiler baseline and the AC never fight
  (climate design M6), so that is a fault to see, not a state to normalise (review 2026-10-09).
- **Climate → Temperature / Humidity (2026-10-11):** generated — every sensor labelled
  `on_room_page` of that class in an area on a floor, named after its area, one colour per room
  shared by the tiles and the 24 h graph (lint C13 now covers both sections). Use `floor_id(entity)`,
  not `floor_id(area_id)`: the area-id form resolved area `bedroom` to the *name* of another area,
  "Bedroom", and dropped or misfiled rooms.
- **One night (lint C22):** dashboards compute night exactly as the climate loop does — the alarm in
  `armed_night`, the schedule only while the alarm itself is unavailable.
- **Lights:** Magic Areas makes a group per light category as well as `_all_lights`; room pages and
  the Home room card use only `_all_lights` (lint C17, C19).
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
