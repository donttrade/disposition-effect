# Example sealed block for the synthetic fixture (not a registration)

This file seals the parameters for the **synthetic** files that `make_fixture_prediction.py` writes with its defaults. Its only use is to check, byte for byte, that your copy of `prediction_test.py` prints the README's expected output. It is not the study's registration. The real one is `PREREG-PREDICTION.md`, completed and posted on OSF.

--- BEGIN SEALED PARAMETERS ---
[prediction-study]
registration = "EXAMPLE: synthetic fixture, not a registration"
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
outcome_mode = "firm"
pnl_basis = "net"
firm_label = "synthetic fixture"
period_start = "2026-01-01"
period_end = "2026-02-28"
data_cut = "2026-06-30"
accounts_in_period = 600
day_start = "00:00"
day_utc_offset = "+02:00"
--- END SEALED PARAMETERS ---
