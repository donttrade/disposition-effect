# S3: Layer 2 synthetic study, through the real script

Batch S3 of `ARCHITECT-PREDICTION-STUDY-2026-10-30.md` §5.1. Synthetic data only.

**How each replication ran.** `partner/make_fixture_prediction.py` wrote firm-format `trades.csv` and `accounts.csv` files. `prediction_test.read_inputs` parsed and checked them, with the firm's own parser and refusals. Then the script's own `classify`, `analyse_full` and `verdict` ran on them. The first two replications of each world also ran through the command line. Their printed VERDICT always equalled the in-process verdict.

**Population AUCs.** These come from 200,000-account runs of the same world. On 3,000 accounts, that computation gives exactly the script's eligibility and labels.

Raw output: `S3-raw.md`. Reproduce it (Claude Code, repo root, about 50 minutes on 2 cores):

```
python3 -B tests/sim_layer2.py --procs 2
```

DT-1 was fixed at commit `007806a`, before these runs, and was not changed after them.

## Results

| World | What is planted | Reps | Per class (mean) | Population AUC of DT-1 | Mean study AUC (bias ± MC SE) | Mean 95% CI | CI covers population AUC | H1 pass | H2 pass | Verdicts |
|---|---|---|---|---|---|---|---|---|---|---|
| **W-L** | breach ~ logistic(z), AUC(z) = 0.70 | 200 | 211 / 389 | 0.6645 | 0.6659 (+0.0013 ± 0.0014) | 0.620–0.712 | **96.5%** | 100% | 100% | 160 PASS meets target, 40 PASS below target |
| **W-M** | breaches from replaying the trades under each account's rules | 200 | 184 / 558 | 0.6449 | 0.6429 (−0.0021 ± 0.0014) | 0.598–0.688 | **97.5%** | 99% | **16.5%** | 165 FAIL adds nothing, 27 PASS meets target, 6 PASS below target, 2 INCONCLUSIVE |
| **W-0** | null: breaches depend on volatility g only, and g is independent of z | 300 | 210 / 390 | 0.50 by construction | 0.4984 | 0.450–0.547 | n/a | **0.0%** (limit 3.6%) | 0% | 297 FAIL does not predict, 3 INCONCLUSIVE |
| **W-C** | confounded: z drives g, and breaches depend on g only | 300 | 211 / 389 | n/a | 0.6558 | 0.610–0.702 | n/a | 99.3% | **0.0%** (limit 5%) | 298 FAIL adds nothing, 2 INCONCLUSIVE |
| **W-K** real | breach depends on k; k = 1 accounts trade at 0.25× size after trade 30 | 40 | 326 / 274 | 0.50 by construction | 0.5004 | 0.454–0.547 | n/a | 0% | 2.5% | 40 FAIL does not predict |
| **W-K** mutant | the same files, with sizes normalised over the whole file (strip.js) | 40 | 326 / 274 | n/a | **0.5978** | 0.552–0.643 | n/a | 55% | 97.5% | 22 PASS below target, 17 INCONCLUSIVE, 1 FAIL |
| **W-E** | 1,000 accounts with planted E1–E7 cases | 1 | 210 / 320 | n/a | n/a | n/a | n/a | n/a | n/a | the reconciliation equals the ground truth exactly |

**W-E reconciliation, script vs ground truth:** E1 230 (200 of them breached by trade 30), E2 20, E3 20, E4 100, E5 50, E6 20, E7 30, eligible 530. Every count is identical.

## Acceptance (plan §5.1, batch S3)

| Rule | Result |
|---|---|
| Recovery: the study AUC is unbiased for the population AUC of DT-1 | **Met.** W-L +0.0013 (0.9 MC SE); W-M −0.0021 (1.5 MC SE) |
| Coverage of about 95% | **Met.** 96.5% and 97.5% at R = 200, where the Monte Carlo SE is about 1.5 points. Both are within 2 SE. The DeLong interval runs slightly wide, which is the safe side. |
| W-0 H1 false pass ≤ 3.6% | **Met.** 0 of 300 |
| W-C H2 false-pass rate reported. If above 5%, B0 is revised before posting. | **0 of 300 (0.0%).** B0 does not need to change. |
| The W-K mutant is caught | **Met.** The whole-file normaliser raises the AUC from 0.500 to 0.598, and makes it higher in all 40 paired replications. The within-W script stays at 0.500. |
| W-E counts equal the ground truth exactly | **Met** |

## Findings to read before posting

1. **30 trades lose some of the signal.** In W-L the hidden trait has an AUC of 0.70, while DT-1 from 30 trades reaches 0.665. Thirty trades measure the trait with noise.
2. **H2 is conservative when habits act through volatility.** In the mechanical world (W-M), habits really do cause breaches: impulsive traders size up after losses. Yet H2 passed only 16.5% of the time, because those same habits raise per-trade P&L volatility (B2) and move P&L so far and headroom (B3, B4). B0 then absorbs most of the effect. The W-C result shows the reverse case is clean: when habits only stand in for volatility, H2 never falsely passes. In real firm data, a "FAIL: adds nothing" can therefore happen even when the habits are the cause. This is the price of a strong baseline, chosen on purpose (§2.6 of the plan). The registration states the measured rates in §3.2. The **Architect and Manager** have to decide whether to accept this as written or to change the H2 baseline **before** posting. Changing it later would be a deviation.
3. **The look-ahead leak is real and is blocked.** Normalising size over the whole file (the paid report's strip.js) leaks later trades into the features. The within-W rule removes the leak entirely.

Seeds:
- replications: 20261101 + 100000 × the world's index + the replication number;
- populations: 20261101 + 7000000 + 1000 × ord(world) + the chunk number;
- W-E: 20261101 + 999.
