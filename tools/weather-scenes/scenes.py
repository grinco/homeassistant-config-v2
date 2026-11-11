"""Render the Zizkov tower weather scenes: <scene>-<day|night>.jpg"""
import sys, os, random, math, numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageEnhance, ImageChops
tower_png, outdir = sys.argv[1], sys.argv[2]
os.makedirs(outdir, exist_ok=True)
# size WxH and the tower's horizontal centre as a fraction of the width
W, H = (int(v) for v in (sys.argv[3] if len(sys.argv) > 3 else '900x620').split('x'))
TOWER_X = float(sys.argv[4]) if len(sys.argv) > 4 else 0.5

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
th = int(H * 1.12); tw = int(tower.width * th / tower.height)
tower = tower.resize((tw, th), Image.LANCZOS)
TX, TY = int(W * TOWER_X - tw / 2), int(H * 0.04)
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

def clouds(img, n, color, ymax, alpha, seed, stretch=1.0, size=1.0):
    rnd = random.Random(seed)
    layer = Image.new('RGBA', (W, H), color + (0,)); d = ImageDraw.Draw(layer)
    for _ in range(n):
        cx, cy = rnd.uniform(-100, W + 100), rnd.uniform(-40, ymax)
        for _ in range(rnd.randint(5, 9)):
            rx = rnd.uniform(40, 110) * stretch * size; ry = rnd.uniform(25, 60) * size
            ox, oy = rnd.uniform(-120, 120) * stretch * size, rnd.uniform(-25, 20) * size
            shade = rnd.uniform(0.9, 1.05)
            c = tuple(int(min(255, v * shade)) for v in color)
            d.ellipse((cx+ox-rx, cy+oy-ry, cx+ox+rx, cy+oy+ry), fill=c + (alpha,))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(14)))

def overcast(img, color, alpha, seed, ymax=H):
    clouds(img, 26, color, ymax, alpha, seed, stretch=1.6, size=1.3)

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

def rain(img, n, length, alpha, seed, slant=0.22, width=2):
    rnd = random.Random(seed); layer = Image.new('RGBA', (W, H), (210, 220, 235, 0)); d = ImageDraw.Draw(layer)
    for _ in range(n):
        x, y = rnd.uniform(-100, W), rnd.uniform(-length, H); L = length * rnd.uniform(0.6, 1.2)
        d.line((x, y, x + L * slant, y + L), fill=(210, 220, 235, int(alpha * rnd.uniform(0.5, 1))), width=width)
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.6)))

def snow(img, n, seed, wet=False):
    rnd = random.Random(seed); layer = Image.new('RGBA', (W, H), (255, 255, 255, 0)); d = ImageDraw.Draw(layer)
    for _ in range(n):
        x, y = rnd.uniform(0, W), rnd.uniform(0, H); r = rnd.choice((1.5, 2, 2.5, 3.5, 4.5))
        d.ellipse((x-r, y-r, x+r, y+r), fill=(255, 255, 255, rnd.randint(170, 250)))
    img.alpha_composite(layer.filter(ImageFilter.GaussianBlur(0.9)))

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
    R = 7  # seed
    if scene in ('sunny', 'partlycloudy', 'windy'):
        sky = grad((14, 22, 52), (40, 58, 102)) if night else grad((38, 110, 205), (150, 200, 240))
        if night: stars(sky, R); disc(sky, int(W*.18), int(H*.2), 34, (245, 240, 220, 255)); glow(sky, int(W*.18), int(H*.2), 140, (200, 210, 255), 0.35)
        else: glow(sky, int(W*.18), int(H*.2), 380, (255, 245, 200), 0.85); disc(sky, int(W*.18), int(H*.2), 48, (255, 252, 235, 255))
        if scene == 'partlycloudy': clouds(sky, 6, (70, 80, 110) if night else (250, 250, 252), H * 0.6, 235, R)
        if scene == 'windy': clouds(sky, 7, (70, 80, 110) if night else (245, 247, 250), H * 0.7, 200, R, stretch=2.6, size=0.7)
        tow = lit_tower(0.38, 0.4, (30, 40, 90), 0.25) if night else lit_tower(1.0, 1.0)
        sky.alpha_composite(tow, (TX, TY))
        if scene == 'windy': wind(sky, R, (230, 235, 245) if not night else (150, 160, 190))
    elif scene == 'cloudy':
        sky = grad((28, 32, 44), (52, 56, 70)) if night else grad((138, 148, 162), (196, 202, 210))
        overcast(sky, (60, 64, 78) if night else (222, 225, 230), 220, R)
        sky.alpha_composite(lit_tower(0.33, 0.3, (30, 35, 60), 0.2) if night else lit_tower(0.86, 0.45), (TX, TY))
    elif scene in ('rainy', 'pouring', 'storm', 'sleet'):
        dark = scene in ('pouring', 'storm')
        if night: sky = grad((14, 16, 24), (34, 38, 50))
        else: sky = grad((70, 76, 88), (122, 128, 140)) if dark else grad((104, 112, 126), (160, 166, 176))
        overcast(sky, (40, 44, 56) if night else ((96, 100, 112) if dark else (150, 156, 166)), 230, R)
        if scene == 'storm': lightning(sky, R)
        sky.alpha_composite(lit_tower(0.3, 0.25, (25, 30, 50), 0.2) if night else lit_tower(0.66 if dark else 0.76, 0.35), (TX, TY))
        if scene == 'sleet': rain(sky, 220, 30, 150, R); snow(sky, 160, R + 1)
        else: rain(sky, 900 if dark else 380, 55 if dark else 38, 200 if dark else 170, R, width=2)
        if dark: fog(sky, (120, 128, 140) if not night else (40, 44, 56), 0.05, 0.3)
    elif scene == 'snowy':
        sky = grad((40, 44, 58), (78, 82, 96)) if night else grad((128, 138, 154), (186, 192, 202))
        overcast(sky, (80, 84, 100) if night else (176, 182, 192), 210, R)
        sky.alpha_composite(lit_tower(0.42, 0.25, (40, 50, 90), 0.2) if night else lit_tower(0.95, 0.3), (TX, TY))
        snow(sky, 520, R)
    elif scene == 'fog':
        sky = grad((40, 44, 52), (66, 70, 78)) if night else grad((190, 194, 198), (220, 222, 224))
        sky.alpha_composite(lit_tower(0.38, 0.2) if night else lit_tower(0.9, 0.25), (TX, TY))
        fog(sky, (70, 74, 82) if night else (226, 228, 230), 0.55, 0.3)
    if night: aviation(sky)
    sky.convert('RGB').save(os.path.join(outdir, f"{scene}-{'night' if night else 'day'}.jpg"), quality=82, optimize=True, progressive=True)

SCENES = ['sunny', 'partlycloudy', 'cloudy', 'rainy', 'pouring', 'storm', 'snowy', 'sleet', 'fog', 'windy']
for s in SCENES:
    for n in (False, True): render(s, n)
