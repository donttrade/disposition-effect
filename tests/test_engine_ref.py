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


def test_dates_are_naive_utc():
    assert E.parse_date("2026.09.01 09:15:02", "mt", 1, "t") == 1788254102000
    assert E.parse_date("20260902;093512", "ibkr", 1, "t") == E.parse_date("2026-09-02 09:35:12", "ibkr", 1, "t")
    assert E.parse_date("09/15/26 09:31", "tradovate", 1, "t") == E.parse_date("2026-09-15 09:31", "generic", 1, "t")
    for bad, code in [("2026-02-30", "E_BAD_DATE"), ("03/04/2026", "E_AMBIGUOUS_DATE"), ("yesterday", "E_BAD_DATE")]:
        with pytest.raises(E.EngineError) as ei:
            E.parse_date(bad, "generic", 1, "t")
        assert ei.value.code == code
