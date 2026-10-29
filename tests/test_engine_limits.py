"""Steps 7–8: size limits and privacy checks for the JS engine in Chromium."""
import base64
import json
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")


@pytest.fixture(scope="module")
def page(browser, repo_server):
    ctx = browser.new_context()
    pg = ctx.new_page()
    console = []
    pg.on("console", lambda m: console.append(m.text))
    pg.goto(repo_server + "/tests/harness.html")
    pg.wait_for_function("document.getElementById('status').textContent === 'ready'")
    yield pg, console
    ctx.close()


def generic_file(n_rows):
    lines = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    for i in range(n_rows):
        day = 1 + (i // 20000)
        sec = i % 20000
        side = "Buy" if i % 2 == 0 else "Sell"
        price = 100 + (i % 7) * 0.25
        lines.append(f"2026-09-{day:02d},{sec // 3600 + 1:02d}:{(sec // 60) % 60:02d}:{sec % 60:02d},"
                     f"S{i % 13},{side},1,{price:.2f},USD,0.10")
    return ("\n".join(lines) + "\n").encode()


def run_timed(pg, data):
    return json.loads(pg.evaluate("b => window.runEngineTimed(b)", base64.b64encode(data).decode()))


def test_100k_rows_completes(page):
    pg, _ = page
    r = run_timed(pg, generic_file(100000))
    assert r["error"] is None, r
    assert r["trades"] > 0
    print(f"\n100,000-row generic file: {r['ms']:.0f} ms in Chromium, {r['trades']} trades")


def test_200001_rows_too_large(page):
    pg, _ = page
    r = run_timed(pg, generic_file(200001))
    assert r["error"]["code"] == "E_TOO_LARGE"


def test_50mb_too_large(page):
    pg, _ = page
    data = b"Date,Time,Symbol,Side,Quantity,Price\n" + b" " * (50 * 1024 * 1024)
    r = run_timed(pg, data)
    assert r["error"]["code"] == "E_TOO_LARGE"


def test_hedging_fixture_warns(page):
    pg, _ = page
    with open(os.path.join(FIX, "mt5/deals_hedging.htm"), "rb") as f:
        res = json.loads(pg.evaluate("b => window.runEngine(b)", base64.b64encode(f.read()).decode()))
    assert [w["code"] for w in res["result"]["warnings"]] == ["W_UNVERIFIED_FORMAT", "W_SKIPPED_ROWS", "W_HEDGING"]


def test_canary_absent_from_output_and_console(page):
    pg, console = page
    for d in ("mt5", "mt4", "ibkr", "tradovate", "tradingview"):
        for name in sorted(os.listdir(os.path.join(FIX, d))):
            with open(os.path.join(FIX, d, name), "rb") as f:
                out = pg.evaluate("b => window.runEngine(b)", base64.b64encode(f.read()).decode())
            assert "CANARY" not in out, name
    assert not any("CANARY" in c for c in console)
    assert pg.evaluate("localStorage.length + sessionStorage.length") == 0
