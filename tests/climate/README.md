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

## The one rule

**The tests never contain the logic.**

Every expression under test is read out of the running system at run time —
`automations.yaml` for the control loop, `.storage/core.config_entries` for the
resolved-temperature sensors. A case supplies **inputs and an expected output**,
never a reimplementation.

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

## Adding a case

When a review round finds something, add the case **before** shipping the fix,
with `finding=` naming the round. Then run `mutate.py`: if re-introducing the bug
does not turn anything red, the case is not testing what you think.
