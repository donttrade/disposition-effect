"""The Challenge Readiness Check page (ARCHITECT-CHALLENGE-READINESS-2026-10-29 R4, R4b, R4c, R5, R7; §8.4-§8.8).

On the live-config build (built_site): presets with "not stated" notes, the three plain visuals, "Try a rule",
Expert details and the results-only export, the share card, counting through the live analytics only, the one
18+ line, word budgets and wording, no finding next to the offer, every input format end to end, the paste route,
CLS, axe and overflow at 390 and 1280 in light and dark.
"""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(HERE, "reference"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import lint as L  # noqa: E402
import check_rules as C  # noqa: E402

PATH = "/tools/prop-challenge-simulator/"
FIX = os.path.join(HERE, "fixtures")
SHOTS = os.environ.get("DT_READINESS_SHOTS")
BRIEF_BANNED = re.compile(r"\b(recommend\w*|should|fix|fixes|fixed it|coach\w*|must|need to|signal\w*|improv\w*|mentor\w*|"
                          r"certified|verified|audited|seal\w*)\b", re.IGNORECASE)
JARGON = ["bootstrap", "resample", "seed", "Monte Carlo", "percentile", "confidence interval", "EOD", "drawdown model"]
FUTURE = re.compile(r"\b(you will (pass|fail)|your chances|odds of passing|ready to buy|best rule|best firm|safest|you should)\b", re.I)
BEACON = ("https://static.cloudflareinsights.com/", "https://cloudflareinsights.com/cdn-cgi/rum")
# 127.0.0.1 only: the beacon's report is refused by CORS. And a timing warning about the site-wide font preload in
# base.html ("preloaded using link preload but not used within a few seconds"): it depends on how fast the run is.
LOCAL_ONLY = ("cloudflareinsights.com/cdn-cgi/rum", "Failed to load resource: net::ERR_FAILED",
              "was preloaded using link preload but not used within a few seconds")
MT_HTML = "Refused to apply inline style"


def open_page(browser, built_site, width=1280, scheme="light", **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, timezone_id="UTC",
                              accept_downloads=True, **kw)
    ctx.add_init_script("""window.__cls = 0; try { new PerformanceObserver((l) => { for (const e of l.getEntries())
        if (!e.hadRecentInput) window.__cls += e.value; }).observe({ type: 'layout-shift', buffered: true }); } catch (e) {}""")
    pg = ctx.new_page()
    log = {"requests": [], "console": []}
    pg.on("request", lambda r: log["requests"].append(r.url))
    pg.on("console", lambda m: log["console"].append(m.text) if m.type in ("error", "warning") else None)
    pg.on("pageerror", lambda e: log["console"].append("pageerror: " + str(e)))
    pg.goto(built_site["url"] + PATH)
    pg.wait_for_load_state("networkidle")
    return ctx, pg, log


def errors(log):
    return [m for m in log["console"] if not any(x in m for x in LOCAL_ONLY)]


def fill(pg, values):
    for k, v in values.items():
        pg.fill(k, v)


def sample(pg, rules=None):
    fill(pg, rules or {"#ps-account": "10000", "#ps-target": "300", "#ps-daily": "40", "#ps-maxloss": "300", "#ps-days": "60"})
    pg.click("#ps-sample-btn")
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')")


def run(pg):
    pg.click("#ps-run")
    pg.wait_for_selector("#ps-out:not([hidden])", timeout=60000)


def whatif(pg, rule="stop_after_losses", n="1"):
    pg.select_option("#ps-wi-rule1", rule)
    if n is not None and rule != "after_loss_factor":
        pg.fill("#ps-wi-n1", n)
    pg.click("#ps-wi-run")
    pg.wait_for_selector("#ps-wi-out:not([hidden])", timeout=60000)


def words(s):
    return len(s.split())


# ------------------------------------------------------------------ the default view
def test_three_visuals_then_try_a_rule_then_expert_then_offer(browser, built_site):
    ctx, pg, log = open_page(browser, built_site)
    sample(pg)
    run(pg)
    assert pg.inner_text("#ps-out-h") == "Passed in 6% of 10,000 replays"
    assert [e.get_attribute("id") for e in pg.query_selector_all("#ps-out .rc-visuals > .rc-card")] == ["ps-v-outcome", "ps-v-rule", "ps-v-habits"]
    assert "In their real order, your days" in pg.inner_text("#ps-v-outcome")
    assert pg.inner_text("#ps-v-rule").startswith("Rule that broke most\n\nDaily loss · 100% of busts")
    hab = pg.inner_text("#ps-v-habits")
    assert "15 past days reached the daily loss limit" in hab and "On 10 of 15 breach days" in hab
    assert pg.get_attribute('[data-habit="large_loss"]', "data-status") == "hit"
    assert pg.is_visible("#ps-whatif") and pg.get_attribute("#ps-expert", "open") is None
    # document order: result, Try a rule, Expert details, card, limits, then the one offer
    order = pg.evaluate("""() => ['ps-out', 'ps-whatif', 'ps-expert', 'ps-share', 'ps-limits-h']
        .map((id) => document.getElementById(id)).concat([document.querySelector('.next-step')])
        .map((e, i, a) => i === 0 || (a[i - 1].compareDocumentPosition(e) & Node.DOCUMENT_POSITION_FOLLOWING) ? 1 : 0)""")
    assert order == [1] * 6
    assert errors(log) == []
    ctx.close()


def test_manual_mode_hides_habits_and_real_order(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site)
    pg.check("#ps-mode-manual")
    fill(pg, {"#ps-wr": "50", "#ps-avgwin": "100", "#ps-avgloss": "80", "#ps-tpd": "3", "#ps-target": "800", "#ps-maxloss": "600"})
    run(pg)
    assert pg.query_selector("#ps-v-habits") is None and pg.query_selector("#ps-real-order") is None
    assert pg.is_disabled('#ps-wi-rule1 option[value="cooldown_s"]')
    ctx.close()


def test_plain_words_in_the_default_view(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site)
    sample(pg)
    run(pg)
    whatif(pg)
    pg.evaluate("document.querySelectorAll('.hint').forEach((h) => { h.style.display = 'none'; })")
    text = pg.inner_text("main")   # closed <details> (Expert details, More rules, FAQ) are not rendered
    for w in JARGON:
        assert not re.search(rf"\b{re.escape(w)}\b", text, re.I), w
    ctx.close()


# ------------------------------------------------------------------ presets
def test_presets_alphabetical_no_default_and_notes(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site)
    opts = pg.eval_on_selector_all("#ps-preset option", "os => os.map((o) => [o.value, o.parentElement.tagName === 'OPTGROUP' ? o.parentElement.label : ''])")
    assert opts[0] == ["", ""] and pg.input_value("#ps-preset") == ""
    firms = [f for _, f in opts[1:]]
    assert firms == sorted(firms, key=str.lower) and len(set(firms)) == 8
    lib = C.load()
    shown = {p["id"] for p in C.shown(lib)}
    assert {v for v, _ in opts[1:]} == shown
    pg.select_option("#ps-preset", "ftmo-1-step")
    assert (pg.input_value("#ps-account"), pg.input_value("#ps-target"), pg.input_value("#ps-daily"), pg.input_value("#ps-maxloss")) == ("100000", "10000", "3000", "10000")
    assert pg.is_checked("#ps-trail-trailing") and pg.input_value("#ps-targetcheck") == "intraday" and pg.input_value("#ps-daytz") == "Europe/Prague"
    src = pg.inner_text("#ps-preset-source")
    assert src.startswith("Read on 29 Oct 2026 from FTMO’s rules page.")
    a = pg.query_selector("#ps-preset-source a")
    assert a.get_attribute("rel") == "nofollow noopener" and a.get_attribute("href") == "https://ftmo.com/en/trading-objectives/"
    assert pg.is_visible("#ps-days-ns") and "Not stated by the firm" in pg.inner_text("#ps-days-ns")
    assert pg.is_visible("#ps-mindays-ns") and pg.is_hidden("#ps-daily-ns")
    assert "does not state: minimum days; time limit" in pg.inner_text("#ps-ns")
    assert "this check does not model" in pg.inner_text("#ps-limits-preset")
    # a percent preset scales with the account size; editing a box says "Edited from"
    pg.fill("#ps-account", "50000")
    pg.dispatch_event("#ps-account", "change")
    assert pg.input_value("#ps-target") == "5000"
    pg.select_option("#ps-preset", "topstep-50k-trading-combine")
    assert pg.input_value("#ps-target") == "3000" and pg.input_value("#ps-stopat") == "0" and pg.input_value("#ps-daytz") == "America/Chicago"
    pg.click("#ps-sample-btn")
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')")
    pg.fill("#ps-maxloss", "2500")
    run(pg)
    assert pg.text_content("#ps-rules-used").startswith("Rules used: Edited from Topstep, Trading Combine 50K")
    for link in pg.eval_on_selector_all("a[href^='http']", "as => as.map((a) => a.href)"):
        assert not re.search(r"ref=|aff|utm_|coupon", link, re.I), link
    ctx.close()


def test_results_go_stale_after_a_change_until_the_next_run(browser, built_site):
    """Tester page report F1: a rule, file or preset change dims the results and stops Try this rule."""
    ctx, pg, log = open_page(browser, built_site)
    sample(pg)
    run(pg)
    assert pg.is_hidden("#ps-stale") and pg.is_enabled("#ps-wi-run")

    def new_file():
        pg.click("#ps-sample-btn")
        pg.wait_for_selector("#ps-file-status:text-matches('^Read ')")
    for change in (lambda: pg.fill("#ps-target", "310"), lambda: pg.select_option("#ps-preset", "ftmo-1-step"), new_file):
        change()
        assert pg.is_visible("#ps-stale") and pg.inner_text("#ps-stale").startswith("Rules or file changed — run again.")
        for part in ("#ps-out", "#ps-whatif", "#ps-expert", "#ps-share"):
            assert "rc-stale" in pg.get_attribute(part, "class").split(), part
        for b in ("#ps-wi-run", "#ps-card-dl", "#ps-csv", "#ps-json"):
            assert pg.is_disabled(b), b
        pg.click("#ps-stale-run")
        pg.wait_for_selector("#ps-stale", state="hidden", timeout=60000)
        assert pg.is_enabled("#ps-wi-run") and "rc-stale" not in pg.get_attribute("#ps-out", "class").split()
    assert errors(log) == []
    ctx.close()


def test_every_preset_change_resets_every_box(browser, built_site):
    """F3: nothing typed for one preset, the account size included, carries over to the next."""
    ctx, pg, _ = open_page(browser, built_site)
    pg.select_option("#ps-preset", "ftmo-1-step")
    pg.fill("#ps-account", "5000")
    pg.dispatch_event("#ps-account", "change")   # a percent preset scales to a typed size
    assert pg.input_value("#ps-target") == "500"
    pg.fill("#ps-target", "123")
    pg.click("#ps-more summary")
    pg.fill("#ps-consistency", "40")
    pg.fill("#ps-profmin", "77")
    pg.select_option("#ps-preset", "topstep-50k-trading-combine")
    assert (pg.input_value("#ps-account"), pg.input_value("#ps-target")) == ("50000", "3000")
    pg.select_option("#ps-preset", "ftmo-1-step")
    assert (pg.input_value("#ps-account"), pg.input_value("#ps-target"), pg.input_value("#ps-consistency"),
            pg.input_value("#ps-profmin")) == ("100000", "10000", "50", "")
    pg.select_option("#ps-preset", "")
    for box in ("#ps-account", "#ps-target", "#ps-daily", "#ps-maxloss", "#ps-days", "#ps-mindays", "#ps-stopat"):
        assert pg.input_value(box) == "", box
    assert pg.is_checked("#ps-trail-static") and pg.input_value("#ps-targetcheck") == "eod" and pg.input_value("#ps-daytz") == "file"
    ctx.close()


def test_a_new_file_ends_a_running_check(browser, built_site):
    """F6: a check still running when a new file is picked stops; no error, nothing stale is drawn."""
    ctx, pg, log = open_page(browser, built_site)
    sample(pg)
    # the second click lands while the replays run (both in one task, so the run cannot finish first)
    pg.evaluate("() => { document.getElementById('ps-run').click(); document.getElementById('ps-sample-btn').click(); }")
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')")
    pg.wait_for_timeout(2500)
    assert pg.is_hidden("#ps-out") and pg.is_enabled("#ps-run") and pg.is_hidden("#ps-status")
    run(pg)
    assert pg.inner_text("#ps-out-h") == "Passed in 6% of 10,000 replays"
    assert errors(log) == []
    ctx.close()


def test_trademark_line_names_every_firm_shown(browser, built_site):
    html = (built_site["out"] / "tools" / "prop-challenge-simulator" / "index.html").read_text(encoding="utf-8")
    line = re.search(r"([^<>]*) are trademarks of their owners\. donttrade is not affiliated", html).group(1)
    for p in C.shown(C.load()):
        assert p["firm"].replace("%", "%") in line, p["firm"]
    assert "is paid by none of them" in html
    assert "None are built in or named" not in html and "No firm’s rules are built in" not in html


# ------------------------------------------------------------------ age, offer, wording
def test_one_adult_line_no_gate(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site)
    text = pg.inner_text("main")
    assert text.count("Prop firms sell challenges only to adults (18+).") == 1
    assert pg.eval_on_selector_all("input[type=checkbox]", "xs => xs.map((x) => x.id)") == ["ps-wi-card"]   # no age tick
    sample(pg)
    run(pg)
    assert pg.evaluate("Object.keys(localStorage).length + Object.keys(sessionStorage).length") == 0 and ctx.cookies() == []
    ctx.close()


def test_offer_is_identical_and_holds_no_result(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site)
    before = pg.inner_html(".next-step")
    sample(pg)
    run(pg)
    whatif(pg)
    after = pg.inner_html(".next-step")
    assert before == after
    numbers = set(re.findall(r"\d+%", pg.inner_text("#ps-out") + pg.inner_text("#ps-wi-out")))
    aside = pg.inner_text(".next-step")
    assert not any(n in aside for n in numbers)
    for sel in ("#ps-out", "#ps-whatif", "#ps-share", "#ps-expert"):
        assert pg.eval_on_selector_all(f"{sel} a[href*='/pricing/'], {sel} a[href*='/sample-report/'], {sel} [data-pay]", "x => x.length") == 0, sel
    assert pg.query_selector("#ps-out .next-step") is None
    ctx.close()


def test_word_budgets_and_wording(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site)
    sample(pg)
    run(pg)
    whatif(pg, "after_loss_factor", None)
    pg.evaluate("document.getElementById('ps-expert').open = true; document.getElementById('ps-more').open = true")
    pg.evaluate("document.querySelectorAll('details').forEach((d) => d.open = true)")
    heads = pg.eval_on_selector_all("main h1, main h2, main h3", "hs => hs.map((h) => h.innerText.trim())")
    for h in heads:
        assert words(h) <= 8, h
    # this page's buttons (the shared offer partial's buy link is the site's own, the same on every tool page)
    for b in pg.eval_on_selector_all("main button, main .btn", "bs => bs.filter((b) => !b.closest('.next-step')).map((b) => b.innerText.trim()).filter(Boolean)"):
        assert words(b) <= 4, b
    text = pg.inner_text("main")
    assert L.lint_text(text, PATH) == []
    assert not BRIEF_BANNED.search(text), BRIEF_BANNED.search(text)
    assert not FUTURE.search(text), FUTURE.search(text)
    assert "This leaves out or shrinks trades from your past days." in pg.inner_text("#ps-wi-out")
    assert "result scales with size" in pg.inner_text("#ps-wi-out")
    assert "Biggest changes" not in text and "Rules that changed the result most" not in text   # whatif_ranked = false
    core = (built_site["out"] / "static" / "js" / "tools" / "prop-sim-core.js").read_text(encoding="utf-8")
    assert "export const WHATIF_RANKED = false;" in core
    ctx.close()


# ------------------------------------------------------------------ Try a rule, Expert details, export
def test_whatif_is_paired_and_described(browser, built_site):
    ctx, pg, log = open_page(browser, built_site)
    sample(pg)
    run(pg)
    whatif(pg, "stop_at_day_loss", "50")
    line = pg.inner_text("#ps-wi-line")
    assert line == "On your past days, with this rule: passed 6% → 9%, broke a rule 94% → 91%, out of time 0% → 0%. 8% of your trades were left out."
    pg.select_option("#ps-wi-rule2", "stop_at_day_loss")
    pg.click("#ps-wi-run")
    assert "Pick two different rules." in pg.inner_text("#ps-wi-errors")
    assert errors(log) == []
    ctx.close()


def test_expert_details_and_export_hold_results_only(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site)
    sample(pg)
    run(pg)
    whatif(pg)
    assert pg.get_attribute("#ps-expert", "open") is None   # collapsed by default
    pg.click("#ps-expert summary")
    body = pg.inner_text("#ps-expert")
    for k in ("Simulation settings", "Uncertainty", "Per-rule counts", "Habits, raw", "Your days in their real order", "What-if, raw"):
        assert k in body, k
    assert "± 0.5%" in pg.inner_text('tr[data-outcome="pass"]')   # 1.96·√(.06·.94/10000) = 0.47 points
    pg.click("#ps-range-btn")
    pg.wait_for_selector("#ps-range-out table", timeout=120000)
    assert "90% range over 200 resamples" in pg.inner_text("#ps-range-out")
    out = {}
    for kind in ("json", "csv"):
        with pg.expect_download() as d:
            pg.click(f"#ps-{kind}")
        out[kind] = open(d.value.path(), encoding="utf-8").read()
        assert d.value.suggested_filename == f"readiness-check-results.{kind}"
    data = json.loads(out["json"])
    assert data["schema"] == "donttrade.readiness-check.results.v1" and data["out"]["runs"] == 10000
    assert data["whatif"]["rule"] == {"stop_after_losses": 1} and data["range"]["B"] == 200
    for kind, text in out.items():
        text = re.sub(r'"(method|rules_lib)": "[^"]*"|(method|rules_lib),[^\n]*', "", text)   # version names, not trade dates
        for bad in ("close_ts", "open_ts", "symbol", "day_pnl", "bust_at", "example-trades", "DEMO-"):
            assert bad not in text, bad
        assert not re.search(r'(^|[",.])drawn_losing\b', text)   # the per-day draw counts (on_drawn_losing is a habit count)
        assert not re.search(r"\b20\d\d-\d\d-\d\d\b", text)   # no trade dates
    assert out["csv"].startswith("key,value\nschema,donttrade.readiness-check.results.v1\n")
    ctx.close()


# ------------------------------------------------------------------ the card
def test_card_strings_and_image(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site)
    sample(pg)
    run(pg)
    whatif(pg)
    pg.check("#ps-wi-card")
    pg.wait_for_timeout(300)
    alt = pg.get_attribute("#ps-card-canvas", "aria-label")
    assert alt.startswith("Passed in 6% of 10,000 replays.") and "Example data." in alt and "not a real" not in alt.lower()
    assert "With stop after 1 loss: passed 6% →" in alt and "3% target · 0.4% daily · 3% max (fixed floor)" in alt
    firms = {p["firm"] for p in C.load()["presets"]}
    for bad in ["$", "USD", "buy", "purchase", "challenge fee", "funded", "price", *firms]:
        assert bad.lower() not in alt.lower(), bad
    assert not re.search(r"\b20\d\d\b|\d{1,2}:\d\d", alt)
    strings = pg.evaluate("""async () => { const m = await import('/static/js/card/readiness-card.js');
        const out = [...Object.values(m.CARD_STRINGS)];
        const rules = [{stop_after_losses: 3}, {stop_at_day_loss: 0.75}, {stop_at_day_loss_amount: 50}, {max_trades: 50},
          {cooldown_s: 14400}, {after_loss_factor: 0.75}, {stop_after_losses: 10, max_trades: 50}];
        const habits = ['Re-entering soon after a loss', 'Trading after a losing streak', 'Size after a loss', 'Losses much larger than your usual loss'];
        for (const r of rules) for (const h of habits) {
          const l = m.cardLines({pass: 0.333, bust: 0.333, timeout: 0.334, runs: 10000, rule: 'daily', habit: h,
            rulesPct: {t: 10, d: 5, m: 10, kind: 'moving'}, whatif: {personal: r, a: 0.18, b: 0.41}, example: true});
          out.push(l.headline, ...l.shares, ...l.facts, ...l.footer, l.example);
        }
        return out; }""")
    for s in strings:
        assert words(s) <= 12, s
        assert not BRIEF_BANNED.search(s) and L.lint_text(s, "card") == [], s
        assert not any(f.lower() in s.lower() for f in firms), s
    png = pg.evaluate("""async () => { const c = document.getElementById('ps-card-canvas');
        const b = await new Promise((r) => c.toBlob(r, 'image/png')); const a = new Uint8Array(await b.arrayBuffer());
        return [c.width, c.height, Array.from(a.slice(0, 8))]; }""")
    assert png[:2] == [1080, 1350] and png[2] == [137, 80, 78, 71, 13, 10, 26, 10]
    pg.select_option("#ps-card-size", "wide")
    pg.wait_for_timeout(300)
    assert pg.evaluate("[document.getElementById('ps-card-canvas').width, document.getElementById('ps-card-canvas').height]") == [1200, 630]
    with pg.expect_download() as d:
        pg.click("#ps-card-dl")
    raw = open(d.value.path(), "rb").read()
    assert raw[:8] == b"\x89PNG\r\n\x1a\n" and d.value.suggested_filename == "readiness-check-card.png"
    ctx.close()


# ------------------------------------------------------------------ counting
def test_counting_uses_the_live_analytics_only(browser, built_site):
    out = built_site["out"]
    assert "Disallow: /tools/prop-challenge-simulator/e/" in (out / "robots.txt").read_text()
    for name in ("ran", "ran-sample", "whatif", "expert", "export", "card"):
        stub = (out / "tools" / "prop-challenge-simulator" / "e" / name / "index.html").read_text(encoding="utf-8")
        assert '<meta name="robots" content="noindex">' in stub and "static.cloudflareinsights.com/beacon.min.js" in stub
    assert "/tools/prop-challenge-simulator/e/" not in (out / "sitemap.xml").read_text()
    ctx, pg, log = open_page(browser, built_site)
    log["requests"].clear()
    sample(pg)
    run(pg)
    run(pg)              # a second run in the same page load is not counted again
    whatif(pg)
    pg.click("#ps-expert summary")
    pg.wait_for_timeout(1500)
    others = [u for u in log["requests"] if not u.startswith(built_site["url"] + "/static/") and not u.startswith(BEACON)]
    stubs = [u[len(built_site["url"]):] for u in others if "/e/" in u]
    assert sorted(stubs) == ["/tools/prop-challenge-simulator/e/expert/", "/tools/prop-challenge-simulator/e/ran-sample/",
                             "/tools/prop-challenge-simulator/e/whatif/"]
    assert others == [built_site["url"] + s for s in stubs] or set(others) == {built_site["url"] + s for s in stubs}
    for u in log["requests"]:
        if "/e/" in u:
            assert "?" not in u and "#" not in u
    ctx.close()


# ------------------------------------------------------------------ every input format, and paste
FORMATS = ["mt5/deals_netting_40.htm", "mt4/statement.htm", "ibkr/activity_flex.csv", "tradovate/orders.csv",
           "tradingview/forty_trades.csv", "generic/ninety_trades.csv", "generic_roundtrip/tradezella.csv",
           "presets/ninjatrader_exec.csv"]


@pytest.mark.parametrize("rel", FORMATS)
def test_every_format_end_to_end(browser, built_site, rel):
    ctx, pg, log = open_page(browser, built_site)
    LOCAL = list(LOCAL_ONLY)   # an MT4/MT5 report no longer draws style-src errors (engine/mt.js withoutStyles)
    pg.set_input_files("#ps-file", os.path.join(FIX, rel))
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=60000)
    assert pg.input_value("#ps-filetz") == ("broker" if rel.startswith("mt") else "local")
    fill(pg, {"#ps-target": "1000", "#ps-daily": "200", "#ps-maxloss": "1000", "#ps-days": "30"})
    run(pg)
    assert len(pg.query_selector_all("#ps-out .rc-visuals > .rc-card")) == 3
    whatif(pg, "max_trades", "1")
    pg.click("#ps-expert summary")
    with pg.expect_download() as d:
        pg.click("#ps-json")
    assert json.loads(open(d.value.path(), encoding="utf-8").read())["out"]["runs"] == 10000
    assert [m for m in log["console"] if not any(x in m for x in LOCAL)] == []
    ctx.close()


def test_paste_needs_a_time_zone_then_runs(browser, built_site):
    ctx, pg, log = open_page(browser, built_site)
    pg.check("#ps-mode-paste")
    pg.fill("#ps-paste", open(os.path.join(FIX, "paste", "dxtrade_grid.txt"), encoding="utf-8").read())
    pg.click("#ps-paste-btn")
    assert "Choose the time zone of the times in your trades." in pg.inner_text("#ps-errors")
    assert pg.get_attribute("#ps-filetz", "aria-invalid") == "true"
    pg.select_option("#ps-filetz", "UTC")
    pg.click("#ps-paste-btn")
    pg.wait_for_selector("#ps-file-status:text-matches('^Read your pasted table')", timeout=60000)
    fill(pg, {"#ps-target": "100", "#ps-daily": "50", "#ps-maxloss": "100", "#ps-days": "20"})
    run(pg)
    assert len(pg.query_selector_all("#ps-out .rc-visuals > .rc-card")) == 3
    assert errors(log) == []
    ctx.close()


def paste(pg, text, tz="UTC"):
    pg.check("#ps-mode-paste")
    pg.select_option("#ps-filetz", tz)
    pg.fill("#ps-paste", text)
    pg.click("#ps-paste-btn")


def test_tradelocker_paste_reads_amount_as_the_size(browser, built_site):
    """Tester page report F2: TradeLocker heads the size column "Amount"."""
    ctx, pg, log = open_page(browser, built_site)
    paste(pg, open(os.path.join(FIX, "tester", "fx_tl.paste.txt"), encoding="utf-8").read())
    pg.wait_for_selector("#ps-file-status:text-matches('^Read your pasted table')", timeout=60000)
    assert pg.is_hidden("#ps-map") and pg.is_hidden("#ps-file-error")
    fill(pg, {"#ps-target": "100", "#ps-daily": "50", "#ps-maxloss": "100", "#ps-days": "20"})
    run(pg)
    assert errors(log) == []
    ctx.close()


def test_a_paste_without_a_named_size_column_asks_which_column(browser, built_site):
    """F2: one choice per missing field from the table's own headings, never a dead-end error."""
    text = open(os.path.join(FIX, "tester", "fx_tl.paste.txt"), encoding="utf-8").read().replace("\tAmount\t", "\tQ\t", 1)
    ctx, pg, log = open_page(browser, built_site)
    paste(pg, text)
    pg.wait_for_selector("#ps-map:not([hidden])", timeout=60000)
    assert pg.is_hidden("#ps-file-error")
    assert [s.get_attribute("data-field") for s in pg.query_selector_all("#ps-map select")] == ["qty"]
    assert pg.inner_text("label[for=ps-map-qty]") == "Quantity (size)"
    labels = [o.inner_text() for o in pg.query_selector_all("#ps-map-qty option")]
    assert labels[0] == "Choose a column" and "Q" in labels and "Instrument" in labels
    pg.click("#ps-run")   # running before the columns are picked says what to do
    assert "Pick the columns above" in pg.inner_text("#ps-errors")
    pg.click("#ps-map-btn")
    assert pg.inner_text("#ps-map-err") == "Pick a column for each box."
    pg.select_option("#ps-map-qty", label="Q")
    pg.click("#ps-map-btn")
    pg.wait_for_selector("#ps-file-status:text-matches('^Read your pasted table')", timeout=60000)
    assert pg.is_hidden("#ps-map")
    fill(pg, {"#ps-target": "100", "#ps-daily": "50", "#ps-maxloss": "100", "#ps-days": "20"})
    run(pg)
    assert errors(log) == []
    ctx.close()


# ------------------------------------------------------------------ layout: CLS, axe, overflow, both themes
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 1280])
def test_layout_axe_cls(browser, built_site, width, scheme):
    ctx, pg, log = open_page(browser, built_site, width=width, scheme=scheme, bypass_csp=True)   # axe is injected
    sample(pg)
    run(pg)
    whatif(pg)
    pg.wait_for_timeout(500)
    cls = pg.evaluate("window.__cls")
    assert cls < 0.05, cls
    pg.evaluate("document.querySelectorAll('details').forEach((d) => d.open = true)")
    if SHOTS:
        os.makedirs(SHOTS, exist_ok=True)
        pg.screenshot(path=os.path.join(SHOTS, f"page-{width}-{scheme}.png"), full_page=True)
    assert horizontal_overflow(pg) == []
    assert axe_violations(pg) == []
    assert errors(log) == []
    ctx.close()


@pytest.mark.parametrize("width", [320, 768])
def test_no_overflow_other_widths(browser, built_site, width):
    ctx, pg, _ = open_page(browser, built_site, width=width)
    sample(pg)
    run(pg)
    pg.evaluate("document.querySelectorAll('details').forEach((d) => d.open = true)")
    assert horizontal_overflow(pg) == []
    ctx.close()


def test_rule_labels_short_and_headings_clear_the_header(browser, built_site):
    ctx, pg, _ = open_page(browser, built_site, width=1280)
    for t in pg.eval_on_selector_all("#ps-wi-rule1 option, #ps-wi-rule2 option", "os => os.map((o) => o.textContent.trim())"):
        assert words(t) <= 6, t
    sample(pg)
    run(pg)
    whatif(pg)
    for sel in ("#ps-whatif-h", "#ps-out-h", "#ps-wi-h", "#ps-limits-h"):
        top, hb = pg.evaluate(f"""() => {{ const h = document.querySelector('{sel}'); h.scrollIntoView();
            return [h.getBoundingClientRect().top, document.querySelector('.site-header').getBoundingClientRect().bottom]; }}""")
        assert top >= hb, (sel, top, hb)   # scroll-margin-top keeps it below the sticky header
    assert pg.evaluate("getComputedStyle(document.querySelector('h2')).scrollMarginTop") == "73px"
    ctx.close()


@pytest.mark.parametrize("path", ["/tools/trade-stats/", "/tools/drawdown-calculator/", "/tools/trading-heatmap/", PATH])
@pytest.mark.parametrize("rel", ["mt5/deals_netting.htm", "mt5/deals_hedging.htm", "mt4/statement.htm"])
def test_metatrader_reports_draw_no_style_errors_on_any_tool(browser, built_site, path, rel):
    """Tester F7: the shared reader parsed the report's own style attributes under the page's CSP."""
    ctx = browser.new_context()
    pg = ctx.new_page()
    msgs = []
    pg.on("console", lambda m: msgs.append(m.text))
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("networkidle")
    pg.set_input_files("input[type=file]", os.path.join(FIX, rel))
    pg.wait_for_timeout(2500)
    assert not [m for m in msgs if MT_HTML in m], (path, rel)
    ctx.close()
