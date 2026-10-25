#!/usr/bin/env python3
"""Stand up a Home Assistant that renders the household dashboard from the committed fixtures.

    bootstrap.py prepare <config-dir>          build the config dir (no network but GitHub)
    bootstrap.py onboard <url> <config-dir>    onboard over the API; writes <config-dir>/ci-token.json
    bootstrap.py verify  <url> <config-dir>    the registry survived start-up, exactly

Design: docs/ci-dashboard-render-design.md, Part 3. Invariant I1 is the reason for most
of what this does NOT do: nothing here fetches data a dashboard would show, so a screenshot
is a function of committed, scanned text and nothing else.
"""

import hashlib
import io
import json
import os
import re
import shutil
import sys
import time
import urllib.error
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
# Which house: CI passes the synthetic one (tests/fixtures/synthetic.py); a local run may
# pass tests/fixtures/real. Required, never defaulted, so the real house is only ever used
# on purpose (review rev 4).
FIXTURES = os.environ.get("FIXTURE_STORAGE") or sys.exit("set FIXTURE_STORAGE to a fixture's storage dir")
CARDS = os.path.join(HERE, "cards.json")
PLACEHOLDER_ENTRY = "fx_ci_fixture"
CLIENT_ID = "http://ci.invalid/"
HACS_RE = re.compile(r"^/hacsfiles/([^/]+)/([^?]+)(?:\?.*)?$")

CONFIGURATION = """\
# Rendering only. Every integration that would fetch data is absent on purpose
# (design invariant I1): no weather, cloud, discovery, alerts or analytics.
homeassistant:
  name: Home
  unit_system: metric
  time_zone: UTC
  latitude: 0
  longitude: 0
  elevation: 0
  currency: EUR
frontend:
  themes: !include_dir_merge_named themes
  extra_module_url:
    - /local/community/material-you-utilities/material-you-utilities.min.js
config:
api:
http:
onboarding:
lovelace:
recorder:
history:
energy:
zone:
system_health:
"""


def _load(name):
    with io.open(os.path.join(FIXTURES, name), encoding="utf-8") as fh:
        return json.load(fh)


def _write(path, doc):
    with io.open(path, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=1)


def _fetch(url, sha256, target):
    with urllib.request.urlopen(url, timeout=60) as r:
        body = r.read()
    got = hashlib.sha256(body).hexdigest()
    if got != sha256:
        raise SystemExit("REFUSING: %s has sha256 %s, cards.json pins %s" % (url, got, sha256))
    os.makedirs(os.path.dirname(target), exist_ok=True)
    with open(target, "wb") as fh:
        fh.write(body)


def prepare(cfg):
    store = os.path.join(cfg, ".storage")
    os.makedirs(store, exist_ok=True)
    with io.open(CARDS, encoding="utf-8") as fh:
        pins = json.load(fh)
    pinned = {(c["dir"], c["file"]) for c in pins["cards"]}

    for name in ("core.area_registry", "core.floor_registry", "core.label_registry",
                 "core.device_registry", "lovelace.lovelace"):
        shutil.copy(os.path.join(FIXTURES, name), os.path.join(store, name))

    # One config entry, of a domain that does not exist: Home Assistant keeps it as "not
    # loaded", so its start-up clean-up keeps every device (and so every entity) that
    # names it. The lint fixture's template entries are left out: they would load and
    # overwrite the seeded states.
    entries = _load("core.config_entries")
    entries["data"]["entries"] = [e for e in entries["data"]["entries"]
                                  if e["entry_id"] == PLACEHOLDER_ENTRY]
    if len(entries["data"]["entries"]) != 1:
        raise SystemExit("the fixture carries no %s entry" % PLACEHOLDER_ENTRY)
    _write(os.path.join(store, "core.config_entries"), entries)
    reg = _load("core.entity_registry")
    for e in reg["data"]["entities"]:
        e["config_entry_id"] = PLACEHOLDER_ENTRY
    _write(os.path.join(store, "core.entity_registry"), reg)

    # Card resources: where HACS would serve them, from files checked against cards.json.
    res = _load("lovelace_resources")
    for item in res["data"]["items"]:
        m = HACS_RE.match(item["url"])
        if not m or (m.group(1), m.group(2)) not in pinned:
            raise SystemExit("REFUSING: resource %s has no pinned, checksummed entry in cards.json"
                             % item["url"])
        item["url"] = "/local/community/%s/%s" % (m.group(1), m.group(2))
    _write(os.path.join(store, "lovelace_resources"), res)
    for c in pins["cards"]:
        _fetch(c["url"], c["sha256"], os.path.join(cfg, "www", "community", c["dir"], c["file"]))
    for t in pins.get("themes", []):
        _fetch(t["url"], t["sha256"], os.path.join(cfg, "themes", t["file"]))

    # The household dashboard is a registered dashboard at /lovelace, not the built-in
    # default (which in 2026.x is Home Assistant's own overview). Only it is registered.
    _write(os.path.join(store, "lovelace_dashboards"), {
        "version": 1, "minor_version": 1, "key": "lovelace_dashboards",
        "data": {"items": [{"id": "lovelace", "icon": "mdi:home-heart", "title": "Home",
                            "url_path": "lovelace", "mode": "storage", "show_in_sidebar": True,
                            "require_admin": False}]}})
    _write(os.path.join(store, "frontend.system_data"), {
        "version": 1, "minor_version": 1, "key": "frontend.system_data",
        "data": {"core": {"default_panel": "lovelace"}}})
    _write(os.path.join(store, "frontend_theme"), {
        "version": 1, "minor_version": 1, "key": "frontend_theme",
        "data": {"frontend_default_theme": "Material You",
                 "frontend_default_dark_theme": "Material You"}})
    with io.open(os.path.join(cfg, "configuration.yaml"), "w", encoding="utf-8") as fh:
        fh.write(CONFIGURATION)
    print("prepared %s: %d entities, %d cards" % (cfg, len(reg["data"]["entities"]), len(pins["cards"])))


def _req(url, data=None, form=False, token=None, method=None):
    headers = {}
    body = None
    if data is not None:
        if form:
            body = "&".join("%s=%s" % (k, urllib.request.quote(str(v), safe="")) for k, v in data.items())
            headers["Content-Type"] = "application/x-www-form-urlencoded"
        else:
            body = json.dumps(data)
            headers["Content-Type"] = "application/json"
        body = body.encode()
    if token:
        headers["Authorization"] = "Bearer " + token
    req = urllib.request.Request(url, data=body, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=30) as r:
        text = r.read().decode()
        return json.loads(text) if text else None


def wait_up(url, seconds=600):
    deadline = time.time() + seconds
    while time.time() < deadline:
        try:
            _req(url + "/api/onboarding")
            return
        except urllib.error.HTTPError:
            return                     # answering, even with an error status
        except Exception:
            time.sleep(3)
    raise SystemExit("Home Assistant did not come up within %d s" % seconds)


def onboard(url, cfg):
    wait_up(url)
    code = _req(url + "/api/onboarding/users", {
        "client_id": CLIENT_ID, "name": "CI", "username": "ci",
        "password": hashlib.sha256(os.urandom(32)).hexdigest(), "language": "en"})["auth_code"]
    tok = _req(url + "/auth/token", {"grant_type": "authorization_code", "code": code,
                                     "client_id": CLIENT_ID}, form=True)
    access = tok["access_token"]
    for step, data in (("core_config", {}), ("analytics", {}),
                       ("integration", {"client_id": CLIENT_ID, "redirect_uri": CLIENT_ID})):
        try:
            _req(url + "/api/onboarding/" + step, data, token=access)
        except urllib.error.HTTPError as e:
            if e.code != 403:          # 403: the step is already done
                raise
    llat = ws(url, access, [{"type": "auth/long_lived_access_token",
                             "client_name": "ci-render", "lifespan": 1}])[0]
    _write(os.path.join(cfg, "ci-token.json"), {"token": llat})
    strip(url, llat)
    print("onboarded; token written to %s" % os.path.join(cfg, "ci-token.json"))


def strip(url, tok):
    """Remove what onboarding set up by itself: sun, shopping list, radio browser, Google
    Translate, analytics, backup, and the onboarding user's person. Two of those reach the
    internet, and none belongs to the fixture (invariant I1); `verify` then demands the
    registry be exactly the fixture's."""
    # Onboarding sets its integrations up in the background, so one pass races them
    # (seen locally: google_translate arrived after the first sweep). Sweep until nothing
    # new has appeared for QUIET seconds.
    QUIET, LIMIT = 15, 180
    removed, quiet_since, deadline = [], time.time(), time.time() + LIMIT
    while time.time() < deadline:
        entries = ws(url, tok, [{"type": "config_entries/get"}])[0]
        extra = [e for e in entries if e["entry_id"] != PLACEHOLDER_ENTRY]
        for e in extra:
            _req(url + "/api/config/config_entries/entry/" + e["entry_id"], token=tok, method="DELETE")
            removed.append(e["domain"])
        if extra:
            quiet_since = time.time()
        elif time.time() - quiet_since >= QUIET:
            break
        time.sleep(3)
    else:
        raise SystemExit("onboarding integrations kept appearing for %d s" % LIMIT)
    people = ws(url, tok, [{"type": "person/list"}])[0]
    ws(url, tok, [{"type": "person/delete", "person_id": p["id"]} for p in people.get("storage", [])])
    print("removed %d onboarding integration(s) (%s) and %d person(s)" % (
        len(removed), ", ".join(sorted(removed)), len(people.get("storage", []))))


def ws(url, token, commands):
    import websocket
    conn = websocket.create_connection(url.replace("http", "ws", 1) + "/api/websocket", timeout=60)
    try:
        json.loads(conn.recv())
        conn.send(json.dumps({"type": "auth", "access_token": token}))
        if json.loads(conn.recv()).get("type") != "auth_ok":
            raise SystemExit("websocket auth failed")
        out = []
        for i, cmd in enumerate(commands, 1):
            conn.send(json.dumps(dict(cmd, id=i)))
            while True:
                msg = json.loads(conn.recv())
                if msg.get("id") == i and msg.get("type") == "result":
                    break
            if not msg.get("success"):
                raise SystemExit("websocket %s failed: %s" % (cmd["type"], msg.get("error")))
            out.append(msg["result"])
        return out
    finally:
        conn.close()


def token(cfg):
    with io.open(os.path.join(cfg, "ci-token.json"), encoding="utf-8") as fh:
        return json.load(fh)["token"]


def verify(url, cfg):
    """Set equality, not a count: a start-up that dropped some entries and created others
    must not pass (review round 1, #2)."""
    ents, devs = ws(url, token(cfg), [{"type": "config/entity_registry/list"},
                                     {"type": "config/device_registry/list"}])
    want_e = {e["entity_id"] for e in _load("core.entity_registry")["data"]["entities"]}
    want_d = {d["id"] for d in _load("core.device_registry")["data"]["devices"]}
    have_e = {e["entity_id"] for e in ents}
    have_d = {d["id"] for d in devs}
    bad = []
    for what, want, have in (("entities", want_e, have_e), ("devices", want_d, have_d)):
        if want - have:
            bad.append("%d %s missing after start-up, e.g. %s" % (
                len(want - have), what, sorted(want - have)[:5]))
        if have - want:
            bad.append("%d %s appeared that the fixture does not have, e.g. %s" % (
                len(have - want), what, sorted(have - want)[:5]))
    if bad:
        print("REGISTRY DID NOT SURVIVE START-UP")
        for b in bad:
            print("  " + b)
        return 1
    print("registry intact: %d entities, %d devices" % (len(have_e), len(have_d)))
    return 0


def main():
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    cmd = sys.argv[1]
    if cmd == "prepare":
        prepare(sys.argv[2])
        return 0
    if cmd == "onboard":
        onboard(sys.argv[2], sys.argv[3])
        return 0
    if cmd == "verify":
        return verify(sys.argv[2], sys.argv[3])
    raise SystemExit(__doc__)


if __name__ == "__main__":
    sys.exit(main())
