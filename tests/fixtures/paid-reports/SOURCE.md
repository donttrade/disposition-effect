Reports copied byte for byte from dt-private `tests/fixtures/expected/` on branch `delivery-39-rd2` after R-D3 I-1
(method `2026-10-23.stats2c`: hold_gap and size_up described, not tested; revenge and tilt as stats2b). They are the
engine's output (JS = Python) on:
- `random` — revenge too_few, tilt not distinguishable (case 1); the coverage lines name revenge;
- `stats__02-spread-trend_right_skew-200` — the stats2 spread-withhold file; V-launch and V-launch-size like every report;
- `stats-r2__33-probe-sizeup0` — the Tester's sizeup0 probe: under stats2b size_up was distinguishable with no trade
  in its dollar figure (case 4, N-none); under stats2c size_up renders M1 and V-launch-size and page 1 is case 1;
- `planted_revenge` — revenge shown first, tilt distinguishable the opposite way (case 6);
- `stats-r2__32-probe-dirnull` — the Tester's dir_null probe (case 9): case 1, with M3 (every loser held 12 hours or more).
Re-copy them whenever dt-private's goldens change (tests/test_paid_wording.py checks the method version).
