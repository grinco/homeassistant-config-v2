"""Cloud strips for the weather card: fractal noise, lit from above, seamless left to right.

Pure numpy, no tower and no command line, so tests/weather/test_clouds.py can import it.
"""
import numpy as np

EDGE_RAMP = 0.4   # alpha ramp at an edge, in field std (was 1.1: edges were ~11 scene px of fringe)
EDGE_DETAIL = 0.06   # weight of the fine field that frays the edges
FINE_LO = 25         # its coarsest wave, in cycles per strip height (lower = bigger wisps)
SS = 2   # the strip is rendered at SS x the scene size (tests/weather/test_clouds.py)


def _field(shape, seed, stretch, beta, lo=2.0):
    """Fractal noise (power-law spectrum). The FFT makes it periodic, so the strip wraps.
    Frequencies count cycles per strip, so the shape does not depend on the pixel size."""
    H, W = shape
    rng = np.random.default_rng(seed)
    ky = np.fft.fftfreq(H)[:, None] * H; kx = np.fft.fftfreq(W)[None, :] * W
    k = np.sqrt((kx * stretch) ** 2 + ky ** 2); k[0, 0] = 1
    amp = 1 / np.maximum(k, lo) ** (beta / 2); amp[0, 0] = 0
    f = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((H, W))) * amp))
    return (f - f.mean()) / f.std()


def _blur(a, sigma):
    """Gaussian blur done in frequency space, so it keeps the strip seamless."""
    ky = np.fft.fftfreq(a.shape[0])[:, None]; kx = np.fft.fftfreq(a.shape[1])[None, :]
    return np.real(np.fft.ifft2(np.fft.fft2(a) * np.exp(-2 * (np.pi * sigma) ** 2 * (kx ** 2 + ky ** 2))))


def strip(size, cover, top, under, ymax, seed, stretch=1.6, density=1.0, lo=4.0, deck=False):
    """An RGBA array (H, W, 4) of clouds for a scene of size (W, H). Fractal billows; light
    comes from above and fades with the cloud mass it has passed through, so tops are bright
    and bellies grey, and the billow texture re-lights the bumps. cover: share of sky (0..1);
    ymax: lowest cloud line as a fraction of the height; top/under: lit and shaded colours;
    deck: a closed overcast layer."""
    W, H = round(size[0] * SS), round(size[1] * SS)
    shape = (H, W)
    f = 0.8 * _field(shape, seed, stretch, 3.6, lo=lo) + 0.2 * _field(shape, seed + 1, stretch * 0.8, 3.0, lo=10)
    # fine detail, so a sharp edge frays into wisps instead of a smooth cut-out outline
    fine = _field(shape, seed + 3, stretch * 0.7, 2.2, lo=FINE_LO)
    f = f + EDGE_DETAIL * fine
    yy = np.linspace(0, 1, H)[:, None]
    f = f - 2.2 * np.clip((yy - ymax * 0.5) / (ymax * 0.5 + 1e-6), 0, 1)   # thin out towards ymax
    th = np.quantile(f, 1 - cover)
    a = np.clip((f - th) / EDGE_RAMP, 0, 1); a = _blur(a * a * (3 - 2 * a), 0.5 * SS).clip(0, 1)
    billow = _blur(_field(shape, seed + 2, stretch * 0.9, 3.0, lo=12) + 0.35 * fine, 0.5 * SS)
    billow = np.clip(billow * 0.3 + 0.5, 0, 1)
    if deck:
        a = np.clip(0.82 + 0.25 * (f - f.mean()) / f.std(), 0.55, 1)
    mass = np.zeros_like(a); acc = np.zeros(W); keep = 0.972 ** (1 / SS)
    for y in range(H):                        # light used up by the cloud above, ~35 scene px memory
        acc = acc * keep + a[y]; mass[y] = acc
    light = np.exp(-mass / ((10 if not deck else 26) * SS)) * (0.55 + 0.45 * billow) + 0.22 * billow
    if not deck:
        light = light + 0.35 * (1 - a)       # thin edges let the light through
    shade = 1 - np.clip(light, 0, 1)
    rgb = np.array(top)[None, None] * (1 - shade[..., None]) + np.array(under)[None, None] * shade[..., None]
    return np.dstack([rgb, a * 255 * density]).clip(0, 255).astype(np.uint8)
