#!/usr/bin/env python3
"""Run the weather_ahead cases against the macro DEPLOYED in Home Assistant.

    python3 tests/weather/run.py

Each case calls the live macro with a literal forecast, so this tests what runs,
not a copy. Uses the climate suite's transport (HA_TOKEN, tests/climate/.ha_token,
or the local ha-mcp server). Exit 0 = pass, 1 = failures, 2 = could not run.
"""
import json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "climate"))
sys.path.insert(0, HERE)
import harness  # noqa: E402
from cases import CASES, NOW  # noqa: E402

SEP = "\n@@@\n"


def build(cases):
    parts = ["{% from 'weather_ahead.jinja' import weather_ahead %}"]
    for c in cases:
        parts.append("{%% set r = weather_ahead(%s, %s) | from_json %%}{{ r.get(%s) }}"
                     % (json.dumps(c["forecast"]), json.dumps(c.get("now", NOW)),
                        json.dumps(c["field"])))
    return parts[0] + SEP.join(parts[1:])


def main():
    try:
        got = harness.evaluate(build(CASES))
    except RuntimeError as exc:
        print("SUITE ERROR: %s" % exc, file=sys.stderr)
        return 2
    if isinstance(got, dict):
        got = got.get("result", json.dumps(got))
    if '"success": false' in str(got) or str(got).lstrip().startswith("{%"):
        err = str(got)
        try:
            err = json.loads(err)["error"]["message"]
        except (ValueError, KeyError, TypeError):
            err = err[:400]
        print("SUITE ERROR: the template did not render: %s" % err, file=sys.stderr)
        return 2
    res = [x.strip() for x in str(got).split("@@@")]
    if len(res) != len(CASES):
        print("SUITE ERROR: expected %d results, got %d:\n%s" % (len(CASES), len(res), got),
              file=sys.stderr)
        return 2
    fails = 0
    w = max(len(c["name"]) for c in CASES)
    for c, r in zip(CASES, res):
        ok = r == str(c["expect"])
        fails += not ok
        print("  %s  %-*s  %s" % ("PASS" if ok else "FAIL", w, c["name"],
                                  "" if ok else "expected %r, got %r  [%s]"
                                  % (str(c["expect"]), r, c.get("finding", ""))))
    print("\n%d/%d passed" % (len(CASES) - fails, len(CASES)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
