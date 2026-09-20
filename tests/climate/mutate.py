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
 ("boot grace dropped again (v5.4)", "expr", "no_temp",
  lambda t: t.replace(" and uptime > boot_grace", "")),
]

print("MUTATION CHECK -- each row re-introduces a bug that actually shipped\n")
allgood = True
for label, kind, key, mutate in BUGS:
    exprs, sens = dict(REAL_EXPR), dict(REAL_SENS)
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
