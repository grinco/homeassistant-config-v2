# Automatic per-room climate control — design

Status: **implemented and live** (2026-09-20). Version 5.6.
Written retrospectively after a v1 model that shipped and had to be replaced the same evening,
then revised through four adversarial reviews. v4 is a deliberate simplification of the control
model requested by the operator, and it closes the round-4 findings at the same time.
Instance: HA 2026.9.3 Supervised, Home.

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
| v4 | **Heat/cool becomes a global HOUSE decision from the outdoor temperature; each room gets a day target and a night target instead of two thresholds; new per-room air-filter mode; human detection rebuilt on a real command timestamp; setpoints rounded and clamped to the unit's range; `climate_safety_always` becomes a true master hatch** | Operator simplification request, plus round-4 findings R4-1 through R4-7 — see §15 and §16 |
| v5.1 | **One resolved template sensor per room owns all sensor selection, bias and gating; the control loop, the graphs and the floor/household averages all read it. Tado TRVs become the bedrooms' preferred source, distrusted while the radiator is hot. Numeric-helper bounds and sensor-blackout alerting added.** | Tado valves installed; round-7 findings R7-3/5/6/9 — see §20 |
| v5.2 | **Blackout alert suppressed during the post-boot window; plausibility checks on the two calibration offsets** | Round-8 findings R8-1 and R8-4 — see §22 |
| **v5.3** | **Exit-only hysteresis on the house-mode boundary; the blackout grace keyed to the sensor instead of the uptime stamp; an implausible offset now distrusts its source; family view shows the newer safety symptoms. Fixes a LIVE bug where the automation read its own successful command as a person at the wall** | Operator report plus round-9 findings — see §23 and §24 |
| **v5.4** | **Offset distrust made symmetric (an implausible AC offset no longer poisons the fallback it falls back to); blackout grace re-keyed to a per-room persistent stamp that survives a restart and ignores sensor flapping; `human_moved` renamed `external_moved` and its notification stopped claiming the operator did it** | Round-10 findings R10-7, R10-6, R10-1 — see §26 |
| **v5.5** | **An implausible calibration offset is now REPLACED BY THE MEASURED DEFAULT instead of discarding the source — v5.4 cost a room its safety floor to avoid a wrong number; the boot grace is restored alongside the per-room blackout clock; a unit that keeps changing itself is escalated as possibly faulty** | Round-11 findings F11-1, F11-3, F11-4 — see §27 |
| **v5.6** | **The AC offset is no longer plausibility-checked at all — its helper range IS the envelope, and the extra check could only reject a *correct* large offset and fail cold; a calibration override now reaches the phone; the recurrence notice stopped naming a cause it cannot know and got its own notification id** | Round-12 findings F-1.1, F-1.5, F-4.2/3/4 — see §28 |

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

> **Note on §2's resolution expression.** From v5.1 the sensor resolution no longer happens in the
> automation at all — it lives in `sensor.climate_temp_<room>`, a template sensor. Any resolution
> template shown above §3 is the **pre-v5 form**, kept as history. The current behaviour is
> described in §21 and the live implementation is the template entity itself.

## 3. Control model

### The house decides heat or cool; the room decides how warm

v2 and v3 gave every room *two* numbers — a heat-below and a cool-above with a dead zone
between them. That worked, but it asked the operator to express one idea (how warm do I want
this room) as two numbers, and it let five rooms disagree about what season it was.

v4 splits the decision along its natural seam:

```
        HOUSE  (one decision, from the outdoor temperature)

          outdoor unreadable                ──►  SHOULDER   (tested first)
          heat below ≥ cool above           ──►  SHOULDER   (tested second)

          then, from the season we were in last (v5.3, exit-only hysteresis):

            was HEATING    hold heat until  outdoor > heat below + hysteresis
            was COOLING    hold cool until  outdoor < cool above − hysteresis
            no memory      outdoor ≤ heat below ──► HEATING
                           outdoor ≥ cool above ──► COOLING
                           between the two      ──► SHOULDER, nothing runs


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

68 helpers plus 11 template entities, split across two pages by how often they are touched. The **Climate** view carries
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
| Sensor bias (AC probe) | `input_number.climate_ac_sensor_offset` | −2 °C |
| Sensor bias (TRV) | `input_number.climate_trv_sensor_offset` | 0.0 °C, unmeasured |
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

**Since v5.5 it has TWO readers** (round 12, F-3.2): the restart guard inside `unit_moved`, and
the boot half of the blackout grace. Round 9 killed an earlier two-consumer arrangement because
the two needed *opposite* things from the stamp; these two do not — both tolerate a stale stamp
in the same direction, which is why the coupling is benign here. It is still a coupling: **when
R10-8 is closed, both readers must be updated**, or the grace silently breaks. Round 13 flagged
this prose as the only place that still described a single consumer.

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
             AND NOT in_flight          ← our own command has had its settle window
             AND NOT external_moved     ← something outside the automation is driving it
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
- Notification uses `notify.send_message` with `entity_id: notify.operator_phone`. The bare
  `notify.operator_phone` *service* does not exist — that name is an entity of the newer
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
- **68 helpers and one ~115-step run.** The automation is at the size where a decide/act split — a
  template entity publishing each room's verdict, with a thin automation applying it — would make
  the decision continuously inspectable instead of only visible in a trace. See §13. **Partly done
  in v5.1**: the per-room *temperature* now resolves in a template entity, so the input to the
  decision is inspectable. The verdict itself still only exists inside a trace.
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

---

## 20. v5 — Tado radiator valves as room sensors

Three Tado Smart Radiator Thermostats arrived in the bedrooms on 2026-09-19. They are the first
independent temperature sensors those rooms have ever had. The boiler is still configured entirely
outside this automation and is still never commanded by it; what changed is that it now has
**instruments** we can read.

### The AC return-air probes were worse than the design admitted

Measured side by side with the radiators cold (`heating = 0 %` on all three):

| Room | TRV | AC probe raw → corrected | Δ |
|---|---|---|---|
| Bedroom | 23.04 | 25.0 → 23.0 | +0.04 |
| Kids room 1 | 24.16 | 25.0 → 23.0 | +1.16 |
| Kids room 2 | 24.16 | 25.0 → 23.0 | +1.16 |

**All three probes reported exactly 25.0.** They resolve to whole degrees, so the automation has
been treating three rooms as the same temperature when two of them were genuinely ~1.2 °C warmer
than the third. That is finding **A11** — one shared offset standing in for three uncalibrated
units — showing up as data rather than as an argument. The TRVs resolve to 0.01 °C and are not
sitting in the return airflow of the very unit being controlled, which is a feedback path the
probes always had.

So the bedrooms now read **TRV first, AC probe as fallback**.

### Bias belongs to the sensor, not the room

The old model carried one `biased` boolean per room. That was wrong in a way that would only ever
have shown up during a failure: Living room and Office were flagged *unbiased* because their
primary is a SwitchBot meter — but their **fallback is the AC probe**, which reads ~2 °C high. If a
meter had died, those rooms would have silently controlled on an uncorrected reading and
under-heated by 2 °C, with nothing in the logs to say why.

Each sensor now declares its own bias (`none`, `ac`, `trv`) and the correction is chosen by
whichever source actually supplied the reading.

### The TRV offset is 0.0, and that is a measurement, not an omission

The valves sit on the radiator, so they will read high once it is hot. But with the radiators cold
they agreed with the corrected probes to within those probes' own 1 °C resolution — there is no
honest number to write down yet. `climate_trv_sensor_offset` exists, defaults to **0.0**, and is to
be calibrated during the heating season against `sensor.<room>_trv_heating`, which reports the
valve's output percent and is precisely the signal that says when the bias is active.

> **A new `input_number` does not default to zero — it defaults to its minimum.** Created with
> `min: -5`, this helper came up at **−5.0**, which made all three bedrooms read 5 °C cold. The
> Bedroom landed at 18.04 °C against an 18 °C safety floor: 0.04 °C from starting an AC at
> midnight on a fabricated reading. Nothing actuated, because those rooms are disabled and only the
> safety band applies to them. This is the same class as the `input_datetime` that reports *today
> 00:00* rather than `none` (§4). **Seed every new helper explicitly and read it back.**

### Liveness comes from the valve, not from a timestamp

"Available but not updating" is a failure this hardware genuinely has — it is exactly why the
HomeKit-local path was abandoned. If the cloud path ever did the same, the entity would stay
available holding a stale number and the automation would control on it.

That cannot be caught with timestamps. Home Assistant dedupes, so `last_reported` tracks *changes*,
not polls, and a stable room is indistinguishable from a stuck sensor. Measured 2026-09-20 with
everything healthy:

| Sensor | Since last change |
|---|---|
| TRVs | 1370 s |
| Office meter | 2715 s |
| Living room meter | 4085 s |
| Bedroom AC probe | **43723 s** (12 h — it only resolves to whole degrees) |

Any threshold loose enough to tolerate the probe would catch nothing; any threshold tight enough to
be useful would fire on a healthy meter at 68 minutes. So liveness is taken from **Tado's own
`connectivity` binary sensor** — evidence rather than inference. When it drops, the room falls back
to the AC probe *with the probe's own correction*; if both sources are dead the room reports `skip`
and is left alone.

Rooms with no liveness sensor pass the gate unconditionally, so the SwitchBot meters are unaffected.

### M6 is checked instead of asserted

M6 has been open since round 3: the AC and the boiler do not fight *only while* each TRV setpoint
stays at or below that room's night target. It was recorded as a prose constraint because no entity
existed to verify it. The valves expose their setpoint, so the config-health check now compares
each one against its room's night target and names the room if it drifts above.

This is §11's boiler-flag lesson applied the right way round. The flag was rejected because a
configuration value asserting something about the world is not evidence about the world. The TRV
setpoint **is** evidence — so it is read, and still never written.

### Not wired in, deliberately

- **`binary_sensor.<room>_trv_window`** — Tado's open-window detection. An obvious candidate for
  suppressing heating, and surfaced read-only on the advanced view, but not in the control path.
- **`sensor.<room>_trv_heating`** — surfaced for calibration, not consumed.

Both are there to be watched first. The rule from §19 applies: establish what the hardware actually
does before building anything on top of it.

### HomeKit local: disabled, and its entities removed

The operator found the `homekit_controller` path was not updating device values and disabled it.
That left **16 entities stranded as `unavailable`**, 15 of them still assigned to the three bedroom
areas — and because the room views are strategy-generated from area membership, they would have
rendered as dead tiles beside each working valve, including a duplicate `climate.*` per room. The
disabled config entry was deleted, which removed them. Re-pairing is a zeroconf rediscovery if it
is ever wanted.

Running both the cloud integration and `homekit_controller` against the same hardware produces two
entity sets for one device, so keeping only the cloud path is also the right call independent of
the update problem.

---

## 21. v5.1 — one resolved temperature per room, and round 7

Round 7 (`review-20260919-59bc.md`) made the strongest single finding of the series, and it was
mine: **v5 moved the bias hazard into the safety band of the three disabled bedrooms.**

Those rooms have comfort control switched off, so the safety band is their *only* automated
protection. v5 switched their primary sensor from an AC probe corrected by −2 to a TRV corrected by
**0** — and the valve sits on the radiator. During precisely the condition the cat floor exists for
(cold weather, boiler running) the reading would have been radiator-local, biased high by an
unmeasured amount, corrected by nothing. A genuinely 17 °C bedroom could read ≥18 and get no heat.
That is F5 and A11 relocated out of the calibrated path and into the uncorrected one, landing in
the rooms with nothing else to catch it.

### The fix, and the structure that came with it

Every room now has **one resolved template sensor**, `sensor.climate_temp_<room>`, which owns:

- **source priority** — meter, else TRV, else AC probe
- **per-sensor bias** — each source carries its own correction
- **usability gating** — the TRV is used only while its `connectivity` is on **and** its
  `heating` is 0 %. A valve driving a hot radiator is distrusted and the room falls back to the
  calibrated AC probe.

The automation reads that entity and nothing else. So does every graph. So do the floor and
household averages. There is one implementation, it cannot drift, and the number the loop acted on
is a real entity with history rather than a variable visible only inside a trace — which is what
§13 has wanted since round 2.

It also makes the system improve cheaply: **adding a better sensor to a room means editing one
template**, and the graphs, both floor averages and the household average all get better at once.

### The aggregates were wrong, and nobody could see it

`indoor`, `downstairs` and `upstairs` temperature and humidity were `min_max` means built
**entirely from AC probes**. Because those probes resolve to whole degrees and read ~2 °C high,
every one of them was pinned at 25.0.

| | before | after |
|---|---|---|
| Household temperature | 25.0 | **23.7** |
| Household humidity | 37.2 | **48.5** |
| Downstairs | 25.0 / 36.0 | 23.9 / 44.0 |
| Upstairs | 25.0 / 38.0 | 23.6 / 51.4 |

The humidity figure was **11 points low** — 37 % reads as "dry, consider humidifying" when the
truth is an unremarkable 48.5 %. All six were repointed in place, so their long-term statistics
history survives.

### Other round-7 findings

| # | Finding | Status |
|---|---|---|
| **R7-3** | TRV bias relocated into the disabled bedrooms' safety band | **Fixed** — TRV distrusted while `heating > 0`, falls back to the corrected probe |
| **R7-4** | `trv_heating` observed but not consumed | **Fixed** — it is now the gate, so the observable that says "the bias is live" actually drives behaviour |
| R7-5 | M6 compared against the night target always, so a fine daytime valve setting would flag | **Fixed** — compares against the target actually in force |
| **R7-6** | The min-default hazard is general, not creation-only | **Fixed** — config-health range-checks `command_settle`, `hysteresis`, `away_min` and `frost_override`. `float()` catches non-numeric, never wrong-numeric |
| R7-7 | A10 regression: were the triggers repointed? | **Not a regression** — they were repointed in v5; now they point at the resolved sensors, so a room re-evaluates the moment its best reading moves |
| R7-8 | §2 and the status line still specified v4 | **Fixed** |
| **R7-9** | A safety room with no usable temperature is silent — `skip` sits above every safety branch, so no command *and* no word | **Fixed** — a blackout now alerts. The bedrooms are two clouds deep (Tado, SmartThings) and one WAN outage takes both |
| R7-1 | The doc showed the pre-v5 resolution template | **Resolved differently** — the template no longer lives in the doc at all; it lives in `sensor.climate_temp_<room>`, which is inspectable directly |
| R7-2 | Source flap steps the corrected temperature and hysteresis cannot tell that from a real crossing | **Open, and now more likely** — the heating gate makes the bedrooms switch source as the radiator cycles. It matters only for an *enabled* bedroom; all three are currently disabled. Watch when one is enabled |

R7-2 is worth stating plainly rather than burying: the fix for R7-3 makes R7-2 more probable. That
is an accepted trade — reading a radiator-warmed valve in a safety band is a wrong number, while a
source step is a timing artefact on a room whose comfort control is off.

---

## 22. Round-8 review, and v5.2

Review artifact `review-20260919-b64a.md`. Its verdict on the v5.1 structure was that the
concentration was right and that it moved the hazard rather than removing it: the resolved sensor
is now the sole input to control, display *and* aggregates at once, and the bedrooms' resolved
sensors — four dependencies, two behind clouds — are the most fragile ones in the system while
protecting the rooms with no comfort control to fall back on.

| # | Finding | Status |
|---|---|---|
| **R8-1** | The R7-9 blackout alert fires on **every routine restart**. A bedroom's resolved sensor depends on cloud entities that initialise late, so it reads `unknown` for minutes after boot, resolves to `skip`, and pushes "no usable temperature" — on a version bump. R7-9 traded a silence failure for a cry-wolf failure, and cry-wolf destroys the alert it added | **Fixed.** The blackout arm is suppressed until `uptime > 600 s`. The *other* arm — the room is out of band on a reading we do have — is not suppressed, because that is real from the first tick |
| R8-2 | The measured 1.2 °C source step **exceeds the 1 °C hysteresis**, so a single TRV↔probe flip can traverse the whole band in one sample; and the resulting churn is **invisible to the breaker**, because every oscillating command is one the unit obeys | **Open, and stated more honestly than v5.1 did.** Still gated by all three bedrooms being disabled. The review is right that "watch when enabled" is too weak given the numbers — before enabling a bedroom, either widen hysteresis past the step or add a dwell on source switching |
| R8-3 | `min_max` mean over resolved sensors: a mean of [23, 23, 18, 23, 23] looks fine while one room sits at the cat floor, and the aggregates now inherit the two-cloud fragility the AC probes never had | **Open.** A `min` alongside the mean would surface the cold room. Not added — the safety band already alerts per room, so this is a display improvement rather than a protection gap |
| **R8-4** | The R7-6 bounds check covered four helpers and **omitted the one that actually demonstrated the hazard**: `climate_trv_sensor_offset` came up at −5.0, which is *inside* its valid range | **Fixed.** Both calibration offsets now get **plausibility** checks, not range checks — an offset is wrong long before it is out of bounds. This matters more since v5.1, because the offsets are applied inside the resolved sensor, ahead of everything: one wrong number moves the safety band, the graphs and the household average together, where no downstream guard can see it |
| R8-4 (part) | `breaker_threshold = 0` re-opens the A5 liveness trap through a slider; `manual_hold_hours = 0` disables human detection | **Rejected — not reachable.** Verified live: `breaker_threshold` has `min: 2.0` and `manual_hold_hours` has `min: 0.5`. The helper bounds already prevent both |
| R8-5 | §2 still showed the pre-v5 resolution template unannotated, so a reader cannot tell which is current | **Fixed** — §2 now carries a note pointing at §21 |

### The pattern, eight rounds in

R8-1 is the one worth carrying. Round 7 closed a *silence* by adding an alert; round 8 found that
the alert fires on a routine event, which would have taught the operator to mute it — converting a
fixed silence into a worse one. Every previous relocation moved a hazard between mechanisms. This
one moved it between **a system property and a human one**: the alert is technically correct and
practically useless, and nothing in the code would ever have shown that.

---

## 23. v5.3 — the house boundary gets hysteresis

Every *room* decision had exit-only hysteresis from v3 onward. The *house* decision never did: it
was a bare comparison of the outdoor reading against two thresholds, with nothing damping it.

The operator hit this on 2026-09-20. Outdoor climbed past `heat_below` (17.0) to 17.3 — a margin of
0.3 °C — and the whole house flipped from heat to shoulder, taking a room that had just been
switched to air-filter mode with it, from `heat` to `fan_only`.

That instance was benign, but the shape is not: a reading that wanders either side of the line
flips the season, and with it every air-filter room, one cloud round trip per crossing. Walked
against the morning's real readings:

| | old rule | new rule |
|---|---|---|
| at outdoor 17.3 | flips to shoulder | holds heat |
| at outdoor 18.1 | shoulder | shoulder |
| on a day hovering at 17 | **8 mode flips** | **0** |

Entering a season uses the bare threshold; leaving it requires clearing the threshold by the
hysteresis margin. The previous mode is remembered in `input_select.climate_house_mode`, whose
options are ordered **shoulder first** so a reset defaults to the season that does nothing — the
min-default hazard, applied deliberately this time. If the helper holds anything unexpected the
expression falls through to the memoryless comparison, so a bad value costs stickiness, never
correctness.

It reuses `climate_hysteresis` rather than adding a knob. The coupling is real and deliberate:
widening room hysteresis also makes the season stickier.

---

## 24. The automation blamed the operator for its own command

This is the most instructive bug in the whole series, because it was found by the operator, in
production, and the automation's report of it was actively false.

**What they saw.** A push notification saying a unit had been changed at the wall and that control
was backing off for two hours, plus a manual hold on the Living room. They had touched nothing.

**What happened.** When the loop commands a unit, the unit obeys about **1.5 seconds later**. The
human-detection test asked:

```
unit_moved := lc < since_cmd        # did the unit change AFTER we commanded it?
```

A unit that *obeys* changes state a moment after the command, so its `last_changed` is permanently
a hair more recent than our command stamp. **`lc < since_cmd` is therefore true for ever after any
successful command**, not briefly.

It stayed hidden for four versions because `human_moved` also requires `not mode_ok`, and a command
that succeeded leaves the mode matching. The two halves could not be true together — until the
*wanted* mode changed for an unrelated reason. The operator switched an air filter off, so a room
holding `fan_only` should have gone `off`; `mode_ok` went false while `unit_moved` was still stale
from our own command. The automation stamped a two-hour hold and told the operator they had done
something they had not.

**The fix** subtracts the settle window:

```
unit_moved := lc < since_cmd - settle
```

which asks the right question: did the unit change **more than one cloud round trip** after we
commanded it? Our own command landing 1.5 s later cannot qualify. A person pressing a button
minutes later always does. Verified against the live data at the time: old rule `True`, new rule
`False`, and a simulated wall change 100 s ago against a command 900 s ago still `True`.

**This is the third appearance of one idea** — the automation reading its own command as somebody
else's doing. M1 caught it on the in-flight command. R4-2 caught it on the divergence counter. This
is the first time it has been the *successful* command, which is why none of the previous fixes
covered it. The lesson worth carrying: *a command that works still leaves evidence, and evidence of
our own action must never be counted as evidence of someone else's.*

A secondary observation from the same incident: a state-triggered change arriving inside the settle
window is evaluated but not acted on, so it waits for the next tick — up to ten minutes. Correct
under the in-flight rule, but the operator experiences it as the switch not working. Recorded, not
changed.

**The gap the fix opens, accepted 2026-09-20.** Subtracting `settle` buys correctness at the edge of
the window: a person who presses a button at the wall *inside* the settle window, immediately after
we commanded that same unit, now falls outside the test and is not detected as a manual override —
the loop reads their change as its own command landing and may correct them on the next tick. The
old rule caught that case, at the price of the false holds in this section.

The operator's call: **not worth guarding.** It requires someone to be standing at a specific unit
in the ~120 s after the automation happened to command that same unit, which is a coincidence rather
than a pattern of use, and the cost of being wrong is one corrected setting rather than an unsafe
one. Re-open it if a hold is ever missed in practice.

This is the shape of every trade in this document worth restating: the fix is not free, the price is
named, and the decision to pay it is recorded next to it rather than discovered later by whoever
wonders why the window has a hole in it.

---

## 25. Round-9 review

Review artifact `review-20260919-e3a6.md`.

| # | Finding | Status |
|---|---|---|
| **1** | The boot grace made the blackout alert a **second consumer of `climate_ha_started`**, the same stamp the restart guard reads — and the two need *opposite* things from it. A stale stamp makes `uptime` enormous, defeating the restart guard *and* making the suppression pass trivially, re-arming the cry-wolf it was added to stop. A spurious mid-run write makes `uptime` tiny, disabling human detection *and* silencing a real blackout | **Fixed.** The grace is keyed to how long *that room's own resolved sensor* has been unusable. **This claim was wrong and round 10 withdrew it** — the threshold was still a flat 600 s, and `last_changed` resets at a restart exactly as the stamp does. Superseded by the per-room stamp in §26 |
| 2 | 600 s was an unvalidated constant, and it violated the rule this design coined — *a throttle must be keyed to the event it throttles* | **Fixed by the same change.** The review was right that v5.2 broke v4.3's own rule |
| 3 | The offset bounds encode an unmeasured assumption; the AC check is one-sided and would miss a wrong-sign entry | **Partly rejected.** Wrong sign is **unreachable**: `climate_ac_sensor_offset` is bounded −4…0, so a positive value cannot be entered. The TRV bound stands because the heating gate means the offset only applies while the radiator is *cold*, where a 3 °C valve bias is not plausible |
| **4** | The plausibility check **notified but still applied** the bad offset, so a fabricated reading could still drive the safety band | **Fixed.** An implausible offset now makes the resolved sensor distrust that source and fall back to the calibrated probe |
| **5** | The dashboard split honoured "do not move the symptoms out of sight" for the 2025-era symptoms and broke it for every symptom added since — blackout, stale stamp, calibration, valve drift were phone-only | **Fixed.** All four now render on the family view |
| 6 | R8-3 (household mean hides a cold room) leans on a per-room alert that R8-1 made boot-fragile | **Open**, and the dependency is now weaker since the grace no longer depends on the stamp |
| 7 | R8-2 source-step churn is invisible to the breaker because every oscillating command is obeyed | **Open**, still gated on the bedrooms being disabled |
| 8 | Stale header (2026.9.2), revision table out of order | **Fixed** |

Round 9 predicted the relocation correctly and in the right place. It did not find §24 — the
operator did, an hour later, from a notification that accused them of something they had not done.

---

## 26. Round-10 review, and v5.4

Review artifact `review-20260920-fa8f.md`. The round was told not to re-derive the settle-window
gap the operator had already accepted, and to find what else the v5.3 fixes hid. It did.

Every finding below was re-checked against the live instance before being actioned, because the
reviewer had only this document. Two of its predictions were **wrong about the code and right about
the document** — the behaviour was already safe and the doc simply did not say so. That distinction
is worth keeping: a review of a design record can only find what the record claims.

| # | Finding | Verified against live state | Status |
|---|---|---|---|
| **R10-7** | An implausible offset makes the resolved sensor distrust the **TRV**, but the fallback still applies `ac_offset` **ungated**, so round 9's fix is reopened through the fallback path | With `ac_offset = −9` the Bedroom's real 24 °C probe emitted **16.0 °C** — below the 18 °C away floor, so the safety band would have started heating a warm room on a fabricated number | **Fixed** |
| **R10-6** | The blackout grace was *relocated*, not fixed: `last_changed` resets at a restart exactly as the shared stamp did, and every `unknown`↔`unavailable` flap resets it too | Confirmed on all three traces | **Fixed** |
| **R10-1** | A unit that changes *itself* is classified as a person | Command 3600 s ago, unit self-changes 30 s ago → hold + accusation. **The old predicate did this too** — the reviewer called it newly opened; it is pre-existing, previously drowned in the permanently-true bug | **Fixed** (the claim, not the behaviour) |
| R10-3 | Widening room hysteresis erodes the house shoulder | Arithmetic right, scale wrong: the live band is **17→28, 11 °C wide**, not the 17→20 this document showed. Erosion needs 5.5, elimination 11, against a hysteresis of 1 | **Guarded** — config health warns at half the shoulder width |
| R10-5 | Exit-hysteresis can pin the house when the band is inverted, regressing P8 | **Wrong against the code.** The inverted-band branch is tested *before* `prev` is consulted, so it falls to shoulder unconditionally | Doc fixed (§2) |
| R10-4 | A dead outdoor sensor either loses the pin or freezes the season, and the doc does not say which | **Already safe** — same branch-order argument; the dead-sensor test also precedes `prev`, and the write-back clears the memory | Doc fixed |
| R10-2 | `settle` does three jobs whose correct values differ; raising it for cloud latency silently widens the human- and fault-detection dead zones | Confirmed. Also: `may_act` **does** include `not in_flight` in the code — the §11 pseudocode omitted it, which is what made the document contradict itself | **Open**, doc fixed |
| R10-8 | `climate_ha_started` still feeds the restart guard, so R6-1.1 is only half closed | Confirmed | **Open** |
| R10-9 | The outdoor sensor is not a state trigger, and the new house-mode helper has no symptom | Confirmed — no `climate.*` or outdoor entity appears in the trigger list | Symptom **added**; trigger gap **open** |
| minor | Revision table still out of order after R9-8 claimed it fixed | Confirmed — v5.1–v5.3 sat between v3.3 and v3.4 | **Fixed**, sorted properly this time |

### R10-7 — distrust has to be symmetric or it is not distrust

Round 9 added a plausibility check and had the resolved sensor *refuse* an implausible source rather
than apply it. It applied that refusal to exactly one of the two sources. The fallback kept consuming
`ac_offset` unconditionally, so a bad AC offset fabricated a reading through the path that exists
precisely for when the primary has failed.

All five resolved sensors now gate **both** sources. If every source for a room is untrustworthy the
sensor emits nothing, which resolves to the existing `skip` sentinel: command nothing, and let the
blackout alert say so. **Refusing to answer is a valid answer; inventing one is not.**

The blast radius is why this mattered: `ac_offset` is a single global helper and the probe is the
*last-resort* source for every room. One bad number took out the fallback for all five rooms at
once. The config-health notice now says what has been switched off rather than that a number looks
odd.

### R10-6 — the third clock, and why the first two were the wrong kind

This grace has been keyed to three clocks, and the progression is the lesson:

1. **`uptime` from the shared restart stamp** (v5.2). Round 9 killed it: one helper gating two safety
   mechanisms that need opposite things from it.
2. **The resolved sensor's `last_changed`** (v5.3). Looked stamp-free, and §25 claimed it "lasts as
   long as a slow restore actually takes." Both halves were false. `last_changed` **resets at a
   restart** exactly as the stamp does, so a sensor dead for days came back from a restart with its
   grace re-armed. Worse, during a slow cloud restore the bedroom sensors flap between `unknown` and
   `unavailable`, and **every flap resets `last_changed`** — the age never reaches the grace, and a
   real blackout is suppressed *indefinitely*. A silence failure, strictly worse than the cry-wolf it
   replaced.
3. **A per-room `input_datetime`, written on the transition into unusable and cleared on the
   transition back** (v5.4). It has neither property: flapping between two unusable states does not
   touch it, because both sit on the same side of the only question it asks; and an `input_datetime`
   survives a restart with its value intact, so the grace expires on schedule instead of restarting.
   Two writes per outage rather than one per tick.

The threshold is still 600 s and this document no longer pretends otherwise. What changed is that
600 s is now measured from **the event being throttled** — the rule §16 coined and v5.2 broke.

The sentinel deserves its own line. "Never been bad" is stored as the year 2000 and tested as
`timestamp > 1e9`, not as `none`, because a freshly created `input_datetime` reports **today 00:00**
and is never `none` — a value that is plausible, wrong, and would read as "bad since midnight." The
fail direction is deliberately the safe one: an unseeded helper makes the alert arm early, never
late.

### R10-1 — the automation was never in a position to make that claim

`human_moved` is now `external_moved`, and the notification no longer says the operator changed
anything.

The predicate can see exactly one thing: the unit changed state for a reason that was not our
command. It cannot distinguish a person at the wall from the Samsung app, a cloud push, a timer on
the unit itself, or a power restore — and there is no presence signal in this flat that could. The
name asserted a fact the code could not establish, and the notification repeated that assertion to
the operator, which is how §24 produced a message blaming them for something they had not done. The
honest response is to report what was observed: *this unit is in a mode we did not ask for, something
outside the automation is driving it, backing off.*

**The behaviour is unchanged and that is deliberate.** Backing off is correct whatever moved the unit
— if something else is driving it, fighting it is wrong regardless of whether that something has
hands. Only the claim was wrong, so only the claim was fixed.

One correction to the review: it presented this as a door the §24 fix opened. It was not. The old
predicate classified self-changes the same way; the permanently-true bug simply hid them. The fix
made the predicate selective, which made a pre-existing misclassification visible rather than
creating it.

The naming point generalises past this automation. **A variable name is an assertion, and a name that
claims more than the code can know will eventually be repeated to a human as fact.**

### Still open after round 10

- **R10-2.** `settle` does three jobs — in-flight window, command-echo dead zone, config-health lower
  bound — and the echo needs seconds where the round trip needs minutes. Raising it for cloud latency
  silently widens the human- and fault-detection dead zones in proportion. Splitting it is the right
  fix and is not done.
- **R10-8.** `climate_ha_started` still feeds the restart guard, so R6-1.1 is only half closed.
- **R10-9.** The outdoor sensor is not a state trigger, so a season crossing waits up to ten minutes.
- **R8-2, R8-3, R9-6/7**, unchanged, still gated on the bedrooms being disabled.

---

## 27. Round-11 review, and v5.5

Review artifact `review-20260920-2a65.md`. This round found that **my round-10 fix made the system
less safe**, and it is the most important finding in the series so far, because it is the first time
a fix traded a bounded failure for an unbounded one.

| # | Finding | Verified against live state | Status |
|---|---|---|---|
| **F11-1** | Symmetric distrust converts a *wrong number* hazard into a *no protection* hazard. `skip` is tested above every safety branch, so a room with no reading loses its frost and cat floors too | Confirmed, and worse than stated. `ac_sensor_offset`'s slider reaches **−4.0**, past the −3.5 line, in one drag; and the bedrooms' TRV is distrusted whenever the radiator is driving, so **in heating season the probe is their only source**. One bad slider → three rooms with no safety floor, in the weather it exists for | **Fixed** |
| **F11-3** | v5.4 silently dropped the boot grace | Confirmed. After a restart the sensors come up `unknown`, the new clock arms, and any cloud restore slower than 600 s cries wolf — the R8-1 shape, re-armed and unstated | **Fixed** |
| **F11-4** | A unit that self-changes on a recurring timer is invisible to *both* detectors and held in a rolling hold forever | Confirmed: every external move resets the breaker counter, and during the hold the room is `manual` so `active` is false and the breaker cannot count at all | **Fixed** |
| F11-8 | A self-change *inside* the settle window is read as our own command, so the breaker blames the unit for an external override | Confirmed. Bounded and visible, but mislabelled | **Documented**, open |
| F11-2 | The arm/clear steps never run when the automation does not fire, so an outage inside a comfort-off window is never alerted | **Mostly wrong.** The condition is `climate_auto OR climate_safety_always`, and safety_always is on, so the loop runs regardless of comfort. The residue needs *both* off — a state config health already shouts about | Doc noted |
| F11-5 | The new guards can cry wolf, and the config-health channel has no throttle | **Half right.** The `input_select` transient point is real and is fixed. The fatigue point is not: this check writes one notification with a **fixed id**, so it replaces rather than stacks, and never pushes to a phone | Transient **fixed** |
| F11-6, F11-7 | §19 prose stale (the stamp now has one consumer); §4 helper table missing the new helpers | Confirmed | Doc fixed |

### F11-1 — the direction a thing fails in matters more than whether it fails

Round 9 said: do not apply an implausible offset. Round 10 implemented that as: refuse the source.
Round 11 showed refusing the source is worse than applying the bad number, and the reason is the
precedence order this design has had since v3:

```
        skip  (no usable reading)      ← tested FIRST
        frost / away floor / away ceiling
        manual hold
        comfort
```

`skip` sits **above** the safety band. That is correct — you cannot act on a reading you do not
have — but it means *anything that destroys the reading also destroys the floor*. v5.4 put a single
global configuration number on that path.

Compare the failure directions with the live numbers. The Bedroom probe reads 25; the true room is
about 23:

| | emitted | against an 18 °C floor |
|---|---|---|
| v5.3, applied the bad offset (−9) | 16.0 °C | heats a 23 °C room — wrong, wasteful, **fails warm** |
| v5.4, refused the source | nothing | no reading, no floor — **fails cold, silently** |
| **v5.5, substitutes the measured default (−2)** | **23.0 °C** | correct reading, correct decision |

`ac_sensor_offset` is bounded at or below zero, so a bad value can only ever subtract, which is why
v5.3's failure was always toward over-heating. That is a tolerable failure in a flat with cats and
water pipes. Having no reading at all is not.

**The fix is to refuse the number without refusing the source.** An implausible offset is replaced
by the measured default — −2 for the AC probe, 0 for the TRV — so the sensor keeps producing a
reading built on the best knowledge available, and config health says loudly which knob is wrong.
That satisfies what round 9 actually wanted (never act on a fabricated correction) without what
round 10 mistakenly paid for it (act on nothing).

**The review's own suggested fix was wrong, in the opposite direction.** It proposed falling back to
the *raw uncorrected* probe, reasoning that a probe reading ~2 °C high "over-heats, which is the safe
direction for a frost floor." It does not. A probe that reads high makes the room look *warmer* than
it is, so we heat *less* — raw would under-protect by exactly the bias. The sign matters, and it is
worth recording that a reviewer arguing correctly about failure *direction* can still get the
*sign* of a specific correction backwards. Checked against live values before implementing.

The general rule this earns: **when a guard sits above a safety interlock in a precedence order,
that guard must never be able to fire on a configuration value.** Configuration is the thing most
likely to be wrong and least likely to be noticed.

### F11-3 — two graces, two questions

v5.2 suppressed the blackout alert on `uptime`. Round 9 killed that. v5.4 replaced it with the
per-room clock and, without saying so, deleted the boot suppression entirely. Round 11 caught it:
after a restart the sensors come up `unknown`, the per-room clock arms on the first tick, and 600 s
later the alert fires — R8-1, back, for any cloud restore slower than ten minutes.

The two graces answer genuinely different questions and v5.5 keeps both:

- *Has this room been genuinely unreadable for ten minutes?* — the per-room stamp.
- *Is this just boot noise?* — `uptime`.

Round 9's objection to `uptime` does not apply now, and the reason is worth stating precisely: it
objected to `uptime` being the **only** gate, where a stale stamp made the suppression pass
trivially. Here it is ANDed with the per-room clock, so a stale stamp makes `uptime` enormous, which
simply **stops suppressing** and lets the per-room clock govern — the safe direction. A spurious
mid-run write delays a genuine alert by at most 600 s. Verified across all four cases.

### F11-4 — a diagnosis, not a new policy

The predicate cannot tell a person from a unit-side timer (§26), so the hold stays: backing off is
right whatever moved the unit. But *recurrence* is observable even when *cause* is not, and the old
design was blind to it in a way that compounded:

every external move reset the breaker counter; during the resulting hold the room is `manual`, so
`active` is false and the breaker could not count at all; the hold expired; the timer fired again; a
fresh hold was stamped. A unit with its own hourly schedule sat permanently outside comfort control
while the operator got an identical "backing off" notice each time and was never told it was
recurring.

`r.ext` records when the last external change happened. A second one inside six hours escalates the
same notification to a different message naming the likely causes — a timer set on the unit, a
recurring power interruption, a failing control board. The hold behaviour is unchanged. This adds a
diagnosis, not a policy.

### Still open after round 11

- **R10-2 / F11-8.** `settle` does three jobs, and the command-echo dead zone it provides means a
  unit self-change *inside* 240 s of our command is read as our own command — so the breaker counts
  it as a unit fault rather than an external move. Bounded and visible, but mislabelled.
- **R10-8.** `climate_ha_started` still feeds the restart guard. It now has that one consumer.
- **R10-9.** The outdoor sensor is not a state trigger, so a season crossing waits up to ten minutes.
- **F11-2 residue.** With *both* master switches off nothing runs, including the stamps — the state
  config health already calls out as fully unprotected.
- **R8-2, R8-3**, unchanged, still gated on the bedrooms being disabled.

---

## 28. Round-12 review, and v5.6

Review artifact `review-20260920-3ff4.md`. Round 11 found my fix made things worse. Round 12 found
the *replacement* fix had an unexamined direction — and it is the same mistake twice, which is the
most useful thing in this document.

| # | Finding | Verified | Status |
|---|---|---|---|
| **F-1.1** | The failure-direction analysis in §27 is one-sided. It covers the operator *over*-correcting; it never covers the operator **correctly** setting a large offset that the plausibility check then rejects and replaces with a smaller one — which under-corrects and **fails cold** | Confirmed. The rejectable-but-in-range window is `[−4.0, −3.5)` — **five reachable slider positions** silently overridden. A unit genuinely reading 4 °C high, correctly set to −4, was read 2 °C warm than truth | **Fixed** |
| **F-1.5** | The whole F11-1 safety case rests on config health, which §27 itself says never reaches the phone | Confirmed | **Fixed** |
| **F-4.2** | The recurrence text asserts "the unit keeps changing itself" and lists only equipment faults — the R10-1 over-claim, reintroduced one section later, in the opposite direction | Confirmed | **Fixed** |
| **F-4.3** | A person adjusting their own AC twice in an afternoon is told their hardware may be failing | Confirmed | **Fixed** |
| **F-4.4** | The escalation shares a notification id with the per-event message, so an ordinary later change overwrites it | Confirmed | **Fixed** |
| F-1.7 | Independent check of my rejection of the "raw probe" proposal | **Confirms I was right**, and goes further: substitution fails warm for all three bedrooms while raw fails cold for all three, so it dominates raw regardless of which room | — |
| F-3.1 | The ANDed two-grace is safe in both directions | **Confirms the argument** | — |
| F-3.2 | …but `climate_ha_started` has two consumers again, so R10-8's eventual fix must touch both or the grace silently breaks | Confirmed | **Documented** in the code |
| F-1.6, F-4.1, F-4.5, F-3.3 | Substitution leans on A11; 6 h is unvalidated; a unit cycling faster than `settle` evades the recurrence detector; "verified" claims should show their cases | Confirmed | Documented; F-4.5 **open** |

### F-1.1 — I made the same mistake twice, in opposite directions

Round 11 caught me trading a bounded failure for an unbounded one. The fix I wrote to correct it has
the identical flaw, mirrored. Both times I analysed one direction of a two-directional hazard and
declared the fix safe.

- **v5.4:** analysed "what if the offset is wrong" → refuse the source → never analysed that refusing
  destroys the reading, and the reading is what the safety floor stands on. **Fails cold.**
- **v5.5:** analysed "what if the operator over-corrects" → substitute the default → never analysed
  that the operator might be *right* and the check wrong. **Fails cold**, again, for the five slider
  positions between −4.0 and −3.5.

The concrete case: a unit whose return-air probe genuinely reads 4 °C high. The operator measures it
and sets −4.0, which is inside the helper's own range. v5.5 rejected that correct value, substituted
−2, and read the room **2 °C warmer than it is** — so heat came late, exactly the silent cold
failure v5.5 existed to prevent.

**The fix is to delete the check.** The AC helper's range is `[−4, 0]`. That range *is* the
plausibility envelope: a wrong sign is unreachable, and a wrong magnitude is bounded at 4 °C and
errs toward heating. The −3.5 line rejected nothing unsafe — it only created a way to override a
legitimate value. An in-range offset is now always honoured.

What replaces it is a *report*, not an override: sitting exactly at the helper minimum is what a
never-set helper reads, so that is called out — while the value is still used, because honouring it
fails warm.

**The TRV check stays**, and the asymmetry is the point. Its range is `[−5, 5]`, `−5.0` was a real
incident, and the offset only applies while the radiator is **cold**, where a valve bias above 3 °C
is not physically possible. There the check tests something the range does not.

> **The rule, stated so the third instance does not happen.** A plausibility check earns its place
> only when it rejects values the helper's own bounds allow *and* physics forbids. If the bounds
> already exclude everything unsafe, an extra check cannot improve safety — it can only override the
> operator. And whenever a guard replaces an operator's value with the system's own, **work both
> directions**: what if the operator is wrong, *and* what if the check is wrong.

### F-1.5 — a silent override of an operator's value has to leave the building

§27's safety case was "bounded-warm failure plus a loud config-health notice," and §26 had already
recorded that config health never pushes to a phone. Bounded-warm is only bounded if somebody
notices.

A calibration offset is the one value that moves the safety band, the dashboard and every aggregate
from a single place. When one is being overridden or sits at a never-set default, that now pushes to
the phone, throttled to `retry_throttle` off its own stamp — a throttle measured against the thing it
throttles, per §16.

### F-4.2 / F-4.3 / F-4.4 — I re-broke R10-1 one section after writing it

§26 removed a notification that told the operator they had changed a unit, on the principle that
*a name that claims more than the code can know will eventually be repeated to a human as fact*.
§27's escalation then said **"the unit keeps changing itself"** and listed only equipment faults.
`external_moved` cannot tell a person from a timer — §26 says so explicitly — so the escalation
asserted a cause from a predicate that cannot establish one. Same error, opposite direction, one
section later.

It now reports what is observable — twice within N hours — and puts the innocent explanation
**first**: if somebody is using the remote or the app, nothing is wrong. Only then does it name the
equipment causes, for the case where nobody is.

It also has its own `notification_id`. Sharing one with the per-event message meant an ordinary later
change overwrote the recurrence notice, so the rarest and most diagnostic signal was the one most
easily erased.

### The four grace cases, shown (F-3.3)

Round 12 is right that "verified" should show its work:

| `uptime` | room unusable for | `no_temp` | why |
|---|---|---|---|
| 120 s | 700 s | **false** | boot noise, suppressed |
| 5000 s | 700 s | **true** | genuine, fires |
| 5000 s | 120 s | **false** | per-room grace still holding |
| enormous (stale stamp) | 700 s | **true** | a stale stamp cannot suppress — it only stops suppressing |

### Still open after round 12

- **F-4.5 (new).** A unit cycling faster than `settle` (240 s) is read as our own command, so
  `r.ext` is never stamped and the recurrence detector cannot see it — the new visibility path
  inherits the settle blind spot and can be evaded by exactly the fast fault it was built to surface.
- **F-1.6 / A11.** Per-room calibration. The substitution that remains (TRV) falls back to a value
  this document records as unmeasured.
- **F-4.1.** 6 h is a judgement, not a measurement; now stated as such in the code.
- **R10-2 / F11-8, R10-8** (now with F-3.2's coupling noted in the code), **R10-9**, **R8-2**, **R8-3**.

---

## 29. Round-13 review: the closing round

Review artifact `review-20260920-c720.md`. **The first round in the series that
found no new open item of its own in the automation** — and the first whose most
valuable finding was about the *tests* rather than the code.

### v5.6 stands

The F-1.1 deletion was checked and upheld, including the question it was most
exposed on: *is deleting a safety check ever right?* Yes — when the check guards
a value the bounds already exclude and its only effect is to override a correct
operator input. The asymmetry between the two offsets holds, on three grounds
the AC case lacks: the TRV range admits a wrong sign, `−5.0` was a real incident,
and the offset applies only while the radiator is **cold**, where a bias above
3 °C is physically impossible. That is the §28 criterion exactly — a check earns
its place when it rejects what the bounds allow *and* physics forbids.

F-1.5 and F-4.2/3/4 were confirmed as closing real defects without reopening the
set, and no prior finding regressed.

Two items recorded rather than fixed:

- **`retry_throttle` now has a fourth consumer** (breaker re-arm, safety throttle,
  alert throttle, and now the calibration push). The "one interval, named" rule
  still holds, but changing it now also changes how often the operator hears
  about a bad calibration. Name it when the interval is next revisited.
- **The TRV substitution still falls back to an unmeasured default** (0.0). Correct
  today because the heating gate means it only applies to a cold radiator — and
  the same "substitute a value we have not measured" shape that F-1.1 attacked on
  the AC side. It goes live the moment radiators run. On the heating-season list.

### The test suite is a regression net, not a discovery tool

This is the finding worth carrying. The suite is an **expression-level** oracle:
it evaluates decision expressions against supplied inputs. It has no step order,
no second evaluation after a write, no restart, and no triggers. The review
mapped every round's headline bug against it, and the result is uncomfortable
in the right way:

> **It would not have found the two bugs that mattered most** — §24 (the
> automation blaming the operator for its own command) and P1 (`last_changed`
> resetting at restart). Both are plumbing and persistence defects. It *would*
> have caught the four most recent findings, all of which were expression-level.

The trend that reveals matters more than the tally: **the suite's coverage rises
as the remaining bugs move out of the state machine and into the arithmetic, so
it is weakest exactly where this system has historically been most dangerous.**
Reporting "53 cases, all five shipped bugs detected" without that sentence would
manufacture the confidence the suite exists to replace. It is now the first thing
`tests/climate/README.md` says.

Two of the review's criticisms were actioned in the harness:

- **Substitution is a source-to-source rewrite and can change meaning, not just
  inject a value.** My substitutions happened to be type-correct — `states()`
  replaced by quoted strings, `is_state()` by bare booleans — but only by
  discipline; nothing enforced it. The harness now rejects a mismatched literal,
  and a case was added that only passes under a type-preserving rewrite (a source
  reporting `'unavailable'` must still travel the `| float(-999)` path to reach
  the skip sentinel). `mutate.py` now also proves both guards *fire*, since a
  guard that never triggers is indistinguishable from a broken one.
- **"The tests never contain the logic" was overstated.** The expected-output
  column encodes the intended behaviour as examples, and golden examples drift.
  The claim is narrowed to "never duplicate the *expression*", with the caveat
  stated.

The review's highest-value suggestion is **not** done: a thin *wiring* layer that
fires the loop and asserts side effects on the bookkeeping helpers, covering the
plumbing class. That is the one remaining gap worth building, and it needs care —
the standing rule forbids `automation.trigger`, which skips conditions and
actuates real hardware.

### Stopping criterion

Thirteen rounds, and the returns are now genuinely declining: R10 found three
real bugs, R11 one severe, R12 one, R13 none in the automation. **The review
cycle stops here.** Not on a calendar — resume when one of these fires:

1. **Heating season starts in anger** — sustained outdoor below `heat_below`,
   radiators running. Highest priority: *the heating paths have never run under
   load*, and the open findings cluster there (A11/F-1.6, R8-2, the TRV
   unmeasured default, the untested heat actuation discipline).
2. **Before enabling the first bedroom** — not after. R7-2 and R8-2 are
   explicitly gated on this, and the suite gives false comfort against exactly
   the class that then goes live.
3. **Any observed misbehaviour** — a false or missing notification, an
   unexpected hold, a unit started in the wrong mode. §24 is the model: the
   operator found it, and no review round would have.
4. **A HA major-version bump or a SmartThings/Tado integration change** — P1 was
   triggered by an auto-update, and the restart-guard and grace logic is
   version-sensitive.

The state machine has converged for the cooling and shoulder paths that have
actually run. The remaining risk is concentrated in the unexercised heating
paths and in the plumbing class the suite does not cover — so the next review
budget is worth more spent on the first cold week with a bedroom enabled than on
another round now.
