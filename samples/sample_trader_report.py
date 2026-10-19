#!/usr/bin/env python3
"""
Sample trader report from real, public, reproducible data.

Picks ONE trader from the main panel of the CC0 Xueqiu dataset behind the
donttrade disposition-effect study (Jin, Li & Zhu 2021, Harvard Dataverse
doi:10.7910/DVN/NI6SBJ, file 4053809 = sample2.Rdata) and computes that
trader's disposition-effect numbers with the study's definitions
(reproduce.py in github.com/donttrade/disposition-effect).

Selection rule (fixed before any individual result was looked at; it uses
only the number of sell-days, never PGR/PLR):
    Eligible = traders with at least 30 sell-days.
    A sell-day = a calendar date on which the trader closed at least one
    position (any row with sale == 1).
    Sort eligible traders by sell-days; the median value is the value at
    position (n-1)//2 (the lower middle if n is even).
    Among traders with exactly that many sell-days, take the lowest ID.

Definitions (as in reproduce.py; unit = trader-stock-lot-day held):
    realised gain  : gain == 1 and sale == 1
    paper gain     : gain == 1 and sale == 0
    realised loss  : gain == 0 and sale == 1
    paper loss     : gain == 0 and sale == 0
    PGR = RG / (RG + PG)       PLR = RL / (RL + PL)
    Odean (1998) standard error of PGR - PLR:
        sqrt( PGR(1-PGR)/(RG+PG) + PLR(1-PLR)/(RL+PL) )

Usage:
    python sample_trader_report.py [path/to/sample2.Rdata]
Prints every number shown on the page, and writes
    sample_trader_report.html   (HTML body fragment, site classes only)
    sample_trader_report.md     (Markdown version)
next to this script.
"""

from __future__ import annotations

import math
import os
import sys
import urllib.request
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
DATA_URL = "https://dataverse.harvard.edu/api/access/datafile/4053809"
USER_AGENT = "donttrade-reproduce/1.0 (+https://github.com/donttrade/disposition-effect)"
CANDIDATES = [HERE / "sample2.Rdata"]

REPO = "https://github.com/donttrade/disposition-effect"
METHOD = "/research/disposition-effect/"
MIN_SELL_DAYS = 30

# Published panel figures (README, per trader then averaged) to reproduce first.
PUBLISHED = {"pgr": 0.1925, "plr": 0.1200, "ratio": 1.61}


# ---------------------------------------------------------------- data
def locate(argv: list[str]) -> Path:
    if len(argv) > 1:
        return Path(argv[1])
    for p in CANDIDATES:
        if p.exists():
            return p
    dest = HERE / "sample2.Rdata"
    print(f"downloading {DATA_URL} -> {dest}", file=sys.stderr)
    req = urllib.request.Request(DATA_URL, headers={"User-Agent": USER_AGENT})
    tmp = str(dest) + ".part"
    with urllib.request.urlopen(req, timeout=300) as r, open(tmp, "wb") as fh:
        while chunk := r.read(1 << 20):
            fh.write(chunk)
    os.replace(tmp, dest)
    return dest


def load(path: Path) -> pd.DataFrame:
    import pyreadr

    d = pyreadr.read_r(str(path))
    df = d[list(d.keys())[0]]
    assert set(df["sale"].unique()) == {0.0, 1.0} and set(df["gain"].unique()) == {0.0, 1.0}
    assert df["sale"].isna().sum() == 0 and df["gain"].isna().sum() == 0
    df = df.rename(columns={"cube.symbol": "trader"})
    df["date"] = pd.to_datetime(df["date"])
    return df


# ---------------------------------------------------------------- measures
def counts_table(df: pd.DataFrame) -> pd.DataFrame:
    """Per-trader RG, PG, RL, PL (lot-days)."""
    g = df.assign(
        rg=((df.gain == 1) & (df.sale == 1)).astype(int),
        pg=((df.gain == 1) & (df.sale == 0)).astype(int),
        rl=((df.gain == 0) & (df.sale == 1)).astype(int),
        pl=((df.gain == 0) & (df.sale == 0)).astype(int),
    ).groupby("trader", observed=True)[["rg", "pg", "rl", "pl"]].sum()
    with np.errstate(divide="ignore", invalid="ignore"):
        g["pgr"] = g.rg / (g.rg + g.pg)
        g["plr"] = g.rl / (g.rl + g.pl)
    return g


def odean(rg: int, pg: int, rl: int, pl: int) -> dict:
    pgr = rg / (rg + pg)
    plr = rl / (rl + pl)
    se = math.sqrt(pgr * (1 - pgr) / (rg + pg) + plr * (1 - plr) / (rl + pl))
    diff = pgr - plr
    return {"pgr": pgr, "plr": plr, "ratio": pgr / plr if plr > 0 else math.inf,
            "diff": diff, "se": se, "t": diff / se}


# ---------------------------------------------------------------- main
def main() -> None:
    path = locate(sys.argv)
    df = load(path)
    print(f"data file                : {path}")
    print(f"rows (trader-stock-lot-days): {len(df):,}")
    print(f"traders in panel         : {df.trader.nunique():,}")

    # ---- 1. panel cross-check, BEFORE any per-trader number is trusted
    ct = counts_table(df)
    both = ct.dropna(subset=["pgr", "plr"])
    panel_pgr, panel_plr = both.pgr.mean(), both.plr.mean()
    panel_ratio = panel_pgr / panel_plr
    pooled_pgr = df.loc[df.gain == 1, "sale"].mean()
    pooled_plr = df.loc[df.gain == 0, "sale"].mean()
    print("\n== PANEL CROSS-CHECK (published: per-trader PGR 0.1925, PLR 0.1200, ratio 1.61)")
    print(f"per-trader-then-averaged PGR {panel_pgr:.6f}  PLR {panel_plr:.6f}  ratio {panel_ratio:.4f}"
          f"   (traders with both defined: {len(both):,})")
    print(f"pooled                   PGR {pooled_pgr:.6f}  PLR {pooled_plr:.6f}  ratio {pooled_pgr / pooled_plr:.4f}")
    assert round(panel_pgr, 4) == PUBLISHED["pgr"], panel_pgr
    assert round(panel_plr, 4) == PUBLISHED["plr"], panel_plr
    assert round(panel_ratio, 2) == PUBLISHED["ratio"], panel_ratio
    print("cross-check: PASS (matches to the published precision)")

    # ---- 2. selection: uses sell-day counts ONLY
    sell_days = df.loc[df.sale == 1].groupby("trader", observed=True)["date"].nunique()
    eligible = sell_days[sell_days >= MIN_SELL_DAYS]
    srt = eligible.sort_values(kind="mergesort")
    n_elig = len(srt)
    med_value = int(srt.iloc[(n_elig - 1) // 2])
    tied = sorted(eligible[eligible == med_value].index)
    chosen = tied[0]
    print("\n== SELECTION")
    print(f"traders with >= {MIN_SELL_DAYS} sell-days : {n_elig:,}")
    print(f"median sell-days (lower middle) : {med_value}")
    print(f"traders tied at the median      : {len(tied)}  -> lowest ID {chosen}")

    # ---- 3. this trader
    t = df[df.trader == chosen]
    c = ct.loc[chosen]
    rg, pg, rl, pl = (int(c[k]) for k in ("rg", "pg", "rl", "pl"))
    o = odean(rg, pg, rl, pl)
    first, last = t.date.min(), t.date.max()
    n_stocks = t.stkcd.nunique()
    n_held = len(t)
    n_sells = rg + rl
    act_months = t.date.dt.to_period("M").nunique()
    span_months = (last.year - first.year) * 12 + last.month - first.month + 1
    print("\n== TRADER", chosen)
    print(f"period held              : {first:%Y-%m-%d} -> {last:%Y-%m-%d}")
    print(f"sell-days                : {int(sell_days[chosen])}")
    print(f"positions closed (lot-days with a sale): {n_sells}")
    print(f"distinct stocks          : {n_stocks}")
    print(f"calendar months with data: {act_months} of {span_months}")
    print(f"position-days held (rows): {n_held:,}")
    print(f"realised gains RG        : {rg:,}")
    print(f"paper gains    PG        : {pg:,}")
    print(f"realised losses RL       : {rl:,}")
    print(f"paper losses   PL        : {pl:,}")
    print(f"PGR = RG/(RG+PG)         : {o['pgr']:.4f}")
    print(f"PLR = RL/(RL+PL)         : {o['plr']:.4f}")
    print(f"PGR/PLR                  : {o['ratio']:.2f}")
    print(f"PGR - PLR                : {o['diff']:.4f}")
    print(f"Odean SE                 : {o['se']:.4f}")
    print(f"t                        : {o['t']:.2f}")

    # ---- 4. where you stand: ratio percentile among eligible traders
    grp = ct.loc[eligible.index].dropna(subset=["pgr", "plr"]).copy()
    with np.errstate(divide="ignore"):
        grp["ratio"] = np.where(grp.plr > 0, grp.pgr / grp.plr, np.inf)
    others = grp.drop(index=chosen)
    lower = int((others.ratio < o["ratio"]).sum())
    ties = int((others.ratio == o["ratio"]).sum())
    pct = 100 * (lower + 0.5 * ties) / len(others)
    above1 = int((grp.ratio > 1).sum())
    grp_median = float(grp.ratio.median())
    print("\n== WHERE THIS TRADER STANDS (PGR/PLR ratio)")
    print(f"comparison group (>= {MIN_SELL_DAYS} sell-days, both PGR and PLR defined): {len(grp):,}")
    print(f"  of whom with PLR == 0 (ratio infinite): {int(np.isinf(grp.ratio).sum())}")
    print(f"others with a lower ratio: {lower:,}  ties: {ties}  of {len(others):,}")
    print(f"percentile               : {pct:.1f}  -> rounded {round(pct)}")
    print(f"group median ratio       : {grp_median:.2f}")
    print(f"group with ratio > 1     : {above1:,} of {len(grp):,} = {100 * above1 / len(grp):.1f}%")

    v = dict(
        id=chosen, n_elig=n_elig, med=med_value, n_tied=len(tied),
        first=f"{first:%-d %b %Y}", last=f"{last:%-d %b %Y}", act_months=act_months, span_months=span_months,
        sell_days=int(sell_days[chosen]), n_sells=n_sells, n_stocks=n_stocks, n_held=n_held,
        rg=rg, pg=pg, rl=rl, pl=pl, **o,
        pct=pct, pct_r=round(pct), n_grp=len(grp), grp_median=grp_median,
        above1=above1, above1_pct=100 * above1 / len(grp),
        panel_pgr=panel_pgr, panel_plr=panel_plr, panel_ratio=panel_ratio,
        n_both=len(both),
    )
    (HERE / "sample_trader_report.html").write_text(render_html(v))
    (HERE / "sample_trader_report.md").write_text(render_md(v))
    print(f"\nwrote {HERE / 'sample_trader_report.html'}")
    print(f"wrote {HERE / 'sample_trader_report.md'}")


# ---------------------------------------------------------------- text
def ordinal(n: int) -> str:
    suf = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def words(v: dict) -> dict:
    """Plain-English pieces shared by HTML and Markdown."""
    ratio = v["ratio"]
    if ratio > 1:
        head = (f"Trader {v['id']} sold winning positions {ratio:.2f} times as readily as losing ones: "
                f"a milder lean than {100 - v['pct_r']}% of comparable traders"
                if v['pct'] < 50 else
                f"Trader {v['id']} sold winning positions {ratio:.2f} times as readily as losing ones: "
                f"a stronger lean than {v['pct_r']}% of comparable traders")
        lean = "sold winners more readily than losers"
    else:
        head = (f"Trader {v['id']} sold losing positions at least as readily as winning ones "
                f"(ratio {ratio:.2f})")
        lean = "did not sell winners more readily than losers"
    head += "."
    if abs(v["t"]) < 2:
        clear = ("With this few observations, a gap this size could easily be chance (a t below about 2 "
                 "is usually read that way), so the lean is suggestive rather than clear.")
    else:
        clear = "A t of 2 or more is usually read as a gap too large to put down to chance alone."
    pgr_pct, plr_pct = 100 * v["pgr"], 100 * v["plr"]
    pgr_1in = 1 / v["pgr"] if v["pgr"] > 0 else math.inf
    plr_1in = 1 / v["plr"] if v["plr"] > 0 else math.inf
    return dict(head=head, lean=lean, clear=clear, pgr_pct=pgr_pct, plr_pct=plr_pct,
                pgr_1in=pgr_1in, plr_1in=plr_1in)


LABEL = ("Sample report: a real trader from a public CC0 research dataset "
         "(pseudonymous ID {id}), not a donttrade customer.")


def strip_svg(v: dict) -> str:
    """Percentile strip: where this trader's ratio sits in the comparison group."""
    W, H, x0, x1 = 640, 92, 16, 624
    X = lambda p: x0 + (x1 - x0) * p / 100
    px = X(v["pct"])
    return f"""<svg viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" aria-label="Trader {v['id']} sits at the {ordinal(v['pct_r'])} percentile of {v['n_grp']:,} traders with at least {MIN_SELL_DAYS} sell-days and both a PGR and a PLR defined, on the PGR/PLR ratio">
  <rect x="{x0}" y="34" width="{x1 - x0}" height="14" rx="2" fill="var(--surface)" stroke="var(--border-hairline)"/>
  <rect x="{x0}" y="34" width="{px - x0:.0f}" height="14" rx="2" fill="var(--chart-1)" opacity="0.35"/>
  <line x1="{px:.0f}" y1="24" x2="{px:.0f}" y2="58" stroke="var(--chart-1)" stroke-width="3"/>
  <text x="{px:.0f}" y="16" text-anchor="{'end' if v['pct'] > 75 else 'start' if v['pct'] < 25 else 'middle'}" font-family="system-ui,sans-serif" font-size="14" font-weight="600" fill="var(--text)">{v['id']}: {ordinal(v['pct_r'])} percentile</text>
  <text x="{x0}" y="78" font-family="system-ui,sans-serif" font-size="13" fill="var(--text-muted)">0 · lowest ratio</text>
  <text x="{x1}" y="78" text-anchor="end" font-family="system-ui,sans-serif" font-size="13" fill="var(--text-muted)">100 · highest ratio</text>
</svg>"""


def render_html(v: dict) -> str:
    w = words(v)
    return f"""<section id="sample-report" aria-labelledby="sample-report-h">
<p class="kicker">SAMPLE TRADER REPORT</p>
<div class="banner"><strong>{LABEL.format(id=v['id'])}</strong> Real, public, reproducible data. Not advice.</div>
<h2 id="sample-report-h" style="margin-top:24px">{w['head']}</h2>
<p class="lede">This is what the coming trader report looks like, run on one real trader’s history. Your own report would be computed the same way from your own trade export.</p>
<ul class="receipts">
  <li>{v['first']} – {v['last']}</li>
  <li>{v['sell_days']} sell-days</li>
  <li>{v['n_stocks']} different stocks</li>
  <li>{v['n_held']:,} position-days held</li>
</ul>

<h3>The four counts</h3>
<p>Every day this trader held a position, that position was either up (a gain) or down (a loss), and it was either sold that day or kept. That gives four counts. The data for this trader fall in {v['act_months']} of the {v['span_months']} calendar months between the first and last date, so the activity came in bursts.</p>
<div class="table-scroll"><table>
  <thead><tr><th scope="col"></th><th scope="col">Sold that day (realised)</th><th scope="col">Kept (paper)</th></tr></thead>
  <tbody>
    <tr><th scope="row">Position was up</th><td>{v['rg']:,} realised gains</td><td>{v['pg']:,} paper gains</td></tr>
    <tr><th scope="row">Position was down</th><td>{v['rl']:,} realised losses</td><td>{v['pl']:,} paper losses</td></tr>
  </tbody>
</table></div>

<h3>The numbers</h3>
<dl class="skeleton">
  <dt>PGR {v['pgr']:.4f}</dt>
  <dd><dfn>Proportion of gains realised.</dfn> Of all the days a position was up, the share on which it was sold: about {w['pgr_pct']:.1f}%.</dd>
  <dt>PLR {v['plr']:.4f}</dt>
  <dd><dfn>Proportion of losses realised.</dfn> Of all the days a position was down, the share on which it was sold: about {w['plr_pct']:.1f}%.</dd>
  <dt>Ratio {v['ratio']:.2f}</dt>
  <dd>PGR divided by PLR. Above 1 means winners were sold more readily than losers, a pattern called the disposition effect. Exactly 1 would mean no difference.</dd>
  <dt>Gap {v['diff']:.4f}</dt>
  <dd>PGR minus PLR, with Odean’s (1998) standard error of {v['se']:.4f}, so t = {v['t']:.2f}. {w['clear']}</dd>
</dl>

<h3>Where this trader stands</h3>
<p>Among the {v['n_grp']:,} traders in the same dataset with at least {MIN_SELL_DAYS} sell-days and both a PGR and a PLR defined, this trader’s ratio of {v['ratio']:.2f} is higher than that of about {v['pct_r']}% of them (the {ordinal(v['pct_r'])} percentile). The middle trader in that group has a ratio of {v['grp_median']:.2f}, and {v['above1_pct']:.0f}% of the group have a ratio above 1.</p>
<figure>
{strip_svg(v)}
<figcaption>Percentile of trader {v['id']}’s PGR/PLR ratio among {v['n_grp']:,} traders with at least {MIN_SELL_DAYS} sell-days and both a PGR and a PLR defined. Ties count half.</figcaption>
</figure>

<h3>What this means, and what it doesn’t</h3>
<ul class="risk">
  <li>It describes what this trader did in the past: they {w['lean']}. It says nothing about what they, or you, should do next.</li>
  <li>It is not advice. It is not a grade, and it is not a prediction of returns.</li>
  <li>It covers one trader, on one platform, in one market (Chinese A-shares), from {v['first']} to {v['last']}.</li>
  <li>Selling a winner is not always a mistake, and holding a loser is not always one either. The ratio shows a pattern, not the reason for it.</li>
  <li>The t-value treats every held day as a separate observation. Days of the same position are related, so treat it as a rough guide to how clear the gap is, not a precise test.</li>
</ul>

<h3>How it was computed</h3>
<ul>
  <li><strong>Data:</strong> Jin, Li &amp; Zhu (2021), <a href="https://doi.org/10.7910/DVN/NI6SBJ">Harvard Dataverse doi:10.7910/DVN/NI6SBJ</a>, file 4053809, CC0. Social-trading portfolios on Xueqiu, 2016–18, pseudonymous IDs.</li>
  <li><strong>How this trader was chosen</strong> (rule fixed before any individual result was looked at): among the {v['n_elig']:,} traders with at least {MIN_SELL_DAYS} sell-days, take the one with the median number of sell-days ({v['med']}; the lower middle value if the count is even); if several are tied, the lowest ID. {v['n_tied']} traders were tied; {v['id']} has the lowest ID. A sell-day is a date on which the trader closed at least one position.</li>
  <li><strong>Definitions:</strong> the same as the flagship study (Odean 1998, as coded in reproduce.py). Each row is one position held on one day; PGR and PLR are shares of those days, so they are daily rates and should only be compared with figures computed the same way.</li>
  <li><strong>Check first:</strong> before any per-trader number was used, the same code reproduced the study’s published panel figures: PGR {v['panel_pgr']:.4f}, PLR {v['panel_plr']:.4f}, ratio {v['panel_ratio']:.2f}, averaged over {v['n_both']:,} traders.</li>
  <li><a href="{METHOD}">Read the method →</a> · <a href="{REPO}/blob/main/reproduce.py">The public script (reproduce.py) →</a></li>
</ul>
<p class="fine">Every number on this page is printed by sample_trader_report.py, which uses the same definitions as reproduce.py.</p>
</section>
"""


def render_md(v: dict) -> str:
    w = words(v)
    return f"""# Sample trader report

> **{LABEL.format(id=v['id'])}** Real, public, reproducible data. Not advice.

## {w['head']}

This is what the coming trader report looks like, run on one real trader's history. Your own report would be computed the same way from your own trade export.

{v['first']} – {v['last']} · {v['sell_days']} sell-days · {v['n_stocks']} different stocks · {v['n_held']:,} position-days held

### The four counts

Every day this trader held a position, that position was either up (a gain) or down (a loss), and it was either sold that day or kept. The data for this trader fall in {v['act_months']} of the {v['span_months']} calendar months between the first and last date, so the activity came in bursts.

| | Sold that day (realised) | Kept (paper) |
|---|---|---|
| Position was up | {v['rg']:,} realised gains | {v['pg']:,} paper gains |
| Position was down | {v['rl']:,} realised losses | {v['pl']:,} paper losses |

### The numbers

- **PGR {v['pgr']:.4f}** — proportion of gains realised. Of all the days a position was up, the share on which it was sold: about {w['pgr_pct']:.1f}%.
- **PLR {v['plr']:.4f}** — proportion of losses realised. Of all the days a position was down, the share on which it was sold: about {w['plr_pct']:.1f}%.
- **Ratio {v['ratio']:.2f}** — PGR divided by PLR. Above 1 means winners were sold more readily than losers (the disposition effect). Exactly 1 would mean no difference.
- **Gap {v['diff']:.4f}** — PGR minus PLR, with Odean's (1998) standard error of {v['se']:.4f}, so t = {v['t']:.2f}. {w['clear']}

### Where this trader stands

Among the {v['n_grp']:,} traders in the same dataset with at least {MIN_SELL_DAYS} sell-days and both a PGR and a PLR defined, this trader's ratio of {v['ratio']:.2f} is higher than that of about {v['pct_r']}% of them (the {ordinal(v['pct_r'])} percentile; ties count half). The middle trader in that group has a ratio of {v['grp_median']:.2f}, and {v['above1_pct']:.0f}% of the group have a ratio above 1.

### What this means, and what it doesn't

- It describes what this trader did in the past: they {w['lean']}. It says nothing about what they, or you, should do next.
- It is not advice. It is not a grade, and it is not a prediction of returns.
- It covers one trader, on one platform, in one market (Chinese A-shares), from {v['first']} to {v['last']}.
- Selling a winner is not always a mistake, and holding a loser is not always one either. The ratio shows a pattern, not the reason for it.
- The t-value treats every held day as a separate observation. Days of the same position are related, so treat it as a rough guide to how clear the gap is, not a precise test.

### How it was computed

- **Data:** Jin, Li & Zhu (2021), Harvard Dataverse [doi:10.7910/DVN/NI6SBJ](https://doi.org/10.7910/DVN/NI6SBJ), file 4053809, CC0. Social-trading portfolios on Xueqiu, 2016–18, pseudonymous IDs.
- **How this trader was chosen** (rule fixed before any individual result was looked at): among the {v['n_elig']:,} traders with at least {MIN_SELL_DAYS} sell-days, take the one with the median number of sell-days ({v['med']}; the lower middle value if the count is even); if several are tied, the lowest ID. {v['n_tied']} traders were tied; {v['id']} has the lowest ID. A sell-day is a date on which the trader closed at least one position.
- **Definitions:** the same as the flagship study (Odean 1998, as coded in reproduce.py). Each row is one position held on one day; PGR and PLR are shares of those days, so they are daily rates and should only be compared with figures computed the same way.
- **Check first:** before any per-trader number was used, the same code reproduced the study's published panel figures: PGR {v['panel_pgr']:.4f}, PLR {v['panel_plr']:.4f}, ratio {v['panel_ratio']:.2f}, averaged over {v['n_both']:,} traders.
- [Read the method](https://donttrade.ca{METHOD}) · [The public script (reproduce.py)]({REPO}/blob/main/reproduce.py)

Every number on this page is printed by `sample_trader_report.py`, which uses the same definitions as `reproduce.py`.
"""


if __name__ == "__main__":
    main()
