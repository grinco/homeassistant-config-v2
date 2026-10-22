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

Heat kills legionella and the other usual waterborne bacteria (Pseudomonas, coliforms). Rough
times to kill 90 % of legionella:

| water | time |
|---|---|
| 50 °C | 1.5–2 hours |
| 55 °C | about 20 minutes |
| 60 °C | about 2 minutes |
| 70 °C | seconds |

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
