# Automations — sanitised reference exports

These are **reference snapshots**, not deployable config. Two things differ from the live
Home Assistant instance:

1. **The two children's rooms are anonymised**, exported as `Kids room 1` / `Kids room 2`
   with entity ids under `kid1_*` / `kid2_*`. The live instance uses different names.
   Applying these files to Home Assistant as-is would target entities that do not exist.
2. They are a point-in-time export. `automations.yaml` on the instance is authoritative;
   edits made through the UI will not appear here until re-exported.

## Before committing any future re-export

A raw export **will reintroduce identifying information about minors** into this public
repository. Re-apply the anonymisation first. The exact substitution list is deliberately
not recorded here — it is kept with the operator's local notes, since writing it down here
would publish precisely what it exists to remove.

Two rules for whoever does it:

- **Anchor every pattern** to a word or token boundary. Plain substring replacement corrupts
  ordinary English: one of the room names is a substring of *deliberately*, *believe*,
  *relies* and *delivered*, all of which occur in the design document.
- **Verify by canary**, not by eye. Count those words before and after; if any count changed,
  the replacement was too greedy. Then grep the result for the originals and expect zero hits.

## `purifier-after-cat-toilet.json`

Runs the corridor air purifier after the litter box reports a completed visit,
for up to 30 minutes or until PM2.5 returns to baseline.

Two things in it are less obvious than they look:

- **"Until PM drops back to 1" cannot be implemented directly.** The purifier
  reports a floor value whenever its fan is off, because it only draws air over
  its laser sensor while the motor turns. Testing the stop condition immediately
  after starting would be true at once and the unit would stop before doing
  anything, so there is a deliberate settle delay before the sensor is trusted,
  and the clear must hold rather than register once.
- **It only ever turns off a purifier it turned on.** A persistent ownership
  flag records that, the run abandons if somebody switches the unit off by hand,
  and a visit that arrives while the purifier is already running is left alone.

Guard expressions are covered by `tests/climate/`; the sequencing is not, and
the suite's README says why.
