#!/usr/bin/env python3
"""Does every dashboard card actually render, and do the readings line up?

`tests/climate/` is an expression oracle for the climate loop. It has nothing to
say about dashboards, and on 2026-09-23 that gap cost three broken views: the
whole admin panel stopped rendering because its cards referenced button-card
templates that were defined on a *different* dashboard.

The check that was supposed to catch it walked both dashboards' cards but
compared them against one dashboard's template library, so it passed while being
blind to the only thing that mattered. **A check that cannot fail is worse than
no check** - the same lesson `tests/climate/` was built on, relearned here.

This reads the LIVE dashboards out of `.storage`, which is authoritative; the
JSON under `lovelace-dashboards/` is a sanitised snapshot and deliberately does
not match.

    python3 tests/dashboards/lint.py
    python3 tests/dashboards/lint.py -v    # list every offending card

Checks, each one written because something it catches actually shipped:

  C1 templates-resolve   every `template:` a card names is defined in ITS OWN
                         dashboard, expanded transitively.
  C2 no-foreign-options  a card carries no options belonging to a different card
                         type (a `state_content` copied onto a button-card).
  C3 uniform-sizing      no button-card resolves to an `aspect_ratio`, and every
                         one declares `grid_options.rows`. Height then comes from
                         the section grid and is uniform; an aspect ratio makes
                         height follow width, so the same card is a small square
                         at columns 4 and a giant one at columns 12.
  C4 entities-exist      every entity id named anywhere, including inside
                         button-card JS templates, is in the entity registry.
  C5 card-resources      every `custom:` card type has a registered Lovelace
                         resource. A card type with no JavaScript behind it
                         renders an error box and no entity check would notice.
  C6 no-debug-keys       no `_`-prefixed scratch key left on a view by a
                         transform.
  C8 variables-defined   a card's OWN js templates only reference `variables.x`
                         that the card, or a template it uses, actually defines.
                         Clobbering a card's label with one written for a
                         different card leaves every lookup undefined and the
                         card renders a fallback dash - which is what happened
                         to six Home tiles.
  C9 area-coverage       every entity a room's AREA holds is reachable from that
                         room's view - either named outright, or matched by an
                         auto-entities rule for that area and domain. A view
                         built by hand goes stale the moment a bulb is added to
                         the area; on 2026-09-23 that hid two lights in Hallway
                         and one in Corridor, and no other check noticed.
  C10 tiles-self-resolve a Home room tile resolves its room from `variables.area`
                         and names no per-room entity id. A tile that hardcodes
                         its light group renders a dash forever once the group
                         is created, renamed, or first appears - which is what
                         Hallway did.
  C11 rollback-intact    the `home-classic` view carries none of the rebuild's
                         vocabulary - no button-card, no auto-entities. It is
                         the fallback the Mushroom rebuild left in place, and a
                         rollback that has been restyled is not a rollback. The
                         transform that generated the room tiles matched the
                         section by its "Rooms" heading and silently rewrote the
                         classic view's too; nothing else noticed.
  C12 outlets-off-rooms  no room page generates a `device_class: outlet` entity.
                         Sockets are on the Energy tab for monitoring and
                         nothing else; a room page that offers one as a toggle
                         undoes that, and one of them feeds the network gear.
  C13 generated          the sections that list DEVICES - Home rooms, Energy
                         sockets, Security sensors, admin people and the admin
                         Devices view - contain headings, markdown and
                         auto-entities only, never a card that names an entity.
                         A hand-listed card is a dashboard edit per device: the
                         mini rack plug (2026-09-24) needed nine of them and
                         still missed the socket total, and renaming the terrace
                         sensor broke ten more. A missing section fails too, so
                         the check cannot pass by the section being deleted.
  C14 one-room-skeleton  every room page is the same page with its area swapped in.
                         A page edited by hand stops receiving fixes made to the
                         others, and a new area can only be added cheaply if its
                         page is a copy of a known-good one.
  C15 focused-rooms      a room page generates lights, climate, fans, covers,
                         locks and media for its area, and anything else ONLY
                         through the `on_room_page` label (or Magic Areas'
                         automation switches). The kitchen page listed 49
                         entities on 2026-09-25, 46 of them appliance settings
                         nobody opens a room page for.
  C16 string-matchers    an auto-entities rule's `domain` (or any matcher) is a
                         string or a /regex/, never a list. A list matches
                         NOTHING and says nothing: the labelled-extras block
                         shipped that way on 2026-09-25 and no labelled switch
                         ever reached a room page until the cat toilet's did not.
  C17 whole-room-group   a room card that picks its light group out of Magic
                         Areas' lights picks the `_all_lights` one. Magic Areas
                         makes one group per light category as well; once the
                         living room got an `overhead_lights` group (2026-10-07)
                         "last Magic Areas light wins" could hand the room's
                         light button a subset of the room.
  C18 environment-shown  every environmental reading in a room's area -
                         temperature, humidity, light level, CO2, particulates,
                         VOC, pressure - is generated as a tile on its room page,
                         unless labelled `not_on_room_pages` (a raw probe that a
                         resolved sensor already reports). Matched rule by rule,
                         not per domain: on 2026-10-07 the terrace's light level,
                         the corridor's PM2.5 and a bedroom's PM2.5/VOC sat in a
                         domain C9 counted as covered, behind a label rule they
                         could never satisfy, and no page showed them.
  C19 one-per-name       an include rule that gives its tile a fixed `name`
                         matches at most one entity per room. Magic Areas' new
                         `overhead_lights` group (2026-10-07) matched the "All
                         lights" rule beside the real all-lights group, and the
                         living room showed two identical "All lights" tiles.
  C20 single-source-agg  a Magic Areas aggregate that stands in for a room's
                         reading (labelled `on_room_page`) averages exactly ONE
                         sensor. It is a mean of every sensor of its class in the
                         area: a second one - a probe in other air, a fridge
                         thermometer - would silently change the room's number.
                         Then the room needs a resolved template, not an
                         aggregate (review 2026-10-07).
  C21 safety-attention   Home's "Needs attention" section appears for ANY safety
                         alarm (it is gated on `binary_sensor.any_safety_alarm`)
                         and names no leak/smoke/gas/CO sensor by entity id. On
                         2026-10-09 a smoke and CO alarm was installed and the
                         section turned out to know one leak sensor by name and
                         nothing about smoke or CO.
  C22 one-night          no dashboard computes night the pre-v5.12 way, "schedule
                         OR alarm". Since 2026-10-11 the alarm's armed_night IS
                         night; the schedule only moves the alarm. A card still
                         reading the schedule says "Night targets" after the
                         operator switched to day by hand.
  C7 compact-layout      the vg_stat family is two lines tall, so it gets
                         `rows: 1` (56px), not `rows: 2` (120px) with half the
                         card empty; `columns` stays on the 6/12/full ladder so
                         rows are even; and a view's `max_columns` is a multiple
                         of its sections' `column_span`, or the leftover column
                         is dead space on every row.
"""

import io
import json
import os
import re
import sys

# Overridable so mutate.py can run this exact script against mutated fixtures
# rather than against a re-implementation of it.
STORAGE = os.environ.get("HA_STORAGE", "/usr/share/hassio/homeassistant/.storage")
DASHBOARDS = {"lovelace": "lovelace.lovelace", "admin-panel": "lovelace.admin_panel"}

# Options that belong to a specific card type and are silently ignored - or worse -
# anywhere else. Extend as they bite.
TILE_ONLY = ("state_content", "features", "features_position", "hide_state",
             "vertical", "state_color")
MUSHROOM_ONLY = ("primary", "secondary", "icon_color", "fill_container",
                 "icon_tap_action", "badge_icon", "badge_color", "multiline_secondary")
FOREIGN = {"custom:button-card": TILE_ONLY + MUSHROOM_ONLY}

# Entity ids appear inside button-card JS templates as plain strings, so a text
# scan reaches them; a structural walk over `entity:` keys would not.
ENTITY_RE = re.compile(
    r"\b(?:sensor|binary_sensor|switch|light|climate|media_player|fan|vacuum|camera|"
    r"alarm_control_panel|person|weather|input_boolean|input_number|input_select|"
    r"input_datetime|input_text|counter|schedule|automation|button|number|select|"
    r"update|remote|lock|image|event|zone|sun)\.[a-z0-9_]+")

# Service names and Jinja/JS concatenation stems the regex cannot tell from ids.
ENTITY_ALLOW = {"button.press", "light.turn_off", "light.turn_on", "sun.sun"}

# Domains a room page is expected to account for. `update`, `button`, `select`,
# `number` and `event` are deliberately absent: they are device plumbing, not
# things a room page is judged on.
ROOM_DOMAINS = ("light", "switch", "fan", "climate", "cover", "lock", "vacuum",
                "media_player", "sensor", "binary_sensor")

# Readings that belong to the Energy tab. Putting them on a room page would undo
# the 2026-09-23 consolidation, so C9 does not demand them.
ENERGY_CLASSES = {"energy", "power", "voltage", "current", "power_factor",
                  "apparent_power", "reactive_power", "monetary", "energy_storage"}

# The registry label that suppresses an entity from its room page. It lives in
# Home Assistant rather than in the dashboard on purpose: a curation decision
# about one entity should not be a dashboard edit, and a filter that is generic
# cannot carry exceptions.
ROOM_HIDDEN_LABEL = "not_on_room_pages"

# Room pages (C15): domains shown by default, and the opt-in label for the rest.
ROOM_DEFAULT_DOMAINS = ("light", "climate", "fan", "cover", "lock", "media_player")
ROOM_SHOW_LABEL = "on_room_page"

# Environmental readings a room page shows by default (C18). A sensor of one of
# these classes, in a room's area, is generated as a tile unless it carries
# ROOM_HIDDEN_LABEL. The Zigbee VOC index is unitless and has no device class,
# so it is named by its entity-id suffix instead.
ENV_CLASSES = ("temperature", "humidity", "illuminance", "carbon_dioxide", "carbon_monoxide",
               "pm1", "pm25", "pm10", "volatile_organic_compounds",
               "volatile_organic_compounds_parts", "aqi", "atmospheric_pressure", "pressure",
               "nitrogen_dioxide", "ozone", "sound_pressure")
ENV_ID_RE = re.compile(r"_voc_index$")

# C21: the classes that make the house unsafe, and the sensor that rolls them up.
SAFETY_CLASSES = ("moisture", "smoke", "gas", "carbon_monoxide", "safety")
SAFETY_ROLLUP = "binary_sensor.any_safety_alarm"

# Sections that list devices and must therefore be generated (C13):
# (dashboard, view path, first heading of the section, or None for every section).
GENERATED = [
    ("lovelace", "home", "Rooms"),
    ("lovelace", "energy", "Sockets"),
    ("lovelace", "security", "Sensors"),
    ("lovelace", "security", "Cameras"),
    ("lovelace", "climate", "Heating & hot water"),
    ("lovelace", "climate", "Temperature"),
    ("lovelace", "climate", "Humidity"),
    ("admin-panel", "system", "Phones & presence"),
    ("admin-panel", "devices", None),
]

RESOURCE_SLUG = {
    "button-card": "button-card",
    "slider-entity-row": "lovelace-slider-entity-row",
    "mini-media-player": "mini-media-player",
    "mini-graph-card": "mini-graph-card",
    "simple-thermostat": "simple-thermostat",
    "simple-weather-card": "simple-weather-card",
    "stack-in-card": "stack-in-card",
    "multiple-entity-row": "lovelace-multiple-entity-row",
    "vacuum-card": "vacuum-card",
    "alarmo-card": "alarmo-card",
    "auto-entities": "lovelace-auto-entities",
}


def load(name):
    with io.open(os.path.join(STORAGE, name), encoding="utf-8") as fh:
        return json.load(fh)["data"]["config"]


def registry():
    with io.open(os.path.join(STORAGE, "core.entity_registry"), encoding="utf-8") as fh:
        return {e["entity_id"] for e in json.load(fh)["data"]["entities"]}


def _store(name, key):
    with io.open(os.path.join(STORAGE, name), encoding="utf-8") as fh:
        return json.load(fh)["data"][key]


def area_members():
    """area_id -> the entities a room page is expected to account for.

    Area comes from the entity, or from its device when the entity itself
    carries none - the same fallback auto-entities applies, so the two agree on
    what "in this room" means.
    """
    devices = {d["id"]: d for d in _store("core.device_registry", "devices")}
    out = {}
    for e in _store("core.entity_registry", "entities"):
        if e.get("disabled_by") or e.get("hidden_by") or e.get("entity_category"):
            continue
        labels = e.get("labels") or []
        if ROOM_HIDDEN_LABEL in labels:
            continue
        domain = e["entity_id"].split(".")[0]
        # Since 2026-09-25 a room page is focused (C15): the default domains, plus
        # whatever carries the opt-in label. Nothing else is owed a place on it.
        if domain not in ROOM_DEFAULT_DOMAINS and ROOM_SHOW_LABEL not in labels:
            continue
        if ROOM_SHOW_LABEL not in labels and \
                (e.get("original_device_class") or e.get("device_class")) in ENERGY_CLASSES:
            continue
        area = e.get("area_id") or (devices.get(e.get("device_id")) or {}).get("area_id")
        if not area:
            continue
        out.setdefault(area, set()).add(e["entity_id"])
    return out


def registry_entities():
    """Every enabled entity with the fields an auto-entities rule can test."""
    devices = {d["id"]: d for d in _store("core.device_registry", "devices")}
    out = []
    for e in _store("core.entity_registry", "entities"):
        if e.get("disabled_by"):
            continue
        out.append(dict(
            entity_id=e["entity_id"], domain=e["entity_id"].split(".")[0],
            area=e.get("area_id") or (devices.get(e.get("device_id")) or {}).get("area_id"),
            labels=e.get("labels") or [], integration=e.get("platform"),
            device_class=e.get("device_class") or e.get("original_device_class"),
            entity_category=e.get("entity_category"), hidden_by=e.get("hidden_by")))
    return out


def _m(pattern, value):
    """auto-entities' matcher for a string: exact, or /regex/ searched."""
    value = "" if value is None else str(value)
    pattern = str(pattern)
    if len(pattern) > 1 and pattern.startswith("/") and pattern.endswith("/"):
        return re.search(pattern[1:-1], value) is not None
    return pattern == value


def rule_matches(rule, ent, area_name_of):
    """Does one include/exclude rule match a registry entity?

    Covers the matchers room pages use. An attribute other than device_class
    cannot be read from the registry, so a rule testing one returns None
    (unknown) rather than guessing - callers decide what unknown means.
    """
    unknown = False
    for k, want in rule.items():
        if k in ("options", "sort"):
            continue
        if k == "domain":
            ok = _m(want, ent["domain"])
        elif k == "area":
            ok = ent["area"] is not None and (_m(want, ent["area"])
                                              or _m(want, area_name_of.get(ent["area"])))
        elif k == "label":
            ok = any(_m(want, l) for l in ent["labels"])
        elif k == "integration":
            ok = _m(want, ent["integration"])
        elif k == "entity_id":
            ok = _m(want, ent["entity_id"])
        elif k in ("entity_category", "hidden_by"):
            ok = ent[k] is not None and _m(want, ent[k])
        elif k == "attributes":
            ok = True
            for ak, av in want.items():
                if ak == "device_class":
                    ok = ok and _m(av, ent["device_class"])
                else:
                    unknown = True
        else:
            unknown = True
            ok = True
        if not ok:
            return False
    return None if unknown else True


def env_rule(rule):
    """Is this the environmental-readings rule (C15 allows it, C18 needs it)?

    Exactly: sensors, selected by a device-class alternation drawn ONLY from
    ENV_CLASSES, or by the VOC-index id suffix. A broader class pattern would
    let the focused room page fill up with power and diagnostic readings again.
    """
    if rule.get("domain") != "sensor" or rule.get("label"):
        return False
    keys = set(rule) - {"domain", "area", "options", "sort"}
    if keys == {"entity_id"}:
        return rule["entity_id"] == "/" + ENV_ID_RE.pattern + "/"
    if keys != {"attributes"} or set(rule["attributes"]) != {"device_class"}:
        return False
    m = re.match(r"^/\^\((.*)\)\$/$", str(rule["attributes"]["device_class"]))
    return bool(m) and all(c in ENV_CLASSES for c in m.group(1).split("|"))


def generators(view):
    """(card, includes, excludes) for each auto-entities card that makes TILES.

    A generator whose own card is a heading only contributes badges, which is
    not a place an operator reads a value from on a phone.
    """
    out = []
    for _, card in cards(view):
        if card.get("type") != "custom:auto-entities":
            continue
        if ((card.get("card") or {}).get("type")) == "heading":
            continue
        f = card.get("filter") or {}
        out.append((card, f.get("include") or [], f.get("exclude") or []))
    return out


def area_names():
    """area_id -> name, for areas on a floor.

    An area with no floor is not a room: `outside` holds the weather station and
    has no page, and demanding one would be a check failing for a wrong reason.
    """
    return {a["id"]: a.get("name") for a in _store("core.area_registry", "areas")
            if a.get("floor_id")}


def generated(view):
    """(area, domain) pairs an auto-entities card on this view populates.

    Only the shape is read, never the matching: what a rule selects is
    auto-entities' business, and re-implementing it here would make the check
    agree with itself rather than with the card.
    """
    pairs = set()
    for _, card in cards(view):
        if card.get("type") != "custom:auto-entities":
            continue
        for rule in ((card.get("filter") or {}).get("include") or []):
            area = rule.get("area")
            dom = rule.get("domain")
            if not area or not dom:
                continue
            for d in (dom if isinstance(dom, list) else [dom]):
                pairs.add((str(area), str(d)))
    return pairs


def resources():
    with io.open(os.path.join(STORAGE, "lovelace_resources"), encoding="utf-8") as fh:
        return " ".join(r["url"] for r in json.load(fh)["data"]["items"])


def cards(node, path="", out=None):
    """Every dict that looks like a card, with the path that located it."""
    if out is None:
        out = []
    if isinstance(node, dict):
        if isinstance(node.get("type"), str):
            out.append((path, node))
        for k, v in node.items():
            cards(v, "%s/%s" % (path, k), out)
    elif isinstance(node, list):
        for i, v in enumerate(node):
            cards(v, "%s/%d" % (path, i), out)
    return out


def template_names(card):
    t = card.get("template")
    if isinstance(t, str):
        return [t]
    if isinstance(t, list):
        return [x for x in t if isinstance(x, str)]
    return []


def resolve(name, lib, seen=None):
    """A template's effective config, parents first. Cycles stop rather than hang."""
    if seen is None:
        seen = set()
    if name in seen or name not in lib:
        return {}
    seen.add(name)
    tpl = lib[name]
    eff = {}
    for parent in template_names(tpl):
        eff.update(resolve(parent, lib, seen))
    for k, v in tpl.items():
        if k != "template":
            eff[k] = v
    return eff


def effective(card, lib):
    eff = {}
    for name in template_names(card):
        eff.update(resolve(name, lib))
    for k, v in card.items():
        if k != "template":
            eff[k] = v
    return eff


def main():
    verbose = "-v" in sys.argv
    reg = registry()
    res = resources()
    fails = []

    def fail(check, msg, detail=None):
        fails.append((check, msg, detail or []))

    for label, fname in DASHBOARDS.items():
        cfg = load(fname)
        lib = cfg.get("button_card_templates", {})
        views = cfg.get("views", [])
        found = cards(views, label)

        # C1 - templates resolve within THIS dashboard
        missing = {}
        for path, card in found:
            for name in template_names(card):
                if name not in lib:
                    missing.setdefault(name, []).append(path)
        if missing:
            fail("C1", "%s: %d template name(s) used by cards are not defined in "
                       "this dashboard's button_card_templates" % (label, len(missing)),
                 ["%-26s %d card(s), e.g. %s" % (n, len(p), p[0]) for n, p in sorted(missing.items())])

        # C2 - no options from a foreign card type
        foreign = []
        for path, card in found:
            for key in FOREIGN.get(card.get("type"), ()):
                if key in card:
                    foreign.append("%s  has %r  (%s)" % (path, key, card.get("entity")))
        if foreign:
            fail("C2", "%s: %d card(s) carry an option from a different card type"
                 % (label, len(foreign)), foreign)

        # C3 - uniform sizing
        ratio, norows = [], []
        for path, card in found:
            if card.get("type") != "custom:button-card":
                continue
            eff = effective(card, lib)
            if eff.get("aspect_ratio"):
                ratio.append("%s  aspect_ratio=%s  (%s)" % (path, eff["aspect_ratio"], card.get("entity")))
            # Only grid-positioned cards. A card nested in a `custom_fields`
            # slot (button-card's power pill, a slider row) is laid out by its
            # parent's grid-template-areas, so grid_options would do nothing -
            # requiring it there would be a check that fails for a wrong reason.
            if "/custom_fields/" in path:
                continue
            if not (card.get("grid_options") or {}).get("rows"):
                norows.append("%s  (%s)" % (path, card.get("entity")))
        if ratio:
            fail("C3", "%s: %d button-card(s) resolve to an aspect_ratio, so height "
                       "follows width and the same card is a different size in every "
                       "column span" % (label, len(ratio)), ratio)
        if norows:
            fail("C3", "%s: %d button-card(s) declare no grid_options.rows, so height "
                       "is content-driven and uneven" % (label, len(norows)), norows)

        # C4 - entities exist. Only the REACHABLE surface: views, plus the
        # templates cards actually reach. A dormant template cannot break a
        # render today, but the moment a card uses it this check must fail -
        # so reachability is computed rather than the template skipped.
        reach, queue = set(), [n for _, c in found for n in template_names(c)]
        for _ in range(len(lib) + 1):
            nxt = []
            for n in queue:
                if n in reach or n not in lib:
                    continue
                reach.add(n)
                nxt.extend(template_names(lib[n]))
            queue = nxt
        blob = json.dumps(views, ensure_ascii=False) + json.dumps(
            {k: lib[k] for k in reach}, ensure_ascii=False)
        ids = set(ENTITY_RE.findall(blob))
        gone = sorted(i for i in ids if i not in reg and i not in ENTITY_ALLOW
                      and not i.endswith("_"))
        if gone:
            fail("C4", "%s: %d entity id(s) named but not in the registry" % (label, len(gone)), gone)

        # C5 - custom card types have a resource
        types = sorted({c.get("type")[7:] for _, c in found
                        if isinstance(c.get("type"), str) and c["type"].startswith("custom:")})
        unbacked = []
        for t in types:
            slug = RESOURCE_SLUG.get(t) or ("lovelace-mushroom" if t.startswith("mushroom-") else None)
            if not slug or slug not in res:
                unbacked.append(t)
        if unbacked:
            fail("C5", "%s: %d custom card type(s) have no registered resource"
                 % (label, len(unbacked)), unbacked)

        # C7 - compact layout. Written after the operator reported dead space
        # on both mobile and laptop: every converted card was rows:2 (120px)
        # carrying ~64px of content, and Home's span-2 sections under a
        # 3-column cap left the third column empty on every row.
        tall, odd = [], []
        for path, card in found:
            if card.get("type") != "custom:button-card" or "/custom_fields/" in path:
                continue
            chain = set()
            queue = list(template_names(card))
            for _ in range(len(lib) + 1):
                nxt = []
                for n in queue:
                    if n in chain or n not in lib:
                        continue
                    chain.add(n)
                    nxt.extend(template_names(lib[n]))
                queue = nxt
            go = card.get("grid_options") or {}
            if "vg_stat" in chain and go.get("rows") != 1:
                tall.append("%s  rows=%r  (%s)" % (path, go.get("rows"), card.get("entity")))
            if go.get("columns") not in (6, 12, "full"):
                odd.append("%s  columns=%r  (%s)" % (path, go.get("columns"), card.get("entity")))
        if tall:
            fail("C7", "%s: %d vg_stat-family card(s) are taller than their content"
                 % (label, len(tall)), tall)
        if odd:
            fail("C7", "%s: %d card(s) sit off the 6/12/full column ladder, so rows "
                       "do not line up" % (label, len(odd)), odd)

        dead = []
        for i, v in enumerate(views):
            secs = v.get("sections") or []
            if not secs:
                continue
            spans = {s.get("column_span", 1) for s in secs}
            mc = v.get("max_columns") or 4
            if len(spans) == 1:
                span = spans.pop()
                if mc % span:
                    dead.append("%s/views/%d %r: max_columns=%d is not a multiple of "
                                "column_span=%d" % (label, i, v.get("title"), mc, span))
        if dead:
            fail("C7", "%s: %d view(s) leave a dead section column" % (label, len(dead)), dead)

        # C8 - a card's own JS may only use variables something defines.
        # Scoped to CARD-level strings on purpose: a template's own JS may
        # reference an optional variable it null-checks (upstream's
        # `custom_s2` does exactly that), and flagging those would be a check
        # failing for a wrong reason.
        undef = []
        for path, card in found:
            if card.get("type") != "custom:button-card":
                continue
            have = set((card.get("variables") or {}).keys())
            for name in template_names(card):
                have |= set((resolve(name, lib).get("variables") or {}).keys())
            own = []
            for k, v in card.items():
                if k in ("variables", "template", "type"):
                    continue
                own.append(json.dumps(v, ensure_ascii=False))
            used = set(re.findall(r"variables\.([A-Za-z_][A-Za-z0-9_]*)", " ".join(own)))
            missing_vars = sorted(used - have)
            if missing_vars:
                undef.append("%s  uses %s  (%s)" % (path, ", ".join(missing_vars), card.get("entity")))
        if undef:
            fail("C8", "%s: %d card(s) reference a variable nothing defines - they "
                       "will render a fallback, not a value" % (label, len(undef)), undef)

        # C10 - a Home room tile resolves its own room.
        # The tile that started this: Hallway's `grp` was "" because the area
        # had no light group when the tile was written. Magic Areas created one
        # the moment a bulb was placed there, and the tile went on rendering a
        # dash - a value frozen at authoring time, in a card whose whole job is
        # to report the present. Naming the AREA instead of the entities is the
        # structural version of the promise room-tile-navigation.md already
        # made: "it starts working by itself the moment a light is added".
        #
        # The room tiles are located by the section they live in, NOT by their
        # template name: `vg_room` is also worn by the six quick-strip tiles and
        # by Energy's Cheapest block, and selecting on the name is what
        # clobbered all seven of them in the compaction pass (C8). The first
        # draft of this check repeated that mistake and reported 19 tiles.
        if label == "lovelace":
            areas = area_names()
            floors = {a["id"]: a.get("floor_id") for a in _store("core.area_registry", "areas")}
            # Since 2026-09-25 the tiles are GENERATED: one auto-entities per floor,
            # whose Jinja reads `floor` and a `rooms` map (area -> name/icon/page/
            # special) out of its own config. The map is structured data on purpose,
            # so this check reads it rather than re-implementing the template.
            gens = []
            for view in views:
                for sec in (view.get("sections") or []):
                    cs = sec.get("cards") or []
                    if not cs or cs[0].get("heading") != "Rooms":
                        continue
                    for i, c in enumerate(cs):
                        if c.get("type") == "custom:auto-entities" and "floor" in c:
                            gens.append(("%s/rooms/%d" % (label, i), c))
            if not gens:
                fail("C10", "%s: found no room-tile generator at all - the Rooms section "
                            "is gone or renamed, and C9/C10 would pass by default" % label)

            tile_area, stale, unknown = {}, [], []
            tpls = {json.dumps((c.get("filter") or {}).get("template")) for _, c in gens}
            if len(tpls) > 1:
                fail("C10", "%s: the %d floor generators run different templates - a fix "
                            "made to one floor silently misses the other" % (label, len(gens)))
            covered = set()
            variants = {}
            for path, gen in gens:
                floor = gen.get("floor")
                covered.add(floor)
                # A floor can be generated once per screen width (2 columns on
                # phones, 4 on wide screens). Every floor must carry the same set
                # of variants, or its rooms vanish at one width only.
                variants.setdefault(floor, set()).add(json.dumps(gen.get("visibility"), sort_keys=True))
                for area, o in sorted((gen.get("rooms") or {}).items()):
                    pinned = sorted(k for k, v in o.items()
                                    if isinstance(v, str) and ENTITY_RE.fullmatch(v))
                    if pinned:
                        stale.append("%s  %s pins %s" % (path, area,
                                                         ", ".join("%s=%s" % (k, o[k]) for k in pinned)))
                    if area not in areas:
                        unknown.append("%s  names area %r, which does not exist" % (path, area))
                    elif floors.get(area) != floor:
                        unknown.append("%s  maps %r, which is not on floor %r" % (path, area, floor))
                    elif o.get("page"):
                        tile_area[area] = o["page"]
            if stale:
                fail("C10", "%s: %d room(s) pin a per-room entity id, so the "
                            "tile freezes at the moment it was written"
                     % (label, len(stale)), stale)
            if unknown:
                fail("C10", "%s: %d room map entr(ies) do not resolve a real area"
                     % (label, len(unknown)), unknown)

            # C9 - every room is reachable, and a styled page accounts for its area.
            # Driven from the AREA REGISTRY. An area with no map entry is legal: its
            # tile opens Home Assistant's own area page until it is given a styled one.
            members = area_members()
            by_path = {v.get("path"): v for v in views}
            allv = set().union(*variants.values()) if variants else set()
            short = sorted("%s lacks %d screen variant(s)" % (f, len(allv - v))
                           for f, v in variants.items() if v != allv)
            if short:
                fail("C9", "%s: a floor's rooms are generated for fewer screen widths than "
                           "another's, so they disappear at some widths" % label, short)
            roomless = sorted(a for a in areas if a in members and floors.get(a) not in covered)
            if roomless:
                fail("C9", "%s: %d area(s) hold entities on a floor no generator covers, "
                           "so they get no Home tile" % (label, len(roomless)), roomless)

            uncovered, pageless = [], []
            for area, path in sorted(tile_area.items()):
                view = by_path.get(path)
                if view is None:
                    pageless.append("%s -> %r" % (area, path))
                    continue
                pairs = generated(view)
                blob_v = json.dumps(view, ensure_ascii=False)
                rx = [re.compile(d[1:-1]) for a2, d in pairs
                      if a2 in (area, str(areas.get(area))) and d.startswith("/") and d.endswith("/")]
                for eid in sorted(members.get(area, ())):
                    domain = eid.split(".")[0]
                    if (area, domain) in pairs or (str(areas.get(area)), domain) in pairs:
                        continue
                    if any(r.search(domain) for r in rx):
                        continue
                    if eid in blob_v:
                        continue
                    uncovered.append("%-14s %s" % (path, eid))
            if pageless:
                fail("C9", "%s: %d room(s) map to a page that does not exist" % (label, len(pageless)), pageless)
            if uncovered:
                fail("C9", "%s: %d entity/entities sit in an area whose room view "
                           "neither names them nor generates their domain"
                     % (label, len(uncovered)), uncovered)

        # C12 - sockets stay off the room pages.
        # Checked on the dashboard rather than on the registry: "a switch whose
        # device also reports power" catches every AC display-lighting and
        # sound-effect switch too, and a check that fails for the wrong reason
        # is worse than none. The invariant here is exact - once an entity is
        # marked an outlet, no room page may generate it.
        if label == "lovelace":
            unguarded = []
            for view in views:
                if not view.get("subview") or view.get("back_path") != "/lovelace/home":
                    continue
                if view.get("path") == "home-classic":
                    continue
                for path, card in cards(view, "%s/%s" % (label, view.get("path"))):
                    if card.get("type") != "custom:auto-entities":
                        continue
                    inc = (card.get("filter") or {}).get("include") or []
                    if not any(r.get("domain") == "switch" for r in inc):
                        continue
                    exc = (card.get("filter") or {}).get("exclude") or []
                    if not any((e.get("attributes") or {}).get("device_class") == "outlet"
                               for e in exc):
                        unguarded.append("%s  (%s)" % (path, view.get("path")))
            if unguarded:
                fail("C12", "%s: %d room block(s) generate switches without excluding "
                            "outlets, so a metered socket lands back on a room page"
                     % (label, len(unguarded)), unguarded)

        # C11 - the rollback view is left alone.
        if label == "lovelace":
            classic = [v for v in views if v.get("path") == "home-classic"]
            leaked = []
            for v in classic:
                for path, card in cards(v, "%s/home-classic" % label):
                    t = card.get("type")
                    if t in ("custom:button-card", "custom:auto-entities"):
                        leaked.append("%s  %s  (%s)" % (path, t, card.get("entity")))
            if leaked:
                fail("C11", "%s: %d card(s) of the rebuild's vocabulary have leaked "
                            "into the rollback view" % (label, len(leaked)), leaked)

        # C13 - device lists are generated, not hand-listed.
        for (dash, vpath, heading) in GENERATED:
            if dash != label:
                continue
            view = next((v for v in views if v.get("path") == vpath), None)
            secs = [] if view is None else [
                s for s in (view.get("sections") or [])
                if heading is None or ((s.get("cards") or [{}])[0].get("heading") == heading)]
            if not secs:
                fail("C13", "%s: %s has no %s section - a generated list that is "
                            "missing passes every other check"
                     % (label, vpath, repr(heading) if heading else "any"))
                continue
            listed = []
            for s in secs:
                for i, c in enumerate(s.get("cards") or []):
                    t_ = c.get("type")
                    if t_ in ("heading", "markdown"):
                        continue
                    if t_ == "custom:auto-entities" and not c.get("entities"):
                        continue
                    listed.append("%s/%s/%s#%d  %s  (%s)" % (label, vpath, heading or "*", i, t_,
                                                            c.get("entity") or c.get("name")))
            if listed:
                fail("C13", "%s: %d hand-listed card(s) in a section the registry could "
                            "generate - every new device is another edit"
                     % (label, len(listed)), listed)

        # C14 / C15 - room pages: one skeleton, and focused.
        if label == "lovelace":
            rooms = [v for v in views if v.get("subview") and v.get("back_path") == "/lovelace/home"
                     and v.get("path") != "home-classic"]
            shapes = {}
            unfocused = []
            for v in rooms:
                areas_here = set()
                for _, card in cards(v):
                    for r in ((card.get("filter") or {}).get("include") or []):
                        if r.get("area"):
                            areas_here.add(str(r["area"]))
                        doms = r.get("domain")
                        doms = doms if isinstance(doms, list) else [doms]
                        if not r.get("area") or r.get("label") == ROOM_SHOW_LABEL:
                            continue
                        if r.get("integration") == "magic_areas":
                            continue
                        if env_rule(r):
                            continue
                        loose = [d for d in doms if d and d not in ROOM_DEFAULT_DOMAINS]
                        if loose:
                            unfocused.append("%s  generates %s without the %r label"
                                             % (v.get("path"), "/".join(loose), ROOM_SHOW_LABEL))
                body = {k: v[k] for k in v if k not in ("title", "path", "icon")}
                blob = json.dumps(body, sort_keys=True, ensure_ascii=False)
                for a in areas_here:
                    blob = blob.replace('"area": "%s"' % a, '"area": "@AREA"')
                shapes.setdefault(blob, []).append(v.get("path"))
            if len(shapes) > 1:
                groups = sorted(shapes.values(), key=len, reverse=True)
                fail("C14", "%s: room pages come in %d shapes, not one - the odd ones out "
                            "no longer receive fixes made to the rest" % (label, len(shapes)),
                     ["%d page(s): %s" % (len(g), ", ".join(sorted(g))) for g in groups])
            if unfocused:
                fail("C15", "%s: %d room rule(s) pull in entities nobody asked for"
                     % (label, len(unfocused)), sorted(set(unfocused)))

        # C18 / C19 - environmental readings reach their room, and a fixed tile
        # name belongs to one entity.
        if label == "lovelace":
            ents = registry_entities()
            area_name_of = {a["id"]: a["name"] for a in _store("core.area_registry", "areas")}
            missing_env, doubled = [], []
            for v in rooms:
                gens = generators(v)
                page_areas = set()
                for _, inc, _ in gens:
                    for r in inc:
                        if r.get("area"):
                            page_areas.add(str(r["area"]))
                here = [e for e in ents if e["area"] is not None and
                        (e["area"] in page_areas or area_name_of.get(e["area"]) in page_areas)]
                for e in here:
                    if e["domain"] != "sensor" or e["entity_category"] or e["hidden_by"]:
                        continue
                    if ROOM_HIDDEN_LABEL in e["labels"]:
                        continue
                    if e["device_class"] not in ENV_CLASSES and not ENV_ID_RE.search(e["entity_id"]):
                        continue
                    shown = any(
                        any(rule_matches(r, e, area_name_of) for r in inc)
                        and not any(rule_matches(x, e, area_name_of) for x in exc)
                        for _, inc, exc in gens)
                    if not shown:
                        missing_env.append("%-14s %s (%s)" % (v.get("path"), e["entity_id"],
                                                              e["device_class"] or "no class"))
                for _, inc, exc in gens:
                    for r in inc:
                        name = (r.get("options") or {}).get("name")
                        # A name CONFIG ([{type: entity}, ...]) is resolved per entity;
                        # only a literal string names every tile the rule makes.
                        if not isinstance(name, str) or not name:
                            continue
                        hit = [e["entity_id"] for e in here
                               if rule_matches(r, e, area_name_of) is not False
                               and not any(rule_matches(x, e, area_name_of) for x in exc)]
                        if len(hit) > 1:
                            doubled.append("%-14s %r <- %s" % (v.get("path"), name, ", ".join(sorted(hit))))
            if missing_env:
                fail("C18", "%s: %d environmental reading(s) in a room's area appear on no "
                            "room page" % (label, len(missing_env)), sorted(missing_env))
            if doubled:
                fail("C19", "%s: %d fixed tile name(s) are given to more than one entity"
                     % (label, len(doubled)), sorted(doubled))

        # C20 - a labelled Magic Areas aggregate has exactly one member.
        if label == "lovelace":
            ents = registry_entities()
            multi = []
            for a in ents:
                if a["integration"] != "magic_areas" or ROOM_SHOW_LABEL not in a["labels"]:
                    continue
                if a["domain"] != "sensor" or "_aggregate_" not in a["entity_id"]:
                    continue
                members = [e["entity_id"] for e in ents
                           if e["domain"] == "sensor" and e["integration"] != "magic_areas"
                           and e["area"] == a["area"] and e["device_class"] == a["device_class"]]
                if len(members) != 1:
                    multi.append("%s averages %d: %s" % (a["entity_id"], len(members), ", ".join(sorted(members))))
            if multi:
                fail("C20", "%s: %d room reading(s) are a Magic Areas mean of other than one sensor"
                     % (label, len(multi)), sorted(multi))

        # C21 - Needs attention covers every safety alarm, by class, not by name.
        if label == "lovelace":
            home = next((v for v in views if v.get("path") == "home"), {})
            na = [sec for sec in (home.get("sections") or [])
                  if (sec.get("cards") or [{}])[0].get("heading") == "Needs attention"]
            safety_ids = {e["entity_id"] for e in registry_entities()
                          if e["domain"] == "binary_sensor" and e["device_class"] in SAFETY_CLASSES}
            problems = []
            if not na:
                problems.append("home has no 'Needs attention' section")
            for sec in na:
                # Structure, not a substring (review 2026-10-09 F7): the section must be
                # visible when the roll-up is ON on its own - a top-level condition, or a
                # branch of a top-level OR. An AND, or the wrong state, hides a lone fire.
                vis = sec.get("visibility") or []
                want = {"condition": "state", "entity": SAFETY_ROLLUP, "state": "on"}
                branches = [c for c in vis if c == want] + [
                    b for c in vis if c.get("condition") == "or" and len(vis) == 1
                    for b in (c.get("conditions") or []) if b == want]
                if not branches:
                    problems.append("the section is not shown whenever %s is on by itself "
                                    "(need it as the sole condition or a branch of a lone OR)"
                                    % SAFETY_ROLLUP)
                for path, card in cards([sec], "home/needs-attention"):
                    named = card.get("entity")
                    if named in safety_ids:
                        problems.append("%s hand-lists %s" % (path, named))
            if problems:
                fail("C21", "%s: Needs attention would miss a safety alarm" % label, problems)

        # C22 - one definition of night.
        stale = [path for path, card in found
                 if "is_state('schedule.climate_night','on') or" in json.dumps(card)
                 and card.get("type") not in ("custom:auto-entities",)]
        if stale:
            fail("C22", "%s: %d card(s) still compute night from the schedule" % (label, len(stale)),
                 stale)

        # C16 - auto-entities matchers are strings.
        listy = []
        for path, card in found:
            if card.get("type") != "custom:auto-entities":
                continue
            for part in ("include", "exclude"):
                for i, r in enumerate(((card.get("filter") or {}).get(part)) or []):
                    for k, val in r.items():
                        if k != "options" and isinstance(val, list):
                            listy.append("%s  %s[%d].%s = %r" % (path, part, i, k, val))
        if listy:
            fail("C16", "%s: %d auto-entities matcher(s) are lists, which match nothing"
                 % (label, len(listy)), listy)

        # C17 - a room card's group is the whole room, not one light category.
        partial = []
        for tname, tdef in sorted(lib.items()):
            js = json.dumps(tdef)
            for m in re.finditer(r"platform\s*===?\s*\\?'magic_areas\\?'", js):
                after = js[m.end():m.end() + 160]
                if "grp" in after[:40] and "_all_lights" not in after:
                    partial.append("%s: ...%s..." % (tname, js[m.start():m.end() + 80]))
        if partial:
            fail("C17", "%s: %d template(s) take ANY Magic Areas light as the room's group"
                 % (label, len(partial)), partial)

        # C6 - no scratch keys
        debris = ["%s/views/%d %r" % (label, i, k)
                  for i, v in enumerate(views) for k in v if k.startswith("_")]
        if debris:
            fail("C6", "%s: %d scratch key(s) left on views" % (label, len(debris)), debris)

    if not fails:
        print("all checks pass")
        return 0
    print("%d FAILURE(S)\n" % len(fails))
    for check, msg, detail in fails:
        print("  [%s] %s" % (check, msg))
        shown = detail if verbose else detail[:4]
        for d in shown:
            print("        %s" % d)
        if not verbose and len(detail) > len(shown):
            print("        ... %d more (-v for all)" % (len(detail) - len(shown)))
        print("")
    return 1


if __name__ == "__main__":
    sys.exit(main())
