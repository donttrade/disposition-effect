#!/usr/bin/env python3
"""Capture the homepage hero images: the real free dashboard (/tools/trade-stats/) run
on the synthetic sample file, in light and dark.

    python3 checks/make_hero_shots.py

Writes site/static/img/hero-trade-stats-{light,dark}.webp and prints their sizes. The
teardown asks for "real UI, not illustration"; this is the actual page, not a mock-up.
Re-run it whenever the dashboard's look changes (the images are committed, so the build
stays byte-identical between runs).

How: build the site to a temp dir, serve it on 127.0.0.1, open the dashboard at 720 px
wide, click "Try a sample file", wait for the noise checks, and clip the region from the
headline numbers to the end of the equity chart.
"""
import functools
import http.server
import io
import os
import subprocess
import sys
import tempfile
import threading

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "site", "static", "img")
WIDTH = 720          # viewport: wide enough for 3 stat tiles per row, narrow enough to read when scaled into the hero
SCALE = 1.5          # device pixel ratio for crisp text on high-density screens
BUDGET = 120 * 1024  # teardown: hero ≤ 120 KB


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


def main():
    tmp = tempfile.mkdtemp()
    env = {**os.environ, "DT_OUT": os.path.join(tmp, "_site")}
    env.pop("DT_DEV", None)
    subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, check=True, capture_output=True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=env["DT_OUT"]))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/tools/trade-stats/"
    os.makedirs(OUT, exist_ok=True)
    sizes = {}
    with sync_playwright() as p:
        b = p.chromium.launch()
        for scheme in ("light", "dark"):
            ctx = b.new_context(viewport={"width": WIDTH, "height": 1000}, color_scheme=scheme, device_scale_factor=SCALE)
            page = ctx.new_page()
            page.goto(url)
            page.wait_for_load_state("networkidle")
            page.click("#ts-sample-btn")
            page.wait_for_selector("#ts-noise table", timeout=90000)
            # Document coordinates (bounding boxes are viewport-relative after the page
            # scrolls to the results), then crop a full-page capture.
            box = page.evaluate("""() => {
                const r = (s) => { const b = document.querySelector(s).getBoundingClientRect();
                                   return {x: b.left + scrollX, y: b.top + scrollY, w: b.width, h: b.height}; };
                return {top: r('#ts-head-h'), fig: r('#ts-out figure.chart svg'), out: r('#ts-out')};
            }""")
            x0, y0 = box["out"]["x"] - 12, box["top"]["y"] - 16
            x1, y1 = box["out"]["x"] + box["out"]["w"] + 12, box["fig"]["y"] + box["fig"]["h"] + 4
            png = page.screenshot(full_page=True)
            img = Image.open(io.BytesIO(png)).convert("RGB")
            img = img.crop(tuple(round(v * SCALE) for v in (x0, y0, x1, y1)))
            path = os.path.join(OUT, f"hero-trade-stats-{scheme}.webp")
            img.save(path, "WEBP", quality=82, method=6)
            sizes[scheme] = (os.path.getsize(path), img.size)
            ctx.close()
        b.close()
    srv.shutdown()
    bad = False
    for scheme, (n, (w, h)) in sizes.items():
        print(f"hero-trade-stats-{scheme}.webp: {n / 1024:.1f} KB, {w}x{h}")
        bad |= n > BUDGET
    if bad:
        print(f"FAIL: a hero image is over the {BUDGET // 1024} KB budget", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
