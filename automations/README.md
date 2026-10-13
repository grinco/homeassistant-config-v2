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

## `house-alarm-sync.json`

Keeps Alarmo (`alarm_control_panel.home`) and the Paradox EVO192 panel (through the Paradox Alarm
Interface add-on over MQTT) in step, both ways, so the house can be armed from Home Assistant or
the keypad. Home and Night both map to Stay on the panel, because night is a house mode rather than
a different level of protection, and Away maps to Away. When the panel refuses to arm, Alarmo is put
back where the panel is and both adults are told why: open zones, a trouble, or the panel being
offline. An Alarmo trigger (leak sensors, once they are added) sends the panel a panic.

It is **disabled** on the instance until a supervised first run at the keypad. The panic mapping in
particular is untested against the panel. The notification targets are neutral placeholders.

## `house-night-mode.json`

The alarm is the house's day/night switch (2026-10-11). `alarm_control_panel.home` in `armed_night`
is night for the climate loop, the lights and Adaptive Lighting's sleep mode. The night schedule
only moves the alarm at its edges, so a manual switch to day or night wins until the next edge.
Alarmo has no sensors, codes or sirens here, so arming it is a mode switch and nothing else.

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

- **"Unreachable" is never read as "off".** The fan drops off the network for
  up to a minute every few minutes, so starts are retried until the fan holds `on`,
  and every stop goes through `purifier-stop-reliably.json`, which waits for the
  device to be reachable and retries until it reports off.

Guard expressions are covered by `tests/climate/`; the sequencing is not, and
the suite's README says why.
