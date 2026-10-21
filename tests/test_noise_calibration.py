"""Tester D3: on P&L with no edge, the expectancy check says "distinguishable" about 5% of the time.

The plan's sign flip said so 18.8% of the time on 90% +1 / 10% -9 P&L at n = 30 (Tester's
calib2.mjs). checks/calib_expectancy.mjs runs the shipped check on seeded zero-mean files, so
this test is repeatable; the full table (all shapes, n = 30/60/200) is in the fix report.
"""
import json
import os
import subprocess

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def rates(files, ns, shapes):
    out = subprocess.run(["node", "checks/calib_expectancy.mjs", str(files), ns, shapes], cwd=REPO,
                         capture_output=True, text=True, check=True, timeout=300)
    return json.loads(out.stdout)


def test_skewed_zero_edge_pnl_is_not_called_real_too_often():
    r = rates(300, "30", "skew_90_10,normal")
    assert r["skew_90_10/n=30"] < 0.10, r       # sign flip: ~0.19
    assert 0.02 <= r["normal/n=30"] <= 0.09, r  # still a 5% test on symmetric P&L


def test_trend_follower_zero_edge_at_n30_is_guarded():
    """Tester F-D1 / amendment section 9: the trend follower at n = 30 read 9.4% before the guard."""
    out = subprocess.run(["node", "checks/calib_expectancy.mjs", "300", "30", "trend_right_skew", "7", "--mirror"],
                         cwd=REPO, capture_output=True, text=True, check=True, timeout=300)
    r = json.loads(out.stdout)
    assert r["trend_right_skew/n=30"] < 0.065, r
    assert r["mirror_diffs"] == 0, r   # F-5: negating every P&L gives the same label, guard and n_needed


def test_free_guard_invariants_fast():
    """Amendment section 8, F-1 to F-5 at CI size (checks/calib_free.mjs; --slow is the full grid)."""
    out = subprocess.run(["node", "checks/calib_free.mjs"], cwd=REPO, capture_output=True, text=True, timeout=600)
    r = json.loads(out.stdout)
    assert out.returncode == 0 and not r["fails"], r["fails"]
    assert r["f2"]["pooled"]["distinguishable"] <= 5.0, r["f2"]["pooled"]
    for n in ("n=30", "n=60", "n=200"):
        assert r["f1"][n]["distinguishable"] <= 6.5, r["f1"]
    assert r["props"]["guards"]["skew_small_n"] > 0 and r["props"]["guards"]["skew_one_more"] > 0, r["props"]
