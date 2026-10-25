#!/usr/bin/env python3
"""The synthetic house must be complete enough that the dashboard renders it without a gap.

    python3 tests/fixtures/test_synthetic.py

CI renders the dashboard against an invented house (tests/fixtures/synthetic.py), never
against the operator's. That house is hand-written, so it drifts: a dashboard change that
names a new entity, or a room tile with no page, would render a hole that no card-error
scan reports. Each check below is one such hole.
"""

import json
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BUILD = os.path.join(HERE, "synthetic.py")
ENTITY_RE = re.compile(
    r"\b(?:sensor|binary_sensor|switch|light|climate|media_player|fan|vacuum|camera|"
    r"alarm_control_panel|person|weather|input_boolean|input_number|input_select|"
    r"input_datetime|input_text|counter|schedule|automation|button|number|select|"
    r"update|remote|lock|image|event|zone|sun|water_heater)\.[a-z0-9_]+")
SERVICES = {"light.turn_off", "light.turn_on", "button.press", "sun.sun"}


def load(d, name):
    with open(os.path.join(d, name), encoding="utf-8") as fh:
        return json.load(fh)


def main():
    out = tempfile.mkdtemp(prefix="synthetic-")
    p = subprocess.run([sys.executable, BUILD, out], capture_output=True, text=True)
    if p.returncode != 0:
        print("synthetic.py failed:\n" + p.stdout + p.stderr)
        return 1
    st = os.path.join(out, "storage")
    cfg = load(st, "lovelace.lovelace")["data"]["config"]
    ents = {e["entity_id"]: e for e in load(st, "core.entity_registry")["data"]["entities"]}
    devs = {d["id"]: d for d in load(st, "core.device_registry")["data"]["devices"]}
    areas = {a["id"]: a for a in load(st, "core.area_registry")["data"]["areas"]}
    floors = {f["floor_id"] for f in load(st, "core.floor_registry")["data"]["floors"]}
    labels = {lb["label_id"] for lb in load(st, "core.label_registry")["data"]["labels"]}
    states = load(out, "states.json")
    views = {v.get("path"): v for v in cfg["views"]}
    bad = []

    # 1. every entity the dashboard names exists (a stem ending in "_" is a Jinja prefix)
    text = json.dumps(cfg)
    for eid in sorted(set(ENTITY_RE.findall(text))):
        if eid in SERVICES or eid.endswith("_"):
            continue
        if eid not in ents:
            bad.append("the dashboard names %s; the synthetic house has no such entity" % eid)

    # 2. every room the floor cards map has a page, and the area is on that card's floor
    for v in cfg["views"]:
        for sec in v.get("sections") or []:
            for c in sec.get("cards") or []:
                if "rooms" in c:
                    for a, o in c["rooms"].items():
                        if a not in areas:
                            bad.append("floor card maps unknown area %s" % a)
                        elif areas[a].get("floor_id") != c.get("floor"):
                            bad.append("area %s is mapped on %s's card but sits on %s"
                                       % (a, c.get("floor"), areas[a].get("floor_id")))
                        if o.get("page") not in views:
                            bad.append("room %s links to page %r, which is not a view" % (a, o.get("page")))

    # 3. every area is on a floor that exists, and has entities (a tile renders only then)
    for a in areas.values():
        if a.get("floor_id") not in floors:
            bad.append("area %s is on no known floor" % a["id"])
        if not any((e.get("area_id") or (devs.get(e.get("device_id")) or {}).get("area_id")) == a["id"]
                   for e in ents.values()):
            bad.append("area %s has no entities, so it would render no tile" % a["id"])

    # 4. every entity has a designed state, and the labels it carries exist
    for eid, e in ents.items():
        if eid not in states:
            bad.append("%s has no state in states.json" % eid)
        for lb in e.get("labels") or []:
            if lb not in labels:
                bad.append("%s carries label %s, which is not in the label registry" % (eid, lb))

    # 5. the room card can resolve each room: a Magic Areas all-lights group and occupancy
    for a in areas:
        mine = [e for e in ents.values()
                if (e.get("area_id") or (devs.get(e.get("device_id")) or {}).get("area_id")) == a]
        if not any(e["platform"] == "magic_areas" and e["entity_id"].endswith("_all_lights") for e in mine):
            bad.append("area %s has no Magic Areas all-lights group" % a)
        if not any(e["platform"] == "magic_areas" and e.get("original_device_class") == "occupancy"
                   for e in mine):
            bad.append("area %s has no Magic Areas occupancy sensor" % a)

    if bad:
        print("%d gap(s) in the synthetic house\n" % len(bad))
        for b in bad:
            print("  " + b)
        return 1
    print("synthetic house complete: %d areas, %d entities, %d views" % (len(areas), len(ents), len(views)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
