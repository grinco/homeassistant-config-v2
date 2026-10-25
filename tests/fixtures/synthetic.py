#!/usr/bin/env python3
"""An invented house for CI to render the dashboard against.

    synthetic.py <out-dir>      writes <out-dir>/storage/ (Home Assistant .storage shape)
                                and <out-dir>/states.json (the state of every entity)

Nothing here comes from the operator's instance. Two floors, two rooms each, one or two
devices per kind, two people, and a calm afternoon: lights mostly off, rooms at target,
nothing to attend to. Small on purpose - it exists to prove the dashboard's GENERATED parts
render (room cards by floor, Comfort, Needs attention, the room-page skeleton), not to
resemble any real home.

The dashboard is assembled from the public exports in lovelace-dashboards/: the Home view
and ONE room-page skeleton (every room page shares it, lint C14), cloned per invented room.
Its person badges and its floor cards' room maps are pointed at the invented house.
tests/fixtures/test_synthetic.py checks the house is complete enough to render.
"""

import copy
import hashlib
import io
import json
import os
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
EXPORTS = os.path.join(REPO, "lovelace-dashboards")
CARDS = os.path.join(REPO, "tests", "render", "cards.json")
T = "2026-01-01T00:00:00+00:00"
ENTRY = "fx_ci_fixture"
SKELETON = "living-room"         # the exported room page cloned for every invented room

FLOORS = [("lower_floor", "Downstairs", "mdi:home-floor-0", 0),
          ("upper_floor", "Upstairs", "mdi:home-floor-1", 1)]
# area id -> (name, floor, icon, page path)
ROOMS = {
    "living_room": ("Living room", "lower_floor", "mdi:sofa-outline", "living-room"),
    "kitchen": ("Kitchen", "lower_floor", "mdi:countertop-outline", "kitchen"),
    "bedroom": ("Bedroom", "upper_floor", "mdi:bed-king-outline", "bedroom"),
    "office": ("Office", "upper_floor", "mdi:desk", "office"),
}
LABELS = ["on_room_page", "not_on_room_pages", "on_home_page", "no_area_needed", "offline_ok"]
PEOPLE = [("person.alex", "Alex", "home"), ("person.sam", "Sam", "not_home")]

# Per room: (light name, on?) ... ; climate unit (if any); readings
ROOM_SPEC = {
    "living_room": {"lights": [("Ceiling", False), ("Floor lamp", True)], "climate": "AC",
                    "temp": 21.4, "hum": 44, "target": (21, 19), "filter": True, "occupied": True},
    "kitchen": {"lights": [("Worktop", False)], "climate": None, "temp": 21.0, "hum": 48},
    "bedroom": {"lights": [("Bedside", False)], "climate": "Radiator", "temp": 19.6, "hum": 50,
                "target": (20, 18), "filter": False},
    "office": {"lights": [("Desk lamp", False)], "climate": None, "temp": 20.8, "hum": 41},
}


def _id(*parts):
    return hashlib.sha256("/".join(parts).encode()).hexdigest()[:32]


class House:
    def __init__(self):
        self.entities, self.devices, self.states = [], [], {}

    def device(self, key, name, area, manufacturer="Synthetic", model="Device", identifiers=None):
        did = _id("device", key)
        self.devices.append({
            "area_id": area, "composite_device_id": None, "composite_primary_config_entry": None,
            "config_entry_id": ENTRY, "config_subentry_id": None, "configuration_url": None,
            "connections": [], "created_at": T, "disabled_by": None, "entry_type": None,
            "has_composite_identifiers": False, "hw_version": None, "id": did,
            "identifiers": identifiers or [["ci_fixture", did]], "labels": [],
            "manufacturer": manufacturer, "model": model, "model_id": None, "modified_at": T,
            "name": name, "name_by_user": None, "primary_config_entry": ENTRY,
            "serial_number": None, "split_at": None, "sw_version": None, "via_device_id": None})
        return did

    def entity(self, eid, name, state, attrs=None, platform="ci_fixture", area=None, device=None,
               device_class=None, unit=None, labels=None, icon=None):
        self.entities.append({
            "aliases": [], "aliases_v2": [], "area_id": area, "capabilities": None,
            "categories": {}, "config_entry_id": ENTRY, "config_subentry_id": None,
            "created_at": T, "device_class": None, "device_id": device, "disabled_by": None,
            "entity_category": None, "entity_id": eid, "has_entity_name": False,
            "hidden_by": None, "icon": icon, "id": _id("entity", eid), "labels": labels or [],
            "modified_at": T, "name": None, "object_id_base": None, "options": {},
            "original_device_class": device_class, "original_icon": None,
            "original_name": name, "platform": platform, "previous_unique_id": None,
            "suggested_object_id": None, "supported_features": (attrs or {}).get("supported_features", 0),
            "translation_key": None, "unique_id": "fx_" + _id("uid", eid)[:16],
            "unit_of_measurement": unit})
        a = dict(attrs or {}, friendly_name=name)
        if device_class:
            a["device_class"] = device_class
        if unit:
            a["unit_of_measurement"] = unit
        if icon:
            a["icon"] = icon
        self.states[eid] = {"state": str(state), "attributes": a}


def build_house():
    h = House()
    for area, (name, floor, _icon, _page) in ROOMS.items():
        spec = ROOM_SPEC[area]
        ma = h.device("ma-" + area, name, area, "Magic Areas", "Magic Area",
                      [["magic_areas", "magic_area_device_" + area]])
        any_on = any(on for _, on in spec["lights"])
        h.entity("light.magic_areas_light_groups_%s_all_lights" % area, "All lights",
                 "on" if any_on else "off",
                 {"supported_color_modes": ["brightness"], "color_mode": "brightness" if any_on else None,
                  "brightness": 150 if any_on else None, "entity_id": []},
                 platform="magic_areas", device=ma)
        h.entity("binary_sensor.magic_areas_presence_tracking_%s_area_state" % area, "Occupancy",
                 "on" if spec.get("occupied") else "off", platform="magic_areas", device=ma,
                 device_class="occupancy")
        for lname, on in spec["lights"]:
            key = lname.lower().replace(" ", "_")
            dev = h.device("light-%s-%s" % (area, key), "%s %s" % (name, lname.lower()), area,
                           model="Bulb")
            h.entity("light.%s_%s" % (area, key), "%s %s" % (name, lname.lower()), "on" if on else "off",
                     {"supported_color_modes": ["brightness"], "color_mode": "brightness" if on else None,
                      "brightness": 150 if on else None}, device=dev)
        sensor_dev = h.device("sensor-" + area, "%s sensor" % name, area, model="Thermometer")
        h.entity("sensor.climate_temp_%s" % area, "%s temperature" % name, spec["temp"],
                 {"state_class": "measurement"}, platform="template", area=area,
                 device_class="temperature", unit="°C", labels=["on_room_page"])
        h.entity("sensor.climate_humidity_%s" % area, "%s humidity" % name, spec["hum"],
                 {"state_class": "measurement"}, platform="template", area=area,
                 device_class="humidity", unit="%", labels=["on_room_page"])
        h.entity("sensor.%s_sensor_battery" % area, "%s sensor battery" % name, 87,
                 device=sensor_dev, device_class="battery", unit="%")
        if spec["climate"]:
            day, night = spec["target"]
            cdev = h.device("climate-" + area, "%s %s" % (name, spec["climate"]), area, model=spec["climate"])
            is_ac = spec["climate"] == "AC"
            h.entity("climate.%s_%s" % (area, "ac" if is_ac else "radiator"), "%s %s" % (name, spec["climate"]),
                     "heat", {"hvac_modes": ["off", "heat"] + (["cool"] if is_ac else []),
                              "current_temperature": spec["temp"], "temperature": day, "min_temp": 7,
                              "max_temp": 30, "target_temp_step": 0.5, "hvac_action": "idle",
                              "supported_features": 385}, device=cdev)
            for kind, value in (("day", day), ("night", night)):
                h.entity("input_number.climate_target_%s_%s" % (kind, area), "%s temperature" % kind.title(),
                         value, {"min": 16, "max": 26, "step": 1, "mode": "slider"}, platform="input_number",
                         area=area, unit="°C", labels=["on_room_page"],
                         icon="mdi:weather-night" if kind == "night" else "mdi:white-balance-sunny")
            h.entity("input_boolean.climate_room_%s" % area, "Automatic climate", "on",
                     platform="input_boolean", area=area, labels=["on_room_page"])
            h.entity("input_boolean.climate_air_filter_%s" % area, "Air filter mode",
                     "on" if spec["filter"] else "off", platform="input_boolean", area=area,
                     labels=["on_room_page"])

    # the house-wide entities the Home view names
    for eid, name, state in PEOPLE:
        h.entity(eid, name, state, platform="person")
    h.entity("weather.home", "Home", "partlycloudy",
             {"temperature": 14, "temperature_unit": "°C", "humidity": 62, "pressure": 1017,
              "pressure_unit": "hPa", "wind_speed": 9, "wind_speed_unit": "km/h", "supported_features": 0},
             platform="weather_ci")
    h.entity("alarm_control_panel.home", "Alarm", "disarmed",
             {"code_arm_required": False, "supported_features": 63}, platform="alarm_ci")
    h.entity("binary_sensor.lighting_night", "Lighting night", "off", platform="template")
    h.entity("binary_sensor.any_safety_alarm", "Any safety alarm", "off", platform="template",
             device_class="safety")
    h.entity("binary_sensor.climate_health_risk", "Climate health risk", "off", platform="template")
    h.entity("sensor.any_low_battery", "Any low battery", "none", platform="template")
    h.entity("sensor.any_safety_sensor_silent", "Any safety sensor silent", "none", platform="template")
    h.entity("sensor.climate_temp_outdoor", "Outdoor temperature", 14.2, {"state_class": "measurement"},
             platform="template", device_class="temperature", unit="°C")
    h.entity("sensor.outside_openweathermap_air_quality_index", "Air quality index", 1,
             platform="aqi_ci", device_class="aqi")
    h.entity("sensor.corridor_xiaomi_air_purifier_filter_life_remaining", "Purifier filter life", 64,
             platform="purifier_ci", unit="%")
    # the room card's own special cases: the kitchen tile reports its appliances, and an
    # outdoor motion sensor adds a line elsewhere (button-card template vg_room_card)
    appl = h.device("kitchen-appliances", "Kitchen appliances", "kitchen", model="Oven")
    h.entity("sensor.house_oven_operation_state", "Oven", "inactive", device=appl)
    h.entity("sensor.house_cooktop_operation_state", "Cooktop", "inactive", device=appl)
    h.entity("binary_sensor.outdoor_motion_occupancy", "Outdoor motion", "off",
             device_class="occupancy")
    h.entity("input_select.material_you_spec", "Material You spec", "2025",
             {"options": ["2021", "2025"]}, platform="input_select")
    return h


def store(key, data, version=1, minor=1):
    return {"version": version, "minor_version": minor, "key": key, "data": data}


def dashboard():
    with io.open(os.path.join(EXPORTS, "home-view.json"), encoding="utf-8") as fh:
        home = json.load(fh)
    with io.open(os.path.join(EXPORTS, "room-views.json"), encoding="utf-8") as fh:
        skel = [v for v in json.load(fh) if v.get("path") == SKELETON][0]
    with io.open(os.path.join(EXPORTS, "button-card-templates.yaml"), encoding="utf-8") as fh:
        templates = yaml.safe_load(fh)["button_card_templates"]

    badge = dict(home["badges"][0]) if home.get("badges") else {"type": "entity", "show_name": True}
    home["badges"] = [dict(badge, entity=eid, name=name) for eid, name, _ in PEOPLE]
    for sec in home.get("sections") or []:
        for c in sec.get("cards") or []:
            if "rooms" in c:
                c["rooms"] = {a: dict({"icon": icon, "name": name, "page": page},
                                      **({"special": "kitchen"} if a == "kitchen" else {}))
                              for a, (name, floor, icon, page) in ROOMS.items() if floor == c.get("floor")}

    # The skeleton names its own room in exactly three forms: area id, path and title.
    s_area, s_path, s_title = "living_room", skel["path"], skel["title"]
    text = json.dumps(skel, ensure_ascii=False)
    for form in (s_area, s_path, s_title):
        if form not in text:
            raise SystemExit("the room skeleton no longer names %r; update synthetic.py" % form)
    rooms = []
    for area, (name, _floor, icon, page) in ROOMS.items():
        t = text.replace('"%s"' % s_area, '"%s"' % area).replace(s_path, page).replace(s_title, name)
        v = json.loads(t)
        v["icon"] = icon
        rooms.append(v)
    return {"button_card_templates": templates, "views": [home] + rooms}


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else os.path.join(HERE, "synthetic")
    st = os.path.join(out, "storage")
    os.makedirs(st, exist_ok=True)
    h = build_house()
    with io.open(CARDS, encoding="utf-8") as fh:
        cards = json.load(fh)["cards"]
    docs = {
        "core.floor_registry": store("core.floor_registry", {"floors": [
            {"aliases": [], "created_at": T, "floor_id": f, "icon": icon, "level": lvl,
             "modified_at": T, "name": name} for f, name, icon, lvl in FLOORS]}, minor=3),
        "core.area_registry": store("core.area_registry", {"areas": [
            {"aliases": [], "created_at": T, "floor_id": floor, "humidity_entity_id": None,
             "icon": icon, "id": a, "labels": [], "modified_at": T, "name": name, "picture": None,
             "temperature_entity_id": None} for a, (name, floor, icon, _p) in ROOMS.items()]}, minor=9),
        "core.label_registry": store("core.label_registry", {"labels": [
            {"color": None, "created_at": T, "description": None, "icon": None, "label_id": lb,
             "modified_at": T, "name": lb.replace("_", " ").capitalize()} for lb in LABELS]}, minor=2),
        "core.device_registry": store("core.device_registry", {
            "devices": h.devices, "child_devices": [], "deleted_devices": []}, version=3, minor=4),
        "core.entity_registry": store("core.entity_registry", {
            "entities": h.entities, "deleted_entities": [], "settings": {"entity_id_parts": None}},
            minor=23),
        "core.config_entries": store("core.config_entries", {"entries": [
            {"created_at": T, "data": {}, "disabled_by": None, "discovery_keys": {},
             "domain": "ci_fixture", "entry_id": ENTRY, "minor_version": 1, "modified_at": T,
             "options": {}, "pref_disable_new_entities": False, "pref_disable_polling": False,
             "source": "user", "subentries": [], "title": "CI fixture", "unique_id": None,
             "version": 2}]}, minor=5),
        "lovelace.lovelace": store("lovelace.lovelace", {"config": dashboard()}),
        "lovelace_resources": store("lovelace_resources", {"items": [
            {"id": _id("res", c["dir"]), "type": "module",
             "url": "/hacsfiles/%s/%s" % (c["dir"], c["file"])} for c in cards]}),
    }
    for name, doc in docs.items():
        with io.open(os.path.join(st, name), "w", encoding="utf-8") as fh:
            json.dump(doc, fh, ensure_ascii=False, indent=1)
    with io.open(os.path.join(out, "states.json"), "w", encoding="utf-8") as fh:
        json.dump(h.states, fh, ensure_ascii=False, indent=1, sort_keys=True)
    print("synthetic house: %d areas, %d devices, %d entities -> %s"
          % (len(ROOMS), len(h.devices), len(h.entities), out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
