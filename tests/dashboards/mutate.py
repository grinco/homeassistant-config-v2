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
         "lovelace_resources")

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


MUTATIONS = [
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
