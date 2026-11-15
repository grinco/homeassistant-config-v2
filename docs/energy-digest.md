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

### A made-up grid, so the Energy dashboard balances (2026-11-15)

> "the energy dashboard doesnt display correctly ... it looks like the battery supplies energy
> non stop. also the devices are consuming but also returning energy"

With no grid source, the dashboard's only sources were the Solix C2000: solar (0 kWh) and its
battery (about 0.03 kWh a day, the USB trickle). It computes the house's use as grid + solar +
battery out − battery in, so it believed the house used ~30 Wh a day while the device meters
reported ~13 kWh. The difference was drawn as a large negative *untracked consumption*, which
reads as devices returning energy, and the battery was the only thing that could have supplied
any of it.

**The fix is a grid that is the sum of the device meters.** `sensor.metered_grid_import`, a
trigger template in `configuration.yaml`, is the dashboard's one grid source. With it, untracked use is only what the Solix's battery and panel
add or take, which is what it really is: the Solix is plugged in **behind the mini rack socket**
(operator), so whatever it draws from the wall is already inside `sensor.mini_rack_energy`. Its
battery and solar stay as sources. Charging it from the wall shows briefly as negative untracked
(the mini rack meter counted energy that went into the battery), discharging as positive; they
cancel over a cycle.

What it is not: a mains meter. Anything not on a metered plug is invisible, so "grid" is a lower
bound, and a real meter (a clamp meter in the panel, or the utility meter's P1/HAN port if it has
one) replaces it the day one exists.

**It adds increases, never the raw sum.** The meters' readings add up to ~14 000 kWh. A sum of
them breaks the first time a plug resets its counter: one plug going to 0 takes ~1000 kWh off,
which the recorder books as a ~1000 kWh negative day (a `total_increasing` drop under 10 % is a
"dip", not a reset), and a drop over 10 % is taken as a meter reset that re-counts the whole sum.
So `custom_templates/metered_total.jinja` keeps each meter's last reading in an attribute and
adds only what it rose by:

| new reading | added | remembered |
|---|---|---|
| first ever for this meter | 0 | the reading |
| unavailable, not a number, negative | 0 | unchanged (the gap is counted on return) |
| higher than last | the difference | the reading |
| below a tenth of last (a counter reset) | the reading | the reading |
| otherwise lower (a group meter losing a member) | 0 | unchanged, so the recovery is not counted twice |

Tests: `tests/energy/run.py` (19 cases against the deployed macro, both sides of the tenth),
`tests/energy/mutate.py` (10 mutations). `tests/climate/wiring.py` fails if the template's meter
list differs from the dashboard's device list (less any `included_in_stat` meter) in either
direction, if anything other than this sensor is the dashboard's grid, if the sensor is not
`total_increasing` kWh energy computed by `metered_step`, or if the repo's macro differs from
the deployed one.

**History is backfilled.** The sensor went live at 22:53 on 2026-11-15. Its hourly statistics
before that (from 2026-09-17, where the device statistics stop being continuous) were imported
with `recorder/import_statistics`: each hour is the sum of the device meters' own hourly changes,
and the imported sums end exactly at the sensor's first live row, so the join books no jump. Daily
grid then equals the daily device total on every day checked. The database was copied to
`home-assistant_v2.db.bak-20261115-prebackfill` first.

**Restart.** The sensor restores its state and `last` after a template reload (checked
2026-11-15: 0.1 kWh and all meters kept; `last` came back as a mapping, which the macro accepts
as well as JSON text). If either were ever lost, the meters re-seed: an undercount until each
reports again, never a double count.

**Accepted:**
- a group meter that falls **below a tenth** of its last reading is taken for a reset: the small
  reading is added, and the recovery to the old level is added again. A powercalc group losing
  90 % of its members at once is the case; it has not been seen;
- a meter whose counter jumps by a glitch is counted, exactly as the recorder counts that
  device's own `total_increasing` statistics;
- trigger renders are serial today; if the sensor ever renders from two paths at once, one
  increase could be lost.

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
