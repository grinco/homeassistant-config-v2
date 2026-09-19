# Climate control — finding status index

**Read this before acting on any climate review chunk.** Six adversarial review rounds produced
~50 findings across six artifacts. Most are closed. This index says which are which, so a future
session does not re-fix something already fixed or trust a chunk describing deleted code.

- Design of record: `docs/climate-control-design.md` (v4.3)
- Automations: `automation.climate_maintain_per_room_targets` (id `1789725511503`),
  `automation.climate_stamp_ha_start`
- 55 helpers. HA 2026.9.3 Supervised, Home.

## Still OPEN — safe to act on

| # | Finding |
|---|---|
| A1 | Hysteresis assumes the unit reports within one tick. Bounded by `settle` (240 s), not eliminated. |
| A7 | A prolonged safety failure alerts on a repeating throttle, not an escalation. |
| A11 | One `climate_ac_sensor_offset` (−2 °C) stands in for three uncalibrated units (Bedroom, Kids room 1, Kids room 2). Measured once, on one unit. |
| M6 | The AC/TRV no-fight invariant is unenforceable until TRV entities exist. **Operator constraint: keep every TRV setpoint at or below the room's NIGHT TARGET (20 °C).** |
| P2 | A setpoint-only change at the wall is classified as a **fault**, not a person: `last_changed` does not move for attribute-only changes, and `last_updated` is bumped by every cloud poll so it is useless as a human signal. Bounded — `will_set_temp` is gated on `not tripped`, so the breaker halts the fight after ~3 ticks and alerts. |
| R5 (cloud re-report) | SmartThings re-emitting an unchanged `hvac_mode` within `human_window` of our last command can still read as a human. Narrowed by the 1200 s cap, not closed. |
| Observation | Whether `heat` above setpoint actually moves air, which decides if the in-season air-filter case should use `fan_only` instead. Needs watching, not a redesign. |

## CLOSED — do NOT reason about current behaviour from these

| Group | Status |
|---|---|
| F1–F9 (round 1) | Closed in v3. |
| A5 → R4-1 → P1 → R6-1 | One liveness trap that relocated four times: the counter, then the hold, then the restart path, then the stamp's dependency chain. Now the breaker never stamps holds, and `unit_moved` carries a restart guard (`lc < uptime − 60`). |
| M1–M11 except M6 | Closed. The per-room boiler flag `climate_boiler_heats_<room>` was **deleted** in v3.4; no per-room boiler configuration exists anywhere. |
| R4-1 … R4-9 | Closed or moot. **The failure counter is no longer consulted for human-vs-fault detection at all** — that now uses `input_datetime.climate_cmd_<room>` vs the entity's `last_changed`. |
| P1 | Closed, and proved in production: during the 2026.9.2 → 2026.9.3 auto-update all five units read `lc = 41 s`; the two-term rule returned `True` for every one (five bogus 2-hour holds), the three-term rule `False` for every one. |
| P3 | **Rejected on the physics.** A heat pump at setpoint 22 in a 24 °C room is above setpoint and idles; it does not heat. Also the operator's explicit specification. |
| P4 | Closed. The `now().minute // 10 == 0` wall-clock gate is gone; throttles use `since_cmd >= retry_throttle` (3000 s) keyed to the per-room command stamp. |
| P6, P7, R4-9 | Doc-accuracy findings, all corrected. |
| P8 | Closed. An inverted house band (`heat_below >= cool_above`) collapses to `shoulder` and raises a config-health notification. |
| P10 | Not reachable — mode and preset are mutually exclusive per tick by construction. |
| P11 | Closed. `settle` raised 120 → 240 s. |
| R6-2 | **Rejected with proof.** `converged = mode_ok and target_ok`; preset is not part of it, so a preset-only difference leaves `diverged` false. For `diverged` and `will_set_preset` to hold together you need `mode_ok and not target_ok` — which is exactly `will_set_temp`, already excluded. |
| R6-3 | Closed in v4.2, before the review was read. Both actuating steps re-read live state at dispatch (`is_state(r.climate, …)`). |
| R6-4 | Closed. The safety alert is **no longer gated on commanding** — it follows the safety condition, throttled by `input_datetime.climate_safety_alert_<room>`. |
| R6-5 | Closed by the config-health notification. |
| R6-6 | **Closed by the hardware.** The units switch preset themselves on a heat start so the mesh opens (observed live: Living room `none` → `quiet`). No automation change was made, and none should be — the proposed fix would have added a preset call, the one call that turns an off unit on in cool. |

## Three hardware facts that caused real shipped bugs

1. `min_temp` 16, `max_temp` 30, `target_temp_step` 1 — a frost setpoint of 7 °C and any
   half-degree value are **silently refused, not rounded**.
2. `climate.set_preset_mode` on an **off** unit **turns it on, in cool**. Verified on the Office AC.
3. A climate entity's `last_changed` does **not** survive an HA restart.
