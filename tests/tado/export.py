#!/usr/bin/env python3
"""Export the Tado hot-water schedule to `automations/hot-water-schedule.json`.

The schedule lives in the Tado app. Home Assistant cannot read or write it (the tado
integration exposes the zone, not its timetable), so without this the repo would only
record what someone remembered to type into the design doc.

Its own login, never Home Assistant's. Tado's refresh tokens ROTATE: every use returns a
new one and invalidates the old. Borrowing the token from Home Assistant's config entry
would leave the integration holding a dead token and silently log it out. So this script
signs in once through Tado's device flow and keeps its own token in `token.local.json`
(gitignored, next to this file).

Read-only, and cheap: four API calls a run (me, zones, active timetable, blocks) against
the account's free-tier budget of about 100 a day, which the radiator automation shares.
Run it after changing the schedule in the app, not on a timer.

    python3 tests/tado/export.py            # first run prints a URL to approve, then exports
    python3 tests/tado/export.py --check    # compare with the committed file, write nothing

Only the schedule is written. `/me` and `/homes` also return the home's address and the
account's e-mail; neither is copied, and the home id stays in the token file.
"""

import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
TOKEN = os.path.join(HERE, "token.local.json")
OUT = os.path.join(REPO, "automations", "hot-water-schedule.json")

# Tado's public client id for its own web app; the device flow is the login Tado
# requires for third-party clients since 2025.
CLIENT_ID = "1bb50063-6b0c-4d11-bd99-387f4a91cc46"
AUTH = "https://login.tado.com/oauth2"
API = "https://my.tado.com/api/v2"

NOTE = (
    "Tado hot-water zone: the active timetable's blocks, as set in the Tado app. Exported by "
    "tests/tado/export.py (its own device login; never Home Assistant's token, which rotates). "
    "Reasoning, usage measurements and the legionella cycle: docs/hot-water.md."
)


def post(url, data):
    req = urllib.request.Request(url, data=urllib.parse.urlencode(data).encode(), method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        return json.load(e)


def get(path, access):
    req = urllib.request.Request(API + path, headers={"Authorization": "Bearer " + access})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def save_token(tok):
    with io.open(TOKEN, "w", encoding="utf-8") as fh:
        json.dump(tok, fh)
    os.chmod(TOKEN, 0o600)


def device_login():
    d = post(AUTH + "/device_authorize", {"client_id": CLIENT_ID, "scope": "offline_access"})
    print("Approve this login in a browser, then wait here:\n  %s" % d["verification_uri_complete"])
    deadline = time.time() + int(d.get("expires_in", 300))
    while time.time() < deadline:
        time.sleep(int(d.get("interval", 5)))
        t = post(AUTH + "/token", {"client_id": CLIENT_ID, "device_code": d["device_code"],
                                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code"})
        if "access_token" in t:
            return t
        if t.get("error") not in ("authorization_pending", "slow_down"):
            raise SystemExit("login failed: %s" % t.get("error"))
    raise SystemExit("login not approved in time")


def access_token():
    tok = None
    if os.path.exists(TOKEN):
        with io.open(TOKEN, encoding="utf-8") as fh:
            tok = json.load(fh)
        t = post(AUTH + "/token", {"client_id": CLIENT_ID, "grant_type": "refresh_token",
                                    "refresh_token": tok["refresh_token"]})
        if "access_token" in t:
            tok.update(t)
            save_token(tok)          # the old refresh token is dead now: keep the new one
            return tok
        print("stored login expired (%s); signing in again" % t.get("error"))
    t = device_login()
    tok = dict(tok or {}, **t)
    save_token(tok)
    return tok


def main():
    check_only = "--check" in sys.argv
    tok = access_token()
    access = tok["access_token"]
    if "home_id" not in tok:
        homes = get("/me", access).get("homes") or []
        if len(homes) != 1:
            raise SystemExit("expected one Tado home, found %d" % len(homes))
        tok["home_id"] = homes[0]["id"]
        save_token(tok)
    home = tok["home_id"]
    zones = [z for z in get("/homes/%s/zones" % home, access) if z.get("type") == "HOT_WATER"]
    if len(zones) != 1:
        raise SystemExit("expected one hot-water zone, found %d" % len(zones))
    zone = zones[0]["id"]
    tt = get("/homes/%s/zones/%s/schedule/activeTimetable" % (home, zone), access)
    blocks = get("/homes/%s/zones/%s/schedule/timetables/%s/blocks" % (home, zone, tt["id"]), access)

    keep = ("dayType", "start", "end", "geolocationOverride", "setting")
    body = json.dumps({"note": NOTE, "timetable": tt.get("type"),
                       "blocks": [{k: b[k] for k in keep if k in b} for b in blocks]},
                      ensure_ascii=False, indent=1) + "\n"
    if check_only:
        existing = io.open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if existing != body:
            print("automations/hot-water-schedule.json differs from the Tado app")
            return 1
        print("hot-water schedule matches the Tado app")
        return 0
    with io.open(OUT, "w", encoding="utf-8") as fh:
        fh.write(body)
    print("wrote automations/hot-water-schedule.json (%d blocks, %s)" % (len(blocks), tt.get("type")))
    return 0


if __name__ == "__main__":
    sys.exit(main())
