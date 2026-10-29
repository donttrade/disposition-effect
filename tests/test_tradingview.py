"""TradingView Order History export: detection, JS <-> reference parity on generated variants,
and the round trip through the free trade-stats tool and the paid report.

All files are synthetic (tests/fixtures/make_tradingview.py). The fixed fixtures are also in
the golden test (test_engine_golden.py) and the hand oracles (fixtures/oracles.py).
"""
import base64
import json
import os
import random
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, os.path.join(HERE, "fixtures"))
import engine_ref as E  # noqa: E402
import make_tradingview as TV  # noqa: E402
from test_engine_golden import comparable, same  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
CANARY = "CANARY-ZQ7X"


def load(rel):
    with open(os.path.join(FIX, rel), "rb") as f:
        return f.read()


def ref(data):
    try:
        return {"result": E.parse_file(data)}
    except E.EngineError as e:
        return {"error": e.to_json()}


def test_detected_by_header_set_not_position():
    """Columns in any order, any case, extra columns: still TradingView, and nothing else is."""
    rng = random.Random(1)
    head = list(TV.HEAD)
    row = ["NASDAQ:AAPL", "Buy", "Market", "10", "", "", "230.50", "Filled", "", "2026-09-14 09:31:10",
           "2026-09-14 09:31:10", "1", "", "1:1", ""]
    row2 = list(row)
    row2[1], row2[6], row2[10] = "Sell", "231.50", "2026-09-14 10:00:00"
    for _ in range(20):
        order = list(range(len(head)))
        rng.shuffle(order)
        h = [head[i].upper() if rng.random() < 0.3 else head[i] for i in order] + ["Notes"]
        lines = [",".join(h)] + [",".join([r[i] for i in order] + [""]) for r in (row, row2)]
        res = E.parse_file(("\n".join(lines) + "\n").encode())
        assert res["format"] == "tradingview" and res["verified_format"] is True
        assert [(t["symbol"], t["dir"], t["pnl"], t["hold_s"]) for t in res["trades"]] == [("NASDAQ:AAPL", "long", 10.0, 1730)]
    # The generic template, Tradovate and IBKR files are not taken for TradingView.
    for rel in ("generic/basic.csv", "tradovate/orders.csv", "ibkr/activity_flex.csv", "generic_roundtrip/tradezella.csv"):
        assert E.parse_file(load(rel))["format"] != "tradingview", rel


def test_symbols_kept_whole_and_fills_read_from_whitelist_only():
    res = E.parse_file(load("tradingview/orders.csv"))
    assert {t["symbol"] for t in res["trades"]} >= {"NASDAQ:AAPL", "BINANCE:BTCUSDT", "FX:EURUSD"}
    assert res["tz_label"] == "as exported, with no time zone stated"
    assert set(res["currency_groups"]) == {"points"}
    assert CANARY not in json.dumps(res)
    # Each Filled order is one execution at its Closing time (not the Placing time).
    first = min(res["executions"], key=lambda e: e["ts"])
    assert first["ts"] == E.utc_ms(2026, 9, 14, 9, 31, 10, None, None)
    limit_sell = [e for e in res["executions"] if e["symbol"] == "NASDAQ:AAPL" and e["price"] == 232.0][0]
    assert limit_sell["ts"] == E.utc_ms(2026, 9, 14, 10, 5, 0, None, None)  # placed 09:40, filled 10:05


def test_unknown_format_message_names_tradingview():
    out = subprocess.run(["node", "--input-type=module", "-e",
                          "import('./site/static/js/engine/errors.js').then(m => process.stdout.write(m.MESSAGES.E_UNKNOWN_FORMAT))"],
                         cwd=REPO, capture_output=True, text=True, check=True).stdout
    assert "TradingView Order History export" in out


VARIANTS = [dict(), dict(numbers=True), dict(semicolon=True), dict(bom=True, crlf=True), dict(no_seconds=True),
            dict(numbers=True, bom=True, crlf=True, no_seconds=True), dict(semicolon=True, numbers=True, bom=True)]


@pytest.fixture(scope="module")
def harness(browser, repo_server):
    ctx = browser.new_context(timezone_id="America/Toronto", locale="fr-CA")
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/tests/harness.html")
    page.wait_for_function("document.getElementById('status').textContent === 'ready'")
    yield page
    assert not errors, errors
    ctx.close()


def js(page, fn, data):
    return json.loads(page.evaluate(f"b => window.{fn}(b)", base64.b64encode(data).decode()))


def test_generated_histories_match_reference(harness):
    """Seeded histories in every export variant (Numbers floats, ';' + decimal commas, BOM, CRLF,
    no seconds), with Rejected/Cancelled rows, shorts and partial closes: the browser engine
    gives exactly the reference's ParseResult, stats and noise checks."""
    n = 0
    for seed in range(12):
        for v in VARIANTS:
            data = TV.history(seed, n_trades=8 + seed, **v)
            want = E.run_fixture(data)
            assert "result" in want, (seed, v, want)
            assert want["result"]["format"] == "tradingview"
            diff = same(comparable(js(harness, "runEngine", data)), comparable(want))
            assert not diff, (seed, v, diff)
            n += 1
    assert n == 12 * len(VARIANTS)


def test_variants_give_the_same_trades():
    """The re-saved and localised copies of one history read as the same trades."""
    base = E.parse_file(TV.history(3))["trades"]
    for v in VARIANTS[1:]:
        got = E.parse_file(TV.history(3, **v))["trades"]
        if v.get("no_seconds"):
            assert len(got) == len(base)
            continue
        assert same(got, base) == "", v


def test_bad_cells_fail_with_existing_codes(harness):
    head = ",".join(TV.HEAD)
    good = "NASDAQ:AAPL,Buy,Market,10,,,230.50,Filled,,2026-09-14 09:31:10,2026-09-14 09:31:10,1,,1:1,"
    cases = {
        "slash date": (head + "\n" + good.replace("2026-09-14 09:31:10", "9/14/2026 9:31"), ("E_AMBIGUOUS_DATE", 2, "time")),
        "12h clock": (head + "\n" + good.replace(",2026-09-14 09:31:10,1,", ",2026-09-14 9:31:10 AM,1,"), ("E_BAD_DATE", 2, "time")),
        "empty fill price": (head + "\n" + good.replace(",230.50,", ",,"), ("E_BAD_NUMBER", 2, "price")),
        "commission with an unknown unit": (head + "\n" + good.replace(",Filled,,", ",Filled,1.00 XYZ,"), ("E_BAD_NUMBER", 2, "commission")),
        "price with two symbols": (head + "\n" + good.replace(",230.50,", ",$$230.50,"), ("E_BAD_NUMBER", 2, "price")),
        "header only": (head, ("E_HEADER_ONLY", None, None)),
    }
    for name, (text, want) in cases.items():
        data = (text + "\n").encode()
        got = ref(data)
        assert "error" in got and (got["error"]["code"], got["error"]["row"], got["error"]["column"]) == want, name
        assert same(comparable(js(harness, "parseOnly", data)), comparable(got)) == "", name


def test_only_filled_orders_count():
    head = ",".join(TV.HEAD)
    rows = ["NASDAQ:AAPL,Buy,Market,10,,,230.50,Filled,,t,2026-09-14 09:31:10,1,,,",
            "NASDAQ:AAPL,Sell,Limit,10,240,,,Working,,t,2026-09-14 09:40:00,2,,,",
            "NASDAQ:AAPL,Sell,Limit,10,240,,239.00,Cancelled,,t,2026-09-14 09:41:00,3,,,",
            "NASDAQ:AAPL,Sell,Market,10,,,,Rejected,,t,2026-09-14 09:42:00,4,,,",
            "NASDAQ:AAPL,Sell,Market,10,,,231.50,filled,,t,2026-09-14 10:00:00,5,,,"]
    res = E.parse_file((head + "\n" + "\n".join(rows) + "\n").encode())
    assert res["skipped"] == {"not_filled": 1, "cancelled": 1, "rejected": 1}
    assert [(t["dir"], t["pnl"], t["fills_n"]) for t in res["trades"]] == [("long", 10.0, 2)]


# ------------------------------------------------------------------ round trip: free tool and paid report

def test_trade_stats_tool_reads_tradingview(browser, built_site):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors, requests = [], []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(built_site["url"] + "/tools/trade-stats/")
    page.wait_for_load_state("networkidle")
    page.on("request", lambda r: requests.append(r.url))
    page.set_input_files("#ts-file", os.path.join(FIX, "tradingview", "orders.csv"))
    page.wait_for_selector('#ts-out dd[data-k="n"]', timeout=90000)
    want = E.parse_file(load("tradingview/orders.csv"))
    st = E.free_stats(want["trades"])
    k = lambda key: page.inner_text(f'#ts-out dd[data-k="{key}"]')
    assert k("n") == str(st["n"]) == "10"
    assert k("win_rate") == f"{100 * st['win_rate']:.1f}%"
    assert k("profit_factor") == f"{st['profit_factor']:.2f}"
    out = page.inner_text("#ts-out")
    assert "TradingView Order History export" in out and "(beta)" not in out
    assert "Times are as exported, with no time zone stated." in out
    assert page.locator('#ts-warnings li[data-code="W_SKIPPED_ROWS"]').count() == 1
    assert page.locator('#ts-warnings li[data-code="W_UNVERIFIED_FORMAT"]').count() == 0
    assert CANARY not in page.content()
    assert all(u.startswith(built_site["url"] + "/static/js/") for u in requests), requests
    assert not errors, errors
    ctx.close()


def test_report_rows_match_reference(harness):
    """What the paid report sends: the browser's StrippedRows equal the reference's, and carry
    no symbol or canary."""
    data = load("tradingview/forty_trades.csv")
    got = json.loads(harness.evaluate("([b, s]) => window.stripFixture(b, s)", [base64.b64encode(data).decode(), "SALT-TV"]))
    want = E.strip_rows(E.parse_file(data)["trades"], "SALT-TV")
    assert same(got, want) == ""
    assert len(got["rows"]) == 40
    raw = json.dumps(got)
    for s in ("NASDAQ", "AAPL", "NYSE", "AMEX", "MSFT", CANARY):
        assert s not in raw, s


PRIVATE = os.environ.get("DT_PRIVATE_REPO") or os.path.join(os.path.dirname(REPO), "dt-private")


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    """test_paid_flow's stack (a paid build + the private dev server), built in Stripe test mode so
    it also runs on the live config, where DT_ALLOW_LOCAL_API is refused."""
    import functools
    import http.server
    import threading
    import test_paid_flow as P
    from test_legal import prices_with_test_link, private_with
    site_port, api_port = P.free_port(), P.free_port()
    site_origin, api = f"http://127.0.0.1:{site_port}", f"http://127.0.0.1:{api_port}"
    tmp = tmp_path_factory.mktemp("paid-tv")
    toml = open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()
    toml = toml.replace("paid_report = false", "paid_report = true").replace('mode = "live"', 'mode = "test"')
    import re
    toml = re.sub(r'(?m)^api_base = "[^"]*"', f'api_base = "{api}"', toml)
    (tmp / "site.toml").write_text(toml, encoding="utf-8")
    out = tmp / "site"
    env = {**os.environ, "DT_SITE_TOML": str(tmp / "site.toml"), "DT_OUT": str(out),
           "DT_PRIVATE_TOML": private_with(tmp), "DT_PRICES_JSON": prices_with_test_link(tmp), "DT_ALLOW_LOCAL_API": "1"}
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", site_port), functools.partial(P.Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    dev = subprocess.Popen(["node", "--no-warnings", "src/adapters/dev-server.mjs"], cwd=PRIVATE,
                           env={**os.environ, "DT_FAKE_STRIPE": "1", "DT_PORT": str(api_port),
                                "DT_ALLOWED_ORIGINS": site_origin}, stdout=subprocess.PIPE, text=True)
    assert "dev server on" in dev.stdout.readline()
    yield {"site": site_origin, "api": api}
    dev.terminate()
    srv.shutdown()


@pytest.mark.skipif(not os.path.isdir(PRIVATE), reason="dt-private (server) not present")
def test_paid_report_end_to_end(browser, stack):
    """The $39 report on a TradingView file: the export tip is on /welcome/, the server accepts
    the stripped rows (currency 'points'), and the page shows a report."""
    ctx = browser.new_context()
    page = ctx.new_page()
    import test_paid_flow as P
    sid = P.new_session(page, stack, "cs_test_tradingview0001")
    page.goto(stack["site"] + "/welcome/?session_id=" + sid)
    page.wait_for_selector("#w-ready", state="visible")
    assert "Trading Panel → History → ⋯ → Export data" in page.content()
    page.click("#w-report")
    page.wait_for_url("**/report/")
    assert "TradingView Order History" in page.inner_text("label[for=rp-file]")
    sent = []
    page.on("request", lambda r: sent.append(r))
    page.set_input_files("#rp-file", os.path.join(FIX, "tradingview", "forty_trades.csv"))
    page.wait_for_selector("#focus", timeout=30000)
    analyse = [r for r in sent if r.url.endswith("/analyse")]
    assert len(analyse) == 1
    body = json.loads(analyse[0].post_data)
    assert len(body["rows"]) == 40 and body["currency"] == "points"
    for s in ("NASDAQ", "AAPL", "NYSE", CANARY):
        assert s not in analyse[0].post_data, s
    assert CANARY not in page.content()
    ctx.close()


def test_currency_affixes_strip_like_the_reference(harness):
    """Item 2 (Tester round 1): a code or symbol around a money cell is removed the same way in both engines."""
    cases = ["0.50 USD", "USD 0.50", "$0.50", "-$0.50", "$-0.50", "0,50 €", "usd 1.5", "1.5usd", "-0.50", "", "abc",
             "1 234,50 EUR", "USD", "12 XYZ", "-USD 0.5", "0.5 USDT", "$ 3", "£12", "12¥", "+$1", "CAD-1.25", "1.25 CAD "]
    got = harness.evaluate("""async (xs) => { const m = await import('/site/static/js/engine/tradingview.js');
        return xs.map((x) => m.stripCurrency(x)); }""", cases)
    assert got == [E.strip_currency(x) for x in cases]
    assert got[:5] == ["0.50", "0.50", "0.50", "-0.50", "-0.50"]


def test_missing_column_named_as_exported(harness):
    """Item 5 (Tester round 1): the message names "Closing time", not the internal field "time"."""
    data = load("errors/tradingview_no_closing_time.csv")
    got = js(harness, "parseOnly", data)["error"]
    assert got["column"] == "Closing time" and '"Closing time" was not found' in got["message"], got
    for drop, label in (("Fill price", "Fill price"), ("Quantity", "Quantity"), ("Status", "Status")):
        head = [h for h in TV.HEAD if h != drop]
        text = ",".join(head) + "\n" + ",".join("x" for _ in head) + "\n"
        assert ref(text.encode())["error"]["column"] == label, drop
        assert js(harness, "parseOnly", text.encode())["error"]["column"] == label, drop
