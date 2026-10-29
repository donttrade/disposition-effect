#!/usr/bin/env python3
"""Capture the homepage hero: the real free dashboard (/tools/trade-stats/) run on the
synthetic sample file, as live HTML (motion plan D1, 21 Oct 2026).

    python3 checks/make_hero_dashboard.py

Writes site/templates/partials/hero_dashboard.html and prints its size, the chart's viewBox
width W and the .veil left offset (L / W, as a percentage) that site.css must hold. The
teardown asks for "real UI, not illustration": this is the tool's own markup (the headline
stat tiles and the inline SVG chart), captured from the tool, not a mock-up. Because it is
HTML coloured by the site's CSS tokens, the hero follows the light/dark toggle (the old
<picture> could only follow the OS setting). Re-run it whenever the sample file or the
dashboard's markup changes: build.py refuses to build when the sample's SHA-256 differs from
the one recorded in the partial.

How: build the site (committed flags, all off) to a temp dir, serve it on 127.0.0.1, open the
dashboard at WIDTH px (the tool sizes the chart's viewBox to its drop zone, so W lands in
460-520 and the 12 px labels stay legible when the SVG is scaled into the hero), click "Try
a sample file", and take dl.stats and the chart <svg> as outerHTML. Then: drop data-k, mark
each <dd> data-count, make the <svg> aria-hidden with no <title>, and drop every id.
"""
import functools
import hashlib
import html as _h
import http.server
import os
import re
import subprocess
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
OUT = os.path.join(REPO, "site", "templates", "partials", "hero_dashboard.html")
SAMPLE = os.path.join(REPO, "site", "static", "samples", "example-trades.csv")
WIDTH = 532            # viewport; the tool's drop zone is then 496 px wide, so W = 496 (measured 21 Oct 2026)
W_RANGE = (460, 520)   # plan §4.2: labels ~10.8 px on desktop, ~7.7 px at 375
L = 92                 # the chart's y-label gutter (trade-stats.js chart(): L = 92)
BUDGET = 8 * 1024      # plan §5: hero partial ≤ 8 KB
SCRIPT = "checks/make_hero_dashboard.py"


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


def sample_sha():
    with open(SAMPLE, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def alt_text(values):
    """The old <img alt>, word for word, with the captured values (plan §4.2: aria-label = old alt)."""
    n, net, win, pf = values[0], values[1], values[2], values[3]
    m = re.fullmatch(r"([+−])\$(\d+(?:\.\d+)?)", net)
    if not m:
        raise SystemExit(f"FAIL: net result {net!r} is not +$X or −$X")
    sign = "plus" if m.group(1) == "+" else "minus"
    return (f"The free trade-stats dashboard on the synthetic sample file: {n} closed trades, a net result of "
            f"{sign} {m.group(2)} US dollars, win rate {win}, profit factor {pf}, and an equity and drawdown chart.")


def transform(dl, svg):
    dl = re.sub(r' data-k="[^"]*"', "", dl)
    dl = re.sub(r"<dd\b", "<dd data-count", dl)
    svg = re.sub(r"<title\b[^>]*>.*?</title>", "", svg, flags=re.S)
    svg, n = re.subn(r"<svg\b[^>]*>", lambda m: '<svg viewBox="' + re.search(r'viewBox="([^"]+)"', m.group(0)).group(1)
                     + '" aria-hidden="true" focusable="false">', svg, count=1)
    if n != 1:
        raise SystemExit("FAIL: no <svg> start tag in the capture")
    # every id goes (the hero must not duplicate the tool's ids or add page anchors)
    return [re.sub(r'\sid="[^"]*"', "", frag) for frag in (dl, svg)]


def main():
    import build as B
    from lint import FREE_BADGE_STRINGS
    if os.environ.get("DT_SITE_TOML"):
        print("FAIL: run with the committed site.toml (DT_SITE_TOML is set)", file=sys.stderr)
        return 1
    flags = B.read_toml(os.path.join(REPO, "site", "config", "site.toml"), "site.toml")["flags"]
    on = sorted(k for k, v in flags.items() if v)
    if on:
        print(f"FAIL: capture with the default flags (all off); on: {', '.join(on)}", file=sys.stderr)
        return 1
    tmp = tempfile.mkdtemp()
    env = {**os.environ, "DT_OUT": os.path.join(tmp, "_site")}
    env.pop("DT_DEV", None)
    subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, check=True, capture_output=True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=env["DT_OUT"]))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{srv.server_address[1]}/tools/trade-stats/"
    with sync_playwright() as p:
        b = p.chromium.launch()
        page = b.new_page(viewport={"width": WIDTH, "height": 1000}, color_scheme="light", reduced_motion="reduce")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        page.click("#ts-sample-btn")
        page.wait_for_selector("#ts-out figure.chart svg", timeout=90000)
        page.wait_for_timeout(300)
        cap = page.evaluate("""() => {
            const out = document.querySelector('#ts-out');
            const svg = out.querySelector('figure.chart svg');
            return {dl: out.querySelector('dl.stats').outerHTML, svg: svg.outerHTML,
                    vb: svg.getAttribute('viewBox'),
                    values: [...out.querySelectorAll('dl.stats dd')].map(d => d.textContent)};
        }""")
        b.close()
    srv.shutdown()
    W = int(cap["vb"].split()[2])
    if not W_RANGE[0] <= W <= W_RANGE[1]:
        print(f"FAIL: viewBox width {W} is outside {W_RANGE}; change WIDTH", file=sys.stderr)
        return 1
    dl, svg = transform(cap["dl"], cap["svg"])
    label = alt_text(cap["values"])
    body = ('<div class="hero-dash" role="img" aria-label="' + _h.escape(label) + '">'
            '<p class="dash-h">Headline numbers</p>' + dl +
            '<p class="dash-h">Equity and drawdown</p><div class="plot chart">' + svg +
            '<span class="veil" aria-hidden="true"></span></div></div>\n')
    for bad in ("{{", "{%", "{#", " id=", "<script", "style="):
        if bad in body:
            print(f"FAIL: the capture holds {bad!r}", file=sys.stderr)
            return 1
    found = [s for s in FREE_BADGE_STRINGS if s in body]
    if found:
        print(f"FAIL: free-badge strings in the capture: {found}", file=sys.stderr)
        return 1
    if body.count("data-count") != 6:
        print(f"FAIL: expected 6 stat tiles, found {body.count('data-count')}", file=sys.stderr)
        return 1
    left = round(L / W * 100, 2)
    head = ("{#- hero_dashboard.html: GENERATED by " + SCRIPT + "; do not edit by hand.\n"
            "    sample-sha256: " + sample_sha() + "\n"
            "    viewbox-w: " + str(W) + "\n"
            "    veil-left: " + f"{left}%" + " (= L / W; site.css .hero-dash .veil must hold it)\n"
            "    values: " + " | ".join(cap["values"]) + " #}\n")
    text = head + body
    if len(text.encode("utf-8")) > BUDGET:
        print(f"FAIL: {len(text.encode('utf-8'))} B is over the {BUDGET} B budget", file=sys.stderr)
        return 1
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"{os.path.relpath(OUT, REPO)}: {len(text.encode('utf-8'))} B (markup {len(body.encode('utf-8'))} B), "
          f"viewBox W = {W}, veil left = {left}%")
    print("values:", " | ".join(cap["values"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
