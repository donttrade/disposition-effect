"""Quick form of batch S3 (the full run is tests/sim_layer2.py; report in research/prediction-study/S3-LAYER2-REPORT.md)."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sim_layer2 as S  # noqa: E402


def test_exclusion_world_reconciles_exactly():
    r = S.replicate(("E", 1000, S.SEED + 999, False, False))
    assert all(r["rec"][k] == v for k, v in r["truth"].items())


def test_lookahead_mutant_is_caught():
    real = S.replicate(("K", 600, S.SEED + 400000, False, False))
    mut = S.replicate(("K", 600, S.SEED + 400000, True, False))
    assert abs(real["auc"] - 0.5) < 0.08 and mut["auc"] > real["auc"] + 0.04


def test_population_shortcut_equals_classify():
    assert S.pop_matches_classify("M", n=400)
