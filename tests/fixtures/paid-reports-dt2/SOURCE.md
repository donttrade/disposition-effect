DT-2 reports (method `2026-10-31.stats3a`, label DT-2): dt-private branch `dt2` at ca2dd5c (E1, E3, F1 c23f9d5, account
index 6b8b82c), `analyse()`
run by the JS engine on every request fixture in dt-private `tests/fixtures/` (`planted`, `planted_revenge`, `too_few`,
`random`, `stats/*`, `stats-r2/*`), with `engine_commit` "golden" and the catch figures included (the Python reference
has none, so dt-private's own `expected/` goldens carry `catch: null`). Written by `make_dt2_reports.mjs`:

    node tests/fixtures/paid-reports-dt2/make_dt2_reports.mjs /path/to/dt-private tests/fixtures/paid-reports-dt2

Steps in this set: Clear (planted_revenge revenge), Some (stats__04, stats__07 both habits, stats__12, stats-r2__30 tilt),
small groups of 5-9 (stats-r2__25, stats__05 revenge, stats__11 tilt), clock guard on (stats-r2__32), No sign, too few (too_few, stats__13, stats-r2__23/24/26/32/33), dates only (stats-r2__21, __35),
merged rows (stats-r2__34), small files (too_few 20, stats-r2__25 30, stats__13 60, stats-r2__24 63 trades).
Regenerate them whenever the engine's method changes (tests/test_dt2_report.py checks the method version).
