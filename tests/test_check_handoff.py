"""The free check's one-tap hand-off (ARCHITECT-PLAN-FREE-CHECK-AND-HOOK-2026-11-07, batch C3).

The check leaves the file it read in sessionStorage['dt_check_v1'] (in this tab only, never sent); /report/ offers "Use the file you
just checked", runs the same strip -> /analyse path on them, and clears the key once /analyse has answered. Held here:
  1. storage blocked: the check promises nothing, and /report/ shows the drop zone with no error;
  2. the report's n_trades equals the check's, and the strip -> /analyse body is the same stripped rows as for a dropped file (no symbols);
  3. the key is cleared after a successful /analyse, after "Choose a different file", and when it is older than 24 hours;
  4. the check page makes no request that carries the stored trades; the privacy page carries the retention line and passes
     storage_claim_problems.
"""
import base64
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
from test_free_check import FIX, csvs, open_page, read_file  # noqa: E402,F401  (csvs is a fixture)

KEY = "dt_check_v1"
TOKEN = base64.urlsafe_b64encode(json.dumps({"salt": "c2FsdHNhbHRzYWx0"}).encode()).decode().rstrip("=") + ".sig"


def api_url(pg):
    return pg.get_attribute("meta[name='dt-api']", "content").rstrip("/") + "/analyse"


def go_to_report(browser_pg, site):
    browser_pg.goto(site["url"] + "/report/#t=" + TOKEN)
    browser_pg.wait_for_load_state("networkidle")


def test_the_check_keeps_the_trades_in_the_tab_and_says_so_only_when_it_did(browser, built_site, csvs):
    exp = json.load(open(os.path.join(FIX, "plain.json")))
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, csvs["plain"])
    line = pg.locator("#ck-out [data-handoff]")
    line.wait_for(state="visible")
    assert line.inner_text() == f"Uses the {exp['n_trades']} trades you just checked. No second upload."
    stored = json.loads(pg.evaluate(f"sessionStorage.getItem('{KEY}')"))
    assert stored["v"] == 1 and stored["n_trades"] == exp["n_trades"] and stored["b64"] and stored["ts"] > 0
    assert base64.b64decode(stored["b64"]) == open(csvs["plain"], "rb").read()     # the file itself, so /report/ reads it with its own engine
    assert pg.evaluate("localStorage.getItem('dt_check_v1')") is None          # the tab only, never localStorage
    assert log["posts"] == []
    ctx.close()


def test_storage_blocked_means_no_promise_and_no_error(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site)
    pg.add_init_script("Storage.prototype.setItem = function () { throw new DOMException('blocked', 'QuotaExceededError'); };")
    pg.reload()
    pg.wait_for_load_state("networkidle")
    read_file(pg, csvs["plain"])
    pg.wait_for_timeout(500)
    assert pg.locator("#ck-out [data-handoff]").is_hidden() and pg.locator("#ck-out [data-pay]").count() == 1
    assert pg.evaluate(f"sessionStorage.getItem('{KEY}')") is None
    assert [m for m in log["console"] if "blocked" in m or "Quota" in m] == [], log["console"]
    go_to_report(pg, built_site)
    assert pg.is_hidden("#rp-handoff") and pg.is_visible("#rp-drop")
    ctx.close()


def test_the_report_uses_the_checked_file_sends_the_same_stripped_rows_and_clears_the_key(browser, built_site, csvs):
    exp = json.load(open(os.path.join(FIX, "plain.json")))
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, csvs["plain"])
    pg.locator("#ck-out [data-handoff]").wait_for(state="visible")
    go_to_report(pg, built_site)
    assert pg.is_visible("#rp-handoff")
    assert pg.inner_text("#rp-hand-what").startswith(f"{exp['n_trades']} trades,")
    sent = []

    def answer(route):
        sent.append(route.request.post_data)
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"report": {}, "uses_left": 1}))

    pg.route(api_url(pg), answer)
    pg.click("#rp-hand-use")
    pg.wait_for_function(f"sessionStorage.getItem('{KEY}') === null")
    assert len(sent) == 1
    body = json.loads(sent[0])
    assert len(body["rows"]) == exp["n_trades"], len(body["rows"])               # the report's n_trades is the check's
    assert not re.search(r"\"(symbol|sym|account)\"|T3", sent[0])                  # stripped rows: no names, no tickers
    assert body["v"] == 1 and body["token"] == TOKEN
    ctx.close()


def test_a_failed_analyse_keeps_the_key_so_the_visitor_can_try_again(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, csvs["plain"])
    pg.locator("#ck-out [data-handoff]").wait_for(state="visible")
    go_to_report(pg, built_site)
    pg.route(api_url(pg), lambda r: r.fulfill(status=503, content_type="application/json", body="{}"))
    pg.click("#rp-hand-use")
    pg.wait_for_selector("#rp-status:not([hidden])")
    assert pg.evaluate(f"sessionStorage.getItem('{KEY}')") is not None
    ctx.close()


def test_choose_a_different_file_clears_the_key_and_a_day_old_key_is_ignored(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, csvs["plain"])
    pg.locator("#ck-out [data-handoff]").wait_for(state="visible")
    go_to_report(pg, built_site)
    pg.click("#rp-hand-other")
    assert pg.is_hidden("#rp-handoff") and pg.evaluate(f"sessionStorage.getItem('{KEY}')") is None
    old = {"v": 1, "b64": "QQ==", "n_trades": 1, "first": 0, "last": 1, "ts": 1}
    pg.evaluate(f"sessionStorage.setItem('{KEY}', JSON.stringify({json.dumps(old)}))")
    go_to_report(pg, built_site)
    pg.reload()
    pg.wait_for_load_state("networkidle")
    assert pg.is_hidden("#rp-handoff") and pg.evaluate(f"sessionStorage.getItem('{KEY}')") is None
    ctx.close()


def test_a_new_own_file_replaces_the_key_and_the_sample_does_not_touch_it(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site)
    read_file(pg, csvs["plain"])
    pg.locator("#ck-out [data-handoff]").wait_for(state="visible")
    before = pg.evaluate(f"sessionStorage.getItem('{KEY}')")
    pg.click("#ck-another")
    pg.click("#ck-sample-btn")
    pg.wait_for_selector("#ck-ex-h:has-text('Real public data, counted')")
    assert pg.evaluate(f"sessionStorage.getItem('{KEY}')") == before
    assert pg.locator("#ck-ex [data-handoff]").count() == 0
    ctx.close()


def test_the_privacy_page_says_where_the_trades_stay(built_site):
    import build as B
    h = (built_site["out"] / "privacy" / "index.html").read_text(encoding="utf-8")
    assert 'id="check-handoff"' in h
    assert "The free check keeps the file you checked in this browser tab until you close it or the report uses it. It is never sent." in re.sub(r"\s+", " ", h)
    assert B.storage_claim_problems(h, "privacy") == []
    fr = (built_site["out"] / "fr" / "confidentialite" / "index.html").read_text(encoding="utf-8")
    assert 'id="verification-gratuite"' in fr and "TODO-FR-REVIEW" not in fr         # the marker is a template comment, never shown


# ------------------------------------------------------------------ D1: no false promise

def fills_csv(path, src, headings, copies=1):
    """The `plain` fixture (round trips) rewritten as two fills per trade under the given headings, repeated `copies` times a week apart."""
    import csv
    import datetime as dt
    rows = list(csv.DictReader(open(src, encoding="utf-8")))
    out = [",".join(headings)]
    fmt = "%Y-%m-%d %H:%M:%S"
    for k in range(copies):
        for r in rows:
            o = dt.datetime.strptime(r["Open Time"], fmt) + dt.timedelta(days=7 * k)
            c = dt.datetime.strptime(r["Close Time"], fmt) + dt.timedelta(days=7 * k)
            buy = r["Direction"].lower().startswith("l")
            out.append(f"{o.strftime(fmt)},{r['Symbol']},{'Buy' if buy else 'Sell'},{r['Quantity']},{r['Open Price']}")
            out.append(f"{c.strftime(fmt)},{r['Symbol']},{'Sell' if buy else 'Buy'},{r['Quantity']},{r['Close Price']}")
    path.write_text("\n".join(out) + "\n")
    return str(path)


def test_a_file_that_needed_the_column_step_is_not_promised_a_second_upload(browser, built_site, csvs, tmp_path):
    p = fills_csv(tmp_path / "mapped.csv", csvs["plain"], ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"])
    ctx, pg, log = open_page(browser, built_site)
    pg.set_input_files("#ck-file", p)
    pg.wait_for_selector("#ck-map-btn")
    for field, col in {"date": "0", "symbol": "1", "side": "2", "qty": "3", "price": "4"}.items():
        if pg.locator(f"#ck-map-{field}").count():
            pg.select_option(f"#ck-map-{field}", col)
    pg.click("#ck-map-btn")
    pg.wait_for_selector("#ck-out-h:text-is('Your file, counted')", timeout=60000)
    line = pg.locator("#ck-out [data-handoff]")
    line.wait_for(state="visible")
    assert line.inner_text() == "You chose columns for this file, so re-select your file on the report page."
    assert "No second upload" not in pg.inner_text("#ck-out")
    assert pg.evaluate(f"sessionStorage.getItem('{KEY}')") is None
    go_to_report(pg, built_site)
    assert pg.is_hidden("#rp-handoff") and pg.is_visible("#rp-drop")                # the report asks for the file, as the line said
    ctx.close()


def test_a_file_over_the_cap_says_so_instead_of_promising(browser, built_site, csvs, tmp_path):
    p = fills_csv(tmp_path / "big.csv", csvs["plain"], ["Date", "Symbol", "Side", "Quantity", "Price"], copies=95)
    assert os.path.getsize(p) > 2500000
    ctx, pg, log = open_page(browser, built_site)
    pg.set_input_files("#ck-file", p)
    pg.wait_for_selector("#ck-out-h:text-is('Your file, counted')", timeout=120000)
    line = pg.locator("#ck-out [data-handoff]")
    line.wait_for(state="visible")
    assert line.inner_text() == "This file is too large to carry over, so re-select it on the report page."
    assert "No second upload" not in pg.inner_text("#ck-out")
    assert pg.evaluate(f"sessionStorage.getItem('{KEY}')") is None
    assert pg.locator("#ck-out [data-pay]").count() == 1                              # the offer itself is unchanged
    ctx.close()
