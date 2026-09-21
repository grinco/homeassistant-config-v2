# Climate decision tests

Programmatic validation of the climate automation's decision logic, against the
**live configuration** — not a copy of it.

```bash
python3 tests/climate/run.py        # the scenario matrix
python3 tests/climate/mutate.py     # does the matrix actually detect anything?
```

Both exit non-zero on failure. No setup is needed on the Home Assistant host:
the runner uses the local `ha-mcp` endpoint from `~/.claude.json` as transport.
Elsewhere (CI, another machine), set `HA_TOKEN` or drop a long-lived token in
`tests/climate/.ha_token` (gitignored), and `HA_URL` if it is not `:8123`.

## What this CANNOT catch

Read this before trusting a green run. **A suite that oversells itself is worse
than no suite — it manufactures confidence.**

This is an **expression-level** oracle. It evaluates decision expressions
against supplied inputs. It has no notion of step order, no second evaluation
after a write, no restart, and no triggers. So it is blind to:

- **Sequencing and TOCTOU.** The `is_state()` re-reads on the actuating steps
  exist because a value sampled at the top of a room's iteration is stale ~17
  steps later. There is only one evaluation here, so "the state changed between
  step 3 and step 20" is inexpressible.
- **How variables get populated.** Cases *bind* `lc`, `since_cmd`, `temp`.
  Nothing checks that the live automation sources them from the right field —
  `last_changed` vs `last_updated`, the right stamp, a field that survives a
  restart.
- **Persistence and restart semantics.** No restart happens here.
- **Trigger coverage.** A case can assert the correct verdict for a season
  crossing while the automation still only re-evaluates on the `/10` tick.
- **The repeat loop.** Rooms are tested independently; a global sampled once at
  the top and stale by room 5, or a write in room 1 read by room 2, is invisible.
- **Actuation, cloud round-trips, notification delivery.**

**Concretely: this suite would NOT have found the two bugs that mattered most.**

| bug | why it was missed |
|---|---|
| The 2026-09-20 `unit_moved` bug — the automation blamed the operator for its own command | Plumbing. The case here binds `lc` directly; finding the bug required knowing an obeying unit changes ~1.5 s *after* the command. The case encodes knowledge gained *from* the incident |
| P1 — `last_changed` resets at restart, so a routine update looked like everybody touched everything | Persistence. There is no restart in this harness |

Both were found the hard way: one by the operator, from a false accusation; one
by an unplanned auto-update an hour after the guard shipped.

**So what is it good for?** Regression. Of the thirteen review rounds, it would
have caught the four most recent headline findings (R7, R10-7, F11-1, F-1.1) —
all expression-level — and locks in every fix since. Its coverage rises as the
remaining bugs move out of the state machine and into the arithmetic, which
means it is weakest exactly where this system has historically been most
dangerous. Treat a green run as "nothing known has regressed", never as
"this is correct".

## The one rule

**The tests never duplicate the expression.**

Every expression under test is read out of the running system at run time —
`automations.yaml` for the control loop, `.storage/core.config_entries` for the
resolved-temperature sensors. A case supplies **inputs and an expected output**,
never a reimplementation.

(The claim is deliberately narrow. The expected-output column *does* encode the
intended behaviour — as examples rather than as an expression. That is what any
golden test does, and it drifts the same way: a case authored against an older
expression can keep passing while meaning something different. What is avoided
is a second copy of the *logic*, which would have agreed with every bad fix.)

This matters more here than in most codebases. The entire failure history of
this automation is *fixes that moved a hazard rather than closing it* — twelve
review rounds, and the worst bug reached production and blamed the operator for
something they had not done. A suite holding its own copy of the logic would
have agreed with every one of those fixes, because it would have been written
from the same misunderstanding.

## What a case looks like

```python
A(case("an obeying unit is NOT an external change", "unit_moved", "False",
       {"since_cmd": 2.0, "settle": 240.0, "human_window": 1200, "uptime": 99999.0},
       {LC: "{% set lc = 1.5 %}"},
       finding="THE 2026-09-20 LIVE BUG: a unit obeys ~1.5s later, so "
               "'lc < since_cmd' was true for ever after any successful command"))
```

- `given` binds the automation's own variables.
- `subs` replaces an impure read (`states(...)`, `now()`) with a literal.
- `finding` names what the case locks down, and is printed on failure — so a red
  test tells you *which* hazard just came back, not merely that something broke.

**Every substitution must match.** If one does not, the harness raises instead of
running the case. A rule that silently failed to match would leave the expression
reading live state, and the case would pass for the wrong reason. That guard has
already earned itself: removing house hysteresis deletes the read one case
substitutes, and the suite errors rather than going green.

## Two failure modes this suite was built to prevent

1. **A test that cannot fail.** On its first run, one case expected `True` and got
   `False` — the input used a toy timestamp where the expression tests against the
   year-2000 sentinel. Its sibling negative case was passing *for the wrong reason*.
   Both are fixed, and the lesson is in `cases.py`.
2. **A test that straddles nothing.** An assertion about a threshold needs a case
   whose input crosses it. Verifying a 2 °C error at a room temperature where both
   the right and wrong answer are "don't heat" proves direction, not consequence.

## Known failure modes of the harness itself

- **The "rendered to source" guard can misfire both ways.** A case that legitimately renders to
  an empty string is hard to distinguish from one that failed to evaluate. If you add a case
  whose expected value is `""`, confirm it fails when you break the expression.
- **Chunking shrank the sentinel-split blast radius; it did not remove it.** One bad case now
  poisons its own chunk of 12 rather than all 99, but within a chunk the same misalignment is
  possible. If a chunk reports several odd failures at once, suspect one bad case in it rather
  than a real regression.
- **Run the expression check BEFORE deploying, not after.** v5.7 went live and *then* the suite
  went red. A more robust harness is not a substitute for `ha_eval_template` against the change
  first. That discipline caught nothing on v5.7 because it was not run.

## Adding a case

When a review round finds something, add the case **before** shipping the fix,
with `finding=` naming the round. Then run `mutate.py`: if re-introducing the bug
does not turn anything red, the case is not testing what you think.
