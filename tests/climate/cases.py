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
    target=22.0, hyst=1.0, filter_on=False,
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
A(case("exit hysteresis keeps heating inside the band", "mode", "heat",
       {"temp": 22.5, "now_mode": "heat"}, finding="v3 exit-only hysteresis"))
A(case("exit hysteresis releases past the band", "mode", "off",
       {"temp": 23.5, "now_mode": "heat"}, finding="v3"))
A(case("cool above target", "mode", "cool",
       {"house": "cool", "temp": 24.0, "target": 22.0}, finding="v4"))
A(case("cool exit hysteresis", "mode", "cool",
       {"house": "cool", "temp": 21.5, "target": 22.0, "now_mode": "cool"}, finding="v3"))
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
PROBE = "states('sensor.master_bedroom_bedroom_ac_temperature')"
TRV_OK = "is_state('binary_sensor.bedroom_trv_bedroom_trv_connectivity','on')"
TRV_HEAT = "states('sensor.bedroom_trv_bedroom_trv_heating')"
TRV_TEMP = "states('sensor.bedroom_trv_bedroom_trv_temperature')"
AC_OFF = "states('input_number.climate_ac_sensor_offset')"
TRV_OFF = "states('input_number.climate_trv_sensor_offset')"


def sensor_case(name, expect, subs, finding="", sensor=BED):
    return dict(name=name, sensor=sensor, expect=expect, given={}, subs=subs, finding=finding)


A(sensor_case(
    "a correct large AC offset is honoured, not overridden", "21.0",
    {AC_OFF: "'-4.0'", TRV_OK: "false", TRV_HEAT: "'0'", TRV_TEMP: "'0'",
     PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="F-1.1: v5.5 substituted -2 here and under-corrected by 2C, failing COLD"))
A(sensor_case(
    "an AC offset at the helper minimum is still honoured", "21.0",
    {AC_OFF: "'-4.0'", TRV_OK: "false", TRV_HEAT: "'0'", TRV_TEMP: "'0'",
     PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="F-1.1: honouring fails WARM, which is the safe direction"))
A(sensor_case(
    "an implausible TRV offset is ignored, not applied", "24.0",
    {AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'0'", TRV_TEMP: "'24.0'",
     PROBE: "'25.0'", TRV_OFF: "'-5.0'"},
    finding="R8-4: a new input_number comes up at its MINIMUM (-5), inside its own range"))
A(sensor_case(
    "the TRV is distrusted while the radiator is driving", "23.0",
    {AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'65'", TRV_TEMP: "'26.0'",
     PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="v5: a valve on a hot radiator reads high by an unmeasured amount"))
A(sensor_case(
    "an offline TRV falls back to the corrected probe", "23.0",
    {AC_OFF: "'-2.0'", TRV_OK: "false", TRV_HEAT: "'0'", TRV_TEMP: "'24.0'",
     PROBE: "'25.0'", TRV_OFF: "'0'"},
    finding="v5"))
A(sensor_case(
    "every source down yields nothing, never a fabricated number", "",
    {AC_OFF: "'-2.0'", TRV_OK: "false", TRV_HEAT: "'0'", TRV_TEMP: "'unavailable'",
     PROBE: "'unavailable'", TRV_OFF: "'0'"},
    finding="R7-9: resolves to the skip sentinel and the blackout alert speaks"))


# ---------------------------------------------------------------- the suite guarding itself
# Round 13 (3c): substitution is a source-to-source rewrite, so it can change an
# expression's MEANING rather than inject a value. This case only holds under a
# type-preserving rewrite: `states()` yields a STRING, and 'unavailable' must
# still travel the `| float(-999)` path to become the skip sentinel. Substituting
# a bare number here would silently stop testing that path.
A(sensor_case(
    "a source reporting 'unavailable' still reaches the skip sentinel", "",
    {AC_OFF: "'-2.0'", TRV_OK: "true", TRV_HEAT: "'unavailable'",
     TRV_TEMP: "'unavailable'", PROBE: "'unavailable'", TRV_OFF: "'0'"},
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



# ---------------------------------------------------------------- BLE over the Matter bridge
# 2026-09-21.  The living room and the office each have a SwitchBot Meter Pro CO2
# that reaches HA twice: over the SwitchBot Hub Mini's Matter bridge, and directly
# over BLE through the Bluetooth proxy.  Same physical sensor, two paths.  BLE is
# measurably the fresher of the two (living room 7.4 min vs 17.6, office 4.8 vs
# 9.1) and is already the source the CO2 sensors read, so the resolved temperature
# and humidity now prefer it.
#
# Matter is DEMOTED, not removed: it stays as the middle tier so that a proxy or
# BLE stack failure lands on the same physical instrument over another transport
# instead of dropping the room to its AC probe.  The probe is the last tier for a
# reason -- it needs the calibration offset and reports in whole degrees, which is
# the A11 problem.  Tier order is the whole point of these cases; a chain that
# quietly collapses to two tiers still passes case 1.
LR_T = "Climate temp living room"
LR_H = "Climate humidity living room"
OF_T = "Climate temp office"
OF_H = "Climate humidity office"

LR_T_BLE = "states('sensor.meter_pro_co2_b5be_temperature')"
LR_T_MAT = "states('sensor.living_room_meter_pro_co2_be_temperature')"
LR_T_AC = "states('sensor.living_room_livingroom_ac_temperature')"
LR_H_BLE = "states('sensor.meter_pro_co2_b5be_humidity')"
LR_H_MAT = "states('sensor.living_room_meter_pro_co2_be_humidity')"
LR_H_AC = "states('sensor.living_room_livingroom_ac_humidity')"

OF_T_BLE = "states('sensor.meter_pro_co2_5fe9_temperature')"
OF_T_MAT = "states('sensor.meter_pro_co2_e9_temperature')"
OF_T_AC = "states('sensor.office_guest_room_office_ac_temperature')"
OF_H_BLE = "states('sensor.meter_pro_co2_5fe9_humidity')"
OF_H_MAT = "states('sensor.meter_pro_co2_e9_humidity')"
OF_H_AC = "states('sensor.office_guest_room_office_ac_humidity')"

# Every tier carries a DIFFERENT value in these cases, so the expected output
# names exactly one tier.  Giving two tiers the same reading would let a wrong
# precedence pass.
A(sensor_case(
    "living room temperature prefers BLE over the Matter bridge", "23.4",
    {LR_T_BLE: "'23.4'", LR_T_MAT: "'22.1'", LR_T_AC: "'25.0'", AC_OFF: "'-2.0'"},
    sensor=LR_T, finding="BLE is the fresher path to the same instrument"))
A(sensor_case(
    "a dead BLE meter falls to Matter, not to the AC probe", "22.1",
    {LR_T_BLE: "'unavailable'", LR_T_MAT: "'22.1'", LR_T_AC: "'25.0'", AC_OFF: "'-2.0'"},
    sensor=LR_T, finding="Matter is demoted to the middle tier, not removed"))
A(sensor_case(
    "both meter paths down fall to the corrected AC probe", "23.0",
    {LR_T_BLE: "'unavailable'", LR_T_MAT: "'unavailable'", LR_T_AC: "'25.0'",
     AC_OFF: "'-2.0'"},
    sensor=LR_T, finding="the probe still needs its offset applied"))
A(sensor_case(
    "every living room temperature source down yields nothing", "",
    {LR_T_BLE: "'unavailable'", LR_T_MAT: "'unavailable'", LR_T_AC: "'unavailable'",
     AC_OFF: "'-2.0'"},
    sensor=LR_T, finding="R7-9: the skip sentinel, never a fabricated number"))

A(sensor_case(
    "office temperature prefers BLE over the Matter bridge", "21.7",
    {OF_T_BLE: "'21.7'", OF_T_MAT: "'20.4'", OF_T_AC: "'25.0'", AC_OFF: "'-2.0'"},
    sensor=OF_T, finding="BLE is the fresher path to the same instrument"))
A(sensor_case(
    "a dead office BLE meter falls to Matter, not to the AC probe", "20.4",
    {OF_T_BLE: "'unavailable'", OF_T_MAT: "'20.4'", OF_T_AC: "'25.0'", AC_OFF: "'-2.0'"},
    sensor=OF_T, finding="Matter is demoted to the middle tier, not removed"))
A(sensor_case(
    "both office meter paths down fall to the corrected AC probe", "23.0",
    {OF_T_BLE: "'unavailable'", OF_T_MAT: "'unavailable'", OF_T_AC: "'25.0'",
     AC_OFF: "'-2.0'"},
    sensor=OF_T, finding="the probe still needs its offset applied"))

A(sensor_case(
    "living room humidity prefers BLE over the Matter bridge", "47.0",
    {LR_H_BLE: "'47'", LR_H_MAT: "'52'", LR_H_AC: "'60'"},
    sensor=LR_H, finding="BLE is the fresher path to the same instrument"))
A(sensor_case(
    "a dead BLE humidity reading falls to Matter", "52.0",
    {LR_H_BLE: "'unavailable'", LR_H_MAT: "'52'", LR_H_AC: "'60'"},
    sensor=LR_H, finding="Matter is demoted to the middle tier, not removed"))
A(sensor_case(
    "both humidity meter paths down fall to the AC probe", "60.0",
    {LR_H_BLE: "'unavailable'", LR_H_MAT: "'unavailable'", LR_H_AC: "'60'"},
    sensor=LR_H, finding="humidity carries no calibration offset"))
A(sensor_case(
    "every living room humidity source down yields nothing", "",
    {LR_H_BLE: "'unavailable'", LR_H_MAT: "'unavailable'", LR_H_AC: "'unavailable'"},
    sensor=LR_H, finding="R7-9: the skip sentinel, never a fabricated number"))

A(sensor_case(
    "office humidity prefers BLE over the Matter bridge", "44.0",
    {OF_H_BLE: "'44'", OF_H_MAT: "'49'", OF_H_AC: "'60'"},
    sensor=OF_H, finding="BLE is the fresher path to the same instrument"))
A(sensor_case(
    "a dead office BLE humidity reading falls to Matter", "49.0",
    {OF_H_BLE: "'unavailable'", OF_H_MAT: "'49'", OF_H_AC: "'60'"},
    sensor=OF_H, finding="Matter is demoted to the middle tier, not removed"))
A(sensor_case(
    "both office humidity paths down fall to the AC probe", "60.0",
    {OF_H_BLE: "'unavailable'", OF_H_MAT: "'unavailable'", OF_H_AC: "'60'"},
    sensor=OF_H, finding="humidity carries no calibration offset"))


# ---------------------------------------------------------------- a real meter in a kid's room
# 2026-09-21.  The operator moved a SwitchBot Meter Pro (Indoor/Outdoor) into Kids room 1,
# in the far corner, away from the AC's discharge.  This is the instrument that was promised
# when the 3 C swing was diagnosed: the AC is mounted directly above the radiator and the
# slatted ceiling blows its own output onto the TRV's thermometer, so the TRV has been
# reporting the unit's discharge air rather than the room.
#
# The room therefore gains a FOUR-tier chain.  Tier order, worst-case first:
#   1. the meter over BLE          -- a real thermometer, correctly placed, no offset needed
#   2. the same meter over Matter  -- second transport, same instrument (see the living room)
#   3. the TRV, only when live AND the radiator is cold, plus the TRV offset
#   4. the AC internal probe, plus the global AC offset
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
K1_M_T = "states('%s')" % K1["matter_temp"]
K1_V_T = "states('%s')" % K1["trv_temp"]
K1_A_T = "states('%s')" % K1["ac_temp"]
K1_CONN = "is_state('%s','on')" % K1["trv_conn"]
K1_HEAT = "states('%s')" % K1["trv_heat"]

K1_B_H = "states('%s')" % K1["meter_hum"]
K1_M_H = "states('%s')" % K1["matter_hum"]
K1_V_H = "states('%s')" % K1["trv_hum"]
K1_A_H = "states('%s')" % K1["ac_hum"]

# Every tier carries a DIFFERENT value, so the expected output names exactly one of them.
# The AC offset is -2 and the TRV offset +1 throughout, so a tier that wrongly picks up a
# correction is visible in the result rather than hidden behind a matching number.
A(sensor_case(
    "the room meter outranks the TRV that the AC blows on", "23.4",
    {K1_B_T: "'23.4'", K1_M_T: "'23.5'", K1_V_T: "'22.0'", K1_A_T: "'25.0'",
     K1_CONN: "true", K1_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="R8-2/A11: the TRV reads the unit's discharge, not the room"))
A(sensor_case(
    "a correctly placed meter takes NO calibration offset", "23.4",
    {K1_B_T: "'23.4'", K1_M_T: "'unavailable'", K1_V_T: "'unavailable'", K1_A_T: "'25.0'",
     K1_CONN: "false", K1_HEAT: "'0'", AC_OFF: "'-4.0'", TRV_OFF: "'-5.0'"},
    sensor=K1_T, finding="offsets correct instruments in the wrong air; this one is not"))
A(sensor_case(
    "a dead BLE meter falls to the same meter over Matter", "23.5",
    {K1_B_T: "'unavailable'", K1_M_T: "'23.5'", K1_V_T: "'22.0'", K1_A_T: "'25.0'",
     K1_CONN: "true", K1_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="second transport to one instrument, as in the living room"))
A(sensor_case(
    "both meter paths down fall to the TRV, offset and all", "23.0",
    {K1_B_T: "'unavailable'", K1_M_T: "'unavailable'", K1_V_T: "'22.0'", K1_A_T: "'25.0'",
     K1_CONN: "true", K1_HEAT: "'0'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="the TRV keeps its place as the only INDEPENDENT fallback"))
# The probe reads 24.0 here, NOT 25.0: with the AC offset at -2 a 25.0 probe resolves to
# 23.0, which is exactly what the TRV tier above would have produced (22.0 + 1.0).  The two
# paths would have been indistinguishable and the case would have passed either way.
A(sensor_case(
    "a hot radiator still disqualifies the TRV, even as third tier", "22.0",
    {K1_B_T: "'unavailable'", K1_M_T: "'unavailable'", K1_V_T: "'26.0'", K1_A_T: "'24.0'",
     K1_CONN: "true", K1_HEAT: "'65'", AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="v5: a valve on a hot radiator reads high by an unmeasured amount"))
A(sensor_case(
    "every source down yields nothing, never a fabricated number", "",
    {K1_B_T: "'unavailable'", K1_M_T: "'unavailable'", K1_V_T: "'unavailable'",
     K1_A_T: "'unavailable'", K1_CONN: "false", K1_HEAT: "'0'",
     AC_OFF: "'-2.0'", TRV_OFF: "'1.0'"},
    sensor=K1_T, finding="R7-9: the skip sentinel, never a fabricated number"))

A(sensor_case(
    "room humidity prefers the meter over the TRV", "39.0",
    {K1_B_H: "'39'", K1_M_H: "'44'", K1_V_H: "'46'", K1_A_H: "'31'", K1_CONN: "true"},
    sensor=K1_H, finding="same instrument ranking as temperature"))
A(sensor_case(
    "a dead BLE humidity reading falls to Matter", "44.0",
    {K1_B_H: "'unavailable'", K1_M_H: "'44'", K1_V_H: "'46'", K1_A_H: "'31'", K1_CONN: "true"},
    sensor=K1_H, finding="Matter is demoted, not removed"))
A(sensor_case(
    "both meter paths down fall to the TRV humidity", "46.0",
    {K1_B_H: "'unavailable'", K1_M_H: "'unavailable'", K1_V_H: "'46'", K1_A_H: "'31'",
     K1_CONN: "true"},
    sensor=K1_H, finding="the TRV humidity has no radiator gate -- only a liveness one"))
A(sensor_case(
    "an offline TRV drops humidity to the AC probe", "31.0",
    {K1_B_H: "'unavailable'", K1_M_H: "'unavailable'", K1_V_H: "'46'", K1_A_H: "'31'",
     K1_CONN: "false"},
    sensor=K1_H, finding="liveness gates the TRV in both resolved sensors"))


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
# refused to touch the fan -- stranded on for ever. Shutdown now turns on a RUN-LOCAL
# fact, we_started; the flag is for cross-restart bookkeeping only.
A(guard("we stop a fan this run actually started", "we_may_stop", "True",
        {FAN_ON: "true", "we_started": "true", "stopped_by_human": "false"},
        finding="F2: shutdown must not depend on the persistent flag"))
A(guard("we never stop a fan this run did not start", "we_may_stop", "False",
        {FAN_ON: "true", "we_started": "false", "stopped_by_human": "false"},
        finding="the climate lesson: never take control away from the operator"))
A(guard("nothing to stop if the fan is already off", "we_may_stop", "False",
        {FAN_ON: "false", "we_started": "true", "stopped_by_human": "false"},
        finding="a person switched it off mid-run; abandon rather than re-command"))
A(guard("a person taking over ends our claim", "we_may_stop", "False",
        {FAN_ON: "true", "we_started": "true", "stopped_by_human": "true"},
        finding="F2: off-then-on by hand during the wait must not be re-stopped by us"))

# we_started is the run-local fact the whole shutdown path now hangs on, so it needs
# its own cases -- binding it as an input to we_may_stop does NOT test it. Caught by
# mutate.py, which flagged "trusts fan.turn_on without re-reading" as undetected.
A(guard("a fan confirmed running counts as started by us", "we_started", "True",
        {FAN_ON: "true"}, finding="F2: re-read after commanding, never assume it worked"))
A(guard("a fan that did not come on is not ours", "we_started", "False",
        {FAN_ON: "false"},
        finding="F2: fan.turn_on can fail; claiming ownership anyway stranded the flag"))

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


# ---------------------------------------------------------------- CO2 (SwitchBot BLE)
# The same two Meter Pro CO2 devices are exposed twice: Matter gives temperature and
# humidity (what the climate loop already uses), the SwitchBot BLE proxy adds carbon
# dioxide. Room mapping was PROVEN by cross-checking both platforms' readings, not by
# the entity-id suffix: living room = b5be, office = 5fe9.
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
# docs/proposal-decide-act-split.md. Written FIRST per the repo's TDD rule; reviewed BEFORE
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
