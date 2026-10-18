# Volatility-scaled momentum: real at factor scale, dead at five positions

A pre-registered test of whether scaling cross-sectional momentum by its own recent realised
volatility survives the constraints of a small retail account.

**It does not.** The mechanism is real — Sharpe 0.78 with t = 5.25 over 45.7 years of
survivorship-free data it was never fitted on. At five long positions, with real costs,
**buy-and-hold SPY beat every specification on risk-adjusted return** — and the two specifications
that did earn the returns would have tripped a 10% drawdown halt eleven and nine times in 13.75
years.

```bash
pip install -r requirements.txt
python reproduce_volmom.py
```

Part A runs in about a minute. Part B needs ~10 minutes on first run to fetch monthly closes for
1,209 tickers, then caches them. Both download their own data; nothing is shipped here but code.

---

## What was fixed before the data was touched

Three specifications, their parameters, the sample splits, the cost model and seven numeric kill
criteria, all written down first.

| | | Part A | Part B |
|---|---|---|---|
| **S1** | control, plain momentum | WML factor, monthly | top 5 by 12-1 return, equal weight |
| **S2** | volatility-scaled | scale by `0.12 / realised_vol` | same scaling on total exposure |
| **S3** | trend filter | hold only when the market index is above its 10-month average | hold a name only above its own average |

Ranking is 12-1 momentum: cumulative return from t−12 to t−1 months, skipping the most recent
month. Target volatility 12% annualised, volatility window 126 trading days. **Both values are
Barroso & Santa-Clara's own and were not tuned.** No parameter sweep was authorised: three
specifications, three tests, Bonferroni α = 0.05/3, so **nothing counts below |t| = 2.394.**

Splits, with the holdout evaluated once: Part A in-sample 1927-01…1980-12, **holdout
1981-01…2026-08 (548 months)**. Part B in-sample 1997-03…2012-12, **holdout 2013-01…2026-09 (165
months)**.

---

## Part A — survivorship-free, 1927–2026

Kenneth French's momentum factor, built from CRSP, which retains delisted firms. 1,196 monthly and
26,216 daily observations; zero rows dropped in parsing.

| Holdout, 1981–2026 (n=548) | ann return | **Sharpe** | max DD | worst month | **t** |
|---|---|---|---|---|---|
| S1 plain momentum | 5.75% | 0.37 | −57.8% | −34.4% | 2.49 |
| **S2 volatility-scaled** | **13.31%** | **0.78** | −27.8% | −20.6% | **5.25** |
| S3 trend filter | 4.99% | 0.47 | −26.0% | −12.6% | 3.18 |

**The mechanism is visible in the moments, not just the returns.** Plain momentum's holdout skew is
**−1.43** with kurtosis **13.22** — that is the crash risk. Volatility-scaled: skew **+0.05**,
kurtosis **5.07**. Scaling removes the crash asymmetry almost entirely. The extra return is not free
money; it is what you get for not being wiped out in the crash months.

### Three conventions, stated because the table does not divide

`Sharpe` is **not** `ann return / ann vol`, and S2's row is where you will notice: 13.31 / 16.16 =
0.82, against the 0.78 printed. Nothing is wrong. The annualised return compounds the arithmetic
monthly mean, `(1 + mean)^12 - 1`, while the Sharpe annualises linearly, `(mean / sd) * sqrt(12)`.
The two agree for small means and diverge as the mean grows, which is why S1 and S3 look fine and
S2 does not.

Two more, for anyone reimplementing: **realised volatility is Barroso & Santa-Clara's uncentred
RMS**, `sqrt(252 * mean(r^2))` — the daily mean is never subtracted, which is their published
formula. Using the centred sample standard deviation instead moves S2's annualised volatility by
+0.25pp and its holdout Sharpe from 0.777 to 0.776; no conclusion here turns on it. And **kurtosis
is raw, not excess** (normal = 3), computed over the sample standard deviation.


### Why believe the implementation

Checked against Barroso & Santa-Clara's window, on the common sample November 1927 – December 2011 (after the scaled strategy's warm-up; `verify/volmom.py` prints this table; on the paper's exact 1927:03–2011:12 window this code's 0.48 and 0.93 become 0.49 and 0.94):

| | this code | the paper |
|---|---|---|
| S1 Sharpe | 0.48 | 0.53 |
| **S2 Sharpe** | **0.93** | **0.97** |
| S2 max drawdown | −42.6% | −45.2% |
| S2 worst month | −29.0% | −28.4% |
| S1 worst month | **−52.6%** | **−79.0%** |

S2 reproduces closely. **S1's tail does not, and that is reported rather than hidden.** The likely
cause is construction — the paper builds WML from the six size-by-momentum portfolios while this
uses French's published `Mom` factor, and volatility scaling suppresses exactly the tail where the
two differ. **It has not been verified**, and S1 is the control, so the gap stays on the record.

### Part A's kill criteria, including one that cannot be answered

| | Criterion | Measured | |
|---|---|---|---|
| **K1a** | S2 holdout Sharpe >= 0.50 | **0.78** | PASS |
| **K1b** | S2 beats S1 by >= 0.15 Sharpe | **0.41** | PASS |
| **K2** | Probability of backtest overfitting <= 0.50 | **0.00 to 0.76** | **INDETERMINATE** |
| **K3** | Deflated Sharpe "<= 0" | 0.876 / 1.000 / 0.973 | **CANNOT FIRE** |

**K2 has no determinate answer, and that is a defect in the pre-registration rather than a result.**
The pre-registration fixed the threshold but never fixed which return matrix the statistic runs on.
It matters:

| PBO computed on | Value | K2 |
|---|---|---|
| In-sample 1927-11…1980-12 | **0.7638** | **FAIL** |
| Holdout 1981-01…2026-08 | 0.0000 | PASS |
| Common sample 1927-11…2026-08 | 0.0828 | PASS |

Same three specifications, same procedure, opposite verdicts. The underlying reason is that **PBO
has almost no resolution at three variants.** It was designed for sweeps of dozens to thousands; with
three columns the out-of-sample rank can only be 1, 2 or 3, so the rank statistic takes three values
and the estimate is nearly all noise. A number that swings from 0.00 to 0.76 on an unstated choice is
not evidence either way, and it is reported here as a range rather than as the single flattering
value.

**K3 could never have fired.** It was pre-registered as *"deflated Sharpe ratio <= 0 retires
everything"*, but the deflated Sharpe is a **probability in [0, 1]**, so the threshold is unreachable
by construction. The measured probabilities are reported above as descriptive statistics only. No
specification was retired by K3, because none could have been. Under the conventional > 0.95
threshold from Bailey & López de Prado, S2 would pass — **but that threshold was not pre-registered**,
and adopting it after seeing the numbers is exactly what a pre-registration exists to prevent. It is
recorded as an amendment, not as a clean pass.

### An independent reimplementation agrees

Part A was reimplemented a second time, from the pre-registration text alone, by someone who had not
read this code's computation. Every figure in both tables above — return, volatility, Sharpe, maximum
drawdown, worst month, t-statistic, skew and kurtosis, across both splits — reproduced to the printed
precision. That second implementation is in [`verify/`](verify/), and it is also what produces the
PBO range above.


---

## Part B — five positions, long only, real costs

Point-in-time S&P 500 membership from [`fja05680/sp500`](https://github.com/fja05680/sp500) (MIT),
2,720 dated snapshots, 1996–2026. Monthly closes from Yahoo. Constraints applied: 5 positions, long
only, minimum price $5, and a 0.20% cost charged on **each side** of every trade.

**The 10% drawdown halt is measured, not applied.** K6 was pre-registered as whether the holdout
*"would trip"* the halt more than three times, so trips are counted on the unhalted return series and
trading never actually stops. The consequence is visible in the table below: a −42.9% maximum
drawdown cannot occur under a rule that stops trading at −10%. An earlier version of this section
listed the halt among the applied constraints, which was wrong.

| Holdout 2013–2026 (n=165), 0.20% cost | ann return | **Sharpe** | max DD | **halt trips** |
|---|---|---|---|---|
| S1 plain momentum | 25.49% | 0.71 | −37.3% | **11** |
| S2 volatility-scaled | 10.57% | 0.66 | −24.6% | **2** |
| S3 trend filter | 25.69% | 0.71 | −42.9% | **9** |
| **SPY, buy and hold** | **16.05%** | **1.06** | **−23.9%** | **3** |

**The trade-off has no good corner.** S1 and S3 earn the returns and trip a 10% halt eleven and nine
times in 13.75 years — under a binding risk gate they stop trading constantly. S2 is holdable at two
trips and loses to buying the index and doing nothing.

In-sample was no better: **nothing reached t = 2**, and SPY's 0.42 Sharpe matched S2's 0.43.

### Costs are charged per side, and the pre-registration asked for both

`turnover` is the one-way fraction of the portfolio replaced, and the code charges
`cost x 2 x turnover` — so the 0.20% base case is **0.20% on each side, 0.40% round trip.** The
breakevens below are per-side figures for the same reason.

That is not a coding slip so much as a third defect in the pre-registration, alongside the two
already published above. It specified a **"base-case round-trip cost: 0.20% of notional, charged on
every entry and every exit"** — and those two halves contradict each other, because a round trip
*is* both sides. The code implemented one reading and an earlier version of this page published the
other.

### Kill criteria — no specification passes all four

| | K4 Sharpe ≥ 0.30 | K5 beats SPY | K6 ≤ 3 halt trips | K7 breakeven ≥ 0.50% round trip |
|---|---|---|---|---|
| S1 | 0.71 PASS | PASS | **11 FAIL** | 0.868% PASS |
| S2 | 0.66 PASS | **FAIL** | 2 PASS | **0.467% FAIL** |
| S3 | 0.71 PASS | PASS | **9 FAIL** | 0.866% PASS |

K7 names a **round trip**, so the per-side breakevens of 0.434%, 0.234% and 0.433% double to
**0.868%, 0.467% and 0.866%**. On those figures S1 and S3 clear K7 and fail only K6; S2 clears K6 and
fails K5 and K7. An earlier version of this page headed this section *"every specification fails at
least two"* and marked all three K7 cells FAIL, by comparing per-side breakevens against a
round-trip floor. That heading was false and is corrected here.

**The conclusion is unchanged: no specification passes all four, so no money moves.** What changed is
which criterion kills which specification.

---

## The limitation that matters most, measured rather than asserted

**Free price data cannot see the losers.**

| | in index | price fetched | coverage |
|---|---|---|---|
| **Current members** | 503 | 501 | **99.6%** |
| **Departed members** | 706 | 261 | **37.0%** |

Zero throttling across the whole fetch, so this is real absence and not a rate limit. At rebalance
dates, median index coverage is **52.6% in-sample and 84.8% in the holdout (re-run 16 Oct 2026; earlier runs printed 85.0%).**

**Every Part B return above is therefore an upper bound.** The names that cannot be fetched are
disproportionately the ones that failed.

The script prices delistings three ways — sold at the last print, Shumway (1997)'s −30%
performance-related delisting return, and total loss. **All three give identical results**, because
the delisted names are absent from the panel entirely rather than filtered out of it: the
survivorship problem lives at the fetch layer, not the selection layer. A top-5 momentum screen also
rarely selects a company about to be delisted for failure, since such a company has poor trailing
returns by then.

**One more reason to discount Part B:** 2013–2026 was a historic run for large-cap momentum. A
top-5 screen on US large caps over that window is largely a mega-cap technology bet. 25% annualised
with a −37% drawdown and eleven halt trips is the signature of a concentrated sector bet, not a
durable edge.

## Two declared deviations

Both forced by one oversight: the pre-registration specified **daily** windows and Part B has
monthly closes.

1. **S2's volatility estimate** uses trailing **12 monthly** returns annualised, not 126 daily ones.
   A 12-observation estimate is far noisier, so S2 is scaled more weakly here than in Part A.
   Leverage is capped at 3×.
2. **S3's trend filter** uses a **10-month** moving average, not a 200-day one.

Neither was chosen after seeing a result.

## What this establishes, and what it does not

**Does:** volatility-scaled cross-sectional momentum produced Sharpe 0.78 over 45.7 years of
survivorship-free data it was not fitted on, t = 5.25, and the overlay is the reason — it beat plain
momentum by 0.41 Sharpe and removed the crash skew.

**Does not:** that it is tradeable in a small account. Part A is a long-short factor across hundreds
of names with no costs and no constraints. **Every difference between that and five long positions
cuts the same way.** Part A says the mechanism exists. Only Part B speaks to holding it, and Part B
says no.

## References

- Barroso, P. & Santa-Clara, P. (2015). "Momentum has its moments." *Journal of Financial
  Economics* **116**(1), 111–120.
- Jegadeesh, N. & Titman, S. (1993). "Returns to Buying Winners and Selling Losers."
  *Journal of Finance* **48**(1), 65–91.
- Bailey, D. & López de Prado, M. (2014). "The Deflated Sharpe Ratio."
  *Journal of Portfolio Management* **40**(5).
- Shumway, T. (1997). "The Delisting Bias in CRSP Data." *Journal of Finance* **52**(1), 327–340.
- [Kenneth French data library](https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/data_library.html)
- [fja05680/sp500](https://github.com/fja05680/sp500) — dated membership table, MIT.
