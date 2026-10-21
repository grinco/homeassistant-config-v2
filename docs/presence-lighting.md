# Presence lighting (2026-10-07)

Magic Areas runs the room lights from presence. Until now it only ever switched them **off**: each
room's "turn on" groups (`overhead_lights` etc.) were empty, so occupancy changed nothing, while the
all-lights group still switched off when the room cleared.

## What turns lights on

A room's lights come on when Magic Areas reports it **occupied** and **dark**, and its *Light
control* switch is on. Only rooms with a real presence sensor take part — a room whose only
"presence" is a media player playing would light up whenever the TV is on.

| room | presence sensor | on-group | dark gate | state |
|---|---|---|---|---|
| Closet | Closet Motion (Zigbee motion) | Closet Light | none — windowless, lit at any hour | **on** (2026-10-11) |
| Corridor | Corridor Presence (mmWave, moved from the living room 2026-10-10) | **day:** entrance + corridor light; **night:** corridor light only | none — interior | **on**. Night = Magic Areas *sleep* state from `binary_sensor.lighting_night` = the alarm in Night mode (the house's one night, set by the schedule or by hand). The front-door camera PIR is EXCLUDED: it sees the doorstep |
| Living room | FP2 (zones) + kitchen motion, since 2026-10-11 | The Moon, Aurora (+ Beam Lights accent) | `living_room_bright` — the FP2 itself, real time (2026-10-20) | **on** |
| Kitchen | FP2 zones + kitchen motion | see the 2026-10-11 and 2026-10-14 sections | accent gate `kitchen_dark` = NOT `living_room_bright` | **on** |
| Hallway | Hallway Presence (FP300) | Hallway | `lighting_hallway_bright` — the FP300 lux (2026-10-20) | **on** |
| Guest room | Bebecam motion/person | — | — | not wired: a baby monitor must never switch a light on |

**The symptom of a room that is not set up:** Magic Areas switches its lights OFF when the room
clears but never ON. "On" needs the room's lights in *overhead_lights* with state *occupied*; an
empty list is the default. That is what the closet and corridor showed on 2026-10-11.

To add a room: put a presence sensor in its area, assign its lights to *overhead* (state
*occupied*) in the area's Magic Areas options, set its dark entity, turn on its *Light control*.

## Darkness: `binary_sensor.lighting_daylight`

Magic Areas treats a room as **dark around the clock** unless it is given a dark entity, so without
one the living room's lamps would come on at noon. `binary_sensor.lighting_daylight` is that
entity: `on` = bright enough, no lights.

- Source: the terrace's outdoor illuminance, against `input_number.lighting_dark_below_lux`
  (400 lx; the helper's minimum is 50, so a "never dark" 0 cannot be set). When that Zigbee
  sensor drops, the sun's elevation decides — **with its own hysteresis**: a dark room needs the
  sun above 12° to turn bright, a bright one stays bright down to 6°. Without it, a dark, occupied
  room whose sensor died at noon flipped straight to BRIGHT and lost its lamps (review 2026-10-07).
  No lux and no sun elevation at all reads as dark.
- **It is an OUTDOOR proxy, uncalibrated against the living room.** Drawn curtains or a dull
  north-facing room are dark indoors while the terrace reads bright; then presence will not light
  the lamps and BRIGHT will switch them off. Tune the threshold from experience; it is a house-wide
  helper. Do not reuse this entity for a room with very different windows without checking it.
- **Hysteresis is the point.** Magic Areas reacts to a room turning BRIGHT by switching an
  *occupied* room's lights off — with someone in it. So the sensor goes dark below the threshold but
  needs **twice** the threshold to come back bright; a cloud at dusk cannot flick the lamps.
- After a restart it starts on the dark side: the failure is a lamp left on, not one switched off.
- It is a template rather than a `threshold` helper or Magic Areas' own illuminance threshold
  because both need the lux sensor alive (no sun fallback), and the latter needs a light sensor in
  the room itself.

Tests: `tests/climate/cases.py` (*daylight:* cases straddle every edge, lux and sun, in both
directions; a missing threshold helper; no sun elevation) and `mutate.py` (lux hysteresis removed or
inverted, sun hysteresis removed, 0 lx treated as dead, no sun fallback, bright after a restart).

## Known behaviour

- A manual switch-off while the room is occupied is respected until the room next clears.
- At sunrise an occupied room's lamps switch off (BRIGHT). That is Magic Areas' design.
- Night walks through the living room switch the lamps on at their last brightness. If that is
  unwanted, a *sleep* entity and *sleep_lights* are the native fix.

## Day and night in the corridor (2026-10-11)

Two Magic Areas light groups: *overhead* = entrance light, state `occupied`; *task* = corridor
light, states `occupied` + `sleep`. Under `sleep` (a priority state) MA drops the non-priority
`occupied` match, so only the corridor light comes on at night. If night begins while someone is
there, the entrance light is switched off; at 06:00 it comes back on if the corridor is occupied.
Since 2026-10-11 the night is the ALARM'S night mode for the whole house (climate, lights,
Adaptive Lighting sleep); the schedule only moves the alarm at 22:00 and 06:00, and switching the
alarm by hand wins until the next edge. See climate-control-design.md v5.12.

## Kitchen (2026-10-11)

Kitchen Motion (motion + lux). **Kitchen Top** is the task light: on with motion at any light level.
**Gallery** (overhead) and **Beam Lights** (accent) only when the kitchen is dark. Magic Areas
cannot gate one group on darkness (a dark entity gates the whole room, and `dark` is not a group
state), so darkness enters as the *accent* state: `accent_entity` = `binary_sensor.kitchen_dark`, a
native `threshold` helper on the kitchen lux (on below 15 lx, off above 35 lx). Task = states
occupied + accented; overhead and accent = accented only. Accented is a priority state, so in the
dark all three are on; when it brightens, gallery and beam go off and the top stays.
- The lamps add only a few lux at the sensor (0–8 lx measured with all three on), well inside the
  20 lx hysteresis, so they cannot switch themselves off. Re-check after a sunny day's data.
- Light control is OFF by the operator until presence sensing arrives; a motion sensor clears on a
  person standing still at the counter. The Echo Dot playing also counts as presence here.

## Living room and kitchen, measured in the room (2026-10-11)

The living room now has an **Aqara FP2** (HomeKit): presence zones 1–4 in the living room, zones 5–6
in the kitchen (the space is open, with a bar in the middle), and its own light sensor. The kitchen
gained a second motion + light sensor at the dining table.

- **Living room darkness is measured in the room**, not outdoors: `sensor.living_room_light_level`
  (native `statistics`, 10-minute mean of the FP2 light level, which jumps 40–80 lx within seconds as
  people move) feeds `binary_sensor.living_room_bright` (native `threshold`: bright above 200 lx,
  dark below 100 lx; "Show as: Light", the only class Magic Areas accepts as a dark entity). Lamps
  come on only when the room is dark, and Magic Areas switches them off when daylight makes it bright.
- **The lamps cannot switch themselves off.** Measured 2026-10-11 12:22: both lamps off for 19 s and
  the FP2 reported no change at all — their contribution is below its reporting step, far inside the
  100 lx band.
- **Kitchen presence bleeds into the living room, on purpose** (operator, 2026-10-11: "so that the
  ambient lights stay on"): the living room's Magic Areas counts FP2 zones 5–6 (kitchen and work
  area, on the living-room device) and, via `include_entities`, both kitchen motion sensors. Someone
  at the bar, the worktop or the dining table keeps the living-room lamps on. One way only: the
  living room does not light the kitchen. The lamps still only come ON when the living room is dark.
- **Kitchen light level** = mean of both kitchen light sensors (native `min_max`); `binary_sensor.kitchen_dark`
  now reads it (dark below 15 lx, bright above 35 lx). The worktop sensor reads ~3x the dining one.
- `binary_sensor.lighting_daylight` (outdoor) is no longer used by any room; it stays, tested, for
  rooms without a light sensor of their own.
- The **FP300** presence sensor is paired but unnamed and unplaced — not in use yet, left alone.

### One darkness for the open space (2026-10-11, evening)

The operator: kitchen lit, living room dark, "despite it being essentially the same space —
separated by the bar", and "the current amount of light is already a little too dark".

- **Cause 1 — two sensors, two scales.** The living room judged darkness by the FP2 (100/200 lx), the
  kitchen by its corner sensors (15/35 lx). All report lux — it was not a unit problem — but they sit
  in different light: at noon the FP2 read ~290 lx while the kitchen sensors read ~50. Now ONE signal
  decides for both: the FP2's 10-minute mean (`sensor.living_room_light_level`), which sees both
  halves. `binary_sensor.living_room_bright` (bright above 300, dark below 150) and
  `binary_sensor.kitchen_dark` (its exact mirror) read it, so the two halves always agree. Thresholds
  raised from 100/200 at the operator's request. The kitchen corner sensors remain for presence and
  display; `sensor.kitchen_light_level` no longer drives anything.
- **Cause 2 — Magic Areas' manual latch.** Any light change Magic Areas did not make sets the room's
  groups to `controlling: false` until the room next EMPTIES. The lamp measurement at 12:22 (lamps
  off/on by hand) tripped it, and the open-plan room — TV, FP2 zones, kitchen bleed — never emptied,
  so at 17:08 the room went dark and nothing came on. **Never toggle a room's lights to test or
  measure while it is occupied**; the lamps were switched on by hand for the evening and the latch
  releases at the next empty room.
- Risk: the FP2 is now a single point of failure for open-space darkness. Unavailable reads as dark
  in the living room (lamps may come on) and as not-dark in the kitchen (gallery/beam stay off).

### Outdoors wins; worktop and kitchen motion switch the Workarea (2026-10-12)

*Outdoors-wins was removed on 2026-10-20 — see the last section.*

The operator: kitchen and living room "dark" while it was bright outside. The FP2 sits in the dim
half of the space (58–167 lx all morning against 16 000+ lx on the terrace), so a darkness judged by
the FP2 alone called a sunny noon dark.

- `binary_sensor.living_room_bright` and `binary_sensor.kitchen_dark` (the entities Magic Areas
  reads) are now template helpers over two inputs: outdoor `binary_sensor.lighting_daylight`
  (hysteretic) and the old FP2 thresholds, renamed `binary_sensor.open_space_indoor_bright` /
  `_dark`. Bright outside = bright inside, whatever the FP2 says; otherwise the FP2 decides, as
  before. Tested in tests/climate (`open space:` cases, prefix `Lighting`).
- Not covered on purpose: a sunny day behind closed curtains reads bright.
- **Workarea** (`light.h1ab2_2`, on/off): `automation.kitchen_workarea_on_with_worktop_presence`
  turns it on when FP2 zone 6 (worktop) or `binary_sensor.kitchen_motion_occupancy` goes on. Not the
  kitchen area state, the dining-table sensor or FP2 zone 5. Off stays with Magic Areas (task group).
  *Superseded 2026-10-14, see below: Workarea follows the counter only.*
  Not testable by the suite (actuation); the trigger entities were checked against live state.
- Room pages open with an **Occupancy** tile (Magic Areas sensor: state and time since), tap = more-info
  with the active sensors and history. Lint C23.

## Hallway (FP300), battery watchdog, lights left on (2026-10-12)

- **Hallway presence lighting.** The FP300 ("Hallway Presence", Aqara, Z2M) is the hallway's only presence
  sensor. Magic Areas: `overhead_lights` = `light.hallway`, state `occupied`, light control ON, no dark
  entity — lit at any hour, like the corridor (*a dark entity was added on 2026-10-20, see the last section*). A dark entity was deliberately not added: the sensor's
  lux is noisy (60–210 lx at noon) and sits near the bulb it would switch, so the lamp itself could
  read the room BRIGHT and switch it off under someone. **The bulb is on a wall switch.** With the switch
  off the bulb is `unavailable` and Home Assistant cannot light it; presence lighting only works while
  the switch is left ON (manual control then needs a battery button/dimmer, or a relay behind the switch).
- **`sensor.any_low_battery`**: lists every battery sensor under 20 % by entity id (state `none` when
  there is nothing to say; ids since 2026-10-20, issue #3, so Home shows each as a tile that opens
  it, and the watchdog's message turns them into names and levels). Phones (`mobile_app`) and the car (`volvo`) are skipped by
  integration, and the vacuums by device (every entity of a device that has a `vacuum.*`): they are
  charged, not replaced. *Audit 2026-10-20: the Roborock is also bridged over Matter, and that copy of
  its battery belongs to no `roborock` entry, so skipping it by integration missed it.* This is the
  only battery list: Home's Needs attention opens on it and renders it (lint C29). The binary
  `Any battery low` and the card's own copy (15 %, a `volvo` substring skip) were retired the same
  day, after a leak sensor at 15 % was named by this sensor and hidden on Home. The list stops before 240
  characters and ends `+N more`: Home Assistant rejects a longer state, and `unknown` would hide the note. `automation.battery_watchdog` notifies Vadim's phone at
  09:00 daily and the moment the first sensor drops under 20 %. An unavailable battery is a different
  alert and is NOT listed (a dead smoke/CO alarm battery reads unavailable today).
- **`sensor.lighting_left_on`**: entity ids of the lights still on, `none` otherwise; group lights
  (Home Assistant groups carry `entity_id`, Zigbee2MQTT groups `group_entities`) and the UniFi
  `*_led` indicators are skipped.
  `automation.lights_left_on_when_everyone_leaves`: `zone.home` below 1 for 10 minutes -> both adults'
  phones get "Still on: …" with a **Turn them off** button; the button is honoured for two hours and
  turns off whatever the sensor lists at that moment. Nothing is switched without the tap.
  *(2026-10-14: that automation was folded into House — everyone left,
  `automations/house-everyone-left.json`, which carries the same list in its one note. The battery
  watchdog is exported as `automations/battery-watchdog.json`.)*
- Not reachable by tests: the notifications and the button. Both roll-ups' expressions are covered in
  tests/climate (`battery:` and `left on:` cases, mutations in mutate.py); the automations were
  checked by rendering their message templates against live state, never by `automation.trigger`.

### The indoor level is a slider (2026-10-12)

*The slider stays; the 10-minute mean and the two indoor helpers were removed on 2026-10-20 — see the last section.*

The operator: changing a light level should not need a code change. The living-room and kitchen
darkness decision is now `binary_sensor.open_space_indoor_bright` / `_dark` (template helpers, with the
same entity ids the wrappers already read) judging the FP2's 10-minute mean against ONE number,
`input_number.lighting_indoor_dark_below_lux` (default 150): dark below it, bright above TWICE it, held
in between, exactly the outdoor rule. Both sliders are in the admin panel, System -> *Lighting levels*,
next to the live readings. A slider that is missing, unavailable or <= 0 falls back to 150 (a new
input_number starts at its minimum, 20). A dead FP2 reads as not bright and not dark, as before.
This replaced two native `threshold` helpers: those only take literal limits, so they cannot follow a
slider. The cost is two templates where there were two helpers; the band is no longer independent of
the slider. The old helpers' held state was lost in the swap: inside the band a first evaluation
starts dark / not-dark. The hallway has no darkness check and no slider.

## Zigbee groups, the counter, and a Magic Areas bug (2026-10-14)

- **Living Room Main and Gallery are Zigbee2MQTT groups** (ids 1 and 2), not Home Assistant groups.
  A Home Assistant group sends one command per bulb, so the bulbs switched one after another; a
  Zigbee group is one broadcast, so they switch together. Each took over the old entity id
  (`light.living_room_main`, `light.gallery`), so Magic Areas, Adaptive Lighting, the dashboards and
  Alexa needed no edits. The member bulbs are hidden.
- **Beam Lights belong to the living room** (operator: they hang between the two rooms and the
  living-room side is used more): living-room accent group, states occupied/extended. The kitchen's
  dark-only accent group is Kitchen Top alone.
- **Workarea follows the counter.** It left the kitchen task group; the counter automation turns it
  on with FP2 zone 6 or kitchen motion and off once both have been clear for 5 minutes.
- **Magic Areas 4.4.2 leaks listeners on reload.** Its light groups and presence sensor subscribe to
  area-state changes without registering the unsubscribe, so every reload (any options change, and
  every registry edit with `reload_on_registry_change`) left the previous objects running with their
  old configuration. The kitchen had five overhead groups, one of them still turning the gallery on
  by day after it had been set to dark-only. Fixed upstream (jseidl/magic-areas #635) but not yet
  released; the same two-line fix is applied locally and a restart cleared the leftovers. Do not
  re-download 4.4.2 from HACS: it would restore the bug.
- **A bulb switched off at the wall is not an alarm.** Wall-switched bulbs read `unavailable`;
  nothing alerts on that, by the operator's decision.

## The room decides: real-time darkness with a fallback (2026-10-20)

The operator: the upstairs hallway lit "even when it's a lot of sun outside and in the room", and the
living room "was very dark before the lights turned on". Asked to simplify the set-up and use
real-time data where there is any, with a fallback.

**Why the living room stayed dark.** It was occupied and the FP2 read 150 lx at 16:49 and about 50 lx
by 17:13 — dark by the room's own slider. The terrace still read 1469 lx, and the 2026-10-12 rule
"bright outside is bright inside" held the lamps off until the terrace fell below 400 lx at 17:40:57.
Fifty-one minutes in a dark room. The 10-minute mean of the FP2 would have added lag on top. The kitchen
motion sensors (which report light only on motion or at an interval) were not involved: they had not
fed the open space's darkness since 2026-10-11.

**One rule, used by every room that has a light sensor.** A template binary sensor, *Show as: Light*
(the only class Magic Areas accepts as a dark entity), on = bright:

- the room's own lux, as reported — no statistics in between;
- bright above TWICE the room's slider, dark below it, held in between;
- native `delay_off` 1 min: a dip has to last a minute before lamps come on. The FP2 dips for single
  seconds (83 lx for one second at 16:10 between readings of 220–260); the 10-minute mean used to
  absorb that, the delay now does, without the lag;
- native `delay_on` 5 min: Magic Areas switches an OCCUPIED room's lights off when it turns bright, so
  a passing sunbeam must not do that;
- the sensor dead or unknown -> outdoor `binary_sensor.lighting_daylight` decides. Outdoors is only
  the fallback now, never an override.

| room | dark entity | sensor | slider (default) |
|---|---|---|---|
| Living room | `binary_sensor.living_room_bright` | FP2 light level | `input_number.lighting_indoor_dark_below_lux` (150 -> bright above 300) |
| Kitchen | accent gate `binary_sensor.kitchen_dark` = NOT `living_room_bright` | — one decision for one open space | — |
| Hallway | `binary_sensor.lighting_hallway_bright` | FP300 illuminance | `input_number.lighting_hallway_dark_below_lux` (30 -> bright above 60) |
| Bedroom | `binary_sensor.lighting_daylight` | outdoor (the new air-quality sensor has no lux) | `input_number.lighting_dark_below_lux` |

**The hallway's 2026-10-12 objection, measured.** A dark entity was left out because the FP300 sits
near the bulb it switches. Measured: the lamp adds 10–20 lx at the sensor (06:27 0 -> 11 lx, 17:39
12 -> 32 lx), while the hallway reads 30–500 lx by day and the lamp had been switching on at 126–250
lx. With the band at twice the slider, the lamp alone cannot carry a dark hallway past the upper edge.
That only holds while the slider is at least 20 lx, so the template raises anything lower to 20 —
the floor is in the logic, not just in the helper's bounds.

**Removed:** `binary_sensor.open_space_indoor_bright` / `_dark` (folded into the two room sensors).
`sensor.living_room_light_level` (the 10-minute mean) and `sensor.kitchen_light_level` are no longer
read by anything; deleting them was left to the operator. The admin panel's *Lighting levels* section
shows the FP2 reading live and has the hallway slider and reading.

**Accepted:** a closed-curtain afternoon now reads dark in the living room (the FP2 sees the room as it
is), so the lamps come on behind drawn curtains — that is the point of measuring indoors. The open
space still has one light sensor; when it dies, outdoors decides for both halves.

Tests: `tests/climate/cases.py` — *open space:* and *hallway:* cases straddle both edges, the held band
in both directions, the slider moving the edge, a missing or too-low slider, the dead-sensor fallback
by day and by night, and the 17:40 case itself (FP2 80 lx, terrace bright -> dark). `mutate.py`
reintroduces outdoors-wins, the missing floor, no hysteresis, a dead sensor reading dark, an ignored
slider and a kitchen that stops mirroring; each is caught by a case failing on its value. The delays
are native helper options and are not reachable by the suite; they were read back from the live
config entries.

## Night starts at 21:00; the open space stays dark towards the bedroom (2026-10-21)

The operator moved `schedule.climate_night` to start at 21:00, trimmed what Magic Areas lights at
night, and asked for two things: no bedroom lights after nine, and less light reaching the bedroom
from the open space at night. The gallery is right in front of the bedroom's glass door; Aurora and
the kitchen top are strong enough to see from bed.

**Night is still the alarm.** At 21:00 the schedule moves the alarm to Night (from Home or Disarmed),
and `binary_sensor.lighting_night` follows the alarm, so a manual Home/Night switch moves the lights
and the heating together. Nothing about that changed.

**Bedroom.** The lamps (Aladdin, torchère) are accent lights on `occupied`, with `lighting_night` as
the sleep entity. `sleep` is a priority state in Magic Areas, so with the alarm in Night the bedroom's
`occupied` is ignored and the lamps never switch on; entering Night switches them off. With night now
starting at 21:00, that is "no bedroom lights after nine". The lamps came on at 21:13 on 2026-10-21
only because the alarm was still Home then.

**Kitchen: `accented` outranked night.** Magic Areas 4.4.2 has two priority states, `sleep` AND
`accented`. When either is present it drops `occupied`/`extended` but keeps every priority state a
group is assigned to. The kitchen's accent entity was `kitchen_dark`, so on a dark night the kitchen
was `sleep` + `accented`, and the gallery and the kitchen top (both assigned `accented`) stayed
eligible. Seen at 22:05 on 2026-10-21, with the alarm in Night: gallery, kitchen top and workarea all on.

Fix: a template binary sensor `binary_sensor.lighting_kitchen_evening` ("Lighting kitchen evening")
= `kitchen_dark` AND NOT `lighting_night`, now the kitchen's accent entity. At night the kitchen
is only `sleep`, so the gallery and the kitchen top drop out and switch off as `accented` is lost.
The workarea (task, `sleep` + `accented`) is the kitchen's one night light. A template, because
neither a native group nor a threshold can express "and not". It fails towards light: an
unavailable `lighting_night` reads as "not night".

**Living room.** Aurora and Beam are accent lights on `occupied` + `extended`, so they drop out at
night already. Only The Moon (sleep group: `occupied`, `sleep`, `extended`) lights at night. The
Moon was also in the accent group. When night started, the accent group turned it off while the sleep
group turned it on, and which one won depended on the order in which the event was handled. It is now only in the
sleep group. That changes nothing by day, because the sleep group is also assigned `occupied`.

Tests: `tests/climate/cases.py` *kitchen evening:* (dark by day, dark at night, bright);
`mutate.py` drops the night term and the dark term, and both are caught. Magic Areas' own priority
handling cannot be reached by the suite. It was read in `light.py` (`state_change_secondary`) and
checked against the live area state, which at 22:30 was `dark, sleep, clear` with no `accented`.
