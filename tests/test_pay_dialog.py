"""The site-wide pay dialog (29 Oct, owner: "the whole website always one click away from paying").

Every buy link opens a <dialog> on the page it is on (static/js/pay.js; partials/pay_dialog.html): three facts,
"Full details before you pay" (the complete Before-you-pay block, copied from /pricing/ only when opened), then the
Stripe button. Without JS the link goes to /pricing/#last-step. Esc closes it and focus goes back to the link. The
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
    ctx = browser.new_context(viewport={"width": width, "height": 844}, color_scheme=scheme)
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
