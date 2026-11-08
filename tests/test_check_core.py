"""The free check's counting module (ARCHITECT-PLAN-FREE-CHECK-AND-HOOK-2026-11-07, batch C1; fixtures from batch C0).

What is held here:
  * site/static/js/check-core.js gives, for every trade list in tests/fixtures/check_parity/make_inputs.mjs, exactly the
    counts the report server's analyse() gives (the committed tests/fixtures/check_parity/*.json, made by dt2-private
    tools/export_check_fixtures.mjs): n_rows, n_trades, dates_only and per habit n_a, n_b and the size of the set the report
    totals. The fixtures hold nothing else: no p-value, no amount, no verdict, no row;
  * hand-worked cases for the merge, the 15-minute window, the loss run, the 30-trade minimum and the dates-only 5% edge;
  * paid/strip.js: stripRows output is byte-identical to before toRows was extracted (sha256 recorded from b2ca2e9), and
    toRows gives the same rows without f;
  * the module exports no test against chance, verdict or money function; its result holds whole numbers of trades only,
    is unchanged when every amount is scaled, and it has no DOM, network or storage; at most 4 KB gzip.
"""
import glob
import gzip
import json
import os
import re
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
RUN = os.path.join(HERE, "reference", "check_core_run.mjs")
FIX = os.path.join(HERE, "fixtures", "check_parity")
CORE = os.path.join(REPO, "site", "static", "js", "check-core.js")
HABITS = ["hold_gap", "revenge", "size_up", "tilt", "oversized_loss"]
FILES = sorted(glob.glob(os.path.join(FIX, "*.json")))


def node(mode, stdin=None):
    r = subprocess.run(["node", RUN, mode], input=stdin, capture_output=True, text=True, cwd=REPO)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


@pytest.fixture(scope="module")
def counted():
    return node("fixtures")


# ---------------------------------------------------------------- C0: the fixtures

def test_there_are_at_least_8_fixtures_for_the_named_cases():
    names = {os.path.basename(f)[:-5] for f in FILES}
    assert len(names) >= 8
    for want in ["plain", "partial_fills_merge", "overlapping_trades", "dates_only", "fewer_than_30_groups", "zero_losses",
                 "cap_20000_rows", "multi_symbol_size", "real_public_data"]:
        assert want in names, want


@pytest.mark.parametrize("path", FILES, ids=lambda p: os.path.basename(p))
def test_fixture_holds_only_counts(path):
    raw = open(path, encoding="utf-8").read()
    d = json.loads(raw)
    assert sorted(d) == ["dates_only", "fixture", "habits", "method_version", "n_rows", "n_trades"]
    assert d["fixture"] == os.path.basename(path)[:-5] and d["method_version"] == "2026-10-23.stats2f"
    assert isinstance(d["dates_only"], bool) and type(d["n_rows"]) is int and type(d["n_trades"]) is int
    assert sorted(d["habits"]) == sorted(HABITS)
    for h in d["habits"].values():
        assert sorted(h) == ["dollars", "n_a", "n_b"] and type(h["n_a"]) is int and type(h["n_b"]) is int
        assert h["dollars"] is None or (sorted(h["dollars"]) == ["n_trades"] and type(h["dollars"]["n_trades"]) is int)
    assert not re.search(r"\d\.\d", raw), "a decimal number in a fixture"        # no p-value, no amount
    assert not re.search(r"p_raw|p_holm|verdict|amount|measure|effect", raw)


def test_fixtures_cover_the_edges():
    f = {os.path.basename(p)[:-5]: json.load(open(p)) for p in FILES}
    assert f["partial_fills_merge"]["n_rows"] > f["partial_fills_merge"]["n_trades"]     # rows merged
    assert f["plain"]["n_rows"] == f["plain"]["n_trades"]
    assert f["dates_only"]["dates_only"] and f["dates_only"]["n_rows"] == f["dates_only"]["n_trades"]
    assert not f["dates_mixed_4_of_100"]["dates_only"] and f["dates_mixed_5_of_100"]["dates_only"]    # the 5% edge
    z = f["zero_losses"]["habits"]
    assert z["hold_gap"]["n_a"] == 0 and z["revenge"]["n_a"] == 0 and z["oversized_loss"]["n_b"] == 0
    few = f["fewer_than_30_groups"]["habits"]
    assert f["fewer_than_30_groups"]["n_rows"] >= 30 and min(few["revenge"]["n_a"], few["revenge"]["n_b"]) < 30
    assert f["cap_20000_rows"]["n_rows"] == 20000
    assert len({h["n_a"] for h in f["multi_symbol_size"]["habits"].values()}) > 1
    assert f["real_public_data"]["n_rows"] == 64


# ---------------------------------------------------------------- C1: counts equal the server's

@pytest.mark.parametrize("path", FILES, ids=lambda p: os.path.basename(p))
def test_counts_equal_the_server_fixture(path, counted):
    exp = json.load(open(path))
    got = counted[exp["fixture"]]
    assert (got["n_rows"], got["n_trades"], got["dates_only"]) == (exp["n_rows"], exp["n_trades"], exp["dates_only"])
    assert got["n_merged"] == exp["n_rows"] - exp["n_trades"]
    for hid in HABITS:
        e, g = exp["habits"][hid], got["habits"][hid]
        assert (g["n_a"], g["n_b"]) == (e["n_a"], e["n_b"]), hid
        assert g["n_set"] == (None if e["dollars"] is None else e["dollars"]["n_trades"]), hid
        assert g["enough"] == (min(e["n_a"], e["n_b"]) >= 30), hid


def test_no_fixture_is_missing_a_counted_list(counted):
    assert sorted(counted) == sorted(os.path.basename(p)[:-5] for p in FILES)


def test_cap_span_and_testable(counted):
    assert counted["cap_20000_rows"]["limited"] and counted["cap_20000_rows"]["n_rows"] == 20000
    assert counted["span_trim_519_weeks"]["span_left_out"] > 0 and not counted["span_trim_519_weeks"]["limited"]
    assert counted["plain"]["testable"] == ["revenge", "tilt"]
    assert counted["dates_only"]["testable"] == [] and counted["dates_mixed_5_of_100"]["testable"] == []
    assert counted["fewer_than_30_groups"]["testable"] == [] and counted["zero_losses"]["testable"] == []
    assert counted["real_public_data"]["testable"] == []


def row(o, h, p, s=0, d=1, q=1):
    return {"o": o, "h": h, "d": d, "q": q, "p": p, "s": s}


def test_hand_worked_cases():
    # A loses (closes at second 600). B opens at second 900, exactly 300 s after it: a re-entry. C opens 2 h later.
    a, b, c = row(0, 600, -5), row(15, 300, 3, s=1), row(180, 60, 2, s=1)
    r = node("rows", json.dumps({"cases": [[a, b, c]]}))[0]
    assert (r["n_rows"], r["n_trades"], r["n_merged"]) == (3, 3, 0)
    assert (r["habits"]["revenge"]["n_a"], r["habits"]["revenge"]["n_b"]) == (1, 1)     # B hit; C not; the first trade is left out
    # exactly 15 minutes after the close counts; 15 minutes and 1 second does not (o is in whole minutes: 10 + 15 = 25)
    r = node("rows", json.dumps({"cases": [[row(0, 600, -5), row(25, 60, 1, s=1)], [row(0, 600, -5), row(26, 60, 1, s=1)]]}))
    assert r[0]["habits"]["revenge"]["n_a"] == 1 and r[1]["habits"]["revenge"]["n_a"] == 0
    # same symbol, direction and open minute: one trade, p summed in cents (+5.10 and -8.20 -> -3.10 is a loss)
    m = [row(10, 300, 5.1, q=1), row(10, 400, -8.2, q=2), row(60, 60, 1), row(120, 60, 1)]
    r = node("rows", json.dumps({"cases": [m]}))[0]
    assert (r["n_rows"], r["n_trades"], r["n_merged"]) == (4, 3, 1)
    assert r["habits"]["hold_gap"]["n_a"] == 1 and r["habits"]["hold_gap"]["n_b"] == 2
    # a win and a loss that cancel to 0.00 is neither
    z = node("rows", json.dumps({"cases": [[row(10, 300, 5), row(10, 300, -5), row(60, 60, 1)]]}))[0]
    assert z["habits"]["hold_gap"]["n_a"] == 0 and z["habits"]["hold_gap"]["n_b"] == 1
    # tilt: two losses in a row, then a trade opened after the second one closes
    t = [row(0, 60, -1), row(10, 60, -1), row(30, 60, 4)]
    r = node("rows", json.dumps({"cases": [t]}))[0]
    assert (r["habits"]["tilt"]["n_a"], r["habits"]["tilt"]["n_b"]) == (1, 1)
    # empty file
    e = node("rows", json.dumps({"cases": [[]]}))[0]
    assert e["n_rows"] == 0 and e["n_trades"] == 0 and not e["dates_only"] and e["below_min_rows"] is True


def test_dates_only_edge_is_5_percent_and_date_only_rows_never_merge():
    d = lambda k: row(1440 * k, 86400, 1 + k * 0.01, s=0)         # noqa: E731  (open 00:00, held a whole day)
    timed = lambda k: row(1440 * k + 600, 300, 1, s=1)            # noqa: E731
    r19 = [d(i) for i in range(1)] + [timed(i) for i in range(19)]      # 1 of 20 = 5%
    r20 = [d(i) for i in range(1)] + [timed(i) for i in range(20)]      # 1 of 21 < 5%
    a, b = node("rows", json.dumps({"cases": [r19, r20]}))
    assert a["dates_only"] is True and b["dates_only"] is False
    same = [row(0, 86400, 1), row(0, 86400, 2)] + [timed(i + 5) for i in range(30)]   # two date-only rows, one open minute
    r = node("rows", json.dumps({"cases": [same]}))[0]
    assert r["n_merged"] == 0, "date-only rows are not merged"


# ---------------------------------------------------------------- the strip.js refactor

GOLDEN = dict(re.match(r"(\S+ \S+) ([0-9a-f]{64})$", ln).groups() for ln in open(os.path.join(FIX, "strip_golden.txt")) if not ln.startswith("#") and ln.strip())


def test_stripRows_is_byte_identical_to_before_the_refactor():
    got = node("strip")
    assert len(GOLDEN) >= 16 and got == GOLDEN


def test_toRows_has_no_fingerprint_and_matches_stripRows():
    out = node("torows")
    for name, o in out.items():
        assert o["keys"] == ["d", "h", "o", "p", "q", "s"] and o["key_order"] == "ohdqps", name
        assert o["same_as_strip"], name


# ---------------------------------------------------------------- counting only

FORBID_NAME = re.compile(r"(^|_)(p|pval|pvalue|verdict|dollar|dollars|money|amount|cost|usd|pnl|holm|perm|shuffle|chance|luck|total|mean|sum|effect)(_|$)", re.I)


def test_exports_hold_no_test_verdict_or_money():
    ex = node("exports")
    assert ex["names"] == ["HABIT_IDS", "MIN_GROUP", "MIN_ROWS", "countRows", "countTrades"]
    assert not [n for n in ex["names"] if FORBID_NAME.search(n)]
    assert {k for k, t in ex["types"].items() if t == "function"} == {"countRows", "countTrades"}


def walk(x, path=""):
    if isinstance(x, dict):
        for k, v in x.items():
            assert not FORBID_NAME.search(k), path + "/" + k
            yield from walk(v, path + "/" + k)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from walk(v, path)
    else:
        yield path, x


def test_results_hold_whole_numbers_booleans_and_names_only(counted):
    for name, res in counted.items():
        for path, v in walk(res, name):
            assert v is None or isinstance(v, (bool, int, str)), (path, v)
            if isinstance(v, str):
                assert v in HABITS, (path, v)
            assert not isinstance(v, float), (path, v)


def test_counts_do_not_move_when_every_amount_is_scaled():
    # Money cannot be in the result if scaling every P&L changes nothing in it.
    import random
    rnd = random.Random(5)
    rows = [row(i * 40 + rnd.randint(0, 20), rnd.randint(60, 1500), round(rnd.uniform(-50, 50), 2), s=rnd.randint(0, 2), d=rnd.choice([1, -1]),
                q=rnd.choice([1, 1.5, 2])) for i in range(300)]
    scaled = [dict(r, p=round(r["p"] * 1000, 2)) for r in rows]
    a, b = node("rows", json.dumps({"cases": [rows, scaled]}))
    assert a == b


def test_source_has_no_test_verdict_money_dom_network_or_storage():
    src = open(CORE, encoding="utf-8").read()
    code = re.sub(r"//[^\n]*", "", src)
    assert not re.search(r"\b(document|window|fetch|XMLHttpRequest|localStorage|sessionStorage|indexedDB|navigator|Math\.random|crypto)\b", code)
    assert not re.search(r"verdict|p_raw|p_holm|holm|labelPermutation|shuffle|mulberry|permut|noise\.js|\.amount|dollars", code, re.I)
    assert re.findall(r"^import .*$", code, re.M) == ["import { toRows } from './paid/strip.js';"]


def test_size_at_most_4_kb_gzip():
    assert len(gzip.compress(open(CORE, "rb").read(), 9)) <= 4096
