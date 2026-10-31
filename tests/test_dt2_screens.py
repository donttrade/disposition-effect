"""DT-2 batch S1/S2 on screen (ARCHITECT-EVIDENCE-SCALE-AND-POWER-2026-10-31 §7 S1: "360 px overflow; axe").

The example report (the DT-2 engine's output on the committed file), a 30-trade DT-2 report (the engine golden
stats-r2__25-n30, drawn by the same report.js into the example page) and the pay dialog with its expectation line: no
sideways scroll at 360 px, no serious or critical axe issue in either theme, every pill on one line without a digit,
and no request to donttrade.ca, the Worker or Stripe (every host but 127.0.0.1 is blocked)."""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402

N30 = json.load(open(os.path.join(HERE, "fixtures", "paid-reports-dt2", "stats-r2__25-n30.report.json"), encoding="utf-8"))


def page_for(browser, built_site, width, scheme="light"):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, bypass_csp=True)
    seen = []
    ctx.route("**/*", lambda r: (seen.append(r.request.url), r.abort()) if not r.request.url.startswith(built_site["url"])
              else r.continue_())
    return ctx, ctx.new_page(), seen


def open_pay_dialog(pg):
    """A visible buy link (width > 0), else the one in the phone menu."""
    links = [a for a in pg.locator(".hdr-cta, a[data-pay]").all() if a.is_visible() and (a.bounding_box() or {}).get("width", 0) > 0]
    if not links:
        pg.click(".nav-menu > summary")
        links = [a for a in pg.locator(".nav-panel a[data-pay]").all() if (a.bounding_box() or {}).get("width", 0) > 0]
    links[0].click()


def draw_30(pg):
    pg.evaluate("""async (rep) => {
      const { renderReport } = await import('/static/js/paid/report.js');
      renderReport(rep, document.getElementById('sample-out'), { uses_left: 1, retest: null });
    }""", N30)


@pytest.mark.parametrize("which", ["example", "thirty"])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_report_fits_360_and_is_axe_clean(browser, built_site, which, scheme):
    ctx, pg, seen = page_for(browser, built_site, 360, scheme)
    pg.goto(built_site["url"] + "/sample-report/")
    pg.wait_for_selector("#sample-out .habit")
    if which == "thirty":
        draw_30(pg)
        pg.wait_for_selector("#sample-out #too-few-all, #sample-out .retest-reason, #sample-out .layer-check")
    pg.evaluate("document.querySelectorAll('#sample-out details').forEach((d) => { d.open = true; })")
    assert horizontal_overflow(pg) == []
    pills = pg.evaluate("[...document.querySelectorAll('#sample-out .badge')].map((b) => [b.textContent, b.getBoundingClientRect().height,"
                        " b.getBoundingClientRect().right])")
    assert pills
    for text, h, right in pills:
        assert not re.search(r"\d", text) and h <= 40 and right <= 360, (text, h, right)
    v = axe_violations(pg)
    assert v == [], v
    assert not [u for u in seen if re.search(r"donttrade\.ca|workers\.dev|stripe\.com", u)], seen   # every other host is blocked too
    ctx.close()


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_pay_dialog_line_fits_360_and_is_axe_clean(browser, built_site, scheme):
    ctx, pg, seen = page_for(browser, built_site, 360, scheme)
    pg.goto(built_site["url"] + "/pricing/")
    open_pay_dialog(pg)
    pg.wait_for_selector("#pay-dialog[open]")
    line = pg.locator("#pay-dialog .pay-expect").inner_text()
    assert line == "Small files often show “No sign”. Every dollar total and rule check is included."
    assert horizontal_overflow(pg) == []
    v = axe_violations(pg)
    assert v == [], v
    assert not [u for u in seen if re.search(r"donttrade\.ca|workers\.dev|stripe\.com", u)], seen   # every other host is blocked too
    ctx.close()
