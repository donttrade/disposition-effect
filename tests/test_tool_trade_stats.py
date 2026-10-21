"""Step 10: the free dashboard at /tools/trade-stats/.

Plan checks: zero non-static requests during analysis, no cookies and nothing stored but
the theme, keyboard-only run, axe clean, no overflow at 375 px, tool JS <= 80 KB gzipped.
Plus: the numbers on screen equal the Python reference on the demo file, error codes are
shown, the canary in account/header fields never reaches the DOM, and the rendered text
passes the wording lint.
"""
import gzip
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(HERE, "reference"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import lint as L  # noqa: E402
import engine_ref as E  # noqa: E402

# Free-launch condition C1: the badges are off by default (site.toml free_badges = false). These
# tests are about the badges, so this module runs on the badges build (conftest.badges_site);
# tests/test_free_badges.py covers the default build.
@pytest.fixture(scope="session")
def built_site(badges_site):
    return badges_site


FIX = os.path.join(HERE, "fixtures")
DEMO = os.path.join(REPO, "site", "static", "samples", "demo-trades.csv")
CANARY = "CANARY-ZQ7X"
PATH = "/tools/trade-stats/"


def open_page(browser, site, width=1280, scheme="light", **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, **kw)
    page = ctx.new_page()
    log = {"requests": [], "console": [], "errors": []}
    page.on("request", lambda r: log["requests"].append((r.method, r.url, r.resource_type)))
    page.on("console", lambda m: log["console"].append(m.text))
    page.on("pageerror", lambda e: log["errors"].append(str(e)))
    page.goto(site["url"] + PATH)
    page.wait_for_load_state("networkidle")
    return ctx, page, log


def wait_done(page):
    page.wait_for_selector("#ts-noise table", timeout=90000)


def test_demo_file_is_what_the_generator_writes():
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "make_demo_trades.py"), "--check"],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stdout


def test_csp_blocks_all_connections(built_site):
    html = (built_site["out"] / "tools" / "trade-stats" / "index.html").read_text()
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1)
    assert "connect-src &#39;none&#39;" in csp


def test_sample_matches_reference_and_sends_nothing(browser, built_site):
    ctx, page, log = open_page(browser, built_site)
    log["requests"].clear()
    page.click("#ts-sample-btn")
    wait_done(page)
    # 1. numbers on screen == the Python reference on the same bytes
    ref = E.parse_file(open(DEMO, "rb").read())
    st = E.free_stats(ref["trades"])
    nc = E.noise_checks(ref["trades"])
    k = lambda key: page.inner_text(f'#ts-out dd[data-k="{key}"]')
    assert k("n") == str(st["n"])
    assert k("win_rate") == f"{100 * st['win_rate']:.1f}%"
    assert k("profit_factor") == f"{st['profit_factor']:.2f}"
    assert k("net_pnl") == "+$" + f"{st['net_pnl']:,.2f}"
    for c in nc["checks"]:
        row = page.locator(f'tr[data-check="{c["stat"]}"]')
        assert c["label"] in row.inner_text()
        assert f"{c['p']:.4f}" in row.inner_text()
    # 2. the network: only same-origin GETs of static files, and none at all after the click
    #    other than the worker script (the analysis itself requests nothing)
    for method, url, _ in log["requests"]:
        assert method == "GET" and url.startswith(built_site["url"] + "/static/js/"), url
    # 3. no cookies; storage holds nothing (the theme key only appears after the toggle)
    assert ctx.cookies() == []
    assert page.evaluate("Object.keys(localStorage)") == []
    assert page.evaluate("Object.keys(sessionStorage)") == []
    assert page.evaluate("indexedDB.databases().then(d => d.length)") == 0
    # 4. no NaN/Infinity/undefined; wording lint clean; no console output; teaser shown
    body = page.inner_text("main")
    assert not re.search(r"\b(NaN|Infinity|undefined|null)\b", body)
    assert L.lint_text(body, PATH) == []
    assert log["console"] == [] and log["errors"] == []
    assert page.is_visible("#ts-teaser")
    assert "Synthetic trades made up for this demo" in body
    assert page.get_attribute("#ts-teaser a.btn", "href") == "/for-traders/#waitlist"
    assert "Join the waitlist — $39 founding price" in page.inner_text("#ts-teaser")
    ctx.close()


def test_own_file_with_canary_never_reaches_page(browser, built_site):
    ctx, page, log = open_page(browser, built_site)
    page.set_input_files("#ts-file", os.path.join(FIX, "mt5", "deals_hedging.htm"))
    wait_done(page)
    html = page.content()
    assert CANARY not in html
    assert "Beta" in page.inner_text("#ts-warnings")
    assert page.locator('#ts-warnings li[data-code="W_HEDGING"]').count() == 1
    assert ctx.cookies() == [] and page.evaluate("Object.keys(localStorage)") == []
    ctx.close()


@pytest.mark.parametrize("name,code", [("empty.csv", "E_EMPTY"), ("header_only.csv", "E_HEADER_ONLY"),
                                       ("one_execution.csv", "E_NO_CLOSED_TRADES"), ("ambiguous_date.csv", "E_AMBIGUOUS_DATE"),
                                       ("unknown_format.csv", "E_UNKNOWN_FORMAT")])
def test_errors_are_shown_with_their_code(browser, built_site, name, code):
    ctx, page, _ = open_page(browser, built_site)
    page.set_input_files("#ts-file", os.path.join(FIX, "errors", name))
    page.wait_for_selector("#ts-error:not([hidden])")
    assert code in page.inner_text("#ts-error")
    assert page.is_hidden("#ts-out")
    ctx.close()


def test_keyboard_only_run(browser, built_site):
    ctx, page, _ = open_page(browser, built_site)
    # Tab until the native file input has focus, then open the chooser with the keyboard.
    for _ in range(40):
        page.keyboard.press("Tab")
        if page.evaluate("document.activeElement.id") == "ts-file":
            break
    assert page.evaluate("document.activeElement.id") == "ts-file"
    with page.expect_file_chooser() as fc:
        page.keyboard.press("Space")
    fc.value.set_files(os.path.join(FIX, "generic", "ninety_trades.csv"))
    wait_done(page)
    assert page.evaluate("document.activeElement.id") == "ts-out-h"  # focus moves to the results
    # the sample button and the table fallback work from the keyboard too
    page.focus("#ts-sample-btn")
    page.keyboard.press("Enter")
    wait_done(page)
    page.focus("#ts-out details summary")
    page.keyboard.press("Enter")
    assert page.evaluate("document.querySelector('#ts-out details').open")
    ctx.close()


def test_starting_balance(browser, built_site):
    ctx, page, _ = open_page(browser, built_site)
    page.click("#ts-sample-btn")
    wait_done(page)
    page.fill("#ts-balance", "1,5")
    page.keyboard.press("Tab")
    assert page.is_visible("#ts-balance-err") and "decimal point" in page.inner_text("#ts-balance-err")
    page.fill("#ts-balance", "10000")
    page.keyboard.press("Tab")
    assert page.is_hidden("#ts-balance-err")
    assert page.inner_text('[data-k="max_drawdown_pct"]').endswith("%")
    assert page.locator("#ts-noise table").count() == 1  # the checks are kept, not re-run
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [375, 1280])
def test_axe_and_overflow_with_results(browser, built_site, scheme, width):
    ctx, page, _ = open_page(browser, built_site, width=width, scheme=scheme, bypass_csp=True)
    page.click("#ts-sample-btn")
    wait_done(page)
    page.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert horizontal_overflow(page) == []
    assert axe_violations(page) == []
    ctx.close()


def test_tool_js_budget(browser, built_site):
    ctx, page, log = open_page(browser, built_site)
    page.click("#ts-sample-btn")
    wait_done(page)
    js = sorted({u for _, u, t in log["requests"] if u.endswith(".js")})
    total = 0
    for u in js:
        rel = u.split(built_site["url"], 1)[1].lstrip("/")
        total += len(gzip.compress((built_site["out"] / rel).read_bytes(), 9))
    assert total <= 80 * 1024, total
    ctx.close()
