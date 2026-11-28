"""The scenario matrix.

Every case names the finding it locks down.  Cases hold INPUTS and an EXPECTED
OUTPUT only -- never the logic.  When a round of review finds something, the
case goes here before the fix ships, so the next round cannot quietly undo it.

`given`  binds automation variables for the expression under test.
`subs`   replaces an impure read with a literal.  Every rule must match, or the
         harness errors -- a silently-unmatched substitution would leave the
         expression reading live state and pass for the wrong reason.
`expect` is compared as a trimmed string ("True"/"False" for booleans).
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import harness  # noqa: E402  -- for the gitignored room-alias map, see load_rooms()

# Defaults mirroring the live configuration, so a case only states what it varies.
BASE = dict(
    temp=21.0, safety_on=True, comfort=True, frost=7.0, away_min=18.0, away_max=30.0,
    manual_active=False, away=False, enabled=True, house="heat", now_mode="off",
    target=22.0, hyst=1.0, room_hyst=0.5, filter_on=False,
    has_rad=False, night=False, boost=1.5, preheat=False, window_open=False, sleeping=False,
)

def case(name, expr, expect, given=None, subs=None, finding=""):
    merged = dict(BASE)
    merged.update(given or {})
    return dict(name=name, expr=expr, expect=expect, given=merged, subs=subs, finding=finding)


CASES = []
A = CASES.append

# ---------------------------------------------------------------- mode: precedence
A(case("skip outranks every safety branch", "mode", "skip",
       {"temp": -999.0}, finding="F11-1 / R10-7: no reading means no floor either"))
A(case("frost outranks the away floor", "mode", "heat",
       {"temp": 5.0}, finding="v3.1"))
A(case("away floor heats", "mode", "heat", {"temp": 17.0}, finding="v3.1 cat floor"))
A(case("away ceiling cools", "mode", "cool", {"temp": 31.0}, finding="v3.1"))
A(case("safety hatch off disables the floor", "mode", "off",
       {"temp": 5.0, "safety_on": False, "comfort": False},
       finding="R6: climate_safety_always is a true master hatch"))
A(case("manual hold outranks comfort", "mode", "manual",
       {"manual_active": True, "temp": 15.0, "safety_on": False}, finding="v3.2"))
A(case("safety outranks the manual hold", "mode", "heat",
       {"manual_active": True, "temp": 15.0}, finding="v3.3"))
A(case("comfort off leaves the room alone", "mode", "off",
       {"comfort": False, "temp": 25.0}, finding="v3"))
A(case("away turns the room off", "mode", "off", {"away": True}, finding="v3"))
A(case("disabled room stays off", "mode", "off", {"enabled": False}, finding="v4"))

# ---------------------------------------------------------------- mode: comfort + hysteresis
A(case("heat below target", "mode", "heat", {"temp": 20.0}, finding="v4"))
A(case("heat stops above target", "mode", "off", {"temp": 23.5}, finding="v4"))
A(case("heat releases well past target", "mode", "off",
       {"temp": 23.5, "now_mode": "heat"}, finding="v3"))
A(case("cool above target", "mode", "cool",
       {"house": "cool", "temp": 24.0, "target": 22.0}, finding="v4"))

# ------------------------------------------------ v5.10: the band moved below target
# Until 2026-09-24 the hysteresis was an OVERSHOOT band ABOVE the target:
# a heating room kept heating until `temp >= target + hyst`. The unit is only
# ever commanded `target`, and it stops at its own setpoint - so that exit could
# not be reached by the unit's own action, and `off` was unreachable. Observed
# live: the living room sat in `heat` from 10:53 to at least 17:30 having burned
# 1.13 kWh before 13:00 and ~nothing after, room flat at 22.6 against a 22
# target and an exit that wanted 24.0.
#
# The band is now a RE-ENTRY deadband BELOW target: heat until the room reaches
# target, then wait until it falls `room_hyst` below before restarting. Each
# pair below straddles the threshold it is about, because a case that does not
# cross the line proves direction, not consequence.
_V510 = "v5.10: exit band sat above the commanded setpoint, so off was unreachable"

A(case("heating stops once the room reaches target", "mode", "off",
       {"temp": 22.6, "target": 22.0, "now_mode": "heat", "hyst": 2.0},
       finding=_V510 + " (the live 2026-09-24 living room)"))
A(case("heating continues below target", "mode", "heat",
       {"temp": 21.8, "target": 22.0, "now_mode": "heat", "hyst": 2.0},
       finding=_V510 + " - the other side of the same threshold"))
A(case("an idle room waits out the deadband", "mode", "off",
       {"temp": 21.8, "target": 22.0, "now_mode": "off", "room_hyst": 0.5},
       finding=_V510 + " - re-entry must not flap at the setpoint"))
A(case("an idle room restarts past the deadband", "mode", "heat",
       {"temp": 21.4, "target": 22.0, "now_mode": "off", "room_hyst": 0.5},
       finding=_V510 + " - and must still restart"))

# The mirror. v5.4 and v5.5 each corrected one direction of a two-directional
# hazard and shipped the mirror of the bug they were fixing; these four exist so
# that cannot happen a third time.
A(case("cooling stops once the room reaches target", "mode", "off",
       {"house": "cool", "temp": 22.0, "target": 22.0, "now_mode": "cool", "hyst": 2.0},
       finding=_V510 + " - cooling mirror"))
A(case("cooling continues above target", "mode", "cool",
       {"house": "cool", "temp": 22.4, "target": 22.0, "now_mode": "cool", "hyst": 2.0},
       finding=_V510 + " - cooling mirror, other side"))
A(case("an idle room waits out the cooling deadband", "mode", "off",
       {"house": "cool", "temp": 22.3, "target": 22.0, "now_mode": "off", "room_hyst": 0.5},
       finding=_V510 + " - cooling mirror, re-entry"))
A(case("an idle room restarts past the cooling deadband", "mode", "cool",
       {"house": "cool", "temp": 22.6, "target": 22.0, "now_mode": "off", "room_hyst": 0.5},
       finding=_V510 + " - cooling mirror, restart"))
A(case("the air filter still overrides the cooling deadband", "mode", "cool",
       {"house": "cool", "temp": 18.0, "target": 22.0, "now_mode": "off",
        "filter_on": True},
       finding=_V510 + " - the filter short-circuit must survive the rewrite"))
A(case("shoulder runs nothing", "mode", "off", {"house": "shoulder"}, finding="v4"))
A(case("air filter runs fan_only in shoulder", "mode", "fan_only",
       {"house": "shoulder", "filter_on": True}, finding="v4 air filter"))
A(case("air filter heats with no thermal need", "mode", "heat",
       {"temp": 24.0, "filter_on": True}, finding="v4 air filter"))

# ---------------------------------------------------------------- setpoint clamping
A(case("frost 7 is lifted to the unit floor", "set_target", "16",
       {"want_target": 7.0, "umin": 16.0, "umax": 30.0},
       finding="v3 shipped an unsendable 7C setpoint"))
A(case("half degrees are rounded away", "set_target", "22",
       {"want_target": 21.5, "umin": 16.0, "umax": 30.0},
       finding="v3: target_temp_step is 1"))
A(case("above max clamps to the unit ceiling", "set_target", "30",
       {"want_target": 35.0, "umin": 16.0, "umax": 30.0}, finding="v3"))

# ---------------------------------------------------------------- unit_moved: the live bug
LC = "{% set lc = (now() - states[r.climate].last_changed).total_seconds() %}"
A(case("an obeying unit is NOT an external change", "unit_moved", "False",
       {"since_cmd": 2.0, "settle": 240.0, "human_window": 1200, "uptime": 99999.0},
       {LC: "{% set lc = 1.5 %}"},
       finding="THE 2026-09-20 LIVE BUG: a unit obeys ~1.5s later, so "
               "'lc < since_cmd' was true for ever after any successful command"))
A(case("a real external change is detected", "unit_moved", "True",
       {"since_cmd": 900.0, "settle": 240.0, "human_window": 1200, "uptime": 99999.0},
       {LC: "{% set lc = 100 %}"}, finding="v3.2"))
A(case("a restart is not everybody touching everything", "unit_moved", "False",
       {"since_cmd": 900.0, "settle": 240.0, "human_window": 1200, "uptime": 60.0},
       {LC: "{% set lc = 41 %}"},
       finding="P1: confirmed in production during the 2026.9.2->9.3 update"))
A(case("a stale change is too old to count", "unit_moved", "False",
       {"since_cmd": 9000.0, "settle": 240.0, "human_window": 1200, "uptime": 99999.0},
       {LC: "{% set lc = 1500 %}"}, finding="v3.2 human_window"))

# ---------------------------------------------------------------- house mode
PREV = "states('input_select.climate_house_mode')"
A(case("dead outdoor sensor falls to shoulder even when pinned", "house", "shoulder",
       {"outdoor": -999.0, "heat_below_out": 17.0, "cool_above_out": 28.0, "hyst": 1.0},
       {PREV: "'heat'"}, finding="R10-4: branch order, tested BEFORE prev"))
A(case("inverted band falls to shoulder even when pinned", "house", "shoulder",
       {"outdoor": 20.0, "heat_below_out": 28.0, "cool_above_out": 17.0, "hyst": 1.0},
       {PREV: "'cool'"}, finding="R10-5 / P8: cannot pin on an inverted band"))
A(case("heat holds inside the hysteresis margin", "house", "heat",
       {"outdoor": 17.3, "heat_below_out": 17.0, "cool_above_out": 28.0, "hyst": 1.0},
       {PREV: "'heat'"}, finding="v5.3: the 2026-09-20 17.3C flap"))
A(case("heat releases past the margin", "house", "shoulder",
       {"outdoor": 18.5, "heat_below_out": 17.0, "cool_above_out": 28.0, "hyst": 1.0},
       {PREV: "'heat'"}, finding="v5.3"))
A(case("no memory uses the bare threshold", "house", "heat",
       {"outdoor": 16.0, "heat_below_out": 17.0, "cool_above_out": 28.0, "hyst": 1.0},
       {PREV: "'unknown'"}, finding="v5.3: a bad helper costs stickiness, never correctness"))

# ---------------------------------------------------------------- blackout grace
NOW = "now().timestamp()"
A(case("boot noise is suppressed", "no_temp", "False",
       {"temp": -999.0, "safety_on": True, "bad_armed": True, "bad_ts": 1000.0,
        "boot_grace": 600, "uptime": 120.0}, {NOW: "1700.0"},
       finding="F11-3 / R8-1: restored boot grace"))
A(case("a genuine blackout fires", "no_temp", "True",
       {"temp": -999.0, "safety_on": True, "bad_armed": True, "bad_ts": 1000.0,
        "boot_grace": 600, "uptime": 5000.0}, {NOW: "1700.0"}, finding="R7-9"))
A(case("the per-room grace still holds", "no_temp", "False",
       {"temp": -999.0, "safety_on": True, "bad_armed": True, "bad_ts": 1000.0,
        "boot_grace": 600, "uptime": 5000.0}, {NOW: "1120.0"}, finding="R10-6"))
A(case("a stale restart stamp cannot suppress", "no_temp", "True",
       {"temp": -999.0, "safety_on": True, "bad_armed": True, "bad_ts": 1000.0,
        "boot_grace": 600, "uptime": 99999999.0}, {NOW: "1700.0"},
       finding="F-3.1: the AND is safe in both directions"))
A(case("a never-armed stamp never alerts", "no_temp", "False",
       {"temp": -999.0, "safety_on": True, "bad_armed": False, "bad_ts": 946681200.0,
        "boot_grace": 600, "uptime": 99999.0}, {NOW: "1700.0"},
       finding="R10-6: year-2000 sentinel, not none"))

# ---------------------------------------------------------------- external change
A(case("an external change during our settle window is not counted", "external_moved", "False",
       {"active": True, "reachable": True, "mode_ok": False, "in_flight": True,
        "unit_moved": True}, finding="M1/R4-2"))
A(case("a genuine external change is counted", "external_moved", "True",
       {"active": True, "reachable": True, "mode_ok": False, "in_flight": False,
        "unit_moved": True, "now_mode": "cool"},
       finding="v3.2 - now_mode must be an ACTIVE mode: a change to 'off' is a stand-down"))
# NOTE: ext_ts must be a REAL timestamp. The expression first tests
# `ext_ts > 1e9` to distinguish "never happened" (the year-2000 sentinel) from
# a real event, so a toy value like 1000.0 can never be recurring -- and the
# negative case would then pass for the WRONG REASON. Caught by this suite on
# its first run, which is the whole argument for having it.
EXT_T = 1789900000.0
A(case("recurrence pairs inside the window", "ext_recurring", "True",
       {"ext_ts": EXT_T, "ext_window": 21600}, {NOW: repr(EXT_T + 3600)},
       finding="F11-4: a unit cycling hourly escalates on its second fire"))
A(case("unrelated changes on different days do not pair", "ext_recurring", "False",
       {"ext_ts": EXT_T, "ext_window": 21600}, {NOW: repr(EXT_T + 40000)},
       finding="F-4.1: two adjustments a day apart must not pair"))
A(case("a room never changed from outside is not recurring", "ext_recurring", "False",
       {"ext_ts": 946681200.0, "ext_window": 21600}, {NOW: repr(EXT_T)},
       finding="R10-6: the year-2000 sentinel means 'never', not 'long ago'"))

# ---------------------------------------------------------------- actuation interlocks
A(case("we never command while our own is in flight", "may_act", "False",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": False, "in_flight": True, "safety_throttled": False,
        "fail_count": 0, "breaker": 3, "is_safety": False, "throttle_ok": False},
       finding="R4-2"))
A(case("we do not fight an external change", "may_act", "False",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": True,
        "standdown": False, "in_flight": False, "safety_throttled": False,
        "fail_count": 0, "breaker": 3, "is_safety": False, "throttle_ok": False},
       finding="v3.2"))
A(case("safety bypasses the breaker", "may_act", "True",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": False, "in_flight": False, "safety_throttled": False,
        "fail_count": 99, "breaker": 3, "is_safety": True, "throttle_ok": False},
       finding="A5 / v3.1"))
A(case("a setpoint we are correcting is not a unit fault", "diverged", "False",
       {"active": True, "reachable": True, "converged": False, "in_flight": False,
        "may_act": False, "external_moved": False, "standdown": False,
        "will_set_temp": True},
       finding="R4-2 relocated into the setpoint path, seen live 2026-09-19"))
# ---------------------------------------------------------------- preset per mode
# 2026-09-23, operator: "make sure that the ac will start in quiet preset at night when
# heating, and windfree at any time when cooling."
#
# Cooling ALREADY asked for wind-free at every hour -- wind_free by day, wind_free_sleep at
# night -- so that half is a confirmation, not a change. The heating half is new.
#
# The decision MOVES INTO the room loop. It could not live where it was: the house-level
# block runs before `mode` and `now_preset` exist, and a preset that depends on the mode
# cannot be decided before the mode is.
#
# Where we have no opinion, `want_preset` returns `now_preset`. That is what makes silence
# free: will_set_preset compares the two, so "no opinion" and "already correct" are the same
# thing and neither issues a command.
A(case("cooling by day asks for wind-free", "want_preset", "wind_free",
       {"mode": "cool", "night": False, "now_preset": "none"},
       finding="2026-09-23 operator: wind-free at any time when cooling"))
A(case("cooling at night still asks for wind-free", "want_preset", "wind_free_sleep",
       {"mode": "cool", "night": True, "now_preset": "none"},
       finding="2026-09-23: 'at any time' includes the night"))
A(case("heating at night asks for quiet", "want_preset", "quiet",
       {"mode": "heat", "night": True, "now_preset": "none"},
       finding="2026-09-23 operator: quiet at night when heating"))
A(case("heating by day asserts nothing", "want_preset", "none",
       {"mode": "heat", "night": False, "now_preset": "none"},
       finding="2026-09-23: the request is night-only"))
A(case("heating by day leaves an existing preset alone", "want_preset", "quiet",
       {"mode": "heat", "night": False, "now_preset": "quiet"},
       finding="no opinion is 'whatever is already set', so it costs no command"))
A(case("a wind-free preset is never asked for outside cool", "want_preset", "quiet",
       {"mode": "heat", "night": True, "now_preset": "wind_free"},
       finding="set_preset_mode on an OFF unit turns it ON in COOL"))
A(case("dry asserts no preset", "want_preset", "none",
       {"mode": "dry", "night": True, "now_preset": "none"},
       finding="only heat and cool carry a preset opinion"))
A(case("a unit we are switching off is asked for no preset", "want_preset", "none",
       {"mode": "off", "night": True, "now_preset": "none"},
       finding="set_preset_mode on an OFF unit turns it ON in COOL"))

# 2026-09-23, MEASURED on the office unit with the operator watching it:
#   - set_preset_mode on a HEATING unit does NOT flip it to cool. The hazard is specific
#     to a unit that is OFF, so the generalised is_state(r.climate, mode) interlock holds.
#   - the preset does NOT survive a power cycle. Switching the unit off reverts preset to
#     'none' and fan to 'auto', so it must be re-applied on EVERY start.
#   - applied ~30 s after the mode, the unit ramps to full fan first and then quiets --
#     "this would have woken us up at night". Applied ~2 s after, it "started in silent
#     immediately".
# The old shape sent the preset on a LATER tick, which cannot happen sooner than one
# settle window (240 s) after the mode. That is minutes of full fan in a bedroom at night:
# the exact opposite of "start in quiet". The preset now rides along with the command that
# turns the unit on, and the standalone step below keeps the correction case.
A(case("turning a unit on carries its preset with it", "preset_with_start", "True",
       {"may_act": True, "mode": "heat", "night": True, "want_preset": "quiet",
        "now_preset": "none"},
       finding="2026-09-23 measured: a preset a tick later is minutes of full fan"))
A(case("cooling carries wind-free with the start too", "preset_with_start", "True",
       {"may_act": True, "mode": "cool", "night": False, "want_preset": "wind_free",
        "now_preset": "none"},
       finding="2026-09-23: the ride-along is not heating-only"))
A(case("no ride-along when we are not commanding the mode", "preset_with_start", "False",
       {"may_act": False, "mode": "heat", "night": True, "want_preset": "quiet",
        "now_preset": "none"},
       finding="the standalone step owns the already-converged case"))
A(case("no ride-along when the preset already matches", "preset_with_start", "False",
       {"may_act": True, "mode": "heat", "night": True, "want_preset": "quiet",
        "now_preset": "quiet"},
       finding="idempotence: a start must not re-send a preset already in place"))
A(case("no ride-along into a mode with no preset opinion", "preset_with_start", "False",
       {"may_act": True, "mode": "dry", "night": True, "want_preset": "none",
        "now_preset": "none"},
       finding="only heat and cool carry a preset opinion"))
A(case("a unit being switched off is never sent a preset", "preset_with_start", "False",
       {"may_act": True, "mode": "off", "night": True, "want_preset": "none",
        "now_preset": "quiet"},
       finding="set_preset_mode on an OFF unit turns it ON in COOL"))

A(case("night heat commands quiet", "will_set_preset", "True",
       {"active": True, "mode_ok": True, "mode": "heat", "night": True,
        "now_preset": "none", "want_preset": "quiet", "in_flight": False, "tripped": False},
       finding="2026-09-23 operator: quiet at night when heating"))
A(case("no command once the preset already matches", "will_set_preset", "False",
       {"active": True, "mode_ok": True, "mode": "heat", "night": True,
        "now_preset": "quiet", "want_preset": "quiet", "in_flight": False, "tripped": False},
       finding="idempotence: this must not re-command every ten minutes"))
A(case("day heat issues no preset command", "will_set_preset", "False",
       {"active": True, "mode_ok": True, "mode": "heat", "night": False,
        "now_preset": "none", "want_preset": "none", "in_flight": False, "tripped": False},
       finding="2026-09-23: night-only"))
A(case("no preset before the mode has converged", "will_set_preset", "False",
       {"active": True, "mode_ok": False, "mode": "cool", "night": False,
        "now_preset": "none", "want_preset": "wind_free", "in_flight": False, "tripped": False},
       finding="the setpoint and the preset both wait for the mode"))
A(case("no preset while our own command is in flight", "will_set_preset", "False",
       {"active": True, "mode_ok": True, "mode": "cool", "night": False,
        "now_preset": "none", "want_preset": "wind_free", "in_flight": True, "tripped": False},
       finding="the settle window applies to presets too"))
A(case("a tripped breaker blocks the preset as well", "will_set_preset", "False",
       {"active": True, "mode_ok": True, "mode": "cool", "night": False,
        "now_preset": "none", "want_preset": "wind_free", "in_flight": False, "tripped": True},
       finding="v4 breaker throttles comfort, presets included"))

# ---------------------------------------------------------------- AC power-saving stand-down
# 2026-09-21: the operator enabled the units' own presence-based power saving, so an AC
# now switches ITSELF off when a room has been empty a while. Nothing on the device says
# so -- no hvac_action, and the drlc_* attributes are utility demand-response, not this --
# and area presence is not trustworthy (magic_areas claims the bedroom has been empty 28 h).
#
# The one reliable discriminator is the SHAPE of the change. Power saving always ends at
# 'off'. It never switches the unit to another mode and never moves a setpoint. So:
#     -> off            = stand-down. Quiet. No accusation, no push, no breaker.
#     -> any other mode = somebody used a remote or the app. Hold and say so.
# A person who switches the unit off by hand also lands in the quiet path, and that is
# the better error: they just pressed off, they do not need telling why we stopped.
A(case("a unit switching ITSELF off is a stand-down, not an override", "standdown", "True",
       {"active": True, "reachable": True, "mode_ok": False, "in_flight": False,
        "unit_moved": True, "now_mode": "off"},
       finding="the operator's power-saving feature must not read as a wall override"))
A(case("a unit switching itself off is NOT an external override", "external_moved", "False",
       {"active": True, "reachable": True, "mode_ok": False, "in_flight": False,
        "unit_moved": True, "now_mode": "off"},
       finding="no 2 h hold and no push for a feature working as intended"))
A(case("a change to another mode IS an external override", "external_moved", "True",
       {"active": True, "reachable": True, "mode_ok": False, "in_flight": False,
        "unit_moved": True, "now_mode": "cool"},
       finding="power saving never selects a mode; a remote or the app did this"))
A(case("a change to another mode is not a stand-down", "standdown", "False",
       {"active": True, "reachable": True, "mode_ok": False, "in_flight": False,
        "unit_moved": True, "now_mode": "cool"}, finding="the two are mutually exclusive"))
A(case("our own in-flight command is neither", "standdown", "False",
       {"active": True, "reachable": True, "mode_ok": False, "in_flight": True,
        "unit_moved": True, "now_mode": "off"}, finding="M1/R4-2 still holds"))
A(case("a stood-down unit is not counted as a fault", "diverged", "False",
       {"active": True, "reachable": True, "converged": False, "in_flight": False,
        "may_act": False, "external_moved": False, "standdown": True,
        "will_set_temp": False},
       finding="the breaker must not isolate a unit that is doing what it was told to do"))
A(case("we do not fight a stood-down unit", "may_act", "False",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": True, "in_flight": False, "safety_throttled": False,
        "fail_count": 0, "breaker": 3, "is_safety": False, "throttle_ok": False},
       finding="re-commanding would loop against the unit's own timer"))
A(case("safety outranks the breaker", "may_act", "True",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": False, "in_flight": False, "safety_throttled": False,
        "fail_count": 99, "breaker": 3, "is_safety": True, "throttle_ok": False},
       finding="A5 / v3.1"))

# R14 F14-5. The mode law puts safety ABOVE manual, so a freezing stood-down room resolves
# to 'heat' rather than 'manual' -- but that only decides WHAT we want. Dispatch is may_act,
# and 'not standdown' / 'not external_moved' sat as TOP-LEVEL ands there while the is_safety
# bypass was buried inside the breaker clause. So the frost command was computed and never
# sent, for as long as unit_moved stayed true: up to human_window, ~20 minutes.
# I verified the PRECEDENCE and asserted the DISPATCH. These cases make it verify itself.
A(case("SAFETY DISPATCHES through a stand-down", "may_act", "True",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": True, "in_flight": False, "safety_throttled": False,
        "fail_count": 0, "breaker": 3, "is_safety": True, "throttle_ok": False},
       finding="F14-5: a freezing room must be heated even while the unit is stood down"))
A(case("SAFETY DISPATCHES through an external override", "may_act", "True",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": True,
        "standdown": False, "in_flight": False, "safety_throttled": False,
        "fail_count": 0, "breaker": 3, "is_safety": True, "throttle_ok": False},
       finding="F14-5: PRE-EXISTING - a wall override suppressed safety dispatch too"))
A(case("comfort still yields to a stand-down", "may_act", "False",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": True, "in_flight": False, "safety_throttled": False,
        "fail_count": 0, "breaker": 3, "is_safety": False, "throttle_ok": False},
       finding="the back-off must still hold for ordinary comfort"))
A(case("safety still respects the in-flight window", "may_act", "False",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": True, "in_flight": True, "safety_throttled": False,
        "fail_count": 0, "breaker": 3, "is_safety": True, "throttle_ok": False},
       finding="M1/R4-2: never double-command, not even for safety"))
A(case("safety still respects its own throttle", "may_act", "False",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": True, "in_flight": False, "safety_throttled": True,
        "fail_count": 0, "breaker": 3, "is_safety": True, "throttle_ok": False},
       finding="the safety retry throttle is a rate limit, not a suppression"))

# ---------------------------------------------------------------- resolved sensors
BED = "Climate temp bedroom"
PROBE = "states('sensor.bedroom_ac_temperature')"
TRV_OK = "is_state('binary_sensor.bedroom_trv_bedroom_trv_connectivity','on')"
TRV_HEAT = "states('sensor.bedroom_trv_bedroom_trv_heating')"
TRV_TEMP = "states('sensor.bedroom_trv_bedroom_trv_temperature')"
AC_OFF = "states('input_number.climate_ac_sensor_offset')"
TRV_OFF = "states('input_number.climate_trv_sensor_offset')"
# 2026-10-20: an IKEA VINDSTYRKA on the Zigbee mesh, in free air, away from both the AC
# discharge and the radiator. It is now the primary bedroom source; the TRV and the AC probe
# stay as fallbacks in their old order. The cases above set it dead so they still test those.
BED_VS = "states('sensor.bedroom_air_quality_sensor_temperature')"


def sensor_case(name, expect, subs, finding="", sensor=BED):
    return dict(name=name, sensor=sensor, expect=expect, given={}, subs=subs, finding=finding)


A(sensor_case(
    "a correct large AC offset is honoured, not overridden", "21.0",
    {AC_OFF: "'-4.0'", TRV_OK: "false", TRV_HEAT: "'0'", TRV_TEMP: "'0'",
     BED_VS: "'unavailable'", PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="F-1.1: v5.5 substituted -2 here and under-corrected by 2C, failing COLD"))
A(sensor_case(
    "an AC offset at the helper minimum is still honoured", "21.0",
    {AC_OFF: "'-4.0'", TRV_OK: "false", TRV_HEAT: "'0'", TRV_TEMP: "'0'",
     BED_VS: "'unavailable'", PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="F-1.1: honouring fails WARM, which is the safe direction"))
A(sensor_case(
    "an implausible TRV offset is ignored, not applied", "24.0",
    {AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'0'", TRV_TEMP: "'24.0'",
     BED_VS: "'unavailable'", PROBE: "'25.0'", TRV_OFF: "'-5.0'"},
    finding="R8-4: a new input_number comes up at its MINIMUM (-5), inside its own range"))
A(sensor_case(
    "the TRV is distrusted while the radiator is driving", "23.0",
    {AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'65'", TRV_TEMP: "'26.0'",
     BED_VS: "'unavailable'", PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="v5: a valve on a hot radiator reads high by an unmeasured amount"))
A(sensor_case(
    "an offline TRV falls back to the corrected probe", "23.0",
    {AC_OFF: "'-2.0'", TRV_OK: "false", TRV_HEAT: "'0'", TRV_TEMP: "'24.0'",
     BED_VS: "'unavailable'", PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="v5"))
A(sensor_case(
    "every source down yields nothing, never a fabricated number", "",
    {AC_OFF: "'-2.0'", TRV_OK: "false", TRV_HEAT: "'0'", TRV_TEMP: "'unavailable'",
     BED_VS: "'unavailable'", PROBE: "'unavailable'", TRV_OFF: "'0'"},
    finding="R7-9: resolves to the skip sentinel and the blackout alert speaks"))


# Every tier carries a DIFFERENT value and both offsets are non-zero, so the expected
# output names exactly one tier and shows whether an offset was (wrongly) applied.
A(sensor_case(
    "bedroom temperature prefers the air quality sensor, uncorrected", "20.0",
    {BED_VS: "'20'", AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'0'",
     TRV_TEMP: "'22.5'", PROBE: "'25.0'", TRV_OFF: "'1.0'"},
    finding="2026-10-20: the free-air sensor is primary; it needs neither offset"))
A(sensor_case(
    "a dead bedroom air quality sensor falls to the TRV, not the probe", "23.5",
    {BED_VS: "'unavailable'", AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'0'",
     TRV_TEMP: "'22.5'", PROBE: "'25.0'", TRV_OFF: "'1.0'"},
    finding="2026-10-20: the TRV keeps its place as the second tier"))
A(sensor_case(
    "a bedroom air quality sensor still booting is not a reading", "23.0",
    {BED_VS: "'unknown'", AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'65'",
     TRV_TEMP: "'26.0'", PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="z2m reports unknown right after a re-pair (seen 2026-10-20 14:05)"))

BED_H = "Climate humidity bedroom"
BED_H_VS = "states('sensor.bedroom_air_quality_sensor_humidity')"
BED_H_TRV = "states('sensor.bedroom_trv_bedroom_trv_humidity')"
BED_H_AC = "states('sensor.bedroom_ac_humidity')"

A(sensor_case(
    "bedroom humidity prefers the air quality sensor", "52.0",
    {BED_H_VS: "'52'", TRV_OK: "true", BED_H_TRV: "'49.5'", BED_H_AC: "'60'"},
    sensor=BED_H, finding="2026-10-20: the free-air sensor is primary"))
A(sensor_case(
    "a dead bedroom air quality sensor falls to the TRV humidity", "49.5",
    {BED_H_VS: "'unavailable'", TRV_OK: "true", BED_H_TRV: "'49.5'", BED_H_AC: "'60'"},
    sensor=BED_H, finding="2026-10-20: the TRV keeps its place as the second tier"))
A(sensor_case(
    "bedroom humidity with the sensor and TRV down falls to the AC", "60.0",
    {BED_H_VS: "'unavailable'", TRV_OK: "false", BED_H_TRV: "'49.5'", BED_H_AC: "'60'"},
    sensor=BED_H, finding="humidity carries no calibration offset"))
A(sensor_case(
    "every bedroom humidity source down yields nothing", "",
    {BED_H_VS: "'unavailable'", TRV_OK: "false", BED_H_TRV: "'unavailable'",
     BED_H_AC: "'unavailable'"},
    sensor=BED_H, finding="R7-9: the skip sentinel, never a fabricated number"))


# ---------------------------------------------------------------- the suite guarding itself
# Round 13 (3c): substitution is a source-to-source rewrite, so it can change an
# expression's MEANING rather than inject a value. This case only holds under a
# type-preserving rewrite: `states()` yields a STRING, and 'unavailable' must
# still travel the `| float(-999)` path to become the skip sentinel. Substituting
# a bare number here would silently stop testing that path.
A(sensor_case(
    "a source reporting 'unavailable' still reaches the skip sentinel", "",
    {AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'unavailable'",
     TRV_TEMP: "'unavailable'", BED_VS: "'unavailable'", PROBE: "'unavailable'", TRV_OFF: "'0'"},
    finding="R13 3c: only passes if states() is substituted as a STRING"))


# ---------------------------------------------------------------- corridor (air purifier)
# The corridor has ONE source and no fallback, so its resolved sensor is thinner
# than a room's -- but it must still exist, because the floor and household
# aggregates read RESOLVED sensors only, never raw device probes. Putting the
# purifier's own entity into a min_max alongside resolved ones would break that
# invariant and mean a future better corridor sensor has to be wired in twice.
COR = "Climate temp corridor"
COR_H = "Climate humidity corridor"
COR_T_SRC = "states('sensor.corridor_xiaomi_air_purifier_temperature')"
COR_H_SRC = "states('sensor.corridor_xiaomi_air_purifier_humidity')"

A(sensor_case("corridor temperature resolves from the purifier", "23.3",
              {COR_T_SRC: "'23.3'"}, sensor=COR,
              finding="aggregates read resolved sensors, never device probes"))
A(sensor_case("a dead corridor source yields nothing, not a fabricated number", "",
              {COR_T_SRC: "'unavailable'"}, sensor=COR,
              finding="min_max then drops the member instead of averaging a lie"))
A(sensor_case("corridor humidity resolves from the purifier", "55.0",
              {COR_H_SRC: "'55'"}, sensor=COR_H,
              finding="aggregates read resolved sensors, never device probes"))
A(sensor_case("a dead corridor humidity source yields nothing", "",
              {COR_H_SRC: "'unavailable'"}, sensor=COR_H,
              finding="same skip-sentinel discipline as the rooms"))



# ---------------------------------------------------------------- the living room and office meters
# The living room and the office each have a SwitchBot Meter Pro CO2, read over BLE through
# the Bluetooth proxies; it is also the source the CO2 sensors read.  When it is down the
# office falls to its AC probe, which needs the calibration offset and reports in whole
# degrees (the A11 problem).  The living room falls to its Tado wall thermostat first
# (2026-10-22, operator): wired, out of the AC's air and away from the radiator, so like the
# meter it takes NO offset.  Tier order is the whole point of these cases.
LR_T = "Climate temp living room"
LR_H = "Climate humidity living room"
OF_T = "Climate temp office"
OF_H = "Climate humidity office"

LR_T_BLE = "states('sensor.meter_pro_co2_b5be_temperature')"
LR_T_WALL = "states('sensor.livingroom_thermostat_livingroom_thermostat_temperature')"
LR_T_AC = "states('sensor.living_room_ac_temperature')"
LR_H_BLE = "states('sensor.meter_pro_co2_b5be_humidity')"
LR_H_WALL = "states('sensor.livingroom_thermostat_livingroom_thermostat_humidity')"
LR_H_AC = "states('sensor.living_room_ac_humidity')"

OF_T_BLE = "states('sensor.meter_pro_co2_5fe9_temperature')"
OF_T_AC = "states('sensor.office_ac_temperature')"
OF_H_BLE = "states('sensor.meter_pro_co2_5fe9_humidity')"
OF_H_AC = "states('sensor.office_ac_humidity')"

# Every tier carries a DIFFERENT value in these cases, so the expected output
# names exactly one tier.  Giving two tiers the same reading would let a wrong
# precedence pass.
A(sensor_case(
    "living room temperature reads its BLE meter", "23.4",
    {LR_T_BLE: "'23.4'", LR_T_WALL: "'22.6'", LR_T_AC: "'25.0'", AC_OFF: "'-2.0'"},
    sensor=LR_T, finding="the meter is the instrument in the room's air"))
A(sensor_case(
    "a dead living room meter falls to the wall thermostat, not the AC probe", "22.6",
    {LR_T_BLE: "'unavailable'", LR_T_WALL: "'22.6'", LR_T_AC: "'25.0'", AC_OFF: "'-2.0'"},
    sensor=LR_T, finding="2026-10-22: the wired thermostat is out of the AC's air and off the radiator"))
A(sensor_case(
    "the wall thermostat takes NO calibration offset", "22.6",
    {LR_T_BLE: "'unavailable'", LR_T_WALL: "'22.6'", LR_T_AC: "'25.0'", AC_OFF: "'-4.0'"},
    sensor=LR_T, finding="offsets correct instruments in the wrong air; this one is not"))
A(sensor_case(
    "meter and thermostat down fall to the corrected AC probe", "23.0",
    {LR_T_BLE: "'unavailable'", LR_T_WALL: "'unavailable'", LR_T_AC: "'25.0'",
     AC_OFF: "'-2.0'"},
    sensor=LR_T, finding="the probe still needs its offset applied"))
A(sensor_case(
    "every living room temperature source down yields nothing", "",
    {LR_T_BLE: "'unavailable'", LR_T_WALL: "'unavailable'", LR_T_AC: "'unavailable'",
     AC_OFF: "'-2.0'"},
    sensor=LR_T, finding="R7-9: the skip sentinel, never a fabricated number"))

A(sensor_case(
    "office temperature reads its BLE meter", "21.7",
    {OF_T_BLE: "'21.7'", OF_T_AC: "'25.0'", AC_OFF: "'-2.0'"},
    sensor=OF_T, finding="the meter is the instrument in the room's air"))
A(sensor_case(
    "a dead office meter falls to the corrected AC probe", "23.0",
    {OF_T_BLE: "'unavailable'", OF_T_AC: "'25.0'",
     AC_OFF: "'-2.0'"},
    sensor=OF_T, finding="the probe still needs its offset applied"))

A(sensor_case(
    "living room humidity reads its BLE meter", "47.0",
    {LR_H_BLE: "'47'", LR_H_WALL: "'52'", LR_H_AC: "'60'"},
    sensor=LR_H, finding="the meter is the instrument in the room's air"))
A(sensor_case(
    "a dead living room humidity meter falls to the wall thermostat", "52.0",
    {LR_H_BLE: "'unavailable'", LR_H_WALL: "'52'", LR_H_AC: "'60'"},
    sensor=LR_H, finding="2026-10-22: same instrument ranking as temperature"))
A(sensor_case(
    "meter and thermostat humidity down fall to the AC probe", "60.0",
    {LR_H_BLE: "'unavailable'", LR_H_WALL: "'unavailable'", LR_H_AC: "'60'"},
    sensor=LR_H, finding="humidity carries no calibration offset"))
A(sensor_case(
    "every living room humidity source down yields nothing", "",
    {LR_H_BLE: "'unavailable'", LR_H_WALL: "'unavailable'", LR_H_AC: "'unavailable'"},
    sensor=LR_H, finding="R7-9: the skip sentinel, never a fabricated number"))

A(sensor_case(
    "office humidity reads its BLE meter", "44.0",
    {OF_H_BLE: "'44'", OF_H_AC: "'60'"},
    sensor=OF_H, finding="the meter is the instrument in the room's air"))
A(sensor_case(
    "a dead office humidity meter falls to the AC probe", "60.0",
    {OF_H_BLE: "'unavailable'", OF_H_AC: "'60'"},
    sensor=OF_H, finding="humidity carries no calibration offset"))


# ---------------------------------------------------------------- a real meter in a kid's room
# 2026-09-21.  The operator moved a SwitchBot Meter Pro (Indoor/Outdoor) into Kids room 1,
# in the far corner, away from the AC's discharge.  This is the instrument that was promised
# when the 3 C swing was diagnosed: the AC is mounted directly above the radiator and the
# slatted ceiling blows its own output onto the TRV's thermometer, so the TRV has been
# reporting the unit's discharge air rather than the room.
#
# The room therefore gains a THREE-tier chain.  Tier order, worst-case first:
#   1. the meter over BLE          -- a real thermometer, correctly placed, no offset needed
#   2. the TRV, only when live AND the radiator is cold, plus the TRV offset
#   3. the AC internal probe, plus the global AC offset
#
# The meter takes NO calibration offset.  That is the single most important thing these
# cases pin: the offsets exist to correct instruments that sit in the wrong air, and
# applying one to a correctly-placed thermometer would inject exactly the error it removes.
#
# Rooms are named by ALIAS.  The live names are the operator's children's, this repo is
# public, and `rooms.local.json` (gitignored) is the only place the real ids appear.
K1 = harness.load_rooms()["kid1"]
K1_T = "Climate temp " + K1["title"]
K1_H = "Climate humidity " + K1["title"]

K1_B_T = "states('%s')" % K1["meter_temp"]
K1_V_T = "states('%s')" % K1["trv_temp"]
K1_A_T = "states('%s')" % K1["ac_temp"]
K1_CONN = "is_state('%s','on')" % K1["trv_conn"]
K1_HEAT = "states('%s')" % K1["trv_heat"]

K1_B_H = "states('%s')" % K1["meter_hum"]
K1_V_H = "states('%s')" % K1["trv_hum"]
K1_A_H = "states('%s')" % K1["ac_hum"]
# 2026-10-07: a Zigbee air-quality sensor joined the room (see the block after these cases).
# Every case pins it, so none of them silently reads the live sensor.
K1_Q_T = "states('%s')" % K1["aq_temp"]
K1_Q_H = "states('%s')" % K1["aq_hum"]

# Every tier carries a DIFFERENT value, so the expected output names exactly one of them.
# The AC offset is -2 and the TRV offset +1 throughout, so a tier that wrongly picks up a
# correction is visible in the result rather than hidden behind a matching number.
A(sensor_case(
    "the room meter outranks the TRV that the AC blows on", "23.4",
    {K1_Q_T: "'unavailable'", K1_B_T: "'23.4'", K1_V_T: "'22.0'", K1_A_T: "'25.0'",
     K1_CONN: "true", K1_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="R8-2/A11: the TRV reads the unit's discharge, not the room"))
A(sensor_case(
    "a correctly placed meter takes NO calibration offset", "23.4",
    {K1_Q_T: "'unavailable'", K1_B_T: "'23.4'", K1_V_T: "'unavailable'", K1_A_T: "'25.0'",
     K1_CONN: "false", K1_HEAT: "'0'", AC_OFF: "'-4.0'", TRV_OFF: "'-5.0'"},
    sensor=K1_T, finding="offsets correct instruments in the wrong air; this one is not"))
A(sensor_case(
    "a dead meter falls to the TRV, offset and all", "23.0",
    {K1_Q_T: "'unavailable'", K1_B_T: "'unavailable'", K1_V_T: "'22.0'", K1_A_T: "'25.0'",
     K1_CONN: "true", K1_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="the TRV keeps its place as the only INDEPENDENT fallback"))
# The probe reads 24.0 here, NOT 25.0: with the AC offset at -2 a 25.0 probe resolves to
# 23.0, which is exactly what the TRV tier above would have produced (22.0 + 1.0).  The two
# paths would have been indistinguishable and the case would have passed either way.
A(sensor_case(
    "a hot radiator still disqualifies the TRV, even as third tier", "22.0",
    {K1_Q_T: "'unavailable'", K1_B_T: "'unavailable'", K1_V_T: "'26.0'", K1_A_T: "'24.0'",
     K1_CONN: "true", K1_HEAT: "'65'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="v5: a valve on a hot radiator reads high by an unmeasured amount"))
A(sensor_case(
    "every source down yields nothing, never a fabricated number", "",
    {K1_Q_T: "'unavailable'", K1_B_T: "'unavailable'", K1_V_T: "'unavailable'",
     K1_A_T: "'unavailable'", K1_CONN: "false", K1_HEAT: "'0'",
     AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="R7-9: the skip sentinel, never a fabricated number"))

A(sensor_case(
    "room humidity prefers the meter over the TRV", "39.0",
    {K1_Q_H: "'unavailable'", K1_B_H: "'39'", K1_V_H: "'46'", K1_A_H: "'31'", K1_CONN: "true"},
    sensor=K1_H, finding="same instrument ranking as temperature"))
A(sensor_case(
    "a dead meter falls to the TRV humidity", "46.0",
    {K1_Q_H: "'unavailable'", K1_B_H: "'unavailable'", K1_V_H: "'46'", K1_A_H: "'31'",
     K1_CONN: "true"},
    sensor=K1_H, finding="the TRV humidity has no radiator gate -- only a liveness one"))
A(sensor_case(
    "an offline TRV drops humidity to the AC probe", "31.0",
    {K1_Q_H: "'unavailable'", K1_B_H: "'unavailable'", K1_V_H: "'46'", K1_A_H: "'31'",
     K1_CONN: "false"},
    sensor=K1_H, finding="liveness gates the TRV in both resolved sensors"))


# ---------------------------------------------------------------- a third instrument in kid 1's room
# 2026-10-07.  A Zigbee air-quality sensor (temperature, humidity, PM2.5, VOC) went into Kids
# room 1.  It is a second, INDEPENDENT thermometer in the room's air, so it ranks below the meter
# (the better-characterised instrument) and above the TRV and the AC probe, which sit
# in the wrong air and need offsets.  Like the meter it takes NO offset.
A(sensor_case(
    "kid 1: a dead meter falls to the air-quality sensor, not the TRV", "22.6",
    {K1_Q_T: "'22.6'", K1_B_T: "'unavailable'", K1_V_T: "'22.0'",
     K1_A_T: "'25.0'", K1_CONN: "true", K1_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="2026-10-07: an independent thermometer in the room's air outranks the TRV"))
A(sensor_case(
    "kid 1: the air-quality sensor takes NO calibration offset", "22.6",
    {K1_Q_T: "'22.6'", K1_B_T: "'unavailable'", K1_V_T: "'unavailable'",
     K1_A_T: "'25.0'", K1_CONN: "false", K1_HEAT: "'0'", AC_OFF: "'-4.0'", TRV_OFF: "'-5.0'"},
    sensor=K1_T, finding="offsets correct instruments in the wrong air; this one is not"))
A(sensor_case(
    "kid 1: the meter still outranks the air-quality sensor", "23.4",
    {K1_Q_T: "'22.6'", K1_B_T: "'23.4'", K1_V_T: "'22.0'",
     K1_A_T: "'25.0'", K1_CONN: "true", K1_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="the meter is the better-characterised instrument"))
A(sensor_case(
    "kid 1: humidity falls to the air-quality sensor before the TRV", "41.0",
    {K1_Q_H: "'41'", K1_B_H: "'unavailable'", K1_V_H: "'46'",
     K1_A_H: "'31'", K1_CONN: "true"},
    sensor=K1_H, finding="same instrument ranking as temperature"))
A(sensor_case(
    "kid 1: humidity still prefers the meter over the air-quality sensor", "39.0",
    {K1_Q_H: "'41'", K1_B_H: "'39'", K1_V_H: "'46'", K1_A_H: "'31'",
     K1_CONN: "true"},
    sensor=K1_H, finding="same instrument ranking as temperature"))


# ---------------------------------------------------------------- a real meter in the second kid's room
# 2026-09-25.  The operator moved the second SwitchBot Meter Pro (the one that sat unplaced on the
# admin page) into Kids room 2, which gains the same chain as Kids room 1 above: the meter
# over BLE, the TRV (live AND cold, plus its offset), the AC probe (plus the AC offset). Same rules, so the same cases - a room whose chain quietly differs from its twin's
# is how one of them ends up reading the radiator.
K2 = harness.load_rooms()["kid2"]
K2_T = "Climate temp " + K2["title"]
K2_H = "Climate humidity " + K2["title"]
K2_B_T = "states('%s')" % K2["meter_temp"]
K2_V_T = "states('%s')" % K2["trv_temp"]
K2_A_T = "states('%s')" % K2["ac_temp"]
K2_CONN = "is_state('%s','on')" % K2["trv_conn"]
K2_HEAT = "states('%s')" % K2["trv_heat"]
K2_B_H = "states('%s')" % K2["meter_hum"]
K2_V_H = "states('%s')" % K2["trv_hum"]
K2_A_H = "states('%s')" % K2["ac_hum"]

A(sensor_case(
    "kid 2: the room meter outranks the TRV", "23.4",
    {K2_B_T: "'23.4'", K2_V_T: "'22.0'", K2_A_T: "'25.0'",
     K2_CONN: "true", K2_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K2_T, finding="2026-09-25: the meter moved in; it is the instrument in the room's air"))
A(sensor_case(
    "kid 2: a correctly placed meter takes NO calibration offset", "23.4",
    {K2_B_T: "'23.4'", K2_V_T: "'unavailable'", K2_A_T: "'25.0'",
     K2_CONN: "false", K2_HEAT: "'0'", AC_OFF: "'-4.0'", TRV_OFF: "'-5.0'"},
    sensor=K2_T, finding="offsets correct instruments in the wrong air; this one is not"))
A(sensor_case(
    "kid 2: a dead meter falls to the TRV, offset and all", "23.0",
    {K2_B_T: "'unavailable'", K2_V_T: "'22.0'", K2_A_T: "'25.0'",
     K2_CONN: "true", K2_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K2_T, finding="the TRV keeps its place as the only INDEPENDENT fallback"))
A(sensor_case(
    "kid 2: a hot radiator still disqualifies the TRV", "22.0",
    {K2_B_T: "'unavailable'", K2_V_T: "'26.0'", K2_A_T: "'24.0'",
     K2_CONN: "true", K2_HEAT: "'65'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K2_T, finding="v5: a valve on a hot radiator reads high by an unmeasured amount"))
A(sensor_case(
    "kid 2: every source down yields nothing", "",
    {K2_B_T: "'unavailable'", K2_V_T: "'unavailable'",
     K2_A_T: "'unavailable'", K2_CONN: "false", K2_HEAT: "'0'",
     AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K2_T, finding="R7-9: the skip sentinel, never a fabricated number"))
A(sensor_case(
    "kid 2: room humidity prefers the meter over the TRV", "39.0",
    {K2_B_H: "'39'", K2_V_H: "'46'", K2_A_H: "'31'", K2_CONN: "true"},
    sensor=K2_H, finding="same instrument ranking as temperature"))
A(sensor_case(
    "kid 2: a dead meter falls to the TRV humidity", "46.0",
    {K2_B_H: "'unavailable'", K2_V_H: "'46'", K2_A_H: "'31'",
     K2_CONN: "true"},
    sensor=K2_H, finding="the TRV humidity has no radiator gate -- only a liveness one"))


# ---------------------------------------------------------------- background radiation
# 2026-09-21. A Geiger-Muller tube on the ESPHome bluetooth proxy (GPIO13) publishes
# COUNTS PER MINUTE, which is the tube-independent measurement. Turning counts into a
# dose rate needs a per-tube sensitivity, and the tube's marking is still unconfirmed.
#
# The factor is a HELPER, not a constant, and the first day already justified that:
# the constant seeded from memory (0.00812) turned out to be derived from an OBSOLETE
# J305 datasheet declaring 18 CPS/mR/h. Tubes sold now declare 44, so
#     1 / (44 x 60 / 8.77) = 0.00332 uSv/h per CPM
# against the old
#     1 / (18 x 60 / 8.77) = 0.00812
# -- the same arithmetic, a 2.45x different answer. Getting that wrong overstates
# background by a factor of two and a half. See docs/radiation-monitoring-design.md.
RAD = "Radiation dose rate"
RAD_CPM = "states('sensor.background_radiation_cpm')"
RAD_FACTOR = "states('input_number.radiation_usv_per_cpm')"

A(sensor_case(
    "counts convert at the configured factor", "0.332",
    {RAD_CPM: "'100'", RAD_FACTOR: "'0.00332'"},
    sensor=RAD, finding="J305 at the current datasheet: 44 CPS/mR/h"))
# The factor must actually reach the arithmetic. With one factor only, a template that
# ignored the helper and inlined a constant would pass the case above, and nothing would
# notice until the tube turned out to be something else.
A(sensor_case(
    "a different tube gives a different dose for the same counts", "0.57",
    {RAD_CPM: "'100'", RAD_FACTOR: "'0.0057'"},
    sensor=RAD, finding="SBM-20 is 0.0057; the helper must reach the arithmetic"))
# The helper can be missing or unavailable -- during a restart, or if it is ever
# deleted. The fallback must be the CURRENT datasheet value, not the obsolete one,
# because a fallback nobody notices is exactly where a stale constant survives.
A(sensor_case(
    "a missing factor helper falls back to the current datasheet value", "0.332",
    {RAD_CPM: "'100'", RAD_FACTOR: "'unavailable'"},
    sensor=RAD, finding="the 2026-09-21 correction: 0.00332, not the obsolete 0.00812"))
# REVERSED 2026-09-22. This case previously asserted that 0 CPM is a real reading of
# zero dose, on the principle that a tube reporting no events differs from a tube
# reporting nothing. The physics says otherwise: counts from a GM tube are Poisson,
# and a J305 sitting in ~20 CPM background has a probability of e^-20, about 2 in a
# BILLION, of recording exactly zero across a 60-second window. Sustained 0 CPM is
# not a measurement of no radiation -- there is no such thing at ground level -- it
# means the counter is not receiving pulses.
#
# Reporting 0.0 uSv/h for it was the worse error: it writes a confident, false zero
# into the statistics and shows a reassuring number on the dashboard while the
# instrument is disconnected. Which is exactly what it did from 2026-09-21 to
# 2026-09-22, with the signal wire on the wrong header pin the whole time.
# The gate lives in the sensor's AVAILABILITY template, not in its state. Rendering an
# empty state was tried first and does not work: HA kept the previous numeric value,
# so the dashboard went on showing 0.0 uSv/h from an instrument that was disconnected.
A(sensor_case(
    "a counter recording no events at all is not measuring", "False",
    {RAD_CPM: "'0'"},
    sensor=RAD + "::availability",
    finding="P(0 counts in 60s at background) = e^-20; 0 means disconnected"))
A(sensor_case(
    "one count is enough to be measuring", "True",
    {RAD_CPM: "'1'"},
    sensor=RAD + "::availability",
    finding="the cutoff is at 1, not at some plausibility floor"))
A(sensor_case(
    "an offline counter is not measuring either", "False",
    {RAD_CPM: "'unavailable'"},
    sensor=RAD + "::availability", finding="the -1 sentinel is below the cutoff too"))
A(sensor_case(
    "one count still converts correctly", "0.003",
    {RAD_CPM: "'1'", RAD_FACTOR: "'0.00332'"},
    sensor=RAD, finding="state stays pure arithmetic; availability does the gating"))
A(sensor_case(
    "a counter that has not reported yet is not measuring", "False",
    {RAD_CPM: "'unknown'"},
    sensor=RAD + "::availability", finding="the first 60s window reports nothing at all"))


# ---------------------------------------------------------------- purifier after the cat toilet
# A second automation. Its logic is mostly SEQUENCING (turn on, settle, wait,
# turn off), which is precisely the class tests/climate cannot reach -- see the
# README. What IS testable is its guards, so those are what live here.
PURIFIER = "1789947000001"


def guard(name, expr, expect, subs=None, finding=""):
    return dict(name=name, automation=PURIFIER, expr=expr, expect=expect,
                given={}, subs=subs or {}, finding=finding)


CNT = "states('sensor.cat_toilet_excretion_times_day')"
WAS = "trigger.from_state.state"
IS_VISIT = "trigger.id == 'visit'"
FAN_ON = "is_state('fan.corridor_xiaomi_air_purifier','on')"
OWNED = "is_state('input_boolean.purifier_auto_run','on')"


def visit(name, expect, was, now_, finding=""):
    return guard(name, "visit_happened", expect,
                 {IS_VISIT: "true", CNT: "'" + now_ + "'", WAS: "'" + was + "'"}, finding)


A(visit("a real visit increments the counter", "True", "7", "8",
        "the counter is the only unambiguous 'a cat just used it' event"))
A(visit("the midnight reset is NOT a visit", "False", "7", "0",
        "excretion_times_DAY resets to 0 at midnight; a bare state trigger fires on it"))
A(visit("a restart restore is NOT a visit", "False", "unknown", "7",
        "P1 class: entities come back at restart and look like fresh events"))
A(visit("an unchanged repeat report is NOT a visit", "False", "7", "7",
        "cloud integrations re-report the same value"))
A(guard("the boot trigger is never a visit", "visit_happened", "False",
        {IS_VISIT: "false", CNT: "'8'", WAS: "'7'"},
        finding="the same automation handles restart recovery; it must not start a run"))
# we_may_stop is deliberately NOT gated on the persistent ownership flag. Round 1
# finding F2: the flag is a second source of truth about a physical device, and in
# the direction "flag off while fan on" the timeout's shutdown was skipped, the boot
# recovery did not fire (it only acts when the flag IS set) and every later visit
# refused to touch the fan -- stranded on for ever. Shutdown turns on run-local facts;
# the flag is for cross-restart bookkeeping only.
#
# 2026-10-02 (v6): the fan drops to `unavailable` for 20-60 s every few minutes. Every
# guard below used to read is_state(..., 'on'), which treats "unreachable" as "off".
# At the end of a run that meant no off command at all (09-28 21:02, ran on to 21:56);
# at the start-confirm it meant FAILED TO START and an off command into a device that
# could not hear it (10-01 13:46, came back on, ran for hours). The question both
# guards actually ask is "is it known to be OFF?" -- so unreachable is not off.
FAN = "states('fan.corridor_xiaomi_air_purifier')"

A(guard("we stop a fan that is running at the end", "we_may_stop", "True",
        {FAN: "'on'", "stopped_by_human": "false"},
        finding="F2: shutdown must not depend on the persistent flag"))
A(guard("a fan unreachable at the end is still stopped", "we_may_stop", "True",
        {FAN: "'unavailable'", "stopped_by_human": "false"},
        finding="2026-09-28 21:02: is_state(on) read a dropout as off, so no off was sent"))
A(guard("nothing to stop if the fan is already off", "we_may_stop", "False",
        {FAN: "'off'", "stopped_by_human": "false"},
        finding="a person switched it off mid-run; abandon rather than re-command"))
A(guard("a person taking over ends our claim", "we_may_stop", "False",
        {FAN: "'on'", "stopped_by_human": "true"},
        finding="F2: off-then-on by hand during the wait must not be re-stopped by us"))

# we_started decides between "run the window" and "give up and command it off". It
# needs its own cases -- binding it as an input to another guard does NOT test it.
A(guard("a fan confirmed running counts as started by us", "we_started", "True",
        {FAN: "'on'"}, finding="F2: re-read after commanding, never assume it worked"))
A(guard("a fan that stayed off did not start", "we_started", "False",
        {FAN: "'off'"},
        finding="F2: fan.turn_on can fail; the run must not pretend otherwise"))
A(guard("a fan unreachable at the confirm is not written off", "we_started", "True",
        {FAN: "'unavailable'"},
        finding="2026-10-01 13:46: a dropout at the read became FAILED TO START, and the "
                "fan came back on 50 s later with nobody owning it"))

# Round 1 F3/F1: the early stop may only be armed once the sensor has PROVED it is
# responsive. A sensor pinned at its floor tells us nothing, so there is nothing to
# wait for -- run the full window instead of ending early on a reading we distrust.
# 2026-09-20: the sensor did not move across 46 min of full airflow right after a
# visit, so the operator declared it broken for now. That assumption is an explicit,
# reversible TOGGLE rather than something baked into the logic -- cleaning the laser
# intake later is one switch, not a code change. pm_usable is the whole gate.
TRUSTED = "is_state('input_boolean.purifier_pm25_trusted','on')"

A(guard("an untrusted sensor never arms the early stop", "pm_usable", "False",
        {TRUSTED: "false", "pm_after_settle": "12.0"},
        finding="operator declared it broken; even a plausible reading gets no vote"))
A(guard("a trusted responsive sensor arms the early stop", "pm_usable", "True",
        {TRUSTED: "true", "pm_after_settle": "12.0"},
        finding="F3: PM rose after the visit, so 'back down' is meaningful"))
A(guard("a trusted sensor pinned at the floor does not arm it", "pm_usable", "False",
        {TRUSTED: "true", "pm_after_settle": "1.0"},
        finding="F1/F3: never leaves 1, so we learn nothing even when trusted"))
A(guard("a trusted zero reading does not arm it either", "pm_usable", "False",
        {TRUSTED: "true", "pm_after_settle": "0.0"}, finding="F3: 0 is still the floor"))

# Round 1 F4: a person who switches the fan off BETWEEN visits had it re-ignited by
# the next cat, with no signal. A manual stop now suppresses re-starts for a while.
# SECOND time this exact mistake was caught by the suite: a toy timestamp where the
# expression tests against the year-2000 sentinel (> 1e9) can never be "recent", and
# the negative sibling then passes for the WRONG REASON. Use real epochs.
STOP_T = 1789947000.0
A(guard("a recent manual stop blocks a re-start", "manual_cooldown", "True",
        {"stop_ts": repr(STOP_T), "now().timestamp()": repr(STOP_T + 600),
         "cooldown": "1800"},
        finding="F4: the operator wanted quiet; the litter box must not overrule them"))
A(guard("an old manual stop does not block", "manual_cooldown", "False",
        {"stop_ts": repr(STOP_T), "now().timestamp()": repr(STOP_T + 5000),
         "cooldown": "1800"},
        finding="F4: the cooldown expires"))
A(guard("never manually stopped means no cooldown", "manual_cooldown", "False",
        {"stop_ts": "946681200.0", "now().timestamp()": "1789947000.0", "cooldown": "1800"},
        finding="the year-2000 sentinel means never, not long ago"))
A(guard("a purifier already running is not ours to take", "already_running", "True",
        {FAN_ON: "true", OWNED: "false"},
        finding="if it was on before the visit, a person started it"))
A(guard("an idle purifier is ours to start", "already_running", "False",
        {FAN_ON: "false", OWNED: "false"}, finding="the normal path"))


# ---------------------------------------------------------------- bedroom purifier (air quality)
# 2026-10-31, operator: "start automatically during the day when either pm2.5 or the allergen
# index is above 2.5 ... turn it off when pm drops to or below two or allergen to one (make sure
# you cover the cases when allergen is one while pm2 is high)". Read as hysteresis: EITHER reading
# high starts it, BOTH readings low stop it - one clean reading must never end a run the other
# still needs. Night is the house's night (the alarm), shared with every other consumer below.
BED_PURIFIER = "1792300000001"


def bp(name, expr, expect, given=None, subs=None, finding=""):
    return dict(name="bedroom purifier: " + name, automation=BED_PURIFIER, expr=expr,
                expect=expect, given=given or {}, subs=subs or {}, finding=finding)


def bp_air(name, expr, expect, pm, allergen, finding):
    return bp(name, expr, expect, {"pm": pm, "allergen": allergen}, finding=finding)


A(bp_air("PM2.5 above 2.5 is dirty", "dirty", "True", 3.0, 1.0,
         "operator 2026-10-31: either reading above 2.5 starts it - allergen 1 must not veto"))
A(bp_air("allergen above 2.5 is dirty", "dirty", "True", 1.0, 3.0,
         "operator 2026-10-31: either reading starts it"))
A(bp_air("2.5 itself is not dirty", "dirty", "False", 2.5, 2.5,
         "'above 2.5' - the threshold is exclusive"))
A(bp_air("an unknown reading never starts it", "dirty", "False", -1.0, -1.0,
         "unavailable maps to -1; no reading is no evidence of dirty air"))
A(bp_air("both low is clear", "clear", "True", 2.0, 1.0,
         "operator 2026-10-31: 'to or below two' / 'to one' - inclusive"))
A(bp_air("allergen 1 while PM2.5 is high is NOT clear", "clear", "False", 5.0, 1.0,
         "operator 2026-10-31: the named case - allergen at 1 must not stop a PM run"))
A(bp_air("PM2.5 low while allergen is high is NOT clear", "clear", "False", 1.0, 3.0,
         "the mirror of the named case (guard both directions)"))
A(bp_air("between the thresholds is neither", "clear", "False", 2.5, 1.0,
         "hysteresis: PM 2.5 neither starts nor stops it"))
A(bp_air("allergen 2 holds a run with clean PM", "clear", "False", 1.0, 2.0,
         "hysteresis band on the allergen side: above 1 keeps it running"))
A(bp_air("an unknown reading never stops it", "clear", "False", -1.0, 1.0,
         "a sensor that dropped out is not evidence of clean air"))


def bp_act(name, expect, finding, **kw):
    g = dict(owned=False, fan="off", night=False, dirty=False, clear=False,
             manual_cooldown=False)
    g.update(kw)
    return bp(name, "act", expect, g, finding=finding)


A(bp_act("dirty air by day starts it", "start", "operator 2026-10-31", dirty=True))
A(bp_act("dirty air at night does not start it", "none",
         "operator 2026-10-31: during the day only", dirty=True, night=True))
A(bp_act("a person's own run is never stopped", "none",
         "never turn off what we did not turn on (purifier design 3.3)",
         fan="on", clear=True))
# 2026-11-07 (operator): at night the purifier is OFF, whoever started it. This replaces the
# earlier rule that left a person's run alone at night (purifier design 3.3 covers day only now).
A(bp_act("a person's run is stopped at night too", "stop",
         "operator 2026-11-07: the bedroom purifier is off in night mode, whoever started it",
         fan="on", night=True))
A(bp_act("our run stops when the air is clear", "stop", "operator 2026-10-31",
         owned=True, fan="on", clear=True))
A(bp_act("our run keeps going while one reading is still high", "none",
         "operator 2026-10-31: allergen 1 with PM high", owned=True, fan="on",
         dirty=True))
A(bp_act("our run stops at night", "stop",
         "auto-runs are a daytime thing; the bedroom is slept in", owned=True, fan="on",
         dirty=True, night=True))
A(bp_act("an unreachable fan of ours is still stopped", "stop",
         "corridor v6 lesson: unreachable is not off", owned=True, fan="unavailable",
         clear=True))
A(bp_act("our fan found off means a person stopped it", "released",
         "release, and hold off a while, rather than fight them", owned=True, fan="off",
         dirty=True))
A(bp_act("a recent manual stop blocks a re-start", "none",
         "the person wanted it off; dirty air must not overrule them at once",
         dirty=True, manual_cooldown=True))
A(bp_act("an unreachable idle fan is not started", "none",
         "only start what is known to be off", fan="unavailable", dirty=True))
A(bp_act("a running fan is not 'started' again", "none",
         "fan on and not ours: a person's run", fan="on", dirty=True))

# Cooldown: real epochs (see the corridor F4 note about toy timestamps and the 2000 sentinel).
BP_STOP = 1792300000.0
A(bp("a manual stop 10 min ago is cooling down", "manual_cooldown", "True",
     {"stop_ts": BP_STOP}, {"now().timestamp()": repr(BP_STOP + 600)},
     finding="hold off after a person switches it off"))
A(bp("a manual stop 2 h ago is not", "manual_cooldown", "False",
     {"stop_ts": BP_STOP}, {"now().timestamp()": repr(BP_STOP + 7200)},
     finding="the cooldown expires"))
A(bp("never stopped means no cooldown", "manual_cooldown", "False",
     {"stop_ts": 946681200.0}, {"now().timestamp()": repr(BP_STOP)},
     finding="the year-2000 sentinel means never"))


# ---------------------------------------------------------------- CO2 (SwitchBot BLE)
# The two Meter Pro CO2 devices report carbon dioxide over BLE. Room mapping was PROVEN by
# cross-checking readings, not by the entity-id suffix: living room = b5be, office = 5fe9.
CO2_LR = "Climate co2 living room"
CO2_OF = "Climate co2 office"
CO2_LR_SRC = "states('sensor.meter_pro_co2_b5be_carbon_dioxide')"
CO2_OF_SRC = "states('sensor.meter_pro_co2_5fe9_carbon_dioxide')"

A(sensor_case("living room CO2 resolves from its BLE meter", "463",
              {CO2_LR_SRC: "'463'"}, sensor=CO2_LR,
              finding="aggregates and checks read resolved sensors, never device probes"))
A(sensor_case("a dead CO2 source yields nothing, not a fabricated number", "",
              {CO2_LR_SRC: "'unavailable'"}, sensor=CO2_LR,
              finding="same skip-sentinel discipline as temperature"))
A(sensor_case("office CO2 resolves from its BLE meter", "1031",
              {CO2_OF_SRC: "'1031'"}, sensor=CO2_OF,
              finding="proven mapping: 5fe9 is the office"))

# The health-risk sensor gains CO2. It iterates five rooms but only two have a meter,
# so a missing reading must never fire it -- the same shape as the existing temp/humidity
# guard. Substituting the whole states(...) call sets every room at once, which is what
# these cases want.
HR = "Climate health risk"
HR_T = "states('sensor.climate_temp_' ~ r)"
HR_H = "states('sensor.climate_humidity_' ~ r)"
HR_C = "states('sensor.climate_co2_' ~ r)"
HR_AQI = "states('sensor.outside_openweathermap_air_quality_index')"


def hr(name, expect, t, h, c, aqi="1", finding=""):
    return dict(name=name, sensor=HR, expect=expect, given={},
                subs={HR_T: "'" + t + "'", HR_H: "'" + h + "'",
                      HR_C: "'" + c + "'", HR_AQI: "'" + aqi + "'"},
                finding=finding)


A(hr("comfortable rooms with fresh air are no risk", "False", "22", "45", "500",
     finding="baseline: nothing fires"))
A(hr("CO2 above the impairment line is a risk", "True", "22", "45", "1500",
     finding="documented cognitive effects; the office already sits near 1000"))
A(hr("CO2 just below the line is not", "False", "22", "45", "1399",
     finding="boundary - the threshold must be an inequality, not a vibe"))
A(hr("a missing CO2 reading never fires it", "False", "22", "45", "unavailable",
     finding="only 2 of the 5 rooms have a meter; absence must not read as danger"))
A(hr("CO2 does not mask a humidity risk", "True", "22", "70", "500",
     finding="the existing mould check must survive the addition"))
A(hr("CO2 does not mask a cold-room risk", "True", "14", "45", "500",
     finding="the existing cold check must survive the addition"))


# ================================================================ Change A (round-15 approved)
# the decide/act split record (retired; see docs/climate-control-design.md §12). Written FIRST per the repo's TDD rule; reviewed BEFORE
# deployment (review-20260921-a472), which approved A and STOPPED B.
#
# Change B's cases are deliberately NOT here. The review found four unlisted hazards in it
# (decision no longer atomic with dispatch, an unanswered trigger question, partial attribute
# availability, recorder amplification) and a contradiction in my own proposal: I listed
# "presence gets easier" as a benefit while leaning toward doing B *after* presence, which
# would mean that benefit is never realised. B is folded into the presence design instead.
# Its cases arrive with that proposal. A permanently-red suite teaches people to ignore red.

# ---------------------------------------------------------------- Change A: why a hold exists
# external_moved and standdown stamp the SAME hold helper with the same value, so after the
# fact nothing distinguishes "somebody used the remote" from "the unit power-saved an empty
# room". v5.7 removed the phone push for stand-downs, which had been the only differentiator.
# The expressions address the helper through the room dict (r.reason), not by a literal
# entity id -- caught by the substitution guard, which refused to run rather than pass.
REASON = "states(r.reason)"
HOLD_TS = "state_attr(r.manual,'timestamp') | float(0)"

A(case("a hold with no reason recorded reads as none", "hold_reason", "none",
       {}, {REASON: "'none'"},
       finding="F14-2: 'none' is FIRST so a created-or-reset select is inert"))
A(case("an external override records itself as external", "hold_reason", "external",
       {}, {REASON: "'external'"}, finding="F14-2: the remote/app case, worth knowing about"))
A(case("a stand-down records itself as standdown", "hold_reason", "standdown",
       {}, {REASON: "'standdown'"}, finding="F14-2: routine power saving, not a person"))

# R15 A3. The review caught that NOT clearing the label leaves a confident-looking reason
# behind an expired hold, gated only by every consumer remembering to check hold_active --
# which is the same "asserts more than it can know" defect A exists to close, re-entered
# through a missed gate. So the label is cleared when the hold is no longer live. The check
# RE-READS the stamp rather than using manual_active, which was sampled before this tick's
# hold was written and would otherwise clear the label we just set.
A(case("a stale label behind an expired hold is cleared", "reason_stale", "True",
       {}, {HOLD_TS: "1000.0", "now().timestamp()": "2000.0", REASON: "'external'"},
       finding="R15 A3: no consumer should have to remember a gate"))
A(case("a live hold keeps its label", "reason_stale", "False",
       {}, {HOLD_TS: "9000.0", "now().timestamp()": "2000.0", REASON: "'external'"},
       finding="R15 A3: only clear once the hold is genuinely over"))
A(case("an already-clear label is not rewritten", "reason_stale", "False",
       {}, {HOLD_TS: "1000.0", "now().timestamp()": "2000.0", REASON: "'none'"},
       finding="idempotent: no write every tick for five rooms"))


# ---------------------------------------------------------------- outdoor temperature
# 2026-09-25.  A Hue outdoor motion sensor went up on the terrace, and the house season
# decision (heat / shoulder / cool) now reads it instead of the forecast.  The automation no
# longer names a source at all: it reads `Climate temp outdoor`, a resolved sensor like the
# rooms have, so the fallback lives in one place and is tested here.
#
#   1. the terrace sensor   -- measured, at the house
#   2. the forecast         -- the only outdoor source before 2026-09-25
#   3. nothing              -- `outdoor` becomes -999 and the house falls to shoulder
#
# Staleness is NOT judged in the template.  The sensor reads in ~0.14 C steps and HA's MQTT
# sensors skip writing an unchanged value, so a still night can hold one reading for hours
# with a perfectly healthy device; an age test on last_reported would flip the house to the
# forecast (2-3 C away the first night) and back.  Zigbee2MQTT marks this one device
# unavailable after 3 h without ANY message instead (it reports four clusters at least
# hourly), and that arrives here as 'unavailable' -- which these cases do cover.
#
# Terrace and forecast carry different values in every case, so the output names one tier.
OUT = "Climate temp outdoor"
OUT_T = "states('sensor.outdoor_motion_temperature')"
# The forecast sensor's live id carries the street name, so it is published as
# `sensor.house_temperature` and resolved from the gitignored local map here.
OUT_W = "states('%s')" % harness.load_rooms()["house"]["forecast_temp"]
OUT_R = "states('sensor.climate_temp_outdoor')"
OUT_A = "states('sensor.ac_outdoor_temperature')"  # the AC probes' min_max helper

A(sensor_case(
    "the terrace sensor outranks the forecast", "13.1",
    {OUT_T: "'13.1'", OUT_W: "'10.6'"},
    sensor=OUT, finding="2026-09-25: measured at the house beats modelled for the area"))
A(sensor_case(
    "an unavailable terrace sensor falls to the forecast when the AC helper is down too", "10.6",
    {OUT_T: "'unavailable'", OUT_A: "'unavailable'", OUT_W: "'10.6'"},
    sensor=OUT, finding="Z2M's 3 h availability timeout lands here, not on a stale number"))
A(sensor_case(
    "a terrace sensor that has not reported yet falls to the forecast", "10.6",
    {OUT_T: "'unknown'", OUT_A: "'unavailable'", OUT_W: "'10.6'"},
    sensor=OUT, finding="after a restart or re-pair the sensor is 'unknown' first"))
A(sensor_case(
    "a terrace reading of exactly zero is a reading", "0.0",
    {OUT_T: "'0.0'", OUT_A: "'2.0'", OUT_W: "'3.0'"},
    sensor=OUT, finding="0 C is the reading that matters most in winter; not falsy. The AC helper is "
                        "pinned: left live, it read 0.0 on 2026-11-27 and the falsy-zero mutation passed"))
A(sensor_case(
    "a sub-zero terrace reading is used as it is", "-5.3",
    {OUT_T: "'-5.3'", OUT_W: "'-2.0'"},
    sensor=OUT, finding="the -900 cutoff must not swallow real frost"))
A(sensor_case(
    "every outdoor source down yields nothing", "",
    {OUT_T: "'unavailable'", OUT_A: "'unavailable'", OUT_W: "'unavailable'"},
    sensor=OUT, finding="R7-9: the skip sentinel, never a fabricated number"))

# The empty state alone does not clear the entity -- HA kept the old number when that was
# tried on the radiation sensor -- so availability gates it, exactly as there.
A(sensor_case(
    "the outdoor sensor is available on the terrace alone", "True",
    {OUT_T: "'13.1'", OUT_A: "'unavailable'", OUT_W: "'unavailable'"},
    sensor=OUT + "::availability", finding="either source is enough"))
A(sensor_case(
    "the outdoor sensor is available on the forecast alone", "True",
    {OUT_T: "'unavailable'", OUT_A: "'unavailable'", OUT_W: "'10.6'"},
    sensor=OUT + "::availability", finding="either source is enough"))
A(sensor_case(
    "the outdoor sensor is unavailable when every source is", "False",
    {OUT_T: "'unavailable'", OUT_A: "'unavailable'", OUT_W: "'unavailable'"},
    sensor=OUT + "::availability",
    finding="an empty state kept the previous number on the radiation sensor"))

# 2026-11-06 (operator): the AC outdoor probes are the second tier, ahead of the forecast, which
# is now the LAST resort.  The probes sit on the five units and drop out when a unit disconnects
# or reboots, so they are read through one min_max helper (it skips unavailable members), and
# the helper is what this tier reads.
#
#   1. the terrace sensor   -- measured, at the house
#   2. the AC outdoor helper -- measured on the units, mean of whichever are reporting
#   3. the forecast         -- only when both measured sources are down

A(sensor_case(
    "the AC outdoor helper answers when the terrace sensor is down", "9.4",
    {OUT_T: "'unavailable'", OUT_A: "'9.4'", OUT_W: "'10.6'"},
    sensor=OUT, finding="2026-11-06: a measured AC probe beats the modelled forecast"))
A(sensor_case(
    "the terrace sensor still outranks the AC outdoor helper", "13.1",
    {OUT_T: "'13.1'", OUT_A: "'9.4'", OUT_W: "'10.6'"},
    sensor=OUT, finding="2026-11-06: the terrace is the house's own sensor, not a probe on a unit"))
A(sensor_case(
    "the forecast is the last resort when terrace and AC are both down", "10.6",
    {OUT_T: "'unavailable'", OUT_A: "'unavailable'", OUT_W: "'10.6'"},
    sensor=OUT, finding="2026-11-06: forecast only when both measured sources are gone"))
A(sensor_case(
    "an unknown AC helper falls through to the forecast", "10.6",
    {OUT_T: "'unknown'", OUT_A: "'unknown'", OUT_W: "'10.6'"},
    sensor=OUT, finding="2026-11-06: after a restart the helper reads unknown until a unit reports"))
A(sensor_case(
    "a reading of exactly zero from the AC helper is a reading", "0.0",
    {OUT_T: "'unavailable'", OUT_A: "'0.0'", OUT_W: "'3.0'"},
    sensor=OUT, finding="2026-11-06: 0 C is falsy-proof, as on the terrace"))
A(sensor_case(
    "the outdoor sensor is available on the AC helper alone", "True",
    {OUT_T: "'unavailable'", OUT_A: "'9.4'", OUT_W: "'unavailable'"},
    sensor=OUT + "::availability", finding="2026-11-06: any measured source keeps it available"))

A(case("the house reads the resolved outdoor sensor", "outdoor", "13.1",
       {}, {OUT_R: "'13.1'"},
       finding="2026-09-25: the automation names no outdoor source of its own"))
A(case("an unavailable resolved outdoor sensor is the -999 sentinel", "outdoor", "-999",
       {}, {OUT_R: "'unavailable'"},
       finding="the sentinel the house decision already falls to shoulder on"))


# ---------------------------------------------------------------- wet rooms
# 2026-10-07: the bathroom and shower readings are Magic Areas aggregates (native, the operator's
# preference) - there is no expression of ours to test. Their one-sensor assumption is guarded by
# tests/dashboards/lint.py C20 instead.


# ---------------------------------------------------------------- daylight, for presence lighting
# 2026-10-07.  Magic Areas turns a room's lights ON when it becomes occupied only while the room is
# DARK -- and with no darkness entity configured it assumes dark, around the clock.  So the living
# room's new mmWave sensor would switch the lamps on at noon.  `binary_sensor.lighting_daylight`
# is that entity: on = bright enough, no lights.
#
# The hazard is a flap at dusk.  Magic Areas reacts to a room turning BRIGHT by switching an
# occupied room's lights OFF -- with somebody sitting in it.  So the sensor has hysteresis: it goes
# dark below the threshold but needs TWICE the threshold to come back bright.  These cases straddle
# both edges, in both directions; a case at a level where both answers agree proves nothing.
# Outdoor light is the Hue terrace sensor; when it is dead the sun's elevation decides.
DAY = "Lighting daylight"
LUX = "states('sensor.outdoor_motion_illuminance')"
LUX_T = "states('input_number.lighting_dark_below_lux')"
WAS = "this.state"
ELEV = "state_attr('sun.sun','elevation')"

A(sensor_case("daylight: bright stays bright between the two edges", "True",
              {LUX: "'500'", LUX_T: "'400.0'", WAS: "'on'", ELEV: "30.0"}, sensor=DAY,
              finding="hysteresis: a passing cloud at dusk must not flip the room bright-dark-bright"))
A(sensor_case("daylight: dark stays dark between the two edges", "False",
              {LUX: "'500'", LUX_T: "'400.0'", WAS: "'off'", ELEV: "30.0"}, sensor=DAY,
              finding="hysteresis: BRIGHT turns an occupied room's lights OFF, so it must be earned"))
A(sensor_case("daylight: bright goes dark below the threshold", "False",
              {LUX: "'390'", LUX_T: "'400.0'", WAS: "'on'", ELEV: "30.0"}, sensor=DAY,
              finding="the lower edge"))
A(sensor_case("daylight: dark goes bright above twice the threshold", "True",
              {LUX: "'810'", LUX_T: "'400.0'", WAS: "'off'", ELEV: "-10.0"}, sensor=DAY,
              finding="the upper edge; the sun is not consulted while the lux sensor is alive"))
A(sensor_case("daylight: dark stays dark just under twice the threshold", "False",
              {LUX: "'790'", LUX_T: "'400.0'", WAS: "'off'", ELEV: "30.0"}, sensor=DAY,
              finding="the upper edge, from below"))
A(sensor_case("daylight: a first evaluation starts on the dark side", "False",
              {LUX: "'500'", LUX_T: "'400.0'", WAS: "'unknown'", ELEV: "30.0"}, sensor=DAY,
              finding="after a restart, err towards a lit room, never towards switching one off"))
A(sensor_case("daylight: 0 lx at night is a reading, not a dead sensor", "False",
              {LUX: "'0'", LUX_T: "'400.0'", WAS: "'on'", ELEV: "30.0"}, sensor=DAY,
              finding="the lux sentinel is -1; a 0 must not fall through to the sun"))
A(sensor_case("daylight: a dead lux sensor falls to the sun, high", "True",
              {LUX: "'unavailable'", LUX_T: "'400.0'", WAS: "'off'", ELEV: "20.0"}, sensor=DAY,
              finding="the terrace sensor drops off Zigbee; lighting must not stop working"))
A(sensor_case("daylight: a dead lux sensor falls to the sun, low", "False",
              {LUX: "'unavailable'", LUX_T: "'400.0'", WAS: "'on'", ELEV: "4.0"}, sensor=DAY,
              finding="a low sun is dark indoors well before sunset"))
A(sensor_case("daylight: a missing threshold helper falls back to 400 lx", "False",
              {LUX: "'390'", LUX_T: "'unavailable'", WAS: "'on'", ELEV: "30.0"}, sensor=DAY,
              finding="the default must be a sane threshold, not 0 (never dark) or a huge one"))

# Review 2026-10-07 (A1): the sun fallback had no hysteresis. A dark, occupied room whose lux sensor
# died at noon flipped straight to BRIGHT - and BRIGHT switches an occupied room's lights OFF. The
# fallback now needs a clearly high sun (12 deg) to brighten a dark room; a bright one stays bright
# down to 6 deg. Straddle: 8 deg is between the two edges.
A(sensor_case("daylight: a dead lux sensor does not brighten a dark room at a middling sun", "False",
              {LUX: "'unavailable'", LUX_T: "'400.0'", WAS: "'off'", ELEV: "8.0"}, sensor=DAY,
              finding="review 2026-10-07 A1: the fallback flipped an occupied room BRIGHT"))
A(sensor_case("daylight: a dead lux sensor keeps a bright room bright at a middling sun", "True",
              {LUX: "'unavailable'", LUX_T: "'400.0'", WAS: "'on'", ELEV: "8.0"}, sensor=DAY,
              finding="review 2026-10-07 A1: the fallback's lower edge"))
A(sensor_case("daylight: a dead lux sensor brightens a dark room once the sun is high", "True",
              {LUX: "'unavailable'", LUX_T: "'400.0'", WAS: "'off'", ELEV: "13.0"}, sensor=DAY,
              finding="review 2026-10-07 A1: the fallback's upper edge"))
A(sensor_case("daylight: no lux and no sun elevation is dark", "False",
              {LUX: "'unavailable'", LUX_T: "'400.0'", WAS: "'on'", ELEV: "none"}, sensor=DAY,
              finding="review 2026-10-07 A4: the fallback of the fallback errs towards a lit room"))

# Review 2026-10-07 (A5): the air-quality sensor reports WHOLE degrees. Pin a real whole-degree input,
# so the case data matches the instrument - this tier is a 1 deg C degraded mode, by design.
A(sensor_case("kid 1: a whole-degree air-quality reading passes through", "24.0",
              {K1_Q_T: "'24'", K1_B_T: "'unavailable'", K1_V_T: "'22.0'",
               K1_A_T: "'25.0'", K1_CONN: "true", K1_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
              sensor=K1_T, finding="review 2026-10-07 A5: the instrument's real resolution"))


# ---------------------------------------------------------------- open-space darkness: the room decides
# 2026-10-20, operator: the living room "was very dark before the lights turned on".  It was occupied
# and the FP2 read 150 lx at 16:49 and ~50 lx by 17:13, but the terrace read 1469 lx, and the
# 2026-10-12 rule "bright outside = bright inside" held the lamps off until the terrace fell below
# 400 lx at 17:40.  Fifty-one minutes in a dark room.  A 10-minute mean of the FP2 added more lag.
#
# Simplified: `Lighting living room bright` reads the FP2 itself (real time) against the indoor
# slider, dark below it, bright above twice it, held in between.  The one-second dips the mean used
# to absorb (83 lx for a second at 16:10) are absorbed by the helper's native delay_off (1 min);
# delay_on (5 min) keeps a sunbeam from switching an occupied room's lamps off.  Outdoors is only
# the fallback for a dead FP2.  `Lighting kitchen dark` is the exact inverse - one decision for one
# open space.  The 2026-10-12 case (FP2 dim at a sunny noon) is now the slider's job, not outdoors'.
LRB = "Lighting living room bright"
FP2 = "states('sensor.living_room_livingroom_fp2_light_sensor_light_level')"
SLIDER = "states('input_number.lighting_indoor_dark_below_lux')"
OUT_BRIGHT = "is_state('binary_sensor.lighting_daylight','on')"


def _lr(expect, lux, slider, was, out="false", finding=""):
    A(sensor_case("open space: FP2 %s, slider %s, was %s, outdoor %s" % (lux, slider, was, out),
                  expect, {FP2: repr(lux), SLIDER: repr(slider), WAS: repr(was), OUT_BRIGHT: out},
                  sensor=LRB, finding=finding))


_lr("False", "80", "150", "on", out="true",
    finding="2026-10-20: a dark room is dark, however bright the terrace (51 min of darkness)")
_lr("True", "301", "150", "off", finding="just above twice the slider is bright")
_lr("False", "300", "150", "off", finding="the upper edge is exclusive")
_lr("True", "299", "150", "on", finding="held: a bright room stays bright inside the band")
_lr("False", "299", "150", "off", finding="held: a dark room stays dark inside the band")
_lr("False", "149", "150", "on", finding="just below the slider is dark")
_lr("True", "150", "150", "on", finding="the lower edge is exclusive")
_lr("True", "250", "100", "off", finding="the slider moves the edge: 250 is bright above 2x100")
_lr("False", "250", "300", "off", finding="and the other way: 250 is inside the band at 300")
_lr("True", "301", "unavailable", "off", finding="a missing slider falls back to 150")
_lr("False", "250", "0", "off",
    finding="a slider at 0 is not a threshold of 0 (new helpers start at the minimum)")
_lr("True", "unavailable", "150", "off", out="true",
    finding="a dead FP2 by day defers to outdoors: no lamps at noon")
_lr("False", "unknown", "150", "on", out="false",
    finding="a dead FP2 at dusk defers to outdoors: the lamps may come on")
_lr("False", "0", "150", "on", finding="0 lx is a reading, not a dead sensor")
_lr("False", "250", "150", "unknown", finding="a first evaluation inside the band starts dark")

# 2026-10-21: the kitchen needs no darkness of its own.  Every kitchen group is gated on dark, so it
# reads `living_room_bright` natively as its Magic Areas dark entity (one open space), and night is
# Magic Areas' own `sleep` priority.  `Lighting kitchen dark` is read by nothing now.

# 2026-10-21, operator: "i sleep in, and don't want lights to turn on automatically at 6 - while it's
# still dark outside and i simply turn in the bed".  At 06:00 the alarm leaves Night, the bedroom
# loses `sleep`, and the PIR lit the lamps.  The bedroom's sleep entity is its own: night, or any
# time before noon.  The evening (before night) still lights the lamps.
BS = "Lighting bedroom sleep"
NIGHT_ON = "is_state('binary_sensor.lighting_night','on')"
HOUR = "now().hour"


def _bs(expect, night, hour, finding=""):
    A(sensor_case("bedroom sleep: night %s at %s:00" % (night, hour), expect,
                  {NIGHT_ON: night, HOUR: hour}, sensor=BS, finding=finding))


_bs("True", "true", "22", finding="night is sleep")
_bs("True", "false", "6", finding="2026-10-21: the alarm left Night at 06:00; the operator is asleep")
_bs("True", "false", "11", finding="the last morning hour still sleeps")
_bs("False", "false", "12", finding="noon ends the morning")
_bs("False", "false", "20", finding="the evening before night lights the lamps")


# ---------------------------------------------------------------- any safety alarm (Home: Needs attention)
# 2026-10-09.  A smoke and CO alarm went into the corridor, and Home's *Needs attention* section
# turned out to be hand-listed: it knew one leak sensor by entity id and nothing about smoke, gas or
# CO.  `binary_sensor.any_safety_alarm` makes it self-maintaining: on while ANY leak, smoke, gas, CO
# or safety sensor in the house is on.  The whole binary_sensor domain is substituted with a literal
# list, so each case states the house it describes.
SAFE = "Any safety alarm"
ALL_BS = "states.binary_sensor"


def _bs(eid, state, dc):
    return {"entity_id": eid, "state": state, "attributes": ({"device_class": dc} if dc else {})}


def _house(*sensors):
    return repr(list(sensors))


A(sensor_case("safety: a CO alarm raises it", "True",
              {ALL_BS: _house(_bs("binary_sensor.co", "on", "carbon_monoxide"),
                              _bs("binary_sensor.door", "on", "door"))},
              sensor=SAFE, finding="2026-10-09: Needs attention knew nothing about smoke or CO"))
A(sensor_case("safety: a smoke alarm raises it", "True",
              {ALL_BS: _house(_bs("binary_sensor.smoke", "on", "smoke"))},
              sensor=SAFE, finding="2026-10-09: Needs attention knew nothing about smoke or CO"))
A(sensor_case("safety: any leak sensor raises it, not only the one it was written for", "True",
              {ALL_BS: _house(_bs("binary_sensor.new_leak", "on", "moisture"))},
              sensor=SAFE, finding="2026-10-09: the section named one leak sensor by entity id"))
A(sensor_case("safety: quiet sensors leave it off", "False",
              {ALL_BS: _house(_bs("binary_sensor.smoke", "off", "smoke"),
                              _bs("binary_sensor.leak", "off", "moisture"))},
              sensor=SAFE, finding="the section must stay hidden in a calm house"))
A(sensor_case("safety: an open door or motion is not a safety alarm", "False",
              {ALL_BS: _house(_bs("binary_sensor.door", "on", "door"),
                              _bs("binary_sensor.motion", "on", "motion"),
                              _bs("binary_sensor.nodc", "on", None))},
              sensor=SAFE, finding="only the safety classes count"))
A(sensor_case("safety: an unavailable alarm is not a fire", "False",
              {ALL_BS: _house(_bs("binary_sensor.smoke", "unavailable", "smoke"))},
              sensor=SAFE, finding="a dead battery must not cry fire on the family Home page"))
A(sensor_case("safety: the roll-up never counts itself", "False",
              {ALL_BS: _house(_bs("binary_sensor.any_safety_alarm", "on", "safety"),
                              _bs("binary_sensor.smoke", "off", "smoke"))},
              sensor=SAFE, finding="a roll-up in its own class would latch on forever"))


# ---------------------------------------------------------------- the hallway gets a darkness gate
# 2026-10-20, operator: the upstairs hallway lit "even when it's a lot of sun outside and in the room".
# It had no dark entity (Magic Areas then assumes dark around the clock).  It now gets the living-room
# rule on its OWN sensor, the FP300's lux, against `input_number.lighting_hallway_dark_below_lux`:
# dark below it, bright above TWICE it, held in between.  The 2026-10-12 objection - the sensor sits
# near the bulb - is measured, not assumed: the lamp adds 10-20 lx at the sensor (06:27 0->11,
# 17:39 12->32), so with the band at 2x a floor of 20 lx the lamp cannot carry a dark hallway
# across the upper edge and have Magic Areas switch it off under someone.  The floor is in the
# template, not only in the helper's bounds.  A dead FP300 defers to the outdoor daylight sensor.
HW_B = "Lighting hallway bright"
HW_LUX = "states('sensor.hallway_presence_illuminance')"
HW_SL = "states('input_number.lighting_hallway_dark_below_lux')"
HW_OUT = "is_state('binary_sensor.lighting_daylight','on')"


def _hw(expect, lux, slider, was, out="false", finding=""):
    A(sensor_case("hallway: lux %s, slider %s, was %s, outdoor %s" % (lux, slider, was, out),
                  expect, {HW_LUX: repr(lux), HW_SL: repr(slider), WAS: repr(was), HW_OUT: out},
                  sensor=HW_B, finding=finding))


_hw("True", "61", "30", "off", finding="2026-10-20: just above twice the slider is bright")
_hw("False", "60", "30", "off", finding="the upper edge is exclusive")
_hw("True", "59", "30", "on", finding="held: a bright hallway stays bright inside the band")
_hw("False", "59", "30", "off", finding="held: a dark hallway stays dark inside the band")
_hw("False", "29", "30", "on", finding="just below the slider is dark")
_hw("True", "30", "30", "on", finding="the lower edge is exclusive")
_hw("False", "49", "30", "off",
    finding="the lamp itself (+20 lx on a 29 lx hallway) does not make it bright")
_hw("True", "250", "100", "off", finding="the slider moves the edge: 250 is bright above 2x100")
_hw("False", "150", "100", "off", finding="and 150 is inside the band at 100")
_hw("True", "61", "unavailable", "off", finding="a missing slider falls back to 30")
_hw("False", "35", "10", "off",
    finding="a slider under the 20 lx floor is raised to it: at 10 the lamp alone would read bright")
_hw("True", "unavailable", "30", "off", out="true",
    finding="a dead FP300 by day defers to outdoors: no lamp at noon")
_hw("False", "unknown", "30", "on", out="false",
    finding="a dead FP300 at night defers to outdoors: the lamp may come on")


# ---------------------------------------------------------------- the office gets presence lighting
# 2026-11-24, operator: an FP2 went into the office / guest room.  Same rule as the living room, on
# the office FP2's own lux, against the HOUSEHOLD indoor slider in the admin panel
# (`input_number.lighting_indoor_dark_below_lux`) - operator: "use them for the whole household", so
# no per-room slider.  Measured at fit-up: Hugo at full adds ~10 lx at the sensor (41 -> 50), far
# below the 2x band, so the lamp cannot carry its own room across the upper edge.  The room read
# ~50 lx at a November noon with the lamps off: dark by the household threshold, as the operator
# wanted.  A dead FP2 defers to the outdoor daylight sensor.
OF_B = "Lighting office bright"
OF_LUX = "states('sensor.guest_room_office_fp2_light_sensor_light_level')"
OF_SL = "states('input_number.lighting_indoor_dark_below_lux')"


def _of(expect, lux, slider, was, out="false", finding=""):
    A(sensor_case("office: lux %s, slider %s, was %s, outdoor %s" % (lux, slider, was, out),
                  expect, {OF_LUX: repr(lux), OF_SL: repr(slider), WAS: repr(was), HW_OUT: out},
                  sensor=OF_B, finding=finding))


_of("False", "50", "150", "on", out="true",
    finding="2026-11-24: 50 lx at a November noon is dark, whatever outdoors says")
_of("True", "301", "150", "off", finding="just above twice the household slider is bright")
_of("False", "300", "150", "off", finding="the upper edge is exclusive")
_of("True", "200", "150", "on", finding="held: a bright office stays bright inside the band")
_of("False", "200", "150", "off", finding="held: a dark office stays dark inside the band")
_of("False", "149", "150", "on", finding="just below the slider is dark")
_of("True", "150", "150", "on", finding="the lower edge is exclusive")
_of("True", "250", "100", "off", finding="the household slider moves the office edge too")
_of("True", "301", "unavailable", "off", finding="a missing slider falls back to 150")
_of("False", "100", "0", "off",
    finding="a slider at 0 falls back to 150, not a threshold of 0 (100 lx would read bright)")
_of("False", "0", "150", "on", out="true",
    finding="0 lx is a reading, not a dead sensor: a pitch-dark office does not defer to outdoors")
_of("True", "unavailable", "150", "off", out="true",
    finding="a dead FP2 by day defers to outdoors: no lamp at noon")
_of("False", "unknown", "150", "on", out="false",
    finding="a dead FP2 at night defers to outdoors: the lamp may come on")
_hw("False", "0", "30", "on", finding="0 lx is a reading, not a dead sensor")
_hw("False", "45", "30", "unknown", finding="a first evaluation inside the band starts dark")


# ---------------------------------------------------------------- stairs: the corridor light, not the entrance
# 2026-10-25, operator: a motion sensor at the foot of the stairs lights the stairs AND the corridor
# light (the two light the staircase), but not the entrance light.  Magic Areas only drives a group
# while its area is occupied, so the stairs sensor is a corridor presence sensor (include_entities),
# and `accented` tells the two corridor groups apart.  `Lighting corridor presence` is that accent:
# some corridor sensor OTHER than the stairs one sees someone.  Entrance light = accented (+ sleep);
# corridor light = occupied + accented (+ sleep).  The inverse ("stairs only") was rejected before
# it shipped: the stairs sensor makes the area occupied a moment before such an accent arrives, so
# the entrance light blinked on, and when the stairs sensor cleared inside the clear timeout the
# accent fell away from an occupied area and lit the entrance for a minute.  Here the stairs sensor
# never reaches the entrance by day.  The sensors are read from Magic Areas' own list, so a new
# corridor sensor needs no edit; the stairs sensor is on that list too and must not count.
CP = "Lighting corridor presence"
CP_LIST = "state_attr('binary_sensor.magic_areas_presence_tracking_corridor_area_state','presence_sensors')"
CP_ON = "select('is_state','on')"
CP_C = ["binary_sensor.corridor_presence_presence", "binary_sensor.evo192_zone_entrance_pir_open",
        "binary_sensor.evo192_zone_entrance_door_open", "binary_sensor.stairs_motion_occupancy"]


def _cp(expect, on, listed=CP_C, finding=""):
    A(sensor_case("corridor presence: on %s, listed %s" % (on, "MA list" if listed == CP_C else listed),
                  expect, {CP_LIST: repr(listed), CP_ON: "select('in', %r)" % list(on)},
                  sensor=CP, finding=finding))


_cp("False", ["binary_sensor.stairs_motion_occupancy"],
    finding="2026-10-25: the stairs sensor alone is not the corridor - no entrance light for the stairs")
_cp("True", ["binary_sensor.stairs_motion_occupancy", "binary_sensor.corridor_presence_presence"],
    finding="someone in the corridor while the stairs sensor is on still gets the entrance light")
_cp("True", ["binary_sensor.corridor_presence_presence"], finding="the corridor mmWave")
_cp("True", ["binary_sensor.evo192_zone_entrance_pir_open"], finding="the alarm PIR counts as the corridor")
_cp("False", [], finding="nobody anywhere")
_cp("False", ["binary_sensor.corridor_presence_presence"], listed=None,
    finding="Magic Areas not loaded: renders, does not error")


# ---------------------------------------------------------------- batteries and lights left on
# 2026-10-12.  Two roll-ups that feed notifications.  `Any low battery` lists the house's battery
# sensors under 20 % so a leak sensor at 15 % is not found by it failing.  Phones, the car and the
# robot vacuums are charged by people, not replaced, so they are skipped: phones and the car by
# integration, vacuums by DEVICE - every entity of a device that has a `vacuum.*`.  Audit 2026-10-20:
# the Roborock is also bridged over Matter, and that copy of its battery belongs to no `roborock`
# entry, so skipping by integration would nag about the vacuum the day it ran low.
# `Lighting left on` lists the lights still on when everyone has left.  Group lights (they carry an
# `entity_id` attribute: Magic Areas, Gallery) would list every lamp twice, and the UniFi switch
# LEDs are indicators, not lighting.  Both answer `none` when there is nothing to say, never "".
LOWB = "Any low battery"
LEFT = "Lighting left on"
ALL_S = "states.sensor"
ALL_L = "states.light"
SKIP_MA = "integration_entities('mobile_app')"
SKIP_VO = "integration_entities('volvo')"
SKIP_VAC = ("states.vacuum | map(attribute='entity_id') | map('device_id') | reject('none') "
            "| map('device_entities') | sum(start=[])")


def _bat(eid, state, name=None):
    return {"entity_id": eid, "state": state,
            "attributes": {"device_class": "battery", "friendly_name": name or eid}}


def _lowb(*sensors, skip_ma=(), skip_vo=(), skip_vac=()):
    return {ALL_S: repr(list(sensors)), SKIP_MA: repr(list(skip_ma)), SKIP_VO: repr(list(skip_vo)),
            SKIP_VAC: "(%r)" % list(skip_vac)}


# Issue #3, 2026-10-20: the roll-up says ENTITY IDS, like `Lighting left on` and the silent-sensor
# roll-up, so Home can make each one a tile that opens it; its consumers render name and level.
A(sensor_case("battery: a sensor under 20 % is listed by entity id", "sensor.leak_battery",
              _lowb(_bat("sensor.leak_battery", "15", "Leak")), sensor=LOWB,
              finding="2026-10-12: a leak sensor sat at 15 % with nothing to say so"))
A(sensor_case("battery: exactly 20 % is not yet low", "none",
              _lowb(_bat("sensor.a_battery", "20")), sensor=LOWB,
              finding="the edge: the threshold is 'under 20'"))
A(sensor_case("battery: 19 % is low", "sensor.a_battery",
              _lowb(_bat("sensor.a_battery", "19", "A")), sensor=LOWB,
              finding="the edge from below"))
A(sensor_case("battery: an unavailable battery is not a number", "none",
              _lowb(_bat("sensor.a_battery", "unavailable")), sensor=LOWB,
              finding="a dead sensor is a different alert, and must not crash the list"))
A(sensor_case("battery: a phone at 5 % is not a replaceable battery", "none",
              _lowb(_bat("sensor.phone_battery_level", "5"), skip_ma=["sensor.phone_battery_level"]),
              sensor=LOWB, finding="phones are charged; they would nag every evening"))
A(sensor_case("battery: the car and the vacuum are skipped too", "none",
              _lowb(_bat("sensor.car_battery", "5"), _bat("sensor.vac_battery", "5"),
                    skip_vo=["sensor.car_battery"], skip_vac=["sensor.vac_battery"]),
              sensor=LOWB, finding="same reason, other integrations"))
A(sensor_case("battery: the vacuum seen through Matter is skipped too", "none",
              _lowb(_bat("sensor.robotic_vacuum_cleaner_battery", "5"),
                    skip_vac=["vacuum.robotic_vacuum_cleaner", "sensor.robotic_vacuum_cleaner_battery"]),
              sensor=LOWB, finding="audit 2026-10-20: the Matter bridge's copy is no roborock entity"))
A(sensor_case("battery: a sensor on a device with no vacuum is still listed", "sensor.leak_battery",
              _lowb(_bat("sensor.leak_battery", "5", "Leak"),
                    skip_vac=["vacuum.robotic_vacuum_cleaner", "sensor.robotic_vacuum_cleaner_battery"]),
              sensor=LOWB, finding="audit 2026-10-20: the vacuum rule skips the vacuum, not Matter"))
A(sensor_case("battery: several are listed together", "sensor.a, sensor.b",
              _lowb(_bat("sensor.a", "10", "A"), _bat("sensor.ok", "80", "OK"),
                    _bat("sensor.b", "3.4", "B")), sensor=LOWB,
              finding="one message, every low battery, healthy ones left out"))
# Audit 2026-10-20: a state over 255 characters is rejected and reads `unknown`, which hides Home's
# note exactly when the most batteries are low.  The list stops before 240 and says how many more,
# as a last item of its own so a consumer splitting on ', ' never reads it as an entity id.
_many = [_bat("sensor.s%02d" % i, "5", "Sensor %02d" % i) for i in range(1, 31)]
A(sensor_case("battery: a long list is cut short and says how many more",
              ", ".join("sensor.s%02d" % i for i in range(1, 21)) + ", +10 more",
              _lowb(*_many), sensor=LOWB,
              finding="audit 2026-10-20: 30 low batteries would exceed HA's 255-character state"))
A(sensor_case("battery: nothing low is the word none, not empty", "none",
              _lowb(_bat("sensor.a", "80")), sensor=LOWB,
              finding="an empty state reads unknown and would trigger the notification"))


def _light(eid, state, group=False):
    attrs = {"entity_id": ["light.x"]} if group else {}
    return {"entity_id": eid, "state": state, "attributes": attrs}


def _left(*lights):
    return {ALL_L: repr(list(lights))}


A(sensor_case("left on: a lamp that is on is named by entity id", "light.lamp",
              _left(_light("light.lamp", "on"), _light("light.other", "off")), sensor=LEFT,
              finding="2026-10-12: nothing said what was left on when the house emptied"))
A(sensor_case("left on: a group light is skipped, its members are listed", "light.gallery_left",
              _left(_light("light.gallery", "on", group=True), _light("light.gallery_left", "on")),
              sensor=LEFT, finding="a group would list every lamp twice and turn it off twice"))
A(sensor_case("left on: a Zigbee2MQTT group is skipped, its bulbs are listed", "light.lr1",
              _left({"entity_id": "light.living_room_main", "state": "on",
                     "attributes": {"group_entities": ["light.lr1"]}},
                    _light("light.lr1", "on")), sensor=LEFT,
              finding="2026-10-14: Living Room Main and Gallery became Zigbee groups, which list "
                      "members as group_entities, not entity_id - each lamp was named twice"))
A(sensor_case("left on: a switch LED is an indicator", "none",
              _left(_light("light.rack_switch_led", "on")), sensor=LEFT,
              finding="UniFi switch LEDs are always on and are not lighting"))
A(sensor_case("left on: an unavailable bulb is not on", "none",
              _left(_light("light.hallway", "unavailable")), sensor=LEFT,
              finding="a wall-switched bulb reads unavailable, not on"))
A(sensor_case("left on: nothing on is the word none", "none", _left(), sensor=LEFT,
              finding="an empty state reads unknown and would trigger the notification"))


# ---------------------------------------------------------------- night: the alarm is the house mode
# 2026-10-11, operator: "switch the alarm to night mode based on a schedule, and sync all binary
# and climate entities to use it as source of truth; I'll also be able to switch the alarm to
# day/night manually".  So `alarm_control_panel.home` == armed_night IS night, for everything.
# `schedule.climate_night` only DRIVES the alarm, at its edges (automation "House - night mode").
# Alarmo has no sensors, codes or sirens here: arming it is a house-mode switch and nothing else.
ALARM = "states('alarm_control_panel.home')"
SCHED_ON = "is_state('schedule.climate_night','on')"

# The climate loop's own night.  Until now it was "schedule OR armed_night", which would keep the
# house in night mode after the operator switched to day by hand - the exact control they asked for.
# Review 2026-10-11 (F12): while the ALARM ITSELF is unavailable/unknown (an Alarmo reload, a
# restart) "not armed_night" is not evidence of day - the loop would compute DAY targets at night.
# Only then does the schedule stand in.  Every case pins both reads.
# Audit 2026-10-20: the same definition is copied into every consumer (harness.NIGHT_CONSUMERS says
# why it is not read from one helper), and the radiators' copy had no case at all.  Every copy runs
# the same table, and wiring.py fails on a copy that is not in the list.
for _who, _where, _key in harness.NIGHT_CONSUMERS:
    def _c(name, expect, alarm, sched, finding, _who=_who, _where=_where, _key=_key):
        subs = {ALARM: alarm, SCHED_ON: sched}
        if _where == "sensor":
            return sensor_case("%s: %s" % (_who, name), expect, subs, finding=finding, sensor=_key)
        if _where == harness.AUTOMATION_ID:
            # No `automation` key: mutate.py's "expr" kind mutates this default set in place.
            return case("%s: %s" % (_who, name), _key, expect, {}, subs, finding=finding)
        return dict(name="%s: %s" % (_who, name), automation=_where, expr=_key,
                    expect=expect, given={}, subs=subs, finding=finding)
    A(_c("night is the alarm's night mode", "True", "'armed_night'", "false",
         "2026-10-11: the alarm is the source of truth, even outside the schedule"))
    A(_c("the schedule alone no longer makes it night", "False", "'armed_home'", "true",
         "2026-10-11: a manual switch to day must win over the schedule"))
    A(_c("disarmed in the schedule window is day", "False", "'disarmed'", "true",
         "2026-10-11: manual wins - disarmed is a choice"))
    A(_c("away is not night", "False", "'armed_away'", "true", "away has its own band"))
    A(_c("an unavailable alarm falls back to the schedule, at night", "True", "'unavailable'", "true",
         "review 2026-10-11 F12: a reload at night must not compute day targets"))
    A(_c("an unavailable alarm falls back to the schedule, by day", "False", "'unavailable'", "false",
         "review 2026-10-11 F12: the fallback is the schedule, not 'always night'"))
    A(_c("an unknown alarm falls back to the schedule", "True", "'unknown'", "true",
         "review 2026-10-11 F12: restart restores to unknown first"))

# The automation that moves the alarm on the schedule's edges, and keeps Adaptive Lighting's
# sleep mode in step with it.
HOUSE = "1790200000001"
SCHED_TO = "trigger.to_state.state"
ALARM_NOW = "states('alarm_control_panel.home')"


def house(name, expr, expect, subs, finding):
    return dict(name=name, automation=HOUSE, expr=expr, expect=expect, given={}, subs=subs,
                finding=finding)


A(house("22:00 turns Home into Night", "want", "night",
        {SCHED_TO: "'on'", ALARM_NOW: "'armed_home'"}, "2026-10-11: the evening edge"))
A(house("22:00 turns Disarmed into Night", "want", "night",
        {SCHED_TO: "'on'", ALARM_NOW: "'disarmed'"}, "2026-10-11 operator: from home OR disarmed"))
A(house("22:00 leaves Away alone", "want", "none",
        {SCHED_TO: "'on'", ALARM_NOW: "'armed_away'"},
        "away wins: the climate away band and the house's empty state must not be undone"))
A(house("22:00 leaves an alarm that is already Night alone", "want", "none",
        {SCHED_TO: "'on'", ALARM_NOW: "'armed_night'"}, "no redundant command"))
A(house("22:00 leaves a triggered alarm alone", "want", "none",
        {SCHED_TO: "'on'", ALARM_NOW: "'triggered'"}, "never touch an alarm that is going off"))
A(house("06:00 turns Night into Home", "want", "home",
        {SCHED_TO: "'off'", ALARM_NOW: "'armed_night'"}, "2026-10-11: the morning edge"))
A(house("06:00 leaves a manual Home alone", "want", "none",
        {SCHED_TO: "'off'", ALARM_NOW: "'armed_home'"},
        "2026-10-11: the operator switched to day by hand; the morning must not re-assert it"))
A(house("06:00 never disarms or arms from Away", "want", "none",
        {SCHED_TO: "'off'", ALARM_NOW: "'armed_away'"}, "the schedule only moves Night <-> Home"))
A(house("06:00 leaves Disarmed alone", "want", "none",
        {SCHED_TO: "'off'", ALARM_NOW: "'disarmed'"}, "the morning only ends a night"))
A(house("a schedule going unavailable does nothing", "want", "none",
        {SCHED_TO: "'unavailable'", ALARM_NOW: "'armed_home'"}, "a reload is not an edge"))
A(house("every Adaptive Lighting sleep switch is found, and only those", "sleep_switches",
        "['switch.adaptive_lighting_a_sleep_mode', 'switch.adaptive_lighting_b_sleep_mode']",
        {"states.switch": repr([{"entity_id": "switch.adaptive_lighting_a_sleep_mode"},
                                {"entity_id": "switch.adaptive_lighting_a_adapt_color"},
                                {"entity_id": "switch.adaptive_lighting_a"},
                                {"entity_id": "switch.adaptive_lighting_b_sleep_mode"},
                                {"entity_id": "switch.kitchen_sleep_mode"}])},
        "2026-10-11: a new Adaptive Lighting zone joins without an edit"))


# Welcome home (operator 2026-11-21): "make sure the alarm switches back automatically to home mode
# once we come back home". Decided with the operator: on ARRIVAL in the home zone (not on approach),
# by ANY tracked phone, to Night inside the night schedule and Home otherwise. Leaving Away also
# disarms the physical panel (alarm sync), so this is an automatic disarm: it acts only on a real
# arrival edge and only from Away.
WELCOME = "1792110000001"
W_FROM, W_TO = "trigger.from_state.state", "trigger.to_state.state"
W_NIGHT = "is_state('schedule.climate_night', 'on')"
W_MODE = "state_attr('alarm_control_panel.home', 'arm_mode')"
W_GONE = "(as_timestamp(now()) - as_timestamp(trigger.from_state.last_changed))"


def welcome(name, expect, frm="'not_home'", to="'home'", alarm="'armed_away'", night="false",
            mode="'armed_away'", gone="3600", finding=""):
    return dict(name="welcome home: " + name, automation=WELCOME, expr="want", expect=expect, given={},
                subs={W_FROM: frm, W_TO: to, ALARM_NOW: alarm, W_NIGHT: night, W_MODE: mode,
                      W_GONE: gone},
                finding=finding)


A(welcome("arriving by day switches Away to Home", "home", finding="2026-11-21 operator: back home = Home"))
A(welcome("arriving in the night window switches Away to Night", "night", night="true",
          finding="2026-11-21 operator: Night when scheduled, so climate and lights follow"))
A(welcome("arriving from another zone counts too", "home", frm="'work'",
          finding="a person's state is the zone name when not home"))
A(welcome("arriving during the exit delay of Away cancels it back to Home", "home", alarm="'arming'",
          finding="someone left and came straight back"))
A(welcome("an exit delay towards Home is left alone", "none", alarm="'arming'", mode="'armed_home'",
          finding="only Away is undone"))
A(welcome("Home is left alone", "none", alarm="'armed_home'", finding="nothing to undo"))
A(welcome("Night is left alone", "none", alarm="'armed_night'", night="true", finding="nothing to undo"))
A(welcome("Disarmed is left alone", "none", alarm="'disarmed'",
          finding="never ARM on arrival: disarmed is a choice"))
A(welcome("an alarm going off is never touched", "none", alarm="'triggered'",
          finding="arriving must not silence a real alarm"))
A(welcome("an entry delay is never touched", "none", alarm="'pending'",
          finding="the panel is counting down because a door opened: the keypad decides"))
A(welcome("an unavailable alarm is left alone", "none", alarm="'unavailable'",
          finding="no command into a reload"))
A(welcome("a restart restoring someone as home does nothing", "none", frm="'unknown'",
          finding="a person restored after a restart has not arrived; a phone left at home must not disarm"))
A(welcome("a person coming back from unavailable does nothing", "none", frm="'unavailable'",
          finding="a tracker reconnecting is not an arrival"))
A(welcome("someone already home re-reporting home does nothing", "none", frm="'home'",
          finding="attribute updates are not arrivals"))
A(welcome("leaving does nothing", "none", frm="'home'", to="'not_home'", finding="only arrivals"))
A(welcome("a phone away for a moment does not count as arriving", "none", gone="40",
          finding="review 2026-11-21 F4: a phone left at home that blips out of the zone and back must not disarm"))
A(welcome("away just under five minutes does not count", "none", gone="299",
          finding="review 2026-11-21 F4: the threshold is five minutes away"))
A(welcome("away just over five minutes counts", "home", gone="301",
          finding="review 2026-11-21 F4: a real trip of five minutes or more is an arrival"))
A(welcome("an unavailable night schedule means day", "home", night="false",
          finding="is_state is false for unavailable: Home, the safer daytime mode for climate"))


# ---------------------------------------------------------------- v6: radiators first (2026-10-11)
# Operator: "tado is now controlling the boiler ... for heating we should use it more ... at night I
# would prefer using TRVs where they exist instead of blowing air - more silent, and the windows
# aren't fogging".  Decided with the operator: HA sets the radiators from the same day/night
# targets; by DAY the radiator holds and the AC only boosts a room that is `boost` (1.5 C) behind,
# handing back near target; at NIGHT the AC heats a radiator room only for SAFETY.  Rooms without
# a radiator (`has_rad` false) are unchanged.  target 22, room_hyst 0.5, boost 1.5 throughout, so
# the day entry edge is 20.5 and the hand-back edge is 21.5 - every pair below straddles one.
RAD = dict(has_rad=True, house="heat", target=22.0)


def rad(given):
    g = dict(RAD); g.update(given); return g


# 2026-11-24 operator: no AC while the room's window is open. Tado already shuts the radiator; the
# AC did not know, and an aired room falls behind its target, which is exactly what calls the boost.
A(case("an open window stops the AC heating", "mode", "off", {"temp": 18.0, "window_open": True},
       finding="2026-11-24: the room below target is the airing, not a call for heat"))
A(case("the same room with the window shut heats", "mode", "heat", {"temp": 18.0, "window_open": False},
       finding="the case above crosses only the window"))
A(case("an open window stops the AC cooling", "mode", "off",
       {"house": "cool", "temp": 27.0, "target": 24.0, "window_open": True}, finding="cool air out of a window"))
A(case("an open window does not stop frost protection", "mode", "heat", {"temp": 6.0, "window_open": True},
       finding="safety before savings: a window left open in frost still gets heat"))
A(case("an open window does not override a person's hold", "mode", "manual",
       {"temp": 18.0, "window_open": True, "manual_active": True}, finding="a person at the remote wins"))
A(case("an open window outranks the air-filter toggle", "mode", "off",
       {"temp": 18.0, "window_open": True, "filter_on": True}, finding="filtering air out of a window is waste"))
A(case("the room's window is read from its detector", "window_open", "True", {},
       subs={"is_state(r.win, 'on')": "true", "r.win": "'binary_sensor.w'"}, finding="the window entity per room"))
A(case("a room without a window sensor never reads open", "window_open", "False", {},
       subs={"r.win": "''"}, finding="the office has none"))

# 2026-11-27 operator: someone sleeping in the office was woken at 06:00 by the AC blowing hot air in
# their face - the alarm left night mode, the office target went 19 -> 21, and the AC is its only heater.
# "Sleeping here" stops the AC for comfort in that room (heat, cool, warm-up, filter fan); safety stays.
A(case("someone sleeping: the AC does not heat at the morning edge", "mode", "off",
       {"temp": 20.0, "target": 21.0, "sleeping": True},
       finding="2026-11-27: hot air in the face at 06:00"))
A(case("the same room with nobody sleeping heats", "mode", "heat",
       {"temp": 20.0, "target": 21.0, "sleeping": False}, finding="the case above crosses only the toggle"))
A(case("someone sleeping: the AC does not cool either", "mode", "off",
       {"house": "cool", "temp": 27.0, "target": 24.0, "sleeping": True}, finding="operator: no air, hot or cold"))
A(case("the same room cooling with nobody sleeping cools", "mode", "cool",
       {"house": "cool", "temp": 27.0, "target": 24.0, "sleeping": False}, finding="review #71: twin of the cool case"))
A(case("the same warm-up with nobody sleeping heats", "mode", "heat",
       {"temp": 20.0, "target": 22.0, "night": True, "preheat": True, "has_rad": True, "sleeping": False},
       finding="review #71: twin of the warm-up case"))
A(case("the same filter fan with nobody sleeping runs", "mode", "fan_only",
       {"house": "shoulder", "filter_on": True, "sleeping": False}, finding="review #71: twin of the filter case"))
A(case("someone sleeping outranks the morning warm-up", "mode", "off",
       {"temp": 20.0, "target": 22.0, "night": True, "preheat": True, "has_rad": True, "sleeping": True},
       finding="the warm-up is exactly the 05:15 blast"))
A(case("someone sleeping outranks the air-filter fan", "mode", "off",
       {"house": "shoulder", "filter_on": True, "sleeping": True}, finding="the filter fan is air in the face too"))
A(case("someone sleeping does not stop the safety floor", "mode", "heat",
       {"temp": 17.0, "sleeping": True}, finding="a forgotten toggle must not let a room fall below 18"))
A(case("someone sleeping does not override a person at the remote", "mode", "manual",
       {"temp": 20.0, "manual_active": True, "sleeping": True}, finding="the sleeper turning it on wins"))
A(case("the room's sleeping toggle is read", "sleeping", "True", {},
       subs={"is_state(r.sleep, 'on')": "true"}, finding="per-room input_boolean"))
A(case("the room's sleeping toggle off reads awake", "sleeping", "False", {},
       subs={"is_state(r.sleep, 'on')": "false"}, finding="per-room input_boolean"))

A(case("radiator room at night: the AC does not heat for comfort", "mode", "off",
       rad({"night": True, "temp": 19.0}),
       finding="v6 operator: radiators only at night - silent, no fogged windows"))
A(case("radiator room at night: the AC still heats below the pet floor", "mode", "heat",
       rad({"night": True, "temp": 17.0}),
       finding="v6 operator: AC at night only for safety"))
A(case("radiator room at night: frost still heats", "mode", "heat",
       rad({"night": True, "temp": 5.0}), finding="v6: safety outranks the radiator rule"))
A(case("radiator room at night: an AC already heating is stood down", "mode", "off",
       rad({"night": True, "temp": 19.0, "now_mode": "heat"}),
       finding="v6: at 22:00 the AC hands over, it does not finish its run"))
A(case("radiator room by day: a small deficit is the radiator's job", "mode", "off",
       rad({"temp": 20.6}), finding="v6: 1.4 C behind is inside the boost band"))
A(case("radiator room by day: a large deficit brings the AC in", "mode", "heat",
       rad({"temp": 20.4}), finding="v6: 1.6 C behind - fast warm-up"))
A(case("radiator room by day: a boosting AC keeps going while well behind", "mode", "heat",
       rad({"temp": 21.4, "now_mode": "heat"}), finding="v6: hand back near target, not at the entry edge"))
A(case("radiator room by day: a boosting AC hands back near target", "mode", "off",
       rad({"temp": 21.6, "now_mode": "heat"}), finding="v6: the radiator finishes the last half degree"))
A(case("a room without a radiator still heats at night by AC", "mode", "heat",
       {"night": True, "temp": 21.0, "house": "heat"},
       finding="v6: the office has no valve yet - unchanged"))
A(case("a room without a radiator still heats on a small deficit by day", "mode", "heat",
       {"temp": 21.0, "house": "heat"}, finding="v6: unchanged for rooms without a valve"))
A(case("radiator room in cooling season cools as before", "mode", "cool",
       rad({"house": "cool", "temp": 24.0}), finding="v6 changes heating only"))
A(case("radiator room at night: the air filter toggle still runs the unit", "mode", "heat",
       rad({"night": True, "temp": 23.0, "filter_on": True}),
       finding="v6: an explicit operator toggle wins - recorded, not silently dropped"))

# The radiator automation (id 1790300000001): what each Tado zone should be set to, and whether
# that needs a command.  Tado's cloud quota is small on the free plan, so a command goes out only
# when the zone differs from what it should be - never on a schedule.
RADS = "1790300000001"
RBASE = dict(comfort=True, enabled=True, house="heat", away=False, night=False,
             day_t=22.0, night_t=20.0, away_min=18.0, last_cmd=0.0, hold_active=False,
             z_window=False)


def rcase(name, expr, expect, given, finding, subs=None):
    g = dict(RBASE); g.update(given)
    return dict(name=name, automation=RADS, expr=expr, expect=expect, given=g, subs=subs or {},
                finding=finding)


A(rcase("radiator: day target by day", "rad_target", "22.0", {}, "v6: one target per room for AC and radiator"))
A(rcase("radiator: night target at night", "rad_target", "20.0", {"night": True}, "v6"))
A(rcase("radiator: off in shoulder season", "rad_target", "off", {"house": "shoulder"},
        "v6: the house decides the season, for radiators too"))
A(rcase("radiator: off in cooling season", "rad_target", "off", {"house": "cool"},
        "v6: never heat against the AC cooling"))
A(rcase("radiator: away holds the pet floor", "rad_target", "18.0", {"away": True},
        "v6 operator: away = only frost and animal health; the boiler holds it cheaper than the AC"))
A(rcase("radiator: away holds the pet floor in shoulder season too", "rad_target", "18.0",
        {"away": True, "house": "shoulder"}, "v6: the floor is not seasonal"))
# A disabled room, or the master switch off, HANDS THE ZONE BACK to Tado's own schedule ('auto').
# 'off' would leave it on Tado's 5 C frost protection: two rooms were disabled when this was
# written, one of them a bedroom, in heating season.
A(rcase("radiator: a disabled room goes back to Tado's schedule", "rad_target", "auto",
        {"enabled": False}, "v6: disabled means hands off, never 'cold'"))
A(rcase("radiator: comfort off hands every zone back to Tado", "rad_target", "auto",
        {"comfort": False}, "v6: the master switch returns control, it does not switch heating off"))
A(rcase("radiator: comfort off wins over away", "rad_target", "auto",
        {"comfort": False, "away": True}, "v6: with the master off, HA does not hold any floor"))
A(rcase("radiator: a disabled room while away still holds the pet floor", "rad_target", "18.0",
        {"enabled": False, "away": True}, "v6 operator: away = frost and animal health, in every room"))

A(rcase("radiator: a zone on Tado's schedule is taken over", "rad_send", "True",
        {"want": "22.0", "z_state": "auto", "z_target": 18.0}, "v6: HA is the radiator boss"))
A(rcase("radiator: a zone already right is not commanded", "rad_send", "False",
        {"want": "22.0", "z_state": "heat", "z_target": 22.0},
        "v6: Tado's free quota - no redundant calls"))
A(rcase("radiator: a zone at the wrong temperature is corrected", "rad_send", "True",
        {"want": "20.0", "z_state": "heat", "z_target": 22.0}, "v6: the night edge"))
A(rcase("radiator: a zone that should be off is switched off", "rad_send", "True",
        {"want": "off", "z_state": "heat", "z_target": 22.0}, "v6: the season edge"))
A(rcase("radiator: a zone already off is left alone", "rad_send", "False",
        {"want": "off", "z_state": "off", "z_target": 0.0}, "v6: no redundant calls"))
A(rcase("radiator: a zone handed back is put on its schedule", "rad_send", "True",
        {"want": "auto", "z_state": "heat", "z_target": 22.0}, "v6: hand-back clears HA's overlay"))
A(rcase("radiator: a zone already on its schedule is left alone", "rad_send", "False",
        {"want": "auto", "z_state": "auto", "z_target": 18.0},
        "v6: never fight Tado's own schedule temperature"))
A(rcase("radiator: an unavailable zone is not commanded", "rad_send", "False",
        {"want": "22.0", "z_state": "unavailable", "z_target": 0.0},
        "v6: a cloud outage is not a reason to spend quota"))

# A valve can be overridden by hand, like the AC (operator, 2026-10-11): someone turns the dial or
# uses the Tado app.  Each zone remembers what HA last commanded (input_number.climate_rad_cmd_<room>:
# a temperature, -1 = off, -2 = Tado's schedule, 0 = never).  A zone that no longer matches it was
# changed by someone else: HA holds off for manual_hold, then reasserts.  After its OWN command HA
# also holds (settle, 30 min) before judging, because Tado is polled slowly on the free API tier and
# would otherwise report the old value and look like a person.
A(rcase("radiator: a dial turned by hand is noticed", "touched", "True",
        {"z_state": "heat", "z_target": 23.0, "last_cmd": 22.0},
        "2026-10-11 operator: valves get overridden by hand, like the AC"))
A(rcase("radiator: a zone switched off in the Tado app is noticed", "touched", "True",
        {"z_state": "off", "z_target": 0.0, "last_cmd": 22.0}, "2026-10-11: any change of ours counts"))
A(rcase("radiator: a zone put back on its schedule in the app is noticed", "touched", "True",
        {"z_state": "auto", "z_target": 18.0, "last_cmd": 22.0}, "2026-10-11"))
A(rcase("radiator: a zone still at our value is not an override", "touched", "False",
        {"z_state": "heat", "z_target": 22.0, "last_cmd": 22.0}, "no false accusation"))
A(rcase("radiator: a zone we never commanded is not an override", "touched", "False",
        {"z_state": "auto", "z_target": 18.0, "last_cmd": 0.0}, "the first takeover is ours to make"))
A(rcase("radiator: inside our settle window nothing is judged", "touched", "False",
        {"z_state": "heat", "z_target": 18.0, "last_cmd": 22.0, "hold_active": True},
        "Tado reports the OLD value until the next poll - that is not a person"))
A(rcase("radiator: an unavailable zone is not an override", "touched", "False",
        {"z_state": "unavailable", "z_target": 0.0, "last_cmd": 22.0}, "an outage is not a person"))
A(rcase("radiator: a turned dial is not reverted", "rad_send", "False",
        {"want": "22.0", "z_state": "heat", "z_target": 24.0, "last_cmd": 22.0},
        "2026-10-11: respect the hand on the valve"))
A(rcase("radiator: a live hold is respected", "rad_send", "False",
        {"want": "22.0", "z_state": "heat", "z_target": 24.0, "last_cmd": 24.0, "hold_active": True},
        "the hold, like the AC's"))
A(rcase("radiator: after the hold HA takes the zone back", "rad_send", "True",
        {"want": "22.0", "z_state": "heat", "z_target": 24.0, "last_cmd": 24.0},
        "the hold expires; the room returns to its target"))
A(rcase("radiator: an unknown season does nothing", "rad_target", "none", {"house": "unknown"},
        "a restart briefly blanks the house-mode helper; 'not heat' must not switch radiators off"))
A(rcase("radiator: 'none' is never sent", "rad_send", "False",
        {"want": "none", "z_state": "heat", "z_target": 22.0}, "no decision, no command"))


# ---------------------------------------------------------------- v6: morning warm-up (2026-10-11)
# Operator: "it's very pleasant to enter in the morning a room that has been also warmed by the AC
# ... some sort of pre-conditioning".  A room with input_boolean.climate_preheat_<room> on, in the
# last input_number.climate_preheat_minutes (45) before the night schedule's MORNING edge, aims at
# its DAY target and the AC may heat it even with a radiator, without the boost threshold.  Only a
# night that the schedule is running counts - a manual afternoon "night" has no morning edge.
A(case("warm-up: a radiator room is heated by the AC before the morning edge", "mode", "heat",
       rad({"night": True, "preheat": True, "temp": 20.0}),
       finding="2026-10-11 operator: walk into a warm room in the morning"))
A(case("warm-up: the AC runs on to the day target, not just the boost band", "mode", "heat",
       rad({"night": True, "preheat": True, "temp": 21.8, "now_mode": "heat"}),
       finding="warm-up means arriving at the day target"))
A(case("warm-up: a room already at the day target is left alone", "mode", "off",
       rad({"night": True, "preheat": True, "temp": 22.2}), finding="no warm-up for a warm room"))
A(case("warm-up: the night target gives way to the day target in the window", "target", "22.0",
       {"night": True, "preheat": True},
       subs={"states(r.night_t)": "'20'", "states(r.day_t)": "'22'"},
       finding="the warm-up aims at the day temperature"))
A(case("warm-up: outside the window the night target stands", "target", "20.0",
       {"night": True, "preheat": False},
       subs={"states(r.night_t)": "'20'", "states(r.day_t)": "'22'"}, finding="v4 night target unchanged"))

# Review #55 F2: the night target is now a template sensor. It renders None only when the operator's
# own input_number is missing, so the consumers' fallbacks are the same as before: pinned here.
A(case("an unknown night target falls back to 21 C in the AC loop", "target", "21",
       {"night": True, "preheat": False},
       subs={"states(r.night_t)": "'unknown'", "states(r.day_t)": "'22'"}, finding="review #55 F2"))
A(rcase("an unknown night target falls back to 19 C for a radiator", "night_t", "19", {},
        "review #55 F2", subs={"states(r.night_t)": "'unknown'"}))

PH_ON = "is_state(r.preheat, 'on')"
SCHED_IS_ON = "is_state('schedule.climate_night','on')"
NEXT = "state_attr('schedule.climate_night','next_event')"
NOWTS = "now().timestamp()"


def ph(name, expect, given, subs, finding):
    g = {"house": "heat", "night": True, "preheat_min": 45.0}; g.update(given)
    base = {PH_ON: "true", SCHED_IS_ON: "true", NEXT: "'2026-09-21T14:43:20+00:00'", NOWTS: "1790000000.0"}
    base.update(subs)
    return case(name, "preheat", expect, g, base, finding=finding)


A(ph("warm-up: 30 min before the edge with a 45 min lead is in the window", "True", {}, {},
     "2026-10-11 operator"))
A(ph("warm-up: 50 min before the edge is not yet", "False", {}, {NEXT: "'2026-09-21T15:03:20+00:00'"},
     "the lead time is the window"))
A(ph("warm-up: a room with the toggle off is not warmed", "False", {}, {PH_ON: "false"},
     "per room, opt-in"))
A(ph("warm-up: a manual day already ended the night", "False", {"night": False}, {},
     "night is the alarm; by day there is nothing to pre-condition"))
A(ph("warm-up: a manual night outside the schedule has no morning edge", "False", {},
     {SCHED_IS_ON: "false"}, "the schedule's next event is then its EVENING edge"))
A(ph("warm-up: only in heating season", "False", {"house": "shoulder"}, {},
     "pre-conditioning is heating; cooling is not asked for"))
A(ph("warm-up: a passed edge is not a window", "False", {}, {NEXT: "'2026-09-21T14:12:20+00:00'"},
     "a stale next_event must not warm all night"))
A(ph("warm-up: an unknown next event does nothing", "False", {}, {NEXT: "none"},
     "a schedule without a next event is no window"))
# 2026-10-31, observed: the schedule stores a night as one block per weekday (21:00-24:00, then
# 00:00-06:00), so before midnight next_event is 00:00 local. The state stays 'on' across it - it
# is no edge - but the warm-up read it as the morning one and heated the living room to its DAY
# target from 23:15. Times are Europe/Prague (UTC+1 in winter); the window is 30 min in both.
A(ph("warm-up: midnight inside the night is not the morning edge", "False", {},
     {NEXT: "'2026-11-01T00:00:00+01:00'", NOWTS: "1793485800.0"},
     "2026-10-31 observed: living room heated to the day target from 23:15"))
A(ph("warm-up: the real morning edge after midnight still warms", "True", {},
     {NEXT: "'2026-11-01T06:00:00+01:00'", NOWTS: "1793507400.0"},
     "the midnight rule must not cost the 05:15 warm-up"))

# Review 2026-10-11 (v6): Tado's OWN open-window detection switches a zone off by itself.  Without
# this, HA called that "changed by hand", held the zone 2 h and pushed a false notification - and
# fought the valve when the window closed.  While the zone's window sensor is on, HA neither judges
# nor commands it.
A(rcase("radiator: an open window switching the zone off is not a person", "touched", "False",
        {"z_state": "off", "z_target": 0.0, "last_cmd": 22.0, "z_window": True},
        "review 2026-10-11: no false accusation from Tado's window detection"))
A(rcase("radiator: a zone with its window open is not commanded", "rad_send", "False",
        {"want": "22.0", "z_state": "off", "z_target": 0.0, "last_cmd": 22.0, "z_window": True},
        "review 2026-10-11: never fight the valve's window protection"))
A(rcase("radiator: once the window closes, a real change is noticed again", "touched", "True",
        {"z_state": "heat", "z_target": 25.0, "last_cmd": 22.0, "z_window": False},
        "the window rule pauses judgement, it does not disable it"))


# ---------------------------------------------------------------- v6: a radiator only counts while it can heat
# Operator, 2026-10-11: "if there is no TRV valve in a given room, heat it with air - even at night as
# a fallback, otherwise we'll freeze".  A valve that is offline, out of battery or switched off is no
# valve: the AC heats as if the room had none.  The one exception is Tado's own open-window shut-off -
# hot air into an open window helps nobody, and the safety band still covers the room.
RAD_E = "states(rad_entity)"
RAD_W = "is_state(rad_window, 'on')"


def hr(name, expect, given, subs, finding):
    g = {"rad_entity": "climate.room_trv", "rad_window": "binary_sensor.room_trv_window"}
    g.update(given)
    return case(name, "has_rad", expect, g, subs, finding=finding)


A(hr("a valve that is heating counts", "True", {}, {RAD_E: "'heat'", RAD_W: "false"}, "v6"))
A(hr("a valve on its own schedule counts", "True", {}, {RAD_E: "'auto'", RAD_W: "false"}, "v6"))
A(hr("an offline valve does not count - the AC heats", "False", {},
     {RAD_E: "'unavailable'", RAD_W: "false"},
     "2026-10-11 operator: otherwise we'll freeze"))
A(hr("a valve switched off does not count - the AC heats", "False", {},
     {RAD_E: "'off'", RAD_W: "false"}, "2026-10-11 operator: no working radiator, heat with air"))
A(hr("a valve shut by Tado's open-window detection still counts", "True", {},
     {RAD_E: "'off'", RAD_W: "true"}, "no hot air into an open window"))
A(hr("a room with no valve has no radiator", "False", {"rad_entity": "", "rad_window": ""},
     {RAD_E: "'unknown'", RAD_W: "false"}, "v6: the office"))


# ---------------------------------------------------------------- alarm sync: Alarmo <-> EVO192 (2026-10-13)
# Operator, 2026-10-13: one automation keeps the virtual alarm (Alarmo, alarm_control_panel.home)
# and the physical Paradox EVO192 (via PAI) in step, both ways. Mapping: Home = Stay, Night = the
# EVO's instant arm (it has no sleep arm), Away = Away. If the panel will not arm, Alarmo does not
# either, and both adults are told WHY. A leak that triggers Alarmo triggers the panel too.
# The physical panel is the truth after a restart and whenever the two disagree after a failure.
SYNC = "1790400000001"
EVO_NOW = "states('alarm_control_panel.evo192_partition_paradox_alarm')"
PAI_NOW = "states('sensor.evo192_pai_status')"
BS = "states.binary_sensor"


def sync(name, expr, expect, given, finding, subs=None):
    return dict(name="alarm sync: " + name, automation=SYNC, expr=expr, expect=expect,
                given=given, subs=subs or {}, finding=finding)


def plan(name, expect, src, a_now, e_now, prev="armed_home", a_next=None, finding=""):
    g = dict(src=src, a_now=a_now, e_now=e_now, prev=prev, a_next=a_next or a_now)
    g["want"] = g["a_next"] if a_now == "arming" else a_now
    return sync(name, "plan", expect, g, finding)


OP = "2026-10-13 operator: one automation syncs both ways"
# Operator, 2026-10-15, after the first live run: Stay on the panel went off seconds after arming,
# so until the panel's Stay zones are set up the sync carries Away only. Home and Night ask nothing
# of the panel except that it is not in Away; a panel disarmed or in a keypad Stay satisfies them.
# An explicit Disarm on Alarmo still disarms the panel.
AWAY_ONLY = "2026-10-15 operator: sync only Away; everything else is disarm (Stay went off on arming)"
# Alarmo moved (the HA interface, the night schedule, a leak).
A(plan("Home on Alarmo leaves a disarmed panel alone", "none", "alarmo", "armed_home", "disarmed",
       prev="disarmed", finding=AWAY_ONLY))
A(plan("Away with an exit delay arms the panel at once", "arm_panel", "alarmo", "arming",
       "armed_home", a_next="armed_away", finding="the panel runs its own exit delay"))
A(plan("the panel's own echo is not sent back", "none", "alarmo", "armed_night", "armed_night",
       finding="no command when the panel is already there - the loop breaker"))
A(plan("a panel still in its exit delay is not re-commanded", "none", "alarmo", "armed_away",
       "arming", prev="arming", finding="Alarmo's 60 s exit delay ends while the panel's runs on"))
A(plan("disarming during the panel's exit delay cancels it", "disarm_panel", "alarmo", "disarmed",
       "arming", prev="arming", finding="'arming' is in progress, not done"))
A(plan("an offline panel fails the arm", "fail", "alarmo", "armed_away", "unavailable",
       prev="disarmed", finding="2026-10-13 operator: if EVO fails to arm, Alarmo fails too"))
A(plan("a leak on Alarmo triggers the panel", "panic", "alarmo", "triggered", "disarmed",
       prev="disarmed", finding="2026-10-13 operator: leaks trigger both alarms"))
A(plan("Alarmo ending its own alarm does not re-arm the panel", "none", "alarmo", "armed_home",
       "triggered", prev="triggered",
       finding="the panel's bell has its own timer; a re-arm command mid-alarm is undefined"))
A(plan("disarming a triggered Alarmo silences the panel", "disarm_panel", "alarmo", "disarmed",
       "triggered", prev="triggered", finding="either side's disarm ends the alarm"))
A(plan("Alarmo's entry delay is not a command", "none", "alarmo", "pending", "armed_away",
       prev="armed_away", finding="only settled states are mirrored"))
# The panel moved (the keypad, or the panel itself).
A(plan("Away on the keypad arms Alarmo away", "arm_alarmo", "evo", "armed_home", "armed_away",
       finding="2026-10-13 operator: leaving = arm EVO away, the house follows"))
# 2026-11-14 live: a keypad disarm (20:30:07.8) was followed 0.6 s later by PAI reporting the panel
# armed_away for 10 s, straight from disarmed. The sync armed Alarmo Away, Away switched every light
# off, and the house came home dark. A real arm always passes through the panel's exit delay
# ('arming'), so an arm reported straight from 'disarmed' is not followed. No timer: the operator
# asked for no waits. Cost: if PAI ever drops the 'arming' report of a real arm, the house stays in
# its mode while the panel guards - the panel still protects, nothing goes dark.
BLIP = "2026-11-14 live: PAI reported Away for 10 s right after a keypad disarm; the house went dark"
# Review 2026-11-14 F2: the ignored arm is written to the logbook ('blip'), so a real arm that PAI
# reported without its exit delay is visible, not silently dropped. F3: a panel coming back from
# unavailable already armed is still followed - the panel is the truth after a reconnect.
A(plan("a panel arm straight from disarmed is a blip, not followed", "blip", "evo", "disarmed",
       "armed_away", prev="disarmed", finding=BLIP))
A(plan("a Stay blip straight from disarmed is not followed either", "blip", "evo", "disarmed",
       "armed_home", prev="disarmed", finding=BLIP + "; review F: the guard covers every mode"))
A(plan("a Night blip straight from disarmed is not followed either", "blip", "evo", "disarmed",
       "armed_night", prev="disarmed", finding=BLIP + "; review F: the guard covers every mode"))
A(plan("a panel back from offline already in Away is followed", "arm_alarmo", "evo", "disarmed",
       "armed_away", prev="unavailable", finding="review 2026-11-14 F3: accepted, the panel is the truth"))
A(plan("a keypad Away after its exit delay arms Alarmo away", "arm_alarmo", "evo", "disarmed",
       "armed_away", prev="arming", finding=BLIP + " - the real arm still follows"))
A(plan("a keypad disarm leaves a Night house alone", "none", "evo", "armed_night", "disarmed",
       finding=AWAY_ONLY))
A(plan("a keypad disarm after Away disarms Alarmo", "disarm_alarmo", "evo", "armed_away", "disarmed",
       finding=OP))
A(plan("the panel going off triggers Alarmo", "trigger_alarmo", "evo", "armed_home", "triggered",
       finding=OP))
A(plan("the panel re-arming after its bell does not cut a leak alarm", "none", "evo",
       "triggered", "armed_home", finding="Alarmo's alarm ends by disarm or its own timer"))
A(plan("the panel's exit delay is not mirrored", "none", "evo", "armed_home", "arming",
       finding="wait for the settled state"))
A(plan("an offline panel changes nothing", "none", "evo", "armed_night", "unavailable",
       finding="PAI dropping off must not disarm the house"))
A(plan("after a restart Alarmo follows a panel in Away", "arm_alarmo", "start", "armed_home",
       "armed_away", prev="none", finding="the physical panel is the truth"))
A(plan("Alarmo arming toward the panel's state is left alone", "none", "evo", "arming",
       "armed_away", a_next="armed_away", finding="no re-arm that would restart Alarmo's delay"))

A(sync("what Alarmo is arming toward is what it wants", "want", "armed_away",
       dict(a_now="arming", a_next="armed_away"), "Alarmo's state is 'arming' during an exit delay"))
A(sync("Night is disarm on the panel", "panel_cmd", "disarm", dict(want="armed_night"), AWAY_ONLY))
A(sync("Home is disarm on the panel", "panel_cmd", "disarm", dict(want="armed_home"), AWAY_ONLY))
A(sync("Away is a full arm", "panel_cmd", "arm", dict(want="armed_away"), OP))
A(sync("Disarm is disarm", "panel_cmd", "disarm", dict(want="disarmed"), OP))
A(sync("a keypad Night arms Alarmo night", "follow_mode", "night", dict(e_now="armed_night"), OP))


def _z(eid, state, name):
    return {"entity_id": eid, "state": state, "name": name}


ZONES_OK = [_z("binary_sensor.evo192_zone_bedroom_open", "off", "EVO192 Zone Bedroom Open")]
TAMPER = _z("binary_sensor.evo192_zone_tamper_open", "on", "EVO192 Zone Tamper Open")
READY = "is_state('binary_sensor.corridor_evo192_partition_paradox_alarm_ready', 'on')"
STAY_READY = "is_state('binary_sensor.corridor_evo192_partition_paradox_alarm_stay_instant_ready', 'on')"


def why(name, expect, want, finding, evo="'disarmed'", pai="'online'", ready="true",
        stay_ready="true", sensors=()):
    return sync(name, "why", expect, dict(want=want), finding,
                subs={EVO_NOW: evo, PAI_NOW: pai, READY: ready, STAY_READY: stay_ready,
                      BS: repr(ZONES_OK + list(sensors))})


A(why("WHY names the open zones when the panel is not ready", "the panel is not ready to arm - "
      "open zones: Tamper, Entrance Door", "armed_away",
      "2026-10-13 operator: a notification WHY it failed", ready="false",
      sensors=[TAMPER, _z("binary_sensor.evo192_zone_tamper_tamper", "on", "EVO192 Zone Tamper Tamper"),
               _z("binary_sensor.evo192_zone_entrance_door_open", "on",
                  "EVO192 Zone Entrance Door Open")]))
A(why("Stay and Night read the stay readiness, not the full one", "the panel is not ready to arm - "
      "open zones: Tamper", "armed_night", "EVO: stay/instant can arm with interior zones open",
      ready="true", stay_ready="false", sensors=[TAMPER]))
A(why("an open zone the panel ignores is not blamed", "the panel did not confirm in time - "
      "check the keypad", "armed_home",
      "2026-10-13: the Tamper zone reads open yet the panel is ready", sensors=[TAMPER]))
A(why("WHY adds panel troubles, not the summary flag", "the panel reports: Battery Failure Trouble",
      "armed_home", "the generic 'System Trouble' only repeats the specific one",
      sensors=[_z("binary_sensor.evo192_system_troubles_system_trouble", "on",
                  "EVO192 System troubles System Trouble"),
               _z("binary_sensor.evo192_system_troubles_battery_failure_trouble", "on",
                  "EVO192 System troubles Battery Failure Trouble")]))
A(why("WHY says the panel is offline", "the panel is offline (PAI offline)", "armed_home",
      "PAI or the HW-622 bridge down", evo="'unavailable'", pai="'offline'"))

A(sync("a failed arm leaves Alarmo where the panel is", "revert_to", "armed_home",
       dict(prev="disarmed"), "2026-10-13 operator: Alarmo fails to arm as well",
       subs={EVO_NOW: "'armed_home'"}))
A(sync("with the panel offline Alarmo goes back where it was", "revert_to", "disarmed",
       dict(prev="disarmed"), "no panel state to follow", subs={EVO_NOW: "'unavailable'"}))
A(sync("a triggered panel is not copied as a revert target", "revert_to", "armed_home",
       dict(prev="armed_home"), "revert restores a mode, it never sets off an alarm",
       subs={EVO_NOW: "'triggered'"}))

# The "disarm, then arm" fallback, for a panel that will not move between armed modes. It opens a
# window with the physical alarm off, so it runs only when the panel says it COULD take the target.
WAIT_DONE = "wait.completed"


def retry(name, expect, want, finding, done="false", e="'armed_home'", ready="true", stay="true"):
    return sync(name, "may_retry", expect, dict(want=want, e_before="armed_home"), finding,
                subs={WAIT_DONE: done, EVO_NOW: e, READY: ready, STAY_READY: stay})


A(retry("a panel stuck in Stay is retried via disarm when ready for Away", "True", "armed_away",
        "the EVO may refuse a direct Stay -> Away change"))
A(retry("no disarm window when the panel is not ready for Away", "False", "armed_away",
        "review 2026-10-13: an open interior zone makes the retry a pointless disarm",
        ready="false"))
A(retry("Night retry reads the stay readiness", "False", "armed_night",
        "instant arm uses the stay set of zones", ready="true", stay="false"))
A(retry("no retry once the panel has moved", "False", "armed_away",
        "it accepted the command", done="true", e="'arming'"))
A(retry("no retry when the panel left the old mode some other way", "False", "armed_away",
        "someone disarmed at the keypad meanwhile", e="'disarmed'"))

# Review 2026-10-13 (companion): F2 - a disarm asked for while the panel is offline must not be
# undone; the house honours it and the adults are told to use the keypad. F7 - a restart with PAI
# still reconnecting must not touch Alarmo.
A(plan("a disarm with the panel offline is honoured", "disarm_offline", "alarmo", "disarmed",
       "unavailable", prev="armed_away",
       finding="review 2026-10-13 F2: never re-arm the house against an explicit disarm"))
A(plan("Night with the panel offline changes nothing", "none", "alarmo", "armed_night", "unknown",
       prev="armed_home", finding=AWAY_ONLY + " - the 22:00 edge must not fail the house"))
A(plan("Away with the panel offline still fails", "fail", "alarmo", "armed_away", "unknown",
       prev="armed_home", finding="2026-10-13 operator: if EVO fails to arm, Alarmo fails too"))
A(plan("a restart with PAI not back yet changes nothing", "none", "start", "armed_night",
       "unavailable", prev="none",
       finding="review 2026-10-13 F7 (disproved, locked): start never disarms on a slow PAI"))


# Operator, 2026-10-13 (later): Home and Night both mean Stay on the panel. Night is a house mode
# (climate, lights) layered on a panel that does not change, so Stay must SATISFY Night in both
# directions, or the sync would flip the house back to day every evening.
NIGHT = "2026-10-13 operator: night = Stay on the EVO"
A(plan("22:00 Night does not touch a panel already in Stay", "none", "alarmo", "armed_night",
       "armed_home", prev="armed_home", finding=NIGHT))
A(plan("a panel in Stay does not pull a Night house back to Home", "none", "evo", "armed_night",
       "armed_home", finding=NIGHT + " - the echo that would undo night every evening"))
A(plan("Night over a disarmed panel leaves it disarmed", "none", "alarmo", "armed_night",
       "disarmed", prev="armed_home", finding=AWAY_ONLY))
A(plan("Stay on the keypad from Disarmed is Home", "arm_alarmo", "evo", "disarmed", "armed_home",
       finding="Stay alone does not mean night"))
A(plan("06:00 Home over a panel in Stay is a no-op", "none", "alarmo", "armed_home", "armed_home",
       prev="armed_night", finding=NIGHT))
A(sync("Night is satisfied by any panel state but Away", "ok_states",
       "['disarmed', 'armed_home', 'armed_night']", dict(want="armed_night"), AWAY_ONLY))
A(sync("Home is satisfied by any panel state but Away", "ok_states",
       "['disarmed', 'armed_home', 'armed_night']", dict(want="armed_home"), AWAY_ONLY))
A(sync("Disarm is satisfied by a disarmed panel only", "ok_states", "['disarmed']",
       dict(want="disarmed"), "an explicit disarm disarms a keypad Stay too"))
# 2026-10-15: leaving Away is the only time Home or Night commands the panel.
A(plan("Home from Away disarms the panel", "disarm_panel", "alarmo", "armed_home", "armed_away",
       prev="armed_away", finding=AWAY_ONLY))
A(plan("Night from Away disarms the panel", "disarm_panel", "alarmo", "armed_night", "armed_away",
       prev="armed_away", finding=AWAY_ONLY))
A(plan("Home after Away with the panel offline tells the adults", "disarm_offline", "alarmo",
       "armed_home", "unavailable", prev="armed_away",
       finding=AWAY_ONLY + " - an armed panel nobody could disarm is waiting at the door"))
A(plan("Night after Away with the panel offline tells the adults", "disarm_offline", "alarmo",
       "armed_night", "unavailable", prev="armed_away",
       finding=AWAY_ONLY + " - review 2026-10-15: the Night side of the same exit"))
A(plan("Home after Night with the panel offline is silent", "none", "alarmo", "armed_home",
       "unavailable", prev="armed_night", finding="the 06:00 edge asks nothing of the panel"))
A(plan("an explicit Disarm still disarms a keypad Stay", "disarm_panel", "alarmo", "disarmed",
       "armed_home", prev="armed_home", finding=AWAY_ONLY))
A(plan("Away arms the panel", "arm_panel", "alarmo", "armed_away", "disarmed", prev="armed_home",
       finding=AWAY_ONLY))
A(plan("a keypad Stay under an Away house brings it Home", "arm_alarmo", "evo", "armed_away",
       "armed_home", finding="someone is in, and armed Stay at the keypad"))
A(sync("Away is satisfied by Away only", "ok_states", "['armed_away']", dict(want="armed_away"),
       "Stay is not Away"))


# ---------------------------------------------------------------- away: the house goes quiet (2026-10-14)
# Operator, 2026-10-13: "when we leave we arm EVO192 away, which should turn the automations off".
# 2026-10-14: lights and media off, presence lighting paused, one note of what is still open.
# Climate is NOT here: the climate loop already drops to its away band after 30 min of Away.
# Presence lighting is paused by turning each room's Magic Areas `light_control` switch off, and
# ONLY the ones that were on - a room the operator switched off by hand stays off on return. The
# list is kept in `input_text.house_away_paused`, so a restart while away loses nothing. The
# corridor stays live: it is the way in, and the keypad is there.
AWAY = "1790500000001"
LC = "switch.magic_areas_light_groups_%s_light_control"
PAUSED = "states('input_text.house_away_paused')"
TRIG = "trigger.id"
AW = "2026-10-14 operator: Away turns the house's automations off"


def away(name, expr, expect, given=None, subs=None, finding=AW):
    return dict(name="away: " + name, automation=AWAY, expr=expr, expect=expect,
                given=given or {}, subs=subs or {}, finding=finding)


def _sw(*pairs):
    return {"states.switch": repr([{"entity_id": e, "state": s} for e, s in pairs])}


A(away("only the rooms whose presence lighting is on are paused", "ma_on", "['closet', 'hallway']",
       subs=_sw((LC % "closet", "on"), (LC % "kitchen", "off"), (LC % "hallway", "on"),
                ("switch.kitchen_socket", "on"))))
A(away("the corridor stays live - it is the way in to the keypad", "ma_on", "['closet']",
       subs=_sw((LC % "corridor", "on"), (LC % "closet", "on")),
       finding=AW + "; entering a dark house to find the keypad is the failure"))
A(away("an unavailable switch is not paused", "ma_on", "[]",
       subs=_sw((LC % "closet", "unavailable"))))
A(away("the stored list survives as a list", "stored", "['closet', 'hallway']",
       subs={PAUSED: "'closet,hallway'"}, finding="a restart while away must lose nothing"))
A(away("a fresh helper stores nothing", "stored", "[]", subs={PAUSED: "''"},
       finding="a new input_text starts empty"))
A(away("an unavailable helper stores nothing", "stored", "[]", subs={PAUSED: "'unavailable'"},
       finding="never restore a room called 'unavailable'"))
A(away("Away again after a trigger keeps what was paused the first time", "paused",
       "['closet', 'hallway']", given=dict(stored=["closet", "hallway"], ma_on=[]),
       finding="armed_away -> triggered -> armed_away: the second pass sees everything off"))
A(away("a room paused twice is listed once", "paused", "['closet', 'hallway']",
       given=dict(stored=["closet"], ma_on=["closet", "hallway"])))
TRIG_FROM = "trigger.from_state.state"
A(away("Away pauses", "act", "pause", given=dict(stored=[]),
       subs={TRIG: "'away'", TRIG_FROM: "'arming'", ALARM: "'armed_away'"}))
A(away("Away straight from Home pauses", "act", "pause", given=dict(stored=[]),
       subs={TRIG: "'away'", TRIG_FROM: "'armed_home'", ALARM: "'armed_away'"}))
A(away("a leak alarm ending back in Away does not pause again", "act", "none",
       given=dict(stored=["closet"]), subs={TRIG: "'away'", TRIG_FROM: "'triggered'",
                                            ALARM: "'armed_away'"},
       finding="review 2026-10-14 M1: triggered -> armed_away re-ran the sequence and re-sent the note"))
A(away("an entry delay ending back in Away does not pause again", "act", "none",
       given=dict(stored=["closet"]), subs={TRIG: "'away'", TRIG_FROM: "'pending'",
                                            ALARM: "'armed_away'"},
       finding="review 2026-10-14 M1"))
A(away("coming home restores", "act", "restore", given=dict(stored=["closet"]),
       subs={TRIG: "'back'", ALARM: "'disarmed'"}))
A(away("Night straight from Away restores", "act", "restore", given=dict(stored=["closet"]),
       subs={TRIG: "'back'", ALARM: "'armed_night'"}, finding="the 22:00 edge never fires from Away, "
       "but a manual Night does"))
A(away("nothing paused, nothing to restore", "act", "none", given=dict(stored=[]),
       subs={TRIG: "'back'", ALARM: "'disarmed'"}))
A(away("a restart while still Away restores nothing", "act", "none",
       given=dict(stored=["closet"]), subs={TRIG: "'start'", ALARM: "'armed_away'"},
       finding="the house is still empty"))
A(away("a restart after a disarm that HA missed restores", "act", "restore",
       given=dict(stored=["closet"]), subs={TRIG: "'start'", ALARM: "'armed_home'"},
       finding="the keypad disarm happened while HA was down"))
A(away("a restart with the alarm not back yet restores nothing", "act", "none",
       given=dict(stored=["closet"]), subs={TRIG: "'start'", ALARM: "'unavailable'"},
       finding="unknown is not evidence anybody came home"))
A(away("only switches that still exist are restored", "restore", "['%s']" % (LC % "closet"),
       given=dict(stored=["closet", "old_room"]), subs=_sw((LC % "closet", "off"))))
A(away("the note names what is open", "open_now", "['Bedroom window']",
       subs={ALL_BS: _house(dict(_bs("binary_sensor.bw", "on", "window"), attributes={
           "device_class": "window", "friendly_name": "Bedroom window"}),
           _bs("binary_sensor.door", "off", "door"),
           _bs("binary_sensor.pir", "on", "motion"),
           _bs("binary_sensor.gone", "unavailable", "window"))}))


# ---------------------------------------------------------------- sleeping: presence lighting (2026-11-27)
# Operator: "the lights might turn on as well while people are sleeping". A room's "Sleeping here"
# pauses its Magic Areas light_control; clearing it un-pauses only what this automation paused. During
# Away the room is handed to Away's list instead, so it comes back with the house, not while it is empty.
SLEEPL = "1792400000011"
SL_PAUSED = "states('input_text.sleeping_paused')"
SLF = "2026-11-27 operator: presence lighting must not wake a sleeper"


def sl(name, expr, expect, given=None, subs=None, finding=SLF):
    return dict(name="sleeping lights: " + name, automation=SLEEPL, expr=expr, expect=expect,
                given=given or {}, subs=subs or {}, finding=finding)


# Review #71: the noon clear re-runs the climate loop, so a guest still asleep at 12:00 got the blast.
# Now a toggle clears from 12:00 to 20:00 once its room is EMPTY; an occupied room waits until it empties.
NOON = "1792400000010"


def noon(name, expect, given, finding="review #71: never wake a sleeper at noon"):
    return dict(name="sleeping clear: " + name, automation=NOON, expr="clear", expect=expect,
                given=given, subs={}, finding=finding)


A(noon("an empty room clears at noon", "['input_boolean.sleeping_office']",
       dict(window_ok=True, rooms=[["input_boolean.sleeping_office", False]])))
A(noon("a room still occupied at noon keeps its toggle", "[]",
       dict(window_ok=True, rooms=[["input_boolean.sleeping_office", True]]),
       finding="review #71: the guest asleep past noon"))
A(noon("only the empty one of two rooms clears", "['input_boolean.sleeping_bedroom']",
       dict(window_ok=True, rooms=[["input_boolean.sleeping_office", True], ["input_boolean.sleeping_bedroom", False]])))
A(noon("an empty room before noon keeps its toggle", "[]",
       dict(window_ok=False, rooms=[["input_boolean.sleeping_office", False]]),
       finding="a sleeper lying still can read empty at night"))
A(dict(name="sleeping clear: 12:00 opens the window", automation=NOON, expr="window_ok", expect="True",
               given={}, subs={"now().hour": "12"}, finding="review #71"))
A(dict(name="sleeping clear: 11:00 is before the window", automation=NOON, expr="window_ok", expect="False",
       given={}, subs={"now().hour": "11"}, finding="review #71"))
A(dict(name="sleeping clear: 20:00 closes the window", automation=NOON, expr="window_ok", expect="False",
       given={}, subs={"now().hour": "20"}, finding="review #71: the evening toggle must survive an empty-looking room"))
A(dict(name="sleeping clear: 19:00 is inside the window", automation=NOON, expr="window_ok", expect="True",
       given={}, subs={"now().hour": "19"}, finding="review #71"))


A(sl("a sleeping room with live presence lighting is paused", "pause", "['guest_room']",
     given=dict(rooms=[["guest_room", "on", True], ["living_room", "on", False]])))
A(sl("an awake room is not paused", "pause", "[]",
     given=dict(rooms=[["guest_room", "on", False]]), finding="the case above crosses only the toggle"))
A(sl("a room whose presence lighting is off by choice is left alone", "pause", "[]",
     given=dict(rooms=[["bedroom", "off", True]]),
     finding="the operator switched the bedroom's off; we must never later switch it ON"))
A(sl("a woken room this automation paused is released", "release", "['guest_room']",
     given=dict(stored=["guest_room"], rooms=[["guest_room", "off", False]])))
A(sl("a room still asleep is not released", "release", "[]",
     given=dict(stored=["guest_room"], rooms=[["guest_room", "off", True]])))
A(sl("a room that lost its toggle is released, not held for ever", "release", "['old_room']",
     given=dict(stored=["old_room"], rooms=[]), finding="a deleted toggle must not leave a room dark"))
A(sl("only what was paused here is remembered", "keep", "['guest_room']",
     given=dict(stored=["living_room"], release=["living_room"], pause=["guest_room"])))
A(sl("a room still asleep stays remembered when nothing new is paused", "keep", "['guest_room']",
     given=dict(stored=["guest_room"], release=[], pause=[]),
     finding="the next run (another room's toggle) must not forget it, or noon never restores it"))
A(sl("a room paused twice is remembered once", "keep", "['guest_room']",
     given=dict(stored=["guest_room"], release=[], pause=["guest_room"])))
A(sl("the stored list survives a restart", "stored", "['guest_room', 'closet']",
     subs={SL_PAUSED: "'guest_room,closet'"}))
A(sl("a fresh helper stores nothing", "stored", "[]", subs={SL_PAUSED: "''"}))
A(sl("an unavailable helper stores nothing", "stored", "[]", subs={SL_PAUSED: "'unavailable'"},
     finding="never release a room called 'unavailable'"))
A(sl("woken during Away: handed to Away, not switched on", "handoff", "['closet', 'guest_room']",
     given=dict(away_now=True, release=["guest_room"]), subs={PAUSED: "'closet'"},
     finding="the noon clear while the house is empty must not re-arm presence lighting"))
A(sl("woken at home: nothing handed to Away", "handoff", "[]",
     given=dict(away_now=False, release=["guest_room"]), subs={PAUSED: "'closet'"},
     finding="the case above crosses only Away"))
A(sl("Away is the alarm's armed_away", "away_now", "True", subs={ALARM: "'armed_away'"}))
A(sl("Night is not Away", "away_now", "False", subs={ALARM: "'armed_night'"}))


# ---------------------------------------------------------------- everyone left: arm Away? (2026-10-14)
# The "lights left on" notice already fired ten minutes after the house emptied. It now also offers
# to arm Away, as ONE notification (two at the same moment would be noise). Nothing arms by itself:
# the button does it, and only if the house is still empty when it is pressed.
LEFT_AUTO = "1791800830017"
ZONE = "states('zone.home')"
LEFT_NOW = "states('sensor.lighting_left_on')"
EL = "2026-10-14 operator: when the last person leaves, offer to arm Away"


def left(name, expr, expect, given=None, subs=None, finding=EL):
    return dict(name="everyone left: " + name, automation=LEFT_AUTO, expr=expr, expect=expect,
                given=given or {}, subs=subs or {}, finding=finding)


for _a, _want in (("disarmed", "True"), ("armed_home", "True"), ("armed_night", "True"),
                  ("armed_away", "False"), ("arming", "False"), ("triggered", "False"),
                  ("unavailable", "False")):
    A(left("offer to arm from %s: %s" % (_a, _want), "offer_arm", _want, subs={ALARM: "'%s'" % _a},
           finding=EL + "; never offer over an alarm that is going off or already leaving"))
A(left("lights on are worth saying", "has_left", "True", subs={LEFT_NOW: "'light.lamp'"}))
for _s in ("none", "unavailable", "unknown"):
    A(left("'%s' is not a light" % _s, "has_left", "False", subs={LEFT_NOW: "'%s'" % _s}))
A(left("all buttons when all apply", "buttons", "['ARM_AWAY_HOUSE', 'HOME_OCCUPIED', 'LEFT_ON_OFF']",
       given=dict(offer_arm=True, has_left=True), finding="2026-11-24: the arm offer can also be answered 'no'"))
A(left("no lights: arm, or someone is home", "buttons", "['ARM_AWAY_HOUSE', 'HOME_OCCUPIED']",
       given=dict(offer_arm=True, has_left=False), finding="2026-11-24: the arm offer can also be answered 'no'"))
A(left("already Away, only the lights button", "buttons", "['LEFT_ON_OFF']",
       given=dict(offer_arm=False, has_left=True), finding="the old notice is unchanged"))
A(left("the button arms an empty house", "arm_now", "True",
       subs={ZONE: "'0'", ALARM: "'disarmed'"}))
A(left("the button does not arm over someone who came back", "arm_now", "False",
       subs={ZONE: "'1'", ALARM: "'disarmed'"}, finding=EL + "; a late tap must not lock a person in"))
A(left("the button does not re-arm a house already Away", "arm_now", "False",
       subs={ZONE: "'0'", ALARM: "'armed_away'"}))
A(left("an unknown zone count does not arm", "arm_now", "False",
       subs={ZONE: "'unknown'", ALARM: "'disarmed'"}, finding="unknown is not 'nobody'"))


# ---------------------------------------------------------------- a safety sensor that stopped reporting
# 2026-10-14 operator. The corridor smoke/CO alarm had been unavailable since 2026-10-12 20:32 and
# nothing said so: `any_safety_alarm` rightly ignores an unavailable alarm (a dead battery is not a
# fire), which also made a dead alarm invisible. This lists them. 30 minutes first, so a Zigbee blip
# or a restart does not put a red box on the family Home page.
SILENT = "Any safety sensor silent"
NOW_TS = "as_timestamp(now())"
T0 = 1791900000.0          # "now" in these cases
OLD = "2026-10-12T18:32:52+00:00"


def _iso(ts):
    import datetime
    return datetime.datetime.fromtimestamp(ts, datetime.timezone.utc).isoformat()


def _sb(eid, state, dc, since):
    s = _bs(eid, state, dc)
    s["last_changed"] = since
    return s


def silent(name, expect, *sensors, finding="2026-10-14: a dead smoke alarm said nothing"):
    return sensor_case("silent: " + name, expect, {ALL_BS: _house(*sensors), NOW_TS: repr(T0)},
                       sensor=SILENT, finding=finding)


A(silent("an alarm unavailable for two days is named", "binary_sensor.co_smoke",
         _sb("binary_sensor.co_smoke", "unavailable", "smoke", OLD)))
A(silent("unknown counts as silent too", "binary_sensor.leak",
         _sb("binary_sensor.leak", "unknown", "moisture", OLD)))
A(silent("ten minutes is a blip, not a dead sensor", "none",
         _sb("binary_sensor.co_smoke", "unavailable", "smoke", _iso(T0 - 600)),
         finding="Zigbee drops and restarts must not raise a red box"))
A(silent("thirty-one minutes is silent", "binary_sensor.co_smoke",
         _sb("binary_sensor.co_smoke", "unavailable", "smoke", _iso(T0 - 1860))))
A(silent("a working alarm is not silent", "none",
         _sb("binary_sensor.co_smoke", "off", "smoke", OLD)))
A(silent("only safety classes count", "none",
         _sb("binary_sensor.car_light", "unavailable", "light", OLD),
         _sb("binary_sensor.door", "unavailable", "door", OLD)),
  )
A(silent("the roll-ups never count themselves", "none",
         _sb("binary_sensor.any_safety_alarm", "unavailable", "safety", OLD)),
  )
A(silent("several are listed together", "binary_sensor.a, binary_sensor.b",
         _sb("binary_sensor.a", "unavailable", "smoke", OLD),
         _sb("binary_sensor.b", "unavailable", "carbon_monoxide", OLD)))


# ---------------------------------------------------------------- everyone left: a child with no phone (2026-10-14)
# Operator: a child is sometimes left at home with a sitter, and neither has a phone that reports a
# location, so "every phone has left" does not mean the house is empty. Before Away is offered, ask
# whether that child is with us; no answer means no - assume the child is home and do not arm.
# The names live in `input_text.house_untracked_people` on the instance (comma-separated), never
# in this repo: these cases use invented names.
UNTRACKED = "states('input_text.house_untracked_people')"
KID = "2026-10-14 operator: ask whether the phone-less child is with us; silence means home"
A(left("the untracked names are read from the helper", "ask_about", "['Alex']",
       subs={UNTRACKED: "'Alex'"}, finding=KID))
A(left("several names, spaces trimmed", "ask_about", "['Alex', 'Sam']",
       subs={UNTRACKED: "'Alex, Sam'"}, finding=KID))
for _s in ("", "unknown", "unavailable"):
    A(left("an empty or missing helper asks about nobody (%r)" % _s, "ask_about", "[]",
           subs={UNTRACKED: "'%s'" % _s}, finding=KID))
A(left("the arm button says who must be with you", "arm_title", "Alex is with us - arm Away",
       given=dict(ask_about=["Alex"]), finding=KID + "; the tap IS the yes"))
A(left("two names read as a group", "arm_title", "Alex and Sam are with us - arm Away",
       given=dict(ask_about=["Alex", "Sam"]), finding=KID))
A(left("nobody untracked, the plain button", "arm_title", "Arm Away", given=dict(ask_about=[])))
A(left("the 'no' names who stayed", "home_title", "Alex is at home", given=dict(ask_about=["Alex"]),
       finding="2026-11-24 operator: say from the push that the house is occupied"))
A(left("two names stay as a group", "home_title", "Alex and Sam are at home", given=dict(ask_about=["Alex", "Sam"])))
A(left("nobody untracked: someone else is home", "home_title", "Someone is home", given=dict(ask_about=[])))
A(left("the arm offer asks the question", "arm_line",
       "Is Alex with you? Arm Away only if so - no answer leaves the alarm as it is.",
       given=dict(ask_about=["Alex"]), subs={ALARM: "'disarmed'"}, finding=KID))
A(left("without an untracked person the offer is unchanged", "arm_line",
       "The alarm is off. Arm Away?", given=dict(ask_about=[]), subs={ALARM: "'disarmed'"}))


# ---------------------------------------------------------------- front door while away (issue #7, 2026-10-20)
# The door is an EVO192 zone, but the Alarmo -> EVO sync is disabled, so arming Away from Home
# Assistant (the everyone-left offer) leaves the panel disarmed and nothing watching the door. Tell
# both adults when the SwitchBot lock unlocks or the door opens while the house is Away - unless the
# panel itself is armed Away, which raises its own alarm (and, once the sync runs, its own push).
DOOR = "1792000000001"
EVO = "states('alarm_control_panel.evo192_partition_paradox_alarm')"
DW = "issue #7: the door is unwatched while the house is Away and the panel is not armed"


ZONE_HOME = "states('zone.home')"


def door(name, expr, expect, subs, finding=DW):
    # Review 2026-10-20: every return home opened the door while still Away, a time-sensitive push
    # on every arrival. A tracked phone at home means someone is back; only an empty house is told.
    if expr == "tell":
        subs = dict({ZONE_HOME: "'0'"}, **subs)
    return dict(name="front door: " + name, automation=DOOR, expr=expr, expect=expect, given={},
                subs=subs, finding=finding)


A(door("opened while Away, panel disarmed, says so", "tell", "True",
       {ALARM: "'armed_away'", EVO: "'disarmed'"}))
A(door("an offline panel watches nothing either", "tell", "True",
       {ALARM: "'armed_away'", EVO: "'unavailable'"}))
for _e in ("armed_away", "triggered", "pending", "arming"):
    A(door("the panel armed Away (%s) raises its own alarm" % _e, "tell", "False",
           {ALARM: "'armed_away'", EVO: "'%s'" % _e}, finding=DW + "; no second alarm"))
for _a in ("armed_home", "armed_night", "disarmed", "triggered"):
    A(door("a house that is not Away (%s) is not told" % _a, "tell", "False",
           {ALARM: "'%s'" % _a, EVO: "'disarmed'"}, finding=DW + "; people are home"))
A(door("a phone already home: someone is back, not told", "tell", "False",
       {ALARM: "'armed_away'", EVO: "'disarmed'", ZONE_HOME: "'1'"},
       finding="review 2026-10-20: the arrival itself was the commonest trigger"))
A(door("an unreadable zone is not taken as someone home", "tell", "True",
       {ALARM: "'armed_away'", EVO: "'disarmed'", ZONE_HOME: "'unknown'"},
       finding="review 2026-10-20: when in doubt, tell"))
A(door("an unlock says unlocked", "what", "unlocked", {TRIG: "'unlock'"}))
A(door("the door contact says opened", "what", "opened", {TRIG: "'door'"}))
A(door("a jammed lock says so: the door may not be locked", "what", "left jammed",
       {TRIG: "'jammed'"}, finding=DW + "; the lock has reported jammed 3 times in 10 days"))


# ---------------------------------------------------------------- energy: yesterday's digest (issue #8, 2026-10-20)
# There is no whole-house meter, so the digest says what the METERED devices used: the Energy
# dashboard's own device list, summed from the same long-term statistics it draws, read with
# recorder.get_statistics just after midnight. The AC share is the meters whose id ends
# `_ac_energy`. A meter with no statistics for the day (offline) is left out and counted out.
DIGEST = "1792100000001"
EN = "issue #8: one line a day from the meters the house already has"


def _st(**changes):
    return {"statistics": {k.replace("__", "."): [{"change": v}] for k, v in changes.items()}}


def digest(name, expr, expect, given, finding=EN):
    return dict(name="energy: " + name, automation=DIGEST, expr=expr, expect=expect,
                given=given, subs={}, finding=finding)


_IDS = ["sensor.tv_energy", "sensor.room_ac_energy", "sensor.other_ac_energy"]
A(digest("every reported meter is summed", "total", "4.75",
         dict(ids=_IDS, stats=_st(sensor__tv_energy=1.5, sensor__room_ac_energy=2.25,
                                  sensor__other_ac_energy=1.0))))
A(digest("the AC share is the AC meters only", "ac", "3.25",
         dict(ids=_IDS, stats=_st(sensor__tv_energy=1.5, sensor__room_ac_energy=2.25,
                                  sensor__other_ac_energy=1.0))))
A(digest("an offline meter is left out, not counted as zero use", "reported", "2",
         dict(ids=_IDS, stats=_st(sensor__tv_energy=1.5, sensor__room_ac_energy=2.25))))
A(digest("an offline meter does not break the sum", "total", "3.75",
         dict(ids=_IDS, stats=_st(sensor__tv_energy=1.5, sensor__room_ac_energy=2.25))))
A(digest("a meter outside the list is ignored", "total", "1.5",
         dict(ids=["sensor.tv_energy"], stats=_st(sensor__tv_energy=1.5, sensor__stray_energy=9.0))))
A(digest("a bucket with no change is offline, not zero use", "reported", "1",
         dict(ids=_IDS, stats={"statistics": {"sensor.tv_energy": [{"change": 1.5}],
                                              "sensor.room_ac_energy": [{"change": None}]}}),
         finding="review 2026-10-20: a meter with metadata but no data in the window"))
A(digest("a bucket with no change adds nothing", "total", "1.5",
         dict(ids=_IDS, stats={"statistics": {"sensor.tv_energy": [{"change": 1.5}],
                                              "sensor.room_ac_energy": [{"change": None}]}})))
A(digest("a day with no data at all says zero meters", "reported", "0",
         dict(ids=_IDS, stats={"statistics": {}})))


# ---------------------------------------------------------------- morning briefing (issue #6, 2026-10-20)
# One message assembled from the roll-ups the house already has. It READS them and derives
# nothing: a second copy of a threshold is how the battery card drifted (audit 2026-10-20, 1-3).
# Optional and off by default. Home's Needs attention is the on-screen surface for the same facts.
BRIEF = "1792200000001"
BR = "issue #6: one line of 'here is the house', from the roll-ups, never re-derived"
B_LOW = "states('sensor.any_low_battery')"
B_SIL = "states('sensor.any_safety_sensor_silent')"
B_LEFT = "states('sensor.lighting_left_on')"
B_RISK = "is_state('binary_sensor.climate_health_risk', 'on')"
B_NAME = "state_attr(e, 'friendly_name')"
B_LVL = "states(e)"
E_T = "states('input_number.energy_yesterday')"
E_A = "states('input_number.energy_yesterday_ac')"
E_M = "states('input_number.energy_yesterday_meters')"
QUIET = {B_LOW: "'none'", B_SIL: "'none'", B_LEFT: "'none'", B_RISK: "false",
         B_NAME: "none", B_LVL: "'0'"}


def brief(name, expr, expect, subs=None, given=None, finding=BR):
    # Every read in `attention` is pinned: the quiet house, then what the case changes.
    s = dict(QUIET) if expr == "attention" else {}
    s.update(subs or {})
    return dict(name="briefing: " + name, automation=BRIEF, expr=expr, expect=expect,
                given=given or {}, subs=s, finding=finding)


_NAMES = "{'sensor.leak_battery': 'Leak Battery', 'binary_sensor.smoke': 'Smoke', 'light.lamp': 'Lamp'}.get(e)"
A(brief("a quiet house says nothing needs attention", "attention", "[]"))
A(brief("a low battery is named with its level", "attention", "['Batteries to replace: Leak 15%']",
        {B_LOW: "'sensor.leak_battery'", B_NAME: _NAMES,
         B_LVL: "'15'"}))
A(brief("the battery list's '+N more' is passed through", "attention",
        "['Batteries to replace: Leak 15%, +3 more']",
        {B_LOW: "'sensor.leak_battery, +3 more'", B_NAME: _NAMES,
         B_LVL: "'15'"}))
A(brief("a silent safety sensor is named", "attention", "['Not reporting: Smoke']",
        {B_SIL: "'binary_sensor.smoke'", B_NAME: _NAMES}))
A(brief("lights left on overnight are named", "attention", "['Lights on: Lamp']",
        {B_LEFT: "'light.lamp'", B_NAME: _NAMES}))
A(brief("the health roll-up is pointed to, not re-derived", "attention",
        "['Damp, health or air-quality risk: see Home']", {B_RISK: "true"}))
for _s in ("unknown", "unavailable", ""):
    A(brief("a roll-up that is %r says nothing" % _s, "attention", "[]",
            {B_LOW: "'%s'" % _s, B_SIL: "'%s'" % _s, B_LEFT: "'%s'" % _s}))
A(brief("yesterday's energy with the AC share", "energy",
        "Yesterday the metered devices used 6.85 kWh, the ACs 32% of it.",
        {E_T: "'6.85'", E_A: "'2.2'", E_M: "'14.0'"}))
A(brief("no meter reported: no energy line", "energy", "",
        {E_T: "'0.0'", E_A: "'0.0'", E_M: "'0.0'"}, finding=BR + "; a zero is not a measurement"))
A(brief("nothing used at all: no division by zero", "energy",
        "Yesterday the metered devices used 0.0 kWh.", {E_T: "'0.0'", E_A: "'0.0'", E_M: "'3.0'"}))
A(brief("the message leads with what needs doing", "message",
        "Batteries to replace: Leak 15%\nYesterday the metered devices used 6.85 kWh.",
        given=dict(attention=["Batteries to replace: Leak 15%"],
                   energy="Yesterday the metered devices used 6.85 kWh.")))
A(brief("a quiet house says so", "message",
        "Nothing needs attention.\nYesterday the metered devices used 6.85 kWh.",
        given=dict(attention=[], energy="Yesterday the metered devices used 6.85 kWh.")))

# 2026-11-07 (operator): an idle AC reports its power as `unknown`, so the AC power total reads
# `unknown` whenever every unit is idle.  Rule: a unit whose climate entity is exactly `off`
# and whose power is `unknown`/`unavailable` publishes 0 W.  Anything else passes the reading
# through, and an unreachable unit (climate `unavailable`) stays unknown, never 0 W.
# The rule is live: the `Climate AC power <room>` template sensors implement it, and these
# cases read those expressions from the live config.  The subs must match the implemented
# expression text exactly; if the expression changes shape, run.py refuses the case rather
# than passing it.
AC_CLIMATE = "states('climate.living_room_ac')"
AC_POWER = "states('sensor.living_room_ac_power')"
AC_TITLE = "Climate AC power living room"

A(sensor_case(
    "an idle AC with no power reading publishes 0 W", "0",
    {AC_CLIMATE: "'off'", AC_POWER: "'unknown'"}, sensor=AC_TITLE,
    finding="2026-11-07: the AC power total reads unknown when every unit is idle"))
A(sensor_case(
    "an idle AC with an unavailable power reading also publishes 0 W", "0",
    {AC_CLIMATE: "'off'", AC_POWER: "'unavailable'"}, sensor=AC_TITLE,
    finding="2026-11-07: off is the commanded state; the unit is not running"))
A(sensor_case(
    "an unreachable AC is not idle: no reading stays unknown", "unknown",
    {AC_CLIMATE: "'unavailable'", AC_POWER: "'unknown'"}, sensor=AC_TITLE,
    finding="unreachable is not off: an unavailable unit must never be published as 0 W"))
A(sensor_case(
    "a running AC with no power reading stays unknown, not zero", "unknown",
    {AC_CLIMATE: "'cool'", AC_POWER: "'unknown'"}, sensor=AC_TITLE,
    finding="a running unit that reports nothing is a gap, not an idle unit"))
A(sensor_case(
    "an idle AC's real standby draw is passed through, not zeroed", "12.0",
    {AC_CLIMATE: "'off'", AC_POWER: "'12.0'"}, sensor=AC_TITLE,
    finding="standby draw is a measurement; only a missing reading becomes 0"))
A(sensor_case(
    "a running AC's power is passed through", "850.0",
    {AC_CLIMATE: "'cool'", AC_POWER: "'850.0'"}, sensor=AC_TITLE,
    finding="the running reading is never replaced"))

# 2026-11-07 (operator): the same idle rule for the other four units, each with its own climate
# entity and power sensor.  Same six cases per unit, so a unit cannot drift from the rule.
#
# The two children's units take their ids from the gitignored room map (the names are scrubbed
# from the repo; see harness.load_rooms), like every other child-room reference in this suite.
_RM = harness.load_rooms()
_AC_UNITS = (
    ("Climate AC power office", "climate.office_ac", "sensor.office_ac_power"),
    ("Climate AC power bedroom", "climate.bedroom_ac", "sensor.bedroom_ac_power"),
    ("Climate AC power " + _RM["kid1"]["title"], _RM["kid1"]["ac_climate"], _RM["kid1"]["ac_power"]),
    ("Climate AC power " + _RM["kid2"]["title"], _RM["kid2"]["ac_climate"], _RM["kid2"]["ac_power"]),
)
for _title, _climate, _power in _AC_UNITS:
    _c = "states('%s')" % _climate
    _p = "states('%s')" % _power
    _unit = _title.replace("Climate AC power ", "")
    A(sensor_case("%s: an idle AC with no power reading publishes 0 W" % _unit, "0",
                  {_c: "'off'", _p: "'unknown'"}, sensor=_title,
                  finding="2026-11-07: idle units read unknown, so the total read unknown"))
    A(sensor_case("%s: an idle AC with an unavailable reading also publishes 0 W" % _unit, "0",
                  {_c: "'off'", _p: "'unavailable'"}, sensor=_title,
                  finding="2026-11-07: off is the commanded state; the unit is not running"))
    A(sensor_case("%s: an unreachable AC is not idle: no reading stays unknown" % _unit, "unknown",
                  {_c: "'unavailable'", _p: "'unknown'"}, sensor=_title,
                  finding="unreachable is not off: never published as 0 W"))
    A(sensor_case("%s: a running AC with no power reading stays unknown" % _unit, "unknown",
                  {_c: "'cool'", _p: "'unknown'"}, sensor=_title,
                  finding="a running unit that reports nothing is a gap, not an idle unit"))
    A(sensor_case("%s: an idle AC's real standby draw is passed through" % _unit, "12.0",
                  {_c: "'off'", _p: "'12.0'"}, sensor=_title,
                  finding="standby draw is a measurement; only a missing reading becomes 0"))
    A(sensor_case("%s: a running AC's power is passed through" % _unit, "850.0",
                  {_c: "'cool'", _p: "'850.0'"}, sensor=_title,
                  finding="the running reading is never replaced"))


# Power cut (operator 2026-11-23): the Solix C2000 is the office UPS. Grid input gone while it is
# still feeding a load means the house lost power. Cloud integration: an unreachable Solix is NOT a
# cut, and a Solix with nothing plugged in cannot tell a cut from an idle grid, so it stays quiet.
POWER = "1792300000010"
P_IN = "states('sensor.guest_room_solix_c2000_gen_2_ac_input_power')"
P_OUT = "states('sensor.guest_room_solix_c2000_gen_2_ac_output_power')"
P_SOC = "states('sensor.guest_room_solix_c2000_gen_2_state_of_charge')"


P_ANN = "is_state('input_boolean.power_cut_announced', 'on')"


def power(name, expect, trig="'cut'", i="'0'", o="'350'", soc="'100'", ann="false", finding=""):
    return dict(name="power: " + name, automation=POWER, expr="want", expect=expect, given={},
                subs={"trigger.id": trig, P_IN: i, P_OUT: o, P_SOC: soc, P_ANN: ann}, finding=finding)


A(power("grid gone while the office runs on battery is a cut", "cut",
        finding="2026-11-23 operator: alert on a power cut"))
A(power("grid present is not a cut", "none", i="'350'", finding="passthrough: input follows the load"))
A(power("an input of 4 W is still a cut", "cut", i="'4'", finding="threshold 5 W: a trickle is not the grid"))
A(power("an input of 6 W is not a cut", "none", i="'6'", finding="the threshold straddled from above"))
A(power("nothing plugged in cannot tell a cut from an idle grid", "none", o="'0'",
        finding="input 0 W with no load is normal; stay quiet rather than guess"))
A(power("an unreachable Solix is not a cut", "none", i="'unavailable'", o="'unavailable'",
        finding="cloud integration: unreachable is not off"))
A(power("an unknown input is not a cut", "none", i="'unknown'",
        finding="a restart restores unknown first"))
A(power("battery under 20 % during a cut warns", "low", trig="'low'", soc="'19'",
        finding="2026-11-23 operator: warn before the office loses power"))
A(power("battery at 21 % does not warn", "none", trig="'low'", soc="'21'",
        finding="the threshold straddled from above"))
A(power("a low battery with the grid back is recharging, not a warning", "none", trig="'low'",
        soc="'15'", i="'900'", finding="after a cut the battery refills from a low level"))
A(power("a low trigger with an unreadable charge stays quiet", "none", trig="'low'", soc="'unavailable'",
        finding="unreachable is not low"))
# review 2026-11-23 (#48): the power-back wait died with a restart; it is now a trigger + a marker.
A(power("load of exactly 5 W with no grid is a cut", "cut", o="'5'", finding="review #48: output edge, from above"))
A(power("load of 4 W with no grid cannot be told from an idle grid", "none", o="'4'",
        finding="review #48: output edge, from below"))
A(power("a cut already announced is not announced again", "none", ann="true",
        finding="review #48: a restart re-arms the numeric trigger; one push per cut"))
A(power("the grid back after an announced cut", "back", trig="'back'", i="'350'", ann="true",
        finding="review #48: power-back survives a restart because it is a trigger, not a wait"))
A(power("the grid back with no cut announced says nothing", "none", trig="'back'", i="'350'",
        finding="an ordinary rise in input is not news"))
A(power("an unreachable Solix is not the grid coming back", "none", trig="'back'", i="'unavailable'",
        o="'unavailable'", ann="true", finding="unreachable is neither cut nor back"))


# Vacuum while away (operator 2026-11-23): vacuum.zorik (Roborock cloud) and
# vacuum.robotic_vacuum_cleaner (Matter) are the SAME robot by two paths. Prefer Roborock, fall
# back to Matter. At most one clean a day, daytime only, dock when someone is home again.
VAC = "1792300000002"
V_ZORIK = "states('vacuum.zorik')"
V_MATTER = "states('vacuum.robotic_vacuum_cleaner')"


def vac_pick(name, expect, z, m, finding):
    return dict(name="vacuum: " + name, automation=VAC, expr="vac", expect=expect, given={},
                subs={V_ZORIK: z, V_MATTER: m}, finding=finding)


A(vac_pick("Roborock is preferred", "vacuum.zorik", "'docked'", "'docked'",
           finding="2026-11-23 operator: one robot, two paths"))
A(vac_pick("Matter is the fallback when Roborock is unreachable", "vacuum.robotic_vacuum_cleaner",
           "'unavailable'", "'docked'", finding="the cloud path drops; the local one may not"))
A(vac_pick("neither path: nothing", "none", "'unavailable'", "'unknown'",
           finding="never command an unreachable robot"))

V_STATE = "states(vac)"
V_ALARM = "states('alarm_control_panel.home')"
V_LAST = "states('sensor.zorik_last_clean_begin')"
V_HOUR = "now().hour"
V_TODAY = "now().strftime('%Y-%m-%d')"


V_OURS = "states('input_datetime.vacuum_away_started')"


def vac(name, expect, trig="'away'", st="'docked'", alarm="'armed_away'",
        last="'2026-11-22T07:15:01+00:00'", hour="10", v="vacuum.zorik", ours="'2026-11-22 10:20:00'",
        finding=""):
    return dict(name="vacuum: " + name, automation=VAC, expr="want", expect=expect, given={"vac": v},
                subs={"trigger.id": trig, V_STATE: st, V_ALARM: alarm, V_LAST: last, V_HOUR: hour,
                      V_TODAY: "'2026-11-23'", V_OURS: ours}, finding=finding)


A(vac("away, docked, not cleaned today: start", "start", finding="2026-11-23 operator: vacuum on Away"))
A(vac("already cleaned today: no second run", "none", last="'2026-11-23T07:15:01+00:00'",
      finding="at most once a day"))
A(vac("cleaned just before local midnight counts as yesterday", "start",
      last="'2026-11-22T22:30:00+00:00'", finding="the day is local: 23:30 CET on the 22nd"))
A(vac("cleaned just after local midnight counts as today", "none",
      last="'2026-11-22T23:30:00+00:00'", finding="00:30 CET on the 23rd is today, though UTC says the 22nd"))
A(vac("no record of a last clean: start", "start", last="'unknown'",
      finding="the Matter path has no history; unknown is not 'cleaned today'"))
A(vac("before 08:00: wait", "none", hour="7", finding="Do Not Disturb runs 22:00-08:00"))
A(vac("08:00 is allowed", "start", hour="8", finding="the window straddled from below"))
A(vac("19:00 is allowed", "start", hour="19", finding="the window straddled from above"))
A(vac("20:00 is too late", "none", hour="20", finding="no clean starting into the evening"))
A(vac("the robot is already out: leave it", "none", st="'cleaning'", finding="never restart a run"))
A(vac("the robot is in error: leave it", "none", st="'error'", finding="only start from the dock"))
A(vac("Away was cancelled before the delay ran out: no start", "none", alarm="'disarmed'",
      finding="the alarm is re-read when the delay ends"))
A(vac("no reachable robot: nothing", "none", v="none", st="'unknown'", finding="vac picks none"))
A(vac("someone back while it cleans: dock", "dock", trig="'back'", st="'cleaning'", alarm="'armed_home'",
      finding="2026-11-23 operator: dock when the house is no longer Away"))
A(vac("someone back while it is docked: nothing", "none", trig="'back'", st="'docked'", alarm="'disarmed'",
      finding="no command for a robot that is home"))
A(vac("someone back while it is already returning: nothing", "none", trig="'back'", st="'returning'",
      alarm="'disarmed'", finding="no duplicate command"))
A(vac("Away again by the time the back step runs: keep cleaning", "none", trig="'back'", st="'cleaning'",
      finding="the alarm is re-read, not taken from the trigger"))
A(vac("started by this automation earlier today: no second run", "none", last="'unknown'",
      ours="'2026-11-23 10:20:00'",
      finding="review #48: on the Matter path the Roborock history is unknown; our own stamp still counts"))
A(vac("started by this automation yesterday: today is allowed", "start", last="'unknown'",
      ours="'2026-11-22 18:00:00'", finding="the stamp is a day, not a lock"))


# Lights stuck on after a room clears (2026-11-23; incident 2026-10-25: a failed Zigbee OFF left
# HA showing the Corridor light ON, so Magic Areas skipped the next turn-on). Magic Areas turns
# every light off when a room clears. A light still on 90 s later that has NOT changed since the
# room cleared is a failed OFF (or a wrong state in HA); one that changed after is somebody's choice.
LIGHTS = "1792300000003"
L_CTRL = "states('switch.magic_areas_light_groups_' ~ area ~ '_light_control')"
L_AREA = "states('binary_sensor.magic_areas_presence_tracking_' ~ area ~ '_area_state')"
L_MEMBERS = "expand('light.magic_areas_light_groups_' ~ area ~ '_all_lights')"
L_CLEARED = "as_timestamp(trigger.to_state.last_changed)"
L_T0 = 1795000000  # the moment the room cleared


def lt(entity, state, changed):
    return {"entity_id": entity, "state": state, "last_changed": changed}


def stuck(name, expect, members, ctrl="'on'", now_="'off'", finding=""):
    return dict(name="lights stuck: " + name, automation=LIGHTS, expr="stuck", expect=expect,
                given={"area": "corridor"},
                subs={L_CTRL: ctrl, L_AREA: now_, L_MEMBERS: repr(members), L_CLEARED: L_T0},
                finding=finding)


_BEFORE, _AFTER = "2026-11-18T11:05:00+00:00", "2026-11-18T11:08:00+00:00"  # around L_T0 (11:06:40 UTC)
A(stuck("a light still on since before the room cleared is stuck", "['light.corridor_light']",
        [lt("light.corridor_light", "on", _BEFORE), lt("light.entrance_light", "off", _BEFORE)],
        finding="2026-10-25: a failed Z2M OFF"))
A(stuck("a light switched on after the room cleared is left alone", "[]",
        [lt("light.corridor_light", "on", _AFTER)], finding="somebody's choice, not a failure"))
A(stuck("lights that went off are fine", "[]",
        [lt("light.corridor_light", "off", _AFTER), lt("light.entrance_light", "off", _AFTER)],
        finding="the normal case"))
A(stuck("an unreachable bulb is not stuck", "[]", [lt("light.corridor_light", "unavailable", _BEFORE)],
        finding="operator rule: wall-switched bulbs are deliberate"))
A(stuck("light control off: Magic Areas never switched them off, so nothing is stuck", "[]",
        [lt("light.corridor_light", "on", _BEFORE)], ctrl="'off'",
        finding="Away pauses light control; a paused room is not a failure"))
A(stuck("the room is occupied again: nothing to do", "[]",
        [lt("light.corridor_light", "on", _BEFORE)], now_="'on'", finding="re-read when the delay ends"))
A(stuck("two stuck lights are both retried", "['light.corridor_light', 'light.entrance_light']",
        [lt("light.corridor_light", "on", _BEFORE), lt("light.entrance_light", "on", _BEFORE)],
        finding="every member, not the first"))

A(stuck("a light that changed in the same second as the clear is not stuck", "[]",
        [lt("light.corridor_light", "on", "2026-11-18T11:06:40+00:00")],
        finding="review #48: the boundary is strict; MA's own batch can land on the clear stamp"))
A(stuck("a room with no light group has nothing stuck", "[]", [],
        finding="review #48: closet/shower/stairs-style areas, or a renamed group"))
# Leak meter (operator 2026-11-23): "we lose temperature very fast when heating is off". Away sets
# every room to 16 C within ~30 min, so from one hour into Away until it ends the flat cools
# unheated. Per room: the % of its indoor-outdoor gap lost per hour (k). Per CO2 room: air changes
# per hour from the CO2 decay toward 400 ppm (the meters' auto-calibration floor). Signals: a room
# losing heat >= 2x the flat's median is the leakiest; >= 1.8x its OWN last run as well = a window
# probably left open. A room that warmed (the office: IT gear) is kept warm, never a suspect.
# The expressions are pure functions of variables built by the automation, so cases bind them.
LEAK = "1792300000020"


L_AWAY = "states('input_number.climate_away_min')"


def leak(name, expr, expect, finding, subs=None, **given):
    if expr == "k" and subs is None:
        subs = {L_AWAY: "'0'"}   # the setpoint exclusion has its own cases; elsewhere it is out of the way
    if expr == "k":
        # socket heat has its own cases; a room with no meters and no heat-loss figure is uncorrected
        given = {"rooms_heat": {}, "heat_w": {}, "ua": {}} | given
    return dict(name="leak meter: " + name, automation=LEAK, expr=expr, expect=expect, given=given,
                subs=subs or {}, finding=finding)


_SNAP = {"t": 0, "o": 5.0, "T": {"kid1": 21.0, "kid2": 21.0}, "C": {}}
A(leak("a room's warmth loss is the log of the gap ratio per hour", "k", "{'kid1': 6.7, 'kid2': 1.6}",
       "k = 100 ln((T1-o)/(T2-o)) / h", snap=_SNAP, now_T={"kid1": 19.0, "kid2": 20.5}, now_o=5.0, hours=2))
A(leak("the outdoor temperature is the mean of start and end", "k", "{'kid1': 6.7}",
       "a cooling evening must not read as a leak",
       snap={"t": 0, "o": 4.0, "T": {"kid1": 21.0}, "C": {}}, now_T={"kid1": 19.0}, now_o=6.0, hours=2))
A(leak("a room that warmed is kept warm (-1), not airtight", "k", "{'kid1': -1}",
       "the office gains ~0.1 C/h from its IT gear with the heating off",
       snap=_SNAP | {"T": {"kid1": 21.0}}, now_T={"kid1": 21.4}, now_o=5.0, hours=2))
A(leak("a gap under 3 C is too small to measure", "k", "{}", "sensor steps swamp a small gap",
       snap={"t": 0, "o": 5.0, "T": {"kid1": 7.9}, "C": {}}, now_T={"kid1": 7.5}, now_o=5.0, hours=2))
A(leak("a gap of exactly 3 C is measured", "k", "{'kid1': 7.2}", "the threshold straddled from above",
       snap={"t": 0, "o": 5.0, "T": {"kid1": 8.0}, "C": {}}, now_T={"kid1": 7.6}, now_o=5.0, hours=2))
A(leak("a room with no reading now is skipped", "k", "{'kid2': 1.6}", "unavailable is not cold",
       snap=_SNAP, now_T={"kid1": None, "kid2": 20.5}, now_o=5.0, hours=2))
# review 2026-11-23 (#49) F5: Away holds every room at climate_away_min. A room that cooled to it
# was heated from then on and would read airtight; it is kept warm, not measured.
A(leak("a room that reached the Away setpoint was heated: kept warm", "k", "{'kid1': -1}",
       "review #49 F5: the asymptote is the setpoint, not outdoors", subs={L_AWAY: "'16'"},
       snap={"t": 0, "o": 5.0, "T": {"kid1": 21.0}, "C": {}}, now_T={"kid1": 16.4}, now_o=5.0, hours=2))
A(leak("just above the Away setpoint is measured", "k", "{'kid1': 16.1}",
       "the 0.5 C margin straddled from above", subs={L_AWAY: "'16'"},
       snap={"t": 0, "o": 5.0, "T": {"kid1": 21.0}, "C": {}}, now_T={"kid1": 16.6}, now_o=5.0, hours=2))

# Socket heat (operator 2026-11-26): "the heat produced by devices when nobody is home - the rack
# with a few servers in the office, the PoE power supply in the living room". A room with a steady
# source P cools toward outdoors + P/H, not toward outdoors (H: its heat loss in W/K, from the
# 1997 radiator sizing, docs/heating-energy-rating.md). The rate is measured against that
# equilibrium. 21.11: the office read 1.2 %/h, the flat's tightest, with ~225 W of rack in it.
_OFFICE = {"office": {"add": ["m.rack", "m.out"], "sub": ["m.in"], "ac": "m.ac"}}
_OSNAP = {"t": 0, "o": 5.705, "T": {"office": 20.4}, "C": {}}
A(leak("a room's socket heat moves the point it cools toward", "k", "{'office': 3.5}",
       "operator 2026-11-26: the rack kept the office 'tightest' (21.11: 1.2 uncorrected)",
       snap=_OSNAP, now_T={"office": 20.1}, now_o=5.705, hours=1.78, rooms_heat=_OFFICE,
       heat_w={"office": {"w": 225, "ac": 0}}, ua={"office": 23}))
A(leak("without its heat figure the same room reads as before", "k", "{'office': 1.2}",
       "the correction is the only difference: 21.11's stored value", snap=_OSNAP,
       now_T={"office": 20.1}, now_o=5.705, hours=1.78))
A(leak("a metered room whose meters could not be read is not measured (-3)", "k", "{'office': -3}",
       "an uncorrected office would be stored ~3x too airtight", snap=_OSNAP,
       now_T={"office": 20.1}, now_o=5.705, hours=1.78, rooms_heat=_OFFICE, heat_w={}, ua={"office": 23}))
A(leak("an air conditioner heating during the run: not measured (-2)", "k", "{'office': -2}",
       "a heat pump delivers 3-4x its power; heat added is not heat kept", snap=_OSNAP,
       now_T={"office": 20.1}, now_o=5.705, hours=1.78, rooms_heat=_OFFICE,
       heat_w={"office": {"w": 225, "ac": 51}}, ua={"office": 23}))
A(leak("an air conditioner at 50 W is standby noise: measured", "k", "{'office': 3.5}",
       "the 50 W threshold straddled from below", snap=_OSNAP,
       now_T={"office": 20.1}, now_o=5.705, hours=1.78, rooms_heat=_OFFICE,
       heat_w={"office": {"w": 225, "ac": 50}}, ua={"office": 23}))
A(leak("a room its own sockets hold within 3 C of its temperature is kept warm (-1)", "k", "{'office': -1}",
       "21.11: 355 W (rack + the Solix charging) put the office's equilibrium above the office; "
       "18 C over outdoors but 2.9 C over where 347 W holds it", snap={"t": 0, "o": 5.0, "T": {"office": 23.0}, "C": {}},
       now_T={"office": 22.8}, now_o=5.0, hours=2, rooms_heat=_OFFICE,
       heat_w={"office": {"w": 347, "ac": 0}}, ua={"office": 23}))
A(leak("exactly 3 C over the equilibrium is measured", "k", "{'office': 3.4}",
       "the threshold straddled from above", snap={"t": 0, "o": 5.0, "T": {"office": 23.0}, "C": {}},
       now_T={"office": 22.8}, now_o=5.0, hours=2, rooms_heat=_OFFICE,
       heat_w={"office": {"w": 345, "ac": 0}}, ua={"office": 23}))

# room_t: a room's temperature for the leak meter (operator 2026-11-27: "use the average for the
# leak meter, same for all rooms that have multiple sensors"). The office's two desk sensors read
# 21.3 and 20.1: one desk is not the room. Rooms with several air sensors (room_temps) take their
# mean, others their climate_temp_ sensor (base). Not air: AC units, valves, chip temperatures.
_RT = {"office": ["t.a", "t.b"], "kid1": ["t.c", "t.d"]}
A(leak("a room with several air sensors reads their mean", "room_t",
       "{'office': 20.7, 'kid1': 20.95, 'corridor': 19.5}", "operator 2026-11-27: one desk is not the room",
       temp_base={"office": "21.3", "kid1": "20.9", "corridor": "19.5"}, room_temps=_RT,
       temp_reads={"t.a": "21.3", "t.b": "20.1", "t.c": "20.9", "t.d": "21"}))
A(leak("one of its sensors unreadable: the room has no reading", "room_t",
       "{'office': None, 'corridor': 19.5}", "a mean of one is the other sensor's level: a false step",
       temp_base={"office": "21.3", "corridor": "19.5"}, room_temps=_RT,
       temp_reads={"t.a": "21.3", "t.b": "unavailable"}))
A(leak("a single-sensor room unreadable has no reading", "room_t", "{'corridor': None}",
       "unavailable is not cold", temp_base={"corridor": "unknown"}, room_temps=_RT, temp_reads={}))

# heat_now: per metered room, [net kWh, AC kWh] from meter_vals (each meter's state, read once)
_HROOMS = {"office": {"add": ["m.rack", "m.out"], "sub": ["m.in"], "ac": "m.ac"},
           "kid2": {"add": [], "sub": [], "ac": "m.ac2"}, "corridor": {"add": ["m.l"], "sub": [], "ac": ""}}
_HVALS = {"m.rack": "651.31", "m.out": "0.62", "m.in": "0.98", "m.ac": "30.42", "m.ac2": "3.81", "m.l": "2.78"}
A(leak("a room's heat is its meters' sum less what its battery stored", "heat_now",
       "{'office': [650.95, 30.42], 'kid2': [0.0, 3.81], 'corridor': [2.78, 0]}",
       "the Solix charges through the rack plug: stored energy is not heat",
       rooms_heat=_HROOMS, meter_vals=_HVALS))
A(leak("a room with any meter unreadable is left out", "heat_now", "{'kid2': [0.0, 3.81], 'corridor': [2.78, 0]}",
       "a partial sum would read as less heat", rooms_heat=_HROOMS, meter_vals=_HVALS | {"m.in": "unavailable"}))
A(leak("an unreadable air conditioner leaves its room out too", "heat_now", "{'office': [650.95, 30.42], 'corridor': [2.78, 0]}",
       "an unseen heat pump could be heating", rooms_heat=_HROOMS, meter_vals=_HVALS | {"m.ac2": "unknown"}))

# heat_w: mean watts over the run from the two readings
A(leak("socket heat is the energy between the readings over the hours", "heat_w",
       "{'office': {'w': 225, 'ac': 6}}", "W = kWh x 1000 / h",
       heat_snap={"office": [650.0, 30.40]}, heat_now={"office": [650.45, 30.412]}, hours=2))
A(leak("a meter that went backwards (reset) leaves the room out", "heat_w", "{}",
       "a negative sum is a reset, not a cooler room",
       heat_snap={"office": [650.0, 30.4]}, heat_now={"office": [0.2, 30.4]}, hours=2))
A(leak("an air conditioner counter that went backwards leaves the room out", "heat_w", "{}",
       "the AC test must not pass on a reset", heat_snap={"office": [650.0, 30.4]},
       heat_now={"office": [650.4, 0.1]}, hours=2))
A(leak("a room missing from either reading is left out", "heat_w", "{'office': {'w': 200, 'ac': 0}}",
       "both ends or nothing", heat_snap={"office": [650.0, 0], "corridor": [2.7, 0]},
       heat_now={"office": [650.4, 0]}, hours=2))
A(leak("no heat snapshot: nothing", "heat_w", "{}", "a pre-existing snapshot or an oversize one",
       heat_snap=None, heat_now={"office": [650.4, 0]}, hours=2))

_CSNAP = {"t": 0, "o": 5.0, "T": {}, "C": {"living_room": 700.0}}
A(leak("air changes from the CO2 decay", "ach", "{'living_room': 0.55}", "ach = ln((C1-400)/(C2-400)) / h",
       snap=_CSNAP, now_C={"living_room": 500.0}, hours=2))
A(leak("CO2 at the meter's floor is clamped to 30 ppm over it", "ach", "{'living_room': 1.15}",
       "the meters bottom out at 400; an unclamped log runs to infinity",
       snap=_CSNAP, now_C={"living_room": 410.0}, hours=2))
A(leak("CO2 that rose is not a decay: skipped", "ach", "{}", "a pet or a person was home",
       snap=_CSNAP, now_C={"living_room": 720.0}, hours=2))
A(leak("a start under 100 ppm over the floor is too little to measure", "ach", "{}",
       "nobody was home long enough to raise it", snap=_CSNAP | {"C": {"office": 499.0}},
       now_C={"office": 450.0}, hours=2))
A(leak("a start of exactly 100 ppm over the floor is measured", "ach", "{'office': 0.35}",
       "the threshold straddled from above", snap=_CSNAP | {"C": {"office": 500.0}},
       now_C={"office": 450.0}, hours=2))

# 2026-11-21 measured: kid1 6.8, corridor 3.6, living room 2.7, kid2 2.1, office 1.1 (median 2.7)
_K = {"kid1": 6.8, "corridor": 3.6, "living_room": 2.7, "kid2": 2.1, "office": 1.1}
_NOPREV = {r: 0.0 for r in _K}


def sig(name, expect, finding, k=_K, prev_k=_NOPREV, ach=None, prev_ach=None):
    return leak(name, "signals", expect, finding, k=k, prev_k=prev_k, ach=ach or {}, prev_ach=prev_ach or {})


A(sig("the room losing >= 2x the flat's median is the leakiest", "['kid1:leakiest']",
      "2026-11-21: the kid 1 room cooled 2.5x faster than the median"))
A(sig("just under 2x the median is not singled out", "[]", "the threshold straddled from below",
      k=_K | {"kid1": 5.3}))
A(sig("much faster than its own last run as well: a window", "['kid1:window']",
      "operator: one room behaving differently = a forgotten open window", prev_k=_NOPREV | {"kid1": 3.77}))
A(sig("just under 1.8x its own last run: still only the leakiest", "['kid1:leakiest']",
      "the self threshold straddled", prev_k=_NOPREV | {"kid1": 3.78}))
A(sig("faster than its own last run but not than the flat: changed", "['kid1:leakiest', 'corridor:changed']",
      "informational: weather moves every room", prev_k=_NOPREV | {"corridor": 2.0}))
A(sig("no previous run is no baseline", "['kid1:leakiest']", "a fresh helper reads 0", prev_k=_NOPREV))
A(sig("two measurable rooms never single one out", "[]",
      "with n <= 2 no value can reach 2x the median, so no quorum guard is needed", k={"kid1": 6.8, "kid2": 2.1}, prev_k={}))
A(sig("a room kept warm is neither in the median nor a suspect", "[]",
      "the office's -1 must not drag the median down: 6.0 < 2 x 3.15, but >= 2 x 2.7 if it did",
      k=_K | {"office": -1, "kid1": 6.0}))
A(sig("air exchange >= 1.8x the last run is reported", "['kid1:leakiest', 'air:living_room']",
      "a window anywhere on the open stairs shows in the living room CO2",
      ach={"living_room": 0.9}, prev_ach={"living_room": 0.5}))
A(sig("air exchange just under 1.8x is not", "['kid1:leakiest']", "the threshold straddled",
      ach={"living_room": 0.89}, prev_ach={"living_room": 0.5}))
A(leak("only a window alerts", "alert", "True", "a push is for something to do now",
       signals=["kid1:window", "air:living_room"]))
A(leak("leakiest, changed and air are not alerts", "alert", "False",
       "they go in the record, not a push", signals=["kid1:leakiest", "corridor:changed", "air:office"]))


# review #49 F8: the baseline writes are the meter's only memory
_HV = {"has_value('input_number.leak_k_' ~ r)": "true", "has_value('input_number.leak_ach_' ~ r)": "true"}
A(leak("a window room's run is not stored as its baseline", "writes",
       "[{'e': 'input_number.leak_k_kid2', 'v': 2.1}]", "a window must not become normal",
       subs=_HV, k={"kid1": 6.8, "kid2": 2.1}, ach={}, signals=["kid1:window"]))
A(leak("a room kept warm stores nothing", "writes", "[]", "-1 is not a rate",
       subs=_HV, k={"office": -1}, ach={}, signals=[]))
A(leak("heat loss is clamped to the helper's range", "writes", "[{'e': 'input_number.leak_k_kid1', 'v': 50}]",
       "input_number max 50", subs=_HV, k={"kid1": 72.0}, ach={}, signals=[]))
A(leak("air changes are clamped to the helper's range", "writes",
       "[{'e': 'input_number.leak_ach_living_room', 'v': 5}]", "input_number max 5",
       subs=_HV, k={}, ach={"living_room": 7.2}, signals=[]))

# review #49 F1/F4: a run that cannot measure says why, in the verdict
L_OUT = "states('sensor.climate_temp_outdoor')"
A(leak("an unreadable snapshot is reported, not retried", "skip", "unreadable snapshot", "review #49 F1",
       subs={L_OUT: "'3'"}, snap=None, hours=0))
A(leak("no outdoor temperature is reported", "skip", "no outdoor temperature", "review #49 F4",
       subs={L_OUT: "'unavailable'"}, snap={"t": 0}, hours=3))
A(leak("a short Away is reported", "skip", "too short", "review #49 F8: under 1.5 h",
       subs={L_OUT: "'3'"}, snap={"t": 0}, hours=1.49))
A(leak("a measurable Away is not skipped", "skip", "", "1.5 h straddled from above",
       subs={L_OUT: "'3'"}, snap={"t": 0}, hours=1.5))
# Heating energy and an indicative A-G class (operator 2026-11-23; docs/heating-energy-rating.md,
# reviewed twice). Gas = a * degree-days + b * days; b measured from summer intervals only, a from
# winter intervals net of b; one trust condition (winter degree-days >= 300); a suspect week is held
# out; the class is on the former fixed apartment-building scale and labelled indicative.
def en(name, sensor, expect, subs, finding):
    return sensor_case("energy: " + name, expect, subs, finding=finding, sensor=sensor)


EB = "Energy gas hot water per day"
EB_G, EB_D = "states('input_number.energy_gas_s_g')", "states('input_number.energy_gas_s_d')"
A(en("hot water is summer gas per summer day", EB, "10.0", {EB_G: "'140'", EB_D: "'14'"},
     "an interval with no degree-days is all hot water"))
A(en("a week of summer data is enough", EB, "10.0", {EB_G: "'70'", EB_D: "'7'"}, "threshold from above"))
A(en("under a week of summer data: no hot-water term yet", EB, "0", {EB_G: "'60'", EB_D: "'6'"},
     "b = 0 until measured; the class errs pessimistic"))

EA = "Energy gas heating per degree-day"
EA_B = "states('sensor.energy_gas_hot_water_per_day')"
EA_G, EA_D, EA_H = ("states('input_number.energy_gas_w_g')", "states('input_number.energy_gas_w_d')",
                    "states('input_number.energy_gas_w_h')")
A(en("heating is winter gas per degree-day when hot water is unknown", EA, "10.0",
     {EA_B: "'0'", EA_G: "'3000'", EA_D: "'21'", EA_H: "'300'"}, "b = 0: all winter gas is heating"))
A(en("a measured hot-water term is taken out of winter gas", EA, "9.3",
     {EA_B: "'10'", EA_G: "'3000'", EA_D: "'21'", EA_H: "'300'"}, "(3000 - 10*21) / 300"))
A(en("never negative", EA, "0.0", {EA_B: "'200'", EA_G: "'3000'", EA_D: "'21'", EA_H: "'300'"},
     "a hot-water estimate larger than the gas cannot make heating negative"))
A(en("no winter degree-days: no heating figure", EA, "None",
     {EA_B: "'0'", EA_G: "'0'", EA_D: "'0'", EA_H: "'0'"}, "division by zero"))

EC = "Energy AC heating per degree-day"
EC_A = "states('input_number.energy_gas_w_a')"
A(en("AC heating electricity per degree-day", EC, "0.3", {EC_A: "'90'", EA_H: "'300'"}, "c = A / H"))
A(en("no winter degree-days: no AC figure", EC, "None", {EC_A: "'0'", EA_H: "'0'"}, "division by zero"))

EY = "Energy heating per m2 year"
EY_A, EY_C = "states('sensor.energy_gas_heating_per_degree_day')", "states('sensor.energy_ac_heating_per_degree_day')"
EY_AREA = "states('input_number.energy_heated_area')"


def ey(name, expect, h="'300'", a="'6.7'", c="'0.3'", b="'0'", finding=""):
    return en(name, EY, expect, {EA_H: h, EY_A: a, EY_C: c, EA_B: b, EY_AREA: "'164.41'"}, finding)


A(ey("annualised to the 3235 K-day Prague normal per m2", "138", finding="(6.7 + 0.3) * 3235 / 164.41"))
A(ey("hot water adds b for every day of the year", "160", b="'10'", finding="+ 10 * 365 / 164.41"))
A(ey("299 winter degree-days: not trusted yet", "None", h="'299'", finding="the one trust condition, from below"))
A(ey("no heating figure: no annual figure", "None", a="'unknown'", finding="unknown is not zero"))

EK = "Energy class"
EK_E = "states('sensor.energy_heating_per_m2_year')"
for _e, _k in (("'42.9'", "A"), ("'43'", "B"), ("'82'", "B"), ("'82.1'", "C"), ("'120'", "C"), ("'120.1'", "D"),
               ("'162'", "D"), ("'162.1'", "E"), ("'205'", "E"), ("'205.1'", "F"), ("'245'", "F"),
               ("'245.1'", "G")):
    A(en("%s kWh/m2 is class %s" % (_e.strip("'"), _k), EK, _k, {EK_E: _e},
         "former vyhlaska 148/2007 apartment-building bands, straddled"))
A(en("no annual figure: not enough data", EK, "not enough data", {EK_E: "'unknown'"},
     "never a letter from two readings"))

EE = "Energy gas estimate"
EE_S, EE_M = "states('input_text.energy_gas_snapshot')", "states('sensor.gas_total')"
EE_CAL, EE_HDD, EE_NOW = ("states('input_number.gas_kwh_per_m3')", "states('input_number.energy_hdd_total')",
                          "as_timestamp(now())")
_SN = '\'{"t": 1000, "m": 6578.678, "h": 100, "n": 5, "a": 0}\''


EE_DAYS, EE_MEAN = "states('input_number.energy_hdd_days')", "states('sensor.energy_outdoor_daily_mean')"
_DAY = 86400


def ee(name, expect, s=_SN, a="'6.7'", b="'0'", hdd="'112'", days="'7'", mean="'5'", now_=1000 + 2 * _DAY,
       finding=""):
    return en(name, EE, expect, {EE_S: s, EE_M: "'6578.678'", EY_A: a, EA_B: b, EE_CAL: "'10.6'",
                                 EE_HDD: hdd, EE_DAYS: days, EE_MEAN: mean, EE_NOW: now_}, finding)


A(ee("degree-days since the reading add heating gas", "6586.263",
     finding="2 days closed, 12 K-d, 2 days elapsed: 6.7 * 12 / 10.6 m3"))
# 2026-11-25 validation: the reading was taken at 23:36; 23 minutes later the 23:59 close added the
# WHOLE day's degree-days, although the meter already held that day's gas. The estimate read 7.6 m3
# high. Degree-days are spread over the closed days and charged for the time actually elapsed.
A(ee("a day closed minutes after the reading counts only the time since", "6579.689",
     hdd="'116'", days="'6'", now_=1000 + _DAY // 10,
     finding="2026-11-25: one closed day of 16 K-d, 0.1 day elapsed: 1.6 K-d, not 16"))
A(ee("before the first close, today's heating is the running daily mean", "6583.735",
     hdd="'100'", days="'5'", mean="'3'", now_=1000 + _DAY // 2,
     finding="2026-11-25: half a day at a 3 C mean is 8 K-d, not nothing"))
A(ee("a 13 C mean is no heating day", "6578.678", hdd="'100'", days="'5'", mean="'13'", now_=1000 + _DAY // 2,
     finding="the 13 C heating-day rule of the degree-day close, straddled"))
A(ee("a 12.9 C mean is a heating day", "6580.606", hdd="'100'", days="'5'", mean="'12.9'",
     now_=1000 + _DAY // 2, finding="6.1 K x 0.5 day"))
A(ee("no daily mean before the first close: no heating added", "6578.678", hdd="'100'", days="'5'",
     mean="'unavailable'", now_=1000 + _DAY // 2, finding="an unknown mean is not a cold one"))
A(ee("and days since the reading add hot water", "6588.15", b="'10'", now_=1000 + 2 * 86400,
     finding="+ 10 * 2 / 10.6 m3"))
A(ee("no snapshot: the last reading", "6578.678", s="''", finding="before the first interval"))
A(ee("no heating figure: the last reading", "6578.678", a="'unknown'", finding="no model, no estimate"))

# The weekly interval (automation 1792300000030)
EGAS = "1792300000030"


def iv(name, expect, has_snap=True, counted=7, cal_days=7, trusted=True, pred=200.0, g=200.0, finding=""):
    return dict(name="energy interval: " + name, automation=EGAS, expr="verdict", expect=expect,
                given=dict(has_snap=has_snap, counted=counted, cal_days=cal_days, trusted=trusted,
                           pred=pred, g=g), subs={}, finding=finding)


A(iv("the first reading only takes a snapshot", "first", has_snap=False, finding="nothing to compare"))
A(iv("a missed 23:59 run inside the interval is a gap", "gap", counted=6,
     finding="review F8: days and degree-days would be short"))
A(iv("an untrusted model counts every interval", "count", trusted=False, g=900.0,
     finding="it cannot judge before it has learned"))
A(iv("within 30 % counts", "count", g=259.0, finding="59 < 60: the relative limit from below"))
A(iv("beyond 30 % and 40 kWh is held out", "flag", g=263.0, finding="review F4: never enters the sums unasked"))
A(iv("beyond 30 % but within 40 kWh counts", "count", pred=100.0, g=135.0,
     finding="review F3: the absolute limit, from below"))
A(iv("beyond both on a small week is held out", "flag", pred=100.0, g=141.0, finding="the absolute limit from above"))
A(iv("a prediction under 50 kWh is never judged", "count", pred=49.0, g=0.0,
     finding="review F3: summer weeks predict little"))
A(iv("a prediction of 50 kWh is judged", "flag", pred=50.0, g=0.0, finding="the floor from above"))

ECAL = "((t_now + 60) | as_datetime | as_local).date() - ((snap.t + 60) | as_datetime | as_local).date()"
A(dict(name="energy interval: a reading at 10:00 to the next week's 10:00 spans 7 runs", automation=EGAS,
       expr="cal_days", expect="7", given={"t_now": 1795597200, "snap": {"t": 1794992400}}, subs={},
       finding="runs at 23:59 between the two readings"))
A(dict(name="energy interval: a reading just after 23:59 starts after that day's run", automation=EGAS,
       expr="cal_days", expect="6", given={"t_now": 1795597200, "snap": {"t": 1795042770}}, subs={},
       finding="the 23:59 of the first day was before the reading"))
A(dict(name="energy interval: a reading just after 23:59 ends after that day's run", automation=EGAS,
       expr="cal_days", expect="8", given={"t_now": 1795647570, "snap": {"t": 1794992400}}, subs={},
       finding="the 23:59 of the last day was before the reading"))
A(dict(name="energy interval: degree-days decide summer or winter", automation=EGAS, expr="target",
       expect="summer", given={"h": 0.0}, subs={}, finding="an interval with no degree-days is hot water"))
A(dict(name="energy interval: any degree-day makes it winter", automation=EGAS, expr="target",
       expect="winter", given={"h": 0.5}, subs={}, finding="a mixed week is heating plus hot water"))
_ACT = "trigger.event.data.action"
A(dict(name="energy interval: Count it counts the week it was sent for", automation=EGAS, expr="count_ok",
       expect="True", given={"pend": '{"id": 1795597200, "g": 1, "d": 7, "h": 80, "a": 2}'},
       subs={_ACT: "'ENERGY_GAS_COUNT_1795597200'"}, finding="review FA1"))
A(dict(name="energy interval: a stale Count it counts nothing", automation=EGAS, expr="count_ok",
       expect="False", given={"pend": '{"id": 1795597200, "g": 1, "d": 7, "h": 80, "a": 2}'},
       subs={_ACT: "'ENERGY_GAS_COUNT_1794992400'"}, finding="review FA1: never a different week"))
A(dict(name="energy interval: Count it with nothing pending counts nothing", automation=EGAS,
       expr="count_ok", expect="False", given={"pend": ""}, subs={_ACT: "'ENERGY_GAS_COUNT_1795597200'"},
       finding="already counted, or replaced"))

# The daily degree-day run (automation 1792300000031)
EDD = "1792300000031"
EDD_M = "states('sensor.energy_outdoor_daily_mean')"
for _m, _x, _f in (("'5'", "14.0", "19 - 5"), ("'12.9'", "6.1", "the 13 C limit from below"),
                   ("'13'", "0", "the 13 C limit: not a heating day"),
                   ("'unavailable'", "0", "an unknown day adds nothing (and is not counted)")):
    A(dict(name="energy degree-days: a day at %s adds %s" % (_m.strip("'"), _x), automation=EDD, expr="add_h",
           expect=_x, given={}, subs={EDD_M: _m}, finding=_f))
EDD_AC, EDD_AC0 = "states('sensor.energy_ac_total')", "states('input_number.energy_ac_at_midnight')"
A(dict(name="energy degree-days: a cold day's AC is heating", automation=EDD, expr="ac_add", expect="3.5",
       given={"cold": True}, subs={EDD_AC: "'123.5'", EDD_AC0: "'120'"}, finding="review FA2"))
A(dict(name="energy degree-days: a warm day's AC is not", automation=EDD, expr="ac_add", expect="0",
       given={"cold": False}, subs={EDD_AC: "'123.5'", EDD_AC0: "'120'"},
       finding="review FA2: cooling in a mixed week stays out"))
A(dict(name="energy degree-days: a meter that went backwards adds nothing", automation=EDD, expr="ac_add",
       expect="0.0", given={"cold": True}, subs={EDD_AC: "'10'", EDD_AC0: "'120'"},
       finding="a replaced or reset meter"))


# The most likely leak (operator 2026-11-23: "show the most likely cause/room"). From the stored
# baselines: the room losing heat >= 2x the flat's median leaks most (structural). A window flagged in
# the last run outranks it: that is something to go and check now.
ES = "Energy leak suspect"
ES_LIST, ES_VERDICT = "states.input_number", "states('input_text.leak_meter_verdict')"
ES_AREA1, ES_AREA2 = "area_name('sensor.climate_temp_' ~ r)", "area_name('sensor.climate_temp_' ~ ns.best)"


def es(name, expect, ks, verdict="'21.11 ... kid1:leakiest'", finding=""):
    lst = [{"entity_id": "input_number.leak_k_" + r, "state": str(v)} for r, v in ks.items()]
    lst.append({"entity_id": "input_number.leak_ach_living_room", "state": "0.3"})  # not a room's heat loss
    return en(name, ES, expect, {ES_LIST: repr(lst), ES_VERDICT: verdict, ES_AREA1: "none", ES_AREA2: "none"},
              finding)


_K21 = {"kid1": 7.1, "bedroom": 3.8, "corridor": 3.7, "living_room": 2.8, "kid2": 2.2, "office": 1.2}
A(es("the room at 2x the flat's median leaks most", "kid1: leaks most (2.2× the flat)", _K21,
     finding="2026-11-21 measured: 7.1 against a median of 3.25"))
A(es("just under 2x: no room stands out", "no room stands out", _K21 | {"kid1": 6.4},
     finding="the threshold straddled from below (2 x 3.25 = 6.5)"))
A(es("exactly 2x leaks most", "kid1: leaks most (2.0× the flat)", _K21 | {"kid1": 6.5},
     finding="the threshold straddled from above"))
A(es("a fresh helper (0) is not a measurement", "not measured yet",
     {"kid1": 7.1, "bedroom": 3.8, "corridor": 0, "living_room": 0, "kid2": 0, "office": 0},
     finding="two measured rooms cannot say which one is odd"))
A(es("a window in the last run outranks the structural leak", "kid2: window left open?", _K21,
     verdict="'23.11 3 h at 2 C. ... kid2:window'", finding="something to check now beats something known"))
A(es("an unmeasured flat says so", "not measured yet", {}, verdict="'unknown'", finding="before the first Away"))


# Window open (operator 2026-11-23). A room aired in the cold loses its moisture toward the outdoor
# level while the rest of the flat keeps it, and its VOC index drops: fresh air. Backtested on
# 11-13..11-23: ratio < 0.75 with VOC < 40 caught the 23.11 airing and a 20-min one on 16.11, and
# nothing else, not even the radiator's on/off sawtooth that fooled a temperature-only rule.
# Both sensors share the template text; only the header naming the room differs.
W_T, W_H = "states('sensor.climate_temp_' ~ room)", "states('sensor.climate_humidity_' ~ room)"
W_V, W_FT, W_FH = "states(voc_e)", "states('sensor.indoor_temperature')", "states('sensor.indoor_humidity')"
W_OT, W_OH = "states('sensor.climate_temp_outdoor')", "state_attr('weather.home', 'humidity')"


# 2026-11-24 operator airing: the detector came on 8 min after the window opened and stayed on after it
# closed (the VOC index recovers slowly), so the 20-min push would have arrived after the window shut.
# The room's Tado valve flags an open window itself (2 min in) and reports the close at once.
W_TW = "states(trv_w)"
W_TAGE = "now().timestamp() - (states[trv_w].last_changed.timestamp() if states[trv_w] is not none else 0)"


def win(title, name, expect, ti="'20'", hi="'45'", voc="'100'", ft="'20'", fh="'40'", ot="'4'", oh="70",
        tw="'off'", tage="99999", finding=""):
    return sensor_case("window %s: %s" % (title.split()[-1] if "bedroom" in title else "kid1", name), expect,
                       {W_T: ti, W_H: hi, W_V: voc, W_FT: ft, W_FH: fh, W_OT: ot, W_OH: oh, W_TW: tw, W_TAGE: tage},
                       finding=finding, sensor=title)


for _title in ("Climate window bedroom", "Climate window " + K1["title"]):
    A(win(_title, "an ordinary closed room", "False", finding="ratio 1.35, VOC 100"))
    A(win(_title, "aired wide open in the cold", "True", hi="'33'", voc="'6'",
          finding="23.11 14:40: ratio 0.5, VOC 6"))
    A(win(_title, "ratio 0.74 with fresh air", "True", hi="'36.3'", voc="'20'", finding="the ratio from below"))
    A(win(_title, "ratio 0.76 with fresh air", "False", hi="'36.6'", voc="'20'", finding="the ratio from above"))
    A(win(_title, "VOC 39 is fresh air", "True", hi="'33'", voc="'39'", finding="the VOC limit from below"))
    A(win(_title, "VOC 40 is not", "False", hi="'33'", voc="'40'",
          finding="dry but stale: the radiator, not a window"))
    A(win(_title, "11.9 C outside is the heating season", "True", hi="'33'", voc="'6'", ot="'11.9'", oh="40",
          finding="the season from below (dry outdoor air, so only the 12 C limit decides)"))
    A(win(_title, "12 C outside is not", "False", hi="'33'", voc="'6'", ot="'12'", oh="40",
          finding="in mild weather airing is no loss and no news"))
    A(win(_title, "outdoor air nearly as moist as the flat says nothing", "False", hi="'33'", voc="'6'",
          oh="96.2", finding="excess 0.79 g/m3: the ratio is noise"))
    A(win(_title, "just enough moisture difference to judge", "True", hi="'33'", voc="'6'", oh="95.8",
          finding="excess 0.82 g/m3: the limit from above"))
    A(win(_title, "an unreachable air-quality sensor is not a window", "False", hi="'33'", voc="'unavailable'",
          finding="unknown is not open"))
    A(win(_title, "the valve's own open-window flag is an opening", "True", tw="'on'",
          finding="2026-11-24: the valve saw it at 2 min, the air at 8"))
    A(win(_title, "the valve's close ends it although the air still looks aired", "False", hi="'33'", voc="'6'",
          tw="'off'", tage="600", finding="2026-11-24: the VOC index stays low long after the window shuts"))
    A(win(_title, "29 min after the valve's close the air still decides nothing", "False", hi="'33'", voc="'6'",
          tw="'off'", tage="1740", finding="the hold from below"))
    A(win(_title, "31 min after the valve's close the air decides again", "True", hi="'33'", voc="'6'",
          tw="'off'", tage="1860", finding="the hold from above: a second opening the valve misses"))
    A(win(_title, "an unreachable valve leaves the air to decide", "True", hi="'33'", voc="'6'",
          tw="'unavailable'", tage="60", finding="unknown is neither open nor closed"))
    # Review #53 F3: every input, not only the VOC, must fail closed. Each case is an airing that
    # reads True with all seven inputs present (the 23.11 case above).
    for _k, _sub in (("ti", "room temperature"), ("hi", "room humidity"), ("ft", "flat temperature"),
                     ("fh", "flat humidity"), ("ot", "outdoor temperature"), ("oh", "outdoor humidity")):
        _kw = dict(hi="'33'", voc="'6'")
        _kw[_k] = "None" if _k == "oh" else "'unavailable'"
        A(win(_title, "a missing %s is not a window" % _sub, "False", finding="review #53 F3", **_kw))
    # Review #53 F4: a room drier than the outdoor air made the ratio negative, which passed `< 0.75`
    # unconditionally; with a VOC baseline reset below 40 that was an open window in a closed room.
    # Airing brings the room TO the outdoor moisture, not below it: 0.5 g/m3 under is sensor accuracy.
    A(win(_title, "a radiator-dried room under damp outdoor air is not a window", "False", hi="'25'",
          fh="'45'", voc="'10'", oh="96", finding="review #53 F4: a = 4.3, outdoor 6.1 g/m3"))
    A(win(_title, "0.44 g/m3 under the outdoor air is sensor accuracy", "True", hi="'23.2'", voc="'6'",
          finding="review #53 F4: the tolerance from inside"))
    A(win(_title, "0.56 g/m3 under is not an airing", "False", hi="'22.5'", voc="'6'",
          finding="review #53 F4: the tolerance from outside"))


# CO2 window detector (operator 2026-11-28): the living room and office have CO2 meters but no VOC
# sensor, and the moisture ratio is useless there (backtest 14-28.11: 137 hits in the living room,
# a room merely drier than the flat). Fresh air shows as CO2 falling fast: at least 100 ppm, and at
# least 30 % of the excess over outdoor air (420 ppm), below the 20-minute maximum (a statistics
# helper). A person leaving decays the excess by ~15 % in 20 min; an open window by most of it.
# Counts airing hours only: not wired to the AC loop or the push until logged airings confirm it.
CW_C, CW_M = "states('sensor.climate_co2_' ~ room)", "states('sensor.climate_co2_' ~ room ~ '_max_20min')"
CW_OT, CW_TW = "states('sensor.climate_temp_outdoor')", "states(trv_w)"


def cw(title, name, expect, c="'800'", m="'800'", ot="'4'", tw="'off'", finding=""):
    return sensor_case("co2 window %s: %s" % (title[len("Climate CO2 window "):], name), expect,
                       {CW_C: c, CW_M: m, CW_OT: ot, CW_TW: tw}, finding=finding, sensor=title)


for _title in ("Climate CO2 window living room", "Climate CO2 window office"):
    A(cw(_title, "a steady room", "False", finding="no fall, no window"))
    A(cw(_title, "aired: 900 to 600 ppm", "True", m="'900'", c="'600'", finding="26.11 20:07: 791 to 557"))
    A(cw(_title, "a 99 ppm fall is noise", "False", m="'700'", c="'601'", finding="the fall from below"))
    A(cw(_title, "a 100 ppm fall at 36 % of the excess counts", "True", m="'700'", c="'600'",
         finding="the fall from above"))
    A(cw(_title, "172 of 580 ppm excess is someone leaving", "False", m="'1000'", c="'828'",
         finding="the share from below: 30 % is 174"))
    A(cw(_title, "176 of 580 ppm excess is fresh air", "True", m="'1000'", c="'824'",
         finding="the share from above"))
    A(cw(_title, "11.9 C outside is the heating season", "True", m="'900'", c="'600'", ot="'11.9'",
         finding="the season from below"))
    A(cw(_title, "12 C outside is not", "False", m="'900'", c="'600'", ot="'12'",
         finding="in mild weather airing is no loss and no news"))
    A(cw(_title, "the valve's own window flag is an opening", "True", tw="'on'",
         finding="the thermostat saw it, whatever the air says"))
    for _k, _sub in ((CW_C, "CO2 reading"), (CW_M, "20-minute maximum"), (CW_OT, "outdoor temperature")):
        _kw = {CW_C: "'600'", CW_M: "'900'", CW_OT: "'4'", CW_TW: "'off'"}
        _kw[_k] = "'unavailable'"
        A(sensor_case("co2 window %s: no %s is not a window" % (_title[len("Climate CO2 window "):], _sub),
                      "False", _kw, finding="unknown is not open", sensor=_title))


# Review #53 F1: the detector fails closed when an input is missing, which is right for the decision
# and silent for the household: Aired most would say "none this week" with the detector blind. This
# names that state; Aired most reads it.
WB = "Climate window detector blind"
for _k, _sub in ((None, "every input present"), (W_T, "room temperature"), (W_H, "room humidity"),
                 (W_V, "VOC index"), (W_FT, "flat temperature"), (W_FH, "flat humidity"),
                 (W_OT, "outdoor temperature"), (W_OH, "outdoor humidity")):
    _subs = {W_T: "'20'", W_H: "'45'", W_V: "'100'", W_FT: "'20'", W_FH: "'40'", W_OT: "'4'", W_OH: "70"}
    if _k:
        _subs[_k] = "None" if _k == W_OH else "'unavailable'"
    A(sensor_case("window detector: %s" % ("blind without the " + _sub if _k else _sub),
                  "True" if _k else "False", _subs, finding="review #53 F1", sensor=WB))


# Dashboard readouts (operator 2026-11-24): the air-change rate with a word a child can read, the room
# aired most (window detector) kept apart from the room that leaks most (Away meter), and heating
# energy per m2 over 24 h and 7 days from the gas model + measured AC.
ER = "Energy air change rating"
ER_V = "states('input_number.leak_ach_living_room')"
for _v, _w, _f in (("'0'", "not measured", "a fresh helper"), ("'0.19'", "low", "from below 0.2"),
                   ("'0.2'", "moderate", "0.2 from above"), ("'0.3'", "moderate", "21.11 measured"),
                   ("'0.49'", "moderate", "from below 0.5"), ("'0.5'", "high", "0.5 from above"),
                   ("'0.99'", "high", "from below 1"), ("'1'", "very high", "1 from above"),
                   ("'unavailable'", "not measured", "unknown is not a rate")):
    A(en("air change %s/h reads %s" % (_v.strip("'"), _w), ER, _w, {ER_V: _v}, _f))

EM = "Energy aired most"
EM_LIST, EM_AREA = "states.sensor", "area_name('sensor.climate_temp_' ~ ns.best)"
EM_BLIND = "is_state('binary_sensor.climate_window_detector_blind', 'on')"


def em(name, expect, hours, finding, blind="false"):
    lst = [{"entity_id": "sensor.airing_%s_last_7_days" % r, "state": str(h)} for r, h in hours.items()]
    lst.append({"entity_id": "sensor.energy_ac_last_7_days", "state": "40"})   # not an airing counter
    return en(name, EM, expect, {EM_LIST: repr(lst), EM_AREA: "none", EM_BLIND: blind}, finding)


A(em("a blind detector says so instead of 'none'", "detector blind", {"kid1": 0.0}, "review #53 F1",
     blind="true"))
# Operator 2026-11-28 overrides review #53 F1's "a half-blind week is not the week": one room's VOC
# sensor dropping out at 23:39 hid the airings counted at 22:23 and 23:46. Hours counted stay shown,
# flagged, so a dead sensor never erases a week.
A(em("a blind detector still names hours it counted, flagged", "kid1: 3.2 h this week (detector blind)",
     {"kid1": 3.2}, "2026-11-28: yesterday's airings vanished behind 'detector blind'", blind="true"))


A(em("the room with the most window hours", "kid1: 3.2 h this week", {"kid1": 3.2, "bedroom": 0.4},
     "ventilation, kept apart from the leak"))
A(em("half an hour is the least worth naming", "bedroom: 0.5 h this week", {"kid1": 0.0, "bedroom": 0.5},
     "from above"))
A(em("under half an hour: none", "none this week", {"kid1": 0.49, "bedroom": 0.1}, "from below"))
A(em("no counters yet", "none this week", {}, "before the first airing"))

E24 = "Energy heating per m2 last 24h"
E24_M, E24_AC = "states('sensor.energy_outdoor_daily_mean')", "states('sensor.energy_ac_last_24h')"


def e24(name, expect, a="'4.95'", m="'5'", b="'0'", ac="'2'", finding=""):
    return en(name, E24, expect, {EY_A: a, E24_M: m, EA_B: b, E24_AC: ac, EY_AREA: "'164.41'"}, finding)


A(e24("a cold day: gas from degree-days plus the AC, per m2", "0.43", finding="(4.95*14 + 2) / 164.41"))
A(e24("12.9 C is still a heating day", "0.2", m="'12.9'", finding="the 13 C limit from below"))
A(e24("13 C is not: only hot water and AC", "0.01", m="'13'", finding="the 13 C limit from above"))
A(e24("hot water counts every day", "0.07", m="'13'", b="'10'", finding="(10 + 2) / 164.41"))
A(e24("a meter that went backwards adds nothing", "0.42", ac="'-5'", finding="AC change clamped at 0"))
A(e24("no gas model yet: no figure", "None", a="'unknown'", finding="never a number from nothing"))

E7 = "Energy heating per m2 last 7 days"
E7_M, E7_AC = "states('sensor.energy_outdoor_weekly_mean')", "states('sensor.energy_ac_last_7_days')"


def e7(name, expect, a="'4.95'", m="'6'", b="'0'", ac="'20'", finding=""):
    return en(name, E7, expect, {EY_A: a, E7_M: m, EA_B: b, E7_AC: ac, EY_AREA: "'164.41'"}, finding)


A(e7("a cold week: seven days of degree-days plus the AC", "2.86", finding="(4.95*7*13 + 20) / 164.41"))
A(e7("a week averaging 13 C: hot water and AC only", "0.55", m="'13'", b="'10'", finding="(70 + 20) / 164.41"))
A(e7("no gas model yet: no figure", "None", a="'unknown'", finding="never a number from nothing"))
# Review #53 F6: the week's degree-days come from the week's mean, not from seven daily cut-offs. A
# mixed week (4 days at 6 C, 3 at 16 C: mean 10.29) is counted as 61 K.d where the daily rule gives
# 52: 1.96 kWh/m2 against 1.69, a 16 % over-read. Pinned here so the bound is a tested number; the
# readout is labelled an estimate and the class never reads it (docs/heating-energy-rating.md).
A(e7("a mixed week over-reads by the days above 13 C", "1.96", m="'10.29'",
     finding="review #53 F6: (4.95*7*8.71 + 20) / 164.41; the daily rule would give 1.69"))

# Every push to a phone is kept in Home Assistant's notification panel (operator 2026-11-24): tapping
# an iOS push opens the app without the text, and the operator wants it back, dismissed by hand.
# Mirrored from the call_service event, so no automation that sends a push has to change.
MIRROR = "1792300000060"


def mir(name, expr, expect, d, finding=""):
    return dict(name="push mirror: " + name, automation=MIRROR, expr=expr, expect=expect, given={"d": d},
                subs={}, finding=finding)


_P = {"title": "Every phone has left", "message": "Still on: Corridor Light.", "data": {"tag": "lights-left-on"}}
A(mir("an ordinary push is shown", "kind", "show", _P))
A(mir("its id follows the tag, so a re-send replaces it", "nid", "push_lights_left_on", _P,
      finding="the same tag on both phones is one entry, not two"))
A(mir("without a tag the title names it", "nid", "push_mould_risk_bedroom",
      {"title": "Mould risk: Bedroom", "message": "x"}))
A(mir("no tag and no title still has an id", "nid", "push_note", {"message": "x"}))
A(mir("clearing a push dismisses its copy", "kind", "clear",
      {"message": "clear_notification", "data": {"tag": "lights-left-on"}},
      finding="a push the automation withdrew is not left behind in HA"))
A(mir("a clear without a tag removes nothing", "kind", "skip", {"message": "clear_notification"},
      finding="nothing to match it to"))
A(mir("a location request is not a message", "kind", "skip", {"message": "request_location_update"}))
A(mir("an empty message is not shown", "kind", "skip", {"title": "x", "message": ""}))
A(mir("the buttons are listed under the text", "body",
      "Still on: Corridor Light.\n\n*On the phone:* Arm Away · Turn the lights off",
      {"title": "t", "message": "Still on: Corridor Light.",
       "data": {"actions": [{"action": "A", "title": "Arm Away"}, {"action": "B", "title": "Turn the lights off"}]}},
      finding="the copy says what the phone offered"))
A(mir("a push without buttons is just its text", "body", "Still on: Corridor Light.", _P))

# Frost setback (operator 2026-11-24): a night setback cools the walls, and a cold corner whose
# surface passes 80 % RH grows mould. Each room's night target is raised, never lowered, until the
# coldest outdoor hour of the next 12 h keeps its wall surface below 80 % RH, and never above the day
# target. The surface temperature is te + (ti - te) / f; f = 1 / fRsi is the room's mould factor
# (1.43 = fRsi 0.7, the kid 1 corner 1.67 = fRsi 0.6), the same as its Mould Indicator helper.
NT_N, NT_D = "states('input_number.climate_target_night_' ~ room)", "states('input_number.climate_target_day_' ~ room)"
NT_OM = "states('input_number.climate_outdoor_min_12h')"
NT_PREV = "this.state"
# (title, label, hi just safe, hi just unsafe, hi holding a raised 19.5, hi releasing it)
NT_ROOMS = (("Climate night target living room", "living", 44.0, 44.5, 44.0, 43.8),
            ("Climate night target office", "office", 44.0, 44.5, 44.0, 43.8),
            ("Climate night target bedroom", "bedroom", 44.0, 44.5, 44.0, 43.8),
            ("Climate night target " + K1["title"], "kid1", 37.5, 38.0, 37.6, 37.4),
            ("Climate night target " + K2["title"], "kid2", 44.0, 44.5, 44.0, 43.8))


def nt(title, label, name, expect, n="'19'", d="'23'", ti="'21'", hi="'40'", ot="'0'", om="'-5'", prev="'unknown'",
       finding=""):
    return sensor_case("night target %s: %s" % (label, name), expect,
                       {NT_N: n, NT_D: d, W_T: ti, W_H: hi, W_OT: ot, NT_OM: om, NT_PREV: prev},
                       finding=finding, sensor=title)


for _title, _l, _lo, _hi, _hold, _rel in NT_ROOMS:
    # Review #55 F1: one per cent of humidity moves the requirement by about half a degree, so a
    # jittery humidity sensor would flip the target, and each flip can cost a Tado call. A raised
    # target is held until the requirement falls 0.75 below it (three quarters of a step).
    A(nt(_title, _l, "a raised target holds while the need is within 0.75", "19.5", hi="'%s'" % _hold,
         prev="'19.5'", finding="review #55 F1: requirement 18.77-18.83 against a held 19.5"))
    A(nt(_title, _l, "and is released when the need falls 0.75 below it", "19.0", hi="'%s'" % _rel,
         prev="'19.5'", finding="review #55 F1: requirement 18.67-18.70: the step is released"))
    A(nt(_title, _l, "a rising need is never held back", "23.0", hi="'55'", om="'-10'", prev="'19.5'",
         finding="the hold only delays a fall"))
    A(nt(_title, _l, "a held value never exceeds a lowered day target", "21.0", d="'21'", hi="'55'", om="'-10'",
         prev="'23'", finding="the operator's day target still caps a held value"))
    A(nt(_title, _l, "a held value never undercuts a raised operator night", "20.0", n="'20'", hi="'%s'" % _hold,
         prev="'19.5'", finding="the operator's night still floors"))
    A(nt(_title, _l, "mild and dry: the operator's night", "19.0", hi="'30'", ot="'5'", om="'2'",
         finding="no raise where the wall is safe: the setback's saving is kept"))
    A(nt(_title, _l, "just safe at the coldest hour: unchanged", "19.0", hi="'%s'" % _lo,
         finding="the 80 % surface limit from below"))
    A(nt(_title, _l, "just unsafe: raised to the next half degree", "19.5", hi="'%s'" % _hi,
         finding="the 80 % surface limit from above; half degrees, so the valves are not chased"))
    A(nt(_title, _l, "the measured outdoor colder than the forecast counts", "19.5", hi="'%s'" % _hi,
         ot="'-5'", om="'0'", finding="a stale or optimistic forecast cannot hide a cold night"))
    A(nt(_title, _l, "frost and humid: no colder than the day target", "23.0", hi="'55'", om="'-10'",
         finding="the cap: never warmer at night than by day"))
    A(nt(_title, _l, "a night set above the day target is never lowered", "22.0", n="'22'", d="'21'",
         hi="'55'", om="'-10'", finding="raise only: the operator's value is a floor"))
    A(nt(_title, _l, "no forecast yet: the measured outdoor alone", "19.0", hi="'%s'" % _hi, om="'unknown'",
         ot="'5'", finding="a missing forecast is not frost; the measured 5 C is mild"))
    A(nt(_title, _l, "no outdoor reading at all: the operator's night", "19.0", hi="'55'", ot="'unavailable'",
         om="'unknown'", finding="nothing to judge: no raise"))
    A(nt(_title, _l, "room humidity unknown: the operator's night", "19.0", hi="'unavailable'", om="'-10'",
         finding="no raise from nothing"))
    A(nt(_title, _l, "the night target itself unknown: no figure", "None", n="'unavailable'",
         finding="the consumers keep their own fallback"))

# The coldest hour ahead: hourly, the next 12 forecast hours' minimum is kept for the night targets.
FROST_FC = "1792300000050"
FC_OUT = "states('sensor.climate_temp_outdoor')"


def fc(name, expect, temps, out="'1.2'", finding=""):
    given = {"fc": {"weather.home": {"forecast": [{"temperature": t} for t in temps]}}} if temps is not None \
        else {"fc": "failed"}
    return dict(name="frost forecast: " + name, automation=FROST_FC, expr="lo", expect=expect, given=given,
                subs={FC_OUT: out}, finding=finding)


A(fc("the coldest of the next 12 hours", "-5.4", [-2.5, -2.3, -1.1, 0.4, 1.6, -3.1, -3.9, -4.3, -4.6, -5.4, -4.7, -4.9],
     finding="tonight's forecast, 24.11"))
A(fc("the 13th hour does not count", "-2.0", [-1.0] * 11 + [-2.0, -9.0], finding="the window is 12 h"))
A(fc("a short forecast is not trusted: the measured outdoor", "1.2", [-8.0] * 5,
     finding="fewer than 6 hours: a truncated answer"))
A(fc("six hours is enough", "-8.0", [-8.0] * 6, finding="the limit from above"))
A(fc("a failed call: the measured outdoor", "1.2", None, finding="continue_on_error leaves no forecast"))

# The bathroom's mould figure is a template, not a Mould Indicator helper: a helper inherits the
# device of the sensor it reads, the bathroom's sensor sits in a Magic Areas room, and Magic Areas
# would average a wall humidity into the room's air humidity (lint C20 caught it). Same physics as
# the helper: surface at to + (ti - to) / f, humidity there from the room's vapour pressure.
MB = "Climate mould bathroom"
MB_T, MB_H = "states('sensor.bathroom_climate_temperature')", "states('sensor.bathroom_climate_humidity')"


def mb(name, expect, ti="'22.3'", hi="'38.3'", ot="'0.3'", finding=""):
    return sensor_case("bathroom mould: " + name, expect, {MB_T: ti, MB_H: hi, W_OT: ot}, finding=finding,
                       sensor=MB)


A(mb("today: the helper's own figure", "58", finding="the Mould Indicator read 58 % on 24.11"))
A(mb("a humid bathroom in frost", "90", ti="'22'", hi="'54'", ot="'-5'", finding="surface 13.9 C"))
A(mb("saturation is 100, not more", "100", ti="'20'", hi="'90'", ot="'-10'",
     finding="above 100 means condensation; the figure stops at 100"))
A(mb("no outdoor reading: no figure", "None", ot="'unavailable'", finding="never a number from nothing"))
A(mb("no room humidity: no figure", "None", hi="'unknown'", finding="never a number from nothing"))

# Leaderboards (operator 2026-11-24): every room ranked, not only the leader. Leaks: each room's Away
# cooling rate against the flat's median room; a room the last run flagged as a window says so.
# Airing: hours each detector room was aired this week.
LR = "Energy leak ranking"
LR_LIST, LR_VERDICT = "states.input_number", "states('input_text.leak_meter_verdict')"
LR_AREA = "area_name('sensor.climate_temp_' ~ r)"


def lr(name, expect, ks, verdict="'ok'", finding=""):
    lst = [{"entity_id": "input_number.leak_k_%s" % r, "state": str(k)} for r, k in ks.items()]
    lst.append({"entity_id": "input_number.climate_away_min", "state": "16"})   # not a leak rate
    return en(name, LR, expect, {LR_LIST: repr(lst), LR_VERDICT: verdict, LR_AREA: "none"}, finding)


_K = {"kid1": 7.1, "bedroom": 3.8, "corridor": 3.7, "living_room": 2.8, "kid2": 2.2, "office": 1.2}
A(lr("every measured room, leakiest first, against the median", 
     "kid1 2.2× · bedroom 1.2× · corridor 1.1× · living_room 0.9× · kid2 0.7× · office 0.4×", _K,
     finding="the 21.11 Away run; median 3.25"))
A(lr("a room never measured is left out", "a 1.5× · b 1.0× · c 0.5×", {"a": 3, "b": 2, "c": 1, "d": 0},
     finding="a fresh helper is 0, not a tight room"))
A(lr("two rooms are not a ranking", "not measured yet", {"a": 3, "b": 2}, finding="as Leaks most"))
A(lr("a window in the last run is named in place", "a 1.5× (window?) · b 1.0× · c 0.5×", {"a": 3, "b": 2, "c": 1},
     verdict="'a:window'", finding="ventilation is not structure"))

AR = "Energy airing ranking"


def ar(name, expect, hours, blind="false", finding=""):
    lst = [{"entity_id": "sensor.airing_%s_last_7_days" % r, "state": str(h)} for r, h in hours.items()]
    lst.append({"entity_id": "sensor.energy_ac_last_7_days", "state": "40"})   # not an airing counter
    return en(name, AR, expect, {EM_LIST: repr(lst), LR_AREA: "none", EM_BLIND: blind}, finding)


A(ar("every detector room, most aired first", "bedroom 0.3 h · kid1 0.0 h", {"kid1": 0.0, "bedroom": 0.27},
     finding="24.11: the bedroom's morning airing"))
A(ar("no counters yet", "none this week", {}, finding="before the first airing"))
A(ar("a blind detector keeps the counted hours", "bedroom 3.0 h · kid1 0.2 h", {"bedroom": 3.0, "kid1": 0.23},
     blind="true", finding="2026-11-28: yesterday's airings vanished behind 'detector blind'"))
A(ar("a blind detector with nothing counted says so", "detector blind", {"bedroom": 0.0}, blind="true",
     finding="review #53 F1"))

# Pre-heat on the way home (operator 2026-11-24). After a long Away the house sits at the pet floor and
# takes hours to recover. When someone heads home and is within 15 km, the Away floor gives way, both
# for the radiators and the AC, so the house warms while they travel.
ARR = "is_state('input_boolean.climate_arrival_preheat', 'on')"
AWAY_ON = "is_state('alarm_control_panel.home','armed_away')"
NOWTS = "now().timestamp()"
for _arr, _want in (("false", "True"), ("true", "False")):
    A(case("the AC's Away floor %s while someone heads home" % ("holds" if _want == "True" else "gives way"),
           "away", _want, {"away_stamp": 1000}, subs={AWAY_ON: "true", NOWTS: "10000", ARR: _arr},
           finding="2026-11-24: pre-heat on the way home"))
    A(rcase("the radiators' Away floor %s while someone heads home" % ("holds" if _want == "True" else "gives way"),
            "away", _want, {}, "2026-11-24: pre-heat on the way home",
            subs={AWAY_ON: "true", NOWTS: "10000",
                  "state_attr('input_datetime.climate_away_since','timestamp')": "1000", ARR: _arr}))

PRE = "1792300000070"
PRE_AWAY = "is_state('alarm_control_panel.home', 'armed_away')"
PRE_SINCE = "state_attr('input_datetime.climate_away_since', 'timestamp')"
PRE_D, PRE_DIR = "states('sensor.home_nearest_distance')", "states('sensor.home_nearest_direction_of_travel')"
PRE_HEAT = "is_state('input_select.climate_house_mode', 'heat')"
PRE_ON = "is_state('input_boolean.climate_arrival_preheat', 'on')"
PRE_ON_SINCE = "as_timestamp(states.input_boolean.climate_arrival_preheat.last_changed, 0)"
PRE_DIR_SINCE = "as_timestamp(states.sensor.home_nearest_direction_of_travel.last_changed, 0)"


def pre(name, expr, expect, away="true", gone="7300", d="'12000'", dr="'towards'", heat="true", on="false",
        on_for="60", dr_for="60", finding=""):
    subs = {PRE_AWAY: away, NOWTS: "100000", PRE_D: d, PRE_ON: on, PRE_DIR: dr}
    if expr == "start":
        subs.update({PRE_SINCE: str(100000 - int(gone)), PRE_HEAT: heat})
    else:
        subs.update({PRE_ON_SINCE: str(100000 - int(on_for)), PRE_DIR_SINCE: str(100000 - int(dr_for))})
    return dict(name="arrival pre-heat: " + name, automation=PRE, expr=expr, expect=expect, given={},
                subs=subs, finding=finding)


A(pre("heading home 12 km out after a long Away starts it", "start", "True", finding="the case it exists for"))
A(pre("15.1 km is still too far", "start", "False", d="'15100'", finding="the distance from above"))
A(pre("14.9 km is close enough", "start", "True", d="'14900'", finding="the distance from below"))
A(pre("driving away does not start it", "start", "False", dr="'away_from'", finding="only towards home"))
A(pre("standing still does not start it", "start", "False", dr="'stationary'", finding="a stop near home is not a return"))
A(pre("a short Away does not need it", "start", "False", gone="7100", finding="2 h from below: the house is still warm"))
A(pre("two hours Away does", "start", "True", gone="7300", finding="2 h from above"))
A(pre("not outside the heating season", "start", "False", heat="false", finding="nothing to recover in summer"))
A(pre("not when nobody is Away", "start", "False", away="false", finding="only Away has a floor to lift"))
A(pre("an unknown distance does not start it", "start", "False", d="'unknown'", finding="no number, no trip"))
A(pre("already on: not started twice", "start", "False", on="true", finding="one push per trip"))
A(pre("arriving ends it", "stop", "True", on="true", away="false", finding="welcome home takes over"))
A(pre("turning back past 25 km ends it", "stop", "True", on="true", d="'25100'", dr="'away_from'",
      finding="a trip home that did not happen"))
A(pre("24.9 km on the way does not end it", "stop", "False", on="true", d="'24900'", finding="the limit from below"))
A(pre("two hours without arriving ends it", "stop", "True", on="true", on_for="7300", finding="a stale pre-heat"))
A(pre("an hour into the trip it holds", "stop", "False", on="true", on_for="3600", finding="the time limit from below"))
A(pre("nothing to stop when it is off", "stop", "False", on="false", away="false"))
# 2026-11-26: Away 13:15-17:06. The nearest phone sat ~3 km out all afternoon, drove past at 0.6-1.5 km
# (15:16-15:18, 'towards') and went back to 3.6 km. Pre-heat ran 1 h 50 min for nobody, and ended the leak
# meter's run. Within 25 km only arrival or 2 h stopped it. Now: heading away for 5 minutes ends it.
A(pre("a drive-past heading away for 5 minutes ends it", "stop", "True", on="true", d="'2242'", dr="'away_from'",
      dr_for="310", on_for="480", finding="2026-11-26: the drive-past heated the flat for 1 h 50 min"))
A(pre("4.8 minutes heading away does not", "stop", "False", on="true", d="'2242'", dr="'away_from'",
      dr_for="290", on_for="480", finding="the 5 min from below: a bend in the road is not a turn back"))
A(pre("a long stop on the way does not end it", "stop", "False", on="true", d="'3600'", dr="'stationary'",
      dr_for="3000", on_for="3600", finding="only heading away ends it, not traffic or a shop"))

# Corner probe (operator 2026-11-24): a thermometer in the kid 1 room's coldest corner measures what the
# wall model assumed. fRsi = (corner - outdoor) / (room - outdoor); the night target and the mould
# figure assumed 0.6 there. Meaningful only when the room is well above the outdoor temperature.
FR = "Climate corner fRsi " + K1["title"]
FR_P = "states(probe)"


def fr(name, expect, tc="'15.7'", ti="'20.3'", ot="'4.2'", finding=""):
    return sensor_case("corner fRsi: " + name, expect, {FR_P: tc, W_T: ti, W_OT: ot}, finding=finding, sensor=FR)


A(fr("the first reading in place", "0.71", finding="24.11: 15.7 C corner, 20.3 C room, 4.2 C outside"))
A(fr("an 8.1 C difference is enough to judge", "0.78", tc="'10.5'", ti="'12.3'", ot="'4.2'",
     finding="the difference from above: 6.3 / 8.1"))
A(fr("a 7.9 C difference is not", "None", tc="'10.5'", ti="'12.1'", ot="'4.2'",
     finding="mild weather: the ratio is noise"))
A(fr("a corner warmer than the room is not a wall reading", "None", tc="'21'", ti="'20.3'",
     finding="sun on the probe, or a hand"))
A(fr("no probe reading, no figure", "None", tc="'unavailable'", finding="never a number from nothing"))

# Hot water off while away (operator 2026-11-24): the Tado tank keeps itself hot for an empty flat.
# After 6 h of Away it is switched off, and back on (its schedule) when someone heads home, the arrival
# pre-heat starts, or the alarm leaves Away. Off for more than 48 h: two hours at 65 C first, the
# temperature of the weekly legionella cycle, because water left lukewarm for days is the risk.
DHW = "1792300000080"
D_AWAY = "is_state('alarm_control_panel.home', 'armed_away')"
D_SINCE = "state_attr('input_datetime.climate_away_since', 'timestamp')"
D_MODE = "is_state('water_heater.hot_water_hot_water', 'auto')"
D_PAUSED = "is_state('input_boolean.house_hot_water_paused', 'on')"
D_PRE = "is_state('input_boolean.climate_arrival_preheat', 'on')"
D_D, D_DIR = "states('sensor.home_nearest_distance')", "is_state('sensor.home_nearest_direction_of_travel', 'towards')"
D_PAUSED_AT = "state_attr('input_datetime.house_hot_water_paused_at', 'timestamp')"


def dhw(name, expr, expect, away="true", gone="21700", auto="true", paused="false", pre="false", d="'40000'",
        towards="false", off_for="3600", finding=""):
    if expr == "pause":
        subs = {"now().timestamp()": "1000000", D_AWAY: away, D_SINCE: str(1000000 - int(gone)), D_MODE: auto,
                D_PAUSED: paused}
    elif expr == "restore":
        subs = {D_PAUSED: paused, D_AWAY: away, D_PRE: pre, D_D: d, D_DIR: towards}
    else:
        subs = {"now().timestamp()": "1000000", D_PAUSED_AT: str(1000000 - int(off_for))}
    return dict(name="hot water away: " + name, automation=DHW, expr=expr, expect=expect, given={}, subs=subs,
                finding=finding)


A(dhw("six hours Away switches it off", "pause", "True", finding="the case it exists for"))
A(dhw("5 h 55 min is not yet", "pause", "False", gone="21300", finding="6 h from below: a day out is not a trip"))
A(dhw("not while someone is home", "pause", "False", away="false"))
A(dhw("a tank the operator set by hand is left alone", "pause", "False", auto="false",
      finding="only the schedule ('auto') is ours to pause"))
A(dhw("not paused twice", "pause", "False", paused="true"))
A(dhw("coming home restores it", "restore", "True", paused="true", away="false"))
A(dhw("the arrival pre-heat restores it", "restore", "True", paused="true", pre="true"))
A(dhw("heading home within 15 km restores it", "restore", "True", paused="true", d="'14900'", towards="true",
      finding="also outside the heating season, when the pre-heat does not run"))
A(dhw("15.1 km out is not yet", "restore", "False", paused="true", d="'15100'", towards="true",
      finding="the distance from above"))
A(dhw("near home but driving away is not a return", "restore", "False", paused="true", d="'5000'"))
A(dhw("nothing to restore that HA did not pause", "restore", "False", paused="false", away="false",
      finding="a tank switched off by hand stays off"))
A(dhw("off just over 48 h: a 65 C cycle first", "shock", "True", off_for="172900",
      finding="the legionella limit from above"))
A(dhw("off just under 48 h: straight back to the schedule", "shock", "False", off_for="172700",
      finding="the limit from below; the weekly cycle still runs on its day"))

# The hot hold survives a restart (2026-11-26). The two hours at 65 C used to be a `delay` inside the
# run: a restart during it ended the run before the tank went back to 'auto', with the pause flag
# already cleared, so the tank stayed at 65 C. The end of the hold is now a stamp
# (input_datetime.house_hot_water_hot_until) with a flag (input_boolean.house_hot_water_hot_hold),
# and `release` is evaluated at start and every 15 min.
D_HOLD = "is_state('input_boolean.house_hot_water_hot_hold', 'on')"
D_UNTIL = "state_attr('input_datetime.house_hot_water_hot_until', 'timestamp')"


def dhw_rel(name, expect, hold="true", left="-1", finding=""):
    subs = {"now().timestamp()": "1000000", D_HOLD: hold, D_UNTIL: str(1000000 + int(left))}
    return dict(name="hot water away: " + name, automation=DHW, expr="release", expect=expect, given={},
                subs=subs, finding=finding)


A(dhw_rel("the hold ends at its stamp", "True", left="0", finding="the end from above"))
A(dhw_rel("one second before the stamp it holds", "False", left="1", finding="the end from below"))
A(dhw_rel("a hold missed during a restart is ended late", "True", left="-5400",
          finding="the restart case: HA came back after the stamp"))
A(dhw_rel("no hold, nothing to end", "False", hold="false", left="-5400",
          finding="an old stamp alone never touches the tank"))


# 2026-11-28 phone room fingerprint (shadow only): Bermuda names the nearest proxy, and five rooms
# have none, so it calls the bedroom "Closet" and both bathrooms "Corridor". The matcher reads the
# phone's distance to every proxy: a room's own proxy within 2 m names that room; otherwise the
# nearest walk fingerprint (log distance) does. Fewer than two proxies hearing the phone is no room.
FP = "Presence room fingerprint vadim"
_FPP = "states('sensor.vadim_s_iphone_distance_to_%s')"
FP_READS = [_FPP % "closet_bt_proxy", "states('%s')" % _RM["kid1"]["ble_dist_vadim"],
            _FPP % "livingroom_br_proxy", _FPP % "office_bt_proxy", _FPP % "corridor_bt_proxy",
            _FPP % "geiger_counter_ble_proxy"]


def fpc(name, expect, metres, finding=""):
    """metres: closet, kid-1 room, living room, office, corridor, Geiger; None = not heard."""
    subs = {r: "'unavailable'" if m is None else "'%s'" % m for r, m in zip(FP_READS, metres)}
    return sensor_case("fingerprint: " + name, expect, subs, finding=finding, sensor=FP)


_BED = [4.3, 27.1, 21.1, 29.3, 9.3, None]
_SOFA = [7.9, 18.8, 3.2, 4.8, 4.7, 4.6]
A(fpc("the bedroom's walk reading is the bedroom, not the closet", "Bedroom", _BED,
      finding="Bermuda said Closet 18 of 18 in the bedroom"))
A(fpc("the closet proxy at 2.0 m names the closet", "Closet", [2.0] + _BED[1:],
      finding="the own-proxy radius from inside"))
A(fpc("the closet proxy at 2.1 m is left to the fingerprints", "Bedroom", [2.1] + _BED[1:],
      finding="the own-proxy radius from outside"))
A(fpc("the office proxy within 2 m names the office", "Guest Room", _SOFA[:3] + [1.5] + _SOFA[4:],
      finding="the office has no walk fingerprint; its proxy is the evidence"))
A(fpc("the sofa is the living room though its proxy is 3 m away", "Living Room", _SOFA,
      finding="the walk: sofa 3.2 m from the living-room proxy"))
A(fpc("two room proxies near: the nearer wins", "Closet", [1.2, 18.8, 1.9, 4.8, 4.7, 4.6],
      finding="the closet sits above the kitchen"))
A(fpc("a bedroom reading without the closet proxy is still not the closet", "Bedroom",
      [None] + _BED[1:], finding="an unheard proxy is far, never near"))
A(fpc("the downstairs bathroom is the shower, not the corridor", "Shower",
      [9.3, 14.7, 7.0, 13.1, 3.2, 15.7], finding="Bermuda said Corridor 18 of 18 at the sink"))
A(fpc("the upstairs bathroom is the bathroom, not the kid-1 room", "Bathroom",
      [14.5, 4.0, 17.1, 11.6, 4.0, 12.6], finding="Bermuda said kid-1 room 14 of 18 there"))
A(fpc("kid-2's room is not the corridor", _RM["kid2"]["area_name"], [8.6, 8.0, 5.4, 8.2, 2.9, 7.4],
      finding="Bermuda said Corridor 17 of 18 there"))
A(fpc("one proxy hearing the phone is no room", "", [None, None, None, None, 2.5, None],
      finding="a phone at the door is not in the corridor"))
A(fpc("two proxies hearing the phone is a room", "Corridor", [None, None, 5.7, None, 2.5, None],
      finding="the heard count from above"))
A(fpc("a far proxy reading double is noise, not another room", _RM["kid2"]["area_name"],
      [8.6, 16.0, 5.4, 8.2, 2.9, 7.4], finding="log distance: 8 m against 16 m weighs as 2 m against 4 m"))
