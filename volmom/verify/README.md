# An independent reimplementation of Part A

Part A was implemented a second time, from the pre-registration text alone, by someone who had not
read `../reproduce_volmom.py`'s computation. The point was to find out whether the published figures
survive being produced by different code.

**They do.** Every figure in the Part A tables of the parent README — annualised return, annualised
volatility, Sharpe, maximum drawdown, worst month, t-statistic, skew and kurtosis, across both the
in-sample and holdout splits — reproduces to the printed precision.

```bash
pip install pandas numpy scipy
python fetch.py     # caches the three Kenneth French files
python volmom.py    # the full report
```

`fetch.py` is idempotent; a second run downloads nothing. `volmom.py` is deterministic — three
consecutive runs are byte-identical.

## What this code answers that the parent script does not

**The probability of backtest overfitting, on every matrix it could be computed from.** The
pre-registration fixed the K2 threshold at 0.50 but never fixed which return matrix the statistic
runs on, and the answer depends entirely on that choice:

| PBO computed on | Value | K2 (<= 0.50) |
|---|---|---|
| In-sample 1927-11…1980-12 | 0.7638 | FAIL |
| Holdout 1981-01…2026-08 | 0.0000 | PASS |
| Common sample 1927-11…2026-08 | 0.0828 | PASS |

The caveat printed beside those numbers matters more than the numbers: at three specifications PBO
has almost no resolution, because the out-of-sample rank of the in-sample winner can only take three
values. Read the output, not the table.

## Two disclosures about how this code was written

**The volatility estimator was chosen after seeing a divergence, not before.** The first
implementation used the centred sample standard deviation — the plain-English reading of "annualised
volatility" — and S1 and S3 matched the published figures to the last decimal while S2 did not.
Barroso & Santa-Clara's own uncentred RMS, `sqrt(252 * mean(r^2))`, reproduces S2 exactly. The
justification for switching is methodological, since this specification is an explicit replication of
their work and that is their published formula — but the switch was made after looking. Both branches
are therefore printed at equal prominence throughout, as `S2` and `S2-centred`, and section 5 of the
output states the sequence in plain language. They differ by 0.0013 in holdout Sharpe.

**Where a convention was unstated, both choices are printed.** Raw kurtosis over the population
standard deviation versus the sample one; the deflated Sharpe's trial variance at ddof 0 versus 1;
the market index starting at 1927-01 versus 1926-07; "otherwise cash" as zero versus the risk-free
rate. None changes a conclusion, and leaving the reader to check is cheaper than asking them to
trust.

`overfit.py` provides the PBO and deflated-Sharpe implementations. It is pure standard library plus
optional numpy, and it is unmodified from the project it was written for.
