#!/usr/bin/env python3
"""Give every registry entity a placeholder state, so the dashboard renders as a lived-in house.

    seed.py <url> <config-dir> [states.json]

With a states.json (CI: the synthetic house's, tests/fixtures/synthetic.py), every state is
posted exactly as designed there. Without one (a local run against the real-data fixture),
a stable hash of the entity id picks on/off and where in a plausible range a reading sits.
"""

import hashlib
import io
import json
import os
import sys
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
FIXTURES = os.environ.get("FIXTURE_STORAGE") or sys.exit("set FIXTURE_STORAGE to a fixture's storage dir")
sys.path.insert(0, HERE)
from bootstrap import token  # noqa: E402

# device_class -> (low, high, unit, decimals)
RANGES = {
    "temperature": (18.5, 23.5, "°C", 1), "humidity": (38, 58, "%", 0),
    "carbon_dioxide": (450, 900, "ppm", 0), "illuminance": (20, 400, "lx", 0),
    "battery": (45, 100, "%", 0), "power": (0, 120, "W", 1), "energy": (1, 400, "kWh", 2),
    "voltage": (228, 238, "V", 1), "current": (0, 1, "A", 2), "pm25": (2, 12, "µg/m³", 0),
    "pm10": (3, 15, "µg/m³", 0), "pm1": (1, 8, "µg/m³", 0), "pressure": (1005, 1022, "hPa", 0),
    "atmospheric_pressure": (1005, 1022, "hPa", 0), "volatile_organic_compounds": (50, 250, "µg/m³", 0),
    "volatile_organic_compounds_parts": (50, 250, "ppb", 0), "aqi": (1, 2, None, 0),
    "signal_strength": (-70, -45, "dBm", 0), "sound_pressure": (30, 45, "dB", 0),
    "duration": (0, 60, "min", 0), "monetary": (0, 5, "EUR", 2), "frequency": (49.9, 50.1, "Hz", 2),
}
# Off is the safe, quiet default: a placeholder house with a smoke alarm going off would
# put a false alarm in every screenshot.
QUIET_BINARY = {"moisture", "smoke", "gas", "carbon_monoxide", "safety", "problem", "tamper",
                "battery", "update", "heat", "cold", "vibration", "sound", "door", "window",
                "opening", "lock", "garage_door"}


def h(entity_id, salt=""):
    return int(hashlib.sha256((salt + entity_id).encode()).hexdigest()[:8], 16)


def pick(entity_id, low, high, decimals, salt=""):
    v = low + (h(entity_id, salt) % 1000) / 1000.0 * (high - low)
    return round(v, decimals) if decimals else int(round(v))


def friendly(e, devices):
    own = e.get("name") or e.get("original_name")
    dev = devices.get(e.get("device_id")) or {}
    dname = dev.get("name_by_user") or dev.get("name")
    if e.get("has_entity_name") and dname:
        return "%s %s" % (dname, own) if own else dname
    return own or dname or e["entity_id"].split(".", 1)[1].replace("_", " ").capitalize()


def state_for(e):
    eid = e["entity_id"]
    dom = eid.split(".")[0]
    dc = e.get("device_class") or e.get("original_device_class")
    unit = e.get("unit_of_measurement")
    a = {}
    if dom == "light":
        on = h(eid) % 3 == 0
        a = {"supported_color_modes": ["brightness"], "color_mode": "brightness" if on else None,
             "brightness": 180 if on else None}
        return ("on" if on else "off"), a
    if dom == "input_boolean" and eid.startswith("input_boolean.climate_room_"):
        return ("on" if h(eid) % 5 else "off"), a      # automatic climate: mostly on
    if dom in ("switch", "input_boolean", "fan", "automation"):
        return ("on" if dom == "automation" else "off"), a
    if dom == "binary_sensor":
        if dc in QUIET_BINARY:
            return "off", a
        return ("on" if h(eid) % 4 == 0 else "off"), a
    if dom == "sensor":
        if dc in RANGES:
            low, high, u, dec = RANGES[dc]
            return pick(eid, low, high, dec), {"unit_of_measurement": unit or u, "state_class": "measurement"}
        if unit:
            return pick(eid, 0, 100, 0), {"unit_of_measurement": unit}
        return "none", a
    if dom == "climate":
        cur = pick(eid, 19, 23, 1)
        return ("heat" if h(eid) % 2 else "off"), {
            "hvac_modes": ["off", "heat", "cool", "auto"], "current_temperature": cur,
            "temperature": 21, "min_temp": 7, "max_temp": 30, "target_temp_step": 0.5,
            "hvac_action": "idle", "supported_features": e.get("supported_features") or 385}
    if dom == "input_number":
        if "climate_target_" in eid:
            return (19 if "_night_" in eid else 21), {"min": 16, "max": 26, "step": 1, "mode": "slider",
                                                      "unit_of_measurement": "°C"}
        return 1, {"min": 0, "max": 100, "step": 1, "mode": "slider"}
    if dom == "input_select":
        if eid == "input_select.material_you_spec":
            return "2025", {"options": ["2021", "2025"]}
        return "auto", {"options": ["auto"]}
    if dom == "input_datetime":
        return "2026-01-01 00:00:00", {"has_date": True, "has_time": True, "timestamp": 0}
    if dom == "person":
        return ("home" if h(eid) % 4 else "not_home"), a
    if dom == "weather":
        return "cloudy", {"temperature": 9, "humidity": 78, "temperature_unit": "°C",
                          "pressure": 1016, "pressure_unit": "hPa", "wind_speed": 11,
                          "wind_speed_unit": "km/h", "supported_features": 0}
    if dom == "alarm_control_panel":
        return "disarmed", {"code_arm_required": False, "supported_features": 63}
    if dom == "media_player":
        return "off", a
    if dom == "vacuum":
        return "docked", {"battery_level": 100, "supported_features": 0}
    if dom == "lock":
        return "locked", a
    if dom == "cover":
        return "closed", a
    if dom == "water_heater":
        return "eco", {"temperature": 50, "current_temperature": 48, "min_temp": 30, "max_temp": 65,
                       "operation_list": ["eco", "off"], "operation_mode": "eco"}
    if dom == "number":
        return 1, {"min": 0, "max": 100, "step": 1}
    if dom in ("update", "schedule", "script", "remote", "siren", "valve"):
        return "off", a
    if dom == "counter":
        return 0, a
    return "unknown", a


EXTRA = [
    # Material You reads its seed from a helper; the live seed is the operator's brand blue.
    ("input_text.material_you_base_color", "#1C7ED6", {"friendly_name": "Material You base color"}),
]


def main():
    url, cfg = sys.argv[1], sys.argv[2]
    tok = token(cfg)
    if len(sys.argv) > 3:
        with io.open(sys.argv[3], encoding="utf-8") as fh:
            designed = json.load(fh)
        post(url, tok, [(eid, s["state"], s["attributes"]) for eid, s in sorted(designed.items())]
             + EXTRA)
        return 0
    with io.open(os.path.join(FIXTURES, "core.entity_registry"), encoding="utf-8") as fh:
        ents = json.load(fh)["data"]["entities"]
    with io.open(os.path.join(FIXTURES, "core.device_registry"), encoding="utf-8") as fh:
        devices = {d["id"]: d for d in json.load(fh)["data"]["devices"]}
    rows = []
    for e in ents:
        if e.get("disabled_by"):
            continue
        state, attrs = state_for(e)
        attrs = dict(attrs, friendly_name=friendly(e, devices))
        if e.get("device_class") or e.get("original_device_class"):
            attrs.setdefault("device_class", e.get("device_class") or e.get("original_device_class"))
        if e.get("icon"):
            attrs["icon"] = e["icon"]
        rows.append((e["entity_id"], state, {k: v for k, v in attrs.items() if v is not None}))
    rows.extend(EXTRA)
    post(url, tok, rows)
    return 0


def post(url, tok, rows):
    n = 0
    for eid, state, attrs in rows:
        req = urllib.request.Request(
            url + "/api/states/" + eid, method="POST",
            data=json.dumps({"state": str(state), "attributes": attrs}).encode(),
            headers={"Authorization": "Bearer " + tok, "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
        n += 1
    print("seeded %d states" % n)


if __name__ == "__main__":
    sys.exit(main())
