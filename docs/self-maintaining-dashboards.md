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
| a temperature, humidity, light-level, CO₂, particulate, VOC or pressure sensor in a room | its room page → *Environment*, as a tile with a 24 h trend. Label it `not_on_room_pages` if it is the probe a resolved room sensor reads first, or an appliance's own probe (AC, TRV, purifier, oven). A probe somewhere else in the room stays shown even when it feeds the resolved sensor as a fallback (lint C33) |
| a leak, smoke, gas or CO sensor anywhere | Home → *Needs attention* the moment it trips (via `binary_sensor.any_safety_alarm`, lint C21), named "Smoke — Corridor"; the room card turns red. A leak sensor also gets a block in admin **Water & Outdoors → Water alarm**: state, battery, battery-low and any device setting (alert behaviour) |
| a heating zone (Tado *Zone*) or a water heater | Climate → *Heating & hot water*: zones with target and modes, hot water with its modes (the zone's heating % graph was dropped 2026-11-13: the tile already says Heating or Idle). Radiator valves (`_trv_`) are listed status-only — the climate automation reads their setpoints and never commands them. Hot water also gets a tile in Home → *Quick actions* |
| a camera in a room | Security → Cameras (live snapshot, tap for the stream). A **battery** camera goes in the section's `exclude` list, as the front door does: the snapshot refreshes every few seconds while the tab is open |
| a motion / door / window / leak / smoke / CO sensor in a room | Security → Sensors (two columns). A device with several (a camera's motion / person / animal) is told apart by its own entity name |
| a person | Security → Presence, and admin → Phones |

The one step Home Assistant does not allow to be generated: adding a new plug to the built-in
**Energy dashboard** (Settings → Dashboards → Energy → Individual devices). `tests/climate/wiring.py` fails
until it is done (and when a meter there no longer exists), and the energy digest's copy of the list
must then be updated to match. A plug that is gone for good is deleted (or, for Tuya, disabled) so it
leaves the generated lists too.

The generated graphs chart only entities reading a number now (lint C36): mini-graph-card draws
nothing until every entity it charts has a point in its window, so one plug offline for a day used
to leave the whole Energy socket graph on its loading spinner. That per-plug graph has since been
retired in favour of the socket total (a registry-walking helper, which C13 allows in the generated
Sockets section); the Climate graphs keep the guard. A graph with more than one line keeps its
legend on (lint C37), or its header names only the first line.

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
  pressure, NO₂, ozone, sound pressure), plus the Zigbee VOC index and the Philips allergen index,
  which have no class and are matched by their `_voc_index` / `_allergen_index` id suffix.
  Tiles show the reading's own name only (lint C38: at most 14 characters, unique in the room);
  a second reading of the same kind in a room gets a short registry name saying where it is
  (*Desk temp.*, *Wall humidity*, *Purifier PM2.5*, *Dining lux*) - name a new one the same way.
  Resolved room sensors (label `on_room_page`) show as plain
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
- **Security → Sensors (2026-10-31):** grouped by room, a subtitle per area and its sensors under it.
  A sensor is named for what it is (Motion, Leak, Window, Smoke, CO); only when a room has two of
  a kind does the device name decide (Entrance Door, Entrance PIR, Tamper), with the room's own
  name and words like *zone*, *open*, *presence* stripped. A Paradox zone that is its room's only
  alarm zone reads *Alarm zone*. `tests/dashboards/security_names.py` renders the live generator
  and fails on a duplicate name within a room, a name repeating its room, or an ungrouped list:
  the flat list had three tiles all called *Corridor zone open*.
- **One night (lint C22):** dashboards compute night exactly as the climate loop does — the alarm in
  `armed_night`, the schedule only while the alarm itself is unavailable.
- **Climate guides sit behind an (i) (lint C39, 2026-11-13).** On Climate and Climate — advanced a
  heading is a name of at most 22 characters, and status lines state facts only ("Isolated: Office",
  "Manual: Bedroom (until 14:00)"). Each section's explanation is a markdown `<details>` whose
  `<summary>` is the `mdi:information-outline` icon: closed by default, per viewer, no helper, no
  popup integration. The settings gear is a button badge on *Automatic climate*. The five
  manual-until stamps, the away-since stamp and the breaker counters' − / reset / + buttons are gone:
  the status lines already name an active hold or a tripped unit, and the breaker clears itself.
- **Climate — advanced is compact (lint C41, 2026-11-13).** Two sections, house-wide and per room, so
  a wide screen fills one row. Each room is its heading plus Day | Night: the Auto, Filter and
  Warm-up switches are tap-to-toggle heading badges, coloured when on (names only, so all three fit
  beside the room name at 390 px). No breaker counters: the Circuit breaker line names a tripped
  unit. *Safety limits always* opens its dialog on tap rather than toggling, so one stray tap cannot
  turn safety off. 3,859 → 1,602 px at 1280; 4,013 → 2,952 px on a phone.
- **Floors side by side, collapsible, three across (lint C44, 2026-11-13).** Home shows each floor's
  room cards in a section of its own (Downstairs, Upstairs), placed together after Weather and Needs
  attention, so from two columns up they sit side by side. Each floor is an `expander-card`
  (MelleD/lovelace-expander-card, Marketplace) whose title card is the floor heading: tap it to fold
  the floor; `storage-id` makes each phone remember its own choice. Rooms are three across; the room
  card adapts to its own width with a CSS container query (`extra_styles`), so below 170 px the icon
  and lamp shrink, humidity hides and the status line clips to one line. The upstairs rooms had begun
  two screens down on a phone. Floor jump buttons were tried and dropped (operator). C10 and C13 find
  the floor generators inside the expander (`sec_heading`, `sec_cards`).
- **Appliances is a glance (lint C43, 2026-11-13).** Three sections, one card style (the one-row
  stat pill). *Kitchen* is one row of three compact cards (a grid card, so it stays three across
  on a phone; template `vg_kitchen`): a 64px sketch of the real model that glows or bubbles while it
  runs, the state, and a detail line: while a program runs, the time left and progress (a
  delayed start says when it will be done); otherwise cavity temperature, program and door; and a
  set kitchen timer (the oven's and cooktop's alarm clock) at any time. Tested by executing the
  card's own JavaScript: `tests/dashboards/kitchencard.py`. They are watched, never driven from Home
  Assistant (operator). No program picker, no Pause/Resume/Stop.
  *Vacuum*: its commands inline on one row, status, battery, room, suction. *Car*: the lock
  inline, doors and windows, location, range, the remote. No settings (switches, numbers,
  connectivity, the vacuum map: they live on each device's page) and no badge row (it repeated
  each state). 3,400 → ~800 px on a phone.
- **The Energy tab names each entity once (lint C42, 2026-11-13).** No view badges (AC load, socket
  load and spot price were each also a graph right below), no load badge on the Sockets heading, and
  no statistics-graph: the 14-day modelled-lights chart went, since Home Assistant's own Energy panel
  keeps that history; *Lights (modelled)* now sits under the AC graph in *Load now*. *Electricity
  now* reads the hour-rank sensor and colours itself from the price, so it no longer repeats the
  price graph's entity. 1,595 → ~1,100 px at 1280; 3,098 → 2,626 px on a phone.
- **The Climate tab shows a reading once (lint C40, 2026-11-13).** No forecast (Home's weather card
  has it), no day/night alarm control (Home and Climate — advanced), no hand-placed copy of a reading
  the Temperature/Humidity generators already list, no Tado heating % graphs. The Floors section keeps
  its four numbers, not its graphs: the all-rooms and Outside graphs chart the same data. C40 does not
  see that last cut; a phone render does (7,339 → 5,501 px).
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
  overrides): `input_text.material_you_base_color` = `#1C7ED6` (EaseIT Blue, brand manual v1.2;
  until 2026-10-12 it was the warm amber `#D08A2E`), `input_select.material_you_spec` = `2025`.
  The seed drives the whole palette, light and dark, so it is the only brand colour the theme
  accepts. What it does NOT accept: Paper `#F6F4EF` / Navy `#101826` as exact surfaces (Material
  You derives surfaces from the seed, so they come out faintly blue), and Space Grotesk / Manrope
  (the theme sets its own font stack). Signal Green is deliberately not used as a fill. The amber of
  a lit room and the orange/blue of heating and cooling are functional colours the cards hard-code;
  they are not part of the brand palette and stay.
- **Keep the spec at 2025.** With `2021`, utilities 2.1.25/2.1.26 threw
  `RangeError: Maximum call stack size exceeded` in `toneDeltaPair` and silently fell back to
  the stock blue palette. There was no visible error, only the wrong colours.
- The theme turns the view tabs into a bottom navigation bar. Full-page renders show it
  floating mid-page because it is `position: fixed`. That comes from the screenshot, not a
  layout bug.
- One device often has an entity from each of several integrations (Android TV Remote, Cast,
  Music Assistant, Denon). Keep the one with real controls on the room page and label the
  others `not_on_room_pages`.

## One layout at every width (2026-10-12)

Rendered at 390 / 820 / 1280 px (`tests/dashboards/render.py`), three things differed by width:

- **Room pages** were one section: a 400 px strip centred on a tablet or laptop. They are now two
  (controls and climate | environment, media, extras), so two columns fill from ~800 px (lint C24).
- **Home room tiles** switched layout at 1024 px, so a tablet got the phone's two tiles per row,
  each stretched to 300 px. The break is now 600 px: two per row on a phone, four from a tablet up
  (lint C25).
- **Main tabs use three columns** (`max_columns: 3`, lint C26). The frontend fits columns of 320 to
  500 px, so 1280 px holds three and 1024 px (a tablet in landscape) holds two; with `max_columns: 4`
  a fourth, empty column was reserved. A section is placed after the previous one, and a tall
  section beside a short one leaves a hole under the short one that `dense_section_placement` does
  NOT fill (rows are as tall as the tallest neighbour). So balance by hand: put sections of similar
  height in the same row, and merge small ones under a short one. Climate is Auto climate + Floors |
  Heating | Outside, then Indoor air | Temperature | Humidity; Home is Rooms (2) | Quick actions, then
  three singles. Climate's Outside section was split at *Air quality — indoors* for this.
- Left alone: the *Environment* heading on a room page is a grid title, larger than the heading
  cards above it.

## Room tiles and their gestures (2026-09-25)

The Home room tiles are one button-card template, `vg_room_card`
(`lovelace-dashboards/button-card-templates.yaml`). Gestures:

- **Tap the card**: open the room's page.
- **Tap the 46 px lamp button**: if anything in the room is lit, turn the room's lights off;
  otherwise on. It uses `light.turn_off` / `light.turn_on` with `target: area_id`, so it needs no
  group and works from the first light. It is lit amber while the room's lights are on.
- **No hold, no double tap.** A long press is invisible, and the family Home must be usable by
  elderly parents, guests and children. The card opens the room, as a tile does everywhere; the
  lamp is a separate button that shows what it does.
- **Trade-off, deliberate:** the lamp turns the whole room off or on, never one light. In a room
  with one lamp on and one off, a tap means "all off", as the old script did.
- The status line does not count lights (2026-10-20, issue #5): on a phone "3 lights on" pushed
  "Someone here" off the card, and the lamp button already shows the lights. Locked by
  `tests/dashboards/roomcard.py`.
- Presence is said both ways (2026-11-13): "Someone here" or "No one here", but only in a room
  whose Magic Areas occupancy entity lists at least one `binary_sensor` in `presence_sensors`.
  Magic Areas makes that entity in every room, sensor or not, and counts speakers and TVs as
  presence; without a real sensor behind it, "No one here" would be a guess, so the card says
  nothing. An occupancy entity that is unavailable or unknown also says nothing. Before this, only occupied rooms said anything, and an empty room looked the same as
  one that cannot tell. Locked by `tests/dashboards/roomcard.py`.

The 2026-09 report that a Kids room tile opened the AC more-info dialog was never proven. The
likely cause was a `perform-action` that did not dispatch, so the card fell back to `more-info` on
the AC entity. The rewrite removes the question: every tap is now `toggle` or `none`. Nothing here
is covered by `tests/climate/`, which is an oracle for the climate loop only. It was verified by
rendering each tile's templates against live state (all twelve) and one real actuation.

## Open items carried from the retired surfacing record (2026-09-23)

- **Both SwitchBot meters were exposed twice**, over BLE and over Matter. The resolved climate
  template read BLE first and fell back to Matter, so the duplicate was load-bearing. The Matter
  bridge was decommissioned on 2026-10-22, so the Matter half is gone; check the BLE-only fallback
  before tidying anything about it.
- **`golemio` and `transit_departures` had produced no entities**, pending a restart. Not
  re-checked in the 2026-11-07 merge.
- **Corridor template sensors emit `''`** when the purifier is unreachable. Open; see
  `docs/climate-control-design.md` §12.
