#!/usr/bin/env python3
"""Draw docs/favicon.ico from docs/assets/favicon.svg (hardening plan item 2, 3 Nov).

    python3 checks/make_favicon.py

Browsers and crawlers that never read <link rel="icon"> ask for /favicon.ico at the site root; without it they
get the 404 page. Chromium draws the SVG at 256 px with a transparent background (the light-mode colours: an
ICO cannot switch with the colour scheme), and Pillow writes one ICO with 16, 32 and 48 px images.
docs/ is the only source for site assets (the build passes docs/ through), so the file lives at docs/favicon.ico.
Re-run it only when the SVG changes; tests/test_hardening_3nov.py checks the result.
"""
import base64
import io
import os
import sys

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SVG = os.path.join(REPO, "docs", "assets", "favicon.svg")
OUT = os.path.join(REPO, "docs", "favicon.ico")
SIZES = [(16, 16), (32, 32), (48, 48)]


def main():
    with open(SVG, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    html = ('<html><body style="margin:0;background:transparent">'
            f'<img src="data:image/svg+xml;base64,{b64}" width="256" height="256"></body></html>')
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 256, "height": 256}, color_scheme="light")
        pg.set_content(html)
        pg.wait_for_function("() => document.images[0].complete && document.images[0].naturalWidth > 0")
        png = pg.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": 256, "height": 256})
        b.close()
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    img.save(OUT, format="ICO", sizes=SIZES)
    print(f"wrote {os.path.relpath(OUT, REPO)} ({os.path.getsize(OUT)} bytes, sizes {[s[0] for s in SIZES]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
