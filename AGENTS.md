# Working in this repository

This repo is a **public reference** for a private Home Assistant instance. Nothing here is
deployable: it holds design records and sanitised snapshots of a live configuration.

If you are an AI agent working on this repo, read this before you write, export, or commit
anything.

---

## 1. This repository is public and the instance is a family home

The live instance is named after the people who live there — **including children**. Real
entity ids and friendly names therefore contain given names, surnames and, in at least one case,
a full name in a `person.*` entity.

**None of that may ever be committed.** Exports are anonymised: rooms and people appear under
neutral placeholders, and the published files intentionally do not match the live instance.

### The substitution map is not in this repo, by design

An earlier attempt documented the mapping in a repo README — a table of "live value → published
value". That file republished, in full, exactly the information the anonymisation existed to
remove. **Do not write the mapping down here.** It lives in the operator's local agent memory.

If you are an agent with access to that memory, look for a note about **repo anonymisation**. If
you do not have it, **stop and ask the operator** rather than inventing a mapping or exporting
raw.

---

## 2. Rules for any export

Exports are produced by reading the live instance (`automations.yaml`, `.storage/lovelace.*`,
`.storage/core.config_entries`) and writing sanitised JSON here. Every time:

1. **Anchor every replacement to a word or token boundary.** Naive substring replacement corrupts
   ordinary English and Jinja. Real examples that have bitten:
   - one of the room names is a substring of *deliberately*, *believe*, *relies* and *delivered*,
     all of which occur in the design document;
   - another is a substring of the Jinja keyword `elif`, which appears throughout the automation
     templates. Corrupting it silently breaks the control logic in the published copy.
2. **Verify with canaries, not by eye.** Count a fixed list of those words before and after the
   substitution. If any count changed, the pattern was too greedy — stop and fix it.
3. **Then grep the result** for every original term and expect **zero** hits.
4. **Re-run the scan on the actual export every time.** Each newly exported view can introduce
   names the existing mapping has never seen. A mapping that was complete last week is not
   evidence that it is complete now.
5. **Scan for more than room names.** `person.*` entities, `notify.*` targets and sensor names
   derived from a person's device or desk all carry names. So do `device_tracker.*` and anything
   named after a phone.
6. **Check the commit message too**, not just the files.

### Where the names hide

Entity ids are not the only place. Check: `friendly_name`, card `name` / `primary` / `secondary`,
markdown card bodies, `notify` service targets, automation `alias` and `description`, persistent
notification titles, area names, and the *options* of `min_max` / `group` helpers — those live in
`core.config_entries`, not in any dashboard, so a dashboard-only scan misses them.

---

## 3. Before you commit

```bash
python3 tests/leakcheck.py --commits
```

It reads the terms from `tests/climate/rooms.local.json` (gitignored) and scans every tracked
file plus every unpushed commit and commit message. Run it before any push.

**Word boundaries are not enough, and this is not theoretical.** `\b` does not fire between
`_` and a letter, because `_` is a word character — so `\bNAME\b`-style patterns silently fail
to match `..._NAME_room_area_state`. On 2026-09-21 a dashboard export carrying a Magic Areas
presence entity passed a `\b`-anchored scan and went into a commit. It was caught before the
push, by a scan that used lookarounds excluding only letters and digits. Use those.

- Scan the **committed blobs**, not the working tree: `git grep -i <term> HEAD`.
- Scan the commit message.
- If a name has already been pushed, say so plainly and immediately — it is a public repo and a
  child's name; it needs history rewriting and a force push, not a follow-up commit.
- Also scan for the usual secrets: tokens, passwords, API keys, cookies, coordinates, IPs.

---

## 4. Other conventions

- **Commit attribution:** commits are authored by the repository owner. Do **not** add
  `Co-Authored-By` trailers or "generated with" footers.
- **Exports are snapshots, not sources.** The live instance is authoritative. If someone edits
  through the Home Assistant UI, the files here go stale silently — re-export before relying on
  them, and re-apply the anonymisation when you do.
- **The design record is `docs/climate-control-design.md`.** It is the reasoning; the JSON is the
  artefact. Rationale belongs there and not in the dashboards, which the household uses daily and
  where explanatory text is unwanted.

## Write the test first

**New behaviour starts with a failing test.** Not "write the feature, then cover
it" — the case goes in, it fails for the right reason, *then* the change ships.

Order, every time:

1. **Write the case.** Inputs and expected output, in `tests/climate/cases.py`,
   with `finding=` naming what it locks down.
2. **Run it and watch it fail.** A new case that passes immediately is testing
   nothing — either the behaviour already exists, or the case does not reach the
   code you think it does. Find out which before going further.
3. **Make the change.**
4. **Run the suite.** The new case passes; nothing else moved.
5. **Run `mutate.py`.** Confirm that reintroducing the bug turns something red.

This is not ceremony, and it is not generic advice imported from elsewhere. It
is the direct lesson of this repo's history:

- Twelve review rounds, and **every single one** found that the previous round's
  fix had moved a hazard rather than closed it.
- The worst bug reached production and **pushed the operator a notification
  blaming them** for something they had not done.
- Two fixes in a row — v5.4 and v5.5 — each corrected one direction of a
  two-directional hazard and shipped the mirror of the bug they were fixing.
  Both were written with conviction and a prose failure table.

Every one of those was a change made confidently, verified by reasoning, and
wrong. A failing test written *before* the change is the only step in the
workflow that cannot be satisfied by a convincing argument.

**Two ways a test lies, both seen in this repo:**

- **It cannot fail.** An `ext_recurring` case used a toy timestamp where the
  expression tests against a year-2000 sentinel, so it could never be true — and
  its negative sibling passed for the wrong reason. Step 2 catches this.
- **It does not straddle the threshold.** Checking a 2 °C error at a room
  temperature where both the right and the wrong answer are "don't heat" proves
  direction, not consequence. An assertion about a threshold needs an input that
  **crosses** it.

For anything that cannot be reached by a test — actuation, cloud round-trips,
notification delivery — say so explicitly rather than implying coverage, and
verify it by replicating the decision expression against live state with
`ha_eval_template`. **Never by `automation.trigger`**, which skips conditions and
actuates real hardware.

## Validating a change to the climate automation

There is a test suite at `tests/climate/`. Run it **before and after** any change
to `automation.climate_maintain_per_room_targets` or the `Climate temp *` template
sensors:

```bash
python3 tests/climate/run.py        # scenarios against the LIVE expressions
python3 tests/climate/mutate.py     # confirms the scenarios actually detect bugs
python3 tests/climate/wiring.py     # do the entity ids the templates NAME exist?
```

`run.py` substitutes every entity read with a literal before evaluating — that is what
makes it a decision oracle, and it is also why it **cannot** see a template naming an
entity that does not exist. That shipped once: a sensor read `unknown` in the house with
every case green. `wiring.py` is the other half; run it after any change that introduces
or renames an entity reference.

It reads the expressions out of the running configuration at run time, so it
tests what is deployed, not a copy. **Never put the logic in the test.** A case
supplies inputs and an expected output only.

When a review round finds something, add the case **before** shipping the fix,
with `finding=` naming the round, then run `mutate.py` to confirm the case turns
red when the bug is reintroduced. A case that cannot fail is worse than no case.
