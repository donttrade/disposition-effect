#!/usr/bin/env python3
"""make_study_assets.py (7 Nov 2026, study-page improvements): the files a study page serves that a browser has to draw.
Dev-only, like make_seo_assets.py: run it when a study's figures or title change; tests/test_study_pages_v2.py checks the result.
The build itself never needs Playwright.

    python3 checks/make_study_assets.py --study selloff

It builds the site to a temp dir, serves it, and reads the BUILT page, so the files cannot drift from it. docs/ is the only source
for site assets (the build passes docs/ through), so everything lands there:
  docs/assets/og/selloff.png                    the share card: the finding and the lead chart (1200 x 630, at most 300 KB)
  docs/assets/charts/selloff/<fig>.png          each chart as an image at twice its 1000 px canvas (title, source and licence inside), at most 350 KB
  docs/assets/press/selloff.zip                 the press pack: the chart PNGs, the CSVs, the plan, a read me and a one-page summary (at most 5 MB)
  docs/assets/charts/selloff/<fig>.src.sha256   the SHA-256 of the built <fig>.svg the PNG was drawn from (a test fails if the chart changes
                                                and the PNG was not drawn again)

No card holds a price, an offer or the name of a product: the finding, the chart, the data credit and the address.
"""
import functools
import shutil
import hashlib
import urllib.request
import html
import http.server
import io
import os
import subprocess
import sys
import tempfile
import zipfile
import threading

from PIL import Image
from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
DOCS = os.path.join(REPO, "docs")
CHROME = ["--no-sandbox", "--disable-gpu", "--disable-dev-shm-usage"]
OG_MAX = 300 * 1024

CARD = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="/static/css/site.css">
<style>
html, body { margin: 0; width: 1200px; height: 630px; overflow: hidden; background: #FFFFFF; color: #16181C; }
body { position: relative; font-family: "Plex Sans", sans-serif; }
.mark { position: absolute; left: 64px; top: 48px; font: 600 40px/1 "Plex Sans", sans-serif; letter-spacing: -.5px; }
.kind { position: absolute; left: 64px; top: 120px; font: 400 24px/1.2 "Plex Sans", sans-serif; color: #4A4F57; }
.bar { position: absolute; left: 64px; top: 164px; width: 96px; height: 6px; background: #9A3B1C; }
.t { position: absolute; left: 64px; top: 192px; width: 470px; font: 600 40px/1.18 "Plex Sans", sans-serif; }
.chart-box { position: absolute; left: 572px; top: 96px; width: 564px; }
.chart-box .sell-chart { margin: 0; }
.chart-box svg { width: 564px; height: auto; display: block; max-width: none; }
.chart-box .grid-line { stroke: #D9DCE1; stroke-width: 1; }
.chart-box .axis { fill: #4A4F57; font: 400 11px "Plex Sans", sans-serif; }
.chart-box .bar-plain { fill: #4A6A94; }
.chart-box .bar-event { fill: #9A3B1C; }
.chart-box .line-median { stroke: #16181C; stroke-width: 1.5; stroke-dasharray: 5 4; }
.chart-box .fig-credit { display: none; }
.foot { position: absolute; left: 64px; right: 64px; bottom: 40px; font: 400 22px/1.2 "Plex Sans", sans-serif; color: #4A4F57; display: flex; justify-content: space-between; }
</style></head><body>
<div class="mark">donttrade</div>
<div class="kind">%(kind)s</div><div class="bar"></div>
<div class="t">%(title)s</div>
<div class="chart-box"><figure class="chart sell-chart">%(svg)s</figure></div>
<div class="foot"><span>donttrade.ca</span><span>%(credit)s</span></div>
</body></html>"""


def card_html(kind, title, svg, credit):
    return CARD % {"kind": html.escape(kind), "title": html.escape(title), "svg": svg, "credit": html.escape(credit)}


class Site:
    """The site built to a temp dir and served on 127.0.0.1."""

    def __enter__(self):
        self.tmp = tempfile.mkdtemp(prefix="dt-study-")
        subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=dict(os.environ, DT_OUT=self.tmp), check=True,
                       cwd=REPO, stdout=subprocess.DEVNULL)

        class Quiet(http.server.SimpleHTTPRequestHandler):
            def log_message(self, *a):
                pass
        self.srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=self.tmp))
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"
        return self

    def __exit__(self, *a):
        self.srv.shutdown()
        shutil.rmtree(self.tmp, ignore_errors=True)


def quantise(png, dest, limit):
    img = Image.open(io.BytesIO(png)).convert("RGB")
    for colours in (256, 128, 64, 32):
        img.quantize(colors=colours).save(dest, optimize=True)
        if os.path.getsize(dest) <= limit:
            return os.path.getsize(dest)
    raise SystemExit(f"{dest}: still over {limit} bytes at 32 colours")


def selloff_og(site, browser):
    import selloff as SO
    ctx = SO.context()
    F = ctx["F"]
    ctx_page = browser.new_context(viewport={"width": 1200, "height": 630}, color_scheme="light", reduced_motion="reduce")
    pg = ctx_page.new_page()
    pg.goto(site.base + "/research/5-november-2026-sell-off/")
    svg = pg.evaluate("() => document.querySelector('#fig-hip3-daily svg').outerHTML")
    doc = card_html("Study · 6 Nov 2026 · wallets, not people", SO.short_title(F), svg, "Data: Ironflow, CC BY 4.0")
    pg.route("**/__card.html", lambda r: r.fulfill(status=200, content_type="text/html", body=doc))
    pg.goto(site.base + "/__card.html")
    pg.wait_for_load_state("networkidle")
    pg.evaluate("document.fonts.ready")
    pg.wait_for_timeout(200)
    png = pg.screenshot(clip={"x": 0, "y": 0, "width": 1200, "height": 630})
    pg.close()
    ctx_page.close()
    dest = os.path.join(DOCS, "assets", "og", "selloff.png")
    n = quantise(png, dest, OG_MAX)
    print(f"wrote {os.path.relpath(dest, REPO)} {n} bytes")


CHART_MAX = 350 * 1024


def selloff_charts(site, browser):
    import selloff as SO
    ctx = SO.context()
    out_dir = os.path.join(DOCS, "assets", "charts", "selloff")
    os.makedirs(out_dir, exist_ok=True)
    c = browser.new_context(viewport={"width": SO.SVG_W, "height": 900}, device_scale_factor=2, color_scheme="light", reduced_motion="reduce")
    for fg in ctx["figs"]:
        raw = urllib.request.urlopen(f"{site.base}/assets/charts/selloff/{fg['id']}.svg").read()
        doc = f'<!doctype html><html><head><meta charset="utf-8"><link rel="stylesheet" href="/static/css/site.css"><style>html,body{{margin:0;background:#fff}}svg{{display:block}}</style></head><body>{raw.decode("utf-8")}</body></html>'
        pg = c.new_page()
        pg.route("**/__chart.html", lambda r, _q, d=doc: r.fulfill(status=200, content_type="text/html", body=d))
        pg.goto(site.base + "/__chart.html")
        pg.wait_for_load_state("networkidle")
        pg.evaluate("document.fonts.ready")
        pg.wait_for_timeout(200)
        png = pg.locator("svg").first.screenshot()
        pg.close()
        dest = os.path.join(out_dir, fg["id"] + ".png")
        n = quantise(png, dest, CHART_MAX)
        with open(os.path.join(out_dir, fg["id"] + ".src.sha256"), "w", encoding="utf-8", newline="\n") as f:
            f.write(hashlib.sha256(raw).hexdigest() + "\n")
        print(f"wrote {os.path.relpath(dest, REPO)} {Image.open(dest).size} {n} bytes")
    c.close()


def selloff_press(site):
    """The press pack, written byte-for-byte reproducibly (sorted names, fixed times) from the built site's CSVs, the charts just drawn,
    the plan, and the texts site/selloff.py builds from the page's own figures."""
    import selloff as SO
    ctx = SO.context()
    readme, one = SO.press_texts(ctx, "https://donttrade.ca")
    src = {"ONE-PAGE-SUMMARY.txt": one.encode("utf-8"), "README.txt": readme.encode("utf-8"),
           "ANALYSIS-PLAN.md": open(os.path.join(SO.PACK_DIR, "ANALYSIS-PLAN.md"), "rb").read()}
    for fg in ctx["figs"]:
        src[f"charts/{fg['id']}.png"] = open(os.path.join(DOCS, "assets", "charts", "selloff", fg["id"] + ".png"), "rb").read()
    for name in ("5-november-2026-hyperliquid-daily.csv", "5-november-2026-hyperliquid-hourly.csv", "5-november-2026-per-market.csv"):
        src["data/" + name] = open(os.path.join(site.tmp, "data", name), "rb").read()
    src["data/MARKETS-VERIFIED.csv"] = open(os.path.join(SO.PACK_DIR, "MARKETS-VERIFIED.csv"), "rb").read()
    assert sorted(src) == sorted(SO.PRESS_ZIP_FILES), sorted(src)
    dest = os.path.join(DOCS, "assets", "press", "selloff.zip")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as z:
        for name in SO.PRESS_ZIP_FILES:
            zi = zipfile.ZipInfo(name, date_time=(2026, 11, 7, 0, 0, 0))
            zi.compress_type = zipfile.ZIP_DEFLATED
            zi.external_attr = 0o644 << 16
            z.writestr(zi, src[name])
    if os.path.getsize(dest) > 5 * 1024 * 1024:
        raise SystemExit("press pack is over 5 MB")
    print(f"wrote {os.path.relpath(dest, REPO)} {os.path.getsize(dest)} bytes")


def main():
    if "--study=selloff" not in sys.argv and sys.argv[1:3] != ["--study", "selloff"]:
        raise SystemExit(__doc__)
    with Site() as site, sync_playwright() as p:
        b = p.chromium.launch(args=CHROME)
        selloff_og(site, b)
        selloff_charts(site, b)
        selloff_press(site)
        b.close()


if __name__ == "__main__":
    main()
