#!/usr/bin/env python3
"""Re-export the sanitised snapshots under `lovelace-dashboards/`, `automations/` and
`tests/fixtures/real/` (local only, gitignored: the real house for a local render run).

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
# The templates every view uses. Its comment header is prose kept in the file itself; the export
# replaces only what follows it. Exported since 2026-10-20 (issue #1 found the copy unchecked).
TEMPLATES = "button-card-templates.yaml"


def templates_header(path):
    if not os.path.exists(path):
        return ""
    with io.open(path, encoding="utf-8") as fh:
        text = fh.read()
    m = re.search(r"^button_card_templates:", text, re.M)
    return text[:m.start()] if m else ""

AUTOMATIONS_YAML = os.environ.get(
    "HA_AUTOMATIONS", "/usr/share/hassio/homeassistant/automations.yaml")
AUTO_OUT = os.path.join(REPO, "automations")
# automation id -> file. Exported because `automations/README.md` promises these
# track the instance, and a snapshot nobody refreshes is worse than none.
AUTOS = {
    "1789725511503": "climate-maintain-per-room-targets.json",
    "1789802676002": "climate-stamp-ha-start.json",
    "1789947000001": "purifier-after-cat-toilet.json",
    "1792300000001": "purifier-bedroom-air-quality.json",
    "1790200000001": "house-night-mode.json",
    "1790300000001": "climate-radiators.json",
    "1790400000001": "house-alarm-sync.json",
    "1790500000001": "house-away.json",
    "1791800830017": "house-everyone-left.json",
    "1791800829345": "battery-watchdog.json",
    "1792000000001": "house-front-door-away.json",
    "1792100000001": "energy-digest.json",
    "1792200000001": "house-morning-briefing.json",
}
# `automations/resolved-sensors.json` is a curated selection of config-flow helpers
# rather than a whole-file dump: these titles, in this order, as PUBLISHED (after the
# scrub). Until 2026-10-20 it was edited by hand, and the audit of that day found three
# helpers the dashboards and automations read that it did not carry.
RESOLVED = "resolved-sensors.json"
RESOLVED_TITLES = (
    "Indoor Temperature", "Indoor Humidity", "Downstairs Temperature", "Downstairs Humidity",
    "Upstairs Temperature", "Upstairs Humidity", "Any low battery", "AC power total",
    "Socket power total", "Climate temp living room", "Climate temp office",
    "Climate temp bedroom", "Climate temp kid1", "Climate temp kid2",
    "Climate humidity living room", "Climate humidity office", "Climate humidity bedroom",
    "Climate humidity kid1", "Climate humidity kid2", "Climate health risk",
    "Climate temp corridor", "Climate temp outdoor", "Climate humidity corridor",
    "Climate co2 living room", "Climate co2 office", "Radiation dose rate", "Lighting daylight",
    "Any safety alarm", "Any safety sensor silent", "Lighting night", "Lighting left on",
    "Lighting living room bright", "Lighting hallway bright", "Lighting bedroom sleep",
    "Lighting corridor presence",
)
RESOLVED_NOTE = (
    "Resolved per-room sensors, the floor/household and power aggregates derived from them, "
    "the climate health-risk binary sensor, and the roll-ups Home's Needs attention reads. "
    "Reference only; entity ids are anonymised. Exported by tests/dashboards/export.py. "
    "2026-10-07: 'Lighting daylight' (on = bright enough, no lights) is the dark entity Magic "
    "Areas reads before switching a room's lights on; the bathroom's and shower's readings are "
    "Magic Areas aggregates (one sensor each, lint C20), not template sensors. 2026-10-09: 'Any "
    "safety alarm' rolls up every leak/smoke/gas/CO/safety binary sensor in the house for Home's "
    "Needs attention; it excludes itself so it cannot latch. 2026-10-12: 'Any low battery' lists "
    "every battery under 20 % that a person replaces (phones, the car and vacuums are skipped; by "
    "entity id since 2026-10-20, so Home can make each one a tile), "
    "'Lighting left on' the lights still on; both say 'none' when there is nothing to say. "
    "2026-10-14: 'Any safety sensor silent' names a safety sensor unavailable for 30 minutes. "
    "2026-10-20: 'Lighting living room bright', 'Lighting kitchen dark' and 'Lighting hallway "
    "bright' are the dark entities Magic Areas reads for the open space and the hallway: the "
    "room's own lux in real time, with outdoor daylight only as the fallback "
    "(docs/presence-lighting.md). 2026-10-20: 'Any low battery' is the ONE battery list; the "
    "binary 'Any battery low' and the Home card's own copy (15 %, a volvo substring skip) are "
    "gone (lint C29). 'Lighting night' is the helper dashboards read for night; the automations "
    "keep their own copy of the same expression (tests/climate/harness.py NIGHT_CONSUMERS). "
    "2026-10-21: the kitchen reads 'Lighting living room bright' natively as its dark entity "
    "(one open space), so 'Lighting kitchen dark' is no longer exported or read. 'Lighting bedroom "
    "sleep' (night, or before noon) is the bedroom's sleep entity: no lamps when someone turns "
    "over in bed after the alarm leaves Night at 06:00. 2026-10-25: 'Lighting corridor presence' "
    "(some corridor sensor other than the stairs one sees someone) is the corridor's accent "
    "entity: the stairs sensor lights the corridor light, and only the corridor proper lights "
    "the entrance light."
)
# Magic Areas lives in config entries and the night schedule in `.storage/schedule`; neither is
# in a dashboard or automations.yaml, so until 2026-10-21 the repo did not show them at all.
MAGIC_AREAS = "magic-areas.json"
MAGIC_AREAS_NOTE = (
    "Magic Areas options for every area, as configured on the instance (entry_ts dropped). "
    "Reference only; entity ids and area names are anonymised. Exported by "
    "tests/dashboards/export.py. Reasoning: docs/presence-lighting.md."
)
SCHEDULE = "night-schedule.json"
SCHEDULE_ID = "climate_night"
SCHEDULE_NOTE = (
    "schedule.climate_night. It does not decide night: it only moves the alarm at its edges "
    "(house-night-mode.json), and stands in for night while the alarm itself is unavailable."
)

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


def _kid_badges(views):
    """A child's name and room share one placeholder in the general map ("Kids room N"), which on a
    person badge reads as a room (issue #4). Structural, so no name is needed: a badge whose
    entity is an anonymised child is labelled as a person."""
    for view in views:
        for badge in (view.get("badges") or []) if isinstance(view, dict) else []:
            m = re.match(r"person\.kid(\d+)_", str(badge.get("entity", "")))
            if m and "name" in badge:
                badge["name"] = "Kid %s" % m.group(1)


def _fixtures_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "fixture_export", os.path.join(REPO, "tests", "fixtures", "export.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def export_fixtures(specific, general, tokens, check_only):
    """tests/fixtures/real (local only): allowlisted (fixtures/export.py), scrubbed and gated here.

    Returns the list of files written (or differing, with --check), or None on refusal.
    Refuses on a moved canary, a surviving term, a privacy-check failure, or a lint failure
    against the new fixtures.
    """
    import shutil
    import subprocess
    import tempfile
    fx = _fixtures_module()
    docs = fx.build(STORAGE)
    terms = tokens + [x[0] for x in specific]
    texts = {}
    for name, doc in docs.items():
        raw = fx.dumps(doc)
        clean = scrub(raw, specific, general)
        moved = [w for w in CANARIES if raw.count(w) != clean.count(w)]
        if moved:
            print("CANARY MOVED in fixture %s: %s" % (name, ", ".join(moved)))
            return None
        if any(anchored(t).search(clean) for t in terms):
            print("LEAK - an original term survived the scrub in fixture %s (term withheld)" % name)
            return None
        parsed = json.loads(clean)
        if name == "lovelace.lovelace":
            _kid_badges(parsed["data"]["config"]["views"])
        texts[name] = fx.dumps(parsed)

    before = fx.committed_vocabulary()
    after = fx.vocabulary({n: json.loads(t) for n, t in texts.items()})
    if before is not None:
        new = sorted(after - before)
        if new:
            print("NEW WORDS in fixture names since the committed fixture - read them; a person's")
            print("name here means the substitution map needs a new entry before this ships:")
            print("   " + ", ".join(new))

    tmp = tempfile.mkdtemp(prefix="fixtures-")
    try:
        for name, text in texts.items():
            with io.open(os.path.join(tmp, name), "w", encoding="utf-8") as fh:
                fh.write(text)
        env = dict(os.environ, HA_STORAGE=tmp, FIXTURE_STORAGE=tmp, LINT_DASHBOARDS="lovelace")
        for script in (os.path.join(REPO, "tests", "fixtures", "check.py"),
                       os.path.join(REPO, "tests", "dashboards", "lint.py")):
            p = subprocess.run([sys.executable, script], env=env, capture_output=True, text=True)
            if p.returncode != 0:
                print("REFUSING to write fixtures: %s fails on them\n%s" % (
                    os.path.relpath(script, REPO), p.stdout[-3000:] + p.stderr[-2000:]))
                return None
        changed = []
        os.makedirs(fx.OUT, exist_ok=True)
        for name, text in sorted(texts.items()):
            target = os.path.join(fx.OUT, name)
            existing = None
            if os.path.exists(target):
                with io.open(target, encoding="utf-8") as fh:
                    existing = fh.read()
            if existing == text:
                continue
            changed.append("fixtures/" + name + ("  (differs)" if check_only else ""))
            if not check_only:
                shutil.copy(os.path.join(tmp, name), target)
        return changed
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


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

    # the curated helpers: scrubbed before matching, because the list holds published titles
    with io.open(os.path.join(STORAGE, "core.config_entries"), encoding="utf-8") as fh:
        entries = json.load(fh)["data"]["entries"]
    by_title = {}
    for e in entries:
        pub = scrub(e.get("title") or "", specific, general)
        if pub in RESOLVED_TITLES and e.get("domain") in ("template", "min_max"):
            by_title[pub] = {"domain": e["domain"], "title": e.get("title"),
                             "options": e.get("options") or {}}
    gone = [t for t in RESOLVED_TITLES if t not in by_title]
    if gone:
        print("WARNING - these curated helpers are no longer on the instance:")
        for t in gone:
            print("   %s" % t)
    payload[RESOLVED] = {"note": RESOLVED_NOTE,
                         "entries": [by_title[t] for t in RESOLVED_TITLES if t in by_title]}

    areas = []
    for e in entries:
        if e.get("domain") == "magic_areas":
            opts = dict(e.get("options") or {})
            opts.pop("entity_ts", None)
            areas.append({"title": e.get("title"), "options": opts})
    payload[MAGIC_AREAS] = {"note": MAGIC_AREAS_NOTE,
                            "areas": sorted(areas, key=lambda a: a["options"].get("id", ""))}

    with io.open(os.path.join(STORAGE, "schedule"), encoding="utf-8") as fh:
        schedules = json.load(fh)["data"]["items"]
    night = [x for x in schedules if x.get("id") == SCHEDULE_ID]
    if not night:
        print("WARNING - schedule.%s is no longer on the instance" % SCHEDULE_ID)
    else:
        payload[SCHEDULE] = {"note": SCHEDULE_NOTE, "schedule": night[0]}

    # The button-card templates keep their own key order (a YAML file people read top to bottom),
    # so they are scrubbed as a separate text under the same canary and leak checks.
    templates = json.dumps({"button_card_templates": cfg.get("button_card_templates") or {}},
                           ensure_ascii=False)
    raw = json.dumps(payload, ensure_ascii=False, indent=1, sort_keys=True) + "\n" + templates
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

    clean_payload, clean_templates = clean.rsplit("\n", 1)
    out = json.loads(clean_payload)
    out[TEMPLATES] = json.loads(clean_templates)

    for data in out.values():
        _kid_badges(data if isinstance(data, list) else [data])
    written = []
    for fname, data in sorted(out.items()):
        to_auto = fname in AUTOS.values() or fname in (RESOLVED, MAGIC_AREAS, SCHEDULE)
        target = os.path.join(AUTO_OUT if to_auto else OUT, fname)
        if fname == TEMPLATES:
            body = templates_header(target) + yaml.safe_dump(
                data, sort_keys=False, allow_unicode=True, width=100)
        else:
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
    fixtures_result = export_fixtures(specific, general, tokens, check_only)
    if fixtures_result is None:
        return 1
    written.extend(fixtures_result)
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
