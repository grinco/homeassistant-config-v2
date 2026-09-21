# Corridor air purifier — design

Status: **implemented and live** (2026-09-20). Version 5, after round 1 of review and
**two live incidents**. The PM2.5 sensor is **assumed broken** — see §2.1.
Instance: HA 2026.9.3 Supervised, Home.

A Xiaomi zhimi mb3 air purifier and a MINI-C self-cleaning litter box share the corridor,
with the purifier directly behind the box. This document covers the automation that runs
the purifier after a cat visit, the corridor's resolved sensors, and — the part that drove
most of the design — what to do with a PM2.5 reading the operator does not trust.

It is a sibling of `climate-control-design.md` and inherits its rules deliberately; where
a decision here exists because of a bug there, the section says so.

---


## The PM2.5 sensor is trusted again (2026-09-21, evening)

`input_boolean.purifier_pm25_trusted` is **on**. The "assumed broken" verdict is withdrawn.

It was set after the sensor failed to move across 46 minutes of full airflow following a cat
visit (incident 7.2). That observation was real, but the conclusion drawn from it was too
strong. History for the same afternoon shows the reading cycling **1 → 2 → 3 → 4 → 6 → 4 → 2
→ 1** repeatedly between 14:03 and 14:33. It responds; it simply spends most of its life at
the floor because the corridor air is clean.

**Why flipping the toggle is a small change, not a risky one.** The early stop was never
gated on the toggle alone:

```jinja
pm_usable: {{ is_state('input_boolean.purifier_pm25_trusted','on') and pm_after_settle >= 2 }}
```

The second clause is a **per-run** responsiveness proof: the reading must actually have risen
above the floor after the settle delay before it is allowed any vote in *that run*. So a run
where the sensor sits at 1 throughout still goes the full 30 minutes, exactly as it does
today. Trusting the sensor restores the originally requested behaviour — *"half an hour or
until the PM reading drops back to 1"* — without removing the guard that made distrusting it
survivable.

**The dashboard banner is gone** along with the `(not trusted)` label on the PM2.5 tile. The
toggle itself stays on the Climate — advanced view, because it is a control rather than
prose, and one switch is still the whole cost of reversing this.

**What the earlier verdict got right, and should be kept:** the assumption lived in a
*toggle*, not in the automation's shape. Withdrawing it cost one service call and two
dashboard edits, and no logic changed. That is the property worth preserving next time a
piece of hardware looks dead.

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

### 2.1 The sensor is assumed broken, and that assumption is a toggle

During incident 7.2 the fan ran **46 minutes at motor speed ~1560**, immediately after a cat
visit, and PM2.5 never left 1. An idle sensor explains a still reading when the fan is off; it
does not explain a still reading through three quarters of an hour of full airflow. **The
inference in §1 is not supported and the operator's original suspicion is.** Their call, on the
evidence: *"for now lets just assume it broken."*

That assumption lives in `input_boolean.purifier_pm25_trusted`, which is **off**. It is a
toggle rather than a rewrite for three reasons:

- **Cleaning the laser intake later is one switch**, not a code change. These units clog and
  pin at a floor value; the operator intends to try.
- **Nothing in the automation's shape encodes a guess about the hardware** that a future reader
  would have to reverse-engineer. The logic says "is this reading allowed a vote", and a helper
  answers.
- **The behaviour barely changes**, which is the point. An unresponsive-but-trusted sensor
  already produced full-window runs. What the toggle buys is that the right thing now happens
  *because it was decided*, not because the reading happened never to rise.

**The settle and the read are still performed while untrusted.** They serve no control purpose
and that is deliberate: every run logs PM before, after settle and final, so if the sensor
starts moving again the line reads `(untrusted - MOVED, worth rechecking)` and the dashboard
card says the same. Deleting the read would make recovery invisible and leave no evidence on
which to ever flip the toggle back.

**It is shown with the evidence**It is shown with the evidence needed to judge it.** A card renders the value, how long it
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

3 (settle) + 25 (wait cap) = **28 minutes**, about the half hour asked for. The 2-minute
hold runs *inside* the 25-minute cap as the `for` on the clear trigger — it is a floor on
how fast the run can end, not an addend. (Round 1 caught the arithmetic double-counting.) The litter box auto-cleans
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

1. **3 minutes** (settle) and **below 2** (threshold) are load-bearing and unmeasured — the
   settle by §3.1's own admission, the threshold because the floor value *is* the failure
   mode. **Favorite level 9**, the 2-minute hold and the 25-minute cap are comfort settings
   in a different class. Round 1 was right that lumping them together hid which ones matter.
2. ~~If the sensor is stuck at 1, every run goes to the full cap.~~ **Superseded by v3.** The
   early stop is now armed only when PM2.5 rose above the floor, so a floor-stuck sensor gets
   no vote and the full window runs by design rather than by accident. Round 1 argued this
   case ends runs at ~5 minutes; that reading of `numeric_state` arming semantics is wrong —
   a trigger whose condition already matches at attach is not armed and never fires — but the
   fix was worth making anyway, because the old design's safety depended on winning that
   argument.
3. **Stuck high** → no early stop, full cap. Bounded and visible. Still true, still tolerable.
4. **Multiple cats.** `mode: restart` restarts the window including the settle. Safe for
   cleaning. The *control* half of this was F4 and is fixed: a manual stop now suppresses
   re-starts for 30 minutes.
5. ~~Nothing reports that the automation ran.~~ **Fixed.** `input_text.purifier_last_run`
   holds one line per run — outcome, duration, PM before/after-settle/final, whether the
   sensor was responsive, corridor temperature before and after. Deliberately temporary.

---

## 7. Two live incidents, and what they cost

### 7.1 The reload (22:07)

A cat used the box at 22:07. **v1 ran.** Writing v2 minutes later reloaded the automation with
that run in flight, and the fan was left on with the ownership flag set.

**A reload is not a restart.** It kills an in-progress run exactly as a restart does, but it
does not raise the `homeassistant` `start` event, so recovery never fired. Recovery now also
triggers on `automation_reloaded`.

Recovery is gated on the **ownership flag alone**. A draft briefly used "flag on OR fan on",
which would have switched off a purifier a person started by hand on every reload and every
restart — the thing this design exists to avoid.

### 7.2 Reading the device too soon (22:23) — the expensive one

A cat visited at 22:23. v2 ran, commanded the fan on, and **declared the start a failure.**
Measured from history:

| time | fan | what happened |
|---|---|---|
| 22:23:05.19 | **on** | our `fan.turn_on`, reported optimistically |
| 22:23:06.38 | **off** | the miio integration polled the device, which had not acted yet |
| 22:23:10 | *(our read)* | saw `off` → **FAILED TO START** → released ownership, stopped |
| 22:23:23.14 | **on** | the device actually started, motor to 1524 |

The run abandoned ownership *while the fan was coming on*. Nothing owned it and nothing would
stop it: **it ran for 46 minutes until the operator noticed.** Worse, `already_running`
(fan on, flag off) would have made every future visit abort — silently, for ever.

**This is the climate `unit_moved` bug in a different device.** That one read a unit's
`last_changed` too soon after commanding it and mistook obedience for a person at the wall.
This one read a fan's state too soon after commanding it and mistook success for failure. v2's
own note said *"never assume the service call worked"* — and then implemented the check as a
single sample at a **guessed 5-second offset**, which is the same error with the opposite sign.

**The fix is to stop sampling at a guess.** The start is confirmed by *waiting* for the fan to
report `on` and hold it 15 seconds, with a 120-second timeout. That is self-timing: it costs
nothing when the device is quick, the 15-second hold ignores the 1.2-second optimistic blip,
and it tolerates a device that takes 18 seconds — or 60 — without any constant needing to be
right. The same hold is now on the human-stop trigger, so the identical flap cannot be misread
as a person switching the fan off mid-run.

**If the start is never confirmed, the fan is commanded off.** Abandoning is what stranded it.

**`already_running` now speaks.** Refusing a fan somebody else started is still right, but a
*silent* refusal is how a stranded fan would have disabled this automation permanently without
a word. It now writes a line saying why it did nothing.

### 7.3 The pattern

Neither incident was found by review. Both were found by the system doing its job while
somebody watched — the reload by editing a file mid-run, the misread by the operator noticing
a fan that would not stop. That is now three times in this project that the worst bug was
found in production and not on paper.

---

## 8. Round-1 review

Artifact `review-20260920-2ca2.md`.

| # | Finding | Verdict | Status |
|---|---|---|---|
| **F2** | Shutdown gated on the persistent ownership flag makes the 25-minute backstop conditional on the very state whose failure is the failure mode. Flag off + fan on → timeout skips the turn-off, boot recovery does not fire (it only acts when the flag *is* set), every later visit refuses to touch the fan → **stranded on for ever** | **Confirmed by trace** | **Fixed** — shutdown turns on `we_started`, a run-local fact from re-reading the fan after commanding it |
| **F3/F1** | The early stop lets a sensor the operator distrusts end every run | **Mechanism disputed** (a `numeric_state` trigger already matching at attach is not armed, so a floor-stuck sensor runs to the cap, not ~5 min) — **but the concern is right** | **Fixed structurally** — the early stop is armed only if PM rose first |
| **F4** | A person who switches the fan off *between* visits has it re-ignited by the next cat, with no signal | **Confirmed by trace** | **Fixed** — 30-minute cooldown after a manual stop |
| F5 | Motor heat biases the corridor reading into the household mean during every run | Confirmed; display-only, control loop unaffected | **Instrumented, not corrected** — the run log records corridor temp before and after so the bias gets measured instead of guessed |
| F6 | The `for` clock's reset behaviour is load-bearing and unstated | Correct | **Documented** (§3.2) |
| F7 | The room with the litter box is excluded from the mould check | Correct, and **coupled to F5** | **Deliberately not actioned** — adding it before the bias is measured would feed a run-correlated temperature into a safety sensor, which is the path §2 exists to block |
| F8 | Boot race could start a spurious run | **Guard already holds** — a restore leaves the previous value non-numeric | No change |
| minor | §3.7 double-counts the hold | Correct | Fixed |

The review's most valuable contribution was not a bug I had missed in code — it was noticing
that **§6.2 analysed the system's headline failure mode backwards**, and that the trust
boundary in §2 was asymmetric in a way the document did not admit. Both are now stated.

---

## 9. What to watch

`input_text.purifier_last_run` after the next few visits:

- **Did PM2.5 leave 1 during the settle?** The line shows `pm before>after-settle>final`. If
  the middle number is always 1 and the line says `UNRESPONSIVE`, the sensor is pinned and
  the operator's original suspicion was right after all.
- **How did the run end?** `cleared` / `full window` / `stopped by hand`. A string of
  `full window` with `UNRESPONSIVE` is the sensor failing, not the air being dirty.
- **Did corridor temperature jump?** The `corridor X>Y` pair is the F5 measurement, and it
  decides whether the corridor may ever join the mould check.
- **Did the fan and the flag move together?** Any cycle where they disagree is F2 returning.
