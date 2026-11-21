#!/usr/bin/env python3
"""Offline checks on the weather card's cloud strips (tools/weather-scenes/clouds.py).

    python3 tests/weather/test_clouds.py

What it locks down (operator, 2026-11-21: "the clouds seem much lower resolution than the
tower in front of them"):
- the strip has at least 2 pixels per scene pixel. The card shows a 900 px scene about
  354 CSS px wide, so a 3x phone draws it over ~1060 device px. The tower's hard edges
  survive that upscale; soft cloud edges turn to mush;
- cloud edges are crisp: the alpha ramp at a cloud's edge spans at most EDGE_MAX scene px.
  The 1x strips ramped over ~11.5 px, so half of every cloud was semi-transparent fringe;
- the strip still wraps: its last column meets its first as smoothly as any two
  neighbouring columns do, or the drift shows a seam once per loop.
Numbers are measured in scene px, so they hold whatever clouds.SS is.
"""
import os, sys
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "weather-scenes"))
import clouds  # noqa: E402

SCENE = (900, 620)
MIN_SS = 2
EDGE_MAX = 4.0     # scene px
# the scenes.py calls that draw separate clouds (overcast decks have no edges to measure)
OPEN = {
    "partlycloudy-day": dict(cover=0.38, top=(255, 255, 255), under=(150, 158, 176), ymax=0.62, seed=7),
    "partlycloudy-night": dict(cover=0.38, top=(52, 58, 78), under=(82, 74, 80), ymax=0.62, seed=7, density=0.85),
    "windy": dict(cover=0.28, top=(255, 255, 255), under=(150, 158, 176), ymax=0.7, seed=7, stretch=4.0, density=0.85),
}
DECK = dict(cover=1.0, top=(255, 255, 255), under=(155, 158, 161), ymax=1.0, seed=7, stretch=2.4,
            density=220 / 255, lo=2.0, deck=True)


def edge_ramp(alpha, ss):
    """Mean width of the 10..90 % alpha ramp at cloud edges, in scene px."""
    a = alpha / alpha.max()
    part = (a > 0.1) & (a < 0.9)
    gy, gx = np.gradient(a)
    return 0.8 / np.mean(np.hypot(gx, gy)[part]) / ss


def seam(rgba):
    """Wrap-around step against the typical neighbour step, both over all channels."""
    x = rgba.astype(float)
    inner = np.abs(np.diff(x, axis=1)).mean()
    wrap = np.abs(x[:, 0] - x[:, -1]).mean()
    return wrap / inner


def main():
    fails = []
    for name, kw in list(OPEN.items()) + [("overcast", DECK)]:
        s = clouds.strip(SCENE, **kw)
        ss = s.shape[1] / SCENE[0]
        if s.shape[:2] != (SCENE[1] * ss, SCENE[0] * ss):
            fails.append("%s: strip %s is not the scene's shape" % (name, s.shape[:2]))
        if ss < MIN_SS:
            fails.append("%s: %.1f px per scene px, need %d" % (name, ss, MIN_SS))
        if seam(s) > 2.0:
            fails.append("%s: wrap step is %.1fx a neighbour step: the drift shows a seam" % (name, seam(s)))
        if not kw.get("deck"):
            r = edge_ramp(s[..., 3].astype(float), ss)
            if r > EDGE_MAX:
                fails.append("%s: cloud edges fade over %.1f scene px, max %.1f" % (name, r, EDGE_MAX))
    for f in fails:
        print("FAIL", f)
    print("%d strip(s) checked, %d failure(s)" % (len(OPEN) + 1, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
