"""Render the 'on the glass' loops: drops and snowflakes landing on the screen and melting away.

    python3 glass.py out/

Writes glass-<kind>.webp (looping animated WebP with alpha) and glass-<kind>-still.png (one
frame, for prefers-reduced-motion) for kind in rain, pour, snow, sleet. The loop is seamless:
every drop's age is taken modulo the loop length.
"""
import os, sys, math, random
import numpy as np
from PIL import Image, ImageDraw, ImageFilter

out = sys.argv[1]; os.makedirs(out, exist_ok=True)
W, H = 600, 413          # same aspect as the scenes (900x620)
FPS, LOOP = 12, 8.0      # seconds
N = int(FPS * LOOP)
SS = 4                   # supersampling for the sprites


def drop_sprite(r):
    """A water drop on glass: faint body, darker lower rim, bright upper-left highlight."""
    s = int(r * 2 * SS + 8 * SS); c = s / 2; R = r * SS
    y, x = np.mgrid[0:s, 0:s]
    dx, dy = (x - c) / R, (y - c) / (R * 1.08)
    d = np.sqrt(dx ** 2 + dy ** 2)
    inside = d < 1
    a = np.zeros((s, s)); rgb = np.zeros((s, s, 3))
    a[inside] = 0.16 + 0.10 * d[inside] ** 3                       # body: clearer in the middle
    rim = inside & (d > 0.78) & (dy > -0.2)                         # lower rim catches dark
    a[rim] = np.maximum(a[rim], 0.45 * (d[rim] - 0.78) / 0.22)
    rgb[...] = 235
    rgb[rim] = 40
    hl = np.sqrt((dx + 0.38) ** 2 + (dy + 0.42) ** 2) < 0.22          # specular highlight
    a[hl] = 0.85; rgb[hl] = 255
    shadow = (np.sqrt(dx ** 2 + (dy - 0.18) ** 2) < 1.12) & ~inside  # soft contact shadow below
    a[shadow] = np.maximum(a[shadow], 0.10)
    rgb[shadow] = 0
    im = Image.fromarray(np.dstack([rgb, a * 255]).astype(np.uint8), 'RGBA')
    return im.filter(ImageFilter.GaussianBlur(SS * 0.5)).resize((s // SS, s // SS), Image.LANCZOS)


def flake_sprite(r):
    s = int(r * 2 * SS + 6 * SS); c = s / 2; R = r * SS
    im = Image.new('RGBA', (s, s), (255, 255, 255, 0)); d = ImageDraw.Draw(im)
    for k in range(6):
        ang = math.pi / 3 * k + math.pi / 6
        ex, ey = c + R * math.cos(ang), c + R * math.sin(ang)
        d.line((c, c, ex, ey), fill=(255, 255, 255, 235), width=max(1, int(SS * 1.1)))
        for f in (0.45, 0.7):                                       # side branches
            bx, by = c + R * f * math.cos(ang), c + R * f * math.sin(ang)
            for side in (-1, 1):
                a2 = ang + side * math.pi / 4
                d.line((bx, by, bx + R * 0.28 * math.cos(a2), by + R * 0.28 * math.sin(a2)),
                       fill=(255, 255, 255, 220), width=max(1, int(SS * 0.8)))
    d.ellipse((c - SS * 1.5, c - SS * 1.5, c + SS * 1.5, c + SS * 1.5), fill=(255, 255, 255, 255))
    im = im.filter(ImageFilter.GaussianBlur(SS * 0.35)).resize((s // SS, s // SS), Image.LANCZOS)
    # a faint dark halo so a white flake still reads on a pale sky
    halo = Image.new('RGBA', im.size, (0, 0, 0, 0)); halo.putalpha(im.getchannel('A').point(lambda v: v * 0.35))
    halo = halo.filter(ImageFilter.GaussianBlur(1.5)); halo.alpha_composite(im)
    return halo


_CACHE = {}


def scaled(sprite, k, alpha):
    k, alpha = round(k * 20) / 20, round(alpha * 20) / 20     # quantise, so frames share resizes
    key = (id(sprite), k, alpha)
    if key not in _CACHE:
        _CACHE[key] = _scaled(sprite, k, alpha)
    return _CACHE[key]


def _scaled(sprite, k, alpha):
    w = max(1, int(sprite.width * k)); h = max(1, int(sprite.height * k))
    im = sprite.resize((w, h), Image.LANCZOS)
    if alpha < 1:
        im.putalpha(im.getchannel('A').point(lambda v: int(v * alpha)))
    return im


def events(kind, seed):
    """(birth s, x, y, type, size, life s, slide px)"""
    rnd = random.Random(seed)
    rate = {'rain': 0.9, 'pour': 2.0, 'snow': 1.0, 'sleet': 1.0}[kind]   # per second
    ev = []
    for i in range(int(rate * LOOP)):
        t = rnd.uniform(0, LOOP)
        typ = 'flake' if kind == 'snow' or (kind == 'sleet' and rnd.random() < 0.5) else 'drop'
        size = rnd.choice((10, 12, 14)) if typ == 'flake' else rnd.choice((6, 7, 8, 10, 12))
        life = rnd.uniform(2.5, 4.5)
        slide = rnd.uniform(30, 80) if typ == 'drop' and size >= 8 and rnd.random() < 0.35 else 0
        ev.append((t, rnd.uniform(10, W - 10), rnd.uniform(10, H * 0.9), typ, size, life, slide))
    return ev


DROPS = {r: drop_sprite(r) for r in (5, 6, 7, 8, 10, 12)}
FLAKES = {}


def frame(ev, t):
    im = Image.new('RGBA', (W, H), (255, 255, 255, 0))
    for (b, x, y, typ, size, life, slide) in ev:
        age = (t - b) % LOOP
        if age >= life:
            continue
        u = age / life
        if typ == 'drop':
            k = min(1.0, 0.35 + age / 0.12)                     # splat in
            a = 1.0 if u < 0.7 else max(0.0, 1 - (u - 0.7) / 0.3)
            k *= 1 - 0.3 * max(0.0, (u - 0.7) / 0.3)          # evaporate: shrink as it fades
            yy = y + (slide * max(0.0, (age - 1.2)) ** 2 / max(0.01, (life - 1.2) ** 2) if slide and age > 1.2 else 0)
            sp = scaled(DROPS[min(DROPS, key=lambda r: abs(r - size))], k, a)
        else:
            if size not in FLAKES:
                FLAKES[size] = flake_sprite(size)
            melt = max(0.0, (u - 0.35) / 0.4)                  # 0..1 flake -> drop
            gone = max(0.0, (u - 0.8) / 0.2)
            fl = scaled(FLAKES[size], 1 - 0.5 * min(1, melt), (1 - min(1, melt)) * (1 - gone))
            dr = scaled(DROPS[6], 0.6 + 0.4 * min(1, melt), min(1, melt) * (1 - gone))
            sp = Image.new('RGBA', (max(fl.width, dr.width), max(fl.height, dr.height)), (255, 255, 255, 0))
            sp.alpha_composite(dr, ((sp.width - dr.width) // 2, (sp.height - dr.height) // 2))
            sp.alpha_composite(fl, ((sp.width - fl.width) // 2, (sp.height - fl.height) // 2))
            yy = y
        im.alpha_composite(sp, (int(x - sp.width / 2), int(yy - sp.height / 2)))
    return im


for i, kind in enumerate(('rain', 'pour', 'snow', 'sleet')):
    ev = events(kind, 11 + i)
    frames = [frame(ev, n / FPS) for n in range(N)]
    frames[0].save(os.path.join(out, 'glass-%s.webp' % kind), save_all=True, append_images=frames[1:],
                   duration=int(1000 / FPS), loop=0, quality=70, method=6, minimize_size=True)
    frame(ev, 2.0).save(os.path.join(out, 'glass-%s-still.png' % kind), optimize=True)
    print(kind, len(ev), 'events', os.path.getsize(os.path.join(out, 'glass-%s.webp' % kind)) // 1024, 'KB')
