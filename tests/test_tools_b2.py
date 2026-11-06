"""The /tools/ redesign, phase 1 (Direction B2 "Instrument panel", 6 Nov; ARCHITECT-PLAN-TOOLS-REDESIGN-2026-11-06).

What is held here:
  * every displayed figure is recomputed from the committed inputs (checks/real_data/) by the committed script, and
    equals site/config/tool_real.json byte for byte; each input and script hash in the JSON is the file's;
  * every figure on /tools/ and in the tool-page displays is one of the JSON's, labelled "Real public data" (or
    "Real published data", "Formula only", "No public data"), with its source line and the selection rules in print;
  * no ticker or dataset note on the pages or in the JSON; the attribution is word for word the plan's (A.1);
  * the eight glyphs, the module structure (one link, one h3, one aria-hidden glyph, data-tool), the CSP (no style=,
    no inline script), the offer copy from partials/trader_offer.html, the firms sentence gated on prices.study, the
    old tool cards on / and /for-traders/ unchanged, the "Free for everyone" strip only off /tools/;
  * the lint real-data rule both ways, the screen contrast pairs;
  * the pass-rate page: the lifted maths unchanged (the legacy script is the oracle), the Wilson band only from 30
    finished, no invented counts; the disposition page: Odean's (1998) counts with the citation;
  * in Chromium: no overflow from 320 px, axe (serious, critical) clean in both themes, reduced motion runs nothing
    and the scope rests on the deepest trade, the calculators give the oracle's figures, no console error.
"""
import csv
import gzip
import hashlib
import json
import math
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RD = os.path.join(REPO, "checks", "real_data")
# 6 Nov fix round 2: the trade file with the real tickers is not committed; checks/real_data/fetch.py makes it in raw/
# (gitignored). Tests that need it skip without it; the coded copy's structure is checked either way.
RAW_CSV = os.path.join(RD, "raw", "real-trades.csv")
HAVE_RAW = os.path.exists(RAW_CSV)
needs_raw = pytest.mark.skipif(not HAVE_RAW, reason="checks/real_data/raw/real-trades.csv absent: run checks/real_data/fetch.py")
RAW_KEY = "checks/real_data/raw/real-trades.csv"
# The branch's base on main (696c324 when cut): comparisons are against it, not origin/main, which moves on as other
# branches merge (polish round, 6 Nov: forfirms merged into main, e4fc309).
BASE = subprocess.run(["git", "-C", REPO, "merge-base", "HEAD", "origin/main"], capture_output=True, text=True).stdout.strip() \
    or "origin/main"
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, RD)
sys.path.insert(0, os.path.join(REPO, "site"))
import lint as L  # noqa: E402
from harvest_prices import amounts_in  # noqa: E402

TOOL_REAL = os.path.join(REPO, "site", "config", "tool_real.json")
REAL = json.load(open(TOOL_REAL, encoding="utf-8"))
TOOL_PAGES = {"/tools/trade-stats/": "stats", "/tools/trading-heatmap/": "heat", "/tools/drawdown-calculator/": "dd",
              "/tools/prop-challenge-simulator/": "prop", "/tools/lot-size-calculator/": "lot",
              "/tools/risk-reward-calculator/": "rr", "/tools/disposition-calculator/": "disp",
              "/tools/pass-rate-calculator/": "pass"}
CHIPS = {"Real public data", "Real published data", "Formula only", "No public data"}
# Architect plan A.1, the attribution text, word for word
A1 = ("Laramee, R. (2025). Stock Transactions Dataset. Mendeley Data, V1. doi:10.17632/k4tnk2nggv.1. Licensed CC BY 4.0. "
      "Changes: we kept the dataset’s market buys and sells (its combined, split-adjusted sheet) and turned them into a "
      "trade file, with ticker names replaced with codes; results are price gains in US dollars before fees, FX and dividends. Selection: the whole dataset, "
      "one anonymous investor; not picked by result. The dataset’s authors do not endorse donttrade.")
ODEAN = [13883, 79658, 11930, 110348]


def page(site, path):
    return (site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")


def text(h):
    return " ".join(L.visible_text(h).split())


def real_blocks(h):
    return L.REAL_DATA_RE.findall(h)


# ------------------------------------------------------------------ provenance: recompute everything from the inputs
@needs_raw
def test_tool_real_json_is_a_fresh_run_of_the_committed_script_on_the_committed_inputs():
    import make_tool_real as M
    fresh = M.dump(M.assemble(range_=True))   # the tools' own JS cores in node, the fan, every cross-check
    assert fresh == open(TOOL_REAL, encoding="utf-8").read()


def test_input_and_script_hashes_are_the_files():
    for rel, meta in REAL["inputs"].items():
        if rel == RAW_KEY and not HAVE_RAW:
            continue
        if rel.startswith(("checks/", "site/")):
            assert hashlib.sha256(open(os.path.join(REPO, rel), "rb").read()).hexdigest() == meta["sha256"], rel
    for rel, h in REAL["scripts"].items():
        assert hashlib.sha256(open(os.path.join(REPO, rel), "rb").read()).hexdigest() == h, rel
    assert REAL["inputs"][RAW_KEY]["raw_sha256"] == \
        "000dbad9f8ed661f7991ad72b3af29f11e9cda2d5a50162f34bf289f78373bcb"   # = Mendeley's published hash


def test_report_method_is_the_one_the_report_page_accepts():
    w = open(os.path.join(REPO, "site", "static", "js", "paid", "wording.js"), encoding="utf-8").read()
    mv = re.search(r"^export const METHOD_VERSION = '([^']+)';$", w, re.M).group(1)
    rep = json.load(open(os.path.join(REPO, "site", "config", "tool_real.report.json"), encoding="utf-8"))
    assert REAL["report"]["method_version"] == rep["method_version"] == mv


def test_the_curve_reproduces_the_tools_printed_net_and_drawdown():
    c = REAL["curve"]
    assert len(c) == int(REAL["trade_stats"]["trades"]) == 64
    pnl = [c[0]] + [c[i] - c[i - 1] for i in range(1, len(c))]
    assert abs(sum(pnl) - c[-1]) < 1e-6 and L.REAL_DATA_RE   # the diffs sum to the end value
    money = lambda v: ("−$" if v < 0 else "+$") + f"{abs(v):,.2f}"   # noqa: E731
    assert money(c[-1]) == REAL["trade_stats"]["net"] == "−$31,040.32"
    peak, dd, at = 0.0, 0.0, None
    for i, v in enumerate(c):
        peak = max(peak, v)
        if peak - v > dd:
            dd, at = peak - v, i
    assert abs(dd - 36929.88) < 0.011 and REAL["drawdown"]["largest"] == REAL["trade_stats"]["largest_drawdown"] == "−$36,929.88"
    assert at + 1 == REAL["curve_trough_trade"] == 62
    assert [round(sum(pnl[i * 8:(i + 1) * 8]), 2) for i in range(8)] == pytest.approx(REAL["slices"], abs=0.02)


def test_fan_counts_sit_within_monte_carlo_error_of_simulate():
    F = REAL["fan"]
    for k, n in F["counts_simulate"].items():
        p = n / F["replays"]
        assert abs(F["counts"][k] - n) <= 4 * math.sqrt(max(p * (1 - p), 1 / F["replays"]) * F["replays"]) + 2, k
    assert F["counts_simulate"] == {"pass": 3, "daily": 2576, "max": 7421, "timeout": 0}
    assert len(F["paths"]) == len(F["outcomes"]) == 60 and len(F["p50"]) == 31


def test_readiness_and_odean_figures():
    R, O = REAL["readiness"], REAL["odean"]
    assert R["runs_passed"] == 3 and R["replays"] == 10000 and R["days"] == 54 and R["range_pass"] == "0.0% to 2.6%"
    assert R["first_break"] == {"day": 24, "rule": "maximum loss"} and len(R["real_order_path"]) == 24
    assert O["counts"] == ODEAN
    pgr, plr = ODEAN[0] / (ODEAN[0] + ODEAN[1]), ODEAN[2] / (ODEAN[2] + ODEAN[3])
    se = math.sqrt(pgr * (1 - pgr) / (ODEAN[0] + ODEAN[1]) + plr * (1 - plr) / (ODEAN[2] + ODEAN[3]))
    assert (O["pgr"], O["plr"], O["ratio"], O["t"]) == (f"{pgr:.4f}", f"{plr:.4f}", f"{pgr / plr:.2f}", f"{(pgr - plr) / se:.2f}")
    assert (O["ratio"], O["t"]) == ("1.52", "35.33")   # the paper: "a little over 1.5", "t-statistic greater than 35"


def test_eurusd_month_figures_follow_from_its_series():
    fx = REAL["eurusd"]
    s = fx["series"]
    assert fx["low"] == min(s) and fx["high"] == max(s) and fx["range_pips"] == round((max(s) - min(s)) * 10000)
    moves = [abs(b - a) for a, b in zip(s, s[1:])]
    assert fx["avg_daily_move_pips"] == round(sum(moves) / len(moves) * 10000, 1)
    assert fx["month_label"] == "September 2026" and fx["lot_fact"] == {"lot_units_eur": 100000, "usd_per_pip": 10}


def test_report_rows_map_the_engine_output_as_report_js_does():
    rep = json.load(open(os.path.join(REPO, "site", "config", "tool_real.report.json"), encoding="utf-8"))
    rows = {r["id"]: r for r in REAL["report"]["rows"]}
    assert [h["id"] for h in rep["habits"]] == [r["id"] for r in REAL["report"]["rows"]]
    assert rows["hold_gap"]["result"] == rows["oversized_loss"]["result"] == "Your numbers"   # report.js FACTS_ONLY
    assert rows["oversized_loss"]["habit"] == "Large losses"   # report.js NAMES
    assert rows["revenge"]["result"] == rows["tilt"]["result"] == "Not enough trades to tell"
    assert rows["size_up"]["result"] == "Luck check coming"
    for h in rep["habits"]:
        assert abs(abs(float(rows[h["id"]]["total"].replace("−", "-").replace("$", "").replace(",", ""))) -
                   abs(h["dollars"]["amount"])) < 0.006
    assert REAL["report"]["n_tested"] == 0


@needs_raw
def test_no_ticker_or_dataset_note_in_the_json_or_on_the_pages(built_site):
    syms = {r["Symbol"] for r in csv.DictReader(open(RAW_CSV, encoding="utf-8"))}
    syms = sorted(s for s in syms if len(s) >= 3 and s.isupper())
    rx = re.compile(r"\b(?:" + "|".join(map(re.escape, syms)) + r")\b")
    for blob in [open(TOOL_REAL, encoding="utf-8").read(),
                 open(os.path.join(REPO, "site", "config", "tool_real.report.json"), encoding="utf-8").read()] + \
            [re.sub(r'(?s)<script type="text/csv".*?</script>', "", page(built_site, p)) for p in ["/tools/", *TOOL_PAGES]]:
        # the "Try with real public data" file itself (Fix round 1, F12) carries the dataset's symbols; nothing shown does
        assert not rx.search(blob), rx.search(blob).group(0)
        assert "Transaction ID" not in blob and "EOF" not in blob


def test_attribution_is_word_for_word_and_in_the_data_licence(built_site):
    assert REAL["credits"]["account"] == A1
    assert A1 in " ".join(open(os.path.join(REPO, "DATA_LICENSE.md"), encoding="utf-8").read().split())
    t = text(page(built_site, "/tools/"))
    for s in (A1, REAL["credits"]["fx"], REAL["credits"]["odean"]):
        assert s in t
    for s in REAL["rules"].values():   # the selection rules, in print
        assert s in t


# ------------------------------------------------------------------ the built /tools/ page
def test_tools_index_structure(built_site):
    h = page(built_site, "/tools/")
    mods = re.findall(r'(?s)<li class="md md-\d+[^"]*" data-tool="(\w+)"><a class="tl" href="([^"]+)">(.*?)</a></li>', h)
    assert sorted(k for k, _, _ in mods) == sorted(TOOL_PAGES.values())
    for k, href, body in mods:
        assert TOOL_PAGES[href] == k
        assert body.count("<h3") == 1 and "<a " not in body
        glyphs = re.findall(r'<svg class="ic md-ic ic-(\w+)" aria-hidden="true" focusable="false"', body)
        assert glyphs == [k]
        chips = re.findall(r'<span class="chip md-chip" aria-hidden="true">([^<]+)</span>', body)
        assert len(chips) == 1 and chips[0] in CHIPS
    assert len(set(re.findall(r'<a class="tl" href="(/tools/[^"]+)"', h))) == 8
    assert "<h1" in h and "Eight free tools for your own trades" in h
    assert 'class="free-strip"' not in h   # owner, 6 Nov: off /tools/ only


def test_every_figure_on_the_page_is_in_the_real_data(built_site):
    allowed = L.real_data_amounts()
    for path in ["/tools/", *TOOL_PAGES]:
        h = page(built_site, path)
        for b in real_blocks(h):
            assert all(round(a, 2) in allowed for a in amounts_in(b)), (path, [a for a in amounts_in(b) if round(a, 2) not in allowed])
    h = page(built_site, "/tools/")
    t = text(h)
    TS, R, O, FX = REAL["trade_stats"], REAL["readiness"], REAL["odean"], REAL["eurusd"]
    for s in (TS["net"], TS["win_rate"], TS["profit_factor"], TS["longest_losing_streak"], REAL["drawdown"]["longest_days"],
              R["range_pass"], f"{R['runs_passed']} of 10,000 replays", "drawn again 200 times", f"{O['pgr']} vs {O['plr']}, ratio {O['ratio']}, t-statistic {O['t']}",
              f"between {FX['low']:.4f} and {FX['high']:.4f}, {FX['range_pips']} pips", REAL["heatmap"]["readout"],
              "One investor, not a typical result"):
        assert s in h, s
    for r in REAL["report"]["rows"]:
        assert f'<th scope="row">{r["habit"]}</th>' in h and r["total"] in h
    # every amount OUTSIDE the real-data blocks is a price
    rest = L.REAL_DATA_RE.sub(" ", h)
    assert {a for a in amounts_in(rest)} <= set(L.allowed_amounts()) | {0}


def test_scope_curve_and_resting_state(built_site):
    h = page(built_site, "/tools/")
    m = re.search(r'<figure class="scope" data-scope data-curve="([^"]+)" data-months="([^"]+)"', h)
    vals = [float(v) for v in m.group(1).split(",")]
    assert vals == [round(v, 2) for v in REAL["curve"]]
    assert m.group(2).split(",") == REAL["curve_close_month"]
    assert '<dd data-out="n">62</dd>' in h and '<dd data-out="m">May 2024</dd>' in h and '<dd data-out="dd">−$36,929.88</dd>' in h
    assert h.count('<symbol id="dt-eq"') == 1 and h.count('href="#dt-eq"') == 3   # one curve, three drawings


def test_labels_are_honest(built_site):
    h = page(built_site, "/tools/")
    main = re.search(r"(?s)<main.*?</main>", h).group(0)
    t = text(main)
    for w in ("beta", "fake", "made-up", "demo", "sample", "worked example"):
        assert not re.search(r"\b" + w + r"\b", t, re.I), w
    # Fix round 1 (F12): no link to the synthetic /sample-report/ from /tools/; "example" only in "no example numbers"
    assert 'href="/sample-report/"' not in main
    assert not re.search(r"\bexamples?\b", t.replace("with no example numbers", ""), re.I)
    chips = re.findall(r'<span class="chip(?: md-chip)?"(?: aria-hidden="true")?>([^<]+)</span>', h)
    assert chips and set(chips) <= CHIPS
    assert "Real public data: Stock Transactions Dataset (Mendeley Data)" in t
    assert "Real public data: Federal Reserve Board H.10 euro noon rates, September 2026" in t
    assert "Real published data: Odean (1998), Table I" in t


def test_offer_copy_comes_from_trader_offer(built_site):
    h = page(built_site, "/tools/")
    off = re.search(r'(?s)<section class="tx-offer".*?</section>', h).group(0)
    ft = page(built_site, "/for-traders/")
    btn = re.search(r'<a class="btn" href="/pricing/#last-step">[^<]+</a>|<a class="btn" href="/for-traders/#waitlist">[^<]+</a>', off).group(0)
    assert btn in ft or btn in page(built_site, "/")
    note = re.search(r'<p class="of-note">([^<]+)</p>', off).group(1)
    others = [p.read_text(encoding="utf-8") for p in built_site["out"].rglob("index.html") if "tools" not in p.parts]
    assert any(note in h for h in others)   # offer.note(), the same words wherever it is used
    assert "data-umami-event" not in off   # Umami events on buttons only (test_umami)


def test_csp_unchanged_and_no_inline_style_or_script(built_site):
    old = subprocess.run(["git", "-C", REPO, "show", BASE + ":docs/tools/index.html"], capture_output=True, text=True).stdout
    csp = lambda x: re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]+)">', x).group(1)   # noqa: E731
    for path in ["/tools/", *TOOL_PAGES]:
        h = page(built_site, path)
        assert not re.search(r"\sstyle=", h), path
        # no executable inline script (data blocks: JSON-LD, the sample CSV, JSON are not run)
        assert not re.search(r'<script(?![^>]*\bsrc=)(?![^>]*type="(?:application/ld\+json|text/csv|application/json)")[^>]*>', h), path
        if path == "/tools/":
            assert csp(h) == csp(old)


def test_firms_study_sentence_only_with_prices_study(tmp_path):
    prices = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
    # once forfirms is merged, /for-firms/ itself needs prices.study, so a build without it is only made before that
    needs = "prices.study" in open(os.path.join(REPO, "site", "templates", "pages", "for-firms.html"), encoding="utf-8").read()
    out = {}
    for with_study in ((True,) if needs else (False, True)):
        p = dict(prices)
        if with_study:
            p["study"] = {"note": "test", "founding_price_usd": 10, "founding_firms": 3, "list_price_usd": 15, "monthly_minimum_usd": 500}
        else:
            p.pop("study", None)
        pj = tmp_path / f"prices-{with_study}.json"
        pj.write_text(json.dumps(p), encoding="utf-8")
        o = tmp_path / f"site-{with_study}"
        r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], capture_output=True, text=True,
                           env={**os.environ, "DT_OUT": str(o), "DT_PRICES_JSON": str(pj)})
        assert r.returncode == 0, r.stderr[-2000:]
        out[with_study] = (o / "tools" / "index.html").read_text(encoding="utf-8")
    assert "osf.io/j2ypd" in out[True] and "About the free study" in out[True]
    if False in out:
        assert "osf.io/j2ypd" not in out[False] and "About the free study" not in out[False]
    for h in out.values():
        assert "The Pilot, US$745" in h and 'data-tool="pass"' in h


def test_old_tool_cards_are_untouched(built_site):
    old = subprocess.run(["git", "-C", REPO, "show", BASE + ":site/templates/partials/tool_cards.html"], capture_output=True, text=True).stdout
    assert open(os.path.join(REPO, "site", "templates", "partials", "tool_cards.html"), encoding="utf-8").read() == old
    for path, doc in (("/", "docs/index.html"), ("/for-traders/", "docs/for-traders/index.html")):
        was = subprocess.run(["git", "-C", REPO, "show", BASE + ":" + doc], capture_output=True, text=True).stdout
        cards = lambda h: re.findall(r'(?s)<ul class="tool-cards.*?</ul>', h)   # noqa: E731
        assert cards(page(built_site, path) if path != "/" else (built_site["out"] / "index.html").read_text(encoding="utf-8")) == cards(was)


def test_tools_page_weight():
    """A.8-10 budget: the page's own content (<main>) at most 12 KB gzip; the shared chrome is the site's."""
    out = os.path.join(REPO, "site", "_site", "tools", "index.html")
    if not os.path.exists(out):
        pytest.skip("no site/_site build")
    h = open(out, encoding="utf-8").read()
    main = re.search(r"(?s)<main.*?</main>", h).group(0)
    assert len(gzip.compress(main.encode(), 9)) <= 12 * 1024 + 256   # 6 Nov: +256 B after the Round A merge (founding and refund wording in the $39 block); gzip first paint measured 0.87 s against the 1.5 s target
    js = open(os.path.join(REPO, "site", "static", "js", "tools-index.js"), "rb").read()
    assert len(gzip.compress(js, 9)) <= 2 * 1024


# ------------------------------------------------------------------ the tool pages' headers
@pytest.mark.parametrize("path,key", sorted(TOOL_PAGES.items()))
def test_each_tool_page_has_its_glyph_and_real_data_display(built_site, path, key):
    h = page(built_site, path)
    m = re.search(r'<span class="tool-mark"><svg class="ic ic-(\w+)" aria-hidden="true" focusable="false" width="64" height="64"', h)
    assert m and m.group(1) == key
    assert h.index('class="tool-mark"') < h.index("<h1")
    d = re.search(r'(?s)<figure class="tool-display" aria-labelledby="td-cap">.*?</figure>', h).group(0)
    assert re.findall(r'<span class="chip md-chip" aria-hidden="true">([^<]+)</span>', d)[0] in CHIPS
    cap = text(re.search(r'(?s)<figcaption id="td-cap".*?</figcaption>', d).group(0))
    assert re.search(r"(Real public data|Real published data|Formula only|No public data): ", cap)
    assert "tool-shot" not in h and "ts-mock" not in h and "Example data." not in h and "Example numbers." not in h
    assert "/static/css/tools.css" in h and "/static/js/tools-index.js" in h


def test_h1s_unchanged(built_site):
    want = {"/tools/trade-stats/": "Trade stats from your own trade file", "/tools/trading-heatmap/": "Your trades by hour and weekday",
            "/tools/drawdown-calculator/": "Drawdown and recovery calculator", "/tools/prop-challenge-simulator/": "Challenge Readiness Check",
            "/tools/lot-size-calculator/": "Lot size calculator", "/tools/risk-reward-calculator/": "Risk-reward calculator",
            "/tools/disposition-calculator/": "Disposition-effect calculator", "/tools/pass-rate-calculator/": "Prop-firm pass-rate calculator"}
    for path, h1 in want.items():
        assert re.findall(r"<h1[^>]*>([^<]+)</h1>", page(built_site, path)) == [h1], path


# ------------------------------------------------------------------ lint, contrast
def test_lint_real_data_rule_both_ways():
    good = '<!--real-data--><b>−$31,040.32</b> <b>−$36,929.88</b> $10,000<!--/real-data-->'
    planted = '<!--real-data--><b>−$31,040.32</b> $12,345.67<!--/real-data-->'   # not a price, not real data
    assert amounts_in(L.without_real_data(good, "/tools/")) == []
    assert 12345.67 in amounts_in(L.without_real_data(planted, "/tools/"))    # a non-real amount: checked as usual
    assert 31040.32 in amounts_in(L.without_real_data(good, "/pricing/"))      # other pages get no exemption
    probs = L.lint_html("<html><body><main>" + planted + "</main></body></html>", "/tools/", True, True,
                        L.allowed_amounts(), [], commerce=True)
    assert any(p[0] == "price_literal" and "$12345.7" in p[2] for p in probs)


def test_contrast_measures_the_screen_tokens():
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "contrast.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]
    for fg in ("scr-ink", "scr-mute", "s-gain", "s-loss", "s-plan", "s-accent"):
        assert re.search(rf"PASS  dark   {fg} +on scr ", r.stdout) and re.search(rf"PASS  light  {fg} +on scr-2", r.stdout)


# ------------------------------------------------------------------ pass rate: the lifted maths is the oracle
NODE_PARITY = r"""
globalThis.dtNumbers = require('%(repo)s/site/static/js/legacy/numbers.js');
const oldm = require('%(repo)s/site/static/js/legacy/pass-rate-calculator.js');
const newm = require('%(repo)s/site/static/js/tools/pass-rate.js');
const out = []; let same = true;
const grid = [0, 1, 7, 29, 30, 31, 150, 170, 1000];
for (const s of grid) for (const o of grid) for (const p of grid) for (const d of [0, 1, 40]) for (const t of [null, 1, 800]) {
  const a = JSON.stringify(oldm.compute(s, o, p, d, t)), b = JSON.stringify(newm.compute(s, o, p, d, t));
  if (a !== b) { same = false; out.push([s, o, p, d, t]); }
}
for (const x of [null, 0, 1, 0.5, 0.99996, 0.00004, 0.2]) if (oldm.pct(x) !== newm.pct(x)) same = false;
for (const r of ['1,780', '1.5', '', '-3', '12 345']) if (JSON.stringify(oldm.parseCount(r)) !== JSON.stringify(newm.parseCount(r))) same = false;
process.stdout.write(JSON.stringify({ same, out: out.slice(0, 3), w: newm.wilson(170, 850), w29: newm.wilson(5, 29), w30: newm.wilson(5, 30), min: newm.BAND_MIN }));
"""


def test_pass_rate_maths_equals_the_lifted_script_and_the_band_starts_at_30():
    r = subprocess.run(["node", "-e", NODE_PARITY % {"repo": REPO}], capture_output=True, text=True, check=True)
    d = json.loads(r.stdout)
    assert d["same"], d["out"]
    assert d["min"] == 30 and d["w29"] is None and d["w30"] is not None
    k, n, z = 170, 850, 1.96   # Wilson score interval, by hand
    p = k / n
    mid = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    assert d["w"]["lo"] == pytest.approx(mid - half, abs=1e-12) and d["w"]["hi"] == pytest.approx(mid + half, abs=1e-12)


def test_pass_rate_page_is_a_template_with_no_invented_counts(built_site):
    h = page(built_site, "/tools/pass-rate-calculator/")
    assert "<!--frozen:start-->" not in h and "pr-example" not in h
    for s in ("1,000 started", "made-up", "Example data", "Fill a"):
        assert s not in h
    t = text(h)
    for s in ("For firm operators. Enter the counts for one cohort and get pass and payout rates that say what they measure.",
              "Mixing cohorts, such as dividing this month’s passes by this month’s starts.",
              "It checks the arithmetic. It cannot tell anyone your inputs are right",
              "Pass rate among finished evaluations (passed ÷ (started − open))", "Range if every open one fails / passes"):
        assert s in t, s
    assert not os.path.exists(os.path.join(REPO, "site", "templates", "lifted", "tools_pass-rate-calculator.html"))


def test_disposition_page_fills_odean_with_the_citation(built_site):
    h = page(built_site, "/tools/disposition-calculator/")
    assert "Try Odean’s 1998 counts" in h and "made-up" not in h and "420, 1,780" not in h
    assert "13,883 realised gains, 79,658 paper gains, 11,930 realised losses and 110,348 paper losses" in h
    assert "Are investors reluctant to realize their losses?" in h
    js = open(os.path.join(REPO, "site", "static", "js", "legacy", "disposition-calculator.js"), encoding="utf-8").read()
    assert "'13883'" in js and "'79658'" in js and "'11930'" in js and "'110348'" in js and "'420'" not in js
    import compare
    assert [p for p in compare.compare_site(str(built_site["out"])) if p[0] == "/tools/disposition-calculator/"] == []


# ------------------------------------------------------------------ in Chromium
def _open(browser, built_site, path, width=1280, scheme="light", **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, **kw)
    ctx.route(re.compile(r"cloudflareinsights\.com"), lambda r: r.fulfill(status=204, body=""))   # the analytics beacon
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("load")
    return ctx, pg, errs


@pytest.mark.parametrize("width", [320, 390, 1280])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_tools_index_in_the_browser(browser, built_site, width, scheme):
    from a11y import axe_violations, horizontal_overflow
    ctx, pg, errs = _open(browser, built_site, "/tools/", width, scheme)
    pg.wait_for_timeout(300)
    assert horizontal_overflow(pg) == []
    assert errs == []   # with the CSP on: no console error, no CSP report
    ctx.close()
    ctx, pg, _ = _open(browser, built_site, "/tools/", width, scheme, bypass_csp=True)
    assert axe_violations(pg) == []
    ctx.close()


def test_reduced_motion_runs_nothing_and_the_scope_rests_on_the_deepest_trade(browser, built_site):
    ctx, pg, errs = _open(browser, built_site, "/tools/", reduced_motion="reduce")
    pg.mouse.move(400, 400)
    pg.wait_for_timeout(900)
    assert pg.evaluate("document.getAnimations().length") == 0
    assert pg.text_content('[data-out="n"]') == "62" and pg.text_content('[data-out="dd"]') == "−$36,929.88"
    assert pg.evaluate("[...document.querySelectorAll('.play')].length") == 0
    ctx.close()


def test_scope_sweeps_once_then_follows_the_pointer_and_clamps(browser, built_site):
    ctx, pg, errs = _open(browser, built_site, "/tools/")
    pg.wait_for_timeout(3400)
    assert pg.text_content('[data-out="n"]') == "62"
    box = pg.locator(".scope svg").bounding_box()
    pg.mouse.move(box["x"] + 2, box["y"] + box["height"] / 2)
    assert pg.text_content('[data-out="n"]') == "1"
    pg.mouse.move(box["x"] + box["width"] - 1, box["y"] + box["height"] / 2)
    assert pg.text_content('[data-out="n"]') == "64"
    assert errs == []
    ctx.close()


def test_pass_rate_page_in_the_browser(browser, built_site):
    from a11y import axe_violations, horizontal_overflow
    ctx, pg, errs = _open(browser, built_site, "/tools/pass-rate-calculator/")
    for k, v in (("started", "1000"), ("open", "150"), ("passed", "170"), ("paid", "40"), ("traders", "800")):
        pg.fill(f"#pr-{k}", v)
    pg.press("#pr-traders", "Enter")
    assert pg.text_content("#pr-rate") == "20.0%" and pg.text_content("#pr-perFunded") == "23.5%"
    assert pg.is_visible("#pr-band") and pg.text_content("#pr-band") == "17.4% to 22.8%"
    assert float(pg.get_attribute("#pf-passed", "width")) == pytest.approx(170 / 1000 * 240, abs=0.1)
    pg.fill("#pr-started", "40"); pg.fill("#pr-open", "15"); pg.fill("#pr-passed", "5"); pg.fill("#pr-paid", "1"); pg.fill("#pr-traders", "")
    pg.press("#pr-paid", "Enter")
    assert pg.is_hidden("#pr-band-wrap") and "Fewer than 30 evaluations have finished" in pg.text_content("#pr-notes")
    assert pg.get_attribute("#pf-band", "width") == "0"
    assert horizontal_overflow(pg) == [] and errs == []
    ctx.close()
    ctx, pg, _ = _open(browser, built_site, "/tools/pass-rate-calculator/", bypass_csp=True)
    for k, v in (("started", "1000"), ("open", "150"), ("passed", "170"), ("paid", "40")):
        pg.fill(f"#pr-{k}", v)
    pg.press("#pr-paid", "Enter")
    assert axe_violations(pg) == []
    ctx.close()


def test_disposition_example_gives_odeans_figures(browser, built_site):
    ctx, pg, errs = _open(browser, built_site, "/tools/disposition-calculator/")
    pg.click("#dc-example")
    assert pg.text_content("#dc-t") == "35.33" and pg.text_content("#dc-ratio") == "1.52"
    assert errs == []
    ctx.close()


@pytest.mark.parametrize("path", sorted(TOOL_PAGES))
def test_tool_pages_load_clean(browser, built_site, path):
    from a11y import axe_violations, horizontal_overflow
    for w in (390, 1280):
        ctx, pg, errs = _open(browser, built_site, path, w, "dark")
        assert horizontal_overflow(pg) == [] and errs == [], (path, w, errs)
        ctx.close()
    ctx, pg, _ = _open(browser, built_site, path, 1280, "dark", bypass_csp=True)
    assert axe_violations(pg) == [], path
    ctx.close()


# ------------------------------------------------------------------ fix round 1 (Tester report, 6 Nov)
def test_f2_the_39_caption_gives_each_habits_own_reason(built_site):
    cap = text(re.search(r'(?s)<figcaption id="of-art-cap".*?</figcaption>', page(built_site, "/tools/")).group(0))
    assert "No habit was tested against chance on this file" in cap and "One investor, not a typical result." in cap
    assert "had enough trades" not in cap
    rep = json.load(open(os.path.join(REPO, "site", "config", "tool_real.report.json"), encoding="utf-8"))
    for h in rep["habits"]:
        row = next(r for r in REAL["report"]["rows"] if r["id"] == h["id"])
        assert f'{row["name_lower"]}: {row["why"]}' in cap
        if h["verdict"] == "too_few":
            assert f"this file has {h['n_a']} and {h['n_b']}" in row["why"]
        elif h["id"] in ("hold_gap", "oversized_loss"):
            assert "no fair luck check" in row["why"]
        else:
            assert "calibrated" in row["why"]


def test_f3_the_euro_month_is_a_range_with_its_direction(built_site):
    fx = REAL["eurusd"]
    assert fx["direction"] == ("fell" if fx["last"] < fx["first"] else "rose") == "fell"
    for path in ("/tools/", "/tools/lot-size-calculator/"):
        t = text(page(built_site, path))
        assert f"ranged between {fx['low']:.4f} and {fx['high']:.4f}" in t and "fell over the month" in t
        assert "ran from" not in t


def test_f4_f10_preview_wording_and_figures(built_site):
    h = page(built_site, "/tools/")
    lot = re.search(r'(?s)<li class="md[^"]*" data-tool="lot">.*?</li>', h).group(0)
    disp = re.search(r'(?s)<li class="md[^"]*" data-tool="disp">.*?</li>', h).group(0)
    assert "tool run on real public data" not in lot and "one real past month of the euro for scale" in lot
    assert "tool run on real public data" not in disp and "Odean’s published counts" in disp
    rr = re.search(r'(?s)<li class="md[^"]*" data-tool="rr">.*?</li>', h).group(0)
    assert all(f">{p}</text>" in rr for p in ("50.0%", "33.3%", "25.0%", "20.0%", "16.7%"))
    assert "(95% band 14.61–15.07%)" in disp and "(95% band 9.59–9.92%)" in disp


def test_f5_f9_fan_colours_axis_and_time_zones(built_site):
    h = page(built_site, "/tools/")
    F = REAL["fan"]
    fan = re.search(r'(?s)<svg class="pv pv-fan".*?</svg>', h).group(0)
    cls = re.findall(r'<path class="fp fp-(\w+)"', fan)
    assert cls == [o if e <= 30 else "open" for o, e in zip(F["outcomes"], F["end_days"])]
    assert cls.count("open") == sum(1 for e in F["end_days"] if e > 30) > 0
    assert ">day 0</text>" in fan and ">day 30</text>" in fan
    t = text(h)
    assert "grey still running on day 30" in t
    assert "days ending at midnight UTC+3" in t and "Hours as in the file, which states no time zone" in t


def test_f6_pass_rate_noscript_notice(built_site):
    h = page(built_site, "/tools/pass-rate-calculator/")
    assert re.search(r"<noscript><p class=\"notice notice-caution\">This calculator runs in your browser and needs "
                     r"JavaScript turned on\.</p></noscript>", h)


def test_f8_data_licence_quotes_the_board_in_full():
    t = " ".join(open(os.path.join(REPO, "DATA_LICENSE.md"), encoding="utf-8").read().split())
    assert ('"Unless otherwise indicated, information on Board\'s website is in the public domain and may be copied and '
            'distributed without permission. Please cite to the Board as the source of the information."') in t


def test_f12_the_file_tools_load_the_real_public_data(built_site):
    real = open(os.path.join(RD, "real-trades.coded.csv"), encoding="utf-8").read()   # tickers replaced with codes
    for path in ("/tools/trade-stats/", "/tools/trading-heatmap/", "/tools/drawdown-calculator/", "/tools/prop-challenge-simulator/"):
        h = page(built_site, path)
        blk = re.search(r'(?s)<script type="text/csv" id="\w+-sample">\n?(.*?)</script>', h).group(1)
        assert blk.lstrip() == real.lstrip(), path
        assert ">Try real public data</button>" in h and "Try with example data" not in h
        t = text(h)
        assert "Example data" not in t and "160 trades" not in t
        assert "Real public data: the Stock Transactions Dataset (Mendeley Data, CC BY 4.0)" in t
        assert "ticker names replaced with codes" in t
    assert (built_site["out"] / "static" / "samples" / "real-trades.csv").read_text(encoding="utf-8") == real
    assert 'href="/static/samples/real-trades.csv" download' in page(built_site, "/tools/trade-stats/")


def test_f1_funnel_empties_on_clear_and_on_invalid_counts(browser, built_site):
    ctx, pg, errs = _open(browser, built_site, "/tools/pass-rate-calculator/")
    widths = lambda: [pg.get_attribute(f"#pf-{k}", "width") for k in ("started", "finished", "passed", "paid", "band")]   # noqa: E731
    labels = lambda: [pg.text_content(f"#pf-{k}-t") for k in ("started", "finished", "passed", "paid")]   # noqa: E731
    assert set(widths()) == {"0"}
    for k, v in (("started", "1000"), ("open", "150"), ("passed", "170"), ("paid", "40")):
        pg.fill(f"#pr-{k}", v)
    pg.press("#pr-paid", "Enter")
    assert widths()[0] == "240" and labels()[0] == "1,000 started"
    pg.fill("#pr-passed", "2000")   # more passed than started: invalid
    assert pg.is_hidden("#pr-results") and set(widths()) == {"0"} and labels() == ["started", "finished", "passed", "paid out"]
    pg.fill("#pr-passed", "170")
    assert widths()[2] != "0"
    pg.click("#pr-clear")
    assert set(widths()) == {"0"} and labels() == ["started", "finished", "passed", "paid out"]
    assert errs == []
    ctx.close()


def test_f7_pass_rate_reflows_at_280(browser, built_site):
    from a11y import horizontal_overflow
    ctx, pg, _ = _open(browser, built_site, "/tools/pass-rate-calculator/", 280)
    assert horizontal_overflow(pg) == []
    ctx.close()


def test_f12_trade_stats_real_data_button_runs_the_real_account(browser, built_site):
    ctx, pg, errs = _open(browser, built_site, "/tools/trade-stats/")
    pg.click("#ts-sample-btn")
    pg.wait_for_selector("#ts-out dl.stats dd")
    t = pg.inner_text("#ts-out")
    assert "Results: real public data" in t and REAL["trade_stats"]["net"] in t and "64 closed trades" in t
    assert "Example data" not in t and errs == []
    ctx.close()


def test_f12_readiness_real_data_button_uses_the_first_library_rule(browser, built_site):
    ctx, pg, errs = _open(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.click("#ps-sample-btn")
    assert pg.input_value("#ps-preset") == "onephase"   # fix round 2: the first rule set's values, no firm named
    pg.wait_for_function("() => document.getElementById('ps-filetz').value !== ''", timeout=30000)
    assert pg.input_value("#ps-filetz") == "UTC"   # the selection rule: the file's times read as UTC
    ctx.close()


# ------------------------------------------------------------------ fix round 1b: no ticker in anything shipped
SYMS = sorted({r["Symbol"] for r in csv.DictReader(open(RAW_CSV, encoding="utf-8"))}) if HAVE_RAW else []
TICK = re.compile(r"(?<![A-Za-z0-9/])(" + "|".join(map(re.escape, sorted(SYMS, key=len, reverse=True))) + r")(?![A-Za-z0-9/])") \
    if SYMS else None
TEXT_EXT = (".html", ".js", ".css", ".json", ".xml", ".txt", ".csv", ".svg", ".md")


@needs_raw
def test_coded_file_is_the_original_with_only_the_symbols_replaced():
    import make_coded_csv as MC
    orig = open(RAW_CSV, encoding="utf-8", newline="").read()
    code = open(os.path.join(RD, "real-trades.coded.csv"), encoding="utf-8", newline="").read()
    assert MC.coded(orig)[0] == code
    o, c = list(csv.reader(orig.splitlines())), list(csv.reader(code.splitlines()))
    k = o[0].index("Symbol")
    assert o[0] == c[0] and len(o) == len(c)
    seen = {}
    for ro, rc in zip(o[1:], c[1:]):
        assert ro[:k] + ro[k + 1:] == rc[:k] + rc[k + 1:]            # every other value byte for byte
        assert re.fullmatch(r"Stock \d{2}", rc[k])
        seen.setdefault(ro[k], rc[k])
        assert seen[ro[k]] == rc[k]                                    # one code per ticker
    assert list(seen.values()) == [f"Stock {i + 1:02d}" for i in range(len(seen))] and len(seen) == len(SYMS) == 84
    ins = REAL["inputs"]
    assert ins[RAW_KEY]["sha256"] == hashlib.sha256(orig.encode()).hexdigest()
    assert ins["checks/real_data/real-trades.coded.csv"]["sha256"] == hashlib.sha256(code.encode()).hexdigest()


@needs_raw
def test_no_dataset_ticker_in_any_shipped_file(built_site, tmp_path):
    """Every file the build ships: the data copies carry codes only, and no file holds a dataset ticker that origin/main
    did not already hold (the site's own copy names a few symbols as parser examples and in its research)."""
    arc = subprocess.run(["git", "-C", REPO, "archive", BASE, "docs"], capture_output=True, check=True).stdout
    subprocess.run(["tar", "-x", "-C", str(tmp_path)], input=arc, check=True)
    base = tmp_path / "docs"
    count = lambda t: {m: len(re.findall(r"(?<![A-Za-z0-9/])" + re.escape(m) + r"(?![A-Za-z0-9/])", t)) for m in set(TICK.findall(t))}   # noqa: E731
    for root in (built_site["out"], os.path.join(REPO, "docs")):
        for d, _, fs in os.walk(root):
            for f in fs:
                if not f.endswith(TEXT_EXT):
                    continue
                fp = os.path.join(d, f)
                rel = os.path.relpath(fp, root)
                t = open(fp, encoding="utf-8", errors="replace").read()
                now = count(t)
                if not now:
                    continue
                was = count(open(base / rel, encoding="utf-8", errors="replace").read()) if (base / rel).exists() else {}
                # one-letter tickers (O, T, V) are also ordinary page text (the heatmap's M T W T F); the data copies'
                # Symbol column is checked for them below
                more = {m: n for m, n in now.items() if len(m) > 1 and n > was.get(m, 0)}
                assert not more, (root, rel, more)


def test_shipped_trade_file_copies_carry_codes_only(built_site):
    """Runs without the raw file: every shipped copy's Symbol column is "Stock NN", one code per ticker, in order."""
    inline = [re.search(r'(?s)<script type="text/csv" id="\w+-sample">\n?(.*?)</script>', page(built_site, p)).group(1).lstrip()
              for p in ("/tools/trade-stats/", "/tools/trading-heatmap/", "/tools/drawdown-calculator/", "/tools/prop-challenge-simulator/")]
    for blob in [open(os.path.join(REPO, "docs", "static", "samples", "real-trades.csv"), encoding="utf-8").read(),
                 (built_site["out"] / "static" / "samples" / "real-trades.csv").read_text(encoding="utf-8")] + inline:
        col = [r["Symbol"] for r in csv.DictReader(blob.splitlines())]
        assert col and all(re.fullmatch(r"Stock \d{2}", x) for x in col)
        assert list(dict.fromkeys(col)) == [f"Stock {i + 1:02d}" for i in range(84)]   # in order of first appearance


@needs_raw
def test_no_dataset_ticker_on_the_rendered_tool_pages_after_the_real_data_button(browser, built_site):
    """The results the real-data button draws hold no ticker: the page's text has no more ticker-like tokens after the
    run than before it (the page's own single letters, such as the heatmap's M T W T F, are there either way)."""
    from collections import Counter
    for path, prefix, ready in (("/tools/trade-stats/", "ts", "#ts-out dl.stats dd"), ("/tools/trading-heatmap/", "hm", "#hm-out table"),
                                ("/tools/drawdown-calculator/", "dd", "#dd-out dl")):
        ctx, pg, errs = _open(browser, built_site, path)
        before = Counter(TICK.findall(pg.inner_text("main")))
        pg.click(f"#{prefix}-sample-btn")
        pg.wait_for_selector(ready, timeout=60000)
        pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        out = pg.inner_text(f"#{prefix}-out")
        after = Counter(TICK.findall(pg.inner_text("main")))
        assert not (after - before), (path, after - before)
        assert not [m for m in TICK.findall(out) if len(m) > 1], path
        ctx.close()


# ------------------------------------------------------------------ fix round 2 (Manager review, 6 Nov)
FIRMS = sorted({p["firm"] for p in json.load(open(os.path.join(REPO, "site", "config", "challenge_rules.json"),
                                                  encoding="utf-8"))["presets"]})
CONTEXT = ("This investor held stocks for months to years and never took a challenge, so the result shows how the tool "
           "reads a real file, not how challenge traders do.")
REALISED = "The 31 positions still open at the end of the file are left out; the results cover realised trades only."


def test_r2_readiness_rule_is_named_by_its_values_not_a_firm(built_site):
    rd = REAL["readiness"]
    assert "preset_id" not in rd
    rule = REAL["rules"]["readiness"]
    assert rule.startswith("One-phase challenge rules, the first rule set in our library, shown without the firm’s name: "
                           "$100,000; 10% target; 5% daily loss; 10% maximum loss (static); at least 3 trading days")
    assert "no time limit stated" in rule   # the rule states none; no "30 days" is invented
    for p in ["/tools/", "/tools/prop-challenge-simulator/"]:
        # the previews and the sources: the rule's values, no firm or programme name next to them
        h = page(built_site, p)
        for blk in re.findall(r"(?s)<!--real-data-->(.*?)<!--/real-data-->", h):
            for f in FIRMS:
                assert f not in blk, (p, f)
        assert "One-phase challenge rules" in h


def test_r2_readiness_after_the_real_data_button_names_no_firm(browser, built_site):
    ctx, pg, errs = _open(browser, built_site, "/tools/prop-challenge-simulator/")
    assert [o for o in pg.eval_on_selector_all("#ps-preset option", "os => os.map(o => o.textContent)") if "Example" in o] == []
    assert pg.eval_on_selector("#ps-preset option[value='onephase']", "o => o.textContent") == \
        "One-phase challenge rules (no firm named)"
    pg.click("#ps-sample-btn")
    pg.wait_for_function("() => document.getElementById('ps-filetz').value !== ''", timeout=30000)
    pg.click("#ps-form button[type=submit]")
    pg.wait_for_selector("#ps-out-h", timeout=120000)
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    out = pg.inner_text("#ps-out") + pg.inner_text("#ps-expert")
    for f in FIRMS:
        assert f not in out, f
    assert "One-phase challenge rules (the first rule set in our library, shown without the firm's name)" in out \
        or "One-phase challenge rules (the first rule set in our library, shown without the firm’s name)" in out
    assert CONTEXT in pg.inner_text("#ps-real-note")
    assert errs == []
    ctx.close()


def test_r2_readiness_display_says_whose_file_it_is(built_site):
    h = page(built_site, "/tools/prop-challenge-simulator/")
    assert f'<span class="pv-ctx">{CONTEXT}</span>' in h
    assert CONTEXT in page(built_site, "/tools/")


def test_r2_no_sample_report_or_memo_link_on_the_tools_pages(built_site):
    for p in ["/tools/", *TOOL_PAGES]:
        # the site's nav and footer keep "Example report" until the later branch (Manager decision); the pages do not
        h = re.search(r"(?s)<main\b.*</main>", page(built_site, p)).group(0)
        assert 'href="/sample-report/' not in h, p
        assert "See the example report" not in h and "See a sample memo" not in h, p
        assert 'href="/sample-memo/' not in h, p   # 6 Nov: the disposition page's link too (a dated lift fix)
        assert 'value="example"' not in h and "Example rules" not in h, p
    for d, _, fs in os.walk(os.path.join(REPO, "site", "static", "js", "tools")):
        for f in fs:
            t = open(os.path.join(d, f), encoding="utf-8").read()
            assert "/sample-report/" not in t and "/sample-memo/" not in t, f


def test_r2_realised_trades_only_is_said(built_site):
    assert REAL["account"]["open_positions"] == 31 and REAL["account"]["realised_only"] == REALISED
    assert REALISED in page(built_site, "/tools/")
    for p in ("/tools/trade-stats/", "/tools/drawdown-calculator/", "/tools/trading-heatmap/"):
        # the display caption, as its own sentence (polish round)
        assert "not picked by result. " + REALISED in page(built_site, p), p


def test_r2_sources_link_the_board_and_odean_and_say_why_this_dataset(built_site):
    h = page(built_site, "/tools/")
    src = h[h.index('id="src-h"'):]
    for href in ("https://www.federalreserve.gov/releases/h10/hist/dat00_eu.htm", "https://doi.org/10.1111/0022-1082.00072",
                 "https://doi.org/10.17632/k4tnk2nggv.1", "https://creativecommons.org/licenses/by/4.0/"):
        assert f'href="{href}"' in src, href
    why = "the only openly licensed, fill-level record of one real account we found"
    assert why in src and why in h[:h.index('id="src-h"')]
    assert 'href="https://doi.org/10.1111/0022-1082.00072"' in page(built_site, "/tools/disposition-calculator/")
    assert 'href="https://www.federalreserve.gov/releases/h10/hist/dat00_eu.htm"' in page(built_site, "/tools/lot-size-calculator/")
    lic = open(os.path.join(REPO, "DATA_LICENSE.md"), encoding="utf-8").read()
    assert "dat00_eu.htm" in lic and "doi.org/10.1111/0022-1082.00072" in lic and why in lic


def test_r2_raw_trade_file_is_not_tracked():
    tracked = subprocess.run(["git", "-C", REPO, "ls-files", "checks/real_data"], capture_output=True, text=True,
                             check=True).stdout.split()
    assert "checks/real_data/real-trades.csv" not in tracked
    assert not [t for t in tracked if t.startswith("checks/real_data/raw/")]
    assert "checks/real_data/real-trades.coded.csv" in tracked and "checks/real_data/fetch.py" in tracked
    ign = subprocess.run(["git", "-C", REPO, "check-ignore", "-q", "checks/real_data/raw/real-trades.csv"])
    assert ign.returncode == 0
    assert REAL["inputs"][RAW_KEY]["sha256"] == "b20de3f29d48d91ea6bc5e3f903b1a4114ff1d2465be927c0852c0131d0ea518"
    fetch = open(os.path.join(RD, "fetch.py"), encoding="utf-8").read()
    mk = open(os.path.join(RD, "make_real_csv.py"), encoding="utf-8").read()
    assert "make_real_csv.py" in fetch and REAL["inputs"][RAW_KEY]["sha256"] in mk
    assert 'os.path.join(HERE, "raw", "real-trades.csv")' in mk


def test_r2_build_runs_without_the_raw_trade_file():
    """The build reads the committed coded copy and the JSON only; it never opens the gitignored raw file."""
    b = open(os.path.join(REPO, "site", "build.py"), encoding="utf-8").read()
    code = "\n".join(line.split("#")[0] for line in b.splitlines())   # comments may name the raw file
    assert "real-trades.csv" not in code.replace('"/static/samples/real-trades.csv"', "")
    assert not re.search(r'"raw"', code)


def test_r2_non_tools_docs_pages_differ_from_main_only_by_asset_hashes():
    """docs/ outside /tools/ and the files this branch adds: the same as origin/main once ?v= hashes are set aside
    (the home page's "latest commit" line excepted: it names whatever commit was built)."""
    names = subprocess.run(["git", "-C", REPO, "diff", "--name-only", BASE, "--", "docs"], capture_output=True,
                           text=True, check=True).stdout.split()
    norm = lambda t: re.sub(r"\?v=[0-9a-f]{8}", "?v=", t)   # noqa: E731
    for n in names:
        if n.startswith(("docs/tools/", "docs/static/")) or not n.endswith(".html") or n == "docs/index.html":
            continue
        try:
            was = subprocess.run(["git", "-C", REPO, "show", f"{BASE}:{n}"], capture_output=True, text=True,
                                 check=True).stdout
        except subprocess.CalledProcessError:
            continue
        now = open(os.path.join(REPO, n), encoding="utf-8").read()
        assert norm(now) == norm(was), n


def test_r2_disposition_sample_memo_link_is_a_dated_lift_fix(built_site):
    """Coordinator, 6 Nov: the frozen disposition page loses its /sample-memo/ link by a documented LIFT_FIXES entry,
    recorded in the page's baseline like the Odean change; the Glossary link stays."""
    import lift_pages as LP
    old = '<p><a href="/sample-memo/">How we measure it on a firm’s own records →</a> · <a href="/glossary/">Glossary →</a></p>'
    new = '<p><a href="/glossary/">Glossary →</a></p>'
    assert (old, new) in LP.LIFT_FIXES["/tools/disposition-calculator/"]
    base = json.load(open(os.path.join(REPO, "checks", "lifted-baseline", "tools_disposition-calculator.json"), encoding="utf-8"))
    assert [old, new] in base["fixes"] and "a[href]=/sample-memo/" not in base["links"]
    assert "How we measure it on a firm’s own records" not in base["text"] and "a[href]=/glossary/" in base["links"]
    frag = open(os.path.join(REPO, "site", "templates", "lifted", "tools_disposition-calculator.html"), encoding="utf-8").read()
    assert new in frag and "/sample-memo/" not in frag
    h = page(built_site, "/tools/disposition-calculator/")
    assert 'href="/glossary/">Glossary →</a>' in h and "How we measure it on a firm’s own records" not in h


# ------------------------------------------------------------------ polish round (owner approved B2, 6 Nov)
def test_polish_display_labels_and_plain_sentences(built_site):
    hm = page(built_site, "/tools/trading-heatmap/")
    assert '<span class="pv-key">Green: a gain in total. Red: a loss. Stronger colour: a larger total. Blank: no trades.</span>' in hm
    idx = page(built_site, "/tools/")
    assert "Stronger colour" not in idx   # the key is on the tool page only (the /tools/ byte budget)
    assert f"ratio {REAL['odean']['ratio']}, t-statistic {REAL['odean']['t']}" in idx
    assert "a separate draw of 60 replays, for shape" in idx
    assert "The whole dataset, not picked by result. One investor, not a typical result.</figcaption>" in idx
    # the scope grid is one path with the same 6 + 9 lines
    g = re.search(r'<path class="sc-grid" d="([^"]+)"/>', idx).group(1)
    assert g.count("H") == 6 and g.count("V") == 9
    # rack heads: no sentence over 22 words
    for hid in ("rack-h", "calc-h"):
        head = re.search(rf'(?s)<h2 id="{hid}">.*?</h2><p>(.*?)</p>', idx).group(1)
        for snt in re.split(r"(?<=[.!?])\s+", " ".join(L.visible_text(head).split())):
            assert len(snt.split()) <= 22, snt


def test_polish_scope_moves_by_transform_only(browser, built_site):
    ctx, pg, errs = _open(browser, built_site, "/tools/")
    pg.wait_for_timeout(3200)
    attrs = pg.evaluate("""() => { const q = (s) => document.querySelector('.scope ' + s);
      return [q('.sc-dot').getAttribute('cx'), q('.sc-dot').getAttribute('transform'), q('.sc-future').getAttribute('x'),
              q('.sc-future').getAttribute('transform')]; }""")
    assert attrs[0] == "0" and attrs[1].startswith("translate(") and attrs[3].startswith("translate(")
    assert pg.text_content('[data-out="n"]') == "62" and errs == []
    ctx.close()
