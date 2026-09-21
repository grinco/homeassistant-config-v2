# Proposal — hold reasons, and moving the decision out of the loop

Status: **reviewed 2026-09-21** (`review-20260921-a472`). **Change A shipped** as v5.9.
**Change B stopped** and folded into the presence work — see "Outcome" at the end.
Companion to `climate-control-design.md` v5.8.

Two changes, independent, presented together because the second is only safe if the first lands
first. Neither adds behaviour; both are about making existing behaviour legible.

---

## Why these two, and not the ones that look bigger

The per-room loop has 43 variable names. Measured by purpose:

| | names |
|---|---|
| reads (entity → variable) | 16 |
| **decision** (`mode`, `want_target`, `set_target`, `target`, `is_safety`, `needs_temp`, `target_ok`) | **7** |
| **dispatch / timing** (`in_flight`, `unit_moved`, `standdown`, `may_act`, `diverged`, …) | **20** |

**All three of the worst bugs in this project lived in dispatch/timing** — `unit_moved` reading
state too soon (§24), the purifier stranded by a 5-second re-read, and safety resolved but never
dispatched (§31). A "decide/act split" therefore extracts the smallest and safest third and
leaves the two-thirds where the bugs actually are. It is worth doing for what it *does* buy —
one implementation of the decision, inspectable, with history — and **not** because it reduces
the bug class. It does not, and an earlier version of this recommendation implied that it would.

The change that *would* attack dispatch complexity is a custom component: 25 of the 71 helpers
are per-room timestamps that exist only because HA has no structured restart-safe state. That is
deferred — see the last section.

---

## Change A — a hold needs to say why it exists

### The problem

`external_moved` and `standdown` both stamp the *same* helper,
`input_datetime.climate_manual_until_<room>`, with the same value and the same semantics. After
the fact nothing distinguishes them. Round 14 (F14-2) found this, and v5.7 made it worse: the
phone push used to be the only differentiator, and v5.7 removed the push for stand-downs. So the
dashboard now shows two qualitatively different situations identically:

- *somebody picked up the remote and switched this unit to cool* — worth knowing
- *the unit power-saved an empty room* — entirely routine

It also breaks the rule this document has enforced since §26: **state must not assert more than
it can know.** `climate_manual_until_<room>` says "a person has this room". For a stand-down
that is false.

### The change

One `input_select.climate_hold_reason_<room>` per room, options ordered:

```
none  |  standdown  |  external
```

`none` is **first deliberately** — a freshly created or reset `input_select` takes its first
option, and this project has already had an incident from a helper arriving at its default (the
−5.0 TRV offset, §20). The failure direction must be the inert one.

Written at the moment a hold is stamped, by whichever branch stamps it. Read only while a hold
is live, so a stale value behind an expired hold is never shown.

### Why not the cheaper options

- **Derive it from `r.ext`.** A stand-down does not stamp `r.ext` and an override does, so
  `hold_active AND ext_ts ≈ hold_start` would recover the reason with no new helper. Rejected:
  it reconstructs a boolean from arithmetic on two timestamps and breaks silently the moment
  `manual_hold_hours` changes mid-hold. This project has twice been bitten by state that was
  *inferred* rather than *recorded* (§24, §31).
- **Separate hold stamps per reason.** Rejected: that puts two sources into the mode law's
  `manual_active` branch — a change to the control path, for a labelling problem.

### What it must not do

The hold *mechanism* stays identical: same stamp, same expiry, same precedence below safety.
Only the label is new. If this change alters when a hold starts or ends, it is wrong.

---

## Change B — the decision moves into a per-room verdict sensor

### The change

A template sensor per room, `sensor.climate_verdict_<room>`:

- **state** — the resolved mode: `heat` / `cool` / `off` / `fan_only` / `manual` / `skip`
- **attributes** — `target` (the commanded setpoint, rounded and clamped), `is_safety`, and
  `reason` (`frost` / `away_floor` / `away_ceiling` / `manual` / `comfort` / `filter` /
  `shoulder` / `disabled` / `no_reading`)

The automation then **reads** it and drops `mode`, `want_target`, `set_target`, `is_safety` and
`needs_temp` from its own chain.

### The rule that makes this safe or unsafe

**The automation must read the verdict, never recompute it.** A verdict sensor that merely
*mirrors* a decision the automation still makes is two implementations that will drift — exactly
what §21 forbade for temperature, and the reason the resolved-temperature sensors exist. If this
ships as a display mirror it is a net negative and should not ship at all.

### The failure mode it introduces

The automation gains a dependency on an entity that can be `unknown` — at boot, or if the
template errors. That must resolve to **`skip`**, the existing sentinel: command nothing, leave
the room alone, let the blackout alert speak. It must **not** resolve to `off`, which would
silently stand every room down.

Same hazard as §26's "no usable reading", and it needs the same treatment: *the absence of a
verdict is not a verdict.*

### What it buys, honestly

- **One implementation of the decision** — §21's argument applied to the verdict rather than the
  temperature.
- **History.** `sensor.climate_verdict_office` becomes graphable: when did this room last want
  heat, and why. Today that exists only inside a trace.
- **The presence work gets easier.** When detectors land, occupancy enters the decision in one
  template rather than in the middle of a 115-step automation.

### What it does not buy

It does not reduce dispatch/timing complexity, where every serious bug has been, and it does not
make the sequencing testable. The suite already tests the decision expressions by binding
variables; this changes *where* they are tested, not *whether*.

---

## Sequencing question for review

Change B touches the most-reviewed part of the system, in shoulder season, with the heating path
still never exercised under load (R13 trigger #1), and with presence detectors arriving within
weeks that will change the decision anyway.

**Is B better done now, or once — after presence lands — so the decision is restructured and
extended in one change rather than two?** Change A is small and useful either way.

---

## When to revisit the custom component

Not now, and the argument is worth recording so it is not re-litigated from scratch.

**For:** 25 of 71 helpers are per-room timestamps that exist only because HA has no structured,
restart-safe per-entity state, and ~20 dispatch/timing variables are hand-rolled state-machine
bookkeeping. A component gets both for free, with ordinary unit tests over exactly the
sequencing that `tests/climate/` structurally cannot reach.

**Against, today:** fourteen rounds of correctness live in this implementation's details. The
design record transfers; the paranoia does not.

**Revisit when the presence detectors arrive.** That is a real behaviour change, and
re-architecting while adding wanted behaviour is a better trade than re-architecting for its own
sake.

---

## Outcome — the review, and what changed

`review-20260921-a472`, taken **before** anything was deployed. This was the first round in the
project's history to review a design rather than a running system, and it stopped half of it.

### Change A — approved, shipped as v5.9, with one addition

The two rejections held: deriving the reason from `r.ext` arithmetic is the "inferred rather
than recorded" shape that produced §24 and §31, and separate hold stamps would put two sources
into the mode law for a labelling problem.

**A3 was a genuine catch.** The proposal left the label in place behind an expired hold, gated
only by every consumer remembering to check `hold_active`. That is the same *"state asserts more
than it can know"* defect A exists to close, re-entered through a missed gate — and somebody
would eventually miss it. The label is now **cleared when the hold is no longer live**.

The clear **re-reads `r.manual`** rather than using `manual_active`, which is sampled at the top
of the room's iteration and therefore predates any hold stamped on this tick; using it would
clear the label a moment after setting it. Same discipline as the `is_state()` re-reads on the
actuating steps. The `and != 'none'` term keeps it idempotent — verified at zero writes in
steady state, not five per tick.

The review also corrected a loose citation: the §20 incident was a *number* helper coming up at
its `min`, whereas an `input_select` takes its first option on **creation and on a manual
reset**. Different mechanism, same conclusion — `none` first — and the reset path is the more
likely one in production, which is what A3's clear now also covers.

### Change B — stopped, and the reason is a contradiction in this document

The review found four hazards B did not list:

| | |
|---|---|
| **The decision stops being atomic with the dispatch.** A template renders asynchronously, so the automation would read *"the decision as of the last render"*, not the decision | Not listed |
| **The trigger question is unanswered, and both answers regress something.** Trigger on the verdict and a source flap wakes the loop (R7-7 amplification, now on the decision itself); don't, and a real verdict change waits up to ten minutes (R10-9, re-introduced by design) | Not listed |
| **Partial attribute availability.** State can render `heat` while the `target` attribute fails — a verdict that says *act* with no setpoint to act with. The current atomic computation cannot produce that state | Not listed |
| **Recorder amplification, and attributes aren't recorded by default** — so the "and why" half of the history benefit needs *more* entities, not the one B proposed | Not listed |

And the finding that settles it: **this document contradicts itself.** It lists *"the presence
work gets easier — occupancy enters the decision in one template"* as a benefit of B, then leans
toward doing B *after* presence. If presence ships into the 115-step automation first, that
benefit is never realised. B's strongest justification is destroyed by the sequencing B was
drifting toward, and I did not notice.

The review's resolution, which is right: **fold B into the presence design so the decision
template is born with occupancy in it.** One refactor instead of two, the benefit actually
realised — and the four hazards above must be answered *in that proposal*, on day one, because
three of them are trigger and sequencing defects that `tests/climate/` is structurally blind to.

### The custom component — reframed

Two corrections worth carrying:

- *"The design record transfers; the paranoia does not"* is only true **after** the record is
  brought current. Fourteen rounds have repeatedly found it stale — §2/§4 counts, the offset
  left out of the range-check set, "safety is untouched" asserted without showing the dispatch.
  Confidence in the record as a transfer medium should be lower than this document claimed.
- *"Revisit when presence lands"* is the right **trigger** but the wrong **disposition**.
  Presence is the first feature to touch *both* the decision and the dispatch, and it lands
  squarely in the 20 dispatch/timing names where all three worst bugs lived. So the question is
  not "ship presence, then maybe rewrite" but **"is a component the right vehicle *for*
  presence"** — because that is exactly when unit-testable sequencing is worth most.
