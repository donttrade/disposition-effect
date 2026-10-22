Reports copied byte for byte from dt-private `tests/fixtures/expected/` at commit 8ea4218 (branch
`delivery-39`, C-1: method `2026-10-21.stats2`). They are the R2 engine's output (JS = Python) on:
- `random` — a hold_gap gap, distinguishable, the habit's way, shown first (truth-table case 2);
- `stats__02-spread-trend_right_skew-200` — hold_gap withheld by the spread rule (finite ratio);
- `stats-r2__33-probe-sizeup0` — the Tester's sizeup0 probe: size_up distinguishable with no trade in
  its dollar figure (case 4, N-none) and hold_gap withheld with an infinite (null) ratio;
- `planted_revenge` — revenge shown first, tilt distinguishable the opposite way (case 6);
- `stats-r2__32-probe-dirnull` — the Tester's dir_null probe (case 9): hold_gap too_few.
Re-copy them whenever dt-private's goldens change (tests/test_paid_wording.py checks the method version).
