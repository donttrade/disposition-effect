#!/usr/bin/env python3
"""Capture the numbers behind the tool-card previews (25 Oct sweep, owner: "show it rather than say it").

    python3 checks/make_tool_previews.py

Builds the site to a temp dir, serves it on 127.0.0.1, opens trade stats, the heatmap, the drawdown
calculator and the prop-challenge simulator, clicks "Try a sample file" (and, for the simulator, its
"Run" button with the page's default rules), and reads the tools' own results from the page. Writes
site/config/tool_previews.json with the sample file's SHA-256: tests/test_tool_previews.py fails when
the sample file changes and this has not been re-run. The cards draw these numbers as small inline
SVG/CSS (partials/tool_cards.html), so every preview is real output on the synthetic sample file.
"""
import functools
import hashlib
import http.server
import json
import os
import re
import subprocess
import sys
import tempfile
import threading

from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "site", "config", "tool_previews.json")
SAMPLE = os.path.join(REPO, "site", "static", "samples", "demo-trades.csv")


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


def sample_sha():
    with open(SAMPLE, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def stat(pg, scope, label):
    return pg.evaluate("""([scope, label]) => { for (const dt of document.querySelectorAll(scope + ' dl dt'))
        if (dt.textContent.trim() === label) return dt.nextElementSibling.textContent.trim(); return null; }""", [scope, label])


def main():
    tmp = tempfile.mkdtemp()
    out = os.path.join(tmp, "_site")
    env = {**os.environ, "DT_OUT": out}
    env.pop("DT_DEV", None)
    subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, check=True, capture_output=True)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=out))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    res = {"sample_sha256": sample_sha(), "script": "checks/make_tool_previews.py"}
    with sync_playwright() as p:
        b = p.chromium.launch()
        pg = b.new_page(viewport={"width": 1280, "height": 900})

        pg.goto(base + "/tools/trade-stats/")
        pg.click("#ts-sample-btn")
        pg.wait_for_selector("#ts-out dl")
        res["trade_stats"] = {k: stat(pg, "#ts-out", label) for k, label in
                              (("trades", "Closed trades"), ("net", "Net result"), ("win_rate", "Win rate"),
                               ("profit_factor", "Profit factor"), ("largest_drawdown", "Largest drawdown"))}
        res["trade_stats"]["fills"] = re.search(r"from ([\d,]+) fills", pg.inner_text("#ts-out")).group(1)
        res["trade_stats"]["hold_ratio"] = pg.evaluate("""() => { for (const tr of document.querySelectorAll('#ts-out tr'))
            if (tr.cells.length > 1 && tr.cells[0].textContent.trim().startsWith('Losing hold')) return tr.cells[1].textContent.trim(); }""")

        pg.goto(base + "/tools/trading-heatmap/")
        pg.click("#hm-sample-btn")
        pg.wait_for_selector("#hm-out table td.heat")
        res["heatmap"] = pg.evaluate("""() => { const t = document.querySelector('#hm-out table');
            const cols = [...t.querySelectorAll('thead th')].slice(1).map(th => th.textContent.trim());
            const rows = [...t.querySelectorAll('tbody tr')].map(tr => {
              const hour = tr.querySelector('th').textContent.trim().slice(0, 2);
              const cells = [...tr.querySelectorAll('td')].map(td => { const s = td.querySelectorAll('span');
                return s.length >= 2 ? s[0].textContent.trim() : null; });
              return {hour, cells}; });
            return {cols, rows}; }""")
        for r in res["heatmap"]["rows"]:   # the tool's own signed totals → −1..1 shade levels for the mini grid
            vals = [float(c.replace("−", "-").replace("$", "").replace(",", "").replace("+", "")) if c else None
                    for c in r["cells"]]
            r["values"] = vals
        top = max(abs(v) for r in res["heatmap"]["rows"] for v in r["values"] if v is not None)
        for r in res["heatmap"]["rows"]:
            r["levels"] = [None if v is None else round(v / top, 2) for v in r["values"]]
            del r["values"]

        pg.goto(base + "/tools/drawdown-calculator/")
        pg.click("#dd-sample-btn")
        pg.wait_for_selector("#dd-out svg path.area-dd")
        d = pg.get_attribute("#dd-out svg path.area-dd", "d")
        pts = [(float(x), float(y)) for x, y in re.findall(r"(-?[\d.]+),(-?[\d.]+)", d)]
        x0, x1 = min(x for x, _ in pts), max(x for x, _ in pts)
        y0, y1 = min(y for _, y in pts), max(y for _, y in pts)
        step = max(1, len(pts) // 80)
        res["drawdown"] = {"largest": stat(pg, "#dd-out", "Largest drawdown"),
                           "points": " ".join(f"{(x - x0) / (x1 - x0) * 200:.1f},{2 + (y - y0) / (y1 - y0) * 52:.1f}"
                                              for x, y in pts[::step] + [pts[-1]])}

        pg.goto(base + "/tools/prop-challenge-simulator/")
        pg.click("#ps-sample-btn")
        pg.wait_for_function("!document.querySelector('#ps-run').disabled")
        pg.click("#ps-run")
        pg.wait_for_selector("#ps-out svg[aria-label]", timeout=60000)
        lab = pg.get_attribute("#ps-out svg[aria-label]", "aria-label")   # "Passed 14.5%, Busted 5.2%, Ran out of time 80.3%"
        got = dict(re.findall(r"(Passed|Busted|Ran out of time) ([\d.]+%)", lab))
        res["prop_sim"] = {"passed": got["Passed"], "busted": got["Busted"], "timed_out": got["Ran out of time"]}
        b.close()
    srv.shutdown()
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
        f.write("\n")
    print(json.dumps({k: v for k, v in res.items() if k != "drawdown"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
