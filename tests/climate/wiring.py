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
    # A device already on the dashboard as a source (the Solix: solar + battery) is
    # placed; listing it as a consumer too would count it twice.
    sources = {v for s in prefs.get("energy_sources") or [] for k, v in s.items()
               if k.startswith("stat_energy") and v}
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
        if meters and not (on | sources) & set(meters):
            missing.append(meters[0])
    known = {e["entity_id"] for e in ents}
    return sorted(missing), sorted(on - known)


DIGEST_ID = "1792100000001"
GRID_ID = "metered_grid_import"


def grid_meters(prefs_path=ENERGY):
    """sensor.metered_grid_import sums exactly the Energy dashboard's meters, and is its grid.

    There is no mains meter; the grid import is made up from the device meters
    (docs/energy-digest.md). Its trigger list is a copy of the dashboard's device list,
    so a meter added to one and not the other makes the dashboard's balance wrong
    silently: a missing meter shows as negative untracked use, an extra one as phantom
    use. Returns (missing, extra, problem) where problem names a wiring error or is None.
    """
    import io
    import json
    import os
    import yaml

    class Loader(yaml.SafeLoader):
        pass
    Loader.add_multi_constructor("!", lambda loader, suffix, node: None)
    with io.open(prefs_path, encoding="utf-8") as fh:
        prefs = json.load(fh)["data"]
    want = [d["stat_consumption"] for d in prefs.get("device_consumption") or []
            if not d.get("included_in_stat")]
    cfg = os.path.join(os.path.dirname(harness.AUTOMATIONS), "configuration.yaml")
    with io.open(cfg, encoding="utf-8") as fh:
        conf = yaml.load(fh, Loader=Loader) or {}
    blocks = conf.get("template") or []
    block = next((b for b in blocks for s in b.get("sensor") or []
                  if s.get("unique_id") == GRID_ID), None)
    if block is None:
        return want, [], "no template sensor with unique_id %s in configuration.yaml" % GRID_ID
    ids = []
    for t in block.get("triggers") or block.get("trigger") or []:
        e = t.get("entity_id") or []
        ids += [e] if isinstance(e, str) else e
    grids = [s for s in prefs.get("energy_sources") or [] if s.get("type") == "grid"]
    problem = None
    sensor = next(s for s in block["sensor"] if s.get("unique_id") == GRID_ID)
    body = (sensor.get("state") or "") + json.dumps(sensor.get("attributes") or {})
    repo = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..",
                        "custom_templates", "metered_total.jinja")
    live = os.path.join(os.path.dirname(cfg), "custom_templates", "metered_total.jinja")
    if [g.get("stat_energy_from") for g in grids] != ["sensor." + GRID_ID]:
        problem = ("the Energy dashboard's grid must be exactly sensor.%s, found %s"
                   % (GRID_ID, [g.get("stat_energy_from") for g in grids]))
    elif (sensor.get("state_class"), sensor.get("unit_of_measurement"),
          sensor.get("device_class")) != ("total_increasing", "kWh", "energy"):
        problem = "the sensor must be total_increasing, kWh, energy"
    elif body.count("metered_step(") != 2:
        problem = "state and the 'last' attribute must both be computed by metered_step"
    elif not os.path.exists(live) or io.open(repo, encoding="utf-8").read() != io.open(
            live, encoding="utf-8").read():
        problem = "custom_templates/metered_total.jinja differs from the deployed copy"
    return sorted(set(want) - set(ids)), sorted(set(ids) - set(want)), problem


WINDOW_HEADER = re.compile(r"^\{% set room = '[a-z0-9_]+' %\}\{% set voc_e = '[a-z0-9_.]+' %\}\{% set trv_w = '[a-z0-9_.]+' %\}")
NIGHT_HEADER = re.compile(r"^\{% set room = '([a-z0-9_]+)' %\}\{% set f = ([0-9.]+) %\}")

# Formulas copied per room on purpose: run.py substitutes the reads in each sensor's own text and
# cannot reach into an imported macro, so the copies stay, every case runs against each of them, and
# this proves they are the same text after the per-room header (review #53 F2).
COPIED_FAMILIES = (
    ("Climate window ", WINDOW_HEADER, ("Climate window detector blind",)),
    ("Climate night target ", NIGHT_HEADER, ()),
)


def family_copies(prefix, header, exclude):
    """Returns (titles, problem); problem is None when every copy matches after its header."""
    tpls = {t: v for t, v in harness.load_sensor_templates().items()
            if t.startswith(prefix) and t not in exclude and "::" not in t}
    if len(tpls) < 2:
        return sorted(tpls), "expected at least two '%s' sensors, found %d" % (prefix, len(tpls))
    bodies = {}
    for title, tpl in tpls.items():
        m = header.match(tpl)
        if not m:
            return sorted(tpls), "%s does not start with its per-room header" % title
        bodies.setdefault(tpl[m.end():], []).append(title)
    if len(bodies) > 1:
        return sorted(tpls), "the copies differ after the header: %s" % " | ".join(
            ", ".join(sorted(v)) for v in bodies.values())
    return sorted(tpls), None


def window_copies():
    return family_copies(*COPIED_FAMILIES[0])


def mould_factors():
    """Each frost night target's wall factor f must equal its room's Mould Indicator factor.

    Both model the same wall: the indicator shows its surface humidity, the night target keeps it
    below 80 %. Returns a list of problems (empty when they agree).
    """
    import io
    import json
    with io.open(harness.ENTRIES, encoding="utf-8") as fh:
        entries = json.load(fh)["data"]["entries"]
    mould = {}
    for e in entries:
        if e.get("domain") == "mold_indicator":
            o = e.get("options") or {}
            mould[o.get("indoor_temp_sensor")] = float(o.get("calibration_factor", 0))
    out = []
    for title, tpl in sorted(harness.load_sensor_templates().items()):
        if not title.startswith("Climate night target ") or "::" in title:
            continue
        m = NIGHT_HEADER.match(tpl)
        if not m:
            out.append("%s has no room/factor header" % title)
            continue
        room, f = m.group(1), float(m.group(2))
        got = mould.get("sensor.climate_temp_" + room)
        if got is None:
            out.append("%s: no Mould Indicator reads sensor.climate_temp_%s" % (title, room))
        elif abs(got - f) > 1e-9:
            out.append("%s: factor %s, its Mould Indicator %s" % (title, f, got))
    return out


LEAK_ID = "1792300000020"
RADIATORS_ID = "1790300000001"
PREHEAT = "input_boolean.climate_arrival_preheat"


def _secs(v):
    if isinstance(v, dict):
        return v.get("hours", 0) * 3600 + v.get("minutes", 0) * 60 + v.get("seconds", 0)
    h, m, sec = (int(x) for x in str(v).split(":"))
    return h * 3600 + m * 60 + sec


def leak_meter_window():
    """The leak meter must measure only while the radiators are set back and cold.

    2026-11-25, its first live run: the radiators drop to the Away floor 30 min into Away, the
    snapshot was taken at 1 h (radiators still warm), and arrival pre-heat turned the heating back
    on 37 min before Away ended. The three rooms it measured were stored 3-10x too airtight.
    Two rules, read from the LIVE automations: the snapshot waits a full hour after the radiators'
    own Away delay, and pre-heat switching on ends the run. Returns a list of problems.
    """
    import io
    import yaml
    with io.open(harness.AUTOMATIONS, encoding="utf-8") as fh:
        autos = {str(a.get("id")): a for a in yaml.safe_load(fh)}
    leak, rads = autos.get(LEAK_ID), autos.get(RADIATORS_ID)
    if leak is None or rads is None:
        return ["leak meter %s or radiators %s not found" % (LEAK_ID, RADIATORS_ID)]
    trig = leak.get("triggers") or leak.get("trigger") or []
    out = []
    setback = [_secs(t["for"]) for t in rads.get("triggers") or rads.get("trigger") or []
               if t.get("entity_id") == "alarm_control_panel.home" and t.get("to") == "armed_away" and t.get("for")]
    start = [t for t in trig if t.get("id") == "start"]
    if len(setback) != 1:
        out.append("the radiator automation has %d Away-delay triggers, expected 1" % len(setback))
    elif len(start) != 1 or not start[0].get("for"):
        out.append("the leak meter needs exactly one delayed 'start' trigger")
    elif _secs(start[0]["for"]) < setback[0] + 3600:
        out.append("the snapshot is taken %d min into Away, the radiators set back at %d min: "
                   "it must wait an hour after that" % (_secs(start[0]["for"]) // 60, setback[0] // 60))
    if not any(t.get("id") == "end" and t.get("entity_id") == PREHEAT and t.get("to") == "on" for t in trig):
        out.append("arrival pre-heat switching on does not end the leak meter's run")
    return out


HOT_WATER_ID = "1792300000080"
HOT_UNTIL = "input_datetime.house_hot_water_hot_until"
HOT_HOLD = "input_boolean.house_hot_water_hot_hold"


def _walk(node):
    """Every action dict in an automation's action tree, in order."""
    if isinstance(node, list):
        for x in node:
            yield from _walk(x)
    elif isinstance(node, dict):
        yield node
        for v in node.values():
            if isinstance(v, (list, dict)):
                yield from _walk(v)


def hot_water_shock_hold():
    """After a long pause the tank must be held hot long enough to disinfect.

    Review 2026-11-26 (field guide, legionella): complete loss of culturability takes about 60 min
    at 60 C (Cervero-Arago et al. 2019) and the hold starts from a tank that sat cold for two days,
    so the hour at 65 C was mostly reheating. The weekend cycle already uses a two-hour window; the
    shock after a pause must too. Read from the LIVE automation. Returns a list of problems.
    """
    import io
    import yaml
    with io.open(harness.AUTOMATIONS, encoding="utf-8") as fh:
        autos = {str(a.get("id")): a for a in yaml.safe_load(fh)}
    hw = autos.get(HOT_WATER_ID)
    if hw is None:
        return ["hot water automation %s not found" % HOT_WATER_ID]
    steps = list(_walk(hw.get("actions") or hw.get("action") or []))
    hot = [i for i, a in enumerate(steps) if a.get("action") == "water_heater.set_temperature"
           and float((a.get("data") or {}).get("temperature", 0)) >= 60]
    if len(hot) != 1:
        return ["expected one hot (>= 60 C) set_temperature step, found %d" % len(hot)]
    if any("delay" in a or "wait_template" in a or "wait_for_trigger" in a for a in steps[hot[0] + 1:]):
        return ["the hot hold waits inside the run: a restart during it leaves the tank at 65 C "
                "(2026-11-26); stamp its end in %s instead" % HOT_UNTIL]
    # The release must run at the stamp, at start and on a 15-minute fallback (review round 3, F4):
    # any one missing and a restart or a missed stamp leaves the tank at 65 C again.
    trig = hw.get("triggers") or hw.get("trigger") or []
    if not any(t.get("trigger") == "homeassistant" and t.get("event") == "start" for t in trig):
        return ["no start trigger: a hold that ended while HA was down is not released at start"]
    if not any(t.get("trigger") == "time_pattern" and str(t.get("minutes")) in ("/15", "/5", "/10") for t in trig):
        return ["no 15-minute fallback trigger for the hot-water release"]
    if not any(t.get("trigger") == "time" and HOT_UNTIL in str(t.get("at")) for t in trig):
        return ["no trigger at %s: the hold is released only by the fallback" % HOT_UNTIL]
    flag = [i for i, a in enumerate(steps) if a.get("action") == "input_boolean.turn_on" and HOT_HOLD in str(a.get("target"))]
    if not flag or flag[0] > hot[0]:
        return ["%s must be turned on before the 65 C command, or a failed call leaves no hold to release" % HOT_HOLD]
    stamps = [a for a in steps if a.get("action") == "input_datetime.set_datetime"
              and HOT_UNTIL in str(a.get("target"))]
    if len(stamps) != 1:
        return ["the hot step must stamp the end of its hold in %s" % HOT_UNTIL]
    import re
    m = re.search(r"now\(\)\.timestamp\(\)\s*\+\s*(\d+)", str((stamps[0].get("data") or {}).get("timestamp", "")))
    if not m or int(m.group(1)) < 7200:
        return ["the tank is held hot for %s s after a long pause; disinfection needs 2 h "
                "(reheat plus an hour at >= 60 C)" % (m.group(1) if m else "an unreadable number of")]
    return []


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

    missing, extra, problem = grid_meters()
    for m in missing:
        print("  GRID MISSES    %s is on the Energy dashboard but not in the metered grid" % m)
    for m in extra:
        print("  GRID EXTRA     %s is in the metered grid but not on the Energy dashboard" % m)
    if problem:
        print("  GRID WIRING    %s" % problem)
    if missing or extra or problem:
        print("\nsensor.%s must sum exactly the Energy dashboard's meters and be its grid."
              % GRID_ID)
        return 1
    print("  the metered grid sums exactly the Energy dashboard's meters and is its grid")

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

    for prefix, header, exclude in COPIED_FAMILIES:
        titles, problem = family_copies(prefix, header, exclude)
        if problem:
            print("  COPIES          %s" % problem)
            return 1
        print("  the %d '%s' sensors are one formula" % (len(titles), prefix.strip()))
    factor_problems = mould_factors()
    for p in factor_problems:
        print("  MOULD FACTOR    %s" % p)
    if factor_problems:
        return 1
    print("  every frost night target uses its room's Mould Indicator factor")

    leak_problems = leak_meter_window()
    for p in leak_problems:
        print("  LEAK WINDOW     %s" % p)
    if leak_problems:
        return 1
    print("  the leak meter measures only an unheated flat")

    hw_problems = hot_water_shock_hold()
    for p in hw_problems:
        print("  HOT WATER       %s" % p)
    if hw_problems:
        return 1
    print("  the hot-water shock after a long pause lasts long enough to disinfect")

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
