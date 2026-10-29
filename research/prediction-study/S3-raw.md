# S3 raw results (full)

pop_chunk equals classify on 3,000 accounts: W-L True, W-M True

population W-L: 200000 accounts, 200000 eligible, 69666 breaches, DT-1 AUC 0.6645; features reentry_share 0.625, streak_share 0.503, size_after_loss_ratio 0.696, size_after_loss_share 0.608, large_loss_share 0.520, hold_gap_ratio 0.616
population W-M: 200000 accounts, 165048 eligible, 40984 breaches, DT-1 AUC 0.6449; features reentry_share 0.617, streak_share 0.654, size_after_loss_ratio 0.593, size_after_loss_share 0.538, large_loss_share 0.510, hold_gap_ratio 0.554

{"bias": 0.001347530463645108, "bias_mcse": 0.001446176287086033, "breaches": 210.71, "cli_agree": true, "coverage": 0.965, "h1_pass": 1.0, "h2_pass": 1.0, "mean_auc": 0.665881177772175, "mean_hi": 0.7116236774665677, "mean_lo": 0.6201386780777824, "measured": 200, "pop_auc": 0.6645336473085299, "reps": 200, "sd_auc": 0.020452021187794347, "survivors": 389.29, "verdict_pass": 1.0, "verdicts": {"PASS: below target": 40, "PASS: meets target": 160}, "world": "L"}
{"bias": -0.0020621515481507036, "bias_mcse": 0.0014204195873264134, "breaches": 183.76, "cli_agree": true, "coverage": 0.975, "h1_pass": 0.99, "h2_pass": 0.165, "mean_auc": 0.6428510740471998, "mean_hi": 0.6878320110249179, "mean_lo": 0.5978701370694818, "measured": 200, "pop_auc": 0.6449132255953505, "reps": 200, "sd_auc": 0.020087766446574087, "survivors": 558.3, "verdict_pass": 0.165, "verdicts": {"FAIL: adds nothing": 165, "INCONCLUSIVE": 2, "PASS: below target": 6, "PASS: meets target": 27}, "world": "M"}
{"breaches": 210.28, "cli_agree": true, "h1_pass": 0.0, "h2_pass": 0.0, "mean_auc": 0.4983874738645604, "mean_hi": 0.546891496713841, "mean_lo": 0.4498834510152798, "measured": 300, "reps": 300, "sd_auc": 0.02392050716723235, "survivors": 389.72, "verdict_pass": 0.0, "verdicts": {"FAIL: does not predict usefully": 297, "INCONCLUSIVE": 3}, "world": "0"}
{"breaches": 210.54, "cli_agree": true, "h1_pass": 0.9933333333333333, "h2_pass": 0.0, "mean_auc": 0.6557651618081947, "mean_hi": 0.7018975418375439, "mean_lo": 0.6096327817788454, "measured": 300, "reps": 300, "sd_auc": 0.022508877055380194, "survivors": 389.46, "verdict_pass": 0.0, "verdicts": {"FAIL: adds nothing": 298, "INCONCLUSIVE": 2}, "world": "C"}
{"breaches": 325.8, "cli_agree": true, "h1_pass": 0.0, "h2_pass": 0.025, "mean_auc": 0.5003500972432836, "mean_hi": 0.5468464800793259, "mean_lo": 0.4538537144072413, "measured": 40, "reps": 40, "sd_auc": 0.021780513380472506, "survivors": 274.2, "verdict_pass": 0.0, "verdicts": {"FAIL: does not predict usefully": 40}, "world": "K"}
{"breaches": 325.8, "cli_agree": true, "h1_pass": 0.55, "h2_pass": 0.975, "mean_auc": 0.5977735522538913, "mean_hi": 0.6433472972813495, "mean_lo": 0.552199807226433, "measured": 40, "reps": 40, "sd_auc": 0.02107051639863091, "survivors": 274.2, "verdict_pass": 0.55, "verdicts": {"FAIL: does not predict usefully": 1, "INCONCLUSIVE": 17, "PASS: below target": 22}, "world": "K-mutant"}

W-E reconciliation {"E1": 230, "E1_breached_before_t0": 200, "E2": 20, "E3": 20, "E4": 100, "E5": 50, "E6": 20, "E7": 30, "breaches": 210, "eligible": 530, "read": 1000, "survivors": 320}
W-E truth {"E1": 230, "E1_breached_before_t0": 200, "E2": 20, "E3": 20, "E4": 100, "E5": 50, "E6": 20, "E7": 30, "eligible": 530, "read": 1000}
W-E exact match: True; CLI verdict agrees: True

seeds: replications SEED 20261101 + 100000 * world index + replication; populations SEED + 7000000 + 1000 * ord(world) + chunk
run time 3132 s
