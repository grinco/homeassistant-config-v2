# Mould risk and the frost night target: design

Operator request, 2026-11-24: watch for mould, and stop a night setback from chilling a cold wall
in frost. Measured inputs only: room temperature and humidity (`sensor.climate_temp_<room>`,
`sensor.climate_humidity_<room>`), the measured outdoor temperature, and the hourly forecast.

## The wall model

Mould grows on a surface that stays above 80 % RH for hours (DIN 4108-2 uses the same 80 %). The
surface is colder than the air: `θsi = θe + (θi − θe) / f`, where `f = 1 / fRsi`. An unknown wall is
taken as fRsi 0.7 (`f = 1.43`); the kid 1 room, the building's corner under a sloped roof with the
least sun, as fRsi 0.6 (`f = 1.67`). Both are assumptions until a probe on the corner measures one.
Surface RH is the room's vapour pressure over the saturation pressure at `θsi` (Magnus).

## Mould figures

`sensor.climate_mould_<room>`: Home Assistant's Mould Indicator helper for the living room, office,
corridor, bedroom and both kids' rooms, with the factors above. The **bathroom** is a template with
the same physics. A helper inherits the device of the sensor it reads; the bathroom's sensor sits in a
Magic Areas room, so Magic Areas would average a wall humidity into the room's air humidity (the
dashboard lint caught it before it shipped). Cases pin the template against the helper's own reading.

The **corridor** is watch-only: it has a mould figure and can push, but no radiator or AC target to
raise. A corridor push is a prompt to air it and check the litter-box corner, not an automatic remedy.

**Push** (`automations/climate-mould-risk.json`): a figure above 80 % for 6 hours, once per crossing;
a return from `unavailable` is not a crossing. **Climate view**, section *Mould risk*: one meter per
room, the worst room in words, and the rooms whose night target is raised.

`binary_sensor.climate_health_risk` (indoor air humidity) is older and stays: it judges the air,
these judge the wall.

## Frost night target

`sensor.climate_night_target_<room>` replaces `input_number.climate_target_night_<room>` in both
consumers (`Climate — maintain per-room targets` and `Climate — radiators`, rooms lists and
triggers). The operator still sets the input_number; the sensor is

```
night = max(operator night, min(day target, ceil½(required)))
required = te + f · (θsi(80 %) − te)        te = min(measured outdoor, coldest of next 12 h)
```

so a room is raised only as far as its wall needs at the coldest hour ahead, never above its day
target, and an operator night set above the day target is never lowered. A missing room reading or
both outdoor readings missing gives the operator's night; a missing night target gives `None`, and the
consumers keep their own fallback (19 °C for a radiator, 21 °C in the AC loop), exactly as when the
input_number itself was missing; cases pin both (review #55 F2). Template sensors render during setup,
before the start event the consumers trigger on, so a restart does not see a blank target.

**Hold (review #55 F1).** One per cent of room humidity moves the requirement by about half a degree,
so jitter would flip the half-degree target, and each flip can cost a Tado call (about 100 a day on
the free tier). A raised target is therefore held (`this.state`) until the requirement falls 0.75 below
it: a fall needs about 1.5 % RH of real drying, while a rise is never held back. Worst case: one step up
and one step down per room per real humidity swing, so a handful of calls a night across four zones,
and none outside frost, where the operator's night wins outright.

On 24.11 (dry air, forecast −5 °C) nothing was raised; at −10 °C the bedroom (48 % RH) would go 21 → 22
and the kid 1 room 20 → 21. It costs heat only where and when a wall is at risk.

`input_number.climate_outdoor_min_12h` is written hourly at :05 and at start by
`automations/climate-coldest-hour-ahead.json` from `weather.get_forecasts`; fewer than 6 forecast hours
or a failed call writes the measured outdoor instead. A stale value is bounded by the measured outdoor
temperature, which the target always takes when it is colder; a stale *cold* value over-heats for at
most an hour, or for as long as the measured outdoor reading is also missing (the forecast is then the
only outdoor figure). The helper was seeded with the forecast minimum within a minute of its creation
(a new input_number starts at its minimum, −40, which would have read as deep frost).

## The corner probe (2026-11-24)

The operator fixed a thermo-hygrometer in the kid 1 room's coldest corner (labels `wall_probe` and
`not_on_room_pages`: it measures a surface, not the room; lint C33 accepts the label). Two uses:

- **Measured fRsi.** `sensor.climate_corner_frsi_<kid1>` = (corner − outdoor) / (room − outdoor), only
  when the room is at least 8 °C above outdoors and the result lies in 0..1 (a sunlit or handled probe
  is not a wall reading); a 48-h mean beside it. The first reading in place was **0.71**, not the 0.6
  assumed for that corner. After two days of data the room's factor (night target and Mould Indicator,
  kept equal by `wiring.py`) is set from the mean: a reviewed calibration, not a live-adapting factor.
- **Measured mould risk.** The probe's own humidity joins the 6-hour/80 % push and the Mould risk
  section, so the corner is watched directly, not only through the model.

## AC and open windows (2026-11-24)

The AC loop now has a window entity per room (the window detector where there is one, else the Tado
valve's flag; none for the office). An open window turns the AC off: comfort heat, cool, the boost
and the air-filter toggle stand down. Frost and pet-floor safety, and a person's manual hold, still win.

## Pre-heat on the way home (2026-11-24)

Proximity (`zone.home`, the three tracked people; entities renamed `sensor.home_*` because the
integration names them after the zone) gives the nearest distance and direction of travel. After more
than 2 h of Away in the heating season, someone heading towards home within 15 km turns
`input_boolean.climate_arrival_preheat` on; both climate automations then drop the Away floor for
comfort targets. Off on arrival (the alarm leaves Away), when the trip turns back past 25 km, or after
2 h. One push says it started. 15 km is roughly half an hour in town; the radiators need about that
to lift a room a couple of degrees.

## Copies and checks

The five night targets are one formula behind a `{% set room %}{% set f %}` header; `wiring.py`
fails when they differ after it, and when a factor differs from its room's Mould Indicator.

## Not covered by cases

The helpers' own arithmetic (cases pin the bathroom template against it), the 6-hour `for`, the
forecast call, notification delivery, and the consumers' use of the new entity (a rename of the
entity each reads; the decision logic is unchanged and its cases still pass).
