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
         "core.device_registry", "core.area_registry", "lovelace_resources",
         "core.config_entries")

LOV, ADM = "lovelace.lovelace", "lovelace.admin_panel"


def _cfg(d, f):
    with io.open(os.path.join(d, f), encoding="utf-8") as fh:
        return json.load(fh)


def _save(d, f, doc):
    with io.open(os.path.join(d, f), "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False)


def _first_button(cfg, template=None):
    """Path to the first grid-positioned button-card, as (view, section, index)."""
    for vi, v in enumerate(cfg["data"]["config"].get("views", [])):
        for si, sec in enumerate(v.get("sections", []) or []):
            for ci, c in enumerate(sec.get("cards", []) or []):
                if (isinstance(c, dict) and c.get("type") == "custom:button-card"
                        and template in (None, c.get("template"))):
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
    """rows:2 under two lines of content - the dead space the operator saw.

    Picks a vg_stat by name: since 2026-10-25 Home opens with Quick actions,
    whose vg_action buttons are not two-line cards, and rows:2 on one is fine."""
    doc = _cfg(d, LOV)
    vi, si, ci = _first_button(doc, "vg_stat")
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


def m_room_loses_page(d):
    """A room on the Home tiles with no page in the room map - its tile falls
    back to Home Assistant's own area page, which is how Tea Room first shipped."""
    doc = _cfg(d, LOV)
    stack = [doc["data"]["config"]]
    while stack:
        o = stack.pop()
        if isinstance(o, dict):
            if isinstance(o.get("rooms"), dict):
                o["rooms"].pop("closet", None)
            stack.extend(o.values())
        elif isinstance(o, list):
            stack.extend(o)
    _save(d, LOV, doc)
    return "C9"


def m_ma_device_unplaced(d):
    """A new room's Magic Areas device left where the config flow puts it: in no
    area. Its page's Occupancy block then generates nothing."""
    doc = _cfg(d, "core.device_registry")
    for dv in doc["data"]["devices"]:
        if ["magic_areas", "magic_area_device_closet"] in (dv.get("identifiers") or []):
            dv["area_id"] = None
    _save(d, "core.device_registry", doc)
    return "C27"


def m_room_without_ma(d):
    """A room on the Home tiles that nobody created a Magic Area for."""
    doc = _cfg(d, "core.config_entries")
    doc["data"]["entries"] = [e for e in doc["data"]["entries"]
                              if not (e.get("domain") == "magic_areas"
                                      and e["data"].get("id") == "closet")]
    _save(d, "core.config_entries", doc)
    return "C27"


def m_silent_unsaid(d):
    """Needs attention forgets the silent-sensor branch: a dead smoke alarm says nothing."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        for sec in v.get("sections") or []:
            if (sec.get("cards") or [{}])[0].get("heading") != "Needs attention":
                continue
            for c in sec.get("visibility") or []:
                if c.get("condition") == "or":
                    c["conditions"] = [b for b in c["conditions"]
                                       if b.get("entity") != "sensor.any_safety_sensor_silent"]
    _save(d, LOV, doc)
    return "C28"


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
    _room_view(doc, "kitchen")["sections"][-1]["cards"].append(
        {"type": "tile", "entity": "light.gallery"})
    _save(d, LOV, doc)
    return "C14"


def m_room_page_unfocused(d):
    """The pre-2026-09-25 kitchen: every sensor in the area, labelled or not."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        if v.get("subview") and v.get("back_path") == "/lovelace/home" and v.get("path") != "home-classic":
            for c in _flat(v):
                if c.get("type") == "custom:auto-entities":
                    for r in (c.get("filter") or {}).get("include") or []:
                        if r.get("label") == "on_room_page":
                            r.pop("label")
    _save(d, LOV, doc)
    return "C15"


def m_list_matcher(d):
    """A rule whose domain is a list: auto-entities matches nothing, silently."""
    doc = _cfg(d, LOV)
    for c in _flat(_room_view(doc, "kitchen")):
        for r in (c.get("filter") or {}).get("include") or []:
            if r.get("domain") == "light":
                r["domain"] = ["light"]
                _save(d, LOV, doc)
                return "C16"
    raise SystemExit("no light rule to mutate")


def _rooms(cfg):
    return [v for v in cfg["data"]["config"]["views"]
            if v.get("subview") and v.get("back_path") == "/lovelace/home" and v.get("path") != "home-classic"]


def _flat(view):
    """Every card of a view, whichever section holds it."""
    return [c for sec in view["sections"] for c in sec["cards"]]


def _env(view):
    return [c for c in _flat(view) if (c.get("card") or {}).get("title") == "Environment"]


def m_camera_hand_listed(d):
    """2026-10-07: cameras are generated; a hand-listed one is an edit per camera."""
    doc = _cfg(d, LOV)
    _section(doc, "security", "Cameras").append(
        {"type": "picture-entity", "entity": "camera.bebecam_fluent", "camera_view": "auto"})
    _save(d, LOV, doc)
    return "C13"


def m_room_card_any_group(d):
    """The room card takes whichever Magic Areas light it meets last."""
    doc = _cfg(d, LOV)
    v = doc["data"]["config"]["button_card_templates"]["vg_room_card"]["variables"]
    v["info"] = v["info"].replace("if (!r.grp || id.slice(-11) === '_all_lights') r.grp = id;", "r.grp = id;")
    _save(d, LOV, doc)
    return "C17"


def m_env_block_dropped(d):
    """Every room page loses its Environment block - the pre-2026-10-07 page."""
    doc = _cfg(d, LOV)
    for v in _rooms(doc):
        envs = _env(v)
        for sec in v["sections"]:
            sec["cards"] = [x for x in sec["cards"] if x not in envs]
    _save(d, LOV, doc)
    return "C18"


def m_env_needs_label(d):
    """Readings only with the opt-in label again: PM2.5 and light level vanish."""
    doc = _cfg(d, LOV)
    for v in _rooms(doc):
        for c in _env(v):
            for r in c["filter"]["include"]:
                r["label"] = "on_room_page"
    _save(d, LOV, doc)
    return "C18"


def m_env_rule_broadened(d):
    """The environment rule grows a non-environmental class (power)."""
    doc = _cfg(d, LOV)
    for v in _rooms(doc):
        for c in _env(v):
            for r in c["filter"]["include"]:
                dc = (r.get("attributes") or {}).get("device_class", "")
                if dc.startswith("/^("):
                    r["attributes"]["device_class"] = dc.replace("/^(", "/^(power|", 1)
    _save(d, LOV, doc)
    return "C15"


def m_all_lights_doubled(d):
    """Magic Areas' per-category groups reach the 'All lights' rule again."""
    doc = _cfg(d, LOV)
    for v in _rooms(doc):
        for c in _flat(v):
            exc = (c.get("filter") or {}).get("exclude") or []
            exc[:] = [x for x in exc if not (x.get("integration") == "magic_areas" and x.get("entity_id"))]
    _save(d, LOV, doc)
    return "C19"


def m_second_sensor_in_aggregated_room(d):
    """A second thermometer lands in the shower: its aggregate becomes a mean of two."""
    path = os.path.join(d, "core.entity_registry")
    with io.open(path, encoding="utf-8") as fh:
        reg = json.load(fh)
    reg["data"]["entities"].append({
        "entity_id": "sensor.mutant_shower_probe_temperature", "platform": "mqtt",
        "area_id": "shower", "device_id": None, "original_device_class": "temperature",
        "device_class": None, "labels": [], "unique_id": "mutant", "disabled_by": None,
        "hidden_by": None, "entity_category": None})
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh)
    return "C20"


def m_diagnostic_sensor_counted(d):
    """A chip thermometer lands in the shower, and the shower's Magic Area does NOT
    ignore diagnostics: it is averaged in. C20 skips diagnostic sensors only where
    Magic Areas does (2026-10-28, an Aqara leak sensor's device temperature)."""
    path = os.path.join(d, "core.entity_registry")
    with io.open(path, encoding="utf-8") as fh:
        reg = json.load(fh)
    reg["data"]["entities"].append({
        "entity_id": "sensor.mutant_shower_leak_device_temperature", "platform": "mqtt",
        "area_id": "shower", "device_id": None, "original_device_class": "temperature",
        "device_class": None, "labels": [], "unique_id": "mutant-chip", "disabled_by": None,
        "hidden_by": None, "entity_category": "diagnostic"})
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh)
    ce = _cfg(d, "core.config_entries")
    for e in ce["data"]["entries"]:
        if e.get("domain") == "magic_areas" and e["data"].get("id") == "shower":
            e["options"]["ignore_diagnostic_entities"] = False
    _save(d, "core.config_entries", ce)
    return "C20"


def _relabel(d, pick, change):
    """Apply `change` to every registry entity `pick` accepts; there must be one."""
    path = os.path.join(d, "core.entity_registry")
    with io.open(path, encoding="utf-8") as fh:
        reg = json.load(fh)
    hit = [e for e in reg["data"]["entities"] if pick(e)]
    assert hit, "mutation found nothing to change"
    for e in hit:
        change(e)
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(reg, fh)


def m_primary_probe_shown(d):
    """2026-10-22: a room meter back on its page beside the resolved reading it feeds."""
    _relabel(d, lambda e: e["entity_id"].startswith("sensor.indoor_outdoor_meter_")
             and "not_on_room_pages" in (e.get("labels") or []),
             lambda e: e["labels"].remove("not_on_room_pages"))
    return "C33"


def m_unique_probe_hidden(d):
    """2026-10-22: an air-quality meter's temperature hidden as if it were a duplicate."""
    _relabel(d, lambda e: e["entity_id"].endswith("_air_quality_temperature")
             and "not_on_room_pages" not in (e.get("labels") or []),
             lambda e: e.setdefault("labels", []).append("not_on_room_pages"))
    return "C33"


def m_presence_probe_hidden(d):
    """Review 2026-10-22 F1: a presence sensor with a switch is not an appliance; its humidity is the room's."""
    _relabel(d, lambda e: e["entity_id"] == "sensor.hallway_presence_humidity",
             lambda e: e.setdefault("labels", []).append("not_on_room_pages"))
    return "C33"


def m_chip_temperature_shown(d):
    """A motion sensor's chip temperature loses its diagnostic category."""
    _relabel(d, lambda e: e["entity_id"].endswith("_device_temperature"),
             lambda e: e.update(entity_category=None))
    return "C33"


def _needs_attention(cfg):
    home = [v for v in cfg["data"]["config"]["views"] if v.get("path") == "home"][0]
    return [x for x in home["sections"] if (x.get("cards") or [{}])[0].get("heading") == "Needs attention"][0]


def m_safety_hand_listed(d):
    """The pre-2026-10-09 shape: one leak sensor named in Needs attention."""
    doc = _cfg(d, LOV)
    _needs_attention(doc)["cards"].append(
        {"type": "custom:button-card", "template": "vg_stat",
         "entity": "binary_sensor.co_smoke_alarm_smoke", "grid_options": {"columns": 12, "rows": 1}})
    _save(d, LOV, doc)
    return "C21"


def m_safety_gate_dropped(d):
    """Needs attention no longer appears for a smoke or CO alarm."""
    doc = _cfg(d, LOV)
    for cond in _needs_attention(doc)["visibility"][0]["conditions"][:]:
        if cond.get("entity") == "binary_sensor.any_safety_alarm":
            _needs_attention(doc)["visibility"][0]["conditions"].remove(cond)
    _save(d, LOV, doc)
    return "C21"


def m_heating_hand_listed(d):
    """A heating zone gets its own hand-made card."""
    doc = _cfg(d, LOV)
    _section(doc, "climate", "Heating & hot water").append(
        {"type": "tile", "entity": "water_heater.hot_water_hot_water"})
    _save(d, LOV, doc)
    return "C13"


def m_safety_gate_and(d):
    """Needs attention shows only when ALL its conditions hold - a lone fire stays hidden."""
    doc = _cfg(d, LOV)
    _needs_attention(doc)["visibility"][0]["condition"] = "and"
    _save(d, LOV, doc)
    return "C21"


def m_safety_gate_wrong_state(d):
    """The roll-up is named in the gate, but for the wrong state."""
    doc = _cfg(d, LOV)
    for cond in _needs_attention(doc)["visibility"][0]["conditions"]:
        if cond.get("entity") == "binary_sensor.any_safety_alarm":
            cond["state"] = "off"
    _save(d, LOV, doc)
    return "C21"


def m_room_temperature_hand_listed(d):
    """A room's temperature tile is hand-added again - the next new room is missing."""
    doc = _cfg(d, LOV)
    _section(doc, "climate", "Temperature").append(
        {"type": "custom:mini-graph-card", "entities": [{"entity": "sensor.climate_temp_office"}]})
    _save(d, LOV, doc)
    return "C13"


def m_night_from_schedule(d):
    """A status card computes night the pre-v5.12 way and says Night after a manual day."""
    doc = _cfg(d, LOV)
    _section(doc, "climate", "Automatic climate").append(
        {"type": "markdown", "content": "{{ 'Night' if is_state('schedule.climate_night','on') or is_state('alarm_control_panel.home','armed_night') else 'Day' }}"})
    _save(d, LOV, doc)
    return "C22"


def m_night_inline(d):
    """A card carries its own copy of today's definition of night (audit 2026-10-20)."""
    doc = _cfg(d, LOV)
    _section(doc, "climate", "Automatic climate").append(
        {"type": "markdown", "content": "{% set a = states('alarm_control_panel.home') %}{{ 'Night' if a == 'armed_night' or (a in ['unavailable', 'unknown'] and is_state('schedule.climate_night','on')) else 'Day' }}"})
    _save(d, LOV, doc)
    return "C22"


def m_night_schedule_by_states(d):
    """The pre-v5.12 bug in another spelling: night from the schedule via states() ==."""
    doc = _cfg(d, LOV)
    _section(doc, "climate", "Automatic climate").append(
        {"type": "markdown", "content": "{{ 'Night' if states('schedule.climate_night') == 'on' else 'Day' }}"})
    _save(d, LOV, doc)
    return "C22"


def m_battery_by_name(d):
    """A card lists batteries by entity id instead of device class."""
    doc = _cfg(d, LOV)
    _needs_attention(doc)["cards"].append(
        {"type": "markdown", "content": "{{ states.sensor | selectattr('entity_id','search','_battery$') | list | count }}"})
    _save(d, LOV, doc)
    return "C29"


def m_attention_gate_misses_card(d):
    """Issue #2: the damp/health card is gated alone but missing from the section's gate."""
    doc = _cfg(d, LOV)
    gate = _needs_attention(doc)["visibility"][0]["conditions"]
    gate[:] = [c for c in gate if c.get("entity") != "binary_sensor.climate_health_risk"]
    _save(d, LOV, doc)
    return "C30"


def m_person_badge_pinned(d):
    """Issue #4: a person badge is green whether or not they are home."""
    doc = _cfg(d, LOV)
    home = [v for v in doc["data"]["config"]["views"] if v.get("path") == "home"][0]
    next(b for b in home["badges"] if b.get("entity", "").startswith("person."))["color"] = "green"
    _save(d, LOV, doc)
    return "C31"


def m_room_link_stale(d):
    """Issue #3: a room page's path changes and the health list's link map is not told."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        if v.get("path") == "guest-room":
            v["path"] = "office"
    _save(d, LOV, doc)
    return "C32"


def m_battery_hand_computed(d):
    """The Home note computes its own battery list again - the 15 % volvo-substring copy."""
    doc = _cfg(d, LOV)
    _needs_attention(doc)["cards"].append(
        {"type": "markdown", "content": "{{ states.sensor | selectattr('attributes.device_class','eq','battery') | rejectattr('entity_id','search','volvo') | map(attribute='state') | map('float', 101) | select('lt', 15) | list | count }}"})
    _save(d, LOV, doc)
    return "C29"


def m_battery_gate_dropped(d):
    """Needs attention no longer opens for a low battery: the 2026-10-20 leak sensor at 15 %."""
    doc = _cfg(d, LOV)
    gate = _needs_attention(doc)["visibility"][0]["conditions"]
    gate[:] = [c for c in gate if c.get("entity") != "sensor.any_low_battery"]
    _save(d, LOV, doc)
    return "C29"


def m_battery_note_ungated(d):
    """The note renders whenever the section is open, saying 'none' under a smoke alarm."""
    doc = _cfg(d, LOV)
    for c in _needs_attention(doc)["cards"]:
        if "sensor.any_low_battery" in json.dumps(c):
            c.pop("visibility", None)
    _save(d, LOV, doc)
    return "C29"


def _occ_cards(v):
    return [c for sec in v["sections"] for c in sec["cards"]
            if c.get("type") == "custom:auto-entities"
            and any((r.get("options") or {}).get("name") == "Occupancy"
                    for r in c["filter"]["include"])]


def m_occupancy_tile_dropped(d):
    """Every room page goes back to the badge-only occupancy of 2026-10-11."""
    doc = _cfg(d, LOV)
    for v in _rooms(doc):
        for sec in v["sections"]:
            sec["cards"] = [c for c in sec["cards"] if c not in _occ_cards(v)]
    _save(d, LOV, doc)
    return "C23"


def m_occupancy_tile_not_tappable(d):
    """The tile is there but tapping it does nothing: 'click for details' is lost."""
    doc = _cfg(d, LOV)
    for v in _rooms(doc):
        for c in _occ_cards(v):
            for r in c["filter"]["include"]:
                (r.get("options") or {}).pop("tap_action", None)
    _save(d, LOV, doc)
    return "C23"


def m_room_page_one_column(d):
    """Every room page back to one section: a 400 px strip on a tablet or laptop."""
    doc = _cfg(d, LOV)
    for v in _rooms(doc):
        v["sections"] = [{"type": "grid", "column_span": 1, "cards": _flat(v)}]
    _save(d, LOV, doc)
    return "C24"


def m_home_tablet_gap(d):
    """The pre-2026-10-12 breakpoints: a tablet is treated as a big phone."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        if v.get("path") != "home":
            continue
        for c in _flat(v):
            for cond in c.get("visibility") or []:
                if cond.get("condition") == "screen":
                    cond["media_query"] = cond["media_query"].replace("599px", "1023px").replace("600px", "1024px")
    _save(d, LOV, doc)
    return "C25"


def m_energy_not_dense(d):
    """Energy stops packing densely: the short section's column is empty below it."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        if v.get("path") == "energy":
            v.pop("dense_section_placement", None)
    _save(d, LOV, doc)
    return "C26"


def m_home_four_columns(d):
    """Home back to max_columns 4 with a section that spans two."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        if v.get("path") == "home":
            v["max_columns"] = 4
    _save(d, LOV, doc)
    return "C26"


def _comfort_template(cfg):
    for c in _section(cfg, "home", "Comfort"):
        if c.get("type") == "custom:auto-entities":
            return c["filter"]
    raise SystemExit("no Comfort generator to mutate")


def m_comfort_hand_listed(d):
    """The living room's target gets its own card - every other room is forgotten."""
    doc = _cfg(d, LOV)
    _section(doc, "home", "Comfort").append(
        {"type": "tile", "entity": "input_number.climate_target_day_living_room"})
    _save(d, LOV, doc)
    return "C13"


def m_comfort_names_room(d):
    """The generator iterates a hand-kept room list instead of the automation's switches."""
    doc = _cfg(d, LOV)
    f = _comfort_template(doc)
    f["template"] = f["template"].replace("climate_room_", "climate_rooom_") + \
        "{# input_number.climate_target_day_living_room #}"
    _save(d, LOV, doc)
    return "C34"


def m_comfort_own_night(d):
    """The Comfort section decides night itself from the alarm."""
    doc = _cfg(d, LOV)
    f = _comfort_template(doc)
    f["template"] = f["template"].replace("binary_sensor.lighting_night", "alarm_control_panel.home")
    _save(d, LOV, doc)
    return "C34"


def m_comfort_day_only(d):
    """At night the section still offers the day target, which the automation ignores."""
    doc = _cfg(d, LOV)
    f = _comfort_template(doc)
    f["template"] = f["template"].replace("climate_target_night_", "climate_target_day_")
    _save(d, LOV, doc)
    return "C34"


def _curated(doc, key):
    """The first Energy card carrying a `sockets` / `outlets` curation map."""
    for v in doc["data"]["config"]["views"]:
        for sec in v.get("sections") or []:
            for c in sec.get("cards") or []:
                if isinstance(c, dict) and c.get(key):
                    return c
    raise SystemExit("no card carries a %r map to mutate" % key)


def m_socket_curation_stale(d):
    """A socket's curation outlives it: the key names a sensor with no device of its own."""
    doc = _cfg(d, LOV)
    _curated(doc, "sockets")["sockets"]["sensor.ac_power_total"] = {"name": "Gone"}
    _save(d, LOV, doc)
    return "C35"


def m_outlet_curation_is_main(d):
    """The unmetered list's curation names a metered socket's own main switch."""
    doc = _cfg(d, LOV)
    regs = _cfg(d, "core.entity_registry")["data"]["entities"]
    dev = {e["entity_id"]: e.get("device_id") for e in regs}
    sock = sorted(_curated(doc, "sockets")["sockets"])[0]
    main = min((e for e, did in dev.items() if did == dev[sock] and e.startswith("switch.")), key=len)
    _curated(doc, "outlets")["outlets"][main] = {"name": "Main"}
    _save(d, LOV, doc)
    return "C35"


def m_graph_charts_offline(d):
    """The socket graph charts a plug that is offline again: the card never leaves its spinner."""
    doc = _cfg(d, LOV)
    for v in doc["data"]["config"]["views"]:
        for sec in v.get("sections") or []:
            for c in sec.get("cards") or []:
                if (isinstance(c, dict) and c.get("type") == "custom:auto-entities"
                        and (c.get("card") or {}).get("type") == "custom:mini-graph-card"
                        and c.get("sockets")):
                    c["filter"]["template"] = c["filter"]["template"].replace(
                        " if is_number(states(s.power))", "")
                    _save(d, LOV, doc)
                    return "C36"
    raise SystemExit("no generated socket graph to mutate")


MUTATIONS = [
    ("the socket graph charts an offline plug", m_graph_charts_offline),
    ("a socket's curation outlives the socket", m_socket_curation_stale),
    ("outlet curation names a metered socket's switch", m_outlet_curation_is_main),
    ("Comfort hand-lists a room's target", m_comfort_hand_listed),
    ("Comfort walks its own room list", m_comfort_names_room),
    ("Comfort computes night itself", m_comfort_own_night),
    ("Comfort offers only the day target", m_comfort_day_only),
    ("a room temperature tile is hand-listed", m_room_temperature_hand_listed),
    ("a card computes night from the schedule", m_night_from_schedule),
    ("a card carries its own copy of night", m_night_inline),
    ("night from the schedule in another spelling", m_night_schedule_by_states),
    ("a card lists batteries by entity id", m_battery_by_name),
    ("Needs attention's gate misses a card", m_attention_gate_misses_card),
    ("a person badge pins its colour", m_person_badge_pinned),
    ("a room page is renamed under its link", m_room_link_stale),
    ("the battery note computes its own list", m_battery_hand_computed),
    ("Needs attention ignores a low battery", m_battery_gate_dropped),
    ("the battery note is shown without a battery", m_battery_note_ungated),
    ("Needs attention gate becomes AND", m_safety_gate_and),
    ("Needs attention gates on the roll-up being off", m_safety_gate_wrong_state),
    ("a safety sensor is hand-listed in Needs attention", m_safety_hand_listed),
    ("Needs attention ignores the safety roll-up", m_safety_gate_dropped),
    ("a heating zone gets a hand-made card", m_heating_hand_listed),
    ("a second sensor joins an aggregated room", m_second_sensor_in_aggregated_room),
    ("a chip thermometer joins a room that counts diagnostics", m_diagnostic_sensor_counted),
    ("a room meter shown beside the reading it feeds", m_primary_probe_shown),
    ("a probe measuring elsewhere in the room hidden", m_unique_probe_hidden),
    ("a chip temperature reaches a room page", m_chip_temperature_shown),
    ("a presence sensor's room humidity hidden as an appliance's", m_presence_probe_hidden),
    ("a camera gets a hand-listed card", m_camera_hand_listed),
    ("the room card takes any Magic Areas group", m_room_card_any_group),
    ("room pages lose the occupancy tile", m_occupancy_tile_dropped),
    ("room pages are one narrow column", m_room_page_one_column),
    ("Energy stops packing densely", m_energy_not_dense),
    ("Home goes back to four columns", m_home_four_columns),
    ("a tablet is treated as a big phone", m_home_tablet_gap),
    ("the occupancy tile no longer opens details", m_occupancy_tile_not_tappable),
    ("room pages lose the Environment block", m_env_block_dropped),
    ("environment readings need the label again", m_env_needs_label),
    ("the environment rule takes in power", m_env_rule_broadened),
    ("'All lights' given to a category group too", m_all_lights_doubled),
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
    ("a tiled room loses its styled page", m_room_loses_page),
    ("a room's Magic Areas device has no area", m_ma_device_unplaced),
    ("a tiled room has no Magic Area", m_room_without_ma),
    ("Needs attention ignores a silent safety sensor", m_silent_unsaid),
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

    bad = skipped = 0
    present = [f for f in FILES if os.path.exists(os.path.join(LIVE, f))]
    # The committed fixtures carry no admin panel by design (CI); every other store must exist.
    absent = sorted(set(FILES) - set(present))
    if absent and absent != [ADM]:
        print("missing store(s): %s" % ", ".join(absent))
        return 2
    for name, fn in MUTATIONS:
        d = tempfile.mkdtemp(prefix="dashlint-")
        try:
            for f in present:
                shutil.copy(os.path.join(LIVE, f), os.path.join(d, f))
            try:
                want = fn(d)
            except FileNotFoundError:
                print("  skipped   %-44s (its dashboard is not in these stores)" % name)
                skipped += 1
                continue
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
    print("all %d mutations caught%s" % (len(MUTATIONS) - skipped,
                                         (", %d skipped" % skipped) if skipped else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
