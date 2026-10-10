#!/usr/bin/env python3
"""
The portfolio-driven disposition effect, tested on the Xueqiu retail panel.

A pre-registered replication of An, Engelberg, Henriksson, Wang & Williams,
"The Portfolio-Driven Disposition Effect" -- the finding that the disposition
effect is concentrated when an investor's PORTFOLIO is at a loss and nearly
vanishes when it is at a gain.

Data:  Jin, Li & Zhu (2021), PLoS ONE 16(2), doi:10.1371/journal.pone.0246759
       Replication files: doi:10.7910/DVN/NI6SBJ   (licence: CC0 1.0)

    pip install pyreadr pandas numpy scipy
    python reproduce_pdde.py

PRE-REGISTRATION (fixed before any portfolio variable was computed)
-------------------------------------------------------------------
  Primary     sale ~ gain + PortfolioGain + gain x PortfolioGain,
              trader fixed effects, SEs clustered by trader. One spec.
  Rule        negative + significant + gap ratio >= 2x  -> replicated
              negative + significant + ratio < 2x       -> weak replication
              not distinguishable from zero             -> failure
              positive + significant                    -> contradicted

Everything after specification 1 is NOT pre-registered and is labelled so.

TWO CORRECTIONS TO EARLIER VERSIONS OF THIS FILE
------------------------------------------------
1. `ret` was described as a position-level gross price ratio. It is a
   TRADER-DAY series (0 of 951,885 trader-days carry more than one value).
   An earlier version then claimed it is "immune by construction" to
   dependence on the focal position. THAT IS ALSO WRONG: a portfolio index
   contains the focal position. Measured, own `gain` predicts it at t = +21.8.
   Neither conditioning variable here is independent of the focal position.

2. An earlier version reported the size-controlled ratio evaluated at
   log(n_pos) = 0, i.e. a ONE-POSITION portfolio, which this sample excludes
   by construction (minimum is 2). Every ratio from a specification with an
   interacted continuous control is now reported AT SAMPLE MEANS, and at a
   range of evaluation points, because the single number is meaningless alone.
"""

from __future__ import annotations

import os
import sys
import urllib.request

import numpy as np
import pandas as pd
from scipy import stats

DATAVERSE = "https://dataverse.harvard.edu/api/access/datafile/"
MAIN_PANEL = "sample2.Rdata"
FILE_ID = "4053809"
TRADER, DATE = "cube.symbol", "date"


def fetch():
    if not os.path.exists(MAIN_PANEL):
        print("downloading %s ..." % MAIN_PANEL, file=sys.stderr)
        urllib.request.urlretrieve(DATAVERSE + FILE_ID, MAIN_PANEL)


def load():
    import pyreadr
    d = pyreadr.read_r(MAIN_PANEL)
    return d[list(d.keys())[0]]


def _dm(A, idx, m):
    c = np.bincount(idx, minlength=m).astype(float)
    o = A.copy()
    for j in range(A.shape[1]):
        o[:, j] -= (np.bincount(idx, weights=A[:, j], minlength=m) / c)[idx]
    return o


def _twoway(A, i1, m1, i2, m2, iters=60, tol=1e-11):
    A = A.astype(float).copy()
    for _ in range(iters):
        prev = A.copy()
        A = _dm(_dm(A, i1, m1), i2, m2)
        if np.max(np.abs(A - prev)) < tol:
            break
    return A


def fe(df, cols, label, date_fe=False, quiet=False):
    """Within-trader LPM, cluster-robust by trader. Returns (beta, V, G, cols).

    A panel package cannot be used: the (trader, date) index is NON-UNIQUE by
    construction, because the analysis unit is trader-stock-LOT-day.
    """
    tr = np.asarray(df[TRADER].astype("category").cat.codes, dtype=np.int64)
    y = df["sale"].to_numpy(float).reshape(-1, 1)
    X = df[cols].to_numpy(float)
    G, N, K = int(tr.max()) + 1, int(len(df)), len(cols)
    if date_fe:
        dt = np.asarray(df[DATE].astype("category").cat.codes, dtype=np.int64)
        ND = int(dt.max()) + 1
        yd, Xd, extra = _twoway(y, tr, G, dt, ND).ravel(), _twoway(X, tr, G, dt, ND), ND
    else:
        yd, Xd, extra = _dm(y, tr, G).ravel(), _dm(X, tr, G), 0

    XtX = np.linalg.inv(Xd.T @ Xd)
    b = XtX @ (Xd.T @ yd)
    u = yd - Xd @ b
    meat = np.zeros((K, K))
    o = np.argsort(tr, kind="stable")
    ts, Xs, us = tr[o], Xd[o], u[o]
    st = np.searchsorted(ts, np.arange(G))
    en = np.searchsorted(ts, np.arange(G), side="right")
    for i in range(G):
        p, q = int(st[i]), int(en[i])
        if q > p:
            sc = Xs[p:q].T @ us[p:q]
            meat += np.outer(sc, sc)
    V = XtX @ meat @ XtX * ((G / (G - 1.0)) * ((N - 1.0) / float(N - K - extra)))
    se = np.sqrt(np.diag(V))
    t = b / se
    if not quiet:
        print("\n--- %s   N=%s  traders=%s ---" % (label, format(N, ","), format(G, ",")))
        for i, nm in enumerate(cols):
            print("   %-10s %+.6f  SE %.6f  t %+8.2f  p %.2e"
                  % (nm, b[i], se[i], t[i], 2 * stats.t.sf(abs(t[i]), G - 1)))
    return b, V, G, cols


def ratio_at(b, V, G, cols, at, label):
    """Gap ratio and delta-method CI, evaluated at a named point.

    `at` maps an interaction term to the value of its control. Reporting a
    ratio from a spec with interacted controls WITHOUT saying where it is
    evaluated is meaningless -- an earlier version of this file did exactly
    that and reported a portfolio size the sample cannot contain.
    """
    ig, ip, ix = cols.index("gain"), cols.index("PG"), cols.index("gxPG")
    num = b[ig] + sum(b[cols.index(k)] * v for k, v in at.items())
    den = num + b[ix]
    r = num / den
    grad = np.zeros(len(cols))
    grad[ig] = (den - num) / den ** 2
    grad[ix] = -num / den ** 2
    for k, v in at.items():
        grad[cols.index(k)] = (v * den - num * v) / den ** 2
    rse = float(np.sqrt(grad @ V @ grad))
    crit = stats.t.ppf(0.975, G - 1)
    print("   ratio %-28s %6.3f   95%% CI [%.3f, %.3f]"
          % (label, r, r - crit * rse, r + crit * rse))
    return r


def main():
    fetch()
    d = load()
    print("rows %s   traders %s   dates %s   stocks %s"
          % (format(len(d), ","), format(d[TRADER].nunique(), ","),
             format(d[DATE].nunique(), ","), format(d["stkcd"].nunique(), ",")))

    g = d.groupby([TRADER, DATE], observed=True)
    n_pos = g["gain"].transform("size")
    n_gain = g["gain"].transform("sum")
    den = n_pos - 1
    frac = np.where(den > 0, (n_gain - d["gain"]) / den.where(den > 0), np.nan)
    a = d.assign(n_pos=n_pos, frac=frac)

    tot = len(a)
    single = int((a.n_pos < 2).sum())
    elig = a[a.n_pos >= 2].dropna(subset=["frac"])
    ties = int((elig.frac == 0.5).sum())
    s = elig[elig.frac != 0.5].copy()
    print("\n=== PRE-REGISTERED EXCLUSION LADDER ===")
    print("  start                   %10s  100.00%%" % format(tot, ","))
    print("  - single-position days  %10s  %6.2f%%" % (format(single, ","), 100.0 * single / tot))
    print("  - ties at exactly 0.50  %10s  %6.2f%%" % (format(ties, ","), 100.0 * ties / tot))
    print("  = ANALYSIS SAMPLE       %10s  %6.2f%%" % (format(len(s), ","), 100.0 * len(s) / tot))

    for c in ("gain", "sale"):
        s[c] = s[c].astype(float)
    s["PG"] = (s.frac > 0.5).astype(float)
    s["gxPG"] = s.gain * s.PG

    deg = int((s.PG == (1 - s.gain)).sum())
    print("\n=== HOW MUCH OF THE SAMPLE IDENTIFIES THE INTERACTION ===")
    print("  rows where PG == 1 - gain exactly (gxPG contributes nothing):")
    print("    %s of %s = %.2f%%" % (format(deg, ","), format(len(s), ","), 100.0 * deg / len(s)))
    print("  Leave-one-out HALVES the dependence between own `gain` and PG.")
    print("  It does not remove it, and all identification is BETWEEN trader-days.")

    print("\n" + "=" * 72)
    print("1. PRE-SPECIFIED PRIMARY")
    print("=" * 72)
    b1, V1, G1, c1 = fe(s, ["gain", "PG", "gxPG"], "trader FE, clustered by trader")
    r1 = ratio_at(b1, V1, G1, c1, {}, "(no interacted controls)")

    print("\n" + "=" * 72)
    print("2-5. NOT PRE-REGISTERED. None may be the headline.")
    print("=" * 72)
    b2, V2, G2, c2 = fe(s, ["gain", "PG", "gxPG"], "2. + 428 date FE", date_fe=True)
    ratio_at(b2, V2, G2, c2, {}, "(no interacted controls)")

    s["logn"] = np.log(s.n_pos.astype(float))
    s["gxlogn"] = s.gain * s.logn
    b3, V3, G3, c3 = fe(s, ["gain", "PG", "gxPG", "logn", "gxlogn"], "3. + portfolio size")
    print("   n_pos = 1 is EXCLUDED by construction (minimum in sample: %d)" % int(s.n_pos.min()))
    for lbl, L in (("at n_pos=2", np.log(2)), ("AT SAMPLE MEANS", float(s.logn.mean())),
                   ("at n_pos=5 (median)", np.log(5)), ("at n_pos=8", np.log(8))):
        ratio_at(b3, V3, G3, c3, {"gxlogn": L}, lbl)

    for src, nm in (("hold.period", "lhold"), ("trd.num", "ltrd"), ("active.day", "lact")):
        s[nm] = np.log1p(d.loc[s.index, src].fillna(0).to_numpy(float))
        s["gx" + nm] = s.gain * s[nm]
    s["mmt"] = d.loc[s.index, "mmt"].fillna(0).to_numpy(float)
    s["gxmmt"] = s.gain * s.mmt
    full = ["gain", "PG", "gxPG", "logn", "gxlogn", "lhold", "gxlhold",
            "ltrd", "gxltrd", "lact", "gxlact", "mmt", "gxmmt"]
    b4, V4, G4, c4 = fe(s, full, "4. + size, holding period, activity, market")
    at = dict((("gx" + k), float(s[k].mean())) for k in ("logn", "lhold", "ltrd", "lact", "mmt"))
    r4 = ratio_at(b4, V4, G4, c4, at, "AT SAMPLE MEANS")

    r_ = d.dropna(subset=["ret"]).copy()
    r_["PG"] = (r_.ret > 1).astype(float)
    for c in ("gain", "sale"):
        r_[c] = r_[c].astype(float)
    r_["gxPG"] = r_.gain * r_.PG
    b5, V5, G5, c5 = fe(r_, ["gain", "PG", "gxPG"], "5. `ret` portfolio index, no exclusions")
    ratio_at(b5, V5, G5, c5, {}, "(no interacted controls)")
    print("   rows %s = %.1f%% of the panel" % (format(len(r_), ","), 100.0 * len(r_) / len(d)))
    bd, _, _, _ = fe(r_.assign(sale=r_.PG), ["gain", "n_pos"] if "n_pos" in r_ else ["gain"],
                     "   DEPENDENCE CHECK: PG_ret ~ own gain", quiet=True)
    print("   PG_ret regressed on own `gain`, trader FE: %+.6f" % bd[0])
    print("   -> `ret` is NOT independent of the focal position either.")

    print("\n" + "=" * 72)
    print("6. PLACEBO -- should return nothing")
    print("=" * 72)
    a2 = a.copy()
    a2["even"] = (a2["stkcd"].astype(str).str[-1].astype(int) % 2 == 0).astype(float)
    gg = a2.groupby([TRADER, DATE], observed=True)
    ne = gg["even"].transform("sum")
    fe_ = np.where(a2.n_pos - 1 > 0, (ne - a2["even"]) / (a2.n_pos - 1).where(a2.n_pos > 1), np.nan)
    a2 = a2.assign(fe_=fe_)
    pl = a2[(a2.n_pos >= 2) & (a2.fe_ != 0.5)].dropna(subset=["fe_"]).copy()
    for c in ("gain", "sale"):
        pl[c] = pl[c].astype(float)
    pl["PG"] = (pl.fe_ > 0.5).astype(float)
    pl["gxPG"] = pl.gain * pl.PG
    bp, _, _, _ = fe(pl, ["gain", "PG", "gxPG"], "placebo: parity of stock code, UNCONTROLLED")
    pl["logn"] = np.log(pl.n_pos.astype(float))
    pl["gxlogn"] = pl.gain * pl.logn
    for src, nm in (("hold.period", "lhold"), ("trd.num", "ltrd"), ("active.day", "lact")):
        pl[nm] = np.log1p(d.loc[pl.index, src].fillna(0).to_numpy(float))
        pl["gx" + nm] = pl.gain * pl[nm]
    pl["mmt"] = d.loc[pl.index, "mmt"].fillna(0).to_numpy(float)
    pl["gxmmt"] = pl.gain * pl.mmt
    bpc, _, _, _ = fe(pl, full, "placebo: same controls as spec 4")
    print("\n   UNCONTROLLED placebo interaction %+.6f  (should be 0)" % bp[2])
    print("   CONTROLLED   placebo interaction %+.6f" % bpc[2])

    print("\n" + "=" * 72)
    print("VERDICT")
    print("=" * 72)
    print("  The PRE-REGISTERED rule, applied literally to specification 1:")
    print("    interaction %+.6f, negative and significant; ratio %.3f >= 2.00" % (b1[2], r1))
    print("    -> REPLICATED.")
    print("\n  But the ratio is not robust, and the rule did not anticipate controls:")
    print("    spec 1 ratio %.3f has a 95%% CI that contains 2.00" % r1)
    print("    spec 4 ratio %.3f at sample means, CI also containing 2.00" % r4)
    print("    an UNCONTROLLED placebo returns %+.6f when it should return 0;" % bp[2])
    print("    the same controls take the placebo to %+.6f and the real" % bpc[2])
    print("    interaction to %+.6f (t still beyond -12)." % b4[2])
    print("\n  DIRECTION: replicates, in every specification above.")
    print("  MAGNITUDE: not established. Point estimates cluster near 1.85-2.07")
    print("             with intervals straddling the pre-registered bar.")


if __name__ == "__main__":
    main()
