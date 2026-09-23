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
}


def load(name):
    with io.open(os.path.join(STORAGE, name), encoding="utf-8") as fh:
        return json.load(fh)["data"]["config"]


def registry():
    with io.open(os.path.join(STORAGE, "core.entity_registry"), encoding="utf-8") as fh:
        return {e["entity_id"] for e in json.load(fh)["data"]["entities"]}


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
