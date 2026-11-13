"""Render the Zizkov tower weather scenes as animation layers.

Per scene and day/night: <name>-back.jpg (sky), <name>-clouds.webp (a seamless strip that
drifts) and <name>-front.webp (the tower). Shared tiles: rain-light, rain-heavy, snow-near,
snow-far, wind-day, wind-night (.webp), which tile seamlessly in both directions.

    python3 scenes.py tower.png out/ [WxH] [tower centre x] [tower height]
"""
import sys, os, random, math, numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
tower_png, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
# size WxH and the tower's horizontal centre as a fraction of the width
W, H = (int(v) for v in (sys.argv[3] if len(sys.argv) > 3 else '900x620').split('x'))
TOWER_X = float(sys.argv[4]) if len(sys.argv) > 4 else 0.68
TOWER_H = float(sys.argv[5]) if len(sys.argv) > 5 else 0.98   # tower height / frame height

# keep only the largest connected opaque component (drops floating sculptures cut off from the tower)
t = Image.open(tower_png).convert('RGBA')
a = np.asarray(t)[..., 3] > 128
lab = np.zeros(a.shape, int); cur = 0; sizes = {}
from collections import deque
for y0, x0 in zip(*np.nonzero(a)):
    if lab[y0, x0]: continue
    cur += 1; q = deque([(y0, x0)]); lab[y0, x0] = cur; n = 0
    while q:
        y, x = q.popleft(); n += 1
        for dy, dx in ((1,0),(-1,0),(0,1),(0,-1)):
            ny, nx = y+dy, x+dx
            if 0 <= ny < a.shape[0] and 0 <= nx < a.shape[1] and a[ny, nx] and not lab[ny, nx]:
                lab[ny, nx] = cur; q.append((ny, nx))
    sizes[cur] = n
keep = max(sizes, key=sizes.get)
arr = np.asarray(t).copy(); arr[..., 3] = np.where(lab == keep, arr[..., 3], 0)
tower = Image.fromarray(arr)
th = int(H * TOWER_H); tw = int(tower.width * th / tower.height)
tower = tower.resize((tw, th), Image.LANCZOS)
TX, TY = int(W * TOWER_X - tw / 2), H - th + int(H * 0.04)
_al = np.asarray(tower)[..., 3]; _ty = int(np.nonzero(_al.max(1) > 128)[0][0]); TIP = (TX + int(np.nonzero(_al[_ty + 2] > 128)[0].mean()), TY + _ty)

def grad(top, bot):
    g = np.linspace(0, 1, H)[:, None, None]
    c = np.array(top)[None, None] * (1 - g) + np.array(bot)[None, None] * g
    return Image.fromarray(np.repeat(c, W, 1).astype(np.uint8), 'RGB').convert('RGBA')

def glow(img, cx, cy, r, color, strength):
    y, x = np.mgrid[0:H, 0:W]
    d = np.sqrt((x - cx) ** 2 + (y - cy) ** 2) / r
    al = (np.clip(1 - d, 0, 1) ** 2 * 255 * strength).astype(np.uint8)
    layer = Image.new('RGBA', (W, H), color + (0,)); layer.putalpha(Image.fromarray(al))
    img.alpha_composite(layer)

def disc(img, cx, cy, r, color):
    d = ImageDraw.Draw(img); d.ellipse((cx-r, cy-r, cx+r, cy+r), fill=color)

def _field(seed, stretch, beta, lo=2.0):
    """Fractal noise (power-law spectrum). The FFT makes it periodic, so the strip wraps."""
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

def clouds(img, cover, top, under, ymax, seed, stretch=1.6, density=1.0, lo=4.0, deck=False):
    """Clouds as a seamless strip. Fractal billows; light comes from above and fades with the
    cloud mass it has passed through, so tops are bright and bellies grey, and the billow
    texture re-lights the bumps. cover: share of sky (0..1); ymax: lowest cloud line as a
    fraction of the height; top/under: lit and shaded colours; deck: a closed overcast layer."""
    f = 0.8 * _field(seed, stretch, 3.6, lo=lo) + 0.2 * _field(seed + 1, stretch * 0.8, 3.0, lo=10)
    yy = np.linspace(0, 1, H)[:, None]
    f = f - 2.2 * np.clip((yy - ymax * 0.5) / (ymax * 0.5 + 1e-6), 0, 1)   # thin out towards ymax
    th = np.quantile(f, 1 - cover)
    a = np.clip((f - th) / 1.1, 0, 1); a = _blur(a * a * (3 - 2 * a), 1.2).clip(0, 1)
    billow = _blur(_field(seed + 2, stretch * 0.9, 3.0, lo=12), 1.0); billow = np.clip(billow * 0.3 + 0.5, 0, 1)
    if deck:
        a = np.clip(0.82 + 0.25 * (f - f.mean()) / f.std(), 0.55, 1)
    mass = np.zeros_like(a); acc = np.zeros(W)
    for y in range(H):                        # light used up by the cloud above, ~35 px memory
        acc = acc * 0.972 + a[y]; mass[y] = acc
    light = np.exp(-mass / (10 if not deck else 26)) * (0.55 + 0.45 * billow) + 0.22 * billow
    if not deck:
        light = light + 0.35 * (1 - a)       # thin edges let the light through
    shade = 1 - np.clip(light, 0, 1)
    rgb = np.array(top)[None, None] * (1 - shade[..., None]) + np.array(under)[None, None] * shade[..., None]
    out = np.dstack([rgb, a * 255 * density]).clip(0, 255).astype(np.uint8)
    img.alpha_composite(Image.fromarray(out, 'RGBA'))

def overcast(img, color, alpha, seed, ymax=1.0):
    """A closed deck: alpha never drops below 0.55, but the texture thins towards the bottom,
    as a real deck looks thinner towards the horizon. Intended."""
    c = np.array(color, float)
    clouds(img, 1.0, tuple((c * 1.18).clip(0, 255)), tuple(c * 0.7), ymax, seed, stretch=2.4,
           density=alpha / 255, lo=2.0, deck=True)

def stars(img, seed):
    rnd = random.Random(seed); d = ImageDraw.Draw(img)
    for _ in range(160):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H * 0.75); b = rnd.randint(140, 255); s = rnd.choice((0.6, 0.8, 1.2))
        d.ellipse((x-s, y-s, x+s, y+s), fill=(b, b, min(255, b+20), 255))

def lit_tower(bright, sat, tint=None, tint_amt=0.0):
    t = tower.copy(); al = t.getchannel('A'); rgb = t.convert('RGB')
    rgb = ImageEnhance.Color(rgb).enhance(sat); rgb = ImageEnhance.Brightness(rgb).enhance(bright)
    if tint: rgb = Image.blend(rgb, Image.new('RGB', rgb.size, tint), tint_amt)
    rgb.putalpha(al); return rgb

def aviation(img):
    # red obstruction light at the antenna tip
    cx, cy = TIP[0], TIP[1] + 3
    glow(img, cx, cy, 26, (255, 40, 30), 0.9); disc(img, cx, cy, 3, (255, 90, 80, 255))

T = 400   # precipitation tile, px (shown at half size in CSS, so sharp on 2x screens)

def _tile(draw_fn, blur, color, size=(T, T)):
    tw_, th_ = size
    big = Image.new('RGBA', (3 * tw_, 3 * th_), color + (0,)); d = ImageDraw.Draw(big)
    for kx in (0, 1, 2):
        for ky in (0, 1, 2):
            draw_fn(d, kx * tw_, ky * th_)
    return big.filter(ImageFilter.GaussianBlur(blur)).crop((tw_, th_, 2 * tw_, 2 * th_))

def rain_tile(n, length, alpha, seed, width=2):
    # slant 1/4: the CSS moves the tile (1, 4) tiles per loop, which is seamless
    rnd = random.Random(seed)
    drops = [(rnd.uniform(0, T), rnd.uniform(0, T), length * rnd.uniform(0.6, 1.2),
              int(alpha * rnd.uniform(0.5, 1))) for _ in range(n)]
    def draw(d, ox, oy):
        for x, y, L, a in drops:
            d.line((ox + x, oy + y, ox + x + L * 0.25, oy + y + L), fill=(210, 220, 235, a), width=width)
    return _tile(draw, 0.6, (210, 220, 235))

def snow_tile(n, radii, seed):
    rnd = random.Random(seed)
    flakes = [(rnd.uniform(0, T), rnd.uniform(0, T), rnd.choice(radii), rnd.randint(170, 250)) for _ in range(n)]
    def draw(d, ox, oy):
        for x, y, r, a in flakes:
            d.ellipse((ox+x-r, oy+y-r, ox+x+r, oy+y+r), fill=(255, 255, 255, a))
    return _tile(draw, 0.9, (255, 255, 255))

def wind_tile(seed, color, n=9):
    rnd = random.Random(seed); size = (2 * T, T)
    gusts = [(rnd.uniform(0, 2 * T), rnd.uniform(20, T - 20), rnd.uniform(160, 380), rnd.randint(90, 160)) for _ in range(n)]
    def draw(d, ox, oy):
        for x, y, L, a in gusts:
            pts = [(ox + x + i * L / 20, oy + y + 10 * math.sin(i / 3.2)) for i in range(21)]
            d.line(pts, fill=color + (a,), width=3)
    return _tile(draw, 1.2, color, size)

def lightning(img, seed):
    rnd = random.Random(seed); x, y = int(W*.22), -10; pts = [(x, y)]
    while y < H * 0.85:
        x += rnd.uniform(-45, 45); y += rnd.uniform(30, 60); pts.append((x, y))
    layer = Image.new('RGBA', (W, H), (200, 210, 255, 0)); d = ImageDraw.Draw(layer)
    d.line(pts, fill=(200, 210, 255, 255), width=14); halo = layer.filter(ImageFilter.GaussianBlur(18))
    img.alpha_composite(halo); d2 = ImageDraw.Draw(img); d2.line(pts, fill=(250, 250, 255, 255), width=4)

def wind(img, seed, color):
    rnd = random.Random(seed); layer = Image.new('RGBA', (W, H), color + (0,)); d = ImageDraw.Draw(layer)
    for _ in range(14):
        x, y, L = rnd.uniform(-50, W * 0.8), rnd.uniform(40, H - 40), rnd.uniform(160, 380)
        pts = [(x + i * L / 20, y + 10 * math.sin(i / 3.2)) for i in range(21)]
        d.line(pts, fill=color + (rnd.randint(90, 160),), width=3)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(1.2)))

def fog(img, color, top_a, bot_a):
    g = np.linspace(top_a, bot_a, H)[:, None]
    al = np.repeat(g, W, 1) * 255
    layer = Image.new('RGBA', (W, H), color + (0,)); layer.putalpha(Image.fromarray(al.astype(np.uint8)))
    img.alpha_composite(layer)

def render(scene, night):
    """Three layers: back (sky, sun/moon, stars, bolt), clouds (seamless strip), front
    (tower, fog, obstruction light). Precipitation and wind come from the shared tiles."""
    R = 7  # seed
    cl = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    front = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    if scene in ('sunny', 'partlycloudy', 'windy'):
        sky = grad((14, 22, 52), (40, 58, 102)) if night else grad((38, 110, 205), (150, 200, 240))
        # no sun or moon: the card's own icon sits top left and already shows which
        if night: stars(sky, R)
        # at night clouds over the city are lit from below (orange street light), not from above
        top, under = ((52, 58, 78), (82, 74, 80)) if night else ((255, 255, 255), (150, 158, 176))
        if scene == 'partlycloudy': clouds(cl, 0.38, top, under, 0.62, R, density=0.85 if night else 1.0)
        if scene == 'windy': clouds(cl, 0.28, top, under, 0.7, R, stretch=4.0, density=0.85)
        front.alpha_composite(lit_tower(0.38, 0.4, (30, 40, 90), 0.25) if night else lit_tower(1.0, 1.0), (TX, TY))
    elif scene == 'cloudy':
        sky = grad((28, 32, 44), (52, 56, 70)) if night else grad((138, 148, 162), (196, 202, 210))
        overcast(cl, (60, 64, 78) if night else (222, 225, 230), 220, R)
        front.alpha_composite(lit_tower(0.33, 0.3, (30, 35, 60), 0.2) if night else lit_tower(0.86, 0.45), (TX, TY))
    elif scene in ('rainy', 'pouring', 'storm', 'sleet'):
        dark = scene in ('pouring', 'storm')
        if night: sky = grad((14, 16, 24), (34, 38, 50))
        else: sky = grad((70, 76, 88), (122, 128, 140)) if dark else grad((104, 112, 126), (160, 166, 176))
        overcast(cl, (40, 44, 56) if night else ((96, 100, 112) if dark else (150, 156, 166)), 230, R)
        if scene == 'storm': lightning(sky, R)
        front.alpha_composite(lit_tower(0.3, 0.25, (25, 30, 50), 0.2) if night else lit_tower(0.66 if dark else 0.76, 0.35), (TX, TY))
        if dark: fog(front, (120, 128, 140) if not night else (40, 44, 56), 0.05, 0.3)
    elif scene == 'snowy':
        sky = grad((40, 44, 58), (78, 82, 96)) if night else grad((128, 138, 154), (186, 192, 202))
        overcast(cl, (80, 84, 100) if night else (176, 182, 192), 210, R)
        front.alpha_composite(lit_tower(0.42, 0.25, (40, 50, 90), 0.2) if night else lit_tower(0.95, 0.3), (TX, TY))
    elif scene == 'fog':
        sky = grad((40, 44, 52), (66, 70, 78)) if night else grad((190, 194, 198), (220, 222, 224))
        front.alpha_composite(lit_tower(0.38, 0.2) if night else lit_tower(0.9, 0.25), (TX, TY))
        fog(front, (70, 74, 82) if night else (226, 228, 230), 0.55, 0.3)
    if night: aviation(front)
    name = f"{scene}-{'night' if night else 'day'}"
    sky.convert('RGB').save(os.path.join(outdir, name + '-back.jpg'), quality=84, optimize=True, progressive=True)
    if cl.getbbox(): cl.save(os.path.join(outdir, name + '-clouds.webp'), quality=82)
    front.save(os.path.join(outdir, name + '-front.webp'), quality=88)

SCENES = ['sunny', 'partlycloudy', 'cloudy', 'rainy', 'pouring', 'storm', 'snowy', 'sleet', 'fog', 'windy']
for s in SCENES:
    for n in (False, True): render(s, n)

R = 7
tiles = {
    'rain-light': rain_tile(26, 60, 170, R),
    'rain-heavy': rain_tile(70, 85, 200, R + 1),
    'snow-near': snow_tile(22, (4, 5, 6.5), R + 2),
    'snow-far': snow_tile(60, (2, 2.5, 3), R + 3),
    'wind-day': wind_tile(R, (230, 235, 245)),
    'wind-night': wind_tile(R, (150, 160, 190)),
}
for k, im in tiles.items():
    im.save(os.path.join(outdir, k + '.webp'), quality=85)
