#!/usr/bin/env python3
"""Offline checks on the weather card's cloud strips (tools/weather-scenes/clouds.py).

    python3 tests/weather/test_clouds.py

What it locks down (operator, 2026-11-21: "the clouds seem much lower resolution than the
tower in front of them"):
- the strip has at least 2 pixels per scene pixel. The card shows a 900 px scene about
  354 CSS px wide, so a 3x phone draws it over ~1060 device px. The tower's hard edges
  survive that upscale; soft cloud edges turn to mush;
- cloud edges are crisp: the alpha ramp at a cloud's edge spans at most EDGE_MAX scene px
  on average over the strip (a mean, so one soft edge among crisp ones can hide).
  The 1x strips ramped over ~11.5 px, so half of every cloud was semi-transparent fringe;
- the strip still wraps: its last column meets its first as smoothly as any two
  neighbouring columns do, or the drift shows a seam once per loop.
- the clouds read as sharp as the tower, which the edges alone did not achieve (operator,
  2026-11-21, after the 2x strips: "I don't see the change"). A 3x screenshot showed the
  real causes: lit tops never got near white (tonal range 60-127 against the tower's
  40-212), the inside of a cloud had a quarter of the tower's fine detail, and the cloud
  shapes were stretched sideways about 2.3:1, which is exactly what an upscaled, stretched
  image looks like. So, on fully opaque cloud by day: the brightest tops reach TOP_MIN,
  the bright-to-dark spread is at least SPREAD_MIN and the fine detail within DETAIL
  (two-sided: too much reads as sand, not as sharpness); and the partly cloudy shapes (alpha, so the top light does not count) have
  horizontal/vertical edge detail within ANISO. The vertical thinning towards ymax adds
  some vertical edge on its own, so round clouds measure a little under 1;
- the strip costs at most KB_MAX once encoded, so the bigger texture does not cost load
  time (a 3x phone needs ~1060 px for the 900 px scene: SS ~1.2, not 2).
Numbers are measured in scene px, so they hold whatever clouds.SS is.
"""
import io, os, sys
import numpy as np
from PIL import Image

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "weather-scenes"))
import clouds  # noqa: E402

SCENE = (900, 620)
MIN_SS = 1.18      # 354 CSS px x 3 / 900
EDGE_MAX = 4.0     # scene px
TOP_MIN = 240      # luminance of the brightest 5 % of lit cloud, day
SPREAD_MIN = 70    # p95 - p5 luminance inside the cloud, day
DETAIL = (6.0, 15.0)  # mean |Laplacian| of luminance at scene scale, inside the cloud, day.
# Old flat clouds: 3.0. Above ~15 it is no longer billows but sand: versions at 16-27
# were rejected on sight while tuning (2026-11-21).
ANISO = (0.8, 1.25)  # horizontal / vertical alpha edge, partly cloudy (windy and decks are streaky on purpose)
KB_MAX = 250
# the scenes.py calls that draw separate clouds (overcast decks have no edges to measure)
OPEN = {
    "partlycloudy-day": dict(cover=0.38, top=(255, 255, 255), under=(150, 158, 176), ymax=0.62, seed=7),
    "partlycloudy-night": dict(cover=0.38, top=(52, 58, 78), under=(82, 74, 80), ymax=0.62, seed=7, density=0.85),
    "windy": dict(cover=0.28, top=(255, 255, 255), under=(150, 158, 176), ymax=0.7, seed=7, stretch=5.8, density=0.85),
}
DECK = dict(cover=1.0, top=(255, 255, 255), under=(155, 158, 161), ymax=1.0, seed=7, stretch=3.5,
            density=220 / 255, lo=2.0, deck=True)


def edge_ramp(alpha, ss):
    """Mean width of the 10..90 % alpha ramp at cloud edges, in scene px."""
    a = alpha / alpha.max()
    part = (a > 0.1) & (a < 0.9)
    gy, gx = np.gradient(a)
    return 0.8 / np.mean(np.hypot(gx, gy)[part]) / ss


def look(rgba, ss):
    """Luminance stats inside the cloud core (alpha at 95 % of its maximum), at scene scale."""
    a = rgba[..., 3].astype(float); core = a >= 0.95 * a.max()
    lum = rgba[..., :3].astype(float) @ [0.299, 0.587, 0.114]
    sc = np.asarray(Image.fromarray(lum.clip(0, 255).astype(np.uint8)).resize(SCENE, Image.LANCZOS)).astype(float)
    cs = np.asarray(Image.fromarray(core.astype(np.uint8) * 255).resize(SCENE, Image.BOX)) == 255
    lap = np.abs(4 * sc[1:-1, 1:-1] - sc[:-2, 1:-1] - sc[2:, 1:-1] - sc[1:-1, :-2] - sc[1:-1, 2:])
    shape = np.abs(np.diff(a, axis=1)).mean() / np.abs(np.diff(a, axis=0)).mean()
    return dict(top=np.percentile(lum[core], 95), spread=np.percentile(lum[core], 95) - np.percentile(lum[core], 5),
                detail=lap[cs[1:-1, 1:-1]].mean(), aniso=shape)


def kb(rgba):
    b = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(b, "webp", quality=clouds.WEBP_QUALITY)
    return len(b.getvalue()) / 1024


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
                fails.append("%s: cloud edges fade over %.1f scene px on average, max %.1f" % (name, r, EDGE_MAX))
        m = look(s, ss)
        if name.endswith("-day") or name in ("windy", "overcast"):   # the scenes lit by day
            if m["top"] < TOP_MIN and name != "overcast":
                fails.append("%s: brightest tops %.0f, need %d (flat grey)" % (name, m["top"], TOP_MIN))
            if m["spread"] < SPREAD_MIN and name != "overcast":
                fails.append("%s: light-to-shade spread %.0f, need %d" % (name, m["spread"], SPREAD_MIN))
            if not DETAIL[0] <= m["detail"] <= DETAIL[1]:
                fails.append("%s: fine detail %.1f inside the cloud, want %.1f..%.1f" % (name, m["detail"], *DETAIL))
        if name.startswith("partlycloudy") and not ANISO[0] <= m["aniso"] <= ANISO[1]:
            fails.append("%s: cloud shapes horizontal/vertical %.2f, want %.2f..%.2f (stretched)" % (name, m["aniso"], *ANISO))
        k = kb(s)
        if k > KB_MAX:
            fails.append("%s: %.0f KB encoded, budget %d" % (name, k, KB_MAX))
    for f in fails:
        print("FAIL", f)
    print("%d strip(s) checked, %d failure(s)" % (len(OPEN) + 1, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
