"""The /journal/ page (ARCHITECT-V3 §d.3-§d.5, step J3 onwards): Tester invariants J10-J13 and the page shell.

Built with [flags] journal = true (conftest journal_site); the default build has no journal at all.
Every test opens its own browser context, so each starts with an empty IndexedDB.
"""
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import build as B  # noqa: E402
from a11y import axe_violations, horizontal_overflow  # noqa: E402

READY = "html[data-journal=ready]"


def _html(site):
    return (site["out"] / "journal" / "index.html").read_text(encoding="utf-8")


def _csp(html):
    import html as h
    return h.unescape(re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html).group(1))


def open_journal(browser, site, hash_="", **kw):
    ctx = browser.new_context(**{"viewport": {"width": 1280, "height": 900}, **kw})
    pg = ctx.new_page()
    pg.goto(site["url"] + "/journal/" + hash_)
    pg.wait_for_selector(READY, state="attached")
    return ctx, pg


def add_sample(pg):
    if not pg.is_visible("#j-sample-btn"):
        pg.click("#j-import-btn")
    pg.click("#j-sample-btn")
    pg.wait_for_selector("#j-imp-add:not([disabled])")
    pg.click("#j-imp-add")
    pg.wait_for_selector("#j-toast:not([hidden])")


# ------------------------------------------------------------------ flag off: no journal anywhere
def test_flag_off_build_has_no_journal(built_site):
    out = built_site["out"]
    assert not (out / "journal").exists()
    assert not (out / "static" / "js" / "journal").exists() and not (out / "static" / "css" / "journal.css").exists()
    for fp in out.rglob("*.html"):
        assert 'href="/journal/' not in fp.read_text(encoding="utf-8", errors="replace"), fp
    assert "/journal/" not in (out / "sitemap.xml").read_text(encoding="utf-8")


# ------------------------------------------------------------------ J10: CSP and no analytics
def test_j10_csp_and_no_analytics_even_with_the_flag(journal_site, tmp_path):
    csp = _csp(_html(journal_site))
    assert "connect-src 'none';" in csp and "form-action 'none';" in csp and "worker-src 'self';" in csp
    assert "unsafe" not in csp
    from test_legal import build, toml_with
    toml = toml_with(tmp_path, journal=True, analytics=True)
    src = open(toml, encoding="utf-8").read().replace('cf_beacon_token = ""', 'cf_beacon_token = "fixture0token"')
    open(toml, "w", encoding="utf-8").write(src)
    r, out = build(tmp_path, "a", DT_SITE_TOML=toml)
    assert r.returncode == 0, r.stderr
    html = (out / "journal" / "index.html").read_text(encoding="utf-8")
    assert "cloudflareinsights" not in html
    assert "connect-src 'none';" in _csp(html) and "script-src 'self';" in _csp(html)
    assert "cloudflareinsights" in (out / "index.html").read_text(encoding="utf-8")   # other pages keep it
    # the build guard refuses a journal page with a beacon or a wider policy
    assert B.journal_problem(html.replace("</head>", '<script src="https://static.cloudflareinsights.com/x.js"></script></head>'), "/journal/")
    assert B.journal_problem(html.replace("connect-src &#39;none&#39;", "connect-src &#39;self&#39;"), "/journal/")
    assert B.journal_problem(html, "/journal/") is None


def test_journal_page_has_no_inline_script_or_style(journal_site):
    html = _html(journal_site)
    assert " style=" not in html
    for m in re.finditer(r"<script\b([^>]*)>(.*?)</script>", html, re.S):
        attrs, body = m.groups()
        assert "src=" in attrs or 'type="application/ld+json"' in attrs or 'type="text/csv"' in attrs, attrs
    assert "<form" not in html   # form-action 'none': the page has no form to send
    assert 'data-ask' not in html  # no answer-box form in the header here either


# ------------------------------------------------------------------ J12: JavaScript off
def test_j12_js_off_explains_and_offers_the_template(browser, journal_site):
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 375, "height": 800})
    pg = ctx.new_page()
    pg.goto(journal_site["url"] + "/journal/")
    note = pg.locator("#j-nojs")
    assert note.is_visible()
    assert "needs JavaScript, because it runs in your browser" in note.inner_text()
    assert pg.locator("#j-nojs a[href='/static/samples/demo-trades.csv']").count() == 1
    assert not pg.is_visible("#j-app")
    assert pg.locator("h2", has_text="Where your journal is kept").is_visible()
    assert horizontal_overflow(pg) == []
    ctx.close()


# ------------------------------------------------------------------ import through the page, J5/J9 end to end
def test_sample_import_reimport_and_undo_through_the_page(browser, journal_site):
    ctx, pg = open_journal(browser, journal_site)
    assert pg.is_visible("#j-import") and not pg.is_visible("#j-bar")   # empty state: the drop zone first
    add_sample(pg)
    assert "Added 160 trades to Sample (synthetic trades)." in pg.inner_text("#j-toast")
    assert pg.evaluate("document.activeElement.id") == "j-toast"
    assert "160 trades saved on this device" in pg.inner_text("#j-status")
    # the same file again: nothing new
    pg.click("#j-import-btn")
    pg.click("#j-sample-btn")
    pg.wait_for_selector("#j-imp-add")
    assert pg.inner_text("[data-k=fresh]") == "0" and pg.inner_text("[data-k=dupes]") == "160"
    assert pg.is_disabled("#j-imp-add")
    pg.click("#j-preview button:has-text('Cancel')")
    # undo from Imports, with the count in the question
    pg.goto(journal_site["url"] + "/journal/#imports")
    pg.wait_for_selector(READY, state="attached")
    pg.click("#j-view-imports button:has-text('Undo')")
    assert "Remove the 160 trades this import added? Notes on them are removed too." in pg.inner_text("#j-view-imports")
    pg.click("button:has-text('Remove them')")
    pg.wait_for_selector("#j-bar", state="hidden")
    assert pg.is_visible("#j-sample-btn")   # back to the empty state; the sample account went with its import
    ctx.close()


def test_import_a_real_format_file_and_account_naming(browser, journal_site):
    ctx, pg = open_journal(browser, journal_site)
    pg.set_input_files("#j-file", os.path.join(REPO, "tests", "fixtures", "mt5", "deals.csv"))
    pg.wait_for_selector("#j-imp-add")
    text = pg.inner_text("#j-preview")
    assert "MetaTrader 5" in text and "(beta)" in text and "times: broker server time" in text
    assert pg.input_value("#j-imp-name") == "MT5 account 1"
    pg.fill("#j-imp-name", "My MT5")
    pg.wait_for_timeout(300)
    pg.click("#j-imp-add")
    pg.wait_for_selector("#j-toast:not([hidden])")
    assert "to My MT5." in pg.inner_text("#j-toast")
    ctx.close()


def test_a_bad_file_shows_the_engine_message(browser, journal_site, tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("hello,world\n1,2\n", encoding="utf-8")
    ctx, pg = open_journal(browser, journal_site)
    pg.set_input_files("#j-file", str(bad))
    pg.wait_for_selector("#j-error:not([hidden])")
    assert "This file could not be read" in pg.inner_text("#j-error")
    ctx.close()


def test_trades_table_sort_pages_and_detail(browser, journal_site):
    ctx, pg = open_journal(browser, journal_site, "#trades")
    add_sample(pg)
    pg.wait_for_selector("#j-view-trades:not([hidden])")
    assert "Showing 1–100 of 160 trades" in pg.inner_text("#j-trades-count")
    first = pg.inner_text(".j-rowbtn >> nth=0")
    assert first.startswith("2026-10-19")   # newest close first
    pg.click("text=Next 100")
    assert "Showing 101–160 of 160 trades" in pg.inner_text("#j-trades-count")
    pg.click("[data-sort=pnl]")
    pg.click("[data-sort=pnl]")   # second click: ascending
    assert pg.get_attribute("th[aria-sort]", "aria-sort") == "ascending"
    vals = pg.eval_on_selector_all("td[data-k=pnl]", "ts => ts.map(t => parseFloat(t.textContent.replace('−', '-').replace(/[^0-9.\\-]/g, '')))")
    assert vals == sorted(vals)
    pg.click(".j-rowbtn >> nth=0")
    assert pg.evaluate("document.activeElement.id") == "j-detail-h"
    assert "cannot be edited here" in pg.inner_text("#j-detail")
    pg.click("text=Close the details")
    assert pg.evaluate("document.activeElement.classList.contains('j-rowbtn')")
    ctx.close()


# ------------------------------------------------------------------ J11: no request leaves the page
def test_j11_no_request_to_any_origin_after_load(browser, journal_site):
    ctx = browser.new_context()
    pg = ctx.new_page()
    seen = []
    pg.goto(journal_site["url"] + "/journal/")
    pg.wait_for_selector(READY, state="attached")
    pg.on("request", lambda r: seen.append(r.url))
    add_sample(pg)
    pg.set_input_files("#j-file", os.path.join(REPO, "tests", "fixtures", "mt5", "deals_netting.htm"))   # HTML: on the page
    pg.wait_for_selector("#j-imp-add")
    pg.click("#j-imp-add")
    pg.wait_for_timeout(300)
    for h in ("#trades", "#imports", "#calendar", "#stats", "#backup"):
        pg.evaluate(f"location.hash = '{h}'")
        pg.wait_for_timeout(100)
    base = journal_site["url"]
    for u in seen:   # only the page's own scripts and worker, and a font the browser loads late
        assert (u.startswith(base + "/static/js/") and re.search(r"\.js\?v=[0-9a-f]{8}$", u)) or \
            re.fullmatch(re.escape(base) + r"/static/fonts/[a-z0-9-]+\.woff2", u), u
    assert "to other sites since it opened: 0" in pg.inner_text("#j-requests")
    ctx.close()


# ------------------------------------------------------------------ standing rules: 320/375/1280, both themes
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 1280])
def test_journal_axe_and_overflow(browser, journal_site, scheme, width):
    ctx = browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    pg.goto(journal_site["url"] + "/journal/")
    pg.wait_for_selector(READY, state="attached")
    assert horizontal_overflow(pg) == [] and axe_violations(pg) == [], ("empty", width, scheme)
    add_sample(pg)
    for h in ("#trades", "#imports"):
        pg.evaluate(f"location.hash = '{h}'")
        pg.wait_for_timeout(150)
        if h == "#trades":
            pg.click(".j-rowbtn >> nth=0")
        assert horizontal_overflow(pg) == [], (h, width, scheme)
        assert axe_violations(pg) == [], (h, width, scheme)
    ctx.close()


# ------------------------------------------------------------------ J38: lint on every journal string
def test_j38_lint_passes_on_the_journal_build_including_script_strings(journal_site, tmp_path):
    import shutil
    import lint as L
    assert L.lint_build(str(journal_site["out"])) == []
    copy = tmp_path / "site"
    shutil.copytree(journal_site["out"], copy)
    js = copy / "static" / "js" / "journal" / "ui.js"
    js.write_text(js.read_text(encoding="utf-8") + "\nconst planted = 'This setup should be your best setup';\n", encoding="utf-8")
    assert any(p[1] == "/static/js/journal/ui.js" for p in L.lint_build(str(copy)))
