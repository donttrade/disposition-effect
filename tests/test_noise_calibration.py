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
