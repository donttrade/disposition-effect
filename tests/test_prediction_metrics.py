"""Batch S1: partner/prediction_metrics.py against numpy / scipy / scikit-learn (dev-only; the firm script
never imports them) on 50 seeded random fixtures, plus the Hanley-McNeil (1982) worked example."""
import math
import os
import random
import sys

import numpy as np
import pytest
from scipy import stats
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import roc_auc_score

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "partner"))
import prediction_metrics as M  # noqa: E402

SEEDS = list(range(50))


def fixture(seed, n=None, ties=False):
    rng = random.Random(1000 + seed)
    n = n or rng.randint(40, 400)
    y = [1 if rng.random() < rng.uniform(0.15, 0.6) else 0 for _ in range(n)]
    if sum(y) < 3:
        y[:3] = [1, 1, 1]
    if n - sum(y) < 3:
        y[-3:] = [0, 0, 0]
    x = [[rng.gauss(0, 1) + 0.6 * t * (j == 0), rng.gauss(0, 2), rng.uniform(-1, 1)] for j, t in
         ((0, t) for t in y)]
    s = [round(r[0], 1) if ties else r[0] for r in x]
    return x, y, s


def np_delong(score, y):
    """Independent DeLong (Sun & Xu 2014 fast form) in numpy."""
    s = np.asarray(score, float)
    y = np.asarray(y)
    pos, neg = s[y == 1], s[y == 0]
    m, n = len(pos), len(neg)
    tx = stats.rankdata(pos)
    ty = stats.rankdata(neg)
    tz = stats.rankdata(np.concatenate([pos, neg]))
    auc = (tz[:m].sum() - m * (m + 1) / 2) / (m * n)
    v10 = (tz[:m] - tx) / n
    v01 = 1 - (tz[m:] - ty) / m
    return auc, v10, v01


@pytest.mark.parametrize("seed", SEEDS)
def test_auc_matches_sklearn_and_scipy(seed):
    _, y, s = fixture(seed, ties=seed % 2 == 0)
    r = M.auc_delong(s, y)
    assert abs(r["auc"] - roc_auc_score(y, s)) < 1e-9
    u = stats.mannwhitneyu([a for a, t in zip(s, y) if t], [a for a, t in zip(s, y) if not t]).statistic
    assert abs(r["auc"] - u / (r["n1"] * r["n0"])) < 1e-9
    auc, v10, v01 = np_delong(s, y)
    se = math.sqrt(np.var(v10, ddof=1) / len(v10) + np.var(v01, ddof=1) / len(v01))
    assert abs(r["se"] - se) < 1e-9


@pytest.mark.parametrize("seed", SEEDS)
def test_paired_delong_matches_numpy(seed):
    x, y, s = fixture(seed)
    s2 = [r[1] for r in x]
    r = M.delong_paired(s, s2, y)
    a, a10, a01 = np_delong(s, y)
    b, b10, b01 = np_delong(s2, y)
    c10 = np.cov(np.vstack([a10, b10]))
    c01 = np.cov(np.vstack([a01, b01]))
    var = (c10[0, 0] + c10[1, 1] - 2 * c10[0, 1]) / len(a10) + (c01[0, 0] + c01[1, 1] - 2 * c01[0, 1]) / len(a01)
    assert abs(r["diff"] - (a - b)) < 1e-9
    assert abs(r["se"] - math.sqrt(var)) < 1e-9
    z = abs(a - b) / math.sqrt(var)
    assert abs(r["p"] - 2 * stats.norm.sf(z)) < 1e-9


def np_newton(X, y, offset=None):
    X = np.column_stack([np.ones(len(y)), np.asarray(X, float)]) if len(X[0]) else np.ones((len(y), 1))
    y = np.asarray(y, float)
    off = np.zeros(len(y)) if offset is None else np.asarray(offset)
    b = np.zeros(X.shape[1])
    for _ in range(200):
        eta = off + X @ b
        mu = 1 / (1 + np.exp(-eta))
        W = mu * (1 - mu)
        step = np.linalg.solve(X.T @ (X * W[:, None]), X.T @ (y - mu))
        b = b + step
        if np.max(np.abs(step)) < 1e-13:
            break
    eta = off + X @ b
    ll = float(np.sum(y * eta - np.logaddexp(0, eta)))
    return b, ll


@pytest.mark.parametrize("seed", SEEDS)
def test_logistic_matches_numpy_and_sklearn(seed):
    x, y, _ = fixture(seed)
    fit = M.logistic_fit(x, y)
    b, ll = np_newton(x, y)
    assert np.allclose(fit["beta"], b, rtol=1e-9, atol=1e-9)
    assert abs(fit["loglik"] - ll) < 1e-9 * max(1, abs(ll))
    sk = LogisticRegression(C=np.inf, solver="newton-cg", tol=1e-12, max_iter=10000).fit(np.array(x), y)
    assert np.allclose(fit["beta"], np.concatenate([sk.intercept_, sk.coef_[0]]), atol=1e-5)


@pytest.mark.parametrize("seed", SEEDS[:20])
def test_lr_test_and_chi2(seed):
    x, y, _ = fixture(seed)
    small = [r[:2] for r in x]
    r = M.lr_test(small, x, y)
    _, l0 = np_newton(small, y)
    _, l1 = np_newton(x, y)
    assert abs(r["stat"] - 2 * (l1 - l0)) < 1e-8
    assert abs(r["p"] - stats.chi2.sf(r["stat"], 1)) < 1e-12


@pytest.mark.parametrize("seed", SEEDS[:20])
def test_calibration_matches_numpy(seed):
    x, y, _ = fixture(seed)
    rng = random.Random(seed)
    pred = [min(0.98, max(0.02, 0.3 + 0.2 * r[0] + rng.uniform(-0.1, 0.1))) for r in x]
    c = M.calibration(pred, y)
    lp = [math.log(p / (1 - p)) for p in pred]
    b, _ = np_newton([[v] for v in lp], y)
    b0, _ = np_newton([[] for _ in lp], y, offset=lp)
    assert abs(c["slope"] - b[1]) < 1e-9
    assert abs(c["intercept"] - b0[0]) < 1e-9


def test_brier_and_scaled():
    y = [1, 0, 0, 1, 0]
    p = [0.8, 0.1, 0.3, 0.6, 0.2]
    r = M.brier(p, y)
    b = np.mean((np.array(p) - np.array(y)) ** 2)
    assert abs(r["brier"] - b) < 1e-15
    assert abs(r["scaled"] - (1 - b / (0.4 * 0.6))) < 1e-12


def test_folds_stratified_seeded():
    y = [1] * 37 + [0] * 113
    f1 = M.stratified_folds(y, 10, random.Random(5))
    f2 = M.stratified_folds(y, 10, random.Random(5))
    assert f1 == f2
    for k in range(10):
        ev = sum(1 for i in range(150) if f1[i] == k and y[i])
        assert ev in (3, 4)


def test_separation_guard():
    y = [0] * 20 + [1] * 20
    x = [[i] for i in range(40)]
    with pytest.raises(M.SeparationError):
        M.logistic_fit(x, y)


def test_holm_matches_definition():
    ps = [0.01, 0.04, 0.03, 0.5]
    assert M.holm(ps) == pytest.approx([0.04, 0.09, 0.09, 0.5])


def test_bands_merge_rule():
    rng = random.Random(3)
    s = [rng.random() for _ in range(300)]
    y = [1 if rng.random() < 0.08 + 0.2 * v else 0 for v in s]
    rows = M.bands(s, y, 10)
    assert sum(r["n"] for r in rows) == 300
    assert all(r["events"] >= 5 and r["nonevents"] >= 5 for r in rows)
    assert [r["first"] for r in rows] == sorted(r["first"] for r in rows)
    assert rows[0]["first"] == 1 and rows[-1]["last"] == 10


def test_confusion_counts():
    s = [0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2, 0.1, 0.0]
    y = [1, 0, 1, 0, 0, 1, 0, 0, 0, 0]
    c = M.confusion_at(s, y, 0.3)
    assert c == {"flagged": 3, "tp": 2, "fp": 1, "fn": 1, "tn": 6}


def test_hanley_mcneil_worked_example():
    """Hanley & McNeil (1982), Radiology 143:29-36, Table 1: CT ratings of 58 normal and 51 abnormal cases on a
    5-point scale. The paper reports AUC 0.893 and SE 0.032 (its own approximation)."""
    normal = [1] * 33 + [2] * 6 + [3] * 6 + [4] * 11 + [5] * 2
    abnormal = [1] * 3 + [2] * 2 + [3] * 2 + [4] * 11 + [5] * 33
    s = abnormal + normal
    y = [1] * 51 + [0] * 58
    r = M.auc_delong(s, y)
    assert round(r["auc"], 3) == 0.893
    assert round(M.hanley_mcneil_se(r["auc"], 51, 58), 3) == 0.032
    assert abs(r["se"] - 0.032) < 0.004   # DeLong's exact SE is close to the paper's approximation


def test_pool_fixed_single_and_two():
    one = M.pool_fixed([0.62], [0.03])
    assert one["auc"] == 0.62 and abs(one["se"] - 0.03) < 1e-15
    two = M.pool_fixed([0.60, 0.70], [0.03, 0.03])
    assert abs(two["auc"] - 0.65) < 1e-12 and two["i2"] > 0.5
