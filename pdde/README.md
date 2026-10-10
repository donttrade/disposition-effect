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

## Verdict: weak replication

**The direction replicates robustly. The magnitude does not clear the bar I set in advance.**

| Specification | Interaction | p | Gap ratio (down ÷ up) |
|---|---|---|---|
| **Headline** — count proxy, leave-one-out, trader FE | **−0.024977** | 2.2e-45 | **2.041×** |
| + 428 date fixed effects | −0.025084 | 3.0e-47 | 2.041× |
| **+ portfolio size control** | −0.021841 | 1.5e-38 | **1.351×** |
| **`ret` portfolio index**, no exclusions, 97.8% of panel | −0.028726 | 2.9e-45 | 2.065× |

Standard errors clustered by trader throughout.

The interaction is negative and overwhelmingly significant in every specification. **The ratio is
not stable.** The pre-registration made the verdict turn on it being ≥ 2×, and:

- the headline 2.041× has a **95% CI of [1.862, 2.220]** — the bar sits inside it, and
  **P(ratio < 2.00) ≈ 0.33**
- controlling for **portfolio size** — which the pre-registration did not think of — takes it to
  **1.351×, CI [1.290, 1.412]**, under the bar decisively

So: something real is happening, in the direction An et al. describe. How big it is depends on how
you ask, and the honest range across defensible specifications is roughly **1.35× to 2.07×**.

## The design decision the whole thing rests on

The panel has no position weights, so the headline portfolio state is a **count** of the trader's
other holdings in profit — a proxy, not An et al.'s value-weighted return.

It is computed **leave-one-out**, excluding the focal position. The focal position's own `gain` is
part of any naive portfolio measure built from the same column, which would mechanically correlate
the conditioning variable with what is being conditioned on and produce a strong, entirely spurious
interaction **that would look exactly like a successful replication**.

That defence was tested adversarially and held. Replacing `sale` with a draw depending only on own
`gain` — a pure unconditional disposition effect with zero portfolio dependence by construction —
returns an interaction of |t| ≤ 2.4 against the real −14.3.

Cost: 11.7% of rows to single-position trader-days, 10.1% to ties where the other holdings split
exactly in half. **78.2% survives — 2,175,069 position-days, 4,482 of 4,731 traders.**

## What `ret` is — and a correction

An earlier version of this README said `ret` was a position-level gross price ratio, and discarded
it because it "does not reproduce `gain`" at 62.7% agreement. **That was wrong, and the test used to
justify it was a category error.**

`ret` is a **trader-day** series — the trader's portfolio net-value index. **0 of 951,885 trader-days
carry more than one distinct value**, while 365,814 of 684,171 (date, stock) pairs do. Comparing a
portfolio-level index against a position-level flag and calling the disagreement a defect was
nonsense.

It is now the fourth specification above, and it is in several ways the better one: **zero dependence
on the focal position**, so it is immune by construction to the trap the leave-one-out construction
exists to avoid, and it needs **no exclusions at all** — 97.8% of the panel against 78.2%.

Its official definition in Jin, Li & Zhu is still unverified; the grouping structure was established
empirically here.

## What else is wrong with this, in order

**1. The pre-registration had a hole, and it is wider than one hole.** It required "the gap at least
2× larger" and never said *which* gap. Pooled gives 4.42×; per-trader gives **0.86× — the opposite
direction**; within-trader gives 2.041×. The case for the within-trader measure is that the primary
test *is* that regression, and per-trader averages compare partly different people. That reasoning is
correct and it is **post hoc**. Beyond those three, a fixed-effects logit on average marginal effects
gives about 1.74×, and a continuous specification runs from 1.54× to 2.47× depending purely on where
it is evaluated.

**2. Portfolio size is an uncontrolled confound and it was not pre-registered.** The disposition gap
collapses with portfolio size independently of portfolio state (`gain × log(n_pos)` has t = −20.1,
a larger t than the headline interaction). A placebo built from an irrelevant column — the share of
the trader's other positions with an even-numbered stock code — returns an interaction of t = −4.1,
which should be zero. Something is leaking through the size channel.

**3. The effect is far weaker than the paper being replicated.** An et al. find roughly 4–10×. Levels
are not comparable at all — percentage points here against basis points there, because this
denominator is the daily chance of closing a position — so only the ratio travels, and this one is
below half their lowest figure.

**4. The tie exclusion is not random.** A tie needs an even number of other positions split exactly
in half, so it can only occur on days when the trader holds an **odd** total number. All 280,771 tie
rows have an odd count; zero have an even one. Tie rates run 38.6% at 3 positions down to 0% at every
even size.

**5. At two positions the design is degenerate in a specific way.** In a mixed pair the winner is
necessarily labelled portfolio-down and the loser necessarily portfolio-up — the same pairs counted
from each side. That is 20.6% of the sample, and it explains the low 1.41× ratio in that stratum.
The synthetic null above shows it does not manufacture the result.

**6. Chinese A-shares, one social-trading platform, 24 June 2016 – 27 March 2018**, a population
selected twice over. Unchanged from the parent study. And this measures the effect; it tests no
remedy for it.

## What is pre-specified and what is not

Pre-specified: the leave-one-out construction, the exclusions, the lot-level unit, one specification
with trader fixed effects and trader-clustered errors, and the four named outcomes with thresholds.

**Not pre-specified, and labelled as such in the output:** the date fixed effects, the portfolio-size
control, and the `ret` specification. None of them may be the headline.

## Review

This was stress-tested adversarially before publication by an independent pass that recomputed every
figure from the raw data with its own code, attempted to break the construction with a synthetic null
and a non-flip subsample, checked the clustered standard errors against a 2,000-replication trader
bootstrap, and found four blocking errors. All four are corrected above. The bootstrap agreed with
the analytic standard error to within 0.6%.
