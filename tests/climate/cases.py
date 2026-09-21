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
A(case("wind-free is never asserted outside cool", "will_set_preset", "False",
       {"active": True, "mode_ok": True, "mode": "heat", "now_preset": "none",
        "preset": "wind_free", "in_flight": False, "tripped": False},
       finding="set_preset_mode on an OFF unit turns it ON in COOL"))

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
A(case("SAFETY still overrides a stood-down unit", "may_act", "True",
       {"active": True, "reachable": True, "mode_ok": False, "external_moved": False,
        "standdown": False, "in_flight": False, "safety_throttled": False,
        "fail_count": 99, "breaker": 3, "is_safety": True, "throttle_ok": False},
       finding="frost and the cat floor outrank every back-off, including this one"))

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
