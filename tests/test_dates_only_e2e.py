"""R-D3 addendum 3 I-9, acceptance 2 (end to end, public): a date-only export, in the donttrade CSV template (an empty
Time column) and in the generic round-trip CSV (dates in Open Time and Close Time), parsed and stripped by the browser
engine in 4 time-zone / locale contexts, gives o mod 1440 = 0 and h mod 86400 = 0 on every row, so the server's rule
(a date-only row) sees it. A timed file (the 40-trade MT5 report, opens at 09:00-09:15) gives no date-only row.
If a context shifted the times, this test would fail: that is a blocker, not something to adjust here."""
import base64
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
CONTEXTS = [("UTC", "en-US"), ("America/Toronto", "en-CA"), ("Asia/Kolkata", "en-IN"), ("Europe/Berlin", "de-DE")]
OFFSETS = {"UTC": 0, "America/Toronto": 240, "Asia/Kolkata": -330, "Europe/Berlin": -120}


def template_csv():
    # 40 round trips over 8 weeks, opened and closed on whole dates (same day or 1-3 days later), no times;
    # the dates cross both DST changes of 2026 (Europe 29 Mar / 25 Oct, North America 8 Mar / 1 Nov).
    import datetime as dt
    lines = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    d0 = dt.date(2026, 3, 2)
    for k in range(40):
        o = d0 + dt.timedelta(days=2 * k + (k // 5) * 30)
        c = o + dt.timedelta(days=k % 4)
        sym = ["AAA", "BBB"][k % 2]
        px = 100 + k
        lines.append(f"{o.isoformat()},,{sym},Buy,10,{px},USD,1.00")
        lines.append(f"{c.isoformat()},,{sym},Sell,10,{px + (1 if k % 3 else -2)},USD,1.00")
    return ("\n".join(lines) + "\n").encode()


def roundtrip_csv():
    import datetime as dt
    lines = ["Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees"]
    d0 = dt.date(2026, 3, 2)
    for k in range(40):
        o = d0 + dt.timedelta(days=3 * k + (k // 8) * 40)
        c = o + dt.timedelta(days=k % 5)
        lines.append(f"{o.isoformat()},{c.isoformat()},{['AAA', 'BBB', 'CCC'][k % 3]},{'Long' if k % 2 else 'Short'},5,"
                     f"{50 + k},{50 + k + (1 if k % 4 else -3)},0.50")
    return ("\n".join(lines) + "\n").encode()


@pytest.fixture(scope="module", params=CONTEXTS, ids=[c[0] for c in CONTEXTS])
def engine_page(request, browser, repo_server):
    tz, locale = request.param
    ctx = browser.new_context(timezone_id=tz, locale=locale)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/tests/harness.html")
    page.wait_for_function("document.getElementById('status').textContent === 'ready'")
    assert page.evaluate("new Date(Date.UTC(2026, 8, 1)).getTimezoneOffset()") == OFFSETS[tz]
    yield page
    assert not errors, errors
    ctx.close()


def stripped(page, data):
    out = page.evaluate("([b, s]) => window.stripFixture(b, s)", [base64.b64encode(data).decode(), "SALT-1"])
    res = json.loads(out)
    assert res is not None, "the file did not parse"
    return res["rows"]


@pytest.mark.parametrize("kind", ["template", "roundtrip"])
def test_a_date_only_export_strips_to_date_only_rows(engine_page, kind):
    rows = stripped(engine_page, template_csv() if kind == "template" else roundtrip_csv())
    assert len(rows) == 40
    bad = [r for r in rows if r["o"] % 1440 != 0 or r["h"] % 86400 != 0]
    assert bad == [], f"BLOCKER: a context shifted date-only times: {bad[:3]}"
    assert any(r["h"] == 0 for r in rows) and any(r["h"] >= 86400 for r in rows)


def test_the_40_trade_mt5_file_has_no_date_only_row(engine_page):
    with open(os.path.join(HERE, "fixtures", "mt5", "deals_netting_40.htm"), "rb") as f:
        rows = stripped(engine_page, f.read())
    assert len(rows) == 40
    assert [r for r in rows if r["o"] % 1440 == 0 and r["h"] % 86400 == 0] == []
