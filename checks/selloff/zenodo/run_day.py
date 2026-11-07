"""Per-day computation for ANALYSIS-PLAN.md (sha256 21ce82c3...). Usage: python -I run_day.py PARQUET YYYY-MM-DD EVENTS_PARQUET_OR_- OUT_JSON
Outputs counts only. No wallet address is written."""
import sys, json, duckdb, datetime as dt
path, day, events, out = sys.argv[1:5]
c = duckdb.connect()
c.execute("SET TimeZone='UTC'"); c.execute("SET threads=2"); c.execute("SET memory_limit='4GB'")
d0 = dt.datetime.fromisoformat(day + "T00:00:00+00:00"); d1 = d0 + dt.timedelta(days=1)
PH = '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
c.execute(f"""CREATE TEMP TABLE t AS SELECT timestamp ts, market, coalesce(dex,'') dex, notional, taker_side, buyer, seller,
  liquidation liq, block, CASE WHEN taker_side='buy' THEN buyer ELSE seller END taker
  FROM read_parquet('{path}') WHERE market_class='perp' AND buyer<>'{PH}' AND seller<>'{PH}'
  AND timestamp >= TIMESTAMPTZ '{d0.isoformat()}' AND timestamp < TIMESTAMPTZ '{d1.isoformat()}'""")
r = {"day": day}
r["perp_trades"] = c.sql("select count(*) from t").fetchone()[0]
r["rows_outside_day"] = c.sql(f"select count(*) from read_parquet('{path}') where market_class='perp' and (timestamp < TIMESTAMPTZ '{d0.isoformat()}' or timestamp >= TIMESTAMPTZ '{d1.isoformat()}')").fetchone()[0]
r["active_wallets"] = c.sql("select count(*) from (select buyer w from t union select seller from t)").fetchone()[0]
c.execute("CREATE TEMP TABLE L AS SELECT * FROM t WHERE liq")
q = lambda s: c.sql(s).fetchone()
r["liq_trades"], r["liq_notional"], r["liq_notional_long"] = q("select count(*), coalesce(sum(notional),0), coalesce(sum(notional) filter (where taker_side='sell'),0) from L")
r["liq_wallets"] = q("select count(distinct taker) from L")[0]
r["liq_events"] = q("select count(*) from (select distinct taker, market, block from L)")[0]
r["hip3_liq_wallets"], r["hip3_liq_notional"], r["hip3_liq_events"] = q("select count(distinct taker), coalesce(sum(notional),0), count(distinct (taker, market, block)) from L where dex<>''")
r["hip3_active_wallets"] = q("select count(*) from (select buyer from t where dex<>'' union select seller from t where dex<>'')")[0]
r["hip3_top5"] = [list(x) for x in c.sql("select market, count(distinct taker) w, sum(notional) n from L where dex<>'' group by 1 order by n desc limit 5").fetchall()]
r["hourly_liq_notional"] = [list(x) for x in c.sql("select hour(ts) h, sum(notional), count(distinct taker) from L group by 1 order by 1").fetchall()]
# S2 re-trade
c.execute("""CREATE TEMP TABLE F AS SELECT taker w, arg_min(ts, ts) t0, arg_min(block, ts) b0 FROM L GROUP BY 1""")
cut = (d1 - dt.timedelta(minutes=60)).isoformat()
c.execute(f"CREATE TEMP TABLE F2 AS SELECT * FROM F WHERE t0 <= TIMESTAMPTZ '{cut}'")
r["s2_denominator"] = q("select count(*) from F2")[0]
for m in (15, 60):
    r[f"s2_retrade_{m}"] = q(f"""select count(*) from F2 where exists (select 1 from t where not t.liq and t.taker=F2.w
        and t.ts > F2.t0 and t.ts <= F2.t0 + INTERVAL {m} MINUTE and t.block > F2.b0)""")[0]
# V1 validation
if events != "-":
    c.execute(f"""CREATE TEMP TABLE E AS SELECT DISTINCT wallet w, market FROM read_parquet('{events}')
      WHERE timestamp >= TIMESTAMPTZ '{d0.isoformat()}' AND timestamp < TIMESTAMPTZ '{d1.isoformat()}'""")
    c.execute("CREATE TEMP TABLE M AS SELECT DISTINCT taker w, market FROM L")
    r["v1_events_wm"] = q("select count(*) from E")[0]
    r["v1_mine_wm"] = q("select count(*) from M")[0]
    r["v1_both_wm"] = q("select count(*) from (select * from E intersect select * from M)")[0]
    r["v1_events_rows"] = q(f"select count(*) from read_parquet('{events}') where timestamp >= TIMESTAMPTZ '{d0.isoformat()}' AND timestamp < TIMESTAMPTZ '{d1.isoformat()}'")[0]
    r["v1_events_notional"] = q(f"select sum(notional_usd) from read_parquet('{events}') where timestamp >= TIMESTAMPTZ '{d0.isoformat()}' AND timestamp < TIMESTAMPTZ '{d1.isoformat()}'")[0]
    r["v1_events_wallets"] = q("select count(distinct w) from E")[0]
json.dump(r, open(out, "w"), default=str, indent=1)
print(json.dumps({k: v for k, v in r.items() if k not in ("hourly_liq_notional",)}, default=str))
