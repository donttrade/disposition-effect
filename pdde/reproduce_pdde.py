#!/usr/bin/env python3
"""
The portfolio-driven disposition effect, tested on the Xueqiu retail panel.

Replicates An, Engelberg, Henriksson, Wang & Williams, "The Portfolio-Driven
Disposition Effect" -- the finding that the disposition effect is concentrated
when an investor's PORTFOLIO is at a loss and nearly vanishes when it is at a
gain -- on free CC0 data.

Data:  Jin, Li & Zhu (2021), "Could social interaction reduce the disposition
       effect? Evidence from retail investors in a directed social trading
       network", PLoS ONE 16(2), doi:10.1371/journal.pone.0246759
       Replication files: doi:10.7910/DVN/NI6SBJ   (licence: CC0 1.0)

Usage:
    pip install pyreadr pandas numpy scipy
    python reproduce_pdde.py          # downloads the file if absent

PRE-REGISTRATION
----------------
The design below was fixed in writing BEFORE any portfolio-level variable was
computed and before any outcome was seen. Everything marked EXPLORATORY was
added afterwards and cannot be promoted to the headline.

  Hypothesis   the gap (PGR - PLR) is larger on trader-days when the trader's
               OTHER holdings are predominantly at a loss. Equivalently the
               `gain x PortfolioGain` interaction is negative.
  Primary      sale ~ gain + PortfolioGain + gain x PortfolioGain,
               trader fixed effects, SEs clustered by trader. One
               specification. No alternatives.
  Thresholds   negative + significant + gap ratio >= 2x  -> replicated
               negative + significant + ratio < 2x       -> weak replication
               not distinguishable from zero             -> failure to replicate
               positive + significant                    -> contradicted

THE ONE DESIGN DECISION THAT DECIDES WHETHER THIS IS REAL
---------------------------------------------------------
The panel has no position value or weight, so portfolio state is a COUNT of
the trader's other positions in profit -- a proxy, and not An et al.'s
value-weighted return. Say so wherever it is reported.

It is computed LEAVE-ONE-OUT, excluding the focal position. The focal
position's own `gain` is part of any naive portfolio measure built from the
same column, which would mechanically correlate the conditioning variable
with the thing being conditioned on and produce a strong, entirely spurious
interaction that looks exactly like a successful replication.

  frac_excl = (other held positions in gain) / (other held positions)
  PortfolioGain = 1 if frac_excl > 0.5, 0 if < 0.5, EXCLUDED at exactly 0.5.
  Trader-days holding a single position are undefined and excluded.

WHY `ret` IS NOT USED
---------------------
The delivered file carries fourteen columns, including `ret`, which would have
triggered the value-weighted branch. It is a gross ratio (1.0 = breakeven) but
it does NOT reproduce `gain`: agreement is 66.3% at ret>0 and 62.7% at ret>1.
Whatever it measures, it is not the position's profit state as this study
defines it, and the files carry no codebook. 272 rows have ret <= 0, which is
impossible for a price ratio (minimum -2767.49), and 2.16% are null.
Building the conditioning variable from it was rejected on those grounds.
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
TERMS = ["gain", "PG", "gxPG"]


def fetch():
    if not os.path.exists(MAIN_PANEL):
        print("downloading %s ..." % MAIN_PANEL, file=sys.stderr)
        urllib.request.urlretrieve(DATAVERSE + FILE_ID, MAIN_PANEL)


def load():
    import pyreadr
    d = pyreadr.read_r(MAIN_PANEL)
    return d[list(d.keys())[0]]


def build(d):
    """Apply the pre-registered construction and exclusions, in order."""
    g = d.groupby([TRADER, DATE], observed=True)
    n_pos = g["gain"].transform("size")
    n_gain = g["gain"].transform("sum")
    den = n_pos - 1
    frac = np.where(den > 0, (n_gain - d["gain"]) / den.where(den > 0), np.nan)
    d = d.assign(n_pos=n_pos, frac=frac)

    total = len(d)
    single = int((d.n_pos < 2).sum())
    elig = d[d.n_pos >= 2].dropna(subset=["frac"])
    ties = int((elig.frac == 0.5).sum())
    s = elig[elig.frac != 0.5].copy()

    print("\n=== THE PRE-REGISTERED EXCLUSION LADDER ===")
    print("  rows at start                 %10s  100.00%%" % format(total, ","))
    print("  - single-position trader-days %10s  %6.2f%%" % (format(single, ","), 100.0 * single / total))
    print("  - frac_excl exactly 0.50      %10s  %6.2f%%" % (format(ties, ","), 100.0 * ties / total))
    print("  = ANALYSIS SAMPLE             %10s  %6.2f%%" % (format(len(s), ","), 100.0 * len(s) / total))
    print("  traders: %s of %s" % (format(s[TRADER].nunique(), ","), format(d[TRADER].nunique(), ",")))

    s["PG"] = (s.frac > 0.5).astype(float)
    s["gain"] = s["gain"].astype(float)
    s["sale"] = s["sale"].astype(float)
    s["gxPG"] = s.gain * s.PG
    return s


def descriptives(s):
    print("\n=== PGR AND PLR BY PORTFOLIO STATE (descriptive) ===")
    out = {}
    for pg, lbl in ((0.0, "portfolio DOWN"), (1.0, "portfolio UP  ")):
        x = s[s.PG == pg]
        pgr = x.loc[x.gain == 1, "sale"].mean()
        plr = x.loc[x.gain == 0, "sale"].mean()
        pt = x.groupby(TRADER, observed=True).apply(
            lambda z: pd.Series({"pgr": z.loc[z.gain == 1, "sale"].mean(),
                                 "plr": z.loc[z.gain == 0, "sale"].mean()})).dropna()
        out[pg] = (pgr - plr, (pt.pgr - pt.plr).mean())
        print("  %s  N=%-10s PGR %.6f  PLR %.6f   pooled gap %+.6f   per-trader gap %+.6f"
              % (lbl, format(len(x), ","), pgr, plr, pgr - plr, (pt.pgr - pt.plr).mean()))
    print("\n  THE THREE GAP RATIOS DISAGREE, AND THE PRE-REGISTRATION DID NOT SAY WHICH COUNTS:")
    print("    pooled      %.2fx" % (out[0.0][0] / out[1.0][0]))
    print("    per-trader  %.2fx   <- wrong direction" % (out[0.0][1] / out[1.0][1]))
    print("    (within-trader, from the regression below, is the third)")


def _demean(A, idx, m):
    cnt = np.bincount(idx, minlength=m).astype(float)
    out = A.copy()
    for j in range(A.shape[1]):
        out[:, j] -= (np.bincount(idx, weights=A[:, j], minlength=m) / cnt)[idx]
    return out


def _twoway(A, i1, m1, i2, m2, iters=60, tol=1e-11):
    """Alternating projections. A single sequential demeaning is NOT two-way FE."""
    A = A.astype(float).copy()
    for _ in range(iters):
        prev = A.copy()
        A = _demean(_demean(A, i1, m1), i2, m2)
        if np.max(np.abs(A - prev)) < tol:
            break
    return A


def fit(y, X, tr, G, N, extra_k, label):
    """Within estimator with cluster-robust SEs, computed explicitly.

    A panel package cannot be used here: the (trader, date) index is NON-UNIQUE
    by construction, because the analysis unit is trader-stock-LOT-day.
    """
    XtX_inv = np.linalg.inv(X.T @ X)
    beta = XtX_inv @ (X.T @ y)
    u = y - X @ beta
    K = X.shape[1]

    meat = np.zeros((K, K))
    o = np.argsort(tr, kind="stable")
    ts, Xs, us = tr[o], X[o], u[o]
    st = np.searchsorted(ts, np.arange(G))
    en = np.searchsorted(ts, np.arange(G), side="right")
    for i in range(G):
        a, b = int(st[i]), int(en[i])
        if b > a:
            sc = Xs[a:b].T @ us[a:b]
            meat += np.outer(sc, sc)

    c = (G / (G - 1.0)) * ((N - 1.0) / float(N - K - extra_k))
    V = XtX_inv @ meat @ XtX_inv * c
    se = np.sqrt(np.diag(V))
    t = beta / se
    p = 2 * stats.t.sf(np.abs(t), G - 1)
    crit = stats.t.ppf(0.975, G - 1)

    print("\n--- %s ---" % label)
    print("  %-7s %11s %11s %9s %12s %24s" % ("term", "coef", "SE", "t", "p", "95% CI"))
    for i, nm in enumerate(TERMS):
        print("  %-7s %+11.6f %11.6f %+9.3f %12.3e   [%+.6f, %+.6f]"
              % (nm, beta[i], se[i], t[i], p[i], beta[i] - crit * se[i], beta[i] + crit * se[i]))
    gap_dn, gap_up = beta[0], beta[0] + beta[2]
    print("  gap DOWN %+.6f   gap UP %+.6f   ratio %.2fx" % (gap_dn, gap_up, gap_dn / gap_up))
    return beta[2], p[2], gap_dn / gap_up


def main():
    fetch()
    d = load()
    print("rows: %s   columns: %s" % (format(len(d), ","), list(d.columns)))
    s = build(d)
    descriptives(s)

    tr = np.asarray(s[TRADER].astype("category").cat.codes, dtype=np.int64)
    dt = np.asarray(s[DATE].astype("category").cat.codes, dtype=np.int64)
    y0 = s["sale"].to_numpy(float).reshape(-1, 1)
    X0 = s[TERMS].to_numpy(float)
    G, ND, N = int(tr.max()) + 1, int(dt.max()) + 1, int(len(s))
    print("\nN=%s  traders=%s  dates=%s" % (format(N, ","), format(G, ","), format(ND, ",")))

    print("\n" + "=" * 74)
    print("PRIMARY -- pre-specified. Trader FE, SEs clustered by trader.")
    print("=" * 74)
    b1, p1, r1 = fit(_demean(y0, tr, G).ravel(), _demean(X0, tr, G),
                     tr, G, N, 0, "trader FE")

    print("\n" + "=" * 74)
    print("EXPLORATORY -- added after the result. Cannot be the headline.")
    print("  Threat: on a market-up day most positions are in gain, so")
    print("  PortfolioGain may proxy MARKET state rather than PORTFOLIO state.")
    print("=" * 74)
    b2, p2, r2 = fit(_twoway(y0, tr, G, dt, ND).ravel(), _twoway(X0, tr, G, dt, ND),
                     tr, G, N, ND, "trader FE + date FE")
    print("\n  %.1f%% of the interaction retained after absorbing %d day effects."
          % (100.0 * b2 / b1, ND))

    print("\n" + "=" * 74)
    print("VERDICT against the thresholds fixed before the data was opened")
    print("=" * 74)
    sig = p1 < 0.05
    if b1 < 0 and sig and r1 >= 2:
        v = "REPLICATED"
    elif b1 < 0 and sig:
        v = "WEAK REPLICATION -- direction yes, magnitude no"
    elif b1 > 0 and sig:
        v = "CONTRADICTED"
    else:
        v = "FAILURE TO REPLICATE"
    print("  interaction %+.6f, p %.2e, within-trader ratio %.2fx  ->  %s" % (b1, p1, r1, v))
    print("  NOTE: %.2fx clears a 2.00x bar by %.2f. A bar of 2.1 would have"
          % (r1, r1 - 2.0))
    print("        given 'weak replication'. The bar was fixed in advance.")
    print("  NOTE: the per-trader gap ratio points the OTHER WAY. The")
    print("        pre-registration did not say which gap measure governs;")
    print("        the case for the within-trader one is post hoc.")


if __name__ == "__main__":
    main()
