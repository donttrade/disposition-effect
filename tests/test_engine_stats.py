"""Step 9: FreeStats and noise checks — hand oracles, worker parity, no NaN/Infinity."""
import base64
import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "reference"))
import engine_ref as E  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def load(rel):
    with open(os.path.join(FIX, rel), "rb") as f:
        return f.read()


def test_stats_hand_oracle():
    # short_reversal_adds: pnls in close order 18, 4, 7 (all wins)
    s = E.free_stats(E.parse_file(load("generic/short_reversal_adds.csv"))["trades"], 1000)
    assert (s["n"], s["wins"], s["losses"], s["scratch"]) == (3, 3, 0, 0)
    assert s["profit_factor"] == "no losing trades"
    assert s["expectancy"] == pytest.approx(29 / 3)
    assert s["max_consec_wins"]["n"] == 3 and s["max_consec_wins"]["pnl"] == pytest.approx(29.0)
    assert s["max_drawdown_abs"] == 0 and s["max_drawdown_pct"] == 0
    # mixed_currency USD trades: +50 then -10 -> drawdown 10; on a 1000 balance 10/1050
    s = E.free_stats(E.parse_file(load("generic/mixed_currency.csv"))["trades"], 1000)
    assert s["max_drawdown_abs"] == 10 and s["max_drawdown_pct"] == pytest.approx(10 / 1050)
    assert s["profit_factor"] == 5.0 and s["win_rate"] == 0.5


def test_permutation_reference_properties():
    r = E.run_fixture(load("generic/ninety_trades.csv"))
    for c in r["noise"]["checks"]:
        assert c["p"] is not None and 1 / (E.N_PERM + 1) <= c["p"] <= 1
    small = E.run_fixture(load("generic/basic.csv"))
    assert {c["label"] for c in small["noise"]["checks"]} == {"not enough trades to tell"}


def test_prng_matches_known_js_values():
    r = E.mulberry32(20261022)
    assert [r() for _ in range(3)] == [0.5591592639684677, 0.21883013984188437, 0.5584872781764716]


@pytest.fixture(scope="module")
def page(browser, repo_server):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(repo_server + "/tests/harness.html")
    pg.wait_for_function("document.getElementById('status').textContent === 'ready'")
    yield pg
    ctx.close()


def b64(rel):
    return base64.b64encode(load(rel)).decode()


def test_worker_equals_reference(page):
    rel = "generic/ninety_trades.csv"
    got = json.loads(page.evaluate("b => window.runNoiseInWorker(b)", b64(rel)))
    want = E.run_fixture(load(rel))["noise"]
    assert [c["p"] for c in got["checks"]] == [c["p"] for c in want["checks"]]
    assert [c["label"] for c in got["checks"]] == [c["label"] for c in want["checks"]]


def test_starting_balance_pct_matches(page):
    rel = "generic/ninety_trades.csv"
    got = json.loads(page.evaluate("([b, x]) => window.statsWithBalance(b, x)", [b64(rel), 25000]))
    want = E.free_stats(E.parse_file(load(rel))["trades"], 25000)
    assert math.isclose(got["max_drawdown_pct"], want["max_drawdown_pct"], rel_tol=1e-9)


def test_no_nan_infinity_undefined(page):
    for rel in E.fixture_paths(FIX):
        out = page.evaluate("b => window.runEngine(b)", b64(rel))
        for bad in ("NaN", "Infinity", "undefined"):
            assert bad not in out, (rel, bad)


def test_quickselect_median_equals_sorted_median():
    """noise.js uses quickselect for speed; it must give the sort-based median on any input."""
    import subprocess
    code = r"""
import('./site/static/js/engine/noise.js').then(({ median, mulberry32 }) => {
  const r = mulberry32(7);
  for (let k = 0; k < 3000; k++) {
    const n = 1 + Math.floor(r() * 60);
    const xs = Array.from({ length: n }, () => Math.floor(r() * (k % 3 ? 10 : 1000)));
    const s = xs.slice().sort((a, b) => a - b);
    const want = n % 2 ? s[n >> 1] : (s[(n >> 1) - 1] + s[n >> 1]) / 2;
    if (median(xs) !== want) { console.log('MISMATCH', JSON.stringify(xs)); process.exit(1); }
  }
  console.log('ok');
});"""
    out = subprocess.run(["node", "--input-type=module", "-e", code], cwd=os.path.dirname(HERE),
                         capture_output=True, text=True)
    assert out.stdout.strip() == "ok", out.stdout + out.stderr
