# The morning briefing

*2026-10-20, issue #6.*

One push in the morning, "here's the house", **assembled** from the roll-ups the house already
keeps. It derives nothing. The audit of 2026-10-20 found the battery threshold drifting
because the Home card carried a second copy of the roll-up's logic, and that is what a briefing
that re-derived its facts would do.

| line | read from | never |
|---|---|---|
| Batteries to replace: names and levels | `sensor.any_low_battery` (entity ids, a last `+N more` item) | a threshold of its own |
| Not reporting: names | `sensor.any_safety_sensor_silent` | |
| Lights on: names | `sensor.lighting_left_on` | |
| Damp, health or air-quality risk: see Home | `binary_sensor.climate_health_risk` | the AQI or humidity thresholds |
| Yesterday the metered devices used X kWh, the ACs Y % of it | `input_number.energy_yesterday*` (`docs/energy-digest.md`) | a whole-house figure; there is no such meter |

A quiet house gets "Nothing needs attention." plus the energy line. A roll-up that is `unknown`
or `unavailable` says nothing. A dead roll-up is the silent-sensor check's job, not a reason
to tell the household about a problem nobody can name.

## Off by default

`input_boolean.house_briefing_push` is created **off**. `input_datetime.house_briefing_time`
is 07:30, seeded at creation (a new time helper starts at 00:00). It goes to both adults,
tag `house-briefing`, so each day's replaces the last.

## The card

Home's *Needs attention* already shows each of these facts live, as tappable tiles. A briefing
card on Home would show them a second time, and Home carries no text that a live card already
shows. The one fact the house did not show anywhere, yesterday's energy, is on the Energy tab
(*Load now*). So the on-screen surface is the existing section plus those two tiles, and the
push is the new part. That departs from the issue's "the card is the primary surface"; this is
why.

## Tests

`briefing:` cases in `tests/climate/cases.py` cover every line, the `+N more` pass-through,
unknown roll-ups, the energy line with and without meters, and a quiet house. There are four
mutations. Delivery is not reachable by a test. The message was checked by rendering the
automation's expressions against live state:

```
Batteries to replace: Shower Sink Leak 15%
Lights on: Beam Lights, Aurora, The Moon
Damp, health or air-quality risk: see Home
Yesterday the metered devices used 6.85 kWh, the ACs 32% of it.
```
