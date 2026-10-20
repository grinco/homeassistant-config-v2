# Energy: a daily digest, and why there is no anomaly flag yet

*2026-10-20, issue #8.*

## What was asked

A daily line, "the house used X kWh, the AC was Y % of it", and an anomaly flag, "the AC ran
9 h today against about 3 h typical". Read-only, on the meters the house already has. Any
anomaly threshold measured from history first, not guessed.

## There is no whole-house meter

The Energy dashboard has **no grid source**, only 14 device meters: five AC units, the light
model, seven sockets and the PoE switch. "The house used X kWh" cannot be measured. What can
be said, and what the digest says, is **what the metered devices used**. The wording in the
briefing is exact for that reason.

## The digest, as built

`automations/energy-digest.json`, at 00:10. It calls `recorder.get_statistics` for yesterday
(local midnight to 23:59) over the Energy dashboard's device list and writes three helpers:

| helper | |
|---|---|
| `input_number.energy_yesterday` | sum of every meter that reported, kWh |
| `input_number.energy_yesterday_ac` | the meters whose id ends `_ac_energy`, kWh |
| `input_number.energy_yesterday_meters` | how many meters reported |

- **One source per fact.** These are the long-term statistics the Energy dashboard itself
  draws, so the digest and the dashboard cannot disagree about a day. The meter list has to be
  copied into the automation, because an automation cannot read the Energy preferences.
  `tests/climate/wiring.py` fails if the two lists differ, in either direction. A meter the
  dashboard counts inside another (`included_in_stat`) is left out of both.
- **It also runs at Home Assistant start**, so a restart over 00:10 does not leave the day
  before yesterday's figures standing; running twice recomputes the same day. Day boundaries are
  local midnight on DST days too: `today_at() - timedelta(days=1)` is zone-aware (checked on
  2026-10-25/26 and 2027-03-28/29).
- **An offline meter is left out, not counted as zero.** A meter with no statistics for the day
  (the PoE switch while UniFi is disabled) is skipped, and `energy_yesterday_meters` says how
  many reported. A day with no meter at all reads 0 meters, and the briefing then says nothing
  about energy instead of "0 kWh".
- **Shown on the Energy tab** (*Load now*: "Metered yesterday", "ACs yesterday"), and in the
  morning briefing (`docs/house-briefing.md`).
- Seeded on creation with 2026-10-20: 6.85 kWh over 14 meters, ACs 2.20 kWh. The values were
  computed by rendering the automation's own expressions against a live `get_statistics`
  response; the automation was not triggered.

Tests: `energy:` cases in `tests/climate/cases.py` (the sum, the AC share, an offline meter,
a stray meter, an empty day) and three mutations.

## The anomaly flag: measured, and not built

The recorder holds ten days of AC states (2026-10-10 to 2026-10-20). Daily hours with any AC
running, and daily AC energy from the long-term statistics:

| day | AC running | AC energy |
|---|---|---|
| 10-10 | 2.8 h | 2.51 kWh |
| 10-11 | 2.7 h | 2.40 kWh |
| 10-12 | 1.3 h | 1.18 kWh |
| 10-13 | 1.1 h | 0.84 kWh |
| 10-14 | 0.8 h | 0.69 kWh |
| 10-15 | 0.6 h | 0.47 kWh |
| 10-16 | 1.3 h | 1.24 kWh |
| 10-17 | 0 h | 0 kWh |
| 10-18 | 1.4 h | 1.38 kWh |
| 10-19 | 2.2 h | 1.70 kWh |
| 10-20 | 2.5 h | 2.21 kWh |

Hours come from state history (any AC in a mode other than `off`), energy from the five AC
meters' daily statistics. The two agree day by day, so either is a usable measure of AC use.

**Why no threshold can be set from this.** The median is 1.3 h. A flag at 2 × the median
(2.6 h) would have fired on 2 of these 11 days, and at 1.5 × on 4, and nothing was wrong on any of them. The
spread is the weather, and a change of system: from 2026-10-11 the radiators took over comfort
heating at night (climate v6), which by itself moved the ACs' hours. A "typical" measured over
two weeks in which the heating moved from one system to another is not a baseline.

**What it would take.** Normalise by the weather before comparing: AC hours per heating or
cooling degree-day (outdoor temperature from `sensor.climate_temp_outdoor`). Then measure the
spread of that ratio over a settled month, once the heating season is under way, and set the
flag from that spread. Same rule as the radiation alert: the threshold comes from a
measurement, and the measurement comes first.

## A baseline that moves with the house (operator, 2026-10-20)

> "can the baseline be calculated with a helper? i'm adding devices and appliances in the
> apartment, so over time it would change and would be triggering frequently"

A fixed "typical" would go stale with every new appliance, and it already has: the mini rack
socket fell from about 4.4 kWh a day to about 1.4 kWh on 2026-10-17. So the baseline must be
computed, not set. Two ways to compute it, and only one survives a restart:

- **A native `statistics` helper** (a rolling median of `input_number.energy_yesterday`) is the
  obvious shape, and it does not hold up here. The helper rebuilds its window from the
  recorder's state history at start-up, and this recorder keeps **10 days** (the default; no
  `purge_keep_days` in `configuration.yaml`). A 28-day window would quietly become a 10-day one
  after every restart.
- **The long-term statistics do hold up.** They are permanent, hourly and daily, and they are
  what the digest already reads. The digest can ask `recorder.get_statistics` for the last 28
  days instead of the last one, and write the baseline into a helper itself.

**Per meter, not per house.** Summing first and comparing the total is exactly what the operator
describes: a new appliance raises every day's total from the day it is plugged in, against a
baseline that has not seen it yet, and the flag fires until the window fills. Comparing each
meter with **its own** 28-day median avoids that by construction:

- a new meter has no history, so it cannot be flagged until it has (say) 7 days of its own;
- a meter that changes for good (the mini rack) is flagged until its own median catches up:
  a median moves only when half the window has the new level, so that is **about 14 days** on a
  28-day window. It is only that meter, and the message says which. A shorter window catches up
  sooner and is noisier; the window is the first thing to measure;
- the message can say which device: "Mini rack used 4.4 kWh, usually 1.4".

**The ACs stay out of it** until they are weather-normalised (kWh per degree-day, above). Their
spread is the weather, so their own median would fire on every cold snap. Concretely, the
per-meter loop runs over `ids | reject('search', '_ac_energy$')`, the same id rule the digest
uses for the AC share.

**A meter with no history.** `recorder.get_statistics` returns no key at all for a meter with no
statistics in the window, and a bucket whose `change` is null for one with metadata but no data.
Both mean "no reading". The digest already treats them that way (`change is number`, cases
*an offline meter…* and *a bucket with no change…*), and the baseline must apply the same rule
day by day before it counts a meter's days.

Still to measure before building: the factor. The long-term statistics already hold 20 days
per meter (since 2026-10-01), so the day-to-day spread of each socket against its own median can
be computed now. The factor is then set from that spread, not chosen.
