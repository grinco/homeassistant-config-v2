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

It shoots only a drawn dashboard view - the launch screen gone and a view with a card in
it - checked just before and just after the shot, because the frontend can reload itself
back to the splash after its first draw. If no such shot is taken within
RENDER_READY_TIMEOUT seconds (default 90) it prints NOT RENDERED and exits 2; it never
publishes the loading screen (2026-10-28: Home was published as the splash, twice).
"""
import os
import sys
import time

from playwright.sync_api import sync_playwright

HA = os.environ.get("HA_URL", "http://localhost:8123")
TOKEN = os.environ.get("HA_TOKEN") or open(os.path.expanduser("~/guest.key")).read().strip()
FIXED_TIME = os.environ.get("RENDER_FIXED_TIME")
READY_TIMEOUT = float(os.environ.get("RENDER_READY_TIMEOUT", "90"))

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

# Drawn = no launch screen left, and a Lovelace view (through shadow roots) holding a card.
DRAWN = """
() => {
  if (document.getElementById('ha-launch-screen')) return false;
  const VIEWS = ['hui-sections-view', 'hui-masonry-view', 'hui-panel-view', 'hui-sidebar-view'];
  let ok = false;
  const walk = (root) => {
    for (const el of root.querySelectorAll('*')) {
      if (ok) return;
      if (VIEWS.includes(el.tagName.toLowerCase())) {
        const inside = el.shadowRoot || el;
        if (inside.querySelector('hui-card, ha-card, hui-section, hui-grid-section') ||
            el.querySelector('hui-card, ha-card, hui-section, hui-grid-section')) { ok = true; return; }
      }
      if (el.shadowRoot) walk(el.shadowRoot);
    }
  };
  walk(document);
  return ok;
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
    # The frontend can reload itself after its first draw, back to the splash; "it drew
    # once" is not enough. A shot counts only when the view is drawn just before AND just
    # after it; otherwise wait for it to draw again and retake, until the deadline.
    deadline = time.monotonic() + READY_TIMEOUT
    shot = False
    while not shot and time.monotonic() < deadline:
        try:
            page.wait_for_function(DRAWN, timeout=max(1, deadline - time.monotonic()) * 1000, polling=500)
        except Exception:  # Playwright's TimeoutError
            break
        time.sleep(4)   # cards settle (images, charts) after the view exists
        if not page.evaluate(DRAWN):
            continue
        errs = page.evaluate(DEEP_ERRORS)
        # Charts animate; on a slow CI runner a full-page shot of Energy outran the 30 s default.
        page.screenshot(path=out, full_page=True, animations="disabled", timeout=120000)
        shot = page.evaluate(DRAWN)
    b.close()
    if not shot:
        if os.path.exists(out):
            os.remove(out)   # never leave a splash behind for a publisher to pick up
        print("rendered", path, "at", width, "px -> nothing")
        print("  NOT RENDERED: no stable drawn view (loading screen) within %ds" % READY_TIMEOUT)
        sys.exit(2)

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
