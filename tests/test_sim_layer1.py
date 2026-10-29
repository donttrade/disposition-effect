"""Quick form of batch S2 (the full run is tests/sim_layer1.py --reps 2000 --confirm; report in
research/prediction-study/S2-LAYER1-REPORT.md)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_layer1 as L  # noqa: E402


def test_layer1_quick():
    null = L.run_cell(0.55, 200, 400, 11)
    tgt = L.run_cell(0.65, 200, 400, 12)
    assert abs(null["bias"]) < 0.006 and abs(tgt["bias"]) < 0.006
    assert null["pass"] < 0.06
    assert 0.90 < tgt["pass"] < 0.99
    assert 0.92 < tgt["coverage"] < 0.98
