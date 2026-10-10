# The portfolio-driven disposition effect, on free CC0 data

A pre-registered replication of An, Engelberg, Henriksson, Wang & Williams, *The Portfolio-Driven
Disposition Effect* — the disposition effect is concentrated when an investor's **portfolio** is at a
loss and nearly vanishes when it is at a gain.

Same CC0 panel as the study in the root of this repository: Jin, Li & Zhu (2021), *PLoS ONE* 16(2),
replication files doi:10.7910/DVN/NI6SBJ. The script downloads it.

```
pip install pyreadr pandas numpy scipy
python reproduce_pdde.py
```

## Result: replicated

| # | Specification | Interaction | t | Ratio | 95% CI |
|---|---|---|---|---|---|
| **1** | **Pre-specified: trader FE** | **−0.024977** | −14.30 | 2.041 | [1.862, 2.220] |
| 2 | + 428 date FE | −0.025084 | −14.61 | 2.041 | — |
| 3 | + portfolio size | −0.021841 | −13.11 | 1.862 † | — |
| 4 | + size, holding period, activity, market | −0.018651 | −12.37 | 1.856 † | [1.689, 2.023] |
| 5 | `ret` portfolio index | −0.028726 | −14.27 | 2.065 | [1.876, 2.254] |
| **7** | **Trader-day FE — strictest** | **−0.023752** | **−9.63** | **3.013** | **[2.442, 3.584]** |

† at sample means; specifications 3 and 4 interact with continuous controls, so the ratio has no
single value. Outcome is whether the position was closed that day. Errors clustered by trader.
**Only specification 1 was pre-registered.**

**The strictest specification gives the largest ratio.** Trader-day fixed effects absorb every
trader-day confound in levels — portfolio size, holding period, activity, the trader's actual book
that day, everything. Under it the ratio is **3.013, CI [2.442, 3.584]**, which excludes the
pre-registered 2.00 bar and is **1.22 standard deviations** from An et al.'s own regression figure of
**3.368** (0.293% at a portfolio loss against 0.087% at a gain, their Table 2 Panel A col 5).

## The placebos, which are the point

**Parity placebo.** Build the identical share from a column that cannot matter — whether the
trader's other stock codes end in an even digit. Returns **−0.005434, t −4.06**, 21.8% of the
headline. Adding size, holding-period and activity controls takes it to **−0.001012, t −0.91** while
the real interaction holds at **−0.018651, t −12.37**.

**But that placebo cannot test the thing that matters.** It is independent of gain composition by
design, so it is structurally blind to any trader-day variable that moves with *how many* of the
trader's holdings are up — their real portfolio return, attention, margin pressure.

**Foreign-portfolio placebo.** Permute the other positions' gain count across trader-days within
(date, portfolio size, own gain). This keeps the date, the size and the exact mechanical coupling to
the position's own flag; it removes only whether it is *this* trader's book. The share stays in
[0, 1] by construction, so nothing is filtered — a filter here would correlate with the variable
under test.

| Design | Real | Placebo (3 seeds) |
|---|---|---|
| Trader FE | −0.024977 | −0.003015 / −0.003168 / −0.003315 — **12–13%** |
| **Trader-day FE** | **−0.023752 (ratio 3.013)** | **ratio 1.057 / 1.035 / 1.083** |

**Without trader-day effects the placebo retains 12–13% of the interaction, so that much of the
uncontrolled headline is structural.** Under trader-day fixed effects the placebo collapses to a
ratio of about 1.05 — no effect — while the real variable gives 3.013. **That contrast is the
evidence that this is behavioural and not mechanical.**

## What identifies this

`frac_excl = (k − own flag)/(n − 1)`, so within a trader-day a winner's share always sits below a
loser's. The two **off-diagonal** cells of the 2×2 — 718,973 rows, 33.06% — are the entire
difference-in-differences contrast. Drop them and the rank of `[gain, PG, gxPG]` falls to **1 of 3**
and nothing is identified. *An earlier version of this README described those rows as "contributing
nothing", which was exactly backwards.*

Exclusions: 325,039 single-position rows (11.69%), 280,771 ties (10.10%). **78.22% survives —
2,175,069 position-days, 4,482 of 4,731 traders.**

## Limitations

**1. The conditioning variable is a count, not a value-weighted return.** An et al. condition on
magnitude. A binary count-share is a noisy proxy, and classification error attenuates the interaction
toward zero — which is one reason specifications 1–5 sit below specification 7.

**2. Neither conditioning variable is independent of the focal position.** The count is dependent by
construction. `ret` (specification 5) is a portfolio index and therefore contains the focal position
too: regressing it on the position's own flag gives **+0.051066**.

**3. The pre-registration named a statistic it then could not pin down.** §6 required "the `PGR − PLR`
gap at least 2× larger" and §5 pre-specified two ways to compute it: pooled gives **4.420**,
per-trader gives **0.857 — the opposite direction**. The regression ratio used above is a third
statistic the pre-registration never named.

**4. The tie exclusion is asymmetric, not merely non-random.** A tie needs an even number of other
holdings split in half, so it occurs only on odd-sized days — all 280,771 excluded rows have an odd
count. It also removes more winners than losers.

**5. At two positions the design is degenerate.** In a mixed pair the winner is necessarily labelled
portfolio-down and the loser portfolio-up. That stratum is 20.6% of the sample.

**6. Chinese A-shares, one social-trading platform, June 2016 to March 2018**, a population selected
twice over. This measures the effect and tests no remedy for it.

## Pre-specified vs not

Specification 1, the exclusion ladder, the lot-level unit, trader clustering and the four outcome
thresholds were fixed before the data was opened. **Specifications 2–8, every control and both
placebos are not pre-registered** and are labelled so in the output.

## Review history

Stress-tested three times by independent adversarial passes that recomputed every figure from the raw
data with their own code. They found four, then seven, then eleven blocking errors — several of them
new errors introduced inside the fixes for earlier ones. Every figure reproduced exactly on every
pass; the failures were all in interpretation. Two corrections are stated in the text above rather
than quietly made, and specification 7 exists because the third pass pointed out it had never been
run.
