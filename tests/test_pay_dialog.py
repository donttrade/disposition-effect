"""The site-wide pay dialog (29 Oct, owner: "the whole website always one click away from paying").

Every buy link opens a <dialog> on the page it is on (static/js/pay.js; partials/pay_dialog.html): three facts,
"Full details before you pay" (the complete Before-you-pay block, copied only when opened from /before-you-pay/, a
noindex page with no analytics, so opening it is not a /pricing/ pageview), then the Stripe button. Without JS the link goes to /pricing/#last-step. Esc closes it and focus goes back to the link. The
seller's address stays out of every page's HTML except build.ADDRESS_LINE_PATHS; no sample figure in the dialog.
"""
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import build as B  # noqa: E402
import lint as L  # noqa: E402


def _no_beacon_network(ctx):
    """With analytics on, the Cloudflare beacon script is answered locally with an empty script: a local origin
    gets CORS errors from the real one, which are not the site's. Requests still show in page.on("request")."""
    ctx.route("https://static.cloudflareinsights.com/**",
              lambda r: r.fulfill(status=200, content_type="text/javascript", body=""))
    return ctx


def _dialog(html):
    m = re.search(r'(?s)<dialog class="pay-dialog".*?</dialog>', html)
    return m.group(0) if m else None


def test_dialog_markup_on_every_page_without_the_address(built_site):
    addresses = L.private_values(("premises_address",), data=L.read_private() or {})
    n = 0
    for root, _, files in os.walk(built_site["out"]):
        for name in files:
            if not name.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(root, name), built_site["out"])
            html = open(os.path.join(root, name), encoding="utf-8").read()
            if 'http-equiv="refresh"' in html or "<main" not in html:
                continue
            d = _dialog(html)
            assert d, rel
            n += 1
            assert "data-seller-block" not in d and all(a not in d for a in addresses), rel
            assert "Continue to secure payment" in d and "Full details before you pay" in d
            # the expander comes before the Stripe button
            assert d.index("Full details before you pay") < d.index("buy.stripe.com")
            # no sample or study figure: the only amount is the price
            assert set(re.findall(r"\$[\d,.]+", re.sub(r"<[^>]+>", " ", d))) == {"$39"}, rel
            url = B.url_of(rel)
            if url not in B.ADDRESS_LINE_PATHS:
                assert all(a not in html for a in addresses), rel
    assert n > 20


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 1280])
def test_buy_link_opens_the_dialog_esc_returns_focus(browser, built_site, width, scheme):
    ctx = _no_beacon_network(browser.new_context(viewport={"width": width, "height": 844}, color_scheme=scheme))
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(built_site["url"] + "/tools/trade-stats/")
    pg.wait_for_load_state("networkidle")
    link = pg.locator('main a[href="/pricing/#last-step"]').first
    link.scroll_into_view_if_needed()
    link.click()
    assert pg.url.endswith("/tools/trade-stats/"), "the page does not change"
    assert pg.evaluate("document.getElementById('pay-dialog').open")
    assert pg.evaluate("document.getElementById('pay-dialog').contains(document.activeElement)")
    box = pg.locator("#pay-dialog").bounding_box()
    assert box["x"] >= -0.5 and box["x"] + box["width"] <= width + 0.5
    pg.click("#pay-dialog .pay-more > summary")
    pg.wait_for_selector("#pd-before-you-pay dl.byp", timeout=10000)
    rows = pg.eval_on_selector_all("#pd-before-you-pay dl.byp dt", "ds => ds.map(d => d.textContent.trim())")
    for need in ("Seller", "Business address", "What you buy", "Price", "Currency and fees", "Refunds", "Restrictions"):
        assert need in rows, rows
    assert pg.locator("#pay-dialog iframe").count() == 0 and pg.locator("iframe.pd-frame").count() == 0
    assert horizontal_overflow(pg) == []
    pg.keyboard.press("Escape")
    assert not pg.evaluate("document.getElementById('pay-dialog').open")
    assert pg.evaluate("document.activeElement.getAttribute('href')") == "/pricing/#last-step"
    assert errors == []
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 1280])
def test_dialog_axe_clean(browser, built_site, width, scheme):
    ctx = browser.new_context(viewport={"width": width, "height": 844}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/pricing/")
    pg.wait_for_load_state("networkidle")
    if width < 900:
        pg.click(".nav-menu > summary")
        pg.click(".nav-panel a[data-pay]")
    else:
        pg.click(".hdr-cta")
    pg.click("#pay-dialog .pay-more > summary")
    pg.wait_for_selector("#pd-before-you-pay")
    assert pg.locator("[id='before-you-pay']").count() == 1, "the copy renames its ids"
    assert axe_violations(pg) == []
    ctx.close()


def test_without_js_the_buy_link_goes_to_the_pay_step(browser, built_site):
    ctx = browser.new_context(viewport={"width": 1280, "height": 844}, java_script_enabled=False)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/tools/")
    pg.click(".hdr-cta")
    pg.wait_for_load_state()
    assert pg.url.endswith("/pricing/#last-step")
    ctx.close()


def test_details_page_is_the_block_alone_without_analytics(built_site):
    """29 Oct: /before-you-pay/ holds the same Before-you-pay block as /pricing/, loads no beacon, is noindex,
    out of the sitemap, disallowed in robots.txt, and may carry the address (build.ADDRESS_LINE_PATHS)."""
    out = built_site["out"]
    page = (out / "before-you-pay" / "index.html").read_text(encoding="utf-8")
    pricing = (out / "pricing" / "index.html").read_text(encoding="utf-8")
    block = lambda h: re.search(r'(?s)<section class="notice" id="before-you-pay".*?</section>', h).group(0)
    # the same block; only the heading's tag differs (h2 under the page's h1, h3 in /pricing/'s panel: axe heading-order)
    assert block(page).replace('<h2 id="byp-h">', '<h3 id="byp-h">').replace("</h2>", "</h3>") == block(pricing)
    assert "cloudflareinsights" not in page   # with analytics on, every other page has it (lint flags_of_build)
    assert '<meta name="robots" content="noindex">' in page
    assert "/before-you-pay/" not in (out / "sitemap.xml").read_text(encoding="utf-8")
    assert "Disallow: /before-you-pay/\n" in (out / "robots.txt").read_text(encoding="utf-8")
    assert "/before-you-pay/" in B.ADDRESS_LINE_PATHS and 'data-business-id="full"' in page


@pytest.mark.parametrize("start", ["/tools/trade-stats/", "/"])
def test_opening_the_details_requests_no_pricing_page(browser, built_site, start):
    """The hidden frame loads /before-you-pay/, never /pricing/, and no beacon fires from it."""
    ctx = _no_beacon_network(browser.new_context(viewport={"width": 1280, "height": 844}))
    pg = ctx.new_page()
    pg.goto(built_site["url"] + start)
    pg.wait_for_load_state("networkidle")
    seen = []
    pg.on("request", lambda r: seen.append(r.url))
    pg.click(".hdr-cta")
    pg.click("#pay-dialog .pay-more > summary")
    pg.wait_for_selector("#pd-before-you-pay dl.byp", timeout=10000)
    pg.wait_for_load_state("networkidle")
    paths = [u[len(built_site["url"]):] for u in seen if u.startswith(built_site["url"])]
    assert "/before-you-pay/" in paths, paths
    assert not any(p.startswith("/pricing/") for p in paths), paths
    assert not any("cloudflareinsights" in u for u in seen), seen
    assert pg.locator('#pay-dialog a[href="/pricing/#before-you-pay"]').count() == 0   # replaced by the block
    assert pg.locator("#pd-byp-h").evaluate("h => h.tagName") == "H3"   # under the dialog's h2
    ctx.close()


@pytest.mark.parametrize("js,hash,want_open", [(False, "#last-step", True), (False, "", True),
                                                (True, "", False), (True, "#last-step", True), (True, "#before-you-pay", True)])
def test_last_step_open_without_js_closed_with_js_unless_targeted(browser, built_site, js, hash, want_open):
    """Tester sweep 3 #4: #last-step (and #byp-more inside it) are open in the HTML (no-JS buyers land on the open pay
    step with the full details); pay.js closes each at load unless the hash targets it or something inside it, with
    no layout shift."""
    ctx = _no_beacon_network(browser.new_context(viewport={"width": 390, "height": 844}, java_script_enabled=js))
    if js:
        ctx.add_init_script("window.__cls = 0; new PerformanceObserver(l => { for (const e of l.getEntries())"
                            " if (!e.hadRecentInput) window.__cls += e.value; }).observe({type: 'layout-shift', buffered: true});")
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/pricing/" + hash)
    pg.wait_for_load_state("networkidle")
    assert pg.locator("#last-step").evaluate("d => d.open") is want_open
    assert pg.locator("#last-step a[href*='buy.stripe.com']").is_visible() is want_open
    # the full details: open without JS, closed with JS unless the URL names them
    assert pg.locator("#before-you-pay").is_visible() is ((not js) or hash == "#before-you-pay")
    if js:
        pg.wait_for_timeout(500)
        assert pg.evaluate("window.__cls") < 0.05
        if not want_open:   # the summary still opens it
            pg.click("#last-step > summary")
            assert pg.locator("#last-step a[href*='buy.stripe.com']").is_visible()
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [390, 1280])
def test_details_page_axe_clean_with_heading_order(browser, built_site, width, scheme):
    """Tester sweep 3 #6: h1 then the block's h2; axe (moderate included) finds nothing."""
    ctx = browser.new_context(viewport={"width": width, "height": 844}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/before-you-pay/")
    pg.wait_for_load_state("networkidle")
    assert axe_violations(pg, impacts=("minor", "moderate", "serious", "critical")) == []
    ctx.close()
