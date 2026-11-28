# Heating energy and an indicative A–G class: design

Operator request, 2026-11-23: a sensor for the energy the heating uses (gas as an estimate between
the weekly readings, checked against each reading) and for the AC, and the A–G class the flat most
likely falls in.

## What is measured, and what is not

| Source | Character | Resolution |
|---|---|---|
| Gas (`sensor.gas_total`, m³) | the operator's weekly manual reading | one value a week |
| AC electricity (5 × Samsung `*_ac_energy`, kWh) | measured per unit | continuous, since 2026-11-06 |
| Outdoor temperature (`sensor.climate_temp_outdoor`) | measured | continuous |
| Boiler run time, modulation, flow | **nothing** — no OpenTherm, no burner signal | — |

The boiler heats the radiators and the hot-water tank; gas does nothing else (operator: induction
cooktop). So gas between two readings is heating, which follows the weather, plus hot water, which
does not.

## Degree-days

The Czech convention (ČSN 38 3350): a day counts when its mean outdoor temperature is below 13 °C,
and contributes `19 − t_mean` K·day. The normal Prague season (Karlov, 1961–1990) is **3 235 K·day
over 225 days**. That is the reference year everything is annualised to.

*Which normal (2026-11-26).* 3 235 K·day is the 1961–1990 normal used by the Czech degree-day tables
(tzb-info, ČHMÚ); the older value in ČSN 38 3350 change a is 3 308. Winters have warmed since, and recent
seasons come out lower, so annualising to this normal makes `E_year` higher than a recent average year
would. Kept: it is the published reference and it errs towards a worse class. It does not affect
comparisons between our own intervals.

- `sensor.energy_outdoor_daily_mean`: a `statistics` helper, time-weighted (`average_step`),
  `max_age` 24 h. Read at 23:59 its window is 23:59 yesterday to 23:59 today: the calendar day,
  one minute off. (Review F7 suspected a half-day offset; that applies to a window read at noon,
  not at 23:59.)
- `input_number.energy_hdd_total` and `input_number.energy_hdd_days`: at 23:59 an automation adds
  that day's `19 − mean` when `mean < 13`, and adds 1 to the day count whether or not the day was
  cold. The day count is the audit: an interval between readings must contain as many counted days
  as calendar days, or a 23:59 run was missed inside it (F8) and the interval is a **gap**.

## The gas model (revised after review F1–F6)

`gas_kWh(interval) = a · HDD(interval) + b · days(interval)`

`a` (kWh per K·day) is the heating, `b` (kWh per day) the hot water and standing losses.

**They are not fitted jointly.** Winter weeks are all about seven days long with similar weather,
so `HDD` and `days` move together and a two-term least-squares fit on a handful of weeks is
ill-conditioned (F1, F2). Each term is measured where it is alone:

- **`b` from summer intervals**: an interval whose HDD is 0 is all hot water: `b = ΣG_s / ΣD_s`.
  Until a summer interval exists, `b = 0`.
- **`a` from winter intervals**: `a = (ΣG_w − b · ΣD_w) / ΣH_w`, recomputed from the running sums
  whenever `b` improves, so the first summer corrects every winter estimate retroactively.

With `b = 0` all winter gas is counted as heating: `a` over-states heating, the class can only come
out worse than the truth, and it says so (`hot water not yet separated`).

**One trust condition** (F5), used by the validation and the class alike: `ΣH_w ≥ 300 K·day`
(three to four winter weeks).

**Estimate between readings:** `gas_total + (a · rate · Δdays + b · Δdays) / calorific`, where
`rate` is the degree-days closed since the reading per closed day (`ΔHDD / Δclosed days`), or before
the first 23:59 close the running day's own `19 − mean` (0 at a mean of 13 °C or more). Before the first
summer interval it under-reads summer weeks by the whole hot-water term (F6): accepted, because
the first summer reading measures `b` and ends it.

*2026-11-25 validation:* the first form added `a · ΔHDD`. The 23.11 reading was taken at 23:36 and 23
minutes later the 23:59 close added that whole day's 16 K·d, although the meter already held its gas:
the estimate read 7.6 m³ high, and every later day was charged only at its close. Charging the closed
days' mean rate for the time actually elapsed removes the 7.6 m³ over-charge and the lump added at each
later close. Cases straddle 0.1 day after a close, the day before the first close, and the 13 °C rule.
A missed 23:59 close (no daily mean) adds neither degree-days nor a closed day, so the rate is the mean
of the days that did close, applied to the whole elapsed time; with none closed yet it is the running
day's own rate (review #62 F2, intended: an estimate, corrected by the next reading).

### Each weekly reading

When `sensor.gas_total` rises, the interval since the previous accepted reading is classified:

| verdict | when | effect |
|---|---|---|
| `first` | no previous snapshot | snapshot only |
| `gap` | counted days ≠ calendar days in the interval (F8) | snapshot only, push |
| `count` | model not trusted yet, or the reading is within tolerance | added to the sums |
| `flag` | trusted, prediction ≥ 50 kWh, actual differs by > 30 % **and** > 40 kWh | held out; push with a **Count it** button |

The prediction floor and the absolute term stop a mild or summer week, where the prediction is
small, from being flagged for arithmetic reasons (F3). A flagged interval is **not** added (F4): a
mistyped reading or a week away must not move `a` and `b` for good. The relative error is kept in
`input_number.energy_gas_model_error_pct`.

**The pending record** (round 2, FA1 and FA3). `input_text.energy_gas_pending` holds the whole
interval as JSON, `{"id", "g", "d", "h", "a"}`: its gas kWh, days, degree-days and AC heating kWh,
so a late **Count it** adds exactly what was measured. `id` is the reading's timestamp and is also
in the button's action (`ENERGY_GAS_COUNT_<id>`); a press counts only when the ids match, so a stale
notification can never count a different week. A new flag replaces a pending record and the
push says that the earlier week was dropped: never a silent loss. A gap leaves a held week alone. A gap is not recoverable; that is
accepted (FA5).

Calorific value: `input_number.gas_kwh_per_m3`, 10.6 until the bill gives the real one.

## AC

`sensor.energy_ac_total`: a `min_max` sum of the five unit meters (native). The 23:59 automation
also splits the AC by day, like the degree-days (round 2, FA2): a day's AC increase is added to
`input_number.energy_ac_heating_total` only when that day's mean is below 13 °C, so a warm day's
cooling inside a mixed week never counts as heating. Over a winter interval that total's increase
joins `ΣA_w`; `c = ΣA_w / ΣH_w` (kWh of electricity per K·day).

## The indicative class

```
E_year = (a + c) · 3235 + b · 365          kWh   (b = 0 until a summer interval)
e      = E_year / 164.41 m²                kWh/m²·year
```

Placed on the fixed **apartment-building** scale of the former vyhláška 148/2007:
A < 43, B ≤ 82, C ≤ 120, D ≤ 162, E ≤ 205, F ≤ 245, G > 245 kWh/m²·year.
(Checked 2026-11-26: the C/D boundary of 120 for apartment buildings is confirmed by a tzb-info worked
example; the other boundaries are as transcribed from the decree's annex and were not re-checked.)

**This is not a PENB.** A current certificate (vyhláška 264/2020) rates against a reference
building computed from the geometry, and counts primary energy, lighting and auxiliary energy,
none of which HA knows. The figure here is delivered heating + hot-water energy per m², on a scale
that was in law until 2013. It is labelled "indicative" everywhere it appears.

Two biases, named (F9): the 2007 scale rated **whole buildings** (stairwells, roofs, shared
losses), and one flat inside a block reads better against it than its building would; lighting
and appliances are not counted. Both flatter. So does `b` measured in summer: winter hot water
(colder mains water, longer showers) costs more, and the class applies the summer rate all year
(FA4). Gas and AC electricity are added as delivered energy,
the basis of the 2007 bands, not primary energy. The `b = 0` fallback errs the other way.

Until the trust condition holds the class reads `not enough data` rather than a letter from two
readings.

## First figure (2026-11-23, two readings, NOT the class)

11-14 → 11-18: 33.6 m³ in 4.4 days ≈ 80 kWh/day at outdoor ≈ 5–10 °C. A rough check, not a fit.

## Seeding and the rolling readouts (2026-11-24)

**Seeded from the recorder.** The winter sums were filled from the two intervals already on record,
14.11→18.11 and 18.11→23.11, with degree-days computed per calendar day from the recorded outdoor
temperature by the same rule as the nightly run. The two weeks disagree by 2× (7.1 vs 3.2 kWh per
K·day): the 18.11 reading is likely mistyped, so the per-week figures are not used. The sums only add intervals, so the pooled
figure (4.95 kWh/K·day over 111 K·day) equals one interval 14.11→23.11 and does not depend on the
middle reading at all. Do not read anything into the per-week split.

**Last 24 h / last 7 days, kWh/m².** `a · HDD + b · days + AC`, divided by the area. HDD comes from
the 24 h and 7-day time-weighted outdoor means (`19 − mean`, times 7 for the week), not from the
nightly counter, so the readout works before a week of counting exists. For the week this ignores
the per-day 13 °C cut-off, which only matters in a week that mixes heating and non-heating days. The
error is bounded and pinned by a case (review #53 F6): four days at 6 °C and three at 16 °C average
10.3 °C and count 61 K·day where the daily rule gives 52, so the week reads 1.96 kWh/m² instead of
1.69, 16 % high. Only spring and autumn produce such weeks; the class never reads this readout.

## Window detector (2026-11-24)

`binary_sensor.climate_window_<room>` for the two rooms with a VOC sensor (bedroom, kid 1 room). A
room aired in the cold shows two things together: its VOC index drops (fresh air), and its moisture
falls toward the outdoor level while the rest of the flat keeps it. On: outdoor below 12 °C, the
flat's moisture excess over outdoors above 0.8 g/m³, VOC below 40, and the room's excess below 0.75 of
the flat's. 5 min on-delay, 15 min off-delay. Backtested on 13.11–23.11: it caught the 23.11 airing
and a 20-minute one on 16.11 and nothing else; a temperature-drop rule had fired 57 times, almost all
on the kid 1 room's radiator on/off cycle (its sensor sits by the radiator; the valve started 172
times in ten days against 66 in the kid 2 room, so the temperature rule chased the radiator, not
windows). Twenty minutes open is a push to Vadim
(`automations/climate-window-open.json`); hours open per week feed **Aired most**, shown apart from
**Leaks most** so ventilation and structure are never confused.

### Review #53 follow-ups (2026-11-24)

- **A room drier than outdoors (F4).** The ratio goes negative when the room's moisture is below the
  outdoor air's, and a negative ratio passed `< 0.75` on its own: a radiator-dried room on a damp day
  needed only a VOC dip (a baseline reset after a power cut) to read as an open window. Airing brings
  a room *to* the outdoor moisture, never below it, so the room must also be within 0.5 g/m³ of it
  (`a − ao > −0.5`, about the RH sensors' accuracy at 20 °C). Cases straddle −0.44 / −0.56.
- **A blind detector (F1, F3).** A missing input makes the detector read closed: right for the push,
  silent for the household. `binary_sensor.climate_window_detector_blind` (problem class) is on when
  any of the eleven inputs (three per room, four shared) is not a number for 30 minutes; **Aired
  most** then reads `detector blind` instead of `none this week`. Each input has a case for both.
- **Two copies of one formula (F2).** A shared Jinja macro is the usual cure, but `run.py` substitutes
  the reads in the sensor's own text and cannot reach into an imported macro. So the copies stay, every
  case runs against both, and `tests/climate/wiring.py` fails when they differ after the header.
- **The flat reference includes the room (F5).** `sensor.indoor_temperature` / `indoor_humidity` are
  `min_max` means of the six rooms, the tested room among them. With a true ratio *q* against the other
  five, the detector sees 6q/(5+q): the 0.75 limit is *q* ≈ 0.71 against the rest of the flat. Slightly
  less sensitive, never a false alarm, and the 0.75 was backtested on the mean as it is. Using a mean
  of the other rooms would mean a third copy of the room list; not worth it.

### The valve's own window flag (2026-11-24)

The first live airing (bedroom, 24.11 ~09:44-10:01) showed both limits of the air signal: the detector
came on at 09:52 (VOC and moisture take minutes to fall, plus the 5-min on-delay) and stayed on after
the window shut, because the VOC index recovers over tens of minutes; the 20-min push went out at
10:12, eleven minutes after the close. Each detector room has a Tado valve that flags an open window
itself (by its temperature drop): on at 09:46, off at 10:01:33. So the valve's flag now decides first:
**on** is an opening; **off within the last 30 min** is a close the air may not contradict; otherwise
(no flag, the valve unreachable, or a later second opening) the air decides as before. The off-delay is
2 min, not 15: the valve now covers the flicker the long delay was for. A Home Assistant restart
re-stamps the valve's state, so for 30 min after one the air cannot open the detector (accepted).

### Leaderboards (2026-11-24)

`sensor.energy_leak_ranking`: every room with a measured Away cooling rate, leakiest first, as a
multiple of the median room, a room the last run flagged as a window marked `(window?)`.
`sensor.energy_airing_ranking`: hours aired this week per detector room, most first; `detector blind`
when the detector cannot see. Both replace the single-name tiles on the Energy view's Airtightness
section with numbered lists; *Leaks most* / *Aired most* remain as sensors for the briefing.

**A blind detector no longer hides the week (operator, 2026-11-28).** Review #53 F1 had a blind
detector replace the list with `detector blind`, on the reasoning that hours from a half-blind week
are not the week. In practice one room's VOC sensor dropped out at 23:39 on 27.11 and hid the two
airings it had counted at 22:23 and 23:46. The `history_stats` counters are already a rolling 7 days
and keep what they counted, so the list now always shows them; `detector blind` appears only when
nothing was counted. *Aired most* appends `(detector blind)` to the room it names, and the Energy
card adds a small line with the time the detector went blind.

### When the leak meter measures (2026-11-25)

The first live run (Away 25.11 11:41-14:55) stored the living room, kid 2 room and corridor at
0.9 / 0.2 / 1.3 %/h against 2.8 / 2.2 / 3.7 from 21.11. Two reasons, both timing. The radiators drop
to the Away floor 30 min into Away, so the 1 h snapshot came 30 min after setback, on warm radiators;
and arrival pre-heat raised the setpoints at 14:18, so the last 37 of 134 minutes were heated. The
snapshot now waits an hour after the setback (1 h 30 min into Away), and pre-heat switching on ends
the run as Away ending does. A run with under 1.5 h between the snapshot and its end is reported as
skipped, which is what today's would have been (snapshot 13:11, pre-heat 14:18). Accepted: short trips
with pre-heat will often skip, so baselines come mostly from long Aways (review #62 F6). `tests/climate/wiring.py` reads both delays from the live
radiator and leak-meter automations and fails if they drift apart. The three baselines were put
back to the 21.11 values. Not covered: a restart still resets the 1 h 30 min `for:` (F3, accepted).

### Air changes and outdoor CO₂ (2026-11-26)

The air-change rate takes outdoor CO₂ as 400 ppm. The global mean is now about 425 ppm (NOAA), so the
rate reads somewhat low (about 9 % for a decay from 900 to 600 ppm). Kept as an accepted bias: every
stored baseline was computed the same way, the 1.8× comparison is between runs of one formula, and the
sensors' own ±30–50 ppm drift is the larger error.

### Socket heat (2026-11-27)

Operator: "you're not taking into account the heat produced by devices when nobody is home: the rack
with a few servers in the office, the network PoE power supply in the living room". A room with a
steady heat source P does not cool toward outdoors but toward outdoors + P/H, where H is the room's
heat loss in W/K. Measured against outdoors, it looks tighter than it is. On 21.11 the office read
1.2 %/h, the flat's tightest at 0.4× the median, with about 225 W of rack and desk in it.

**H per room** comes from the flat's 1997 heating design (the building-office file of the loft
conversion, kept privately): a total design heat loss of 7 950 W (ČSN 06 0210, Prague's −12 °C design
outdoor, 20 °C rooms, so a 32 K difference), with each room's radiator sized to its own loss. A room's
share of the 7 950 W is its radiator's rated output over the sum of all twelve (approximate catalogue
outputs at 75/65/20 °C for 500 mm panels: type 11 ≈ 780, 21 ≈ 1 100, 22 ≈ 1 460 W per metre; towel
rails ≈ 550 and 1 000 W; installed ≈ 10.7 kW, 1.34× the loss). Only the shares matter, so the
catalogue figures' absolute error cancels.

| Room | Radiator | Design loss | H (W/K) |
|---|---|---|---|
| Living room + kitchen (one space) | 2 × 21 / 1200 | 1 960 W | 61 |
| Corridor (lower hall) | 22 / 900 | 980 W | 31 |
| Office | 21 / 900 | 740 W | 23 |
| Bedroom | 11 / 1200 | 700 W | 22 |
| Kid 1 room | 11 / 500 | 290 W | 9 |
| Kid 2 room | 11 / 500 | 290 W | 9 |

**Socket heat per room** is the energy of every metered socket in the room between the snapshot and
the end, as mean watts (`rooms_heat`, read into `input_text.leak_meter_heat` at the snapshot). The
office rack sits behind the Solix battery, whose charging goes through the same plug: energy stored is
not heat, so the battery's charge is subtracted and its discharge (and any solar input) added
(`sensor.solix_battery_in_energy` / `_out_energy`). On 21.11 the plug drew 1.57 kWh over the run, 0.96 kWh of it into the battery.
The rate is then `100 ln((T1 − g) / (T2 − g)) / h` with `g = outdoor + W / H`. The living room's
~75 W (PoE, media) moves `g` up by 1.2 °C.

Rules: a room whose own sockets hold it within 3 °C of its temperature (`T1 − g < 3`) is reported kept
warm, not measured: its cooling is then mostly the equipment, and the result swings with an H nobody
measured. A metered room whose meters could not be read at both ends is reported `no meter` and not
measured (an uncorrected office would be stored ~3× too airtight). A meter that went backwards (a
reset) counts as unread. A room whose air conditioner drew over 50 W on average is reported `AC on`
and not measured: a heat pump delivers 3–4× its electricity, and standby is about 1 W. No AC
specification is needed for that rule. `tests/climate/wiring.py` fails when a metered socket or an
air conditioner in a measured room's area is missing from `rooms_heat`, or when `rooms_heat` and `ua`
name different rooms.

**21.11 recomputed with the rule as built.** Living room 2.8 → 3.0 %/h. The office is kept warm: the
rack plug drew 1.57 kWh over the run while the Solix stored 0.96 kWh (it was charging), so the room
held 0.63 kWh, 355 W, and `g` = 5.7 + 355 / 23 = 21.1 °C, above the office's 20.4 °C. The office
cooled anyway, by 0.3 °C, so its real H is above 24 W/K: the radiator figure misses the heat it gives
the cooler rooms next to it through the plasterboard walls, which the other rooms barely have, since
they cool together. The office is therefore not measurable by this method on a run like that one; its
baseline was cleared (0, "not measured") rather than kept at the uncorrected 1.2, and the living room's
set to 3.0. Ranking from 21.11: kid 1 room 7.1, bedroom 3.8, corridor 3.7, living room 3.0, kid 2 room
2.2; office not measured.

Accepted: H is the 1997 design (radiators may have been changed since, and the design loss includes
heat to the unheated stairwell and neighbours); interior exchange between rooms is ignored, which is
fair for rooms that cool together and wrong for one with its own heat source (above); unmetered heat
(the fridge, about 40 W in the living room) is not counted. The kid rooms' small H means a desk PC
left on (100 W) moves their equilibrium by 11 °C: such a run reports the room kept warm. A per-room H
fitted from several runs with different socket heat (the office's varies by ~150 W with the Solix
charging) would replace the 1997 figure; it needs a winter of runs and is not built.

### One temperature per room: the mean of its air sensors (2026-11-27)

Operator: "use the average for the leak meter (same for all rooms that have multiple sensors)". The
office's two desk sensors read 21.3 and 20.1 °C at the same moment: one desk is not the room. The leak
meter now reads a room with several air sensors as their mean (`room_temps`), and the others by their
`climate_temp_` sensor as before. Only air sensors count. Not counted: AC indoor units (they read near
the ceiling, 1–2 °C warm), radiator valves (they read their radiator), the motion and presence sensors'
chip temperatures, and the kid 1 room's corner probe (it measures the wall surface, for mould).

| Room | Sensors averaged |
|---|---|
| Office | the CO₂ meter on one desk, the thermometer on the other |
| Living room | the CO₂ meter, the Tado wall thermostat |
| Kid 1 room | the furniture thermometer, the air-quality sensor |

A room with one of its sensors unreadable at either end has no reading, and is not measured: a mean
of the one left would step to that sensor's level. Climate control keeps its own sensors; this is the
leak meter only. `tests/climate/wiring.py` fails when an averaged sensor is missing, is not a
temperature sensor in that room, or sits on an AC unit or a valve (a wall thermostat is allowed).

## Not covered by cases

The 23:59 write itself, the statistics helper's window, notification delivery, and the blind
sensor's 30-minute delay. The interval
verdict, the coefficients, the estimate and the class are templates with cases; the sum update is
the verdict's `count` branch.
