#!/usr/bin/env python3
"""The local real-house fixture (tests/fixtures/real, gitignored) holds only what the renderer needs.

They are a copy of the live registries, and the live registries know a great deal a
public repo must not: MAC addresses, Zigbee IEEE addresses, serial numbers, device web
UIs on the LAN, cloud account ids inside unique ids, credentials inside config entries.
`export.py` keeps an ALLOWLIST of fields and resets the rest. This check is the other
half: it fails on any value that looks like one of those, and on any field outside the
allowlist that holds anything but its empty default. Child names and the address are
`leakcheck.py`'s job; it scans these files like every other tracked file.

    python3 tests/fixtures/check.py              # check the committed fixtures
    python3 tests/fixtures/check.py --self-test  # plant each leak, expect red
"""

import copy
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
STORE = os.environ.get("FIXTURE_STORAGE", os.path.join(HERE, "real"))

PATTERNS = {
    "MAC address": re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"),
    "IEEE address": re.compile(r"(?i)\b0x[0-9a-f]{16}\b"),
    "IPv4 address": re.compile(r"(?<![\d.])(?:\d{1,3}\.){3}\d{1,3}(?![\d.])"),
    "URL": re.compile(r"(?i)\b(?:https?|wss?|rtsp)://"),
    "e-mail address": re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
}
# Card resources are URLs by nature, and local paths, not hosts.
URL_OK_FILES = {"lovelace_resources"}

# Per store: the fields that may hold a value. Everything else must be empty.
ENTITY_KEEP = {"entity_id", "id", "area_id", "device_id", "labels", "platform", "device_class",
               "original_device_class", "entity_category", "hidden_by", "disabled_by", "name",
               "original_name", "icon", "original_icon", "unit_of_measurement", "has_entity_name",
               "translation_key", "supported_features", "config_entry_id", "unique_id",
               "created_at", "modified_at", "object_id_base", "suggested_object_id"}
DEVICE_KEEP = {"id", "area_id", "labels", "name", "name_by_user", "manufacturer", "model",
               "via_device_id", "identifiers", "config_entry_id", "primary_config_entry",
               "created_at", "modified_at", "entry_type", "disabled_by"}
ENTRY_KEEP = {"entry_id", "domain", "title", "data", "options", "version", "minor_version",
              "source", "created_at", "modified_at"}
ENTRY_DOMAINS = {"template", "magic_areas", "min_max", "group", "ci_fixture"}
ENTRY_DATA_KEEP = {"magic_areas": {"id", "name"}}
ENTRY_OPTIONS_KEEP = {"template": {"state", "name", "template_type", "device_class",
                                   "unit_of_measurement", "state_class"},
                      "min_max": {"entity_ids", "name", "type", "round_digits"},
                      "group": {"entities", "name", "group_type", "hide_members", "all"}}
UNIQUE_RE = re.compile(r"^fx_[0-9a-f]{16}$")
# The only stores a fixture may hold. Anything else - the admin panel above all, with its
# Wi-Fi names, firewall rules and VPN routes - must not ride along unnoticed.
EXPECTED_FILES = {"core.entity_registry", "core.device_registry", "core.area_registry",
                  "core.floor_registry", "core.label_registry", "core.config_entries",
                  "lovelace.lovelace", "lovelace_resources"}
EMPTY = (None, "", [], {}, False, 0)


def load(name):
    with io.open(os.path.join(STORE, name), encoding="utf-8") as fh:
        return json.load(fh)


def walk(node, path=""):
    if isinstance(node, dict):
        for k, v in node.items():
            yield from walk(v, "%s.%s" % (path, k))
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, "%s[%d]" % (path, i))
    elif isinstance(node, str):
        yield path, node


def check(docs):
    """docs: file name -> parsed JSON. Returns a list of problems."""
    bad = ["unexpected store in the fixtures: %s" % n for n in sorted(set(docs) - EXPECTED_FILES)]
    bad += ["missing store in the fixtures: %s" % n for n in sorted(EXPECTED_FILES - set(docs))]
    for name, doc in docs.items():
        for path, s in walk(doc):
            for what, rx in PATTERNS.items():
                if what == "URL" and name in URL_OK_FILES:
                    continue
                if rx.search(s):
                    bad.append("%s%s: %s %r" % (name, path, what, s[:80]))

    for e in docs.get("core.entity_registry", {}).get("data", {}).get("entities", []):
        for k, v in e.items():
            if k not in ENTITY_KEEP and v not in EMPTY:
                bad.append("entity %s: %s is not allowlisted but holds %r" % (e.get("entity_id"), k, v))
        if not UNIQUE_RE.match(str(e.get("unique_id"))):
            bad.append("entity %s: unique_id %r is not an opaque fixture id" % (e.get("entity_id"), e.get("unique_id")))

    for d in docs.get("core.device_registry", {}).get("data", {}).get("devices", []):
        for k, v in d.items():
            if k not in DEVICE_KEEP and v not in EMPTY:
                bad.append("device %s: %s is not allowlisted but holds %r" % (d.get("id"), k, v))
        for ident in d.get("identifiers") or []:
            if ident[0] not in ("magic_areas", "ci_fixture"):
                bad.append("device %s: identifier %r" % (d.get("id"), ident))

    for en in docs.get("core.config_entries", {}).get("data", {}).get("entries", []):
        dom = en.get("domain")
        if dom not in ENTRY_DOMAINS:
            bad.append("config entry of domain %r" % dom)
            continue
        for k, v in en.items():
            if k not in ENTRY_KEEP and v not in EMPTY:
                bad.append("config entry %s: %s holds %r" % (dom, k, v))
        for k in (en.get("data") or {}):
            if k not in ENTRY_DATA_KEEP.get(dom, set()):
                bad.append("config entry %s: data.%s" % (dom, k))
        for k in (en.get("options") or {}):
            if k not in ENTRY_OPTIONS_KEEP.get(dom, set()):
                bad.append("config entry %s: options.%s" % (dom, k))
    return bad


def load_all():
    return {n: load(n) for n in sorted(os.listdir(STORE))}


# Each plants one thing a real registry holds and the fixture must not.
def _ent(docs):
    return docs["core.entity_registry"]["data"]["entities"][0]


def _dev(docs):
    return docs["core.device_registry"]["data"]["devices"][0]


PLANTS = [
    ("the admin panel rides along",
     lambda d: d.update({"lovelace.admin_panel": {"data": {"config": {"views": []}}}})),
    ("a device MAC in connections", lambda d: _dev(d).update(connections=[["mac", "a4:c1:38:12:34:56"]])),
    ("a Zigbee IEEE identifier", lambda d: _dev(d).update(identifiers=[["mqtt", "zigbee2mqtt_0x00158d0001a2b3c4"]])),
    ("a serial number", lambda d: _dev(d).update(serial_number="SN12345678")),
    ("a device web UI on the LAN", lambda d: _dev(d).update(configuration_url="http://192.168.2.40")),
    ("a cloud id in unique_id", lambda d: _ent(d).update(unique_id="tuya.bf1234567890abcdef")),
    ("entity options", lambda d: _ent(d).update(options={"sensor": {"display_precision": 1}})),
    ("an alias", lambda d: _ent(d).update(aliases=["the big lamp"])),
    ("an IP in a name", lambda d: _ent(d).update(name="Camera 10.0.0.7")),
    ("an e-mail in a name", lambda d: _ent(d).update(name="someone@example.com")),
    ("a credential in a config entry",
     lambda d: d["core.config_entries"]["data"]["entries"].append(
         {"entry_id": "x", "domain": "template", "data": {"token": "abc"}, "options": {}})),
    ("an integration's config entry",
     lambda d: d["core.config_entries"]["data"]["entries"].append(
         {"entry_id": "y", "domain": "unifi", "data": {}, "options": {}})),
]


def self_test():
    base = load_all()
    if check(base):
        print("REFUSING: the committed fixtures already fail; fix them first")
        return 2
    missed = 0
    for what, plant in PLANTS:
        docs = copy.deepcopy(base)
        plant(docs)
        if check(docs):
            print("  caught    %s" % what)
        else:
            print("  SURVIVED  %s" % what)
            missed += 1
    print("")
    if missed:
        print("%d plant(s) not caught" % missed)
        return 1
    print("all %d plants caught" % len(PLANTS))
    return 0


def main():
    if "--self-test" in sys.argv:
        return self_test()
    if not os.path.isdir(STORE):
        print("no fixtures at %s" % STORE)
        return 1
    bad = check(load_all())
    if bad:
        print("%d problem(s) in the fixtures\n" % len(bad))
        for b in bad[:40]:
            print("  " + b)
        return 1
    print("fixtures clean: allowlisted fields only, no address, serial, URL or e-mail")
    return 0


if __name__ == "__main__":
    sys.exit(main())
