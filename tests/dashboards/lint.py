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
        if ROOM_HIDDEN_LABEL in (e.get("labels") or []):
            continue
        domain = e["entity_id"].split(".")[0]
        if domain not in ROOM_DOMAINS:
            continue
        if (e.get("original_device_class") or e.get("device_class")) in ENERGY_CLASSES:
            continue
        area = e.get("area_id") or (devices.get(e.get("device_id")) or {}).get("area_id")
        if not area:
            continue
        out.setdefault(area, set()).add(e["entity_id"])
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
            tiles = []
            for view in views:
                for sec in (view.get("sections") or []):
                    cs = sec.get("cards") or []
                    if not cs or cs[0].get("heading") != "Rooms":
                        continue
                    for i, c in enumerate(cs):
                        if c.get("type") == "custom:button-card" and "vg_room" in template_names(c):
                            tiles.append(("%s/rooms/%d" % (label, i), c))
            if not tiles:
                fail("C10", "%s: found no room tiles at all - the Rooms section is "
                            "gone or renamed, and C9/C10 would pass by default" % label)

            tile_area, stale, unknown = {}, [], []
            for path, card in tiles:
                v = card.get("variables") or {}
                nav = (card.get("hold_action") or {}).get("navigation_path") or ""
                frozen = sorted(k for k in ("grp", "ac", "pres")
                                if isinstance(v.get(k), str) and "." in v[k])
                if frozen:
                    stale.append("%s  %r pins %s" % (path, card.get("name"),
                                                     ", ".join("%s=%s" % (k, v[k]) for k in frozen)))
                area = v.get("area")
                if not area:
                    unknown.append("%s  %r defines no variables.area" % (path, card.get("name")))
                elif area not in areas:
                    unknown.append("%s  %r names area %r, which does not exist"
                                   % (path, card.get("name"), area))
                else:
                    tile_area[area] = nav[len("/lovelace/"):] if nav.startswith("/lovelace/") else None
            if stale:
                fail("C10", "%s: %d room tile(s) pin a per-room entity id, so the "
                            "tile freezes at the moment it was written"
                     % (label, len(stale)), stale)
            if unknown:
                fail("C10", "%s: %d room tile(s) do not resolve a real area"
                     % (label, len(unknown)), unknown)

            # C9 - a room view accounts for everything its area holds.
            # Driven from the AREA REGISTRY rather than from the views, so a
            # room that lost its tile or its page fails loudly instead of
            # dropping out of the loop and passing.
            members = area_members()
            by_path = {v.get("path"): v for v in views}
            roomless = sorted(a for a in areas
                              if a in members and a not in tile_area)
            if roomless:
                fail("C9", "%s: %d area(s) hold entities but no Home tile claims "
                           "them, so nothing routes to a room page" % (label, len(roomless)),
                     roomless)

            uncovered, pageless = [], []
            for area, path in sorted(tile_area.items()):
                view = by_path.get(path)
                if view is None:
                    pageless.append("%s -> %r" % (area, path))
                    continue
                pairs = generated(view)
                blob_v = json.dumps(view, ensure_ascii=False)
                for eid in sorted(members.get(area, ())):
                    domain = eid.split(".")[0]
                    if (area, domain) in pairs or (str(areas.get(area)), domain) in pairs:
                        continue
                    if eid in blob_v:
                        continue
                    uncovered.append("%-14s %s" % (path, eid))
            if pageless:
                fail("C9", "%s: %d room tile(s) navigate nowhere" % (label, len(pageless)), pageless)
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
