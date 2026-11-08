"""5 Nov 2026, the free-tools audit fixes (AUDIT-FREE-TOOLS-2026-11-05.md): one test per fix.

Engine fixes run in Node against the same files as the Python reference (the JS must equal it); page fixes run
in Chromium on a flag-on build (the live flags). Run file by file on the 2-core box.
"""
import json
import os
import random
import re
import subprocess
import sys
import tempfile
from decimal import Decimal

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "reference"))
import engine_ref as E  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
HDR = "Date,Time,Symbol,Side,Quantity,Price\n"


# ------------------------------------------------------------------ engine: JS vs the Python reference
def js_run(files):
    """The JS engine on each byte string → [{result|error}] (trades reduced to what is compared)."""
    with tempfile.TemporaryDirectory() as d:
        paths = []
        for i, b in enumerate(files):
            p = os.path.join(d, f"f{i}.csv")
            open(p, "wb").write(b)
            paths.append(p)
        script = os.path.join(d, "run.mjs")
        open(script, "w").write("""
import { runFile } from %r;
import fs from 'node:fs';
const out = [];
for (const p of process.argv.slice(2)) {
  const r = runFile(new Uint8Array(fs.readFileSync(p)));
  out.push(r.error ? { error: { code: r.error.code, row: r.error.row, column: r.error.column, message: r.error.message } }
    : { trades: r.result.trades.map((t) => [t.open_ts, t.close_ts, t.pnl, t.dir]), warnings: r.result.warnings.map((w) => [w.code, w.n]) });
}
console.log(JSON.stringify(out));
""" % ("file://" + os.path.join(REPO, "site", "static", "js", "engine", "index.js"),))
        r = subprocess.run(["node", script, *paths], capture_output=True, text=True, timeout=60)
        assert r.returncode == 0, r.stderr
        return json.loads(r.stdout)


def py_run(b):
    r = E.run_files([b])
    if "error" in r:
        e = r["error"]
        return {"error": {"code": e["code"], "row": e["row"], "column": e["column"]}}
    res = r["result"]
    return {"trades": [[t["open_ts"], t["close_ts"], t["pnl"], t["dir"]] for t in res["trades"]],
            "warnings": [[w["code"], w["n"]] for w in res["warnings"]]}


def two_trades(d1, d2, extra=""):
    return (HDR + f"{d1},09:30:00,AAA,Buy,10,100{extra}\n{d1},10:30:00,AAA,Sell,10,105{extra}\n"
            + f"{d2},09:30:00,AAA,Sell,10,110{extra}\n{d2},11:00:00,AAA,Buy,10,104{extra}\n").encode()


ISO = two_trades("2026-11-13", "2026-11-14")
SLASH_CASES = {
    "year first": two_trades("2026/11/13", "2026/11/14"),
    "day first, a day over 12": two_trades("13/11/2026", "14/11/2026"),
    "month first, a day over 12": two_trades("11/13/2026", "11/14/2026"),
    "one over-12 day decides all": two_trades("03/11/2026", "13/11/2026"),     # 3 Nov and 13 Nov
    "single digits padded": two_trades("2026/1/3", "2026/1/4"),
}


@pytest.mark.parametrize("name", list(SLASH_CASES))
def test_unambiguous_slash_dates_are_read_and_equal_the_iso_file(name):
    b = SLASH_CASES[name]
    js = js_run([b])[0]
    assert "trades" in js, js
    assert js == py_run(b)                              # the JS engine equals the Python reference
    if name in ("year first", "day first, a day over 12", "month first, a day over 12"):
        assert js["trades"] == js_run([ISO])[0]["trades"]   # the same instants as 2026-11-13 / 2026-11-14


def test_one_over_12_day_sets_the_order_for_the_whole_file():
    js = js_run([SLASH_CASES["one over-12 day decides all"]])[0]
    # 03/11/2026 is read day-first as 3 Nov, so the first trade opened on 3 Nov 2026 09:30 UTC
    assert js["trades"][0][0] == 1793698200000


def test_truly_ambiguous_and_mixed_slash_dates_are_still_refused_with_an_accurate_message():
    amb = two_trades("03/04/2026", "04/05/2026")
    js, = js_run([amb])
    assert js["error"]["code"] == "E_AMBIGUOUS_DATE" and js["error"]["row"] == 2 and js["error"]["column"] == "date"
    assert "12 or less" in js["error"]["message"] and "2026-09-01" in js["error"]["message"]
    assert js_run([amb])[0]["error"]["code"] == py_run(amb)["error"]["code"]
    mixed = two_trades("13/11/2026", "11/14/2026")            # day-first, then month-first
    m = js_run([mixed])[0]
    assert m["error"]["code"] == "E_BAD_DATE" and m["error"]["row"] == 4
    assert {k: m["error"][k] for k in ("code", "row", "column")} == py_run(mixed)["error"]
    two_digit = two_trades("13/11/26", "14/11/26")           # a two-digit year: the problem is the year form, not the order
    td = js_run([two_digit])[0]["error"]
    assert td["code"] == "E_BAD_DATE" and "four-digit year" in td["message"] and "told apart" not in td["message"]
    assert {k: td[k] for k in ("code", "row", "column")} == py_run(two_digit)["error"]
    both = two_trades("13/14/2026", "14/14/2026")             # no month over 12: an impossible date, not an ambiguous one
    bd = js_run([both])[0]["error"]
    assert bd["code"] == "E_BAD_DATE" and "both over 12" in bd["message"] and "12 or less" not in bd["message"]
    assert {k: bd[k] for k in ("code", "row", "column")} == py_run(both)["error"]


def test_datetime_column_with_slashes_and_the_single_cell_parser_unchanged():
    b = (b"Datetime,Symbol,Side,Quantity,Price\n13/11/2026 09:30:00,AAA,Buy,10,100\n13/11/2026 10:30:00,AAA,Sell,10,105\n")
    js, = js_run([b])
    assert js == py_run(b) and js["trades"][0][3] == "long", js
    with pytest.raises(E.EngineError):                    # parse_date itself still never guesses
        E.parse_date("03/04/2026", "generic", 1, "t")


def test_negative_quantity_is_flagged_not_silent():
    b = (HDR + "2026-11-05,09:30:00,AAA,Buy,-10,100\n2026-11-05,10:30:00,AAA,Sell,-10,105\n").encode()
    js, = js_run([b])
    assert js == py_run(b)
    assert js["warnings"] == [["W_NEGATIVE_QTY", 2]] and js["trades"][0][2] == 50
    ok, = js_run([ISO])
    assert ok["warnings"] == []                            # a normal file gets no new note


# ------------------------------------------------------------------ pages
def page_for(browser, built_site, path, width=1280, scheme="light"):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, timezone_id="UTC")
    pg = ctx.new_page()
    log = []
    pg.on("console", lambda m: log.append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: log.append("pageerror: " + str(e)))
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("networkidle")
    return ctx, pg, log


def clean(log):
    return [m for m in log if "cloudflareinsights" not in m and "net::ERR_FAILED" not in m and "preloaded" not in m]


def write_tmp(tmp_path, name, text):
    p = tmp_path / name
    p.write_text(text, encoding="utf-8")
    return str(p)


def round_trips(n_days, per_day=1, eur_every=0, pnl=48):
    """n_days days, per_day long trades each (open then close), optional currency column; USD unless EUR."""
    rows = ["Date,Time,Symbol,Side,Quantity,Price,Currency"]
    k = 0
    for d in range(n_days):
        day = f"2026-{1 + d // 28:02d}-{1 + d % 28:02d}"
        for i in range(per_day):
            k += 1
            cur = "EUR" if eur_every and k % eur_every == 0 else "USD"
            rows.append(f"{day},10:{i:02d}:00,S{k},Buy,1,100,{cur}")
            rows.append(f"{day},11:{i:02d}:00,S{k},Sell,1,{100 + pnl},{cur}")
    return "\n".join(rows) + "\n"


def ps_run(pg, target="1000", maxloss="500", days=None):
    pg.fill("#ps-target", target)
    pg.fill("#ps-maxloss", maxloss)
    pg.fill("#ps-daily", "")
    if days is not None:
        pg.fill("#ps-days", days)
    pg.click("#ps-run")
    pg.wait_for_selector("#ps-out:not([hidden])", timeout=90000)


# Fix 1 ---------------------------------------------------------------------------------------------------------
def test_challenge_check_shows_the_files_notes(browser, built_site, tmp_path):
    f = write_tmp(tmp_path, "mixed.csv", round_trips(40, 3, eur_every=3))
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", f)
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg, days="30")
    note = pg.inner_text("#ps-out #ps-warnings")
    assert "1 note about this file" in note and "mixes currencies" in note and "left out" in note
    assert pg.get_attribute("#ps-out #ps-warnings li", "data-code") == "W_MIXED_CURRENCY"
    # a clean file has no such box
    ctx2, pg2, _ = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg2.set_input_files("#ps-file", write_tmp(tmp_path, "clean.csv", round_trips(40, 3)))
    pg2.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg2, days="30")
    assert pg2.query_selector("#ps-out #ps-warnings") is None
    assert clean(log) == []
    ctx.close(); ctx2.close()


# Fix 2 ---------------------------------------------------------------------------------------------------------
def test_one_trade_headline_leads_with_the_caveat(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", write_tmp(tmp_path, "one.csv", round_trips(1)))
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg)
    assert pg.inner_text("#ps-out-h") == "Too few trading days to read: 1 day (1 trade)"
    assert "Passed in" not in pg.inner_text("#ps-out-h")
    assert "lean heavily on a few days" in pg.inner_text("#ps-out")      # the note stays under it
    assert pg.evaluate("document.activeElement.id") == "ps-out-h"
    assert clean(log) == []
    ctx.close()


def test_a_long_file_keeps_the_passed_in_headline(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", write_tmp(tmp_path, "long.csv", round_trips(60, 2)))
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg, target="100", maxloss="500", days="30")
    assert pg.inner_text("#ps-out-h").startswith("Passed in ")
    ctx.close()


# Fix 3 ---------------------------------------------------------------------------------------------------------
def test_whole_percent_never_shows_all_or_none_unless_exact(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/lot-size-calculator/")
    got = pg.evaluate("""async () => { const { wholePercent: w } = await import('/static/js/tools/format.js');
        return [w(1), w(0), w(0.9997), w(0.99996), w(0.0003), w(0.00004), w(0.004), w(0.996), w(0.5), w(0.124)]; }""")
    assert got == ["100%", "0%", "over 99.9%", "over 99.9%", "under 0.1%", "under 0.1%", "0.4%", "99.6%", "50%", "12%"]
    ctx.close()


def test_rare_busts_do_not_show_as_zero_percent(browser, built_site, tmp_path):
    # 3,999 days of +100 and one day of -600: a few of 10,000 replays break the 500 maximum loss
    rows = ["Date,Time,Symbol,Side,Quantity,Price"]
    for d in range(4000):
        day = f"{2000 + d // 336}-{1 + (d % 336) // 28:02d}-{1 + d % 28:02d}"
        loss = d == 17
        rows += [f"{day},10:00:00,A{d},Buy,1,1000", f"{day},11:00:00,A{d},Sell,1,{1000 - 600 if loss else 1100}"]
    f = write_tmp(tmp_path, "rare.csv", "\n".join(rows) + "\n")
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", f)
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=90000)
    ps_run(pg, target="1000", maxloss="500")
    text = pg.inner_text("#ps-out")
    assert pg.inner_text("#ps-out-h") == "Passed in over 99.9% of 10,000 replays"
    assert "Broke a rule under 0.1%" in text and "Broke a rule 0%" not in text
    ctx.close()


def test_card_text_never_shows_all_or_none_unless_exact(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    lines = pg.evaluate("""async () => { const m = await import('/static/js/card/readiness-card.js');
        return m.cardLines({ pass: 0.9997, bust: 0.0003, timeout: 0, runs: 10000, rule: null, habit: null, rulesPct: null, whatif: null, example: false }); }""")
    assert lines["headline"] == "Passed in over 99.9% of 10,000 replays"
    assert lines["shares"] == ["Passed over 99.9%", "Broke a rule under 0.1%", "Out of time 0%"]
    ctx.close()


# Fix 4 ---------------------------------------------------------------------------------------------------------
def lot_page(browser, built_site):
    return page_for(browser, built_site, "/tools/lot-size-calculator/")


def lots_by_hand(formula):
    """Redo the page's worked lines from the printed numbers only, with Decimal."""
    nums = lambda s: [Decimal(x.replace(",", "")) for x in re.findall(r"(?<![\w.])\d[\d,]*(?:\.\d+)?", s)]
    last = [ln for ln in formula.split("\n") if ln.startswith("Lots =")][0]
    a, b, shown = nums(last.split("=", 1)[1])
    return a / b, shown


def test_lot_size_formula_reproduces_by_hand(browser, built_site):
    ctx, pg, log = lot_page(browser, built_site)
    fixed = [("100", "12.34", "0.1"), ("25", "3", "0.0005"), ("100", "37", "0.0123"), ("250", "7.5", "0.02"), ("100", "10", "1")]
    rnd = random.Random(5)
    cases = fixed + [(str(rnd.randint(10, 5000)), f"{rnd.uniform(0.5, 90):.{rnd.randint(0, 3)}f}", f"{rnd.uniform(0.01, 12):.{rnd.randint(1, 4)}f}") for _ in range(25)]
    cases = [c for c in cases if Decimal(c[1]) > 0 and Decimal(c[2]) > 0]
    for risk, stop, vpp in cases:
        pg.check("input[name=ls-mode][value=amount]") if pg.query_selector("input[name=ls-mode][value=amount]") else None
        pg.fill("#ls-risk", risk); pg.fill("#ls-stop", stop); pg.fill("#ls-vpp", vpp)
        pg.click("#ls-form button[type=submit]")
        pg.wait_for_selector("#ls-out:not([hidden]) pre.formula")
        formula = pg.inner_text("#ls-out pre.formula")
        by_hand, shown = lots_by_hand(formula)
        true = Decimal(risk) / (Decimal(stop) * Decimal(vpp))
        # the printed per-lot figure is the exact product, so the division of printed numbers equals the true size
        assert abs(by_hand - true) <= Decimal("0.00005") * max(1, true), (risk, stop, vpp, formula)
        assert abs(by_hand - shown) <= Decimal("0.00006"), (risk, stop, vpp, formula, by_hand)
        assert abs(true - shown) <= Decimal("0.00006"), (risk, stop, vpp, formula)
    ctx.close()


def test_lot_size_percent_mode_formula_reproduces(browser, built_site):
    ctx, pg, log = lot_page(browser, built_site)
    pg.check("input[name=ls-mode][value=pct]")
    pg.fill("#ls-balance", "1234.56"); pg.fill("#ls-risk", "1.5"); pg.fill("#ls-stop", "12.34"); pg.fill("#ls-vpp", "0.1")
    pg.click("#ls-form button[type=submit]")
    pg.wait_for_selector("#ls-out:not([hidden]) pre.formula")
    formula = pg.inner_text("#ls-out pre.formula")
    assert "= 18.5184" in formula.split("\n")[0] and "÷ 1.234 =" in formula and "÷ 18.5184" not in formula or "18.5184 ÷ 1.234" in formula
    by_hand, shown = lots_by_hand(formula)
    assert abs(by_hand - Decimal("18.5184") / Decimal("1.234")) < Decimal("0.0001") and abs(by_hand - shown) < Decimal("0.00006")
    ctx.close()


def test_lot_size_page_does_not_load_the_file_parsers(browser, built_site):
    for path in ("/tools/lot-size-calculator/", "/tools/risk-reward-calculator/"):
        ctx = browser.new_context()
        pg = ctx.new_page()
        urls = []
        pg.on("request", lambda r: urls.append(r.url))
        pg.goto(built_site["url"] + path)
        pg.wait_for_load_state("networkidle")
        js = [u for u in urls if "/static/js/" in u]
        assert not [u for u in js if "/engine/" in u or "read-file" in u or "tool-state" in u], js
        assert any("form-errors" in u for u in js)
        ctx.close()


# Fix 5 and 6: the offers ---------------------------------------------------------------------------------------
def built(built_site, rel):
    return (built_site["out"] / rel / "index.html").read_text(encoding="utf-8")


def card(html):
    m = re.search(r'(?s)<aside class="notice notice-gap next-step".*?</aside>', html)
    assert m
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m.group(0))).strip()


def test_pass_rate_calculator_leads_with_the_firm_pilot(built_site):
    t = card(built(built_site, "tools/pass-rate-calculator"))
    assert t.startswith("Test your whole book") and "Start a Pilot, $745" in t
    assert t.index("$745") < t.index("$39")                       # the pilot first, the trader test second
    h = built(built_site, "tools/pass-rate-calculator")
    assert 'href="/for-firms/#request"' in h and 'data-lead="firm"' in h
    # the trader test is still there, as the smaller line
    assert "Trading your own account?" in t


def test_other_tools_keep_the_trader_offer_first_and_typed_ones_say_what_to_bring(built_site):
    for rel, typed in [("tools/lot-size-calculator", True), ("tools/risk-reward-calculator", True), ("tools/drawdown-calculator", True),
                       ("tools/disposition-calculator", True), ("tools/trade-stats", False), ("tools/trading-heatmap", False),
                       ("tools/prop-challenge-simulator", False)]:
        t = card(built(built_site, rel))
        assert t.startswith("Is this habit real, or luck?") and "Get the report for $39" in t, rel
        assert ("Bring an export of your trade history" in t) == typed, rel


def test_pay_dialog_says_what_to_bring(built_site):
    h = built(built_site, "tools/trade-stats")
    d = re.search(r'(?s)<dialog class="pay-dialog".*?</dialog>', h).group(0)
    assert "What to bring: an export of your trade history" in re.sub(r"<[^>]+>", "", d)


# Fix 7: the column picker on the three file tools --------------------------------------------------------------
@pytest.mark.parametrize("path,prefix,out", [("/tools/trade-stats/", "ts", "#ts-out-h"), ("/tools/trading-heatmap/", "hm", "#hm-out-h"),
                                             ("/tools/drawdown-calculator/", "dd", "#dd-out-h")])
def test_unknown_headings_get_the_column_picker(browser, built_site, tmp_path, path, prefix, out):
    text = open(os.path.join(FIX, "tester", "fx_tl.paste.txt"), encoding="utf-8").read().replace("\tAmount\t", "\tQ\t", 1)
    f = write_tmp(tmp_path, "fx.tsv", text)
    ctx, pg, log = page_for(browser, built_site, path)
    pg.set_input_files(f"#{prefix}-file", f)
    pg.wait_for_selector(f"#{prefix}-map:not([hidden])", timeout=60000)
    assert pg.is_hidden(f"#{prefix}-error")
    assert [s.get_attribute("data-field") for s in pg.query_selector_all(f"#{prefix}-map select")] == ["qty"]
    pg.click(f"#{prefix}-map-btn")
    assert pg.inner_text(f"#{prefix}-map-err") == "Pick a column for each box."
    pg.select_option(f"#{prefix}-map-qty", label="Q")
    pg.click(f"#{prefix}-map-btn")
    pg.wait_for_selector(f"{out}", timeout=60000)
    assert pg.is_hidden(f"#{prefix}-map")
    assert clean(log) == []
    ctx.close()


def test_slash_dates_open_on_the_trade_stats_page(browser, built_site, tmp_path):
    f = write_tmp(tmp_path, "dmy.csv", SLASH_CASES["day first, a day over 12"].decode())
    ctx, pg, log = page_for(browser, built_site, "/tools/trade-stats/")
    pg.set_input_files("#ts-file", f)
    pg.wait_for_selector("#ts-out-h", timeout=60000)
    assert pg.is_hidden("#ts-error") and "2 closed trades" in pg.inner_text("#ts-out")
    amb = write_tmp(tmp_path, "amb.csv", two_trades("03/04/2026", "04/05/2026").decode())
    pg.set_input_files("#ts-file", amb)
    pg.wait_for_selector("#ts-error:not([hidden])")
    assert "12 or less" in pg.inner_text("#ts-error")
    ctx.close()


# Fix 8: the heatmap on a phone -----------------------------------------------------------------------------------
def week_file():
    rows = ["Date,Time,Symbol,Side,Quantity,Price"]
    for i in range(14):   # 2026-11-02 is a Monday; two full weeks, Monday to Sunday
        day = f"2026-11-{2 + i:02d}"
        for h in (9, 14):
            rows += [f"{day},{h:02d}:05:00,A{i}{h},Buy,1,100", f"{day},{h:02d}:35:00,A{i}{h},Sell,1,{101 + (i % 3) - 1}"]
    return "\n".join(rows) + "\n"


def test_heatmap_on_a_phone_lists_all_seven_weekdays_without_page_scroll(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/trading-heatmap/", width=390)
    pg.set_input_files("#hm-file", write_tmp(tmp_path, "week.csv", week_file()))
    pg.wait_for_selector("#hm-out-h", timeout=60000)
    assert pg.is_visible("#hm-compact") and pg.is_hidden("#hm-grid")
    first = pg.inner_text("#hm-compact .heat-hour")
    for wd in ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"):
        assert wd in first, first
    for el in pg.query_selector_all("#hm-compact .heat-c"):          # every cell is fully on screen
        box = el.bounding_box()
        assert box["x"] >= 0 and box["x"] + box["width"] <= 390 + 0.5, box
    assert pg.evaluate("document.documentElement.scrollWidth") <= 390
    assert clean(log) == []
    ctx.close()


def test_heatmap_on_a_desktop_keeps_the_table(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/trading-heatmap/", width=1280)
    pg.set_input_files("#hm-file", write_tmp(tmp_path, "week.csv", week_file()))
    pg.wait_for_selector("#hm-out-h", timeout=60000)
    assert pg.is_visible("#hm-grid") and pg.is_hidden("#hm-compact")
    ctx.close()


# Fix 9: landmarks and announcements --------------------------------------------------------------------------------
def landmark_names(pg):
    return pg.evaluate("""() => [...document.querySelectorAll('main section[aria-labelledby], main [role=region][aria-label]')]
        .map((e) => e.getAttribute('aria-label') || document.getElementById(e.getAttribute('aria-labelledby')).textContent.trim())""")


@pytest.mark.parametrize("path,prefix", [("/tools/trade-stats/", "ts"), ("/tools/drawdown-calculator/", "dd")])
def test_result_landmarks_have_unique_names_and_the_result_is_announced(browser, built_site, path, prefix):
    ctx, pg, log = page_for(browser, built_site, path)
    pg.click(f"#{prefix}-sample-btn")
    pg.wait_for_selector(f"#{prefix}-out-h", timeout=60000)
    names = landmark_names(pg)
    assert len(names) == len(set(names)), names
    pg.wait_for_function("() => document.getElementById('tool-live') && document.getElementById('tool-live').textContent.length > 0")
    live = pg.eval_on_selector("#tool-live", "e => [e.getAttribute('role'), e.getAttribute('aria-live'), e.textContent]")
    assert live[0] == "status" and live[1] == "polite" and live[2].startswith("Results: real public data.")   # Fix round 1 (F12)
    assert clean(log) == []
    ctx.close()


def test_calculators_announce_their_result(browser, built_site):
    ctx, pg, log = lot_page(browser, built_site)
    pg.fill("#ls-risk", "100"); pg.fill("#ls-stop", "10"); pg.fill("#ls-vpp", "1")
    pg.click("#ls-form button[type=submit]")
    pg.wait_for_function("() => document.getElementById('tool-live').textContent.includes('Position size')")
    assert "Position size: 10.0000 lots" in pg.inner_text("#tool-live")
    ctx.close()
    ctx, pg, log = page_for(browser, built_site, "/tools/risk-reward-calculator/")
    for k, v in {"#rr-entry": "100", "#rr-stop": "95", "#rr-target": "110"}.items():
        pg.fill(k, v)
    pg.click("#rr-form button[type=submit]")
    pg.wait_for_function("() => document.getElementById('tool-live').textContent.includes('R multiple')")
    ctx.close()


# Fix 10: the small ones ---------------------------------------------------------------------------------------------
def test_expectancy_that_rounds_to_zero_has_no_sign(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/risk-reward-calculator/")
    for k, v in {"#rr-entry": "100", "#rr-stop": "95", "#rr-target": "110", "#rr-winrate": "33.3"}.items():
        pg.fill(k, v)
    pg.click("#rr-form button[type=submit]")
    pg.wait_for_selector("#rr-out:not([hidden])")
    text = pg.inner_text("#rr-out")
    assert "−0.00R" not in text and "-0.00R" not in text and "+0.00R" not in text
    assert "= 0.00R" in text
    pg.fill("#rr-winrate", "50")
    pg.click("#rr-form button[type=submit]")
    assert "+0.50R" in pg.inner_text("#rr-out")
    ctx.close()


def test_drawdown_percent_label_matches_what_is_computed(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/trade-stats/")
    pg.fill("#ts-balance", "10000")
    pg.click("#ts-sample-btn")
    pg.wait_for_selector("#ts-out-h", timeout=60000)
    label = pg.inner_text("tr:has([data-k=max_drawdown_pct]) th")
    assert "% of its high" in label and "% of balance" not in label
    shown = pg.inner_text("[data-k=max_drawdown_pct]")
    # recompute with the label's own definition: depth ÷ (starting balance + equity high), the worst such share
    dd = pg.evaluate("""async () => { const csv = document.getElementById('ts-sample').textContent.replace(/^\\s+/, '');
        const { runFile } = await import('/static/js/engine/index.js');
        const r = runFile(new TextEncoder().encode(csv)).result; let eq = 0, peak = 0, best = 0;
        for (const t of r.trades) { eq += t.pnl; peak = Math.max(peak, eq); const top = 10000 + peak; best = Math.max(best, (top - (10000 + eq)) / top); }
        return best; }""")
    assert shown == f"{dd * 100:.1f}%"
    ctx.close()


# ------------------------------------------------------------------ fix round 1
CARD_FEW = """async () => { const m = await import('/static/js/card/readiness-card.js');
    return [m.cardLines({ pass: 1, bust: 0, timeout: 0, runs: 10000, rule: null, habit: null, rulesPct: null, example: false,
      whatif: { personal: { max_trades: 1 }, a: 0.5, b: 0.6 }, few: { days: 1, trades: 1 } }),
      m.altText({ pass: 1, bust: 0, timeout: 0, runs: 10000, rule: null, habit: null, rulesPct: null, whatif: null, example: false, few: { days: 28, trades: 40 } })]; }"""


def test_card_and_alt_text_say_too_few_days_not_passed(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    lines, alt = pg.evaluate(CARD_FEW)
    assert lines["headline"] == "Too few trading days to read: 1 day (1 trade)" and lines["shares"] == []
    assert not [f for f in lines["facts"] if "assed" in f]                  # no what-if "passed a to b" claim either
    assert alt.startswith("Too few trading days to read: 28 days (40 trades).") and "Passed" not in alt
    # the real page: the canvas label and the headline agree, for a file under 30 days and for one over
    pg.set_input_files("#ps-file", write_tmp(tmp_path, "one.csv", round_trips(1)))
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg)
    pg.wait_for_function("() => document.getElementById('ps-card-canvas').getAttribute('aria-label')")
    label = pg.get_attribute("#ps-card-canvas", "aria-label")
    assert label.startswith(pg.inner_text("#ps-out-h") + ".") and "Passed" not in label
    ctx2, pg2, _ = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg2.set_input_files("#ps-file", write_tmp(tmp_path, "long.csv", round_trips(60, 2)))
    pg2.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg2, target="100", maxloss="500", days="30")
    pg2.wait_for_function("() => document.getElementById('ps-card-canvas').getAttribute('aria-label')")
    assert pg2.get_attribute("#ps-card-canvas", "aria-label").startswith("Passed in ")
    ctx.close(); ctx2.close()


def test_headline_counts_days_like_its_trigger(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", write_tmp(tmp_path, "d28.csv", round_trips(28, 2)))     # 56 trades on 28 days
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg)
    assert pg.inner_text("#ps-out-h") == "Too few trading days to read: 28 days (56 trades)"
    ctx.close()
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", write_tmp(tmp_path, "d30.csv", round_trips(30, 2)))     # 30 days is enough
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg, target="100")
    assert pg.inner_text("#ps-out-h").startswith("Passed in ")
    ctx.close()


def test_no_beta_wording_on_the_tool_pages_or_pricing_faq(built_site):
    faq = re.search(r"<summary>Which files work\?</summary><p>(.*?)</p>", built(built_site, "pricing"), re.S).group(1)
    assert "not yet tested on a real export" in faq and "beta" not in faq.lower()
    for rel in ("tools/trade-stats", "tools/trading-heatmap", "tools/drawdown-calculator", "tools/prop-challenge-simulator",
                "tools/lot-size-calculator", "tools/risk-reward-calculator"):
        h = re.sub(r"<script.*?</script>", "", built(built_site, rel), flags=re.S)
        assert not re.search(r"beta", re.sub(r"<[^>]+>", " ", h), re.I), rel
    ts = built(built_site, "tools/trade-stats")
    assert "Not yet tested on a real export" in ts and "tell us if a column reads wrong" in ts
    for js in ("tools/file-tool.js", "tools/trade-stats.js", "tools/prop-sim.js", "tools/file-worker.js", "engine/errors.js"):
        src = (built_site["out"] / "static" / "js" / js).read_text(encoding="utf-8")
        assert not re.search(r"['\"`][^'\"`\n]*\bbeta\b", src, re.I), js        # no beta inside a string


def test_unverified_format_result_says_the_factual_caveat(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/trade-stats/")
    pg.set_input_files("#ts-file", os.path.join(FIX, "tradingview", "forty_trades.csv"))
    pg.wait_for_selector("#ts-out-h", timeout=60000)
    out = pg.inner_text("#ts-out")
    assert "TradingView Order History export (not yet tested on a real export)" in out
    assert "not yet tested on a real export" in pg.inner_text("#ts-warnings") and "beta" not in out.lower()
    ctx.close()


JUNK = {
    "doc.pdf": b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n1 0 obj\n<< /Type /Catalog >>\nendobj\n" * 3,
    "img.png": b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x01,\x00\x00\x01,\x08\x06" + bytes(range(256)) * 4,
    "random.bin": bytes(random.Random(3).randrange(256) for _ in range(4000)),
    "prose.txt": b"Dear trader, here are my thoughts on the market this week.\nIt went up and then it went down.\nBest wishes\n" * 5,
    "data.json": json.dumps({"trades": [{"a": 1, "b": 2, "c": 3, "d": 4, "e": 5, "f": 6}] * 5}).encode(),
    "two_cols.csv": b"Name,Value\nalpha,1\nbeta,2\ngamma,3\n",
    "numbers.csv": b"1,2,3,4,5,6\n7,8,9,10,11,12\n13,14,15,16,17,18\n",
}


@pytest.mark.parametrize("path,prefix", [("/tools/trade-stats/", "ts"), ("/tools/trading-heatmap/", "hm"),
                                         ("/tools/drawdown-calculator/", "dd"), ("/tools/prop-challenge-simulator/", None)])
def test_junk_files_get_not_recognised_not_the_picker(browser, built_site, tmp_path, path, prefix):
    ctx, pg, log = page_for(browser, built_site, path)
    inp, err, mp = (f"#{prefix}-file", f"#{prefix}-error", f"#{prefix}-map") if prefix else ("#ps-file", "#ps-file-error", "#ps-map")
    for name, data in JUNK.items():
        f = tmp_path / name
        f.write_bytes(data)
        pg.set_input_files(inp, str(f))
        pg.wait_for_selector(f"{err}:not([hidden])", timeout=30000)
        assert pg.is_hidden(mp), name
        assert "was not recognised" in pg.inner_text(err) or "not a text" in pg.inner_text(err), (name, pg.inner_text(err))
    ctx.close()


GUESSED = ("When,Instrument,Dir,Size,Px\n2026-11-02 09:30:00,AAA,Buy,10,100\n2026-11-02 10:30:00,AAA,Sell,10,105\n"
           "2026-11-03 09:30:00,AAA,Sell,10,110\n2026-11-03 11:00:00,AAA,Buy,10,104\n")


def test_guessed_columns_say_matched_from_headings(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/trade-stats/")
    pg.set_input_files("#ts-file", write_tmp(tmp_path, "guess.csv", GUESSED))
    pg.wait_for_selector("#ts-out-h", timeout=60000)
    w = pg.inner_text("#ts-warnings")
    assert "matched from your headings" in w and "yourself" not in w
    # picked by the person: the old words stay
    text = open(os.path.join(FIX, "tester", "fx_tl.paste.txt"), encoding="utf-8").read().replace("\tAmount\t", "\tQ\t", 1)
    pg.set_input_files("#ts-file", write_tmp(tmp_path, "fx.tsv", text))
    pg.wait_for_selector("#ts-map:not([hidden])", timeout=60000)
    pg.select_option("#ts-map-qty", label="Q")
    pg.click("#ts-map-btn")
    pg.wait_for_selector("#ts-warnings", timeout=60000)
    assert "You matched these columns yourself" in pg.inner_text("#ts-warnings")
    ctx.close()


def test_risk_reward_never_echoes_all_or_none_for_a_near_value(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/risk-reward-calculator/")
    for wr, want in (("99.99", "win rate of over 99.9%"), ("0.04", "win rate of under 0.1%"), ("50", "win rate of 50.0%")):
        for k, v in {"#rr-entry": "100", "#rr-stop": "95", "#rr-target": "110", "#rr-winrate": wr}.items():
            pg.fill(k, v)
        pg.click("#rr-form button[type=submit]")
        pg.wait_for_selector("#rr-out:not([hidden])")
        text = pg.inner_text("#rr-out")
        assert want in text and "100.0%" not in text and " 0.0%" not in text, (wr, text)
    ctx.close()


def test_heatmap_and_drawdown_announce_key_figures(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/trading-heatmap/")
    pg.click("#hm-sample-btn")
    pg.wait_for_selector("#hm-out-h", timeout=60000)
    pg.wait_for_function("() => document.getElementById('tool-live') && document.getElementById('tool-live').textContent.includes('Highest total')")
    live = pg.inner_text("#tool-live")
    assert "closed trades" in live and "Lowest total" in live and "−" in live or "+" in live
    ctx.close()
    ctx, pg, log = page_for(browser, built_site, "/tools/drawdown-calculator/")
    pg.click("#dd-sample-btn")
    pg.wait_for_selector("#dd-out-h", timeout=60000)
    pg.wait_for_function("() => document.getElementById('tool-live') && document.getElementById('tool-live').textContent.length > 0")
    live = pg.inner_text("#tool-live")
    assert "Enter a starting balance" in live and "—" not in live and "Largest drawdown:" in live
    ctx.close()


# ------------------------------------------------------------------ fix round 2
def test_format_caveat_is_not_yet_tested_on_a_real_export(browser, built_site):
    ts = built(built_site, "tools/trade-stats")
    assert "Not yet tested on a real export" in ts and "tell us if a column reads wrong" in ts
    for rel in ("tools/trade-stats", "tools/trading-heatmap", "tools/drawdown-calculator", "tools/prop-challenge-simulator", "pricing"):
        h = re.sub(r"<script.*?</script>", "", built(built_site, rel), flags=re.S)
        assert "sample files only" not in h, rel
    ctx, pg, log = page_for(browser, built_site, "/tools/trade-stats/")
    pg.set_input_files("#ts-file", os.path.join(FIX, "tradingview", "forty_trades.csv"))
    pg.wait_for_selector("#ts-out-h", timeout=60000)
    assert "TradingView Order History export (not yet tested on a real export)" in pg.inner_text("#ts-out")
    w = pg.inner_text("#ts-warnings")
    assert "not yet tested on a real export" in w and "tell us if a column reads wrong" in w and "sample files only" not in pg.inner_text("#ts-out")
    ctx.close()


def test_small_sample_page_shows_no_pass_rate_anywhere(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", write_tmp(tmp_path, "d20.csv", round_trips(20, 2)))
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg, target="100")
    assert pg.inner_text("#ps-out-h").startswith("Too few trading days to read: 20 days")
    out = pg.inner_text("#ps-out")
    assert not re.search(r"\d(\.\d)?%\s*(passed|of 10,000)|Passed \d|Passed over|Broke a rule \d|passed \d", out), out
    assert pg.query_selector("#ps-out .rc-legend") is None and pg.query_selector("#ps-out svg") is None
    assert pg.is_hidden("#ps-whatif")
    pg.click("#ps-expert summary")
    assert "%" not in pg.inner_text("#ps-expert table")
    label = pg.get_attribute("#ps-card-canvas", "aria-label") or ""
    assert "Passed" not in label
    ctx.close()
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", write_tmp(tmp_path, "d40.csv", round_trips(40, 2)))      # 30 days or more: everything is back
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg, target="100")
    assert pg.query_selector("#ps-out .rc-legend") is not None and pg.query_selector("#ps-out svg") is not None
    assert pg.is_visible("#ps-whatif")
    ctx.close()


def test_card_alt_text_has_no_double_full_stop(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    alts = pg.evaluate("""async () => { const m = await import('/static/js/card/readiness-card.js');
      const base = { pass: 0.5, bust: 0.3, timeout: 0.2, runs: 10000, rule: 'daily', habit: null, rulesPct: null, whatif: null, example: true };
      return [m.altText({ ...base, few: { days: 28, trades: 40 } }), m.altText(base)]; }""")
    for a in alts:
        assert ".." not in a and ". ." not in a, a
    assert alts[0].startswith("Too few trading days to read: 28 days (40 trades). Replays of so few days lean heavily on a few days. ")
    assert alts[1].startswith("Passed in 50% of 10,000 replays. Passed 50%, Broke a rule 30%, Out of time 20%.")
    ctx.close()


# ------------------------------------------------------------------ fix round 3
def losing_file(tmp_path, days, name):
    return write_tmp(tmp_path, name, round_trips(days, 2, pnl=-48))


def test_small_sample_range_table_and_bust_shares_are_blank(browser, built_site, tmp_path):
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", losing_file(tmp_path, 20, "lose20.csv"))
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg, target="1000", maxloss="100")
    assert pg.inner_text("#ps-out-h").startswith("Too few trading days to read")
    rule = pg.inner_text("#ps-v-rule")
    assert "of busts" not in rule and "Not shown" in rule and not re.search(r"\d+(\.\d)?%", rule)
    pg.click("#ps-expert summary")
    pg.click("#ps-range-btn")
    pg.wait_for_selector("#ps-range-out table", timeout=120000)
    cells = pg.inner_text("#ps-range-out table")
    assert "%" not in cells.replace("90% range", "") and "to " not in cells.split("Share", 1)[1], cells
    assert "Per-rule counts" in pg.inner_text("#ps-expert")
    ctx.close()
    ctx, pg, log = page_for(browser, built_site, "/tools/prop-challenge-simulator/")
    pg.set_input_files("#ps-file", losing_file(tmp_path, 40, "lose40.csv"))                 # 30 days or more: back as before
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    ps_run(pg, target="1000", maxloss="100")
    assert "of busts" in pg.inner_text("#ps-v-rule")
    pg.click("#ps-expert summary")
    pg.click("#ps-range-btn")
    pg.wait_for_selector("#ps-range-out table", timeout=120000)
    assert " to " in pg.inner_text("#ps-range-out table")
    ctx.close()


def test_expectancy_label_reads_naturally_at_the_extremes(browser, built_site):
    ctx, pg, log = page_for(browser, built_site, "/tools/risk-reward-calculator/")
    for wr, want in (("99.99", "Expectancy at a win rate of over 99.9%"), ("0.04", "Expectancy at a win rate of under 0.1%"),
                     ("50", "Expectancy at a win rate of 50.0%")):
        for k, v in {"#rr-entry": "100", "#rr-stop": "95", "#rr-target": "110", "#rr-winrate": wr}.items():
            pg.fill(k, v)
        pg.click("#rr-form button[type=submit]")
        pg.wait_for_selector("#rr-out:not([hidden])")
        text = pg.inner_text("#rr-out")
        assert want in text and "at a over" not in text and "at a under" not in text, (wr, text)
    ctx.close()
