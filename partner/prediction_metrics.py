#!/usr/bin/env python3
"""Statistics for the prediction study (DT-1). Standard library only.

Imported by prediction_test.py. It opens no file, writes nothing and prints
nothing: every function takes numbers and returns numbers.

  auc_delong        Mann-Whitney AUC (ties count 1/2), DeLong standard error and 95% interval
  delong_paired     two scores on the same accounts: the AUC difference, its SE, 95% interval, p
  logistic_fit      logistic regression by IRLS (Newton), at most 6 terms, with a separation guard
  lr_test           likelihood-ratio test, 1 degree of freedom
  stratified_folds  seeded, stratified k-fold assignment
  cv_predict        out-of-fold predicted probabilities
  calibration       calibration intercept (offset model) and slope
  brier             Brier score and scaled Brier
  bands             decile / 10-band tables with the small-cell merge (>= MIN_CELL per cell)
  hanley_mcneil_se  the approximate SE used for planning
  holm              Holm step-down adjustment
  pool_fixed        fixed-effect inverse-variance pooling of per-firm AUCs, with I-squared

Version 1.0 (30 Oct 2026).
"""

import math

Z975 = 1.959963984540054   # the standard normal quantile at 0.975
MIN_CELL = 5               # no printed table cell describes fewer accounts
MAX_TERMS = 6
MAX_ITER = 100
SEPARATION_BETA = 30.0     # |coefficient| above this on standardised inputs = (quasi-)separation


class SeparationError(Exception):
    """The logistic fit did not converge to finite coefficients (separation or collinearity)."""


# ---------------------------------------------------------------- basic helpers

def norm_cdf(x):
    return 0.5 * math.erfc(-x / math.sqrt(2.0))


def chi2_1_sf(x):
    """Upper tail of a chi-square with 1 degree of freedom."""
    if x <= 0:
        return 1.0
    return math.erfc(math.sqrt(x / 2.0))


def midranks(values):
    """1-based mid-ranks (ties get the average rank)."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    r = [0.0] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and values[order[j]] == values[order[i]]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            r[order[k]] = avg
        i = j
    return r


def _mean(xs):
    s = 0.0
    for v in xs:
        s += v
    return s / len(xs)


def _cov(xs, ys):
    n = len(xs)
    if n < 2:
        return 0.0
    mx, my = _mean(xs), _mean(ys)
    s = 0.0
    for a, b in zip(xs, ys):
        s += (a - mx) * (b - my)
    return s / (n - 1)


# ---------------------------------------------------------------- AUC and DeLong

def _components(score, y):
    """DeLong structural components. Returns (auc, V10 over events, V01 over non-events)."""
    pos = [s for s, t in zip(score, y) if t == 1]
    neg = [s for s, t in zip(score, y) if t == 0]
    n1, n0 = len(pos), len(neg)
    if n1 == 0 or n0 == 0:
        raise ValueError("auc: needs at least one event and one non-event")
    rz = midranks(pos + neg)
    rx = midranks(pos)
    ry = midranks(neg)
    v10 = [(rz[i] - rx[i]) / n0 for i in range(n1)]
    v01 = [1.0 - (rz[n1 + j] - ry[j]) / n1 for j in range(n0)]
    s = 0.0
    for i in range(n1):
        s += rz[i]
    auc = (s - n1 * (n1 + 1) / 2.0) / (n1 * n0)
    return auc, v10, v01


def auc_only(score, y):
    return _components(score, y)[0]


def auc_delong(score, y):
    """{auc, se, lo, hi, n1, n0}: the 95% interval is auc +/- 1.96 SE, clipped to [0, 1]."""
    auc, v10, v01 = _components(score, y)
    n1, n0 = len(v10), len(v01)
    var = (_cov(v10, v10) / n1 if n1 > 1 else 0.0) + (_cov(v01, v01) / n0 if n0 > 1 else 0.0)
    se = math.sqrt(var) if var > 0 else 0.0
    return {"auc": auc, "se": se, "lo": max(0.0, auc - Z975 * se), "hi": min(1.0, auc + Z975 * se),
            "n1": n1, "n0": n0}


def auc_p_greater(r):
    """One-sided p for AUC > 0.5 from a DeLong result (normal approximation)."""
    if r["se"] <= 0:
        return 0.0 if r["auc"] > 0.5 else 1.0
    return 1.0 - norm_cdf((r["auc"] - 0.5) / r["se"])


def delong_paired(score_a, score_b, y):
    """AUC(a) - AUC(b) on the same accounts: {diff, se, lo, hi, p (two-sided)}."""
    a, a10, a01 = _components(score_a, y)
    b, b10, b01 = _components(score_b, y)
    n1, n0 = len(a10), len(a01)
    d10 = [u - v for u, v in zip(a10, b10)]
    d01 = [u - v for u, v in zip(a01, b01)]
    var = (_cov(d10, d10) / n1 if n1 > 1 else 0.0) + (_cov(d01, d01) / n0 if n0 > 1 else 0.0)
    se = math.sqrt(var) if var > 0 else 0.0
    diff = a - b
    p = 1.0 if se == 0 else 2.0 * (1.0 - norm_cdf(abs(diff) / se))
    return {"auc_a": a, "auc_b": b, "diff": diff, "se": se, "lo": diff - Z975 * se, "hi": diff + Z975 * se,
            "p": min(1.0, p)}


def hanley_mcneil_se(auc, n1, n0):
    q1 = auc / (2.0 - auc)
    q2 = 2.0 * auc * auc / (1.0 + auc)
    var = (auc * (1 - auc) + (n1 - 1) * (q1 - auc * auc) + (n0 - 1) * (q2 - auc * auc)) / (n1 * n0)
    return math.sqrt(var)


# ---------------------------------------------------------------- linear algebra (tiny, dense)

def _solve(A, b):
    """Gaussian elimination with partial pivoting; A is k x k (k <= MAX_TERMS)."""
    k = len(A)
    M = [list(A[i]) + [b[i]] for i in range(k)]
    for c in range(k):
        p = max(range(c, k), key=lambda r: abs(M[r][c]))
        if abs(M[p][c]) < 1e-12:
            raise SeparationError("singular information matrix")
        M[c], M[p] = M[p], M[c]
        for r in range(c + 1, k):
            f = M[r][c] / M[c][c]
            if f != 0.0:
                for j in range(c, k + 1):
                    M[r][j] -= f * M[c][j]
    x = [0.0] * k
    for r in range(k - 1, -1, -1):
        s = M[r][k]
        for j in range(r + 1, k):
            s -= M[r][j] * x[j]
        x[r] = s / M[r][r]
    return x


# ---------------------------------------------------------------- logistic regression

def _sigmoid(t):
    if t >= 0:
        return 1.0 / (1.0 + math.exp(-t))
    e = math.exp(t)
    return e / (1.0 + e)


def _loglik(eta, y):
    s = 0.0
    for t, yi in zip(eta, y):
        # log(1 + exp(t)) computed stably
        lse = t + math.log1p(math.exp(-t)) if t > 0 else math.log1p(math.exp(t))
        s += yi * t - lse
    return s


def _standardise(X):
    """Columns centred and scaled (the intercept is added later). Returns Z, means, sds."""
    k = len(X[0]) if X else 0
    means, sds = [], []
    for j in range(k):
        col = [row[j] for row in X]
        m = _mean(col)
        v = _cov(col, col)
        sd = math.sqrt(v) if v > 0 else 1.0
        means.append(m)
        sds.append(sd)
    Z = [[(row[j] - means[j]) / sds[j] for j in range(k)] for row in X]
    return Z, means, sds


def logistic_fit(X, y, offset=None):
    """X: list of rows (no intercept column). Returns {beta (original scale, intercept first), loglik, iters}.
    Raises SeparationError when the fit runs away (perfect or quasi-complete separation)."""
    n = len(y)
    k = len(X[0]) if X else 0
    if k + 1 > MAX_TERMS:
        raise ValueError("logistic_fit: at most %d terms" % MAX_TERMS)
    Z, means, sds = _standardise(X) if k else ([[] for _ in range(n)], [], [])
    D = [[1.0] + Z[i] for i in range(n)]
    p_terms = len(D[0])
    off = offset if offset is not None else [0.0] * n
    beta = [0.0] * p_terms
    eta = [off[i] for i in range(n)]
    ll = _loglik(eta, y)
    it = 0
    for it in range(1, MAX_ITER + 1):
        mu = [_sigmoid(t) for t in eta]
        w = [m * (1 - m) for m in mu]
        H = [[0.0] * p_terms for _ in range(p_terms)]
        g = [0.0] * p_terms
        for i in range(n):
            di = D[i]
            wi = w[i]
            ri = y[i] - mu[i]
            for a in range(p_terms):
                g[a] += di[a] * ri
                wa = wi * di[a]
                for b in range(a, p_terms):
                    H[a][b] += wa * di[b]
        for a in range(p_terms):
            for b in range(a):
                H[a][b] = H[b][a]
        step = _solve(H, g)
        t = 1.0
        while True:
            nb = [beta[j] + t * step[j] for j in range(p_terms)]
            ne = [off[i] + sum(D[i][j] * nb[j] for j in range(p_terms)) for i in range(n)]
            nl = _loglik(ne, y)
            if nl >= ll - 1e-12 or t < 1e-6:
                break
            t /= 2.0
        delta = nl - ll
        beta, eta, ll = nb, ne, nl
        if any(abs(v) > SEPARATION_BETA for v in beta):
            raise SeparationError("coefficients diverge (separation)")
        if abs(delta) < 1e-11 * (1.0 + abs(ll)) and max(abs(s) for s in step) * t < 1e-9:
            break
    else:
        raise SeparationError("no convergence")
    # back to the original scale
    b0 = beta[0] - sum(beta[1 + j] * means[j] / sds[j] for j in range(k))
    out = [b0] + [beta[1 + j] / sds[j] for j in range(k)]
    return {"beta": out, "loglik": ll, "iters": it}


def logistic_predict(beta, X, offset=None):
    n = len(X)
    off = offset if offset is not None else [0.0] * n
    return [_sigmoid(off[i] + beta[0] + sum(beta[1 + j] * X[i][j] for j in range(len(X[i])))) for i in range(n)]


def lr_test(X_small, X_big, y):
    """Nested models (X_big = X_small plus one column, last). Returns {stat, p, coef_last}."""
    a = logistic_fit(X_small, y)
    b = logistic_fit(X_big, y)
    stat = max(0.0, 2.0 * (b["loglik"] - a["loglik"]))
    return {"stat": stat, "p": chi2_1_sf(stat), "coef": b["beta"][-1], "ll_small": a["loglik"], "ll_big": b["loglik"]}


# ---------------------------------------------------------------- cross-validation

def stratified_folds(y, k, rng):
    """Fold id per account. rng is a random.Random seeded by the caller (the sealed fingerprint)."""
    fold = [0] * len(y)
    for cls in (0, 1):
        idx = [i for i, t in enumerate(y) if t == cls]
        rng.shuffle(idx)
        for pos, i in enumerate(idx):
            fold[i] = pos % k
    return fold


def cv_predict(X, y, fold, k):
    """Out-of-fold probabilities of a logistic model on X (with intercept)."""
    pred = [0.0] * len(y)
    for f in range(k):
        tr = [i for i in range(len(y)) if fold[i] != f]
        te = [i for i in range(len(y)) if fold[i] == f]
        if not te:
            continue
        fit = logistic_fit([X[i] for i in tr], [y[i] for i in tr])
        pr = logistic_predict(fit["beta"], [X[i] for i in te])
        for i, p in zip(te, pr):
            pred[i] = p
    return pred


# ---------------------------------------------------------------- calibration and Brier

def _logit(p):
    p = min(max(p, 1e-12), 1 - 1e-12)
    return math.log(p / (1 - p))


def calibration(pred, y):
    """{intercept, slope}: slope from y ~ a + b*logit(p); intercept from y ~ a + offset(logit(p))."""
    lp = [_logit(p) for p in pred]
    slope_fit = logistic_fit([[v] for v in lp], y)
    int_fit = logistic_fit([[] for _ in lp], y, offset=lp)
    return {"intercept": int_fit["beta"][0], "slope": slope_fit["beta"][1]}


def brier(pred, y):
    n = len(y)
    b = sum((p - t) ** 2 for p, t in zip(pred, y)) / n
    base = sum(y) / n
    ref = base * (1 - base)
    return {"brier": b, "scaled": (1.0 - b / ref) if ref > 0 else None}


# ---------------------------------------------------------------- banded tables

def band_of(score, n_bands):
    """Band per account by mid-rank: ties always share a band. Band 0 = lowest scores."""
    n = len(score)
    r = midranks(score)
    return [min(n_bands - 1, int(n_bands * (ri - 0.5) / n)) for ri in r]


def bands(score, y, n_bands=10, pred=None, min_cell=MIN_CELL):
    """Rows (lowest band first) of {first, last, n, events, nonevents, mean_pred}. Adjacent bands are merged,
    lowest first, until every row has >= min_cell events and >= min_cell non-events; a short last row merges
    into the row before it. first/last are the original band numbers (1-based) the row covers."""
    b = band_of(score, n_bands)
    rows = []
    for k in range(n_bands):
        idx = [i for i in range(len(y)) if b[i] == k]
        if not idx:
            continue
        ev = sum(y[i] for i in idx)
        rows.append({"first": k + 1, "last": k + 1, "n": len(idx), "events": ev, "nonevents": len(idx) - ev,
                     "sum_pred": sum(pred[i] for i in idx) if pred is not None else 0.0})

    def ok(r):
        return r["events"] >= min_cell and r["nonevents"] >= min_cell

    def join(a, c):
        return {"first": a["first"], "last": c["last"], "n": a["n"] + c["n"], "events": a["events"] + c["events"],
                "nonevents": a["nonevents"] + c["nonevents"], "sum_pred": a["sum_pred"] + c["sum_pred"]}
    out = []
    cur = None
    for r in rows:
        cur = r if cur is None else join(cur, r)
        if ok(cur):
            out.append(cur)
            cur = None
    if cur is not None:
        if out:
            out[-1] = join(out[-1], cur)
        else:
            out.append(cur)
    for r in out:
        r["mean_pred"] = r["sum_pred"] / r["n"]
        r["ok"] = ok(r)
        del r["sum_pred"]
    return out


def confusion_at(score, y, share):
    """Flag the top `share` of scores (ties at the cut are all flagged). Returns {flagged, tp, fp, fn, tn}."""
    n = len(score)
    k = int(math.ceil(share * n - 1e-9))
    if k <= 0:
        cut = math.inf
    else:
        cut = sorted(score, reverse=True)[k - 1]
    tp = fp = fn = tn = 0
    for s, t in zip(score, y):
        f = s >= cut
        if f and t:
            tp += 1
        elif f:
            fp += 1
        elif t:
            fn += 1
        else:
            tn += 1
    return {"flagged": tp + fp, "tp": tp, "fp": fp, "fn": fn, "tn": tn}


# ---------------------------------------------------------------- multiplicity and pooling

def holm(ps):
    m = len(ps)
    order = sorted(range(m), key=lambda k: (ps[k], k))
    adj = [0.0] * m
    running = 0.0
    for rank, k in enumerate(order):
        v = min(1.0, (m - rank) * ps[k])
        if v > running:
            running = v
        adj[k] = running
    return adj


def pool_fixed(aucs, ses):
    """Fixed-effect inverse-variance pooling. Returns {auc, se, lo, hi, q, i2}."""
    w = [1.0 / (s * s) for s in ses]
    sw = sum(w)
    est = sum(wi * a for wi, a in zip(w, aucs)) / sw
    se = math.sqrt(1.0 / sw)
    q = sum(wi * (a - est) ** 2 for wi, a in zip(w, aucs))
    df = len(aucs) - 1
    i2 = max(0.0, (q - df) / q) if q > 0 and df > 0 else 0.0
    return {"auc": est, "se": se, "lo": est - Z975 * se, "hi": est + Z975 * se, "q": q, "i2": i2}
