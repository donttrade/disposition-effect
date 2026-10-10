# The disposition effect, measured on 4,731 retail traders

**76% of individual traders sold their winners more readily than their losers.**

A PGR/PLR replication of Odean (1998) on free, CC0, openly downloadable data.
One script, no model, nothing to tune. Runs in about ten minutes including the
download.

```bash
pip install -r requirements.txt
python reproduce.py
```

---

## Result

Main panel — 4,731 traders, 2,780,879 trader-stock-lot-days, 3,501 stocks,
24 June 2016 to 27 March 2018.

| | PGR | PLR | Ratio |
|---|---|---|---|
| Pooled over all observations | 0.078536 | 0.053510 | **1.4677** |
| Per trader, then averaged | 0.192529 | 0.119952 | **1.6051** |

**3,547 of the 4,659 traders** who held at least one winner and at least one
loser — so that both measures are defined — realised gains more readily than
losses. That is **76.1%**.

Paired t = 33.542 · Cohen's d = 0.4914 · binomial p = 5.64e-293.

For reference, Odean (1998) reported PGR 0.148 / PLR 0.098 — "a little over
1.5" — on 10,000 discount-brokerage accounts, 1987–1993. **Read the
denominator note below before putting those levels next to these.**

---

## What is being measured

Each row of the data is one trader-stock-lot-day on which a position was held,
carrying two binary flags:

- `sale == 1` — the position was closed that day
- `gain == 1` — the position was in profit that day

```
PGR = mean(sale | gain == 1)     proportion of gains realised
PLR = mean(sale | gain == 0)     proportion of losses realised
```

If people were indifferent between closing a winner and closing a loser, these
would be roughly equal. They are not, and the gap is the disposition effect.

There is no model here and no parameter to choose. That is the point — there is
nowhere to hide a researcher degree of freedom.

---

## The data

> Xuejun Jin, Rui Li & Yu Zhu (2021). "Could social interaction reduce the
> disposition effect? Evidence from retail investors in a directed social
> trading network." *PLoS ONE* **16**(2): e0246759.
> <https://doi.org/10.1371/journal.pone.0246759>
>
> Replication files: <https://doi.org/10.7910/DVN/NI6SBJ> — **CC0 1.0**,
> unrestricted download, no request form.

The platform is **Xueqiu.com**, described by the authors as China's largest
social trading platform. Holdings are Shanghai and Shenzhen A-shares. The
dataset covers **4,732 traders**; the main panel file contains 4,731 of them.

`reproduce.py` fetches both files from Dataverse on first run. They are not
committed here. See `DATA_LICENSE.md`.

**Jin, Li and Zhu never report PGR or PLR** — they report hazard and odds
ratios from survival and logistic models. So this measurement appears to be new
on their data, though it is arithmetic rather than anything clever.

---

## Three caveats, all checked by the script

### 1. The dataset's two files are nested, not independent

It is tempting to treat them as two samples and report both. They are not
independent:

| | |
|---|---|
| Traders in file 1 also in file 2 | **2,648 of 2,649 — 100.0%** |
| Stocks in file 1 also in file 2 | **all 3,468** |
| Union of traders across both | **4,732** |

File 1 is the subsample of traders **selected on having acquired at least one
follower** — `follow.date` is non-null on all 1,727,202 of its rows, because it
exists for the paper's pre/post-follow design. Selecting on being followed is
selecting on a behavioural variable.

It gives **1.7485** per trader — same sign, larger magnitude. Treated here as a
robustness check and **not** a replication.

Adding the two trader counts to claim 7,380 traders double-counts the subset.

### 2. Multiple lots in the same stock on the same day

**4,873 rows (0.175%)** share a (trader, date, stock) key with another row. In
**4,028 of 4,845** such groups the `gain` flag *disagrees* — two lots opened at
different prices, one in profit and one under water. `sale` never disagrees.

So the real unit is trader-stock-**lot**-day, and every lot is kept.

Collapsing to one row per trader-stock-day instead:

| | Kept (default) | Collapsed |
|---|---|---|
| Pooled ratio | 1.4677 | 1.5791 |
| Per-trader ratio | **1.6051** | **1.7764** |
| Share with PGR > PLR | 76.1% | 78.8% |

Robust in sign, sensitive in magnitude. The collapsed treatment gives the
*stronger* result, which is exactly why keeping every lot is the conservative
choice — and why the alternative is reported rather than quietly discarded.

### 3. These levels are not comparable to Odean's. Only the ratio is.

Odean counted only days on which a sale occurred somewhere in the account. In
his words: *"On days when no sales take place in an account, no gains or losses,
realized or paper, are counted."*

This dataset's unit is **every held day**, so PGR and PLR here are daily
hazards: P(close today | in profit today). That is the authors' design, not a
choice imposed on it.

The difference is large, and Odean's own paper shows how large — his
account-level alternative on the same data gives PGR 0.57 / PLR 0.36:

| Convention | PGR / PLR | Ratio |
|---|---|---|
| Odean, Table I (sale-day denominator) | 0.148 / 0.098 | **1.51** |
| Odean, account-level alternative | 0.57 / 0.36 | **1.58** |
| This dataset (all held days) | 0.1925 / 0.1200 | **1.61** |

**Levels move by a factor of four to six. The ratio moves under 5%.** Ratios
survive the change of denominator; levels do not. Be suspicious of anyone
putting a PGR level from one study beside a PGR level from another without
saying which denominator each used.

---

## What this does not show

- **It measures the problem, not a fix.** Nothing here says whether anything
  corrects the disposition effect.
- **Chinese A-shares, mid-2016 to early 2018, one platform.** Whether it holds
  for North American retail today is an assumption, not a result.
- **Social-trading users are a selected population.** Xueqiu cube operators
  chose to run public portfolios.
- **I did not collect this data.** It is someone else's replication file,
  released CC0. The contribution is the computation and publishing it.
- **The pooled and per-trader ratios differ** (1.4677 vs 1.6051) because the
  denominators differ. Both are reported. Quoting one without the other is
  picking.
- **Significance is not effect size.** The t-statistics are enormous because n
  is enormous. Cohen's d of 0.49 is the honest magnitude: moderate, not
  overwhelming.

---

## Reproducing just the headline

If you want the two numbers without running the whole script:

```bash
curl -sL "https://dataverse.harvard.edu/api/access/datafile/4053809" -o sample2.Rdata
pip install pyreadr
```

```python
import pyreadr
df = list(pyreadr.read_r("sample2.Rdata").values())[0]
print(df[df.gain == 1].sale.mean(), df[df.gain == 0].sale.mean())
```

Expected: `0.07853608...` and `0.05351043...`

There are no nulls in either column, so there is nothing to drop first.

If you get anything else, open an issue — I want to know.

---

## References

- Odean, T. (1998). "Are Investors Reluctant to Realize Their Losses?"
  *Journal of Finance* **53**(5), 1775–1798.
  [PDF](https://faculty.haas.berkeley.edu/odean/papers/disposition/disposit.pdf)
- Jin, X., Li, R. & Zhu, Y. (2021). *PLoS ONE* **16**(2): e0246759.
  <https://doi.org/10.1371/journal.pone.0246759>
- An, L., Engelberg, J., Henriksson, M., Wang, B. & Williams, J. (2024).
  "The Portfolio-Driven Disposition Effect." *Journal of Finance* **79**(5).
  <https://doi.org/10.1111/jofi.13378>
- Fischbacher, U., Hoffmann, G. & Schudy, S. (2017). "The Causal Effect of
  Stop-Loss and Take-Gain Orders on the Disposition Effect." *Review of
  Financial Studies* **30**(6), 2110–2129. *(Note: a corrigendum exists at RFS
  31(9), 3687–3688, doi:10.1093/rfs/hhy056, which I have not been able to
  retrieve — treat figures from this paper as provisional.)*

---

## Also in this repository

Three further studies. Each is independent of the disposition-effect replication above and of each
other, each has its own README, its own result and its own caveats, and each downloads its own
free data.

**[`form4/`](form4/) — SEC Form 4 insider-cluster returns, 2006–2026.** Do stocks outperform after
several insiders buy in the same week, and does the effect still exist? Built from the SEC's free
quarterly bulk files. **The tradable version of the effect was mostly 2008–09.**

**[`pdde/`](pdde/) — the portfolio-driven disposition effect.** A pre-registered replication of An,
Engelberg, Henriksson, Wang & Williams (*Journal of Finance*, 2024) on free CC0 data.
**It replicates** — a ratio of 2.041 on the pre-specified specification and 3.013 under trader-day
fixed effects, with placebos collapsing to about 1.05.

**[`volmom/`](volmom/) — volatility-scaled momentum, and why it is not tradeable in a small
account.** A pre-registered test with its kill criteria fixed in advance. The mechanism is real at
factor scale — Sharpe 0.78, t = 5.25, over 45.7 years of survivorship-free data it was never fitted
on. **At five long positions with real costs and a 10% drawdown halt, buy-and-hold SPY beat every
specification.** A negative result, published with the code.

The disposition-effect replication described above is unchanged and independent of all three.
