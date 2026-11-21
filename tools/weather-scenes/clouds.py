"""Cloud strips for the weather card: separate soft clouds on a layer above the city, seen in
perspective, seamless left to right.

Pure numpy, no tower and no command line, so tests/weather/test_clouds.py can import it.

Why objects and not a noise sheet (operator, 2026-11-21): a thresholded noise field is one
cloud full of holes, and it is flat; the clouds "looked 2D, not aligned with the skyline".
Here each cloud is placed on a horizontal layer and projected: a cloud whose flat base sits
p px above the horizon on screen is at a distance proportional to 1/p, so its size scales
with p. Distant clouds are small, low, and seen from the side (a lit dome on a flat base);
clouds overhead are large and seen from below (mostly grey underside). Distance also fades
them into the haze. The soft edges and gentle light are the original look the operator
preferred to every sharper version.
"""
import numpy as np

WEBP_QUALITY = 78
SS = 1.2          # strip px per scene px: a 3x phone draws the 900 px scene over ~1060 px
HORIZON = 0.72    # the horizon, as a fraction of the height from the top: behind the city,
                  # under the scrim and the tower's base
WIDTH_K = 0.6    # cloud width / its base's height above the horizon (both on screen)
DOME = 0.42       # height of a distant cloud's lit dome / its width
UNDER = 0.20      # depth of an overhead cloud's visible underside / its width
SOFT_K = 0.16    # edge softness / cloud width
SOFT_MIN = 6.0    # scene px
MIN_COUNT = 25    # a few big clouds must not use up the whole sky
FRAY = 0.14       # how much the outline billows, / cloud width


def _field(shape, seed, beta, lo=2.0):
    """Fractal noise (power-law spectrum), unit std, periodic in both directions. Frequencies
    count cycles per patch HEIGHT both ways, so it is round in pixels."""
    H, W = shape
    rng = np.random.default_rng(seed)
    ky = np.fft.fftfreq(H)[:, None] * H; kx = np.fft.fftfreq(W)[None, :] * H
    k = np.sqrt(kx ** 2 + ky ** 2); k[0, 0] = 1
    amp = 1 / np.maximum(k, lo) ** (beta / 2); amp[0, 0] = 0
    f = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((H, W))) * amp))
    return (f - f.mean()) / f.std()


def _blur(a, sigma):
    """Gaussian blur in frequency space (periodic, like the fields)."""
    ky = np.fft.fftfreq(a.shape[0])[:, None]; kx = np.fft.fftfreq(a.shape[1])[None, :]
    return np.real(np.fft.ifft2(np.fft.fft2(a) * np.exp(-2 * (np.pi * sigma) ** 2 * (kx ** 2 + ky ** 2))))


def _smooth(x):
    x = np.clip(x, 0, 1)
    return x * x * (3 - 2 * x)


def _shape(rng):
    """A random cloud's character: no two alike (operator: "real clouds are random").
    tall: height over a typical cumulus; lobes: (centre, half-width, height) of the one to
    three domes it is built from, across -1..1; fray: how torn its outline is."""
    n = int(rng.choice([1, 2, 2, 3, 3]))
    lobes = []
    for i in range(n):
        c = 0.0 if n == 1 else rng.uniform(-0.55, 0.55)
        hw = min(rng.uniform(0.45, 1.0), 1 - abs(c)) if n > 1 else 1.0   # stays within the width
        lobes.append((c, hw, rng.uniform(0.45, 1.0) if i else 1.0))
    return dict(tall=float(np.clip(np.exp(rng.normal(0, 0.4)), 0.5, 1.7)), lobes=lobes, fray=FRAY * rng.uniform(0.6, 1.5))


def _cloud(w, t, aspect, rng, top, under, deck=False, shape=None):
    """One cloud: premultiplied RGB, alpha, and the row of its flat bottom in the patch.
    w: width (px); t: nearness, 0 at the lowest base line to 1 overhead; aspect: >1 flattens
    (wind, decks); shape: from _shape (a plain dome if None)."""
    shape = shape or dict(tall=1.0, lobes=[(0.0, 1.0, 1.0)], fray=FRAY)
    aspect = aspect / shape["tall"]
    dome = w * DOME * (1 - 0.65 * t) / aspect        # seen from the side far away, hidden overhead
    und = w * UNDER * t / aspect                      # the flat base, foreshortened: thin far away
    hgt = dome + und
    pw, ph = int(w * 1.6) + 8, int(hgt * 1.6 + w * 0.3) + 8
    cx, yb = pw / 2, ph - w * 0.08 - 4                # yb: the flat bottom line
    Y, X = np.mgrid[0:ph, 0:pw].astype(float)
    u = (X - cx) / (w / 2)
    v = (yb - Y) / max(hgt, 1)                         # 0 at the base, 1 at the top of the dome
    # outline: a dome over a flat base, billowed by noise whose features scale with the cloud
    # the original sky's fractal texture, scaled to this cloud: big billows plus finer wisps,
    # with the finest scale tied to the cloud's size so a near cloud is not jagged
    seed = int(rng.integers(1 << 30)); lo = max(ph / (w * 0.6), 1.5)
    n = 0.75 * _field((ph, pw), seed, 3.6, lo=lo) + 0.25 * _field((ph, pw), seed + 1, 2.6, lo=lo * 3)
    n = _blur(n, 0.008 * w); n = n / n.std()
    billow = _blur(_field((ph, pw), seed + 2, 3.0, lo=lo * 2), 0.01 * w); billow = billow / billow.std()
    # domes, finite slope at their sides (a |1-u^2|^0.55 dome drew a line at u = +-1); the
    # lobes are joined with a soft maximum so the outline has no creases
    e = 2.2                                            # rounded domes: pointed ones read as cartoons
    parts = [hl * (1 - np.abs((u - c) / hw) ** e) for c, hw, hl in shape["lobes"]]
    env = 0.12 * np.logaddexp.reduce(np.array(parts) / 0.12, axis=0)   # stable soft maximum
    side = np.clip(v * 2.5, 0.25, 1)                   # the base stays flat, the dome billows
    depth = np.minimum((env - v) * hgt, v * hgt)       # px inside the plain outline
    reach = np.clip(1 - depth / (0.12 * w), 0.15, 1)    # the noise frays the edge, never punches holes
    d1, d2, k = (env - v) * hgt + shape["fray"] * w * n * side * reach, v * hgt + 0.03 * w * n, 0.06 * w
    d = -k * np.logaddexp(-d1 / k, -d2 / k)            # a soft minimum: the base's corners are round
    soft = max(SOFT_K * w, SOFT_MIN * SS)
    gy, gx = np.gradient(d)
    slope = _blur(np.hypot(gx, gy), 0.03 * w)          # smoothed, or its ridges draw marbled lines
    d = d / np.maximum(slope, 1)                       # px to the edge: the noise makes d steep, and
    a = _smooth(d / soft + 0.4)                        # without this the edge was crisp at any soft
    edge = np.minimum(np.minimum(X, pw - 1 - X) / (0.08 * pw), np.minimum(Y, ph - 1 - Y) / (0.08 * ph))
    a = a * _smooth(edge)                              # nothing reaches the patch border: no cut lines
    # light from above, used up by the cloud it passes (memory: a third of the cloud's height)
    mass = np.zeros_like(a); acc = np.zeros(pw); keep = np.exp(-1 / max(hgt * 0.35, 1))
    for y in range(ph):
        acc = acc * keep + a[y]; mass[y] = acc
    light = np.exp(-mass / max(hgt * 0.3, 1)) * (0.75 + 0.25 * np.tanh(billow)) + 0.12 * np.tanh(billow) + 0.3 * (1 - a)
    # the underside is in shade, blending into the lit dome over a tenth of the cloud's height
    light = light * (1 - 0.45 * _smooth((und / max(hgt, 1) - v) / 0.1 + 0.5))
    light = 0.5 + (np.clip(light, 0, 1) - 0.5) * (0.45 + 0.55 * t)  # far away: lower contrast
    if deck:                                           # rolls: low contrast, gone into the haze at the horizon
        light = 0.5 + (light - 0.5) * 0.6
        a = a * 0.85 * np.sqrt(t)
    else:
        a = a * (0.55 + 0.45 * np.sqrt(t))             # haze: distant clouds thin out
    shade = 1 - np.clip(light, 0, 1)
    rgb = np.array(top)[None, None] * (1 - shade[..., None]) + np.array(under)[None, None] * shade[..., None]
    return rgb * a[..., None], a, yb


def _overlap(a, b, W):
    """Overlap of two boxes as a share of the smaller, with the strip wrapping."""
    best = 0.0
    for s in (-W, 0, W):
        ix = max(0, min(a[2], b[2] + s) - max(a[0], b[0] + s))
        iy = max(0, min(a[3], b[3]) - max(a[1], b[1]))
        area = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
        best = max(best, ix * iy / max(area, 1))
    return best


def strip(size, cover, top, under, ymax, seed, stretch=1.0, density=1.0, deck=False):
    """An RGBA array (H, W, 4) of clouds for a scene of size (W, H), at SS x that size.
    cover: share of the sky band covered; ymax: the lowest cloud base, as a fraction of the
    height; top/under: lit and shaded colours; stretch: cloud width/height relative to a
    cumulus (wind, decks); deck: a closed overcast layer of many overlapping clouds."""
    W, H = round(size[0] * SS), round(size[1] * SS)
    rng = np.random.default_rng(seed)
    yh = HORIZON * H
    p_lo, p_hi = max(yh - ymax * H, 0.05 * H), yh * 1.04   # base heights above the horizon
    aspect = stretch ** 0.5
    placed, covered = [], 0.0
    target = cover * W * ymax * H * (2.5 if deck else 1.0)
    # clouds come in groups with clear sky between (an even scatter read as cartoonish):
    # a few clusters on the layer, each spread in proportion to its distance on screen
    lp_lo, lp_hi = np.log(p_lo), np.log(p_hi)
    clusters = [(rng.uniform(0, W), rng.uniform(lp_lo, lp_hi), rng.uniform(0.4, 1.1), rng.uniform(0.1, 0.25))
                for _ in range(int(rng.integers(5, 9)))]
    def crowd(x, p):
        d = 0.0
        for cx, clp, sx, slp in clusters:
            dx = (x - cx + W / 2) % W - W / 2
            d += np.exp(-0.5 * ((dx / (sx * p)) ** 2 + ((np.log(p) - clp) / slp) ** 2))
        return d
    for _ in range(60000):
        if covered >= target and len(placed) >= (0 if deck else MIN_COUNT):
            break
        p = 1 / rng.uniform(1 / p_hi, 1 / p_lo)         # uniform in distance ~ 1/p
        x = rng.uniform(0, W)
        if not deck and rng.uniform() > 0.02 + crowd(x, p):
            continue
        # sizes are log-normal: many small clouds and a few big ones
        w = WIDTH_K * p * aspect * float(np.clip(np.exp(rng.normal(-0.2, 0.75)), 0.25, 2.0))
        if int(w * 1.6) + 8 > W:                       # its patch would not fit the strip
            continue
        shape = _shape(rng)
        yb = yh - p
        box = (x - w / 2, yb - w * 0.45 * shape["tall"] / aspect, x + w / 2, yb)
        # keep apart with room for the frayed outline, so two clouds never close a pocket of sky
        pad = (box[0] - 0.12 * w, box[1] - 0.1 * w, box[2] + 0.12 * w, box[3])
        # near clouds stay apart; distant ones may overlap on screen, as they do in a real sky,
        # where they are far apart in depth and merge into bands towards the skyline
        t = (p - p_lo) / (p_hi - p_lo)
        if not deck and any(_overlap(pad, b, W) > 0.04 + 0.3 * (1 - t) ** 3 for b, _ in placed):
            continue
        placed.append((box, shape)); covered += w * w * 0.3 * shape["tall"] / aspect
    acc_rgb = np.zeros((H, W, 3)); acc_a = np.zeros((H, W))
    for box, shape in sorted(placed, key=lambda b: -b[0][3]):   # far (low on screen) first, near last
        x0, _, x1, base = box; w = x1 - x0
        t = np.clip((yh - base - p_lo) / (p_hi - p_lo), 0, 1)
        rgb, a, yb = _cloud(w, t, aspect, rng, top, under, deck, shape)
        ph, pw = a.shape
        oy, ox = int(round(base - yb)), int(round((x0 + x1) / 2 - pw / 2))
        y0, y1 = max(oy, 0), min(oy + ph, H)
        if y0 >= y1:
            continue
        rows, cols = np.arange(y0, y1), (np.arange(pw) + ox) % W   # wrap left to right
        r, al = rgb[y0 - oy:y1 - oy], a[y0 - oy:y1 - oy]
        ix = np.ix_(rows, cols)
        acc_rgb[ix] = r + acc_rgb[ix] * (1 - al[..., None])
        acc_a[ix] = al + acc_a[ix] * (1 - al)
    if deck:
        # dozens of distant rolls overlap near the skyline, so together they stay opaque and
        # would stop in a hard line: fade them out together over the last band above it
        fade = _smooth((yh - 0.06 * H - np.arange(H)) / (0.18 * H))[:, None]
        acc_rgb, acc_a = acc_rgb * fade[..., None], acc_a * fade
        # the deck itself: a closed fill behind the rolls, a little lighter towards the horizon
        g = np.linspace(0, 1, H)[:, None, None]
        fill = np.array(under, float) * (1 - 0.35 * g) + np.array(top, float) * 0.35 * g
        acc_rgb = acc_rgb + fill * 0.88 * (1 - acc_a[..., None])
        acc_a = acc_a + 0.88 * (1 - acc_a)
    rgb = acc_rgb / np.maximum(acc_a[..., None], 1e-6)
    return np.dstack([rgb, acc_a * 255 * density]).clip(0, 255).astype(np.uint8)
