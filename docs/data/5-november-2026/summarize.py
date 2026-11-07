import json, glob, statistics as st
R = {}
for f in sorted(glob.glob('/home/claude/proj/selloff/out/2026-*.json')):
    r = json.load(open(f)); R[r['day']] = r
E = '2026-11-05'; B = [d for d in R if d != E and d <= '2026-11-04']
assert len(B) == 30, len(B)
def stats(fn, name):
    vals = {d: fn(R[d]) for d in R if d <= E}
    b = sorted(vals[d] for d in B); q = st.quantiles(b, n=4)
    e = vals[E]; rank = 1 + sum(v > e for v in vals.values())
    return {"measure": name, "E": e, "median": st.median(b), "q1": q[0], "q3": q[2], "min": b[0], "max": b[-1],
            "ratio_E_over_median": e / st.median(b) if st.median(b) else None, "rank_of_31": rank,
            "max_day_baseline": max(B, key=lambda d: vals[d])}
out = {}
out['P1_liq_wallets'] = stats(lambda r: r['liq_wallets'], 'P1')
out['P2_liq_notional'] = stats(lambda r: r['liq_notional'], 'P2')
out['P3_share_active_liquidated'] = stats(lambda r: r['liq_wallets'] / r['active_wallets'], 'P3')
out['S1_hip3_liq_wallets'] = stats(lambda r: r['hip3_liq_wallets'], 'S1w')
out['S1_hip3_liq_notional'] = stats(lambda r: r['hip3_liq_notional'], 'S1n')
out['S5_liq_events'] = stats(lambda r: r['liq_events'], 'S5')
out['active_wallets'] = stats(lambda r: r['active_wallets'], 'ctx')
out['perp_trades'] = stats(lambda r: r['perp_trades'], 'ctx')
for m in (15, 60):
    out[f'S2_retrade_{m}_daily'] = stats(lambda r: r[f's2_retrade_{m}'] / r['s2_denominator'], 'S2')
    out[f'S2_retrade_{m}_pooled_baseline'] = sum(R[d][f's2_retrade_{m}'] for d in B) / sum(R[d]['s2_denominator'] for d in B)
out['S2_E_counts'] = {k: R[E][k] for k in ('s2_denominator', 's2_retrade_15', 's2_retrade_60')}
out['S4_long_share_E'] = R[E]['liq_notional_long'] / R[E]['liq_notional']
out['S4_long_share_baseline_median'] = st.median(R[d]['liq_notional_long'] / R[d]['liq_notional'] for d in B)
h = R[E]['hourly_liq_notional']; tot = sum(x[1] for x in h)
# US cash session 14:30-21:00 UTC; hours 15..20 full, hour 14 half (approximation flagged)
out['S3_hours_E'] = h
out['S3_share_hours_15_20_utc'] = sum(x[1] for x in h if 15 <= x[0] <= 20) / tot
out['S3_share_hours_14_20_utc'] = sum(x[1] for x in h if 14 <= x[0] <= 20) / tot
out['S1_top5_E'] = R[E]['hip3_top5']
out['hip3_active_E'] = R[E]['hip3_active_wallets']
v = [R[d] for d in B if d <= '2026-10-31']
out['V1'] = {"days": len(v), "events_wm": sum(r['v1_events_wm'] for r in v), "mine_wm": sum(r['v1_mine_wm'] for r in v),
  "both_wm": sum(r['v1_both_wm'] for r in v), "events_rows": sum(r['v1_events_rows'] for r in v), "my_events": sum(r['liq_events'] for r in v),
  "events_notional": sum(r['v1_events_notional'] for r in v), "my_notional": sum(r['liq_notional'] for r in v)}
out['V1']['precision'] = out['V1']['both_wm'] / out['V1']['mine_wm']; out['V1']['recall'] = out['V1']['both_wm'] / out['V1']['events_wm']
out['rows_outside_day_total'] = sum(R[d]['rows_outside_day'] for d in R)
out['daily'] = {d: [R[d]['liq_wallets'], round(R[d]['liq_notional']), R[d]['active_wallets']] for d in sorted(R)}
json.dump(out, open('/home/claude/proj/selloff/out/SUMMARY.json', 'w'), indent=1, default=str)
print(json.dumps(out, indent=1, default=str))
