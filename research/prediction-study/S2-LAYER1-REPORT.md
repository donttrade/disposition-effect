# S2: Layer 1 synthetic check (metrics only)

Batch S2 of `ARCHITECT-PREDICTION-STUDY-2026-10-30.md` §5.1. Synthetic data only. No real account was used.

**What was planted.** Breached accounts' scores were drawn from N(δ, 1) and survivors' scores from N(0, 1), so the true AUC is Φ(δ/√2). Each cell is 2,000 replications through `partner/prediction_metrics.auc_delong`. The H1 pass rule is the pre-registered one: the lower end of the 95% interval is above 0.55.

Reproduce (Claude Code or plain Terminal, repo root): `python3 tests/sim_layer1.py --reps 2000 --confirm`

| True AUC | Per class | Mean AUC | Bias | 95% CI coverage | H1 pass rate | Hanley-McNeil power |
|---|---|---|---|---|---|---|
| 0.50 | 100 | 0.4992 | -0.0008 | 0.940 | 0.001 | 0.001 |
| 0.50 | 200 | 0.5002 | +0.0002 | 0.957 | 0.000 | 0.000 |
| 0.50 | 400 | 0.5003 | +0.0003 | 0.955 | 0.000 | 0.000 |
| 0.55 | 100 | 0.5514 | +0.0014 | 0.940 | 0.035 | 0.025 |
| 0.55 | 200 | 0.5498 | -0.0002 | 0.950 | 0.024 | 0.025 |
| 0.55 | 400 | 0.5500 | +0.0000 | 0.944 | 0.029 | 0.025 |
| 0.60 | 100 | 0.6013 | +0.0013 | 0.949 | 0.259 | 0.240 |
| 0.60 | 200 | 0.5993 | -0.0007 | 0.946 | 0.420 | 0.426 |
| 0.60 | 400 | 0.5998 | -0.0002 | 0.946 | 0.704 | 0.709 |
| 0.65 | 100 | 0.6510 | +0.0010 | 0.955 | 0.731 | 0.735 |
| 0.65 | 200 | 0.6500 | -0.0000 | 0.944 | 0.939 | 0.956 |
| 0.65 | 400 | 0.6499 | -0.0001 | 0.951 | 1.000 | 0.999 |
| 0.70 | 100 | 0.6994 | -0.0006 | 0.947 | 0.979 | 0.983 |
| 0.70 | 200 | 0.7009 | +0.0009 | 0.944 | 1.000 | 1.000 |
| 0.70 | 400 | 0.6998 | -0.0002 | 0.946 | 1.000 | 1.000 |
| 0.75 | 100 | 0.7494 | -0.0006 | 0.947 | 1.000 | 1.000 |
| 0.75 | 200 | 0.7497 | -0.0003 | 0.944 | 1.000 | 1.000 |
| 0.75 | 400 | 0.7498 | -0.0002 | 0.960 | 1.000 | 1.000 |

R = 2000 replications per cell, seed base 20261030.

- mean AUC bias below 0.003 in every cell: **met**
- 95% CI coverage between 93.9% and 96.1% in every cell: **met**
- H1 pass rate at true AUC 0.55 below 3.6% (expected 2.5%): **met**
- H1 pass rate at 0.65, 200/200, inside 95.6% +/- 1.5 points (R = 2000: 93.9%): **NOT MET**
- the same cell at R = 20000: 94.8% (inside 95.6% +/- 1.5 points): **met**


## Findings

1. **Recovery.** The AUC is unbiased (|bias| ≤ 0.0014 in every cell). DeLong 95% intervals cover the true AUC 94.0–96.0% of the time.
2. **False pass.** At a true AUC of 0.55, the H1 pass rate is 2.4–3.5% (expected 2.5%, one-sided). It is highest at 100/100 (3.5%), which is still under the 3.6% limit.
3. **Power at the target (replaces §2.8's 95.6%).** At a true AUC of 0.65 with 200/200, the measured chance of passing H1 is **94.8%** (R = 20,000, Monte Carlo SE ≈ 0.15 points). The R = 2,000 cell gave 93.9%, 0.2 points below the planned 95.6% ± 1.5 band. The 20,000-replication value is inside it.
4. **Why the planning figure is slightly high.** The Hanley–McNeil figure treats the SE as fixed at its value for AUC 0.65. In a real run, the SE is estimated from the data, and it is larger when the estimate comes out lower (nearer 0.5). So the estimates that come close to the line are slightly less likely to clear it. The gap is about 0.8 points at 200/200 and too small to notice elsewhere. **§2.8 of the registration uses the measured column.**
