"""Batch F3: partner/dt1_outcomes.py. The golden file against prop-sim-core.js (public check), the live
re-check when the readiness checkout is present, and hand-worked censoring, pass and headroom cases."""
import json
import os
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "partner"))
sys.path.insert(0, os.path.join(HERE, "parity"))
import dt1_outcomes as O  # noqa: E402

GOLDEN = os.path.join(REPO, "partner", "parity", "rules_golden.json")
READINESS = os.environ.get("DT_READINESS_RO", os.path.join(REPO, "..", "readiness"))
D = 86400
T0 = 20000 * D          # a UTC midnight


def test_golden_replay_matches_prop_sim_core():
    with open(GOLDEN, encoding="utf-8") as fh:
        g = json.load(fh)
    assert len(g["sequences"]) >= 100
    for s in g["sequences"]:
        r = s["rules"]
        x = O.replay(s["days"], r["daily_loss"], r["max_loss"], r["drawdown"], r["trail_stop_at"])
        e = s["expected"]
        assert (x["outcome"], x["why"], x["day"]) == (e["outcome"], e["why"], e["day"]), s["id"]
        assert ([[x["at"][0], x["at"][1], 1]] if x["at"] else []) == e["bust_at"], s["id"]


@pytest.mark.skipif(not (os.path.isdir(os.path.join(READINESS, "tests", "reference")) and shutil.which("node")),
                    reason="readiness checkout or node not present")
def test_live_rules_parity():
    import build_rules_golden as B
    _seqs, _js, bad = B.check(READINESS)
    assert bad == []


# ------------------------------------------------------------ firm mode

def acc(outcome, ot, end):
    return {"outcome": outcome, "outcome_time": ot, "data_end": end}


def test_firm_breach_inside_window_is_1():
    assert O.firm_label(acc("daily", T0 + 5 * D, T0 + 5 * D), T0, 30)["o1"] == 1
    assert O.firm_label(acc("max", T0 + 30 * D, T0 + 30 * D), T0, 30)["o1"] == 1      # the window is closed at the end


def test_firm_breach_after_window_is_0():
    assert O.firm_label(acc("max", T0 + 30 * D + 1, T0 + 40 * D), T0, 30)["o1"] == 0


def test_firm_passed_inside_window_is_0():
    r = O.firm_label(acc("passed", T0 + 3 * D, T0 + 3 * D), T0, 30)
    assert r == {"o1": 0, "o3": 0}


def test_firm_censoring():
    assert O.firm_label(acc("active", None, T0 + 29 * D), T0, 30)["o1"] is None          # data end early
    assert O.firm_label(acc("closed_no_breach", T0 + 2 * D, T0 + 2 * D), T0, 30)["o1"] is None
    assert O.firm_label(acc("other_rule", T0 + 2 * D, T0 + 2 * D), T0, 30) == {"o1": None, "o3": 1}
    assert O.firm_label(acc("active", None, T0 + 30 * D), T0, 30) == {"o1": 0, "o3": None}


# ------------------------------------------------------------ rule mode

def tr(day, sec, pnl):
    return {"close_s": T0 + day * D + sec, "pnl": pnl}


def test_rule_daily_breach_and_o2():
    after = [tr(1, 100, -20.0), tr(1, 200, -31.0)]       # -51 in one day on 1,000: daily 50 is broken
    r = O.rule_label(after, T0, 30, 1000.0, T0 + 31 * D, 0)
    assert r["o1"] == 1 and r["why"] == "daily" and r["o2"] == 0


def test_rule_max_breach_across_days_and_censoring():
    after = [tr(d, 100, -40.0) for d in range(1, 4)]      # -120 over three days: max loss 100 broken on day 3
    assert O.rule_label(after, T0, 30, 1000.0, T0 + 31 * D, 0)["why"] == "max"
    calm = [tr(1, 100, 5.0)]
    assert O.rule_label(calm, T0, 30, 1000.0, T0 + 10 * D, 0)["o1"] is None
    assert O.rule_label(calm, T0, 30, 1000.0, T0 + 30 * D, 0)["o1"] == 0


def test_rule_ignores_trades_at_or_before_t0_and_after_window():
    after = [{"close_s": T0, "pnl": -500.0}, {"close_s": T0 + 30 * D + 1, "pnl": -500.0}]
    assert O.rule_label(after, T0, 30, 1000.0, T0 + 40 * D, 0)["o1"] == 0


def test_o2_fifty_percent_from_peak():
    after = [tr(1, 1, 1.0), tr(2, 1, -0.3), tr(3, 1, -0.3), tr(4, 1, -0.31)]    # peak 2.0, then 1.09
    r = O.rule_label(after, T0, 30, 1.0, T0 + 31 * D, 0)
    assert r["o2"] == 0
    after.append(tr(5, 1, -0.1))          # 2.0 -> 0.99: 50.5% below the peak
    assert O.rule_label(after, T0, 30, 1.0, T0 + 31 * D, 0)["o2"] == 1


def test_day_boundary_uses_day_start():
    # two losses 2 hours apart, either side of 17:00: one day with day_start 00:00, two days with 17:00
    a = {"close_s": T0 + D + 16 * 3600, "pnl": -30.0}
    b = {"close_s": T0 + D + 18 * 3600, "pnl": -30.0}
    assert O.rule_label([a, b], T0, 30, 1000.0, T0 + 31 * D, 0)["why"] == "daily"
    assert O.rule_label([a, b], T0, 30, 1000.0, T0 + 31 * D, 17 * 3600)["o1"] == 0


# ------------------------------------------------------------ headroom

def test_headroom_static_and_trailing():
    w = [tr(0, 100, 30.0), tr(1, 100, -10.0)]
    assert O.headroom(w, 100.0, "static", None, 0) == pytest.approx((20 + 100) / 100)
    # trailing EOD: peak 30 after day 0, floor -70, equity 20 -> 0.9
    assert O.headroom(w, 100.0, "trailing_eod", None, 0) == pytest.approx(0.9)
    # with the trail stopping at 0 (break-even): floor min(peak - 100, 0) -> -70 still
    assert O.headroom(w, 100.0, "trailing_eod", 0.0, 0) == pytest.approx(0.9)
    w2 = [tr(0, 100, 150.0)]
    assert O.headroom(w2, 100.0, "trailing_eod", 0.0, 0) == pytest.approx(1.5)   # floor stops at 0
