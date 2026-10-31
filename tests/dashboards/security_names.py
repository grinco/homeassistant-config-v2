#!/usr/bin/env python3
"""Does Security -> Sensors read cleanly? Renders the LIVE generator and checks its names.

lint.py works offline from `.storage` and cannot evaluate Jinja, so the generator's
naming is checked here by rendering its own template through Home Assistant (the
transport tests/climate uses). The logic is not copied: the template is read out of
the dashboard at run time.

2026-10-31: the flat list carried three tiles all named "Corridor zone open" (the
Paradox zones Entrance Door, Entrance PIR and Tamper) and names like "Kitchen kitchen
work ..." that ran off a phone screen. The section is now grouped by room, so:

  S1 the section is grouped: a heading per room, then that room's sensors;
  S2 within a room every sensor name is unique;
  S3 no sensor name repeats its room's name (the heading already says it);
  S4 no name is empty.

    python3 tests/dashboards/security_names.py
"""
import ast
import io
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "climate"))
import harness  # noqa: E402

STORAGE = os.environ.get("HA_STORAGE", "/usr/share/hassio/homeassistant/.storage")


def generator():
    with io.open(os.path.join(STORAGE, "lovelace.lovelace"), encoding="utf-8") as fh:
        cfg = json.load(fh)["data"]["config"]
    view = [v for v in cfg["views"] if v.get("path") == "security"][0]
    for sec in view["sections"]:
        if sec["cards"] and sec["cards"][0].get("heading") == "Sensors":
            # Only the cards under the Sensors heading: Presence shares the section.
            mine = []
            for c in sec["cards"][1:]:
                if c.get("type") == "heading":
                    break
                mine.append(c)
            gens = [c for c in mine if c.get("type") == "custom:auto-entities"]
            if len(gens) != 1:
                raise SystemExit("Security -> Sensors: expected one generator, found %d" % len(gens))
            return gens[0]
    raise SystemExit("Security -> Sensors: section not found")


def main():
    gen = generator()
    tpl = gen["filter"]["template"]
    pre = "{%% set config = %s %%}" % json.dumps({k: v for k, v in gen.items() if k != "filter"})
    out = harness.evaluate(harness.SENTINEL + pre + tpl + harness.SENTINEL)
    body = out.split(harness.SENTINEL)[1].strip()
    cards = ast.literal_eval(body)

    bad = []
    groups, room = [], None
    for c in cards:
        if c.get("type") == "heading":
            room = c.get("heading") or ""
            groups.append((room, []))
        elif c.get("type") == "grid":
            if not groups:
                bad.append("S1 a sensor grid comes before any room heading")
                continue
            groups[-1][1].extend(x.get("name", "") for x in c.get("cards", []))
        else:
            bad.append("S1 ungrouped card %s (%s)" % (c.get("entity"), c.get("name")))
    if not groups:
        bad.append("S1 no room headings at all - the list is flat")
    for room, names in groups:
        seen = set()
        for n in names:
            if not n.strip():
                bad.append("S4 %s: a sensor with no name" % room)
            if n.lower() in seen:
                bad.append("S2 %s: '%s' appears twice" % (room, n))
            seen.add(n.lower())
            if room and room.lower() in n.lower():
                bad.append("S3 %s: '%s' repeats the room" % (room, n))

    for b in bad:
        print("  FAIL  " + b)
    print("%d room(s), %d sensor(s), %d problem(s)" % (
        len(groups), sum(len(n) for _r, n in groups), len(bad)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
