#!/usr/bin/env python3
"""Does every entity the templates NAME actually exist?

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


def main():
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
