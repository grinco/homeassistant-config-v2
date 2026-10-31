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

## Run modes

Three overload strategies are used, on purpose, and each follows from what a run does:

- **`single`, `max_exceeded: silent`: the climate loop.** Every run re-reads the whole house
  and decides from scratch, so a trigger that lands during a run loses nothing: the next state
  change or the 10-minute tick decides the same thing. Runs take about 0.1 s (traces,
  2026-10-20), and the only waits are the per-room preset `wait_template`s, 10 s each with
  `continue_on_timeout`, so even the worst case is under a minute and cannot swallow a tick.
  `silent` keeps the log free of a warning for an event that is not a fault.
- **`queued`: the alarm sync, Away, the night mode, the radiators and the bedroom knob.** Each run acts on a
  *transition* (an arm, an edge of the schedule, a target change), and a dropped transition
  is a missed command. Queued runs re-read live state at the start, so a queued echo of the
  automation's own write does nothing. The alarm sync allows 25 and warns when that is
  exceeded, because a queue that deep means two systems are writing to each other in a loop,
  which is a fault worth a log line.
- **`restart`: the purifier and everyone-left.** A newer trigger replaces the older run's
  intent: a new litter-box visit restarts the 30-minute run, and someone arriving cuts short
  the run that is still waiting for the Arm Away button, so the arrival can clear the offer.
  Stacking those would give two runs fighting over one purifier or one notification.

## `battery-watchdog.json`

Sends `sensor.any_low_battery` (in `resolved-sensors.json`) to one adult's phone at 09:00, and
again the moment the list stops being `none`. All the logic is in the sensor, which is also what
Home's Needs attention shows, so the notification and the dashboard cannot disagree.

## `bedroom-knob.json`

The bedroom's Tuya ERS-10TZBVK-AA knob, driving the Torchère only. The knob is in **command**
mode (triple-press on the knob switches it; a write from Z2M times out while it sleeps). In event
mode it reports at most one rotate event every 1.5–2 s however many detents are turned, so a
quick multi-click turn moved the lamp one step (Z2M log, 2026-10-31). In command mode each turn
is one `brightness_step_up`/`_down` carrying `action_step_size`, about 13 per detent and growing
with the turn (25–85 seen), and that size is passed through 1:1. A press is `toggle`. The
event-mode actions (single/double press, `rotate_*` at 25) are still mapped, so the knob keeps
working if it falls back to event mode. MQTT triggers on the knob's topic rather than the EPMatt
blueprint, which reads only the action and drops the step size. `queued`, because each message
is a step and dropping one loses it.
The steps go to Zigbee2MQTT as `brightness_step`, not through `light.turn_on`: Z2M sends that
as a plain ZCL `step`, which a lamp that is off ignores. `light.turn_on` with a step becomes
`moveToLevelWithOnOff`, which turns the lamp on, so a step decided on a stale "on" state, or
retried by Z2M after a timeout, lit lamps that had just been switched off (2026-10-30). The
Aladdin lamp is out of the network for now; add it back here when it is re-paired. The topic
uses the Z2M friendly name, so renaming the lamp in Z2M breaks the turn actions.

## `energy-digest.json`

At 00:10, yesterday's consumption over the Energy dashboard's own meters, from the same
long-term statistics, into three helpers: the total, the AC share, and how many meters
reported. There is no whole-house meter, so it is "the metered devices", never "the house".
The meter list must match the Energy dashboard's (`tests/climate/wiring.py`). No anomaly flag:
ten days of history did not support a threshold (`docs/energy-digest.md`). (Issue #8.)

## `house-morning-briefing.json`

One push at `input_datetime.house_briefing_time`, only while `input_boolean.house_briefing_push`
is on. The helper is created off. It reads the roll-ups (batteries, silent safety sensors,
lights on, the health risk, yesterday's energy) and derives nothing (`docs/house-briefing.md`).
(Issue #6.)

## `house-alarm-sync.json`

Keeps Alarmo (`alarm_control_panel.home`) and the Paradox EVO192 panel (through the Paradox Alarm
Interface add-on over MQTT) in step, both ways, so the house can be armed from Home Assistant or
the keypad. Home and Night both map to Stay on the panel, because night is a house mode rather than
a different level of protection, and Away maps to Away. When the panel refuses to arm, Alarmo is put
back where the panel is and both adults are told why: open zones, a trouble, or the panel being
offline. An Alarmo trigger (leak sensors, once they are added) sends the panel a panic.

It is **disabled** on the instance until a supervised first run at the keypad. The panic mapping in
particular is untested against the panel. The notification targets are neutral placeholders.

## `house-away.json`

Leaving means arming Away, and Away turns the house's automations off (2026-10-14). Each room's
presence lighting is paused, but only in rooms where it was on, so a room someone switched off by
hand stays off on return. The paused list is kept in a text helper, so a restart while away loses
nothing. Then every indoor light and media player is switched off, and a minute later both adults
get one note naming anything still open or on. The corridor keeps its presence lighting, because
it is the way in to the keypad. Coming back (Disarmed, Home or Night) restores exactly the rooms
that were paused. Climate is not here: the climate loop already has its own away band.

## `house-front-door-away.json`

The front door is a zone of the EVO192 panel, but the Alarmo → EVO sync is still disabled, so
arming Away from Home Assistant (the everyone-left offer) leaves the panel disarmed and nothing
watching the door. This tells both adults, time-sensitive, when the SwitchBot lock unlocks or jams (a
jammed lock may have left the door unlocked) or the door opens (the lock's own contact or the panel's entrance zone) while the house is armed Away.
It stays quiet when the panel itself is armed Away, because the panel raises its own alarm, and
while a tracked phone is home: someone coming back opens the door before disarming, and that
was the commonest trigger by far (review 2026-10-20). An
offline panel watches nothing, so that case is told. It only notifies. A returning person whose
phone has not yet reached the home zone still gets the note, and it says so: "If that is you,
disarm". (Issue #7.)

## `house-everyone-left.json`

Ten minutes after the last phone leaves home, one notification to both adults: which lights are
still on, and an offer to arm Away unless the alarm is already Away, arming or going off. Nothing
happens without a button. Arm Away is honoured only if the house is still empty when the button is
pressed, and someone coming home clears the notification. A child's phone counts, so a child home
alone is not an empty house.

Not everyone has a phone. A child can be at home with a sitter while every tracked phone is away,
so the names of anyone who can be home without one are kept in a text helper on the instance (not
here). When it names someone, the offer becomes a question ("Is <name> with you?") and the arm
button is the yes. No answer means no: the alarm is left as it is. Any future automatic arming
must ask the same way.

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

## `magic-areas.json` and `night-schedule.json`

Magic Areas is configured in config entries and the night schedule in `.storage/schedule`, so
neither appears in `automations.yaml` or a dashboard. These two files are exported so the repo shows
which lights each area switches, in which states, and when night starts (21:00–06:00 since
2026-10-21). The schedule only moves the alarm at its edges (`house-night-mode.json`); the alarm
is what decides night. Reasoning: `docs/presence-lighting.md`.

## `hot-water-schedule.json` (not exported yet)

The Tado hot-water zone's active timetable, as set in the Tado app. Until the first run, the
schedule is recorded in `docs/hot-water.md`. Home Assistant cannot read
Tado schedules, so `tests/tado/export.py` reads it from the Tado API. The script signs in with its
own device login, because Tado's refresh tokens rotate and borrowing Home Assistant's would log
the integration out. Run it after changing the schedule in the app. Reasoning: `docs/hot-water.md`.
