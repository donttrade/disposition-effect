# The portfolio-driven disposition effect, on free CC0 data

A pre-registered replication of An, Engelberg, Henriksson, Wang & Williams, *The Portfolio-Driven
Disposition Effect* — the finding that the disposition effect is concentrated when an investor's
**portfolio** is at a loss and nearly vanishes when it is at a gain.

Same CC0 panel as the study in the root of this repository: Jin, Li & Zhu (2021), *PLoS ONE* 16(2),
replication files doi:10.7910/DVN/NI6SBJ. The script downloads it.

```
pip install pyreadr pandas numpy scipy
python reproduce_pdde.py
```

## Result

**Direction replicates. Magnitude is not established.**

| # | Specification | Interaction | t | Gap ratio | 95% CI |
|---|---|---|---|---|---|
| **1** | **Pre-specified: trader FE** | **−0.024977** | **−14.30** | **2.041** | [1.862, 2.220] |
| 2 | + 428 date fixed effects | −0.025084 | −14.61 | 2.041 | [1.864, 2.219] |
| 3 | + portfolio size | −0.021841 | −13.11 | 1.862 † | [1.706, 2.018] |
| 4 | + size, holding period, activity, market | −0.018651 | −12.37 | 1.856 † | [1.689, 2.023] |
| 5 | `ret` portfolio index, no exclusions | −0.028726 | −14.27 | 2.065 | [1.876, 2.254] |

† evaluated **at sample means**. Specifications 3 and 4 interact `gain` with continuous controls, so
the ratio has no single value — see below.

**Only specification 1 is pre-registered.** Standard errors clustered by trader throughout.

The interaction is negative with |t| > 12 in all five. **The ratio is not stable, and the
pre-registered verdict turns entirely on the ratio.** Applied literally, the rule returns
*replicated* (2.041 ≥ 2.00). But that point estimate has a CI containing 2.00, and so does every
other specification here.

## The placebo, and what it cost

Building the same leave-one-out share from an **irrelevant** column — the share of the trader's other
positions whose stock code ends in an even digit — should return nothing. It returns
**−0.005434, t = −4.06**.

That is 22% of the headline magnitude, from a variable that cannot possibly matter.

The cause is identifiable. Portfolio state correlates with portfolio size, holding period and trader
activity, and all three modulate the disposition gap independently. Controlling for them
(specification 4):

| | Uncontrolled | Controlled |
|---|---|---|
| **Placebo** interaction | −0.005434 (t −4.06) | **−0.001012 (t −0.91)** |
| **Real** interaction | −0.024977 (t −14.30) | **−0.018651 (t −12.37)** |

**The placebo goes to null and 75% of the real effect survives at t beyond −12.** That is the
strongest evidence here that the finding is behavioural rather than mechanical — and it also means
the uncontrolled headline is inflated.

## Two corrections to earlier versions of this README

**1. What `ret` is, and what it is not.** An earlier version called it a position-level gross price
ratio and discarded it. It is a **trader-day** series — the portfolio net-value index; 0 of 951,885
trader-days carry more than one value. A later version then claimed it is *"immune by construction"*
to dependence on the focal position. **That is also wrong, and is the same category error.** A
portfolio index contains the focal position. Measured: regressing it on own `gain` with trader fixed
effects gives **+0.051066**. **Neither conditioning variable in this repository is independent of the
focal position.**

**2. A ratio reported at a point the sample cannot contain.** An earlier version reported
specification 3's ratio as **1.351** — evaluated at `log(n_pos) = 0`, a one-position portfolio, which
this sample **excludes by construction** (the minimum is 2). The ratio depends entirely on where it
is evaluated:

| Evaluated at | Ratio |
|---|---|
| n_pos = 2 | 1.478 |
| **sample mean** | **1.862** |
| n_pos = 5 (median) | 1.914 |
| n_pos = 8 | 2.722 |

Every ratio from a specification with interacted controls is now reported at sample means and at a
range of points.

## What limits this, in order

**1. A third of the sample cannot identify the interaction at all.** Because
`frac_excl = (k − gain_i)/(n − 1)`, within one trader-day a winner's share is always below a loser's.
Either the portfolio state is constant within the day, or it equals `1 − gain` exactly and the
interaction term is identically zero. **718,973 of 2,175,069 rows (33.06%)** are the second kind.
Leave-one-out **halves** the mechanical dependence between own `gain` and portfolio state; it does
not remove it, and all identification is **between** trader-days — which is why trader-day confounds
like the ones above bite.

**2. The conditioning variable is a count, not a value-weighted return.** One holding up 1% and one
down 40% is a tie and is dropped — 10.1% of rows. This is the central difference from An et al.
Specification 5 uses a genuine portfolio index instead and needs no exclusions.

**3. The pre-registration had a hole.** It required "the gap at least 2× larger" and never said
*which* gap. Pooled gives 4.420×; averaged equally across traders gives **0.857× — the opposite
direction**; within-trader gives 2.041×. The case for the within-trader measure is that the
pre-specified test *is* that regression. That reasoning is **post hoc**.

**4. It is weaker than the paper being replicated.** An et al. report roughly 4–10×. Levels are not
comparable — percentage points here against basis points there, because this denominator is the daily
chance of closing a position — so only the ratio travels.

**5. The tie exclusion is not random.** A tie needs an even number of other positions split exactly in
half, so it occurs only on days with an **odd** total count. All 280,771 excluded tie rows have an odd
count; zero have an even one.

**6. At two positions the design is degenerate.** In a mixed pair the winner is necessarily labelled
portfolio-down and the loser portfolio-up — the same pairs counted from both sides, contributing zero
to the interaction. That stratum is 20.6% of the sample.

**7. Chinese A-shares, one social-trading platform, June 2016 to March 2018**, a population selected
twice over. Nothing here is a claim about retail investors generally, and it tests no remedy.

## What is pre-specified

Specification 1 only, plus the exclusion ladder, the lot-level unit, trader clustering and the four
named outcome thresholds. **Specifications 2–5, the placebo and every control are not
pre-registered**, are labelled so in the output, and none may be the headline.

## Review

Stress-tested twice before publication by independent adversarial passes that recomputed every figure
from the raw data with their own code. The first found four blocking errors; the second found seven
more, including two cases where a correction introduced a new error of the same kind. All are fixed
above, and the two most consequential are stated as corrections rather than quietly amended.
