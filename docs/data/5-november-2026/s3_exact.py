"""S3 exact: liquidated notional share inside 14:30-21:00 UTC on 5 Nov, plus the busiest 15-minute window. Counts only."""
import sys, duckdb, json
p = sys.argv[1]; c = duckdb.connect(); c.execute("SET TimeZone='UTC'")
PH = '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
c.execute(f"""CREATE TEMP TABLE L AS SELECT timestamp ts, notional, CASE WHEN taker_side='buy' THEN buyer ELSE seller END w
 FROM read_parquet('{p}') WHERE market_class='perp' AND liquidation AND buyer<>'{PH}' AND seller<>'{PH}'""")
tot = c.sql("select sum(notional) from L").fetchone()[0]
ins = c.sql("select sum(notional), count(distinct w) from L where ts >= TIMESTAMPTZ '2026-11-05 14:30:00+00' and ts < TIMESTAMPTZ '2026-11-05 21:00:00+00'").fetchone()
top = c.sql("select strftime(time_bucket(INTERVAL 15 MINUTE, ts), '%Y-%m-%d %H:%M') b, sum(notional) n, count(distinct w) w from L group by 1 order by n desc limit 3").fetchall()
print(json.dumps({"total": tot, "us_session_notional": ins[0], "us_session_share": ins[0]/tot, "us_session_wallets": ins[1],
                  "top15": [[str(b), n, w] for b, n, w in top]}, indent=1))
