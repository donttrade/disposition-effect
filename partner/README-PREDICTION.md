# The prediction study script (`prediction_test.py`)

This script tests whether a trader's first 30 trades say anything about what happens next. It asks one question of a firm's **past** accounts. Take each account's first 30 closed trades. Does the donttrade habit score (DT-1) computed from them rank the accounts that went on to break a daily-loss or max-loss rule in the next 30 days above the accounts that didn't? And does it add anything beyond activity, volatility, P&L so far and how close the account already was to its loss limit?

The full plan, the pass and fail rules and the analysis are in the pre-registration, `PREREG-PREDICTION.md`. That registration is posted on OSF before any firm runs the script. donttrade publishes the result whatever it is, including a FAIL.

You run the script on your own machine, on your own records. Nothing leaves your machine except the printed text, and you read that text before you send it.

## What it does and does not do

- **Standard library only.** It runs on any Python 3.8 or later, with nothing to install.
- **No network.** It imports no network module (`socket`, `urllib`, `http`, `ssl`), no `os`, no `subprocess` and no `importlib`. The tests check this four ways:
  - an AST walk of all four files against the import list;
  - exactly three `open()` calls at run time, all read-only;
  - identical output with the socket functions replaced by a stub that raises;
  - identical output inside a network-less namespace.

  You can check the last one yourself (below).
- **Opens exactly three files, read-only:** `trades.csv`, `accounts.csv` and the pre-registration. **It writes no file.** Output goes to stdout. Errors go to stderr, as one line with a row number and a fixed sentence. They never quote a cell.
- **Prints aggregates only:**
  - counts, AUCs and intervals;
  - p-values and the sign of a coefficient;
  - banded tables, where adjacent bands are merged until every cell holds at least 5 breaches and 5 survivors. Confusion counts under 5 print as `<5`.

  It prints no account, identifier, symbol, time or amount.
- **Every choice is fixed by the pre-registration's parameter block.** There is no command-line option for any of them. The study constants (30 trades, 30 days, the 0.55 / 0.60 / 0.65 lines and so on) accept only their registered values. The cross-validation seed comes from the block's SHA-256, so nobody chooses it.

The script is four files. Run it from a folder that holds all four:

| File | What it holds |
|---|---|
| `prediction_test.py` | Reading and checking the files, exclusions E1–E7, the analysis, the output. The AUDIT MAP at the top names every line that opens a file or prints. |
| `dt1_features.py` | The six habit features. These are verbatim copies of the paid engine's group functions. Each copy names its source lines and the source file's SHA-256. |
| `dt1_outcomes.py` | Breach labels: the firm's own record, or rule set R* replayed. Also the B4 headroom. |
| `prediction_metrics.py` | AUC, DeLong intervals, logistic regression, cross-validation, calibration, Brier, banded tables. |

Two golden files show that the published code gives the paid engine's numbers. Anyone can check them without the private engine (`tests/test_dt1_parity.py`, `tests/test_dt1_outcomes.py`).

| File | What it shows |
|---|---|
| `parity/dt1_golden.json` | 521 thirty-trade windows on which `dt1_features.py` and the paid engine (`habits.mjs`) agree, counts exactly and measures to 1e-12 |
| `parity/rules_golden.json` | 160 day sequences on which `dt1_outcomes.replay` and the Challenge Readiness engine (`prop-sim-core.js`) agree |

## Check your copy (plain Terminal)

1. Download the tagged release `prediction-v1`.
2. Print the fingerprints:

   ```
   sha256sum partner/prediction_test.py partner/dt1_features.py partner/dt1_outcomes.py partner/prediction_metrics.py
   ```

3. Compare them with three places, which must all agree: [`LICENSING.md`](LICENSING.md), the OSF registration, and the release notes.
4. Write the synthetic fixture. Run the script on it. Compare the output with the block below **byte for byte**:

   ```
   mkdir fixture
   python3 -I partner/make_fixture_prediction.py --out fixture
   sha256sum fixture/trades.csv fixture/accounts.csv
   python3 -I partner/prediction_test.py fixture/trades.csv fixture/accounts.csv partner/PREREG-PREDICTION-EXAMPLE.md > out.txt
   ```

   The fixture's fingerprints:

<!-- BEGIN FIXTURE SHA-256 -->
```text
d213660000e8c0a7bdc547cb62f25fc1eea6e0c66a5b2bb65b413a38f8286474  trades.csv
1cdfd73bcb7d20ffd947d442339433c61c4a812aaf79e6b899ccfbb2a10cc22b  accounts.csv
```
<!-- END FIXTURE SHA-256 -->

5. Check that it cannot reach a network (plain Terminal, Linux). The output must be the same:

   ```
   unshare -rn python3 -I partner/prediction_test.py fixture/trades.csv fixture/accounts.csv partner/PREREG-PREDICTION-EXAMPLE.md
   ```

6. Read the AUDIT MAP at the top of `prediction_test.py` and spot-check the lines it names.

Running the script on the fixture is covered by the 32-day evaluation permission in `LICENSING.md`. Running it on real records for this study is covered by the study permission in the same file.

### Expected output on the fixture

The fixture is synthetic. It plants a link between the habits and breaches (world L of the plan: AUC of the hidden trait 0.70), so the numbers below describe that planted world and nothing real.

<!-- BEGIN EXPECTED OUTPUT -->
```text
donttrade prediction study: prediction_test.py 1.0 (30 Oct 2026)
Score: DT-1   Engine method: 2026-10-23.stats2f   Outcome mode: firm   P&L basis: net
Registration: EXAMPLE: synthetic fixture, not a registration
Sealed block fingerprint (SHA-256): 463e7dab680f333a17e339624bdbc587a62ff3a478e67088b5e016a48349bb19
Fold seed: the fingerprint's first 16 hex digits

RECONCILIATION
  Accounts read ................................. 600
  E1 fewer than 30 trades before any breach ..... 0
     of which breached at or before trade 30 .... 0
  E2 first 30 trades are dates only ............. 0
  E3 fewer than 3 of the 6 features defined ..... 0
  E4 censored (not observed for 30 days) ........ 0
  E5 flagged by the firm for abuse .............. 0
  E6 failed the human-pattern screen ............ 0
  E7 a later account of the same trader ......... 0
  Eligible ...................................... 600
  Breaches (daily or max loss within 30 days) ... 231
  Survivors ..................................... 369

H1  AUC of DT-1 (primary)
  AUC 0.672 (95% CI 0.628 to 0.716)   DeLong SE 0.0227   breaches 231, survivors 369

H2  Does DT-1 add to the baseline B0 (activity, volatility, P&L so far, headroom)?
  Cross-validated AUC, B0 only ......... 0.592 (95% CI 0.545 to 0.639)
  Cross-validated AUC, B0 + DT-1 ....... 0.682 (95% CI 0.638 to 0.726)
  Difference (paired DeLong) ........... +0.090 (95% CI +0.045 to +0.135)
  Likelihood-ratio test (1 df) ......... statistic 47.901, p <0.0001, DT-1 coefficient positive
  H2 passed ............................ yes

FEATURES (exploratory, one-sided, Holm-adjusted across 6)
  feature                  AUC (95% CI)                       Holm p    undefined
  reentry_share            0.623 (95% CI 0.577 to 0.669)      <0.0001   0
  streak_share             0.520 (95% CI 0.473 to 0.567)      0.2030    0
  size_after_loss_ratio    0.703 (95% CI 0.660 to 0.746)      <0.0001   0
  size_after_loss_share    0.617 (95% CI 0.578 to 0.655)      <0.0001   0
  large_loss_share         0.538 (95% CI 0.503 to 0.574)      0.0349    0
  hold_gap_ratio           0.605 (95% CI 0.559 to 0.652)      <0.0001   0

USEFULNESS (DT-1 deciles, lowest scores first; adjacent deciles merged until every cell has 5+)
  decile    n      breaches  survivors
  1         60     16        44
  2         60     11        49
  3         60     12        48
  4         60     18        42
  5         60     22        38
  6         60     23        37
  7         60     27        33
  8         60     28        32
  9         60     35        25
  10        60     39        21
  Breach rate in the top row divided by the overall rate: 1.688
  Confusion counts when the top share of scores is flagged:
    top 10%: flagged 60, breached and flagged 39, survived and flagged 21, breached and not flagged 192, survived and not flagged 348
    top 20%: flagged 120, breached and flagged 74, survived and flagged 46, breached and not flagged 157, survived and not flagged 323
    top 30%: flagged 180, breached and flagged 102, survived and flagged 78, breached and not flagged 129, survived and not flagged 291

CALIBRATION (cross-validated predicted chance of a breach)
  DT-1 (recalibrated): intercept +0.002, slope 0.953, Brier 0.2178, scaled Brier 0.080
    band 1      n 60    mean predicted 0.187   observed 0.267
    band 2      n 60    mean predicted 0.235   observed 0.200
    band 3      n 60    mean predicted 0.268   observed 0.200
    band 4      n 60    mean predicted 0.311   observed 0.283
    band 5      n 60    mean predicted 0.341   observed 0.433
    band 6      n 60    mean predicted 0.378   observed 0.317
    band 7      n 60    mean predicted 0.426   observed 0.433
    band 8      n 60    mean predicted 0.482   observed 0.483
    band 9      n 60    mean predicted 0.557   observed 0.600
    band 10     n 60    mean predicted 0.662   observed 0.633
  Full model (B0 + DT-1): intercept +0.003, slope 0.906, Brier 0.2136, scaled Brier 0.098
    band 1      n 60    mean predicted 0.169   observed 0.183
    band 2      n 60    mean predicted 0.219   observed 0.200
    band 3      n 60    mean predicted 0.253   observed 0.300
    band 4      n 60    mean predicted 0.286   observed 0.267
    band 5      n 60    mean predicted 0.328   observed 0.333
    band 6      n 60    mean predicted 0.374   observed 0.450
    band 7      n 60    mean predicted 0.425   observed 0.383
    band 8      n 60    mean predicted 0.491   observed 0.417
    band 9      n 60    mean predicted 0.582   observed 0.617
    band 10     n 60    mean predicted 0.718   observed 0.700
  Baseline B0: intercept +0.002, slope 0.778, Brier 0.2313, scaled Brier 0.023
    band 1      n 60    mean predicted 0.244   observed 0.333
    band 2      n 60    mean predicted 0.288   observed 0.250
    band 3      n 60    mean predicted 0.318   observed 0.333
    band 4      n 60    mean predicted 0.343   observed 0.317
    band 5      n 60    mean predicted 0.362   observed 0.400
    band 6      n 60    mean predicted 0.383   observed 0.350
    band 7      n 60    mean predicted 0.410   observed 0.500
    band 8      n 60    mean predicted 0.443   observed 0.317
    band 9      n 60    mean predicted 0.486   observed 0.500
    band 10     n 60    mean predicted 0.570   observed 0.550

O3  Challenge failure (secondary): ended challenges, failed vs passed
  AUC 0.692 (95% CI 0.621 to 0.763)   failed 231, passed 64

H5  ROBUSTNESS (AUC of DT-1 under each check)
  censored accounts counted as no breach: AUC 0.672 (95% CI 0.628 to 0.716), breaches 231, survivors 369
  abuse-flagged accounts included: AUC 0.672 (95% CI 0.628 to 0.716), breaches 231, survivors 369
  a 15-trade window: AUC 0.643 (95% CI 0.595 to 0.691), breaches 181, survivors 419
  CFD and futures separately; each firm separately: one market family and one firm per run, so these are compared across runs.

VERDICT: PASS: meets target
HOW TO READ: The habit score ranks later breaches above survivors (lower 95% bound above 0.55), adds to the baseline, and reaches the 0.65 target. This describes these accounts as a group, never one trader. Past accounts only: this says nothing about any one trader and is not investment advice.
```
<!-- END EXPECTED OUTPUT -->

## Running it on your records (plain Terminal)

1. Export the two files described in [`EXPORT-GUIDE-PREDICTION.md`](EXPORT-GUIDE-PREDICTION.md).
2. Complete the firm fields of the parameter block in `PREREG-PREDICTION.md`: `firm_label`, `period_start`, `period_end`, `data_cut`, `accounts_in_period`, `day_start`, `day_utc_offset`, `outcome_mode` and `pnl_basis`. Send the completed block to donttrade.research@gmail.com **before** you run the script. donttrade adds it to the OSF registration as a dated amendment. The script refuses to run if the number of accounts it reads differs from `accounts_in_period`. That count proves the export holds every account of the period.
3. Run:

   ```
   python3 -I partner/prediction_test.py trades.csv accounts.csv PREREG-PREDICTION.md > result.txt
   ```

4. Read `result.txt`. If you are content that it holds only aggregates, send it to donttrade. The same numbers are available as JSON with `--json`. The results page uses that form.

There is one analysis per data cut. A firm that runs the registered version is always included in the pooled result. No firm is dropped after its result is seen.

## Reading the result

The last line is one of six verdicts. The rules are checked from the top, and the first one that matches wins:

| Verdict | When |
|---|---|
| NOT MEASURED | Fewer than 100 breaches or 100 survivors after exclusions |
| FAIL: does not predict usefully | AUC below 0.55, or the upper end of its 95% interval below 0.60 |
| FAIL: adds nothing | The lower end of the 95% interval is above 0.55, but DT-1 adds nothing to the baseline (H2) |
| PASS: meets target | The lower end is above 0.55, H2 passes, and the AUC is 0.65 or more |
| PASS: below target | The lower end is above 0.55, H2 passes, and the AUC is below 0.65 |
| INCONCLUSIVE | Anything else |

An AUC is the chance that a randomly chosen breached account scores higher than a randomly chosen account that didn't breach. 0.50 is a coin flip.

The result describes past accounts as a group. It says nothing about any one trader, and it is not investment advice.

## Known limits (also stated in the registration)

- Accounts that broke a rule within their first 30 trades are excluded and counted (E1). A pass therefore means "among accounts that lasted 30 trades".
- DT-1 is a rank within the sample. It cannot yet score one new account on its own.
- Rule mode (R*) sees closed trades only, so it undercounts breaches. Rule-mode results are never pooled with firm results.
- The day boundary uses one fixed UTC offset (`day_utc_offset`). If your server clock follows daylight saving, days near the switch are off by an hour. Export in the server's own clock and seal that offset, or seal UTC.
