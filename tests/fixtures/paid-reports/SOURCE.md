Reports copied byte for byte from dt-private `tests/fixtures/expected/` at commit 36d5d39 (branch
`delivery-39-rd2`, R-D2 H-1: method `2026-10-23.stats2b`, hold_gap described, not tested). They are the
engine's output (JS = Python) on:
- `random` — under stats2 a hold_gap gap was shown first; under stats2b nothing is distinguishable (case 1),
  and revenge is too_few (the coverage lines name it);
- `stats__02-spread-trend_right_skew-200` — the stats2 spread-withhold file; now V-launch like every report;
- `stats-r2__33-probe-sizeup0` — the Tester's sizeup0 probe: size_up distinguishable with no trade in
  its dollar figure (case 4, N-none); hold_gap renders V-launch (R-D2 supersedes D-1's V-spread0 here);
- `planted_revenge` — revenge shown first, tilt distinguishable the opposite way (case 6);
- `stats-r2__32-probe-dirnull` — the Tester's dir_null probe (case 9): case 1 for the three tested habits,
  with M3 (every loser held 12 hours or more).
Re-copy them whenever dt-private's goldens change (tests/test_paid_wording.py checks the method version).
