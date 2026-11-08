#!/usr/bin/env python3
"""make_seo_assets.py (6 Nov 2026, SEO round 1): the Organization logo and the Open Graph cards for the pages that had
the default card. Run it only when a title, a tool glyph or the favicon changes; tests/test_seo1.py checks the result.

    python3 checks/make_seo_assets.py            # logo, then the cards
    python3 checks/make_seo_assets.py --logo     # only docs/assets/logo-512.png

docs/ is the only source for site assets (the build passes docs/ through), so both land there:
  docs/assets/logo-512.png            512 x 512, the favicon drawn in its light-mode colours (Organization.logo)
  docs/assets/og/tool-<glyph>.png     one 1200 x 630 card per tool: the tool's own B2 glyph (the real-data drawing from
                                       partials/tool_glyphs.html, taken from the built page), its name, its one line
  docs/assets/og/tools.png, glossary.png, learn.png, learn-drawdown.png, learn-streaks.png

No card holds a number: the text is the tool name and its card line (config TOOLS), and the glyph is a drawing. Chromium
(Playwright, already a dev dependency) draws them; the build itself never needs it. The cards are the site's colours and its
own fonts (Plex Serif, Plex Sans from site/static/fonts), at most 300 KB each.
"""
import base64
import functools
import html
import http.server
import io
import os
import re
import subprocess
import sys
import tempfile
import threading

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
DOCS = os.path.join(REPO, "docs")
OG_DIR = os.path.join(DOCS, "assets", "og")
LOGO = os.path.join(DOCS, "assets", "logo-512.png")
CHROME = ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
MAX_BYTES = 300 * 1024

CARD = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/css/site.css"><link rel="stylesheet" href="/static/css/tools.css">
<style>
html, body { margin: 0; width: 1200px; height: 630px; overflow: hidden; background: #FBF8F3; }
body { position: relative; font-family: "Plex Sans", sans-serif; color: #1C1A17;
  background-image: radial-gradient(circle, rgba(28,26,23,.10) 1px, transparent 1.4px); background-size: 24px 24px; background-position: 12px 12px; }
.mark { position: absolute; left: 72px; top: 56px; font: 600 52px/1 "Plex Serif", Georgia, serif; letter-spacing: -.5px; }
.rule { position: absolute; left: 72px; width: 120px; height: 6px; background: #9A3B1C; }
.t { position: absolute; left: 72px; font: 600 66px/1.08 "Plex Serif", Georgia, serif; width: %(tw)dpx; }
.s { position: absolute; left: 72px; font: 400 28px/1.35 "Plex Sans", sans-serif; color: #4A453E; width: %(tw)dpx; }
.well { position: absolute; right: 72px; top: 150px; width: 340px; height: 340px; border: 2px solid #D9D3C8; border-radius: 28px; background: #FFFFFF;
  display: flex; align-items: center; justify-content: center; --well: #FFFFFF; --bg: #FFFFFF; --text: #1C1A17; --border: #D9D3C8; }
.well .ic { width: 260px; height: 260px; }
</style></head><body>
<div class="mark">donttrade</div>
%(well)s
<div class="rule" id="rule"></div><div class="t" id="t">%(title)s</div><div class="s" id="s">%(sub)s</div>
<script>
// stack the rule, title and subtitle upward from a fixed baseline (the text height is only known after layout)
const t = document.getElementById('t'), s = document.getElementById('s'), r = document.getElementById('rule');
const bottom = 566;
s.style.top = (bottom - s.offsetHeight) + 'px';
t.style.top = (bottom - s.offsetHeight - 18 - t.offsetHeight) + 'px';
r.style.top = (bottom - s.offsetHeight - 18 - t.offsetHeight - 28) + 'px';
</script></body></html>"""


def logo():
    with open(os.path.join(DOCS, "assets", "favicon.svg"), "rb") as f:
        b64 = base64.b64encode(f.read()).decode("ascii")
    page_html = (f'<html><body style="margin:0;background:transparent"><img src="data:image/svg+xml;base64,{b64}" '
                 'width="512" height="512"></body></html>')
    with sync_playwright() as p:
        b = p.chromium.launch(args=CHROME)
        pg = b.new_page(viewport={"width": 512, "height": 512}, color_scheme="light")
        pg.set_content(page_html)
        pg.wait_for_function("() => document.images[0].complete && document.images[0].naturalWidth > 0")
        png = pg.screenshot(omit_background=True, clip={"x": 0, "y": 0, "width": 512, "height": 512})
        b.close()
    img = Image.open(io.BytesIO(png)).convert("RGBA")
    img.save(LOGO, optimize=True)
    print(f"wrote {os.path.relpath(LOGO, REPO)} {img.size} {os.path.getsize(LOGO)} bytes")


def specs(site_dir):
    """[(file name, title, subtitle, glyph svg or None)] for every card."""
    import build
    out = []
    for t in build.TOOLS:
        key = t["glyph"]
        path = os.path.join(site_dir, t["href"].strip("/"), "index.html")
        with open(path, encoding="utf-8") as f:
            m = re.search(r'<span class="tool-mark">(<svg .*?</svg>)</span>', f.read(), re.S)
        if not m:
            raise SystemExit(f"{t['href']}: no .tool-mark glyph in the built page")
        out.append((f"tool-{key}.png", t["name"], t["short"], m.group(1)))
    out += [("tools.png", "Free trading tools", "Nine tools that run in your browser. Your file is not uploaded.", None),
            ("glossary.png", "Glossary", "Plain definitions of trading habits and risk terms.", None),
            ("learn.png", "Learn", "Trading habits and risk math, measured.", None),
            ("learn-drawdown.png", "Drawdown recovery table", "The gain that gets an account back.", None),
            ("learn-streaks.png", "Losing streak probability", "How many losses in a row to expect.", None)]
    # selloff.png is drawn by checks/make_study_assets.py since 7 Nov 2026 (the finding and the lead chart), not here
    return out


def cards():
    tmp = tempfile.mkdtemp(prefix="dt-og-")
    env = dict(os.environ, DT_OUT=tmp)
    subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, check=True, cwd=REPO, stdout=subprocess.DEVNULL)
    class Quiet(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    handler = functools.partial(Quiet, directory=tmp)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    os.makedirs(OG_DIR, exist_ok=True)
    with sync_playwright() as p:
        b = p.chromium.launch(args=CHROME)
        ctx = b.new_context(viewport={"width": 1200, "height": 630}, color_scheme="light", reduced_motion="reduce")
        only = [a.split("=", 1)[1] for a in sys.argv if a.startswith("--only=")]   # --only=selloff.png,tool-badday.png
        names = only[0].split(",") if only else None
        for name, title, sub, glyph in specs(tmp):
            if names and name not in names:
                continue
            well = f'<div class="well"><span class="tool-mark">{glyph}</span></div>' if glyph else ""
            doc = CARD % {"tw": 640 if glyph else 900, "well": well, "title": html.escape(title), "sub": html.escape(sub)}
            pg = ctx.new_page()
            pg.goto(base + "/static/css/site.css")   # same origin for the relative stylesheet and font URLs
            pg.set_content(doc.replace("</head>", f'<base href="{base}/"></head>', 1))
            pg.wait_for_load_state("networkidle")
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(150)
            # lay the text out again once the fonts are in
            pg.evaluate("""() => { const t=document.getElementById('t'), s=document.getElementById('s'), r=document.getElementById('rule');
              const bottom=566; s.style.top=(bottom-s.offsetHeight)+'px'; t.style.top=(bottom-s.offsetHeight-18-t.offsetHeight)+'px';
              r.style.top=(bottom-s.offsetHeight-18-t.offsetHeight-28)+'px'; }""")
            png = pg.screenshot(clip={"x": 0, "y": 0, "width": 1200, "height": 630})
            pg.close()
            img = Image.open(io.BytesIO(png)).convert("RGB")
            dest = os.path.join(OG_DIR, name)
            img.save(dest, optimize=True)
            if os.path.getsize(dest) > MAX_BYTES:   # palette-reduce the (rare) heavy card
                img.quantize(colors=128).save(dest, optimize=True)
            print(f"wrote {os.path.relpath(dest, REPO)} {img.size} {os.path.getsize(dest)} bytes")
        b.close()
    srv.shutdown()


if __name__ == "__main__":
    if not any(a.startswith("--only=") for a in sys.argv):
        logo()
    if "--logo" not in sys.argv:
        cards()
