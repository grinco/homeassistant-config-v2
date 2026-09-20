# Corridor air purifier — design

Status: **implemented and live** (2026-09-20). Version 1.0. Never run for real yet.
Instance: HA 2026.9.3 Supervised, Home.

A Xiaomi zhimi mb3 air purifier and a MINI-C self-cleaning litter box share the corridor,
with the purifier directly behind the box. This document covers the automation that runs
the purifier after a cat visit, the corridor's resolved sensors, and — the part that drove
most of the design — what to do with a PM2.5 reading the operator does not trust.

It is a sibling of `climate-control-design.md` and inherits its rules deliberately; where
a decision here exists because of a bug there, the section says so.

---

## 1. The operator's request, and why it could not be implemented literally

> "start the purifier for half an hour or until the pm reading drops back to 1 after the
> cats use the toilet. the purifier is right behind the toilet"

and, separately:

> "i am not sure i can trust the pm2.5 reading from the purifier. its almost always at one"

The second sentence explains the first. **The mb3 only draws air across its laser sensor
while the fan is turning.** With the unit idle it reports a floor value — observed at 1,
with motor speed 0. So:

- "almost always at one" is very likely *not* a broken sensor. It is a sensor that is not
  sampling, because the purifier is off most of the time.
- **"Run until PM drops back to 1" is self-defeating as written.** At the moment the
  automation starts the unit, PM2.5 already reads 1. A stop condition tested then is true
  immediately, and the purifier would switch off before moving any air.

This is the whole reason the automation has the shape it has. The literal implementation
would have appeared to work — it would have turned on and off, and the log would look
right — while never clearing anything.

## 2. Trust: what a distrusted sensor is allowed to do

Three decisions, in increasing order of how much they matter.

**It is displayed.** The climate view has an "Air quality — indoors" group: the fan, PM2.5,
filter life, and the corridor temperature and humidity the purifier also reports.

**It is shown with the evidence needed to judge it.** A card renders the value, how long it
has been unchanged, and whether the fan was running, then says which of three things that
means: *not sampling* (fan off), *sampling* (fan on, reading fresh), or **suspect** (fan on
and unchanged for six hours — a working sensor should move). The reading argues for or
against itself instead of the operator having to remember the caveat. This satisfies the
dashboard rule that only live state earns space: every token of it is computed.

**It drives nothing that alarms.** `binary_sensor.climate_health_risk` was built extensible
for air-quality sensors and PM2.5 is deliberately *not* wired into it. An untrusted sensor
must not be able to raise an alarm, and the climate system already has two incidents where
a bad input reached an actuator through a path nobody had traced.

It *is* allowed to end a run early — the weakest possible authority, bounded by a hard
timeout, where being wrong costs a few minutes of fan.

## 3. The automation

`automation.purifier_run_after_the_cat_toilet` (id `1789947000001`), `mode: restart`.

```
trigger: sensor.cat_toilet_excretion_times_day changed      (id: visit)
trigger: homeassistant start                                (id: boot)

boot  -> if the ownership flag is set, turn the purifier off and clear it

visit -> visit_happened?        previous value numeric AND new value strictly greater
         already_running?       fan on while we do NOT own it  -> abandon
         claim ownership, fan.turn_on, then set preset Favorite
         delay 3 min                          <- let the sensor actually sample
         wait for:  PM2.5 below 2 for 2 min   (cleared)
                    fan -> off                (a person took over)
           timeout: 25 min
         we_may_stop?           fan still on AND we still own it -> turn off
         release ownership
```

### 3.1 The settle delay is the point

Three minutes of fan before the stop condition is armed. Without it the automation is a
no-op that looks healthy (§1). The number is a judgement, not a measurement: long enough
for a bedroom-sized unit to move the corridor's air past its own intake, short enough that
a genuinely clear corridor is not held for long. **It is the single most load-bearing
constant in the design and it is unvalidated.**

### 3.2 The clear must hold

`below: 2` for **two minutes**, not a single sample. One reading at 1 from a sensor the
operator distrusts is not evidence the air is clear. `below 2` covers 0 and 1 because the
sensor reports whole µg/m³.

### 3.3 Never turn off what we did not turn on

If the purifier is already running when a cat visits, a person started it, and switching it
off half an hour later would be taking control away from them. `already_running` detects
that and the run ends immediately. The wait also watches for the fan going off, so a manual
switch-off abandons the run rather than being fought.

This is not hypothetical caution. On 2026-09-20 the climate automation stamped a two-hour
hold on a room and pushed the operator a notification blaming them for a change they had
not made. The rule that came out of it — *only ever act on what you can actually establish,
and never take control away from the operator* — is applied here before it could bite.

### 3.4 The visit counter is not a clean event

`excretion_times_day` resets to **0 at midnight** and returns from `unknown` after a
restart. A bare state trigger fires on both. `visit_happened` requires the previous value to
be numeric *and* the new value strictly greater, rejecting a reset, a restore, and a
repeated identical report from a cloud integration.

### 3.5 Ownership survives a restart; a run does not

`mode: restart` means a second cat restarts the timer, which is wanted. But an HA restart
mid-run loses the run and would leave the purifier on indefinitely, so ownership lives in a
persistent `input_boolean` and the boot trigger clears it. This is the P1 lesson from the
climate work, where `last_changed` resetting at boot was misread as everyone touching
everything at once.

### 3.6 Ordering

The preset is set *after* `fan.turn_on`, never before. On the sibling Samsung units a
preset sent to an off device turns it on in an unexpected mode; the same discipline is
nearly free here. It is `continue_on_error` because the unit running matters more than the
mode it runs in.

### 3.7 Timing

3 (settle) + 25 (wait cap) + 2 (hold) = **30 minutes**, as asked. The litter box auto-cleans
six minutes after a visit and the rake stirring is a second odour burst, so the window
covers it deliberately.

---

## 4. Corridor sensors and the aggregates

The purifier reports corridor temperature and humidity. Both now feed the household and
downstairs means (upstairs untouched, the corridor being downstairs).

They go in through a **resolved sensor of the corridor's own**, not directly. The invariant
is that aggregates read resolved per-room sensors and never raw device probes: mixing a
probe in would contradict the record and mean a better corridor sensor later has to be
wired in twice. The corridor's version is thinner than a room's — one source, no fallback,
**no offset**, because any bias from the unit's own motor heat is unmeasured and inventing a
correction is what round 12 of the climate review was about.

The corridor is **not** a controlled room. The climate loop's room list is unchanged.

**Known gap.** `binary_sensor.climate_health_risk` iterates an explicit five-room list, so
the corridor joined the *averages* but not the *mould check*. That is the status quo rather
than a decision — the corridor now has the temperature and humidity the check needs, and it
is the room with the litter box in it. Raised, not actioned.

---

## 5. What is tested, and what is not

Guard expressions are covered by `tests/climate/`, extended for this automation:
`visit_happened` across a real visit, the midnight reset, a restart restore, an unchanged
repeat and the boot trigger; `already_running` and `we_may_stop` across ownership. Four
mutations — bare state trigger, missing numeric guard, stopping a person's purifier, taking
over a running one — each turn a case red.

**The sequencing is not tested and cannot be by that harness.** Turn on → settle → wait →
turn off is exactly the class the suite's README names as its blind spot: no step order, no
restart, no triggers. This automation is almost entirely that class.

**It has never run.** Every statement about its behaviour is derived from the live guards
and the device's reported state, not from an observed cycle.

---

## 6. Open questions

1. **3 minutes** (settle), **2 minutes** (hold), **25 minutes** (cap), **below 2**
   (threshold) and **Favorite level 9** are all judgements. None is measured.
2. If the sensor *is* genuinely stuck at 1, every run goes to the full cap. Tolerable, and
   the dashboard card would say so — but the automation cannot tell.
3. If it is stuck *high*, the early stop never fires and every run hits the cap. Also
   tolerable, also invisible to the automation.
4. Multiple cats in quick succession: `mode: restart` restarts the window, which is right,
   but it also re-runs the settle delay.
5. Nothing reports that the automation ran. Deliberate — a notification per cat visit would
   be intolerable — but it means a silent failure stays silent.
