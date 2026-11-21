"""Cloud strips for the weather card: fractal noise, lit from above, seamless left to right.

Pure numpy, no tower and no command line, so tests/weather/test_clouds.py can import it.
"""
import numpy as np

EDGE_RAMP = 0.4   # alpha ramp at an edge, in field std (was 1.1: edges were ~11 scene px of fringe)
EDGE_DETAIL = 0.06   # weight of the fine field that frays the edges
FINE_LO = 25         # its coarsest wave, in cycles per strip height (lower = bigger wisps)
WEBP_QUALITY = 78
MACRO_PX = 22   # how far light from above reaches into a cloud, scene px
BASE_PX = 10     # depth of the shaded underside, scene px
HGT_BLUR = 0.8   # scene px
DECK_BUMP = 0.5  # an overcast deck is flatter-lit than a cumulus
BUMP = 8        # slope gain of the billow height field
SS = 1.2   # the strip is rendered at SS x the scene size (tests/weather/test_clouds.py)


def _field(shape, seed, stretch, beta, lo=2.0):
    """Fractal noise (power-law spectrum). The FFT makes it periodic, so the strip wraps.
    Frequencies count cycles per strip HEIGHT in both directions, so stretch=1 is round in
    pixels. (Until 2026-11-21 kx counted cycles per strip width: on the 1.45:1 strip every
    field came out 1.45x wider than tall, and the partly cloudy 1.6 meant 2.3:1, which read
    as an image stretched sideways.)"""
    H, W = shape
    rng = np.random.default_rng(seed)
    ky = np.fft.fftfreq(H)[:, None] * H; kx = np.fft.fftfreq(W)[None, :] * H
    k = np.sqrt((kx * stretch) ** 2 + ky ** 2); k[0, 0] = 1
    amp = 1 / np.maximum(k, lo) ** (beta / 2); amp[0, 0] = 0
    f = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((H, W))) * amp))
    return (f - f.mean()) / f.std()


def _band(shape, seed, k0, stretch=1.0):
    """Band-pass noise around k0 cycles per strip height (one octave wide), unit std.
    Periodic like _field, so the strip still wraps."""
    H, W = shape
    rng = np.random.default_rng(seed)
    ky = np.fft.fftfreq(H)[:, None] * H; kx = np.fft.fftfreq(W)[None, :] * H
    k = np.sqrt((kx * stretch) ** 2 + ky ** 2)
    amp = np.exp(-0.5 * (np.log2(np.maximum(k, 1e-6) / k0) / 0.5) ** 2)
    f = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((H, W))) * amp))
    return f / f.std()


def billows(shape, seed, octaves=(4, 8, 16, 32), stretch=1.0, crease=True):
    """Billow noise: |band-pass| summed over octaves. Each zero crossing becomes a crease and
    each lobe a rounded hump, so the height field looks like cumulus cauliflower. Without
    crease the octaves add signed: smooth rolls, the underside of a deck."""
    h = np.zeros(shape)
    for i, k0 in enumerate(octaves):
        b = _band(shape, seed + 10 * i, k0, stretch)
        h += 0.3 ** i * (np.abs(b) if crease else 0.6 * b)
    return h


def _blur(a, sigma):
    """Gaussian blur done in frequency space, so it keeps the strip seamless."""
    ky = np.fft.fftfreq(a.shape[0])[:, None]; kx = np.fft.fftfreq(a.shape[1])[None, :]
    return np.real(np.fft.ifft2(np.fft.fft2(a) * np.exp(-2 * (np.pi * sigma) ** 2 * (kx ** 2 + ky ** 2))))


def strip(size, cover, top, under, ymax, seed, stretch=1.1, density=1.0, lo=4.0, deck=False):
    """An RGBA array (H, W, 4) of clouds for a scene of size (W, H), at SS x that size.
    cover: share of sky (0..1); ymax: lowest cloud line as a fraction of the height;
    top/under: lit and shaded colours; deck: a closed overcast layer.

    Shape: fractal noise thresholded into crisp, fraying edges. Light, two parts:
    - macro: light from above is used up by the cloud mass it passes through, so tops are
      bright and bellies grey (the memory is in scene px, so SS does not change it);
    - bumps: a fine height field lit by a sun high in the sky, so every billow has a lit
      top and a shaded underside. This is what gives the cloud the tower's crispness;
      the macro term alone left a flat grey (tests/weather/test_clouds.py)."""
    W, H = round(size[0] * SS), round(size[1] * SS)
    shape = (H, W)
    f = 0.8 * _field(shape, seed, stretch, 3.6, lo=lo) + 0.2 * _field(shape, seed + 1, stretch * 0.8, 3.0, lo=10)
    # fine detail, so a sharp edge frays into wisps instead of a smooth cut-out outline
    fine = _field(shape, seed + 3, stretch * 0.7, 2.2, lo=FINE_LO)
    body = f                                  # without the fray: it is pixel-fine and would grain the light
    f = f + EDGE_DETAIL * fine
    yy = np.linspace(0, 1, H)[:, None]
    f = f - 2.2 * np.clip((yy - ymax * 0.5) / (ymax * 0.5 + 1e-6), 0, 1)   # thin out towards ymax
    th = np.quantile(f, 1 - cover)
    a = np.clip((f - th) / EDGE_RAMP, 0, 1); a = _blur(a * a * (3 - 2 * a), 0.5 * SS).clip(0, 1)
    if deck:
        a = np.clip(0.82 + 0.25 * (f - f.mean()) / f.std(), 0.55, 1)
    # macro light: memory MACRO_PX scene px
    mass = np.zeros_like(a); acc = np.zeros(W); keep = np.exp(-1 / (MACRO_PX * SS))
    for y in range(H):
        acc = acc * keep + a[y]; mass[y] = acc
    macro = np.exp(-mass / ((MACRO_PX if not deck else 2.5 * MACRO_PX) * SS))
    # bumps: billows at two scales, slopes per scene px, sun up and a little left
    # a deck's rolls are soft and only a little wider than tall; its stretch shapes the gaps
    hgt = billows(shape, seed + 2, stretch=min(stretch, 1.6) if deck else stretch, crease=not deck) + 0.5 * (body - th)   # the body bulges too
    hgt = _blur(hgt, HGT_BLUR * SS)          # |.| creases ring down to the pixel: that read as sand
    gy, gx = np.gradient(hgt)
    gain = BUMP * (DECK_BUMP if deck else 1)
    gy, gx = gy * SS * gain, gx * SS * gain
    ndl = (0.25 * gx + 0.85 * gy + 0.45) / np.sqrt(1 + gx ** 2 + gy ** 2)   # -h' . (-0.25, -0.85) + lz
    ndl = np.clip(ndl, 0, 1)
    light = (0.35 + 0.65 * macro) * (0.25 + 1.55 * ndl)
    if not deck:
        # bases: little cloud below a point means it is near the underside, which is in shade
        below = np.zeros_like(a); acc = np.zeros(W); keep_b = np.exp(-1 / (BASE_PX * SS))
        for y in range(H - 1, -1, -1):
            acc = acc * keep_b + a[y]; below[y] = acc
        light = light * (1 - 0.4 * np.exp(-below / (BASE_PX * SS)))
    if not deck:
        light = light + 0.3 * (1 - a)        # thin edges let the light through
    shade = 1 - np.clip(light, 0, 1)
    rgb = np.array(top)[None, None] * (1 - shade[..., None]) + np.array(under)[None, None] * shade[..., None]
    return np.dstack([rgb, a * 255 * density]).clip(0, 255).astype(np.uint8)
