"""Step 5: the Python reference against the hand oracles, and each error fixture's code."""
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, os.path.join(HERE, "fixtures"))
import engine_ref as E  # noqa: E402
from oracles import ERRORS, ORACLES, ORACLES_COUNT_ONLY  # noqa: E402

FIX = os.path.join(HERE, "fixtures")


def load(rel):
    with open(os.path.join(FIX, rel), "rb") as f:
        return f.read()


@pytest.mark.parametrize("rel", sorted(ORACLES))
def test_oracle(rel):
    want = ORACLES[rel]
    got = E.parse_file(load(rel))
    assert len(got["trades"]) == len(want["trades"]), rel
    for g, w in zip(got["trades"], want["trades"]):
        for k, v in w.items():
            if isinstance(v, float) or (isinstance(v, int) and k == "qty"):
                assert math.isclose(g[k], v, rel_tol=1e-9, abs_tol=1e-9), (rel, g["id"], k, g[k], v)
            else:
                assert g[k] == v, (rel, g["id"], k, g[k], v)
    assert {w["code"]: w["n"] for w in got["warnings"]} == want["warnings"], rel
    assert got["skipped"] == want["skipped"], rel


@pytest.mark.parametrize("rel", sorted(ORACLES_COUNT_ONLY))
def test_count_only(rel):
    got = E.parse_file(load(rel))
    assert len(got["trades"]) == ORACLES_COUNT_ONLY[rel]
    assert got["warnings"] == [] and got["skipped"] == {}


@pytest.mark.parametrize("rel", sorted(ERRORS))
def test_error_codes(rel):
    code, row, col = ERRORS[rel]
    with pytest.raises(E.EngineError) as ei:
        E.parse_file(load(rel))
    assert (ei.value.code, ei.value.row, ei.value.column) == (code, row, col)


def test_every_fixture_has_an_oracle():
    covered = set(ORACLES) | set(ERRORS) | set(ORACLES_COUNT_ONLY)
    assert set(E.fixture_paths(FIX)) == covered


def test_canary_never_in_output():
    for rel in E.fixture_paths(FIX):
        res = E.run_fixture(load(rel))
        assert "CANARY" not in repr(res), rel


def test_too_many_rows():
    head = "Date,Time,Symbol,Side,Quantity,Price\n"
    body = "2026-09-01,10:00:00,SPY,Buy,1,500\n" * 200001
    with pytest.raises(E.EngineError) as ei:
        E.parse_file((head + body).encode())
    assert ei.value.code == "E_TOO_LARGE"


def test_number_rules():
    assert E.parse_number("1 234,50") == 1234.5
    assert E.parse_number("1,5") == 1.5
    assert E.parse_number("1,234.5") == 1234.5
    assert E.parse_number("1.234,5") == 1234.5
    assert E.parse_number("−3.5") == -3.5
    for bad in ["1,234", "1,0,0", "$5", "1e5", "--1", "1.2.3"]:
        with pytest.raises(E.EngineError) as ei:
            E.parse_number(bad)
        assert ei.value.code == "E_BAD_NUMBER", bad


def test_number_style_is_decided_per_file():
    # B2: a cell alone cannot say whether "1.500" is 1.5 or 1,500; the rest of the file can.
    def one(qty, price, sep=";"):
        h = sep.join(["Date", "Time", "Symbol", "Side", "Quantity", "Price"])
        rows = [sep.join(["2026-01-05", "09:30:00", "AAA", "Buy", qty, price]),
                sep.join(["2026-01-05", "10:30:00", "AAA", "Sell", qty, price])]
        return E.parse_file(("\n".join([h] + rows) + "\n").encode())["trades"][0]["qty"]
    assert one("1.500", "12,50") == 1500          # decimal commas elsewhere: dot = thousands
    assert one("1.500", "12.5") == 1.5            # decimal points elsewhere: dot = decimal
    assert one("1.500", "12", sep=",") == 1.5     # comma-separated CSV: US style by default
    assert one("1.234.567", "12,5") == 1234567
    assert one("1.234,567", "12,5") == 1234.567   # full European form keeps its decimals
    for qty, price in [("1.500", "12"), ("12,5", "1,234.5")]:
        with pytest.raises(E.EngineError) as ei:
            one(qty, price)
        assert ei.value.code == "E_BAD_NUMBER"


def test_dates_are_naive_utc():
    assert E.parse_date("2026.09.01 09:15:02", "mt", 1, "t") == 1788254102000
    assert E.parse_date("20260902;093512", "ibkr", 1, "t") == E.parse_date("2026-09-02 09:35:12", "ibkr", 1, "t")
    assert E.parse_date("09/15/26 09:31", "tradovate", 1, "t") == E.parse_date("2026-09-15 09:31", "generic", 1, "t")
    for bad, code in [("2026-02-30", "E_BAD_DATE"), ("03/04/2026", "E_AMBIGUOUS_DATE"), ("yesterday", "E_BAD_DATE")]:
        with pytest.raises(E.EngineError) as ei:
            E.parse_date(bad, "generic", 1, "t")
        assert ei.value.code == code


def test_pgr_plr_hand_oracle():
    # tests/fixtures/generic/pgr_oracle.csv, worked by hand:
    # day 2: AAA sold +5 -> realised gain; BBB (avg 49.33 after the add) marked at 48 -> paper loss;
    #        CCC did not trade -> unmarked.            (open position-days 2, marked 1)
    # day 3: BBB sold at 47 < 49.33 -> realised loss; DDD opened short; CCC unmarked; DDD marked at
    #        its own price -> neither.                  (open position-days 2, marked 1)
    # day 4: CCC sold 19 < 20 -> realised loss; DDD covered 29 < 30 short -> realised gain.
    res = E.parse_file(load("generic/pgr_oracle.csv"))
    assert E.pgr_plr_counts(res["executions"]) == {"rg": 2, "pg": 0, "rl": 2, "pl": 1, "coverage_pct": 50.0}
