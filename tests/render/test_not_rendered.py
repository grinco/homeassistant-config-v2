#!/usr/bin/env python3
"""render.py must refuse to publish Home Assistant's loading screen.

On 2026-10-28 the published home-390.png was the launch splash ("Loading..."): the first
render after Home Assistant starts hit a cold frontend, and the broken-card check finds
nothing wrong on a splash, so the run passed. This serves two pages to render.py:

- the launch screen and nothing else: render.py --strict must fail and say why;
- a drawn view with a card in it: render.py --strict must pass (the check is not just "fail").

    python3 tests/render/test_not_rendered.py
"""

import http.server
import os
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
RENDER = os.path.join(HERE, "..", "dashboards", "render.py")

SPLASH = b"""<!doctype html><html><body>
<div id="ha-launch-screen"><div class="ha-launch-screen-spacer-top"></div>
<div id="ha-launch-screen-info-box">Loading...</div></div></body></html>"""

DRAWN = b"""<!doctype html><html><body>
<home-assistant></home-assistant>
<script>
  const root = document.querySelector('home-assistant').attachShadow({mode: 'open'});
  root.innerHTML = '<hui-sections-view><hui-card><ha-card>Living room</ha-card></hui-card></hui-sections-view>';
</script></body></html>"""


def serve(body):
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def render(body):
    srv = serve(body)
    try:
        out = os.path.join(tempfile.mkdtemp(), "shot.png")
        env = dict(os.environ, HA_URL="http://127.0.0.1:%d" % srv.server_port, HA_TOKEN="test",
                   RENDER_READY_TIMEOUT="6")
        return subprocess.run([sys.executable, RENDER, out, "/lovelace/home", "390", "--strict"],
                              env=env, capture_output=True, text=True, timeout=120)
    finally:
        srv.shutdown()


def main():
    bad = 0
    p = render(SPLASH)
    if p.returncode == 0 or "NOT RENDERED" not in p.stdout:
        bad += 1
        print("  FAIL  the loading screen was accepted (exit %d)\n%s" % (p.returncode, p.stdout[-400:]))
    else:
        print("  ok    the loading screen is refused")
    p = render(DRAWN)
    if p.returncode != 0:
        bad += 1
        print("  FAIL  a drawn view was refused (exit %d)\n%s%s" % (p.returncode, p.stdout[-400:], p.stderr[-400:]))
    else:
        print("  ok    a drawn view is accepted")
    print("\n%d/2 passed" % (2 - bad))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
