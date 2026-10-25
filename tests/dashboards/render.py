"""Render Home Assistant pages the way a person sees them.

usage: render.py <out.png> <path> [width] [--dark] [--height N] [--strict]
       path like /lovelace/kitchen

Logs in with the guest user's long-lived token (~/guest.key), seeded into the
frontend's localStorage exactly as a normal login would leave it. Prints broken
cards (hui-error-card, found through shadow roots) and console errors, so a card
that failed to load is reported rather than just looking blank.

CI (tests/render/shoot.py) points it elsewhere with HA_URL and HA_TOKEN, freezes the
browser clock with RENDER_FIXED_TIME (ISO 8601), and passes --strict: exit 1 on any
broken card.
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

HA = os.environ.get("HA_URL", "http://localhost:8123")
TOKEN = os.environ.get("HA_TOKEN") or open(os.path.expanduser("~/guest.key")).read().strip()
FIXED_TIME = os.environ.get("RENDER_FIXED_TIME")

out, path = sys.argv[1], sys.argv[2]
width = int(sys.argv[3]) if len(sys.argv) > 3 and sys.argv[3].isdigit() else 390
dark = "--dark" in sys.argv
height = 844
if "--height" in sys.argv:
    height = int(sys.argv[sys.argv.index("--height") + 1])

DEEP_ERRORS = """
() => {
  const found = [];
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      const t = el.tagName.toLowerCase();
      if (t === 'hui-error-card' || t === 'hui-warning') {
        // the nearest config up the tree names the card that broke
        let p = el, cfg = null;
        for (let i = 0; i < 8 && p; i++) {
          if (p._config || p.config) { cfg = p._config || p.config; break; }
          p = p.parentNode || p.host;
        }
        const text = (el.shadowRoot ? el.shadowRoot.textContent : el.textContent).trim().slice(0, 160);
        found.push(((cfg && cfg.type) || '?') + ': ' + text);
      }
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  return found;
}
"""

with sync_playwright() as p:
    b = p.chromium.launch(args=["--no-sandbox"])
    ctx = b.new_context(viewport={"width": width, "height": height}, device_scale_factor=1,
                        color_scheme="dark" if dark else "light")
    ctx.add_init_script("""
        localStorage.setItem('hassTokens', JSON.stringify({
          access_token: %s, token_type: 'Bearer', expires_in: 1e9, refresh_token: '',
          hassUrl: '%s', clientId: '%s/', expires: Date.now() + 1e12 }));
        localStorage.setItem('dockedSidebar', JSON.stringify('always_hidden'));
    """ % (repr(TOKEN), HA, HA))
    page = ctx.new_page()
    if FIXED_TIME:
        from datetime import datetime
        page.clock.set_fixed_time(datetime.fromisoformat(FIXED_TIME))
    console = []
    page.on("console", lambda m: console.append(m.text) if m.type == "error" else None)
    page.goto(HA + path, wait_until="networkidle")
    time.sleep(4)
    errs = page.evaluate(DEEP_ERRORS)
    # Charts animate; on a slow CI runner a full-page shot of Energy outran the 30 s default.
    page.screenshot(path=out, full_page=True, animations="disabled", timeout=120000)
    b.close()

print("rendered", path, "at", width, "px ->", out)
for e in errs:
    print("  CARD ERROR:", e)
for c in console[:15]:
    print("  console:", c[:200])
# A card whose backend cannot exist in the environment, named by type and reported, never
# silently dropped: RENDER_EXPECTED_BROKEN="custom:alarmo-card,..."
expected = tuple(t for t in os.environ.get("RENDER_EXPECTED_BROKEN", "").split(",") if t)
for e in errs:
    for t in expected:
        if e.startswith(t + ":"):
            print("  expected-broken (environment):", t)
if "--strict" in sys.argv and [e for e in errs if not e.startswith(tuple(t + ":" for t in expected))]:
    sys.exit(1)
