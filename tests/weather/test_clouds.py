#!/usr/bin/env python3
"""Offline checks on the weather card's cloud strips (tools/weather-scenes/clouds.py).

    python3 tests/weather/test_clouds.py

History, all operator, 2026-11-21. The clouds "looked low resolution" next to the tower.
Two rounds of sharper edges, more relief and more detail made them worse ("cheese"): the
operator preferred the original soft look. What was actually wrong, in their words:
"the clouds look 2D, they are not aligned with the skyline" and "they need to be distinct
clouds, not one cloud with holes". So this locks down:

- distinct clouds: a partly cloudy sky is several separate clouds (at least MIN_CLOUDS),
  and the sky between them is sky, not holes: sky enclosed by cloud is at most HOLES_MAX
  of the cloud area (HOLES_MAX_WINDY for torn wind clouds). The old noise-threshold sheet was one cloud full of holes;
- perspective: clouds sit on a layer above the city, so they shrink and bunch towards the
  skyline: there are at least BUNCH_MIN times as many separate clouds just above it (5-30 %
  of the way from the horizon to the top) as near the top (above 60 %). (A width/height correlation was
  tried first and swung 0.5-0.9 between seeds; "the widest cloud is in the top half" was
  dropped because a sky without perspective passed it too.) Noise has no reason to do either. An overcast deck
  shows the same thing in its texture: just above the horizon (0.1-0.22 of the height above
  it; lower down a deck is haze) it is at least DECK_DEPTH times finer than near the top;
- random, like real clouds (operator, after the perspective version: "still a little
  cartoonish... all clouds are more or less the same shape and size, real clouds are
  random", and the spacing "doesn't seem natural, especially in the distance"). With the
  perspective factored out (width over height above the horizon), cloud sizes spread with
  a coefficient of variation of at least CV_SIZE_MIN (log-normal sizes: many small, a few
  big); and near clouds are not evenly spaced: their nearest-neighbour distance is at most
  CLUSTER_MAX of random points' (the evenly spaced layout scored 1.28-1.46). Partly cloudy
  only. NOT covered, checked by eye: shape variety (lobes, height, fraying: a height/width
  spread could not tell them from identical domes) and the grouping into clusters (the
  spacing check catches an even layout, but not clusters removed from a log-normal one).
- the whole sky (operator: "your horizon ends at around 2/3 from the top, but the view from
  below shows the entire skyline, so the clouds would cover all of it"): the band just above
  the bottom edge, 0.8-0.95 of the height, has at least LOW_COVER_MIN cloud. Bands for the
  perspective and deck checks are measured from the horizon, wherever it is;
- soft: the operator liked the original soft edges, so the alpha ramp at a cloud's edge is
  at least EDGE_SOFT scene px (the crisp version that was rejected had under 4);
- NOT covered: the overcast deck's rolls fade out together above the skyline instead of
  stopping in a line. That was checked by eye on all 16 strips; a row-step metric could
  not tell the two apart reliably (0.44 vs 0.65).
- the overcast deck made from a photo (operator, 2026-11-21: of real photos laid on the card,
  "12 is best for overcast"): it keeps the scene's own tone, its texture, no gaps, no ground
  from the photo, and it wraps. Checked on a synthetic photo, so CI needs no network;
- the strip still wraps, has enough pixels for a 3x phone (SS >= MIN_SS) and costs at
  most KB_MAX encoded.
Numbers are in scene px, so they hold whatever clouds.SS is.
"""
import io, os, sys
from collections import deque
import numpy as np
from PIL import Image, ImageFilter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "tools", "weather-scenes"))
import clouds  # noqa: E402

SCENE = (900, 620)
MIN_SS = 1.18        # 354 CSS px x 3 / 900
KB_MAX = 250
LOW_COVER_MIN = 0.1  # the band above the skyline is not empty
MIN_CLOUDS = 6       # a floor, not a discriminator: ~60 here, and the noise sheet passed it too
HOLES_MAX = 0.01     # partly cloudy: 0.1-0.5 % over seeds; 1.5 % if the noise may punch holes
HOLES_MAX_WINDY = 0.025  # torn wind clouds: up to 2 % over seeds
BUNCH_MIN = 1.5      # with perspective 1.6-4.7 (merged distant clouds count as one, which
                     # lowers it); without 0.1-0.9. Accepted: a halved perspective could pass
DECK_DEPTH = 1.35    # new deck 1.6-2.0 over seeds, the flat noise deck ~0.93
# These two guard the SHIPPED strip (seed 7: 0.76 and 1.10), not every seed: over seeds 7-14
# the random layout scores 0.58-0.76 and 1.02-1.43, so a few seeds overlap the even layout
# (0.39-0.53, 1.28-1.46 over seeds 7-10). Changing the seed means re-checking these by eye.
CV_SIZE_MIN = 0.6
CLUSTER_MAX = 1.2
EDGE_SOFT = 6.0      # scene px: 7.2-7.8 over seeds; 5.2 without the distance normalisation
# the scenes.py calls (keep in step with scenes.py; the deck's colours are one example,
# scenes.py derives them from each scene's colour)
OPEN = {
    "partlycloudy-day": dict(cover=0.3, top=(255, 255, 255), under=(150, 158, 176), ymax=1.0, seed=7),
    "partlycloudy-night": dict(cover=0.3, top=(52, 58, 78), under=(82, 74, 80), ymax=1.0, seed=7, density=0.85),
    "windy": dict(cover=0.28, top=(255, 255, 255), under=(150, 158, 176), ymax=1.0, seed=7, stretch=3.0, density=0.85),
}
DECK = dict(cover=1.0, top=(255, 255, 255), under=(155, 158, 161), ymax=1.0, seed=7, stretch=2.0,
            density=220 / 255, deck=True)


def mask(rgba, level=0.35, step=4):
    """Cloud mask at scene scale / step: alpha above level of its maximum."""
    a = rgba[..., 3].astype(float)
    small = np.asarray(Image.fromarray(a.astype(np.uint8)).resize((SCENE[0] // step, SCENE[1] // step), Image.BOX))
    return small >= level * a.max()


def components(m):
    """Labels of 4-connected regions of m, wrapping left to right (the strip wraps)."""
    H, W = m.shape
    lab = np.zeros(m.shape, int); n = 0
    for y0, x0 in zip(*np.nonzero(m)):
        if lab[y0, x0]:
            continue
        n += 1; lab[y0, x0] = n; q = deque([(y0, x0)])
        while q:
            y, x = q.popleft()
            for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                ny, nx = y + dy, (x + dx) % W
                if 0 <= ny < H and m[ny, nx] and not lab[ny, nx]:
                    lab[ny, nx] = n; q.append((ny, nx))
    return lab, n


def clouds_of(rgba):
    """(width, centre height above the bottom) of each cloud bigger than a speck, scene px."""
    m = mask(rgba); lab, n = components(m); out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(ys) < 6:
            continue
        cols = np.unique(xs)
        out.append((len(cols) * 4, (m.shape[0] - ys.mean()) * 4))
    return out


def layout(rgba):
    """Per cloud: (width, height, x centre, y centre, px above the horizon), at mask scale."""
    m = mask(rgba); lab, n = components(m); H, W = m.shape; out = []
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        if len(ys) < 6:
            continue
        ang = xs / W * 2 * np.pi                       # circular mean: a cloud may straddle the seam
        xc = (np.arctan2(np.sin(ang).mean(), np.cos(ang).mean()) % (2 * np.pi)) / (2 * np.pi) * W
        p = clouds.HORIZON * H - ys.mean()
        if p > 1:
            out.append((len(np.unique(xs)), len(np.unique(ys)), xc, ys.mean(), p))
    return np.array(out)


def variety(rgba):
    """(size CV, spacing ratio). Size: width over height above the horizon, so perspective is
    factored out. Spacing: mean nearest-neighbour distance of the near clouds (more than 35 %
    of the horizon's height above it, where none merge) on the layer (x over distance, log
    distance), against random points in the same box: under 1 is clustered, over 1 even."""
    w, h, xc, yc, p = layout(rgba).T
    size = w / p
    near = p > 0.35 * clouds.HORIZON * mask(rgba).shape[0]
    pts = np.c_[(xc / p)[near], np.log(p[near])]
    if len(pts) < 5:
        return size.std() / size.mean(), float("nan")   # too few to judge: main() fails it
    def nn(P):
        d = np.sqrt(((P[:, None, :] - P[None, :, :]) ** 2).sum(-1)); np.fill_diagonal(d, np.inf)
        return d.min(1).mean()
    rng = np.random.default_rng(0); lo, hi = pts.min(0), pts.max(0)
    rand = np.mean([nn(rng.uniform(lo, hi, pts.shape)) for _ in range(30)])
    return size.std() / size.mean(), nn(pts) / rand


def holes(rgba):
    """Share of the cloud area that is sky enclosed by cloud (not reachable from open sky)."""
    m = mask(rgba); lab, n = components(~m)
    if n == 0:
        return 0.0
    sizes = np.bincount(lab.ravel())[1:]
    open_sky = set(np.unique(lab[0])) | set(np.unique(lab[-1])) | {int(np.argmax(sizes)) + 1}
    enclosed = sum(s for i, s in enumerate(sizes, 1) if i not in open_sky)
    return enclosed / max(m.sum(), 1)


def edge_ramp(rgba, ss):
    """Mean width of the 10..90 % alpha ramp at cloud edges, in scene px. Each pixel is taken
    against the highest alpha within ~10 scene px, so a cloud faded by haze is measured
    against its own plateau, not the nearest cloud's."""
    a = rgba[..., 3]
    k = int(10 * ss) | 1
    peak = np.asarray(Image.fromarray(a).filter(ImageFilter.MaxFilter(k))).astype(float)
    rel = np.where(peak > 25, a / np.maximum(peak, 1), 0.0)
    part = (rel > 0.1) & (rel < 0.9)
    gy, gx = np.gradient(rel)
    return 0.8 / np.mean(np.hypot(gx, gy)[part]) / ss


def texture_scale(rgba, lo, hi):
    """Power-weighted mean horizontal frequency (cycles per strip) of the luminance over a band
    of rows (fractions of the height). Bigger rolls, lower number."""
    lum = rgba[..., :3].astype(float) @ [0.299, 0.587, 0.114]
    sc = np.asarray(Image.fromarray(lum.clip(0, 255).astype(np.uint8)).resize(SCENE, Image.BOX)).astype(float)
    band = sc[int(SCENE[1] * lo):int(SCENE[1] * hi)]
    band = band - band.mean(axis=1, keepdims=True)
    power = (np.abs(np.fft.rfft(band, axis=1)) ** 2).mean(axis=0)[1:]
    k = np.arange(1, len(power) + 1)
    return (power * k).sum() / power.sum()


def seam(rgba):
    """Wrap-around step against the typical neighbour step."""
    x = rgba.astype(float)
    return np.abs(x[:, 0] - x[:, -1]).mean() / np.abs(np.diff(x, axis=1)).mean()


def kb(rgba):
    b = io.BytesIO(); Image.fromarray(rgba, "RGBA").save(b, "webp", quality=clouds.WEBP_QUALITY)
    return len(b.getvalue()) / 1024


def photo_deck_fails():
    """The overcast deck made from a photo (clouds.photo_deck), checked on a synthetic photo so
    CI needs no network: a smooth cloud texture with dark ground across its bottom fifth."""
    fails = []
    rng = np.random.default_rng(3)
    H, W = 900, 1200
    f = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((H, W))) / np.maximum(
        np.hypot(*np.meshgrid(np.fft.fftfreq(W) * W, np.fft.fftfreq(H) * H)), 2) ** 1.6))
    sky = 0.6 + 0.12 * f / f.std()
    sky[int(H * 0.8):] = 0.08                           # ground: must be cropped away
    photo = (np.repeat(sky[..., None], 3, -1) * 255).clip(0, 255).astype(np.uint8)
    for color, density in (((222, 225, 230), 220 / 255), ((40, 44, 56), 230 / 255)):
        s = clouds.photo_deck(photo, SCENE, color, density, keep=0.78)
        name = "photo deck %s" % (color,)
        if s.shape[:2] != (round(SCENE[1] * clouds.SS), round(SCENE[0] * clouds.SS)):
            fails.append("%s: strip %s is not the scene's shape" % (name, s.shape[:2]))
            continue
        if seam(s) > 2.0:
            fails.append("%s: wrap step %.1fx a neighbour step: the drift shows a seam" % (name, seam(s)))
        if s[..., 3].min() < 0.85 * density * 255:
            fails.append("%s: the deck has gaps (alpha down to %d)" % (name, s[..., 3].min()))
        mean = s[..., :3].reshape(-1, 3).mean(0)
        if np.abs(mean - np.array(color)).max() > 8:
            fails.append("%s: tone %s, want the scene's %s" % (name, mean.round(), color))
        lum = s[..., :3].astype(float).mean(-1)
        if lum.std() < 0.04 * max(np.mean(color), 60):
            fails.append("%s: texture flattened (std %.1f)" % (name, lum.std()))
        if lum[-lum.shape[0] // 20:].mean() < 0.85 * lum.mean():
            fails.append("%s: the bottom is dark: ground left in the photo" % name)
    return fails


def main():
    fails = photo_deck_fails()
    for name, kw in list(OPEN.items()) + [("overcast", DECK)]:
        s = clouds.strip(SCENE, **kw)
        ss = s.shape[1] / SCENE[0]
        if s.shape[:2] != (round(SCENE[1] * ss), round(SCENE[0] * ss)):
            fails.append("%s: strip %s is not the scene's shape" % (name, s.shape[:2]))
        if ss < MIN_SS:
            fails.append("%s: %.2f px per scene px, need %.2f" % (name, ss, MIN_SS))
        if seam(s) > 2.0:
            fails.append("%s: wrap step %.1fx a neighbour step: the drift shows a seam" % (name, seam(s)))
        if kb(s) > KB_MAX:
            fails.append("%s: %.0f KB encoded, budget %d" % (name, kb(s), KB_MAX))
        if name == "overcast":
            near, far = texture_scale(s, 0, 0.2), texture_scale(s, clouds.HORIZON - 0.22, clouds.HORIZON - 0.1)
            if far < DECK_DEPTH * near:
                fails.append("overcast: texture %.1f cycles at the top, %.1f near the horizon: no depth" % (near, far))
            continue
        a = s[..., 3].astype(float) / 255
        low = a[int(0.8 * a.shape[0]):int(0.95 * a.shape[0])]
        if (low > 0.3).mean() < LOW_COVER_MIN:
            fails.append("%s: %.0f %% cloud just above the skyline (0.8-0.95 of the height), want %.0f %%"
                         % (name, 100 * (low > 0.3).mean(), 100 * LOW_COVER_MIN))
        cl = clouds_of(s)
        if not cl:
            fails.append("%s: no clouds at all" % name)
            continue
        if len(cl) < MIN_CLOUDS:
            fails.append("%s: %d separate clouds, need %d" % (name, len(cl), MIN_CLOUDS))
        h, limit = holes(s), HOLES_MAX_WINDY if name == "windy" else HOLES_MAX
        if h > limit:
            fails.append("%s: %.1f %% of the cloud is enclosed sky (holes), max %.1f %%" % (name, 100 * h, 100 * limit))
        w, y = np.array(cl).T
        H = SCENE[1]
        q = (y - (1 - clouds.HORIZON) * H) / (clouds.HORIZON * H)   # height above the skyline, 0..1
        near, far = (q > 0.6).sum(), ((q > 0.05) & (q < 0.3)).sum()
        if far < BUNCH_MIN * max(near, 1):
            fails.append("%s: %d clouds just above the skyline, %d near the top: no perspective" % (name, far, near))
        if name.startswith("partlycloudy"):
            cs, cr = variety(s)
            if cs < CV_SIZE_MIN:
                fails.append("%s: cloud sizes vary by %.2f (CV), want %.2f: all the same size" % (name, cs, CV_SIZE_MIN))
            if not np.isfinite(cr):
                fails.append("%s: under 5 near clouds, spacing cannot be judged" % name)
            elif cr > CLUSTER_MAX:
                fails.append("%s: spacing %.2f of random, want at most %.2f: too even" % (name, cr, CLUSTER_MAX))
        r = edge_ramp(s, ss)
        if r < EDGE_SOFT:
            fails.append("%s: edges fade over %.1f scene px, want at least %.1f (soft)" % (name, r, EDGE_SOFT))
    for f in fails:
        print("FAIL", f)
    print("%d strip(s) checked, %d failure(s)" % (len(OPEN) + 1, len(fails)))
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
