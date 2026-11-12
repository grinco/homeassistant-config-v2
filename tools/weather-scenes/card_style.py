"""Print the card_mod style for the animated Home weather card.

    python3 card_style.py [version] > style.jinja

The style picks the scene from sensor.weather_ahead (scene, daytime) and stacks:
  ha-card background   <scene>-<dn>-back.jpg            still sky
  ha-card::before      <scene>-<dn>-clouds.webp         strip drifting left (transform)
  ha-card::after       precipitation tiles, scrim,      tiles move (background-position),
                       <scene>-<dn>-front.webp          tower and scrim stay put
  topmost in ::after   glass-<kind>.webp                drops/flakes landing on the screen
                                                          (an animated WebP; it loops by itself)
Everything stops under prefers-reduced-motion: the glass swaps to a still frame.
"""
import sys

V = sys.argv[1] if len(sys.argv) > 1 else '4'
URL = "/local/zizkov/anim/%s.%s?v=" + V
TILE = 200            # CSS px a 400 px tile is shown at
STOPS = (0, 25, 50, 75, 100)

# per-layer motion over one loop: (dx tiles, dy tiles, sway px at 25%/75%)
RAIN_L, RAIN_H = ('rain-light', (1, 4, 0)), ('rain-heavy', (1, 4, 0))
SCENES = {
    #             clouds drift (s)  loop (s)  layers, front to back
    'sunny':        (0,   0, []),
    'partlycloudy': (90,  0, []),
    'cloudy':       (160, 0, []),
    'fog':          (0,   0, []),
    'windy':        (30,  3, [('wind-DN', (2, 0, 0))]),
    'rainy':        (160, 1.4, [RAIN_L]),
    'pouring':      (160, 2, [('rain-heavy', (2, 8, 0)), ('rain-light', (1, 4, 0))]),
    'storm':        (160, 2, [('rain-heavy', (2, 8, 0)), ('rain-light', (1, 4, 0))]),
    'sleet':        (160, 4, [('rain-light', (2, 8, 0)), ('snow-near', (0, 1, 10))]),
    'snowy':        (160, 10, [('snow-near', (0, 2, 14)), ('snow-far', (0, 1, 6))]),
}


GLASS = {'rainy': 'rain', 'pouring': 'pour', 'storm': 'pour', 'snowy': 'snow', 'sleet': 'sleet'}


def css(scene):
    drift, loop, layers = SCENES[scene]
    glass = GLASS.get(scene)
    base = scene + '-DN'
    out = []
    out.append("ha-card { background: url('%s') center / cover no-repeat !important; }" % (URL % (base + '-back', 'jpg')))
    if drift:
        anim = 'wx-drift %ds linear infinite' % drift
        if scene == 'storm':
            anim += ', wx-flash 7s linear infinite'
        out.append("ha-card::before { content: ''; position: absolute; top: 0; bottom: 0; left: 0; width: 200%%; z-index: 0; "
                   "pointer-events: none; background: url('%s') 0 0 / 50%% 100%% repeat-x; animation: %s; will-change: transform; }"
                   % (URL % (base + '-clouds', 'webp'), anim))
    imgs, sizes, reps, pos0 = [], [], [], []
    if glass:
        imgs.append("url('%s')" % (URL % ('glass-' + glass, 'webp')))
        sizes.append('cover'); reps.append('no-repeat'); pos0.append('center')
    for name, _ in layers:
        imgs.append("url('%s')" % (URL % (name, 'webp')))
        w = 2 * TILE if name.startswith('wind') else TILE
        sizes.append('%dpx %dpx' % (w, TILE)); reps.append('repeat'); pos0.append('0 0')
    imgs += ["linear-gradient(180deg, rgba(0,0,0,.42) 0%, rgba(0,0,0,.12) 38%, rgba(0,0,0,.18) 55%, rgba(0,0,0,.62) 100%)",
             "url('%s')" % (URL % (base + '-front', 'webp'))]
    sizes += ['100% 100%', 'cover']; reps += ['no-repeat', 'no-repeat']; pos0 += ['0 0', 'center']
    after = ("ha-card::after { content: ''; position: absolute; inset: 0; z-index: 1; pointer-events: none; "
             "background-image: %s; background-size: %s; background-repeat: %s; background-position: %s;"
             % (', '.join(imgs), ', '.join(sizes), ', '.join(reps), ', '.join(pos0)))
    if layers:
        after += ' animation: wx-fall-%s %ss linear infinite;' % (scene, loop)
        frames = []
        for st in STOPS:
            f = st / 100.0
            ps = []
            for name, (dx, dy, sway) in layers:
                w = 2 * TILE if name.startswith('wind') else TILE
                x = dx * w * f + (sway if st in (25,) else -sway if st == 75 else 0)
                ps.append('%gpx %gpx' % (x, dy * TILE * f))
            frames.append('%d%% { background-position: %s%s, 0 0, center; }'
                          % (st, 'center, ' if glass else '', ', '.join(ps)))
        out.append(after + ' }')
        out.append('@keyframes wx-fall-%s { %s }' % (scene, ' '.join(frames)))
    else:
        out.append(after + ' }')
    if glass:
        still = "url('%s')" % (URL % ('glass-%s-still' % glass, 'png'))
        out.append('@media (prefers-reduced-motion: reduce) { ha-card::after { background-image: %s; } }'
                   % ', '.join([still] + imgs[1:]))
    return ' '.join(out)


COMMON = """{% set a = states.sensor.weather_ahead.attributes if states.sensor.weather_ahead is not none else {} %}
{% set sc = a.get('scene') if a.get('scene') in FX else 'cloudy' %}
{% set dn = 'day' if (a.get('daytime') if a.get('daytime') in [true, false] else is_state('sun.sun', 'above_horizon')) else 'night' %}
{% set words = {'clear-night': 'clear', 'sunny': 'sunny', 'partlycloudy': 'partly cloudy', 'cloudy': 'cloudy', 'fog': 'fog', 'rainy': 'rain', 'pouring': 'heavy rain', 'lightning': 'thunder', 'lightning-rainy': 'thunderstorms', 'hail': 'hail', 'snowy': 'snow', 'snowy-rainy': 'sleet', 'windy': 'windy', 'windy-variant': 'windy', 'exceptional': 'unusual weather'} %}
{% set ahead = words.get(states('sensor.weather_ahead')) %}
ha-card {
  position: relative; overflow: hidden; isolation: isolate;
  --primary-text-color: #fff;
  --secondary-text-color: rgba(255,255,255,.88);
  color: #fff;
  text-shadow: 0 1px 4px rgba(0,0,0,.75);
}
ha-card > * { position: relative; z-index: 2; }
{{ FX[sc] | replace('DN', dn) }}
@keyframes wx-drift { from { transform: translateX(0); } to { transform: translateX(-50%); } }
@keyframes wx-flash { 0%, 86%, 89%, 92%, 100% { filter: brightness(1); } 87% { filter: brightness(2.4); } 90.5% { filter: brightness(1.9); } }
@media (prefers-reduced-motion: reduce) { ha-card::before, ha-card::after { animation: none !important; } }
{% if ahead %}.name { font-size: 0 !important; }
.name::after { content: 'Next 3 h: {{ ahead }}'; font-size: var(--ha-font-size-m, 14px); }{% endif %}"""

fx = '{' + ', '.join("'%s': \"%s\"" % (k, css(k)) for k in SCENES) + '}'
print(('{% set FX = ' + fx + ' %}\n' + COMMON).replace('FX', 'fx'))
