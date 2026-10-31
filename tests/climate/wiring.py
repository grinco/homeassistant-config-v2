#!/usr/bin/env python3
"""Does every entity the templates NAME actually exist? And is every copy of night tested?

The scenario suite cannot answer this. It substitutes each impure read with a
literal before evaluating, which is what makes it a decision oracle -- and also
why a template can name `sensor.does_not_exist` and still pass every case about
the arithmetic it performs on that value.

That gap shipped on 2026-09-21: `Radiation dose rate` read
`sensor.background_radiation_cpm` while the device actually published
`sensor.hallway_geiger_counter_ble_proxy_background_radiation_cpm`. Five cases
passed. The sensor read `unknown` in the house.

This check is the other half: pull every entity id out of the live templates and
ask Home Assistant whether it exists. It proves nothing about values -- only that
the names resolve.
"""

import re
import sys

sys.path.insert(0, __file__.rsplit("/", 1)[0])

import harness  # noqa: E402

CHUNK = 12  # same ceiling as the scenario suite: a larger template fails to render

REF = re.compile(
    r"""(?:states|is_state|state_attr|has_value|is_state_attr)\s*\(\s*['"]([a-z_]+\.[a-z0-9_]+)['"]"""
    r"""|states\s*\[\s*['"]([a-z_]+\.[a-z0-9_]+)['"]\s*\]"""
)


def referenced():
    """Every literal entity id named by a template sensor, and who names it.

    Ids built by concatenation -- `states('sensor.climate_temp_' ~ r)` in the
    health-risk sensor -- are NOT entity ids, they are prefixes. They are skipped
    rather than reported missing, which would be a permanent false alarm.
    """
    out, skipped = {}, set()
    for title, tpl in sorted(harness.load_sensor_templates().items()):
        for match in REF.finditer(tpl):
            eid = match.group(1) or match.group(2)
            if eid.endswith("_"):
                skipped.add(eid)
                continue
            out.setdefault(eid, []).append(title)
    return out, sorted(skipped)


def probe(ids):
    """Ask HA whether each id resolves, in chunks, refusing an unrendered answer."""
    out = []
    for i in range(0, len(ids), CHUNK):
        batch = ids[i:i + CHUNK]
        tpl = "".join(
            "%s{{ 'MISSING' if states[%r] is none else 'ok' }}" % (harness.SENTINEL, eid)
            for eid in batch
        ) + harness.SENTINEL
        results = harness.split_results(harness.evaluate(tpl), len(batch))
        for eid, res in zip(batch, results):
            # A result that is neither token means the template was NOT evaluated
            # -- an error body or the source echoed back. Treating that as a pass
            # is how the first version of this check reported 46/46 clean while
            # one of them was genuinely missing.
            if res not in ("ok", "MISSING"):
                raise harness.ExtractionError(
                    "probing %s returned %r, which is neither 'ok' nor 'MISSING' "
                    "-- the template did not evaluate, so this run proves nothing"
                    % (eid, res[:120]))
            out.append((eid, res))
    return out


def night_copies():
    """Every live definition of night that the truth table in cases.py does not run.

    The definition is copied into each consumer on purpose (harness.NIGHT_CONSUMERS says why),
    so the hazard is a copy nobody tests: edited in one place, it drifts from the rest.
    """
    known = {(where, key) for _who, where, key in harness.NIGHT_CONSUMERS}
    found = set(harness.night_definitions())
    return sorted(found - known), sorted(known - found)


ENERGY = harness.ENTRIES.replace("core.config_entries", "energy")


def digest_meters(prefs_path=ENERGY):
    """The energy digest's meter list against the Energy dashboard's, both ways.

    The digest copies the list because an automation cannot read the Energy preferences. A meter
    added to the dashboard and not to the digest would be missing from every daily total, silently.
    A meter the dashboard counts inside another (`included_in_stat`) is not a separate use.
    """
    import io
    import json
    with io.open(prefs_path, encoding="utf-8") as fh:
        prefs = json.load(fh)["data"]
    want = [d["stat_consumption"] for d in prefs.get("device_consumption") or []
            if not d.get("included_in_stat")]
    ids = harness.load_expressions(DIGEST_ID).get("ids")
    if ids is None:
        import yaml
        with io.open(harness.AUTOMATIONS, encoding="utf-8") as fh:
            auto = [a for a in yaml.safe_load(fh) if str(a.get("id")) == DIGEST_ID][0]
        ids = next(a["variables"]["ids"] for a in auto["actions"]
                   if isinstance(a.get("variables"), dict) and "ids" in a["variables"])
    return sorted(set(want) - set(ids)), sorted(set(ids) - set(want))


def sockets_on_energy(prefs_path=ENERGY):
    """Every metered socket is on the Energy dashboard, and every meter there still exists.

    Adding a plug to the Energy dashboard is the one step Home Assistant does not let a
    dashboard generate (docs/self-maintaining-dashboards.md), so it is the step that gets
    missed: on 2026-10-31 three new plugs were absent and a gone vacuum dock was still summed.
    A metered socket is the Energy tab's own rule: a power sensor not made by Powercalc, on a
    device with a switch and no climate entity. Its meter is that device's energy sensor.
    """
    import io
    import json
    reg = harness.ENTRIES.replace("core.config_entries", "core.entity_registry")
    with io.open(reg, encoding="utf-8") as fh:
        ents = [e for e in json.load(fh)["data"]["entities"] if not e.get("disabled_by")]
    with io.open(prefs_path, encoding="utf-8") as fh:
        prefs = json.load(fh)["data"]
    on = {d["stat_consumption"] for d in prefs.get("device_consumption") or []}
    cls = lambda e: e.get("device_class") or e.get("original_device_class")
    by_dev = {}
    for e in ents:
        if e.get("device_id"):
            by_dev.setdefault(e["device_id"], []).append(e)
    missing = []
    for did, dev in by_dev.items():
        ids = [e["entity_id"] for e in dev]
        mine = [e for e in dev if e.get("platform") != "powercalc"]
        if not (any(cls(e) == "power" and e["entity_id"].startswith("sensor.") for e in mine)
                and any(i.startswith("switch.") for i in ids)
                and not any(i.startswith("climate.") for i in ids)):
            continue
        meters = sorted(e["entity_id"] for e in mine
                        if cls(e) == "energy" and e["entity_id"].startswith("sensor."))
        if meters and not on & set(meters):
            missing.append(meters[0])
    known = {e["entity_id"] for e in ents}
    return sorted(missing), sorted(on - known)


DIGEST_ID = "1792100000001"


def main():
    missing, extra = digest_meters()
    for m in missing:
        print("  DIGEST MISSES  %s is on the Energy dashboard but not in the digest" % m)
    for m in extra:
        print("  DIGEST EXTRA   %s is in the digest but not on the Energy dashboard" % m)
    if missing or extra:
        print("\nThe energy digest must sum exactly the Energy dashboard's meters.")
        return 1
    print("  the energy digest sums exactly the Energy dashboard's meters")

    unlisted, gone = sockets_on_energy()
    for m in unlisted:
        print("  NOT ON ENERGY   %s meters a socket but is not on the Energy dashboard" % m)
    for m in gone:
        print("  GONE METER      %s is on the Energy dashboard but no longer exists" % m)
    if unlisted or gone:
        print("\nEvery metered socket belongs on the Energy dashboard (Settings > Dashboards > Energy).")
        return 1
    print("  every metered socket is on the Energy dashboard")

    stray, gone = night_copies()
    for where, key in stray:
        print("  UNTESTED NIGHT  %s / %s defines night but is not in harness.NIGHT_CONSUMERS"
              % (where, key))
    for where, key in gone:
        print("  STALE NIGHT     %s / %s is in harness.NIGHT_CONSUMERS but defines no night"
              % (where, key))
    if stray or gone:
        print("\nEvery copy of the night definition must run the same truth table.")
        return 1
    print("  all %d definitions of night are under the truth table" % len(harness.NIGHT_CONSUMERS))

    refs, skipped = referenced()
    if not refs:
        print("SUITE ERROR: no entity references found -- the extractor is broken",
              file=sys.stderr)
        return 2

    try:
        results = probe(sorted(refs))
    except harness.ExtractionError as exc:
        print("SUITE ERROR: %s" % exc, file=sys.stderr)
        return 2

    missing = [(eid, refs[eid]) for eid, res in results if res == "MISSING"]
    print("checked %d entity references across %d template sensors"
          % (len(results), len(harness.load_sensor_templates())))
    if skipped:
        print("skipped %d concatenated prefix(es): %s" % (len(skipped), ", ".join(skipped)))
    print("")
    for eid, titles in missing:
        print("  MISSING  %s" % eid)
        for title in titles:
            print("             named by: %s" % title)
    if missing:
        print("\n%d reference(s) name an entity that does not exist. A template "
              "reading a missing entity does not error -- it silently takes its "
              "fallback, so this fails quietly in the house." % len(missing))
        return 1
    print("  all %d references resolve" % len(results))
    return 0


if __name__ == "__main__":
    sys.exit(main())
