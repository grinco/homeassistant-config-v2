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
 ("boot grace dropped again (v5.4)", "expr", "no_temp",
  lambda t: t.replace(" and uptime > boot_grace", "")),
 # purifier automation -- bugs it would be natural to write
 ("purifier: bare state trigger (fires on midnight reset)", "expr2", "visit_happened",
  lambda t: "{{ trigger.id == 'visit' }}"),
 ("purifier: no numeric guard on the previous value", "expr2", "visit_happened",
  lambda t: t.replace("(trigger.from_state.state | float(-1)) >= 0 and ", "")),
 ("purifier: turns off a purifier a person started", "expr2", "we_may_stop",
  lambda t: "{{ is_state('fan.corridor_xiaomi_air_purifier','on') }}"),
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
 # CO2 additions
 ("health risk: CO2 check dropped", "sensor", "Climate health risk",
  lambda t: t.replace("{% if c >= 1400 %}{% set ns.risk = true %}{% endif %}", "")),
 ("health risk: missing CO2 reads as danger", "sensor", "Climate health risk",
  lambda t: t.replace("{% if c >= 1400 %}", "{% if c < 1400 %}")),
 ("health risk: CO2 check swallows the humidity check", "sensor", "Climate health risk",
  lambda t: t.replace("{% if h >= 65 or h < 30 or t < 16 %}", "{% if false %}")),
]

print("MUTATION CHECK -- each row re-introduces a bug that actually shipped\n")
allgood = True
for label, kind, key, mutate in BUGS:
    exprs, sens = dict(REAL_EXPR), dict(REAL_SENS)
    if kind == "expr2":
        # A second automation: mutate its expression by shadowing the loader,
        # so the case still runs against everything else unchanged.
        exprs2 = dict(harness.load_expressions("1789947000001"))
        before = exprs2[key]
        exprs2[key] = mutate(before)
        if exprs2[key] == before:
            print("  ?? %-46s MUTATION DID NOT APPLY" % label); allgood = False; continue
        orig = harness.load_expressions
        harness.load_expressions = lambda aid=None, _o=orig, _e=exprs2: (
            _e if aid == "1789947000001" else _o(aid) if aid else _o())
        try:
            rendered = harness.evaluate(harness.build_template(CASES, exprs, sens))
            got = harness.split_results(rendered, len(CASES))
            caught = [c["name"] for c, g in zip(CASES, got) if g != str(c["expect"])]
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
        rendered = harness.evaluate(harness.build_template(CASES, exprs, sens))
        got = harness.split_results(rendered, len(CASES))
        caught = [c["name"] for c, g in zip(CASES, got) if g != str(c["expect"])]
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
