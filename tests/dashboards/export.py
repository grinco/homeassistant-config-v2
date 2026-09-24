#!/usr/bin/env python3
"""Re-export the sanitised snapshots under `lovelace-dashboards/` and `automations/`.

AGENTS.md states the rules for an export as prose. Every one of them has been
broken at least once by someone following them carefully, so they are code here:

  1. every replacement is anchored with lookarounds that exclude only letters
     and digits. `\\b` is NOT a safe boundary - `_` is a word character, so a
     `\\b`-anchored pattern silently fails to match `..._NAME_room_area_state`.
     That shipped into a commit on 2026-09-21;
  2. the multi-token forms are applied BEFORE the general stems, longest first,
     so published ids keep matching the exports already committed;
  3. canary words are counted before and after. A stem that is a substring of
     ordinary English (the general case, not a hypothetical) makes a greedy
     pattern corrupt prose and Jinja alike, and the count is what notices;
  4. the result is scanned for every original term and must contain none.

The live names are NOT in this file and must never be. They are read from
`tests/climate/rooms.local.json`, which is gitignored and is the only place on
disk that holds them - the same file `leakcheck.py` reads.

    python3 tests/dashboards/export.py           # write the files
    python3 tests/dashboards/export.py --check   # verify only, write nothing
"""

import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
REPO = os.path.dirname(os.path.dirname(HERE))
STORAGE = os.environ.get("HA_STORAGE", "/usr/share/hassio/homeassistant/.storage")
ROOMS = os.path.join(REPO, "tests", "climate", "rooms.local.json")
OUT = os.path.join(REPO, "lovelace-dashboards")

# view path -> file. The admin panel is deliberately absent: it carries Wi-Fi
# network names, firewall rules and VPN routes, which a public reference repo
# has no business holding. That is a standing exclusion, not an oversight.
SINGLE = {
    "home": "home-view.json",
    "climate": "climate-view.json",
    "climate-advanced": "climate-advanced-view.json",
    "energy": "energy-view.json",
    "appliances": "appliances-view.json",
    "security": "security-view.json",
}
ROOM_FILE = "room-views.json"

AUTOMATIONS_YAML = os.environ.get(
    "HA_AUTOMATIONS", "/usr/share/hassio/homeassistant/automations.yaml")
AUTO_OUT = os.path.join(REPO, "automations")
# automation id -> file. Exported because `automations/README.md` promises these
# track the instance, and a snapshot nobody refreshes is worse than none.
AUTOS = {
    "1789725511503": "climate-maintain-per-room-targets.json",
    "1789802676002": "climate-stamp-ha-start.json",
    "1789947000001": "purifier-after-cat-toilet.json",
}
# `automations/resolved-sensors.json` is NOT re-exported here. It is a curated
# selection of config-flow helpers rather than a whole-file dump, and nothing in
# this change touched a template sensor. Left for whoever next changes one.

# Ordinary English that contains one of the stems. If a count moves, the
# pattern reached into prose and the export is wrong.
CANARIES = ("deliberately", "believe", "believed", "relies", "relied", "delivered",
            "deliver", "reliable", "reliability", "relief", "delight", "delightful",
            "irrelevant", "elsewhere", "selection", "Delete", "self", "shelf",
            "elif", "else", "helper", "helpers")


def load_rooms():
    if not os.path.exists(ROOMS):
        raise SystemExit(
            "%s is missing.\n"
            "It is gitignored and holds the live room names plus the published\n"
            "mapping. Without it this script cannot anonymise, and exporting raw\n"
            "would publish a child's name. Recreate it, or stop and ask the\n"
            "operator - do not invent a mapping." % ROOMS)
    with io.open(ROOMS, encoding="utf-8") as fh:
        return json.load(fh)


def substitutions(rooms):
    subs = rooms.get("substitutions")
    if not subs:
        raise SystemExit("rooms.local.json carries no `substitutions` table")
    return [tuple(x) for x in subs["specific"]], [tuple(x) for x in subs["general"]]


def anchored(term):
    """A boundary that treats `_` as a separator, because `\\b` does not."""
    return re.compile(r"(?<![A-Za-z0-9])%s(?![A-Za-z0-9])" % re.escape(term))


def scrub(text, specific, general):
    for live, pub in specific:          # multi-token forms first, longest first
        text = anchored(live).sub(pub, text)
    for live, pub in general:
        text = anchored(live).sub(pub, text)
    return text


def main():
    check_only = "--check" in sys.argv
    rooms = load_rooms()
    specific, general = substitutions(rooms)
    tokens = list(rooms.get("scrub_tokens") or [])

    with io.open(os.path.join(STORAGE, "lovelace.lovelace"), encoding="utf-8") as fh:
        cfg = json.load(fh)["data"]["config"]

    views = {v.get("path"): v for v in cfg["views"] if v.get("path")}
    payload = {}
    for path, fname in SINGLE.items():
        if path in views:
            payload[fname] = views[path]
    room_views = [v for v in cfg["views"]
                  if v.get("subview") and v.get("back_path") == "/lovelace/home"
                  and v.get("path") != "home-classic"]
    payload[ROOM_FILE] = room_views

    # the automations, read from the same file the test harness reads
    import yaml
    with io.open(AUTOMATIONS_YAML, encoding="utf-8") as fh:
        autos = yaml.safe_load(fh)
    auto_payload = {}
    for a in autos:
        fname = AUTOS.get(str(a.get("id")))
        if fname:
            auto_payload[fname] = a
    missing = sorted(set(AUTOS.values()) - set(auto_payload))
    if missing:
        print("WARNING - these automations are no longer in the live file:")
        for m in missing:
            print("   %s" % m)

    payload.update(auto_payload)
    raw = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True)
    before = dict((w, raw.count(w)) for w in CANARIES)
    clean = scrub(raw, specific, general)
    after = dict((w, clean.count(w)) for w in CANARIES)

    moved = sorted(w for w in CANARIES if before[w] != after[w])
    if moved:
        print("CANARY MOVED - the substitution reached into ordinary text:")
        for w in moved:
            print("   %-14s %d -> %d" % (w, before[w], after[w]))
        return 1

    leaked = []
    for term in tokens + [s[0] for s in specific]:
        if anchored(term).search(clean):
            leaked.append(term)
    if leaked:
        print("LEAK - %d original term(s) survived the scrub:" % len(leaked))
        for t in leaked:
            print("   (term withheld; index %d)" % (tokens + [s[0] for s in specific]).index(t))
        return 1

    out = json.loads(clean)
    written = []
    for fname, data in sorted(out.items()):
        target = os.path.join(AUTO_OUT if fname in AUTOS.values() else OUT, fname)
        body = json.dumps(data, ensure_ascii=False, indent=1) + "\n"
        if check_only:
            existing = ""
            if os.path.exists(target):
                with io.open(target, encoding="utf-8") as fh:
                    existing = fh.read()
            if existing != body:
                written.append(fname + "  (differs)")
            continue
        with io.open(target, "w", encoding="utf-8") as fh:
            fh.write(body)
        written.append(fname)

    print("canaries unmoved (%d words), zero original terms in the output" % len(CANARIES))
    if check_only:
        if written:
            print("%d file(s) are out of date:" % len(written))
            for w in written:
                print("   %s" % w)
            return 1
        print("every exported file matches the live instance")
        return 0
    for w in written:
        print("  wrote %s" % w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
