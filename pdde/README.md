# The portfolio-driven disposition effect, on free CC0 data

A pre-registered replication of An, Engelberg, Henriksson, Wang & Williams,
*The Portfolio-Driven Disposition Effect* — the finding that the disposition effect is concentrated
when an investor's **portfolio** is at a loss and nearly vanishes when it is at a gain.

It runs on the same CC0 panel as the study in the root of this repository: Jin, Li & Zhu (2021),
*PLoS ONE* 16(2), replication files doi:10.7910/DVN/NI6SBJ. The script downloads the file itself.

```
pip install pyreadr pandas numpy scipy
python reproduce_pdde.py
```

About ten minutes including the download.

## Result

| | |
|---|---|
| Analysis sample | 2,175,069 rows (78.2% of 2,780,879), 4,482 of 4,731 traders |
| `gain × PortfolioGain` | **−0.024977** (SE 0.001747, t −14.298, p 2.2e-45) |
| Disposition gap, portfolio **down** | **+0.048971** |
| Disposition gap, portfolio **up** | **+0.023994** |
| Ratio | **2.04×** |

Trader fixed effects, standard errors clustered by trader across 4,482 clusters.

**Verdict against thresholds fixed before the data was opened: replicated — barely.** 2.04× clears a
2.00× bar by 0.04. A bar of 2.1, equally defensible in advance, would have given "weak replication."

## The three things this README will not bury

**1. The pre-registration had a hole in it.** It required the gap to be "at least 2× larger" in the
portfolio-loss state and never said *which* gap. The three available measures disagree:

| Measure | Ratio | Implies |
|---|---|---|
| Pooled | 4.42× | replicated |
| **Per-trader** | **0.86×** | **the other direction** |
| Within-trader (the regression) | 2.04× | replicated |

The case for the within-trader measure is that the primary test *is* that regression, and per-trader
averages compare partly different people — 3,361 traders appear in the down cell against 4,214 in the
up cell. That reasoning is correct and it is **post hoc**. It was not written down in advance.

**2. The conditioning variable is a count, not a value-weighted return.** The panel has no position
weights. One holding up 1% and one down 40% is a 50/50 tie and is dropped — 10.1% of all rows. This is
the central gap against An et al., who use a portfolio return, and it is unresolved.

**3. The effect is much weaker than the paper it replicates.** An et al. find roughly 4–10×. This is
2.04×, at or below the bottom of their range. Levels are not comparable at all: these are percentage
points against their basis points, because the denominator here is a daily hazard of closing a
position.

## What is pre-specified and what is not

Everything above is pre-specified. One check is **exploratory**, added after the result and marked as
such in the output: absorbing 428 date fixed effects alongside trader effects, to test whether
`PortfolioGain` is really proxying *market* state on days when everything is up. Two-way by
alternating projections iterated to convergence. **100.4% of the interaction is retained** — the
market-wide explanation does not hold.

## The design decision the whole thing rests on

Portfolio state is computed **leave-one-out**, excluding the focal position. The focal position's own
`gain` is part of any naive portfolio measure built from the same column, which would mechanically
correlate the conditioning variable with what is being conditioned on and produce a strong, entirely
spurious interaction **that would look exactly like a successful replication**. Single-position
trader-days are therefore undefined and excluded.

## Why `ret` is not used

The delivered file has fourteen columns, including `ret`, which would have allowed a better
conditioning variable. It is a gross ratio (1.0 = breakeven), but it does not reproduce `gain`:
agreement is 66.3% at `ret > 0` and 62.7% at `ret > 1`. Whatever it measures, it is not the position's
profit state as this study defines it, and the files carry no codebook. 272 rows have `ret <= 0`,
impossible for a price ratio, with a minimum of −2767.49; 2.16% are null.

Reading the source paper's variable definitions would settle it. That has not been done.

## Limitations

- Chinese A-shares, one social-trading platform, 24 June 2016 – 27 March 2018. The population is
  selected twice over. Nothing here is a claim about retail investors generally.
- `gain` is binary, so a portfolio marginally up and one hugely up are the same state.
- The tie exclusion is not random with respect to portfolio size: a tie needs an even number of other
  positions split exactly in half, so it can only occur on days with an odd total position count.
- This measures the effect. It tests no remedy for it.
