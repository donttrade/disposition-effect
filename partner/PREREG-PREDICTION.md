# Do early trading habits predict prop-challenge rule breaches? A pre-registered external validation of the donttrade DT-1 habit index

**Status: draft for OSF, not yet posted.** Once posted, the OSF timestamp is the registration date. Each firm completes the firm fields of the parameter block at the end (§2.13) and sends it in before running the script. Each firm's completed block is added as a dated amendment, before that firm's run.

Order follows the OSF "Preregistration" template: study information, design, sampling, variables, analysis, other. Reporting will follow TRIPOD+AI.

Nothing here is investment advice, and nothing here is a prediction about any one trader.

---

## 1. Study information

### 1.1 Title and authors

**Do early trading habits predict prop-challenge rule breaches? A pre-registered external validation of the donttrade DT-1 habit index.**

Authors: donttrade (study lead). Invited reviewers and co-authors will be listed in an amendment if they accept.

**Conflict of interest.** donttrade sells the donttrade test and benefits from a positive result. That is why this study is pre-registered and why the code is public.

**Publication commitment.** donttrade will publish the result whatever it is. That includes a FAIL showing the habits add nothing beyond size, volatility and headroom, and it includes NOT MEASURED and INCONCLUSIVE results. Results go on the donttrade site at `/research/does-the-test-predict/`. That page's wording for every verdict was written and committed before any data was run. A preprint follows when the first verdict exists.

### 1.2 Hypotheses

| # | Hypothesis | Role |
|---|---|---|
| **H1** | Take accounts with at least 30 closed trades. The DT-1 habit index from trades 1–30 ranks accounts that breach a daily-loss or max-loss rule in the next 30 days above accounts that do not, with **AUC > 0.55**. | Primary |
| **H2** | DT-1 adds to the baseline model B0 (§3.4). In a logistic model with B0's four variables plus DT-1, the DT-1 coefficient is positive with a likelihood-ratio p < 0.05. | Primary (co-primary) |
| H3 | The same as H1 for **challenge failure**: ended challenges, failed vs passed. | Secondary |
| H4 | Each of the 6 features alone has AUC > 0.5 (Holm-adjusted across the 6). | Exploratory |
| H5 | The results hold under each robustness check in §4.6. | Exploratory |

Every feature is coded so that **higher = more of the habit**, and every hypothesis is one-sided in that direction. The directions come from the literature (Coval & Shumway 2005 on loss-chasing; Odean 1998 on holding losers), not from data.

---

## 2. Design

### 2.1 Unit, index time and windows

- **Unit:** one account. If the firm supplies a pseudonymous `trader_key`, only that trader's earliest eligible account is used.
- **Trades:** rows sharing a symbol, direction and open minute are merged into one trade, exactly as the engine's `mergeRows` does. Trades are then ordered by close time: close, then open, then input position, as the engine's `byClose`. Open times are taken to the minute and hold times to the second, as in the engine's stripped rows.
- **Window W** = the first 30 trades by close time. **Index time T0** = the close time of trade 30.
- **Outcome window** = (T0, T0 + 30 calendar days]. Nothing at or before T0 is used in an outcome. Nothing after T0 is used in a feature or a baseline variable.

### 2.2 Outcomes

| Code | Definition | Where it applies |
|---|---|---|
| **O1 (primary)** | A **rule breach** in the outcome window: a daily-loss or max-loss breach. **Firm mode:** the firm's own risk-system record (`outcome` = `daily` or `max`, with `outcome_time` in the window). **Rule mode:** rule set **R\*** replayed day by day on the trades closed in the window, starting at T0 with equity 0. R\* is a daily loss of 5% of A, a max loss of 10% of A, a static drawdown, no profit target, and days cut at the sealed day start. A = the account size in `start_balance`. | Firm mode; rule mode |
| **O2 (rule mode only)** | **A 50% drawdown:** equity A + the running sum of closed P&L after T0 falls 50% or more below its running peak within the window. | Rule mode, secondary |
| **O3 (secondary)** | **Challenge failure:** the challenge ended as failed (any rule, including time limit or consistency), not passed. Only challenges that ended after T0 and by the data cut. | Firm mode |

**Labels:**
- **O1 = 1** if a breach falls in the window.
- **O1 = 0** if there was no breach and the account was either observed for the whole 30 days or passed inside the window.
- **Censored** (excluded; counted as 0 in a robustness check) if, within the window and without a breach, the data ended, the account closed, or it ended under another rule.

**Known limitation.** Rule mode sees closed trades only, so it misses breaches caused by open P&L and **undercounts** breaches. Rule-mode results are never pooled with firm results.

### 2.3 Features: DT-1, frozen

All six come from the engine's group functions applied to W alone. Size `q` is each trade's size divided by that symbol's median size **within W**. It is never computed over the whole file, because a whole-file median would let later trades leak into the features (§5.2, world W-K).

| # | Feature | Definition (engine function) | Undefined when |
|---|---|---|---|
| F1 | `reentry_share` | `revenge_groups`: n_a ÷ (n_a + n_b), the share of trades opened within 900 s after a losing trade's close (the first trade excluded) | never |
| F2 | `streak_share` | `tilt_groups`: n_a ÷ (n_a + n_b), the share of trades whose last prior close ended a run of 2 or more losses | n_a + n_b = 0 |
| F3 | `size_after_loss_ratio` | `size_up`: log(median q after a loss ÷ median q after a win) | either group is empty, or either median is 0 |
| F4 | `size_after_loss_share` | `size_up`: after-loss trades with q ≥ 1.5, ÷ n_a | n_a = 0 |
| F5 | `large_loss_share` | `oversized`: the share of W's trades that are losses above 2× the median loss in W | W has no loss |
| F6 | `hold_gap_ratio` | `hold_gap`: log(median hold of losers ÷ median hold of winners) | no loser, no winner, or either median is 0 |

**DT-1 habit index.** Each defined feature becomes its mid-rank percentile, (mid-rank − 0.5) ÷ n, among the analysed accounts where it is defined. Ties share the average rank. The index is the **mean of the defined percentiles**. An account gets an index only if at least **3 of the 6** features are defined. Nothing is fitted, so the primary AUC carries no optimism. A cross-firm index with absolute calibration (DT-2) is only possible after pooled results exist. It is not part of this registration.

**Not in DT-1.** The P&L effects, overtrading and size creep are not computed in version 1.0 of the script and are not reported.

### 2.4 Baseline model B0 (no habits)

| # | Variable | Definition |
|---|---|---|
| B1 | Activity | 30 ÷ the number of distinct trading days in W (by the close day, at the sealed day start) |
| B2 | Volatility | log(standard deviation of per-trade net P&L in W ÷ account size). A standard deviation of 0 is floored at 10⁻⁹ before the log. |
| B3 | P&L so far | the sum of net P&L in W ÷ account size |
| B4 | Headroom at T0 | (equity at T0 − the max-loss floor at T0) ÷ the max-loss amount, with the floor from the readiness engine's drawdown logic for the account's drawdown kind. R\* in rule mode. |

B0 is a logistic regression on B1–B4. H2 adds DT-1 as a fifth term.

---

## 3. Sampling

### 3.1 Data

- **Firm mode (decisive).** A prop firm runs the open-source script on its own historical records, on its own machines, and sends back only the printed aggregate text.
- **Rule mode.** For data with no outcome record. It is reported separately and never pooled with firm results.

**Existing data (OSF item).** This is a registration made before the data is analysed. The firms' historical records already exist, but donttrade has not seen them and never receives them. Each firm analyses its own records with the registered script, only after this registration and its own amendment are posted. Study type: observational. There is no blinding and no randomisation, apart from the seeded fold assignment.

The two input files are described in `EXPORT-GUIDE-PREDICTION.md`. The firm's completed parameter block (§5) states `accounts_in_period`. The script refuses an export whose account count differs from it, so a firm cannot export a chosen subset.

### 3.2 Sample size and power

The figures come from Layer 1 of the synthetic dry run: 2,000 replications per cell, and 20,000 for the 0.65 cell at 200/200 (research/prediction-study/S2-LAYER1-REPORT.md). Each cell gives the probability that H1 passes (the lower 95% bound above 0.55).

| Breaches = survivors | P(pass H1), true AUC 0.55 | 0.60 | **0.65** | 0.70 |
|---|---|---|---|---|
| 100 | 0.035 | 0.26 | 0.73 | 0.98 |
| **200** | 0.024 | 0.42 | **0.948** | 1.00 |
| 400 | 0.029 | 0.70 | 1.00 | 1.00 |

- **Target: 200 breaches and 200 survivors** after exclusions. The minimum for any verdict is 100 of each.
- **False pass.** With a true AUC of exactly 0.55, H1 falsely passes 2.4–3.5% of the time.
- **Reaching 0.65.** When the true AUC is 0.65, the point estimate reaches 0.65 about half the time, so 0.65 is the target, not the pass line.
- **H2 power and false-pass rate, measured in the Layer 2 synthetic worlds** (research/prediction-study/S3-LAYER2-REPORT.md):
  - H2 passes in 100% (200 of 200) of study-size runs when habits drive breaches (world W-L);
  - it passes in 16.5% (33 of 200) when breaches come mechanically from the rules (world W-M). There, the habits raise volatility and move P&L so far and headroom, so B0 absorbs most of their effect. H2 is therefore conservative when habits act through volatility;
  - its false-pass rate is 0% (0 of 300) when habits only stand in for volatility (world W-C).
- **Accounts needed** for 200 + 200: 1,334, 800, 572 and 400 at breach rates of 15%, 25%, 35% and 50%.

### 3.3 Stopping rules

1. **One analysis per data cut**, with no interim looks. Each firm states its data cut and its account count for the period in the parameter block before exporting.
2. **Every firm that runs the registered version is included.** No firm is dropped after its result is seen.
3. **The pooled verdict** applies §4.5 to a fixed-effect inverse-variance meta-analysis of the per-firm AUCs. With one firm, that firm's result is the verdict. Per-firm results and I² are always shown.
4. **INCONCLUSIVE** is followed only by a **new registration**, with DT-1 unchanged, on new accounts. It is reported as a replication and never merged with the first result.
5. **Changes** after posting are dated amendments, made before any new data is run. A change after data is seen is reported as a deviation.

---

## 4. Analysis plan

### 4.1 Exclusions (applied in this order; each counted in the printed reconciliation)

| # | Rule |
|---|---|
| E1 | Fewer than 30 trades before any breach or account end, including accounts that breached at or before T0 (that count is printed separately) |
| E2 | W is dates only (at least 5% of W's rows open at 00:00 and are held whole days: the engine's rule) |
| E3 | Fewer than 3 of the 6 features defined |
| E4 | Censored (§2.2) |
| E5 | Flagged by the firm for abuse (copy trading, hedging across accounts, latency arbitrage), using the firm's own flag. Included again in a robustness check. |
| E6 | Flagged as automated (`bot_flag`, used for on-chain data) |
| E7 | A later account of the same `trader_key` |

### 4.2 Metrics

| Metric | Method |
|---|---|
| **AUC of DT-1 (primary)** | Mann–Whitney, ties counted ½; DeLong SE; 95% CI = AUC ± 1.96 SE |
| AUC of B0 and of B0 + DT-1 | 10-fold stratified cross-validation, with folds seeded by the parameter block's SHA-256 fingerprint (its first 16 hex digits) |
| ΔAUC (full − B0) | Paired DeLong on the out-of-fold predictions, with a 95% CI (reported) |
| **H2 test** | Likelihood-ratio test, 1 df, in-sample, with the sign of the DT-1 coefficient. A fit that separates counts as H2 not passed. |
| Calibration | DT-1 turned into a probability by cross-validated logistic recalibration. For that, for the full model and for B0: calibration intercept (offset model), slope, and a 10-band table of mean predicted vs observed |
| Brier | Brier score and scaled Brier, 1 − Brier ÷ (base rate × (1 − base rate)) |
| Usefulness | Breaches and survivors per DT-1 decile; lift in the top decile; confusion counts when the top 10%, 20% and 30% of the index are flagged |
| H4 | Each feature's AUC with a DeLong CI, a one-sided p for AUC > 0.5, Holm-adjusted across 6 |

**Small cells.** Every printed table cell describes at least 5 accounts. Adjacent bands are merged, lowest first, until each row has at least 5 breaches and 5 survivors, and a short last row merges into the row before it. Confusion counts under 5 print as `<5`. Reconciliation counts are exact.

### 4.3 Analysis code and hash

The code is the public repository's `partner/` folder at the tagged release `prediction-v1`. The script `prediction_test.py` imports three sibling modules, so **all four files are fingerprinted**:

<!-- BEGIN PREDICTION SHA-256 -->

The analysis code (`sha256sum` prints the same):

```
7bc070e8e9496afe730ccffb9900449034edbc8faec124f6f7fbd03d79a8b8a4  partner/prediction_test.py
db81646693dc6888d2361cb49a0031dda659e05c73d23593c5886461882c59c1  partner/dt1_features.py
07f9da966b4734e4d94d86a6f126df6bd24b8ace49709855a7b6fc6e58f6c152  partner/dt1_outcomes.py
2d810ad6222ea724bd649185deac67a25a06de259eee63f508921041a12798ff  partner/prediction_metrics.py
```

The supporting files and the fixture run:

```
daaaecc53c0a96be065b120c43466797670d2116eb45e2afd4c3232ccdbd0da2  partner/make_fixture_prediction.py
cf921b4b9a0c979fdcdb9ee2f0c8aac4c79d9aebba604ef3137e8ecd451159f7  partner/parity/dt1_golden.json
07fcf9ec005837be4410f213b856a1a4e3e96462ab38b001c92598070eaedfa8  partner/parity/rules_golden.json
abf723c530f13bae94b5612c0ea52a6a26c2cd919176f34cdd4689cc7b519e1f  partner/PREREG-PREDICTION-EXAMPLE.md
d213660000e8c0a7bdc547cb62f25fc1eea6e0c66a5b2bb65b413a38f8286474  fixture trades.csv
1cdfd73bcb7d20ffd947d442339433c61c4a812aaf79e6b899ccfbb2a10cc22b  fixture accounts.csv
c4503575f2538e3f0fd90f4fb12bea5df9a010d485a7d8bbba5ff4c0da124ed1  fixture expected output
```

<!-- END PREDICTION SHA-256 -->

- **The parity golden files.** `partner/parity/dt1_golden.json` holds 521 windows: on every one, `dt1_features.py` matches the paid engine `habits.mjs`, counts exactly and measures to 1e-12. `partner/parity/rules_golden.json` holds 160 day sequences on which the outcome replay matches the readiness engine `prop-sim-core.js`. Both ship in the release. Their SHA-256 fingerprints are listed above.
- **The fixture.** `make_fixture_prediction.py` writes a synthetic fixture. The script's output on that fixture, using `PREREG-PREDICTION-EXAMPLE.md`, must equal `README-PREDICTION.md`'s expected output byte for byte. The fingerprints of the fixture files and of that output are listed above.
- **The no-network guarantee** (tests in the release):
  - standard library only, with an import allowlist checked by an AST walk;
  - exactly three files opened, read-only;
  - no file written;
  - identical output with sockets disabled, and identical output inside a network-less namespace (`unshare -rn`).

### 4.4 Inference

| Hypothesis | Rule |
|---|---|
| H1 | The lower 95% bound of the DT-1 AUC is above 0.55 |
| H2 | The DT-1 coefficient is positive with likelihood-ratio p < 0.05 |
| H3, H4, H5 | Reported with intervals. They enter no verdict. |

### 4.5 What counts as a pass and a fail (checked top-down; the first match wins; the script prints it)

| Order | Verdict | Condition | What donttrade then does |
|---|---|---|---|
| 1 | **NOT MEASURED** | Fewer than 100 breaches or 100 survivors after exclusions, or the script refuses the input | Says so, and keeps collecting under this registration |
| 2 | **FAIL: does not predict usefully** | Point AUC < 0.55, **or** the upper 95% bound < 0.60 | Stops describing DT-1 as a risk measure. Publishes. |
| 3 | **FAIL: adds nothing** | The lower 95% bound > 0.55, but H2 is not passed | Publishes "habits rank risk, but no better than size, volatility and headroom". Makes no claim that habits add value. |
| 4 | **PASS: meets target** | The lower 95% bound > 0.55, H2 passes, and point AUC ≥ 0.65 | Publishes the full CI and calibration, with population wording only ("in a pre-registered study…") |
| 5 | **PASS: below target** | The lower 95% bound > 0.55, H2 passes, and point AUC < 0.65 | Publishes "it predicts, modestly". Describes DT-1 as a group-level monitoring indicator, not a standard. |
| 6 | **INCONCLUSIVE** | Everything else | Publishes, and starts the §3.3(4) replication |

### 4.6 Robustness checks (H5)

- Censored accounts counted as 0.
- E5 accounts included.
- A 15-trade window.
- CFD and futures separately, and each firm separately. Each run covers one market family and one firm, so these comparisons are made across runs.

---

## 5. Other

### 5.1 Prior exposure statement

Before posting, the authors ran this pipeline on synthetic data with planted effects:
- Layer 1: the metrics alone;
- Layer 2: six synthetic worlds, through the script itself.

DT-1's definition was fixed at commit `007806a` (30 Oct 2026), before the Layer 2 runs, and was not changed after them. No change was made after those runs. An internal run on public on-chain perpetual-futures fills is planned as a method check (whether the code runs on real-shaped data); it had not been run when this text was written. No firm data and no user data had been analysed.

### 5.2 Synthetic dry run (summary)

Relationships were planted at several known AUCs. The pipeline recovered them within their intervals, and the pass and fail rules behaved as stated. The results are in research/prediction-study/S2-LAYER1-REPORT.md and S3-LAYER2-REPORT.md, in the release.

**Layer 1.** True AUCs 0.50–0.75 at 100, 200 and 400 per class, 2,000 replications each:
- absolute bias ≤ 0.0014;
- 95% CI coverage 94.0–96.0%;
- H1 false pass at 0.55 of 2.4–3.5%;
- power at 0.65 with 200/200 of 94.8% (R = 20,000).

**Layer 2.** Through the script itself, against 200,000-account population AUCs:
- W-L: population 0.6645, recovered 0.6659, CI coverage 96.5%;
- W-M: population 0.6449, recovered 0.6429, coverage 97.5%;
- null world: H1 false pass 0 of 300;
- confounded world: H2 false pass 0 of 300;
- look-ahead canary: a whole-file size normaliser raised the AUC from 0.500 to 0.598, and the registered within-W rule did not;
- exclusion world: the E1–E7 counts equalled the ground truth exactly.

### 5.3 Known limitations

- **Survivor framing.** Accounts that break a rule within their first 30 trades are excluded (E1). A pass means "among accounts that lasted 30 trades".
- **DT-1 is a within-sample rank.** It cannot yet rate one new account on its own.
- **Rule mode undercounts breaches.** It sees closed trades only.
- **The day boundary uses one fixed UTC offset** (`day_utc_offset`). Firms whose server clock changes for daylight saving export in that clock and register its offset, or register UTC.
- **Firm selection.** The registered `accounts_in_period` count is checked against the export.

### 5.4 Licence for the study

Firms and academic partners may run the registered version on their real client records **free of charge, for this study only**, and send the aggregate output to donttrade (`partner/LICENSING.md`, "Additional permission: prediction study"). Using DT-1 in a firm's own operations stays a paid engagement.

### 5.5 Parameter block (the script reads only this block)

The study constants accept only the registered values. The firm completes the `FILL_IN` fields and sends the block to donttrade before exporting. The script refuses any `FILL_IN`. The SHA-256 of the block's lines (from the BEGIN line to the END line, joined by newlines) is its fingerprint, and it seeds the cross-validation folds.

--- BEGIN SEALED PARAMETERS ---
[prediction-study]
registration = "OSF FILL_IN"
dt_version = "DT-1"
engine_method = "2026-10-23.stats2f"
window_trades = 30
outcome_days = 30
min_features = 3
pass_lower = 0.55
fail_point = 0.55
fail_upper = 0.60
target = 0.65
h2_alpha = 0.05
min_each = 100
cv_folds = 10
outcome_mode = "firm"                      # firm (risk-system outcomes) or rule (R*)
pnl_basis = "FILL_IN net or gross"
firm_label = "FILL_IN (published name or 'a CFD prop firm')"
period_start = "FILL_IN YYYY-MM-DD"
period_end = "FILL_IN YYYY-MM-DD"
data_cut = "FILL_IN YYYY-MM-DD"
accounts_in_period = FILL_IN
day_start = "FILL_IN HH:MM"
day_utc_offset = "FILL_IN +HH:MM"
--- END SEALED PARAMETERS ---
