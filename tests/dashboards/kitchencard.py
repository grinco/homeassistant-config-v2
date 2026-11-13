#!/usr/bin/env python3
"""Run the kitchen card's own JavaScript against made-up appliances.

Appliances' kitchen row is one button-card template, `vg_kitchen`. Its detail
line (time left, progress, a running kitchen timer, otherwise program, cavity
temperature and door) is JavaScript in `variables.info`. This harness pulls that
exact code out of the LIVE `.storage/lovelace.lovelace` and executes it in
headless Chromium with fake `states`, as `roomcard.py` does for the Home room
card. The test carries inputs and expected text only, never the logic.

    python3 tests/dashboards/kitchencard.py

The clock is frozen at NOW and the browser runs in UTC, so times are exact.
"""

import io
import json
import os
import sys

STORAGE = os.environ.get("HA_STORAGE", "/usr/share/hassio/homeassistant/.storage")
NOW = "2026-11-13T18:00:00Z"


def js(text):
    text = text.strip()
    if not (text.startswith("[[[") and text.endswith("]]]")):
        raise SystemExit("not a button-card JS template: %r..." % text[:40])
    return text[3:-3]


def load():
    with io.open(os.path.join(STORAGE, "lovelace.lovelace"), encoding="utf-8") as fh:
        t = json.load(fh)["data"]["config"]["button_card_templates"]["vg_kitchen"]
    return js(t["variables"]["info"])


def st(eid, state, **attrs):
    return eid, {"entity_id": eid, "state": state, "attributes": attrs}


def at(minutes):
    return "2026-11-13T%02d:%02d:00+00:00" % (18 + minutes // 60, minutes % 60)


OVEN = dict(kind="oven", state="sensor.k_oven_operation_state", finish="sensor.k_oven_program_finish_time",
            progress="sensor.k_oven_program_progress", timer="number.k_oven_alarm_clock",
            temp="sensor.k_oven_current_oven_cavity_temperature", door="sensor.k_oven_door")
DISH = dict(kind="dishwasher", state="sensor.k_dishwasher_operation_state",
            finish="sensor.k_dishwasher_program_finish_time", progress="sensor.k_dishwasher_program_progress",
            program="select.k_dishwasher_selected_program", door="sensor.k_dishwasher_door")
COOK = dict(kind="cooktop", state="sensor.k_cooktop_operation_state", timer="number.k_cooktop_alarm_clock")


def case(name, finding, variables, states, say=(), never=()):
    return dict(name=name, finding=finding, variables=variables, states=dict(states),
                say=list(say), never=list(never))


CASES = [
    case("a running oven shows the time left and its progress",
         "2026-11-13: operator asked whether the cards show timers when active",
         OVEN, [st(OVEN["state"], "run"), st(OVEN["finish"], at(42)), st(OVEN["progress"], "40"),
                st(OVEN["temp"], "180"), st(OVEN["door"], "closed")],
         say=["42 min left", "40%"], never=["door closed"]),
    case("more than an hour reads in hours and minutes",
         "'125 min left' is hard to read",
         DISH, [st(DISH["state"], "run"), st(DISH["finish"], at(125)), st(DISH["program"], "eco_50")],
         say=["2 h 5 min left"], never=["125 min"]),
    case("a paused program says so beside the time",
         "a paused program's time does not count down",
         DISH, [st(DISH["state"], "pause"), st(DISH["finish"], at(30))], say=["paused", "30 min left"]),
    case("a delayed start says when it will be done",
         "Home Connect delayedstart",
         DISH, [st(DISH["state"], "delayedstart"), st(DISH["finish"], at(300))],
         say=["starts later", "done 23:00"], never=["%"]),
    case("a finish time already passed never counts below zero",
         "a stale finish stamp must not read '-3 min left'",
         OVEN, [st(OVEN["state"], "run"), st(OVEN["finish"], "2026-11-13T17:57:00+00:00")],
         say=["finishing"], never=["-", "NaN"]),
    case("a running oven with no finish time does not invent one",
         "Home Connect drops the finish time on some programs",
         OVEN, [st(OVEN["state"], "run"), st(OVEN["finish"], "unavailable"), st(OVEN["progress"], "unavailable")],
         never=["min left", "NaN", "unavailable", "%"]),
    case("a kitchen timer shows even with the oven off",
         "2026-11-13: the alarm clock is a kitchen timer, independent of a program",
         OVEN, [st(OVEN["state"], "inactive"), st(OVEN["timer"], "300"), st(OVEN["temp"], "20"),
                st(OVEN["door"], "closed")],
         say=["timer 5 min"]),
    case("the cooktop shows its timer",
         "the cooktop has an alarm clock too",
         COOK, [st(COOK["state"], "run"), st(COOK["timer"], "90")], say=["timer 2 min"]),
    case("a timer at zero says nothing",
         "0 s is 'no timer', not 'timer 0 min'",
         COOK, [st(COOK["state"], "inactive"), st(COOK["timer"], "0")], never=["timer"]),
    case("an idle oven shows its temperature and door",
         "2026-11-13: the operator kept these on the idle card",
         OVEN, [st(OVEN["state"], "inactive"), st(OVEN["temp"], "20"), st(OVEN["door"], "closed")],
         say=["20", "door closed"], never=["min left"]),
    case("an idle dishwasher names its program",
         "2026-11-13: the program is the useful idle detail",
         DISH, [st(DISH["state"], "ready"), st(DISH["program"], "eco_50"), st(DISH["door"], "closed")],
         say=["eco_50", "door closed"]),
]

RUNNER = """
([info, now, cases]) => {
  const fixed = Date.parse(now);
  Date.now = () => fixed;
  return cases.map(c => {
    const variables = Object.assign({}, c.variables);
    const hass = {states: c.states};
    try {
      const f = new Function('states', 'entity', 'user', 'hass', 'variables', 'html', info);
      return {out: String(f(c.states, c.states[c.variables.state] || null, null, hass, variables, null))};
    } catch (e) { return {error: String(e)}; }
  });
}
"""


def main():
    info = load()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(timezone_id="UTC")
        results = page.evaluate(RUNNER, [info, NOW, CASES])
        b.close()
    bad = 0
    for c, r in zip(CASES, results):
        out = r.get("out", "")
        why = ["threw " + r["error"]] if "error" in r else []
        why += ["missing %r" % w for w in c["say"] if w not in out]
        why += ["has %r" % w for w in c["never"] if w in out]
        if why:
            bad += 1
            print("  FAIL  %-58s %s\n        text: %r\n        finding: %s" % (c["name"], "; ".join(why), out, c["finding"]))
        else:
            print("  PASS  %s" % c["name"])
    print("\n%d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
