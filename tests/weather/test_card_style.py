#!/usr/bin/env python3
"""Offline checks on the animated weather card's generated CSS (tools/weather-scenes/card_style.py).

No Home Assistant needed, so CI can run it:

    python3 tests/weather/test_card_style.py

What it locks down (review 2026-11-12):
- every rain layer moves on the 1:4 slant the tiles are drawn with (scenes.py rain_tile),
  and every layer's shift per loop is a whole number of tiles, so no loop shows a seam;
- in every scene and keyframe stop, background-position has exactly one entry per
  background-image layer, so no layer silently takes another's position;
- the reduced-motion override keeps the same number of layers, swapping only the glass.
- day or night follows sun.sun at render time, in both directions (why: docs/weather-ahead.md).
  The render is plain Jinja with a fake `states`; it checks which picture and headline the
  template picks, not card-mod's re-rendering, and it compares strings, not HA's native types.
"""
import os, re, sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "weather-scenes"))
import card_style  # noqa: E402

RAIN_SLANT = 0.25   # scenes.py rain_tile draws (x + L*0.25, y + L)


def split_layers(value):
    """Split a CSS list on top-level commas (not the ones inside url(...) or gradients)."""
    out, depth, cur = [], 0, ""
    for ch in value:
        depth += ch == "("
        depth -= ch == ")"
        if ch == "," and depth == 0:
            out.append(cur.strip()); cur = ""
        else:
            cur += ch
    return out + [cur.strip()] if cur.strip() else out


class _States:
    """Just enough of Home Assistant's `states` for the style's Jinja: callable and dotted."""
    def __init__(self, st):
        self._st = st
    def __call__(self, eid):
        return self._st.get(eid, {}).get("state", "unknown")
    def __getattr__(self, domain):
        class _D:
            def __getattr__(_, obj):
                e = self._st.get(domain + "." + obj)
                return type("S", (), e) if e else None
        return _D()


def render_style(sun, sensor_state="sunny", sensor_attrs=None):
    import jinja2
    st = {"sun.sun": {"state": sun, "attributes": {}},
          "sensor.weather_ahead": {"state": sensor_state,
                                   "attributes": dict({"scene": sensor_state}, **(sensor_attrs or {}))}}
    env = jinja2.Environment()
    env.globals.update(states=_States(st), is_state=lambda e, v: st.get(e, {}).get("state") == v)
    return env.from_string(card_style.style()).render()


def day_night(fails):
    # Straddle sunset both ways: the sensor's attributes say one thing, the sun the other.
    for sun, stale, want, wrong in (("below_horizon", True, "-night-", "-day-"),
                                    ("above_horizon", False, "-day-", "-night-")):
        out = render_style(sun, sensor_attrs={"daytime": stale})
        if want + "back" not in out or wrong + "back" in out:
            fails.append("sun %s, sensor daytime %s: card does not show %s" % (sun, stale, want.strip("-")))
    # Sensor unavailable (no forecast): cloudy picture, no headline swap (review 2026-11-13).
    out = render_style("above_horizon", sensor_state="unavailable", sensor_attrs={"scene": None})
    if "cloudy-day-back" not in out or "Next 3 h" in out:
        fails.append("sensor unavailable: not the cloudy picture without a headline")
    # The forecast keeps 'sunny' for an hour that started before sunset: after dark say clear.
    for sun, want in (("below_horizon", "Next 3 h: clear'"), ("above_horizon", "Next 3 h: sunny'")):
        if want not in render_style(sun, sensor_state="sunny"):
            fails.append("sun %s, forecast sunny: headline is not %s" % (sun, want.rstrip("'")))


def main():
    fails = []
    day_night(fails)
    for scene, (drift, loop, layers) in card_style.SCENES.items():
        for name, (dx, dy, sway) in layers:
            if not (float(dx).is_integer() and float(dy).is_integer()):
                fails.append("%s/%s: shift (%s, %s) is not whole tiles" % (scene, name, dx, dy))
            if name.startswith("rain") and dx / dy != RAIN_SLANT:
                fails.append("%s/%s: moves on slant %s, tiles are drawn on %s" % (scene, name, dx / dy, RAIN_SLANT))
            if name.startswith("wind") and dy != 0:
                fails.append("%s/%s: wind moves vertically" % (scene, name))
        css = card_style.css(scene)
        after = re.search(r"ha-card::after \{[^}]*\}", css).group(0)
        n = len(split_layers(re.search(r"background-image: ([^;]*);", after).group(1)))
        for what in ("background-size", "background-repeat", "background-position"):
            got = len(split_layers(re.search(what + r": ([^;]*);", after).group(1)))
            if got != n:
                fails.append("%s: %s has %d entries for %d layers" % (scene, what, got, n))
        for stop in re.findall(r"\d+% \{ background-position: ([^;]*); \}", css):
            if len(split_layers(stop)) != n:
                fails.append("%s: a keyframe stop has %d positions for %d layers" % (scene, len(split_layers(stop)), n))
        if layers and not re.search(r"@keyframes wx-fall-%s " % scene, css):
            fails.append("%s: layers move but there are no keyframes" % scene)
        rm = re.search(r"@media \(prefers-reduced-motion: reduce\) \{ ha-card::after \{ background-image: ([^;]*);", css)
        if rm and len(split_layers(rm.group(1))) != n:
            fails.append("%s: reduced-motion override has %d layers, not %d" % (scene, len(split_layers(rm.group(1))), n))
        if card_style.GLASS.get(scene) and not rm:
            fails.append("%s: glass loop has no reduced-motion still" % scene)
    for f in fails:
        print("FAIL", f)
    print("%d scene(s) checked, %d failure(s)" % (len(card_style.SCENES), len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
