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
the same physics: a helper inherits the device of the sensor it reads, the bathroom's sensor sits in
a Magic Areas room, and Magic Areas would then average a wall humidity into the room's air humidity
(lint C20/C33 caught it before it shipped). Cases pin it against the helper's own reading.

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
consumers keep their own fallback, as before. Half degrees, so a valve is not chased by humidity noise.

On 24.11 (dry air, forecast −5 °C) nothing was raised; at −10 °C the bedroom (48 % RH) would go 21 → 22
and the kid 1 room 20 → 21. It costs heat only where and when a wall is at risk.

`input_number.climate_outdoor_min_12h` is written hourly at :05 and at start by
`automations/climate-coldest-hour-ahead.json` from `weather.get_forecasts`; fewer than 6 forecast hours
or a failed call writes the measured outdoor instead. A stale value is bounded by the measured outdoor
temperature, which the target always takes when it is colder; a stale *cold* value over-heats for at
most an hour. Seeded at creation (a new input_number starts at its minimum, −40).

## Copies and checks

The five night targets are one formula behind a `{% set room %}{% set f %}` header; `wiring.py`
fails when they differ after it, and when a factor differs from its room's Mould Indicator.

## Not covered by cases

The helpers' own arithmetic (cases pin the bathroom template against it), the 6-hour `for`, the
forecast call, notification delivery, and the consumers' use of the new entity (a rename of the
entity each reads; the decision logic is unchanged and its cases still pass).
