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
| Living room | none since the mmWave moved — only TV/Shield media players | The Moon, Aurora | `lighting_daylight` | waiting for a new presence sensor (operator, 2026-10-11). Until it arrives, playing the TV after dark lights the lamps and they go off ~1 min after playback stops |
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
  Not testable by the suite (actuation); the trigger entities were checked against live state.
- Room pages open with an **Occupancy** tile (Magic Areas sensor: state and time since), tap = more-info
  with the active sensors and history. Lint C23.
