#!/usr/bin/env python3
"""per_market.py: the 5 November 2026 sell-off study, market by market.

DESCRIPTIVE, ADDED AFTER THE WRITTEN PLAN. This breakdown is not one of the measures stated in ANALYSIS-PLAN.md. It splits the
study's own counts by market so that each market can be checked on its own. It uses the SAME rows, filters and force-close rule as
run_day.py: the table-building SQL below is copied from run_day.py character for character (tests/test_selloff.py checks that).

Three steps:
  1. python3 -I per_market.py run DATA_DIR DAYS_DIR [--delete]
       Downloads the 31 daily files of ironflow/hyperliquid-trades AT THE REVISION THE STUDY USED (below), one at a time, checks each
       SHA-256 against RUN-LOG.txt (the hashes are copied into INPUTS here), counts force-closes per market and writes DAYS_DIR/DAY.json
       (counts only). With --delete each Parquet file is removed once counted. A file already in DATA_DIR is reused if its hash matches.
  2. python3 -I per_market.py build DAYS_DIR OUT_CSV
       Joins the 31 days, checks the totals against the published study (SUMMARY.json and the daily CSV, see EXPECT), applies the
       plan's small-cell rule (no cell under 10 wallets is published) and writes the CSV.
  3. sha256sum OUT_CSV   (compare with the hash printed on the study page and in MARKETS-README.txt)

Ironflow replaced five daily files (6, 10, 11 Oct; 4, 5 Nov) on 6 Nov 2026 at 23:24 UTC, after this study ran. The current files on
the dataset's main branch therefore have different hashes. REVISION pins the dataset version the study read.
Data: Ironflow (ironflow.sh), Hyperliquid trades, CC BY 4.0. No wallet address is written to any output.
Needs: Python 3.10+, duckdb (tested with 1.1.3).
"""
import csv
import datetime as dt
import glob
import hashlib
import json
import os
import statistics as st
import sys
import urllib.request

REVISION = "8e0c2f593fdbf324772db734747ccfce597f3b80"  # ironflow/hyperliquid-trades, commit of 2026-11-06T04:16:06Z
URL = "https://huggingface.co/datasets/ironflow/hyperliquid-trades/resolve/" + REVISION + "/data/{day}.parquet"
EVENT = "2026-11-05"
# SHA-256 of each input file, copied from RUN-LOG.txt (tests check they match it)
INPUTS = {
    "2026-10-06": "487d5d211b64de742b2d0cfdcdcd9bf6c1786b12bd9b5989449b0604a0f5d842",
    "2026-10-07": "81372a3595b99b93771b737f1e3fc4933661c534b03288dd250176dcfed9e984",
    "2026-10-08": "58bd62009f36c8c3e805d0571103647accfc852815cf67777bd718a866c0b9a5",
    "2026-10-09": "f6bd44f375732900a7e0b73a7da0950a321c981d7dbee8379e0a866faf2f64b7",
    "2026-10-10": "f35687b00fdca24ae3bf7bbf9e54b428173f5840875b485104ddcc90276aa2aa",
    "2026-10-11": "dd61c2930ff0a1aba03bd4d600410d7589552306fc2f4f7323831ab72d9ff86d",
    "2026-10-12": "dfbe490e4f2d983de74fa7da73e81d2ac51778eeec6d75db4f96a06fe3684142",
    "2026-10-13": "6689e6801cb6ad1e10ffafaae236a6e478b7f4f6e0a401ebd07193b0084764dc",
    "2026-10-14": "3373e2ff133f4b4413f4323fca616706647f470d21d16dae56276c278b4aa709",
    "2026-10-15": "5655ac641563ab4c191bb39697c703f17f8432b7be3567700891e9ebde25f729",
    "2026-10-16": "bacaffd2569e9c996ae859c851a82637aa48784b4332a2a4f492ba28a30a2dbc",
    "2026-10-17": "42772f54f7743008f251e7068637a8b0327eda81eb43f1f51e6eadabd55de4a6",
    "2026-10-18": "496c3f5d15a0b5831afe5c3a6006c8bcaa1b20639f2fd705e337ada54c1e2059",
    "2026-10-19": "0acacbc192dff1cc403dd45a196a12985d1dd730089dc709b047f6536e4aa213",
    "2026-10-20": "350bab81e189bd14bcc2a5264746f9b4ae7744ae8b3d689794e45705fdfea1e9",
    "2026-10-21": "1d9ffee7a99ba86c75b6912c0052f6001d68e9dbc53a77cbad0e791845585788",
    "2026-10-22": "10b1f1f01ddfa88cb9bbf9b57280109e4bb5a54497b85a5647ad1e2280c20371",
    "2026-10-23": "3241a0c72399c37317c47963157e6df3f880c4882681dc6275396df1687d2d15",
    "2026-10-24": "403cd1703518c0f4f4046d99b18ab7122de8ee1aff15bb3c4ce429e7d3320f89",
    "2026-10-25": "35c9f3db6844818d0167e0fd7d958ae5b20ff0346566816d29a51a9165a6600a",
    "2026-10-26": "abfaf921c7f991cf2c44b6f18ade53b10d052ea33056d319b08239ae8e51244a",
    "2026-10-27": "aa5855e53f17888ac2decdb3593228079c6c2aa2825fc48ec7704b1bd6675354",
    "2026-10-28": "0e5b5371ffe4f7010976cc1d3a618a18573ad16b069eebc962a52694f6fc9a3b",
    "2026-10-29": "6a513feeba4376e88ac913c44579dfde41063059be10f15e287a47d739d88558",
    "2026-10-30": "51c08e5e59e6815211372e396788b14ea350fb8e281d5b13dabc2b007e3821a7",
    "2026-10-31": "c53069998ebaafad0ed346e83665ddc7390159171495bb78937aae3b0c440b8f",
    "2026-11-01": "df5849caa2e47972d6b612893170dfa2a4c3a982ab0e83901c860928d78fa572",
    "2026-11-02": "d3832ef1d5f16fa791db1bb759506eee53c4c796f8011763488b933f61a2c28e",
    "2026-11-03": "84d914df5fe60fde8d64f91b9b6e8cdd81f163754636be39fbc9a6f62a14e3c2",
    "2026-11-04": "1c3051344b7ab4b9f9ca65377571f704f4b98bcc4d653710a222c5bf75ac4210",
    "2026-11-05": "decf2e1e65508794133e938c5bce4d74daf8d524df9cf749a31de64d63c0a46d",
}
BASELINE = [d for d in INPUTS if d != EVENT]
MIN_CELL = 10  # ANALYSIS-PLAN.md section 7: cells under 10 wallets are suppressed
# What the published study says for 5 November (SUMMARY.json / the study page). build stops if the per-market data disagree.
EXPECT = {"hip3_liq_wallets": 9054, "liq_wallets": 18813}
COLUMNS = ["date_utc", "row_type", "scope", "dex", "market", "wallets_force_closed", "value_force_closed_usd", "force_close_fills",
           "long_share_of_value", "sum_of_market_wallet_counts", "market_median_wallets_30d", "ratio_5nov_to_median",
           "median_uses_unlisted_days"]


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def fetch(day, data_dir):
    dest = os.path.join(data_dir, day + ".parquet")
    if os.path.exists(dest) and sha256(dest) == INPUTS[day]:
        return dest
    tmp = dest + ".part"
    h = hashlib.sha256()
    with urllib.request.urlopen(URL.format(day=day), timeout=120) as r, open(tmp, "wb") as f:
        for b in iter(lambda: r.read(1 << 20), b""):
            h.update(b)
            f.write(b)
    if h.hexdigest() != INPUTS[day]:
        os.remove(tmp)
        sys.exit(f"{day}: SHA-256 {h.hexdigest()} does not match RUN-LOG.txt ({INPUTS[day]}); stopped")
    os.replace(tmp, dest)
    return dest


def count_day(path, day):
    """Per-market counts for one UTC day. Counts only: no wallet address leaves this function."""
    import duckdb
    c = duckdb.connect()
    # ---- copied from run_day.py, unchanged (lines 6 to 12 and 17) ----
    c.execute("SET TimeZone='UTC'"); c.execute("SET threads=2"); c.execute("SET memory_limit='4GB'")
    d0 = dt.datetime.fromisoformat(day + "T00:00:00+00:00"); d1 = d0 + dt.timedelta(days=1)
    PH = '0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee'
    c.execute(f"""CREATE TEMP TABLE t AS SELECT timestamp ts, market, coalesce(dex,'') dex, notional, taker_side, buyer, seller,
  liquidation liq, block, CASE WHEN taker_side='buy' THEN buyer ELSE seller END taker
  FROM read_parquet('{path}') WHERE market_class='perp' AND buyer<>'{PH}' AND seller<>'{PH}'
  AND timestamp >= TIMESTAMPTZ '{d0.isoformat()}' AND timestamp < TIMESTAMPTZ '{d1.isoformat()}'""")
    c.execute("CREATE TEMP TABLE L AS SELECT * FROM t WHERE liq")
    # ---- end of copied block ----
    q = lambda s: c.sql(s).fetchone()
    r = {"day": day, "input_sha256": sha256(path)}
    # day totals, the same expressions as run_day.py
    r["liq_wallets"] = q("select count(distinct taker) from L")[0]
    r["liq_notional"], r["liq_notional_long"], r["liq_trades"] = q(
        "select coalesce(sum(notional),0), coalesce(sum(notional) filter (where taker_side='sell'),0), count(*) from L")
    r["hip3_liq_wallets"], r["hip3_liq_notional"] = q("select count(distinct taker), coalesce(sum(notional),0) from L where dex<>''")
    r["hip3_liq_notional_long"], r["hip3_liq_trades"] = q(
        "select coalesce(sum(notional) filter (where taker_side='sell'),0), count(*) from L where dex<>''")
    r["core_liq_wallets"], r["core_liq_notional"] = q("select count(distinct taker), coalesce(sum(notional),0) from L where dex=''")
    r["core_liq_notional_long"], r["core_liq_trades"] = q(
        "select coalesce(sum(notional) filter (where taker_side='sell'),0), count(*) from L where dex=''")
    # one wallet can be force-closed in several markets: the number of (wallet, market) pairs
    r["hip3_wallet_market_pairs"] = q("select count(*) from (select distinct taker, market from L where dex<>'')")[0]
    r["core_wallet_market_pairs"] = q("select count(*) from (select distinct taker, market from L where dex='')")[0]
    r["markets"] = [list(x) for x in c.sql(
        """select dex, market, count(distinct taker) w, sum(notional) n, count(*) fills,
           coalesce(sum(notional) filter (where taker_side='sell'),0) n_long
           from L group by 1, 2 order by 1, 2""").fetchall()]
    c.close()
    return r


def cmd_run(data_dir, days_dir, delete):
    os.makedirs(data_dir, exist_ok=True)
    os.makedirs(days_dir, exist_ok=True)
    for day in INPUTS:
        p = fetch(day, data_dir)
        r = count_day(p, day)
        assert r["input_sha256"] == INPUTS[day]
        with open(os.path.join(days_dir, day + ".json"), "w") as f:
            json.dump(r, f, indent=1)
        print(day, r["liq_wallets"], r["hip3_liq_wallets"], round(r["hip3_liq_notional"]), len(r["markets"]), "markets", flush=True)
        if delete:
            os.remove(p)


def money(x):
    return f"{x:.2f}"


def share(x):
    return f"{x:.6f}"


def build(days_dir):
    """Returns (rows for the public CSV, reconciliation dict, full unsuppressed per-market table for 5 Nov)."""
    R = {}
    for f in sorted(glob.glob(os.path.join(days_dir, "2026-*.json"))):
        r = json.load(open(f))
        R[r["day"]] = r
    if sorted(R) != sorted(INPUTS):
        sys.exit(f"need the 31 days {min(INPUTS)} to {max(INPUTS)}; have {len(R)}")
    for d, r in R.items():
        if r["input_sha256"] != INPUTS[d]:
            sys.exit(f"{d}: counted from a file whose hash is not the one in RUN-LOG.txt")
    rec = {"days": {}}
    for d, r in R.items():
        ms = r["markets"]
        h = [m for m in ms if m[0] != ""]
        k = [m for m in ms if m[0] == ""]
        x = {"hip3_value_sum_of_markets": sum(m[3] for m in h), "hip3_value_total": r["hip3_liq_notional"],
             "hip3_wallets_unique": r["hip3_liq_wallets"], "hip3_wallets_sum_of_markets": sum(m[2] for m in h),
             "all_value_sum_of_markets": sum(m[3] for m in ms), "all_value_total": r["liq_notional"],
             "all_wallets_unique": r["liq_wallets"], "all_wallets_sum_of_markets": sum(m[2] for m in ms),
             "core_wallets_unique": r["core_liq_wallets"], "core_wallets_sum_of_markets": sum(m[2] for m in k)}
        assert x["hip3_wallets_sum_of_markets"] == r["hip3_wallet_market_pairs"]
        assert x["core_wallets_sum_of_markets"] == r["core_wallet_market_pairs"]
        assert abs(x["hip3_value_sum_of_markets"] - x["hip3_value_total"]) < 0.01, d
        assert abs(x["all_value_sum_of_markets"] - x["all_value_total"]) < 0.01, d
        x["hip3_overlap"] = x["hip3_wallets_sum_of_markets"] - x["hip3_wallets_unique"]
        x["all_overlap"] = x["all_wallets_sum_of_markets"] - x["all_wallets_unique"]
        rec["days"][d] = x
    e = R[EVENT]
    for key, want in EXPECT.items():
        if e[key] != want:
            sys.exit(f"STOP: {key} on {EVENT} is {e[key]}, the study says {want}")
    rec["event"] = rec["days"][EVENT]

    # each market's own 30-day median of wallets force-closed (a day with no force-close in that market counts as 0)
    per = {}
    for d, r in R.items():
        for dex, mk, w, n, fills, nl in r["markets"]:
            per.setdefault((dex, mk), {})[d] = w
    med = {key: st.median([v.get(d, 0) for d in BASELINE]) for key, v in per.items()}
    # A day with 1 to 9 wallets in a market is counted at its true value in that market's median, but it has no row of its own
    # (the under-10 rule). median_uses_unlisted_days is "yes" when those unlisted days change the median, i.e. when the median
    # cannot be recomputed from the CSV alone (taking a missing day as 0 gives another number); "no" means the CSV reproduces it.
    unlisted = {key: med[key] != st.median([v.get(d, 0) if v.get(d, 0) >= MIN_CELL else 0 for d in BASELINE]) for key, v in per.items()}

    rows = []
    full_event = []
    for d in sorted(R):
        r = R[d]
        for scope, sel in (("builder_listed", lambda m: m[0] != ""), ("core", lambda m: m[0] == "")):
            ms = sorted((m for m in r["markets"] if sel(m)), key=lambda m: (-m[3], m[1]))
            small = [m for m in ms if m[2] < MIN_CELL]
            for dex, mk, w, n, fills, nl in ms:
                if d == EVENT:
                    full_event.append({"scope": scope, "dex": dex, "market": mk, "wallets": w, "value": n, "fills": fills,
                                       "long_share": nl / n if n else None, "median30": med[(dex, mk)]})
                if w < MIN_CELL:
                    continue
                m30 = med[(dex, mk)] if d == EVENT else None
                rows.append([d, "market", scope, dex, mk, w, money(n), fills, share(nl / n) if n else "", "",
                             ("%g" % m30) if m30 is not None else "",
                             (f"{w / m30:.2f}" if m30 else "") if m30 is not None else "",
                             ("yes" if unlisted[(dex, mk)] else "no") if m30 is not None else ""])
            if small:
                sw = sum(m[2] for m in small)
                sn = sum(m[3] for m in small)
                snl = sum(m[5] for m in small)
                # one row for all the markets with fewer than 10 wallets that day, so the rows still add up to the day's value
                # (that total is published anyway). Its wallet column stays blank; its count of (wallet, market) pairs is
                # shown only when it is 10 or more.
                rows.append([d, "markets_under_10_wallets_combined", scope, "", f"{len(small)} markets", "",
                             money(sn), sum(m[4] for m in small), share(snl / sn) if sn else "", sw if sw >= MIN_CELL else "", "", "", ""])
            pre = "hip3" if scope == "builder_listed" else "core"
            tot_n = r[f"{pre}_liq_notional"]
            rows.append([d, "scope_total_unique_wallets", scope, "", "", r[f"{pre}_liq_wallets"], money(tot_n), r[f"{pre}_liq_trades"],
                         share(r[f"{pre}_liq_notional_long"] / tot_n) if tot_n else "", r[f"{pre}_wallet_market_pairs"], "", "", ""])
        n = r["liq_notional"]
        rows.append([d, "scope_total_unique_wallets", "all_markets", "", "", r["liq_wallets"], money(n), r["liq_trades"],
                     share(r["liq_notional_long"] / n) if n else "", sum(m[2] for m in r["markets"]), "", "", ""])
    return rows, rec, full_event


def cmd_build(days_dir, out_csv):
    rows, rec, full_event = build(days_dir)
    with open(out_csv, "w", newline="") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(COLUMNS)
        w.writerows(rows)
    e = rec["event"]
    print(f"{EVENT} builder-listed: value {e['hip3_value_sum_of_markets']:.2f} (sum of markets) = {e['hip3_value_total']:.2f} (total); "
          f"wallets unique {e['hip3_wallets_unique']}, sum of per-market counts {e['hip3_wallets_sum_of_markets']}, "
          f"overlap {e['hip3_overlap']}")
    print(f"{EVENT} all markets: value {e['all_value_total']:.2f}; wallets unique {e['all_wallets_unique']}, "
          f"sum of per-market counts {e['all_wallets_sum_of_markets']}, overlap {e['all_overlap']}")
    print(f"{out_csv}: {len(rows)} rows, sha256 {sha256(out_csv)}")


if __name__ == "__main__":
    a = sys.argv[1:]
    if len(a) >= 3 and a[0] == "run":
        cmd_run(a[1], a[2], "--delete" in a)
    elif len(a) == 3 and a[0] == "build":
        cmd_build(a[1], a[2])
    else:
        sys.exit(__doc__)
