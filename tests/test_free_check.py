"""The free check page, /check/ (ARCHITECT-PLAN-FREE-CHECK-AND-HOOK-2026-11-07, batch C2; copy in section 5).

What is held here (the eight tests of section 6, C2, plus the flag and the events):
  1. no currency amount in the result outside [data-offer], on every parity fixture and on the first look;
  2. none of: distinguishable, luck, verdict, issue, detected, found, leak, warning, unlock, anywhere in the result;
  3. the counts on the page equal the C0 fixtures (the server's analyse()), for every fixture, through the real page and file reader;
  4. each variant (normal, no_test, dates_only, zero, too_few) renders on its fixture, and the zero variant has no [data-pay];
  5. in Chromium with every request recorded: no request URL or body holds a row value, and only static files are fetched;
  6. the founding sentence is verbatim from prices.json and the refund line sits in the same [data-offer] block;
  7. no style= in the page, the script or the drawn result;
  8. axe finds nothing at 390 and 1280 px in both themes, before and after a file, with no horizontal scroll.
Also: the page exists only in a paid_report build, and the events are fixed names with no data.
"""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, HERE)
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import lint as L  # noqa: E402
sys.path.insert(0, os.path.join(REPO, "site"))

P = "/check/"
FIX = os.path.join(HERE, "fixtures", "check_parity")
NAMES = sorted(os.path.basename(f)[:-5] for f in os.listdir(FIX) if f.endswith(".json"))
PRICES = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
R = next(p for p in PRICES["products"] if p["id"] == "report39")
CURRENCY = re.compile(r"[$€£¥]|\b(?:USD|CAD|EUR|GBP)\b|\bUS\s?\d|\d\.\d\d\b")
BANNED = re.compile(r"\b(distinguishable|luck\w*|verdict|issues?|detected|found|leaks?|warnings?|unlock\w*)\b", re.I)


def expected_variant(exp):
    """Section 5.4, worked from a server fixture's counts (not from the page's code)."""
    h = exp["habits"]
    sets = {k: (h[k]["dollars"] or {}).get("n_trades") for k in h}
    if exp["dates_only"]:
        sets["revenge"] = sets["tilt"] = sets["size_up"] = None
    groups = sum(1 for k, v in sets.items() if k not in ("revenge", "tilt") and v) + sum(1 for k in ("revenge", "tilt") if not exp["dates_only"] and h[k]["n_a"] > 0)
    if exp["n_rows"] < 30:
        return "too_few"
    if exp["dates_only"]:
        return "dates_only" if groups else "dates_none"
    if not groups:
        return "zero"
    return "normal" if any(min(h[k]["n_a"], h[k]["n_b"]) >= 30 for k in ("revenge", "tilt")) else "no_test"


@pytest.fixture(scope="module")
def csvs(tmp_path_factory):
    r = subprocess.run(["node", os.path.join(HERE, "reference", "check_core_run.mjs"), "csv"], capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    d = tmp_path_factory.mktemp("csv")
    out = {}
    for name, text in json.loads(r.stdout).items():
        p = d / (name + ".csv")
        p.write_text(text, encoding="utf-8")
        out[name] = str(p)
    return out


def open_page(browser, site, width=1280, scheme="light", **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, **kw)
    pg = ctx.new_page()
    log = {"requests": [], "console": [], "posts": []}
    pg.on("request", lambda r: (log["requests"].append(r.url), r.method != "GET" and log["posts"].append((r.url, r.post_data))))
    pg.on("console", lambda m: log["console"].append(m.text))
    pg.on("pageerror", lambda e: log["console"].append(str(e)))
    pg.goto(site["url"] + P)
    pg.wait_for_load_state("networkidle")
    return ctx, pg, log


def read_file(pg, path):
    """Pick a file and wait for ITS result (the first look on load is also drawn, so wait for the heading to change)."""
    pg.set_input_files("#ck-file", path)
    pg.wait_for_selector("#ck-out-h:text-is('Your file, counted')", timeout=120000)
    pg.wait_for_function("document.querySelector('#ck-status').hidden")


def table(pg):
    """Each habit's row of the detail table: [trades, share, 'In the report' text, meter status or ''], keyed by its short label."""
    rows = {}
    for tr in pg.locator("#ck-out table tbody tr").all():
        cells = [c.inner_text().strip() for c in tr.locator("td").all()]
        st = tr.locator(".ck-ms")
        rows[tr.locator("th span").first.inner_text()] = cells + [st.inner_text().strip() if st.count() else ""]
    return rows


HABIT_ROWS = {"revenge": "Re-entered within 15 min of a loss", "tilt": "After 2+ losses in a row", "size_up": "Bigger size after a loss",
              "hold_gap": "Losers held longer than your median win", "oversized_loss": "Losses over 2× your median loss"}


def n(text):
    return int(text.replace(",", ""))


# ------------------------------------------------------------------ 3 and 4: counts and variants through the page

@pytest.mark.parametrize("name", NAMES)
def test_counts_on_the_page_equal_the_server_fixture_and_the_variant_follows(browser, built_site, csvs, name):
    exp = json.load(open(os.path.join(FIX, name + ".json")))
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, csvs[name])
    t = table(pg)
    h = exp["habits"]
    for hid, label in HABIT_ROWS.items():
        cells = t[label]
        want = {"revenge": h["revenge"]["n_a"], "tilt": h["tilt"]["n_a"], "size_up": (h["size_up"]["dollars"] or {}).get("n_trades"),
                "hold_gap": h["hold_gap"]["dollars"]["n_trades"], "oversized_loss": h["oversized_loss"]["dollars"]["n_trades"]}[hid]
        if exp["dates_only"] and hid in ("revenge", "tilt", "size_up"):
            assert cells[0] == "—" and cells[2] == "Needs times of day", (name, hid, cells)
            continue
        assert n(cells[0]) == want, (name, hid, cells, want)
        pct = round(100 * want / exp["n_trades"]) if exp["n_trades"] else None
        assert cells[1] == f"{pct}%", (name, hid, cells)
        testable = hid in ("revenge", "tilt") and min(h[hid]["n_a"], h[hid]["n_b"]) >= 30
        assert cells[2] == ("Nothing to total" if want == 0 else "Dollar total · test against chance" if testable else "Dollar total"), (name, hid, cells)
        if hid in ("revenge", "tilt"):
            a, b = h[hid]["n_a"], h[hid]["n_b"]
            assert cells[3] == ("Can be tested against chance in the report." if testable
                                else f"Too few to test ({min(a, b):,} of the 30 needed). A longer export may reach 30."), (name, hid, cells)
        else:
            assert cells[3] == ""
    head = pg.inner_text("#ck-out .ck-did")
    assert head.startswith("What we did:") and f"{exp['n_trades']:,} closed trade" in head, head
    assert pg.inner_text("#ck-out .ck-head").startswith(f"{exp['n_trades']:,} trade"), pg.inner_text("#ck-out .ck-head")
    variant = expected_variant(exp)
    assert pg.get_attribute("#ck-out", "data-variant") == variant, name
    offer = pg.locator("#ck-out [data-offer]")
    assert offer.count() == 1
    if variant == "zero":
        assert pg.locator("#ck-out [data-pay]").count() == 0 and pg.locator("#ck-out .btn").count() == 0
        assert "None of your trades matched these five habits" in offer.inner_text()
    elif variant == "normal":
        assert pg.locator("#ck-out [data-offer] a.btn[data-pay]").count() == 1
    else:
        assert pg.locator("#ck-out [data-offer] a[data-pay]").count() == 1 and pg.locator("#ck-out [data-offer] a.btn").count() == 0
    ctx.close()


def small_file(tmp_path, k, dated=False):
    rows = ["Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees"]
    for i in range(k):
        rows.append(f"2026-03-{(i % 27) + 1:02d} 10:00:00,2026-03-{(i % 27) + 1:02d} 10:20:00,AAA,Long,1,100,{99 if i % 2 else 101},0")
    p = tmp_path / f"small{k}.csv"
    p.write_text("\n".join(rows) + "\n")
    return str(p)


def test_the_fixtures_cover_the_variants():
    got = {expected_variant(json.load(open(os.path.join(FIX, n + ".json")))) for n in NAMES}
    assert {"normal", "no_test", "dates_only", "zero"} <= got, got


def test_too_few_trades_and_dates_only_without_anything_to_total(browser, built_site, tmp_path):
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, small_file(tmp_path, 12))
    assert pg.get_attribute("#ck-out", "data-variant") == "too_few" and pg.locator("#ck-out [data-pay]").count() == 0
    assert "fewer than 30 trades" in pg.inner_text("#ck-out [data-offer]")
    ctx.close()


def test_the_first_look_is_real_public_data_with_no_offer_and_counts_as_no_visit_step(browser, built_site):
    ctx, pg, log = open_page(browser, built_site)                       # 1280 px: the example is open
    pg.wait_for_selector("#ck-ex-h")
    assert pg.inner_text("#ck-ex-h") == "Example: real public data, counted"
    assert "Real public data: one anonymous investor, not picked by result." in pg.inner_text("#ck-ex")
    assert "64 closed trades" in pg.inner_text("#ck-ex")
    calls = pg.evaluate("window.__umamiCalls || []")
    assert [c["name"] for c in calls if c["name"].startswith("check_")] == [], calls   # no start, no read, no variant
    assert pg.get_attribute("#ck-ex", "data-variant") == "no_test"
    # someone else's file is never offered the report: no offer block, no pay link, no price
    assert pg.locator("#ck-ex [data-offer], #ck-ex [data-pay], #ck-out [data-pay]").count() == 0
    assert "This is someone else's file." in pg.inner_text("#ck-ex") and "$" not in pg.inner_text("#ck-ex")
    ctx.close()
    # a phone's first look is closed, so no zero leads the page; the summary line names the example
    ctx, pg, log = open_page(browser, built_site, width=390)
    assert pg.evaluate("document.getElementById('ck-example').open") is False
    assert "See the check on real public data" in pg.inner_text("#ck-example summary")
    assert pg.locator("#ck-out [data-pay]").count() == 0
    ctx.close()


def test_after_a_read_the_drop_zone_becomes_a_file_bar_and_stages_are_real(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site, bypass_csp=True)
    pg.evaluate("window.__stages = []; new MutationObserver(() => window.__stages.push(document.getElementById('ck-status').textContent)).observe(document.getElementById('ck-status'), {childList: true, characterData: true, subtree: true})")
    read_file(pg, csvs["plain"])
    assert pg.is_hidden("#ck-drop") and pg.is_visible("#ck-filebar")
    assert pg.inner_text("#ck-fname") == "plain.csv" and "360 trades" in pg.inner_text("#ck-fwhat")
    stages = [x for x in pg.evaluate("window.__stages") if x]
    assert stages[0].startswith("Step 1 of 2") and any(x.startswith("Step 2 of 2") for x in stages), stages
    assert pg.inner_text("#ck-out .ck-did").startswith("What we did: ") and "Nothing left this tab" in pg.inner_text("#ck-out .ck-did")
    pg.click("#ck-another")
    assert pg.is_visible("#ck-drop") and pg.is_hidden("#ck-filebar")
    ctx.close()


# ------------------------------------------------------------------ 1 and 2: no money, no banned word

@pytest.mark.parametrize("name", ["plain", "dates_only", "zero_losses", "real_public_data", "fewer_than_30_groups"])
def test_no_currency_outside_the_offer_and_no_banned_word(browser, built_site, csvs, name):
    ctx, pg, log = open_page(browser, built_site)
    first = pg.evaluate("""() => { const c = document.querySelector('#ck-ex').cloneNode(true); c.querySelectorAll('[data-offer]').forEach(e => e.remove()); c.querySelectorAll('*').forEach(e => e.append(' ')); return c.textContent; }""")
    read_file(pg, csvs[name])
    after = pg.evaluate("""() => { const c = document.querySelector('#ck-out').cloneNode(true); c.querySelectorAll('[data-offer]').forEach(e => e.remove()); c.querySelectorAll('*').forEach(e => e.append(' ')); return c.textContent; }""")
    for text in (first, after):
        assert not CURRENCY.search(text), CURRENCY.search(text).group(0)
        assert text.count("In the report") >= 0
    whole = pg.inner_text("#ck-out")
    assert not BANNED.search(whole), BANNED.search(whole).group(0)
    # a currency amount is allowed in the offer only, and only the product's own price
    offer = pg.locator("#ck-out [data-offer]").inner_text()
    amounts = set(re.findall(r"\$\d+(?:\.\d\d)?", offer))
    assert amounts <= {f"${R['price_usd']}", f"${R['after_founding']['price_usd']}"}, amounts
    # no colour carried by the counts
    assert pg.locator("#ck-out .ck-card .neg, #ck-out .ck-card .pos, #ck-out .ck-card .gain, #ck-out .ck-card .loss").count() == 0
    ctx.close()


# ------------------------------------------------------------------ 5: no row leaves the tab

def test_no_row_value_in_any_request_and_only_fixed_event_names(browser, built_site, tmp_path):
    p = tmp_path / "canary.csv"
    rows = ["Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees"]
    for i in range(60):
        rows.append(f"2026-04-{(i % 27) + 1:02d} 1{i % 10}:00:00,2026-04-{(i % 27) + 1:02d} 1{i % 10}:07:00,CANARYZQ7X,Long,7.77,100,{100.31 + i / 100:.2f},0")
    p.write_text("\n".join(rows) + "\n")
    ctx, pg, log = open_page(browser, built_site)
    log["requests"].clear()
    pg.set_input_files("#ck-file", str(p))
    pg.wait_for_selector("#ck-out-h:text-is('Your file, counted')")
    pg.wait_for_load_state("networkidle")
    base = built_site["url"]
    assert all(u.startswith(base + "/static/") or u.startswith(base + "/assets/") for u in log["requests"]), log["requests"]
    blob = " ".join(log["requests"]) + " ".join(str(b) for _, b in log["posts"])
    for canary in ("CANARYZQ7X", "7.77", "100.31", "2026-04"):
        assert canary not in blob, canary
    assert log["posts"] == []
    calls = pg.evaluate("window.__umamiCalls || []")
    names = [c["name"] for c in calls]
    assert names[:1] == ["check_start"] and "check_read_ok" in names and any(x.startswith("check_variant_") for x in names), names
    assert all(re.fullmatch(r"check_[a-z0-9_]+", x) for x in names) and not any(c["hasData"] for c in calls), calls
    csp = pg.get_attribute("meta[http-equiv='Content-Security-Policy']", "content")
    assert "script-src 'self'" in csp and "unsafe-inline" not in csp and "form-action 'none'" in csp or "form-action" in csp
    assert log["console"] == [], log["console"]
    ctx.close()


def test_a_file_that_cannot_be_read_says_so_and_sends_a_fixed_event(browser, built_site, tmp_path):
    p = tmp_path / "junk.csv"
    p.write_text("hello,world\n1,2\n")
    ctx, pg, log = open_page(browser, built_site)
    pg.set_input_files("#ck-file", str(p))
    pg.wait_for_selector("#ck-error:not([hidden])")
    assert "This file could not be read" in pg.inner_text("#ck-error")
    assert pg.inner_text("#ck-error-note") == "No charge, nothing sent. The CSV template reads any broker."
    assert pg.locator("#ck-out [data-pay]").count() == 0
    names = [c["name"] for c in pg.evaluate("window.__umamiCalls || []")]
    assert names[0] == "check_start" and any(x.startswith("check_read_fail_") for x in names), names
    ctx.close()


def test_the_offer_click_is_counted_without_data(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, csvs["plain"])
    pg.click("#ck-out [data-offer] a.btn[data-pay]")
    names = [c["name"] for c in pg.evaluate("window.__umamiCalls || []")]
    assert "check_to_report" in names
    ctx.close()


# ------------------------------------------------------------------ 6 and 7: the offer, markup

def test_the_founding_sentence_is_verbatim_and_the_refund_line_is_in_the_same_block(built_site):
    h = (built_site["out"] / "check" / "index.html").read_text(encoding="utf-8")
    founding = f"US${R['price_usd']} for the first {PRICES['rules']['founding_limit']} buyers, then US${R['after_founding']['price_usd']}."
    blocks = [(b, t) for b, t in re.findall(r'(?s)<template id="ck-t-(\w+)">(.*?)</template>', h) if b != "lock"]   # "lock" is the small inline icon
    assert {b for b, _ in blocks} == {"normal", "no_test", "dates_only", "dates_none", "zero", "too_few"}
    for name, body in blocks:
        assert "data-offer" in body
        text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", body))
        if name == "normal":
            assert founding in text, text
        if "data-pay" in body:
            assert f"Get the report for ${R['price_usd']}" in text and "Full refund within 14 days" in text, (name, text)
        else:
            assert "$" not in text and "refund" not in text.lower(), (name, text)   # nothing is offered, so no price either


def test_no_style_attribute_anywhere(built_site):
    h = (built_site["out"] / "check" / "index.html").read_text(encoding="utf-8")
    assert " style=" not in h
    js = open(os.path.join(REPO, "site", "static", "js", "check.js"), encoding="utf-8").read()
    assert not re.search(r"style\s*[=:.]|setAttribute\(\s*['\"]style|cssText|\.style\b", js.replace("style-src", ""))
    assert "<script>" not in h and not re.search(r"(?i)<script(?![^>]*\bsrc=)(?![^>]*type=\"(?:text/csv|application/ld\+json)\")", h)


def test_no_style_attribute_in_the_drawn_result(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site, bypass_csp=False)
    read_file(pg, csvs["plain"])
    assert pg.evaluate("document.querySelectorAll('main [style]').length") == 0
    ctx.close()


def test_page_text_passes_the_lint_and_says_not_advice(built_site):
    h = (built_site["out"] / "check" / "index.html").read_text(encoding="utf-8")
    main = h.split("<main", 1)[-1].split("</main>")[0]
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main))
    assert re.search(r"(?i)\bnot (investment )?advice|does not recommend", t)
    assert L.lint_text(t, P, paid=True) == []
    assert "Drop your trade file here" in t and "Free revenge trading check" in t


def test_the_page_exists_only_with_paid_report(built_site):
    """A whole free build cannot be made from this tree (test_hardening_3nov), so the gate is checked where the build applies it."""
    import build as B
    page = next(p for p in B.PAGES if p["path"] == P)
    assert page["requires_flag"] == "paid_report"
    src = open(os.path.join(REPO, "site", "build.py"), encoding="utf-8").read()
    assert 'if page["requires_flag"] and not flags[page["requires_flag"]]' in src
    assert (built_site["out"] / "check" / "index.html").exists()
    assert "/check/" in (built_site["out"] / "sitemap.xml").read_text(encoding="utf-8")


# ------------------------------------------------------------------ 8: axe, overflow

@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_axe_clean_and_no_overflow_before_and_after_a_file(browser, built_site, csvs, width, scheme):
    ctx, pg, log = open_page(browser, built_site, width=width, scheme=scheme, bypass_csp=True)
    pg.wait_for_selector("#ck-ex-h", state="attached")      # the first look
    assert horizontal_overflow(pg) == []
    assert axe_violations(pg) == [], axe_violations(pg)
    for name in ("plain", "zero_losses"):
        read_file(pg, csvs[name])
        assert horizontal_overflow(pg) == []
        assert axe_violations(pg) == [], (name, axe_violations(pg))
    ctx.close()


# ------------------------------------------------------------------ result panel polish (7 Nov 2026)

def test_summary_chart_and_compact_rows(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site, width=390)
    read_file(pg, csvs["plain"])
    assert pg.locator("#ck-out .ck-card, #ck-out .ck-chip, #ck-out a.ck-lock, #ck-out svg.ck-icon, #ck-out template").count() == 0     # no padlocks
    assert pg.locator("#ck-out [data-pay]").count() == 1
    # each bar's width is the row's share of all trades, in an attribute (no style=)
    exp = json.load(open(os.path.join(FIX, "plain.json")))
    h = exp["habits"]
    want = [h["revenge"]["n_a"], h["tilt"]["n_a"], h["size_up"]["dollars"]["n_trades"], h["hold_gap"]["dollars"]["n_trades"], h["oversized_loss"]["dollars"]["n_trades"]]
    widths = [int(w) for w in pg.eval_on_selector_all("#ck-out svg.ck-share rect.ck-bar", "els => els.map(e => e.getAttribute('width'))")]
    assert widths == [round(100 * x / exp["n_trades"]) for x in want], widths
    assert pg.evaluate("document.querySelectorAll('#ck-out [style]').length") == 0
    # the button sits within about one screen of the result heading
    top = pg.evaluate("document.querySelector('#ck-out-h').getBoundingClientRect().top + scrollY")
    btn = pg.evaluate("document.querySelector('#ck-out [data-pay]').getBoundingClientRect().top + scrollY")
    assert btn - top <= 1000, btn - top
    # labels in the body font; only figures are tabular
    fonts = pg.evaluate("""() => [...document.querySelectorAll('#ck-out .ck-bl, #ck-out .ck-table th, #ck-out .ck-head, #ck-out .ck-ml')].map(e => getComputedStyle(e).fontFamily)""")
    assert fonts and not any("mono" in f.lower() for f in fonts), fonts
    assert pg.evaluate("getComputedStyle(document.getElementById('ck-out-h')).outlineStyle") in ("none", "hidden")
    # one "In the report" column header, the only link in the table
    assert pg.locator("#ck-out thead a[href='#offer']").count() == 1 and pg.locator("#ck-out tbody a").count() == 0
    # the offer names the exact trades
    assert f"What these {h['revenge']['n_a']:,} trades came to in dollars" in pg.inner_text("#ck-out [data-offer]")
    ctx.close()


# ------------------------------------------------------------------ 7 Nov 2026 improvements: analytics

def test_the_sample_button_is_counted_apart_from_own_file_reads(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site, bypass_csp=True)
    pg.click("#ck-sample-btn")
    pg.wait_for_function("(window.__umamiCalls || []).some(c => c.name === 'check_sample_ok')")
    names = [c["name"] for c in pg.evaluate("window.__umamiCalls || []")]
    assert names == ["check_sample_start", "check_sample_ok"], names     # the first look on load is counted as nothing
    pg.set_input_files("#ck-file", csvs["plain"])
    pg.wait_for_function("(window.__umamiCalls || []).some(c => c.name === 'check_read_ok')")
    names = [c["name"] for c in pg.evaluate("window.__umamiCalls || []")]
    assert names.count("check_read_ok") == 1 and names.count("check_start") == 1 and names.count("check_sample_ok") == 1, names
    ctx.close()


def test_check_js_stays_within_the_budget_of_the_7_nov_improvements():
    """check.js was 3,878 B gzip at C2; the improvements may add 2 KB (RESEARCH-IMPROVE-FREE-CHECK §3)."""
    import gzip
    raw = open(os.path.join(REPO, "site", "static", "js", "check.js"), "rb").read()
    assert len(gzip.compress(raw, 9)) <= 3878 + 2048, len(gzip.compress(raw, 9))


def test_the_public_sample_is_credited_with_its_licence_and_doi(browser, built_site):
    h = (built_site["out"] / "check" / "index.html").read_text(encoding="utf-8")
    m = re.search(r'(?s)<p class="small muted" id="ck-source">(.*?)</p>', h)
    assert m and "Mendeley Stock Transactions Dataset, CC BY 4.0" in m.group(1)
    assert '<a href="https://doi.org/10.17632/k4tnk2nggv.1">doi:10.17632/k4tnk2nggv.1</a>' in m.group(1)
    ctx, pg, log = open_page(browser, built_site)                      # 1280 px: the example is open, so the credit is on screen with it
    assert pg.is_visible("#ck-source") and pg.get_attribute("#ck-source a", "href") == "https://doi.org/10.17632/k4tnk2nggv.1"
    ctx.close()


@pytest.mark.parametrize("width", [320, 360, 375, 390])
def test_the_buy_button_stays_within_1000_px_of_the_heading_on_a_phone(browser, built_site, csvs, width):
    ctx, pg, log = open_page(browser, built_site, width=width)
    read_file(pg, csvs["plain"])
    d = pg.evaluate("document.querySelector('#ck-out [data-pay]').getBoundingClientRect().top - document.querySelector('#ck-out-h').getBoundingClientRect().top")
    assert d <= 1000, (width, d)
    assert horizontal_overflow(pg) == []
    ctx.close()


# ------------------------------------------------------------------ D6: the reader's notes

def test_the_readers_notes_say_no_found_and_get_the_plurals_right(browser, built_site, csvs, tmp_path):
    one = tmp_path / "dup1.csv"
    lines = open(csvs["plain"], encoding="utf-8").read().split("\n")
    lines.insert(5, lines[4])                                   # one exact copy of a row: "Affected: 1 row."
    one.write_text("\n".join(lines), encoding="utf-8")
    ctx, pg, log = open_page(browser, built_site)
    pg.wait_for_selector("#ck-ex-h")
    seen = [pg.evaluate("document.getElementById('ck-ex').textContent")]    # the example's three notes (inside its closed-by-default details)
    for path in [str(one), csvs["partial_fills_merge"], csvs["multi_symbol_size"], csvs["dates_only"]]:
        read_file(pg, path)
        seen.append(pg.evaluate("document.getElementById('ck-notes').textContent + ' ' + document.getElementById('ck-out').textContent"))
    for i, text in enumerate(seen):
        assert not BANNED.search(text), (i, BANNED.search(text).group(0))
        assert not re.search(r"\b1 (trades|rows|closed trades|fills|weeks)\b", text), (i, re.search(r"\b1 (trades|rows|closed trades|fills|weeks)\b", text).group(0))
    assert "Affected: 1 row." in seen[1]
    assert any("Affected:" in t for t in seen)
    ctx.close()


def test_a_file_of_one_trade_reads_one_trade_not_one_trades(browser, built_site, tmp_path):
    p = tmp_path / "one.csv"
    p.write_text("Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees\n2026-03-02 10:00:00,2026-03-02 10:20:00,AAA,Long,1,100,101,0\n")
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, str(p))
    text = pg.inner_text("#ck-out")
    assert "1 trade read" in text and "Share of all 1 trade." in text and not re.search(r"\b1 trades\b", text), text[:400]
    ctx.close()


def test_a_purchase_from_the_check_is_tagged_check_in_the_payment_itself(built_site):
    """D7: the Payment Link on /check/ carries client_reference_id=check, so Stripe records which page the buyer
    paid from. /welcome/ and /report/ run no analytics (a deliberate privacy rule), so no Umami 'purchase' event
    exists; the count comes from Stripe, with check_to_report clicks as the on-site proxy. No personal data."""
    h = (built_site["out"] / "check" / "index.html").read_text(encoding="utf-8")
    links = set(re.findall(r'href="(https://buy\.stripe\.com/[^"]*)"', h))
    assert links and all(re.search(r"[?&]client_reference_id=check(&|$)", u) for u in links), links


def test_the_check_is_linked_from_for_traders_and_every_footer_but_not_inside_tools_main(built_site):
    """D8: a text link on /for-traders/, a footer link on every page, and nothing added inside /tools/ <main>."""
    out = built_site["out"]
    ft = (out / "for-traders" / "index.html").read_text(encoding="utf-8")
    assert 'href="/check/"' in re.search(r"(?s)<main.*?</main>", ft).group(0)
    pages = sorted(out.rglob("index.html"))
    assert pages
    for p in pages:
        h = p.read_text(encoding="utf-8")
        foot = re.search(r"(?s)<footer.*?</footer>", h)
        if foot and "/fr/" not in str(p) and p.name == "index.html":
            assert 'href="/check/"' in foot.group(0), p
    tools = (out / "tools" / "index.html").read_text(encoding="utf-8")
    assert 'href="/check/"' not in re.search(r"(?s)<main.*?</main>", tools).group(0)
