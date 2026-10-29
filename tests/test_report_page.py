"""Step 23: the rendered /report/ — lint on the report text, identical rule library,
consent unticked by default and counted only when ticked, axe, print, .ics, mailto."""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "checks"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
from lint import lint_text  # noqa: E402
from test_paid_flow import PRIVATE, new_session, stack  # noqa: E402,F401  (module-scoped stack fixture)

pytestmark = pytest.mark.skipif(not os.path.isdir(PRIVATE), reason="dt-private (server) not present")
FIX = os.path.join(HERE, "fixtures")
# Each has at least 30 trades: the server refuses a report on fewer (nothing is counted).
FILES = ["mt5/deals_netting_40.htm", "generic/ninety_trades.csv", "generic/no_losses.csv"]


def open_report(browser, stack, sid, color="light", width=1280, downloads=False):
    ctx = browser.new_context(color_scheme=color, viewport={"width": width, "height": 900}, accept_downloads=downloads)
    page = ctx.new_page()
    new_session(page, stack, sid)
    page.goto(stack["site"] + "/welcome/?session_id=" + sid)
    page.wait_for_selector("#w-ready", state="visible")
    page.click("#w-report")
    page.wait_for_url("**/report/")
    return ctx, page


def run(page, rel):
    sent = []
    page.on("request", lambda r: sent.append(r) if r.url.endswith("/analyse") else None)
    page.set_input_files("#rp-file", os.path.join(FIX, rel))
    page.wait_for_selector("#focus", timeout=60000)
    return json.loads(sent[-1].post_data)


@pytest.fixture(scope="module")
def three_reports(browser, stack):
    out = {}
    for i, rel in enumerate(FILES):
        ctx, page = open_report(browser, stack, f"cs_test_report{i:08d}")
        body = run(page, rel)
        out[rel] = {"text": page.inner_text("#rp-out"),
                    "rules": page.eval_on_selector_all("#rules label", "ls => ls.map(l => l.textContent)"),
                    "body": body}
        ctx.close()
    return out


def test_report_text_passes_lint(three_reports):
    for rel, r in three_reports.items():
        assert lint_text(r["text"], rel, paid=True) == [], rel
        for bad in ("NaN", "Infinity", "undefined", "null"):
            assert bad not in r["text"], (rel, bad)


def test_rule_library_order_identical_across_reports(three_reports):
    orders = [json.dumps(r["rules"]) for r in three_reports.values()]
    assert len(set(orders)) == 1 and len(three_reports[FILES[0]]["rules"]) >= 7


def test_focus_page_one(three_reports):
    # the 40-trade MT5 file has groups under 30, so nothing is tested (R-D3 addendum 3: the None line replaces H0a/H0b).
    # Its opens are 10 each at 09:00, 09:05, 09:10 and 09:15: it is NOT dates-only (stats2f), so no dates line.
    t = three_reports[FILES[0]]["text"]
    assert "None of the patterns could be tested in this file. Some are shown below without a verdict." in t   # 29 Oct: report.js plain()
    assert "open at exactly 00:00" not in t and "No pattern in this file is distinguishable from noise." not in t
    assert "Luck check coming: " in t and "described" not in t and "not tested" not in t.lower()
    assert three_reports[FILES[0]]["text"].lstrip().startswith("donttrade measures your own past trades.")


def test_consent_unticked_by_default_and_counted_only_when_ticked(browser, stack, three_reports):
    for r in three_reports.values():
        assert r["body"]["firm_consent"] is False
    ctx, page = open_report(browser, stack, "cs_test_consent0000001")
    assert page.is_checked("#rp-firm-consent") is False
    page.fill("#rp-firm", "Acme Prop, LLC")
    body = run(page, FILES[0])
    assert body["firm_consent"] is False and body["firm_name"] == "Acme Prop, LLC"
    db = json.loads(page.request.get(stack["api"] + "/__test/db").text())
    assert db["firm_counts"] == []
    ctx.close()
    ctx, page = open_report(browser, stack, "cs_test_consent0000002")
    page.fill("#rp-firm", "Acme Prop, LLC")
    page.check("#rp-firm-consent")
    run(page, FILES[0])
    db = json.loads(page.request.get(stack["api"] + "/__test/db").text())
    assert db["firm_counts"] == [{"firm_norm": "acme prop llc", "n": 1}]
    ctx.close()


@pytest.mark.parametrize("color", ["light", "dark"])
def test_axe_print_ics_mailto(browser, stack, color):
    ctx, page = open_report(browser, stack, "cs_test_axe" + color.ljust(11, "0"), color=color, width=375, downloads=True)
    run(page, FILES[1])
    assert horizontal_overflow(page) == []
    ctx2_page = page  # axe needs the page CSP bypassed only for injecting itself
    ctx.close()
    ctx = browser.new_context(color_scheme=color, bypass_csp=True, accept_downloads=True)
    page = ctx.new_page()
    new_session(page, stack, "cs_test_axb" + color.ljust(11, "0"))
    page.goto(stack["site"] + "/welcome/?session_id=cs_test_axb" + color.ljust(11, "0"))
    page.wait_for_selector("#w-ready", state="visible")
    page.click("#w-report")
    page.wait_for_url("**/report/")
    run(page, FILES[1])
    assert axe_violations(page) == []
    with page.expect_download() as dl:
        page.click("text=Add a re-test reminder (.ics)")
    ics = open(dl.value.path(), encoding="utf-8").read()
    assert "BEGIN:VCALENDAR" in ics and "SUMMARY:donttrade re-test" in ics
    # delta D1: the reminder starts at the second the server opens the re-test (first report + 30 d)
    db = json.loads(page.request.get(stack["api"] + "/__test/db").text())
    created = max(r["created"] for r in db["first_runs"]) // 1000
    import datetime as dt
    start = dt.datetime.fromtimestamp(created + 30 * 86400, dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    assert f"DTSTART:{start}" in ics.replace("\r\n ", ""), (start, ics)
    assert "opens at" in page.inner_text("#rp-retest")
    href = page.get_attribute("text=Send to your firm", "href")
    assert href.startswith("mailto:") and "for-firms%2F%3Fref%3Dreport" in href
    page.emulate_media(media="print")
    assert page.is_hidden("#pick-h") and page.is_hidden(".site-header")
    assert page.is_visible("#focus")
    ctx.close()
