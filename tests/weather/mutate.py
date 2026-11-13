#!/usr/bin/env python3
"""Confirm the weather_ahead cases detect bugs.

Reads the DEPLOYED macro, applies one plausible bug at a time, inlines the
mutated macro in place of the import, and requires at least one case to fail.
A mutation that every case survives means the suite cannot see that bug.
"""
import io, json, os, sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import run  # noqa: E402
from run import harness, CASES  # noqa: E402

LIVE = os.environ.get("HA_CONFIG", "/usr/share/hassio/homeassistant") + "/custom_templates/weather_ahead.jinja"

MUTATIONS = [
    ("window end inclusive of the next hour", "t < end", "t <= end + timedelta(hours=1)"),
    ("hour in progress dropped", "t + timedelta(hours=1) > now", "t >= now"),
    ("window one hour short", "set end = now + timedelta(hours=hours)", "set end = now + timedelta(hours=hours - 1)"),
    ("rain ranked below fog", "'rainy': 8", "'rainy': 4.5"),
    ("snow ranked below rain", "'snowy': 10", "'snowy': 7.5"),
    ("ties go to the later hour", "if r > ns.best_rank", "if r >= ns.best_rank"),
    ("sleet shown as rain", "'snowy-rainy': 'sleet'", "'snowy-rainy': 'rainy'"),
    ("feels-like takes max", "'feels_min': feels | min", "'feels_min': feels | max"),
    ("wind takes min", "'wind_max': wind | max", "'wind_max': wind | min"),
    ("precip over whole forecast", "'precip': mm | sum", "'precip': (forecast | map(attribute='precipitation') | list) | sum"),
]


def main():
    src = io.open(LIVE, encoding="utf-8").read()
    base = run.build(CASES)
    imp = "{% from 'weather_ahead.jinja' import weather_ahead %}"
    survived = 0
    for label, old, new in MUTATIONS:
        if src.count(old) != 1:
            print("  STALE   %s  (pattern not found once in the live macro)" % label)
            survived += 1
            continue
        tpl = base.replace(imp, src.replace(old, new), 1)
        got = harness.evaluate(tpl)
        if isinstance(got, dict):
            got = got.get("result", json.dumps(got))
        res = [x.strip() for x in str(got).split("@@@")]
        killed = len(res) != len(CASES) or any(r != str(c["expect"]) for c, r in zip(CASES, res))
        survived += not killed
        print("  %s  %s" % ("KILLED " if killed else "SURVIVED", label))
    print("\n%d/%d mutations killed" % (len(MUTATIONS) - survived, len(MUTATIONS)))
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
