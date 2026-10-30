#!/usr/bin/env python3
"""Batch S2: Layer 1 synthetic check of the metrics alone (ARCHITECT-PREDICTION-STUDY-2026-10-30 section 5.1).

Breached accounts' scores ~ N(delta, 1), survivors' ~ N(0, 1), so the true AUC = Phi(delta / sqrt 2).
For each true AUC and each sample size, R replications: mean AUC bias, 95% CI coverage, and the H1 pass
rate (the lower 95% bound above 0.55).

Usage (Claude Code or plain Terminal, from the repo root):
  python3 tests/sim_layer1.py            # R = 2000, prints the markdown table
  python3 tests/sim_layer1.py --reps 200
"""
import argparse
import math
import os
import random
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "partner"))
import prediction_metrics as M  # noqa: E402

DELTAS = {0.50: 0.0, 0.55: 0.1777, 0.60: 0.3583, 0.65: 0.5449, 0.70: 0.7416, 0.75: 0.9539}
SIZES = (100, 200, 400)
SEED = 20261030
PASS_LOWER = 0.55


def true_auc(delta):
    return M.norm_cdf(delta / math.sqrt(2.0))


def run_cell(target, n, reps, seed):
    delta = DELTAS[target]
    truth = true_auc(delta)
    rng = random.Random(seed)
    s_auc = 0.0
    cover = passes = 0
    for _ in range(reps):
        pos = [rng.gauss(delta, 1.0) for _ in range(n)]
        neg = [rng.gauss(0.0, 1.0) for _ in range(n)]
        r = M.auc_delong(pos + neg, [1] * n + [0] * n)
        s_auc += r["auc"]
        cover += r["lo"] <= truth <= r["hi"]
        passes += r["lo"] > PASS_LOWER
    return {"target": target, "truth": truth, "n": n, "reps": reps, "bias": s_auc / reps - truth,
            "coverage": cover / reps, "pass": passes / reps,
            "hm_power": 1 - M.norm_cdf((PASS_LOWER - truth) / M.hanley_mcneil_se(truth, n, n) + M.Z975)}


def run(reps):
    out = []
    for i, target in enumerate(sorted(DELTAS)):
        for j, n in enumerate(SIZES):
            out.append(run_cell(target, n, reps, SEED + 100 * i + j))
    return out


CONFIRM_REPS = 20000


def confirm_power(reps=CONFIRM_REPS):
    """The 0.65, 200/200 power cell again with R = 20,000 (two seeds of 10,000): the measured figure that
    replaces the Hanley-McNeil 95.6% in section 2.8 (Monte Carlo SE about 0.0015)."""
    a = run_cell(0.65, 200, reps // 2, SEED + 9001)
    b = run_cell(0.65, 200, reps // 2, SEED + 9002)
    return (a["pass"] + b["pass"]) / 2


def acceptance(rows, reps, confirmed=None):
    """The section 5.1 acceptance rules, as written there. Returns a list of (rule, ok)."""
    res = []
    res.append(("mean AUC bias below 0.003 in every cell", all(abs(r["bias"]) < 0.003 for r in rows)))
    res.append(("95% CI coverage between 93.9% and 96.1% in every cell",
                all(0.939 <= r["coverage"] <= 0.961 for r in rows)))
    at55 = [r for r in rows if r["target"] == 0.55]
    res.append(("H1 pass rate at true AUC 0.55 below 3.6% (expected 2.5%)", all(r["pass"] < 0.036 for r in at55)))
    p65 = [r for r in rows if r["target"] == 0.65 and r["n"] == 200][0]
    res.append(("H1 pass rate at 0.65, 200/200, inside 95.6%% +/- 1.5 points (R = %d: %.1f%%)"
                % (reps, 100 * p65["pass"]), abs(p65["pass"] - 0.956) <= 0.015))
    if confirmed is not None:
        res.append(("the same cell at R = %d: %.1f%% (inside 95.6%% +/- 1.5 points)"
                    % (CONFIRM_REPS, 100 * confirmed), abs(confirmed - 0.956) <= 0.015))
    return res


def table(rows, reps, confirmed=None):
    lines = ["| True AUC | Per class | Mean AUC | Bias | 95% CI coverage | H1 pass rate | Hanley-McNeil power |",
             "|---|---|---|---|---|---|---|"]
    for r in rows:
        lines.append("| %.2f | %d | %.4f | %+.4f | %.3f | %.3f | %.3f |" % (
            r["target"], r["n"], r["truth"] + r["bias"], r["bias"], r["coverage"], r["pass"], r["hm_power"]))
    lines.append("")
    lines.append("R = %d replications per cell, seed base %d." % (reps, SEED))
    lines.append("")
    for rule, ok in acceptance(rows, reps, confirmed):
        lines.append("- %s: **%s**" % (rule, "met" if ok else "NOT MET"))
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=2000)
    ap.add_argument("--confirm", action="store_true", help="also re-run the 0.65, 200/200 cell at R = 20,000")
    a = ap.parse_args()
    t = time.time()
    rows = run(a.reps)
    sys.stdout.write(table(rows, a.reps, confirm_power() if a.confirm else None))
    sys.stdout.write("\nRun time %.0f s.\n" % (time.time() - t))
