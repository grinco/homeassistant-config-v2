#!/usr/bin/env python3
"""Render the household dashboard's main pages at phone and desktop width.

    shoot.py <url> <config-dir> <out-dir>

Exit 1 if any page has a broken card (hui-error-card): that is the end-to-end test.
The browser clock is frozen so frontend-computed times do not move between runs;
server-side Jinja still reads the real clock (design, Part 3, known limit).
"""

import os
import subprocess
from datetime import datetime, timezone
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
RENDER = os.path.join(REPO, "tests", "dashboards", "render.py")
sys.path.insert(0, HERE)
from bootstrap import token  # noqa: E402

# CI renders the synthetic house: Home and one room page. A local run against the real-data
# fixture can ask for every tab: RENDER_PAGES=home,climate,energy,appliances,security,...
PAGES = tuple(os.environ.get("RENDER_PAGES", "home,living-room").split(","))
WIDTHS = (390, 1280)
# Frozen at the moment the run starts, not at a fixed date: states are stamped "now" by the
# seed, and a clock months behind them printed "In 9 months" on every occupancy tile.
FIXED_TIME = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
# Cards whose backend cannot run here. alarmo-card talks to the Alarmo integration over
# its own websocket API; Alarmo needs the house's alarm configuration, which is not and
# will not be in the fixtures. Exempt by card TYPE only, and every exemption is printed.
EXPECTED_BROKEN = ("custom:alarmo-card",)


def main():
    url, cfg, out = sys.argv[1], sys.argv[2], sys.argv[3]
    os.makedirs(out, exist_ok=True)
    env = dict(os.environ, HA_URL=url, HA_TOKEN=token(cfg), RENDER_FIXED_TIME=FIXED_TIME,
               RENDER_EXPECTED_BROKEN=",".join(EXPECTED_BROKEN))
    failed = []
    for page in PAGES:
        for w in WIDTHS:
            png = os.path.join(out, "%s-%d.png" % (page, w))
            # render.py exits 1 for a broken card, 2 when the page never drew (still the
            # loading screen), and with a traceback (Python's 1 too, so tell them apart by
            # output) when the browser itself failed. The last two are retried, once - a
            # broken card is never retried away.
            for attempt in (1, 2):
                p = subprocess.run([sys.executable, RENDER, png, "/lovelace/" + page, str(w),
                                    "--strict"], env=env, capture_output=True, text=True)
                sys.stdout.write(p.stdout)
                sys.stderr.write(p.stderr)
                undrawn = p.returncode == 2
                crashed = p.returncode != 0 and "Traceback" in p.stderr
                if not (crashed or undrawn) or attempt == 2:
                    break
                print("  %s; retrying once" % ("page never drew" if undrawn else "render crashed"))
            if undrawn:
                failed.append("%s at %d px (never drew: loading screen)" % (page, w))
            elif crashed:
                failed.append("%s at %d px (render crashed)" % (page, w))
            elif p.returncode != 0:
                failed.append("%s at %d px (broken card)" % (page, w))
    if failed:
        print("\nFAILED: " + ", ".join(failed))
        return 1
    print("\n%d screenshots, no broken card" % (len(PAGES) * len(WIDTHS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
