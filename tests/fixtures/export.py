"""Build tests/fixtures/real (LOCAL ONLY, gitignored): the live stores, cut down to an
allowlist and anonymised, for running the render pipeline against the real house.
CI never sees it; it renders the invented house in synthetic.py.

Called by `tests/dashboards/export.py`, which owns the substitution map and its canary
and leak checks; this module only decides WHAT is kept. The design and the reasons
are in docs/ci-dashboard-render-design.md (Part 1).

A field outside the allowlist is reset to the empty value of its type, not scrubbed:
MAC addresses, serial numbers, device web UIs, cloud ids inside unique ids and
integration credentials are not names, so the substitution map would never catch
them. `tests/fixtures/check.py` is the test that holds this module to that.
"""

import hashlib
import io
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
# Local only (gitignored): the real house, for running the render pipeline against it on
# the operator's machine. CI renders the synthetic house instead (synthetic.py).
OUT = os.path.join(HERE, "real")

STORES = ("core.entity_registry", "core.device_registry", "core.area_registry",
          "core.floor_registry", "core.label_registry", "core.config_entries",
          "lovelace.lovelace", "lovelace_resources")

FIXED_TIME = "2026-01-01T00:00:00+00:00"
# Every device, and every entity whose own entry is not kept, points here. Home Assistant
# keeps an entry whose integration does not exist (it shows as "not loaded"), and its
# start-up clean-up removes a device whose entry it does not know - and with it the
# device's entities. See the design, Part 3.
PLACEHOLDER_ENTRY = "fx_ci_fixture"

ENTITY_KEEP = ("entity_id", "id", "area_id", "device_id", "labels", "platform", "device_class",
               "original_device_class", "entity_category", "hidden_by", "disabled_by", "name",
               "original_name", "icon", "original_icon", "unit_of_measurement", "has_entity_name",
               "translation_key", "supported_features", "object_id_base", "suggested_object_id")
DEVICE_KEEP = ("id", "area_id", "labels", "name", "name_by_user", "manufacturer", "model",
               "via_device_id", "entry_type", "disabled_by")
ENTRY_DOMAINS = ("template", "magic_areas", "min_max", "group")
ENTRY_DATA_KEEP = {"magic_areas": ("id", "name")}
ENTRY_OPTIONS_KEEP = {"template": ("state", "name", "template_type", "device_class",
                                   "unit_of_measurement", "state_class"),
                      "min_max": ("entity_ids", "name", "type", "round_digits"),
                      "group": ("entities", "name", "group_type", "hide_members", "all")}
NAME_FIELDS = ("name", "original_name", "name_by_user")
# Hardware addresses and accounts that people (and integrations) put into NAMES: Bluetooth
# proxies carry their MAC, an unplaced Zigbee device its IEEE address, a cloud account its
# e-mail. Masked in names and ids; tests/fixtures/check.py fails if one gets through.
MASKS = (
    (re.compile(r"(?i)(?<![0-9a-f])(?:[0-9a-f]{2}[:-]){5}[0-9a-f]{2}(?![0-9a-f])"), "mac"),
    (re.compile(r"(?i)\b0x[0-9a-f]{16}\b"), "ieee"),
    (re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"), "account"),
)
ID_FIELDS = ("entity_id", "suggested_object_id", "object_id_base")


def _h(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


def _empty(value):
    if isinstance(value, bool):
        return False
    if isinstance(value, list):
        return []
    if isinstance(value, dict):
        return {}
    return None


def _mask(value):
    if not isinstance(value, str):
        return value
    for rx, word in MASKS:
        value = rx.sub(lambda m: "%s_%s" % (word, _h(m.group(0))[:8]), value)
    return value


def _masked(item):
    for f in NAME_FIELDS + ID_FIELDS:
        if f in item:
            item[f] = _mask(item[f])
    return item


def _cut(item, keep):
    out = {}
    for k, v in item.items():
        out[k] = v if k in keep else _empty(v)
    return out


def _load(storage, name):
    with io.open(os.path.join(storage, name), encoding="utf-8") as fh:
        return json.load(fh)


def build(storage):
    """name -> store document, allowlisted but NOT yet anonymised."""
    docs = {n: _load(storage, n) for n in STORES}

    entries = docs["core.config_entries"]["data"]["entries"]
    kept_ids = {}
    new_entries = []
    for en in entries:
        if en.get("domain") not in ENTRY_DOMAINS:
            continue
        fid = "fx_" + _h(en["entry_id"])
        kept_ids[en["entry_id"]] = fid
        cut = _cut(en, ("domain", "title", "version", "minor_version", "source"))
        cut["entry_id"] = fid
        cut["created_at"] = cut["modified_at"] = FIXED_TIME
        dom = en["domain"]
        cut["data"] = {k: v for k, v in (en.get("data") or {}).items()
                       if k in ENTRY_DATA_KEEP.get(dom, ())}
        cut["options"] = {k: v for k, v in (en.get("options") or {}).items()
                          if k in ENTRY_OPTIONS_KEEP.get(dom, ())}
        new_entries.append(cut)
    placeholder = _cut(new_entries[0], ("version", "minor_version"))
    placeholder.update(entry_id=PLACEHOLDER_ENTRY, domain="ci_fixture", title="CI fixture",
                       source="user", created_at=FIXED_TIME, modified_at=FIXED_TIME,
                       data={}, options={})
    new_entries.append(placeholder)
    docs["core.config_entries"]["data"]["entries"] = sorted(new_entries, key=lambda e: e["entry_id"])

    ents = []
    for e in docs["core.entity_registry"]["data"]["entities"]:
        cut = _cut(e, ENTITY_KEEP)
        cut["unique_id"] = "fx_" + _h(e["entity_id"])
        cut["config_entry_id"] = kept_ids.get(e.get("config_entry_id"), PLACEHOLDER_ENTRY)
        cut["created_at"] = cut["modified_at"] = FIXED_TIME
        ents.append(_masked(cut))
    reg = docs["core.entity_registry"]["data"]
    reg["entities"] = sorted(ents, key=lambda e: e["entity_id"])
    reg["deleted_entities"] = []
    reg["settings"] = _cut(reg.get("settings") or {}, ())   # keys must stay: the loader reads them

    devs = []
    for d in docs["core.device_registry"]["data"]["devices"]:
        cut = _cut(d, DEVICE_KEEP)
        ma = [i for i in (d.get("identifiers") or []) if i and i[0] == "magic_areas"]
        cut["identifiers"] = ma or [["ci_fixture", d["id"]]]
        cut["config_entry_id"] = cut["primary_config_entry"] = PLACEHOLDER_ENTRY
        cut["created_at"] = cut["modified_at"] = FIXED_TIME
        devs.append(_masked(cut))
    dreg = docs["core.device_registry"]["data"]
    dreg["devices"] = sorted(devs, key=lambda d: d["id"])
    dreg["deleted_devices"] = []
    dreg["child_devices"] = []

    for store, key in (("core.area_registry", "areas"), ("core.floor_registry", "floors"),
                       ("core.label_registry", "labels")):
        for item in docs[store]["data"][key]:
            for t in ("created_at", "modified_at"):
                if t in item:
                    item[t] = FIXED_TIME
            if "picture" in item:
                item["picture"] = None
    return docs


def dumps(doc):
    """One registry item per line: readable diffs without a 2 MB pretty-print."""
    head = {k: v for k, v in doc.items() if k != "data"}
    lines = ["{"]
    for k, v in head.items():
        lines.append(" %s: %s," % (json.dumps(k), json.dumps(v, ensure_ascii=False)))
    lines.append(' "data": {')
    items = list(doc["data"].items())
    for i, (k, v) in enumerate(items):
        sep = "," if i < len(items) - 1 else ""
        if isinstance(v, list) and v and all(isinstance(x, dict) for x in v):
            lines.append("  %s: [" % json.dumps(k))
            lines.append(",\n".join("   " + json.dumps(x, ensure_ascii=False, sort_keys=True)
                                    for x in v))
            lines.append("  ]" + sep)
        else:
            lines.append("  %s: %s%s" % (json.dumps(k), json.dumps(v, ensure_ascii=False,
                                                                 sort_keys=True), sep))
    lines.append(" }")
    lines.append("}")
    return "\n".join(lines) + "\n"


WORD_RE = re.compile(r"[^\W\d_]{2,}", re.UNICODE)


def vocabulary(docs):
    """Every word of every person-facing name in the fixture, lower-cased."""
    words = set()
    for store, key in (("core.entity_registry", "entities"), ("core.device_registry", "devices"),
                       ("core.area_registry", "areas"), ("core.floor_registry", "floors"),
                       ("core.label_registry", "labels")):
        for item in docs.get(store, {}).get("data", {}).get(key, []):
            for f in NAME_FIELDS:
                if isinstance(item.get(f), str):
                    words.update(w.lower() for w in WORD_RE.findall(item[f]))
    return words


def committed_vocabulary():
    docs = {}
    for n in STORES:
        p = os.path.join(OUT, n)
        if os.path.exists(p):
            with io.open(p, encoding="utf-8") as fh:
                docs[n] = json.load(fh)
    return vocabulary(docs) if docs else None
