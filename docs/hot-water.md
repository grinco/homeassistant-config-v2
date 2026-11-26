# Hot water: a schedule fitted to the household, and a weekly hot cycle

*2026-10-21.*

## The system

A Buderus Logamax plus GB172 gas boiler (the operator believes the -25 variant; unconfirmed)
heats an accumulation (storage) tank. Tado runs the hot water as its own zone over the boiler
connection: Home Assistant sees it as `water_heater.hot_water_hot_water`, modes `auto` / `heat`
/ `off`, setpoint 30–65 °C. No tank temperature is reported.

**The schedule lives in the Tado app.** Home Assistant cannot read or edit Tado timetables, and
driving the setpoint from an automation would spend the account's free-tier API budget (about
100 calls a day, shared with `automation.climate_radiators`). A schedule in Tado costs no calls.
The operator set the schedule in the app, and the table below is the record of it.
`tests/tado/export.py` can read the timetable from the Tado API into
`automations/hot-water-schedule.json`. It has its own device login, because Tado's refresh tokens
rotate and borrowing Home Assistant's would log the integration out. It has not been run yet;
once it has, that export is the record and this document stays the reasoning.

## The schedule it replaced

Read back from ten days of the zone's setpoint history (the same every day):

| time | setpoint |
|---|---|
| 00:00–04:00 | 40 °C |
| 04:00–10:00 | 55 °C |
| 10:00–17:00 | 40 °C |
| 17:00–22:00 | 55 °C |
| 22:00–24:00 | 30 °C |

The tank was held at 55 °C for 11 hours a day and at a 30–40 °C setpoint for most of the rest,
which is the range legionella grows in.

## When hot water is used

No flow meter, so use was read from humidity: a hot shower or bath raises the room's humidity
sharply. Over 11 days (5-minute maxima from the recorder, a rise of 6 points or more over the
previous 30 minutes):

- **Shower, 19:45–21:30, ten evenings of eleven.** This is the main draw.
- **Baths, about 20:20, one or two a week** (13th, 15th and 19th), in the upstairs bathroom.
- Weekend middays, 12:00–14:30, about four days in eleven.
- Some mornings, mostly weekends, 07:30–09:45: small rises upstairs, one shower at 06:50.

The operator added what humidity cannot see: hands are washed and fruit rinsed many times a
day, and the kitchen uses hot water. These are small draws, but they come all day.

## The schedule now (set by the operator, 2026-10-21)

| time | setting | why |
|---|---|---|
| 06:30–08:30 | 50 °C | one reheat for the light morning use |
| 08:30–18:30 | 45 °C | the boiler fires only when the tank falls below about 40 °C, which keeps the taps warm for small draws |
| 18:30–21:30 | 55 °C | the evening showers and the baths |
| 21:30–06:30 | off | |
| **Saturday and Sunday, 15:00–17:00** | **65 °C** | the hot cycle, below |

**Why it is cheaper.** A tank loses heat in proportion to how much hotter it is than the room
around it. The old schedule kept it at 55 °C through the night and the working day, when it is
barely drawn. The new one heats it shortly before the two real uses and lets it coast at 45 °C
in between.

**Why not 40 °C or off in the day.** 40 °C is lukewarm at a tap after the pipe has taken its
share, and it is inside the legionella growth band. Off all day would leave the afternoon
hand-washing cold.

**Small draws are mostly pipe loss.** A hand wash ends about when the hot water reaches the
tap, and that pipe-full then cools. No setpoint changes that.

## The hot cycle

Heat kills legionella and the other usual waterborne bacteria (Pseudomonas, coliforms).

*Corrected 2026-11-26 (review of the field guide).* The table that stood here (90 % kill in 1.5–2 h at
50 °C, ~20 min at 55 °C, ~2 min at 60 °C, seconds at 70 °C) had no source and is too optimistic at 55 and
60 °C. What the laboratory studies report, with several-fold spread between strains and more in biofilm:

| water | time | source |
|---|---|---|
| 50 °C | survives for hours, not reliably killed | HSE HSG274 Part 2; WHO 2007 |
| 55 °C | complete loss of culturability after 3–8 h | Cervero-Aragó et al. 2019 (PMC6520252) |
| 60 °C | thermal death 1.3–10.6 min across Legionellaceae; complete loss of culturability after 60 min | Stout, Best & Yu 1986 (PMC203540); Cervero-Aragó 2019 |
| 70 °C | 0.7–2.6 min; under 2 min | same |

Stout's minutes are from laboratory suspensions in clean water; in a tank, biofilm and sediment shield the
bacteria, which is why the rule follows Cervero-Aragó's 60 minutes, not Stout's minutes. So **60 °C or more
for an hour** is the conservative reading, which is the rule below.

The rules followed, after the German DVGW W551 guidance:

1. **The whole tank at 60 °C or more for an hour or more.** The bottom of a coil-heated tank,
   below the coil near the cold inlet, runs cooler than the setpoint. A two-hour window gives the
   heat time to reach it. A 55 °C setpoint alone does not.
2. **Flush the pipes right after.** Run every hot tap and shower on full hot for 2–3 minutes,
   so that 60 °C+ water passes through the pipes and fittings. Legionella lives there too, not
   only in the tank.
3. **Run rarely used taps weekly**, and descale the shower heads every few months: the biofilm
   in limescale shelters bacteria from heat.

**Twice a week (operator).** Running the cycle on both Saturday and Sunday makes it more likely
that every tap gets flushed while the water is hot. The second cycle costs one more heating of
the tank a week, and most of that heat goes into the evening showers rather than being lost.

**Timed in the afternoon, not before the baths.** 65 °C from a tap without a thermostatic mixer
scalds in seconds, and there are children in the house. By 18:30 the tank is still near 60 °C,
so the evening setpoint costs almost nothing extra.

## Open

- Whether the GB172 caps hot water at 60 °C. If it does, Tado shows 65 and the tank stops at
  60. With a two-hour hold that is still effective.
- Whether the boiler's own thermal disinfection runs at all with Tado driving the hot water. The
  Tado cycle was added so that the answer does not matter.
- Whether the bath tap has a thermostatic mixer.
- To verify a cycle ran, look for 65 between 15:00 and 17:00 in the water heater's setpoint
  history on a weekend.
- Not acted on: the shower room's humidity never falls below about 73–87 %, even hours after a
  shower. That is a mould risk, and the fix is ventilation, not hot water.

## Off while the house is away (2026-11-24)

Operator: the tank kept itself hot for an empty flat. `automations/house-hot-water-away.json`:

- **Off** after 6 h of Away (`input_datetime.climate_away_since`), only if the tank runs its Tado
  schedule (`auto`); a tank set by hand is never touched. `input_boolean.house_hot_water_paused`
  records that HA did it and `input_datetime.house_hot_water_paused_at` when.
- **Back to `auto`** when the alarm leaves Away, the arrival pre-heat starts, or the nearest tracked
  person heads home within 15 km (Proximity; also outside the heating season, when the pre-heat does
  not run). Only a pause HA made is undone.
- **Legionella.** Off for more than 48 h means the water sat lukewarm for days: the tank first runs
  **two hours** at 65 °C (`heat`), the weekend cycle's temperature, then returns to `auto` (2026-11-26:
  was one hour, which from a tank cold for two days is mostly reheating; `tests/climate/wiring.py` now
  fails if the hold after the hot step is under 2 h). Shorter pauses
  go straight back; the weekly 15-17 h cycle on Saturday and Sunday still runs from the Tado schedule.

Cases cover the pause, the restore and the 48 h choice (13, straddling 6 h, 15 km and 48 h). Not
covered: Tado accepting `off` / `heat` / `auto` through the cloud (first real Away will show it in
the trace), and the delay itself.

**The hold survives a restart (2026-11-26).** The hold used to be a `delay` inside the run, and a Home
Assistant restart during it ended the run before the step that returns the tank to `auto`, with the pause
flag already cleared: the tank stayed at 65 °C until someone noticed. Now the run that starts the hot cycle
writes the hold's end (`input_datetime.house_hot_water_hot_until`, now + 2 h) and a flag
(`input_boolean.house_hot_water_hot_hold`) **before** commanding 65 °C, and returns. A separate branch,
`release`, ends the hold once the flag is on and the stamp has passed: it clears the flag and, only if the
tank is still in `heat`, sets `auto` (a tank someone changed by hand during the hold is left alone). It runs
at the stamp itself, at every start (so a restart ends an overdue hold as soon as HA is back), and every 15
minutes as a fallback.

The hold only ever starts in the `restore` branch, i.e. when the pause ends because someone is coming home,
and that branch clears the pause flag first. So `auto` at the end of the hold is the right state. If the trip
turns back instead, the tank is in `auto` again and the 6-hour pause rule switches it off at the next check;
during the hold the tank is in `heat`, which the pause rule never touches, and `restore` cannot fire because
the pause flag is already off (review round 3, 2026-11-26: F1 to F3 checked against this and rejected). Cases straddle the stamp by one second and cover a stamp missed during a restart and an old stamp
with no hold; `wiring.py` fails if a `delay` or a wait follows the hot step, if the stamp is under 2 h, if the
hold flag is not turned on before the 65 °C command, or if any of the three release triggers is missing.
Not covered: the `heat` check in the release branch and Tado accepting the calls.

## Where this departs from the hygiene guidance (2026-11-26)

HSE HSG274 Part 2 and the Czech National Institute of Public Health (SZU, recommendation of 4.9.2025)
recommend storing hot water at **60 °C** and reaching at least **50 °C (better 55 °C) at the tap within a
minute**. The day setting of 45 °C and the overnight off are below that, by the operator's choice: lower
standing losses against a higher legionella risk, mitigated by the twice-weekly 65 °C cycle, the flush and
the 48-hour rule. A household with an elderly or immunocompromised member should follow the guidance.
