Reports copied byte for byte from dt-private `tests/fixtures/expected/` on branch `delivery-39-rd2` after the R-D3
addendum 3 I-9 (method `2026-10-23.stats2f`: dates-only files, where 5% or more of the rows open at 00:00 and are
held whole days, are not merged and their order-based habits are blanked; other rows sharing open minute, symbol and
direction merged into one trade, date-only rows never;
hold_gap and size_up described, not tested; revenge and tilt as stats2c). They are the engine's output (JS = Python) on:
- `random` — revenge too_few, tilt not distinguishable (case 1); the coverage lines name revenge;
- `stats__02-spread-trend_right_skew-200` — the stats2 spread-withhold file; V-launch and V-launch-size like every report;
- `stats-r2__33-probe-sizeup0` — the Tester's sizeup0 probe: under stats2b size_up was distinguishable with no trade
  in its dollar figure (case 4, N-none); under stats2c/2d size_up renders M1 and V-launch-size and page 1 is case 1;
- `planted_revenge` — revenge shown first, tilt distinguishable the opposite way (case 6);
- `stats-r2__32-probe-dirnull` — the Tester's dir_null probe (case 9): case 1, with M3 (every loser held 12 hours or more);
- `stats-r2__34-partial-rows` — decisions exported as 1 to 4 rows (a position closed in parts): 488 rows became 263
  trades, so page 1 shows the merged-rows line;
- `stats-r2__21-dateonly` — every trade at 00:00 and held whole days (a date-only export): dates-only, "All 200 trades";
- `stats-r2__35-dates-mixed` — 12 of 200 rows date-only (6%): dates-only, "12 of the 200 trades";
- `stats-r2__36-dates-few` — 9 of 200 rows date-only (4.5%): a timed report, tested as normal;
- `too_few` — a timed file whose habits are all too few: n_tested 0, so page 1 says none could be tested.
Re-copy them whenever dt-private's goldens change (tests/test_paid_wording.py checks the method version).
