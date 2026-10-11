"""Mutation check -- does the suite actually detect anything?

A green suite proves nothing on its own; it may simply be asserting things that
cannot fail.  This re-introduces bugs that GENUINELY SHIPPED in this system and
confirms at least one case turns red for each.

Run it after adding cases.  A `MISSED` row means the suite has a blind spot
exactly where this system has historically been weakest.
"""
import io, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import harness
from cases import CASES, AC_OFF as AC_OFF_G

REAL_EXPR = harness.load_expressions()
REAL_SENS = harness.load_sensor_templates()
KID1_T = "Climate temp " + harness.load_rooms()["kid1"]["title"]
KID1_H = "Climate humidity " + harness.load_rooms()["kid1"]["title"]
KID2_T = "Climate temp " + harness.load_rooms()["kid2"]["title"]

BUGS = [
 ("the 2026-09-20 unit_moved bug (drop '- settle')", "expr", "unit_moved",
  lambda t: t.replace("lc < since_cmd - settle", "lc < since_cmd")),
 ("v5.5 offset substitution (reject a correct -4)", "sensor", "Climate temp bedroom",
  lambda t: t.replace("{% set f = states('sensor.master_bedroom_bedroom_ac_temperature') | float(-999) %}",
                      "{% set ac = ac if ac >= -3.5 else -2 %}{% set f = states('sensor.master_bedroom_bedroom_ac_temperature') | float(-999) %}")),
 ("v3 unclamped frost setpoint", "expr", "set_target", lambda t: "{{ want_target | float(21) }}"),
 ("house hysteresis removed", "expr", "house",
  lambda t: "{% if outdoor <= -900 %}shoulder{% elif outdoor <= heat_below_out %}heat{% elif outdoor >= cool_above_out %}cool{% else %}shoulder{% endif %}"),
 ("standdown: a self-off counted as a wall override again", "expr", "external_moved",
  lambda t: t.replace(" and now_mode != 'off'", "")),
 ("standdown: self-off no longer recognised", "expr", "standdown",
  lambda t: "{{ false }}"),
 ("standdown: we fight the unit's power saving", "expr", "may_act",
  lambda t: t.replace(" and not standdown", "")),
 ("standdown: the breaker isolates a power-saving unit", "expr", "diverged",
  lambda t: t.replace(" and not standdown", "")),
 # F14-5: the safety dispatch bug, restored
 ("F14-5: safety dispatch gated on the back-offs again", "expr", "may_act",
  lambda t: t.replace("and (is_safety or (not external_moved and not standdown))",
                      "and not external_moved and not standdown")),
 ("F14-5: safety allowed to double-command in flight", "expr", "may_act",
  lambda t: t.replace("not in_flight and ", "")),
 ("R15 A3: stale hold label never cleared", "expr", "reason_stale",
  lambda t: "{{ false }}"),
 ("R15 A3: label cleared while the hold is still live", "expr", "reason_stale",
  lambda t: "{{ states(r.reason) != 'none' }}"),
 ("boot grace dropped again (v5.4)", "expr", "no_temp",
  lambda t: t.replace(" and uptime > boot_grace", "")),
 # v5.10: the exit band that could not be reached
 ("v5.10: room hysteresis back above the target (heat)", "expr", "mode",
  lambda t: t.replace("temp < target - (0 if now_mode == 'heat' else room_hyst)",
                      "temp < target or (now_mode == 'heat' and temp < target + room_hyst)")),
 ("v5.10: the cooling mirror of the same band", "expr", "mode",
  lambda t: t.replace("temp > target + (0 if now_mode == 'cool' else room_hyst)",
                      "temp > target or (now_mode == 'cool' and temp > target - room_hyst)")),
 ("v5.10: deadband dropped, so the room flaps at the setpoint", "expr", "mode",
  lambda t: t.replace("target - (0 if now_mode == 'heat' else room_hyst)", "target")),
 # purifier automation -- bugs it would be natural to write
 ("purifier: bare state trigger (fires on midnight reset)", "expr2", "visit_happened",
  lambda t: "{{ trigger.id == 'visit' }}"),
 ("purifier: no numeric guard on the previous value", "expr2", "visit_happened",
  lambda t: t.replace("(trigger.from_state.state | float(-1)) >= 0 and ", "")),
 ("purifier: turns off a purifier a person started", "expr2", "we_may_stop",
  lambda t: "{{ states('fan.corridor_xiaomi_air_purifier') != 'off' }}"),
 ("purifier: takes over a running purifier", "expr2", "already_running",
  lambda t: "{{ false }}"),
 # round-1 findings: each mutation restores the bug the fix removed
 ("purifier F2: shutdown gated on the ownership flag again", "expr2", "we_may_stop",
  lambda t: "{{ is_state('fan.corridor_xiaomi_air_purifier','on') and is_state('input_boolean.purifier_auto_run','on') }}"),
 ("purifier F2: trusts fan.turn_on without re-reading", "expr2", "we_started",
  lambda t: "{{ true }}"),
 ("purifier F3: arms the early stop on an unresponsive sensor", "expr2", "pm_usable",
  lambda t: "{{ true }}"),
 ("purifier: ignores the 'sensor is broken' toggle", "expr2", "pm_usable",
  lambda t: "{{ pm_after_settle >= 2 }}"),
 ("purifier F4: no cooldown after a manual stop", "expr2", "manual_cooldown",
  lambda t: "{{ false }}"),
 # v6, 2026-10-02: the fan drops to 'unavailable' every few minutes, and is_state(on)
 # read every dropout as "off". Each mutation restores one of the two shipped readings.
 ("purifier v6: an unreachable fan at the end is left running", "expr2", "we_may_stop",
  lambda t: t.replace("!= 'off'", "== 'on'")),
 ("purifier v6: an unreachable fan at the confirm is written off", "expr2", "we_started",
  lambda t: t.replace("!= 'off'", "== 'on'")),
 # CO2 additions
 ("health risk: CO2 check dropped", "sensor", "Climate health risk",
  lambda t: t.replace("{% if c >= 1400 %}{% set ns.risk = true %}{% endif %}", "")),
 ("health risk: missing CO2 reads as danger", "sensor", "Climate health risk",
  lambda t: t.replace("{% if c >= 1400 %}", "{% if c < 1400 %}")),
 ("health risk: CO2 check swallows the humidity check", "sensor", "Climate health risk",
  lambda t: t.replace("{% if h >= 65 or h < 30 or t < 16 %}", "{% if false %}")),
 # BLE over the Matter bridge -- the tier ORDER is the whole point, and a chain
 # that quietly collapses back to two tiers still satisfies the happy path.
 ("source order: the Matter bridge outranks BLE again", "sensor", "Climate temp living room",
  lambda t: t.replace("{% if b > -900 %}{{ b | round(2) }}{% elif m > -900 %}{{ m | round(2) }}",
                      "{% if m > -900 %}{{ m | round(2) }}{% elif b > -900 %}{{ b | round(2) }}")),
 ("source order: the Matter tier is dropped, not demoted", "sensor", "Climate humidity office",
  lambda t: t.replace("{% elif m >= 0 %}{{ m | round(1) }}", "")),
 # A real meter in a kid's room. The offset traps are the point: the meter is correctly
 # placed, so a correction applied to it injects the very error the correction removes.
 ("kid1: the TRV outranks the room meter again", "sensor", KID1_T,
  lambda t: t.replace("{% if b > -900 %}{{ b | round(2) }}{% elif m > -900 %}{{ m | round(2) }}{% elif q > -900 %}{{ q | round(2) }}{% elif p > -900 %}",
                      "{% if p > -900 %}{{ (p + tv_eff) | round(2) }}{% elif b > -900 %}{{ b | round(2) }}{% elif m > -900 %}{{ m | round(2) }}{% elif q > -900 %}")),
 # 2026-10-07: the air-quality sensor is the third tier -- below the meter, above the TRV.
 ("kid1: the air-quality tier is dropped", "sensor", KID1_T,
  lambda t: t.replace("{% elif q > -900 %}{{ q | round(2) }}", "")),
 ("kid1: the air-quality sensor outranks the meter", "sensor", KID1_T,
  lambda t: t.replace("{% if b > -900 %}{{ b | round(2) }}{% elif m > -900 %}{{ m | round(2) }}{% elif q > -900 %}{{ q | round(2) }}",
                      "{% if q > -900 %}{{ q | round(2) }}{% elif b > -900 %}{{ b | round(2) }}{% elif m > -900 %}{{ m | round(2) }}")),
 ("kid1: the air-quality sensor gets the TRV offset", "sensor", KID1_T,
  lambda t: t.replace("{% elif q > -900 %}{{ q | round(2) }}", "{% elif q > -900 %}{{ (q + tv_eff) | round(2) }}")),
 ("kid1: humidity loses the air-quality tier", "sensor", KID1_H,
  lambda t: t.replace("{% elif q >= 0 %}{{ q | round(1) }}", "")),
 # Daylight for presence lighting. BRIGHT switches an occupied room's lights OFF, so a
 # flap at dusk is the hazard; and a dead lux sensor must not stop the lights.
 ("daylight: hysteresis removed (flaps at dusk)", "sensor", "Lighting daylight",
  lambda t: t.replace("(dark if was_bright else dark * 2)", "dark")),
 ("daylight: hysteresis inverted", "sensor", "Lighting daylight",
  lambda t: t.replace("(dark if was_bright else dark * 2)", "(dark * 2 if was_bright else dark)")),
 ("daylight: 0 lx treated as a dead sensor", "sensor", "Lighting daylight",
  lambda t: t.replace("{% if lux >= 0 %}", "{% if lux > 0 %}")),
 ("daylight: no sun fallback", "sensor", "Lighting daylight",
  lambda t: t.replace("(state_attr('sun.sun','elevation') | float(0)) > (6 if was_bright else 12)", "false")),
 ("daylight: a restart starts on the bright side", "sensor", "Lighting daylight",
  lambda t: t.replace("this.state == 'on'", "this.state != 'off'")),
 # Review 2026-10-07 (A1, A7, A8).
 # 2026-10-11: the night bridge must mirror the schedule, not invert or ignore it.
 ("night: the bridge is inverted", "sensor", "Lighting night",
  lambda t: t.replace("a == 'armed_night'", "a == 'armed_home'")),
 ("night: the lights lose the unavailable-alarm fallback", "sensor", "Lighting night",
  lambda t: t.replace(" or (a in ['unavailable', 'unknown'] and is_state('schedule.climate_night','on'))", "")),
 ("night: the climate loop loses the unavailable-alarm fallback", "expr", "night",
  lambda t: t.replace(" or (a in ['unavailable', 'unknown'] and is_state('schedule.climate_night','on'))", "")),
 ("night: an unavailable alarm is always night", "expr", "night",
  lambda t: t.replace(" and is_state('schedule.climate_night','on'))", ")")),
 # 2026-10-11: the alarm is the house's night. Each of these is a way to lose the operator's
 # manual control, or to let the schedule override a state it must leave alone.
 ("night: the climate loop reads the schedule again", "expr", "night",
  lambda t: "{{ is_state('schedule.climate_night','on') or is_state('alarm_control_panel.home','armed_night') }}"),
 ("house: 22:00 arms night from Away", "expr2", "want",
  lambda t: t.replace("a in ['armed_home', 'disarmed']", "a in ['armed_home', 'disarmed', 'armed_away']"), "1790200000001"),
 ("house: 22:00 ignores a disarmed house", "expr2", "want",
  lambda t: t.replace("a in ['armed_home', 'disarmed']", "a in ['armed_home']"), "1790200000001"),
 ("house: 06:00 re-asserts Home over a manual day", "expr2", "want",
  lambda t: t.replace("s == 'off' and a == 'armed_night'", "s == 'off' and a != 'armed_away'"), "1790200000001"),
 ("house: 06:00 disarms instead of Home", "expr2", "want",
  lambda t: t.replace("night{% elif s == 'off' and a == 'armed_night' %}home", "night{% elif s == 'off' and a == 'armed_night' %}disarm"), "1790200000001"),
 ("house: Adaptive Lighting sleep is inverted", "expr2", "sleep_on",
  lambda t: t.replace("a == 'armed_night'", "a == 'armed_home'"), "1790200000001"),
 ("house: Adaptive Lighting loses the unavailable-alarm fallback", "expr2", "sleep_on",
  lambda t: t.replace(" or (a in ['unavailable', 'unknown'] and is_state('schedule.climate_night','on'))", ""), "1790200000001"),
 ("house: the sleep-switch finder takes every Adaptive Lighting switch", "expr2", "sleep_switches",
  lambda t: t.replace("_.*_sleep_mode$", "_"), "1790200000001"),
 # v6 fallback (operator 2026-10-11: "otherwise we'll freeze").
 ("v6: an offline valve still counts as a radiator", "expr", "has_rad",
  lambda t: t.replace("s in ['heat', 'auto']", "s not in ['none']")),
 ("v6: a switched-off valve still counts as a radiator", "expr", "has_rad",
  lambda t: t.replace("s in ['heat', 'auto']", "s in ['heat', 'auto', 'off']")),
 ("v6: the open-window exception is dropped", "expr", "has_rad",
  lambda t: t.replace(" or (s == 'off' and rad_window != '' and is_state(rad_window, 'on'))", "")),
 # v6 morning warm-up (2026-10-11).
 ("warm-up: a manual night warms too (schedule ignored)", "expr", "preheat",
  lambda t: t.replace(" and is_state('schedule.climate_night','on')", "")),
 ("warm-up: the per-room toggle is ignored", "expr", "preheat",
  lambda t: t.replace("is_state(r.preheat, 'on') and ", "")),
 ("warm-up: no lead-time bound (warms all night)", "expr", "preheat",
  lambda t: t.replace(" <= (preheat_min | float(45)) * 60", "")),
 ("warm-up: a passed edge still counts", "expr", "preheat",
  lambda t: t.replace("0 < ((as_timestamp", "-99999999 < ((as_timestamp")),
 ("warm-up: aims at the night target", "expr", "target",
  lambda t: t.replace("(night and not preheat)", "night")),
 ("warm-up: the radiator rule still blocks the AC", "expr", "mode",
  lambda t: t.replace("{% elif has_rad and night and not preheat %}off", "{% elif has_rad and night %}off")),
 # v6 (2026-10-11): radiators first. The AC loop's yield, and the radiator automation's decisions.
 ("v6: the AC heats radiator rooms at night again", "expr", "mode",
  lambda t: t.replace("{% elif has_rad and night and not preheat %}off", "")),
 ("v6: the AC boosts on any deficit (boost ignored)", "expr", "mode",
  lambda t: t.replace("(room_hyst if now_mode == 'heat' else boost)", "(0 if now_mode == 'heat' else room_hyst)")),
 ("v6: a boosting AC runs to target instead of handing back", "expr", "mode",
  lambda t: t.replace("(room_hyst if now_mode == 'heat' else boost)", "(0 if now_mode == 'heat' else boost)")),
 ("v6: the radiator rule swallows the air-filter toggle", "expr", "mode",
  lambda t: t.replace("{% if filter_on %}heat{% elif has_rad and night and not preheat %}", "{% if has_rad and night %}off{% elif filter_on %}heat{% elif has_rad and night and not preheat %}")),
 ("radiator: a disabled room is switched off (cold bedroom)", "expr2", "rad_target",
  lambda t: t.replace("{% elif not enabled %}auto", "{% elif not enabled %}off"), "1790300000001"),
 ("radiator: away does not hold the pet floor", "expr2", "rad_target",
  lambda t: t.replace("{% elif away %}{{ away_min | float | round(1) }}", ""), "1790300000001"),
 ("radiator: radiators heat outside the heating season", "expr2", "rad_target",
  lambda t: t.replace("{% elif house != 'heat' %}off", ""), "1790300000001"),
 ("radiator: an unknown season switches radiators off", "expr2", "rad_target",
  lambda t: t.replace("{% if house not in ['heat', 'shoulder', 'cool'] %}none{% elif", "{% if"), "1790300000001"),
 ("radiator: comfort off switches radiators off", "expr2", "rad_target",
  lambda t: t.replace("{% elif not comfort %}auto", "{% elif not comfort %}off"), "1790300000001"),
 ("radiator: a turned dial is reverted", "expr2", "rad_send",
  lambda t: t.replace(" and (lc == 0 or zc == lc)", ""), "1790300000001"),
 ("radiator: the hold is ignored", "expr2", "rad_send",
  lambda t: t.replace(" and not hold_active", ""), "1790300000001"),
 ("radiator: an unavailable zone is commanded", "expr2", "rad_send",
  lambda t: t.replace(" and z_state not in ['unavailable', 'unknown']", ""), "1790300000001"),
 ("radiator: a redundant command is sent", "expr2", "rad_send",
  lambda t: t.replace(" and zc != wc", ""), "1790300000001"),
 ("radiator: our own command looks like a person (no settle)", "expr2", "touched",
  lambda t: t.replace(" and not hold_active", ""), "1790300000001"),
 ("radiator: Tado's open-window shut-off called a person", "expr2", "touched",
  lambda t: t.replace(" and not z_window", ""), "1790300000001"),
 ("radiator: a zone with its window open is commanded", "expr2", "rad_send",
  lambda t: t.replace(" and not z_window", "").replace(" and (lc == 0 or zc == lc)", ""), "1790300000001"),
 ("radiator: a zone we never commanded is called an override", "expr2", "touched",
  lambda t: t.replace(" and lc != 0", ""), "1790300000001"),
 # 2026-10-09: the house-wide safety roll-up behind Home's Needs attention.
 ("safety: the roll-up counts itself and latches", "sensor", "Any safety alarm",
  lambda t: t.replace("| rejectattr('entity_id','eq','binary_sensor.any_safety_alarm') ", "")),
 ("safety: smoke is not a safety class", "sensor", "Any safety alarm",
  lambda t: t.replace("'smoke',", "")),
 ("safety: carbon monoxide is not a safety class", "sensor", "Any safety alarm",
  lambda t: t.replace("'carbon_monoxide',", "")),
 ("safety: an unavailable alarm cries fire", "sensor", "Any safety alarm",
  lambda t: t.replace("selectattr('state','eq','on')", "rejectattr('state','eq','off')")),
 ("daylight: the sun fallback loses its hysteresis", "sensor", "Lighting daylight",
  lambda t: t.replace("> (6 if was_bright else 12)", "> 6")),
 ("kid1: the air-quality sensor outranks the Matter path", "sensor", KID1_T,
  lambda t: t.replace("{% elif m > -900 %}{{ m | round(2) }}{% elif q > -900 %}{{ q | round(2) }}",
                      "{% elif q > -900 %}{{ q | round(2) }}{% elif m > -900 %}{{ m | round(2) }}")),
 ("kid1: the air-quality sensor gets the AC offset", "sensor", KID1_T,
  lambda t: t.replace("{% elif q > -900 %}{{ q | round(2) }}", "{% elif q > -900 %}{{ (q + ac) | round(2) }}")),
 ("kid1: the room meter gets the AC offset applied to it", "sensor", KID1_T,
  lambda t: t.replace("{% if b > -900 %}{{ b | round(2) }}", "{% if b > -900 %}{{ (b + ac) | round(2) }}")),
 ("kid1: a hot radiator no longer disqualifies the TRV", "sensor", KID1_T,
  lambda t: t.replace("if (live and cold) else -999", "if live else -999")),
 # Background radiation. The tube marking is unconfirmed, so the two failures that
 # matter are a hard-coded factor and a dead counter reported as a real zero.
 ("radiation: the tube factor is hard-coded again", "sensor", "Radiation dose rate",
  lambda t: t.replace("states('input_number.radiation_usv_per_cpm') | float(0.00332)", "0.00332")),
 ("radiation: the obsolete 18 CPS/mR/h factor comes back as the fallback", "sensor", "Radiation dose rate",
  lambda t: t.replace("| float(0.00332)", "| float(0.00812)")),
 ("radiation: a disconnected counter reports a confident zero again", "sensor", "Radiation dose rate::availability",
  lambda t: t.replace(">= 1 }}", ">= 0 }}")),
 ("radiation: availability stops gating on the counter at all", "sensor", "Radiation dose rate::availability",
  lambda t: "{{ true }}"),
 # RETIRED 2026-09-22, not lost. This mutation moved the no-reading sentinel from -1
 # to 0, which used to turn a dead counter into a confident 0.0 uSv/h. The cutoff is
 # now `c >= 1`, so -1 and 0 both fall the same side of it and the mutation no longer
 # introduces a bug -- it is equivalent to the real expression. The hazard it guarded
 # is now guarded by "a disconnected counter reports a confident zero again", which
 # attacks the cutoff itself rather than the sentinel feeding it.
 # The preset ride-along, 2026-09-23. Each of these is a way to lose the silent
 # start the operator asked for, or to reintroduce the OFF-turns-on-in-COOL hazard.
 ("ride-along: fires when we are not commanding the mode", "expr", "preset_with_start",
  lambda t: t.replace("may_act and ", "")),
 ("ride-along: loses the mode guard, so an OFF unit gets a preset", "expr", "preset_with_start",
  lambda t: t.replace(" and mode in ['cool','heat']", "")),
 ("ride-along: re-sends a preset that already matches", "expr", "preset_with_start",
  lambda t: t.replace(" and want_preset != now_preset", "")),
 ("ride-along: removed entirely, back to a 240 s loud start", "expr", "preset_with_start",
  lambda t: "{{ false }}"),
 # Presets per mode, 2026-09-23. The rule is cheap to state and cheap to break:
 # "wind-free whenever cooling, quiet when heating at night, silence otherwise."
 # Each mutation below breaks exactly one clause of that sentence.
 ("presets: wind-free asserted outside cool again", "expr", "want_preset",
  lambda t: "{{ 'wind_free_sleep' if night else 'wind_free' }}"),
 ("presets: the night quiet rule dropped", "expr", "want_preset",
  lambda t: t.replace("{% elif mode == 'heat' and night %}quiet", "")),
 ("presets: quiet asserted all day, not just at night", "expr", "want_preset",
  lambda t: t.replace("mode == 'heat' and night", "mode == 'heat'")),
 ("presets: re-commands a preset that already matches", "expr", "will_set_preset",
  lambda t: t.replace(" and want_preset != now_preset", "")),
 ("presets: commanded before the mode converges", "expr", "will_set_preset",
  lambda t: t.replace("active and mode_ok and", "active and")),
 # Kids room 2 gained its meter on 2026-09-25; the chain must not quietly revert.
 ("kid 2: the room meter dropped from the chain", "sensor", KID2_T,
  lambda t: t.replace("{% if b > -900 %}{{ b | round(2) }}{% elif m > -900 %}", "{% if m > -900 %}")),
 # Outdoor temperature, 2026-09-25: terrace sensor first, forecast second.
 ("outdoor: the forecast outranks the terrace again", "sensor", "Climate temp outdoor",
  lambda t: t.replace("{% if t > -900 %}{{ t | round(2) }}{% elif w > -900 %}{{ w | round(2) }}",
                      "{% if w > -900 %}{{ w | round(2) }}{% elif t > -900 %}{{ t | round(2) }}")),
 ("outdoor: a reading of exactly zero taken for no reading", "sensor", "Climate temp outdoor",
  lambda t: t.replace("{% if t > -900 %}", "{% if t and t > -900 %}")),
 ("outdoor: availability gated on the terrace alone", "sensor", "Climate temp outdoor::availability",
  lambda t: "{{ states('sensor.outdoor_motion_temperature') | float(-999) > -900 }}"),
 ("outdoor: the house reads the forecast directly again", "expr", "outdoor",
  lambda t: "{{ states('%s') | float(-999) }}" % harness.load_rooms()["house"]["forecast_temp"]),
]

print("MUTATION CHECK -- each row re-introduces a bug that actually shipped\n")
allgood = True
for label, kind, key, mutate, *aid in BUGS:
    aid = aid[0] if aid else "1789947000001"   # second automation; the purifier by default
    exprs, sens = dict(REAL_EXPR), dict(REAL_SENS)
    if kind == "expr2":
        # A second automation: mutate its expression by shadowing the loader,
        # so the case still runs against everything else unchanged.
        exprs2 = dict(harness.load_expressions(aid))
        before = exprs2[key]
        exprs2[key] = mutate(before)
        if exprs2[key] == before:
            print("  ?? %-46s MUTATION DID NOT APPLY" % label); allgood = False; continue
        orig = harness.load_expressions
        harness.load_expressions = lambda a=None, _o=orig, _e=exprs2, _aid=aid: (
            _e if a == _aid else _o(a) if a else _o())
        try:
            # Only the cases that evaluate THIS expression of THIS automation can change.
            sel = [c for c in CASES if c.get("automation") == aid and c.get("expr") == key]
            rendered = harness.evaluate(harness.build_template(sel, exprs, sens))
            got = harness.split_results(rendered, len(sel))
            caught = [c["name"] for c, g in zip(sel, got) if g != str(c["expect"])]
        except harness.ExtractionError as exc:
            caught = ["structural: " + str(exc).split(":")[0]]
        finally:
            harness.load_expressions = orig
        if caught:
            print("  CAUGHT  %-46s by %d case(s): %s" % (label, len(caught), caught[0]))
        else:
            print("  MISSED  %-46s NO CASE DETECTED THIS" % label); allgood = False
        continue
    tgt = exprs if kind == "expr" else sens
    before = tgt[key]; tgt[key] = mutate(before)
    if tgt[key] == before:
        print("  ?? %-46s MUTATION DID NOT APPLY" % label); allgood = False; continue
    try:
        # Each case evaluates exactly ONE expression or sensor, so only the cases that evaluate
        # the mutated one can change - running the other ~300 proved nothing and took hours.
        if kind == "expr":
            sel = [c for c in CASES if c.get("expr") == key and "sensor" not in c and not c.get("automation")]
        else:
            sel = [c for c in CASES if c.get("sensor") == key]
        rendered = harness.evaluate(harness.build_template(sel, exprs, sens))
        got = harness.split_results(rendered, len(sel))
        caught = [c["name"] for c, g in zip(sel, got) if g != str(c["expect"])]
    except harness.ExtractionError as exc:
        # The substitution guard refused to run a case whose expression changed
        # shape. That is a CATCH, not a crash: it is the protection against a
        # case silently passing while reading live state instead of the input.
        print("  CAUGHT  %-44s structural: %s" % (label, str(exc).split(":")[0]))
        continue
    if caught:
        print("  CAUGHT  %-44s by %d case(s): %s" % (label, len(caught), caught[0]))
    else:
        print("  MISSED  %-44s NO CASE DETECTED THIS" % label); allgood = False
print("\n%s" % ("all historical bugs are detected" if allgood else "GAPS EXIST -- add cases"))

# ---------------------------------------------------------------------------
# The guards must themselves fire. A guard that never triggers is indistinguishable
# from one that is broken, so exercise both refusal paths directly.
print("\nGUARD CHECK -- the harness must REFUSE these, not run them\n")
guard_ok = True
for label, subs, why in [
    ("unmatched substitution", {"states('sensor.does_not_exist')": "'1'"},
     "would leave the expression reading the real house"),
    ("wrong type: states() as a bare number", {AC_OFF_G: "-2.0"},
     "would stop testing the string-coercion path"),
]:
    probe = dict(sensor="Climate temp bedroom", name="guard:" + label,
                 expect="", given={}, subs=subs)
    try:
        harness.build_template([probe], REAL_EXPR, REAL_SENS)
        print("  LEAKED  %-40s NOT REFUSED -- %s" % (label, why)); guard_ok = False
    except harness.ExtractionError:
        print("  REFUSED %-40s (%s)" % (label, why))
print("\n%s" % ("both guards fire" if guard_ok else "A GUARD IS NOT FIRING"))
allgood = allgood and guard_ok
sys.exit(0 if allgood else 1)
