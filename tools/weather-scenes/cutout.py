import sys, numpy as np
from PIL import Image, ImageFilter
from collections import deque
src, out = sys.argv[1], sys.argv[2]
im = np.asarray(Image.open(src).convert('RGB')).astype(int)
r,g,b = im[...,0], im[...,1], im[...,2]
h,w = r.shape
sky = (b - r > 35) & (b > g)          # saturated blue
loose = (b - r > int(sys.argv[3]) if len(sys.argv)>3 else 18) & (b >= g)
# flood fill sky from the top/side edges only
seen = np.zeros((h,w),bool); q=deque()
for x in range(w):
  for y0 in (0,h-1):
    if sky[y0,x] and not seen[y0,x]: q.append((y0,x)); seen[y0,x]=True
for y in range(h):
    for x in (0,w-1):
        if sky[y,x] and not seen[y,x]: q.append((y,x)); seen[y,x]=True
while q:
    y,x=q.popleft()
    for dy,dx in ((1,0),(-1,0),(0,1),(0,-1)):
        ny,nx=y+dy,x+dx
        if 0<=ny<h and 0<=nx<w and loose[ny,nx] and not seen[ny,nx]:
            seen[ny,nx]=True; q.append((ny,nx))
alpha = np.where(seen,0,255).astype(np.uint8)
a = Image.fromarray(alpha).filter(ImageFilter.MinFilter(3)).filter(ImageFilter.GaussianBlur(0.8))
# defringe: pull blue cast out of the tower (it's grey/white concrete)
rgb = im.copy()
grey = (r+g+b)//3
blue = (b - r) > 12
for c in range(3):
    rgb[...,c] = np.where(blue & ~seen, (rgb[...,c]*0.3 + grey*0.7).astype(int), rgb[...,c])
o = Image.fromarray(rgb.clip(0,255).astype(np.uint8)); o.putalpha(a)
bbox = o.getbbox(); o = o.crop(bbox); o.save(out); print(o.size, bbox)
