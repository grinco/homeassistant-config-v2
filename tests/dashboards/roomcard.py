#!/usr/bin/env python3
"""Run the Home room card's own JavaScript against made-up rooms.

`lint.py` reads the dashboard as data; it cannot tell what the card will SAY.
The room card's status line is JavaScript inside `vg_room_card` (button-card
`[[[ ]]]` templates), so this harness pulls that exact code out of the LIVE
`.storage/lovelace.lovelace` and executes it in headless Chromium - the same
browser `render.py` uses - with a fake `hass` and `states`. The rule from
`tests/climate` holds here too: the test never carries a copy of the logic,
only inputs and an expected outcome.

    python3 tests/dashboards/roomcard.py

A case names the finding it locks down. `say` must all appear in the status
line, `never` must not, and `info` keys must equal what the card resolved.
"""

import io
import json
import os
import sys

STORAGE = os.environ.get("HA_STORAGE", "/usr/share/hassio/homeassistant/.storage")


def js(text):
    text = text.strip()
    if not (text.startswith("[[[") and text.endswith("]]]")):
        raise SystemExit("not a button-card JS template: %r..." % text[:40])
    return text[3:-3]


def load():
    with io.open(os.path.join(STORAGE, "lovelace.lovelace"), encoding="utf-8") as fh:
        t = json.load(fh)["data"]["config"]["button_card_templates"]["vg_room_card"]
    return js(t["variables"]["info"]), js(t["custom_fields"]["status"])


def ent(eid, platform="mqtt", area="room", labels=None):
    return eid, {"entity_id": eid, "platform": platform, "area_id": area, "labels": labels or []}


def st(eid, state, **attrs):
    return eid, {"entity_id": eid, "state": state, "attributes": attrs}


def room(entities, states, special=""):
    return {"entities": dict(entities), "states": dict(states), "special": special}


AC = "climate.room_ac"
ZONE = "climate.room_thermostat"
TRV = "climate.room_trv_room_trv"

CASES = [
    dict(name="a boiler zone that is heating says Heating, even with the AC off",
         finding="2026-10-09: the AC was preferred, so the boiler heating the room was never shown",
         room=room([ent(AC, "smartthings"), ent(ZONE, "tado")],
                   [st(AC, "off"), st(ZONE, "auto", hvac_action="heating")]),
         say=["Heating"], never=["Auto"]),
    dict(name="a boiler zone on its schedule but idle says nothing",
         finding="2026-10-09: a Tado zone is permanently in mode 'auto' - a mode, not an activity",
         room=room([ent(ZONE, "tado")], [st(ZONE, "auto", hvac_action="idle")]),
         never=["Auto", "Heating"]),
    dict(name="an AC with no hvac_action still reports its mode",
         finding="the Samsung units report a mode only; dropping the mode fallback hides them",
         room=room([ent(AC, "smartthings")], [st(AC, "cool")]),
         say=["Cooling"]),
    dict(name="an AC in heat mode next to an idle zone says Heating",
         finding="either device heating the room is enough",
         room=room([ent(ZONE, "tado"), ent(AC, "smartthings")],
                   [st(ZONE, "auto", hvac_action="idle"), st(AC, "heat")]),
         say=["Heating"]),
    dict(name="a radiator valve opening says Heating",
         finding="the bedrooms' TRVs are climate entities with an hvac_action too",
         room=room([ent(TRV, "tado")], [st(TRV, "auto", hvac_action="heating")]),
         say=["Heating"]),
    dict(name="an unavailable climate says nothing",
         finding="an offline unit is not heating",
         room=room([ent(AC, "smartthings")], [st(AC, "unavailable")]),
         never=["Heating", "Cooling", "unavailable"]),
    dict(name="a zone heating while the AC cools says both, as a conflict",
         finding="review 2026-10-09 F3: by design (M6) boiler and AC never fight - if they do, show it",
         room=room([ent(ZONE, "tado"), ent(AC, "smartthings")],
                   [st(ZONE, "auto", hvac_action="heating"), st(AC, "cool")]),
         say=["Heating + cooling"]),
    dict(name="an AC that reports idle while set to cool says nothing",
         finding="review 2026-10-09 F2: a device that reports its action is believed - idle is idle",
         room=room([ent(AC, "smartthings")], [st(AC, "cool", hvac_action="idle")]),
         never=["Cooling", "Auto"]),
    dict(name="a zone preheating says Heating",
         finding="review 2026-10-09 F2: preheating is the boiler running",
         room=room([ent(ZONE, "tado")], [st(ZONE, "auto", hvac_action="preheating")]),
         say=["Heating"]),
    dict(name="the room's light group is the whole room, whichever Magic Areas group comes first",
         finding="review 2026-10-09 F8: C17 matches text; this executes the choice",
         room=room([ent("light.magic_areas_light_groups_room_overhead_lights", "magic_areas"),
                    ent("light.magic_areas_light_groups_room_all_lights", "magic_areas"),
                    ent("light.magic_areas_light_groups_room_task_lights", "magic_areas")],
                   [st("light.magic_areas_light_groups_room_overhead_lights", "off"),
                    st("light.magic_areas_light_groups_room_all_lights", "off"),
                    st("light.magic_areas_light_groups_room_task_lights", "off")]),
         info={"grp": "light.magic_areas_light_groups_room_all_lights"}),
    dict(name="a CO alarm reaches the room card",
         finding="2026-10-09: the corridor got a smoke and CO alarm",
         room=room([ent("binary_sensor.alarm_co")],
                   [st("binary_sensor.alarm_co", "on", device_class="carbon_monoxide")]),
         say=["Carbon monoxide"]),
    dict(name="a smoke alarm reaches the room card",
         finding="2026-10-09: the corridor got a smoke and CO alarm",
         room=room([ent("binary_sensor.alarm_smoke")],
                   [st("binary_sensor.alarm_smoke", "on", device_class="smoke")]),
         say=["Smoke"]),
]

RUNNER = """
([info, status, cases]) => cases.map(c => {
  const hass = {entities: c.room.entities, devices: {}, states: c.room.states};
  const variables = {area: 'room', special: c.room.special};
  const mk = body => new Function('states', 'entity', 'user', 'hass', 'variables', 'html', body);
  try {
    variables.info = mk(info)(c.room.states, null, null, hass, variables, null);
    return {out: mk(status)(c.room.states, null, null, hass, variables, null), info: variables.info};
  } catch (e) { return {error: String(e)}; }
})
"""


def main():
    info, status = load()
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page()
        results = page.evaluate(RUNNER, [info, status, CASES])
        b.close()
    bad = 0
    for c, r in zip(CASES, results):
        out = r.get("out", "")
        why = []
        if "error" in r:
            why.append("threw " + r["error"])
        why += ["missing %r" % w for w in c.get("say", []) if w not in out]
        got = r.get("info") or {}
        why += ["info.%s is %r, not %r" % (k, got.get(k), v) for k, v in c.get("info", {}).items() if got.get(k) != v]
        why += ["has %r" % w for w in c.get("never", []) if w in out]
        if why:
            bad += 1
            print("  FAIL  %-62s %s\n        status: %r\n        finding: %s" % (c["name"], "; ".join(why), out, c["finding"]))
        else:
            print("  PASS  %s" % c["name"])
    print("\n%d/%d passed" % (len(CASES) - bad, len(CASES)))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
