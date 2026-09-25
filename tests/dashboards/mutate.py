#!/usr/bin/env python3
"""Reintroduce each bug the lint exists for, and confirm the lint turns red.

`tests/climate/mutate.py` does this for the climate oracle, for the reason
AGENTS.md states plainly: a case that cannot fail is worse than no case. The
dashboard lint earned its own copy the hard way - its first version compared
both dashboards' cards against ONE dashboard's template library, so it passed
while three views were failing to render.

Each mutation below is a bug that actually shipped, or the mirror of one. The
harness copies the live `.storage` files to a temp directory, applies one
mutation, and runs `lint.py` unmodified against it via HA_STORAGE - so what is
proven is the real script, not a re-implementation of its logic.

    python3 tests/dashboards/mutate.py
"""

import io
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.join(HERE, "lint.py")
LIVE = os.environ.get("HA_STORAGE", "/usr/share/hassio/homeassistant/.storage")
FILES = ("lovelace.lovelace", "lovelace.admin_panel", "core.entity_registry",
         "core.device_registry", "core.area_registry", "lovelace_resources")

LOV, ADM = "lovelace.lovelace", "lovelace.admin_panel"


def _cfg(d, f):
    with io.open(os.path.join(d, f), encoding="utf-8") as fh:
        return json.load(fh)


def _save(d, f, doc):
    with io.open(os.path.join(d, f), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)


def _first_button(cfg):
    """Path to the first grid-positioned button-card, as (view, section, index)."""
    for vi, v in enumerate(cfg["data"]["config"].get("views", [])):
        for si, sec in enumerate(v.get("sections", []) or []):
            for ci, c in enumerate(sec.get("cards", []) or []):
                if isinstance(c, dict) and c.get("type") == "custom:button-card":
                    return vi, si, ci
    raise SystemExit("no button-card found to mutate")


# -- mutations -------------------------------------------------------------
# Each returns the check id it must provoke.

def m_templates_elsewhere(d):
    """The real 2026-09-23 bug: templates defined on the OTHER dashboard."""
    doc = _cfg(d, ADM)
    doc["data"]["config"].pop("button_card_templates", None)
    _save(d, ADM, doc)
    return "C1"


def m_foreign_option(d):
    doc = _cfg(d, LOV)
    vi, si, ci = _first_button(doc)
    doc["data"]["config"]["views"][vi]["sections"][si]["cards"][ci]["state_content"] = ["state"]
    _save(d, LOV, doc)
    return "C2"


def m_aspect_ratio(d):
    """Height follows width again - the 'giant radiation card'."""
    doc = _cfg(d, LOV)
    doc["data"]["config"]["button_card_templates"]["vg_stat"]["aspect_ratio"] = "1/1"
    _save(d, LOV, doc)
    return "C3"


def m_drop_rows(d):
    doc = _cfg(d, LOV)
    vi, si, ci = _first_button(doc)
    doc["data"]["config"]["views"][vi]["sections"][si]["cards"][ci].pop("grid_options", None)
    _save(d, LOV, doc)
    return "C3"


def m_dead_entity(d):
    doc = _cfg(d, LOV)
    vi, si, ci = _first_button(doc)
    doc["data"]["config"]["views"][vi]["sections"][si]["cards"][ci]["entity"] = "sensor.does_not_exist_at_all"
    _save(d, LOV, doc)
    return "C4"


def m_dead_entity_in_js(d):
    """The one a structural walk would miss: an id only inside a JS template."""
    doc = _cfg(d, LOV)
    vi, si, ci = _first_button(doc)
    doc["data"]["config"]["views"][vi]["sections"][si]["cards"][ci]["label"] = \
        "[[[ return states['sensor.ghost_entity_xyz'].state; ]]]"
    _save(d, LOV, doc)
    return "C4"


def m_unregistered_card(d):
    doc = _cfg(d, "lovelace_resources")
    doc["data"]["items"] = [r for r in doc["data"]["items"] if "button-card" not in r["url"]]
    _save(d, "lovelace_resources", doc)
    return "C5"


def m_scratch_key(d):
    doc = _cfg(d, LOV)
    doc["data"]["config"]["views"][0]["_leftover"] = 1
    _save(d, LOV, doc)
    return "C6"


def m_tall_cards(d):
    """rows:2 under two lines of content - the dead space the operator saw."""
    doc = _cfg(d, LOV)
    vi, si, ci = _first_button(doc)
    doc["data"]["config"]["views"][vi]["sections"][si]["cards"][ci]["grid_options"]["rows"] = 2
    _save(d, LOV, doc)
    return "C7"


def m_off_ladder_columns(d):
    """columns:4 gives 6-up on a laptop and ragged rows beside columns:6."""
    doc = _cfg(d, LOV)
    vi, si, ci = _first_button(doc)
    doc["data"]["config"]["views"][vi]["sections"][si]["cards"][ci]["grid_options"]["columns"] = 4
    _save(d, LOV, doc)
    return "C7"


def m_dead_column(d):
    """max_columns not a multiple of column_span - a column empty on every row."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        secs = v.get("sections") or []
        if secs and {s.get("column_span", 1) for s in secs} == {2}:
            v["max_columns"] = 3
            break
    _save(d, LOV, doc)
    return "C7"


def m_clobbered_label(d):
    """A label written for a different card: every variables.x undefined, so the
    card renders its fallback instead of a value. Six Home tiles and one Energy
    tile shipped like this."""
    doc = _cfg(d, LOV)
    vi, si, ci = _first_button(doc)
    card = doc["data"]["config"]["views"][vi]["sections"][si]["cards"][ci]
    card.pop("variables", None)
    card["label"] = "[[[ return variables.grp ? states[variables.grp].state : '-'; ]]]"
    _save(d, LOV, doc)
    return "C8"


def _room_gen(cfg, floor="upper_floor"):
    """The auto-entities that generates one floor's Home tiles."""
    for v in cfg["data"]["config"]["views"]:
        for sec in (v.get("sections") or []):
            cs = sec.get("cards") or []
            if cs and cs[0].get("heading") == "Rooms":
                for c in cs:
                    if c.get("type") == "custom:auto-entities" and c.get("floor") == floor:
                        return c, cs
    raise SystemExit("no %s room generator found to mutate" % floor)


def _room_view(cfg, path="hallway"):
    for v in cfg["data"]["config"]["views"]:
        if v.get("path") == path:
            return v
    raise SystemExit("no %s view found to mutate" % path)


def m_tile_pins_entity(d):
    """The bug that started this: a tile naming its room's light group instead
    of its room. Correct on the day it was written, a dash ever after. In the
    generated form it can only come back through the room map."""
    doc = _cfg(d, LOV)
    gen, _ = _room_gen(doc)
    gen["rooms"]["hallway"]["grp"] = "light.magic_areas_light_groups_hallway_all_lights"
    _save(d, LOV, doc)
    return "C10"


def m_tile_loses_area(d):
    doc = _cfg(d, LOV)
    gen, _ = _room_gen(doc)
    gen["rooms"]["no_such_room"] = {"name": "Nowhere", "page": "closet"}
    _save(d, LOV, doc)
    return "C10"


def m_floor_generator_dropped(d):
    """A floor whose generator is gone: its rooms vanish from Home, silently."""
    doc = _cfg(d, LOV)
    gen, cs = _room_gen(doc)
    cs.remove(gen)
    _save(d, LOV, doc)
    return "C9"


def m_generators_diverge(d):
    """One floor's template edited and the other forgotten."""
    doc = _cfg(d, LOV)
    gen, _ = _room_gen(doc)
    gen["filter"]["template"] = gen["filter"]["template"].replace("area_name(a)", "a")
    _save(d, LOV, doc)
    return "C10"


def _section(cfg, vpath, heading):
    for v in cfg["data"]["config"]["views"]:
        if v.get("path") == vpath:
            for sec in (v.get("sections") or []):
                cs = sec.get("cards") or []
                if cs and cs[0].get("heading") == heading:
                    return cs
    raise SystemExit("no %s/%s section found to mutate" % (vpath, heading))


def m_socket_hand_listed(d):
    """The pre-2026-09-25 shape: a plug gets its own card, one edit per device."""
    doc = _cfg(d, LOV)
    _section(doc, "energy", "Sockets").append(
        {"type": "custom:button-card", "entity": "sensor.mini_rack_power",
         "template": "vg_meter", "grid_options": {"columns": 6, "rows": 1}})
    _save(d, LOV, doc)
    return "C13"


def m_devices_view_gone(d):
    doc = _cfg(d, ADM)
    views = doc["data"]["config"]["views"]
    doc["data"]["config"]["views"] = [v for v in views if v.get("path") != "devices"]
    _save(d, ADM, doc)
    return "C13"


def m_rooms_section_renamed(d):
    """C9 and C10 both hang off finding the Rooms section. If that lookup comes
    back empty they would pass by saying nothing, which is the failure mode this
    whole suite exists for - so the empty case is itself a failure."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        for sec in (v.get("sections") or []):
            cs = sec.get("cards") or []
            if cs and cs[0].get("heading") == "Rooms":
                cs[0]["heading"] = "The rooms"
    _save(d, LOV, doc)
    return "C10"


def m_room_loses_lights(d):
    """A room page built by hand again: the generative rule for its lights is
    gone, so a bulb added to that area would appear nowhere."""
    doc = _cfg(d, LOV)
    view = _room_view(doc)
    for sec in view["sections"]:
        sec["cards"] = [c for c in sec["cards"]
                        if not (c.get("type") == "custom:auto-entities"
                                and any(r.get("domain") == "light"
                                        for r in c["filter"]["include"]))]
    _save(d, LOV, doc)
    return "C9"


def m_rule_names_wrong_area(d):
    """Copy-paste between two room pages - the rule is present and well-formed,
    it just populates from the wrong room. Nothing renders an error."""
    doc = _cfg(d, LOV)
    view = _room_view(doc)
    for sec in view["sections"]:
        for c in sec["cards"]:
            if c.get("type") != "custom:auto-entities":
                continue
            for r in c["filter"]["include"]:
                if r.get("area") == "hallway":
                    r["area"] = "closet"
    _save(d, LOV, doc)
    return "C9"


def m_rollback_restyled(d):
    """What the room-tile transform did before it was scoped by path: the
    classic view's Rooms section rewritten because it shares the heading."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        if v.get("path") != "home-classic":
            continue
        v["sections"][0]["cards"].append(
            {"type": "custom:button-card", "template": "vg_stat",
             "entity": "sun.sun", "grid_options": {"columns": 6, "rows": 1}})
    _save(d, LOV, doc)
    return "C11"


def m_socket_back_on_room(d):
    """The outlet exclusion dropped from a room's Controls block - every metered
    plug returns as a toggle, including the one feeding the network gear."""
    doc = _cfg(d, LOV)
    view = _room_view(doc, "living-room")
    for sec in view["sections"]:
        for c in sec["cards"]:
            if c.get("type") != "custom:auto-entities":
                continue
            inc = (c.get("filter") or {}).get("include") or []
            if any(r.get("domain") == "switch" for r in inc):
                c["filter"]["exclude"] = [
                    e for e in c["filter"]["exclude"]
                    if (e.get("attributes") or {}).get("device_class") != "outlet"]
    _save(d, LOV, doc)
    return "C12"


def m_room_page_hand_edited(d):
    """One room page gets a card the others do not: it has left the skeleton."""
    doc = _cfg(d, LOV)
    _room_view(doc, "kitchen")["sections"][0]["cards"].append(
        {"type": "tile", "entity": "light.gallery"})
    _save(d, LOV, doc)
    return "C14"


def m_room_page_unfocused(d):
    """The pre-2026-09-25 kitchen: every sensor in the area, labelled or not."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        if v.get("subview") and v.get("back_path") == "/lovelace/home" and v.get("path") != "home-classic":
            for c in v["sections"][0]["cards"]:
                if c.get("type") == "custom:auto-entities":
                    for r in (c.get("filter") or {}).get("include") or []:
                        if r.get("label") == "on_room_page":
                            r.pop("label")
    _save(d, LOV, doc)
    return "C15"


def m_list_matcher(d):
    """A rule whose domain is a list: auto-entities matches nothing, silently."""
    doc = _cfg(d, LOV)
    for c in _room_view(doc, "kitchen")["sections"][0]["cards"]:
        for r in (c.get("filter") or {}).get("include") or []:
            if r.get("domain") == "light":
                r["domain"] = ["light"]
                _save(d, LOV, doc)
                return "C16"
    raise SystemExit("no light rule to mutate")


MUTATIONS = [
    ("a socket returns to a room page", m_socket_back_on_room),
    ("a room page is edited by hand", m_room_page_hand_edited),
    ("an auto-entities matcher becomes a list", m_list_matcher),
    ("a room page lists every sensor again", m_room_page_unfocused),
    ("the rollback view gets restyled", m_rollback_restyled),
    ("a room map pins its light group", m_tile_pins_entity),
    ("a room map names an area that does not exist", m_tile_loses_area),
    ("a floor loses its tile generator", m_floor_generator_dropped),
    ("the floor generators diverge", m_generators_diverge),
    ("a socket gets a hand-listed card again", m_socket_hand_listed),
    ("the admin Devices view is deleted", m_devices_view_gone),
    ("the Rooms section is renamed away", m_rooms_section_renamed),
    ("a room page loses its lights rule", m_room_loses_lights),
    ("a room rule names the wrong area", m_rule_names_wrong_area),
    ("a label using variables nothing defines", m_clobbered_label),
    ("a card taller than its content", m_tall_cards),
    ("a card off the column ladder", m_off_ladder_columns),
    ("max_columns leaves a dead column", m_dead_column),
    ("templates defined on the other dashboard", m_templates_elsewhere),
    ("tile option copied onto a button-card", m_foreign_option),
    ("aspect_ratio back on the stat template", m_aspect_ratio),
    ("a card loses grid_options.rows", m_drop_rows),
    ("a card names a dead entity", m_dead_entity),
    ("a dead entity only inside a JS template", m_dead_entity_in_js),
    ("button-card's resource unregistered", m_unregistered_card),
    ("a transform leaves a scratch key", m_scratch_key),
]


def run_lint(storage):
    env = dict(os.environ, HA_STORAGE=storage)
    p = subprocess.run([sys.executable, LINT], env=env, capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def main():
    code, out = run_lint(LIVE)
    if code != 0:
        print("REFUSING TO RUN: the lint is already failing on the live config.\n"
              "Mutation testing only means something from a green baseline.\n")
        print(out)
        return 2
    print("baseline green\n")

    bad = 0
    for name, fn in MUTATIONS:
        d = tempfile.mkdtemp(prefix="dashlint-")
        try:
            for f in FILES:
                shutil.copy(os.path.join(LIVE, f), os.path.join(d, f))
            want = fn(d)
            code, out = run_lint(d)
            if code == 0:
                print("  SURVIVED  %-44s (expected %s)" % (name, want))
                bad += 1
            elif want not in out:
                print("  WRONG     %-44s failed, but not on %s" % (name, want))
                bad += 1
            else:
                print("  caught    %-44s -> %s" % (name, want))
        finally:
            shutil.rmtree(d, ignore_errors=True)

    print("")
    if bad:
        print("%d mutation(s) not caught - the lint has a blind spot" % bad)
        return 1
    print("all %d mutations caught" % len(MUTATIONS))
    return 0


if __name__ == "__main__":
    sys.exit(main())
