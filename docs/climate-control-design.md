# Automatic per-room climate control — design

Status: **implemented and live** (2026-09-19). Version 4.
Written retrospectively after a v1 model that shipped and had to be replaced the same evening,
then revised through four adversarial reviews. v4 is a deliberate simplification of the control
model requested by the operator, and it closes the round-4 findings at the same time.
Instance: HA 2026.9.2 Supervised, Home.

> **Naming note.** The two children's rooms appear throughout this document and in the exported
> configs as **Kids room 1** and **Kids room 2** (`kid1_*`, `kid2_*`). The live instance uses the
> children's actual names. The substitution exists so this repository does not publish
> identifying information about minors, and it must be re-applied to any future export — see
> `automations/README.md`.

**Revision history**
| v | What changed | Why |
|---|---|---|
| v1 | One setpoint per mode ± symmetric deadband; forecast-high season guard | Shipped and failed — see §7 |
| v2 | Two thresholds per room, dead zone, outdoor lockouts, forecast removed | Fixed the cooling-to-19 incident |
| v3 | Exit hysteresis, unconditional frost override, away branch respects lockouts, persisted away stamp, sensor-bias correction in *all* branches, availability guards, mode-before-setpoint sequencing, per-room circuit breaker | Closed nine round-1 findings — see §9 |
| v3.1 | **Safety band made universal and unconditional**; breaker re-arms hourly | Round 2 found that v3's away-respects-lockouts change and its breaker both had holes — see §10 |
| v3.2 | **Manual changes at the wall win**; gas boiler recognised as a low baseline | Operator requirements — see §11 |
| v3.3 | Safety band outranks the manual hold; boiler flag no longer suppresses it; human-vs-fault detection rebuilt on the failure counter; hold now notifies | Round 3 found both v3.2 additions had safety holes — see §14 |
| v3.4 | **Per-room boiler flags deleted entirely** (5 helpers, dashboard section, automation references) | Operator: "the boiler settings per room are redundant… they complicate the setup and the dashboard" |
| **v4** | **Heat/cool becomes a global HOUSE decision from the outdoor temperature; each room gets a day target and a night target instead of two thresholds; new per-room air-filter mode; human detection rebuilt on a real command timestamp; setpoints rounded and clamped to the unit's range; `climate_safety_always` becomes a true master hatch** | Operator simplification request, plus round-4 findings R4-1 through R4-7 — see §15 and §16 |

---

## 1. Problem

Five Samsung split units, one per room, each a competent thermostat on its own but with no
coordination, no schedule, and no relationship to outdoor conditions. Every adjustment was
manual, at the unit or in the app.

The operator asked for, in their words:

> per-room target temperature maintained automatically … based on the outdoor and indoor
> temperatures, as well as season and forecast … a day/night setting, for more comfortable
> sleep … when the alarm is armed_away turn off the automations maintaining the apartment at
> 18C in winter to prevent cats freezing and pipes bursting and below 30 in summer

and a hard constraint:

> if any of the ACs are running or must start — they must be in silent + windfree mode

They had explicitly **rejected** manually-triggered routines ("I don't like routines that need
to be triggered manually"), and the house has **no presence or motion sensors**. So the system
must decide entirely from temperature, time, and alarm state.

### Non-goals

- Presence-based control. No sensors exist; adding them is a separate project.
- Replacing the units' own PID loop. We choose a setpoint and a mode; the unit does the rest.
- Humidity, air quality or ventilation control.
- Scheduling around electricity price. The spot-price integration is installed but exposes no
  entities, so there is nothing to optimise against yet.

---

## 2. Constraints discovered from the hardware

Read from the live entities before designing anything — each of these changed the design.

| Finding | Consequence |
|---|---|
| `hvac_modes` includes **`heat`** | The units are heat pumps. Winter heating is in scope, so the system is not cooling-only. |
| `preset_modes` = `none, sleep, quiet, boost, motion_indirect, wind_free, wind_free_sleep` | `preset_mode` is a **single exclusive value**. "Silent + windfree" cannot be two settings; it is `wind_free` by day and `wind_free_sleep` at night, the latter already being the quiet+windfree combination. |
| `min_temp` 16, `max_temp` 30, `target_temp_step` 1 | Room-target helpers are bounded 16–30 with a step of **1**, matching the hardware. v3 used 0.5 "for UI feel, the unit rounds" — it does not round, it refuses, and the refusal is silent. See §3, Setpoint clamping. |
| AC `current_temperature` reads **~2 °C high** vs an independent meter in the same room, same moment (25.0 vs 23.1) | It is return-air temperature from a unit mounted high on the wall. Controlling on it would overcool in summer and underheat in winter by that error. **A dedicated room sensor must be preferred where one exists.** |
| `alarm_control_panel.home` `supported_features: 11` = arm_home + arm_away + **arm_night** | The alarm can supply the day/night signal, reusing a ritual the household already performs. |
| The integration is cloud-backed (SmartThings) | Every service call is a WAN round trip. Actuation must be idempotent and rare. |

### `set_preset_mode` TURNS AN OFF UNIT ON — verified 2026-09-19

Calling `climate.set_preset_mode` on a unit whose state is `off` does not merely stage a preset
for later. **It turns the unit on, in `cool`.** Observed directly on the Office AC: the unit was
`off`, a single `set_preset_mode(wind_free)` call returned `verified_state: "cool"`, and the unit
was running until it was explicitly commanded `off` again.

This is the single most dangerous service call in this integration, because it looks inert. Two
rules follow, and both are now load-bearing:

- **Never send a preset to a unit that is not already in an active mode.** The preset step is
  gated on `mode_ok and needs_temp`, so it only ever runs when the unit is confirmed to be in
  `heat` or `cool`. That gate was written to avoid a swallowed command; it turns out to be
  preventing an unwanted *start*.
- **"Start the unit in wind_free" cannot be implemented by sending the preset first, or by
  sending it alongside the mode.** The obvious implementation — set the preset so the unit comes
  up already in wind-free — is exactly the call that starts it in `cool`, which in heating season
  is the v1 incident again by a different route. Any future attempt at this must be tested
  against an `off` unit before it goes anywhere near the loop.

The cost today is that a unit the automation starts runs in its previous preset for one tick
(up to 10 minutes) before wind-free is applied on the following tick, once the mode is confirmed.

### Sensor assignment

| Room | Control sensor | Quality |
|---|---|---|
| Living Room | `sensor.living_room_meter_pro_co2_be_temperature` | SwitchBot meter — good |
| Office / Guest Room | `sensor.meter_pro_co2_e9_temperature` | SwitchBot meter — good |
| Bedroom | `sensor.master_bedroom_bedroom_ac_temperature` | **AC internal — known ~2 °C high** |
| Kids room 1 | `sensor.kid1_room_ac_temperature` | AC internal (room unused) |
| Kids room 2 | `sensor.kid2_room_ac_temperature` | AC internal (room unused) |

Each room carries a `sensor` and a `fallback`; the fallback is the AC's own sensor. Where no
dedicated meter exists the two are the same entity. Resolution:

```jinja
{{ states(r.sensor) | float(states(r.fallback) | float(-999)) }}
```

`-999` is a sentinel meaning *no usable reading*, which resolves to mode `skip` — the room is
left alone rather than actuated on a default.

**Bias correction (v3).** The three AC-internal rooms are flagged `biased: true` and have
`input_number.climate_ac_sensor_offset` (default −2.0 °C) applied **before every comparison,
including the safety band**. v2 applied no correction, which meant the Bedroom reading 18 °C —
the away/frost trigger — was a *true* ~16 °C room. The 18 °C floor the operator specified for
the cats was therefore really a 16 °C floor in exactly the room they sleep in. The offset is a
calibration constant, not a comfort setting, which is why it is one global helper rather than
five.

---

## 3. Control model

### The house decides heat or cool; the room decides how warm

v2 and v3 gave every room *two* numbers — a heat-below and a cool-above with a dead zone
between them. That worked, but it asked the operator to express one idea (how warm do I want
this room) as two numbers, and it let five rooms disagree about what season it was.

v4 splits the decision along its natural seam:

```
        HOUSE  (one decision, from the outdoor temperature)

          outdoor ≤ heat below (17°)        ──►  HEATING
          outdoor ≥ cool above (20°)        ──►  COOLING
          between the two                   ──►  SHOULDER, nothing runs


        ROOM   (one number, the one you actually want)

          day target   22°          night target  20°
```

The house is **never in both modes at once**, so a single target per room is now safe: there is
no second threshold for it to collide with. The 3-degree shoulder band between the two global
numbers is what stops the house flipping mode on a mild day — it is the seasonal equivalent of
the per-room dead zone it replaces.

Two properties worth stating explicitly:

- **The mode is a property of the weather, not of a room.** Cooling a room to its target when
  it is 13 °C outside is the v1 bug (§7). Making the season a single global fact makes that
  class of bug unrepresentable rather than merely guarded against.
- **If the outdoor sensor is unusable the house falls to SHOULDER**, not to a guessed season.
  v3 defaulted the reading to 15 °C, which would have put the whole house into heating on a
  fabricated number. The safety band does not read the outdoor sensor and still runs.

### Night

Night is the same window as before — the `schedule.climate_night` helper (22:00–06:00), or the
alarm armed night. v3 expressed night as a *setback*, a shift applied to both thresholds. v4
expresses it as what it is: a second target. Cooler at night for sleep, warmer by day, both set
directly.

The operator goes out with the dog inside that window, so night must not be inferred from
presence, and it is not: it is a schedule.

### Air filter

Per room, optional, default off. When the house has a season but the room has no thermal work
to do, air filter still starts the unit **in the house mode at the room's target** — heat at 22
in a room already at 24. The unit will not do much thermally; the point is that the fan and the
filter run. In shoulder season there is no house mode to borrow, so it runs `fan_only`, the one
mode that guarantees airflow with no thermal intent.

It sits *below* the room's Maintain toggle in precedence: a room that is off stays off, and it
never overrides away or the safety band.

> Open question for the operator: whether these units actually move air in `heat` while sitting
> above setpoint is a property of the unit's idle-fan behaviour, not of this automation. If the
> filtering turns out not to happen, the fix is to use `fan_only` for the in-season no-work case
> too, which is a one-line change to the `mode` template.

### Mode resolution

Branch order is load-bearing; the first match wins.

```
if temp is unusable                    -> skip     (issue nothing at all)
elif safety_on and temp < frost        -> HEAT to frost        # unconditional
elif safety_on and temp < away_min     -> HEAT to away_min     # unconditional
elif safety_on and temp > away_max     -> COOL to away_max     # unconditional
elif manual hold is live               -> MANUAL   (issue nothing at all)
elif not comfort                       -> off
elif away OR room disabled             -> off
elif house == heat                     -> HEAT to target  if temp < target
                                                          or (already heating and temp < target + hyst)
                                                          or air filter on
                                          else off
elif house == cool                     -> COOL to target  if temp > target
                                                          or (already cooling and temp > target - hyst)
                                                          or air filter on
                                          else off
else  (shoulder)                       -> FAN_ONLY if air filter on else off
```

`target` is the night target while night is in effect, the day target otherwise.

Precedence is **frost > away floor > away ceiling > manual hold > comfort**. Round 3 (M7)
established that a manual hold must not be able to leave a room at 8 °C for two hours, so safety
outranks it. Round 4 (R4-4) then pointed out the mirror harm: a person airing a room in winter
would be fought every ten minutes, indefinitely, with no way out. v4 gives that two answers,
both in §16.

### Hysteresis

Exit-only, and it applies to the single target: a room enters heating below the target and
leaves it at target + hysteresis. A room sitting exactly on its target therefore does not flap.
The same logic mirrored for cooling.

### Setpoint clamping

The units advertise `min_temp: 16`, `max_temp: 30`, `target_temp_step: 1`. Two consequences that
v3 got wrong and shipped:

- The frost branch commanded a setpoint of **7 °C**, which the hardware cannot accept.
- Room helpers had a 0.5 step, so **half-degree values** were also unacceptable.

In both cases the unit keeps its old setpoint and every later tick reads as divergence — a
permanent, silent fault that would eventually trip the breaker for a reason nobody could see.
v4 rounds every commanded setpoint to a whole degree and clamps it into the unit's own
advertised range, so frost commands `heat` at **16**. The frost *trigger* stays at 7: the
threshold at which we act and the setpoint we are able to send are different things.

### Actuation discipline

- **Mode first, setpoint second, and never in the same tick.** These units reject setpoint
  changes while off, so a setpoint sent alongside a mode change is swallowed and then reads as
  a fault. The setpoint step requires the mode to already match.
- **Preset last, cooling only, and outside the convergence test.** Wind-free is a
  **cooling-only** feature on these units: it is not offered in heat mode, most plausibly so the
  plastic diffuser mesh never sits behind hot coils. The automation therefore asserts
  `wind_free` / `wind_free_sleep` **only when the unit is confirmed to be in `cool`**, and in
  heat, dry and fan-only it leaves the preset exactly as it found it — that setting is not ours
  to own outside cooling.

  There is also nothing to clean up: **the units manage the transition themselves**, switching to
  a different preset on a heat start so the mesh opens (operator-confirmed, and observed live on
  the Living room unit moving `none` → `quiet` after a heat start). A guard here would have meant
  issuing a preset call — the most dangerous call in this integration, §2 — to defend against a
  state that cannot occur.

  The preset is also not part of `converged`: a unit that silently drops wind-free should not be
  isolated from temperature control over it.
- **Nothing at all is issued** for `skip` (no usable temperature) or `manual` (a person has the
  room). These are not "command off" — they are "do not touch".

## 4. Data model

55 helpers, split across two pages by how often they are touched. The **Climate** view carries
only the day-to-day controls: the master switch, the house-mode band, and per room its Maintain
toggle, Air filter toggle and Day/Night targets. Everything set once — the night window, the away
safety band, the safety master and frost/hysteresis, sensor calibration, the circuit breaker and
the manual-hold list — lives on a **subview** at `/lovelace/climate-advanced`, reached by one
button and absent from the tab bar.

The split deliberately leaves the *live state* behind on the main view: a single status line that
names any isolated room, any live manual hold, an inverted house band or a disabled safety master,
and otherwise renders one reassuring line. Moving the controls out of sight must not move the
symptoms out of sight with them.

The ones an operator is meant to tune are on the Climate view; `climate_ha_started`, `climate_cmd_<room>` and `climate_safety_alert_<room>` are **machine-written bookkeeping** and are deliberately NOT on it — hand-editing them would make the restart guard, the in-flight clock or the alert throttle classify on fiction. **No helper sets `initial:`** — that would
discard the restored value on every HA restart and silently reset the operator's settings.

| Group | Helpers | Default |
|---|---|---|
| Master | `input_boolean.climate_auto` | on |
| Safety master | `input_boolean.climate_safety_always` | on |
| Per room, enable | `input_boolean.climate_room_<room>` ×5 | on for Living room / Office |
| Per room, air filter | `input_boolean.climate_air_filter_<room>` ×5 | off |
| Per room, day target | `input_number.climate_target_day_<room>` ×5 | 22 °C |
| Per room, night target | `input_number.climate_target_night_<room>` ×5 | 20 °C |
| House mode | `input_number.climate_heat_below_outdoor` | 17 °C |
| House mode | `input_number.climate_cool_above_outdoor` | 20 °C |
| Away band | `input_number.climate_away_min` / `_away_max` | 18 / 30 °C |
| Frost | `input_number.climate_frost_override` | 7 °C |
| Hysteresis | `input_number.climate_hysteresis` | 1 °C |
| Sensor bias | `input_number.climate_ac_sensor_offset` | −2 °C |
| Breaker | `input_number.climate_breaker_threshold` | 3 ticks |
| Settle | `input_number.climate_command_settle` | 240 s |
| Manual hold | `input_number.climate_manual_hold_hours` | 2 h |
| Per room, failures | `counter.climate_fail_<room>` ×5, `restore: true` | 0 |
| Per room, manual until | `input_datetime.climate_manual_until_<room>` ×5 | past |
| Per room, last command | `input_datetime.climate_cmd_<room>` ×5 | 2000-01-01 |
| Away stamp | `input_datetime.climate_away_since` | — |
| Night window | `schedule.climate_night` | 22:00–06:00 |
| HA start stamp | `input_datetime.climate_ha_started` | 2000-01-01 |
| Per room, safety alert stamp | `input_datetime.climate_safety_alert_<room>` ×5 | 2000-01-01 |

Room targets use a **step of 1 °C**, matching `target_temp_step` on the hardware. A half-degree
value is not a setpoint these units can hold, so offering one in the UI would be a lie.

`input_datetime.climate_ha_started` is written by a second, one-line automation
(`automation.climate_stamp_ha_start`) on the `homeassistant` `start` event. The loop needs it
because a climate entity's `last_changed` does **not** survive a restart — see §16, P1. It is
seeded to 2000-01-01 so that on a long-running instance the restart guard is inert, and it
becomes accurate the first time HA restarts.

`input_datetime.climate_cmd_<room>` is seeded to **2000-01-01**, not left at its creation
default. A freshly created `input_datetime` reports *today 00:00* and is never `none`, so "we
have never commanded this room" is otherwise indistinguishable from "we commanded it at
midnight" — which would make any mode change earlier the same day look like a person at the
wall, and would make the in-flight window briefly true just after midnight every night.

### The room list is an allow-list

The automation addresses exactly five `climate.*` entities, named literally in `actions[0]`. The
gas boiler and its thermostatic valve entities are configured entirely outside this automation
and must never be added. The boiler is the winter failsafe: it holds a low baseline (~18 °C) and
the AC lifts rooms to comfort on top. The two do not fight, because the TRV closes once the room
is above its own setpoint.

## 5. Implementation shape

One automation, `automation.climate_maintain_per_room_targets`, `mode: single`,
`max_exceeded: silent`.

**Triggers:** `time_pattern` every 10 minutes; state triggers on the master switch, the five
room toggles, the schedule and the alarm; and state triggers on all 16 numeric helpers so that
moving a dashboard slider applies immediately rather than at the next tick.

**Condition:** `input_boolean.climate_auto` is on.

**Actions:** compute globals → `repeat.for_each` over a literal list of five room dicts
(`climate`, `sensor`, `fallback`, `enable`, `heat`, `cool`) → per room, resolve temperature,
thresholds and mode → three guarded service calls.

One looped automation rather than five copies. This costs a templated `target.entity_id` and
template conditions, which the config API flags as best-practice warnings. The trade is
deliberate and recorded in the automation's `description`: five duplicated automations drift
apart the first time someone edits one.

### Circuit breaker (v3)

The integration is shared across all five units, so a single unit that stops obeying can keep a
failing command in flight every 10 minutes forever and risk rate-limiting the other four.

Failure is detected by **divergence, not by exception**: HA's service calls do not reliably
report whether a cloud device actually complied, so the breaker compares *commanded* against
*observed* on the following tick.

```
converged := unit's reported mode == the mode we want
may_act   := mode != skip AND unit reachable AND NOT converged
             AND (fail_count < breaker_threshold OR this is the frost override)

on every command issued:      counter.increment
when fail_count+1 == threshold: notify once (persistent notification + phone)
on the first converged tick:   counter.reset, dismiss the notification
```

Properties:

- **Counting is independent of commanding** (v3.1). The counter advances on every divergent
  tick whether or not a command went out, so it measures the *age* of the divergence. It is
  cleared by the first tick where the unit reports the mode we asked for.
- **Throttle, not lockout** (v3.1). Past the threshold the room retries every 6th tick
  (~hourly) instead of never. v3 suppressed commanding entirely once tripped, which was a
  **liveness trap**: no command meant the unit could never converge, which meant the counter
  could never clear, which meant a slow-but-compliant unit was locked out permanently. Round 2
  caught this; the claim "recovery is automatic" was false as written.
- **The safety band bypasses the breaker entirely**, at full rate. Giving up on a room outside
  the operator's hard limits is the one failure that actually matters.
- **Recovery needs no manual reset**, though the counters are on the dashboard with
  `counter-actions` so one can be cleared by hand.
- **Notification fires exactly once** per trip, because the counter only resets on convergence, so
  counter stops advancing.
- Notification uses `notify.send_message` with `entity_id: notify.vadims_iphone_17`. The bare
  `notify.vadims_iphone_17` *service* does not exist — that name is an entity of the newer
  entity-based notify platform, and the config API's service-registry validation catches the
  mistake.

---

## 6. Verification method

The automation is gated on a master switch and was first handed over **off**. Every change is
proven by replicating the decision expression in `ha_eval_template` against live state and
printing the per-room verdict — **no actuation**.

**Never dry-run with `automation.trigger`.** It skips conditions by default, so it runs the
actions *and ignores the master switch* — actuating the hardware you were trying not to touch.

v2 was signed off on a single all-off sample, which the review correctly called out: it proved
the lockout and dead-zone paths and exercised none of the branches under attack. v3 is verified
across the whole matrix.

> **The table below is the v3 record and its verdicts are v3 verdicts.** It is kept because the
> reasoning behind each case is still the reasoning, but the setpoints in it (`20.5`, `25.0`,
> `HEAT→7`) belong to the two-threshold model and do not exist in v4: the day target is 22, the
> night target 20, frost clamps to 16 and the away floor is 18. **The v4 verification record is
> the 17-case table in §16**, plus the live pass above it. Round 5 (P7) was right that leaving
> this table unlabelled made the document appear to prove v4 with v3 evidence.

| Case | Input | Verdict |
|---|---|---|
| Heat entry | 20.4 °C, currently off | `HEAT→20.5` |
| Heat hold (hysteresis) | 20.6 °C, currently heating | `HEAT→20.5` — no longer flaps |
| Heat exit | 21.6 °C, currently heating | `off` |
| Cool entry | 25.1 °C, outdoor 28 | `COOL→25.0` |
| Cool hold | 24.9 °C, currently cooling | `COOL→25.0` |
| Cool exit | 23.9 °C, currently cooling | `off` |
| Away + cold outdoors | away, 31 °C, outdoor 12 | `off` — v2 gave `COOL→30` |
| Away + hot outdoors | away, 31 °C, outdoor 28 | `COOL→30` |
| Away + warm outdoors | away, 17 °C, outdoor 24 | `off` — v2 gave `HEAT→18` |
| Away + genuinely cold | away, 17 °C, outdoor −5 | `HEAT→18` |
| Master off, frost | comfort off, 5 °C | `HEAT→7` |
| Master off, mild | comfort off, 15 °C | `off` |
| Master off, overheat | comfort off, 31 °C, outdoor 28 | `COOL→30` |
| Disabled room, frost | disabled, 5 °C | `HEAT→7` |
| Disabled room, safety band | disabled, 15 °C, outdoor −5 | `HEAT→18` |
| Frost beats everything | comfort off + away + disabled, 3 °C, outdoor 25 | `HEAT→7` |
| Bedroom bias, comfort | raw 20.0 → corrected 18.0 | `HEAT→20.5` |
| Bedroom bias, safety | raw 19.9 → corrected 17.9, disabled | `HEAT→18` |
| Breaker, below threshold | fail_count 0–2, not converged | commands, increments; notifies at 2→3 |
| Breaker, tripped | fail_count ≥ 3, not converged | no command issued |
| Breaker, frost room | fail_count 9, below frost floor | commands anyway |
| **Manual — human at the wall** | converged (fc 0), unit turned off, we want heat | `human_moved` → hold stamped + notified |
| **Manual — human picks another mode** | converged (fc 0), unit set to `dry`, we want off | `human_moved` → hold stamped |
| **Manual — our own command in flight** | fc 1, unit still reports `cool`, we commanded `heat` | **not** human — keep trying |
| **Manual — still in flight** | fc 2, same | **not** human |
| **Manual — gave up** | fc ≥ breaker, unit will not move | treated as human/back-off either way |
| **Manual — hold live, comfort** | hold live, 21.0 °C | `MANUAL` — nothing issued |
| **Manual — hold live, below floor** | hold live, 17.0 °C | `HEAT→18.0` — safety outranks the hold |
| **Manual — hold live, frost** | hold live, 8.0 °C | `HEAT→18.0` (and `HEAT→7` below 7) |

Live confirmation after each deploy: both automations on, all five units `off`,
`sensor.ac_power_total` 12 W standby, 12–13 °C outdoors, all five failure counters at 0, no
manual holds, no persistent notifications, and no climate errors in the core log.

---

## 7. What v1 got wrong

v1 shipped with **one setpoint per mode** (day 22, night 19) and a symmetric deadband, plus a
"season guard" derived from the day's forecast high.

Enabled at 23:11 with **13.6 °C outdoors and a clear sky**, it set Living Room (23.7 °C) and
Office (23.4 °C) to **cool, target 19 °C**.

Four compounding errors:

1. **One number doing two jobs.** The night value of 19 was authored as a sleep *floor* — don't
   let the room fall below this — and read by the code as a cooling *target*. A single setpoint
   silently makes the heating target double as the cooling target. This is the root cause.
2. **No outdoor lockout.** Nothing in the logic knew that 13.6 °C air outside makes a compressor
   the wrong tool.
3. **The season guard keyed off the forecast daily high**, which is meaningless at 23:00. It saw
   ~20 °C, classified a "shoulder day", and permitted cooling on a cold night.
4. **The target was the setpoint**, so a room 1 °C outside the deadband was driven all the way
   across the dead zone rather than just back to the threshold.

The lesson, stated generally: *when a system can both add and remove a quantity, model the two
thresholds separately and treat the gap between them as a first-class "do nothing" region.* And
gate any actuator against the free alternative — ventilation, solar gain, thermal mass — before
running it.

---

## 8. Rejected alternatives

| Option | Why not |
|---|---|
| **Single setpoint + deadband** | Shipped as v1; failed as above. Conflates two independent decisions. |
| **Forecast-driven season guard** | Wrong signal for a cold night, and redundant once outdoor lockouts exist. Removing it also removed a dependency on `weather.get_forecasts` and one failure mode. The operator's underlying want — hot days cooled, cold nights warmed — is served better by current outdoor temperature plus separate thresholds. |
| **Per-room night thresholds** (20 helpers) | Doubles the helper count and the dashboard for a setback that is uniform in practice. |
| **`generic_thermostat` helper** | Designed to bang-bang a dumb switch. These units are already thermostats; wrapping them would fight their own control loop. |
| **Five separate automations** | No templated targets, no API warnings — but they drift apart under maintenance. |
| **Controlling from AC internal sensors throughout** | Measured ~2 °C high. Would bake the comfort error the project exists to fix. |
| **Presence-based control** | No sensors. Alarm state is the available proxy and the household already arms it. |

---

## 9. Review findings closed in v3

An adversarial review of the v2 document (`review-20260918-f974.md`) raised nine findings. Eight
were valid and are closed; one was disputed with evidence.

| # | Finding | Disposition |
|---|---|---|
| F1 | Dead zone has no hysteresis at its edges; writing the threshold as the target makes the unit hold exactly the boundary, so a room resting there hunts | **Fixed** — exit-only hysteresis, default 1.0 °C |
| F2 | Mode is recomputed on a 10-min tick and on helper changes, but **not** on the control sensors changing, so a real crossing waits up to 10 min | **Fixed** — state triggers on the two good meters. AC probes excluded: too noisy to trigger on |
| F3 | The away branch bypassed *both* lockouts, so it would cool a 31 °C room at 12 °C outdoors with nobody home to open a window | **Fixed** — only the frost override bypasses lockouts now |
| F4 | The "fails in the safe direction" claim covered only the dog-walk case; a restart during a genuine long absence re-arms the hold and runs comfort control in an empty house | **Fixed** — persisted `input_datetime` stamp; both failure directions now documented |
| F5 | The Bedroom's +2 °C bias propagates into the *safety* band, so the 18 °C cat floor was a true ~16 °C | **Fixed** — offset applied before every comparison |
| F6 | "The frost floor is alarm-gated for enabled rooms" | **Disputed.** Verified false: enabled room, alarm not armed, outdoor −5 °C, room 10 °C → `HEAT→18.5`. Enabled rooms are covered by the comfort heat threshold, which sits *above* the 18 °C floor. **Its secondary point was valid and is fixed**: everything hung off `climate_auto`, so switching it off silently removed every floor |
| F7 | No availability check before actuating; no isolation for a persistently failing unit | **Fixed** — guards skip `unavailable`/`unknown`; per-room circuit breaker added |
| F8 | Mode-then-setpoint race: these units reject `set_temperature` while off, so the setpoint is silently dropped | **Fixed** — setpoint and preset only issued once the unit is already in the commanded mode |
| F9 | `night_cool_setback` accepted a positive value, which would invert the intended night direction | **Fixed** — max clamped from +2 to 0 |

---

## 10. Round-2 review: what it found in v3

The v3 document was re-reviewed (`review-20260918-28a8.md`) with an explicit instruction not to
confirm its own fixes. It found that two v3 "fixes" had **moved** their finding rather than
closed it, and that the new circuit breaker introduced three problems of its own.

| # | Finding | Disposition |
|---|---|---|
| A3 | Making away respect the lockouts opens an empty-house overheat/overcool gap with no recourse — the lockout premise "open a window" assumes a human present | **Fixed in v3.1** — safety band made universal and unconditional |
| A8 | The F6 dispute was literally right about the *frost* floor but missed that an enabled room with heating locked out has no floor between 7 °C and 20.5 °C | **Fixed in v3.1** — same change; verified `enabled, 12 °C, outdoor 20 → HEAT→18` |
| A5 | Breaker liveness trap: once tripped no command is issued, so the unit can never converge, so the counter never clears — recovery was **not** automatic | **Fixed in v3.1** — counting decoupled from commanding, hourly re-arm |
| A1 | Hysteresis uses the unit's reported mode as state memory, so it silently assumes the unit reports within one tick; cloud latency can produce a HEAT→OFF→HEAT flap | **Open** — needs a per-room "commanded since" stamp |
| A2 | A human changing the mode at the wall is co-opted as hysteresis state, so the automation overrides them silently | **Open** — needs an explicit manual-override policy |
| A4 | A human wall change looks identical to a failing unit, so it can trip the breaker and send a false alert | **Open** — related to A2 |
| A6 | `converged` is defined on mode only, so a unit that accepts the mode but silently drops the setpoint (the F8 failure) never trips the breaker | **Open** |
| A7 | The safety bypass re-opens unbounded retry for a genuinely broken unit, and the one-shot notification then goes silent on an ongoing safety failure | **Open** — wants backoff plus escalating re-alert |
| A9 | Away-stamp lifecycle unspecified in the doc | **Doc gap only** — verified the stamping automation triggers `to: armed_away`, so it does re-stamp on every re-arm. Behaviour correct, documentation wasn't. |
| A10 | F2's "fixed" overstated coverage: sensor triggers exist only for the two metered rooms | **Accepted** — see limitations |
| A11 | One global −2 °C offset applied to three different units assumes uniform bias, measured on only one | **Accepted** — see limitations |

The lesson from A3 in particular: **a hard limit and an efficiency heuristic must not share a
code path.** v2 had the safety band bypassing the lockouts, round 1 said that was wrong, v3
subordinated safety to the lockouts, round 2 showed that was worse. The resolution is that they
are different *kinds* of rule — limits are absolute, lockouts are optimisations — and the design
now separates them structurally rather than ordering them.

---

## 11. Manual control, and the gas boiler (v3.2, corrected in v3.3, rebuilt in v4)

### Manual changes at the wall win

If someone walks to a unit and changes it, that person is standing in the room and this
automation is not. Their change wins for `climate_manual_hold_hours` (default 2 h), during
which the room gets **no mode, no setpoint, no preset** — only the safety band still acts, and
only on the terms in §16.

The hard part is telling a person apart from a unit that will not comply. Both present
identically: the unit reports something other than what we asked for.

**v3.3 used the failure counter as a "command in flight" clock** — `fail_count == 0` meant
converged so any divergence was external, `0 < fc < breaker` meant our command was still landing.
Round 4 (R4-2) showed this is not what the counter measures. It counts the **age of divergence**,
regardless of cause. It can read non-zero with nothing of ours pending, and zero with a command
genuinely in flight across a restart, because the counter has `restore: true` and the increment
that would have recorded the command can be lost. Worse, R4-1 showed the two mechanisms sharing
that counter were incompatible: at `fc >= breaker` the rule stamped a 2 h hold, the hold
suppressed all commanding including the hourly re-arm, the counter kept climbing, and on expiry
the same condition re-stamped a fresh 2 h hold — forever.

**v4 records the thing the design actually needs.** Every command writes
`input_datetime.climate_cmd_<room>`. From that:

```
since_cmd   = now - cmd_stamp                     # how long ago WE commanded
in_flight   = since_cmd < settle                  # our command has not had time to land
lc          = now - climate.<room>.last_changed   # how long ago the UNIT changed state
uptime      = now - ha_started                    # how long HA has been up

unit_moved  = lc < since_cmd        # the unit changed AFTER we commanded
          and lc < human_window     # ...and recently, in absolute terms
          and lc < uptime - 60      # ...and not merely because HA restarted

human_moved = diverged and not in_flight and unit_moved
fault       = diverged and not in_flight and not unit_moved
```

The third term is the v4.1 restart guard and is not optional; it was added after round 5 (P1)
and proved necessary in production the same hour — see §18.

The asymmetry that makes this work: **a unit that is ignoring us never changes state.** It
cannot produce `unit_moved`, so it can never masquerade as a person. A person, by definition,
changes the unit's state after our last command.

`human_window` (1200 s, two ticks) is the second term and is not optional. Without it, a room we
have never commanded reads its stamp as today 00:00 — an `input_datetime` is never `none` once
created — and any mode change made earlier that day looks like someone at the wall.

The third term bounds the asymmetry above, which holds only **within one continuous uptime**: a
climate entity's `last_changed` does not survive a restart, so after a reboot every unit looks
like it "just changed". See §18 for the production measurement.

Consequences of the rebuild:

- **The counter is now reset when a human is detected.** v3.3 deliberately did not, because it
  could not tell a fault from a person and a stuck unit would otherwise have masqueraded as one
  on every cycle (M3). v4 can tell them apart, so the reset is correct — and it is what removes
  the R4-1 trap at the root: a breaker trip no longer stamps a hold at all, so there is nothing
  to re-stamp on expiry and the hourly re-arm is never starved.
- **Divergence is only counted after the settle window** and never on a tick where we issued a
  fresh command, so the counter measures the unit failing to comply and nothing else.
- **Convergence now includes the setpoint** (see §16, R4-5).


### The gas boiler is a baseline, and this automation knows nothing about it

The boiler is configured **entirely outside** this automation and is the winter failsafe. Its TRVs
hold a **low baseline (~18 °C)**; the AC still lifts rooms to the comfort target on top.

> the boiler will be set to a lower temperature than comfortable - i still expect heating via the
> climate control automation - i.e the valves will be set for 18C but ill want 22 during the day

The two do not fight: the TRV simply closes once the room is warmer than its own setpoint. No
coordination is required, and **no per-room boiler configuration is kept here** (v3.4).

That last point took two wrong turns to reach:

1. **v3.2** added `climate_boiler_heats_<room>` and had it suppress the AC's own 18 °C safety-band
   heating, on the grounds that the boiler already covered it.
2. **Round 3 (M5)** rejected that: the flag is a *claim* about the boiler, not *evidence*. It knows
   nothing about whether the boiler is running, powered, off for the summer, or whether a TRV's
   battery is dead — and the boiler was not even installed. Flipping the toggle would have left the
   7–18 °C band unprotected, and with the Bedroom's sensor bias a **true 8 °C** room reads corrected
   8, above the 7 °C frost override, so nothing would have heated it. v3.3 made the flag inert.
3. **v3.4** deleted it. An inert toggle on a dashboard is worse than no toggle: it invites someone
   to flip it expecting an effect. The operator called it correctly — the setting was redundant
   with what the boiler already knows, and it complicated both the config and the UI.

The general lesson, which is the same one §14 draws from three rounds: **a configuration flag that
asserts something about the world is not evidence about the world.** If the automation needs to
know whether the boiler is heating a room, that must come from an entity it can observe. Until such
an entity exists, the correct amount of boiler configuration here is none.

**One invariant the automation still cannot enforce** (M6): the no-fight property holds only while
each TRV setpoint stays *below* the room's own AC target — in v4 terms, below the **night target**
(20 °C), since that is the lower of the two and applies while the TRV is most likely to be the
active heat source. Set a TRV to 22 °C and the two heat sources alternate: the AC heats to its
target and stops, the TRV opens and drives higher. **Operator constraint: keep every TRV setpoint
at or below the room's night target.** This automation cannot see TRV setpoint drift, which the
containment note below makes a safety property and a blind spot at the same time.

**Containment.** The room list is an explicit **allow-list** of the five `climate.*` AC entities,
stated in a `note` on the variables block. No boiler or TRV entity is reachable from this
automation, and none may be added to that list.

---

## 12. Known limitations and next steps

- **Bedroom has no independent sensor.** It controls on its AC's internal reading and will be
  ~2 °C off until a real sensor is added. Living Room and Office are fine.
- Two unplaced SwitchBot Outdoor Meters are earmarked for Kids room 2's and Kids room 1's rooms. Placing them
  upgrades two more rooms from AC-internal to measured — now a functional requirement, not
  tidiness.
- **Stale unit setpoints.** Living Room and Office still hold `target: 19` from the v1 incident.
  The units reject `climate.set_temperature` while powered off, so this clears only when the
  automation next actuates, or by hand. A manual power-on before then would cool to 19. (This is
  the same behaviour F8 documents; v3 defers the setpoint by one tick rather than losing it.)
- No electricity-price awareness. The Czech spot-price integration is installed but produces no
  entities.
- The dead zone is wide by design (4.5 °C by day). If rooms feel unattended, narrow the gap
  before touching anything else — that is the intended tuning knob.
- Cloud dependency: a SmartThings outage means no actuation. The units keep their last setpoint,
  which is a safe failure mode. The circuit breaker limits the blast radius of a *single* failing
  unit but does nothing for a whole-integration outage — every room simply trips in turn.
- The breaker counts divergence, not HTTP failures, so a unit that reports the commanded mode but
  does not physically act (a mechanical fault) is invisible to it. It is also blind to setpoint
  and preset divergence (A6) — only `hvac_mode` is compared.
- Hysteresis state still lives in the unit's reported mode, so it assumes the unit reports back
  within one tick (A1) — the same assumption the override detector had until v3.3 fixed it there.
  A per-room "commanded since" stamp would close both properly. A2/A4 are resolved: a human change
  is now recognised and can no longer trip the breaker.
- **The TRV-setpoint invariant is unenforceable** (M6): the automation cannot see a TRV set above
  its own heat threshold, which would make the two heat sources alternate.
- The 18 °C floor now outranks a manual hold. That is a deliberate reading of two requirements
  that conflict ("manual should win" vs "18 °C for the cats") and is trivially reversible if the
  operator prefers the other side.
- ~~Sensor state triggers cover only the two metered rooms (A10).~~ **Closed in v4** — all five
  room temperature sensors are state triggers, so the three AC-probe rooms no longer wait for the
  tick.
- The −2 °C AC offset was measured on one unit and is applied to three (A11). Return-air bias
  depends on mounting and airflow, so per-unit calibration would be more honest.
- Safety retries are unbounded by design; a permanently broken unit in a freezing room will be
  commanded every 10 min forever and will alert only once (A7).
- `schedule.climate_night` must be edited in 14 places (7 days × 2 blocks) because HA schedules
  cannot express a window crossing midnight. There is no single editable night range.
- ~~The stated day comfort target is 22 °C but every room is seeded at 20.5.~~ **Resolved by v4** —
  the two-threshold pair is gone and every room is seeded at the stated 22 °C day / 20 °C night.
- **55 helpers and one ~100-step run.** The automation is at the size where a decide/act split — a
  template entity publishing each room's verdict, with a thin automation applying it — would make
  the decision continuously inspectable instead of only visible in a trace. See §13.
- Thermostatic valve entities are coming. If they are read-only they become the best control
  sensor for the three rooms still on AC return-air probes, closing the single-offset assumption
  and the tick-bound latency for those rooms at once.

---

## 13. Should this be a blueprint?

Considered and **declined**, for now. HA's own guidance is explicit: *"Author a blueprint only when
a pattern will be instantiated more than once or shared/distributed. A one-off automation should
stay a plain automation."* Its decision table lists *"a single automation for one specific set of
entities"* as a **No**.

The motivation was size, and a blueprint does not reduce size — it adds an input schema on top of
the same logic. Three specific frictions make it a poor fit here:

1. **`!input` cannot appear inside a template.** It is a YAML tag, not a value; every input must
   first be bound to a `variables:` entry. This automation is almost entirely Jinja — the whole
   decision law is one expression — so every parameter would need a binding layer that buys
   nothing.
2. **The room list is a list of records**, eight fields each. No selector expresses that. The only
   blueprint shape that works is *one instance per room*, which turns one 87-step run into five
   automations that each re-evaluate the shared globals (night window, alarm, outdoor temp,
   lockouts) — five runs per shared-entity change instead of one.
3. **The globals would have to be inputs too**, repeated across five instances, or hardcoded by
   entity_id inside the blueprint — which defeats the portability that is the only reason to
   blueprint in the first place.

A blueprint would be right if this logic were going to other houses. It isn't.

### The decomposition that would actually help

Split **decide** from **act**:

- A template entity per room (or one with per-room attributes) publishes the verdict — `mode`,
  `target`, and why.
- A thin automation applies it: for each room, if the verdict differs from the unit's state, issue
  the guarded calls.

This is worth doing because it converts the thing that has been hardest all along — *seeing what
the logic decided without actuating anything* — from a manual `ha_eval_template` exercise into a
permanently visible entity. Every verification table in §6 was produced by hand-replicating the
decision expression; a template entity makes that the live artifact instead of a copy that can
drift from the automation it claims to describe.

**One correction to that framing**, from round 3: a template entity is *read-only*, so it cannot
own any of this system's state. The circuit-breaker counters, the manual holds, the away stamp and
the counter resets all stay on the act side. The split is therefore smaller than "thin automation"
suggests — it moves the *decision* out, not the *state machine*. Plan it against that real
surface, or the act automation will end up nearly as large as today's with a template entity
bolted on beside it.

Deferred, not rejected: it is a rewrite of a safety-relevant automation that has been through
three adversarial reviews, and it should be done deliberately rather than at the end of a long
night.


---

## 14. Round-3 review: what it found in v3.2

`review-20260918-ff7e.md`. Both v3.2 additions — the manual override and the boiler flag — were
found to have safety holes, and two round-1/round-2 fixes were found to have been regressed.

| # | Finding | Disposition |
|---|---|---|
| M1 | The override detector read the automation's **own in-flight command** as a human, because mid-round-trip the unit still reports its old mode. A sensor-triggered run would stamp a false 2 h hold. | **Fixed in v3.3** — detection now keyed to the failure counter as a command-in-flight clock |
| M2 | "Anything that isn't `off`" swept in `auto` / `dry` / `fan_only`, which these units genuinely report | **Fixed** — subsumed by the same change |
| M3 | Detection **reset the failure counter**, so a unit stuck reporting an active mode masqueraded as a human forever: breaker never tripped, alert never fired | **Fixed** — the counter is no longer reset; it freezes during a hold and clears on genuine convergence |
| M4 | A wall-off was fought for 30 min before being respected | **Fixed** — respected on the first divergence from a converged state |
| M5 | The boiler flag suppressed the 18 °C floor on a **claim**, with the boiler uninstalled and zero TRV entities in existence — leaving 7–18 °C unprotected, and (with the Bedroom bias) a true 8 °C room unheated | **Fixed** — the flag no longer suppresses anything; it records intent until a TRV entity can serve as evidence |
| M7 | `manual > safety` let an aired room sit at **8 °C for two hours** | **Fixed** — precedence is now frost > safety > manual > comfort |
| M8 | `manual` appeared in the predicate but not in the §3 control law, so the precedence claim was unverifiable from the spec | **Fixed** — §3 pseudocode now carries the branch |
| M9 | The verification matrix had **no v3.2 cases** — the doc's own method was not applied to its newest behaviour | **Fixed** — 12 manual/boiler cases added to §6 |
| M10 | §4 omitted all 11 v3.2 helpers and quoted "23/34" against a real 45 | **Fixed** — table and count reconciled |
| M11 | A 2 h blackout was invisible; combined with M3 a fault could be silent *and* look deliberate | **Fixed** — hold now notifies, and says whether it followed failed commands |
| M6 | The AC/TRV no-fight property depends on the TRV setpoint staying below the AC heat threshold, which this automation cannot see | **Accepted** — documented as a hard operator constraint in §11 |

**The pattern worth naming.** Three rounds, and the same shape each time: a rule that is correct
in the common case is given authority over a rule that is absolute. v1 let one setpoint serve as
both a heating and a cooling target. v3 let an efficiency lockout outrank a hard limit. v3.2 let a
human's convenience outrank the same limit, and let a *claim* about equipment outrank it too.

The invariant this design keeps re-learning: **absolute limits sit at the top of the precedence
order and take no arguments** — not from an optimisation, not from a person's last click, not from
a configuration flag asserting that something else has it covered. Everything else negotiates
below them.

---

## 15. Round-4 review: what it found in v3.3

Review artifact `review-20260919-2a9b.md`. It was asked, as every round has been, to assume the
previous round's fix had *moved* the finding rather than closed it. It had.

| # | Finding | Status in v4 |
|---|---|---|
| R4-1 | The counter-clock reintroduces A5's liveness trap: at `fc >= breaker` a 2 h hold is stamped, the hold suppresses all commanding including the hourly re-arm, the counter keeps climbing, and expiry re-stamps a fresh hold — permanently | **Closed at the root.** The breaker no longer stamps holds at all; `human_moved` has no `fc >= breaker` arm. See §11 |
| R4-2 | `fail_count` is not a command-in-flight clock; it measures divergence age. A human change arriving while `fc > 0` is fought to saturation | **Closed.** Replaced with a real command timestamp per room. See §11 |
| R4-3 | Command and counter-increment are not atomic; an HA restart between them leaves `fc == 0` with a command in flight, and the automation stamps a hold on its own command | **Closed** by the same mechanism — the stamp is written with the command, and a restart cannot make it lie about *when* |
| R4-4 | Safety > manual with no escape hatch: a person airing a room in winter is fought every 10 min, indefinitely, silently | **Closed**, two ways. See §16 |
| R4-5 | `converged` is mode-only, so a unit that accepts the mode and silently drops the setpoint looks converged forever — no breaker trip, no alert | **Closed.** `converged` now covers the setpoint |
| R4-6 | §5's "notification fires exactly once *because commanding stops at the threshold*" contradicts two other stated properties; commanding does not stop | **Closed.** The one-shot property comes from the counter not resetting without convergence, and the doc and the automation now say so |
| R4-7 | Three reachable cases missing from the 33-case matrix: hold-expiry-with-fc-still-over-threshold, restart-with-command-in-flight, human-change-racing-in-flight | First two are **unrepresentable in v4**; the third is covered by the settle window. New matrix in §16 |
| R4-8 | The boiler flag is an inert dashboard control that lies about a capability | **Moot** — deleted in v3.4, before this review was read |
| R4-9 | §4 lead-in said "23 helpers" where the count was 45; away-age test ambiguous between the persisted stamp and `last_changed` | **Fixed.** §4 states 50 and the count is derived from the live helper list; the away test reads the persisted stamp, with `last_changed` only as a fallback when no stamp exists |

Two findings were **not** accepted as stated:

- R4-2's suggested fix and R4-5's were treated as one mechanism, not two, because the command
  stamp closes both.
- R4-7's framing assumed the cases needed to be *added*. Two of them describe states v4 cannot
  reach, and a verification case for an unreachable state is not a test, it is a comment.

---

## 16. What v4 changed

### The control model (operator request)

Stated as: *"the heat below and cool above values — they can be global — measured against the
outside/forecast values to decide whether the home should be in cooling or heating mode… the
target temperature per room should be what we are aiming to achieve, and there should be a day
and a night setting per room… and finally, there should be a per-room option whether the AC will
start with the configured target to filter the air — even if it will do nothing."*

All four delivered, in §3. The two global numbers were not new helpers: v3's outdoor lockouts
(`no heating above` / `no cooling below`) were already exactly this test, used only to *veto*
rather than to *decide*. v4 promotes them to the decision and renames them to match what they
mean. Night stopped being a setback and became a second target. Day 22, night 20, everywhere.

**On the forecast.** The request mentioned "outside/forecast". v4 reads the live outdoor sensor
only. The 3-degree shoulder band already provides the seasonal stability a forecast would, and
`weather.get_forecasts` is a service call with a response variable — a network dependency inside
a control loop that runs every ten minutes, which would need its own failure handling. If the
house is seen flipping mode around dawn or dusk, widening the band is the cheaper fix and the
first thing to try.

### The safety escape hatch (R4-4)

Safety still outranks a manual hold — M7's reasoning has not changed, a room must not sit at
8 °C for two hours because someone pressed a button. But v4 stops that being a silent,
unbounded fight:

1. **While a manual hold is live, the safety band re-asserts at most once per `retry_throttle`
   (3000 s)**, not every ten minutes, and sends a notification saying so and naming the way out.
   Airing a room in winter now costs one interruption roughly hourly instead of six.

   The throttle is measured **from our own last command to that room**, not from a wall-clock
   window. The first attempt used `now().minute // 10 == 0`, which is wrong for a reason worth
   recording: this automation is triggered by state changes as well as by the `/10` time
   pattern, so a "`:00`–`:09`" window can be *entered many times*, and the only thing limiting
   the repeats would have been the 120 s settle — about five commands per hour, not one. A rate
   limit has to be measured against the thing being rate-limited. The circuit breaker's re-arm
   uses the same interval, for the same reason.

   The *notification* went through two further corrections, both recorded because the second
   reverses the first. Gating it on the throttle alone was wrong: when the unit already complies
   no command is sent, so no stamp is written, the throttle never closes, and the push would have
   repeated every ten minutes while nothing was being overridden. Gating it on `may_act` — "a
   command was actually issued" — fixed that and introduced a worse fault, because `may_act` is a
   statement about the automation rather than about the flat: it is false when the unit is
   unreachable and false when the unit is nominally converged, which are exactly the two
   situations a person most needs to hear about. **The alert is now driven by the safety
   condition itself**, throttled by its own per-room stamp. See §19, R6-4.
2. **`climate_safety_always` is now a true master hatch.** In v3 it was documented as disabling
   the frost override only, leaving the 18/30 band undisableable. In v4 all three safety branches
   are gated on it. One switch turns off every unconditional action in the system.

The general principle, unchanged since §14: absolute limits sit at the top of the precedence
order and take no arguments. What v4 adds is that an absolute limit still owes the person in the
room an explanation and a way out.

### Verification

Method unchanged and still the rule: **replicate the decision expression in `ha_eval_template`
against live state and print a per-room verdict, actuating nothing.** Do *not* dry-run with
`automation.trigger` — it skips conditions and ignores the master switch.

Live pass at 2026-09-19 09:1x, automation disabled during the migration, outdoor 14.1 °C
(house = HEATING), all five rooms 22–23 °C against a day target of 22:

```
Living room: 23.0  off@19 => off   converged, nothing to do
Office:      22.9  off@19 => off   converged
Bedroom:     23.0  off@20 => off   converged, room disabled
Kids room 1:         22.0  off@20 => off   converged, room disabled
Kids room 2:         22.0  off@20 => off   converged, room disabled
```

This is the v1 incident's exact weather and room temperatures, and v4 runs nothing. Then 17
synthetic cases over the decision expression:

| # | Case | Verdict |
|---|---|---|
| 1 | Heat season, room 24, target 22, **air filter on** (the operator's own example) | `heat@22` |
| 2 | Same, air filter off | `off` |
| 3 | Heat season, room below target | `heat@22` |
| 4 | Heat season, inside exit hysteresis while heating | `heat@22` |
| 5 | Heat season, past hysteresis while heating | `off` |
| 6 | Shoulder season, air filter on | `fan_only` |
| 7 | Shoulder season, air filter off | `off` |
| 8 | Cool season, room above target | `cool@22` |
| 9 | Night target 20, room 21, heat season | `off` |
| 10 | Safety floor, master switch **off**, room 17.5 | `heat@18` |
| 11 | Frost, room 5 °C — setpoint must clamp to the unit's min | `heat@16` |
| 12 | **Hatch:** `safety_always` off, room 5 °C | `off` |
| 13 | Manual hold live, room inside the safety band | `manual` (nothing issued) |
| 14 | Manual hold live, room **below** the safety floor | `heat@18`, throttled, notified only when a command is issued |
| 15 | Room disabled, air filter on | `off` — filter never overrides Maintain |
| 16 | Away, heat season | `off` |
| 17 | Sensor dead | `skip` — nothing issued |

Cases 11, 12, 14 and 15 are the ones worth keeping: 11 is a bug v3 shipped, 12 and 14 are R4-4,
and 15 is the precedence question the air-filter feature raises.

### Still open

- **A11** — one `ac_sensor_offset` is applied to three units that were never individually
  calibrated. Unchanged; it is a single number standing in for three measurements.
- **M6** — the TRV-setpoint invariant cannot be enforced while zero TRV entities exist.
- **A7** — a safety fight is now alerted hourly rather than once, which is better than v3 but
  still not an escalation.
- Whether `heat` above setpoint actually moves air on these units, which decides if the
  in-season air-filter case should use `fan_only` instead. Needs an observation, not a decision.
- **The counter used to count our own in-flight setpoint command.** `diverged` excluded the
  tick on which a *mode* command was issued but not the tick on which a *setpoint* command was
  issued, so a room whose mode already matched and whose setpoint we were actively correcting
  scored a failure against the unit on the very tick we were fixing it. Caught live on
  2026-09-19: the Living room setpoint moved 19 → 22 and `counter.climate_fail_living_room` went
  to 1, clearing itself on the next tick. Fixed by excluding `will_set_temp` as well. Same class
  as R4-2/M1 — the automation reading its own command as the unit's fault — which had been
  closed in the mode path and left open in the setpoint path. **Third time a fix has moved a
  finding rather than closed it; assume it has happened again somewhere.**
- **A setpoint-only change at the wall is classified as a fault, not as a person.** `last_changed`
  on a climate entity moves for *mode* transitions only; a setpoint is an attribute, and attribute
  updates move `last_updated`, which the cloud integration bumps on every poll and is therefore
  useless as a human signal. So someone who leaves a unit in `heat` and only nudges the
  temperature does not trigger a manual hold — the automation re-asserts its own setpoint, the
  divergence counts, and after three ticks the breaker throttles that room to roughly hourly and
  sends an alert. The room is not fought indefinitely and the operator is told, but it is told
  "unit not obeying" when the truth is "a person disagreed". This is the honest residue of
  R4-2/M4: mode changes at the wall are now handled correctly, setpoint-only changes are
  degraded-but-bounded. Closing it properly needs a signal the integration does not currently
  expose.

---

## 17. Round-5 review: what it found in v4, and v4.1

Review artifact `review-20260919-dd64.md`. Eleven findings, P1–P11. It was the strongest round so
far, and it was right about the one that mattered.

| # | Finding | Status |
|---|---|---|
| **P1** | **The human-vs-fault test misclassifies after a restart.** A climate entity's `last_changed` does **not** survive a restart — every entity is re-created at boot and the timestamp resets to the boot instant — while the command stamp, an `input_datetime`, *is* restored. A unit that never complied then shows a tiny `lc` against a large `since_cmd` and reads as a person: a 2 h hold stamped on a fault, which starves the retry. A5 on the restart path | **Fixed.** `unit_moved` gains a third term, `lc < uptime − 60`, fed by `input_datetime.climate_ha_started` (written by `automation.climate_stamp_ha_start` on the `homeassistant` `start` event). If `last_changed` is as old as the uptime, the reboot manufactured it |
| P2 | A setpoint-only wall change is classified as a fault, because `last_changed` does not move for attribute changes | **Accepted, already documented.** The reviewer's "fights the person forever" is not accurate: `will_set_temp` is gated on `not tripped`, so the breaker halts it after ~3 ticks and alerts. Bounded and visible, but mislabelled as a unit fault. Using `last_updated` instead is not viable — the cloud bumps it on every poll |
| **P3** | The air filter commands `heat@target` in a room above target, which "heats an already-warm room" | **Rejected on the physics.** A heat pump at setpoint 22 in a 24 °C room is above setpoint and will not heat; it idles. This is also the operator's explicit specification. The open question — whether an idling unit moves any air — is unchanged and needs an observation, not a redesign |
| **P4** | The `now().minute // 10 == 0` gate is true for a whole ten-minute window, and the automation is state-triggered as well as time-triggered, so "once an hour" was really ~5 commands | **Already fixed before the review returned**, independently and for the same reason. See §16. The review also exposed a *second-order* bug in that fix — the notification was gated on the throttle, so a complying unit would have re-notified every tick. That was corrected to a command gate, which round 6 then showed was itself wrong; the alert is now condition-driven (§19, R6-4) |
| P5 | Past the breaker threshold there is no re-alert on an ongoing setpoint fight | **Confirmation of A7**, already on the open list |
| **P6** | §5 still read "notification fires exactly once *because commanding stops at the threshold*" — the R4-6 closure claimed the text was amended and it was not | **Fixed.** Correct: I marked a finding closed on the strength of an edit I had not made. The sentence now attributes the one-shot to the counter not resetting without convergence |
| **P7** | §2 still claimed 0.5° helper steps; §12 said 45 helpers where §4 said 49; the 33-case §6 table asserts v3 setpoints (`20.5`, `25.0`) under a v4 heading | **Fixed.** Step row corrected, counts reconciled to 50, and the §6 table explicitly labelled as the **v3** record with a pointer to §16 for v4. The reviewer was right that an unlabelled table made the document appear to prove v4 with v3 evidence |
| **P8** | `heat_below_outdoor` and `cool_above_outdoor` are independent sliders with no enforced relationship. Drag them into overlap and at 21 °C outdoor both tests pass; first-match-wins heats the house at 21 °C outdoor — the v1 incident re-entered through a dashboard slider | **Fixed.** An overlapping band collapses to `shoulder`: comfort control stands down, the safety band (which reads neither helper) keeps running |
| P9 | A misconfigured `away_min` above the unit's max would clamp to 30 while triggering at a higher value | **Not reachable.** `climate_away_min` is bounded 5–22 and `away_max` 24–35; the helper bounds are the enforcement. Noted rather than coded |
| P10 | Mode and preset both stamp `cmd`, so the second write wins and the in-flight clock keys off the wrong command | **Not reachable.** Mode and preset are mutually exclusive per tick by construction: the mode command requires `not mode_ok`, the preset requires `mode_ok` |
| P11 | `settle` of 120 s may be shorter than a real SmartThings round trip, making our own in-flight command read as a fault | **Fixed.** Default raised to 240 s |

### Found outside the review, during the same session

- **The counter counted our own in-flight *setpoint* command.** `diverged` excluded the tick on
  which a mode command was issued but not the tick on which a setpoint command was issued.
  Observed live: the Living room setpoint moved 19 → 22 after a wall change and the counter went
  to 1. Same class as R4-2/M1, relocated from the mode path into the setpoint path. Fixed by
  excluding `will_set_temp` as well.

- **`climate.set_preset_mode` on an `off` unit turns it on, in `cool`.** See §2. Found by probing
  the hardware before implementing "start the unit in wind-free", and the reason that feature
  cannot be implemented the obvious way.

- **Wind-free is a cooling-only feature** on these units. The automation now asserts the preset
  only when the unit is confirmed in `cool`, and leaves it alone in heat, dry and fan-only.

### The pattern, five rounds in

Every round so far has found that the previous round's fix **moved** a finding rather than closing
it: A5 → R4-1 → P1 are the same liveness trap relocating through the counter, then the hold, then
the restart path. R4-2/M1 → the setpoint counter is the same "our own command read as the unit's
fault" relocating through the mode path into the setpoint path. The working assumption for round 6
is that this has happened again, most probably around `unit_moved`, which now carries three terms
and two implicit assumptions (continuous uptime, and `last_changed` meaning a mode change).

P6 is the one worth keeping in view as a process failure rather than a code one: a finding was
recorded as closed on the strength of a doc edit that was never made. A closure claim is itself an
assertion that needs checking.

---

## 18. v4.2 — the TOCTOU interlock, and P1 confirmed in production

### P1 was proved by an unplanned restart, within the hour

Home Assistant auto-updated 2026.9.2 → 2026.9.3 at 09:32 on 2026-09-19, roughly an hour after the
round-5 guard went in. That restart is the exact scenario P1 described, and the measurement is
unambiguous — immediately after boot, every one of the five units reported `last_changed = 41 s`:

```
                       lc     since_cmd     OLD 2-term rule   NEW 3-term rule
  Living room         41 s        526 s          True              False
  Office              41 s   843121985 s         True              False
  Bedroom             41 s   843121985 s         True              False
  Kids room 1                 41 s   843121985 s         True              False
  Kids room 2                 41 s   843121985 s         True              False
```

Under the v4.0 two-term rule **all five rooms would have been classified as "a person at the
wall"**: five 2-hour manual holds and five push notifications, on a system with zero faults and
nobody in the flat, caused by nothing but a version bump. With the guard: all five `False`,
counters 0, no holds, no notifications.

Worth noting *why* the guard holds rather than just that it did. The stamp automation fires on the
`homeassistant` `start` event, which is raised **after** entities are restored, so `ha_started` is
a few tens of seconds *later* than the entities' boot `last_changed`. That makes `lc` slightly
**larger** than `uptime` for any entity that has not genuinely changed since boot, and the guard
holds by a comfortable margin rather than by a hair. The 60 s subtraction is belt-and-braces on
top of that.

This is the most valuable single data point in six rounds: a reviewer's theoretical finding,
reproduced in production by accident, with the fix already in place to catch it.

### The TOCTOU interlock (found while briefing round 6)

`now_mode` is sampled at the top of each room's iteration. The setpoint and preset calls execute
~17 steps and several cloud round trips later. `mode_ok` is therefore a **stale reading** by the
time it is acted on, and for the preset call that staleness is dangerous rather than merely
untidy: `set_preset_mode` on an `off` unit **starts it cooling** (§2). If a unit went off in that
gap — someone at the wall, a cloud push, a power blip — the cached `mode_ok` would have us start
an AC cooling, in winter, unasked.

Both actuating steps now re-read live state in their own condition, which HA evaluates at
execution time:

```
setpoint:  {{ will_set_temp   and is_state(r.climate, mode)   }}
preset:    {{ will_set_preset and is_state(r.climate, 'cool') }}
```

The residual window is the microseconds between the condition and the call, which is not
closeable from a YAML automation and is orders of magnitude smaller than the one removed.

A native `condition: state` would be the idiomatic form and the linter asks for it, but the entity
is `r.climate`, a loop variable, and native conditions cannot take a templated `entity_id`. This
is one of the few places where a template condition is the only correct construction.

### Safety notification: widened to any issued command — then abandoned entirely in v4.3

Corrected here, and then corrected again one round later; both steps are kept because the
sequence is the lesson. The notification was gated on `may_act`, which covers only *mode*
commands, so a unit already in the right mode but at the wrong setpoint had its safety setpoint
corrected through `will_set_temp` and could override a live manual hold **in silence**. v4.2
widened the gate to `may_act or will_set_temp`.

That was still wrong, and round 6 (R6-4) said why: every one of those predicates is a statement
about *whether the automation managed to act*, and the cases that matter most are the ones where
it cannot act at all. **v4.3 stopped gating the alert on commanding altogether** — it now follows
the safety condition. See §19.

---

## 19. Round-6 review: what it found in v4.1, and v4.3

Review artifact `review-20260919-556b.md`. Six findings. Its central prediction — *"assume the
last fix relocated the finding again"* — was right once, in the place that mattered most.

Note on scope: the artifact reviewed was uploaded at 09:30, **before** the v4.2 TOCTOU interlock
(§18) went in. R6-3 was therefore already closed by the time the review was read.

| # | Finding | Verdict |
|---|---|---|
| R6-1.1 | The restart guard depends on a **separate** automation the climate loop cannot observe. Disable, delete or break it and the third term silently degrades to the pre-v4.1 two-term form — the P1 misclassification, back again | **Valid, fixed.** The loop no longer trusts the claim; it checks the evidence. If `uptime` exceeds 400 days the stamp cannot be real, and a persistent notification says so by name. This is the boiler-flag lesson (§11) applied to our own machinery |
| R6-1.2 | Seeded to 2000-01-01, so the guard is **inert until the first restart** — absent exactly when an instance is most likely to be trusted unexamined | **Valid, now moot in fact and covered in principle.** The 09:32 restart made the stamp real (§18). On a fresh deployment it would still be inert, and the staleness check above now makes that visible instead of silent |
| R6-1.3 | Double restart within 60 s leaves a boot-manufactured `last_changed` mismatched against the newer stamp | **Rejected — not reachable.** The scenario requires an entity's `last_changed` to survive from the first boot into the second. Every entity is re-created on *every* restart, so `lc` always measures from the latest boot, the same boot the stamp records. The two move together by construction |
| R6-1.4 | `climate_ha_started` is hand-editable from the Climate view, so the guard can be made to classify on fiction | **Half right, and the doc was wrong.** The helper is not on the Climate view — but §4 claimed *"every one editable from the Climate view"*, which stopped being true the moment machine-written bookkeeping helpers were added. §4 now distinguishes operator helpers from bookkeeping |
| R6-2 | `diverged` excludes `will_set_temp` but not `will_set_preset` — the third relocation of "counts our own command" | **Rejected, with proof.** `converged = mode_ok and target_ok`; preset is deliberately not part of it. A preset-only difference therefore leaves `converged` true and `diverged` false. For both to be true at once you need `mode_ok` and `not target_ok` — but that is exactly `will_set_temp`, which *is* excluded. The two predicates cannot both hold |
| R6-3 | TOCTOU: the preset gate is evaluated at loop top but dispatches ~17 steps later, and a unit that went off in the gap is **started in cool** | **Already fixed in v4.2** (§18), independently, before the review was read. Both actuating steps re-read live state in their own condition |
| **R6-4** | The `may_act` notification gate makes real safety failures **silent**: an `unavailable` unit fails `reachable` so a freezing room with an offline AC alerts nobody; and a unit reporting the commanded mode is `converged`, so a room losing to an open window or a mechanical fault also alerts nobody | **Valid, and the most important finding of the round. Fixed** — see below |
| R6-5 | Shoulder-collapse on an inverted band stands comfort down, leaving the safety band as the only floor — and that band is itself a toggle the operator can switch off. Two individually reasonable toggles compose into a fully unprotected flat, with no warning | **Valid, fixed.** The health check notifies on an inverted band and says explicitly when `climate_safety_always` is also off |
| R6-6 | A `wind_free` preset set by us during cooling season survives into a heat start, putting the plastic diffuser mesh behind hot coils | **Closed — the hardware already handles it.** The operator confirmed the units switch to a different preset themselves on a heat start, which opens the mesh. There is nothing for this automation to do, and the correct action was the one already taken: leave the preset alone outside cooling. See §2 |
| Minor | `retry_throttle` is 3000 s (50 min) but the prose says "roughly hourly" in places | Intentional and now stated: one interval, named, used by the breaker re-arm, the safety throttle and the alert throttle alike |

### R6-4: the alert now follows the condition, not the command

This is the finding worth internalising. Every previous round moved the *command* logic around;
this one caught the **alerting** logic inheriting the same mistake. The notification had been
gated on `may_act` — "did we send something?" — which is a statement about the automation, not
about the flat. The two cases it silenced are precisely the two where the operator is the only
remaining actuator:

- **Unit unavailable.** `may_act` requires `reachable`. A room at 5 °C whose AC is offline —
  SmartThings outage, WAN down, unit unplugged — produced no alert at all, because we could not
  command it. The one situation where a human *must* be told was the one situation guaranteed to
  be silent.
- **Converged but losing.** A unit reporting `heat` at 18 is `converged`, so `may_act` is false —
  even while the room goes on falling because a window is open or the compressor has failed.
  Nominal compliance masked a real thermal failure.

The alert is now driven by `is_safety` — the room is outside the band — throttled per room by its
own stamp, and it names which of the three situations applies. It deliberately uses a separate
stamp from the command stamp: when nothing is commanded the command stamp never advances, so a
throttle keyed to it would never close. That is the same class of bug as the wall-clock gate in
§16, and worth stating as a rule: **a throttle must be keyed to the event it is throttling.**

### The pattern, six rounds in

A5 → R4-1 → P1 → R6-1 is one liveness hazard that has now relocated four times: from the counter,
to the hold, to the restart path, to the stamp's own dependency chain. It has not been closed so
much as pushed steadily further from the control path, each time into a place where its failure is
less likely and more visible. R6-4 suggests where to look next: the parts of the system that
*observe* rather than *act*. Six rounds of scrutiny went into the command path, and the alerting
path quietly inherited a command-shaped assumption the whole time.

### A note on scope, recorded deliberately

R6-6 is worth keeping as an example of the opposite failure mode to the one this document mostly
catalogues. Six rounds of adversarial review train a habit of assuming every hazard needs a guard
in *our* code. The units already protect their own mesh. Had that guard been written, it would
have added a preset call — the single most dangerous call in this integration (§2) — to defend
against a condition that cannot occur.

The rule that follows: **before building a guard, establish whether the hardware already has one.**
A guard for an impossible state is not free; it is new code on the actuation path, and on this
system the actuation path is where every serious bug has lived.
