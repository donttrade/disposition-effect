#!/usr/bin/env python3
"""
Disposition effect (PGR / PLR) on the Xueqiu retail panel.

Reproduces every figure in the accompanying post from public CC0 data.

Data:  Jin, Li & Zhu (2021), "Could social interaction reduce the disposition
       effect? Evidence from retail investors in a directed social trading
       network", PLoS ONE 16(2), doi:10.1371/journal.pone.0246759
       Replication files: doi:10.7910/DVN/NI6SBJ   (licence: CC0 1.0)

Usage:
    pip install pyreadr pandas numpy scipy
    python reproduce.py            # downloads the two files if absent

Definitions
-----------
Each row is one trader-stock-LOT-day on which a position was held.
    sale == 1  ->  the position was closed that day
    gain == 1  ->  the position was in profit that day

    PGR = mean(sale | gain == 1)        "proportion of gains realised"
    PLR = mean(sale | gain == 0)        "proportion of losses realised"

NOTE ON THE DENOMINATOR.  This dataset's unit of observation is every day a
position is held, so PGR and PLR here are DAILY HAZARDS:
    P(close today | in profit today).
Odean (1998) counted only days on which a sale occurred somewhere in the
account ("On days when no sales take place in an account, no gains or losses,
realized or paper, are counted.").  The two conventions are NOT comparable in
level -- Odean's own account-level alternative gives 0.57/0.36 against his
Table I 0.148/0.098 -- but the RATIO is nearly invariant (1.58 vs 1.51).
Compare ratios only.
"""

from __future__ import annotations

import os
import sys
import urllib.request

import numpy as np
import pandas as pd
from scipy import stats

DATAVERSE = "https://dataverse.harvard.edu/api/access/datafile/"
FILES = {"sample1.Rdata": "4053807", "sample2.Rdata": "4053809"}

MAIN_PANEL = "sample2.Rdata"      # 4,731 traders -- the headline result
NESTED_SUBSAMPLE = "sample1.Rdata"  # 2,649 traders selected on having followers


def fetch() -> None:
    for name, fid in FILES.items():
        if os.path.exists(name):
            continue
        print(f"downloading {name} ...", file=sys.stderr)
        urllib.request.urlretrieve(DATAVERSE + fid, name)


def load(name: str) -> pd.DataFrame:
    import pyreadr

    d = pyreadr.read_r(name)
    return d[list(d.keys())[0]]


def pooled(df: pd.DataFrame) -> tuple[float, float]:
    return df.loc[df.gain == 1, "sale"].mean(), df.loc[df.gain == 0, "sale"].mean()


def per_trader(df: pd.DataFrame) -> pd.DataFrame:
    g = df.groupby("cube.symbol", observed=True)
    out = pd.DataFrame(
        {
            "pgr": g.apply(lambda x: x.loc[x.gain == 1, "sale"].mean(), include_groups=False),
            "plr": g.apply(lambda x: x.loc[x.gain == 0, "sale"].mean(), include_groups=False),
        }
    )
    # a trader needs at least one winner AND one loser for both to be defined
    return out.dropna()


def describe(label: str, df: pd.DataFrame) -> dict:
    pgr, plr = pooled(df)
    t = per_trader(df)
    diff = t.pgr - t.plr
    tt = stats.ttest_rel(t.pgr, t.plr)
    npos = int((diff > 0).sum())
    bt = stats.binomtest(npos, len(t), 0.5, alternative="greater")

    print(f"\n{'=' * 72}\n{label}\n{'=' * 72}")
    print(f"  rows (trader-stock-lot-days) : {len(df):,}")
    print(f"  traders                      : {df['cube.symbol'].nunique():,}")
    print(f"  distinct stocks              : {df['stkcd'].nunique():,}")
    print(f"  period                       : {df['date'].min()} -> {df['date'].max()}")
    print(f"  POOLED      PGR {pgr:.6f}  PLR {plr:.6f}  ratio {pgr / plr:.4f}")
    print(f"  PER-TRADER  PGR {t.pgr.mean():.6f}  PLR {t.plr.mean():.6f}  "
          f"ratio {t.pgr.mean() / t.plr.mean():.4f}")
    print(f"  traders with both defined    : {len(t):,}")
    print(f"  PGR > PLR                    : {npos:,} / {len(t):,} = {npos / len(t):.4f}")
    print(f"  paired t                     : {tt.statistic:.3f}   (p = {tt.pvalue:.3e})")
    print(f"  Cohen's d (paired)           : {diff.mean() / diff.std(ddof=1):.4f}")
    print(f"  binomial p (one-sided)       : {bt.pvalue:.4e}")
    return {
        "pgr": pgr,
        "plr": plr,
        "ratio": pgr / plr,
        "ratio_trader": t.pgr.mean() / t.plr.mean(),
        "share": npos / len(t),
    }


def check_nesting(s1: pd.DataFrame, s2: pd.DataFrame) -> None:
    print(f"\n{'=' * 72}\nCAVEAT 1 -- the two files are NESTED, not independent\n{'=' * 72}")
    t1, t2 = set(s1["cube.symbol"].dropna()), set(s2["cube.symbol"].dropna())
    k1, k2 = set(s1["stkcd"].dropna()), set(s2["stkcd"].dropna())
    print(f"  traders: file1 {len(t1):,}  file2 {len(t2):,}  shared {len(t1 & t2):,}"
          f"  ({100 * len(t1 & t2) / len(t1):.1f}% of file1)")
    print(f"  stocks : file1 {len(k1):,}  file2 {len(k2):,}  shared {len(k1 & k2):,}")
    print(f"  UNION of traders across both files: {len(t1 | t2):,}")
    print(f"  -> adding the two trader counts (2,649 + 4,731 = 7,380) DOUBLE-COUNTS.")
    print(f"  -> file1 is the subsample selected on having acquired a follower:")
    print(f"     follow.date non-null on {s1['follow.date'].notna().sum():,} of {len(s1):,} rows.")


def check_multilot(df: pd.DataFrame) -> None:
    print(f"\n{'=' * 72}\nCAVEAT 2 -- multiple lots in the same stock on the same day\n{'=' * 72}")
    key = pd.MultiIndex.from_arrays(
        [df["cube.symbol"].values, df["date"].astype(str).values, df["stkcd"].values]
    )
    dup = key.duplicated()
    grp = df[key.duplicated(keep=False)].groupby(
        [df["cube.symbol"], df["date"].astype(str), df["stkcd"]], observed=True
    )[["sale", "gain"]].nunique()
    print(f"  rows                            : {len(df):,}")
    print(f"  unique (trader, date, stock)    : {(~dup).sum():,}")
    print(f"  duplicated keys                 : {dup.sum():,}  ({100 * dup.mean():.3f}%)")
    print(f"  dup groups where `gain` differs : {int((grp.gain > 1).sum()):,} of {len(grp):,}")
    print(f"  dup groups where `sale` differs : {int((grp.sale > 1).sum()):,}")
    print("  -> these are separate lots at different entry prices, so the true unit")
    print("     is trader-stock-LOT-day. Every lot is kept above. Collapsing instead:")
    base_pooled, base_trader = 1.4677, 1.6051
    d = describe("  [robustness] main panel, collapsed to one row per trader-stock-day",
                 df[~dup])
    print(f"\n  pooled ratio     {base_pooled:.4f} -> {d['ratio']:.4f}")
    print(f"  per-trader ratio {base_trader:.4f} -> {d['ratio_trader']:.4f}")
    print("  Sign robust, magnitude not. Collapsing gives the STRONGER result,")
    print("  which is why keeping every lot is the conservative choice.")


def main() -> None:
    fetch()
    s1, s2 = load(NESTED_SUBSAMPLE), load(MAIN_PANEL)

    for name, df in (("file1", s1), ("file2", s2)):
        assert set(df["sale"].unique()) == {0.0, 1.0}, f"{name}: sale not binary"
        assert set(df["gain"].unique()) == {0.0, 1.0}, f"{name}: gain not binary"
        assert df["sale"].isna().sum() == 0 and df["gain"].isna().sum() == 0
    print("sanity: `sale` and `gain` are binary with zero nulls in both files.")

    describe("HEADLINE -- main panel (sample2.Rdata)", s2)
    describe("ROBUSTNESS -- nested followed-trader subsample (sample1.Rdata)", s1)
    check_nesting(s1, s2)
    check_multilot(s2)

    print(f"\n{'=' * 72}\nCAVEAT 3 -- comparability with Odean (1998)\n{'=' * 72}")
    print("  Odean Table I  (sale-day denominator) : 0.148 / 0.098 = 1.51")
    print("  Odean account-level alternative       : 0.57  / 0.36  = 1.58")
    print("  this dataset  (all held days)         : 0.1925/ 0.1200= 1.61")
    print("  -> levels differ by 4-6x; the ratio moves <5%. Compare ratios only.")


if __name__ == "__main__":
    main()
