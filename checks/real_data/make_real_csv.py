#!/usr/bin/env python3
"""Turn the public Stock Transactions Dataset into the site's CSV template, by a rule fixed in advance.

Source: Stock Transactions Dataset, Mendeley Data, DOI 10.17632/k4tnk2nggv.1, licence CC BY 4.0
        (https://data.mendeley.com/datasets/k4tnk2nggv/1). One anonymous investor, US stocks, 2020-2024.
        File: "Open Stock Transaction Data 2020-2024.xlsx", SHA-256 000dbad9...373bcb (equals the hash the
        Mendeley API publishes for the file).

SELECTION RULE (written before any result was computed; nothing below looks at a trade's result):
  1. Sheet "2020-2024 with Splits": the dataset's own combined, split-adjusted sheet of the investor's
     transactions (both of the investor's accounts, as the authors combined them).
  2. Keep every row whose Action is "Market buy" or "Market sell". Dividends, interest, deposits and
     withdrawals are not trades and are dropped (they also carry the only free-text and bank details).
  3. Shares and price: the split-adjusted columns where the sheet fills them, else the raw columns.
  4. Keep USD-priced rows only (the free tools analyse one currency; the sheet has 2 GBX rows).
  5. Time order; ties keep file order. Fees are left at 0: the results are price gains in US dollars,
     before fees, FX conversion and dividends. Tickers are kept in the CSV (the tools need a symbol) but are
     never shown on the page.
CHANGES MADE (CC BY 4.0 s.3(a)(1)(B)): rows selected and reformatted as above; nothing else altered.

Writes checks/real_data/raw/real-trades.csv (gitignored, never committed: it holds the real tickers; the repo keeps
only its SHA-256 and the coded copy, make_coded_csv.py) and prints its SHA-256 and the counts. The raw xlsx comes
from fetch.py, which runs this script after the download. A file whose SHA-256 is not CSV_SHA is refused.
    python3 -I checks/real_data/make_real_csv.py
"""
import csv
import hashlib
import math
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw", "mendeley-open-stock-transactions-2020-2024.xlsx")
OUT = os.path.join(HERE, "raw", "real-trades.csv")
RAW_SHA = "000dbad9f8ed661f7991ad72b3af29f11e9cda2d5a50162f34bf289f78373bcb"
# the SHA-256 of the file this script writes, recorded in site/config/tool_real.json; a different output is refused
CSV_SHA = "b20de3f29d48d91ea6bc5e3f903b1a4114ff1d2465be927c0852c0131d0ea518"


def sha(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def num(v):
    try:
        x = float(v)
        return None if math.isnan(x) else x
    except (TypeError, ValueError):
        return None


def main():
    if sha(RAW) != RAW_SHA:
        sys.exit("input file changed: SHA-256 differs from the published one")
    d = pd.read_excel(RAW, sheet_name="2020-2024 with Splits")
    d = d[d["Action"].isin(["Market buy", "Market sell"])].copy()
    n_trades_all = len(d)
    rows = []
    for i, r in d.iterrows():
        qty = num(r["No. of shares adjusted for split(s)"]) or num(r["No. of shares"])
        px = num(r["Price / share adjusted for split(s) (USD)"]) or num(r["Price / share (USD)"])
        cur = str(r["Currency (Price / share)"]).strip()
        date = pd.Timestamp(r["Transaction Date"]).date()
        t = r["Time"]
        hms = t.strftime("%H:%M:%S") if hasattr(t, "strftime") else str(t)[:8]
        rows.append((f"{date} {hms}", i, date.isoformat(), hms, str(r["Ticker"]).strip(),
                     "Buy" if r["Action"] == "Market buy" else "Sell", qty, px, cur))
    usd = [r for r in rows if r[8] == "USD" and r[6] and r[7]]
    usd.sort(key=lambda r: (r[0], r[1]))
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", newline="\n", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["Date", "Time", "Symbol", "Side", "Quantity", "Price", "Currency", "Fees"])
        for r in usd:
            w.writerow([r[2], r[3], r[4], r[5], f"{r[6]:.8g}", f"{r[7]:.6g}", "USD", "0"])
    print({"market_rows": n_trades_all, "usd_rows_written": len(usd), "dropped_non_usd_or_blank": n_trades_all - len(usd),
           "first": usd[0][0], "last": usd[-1][0], "symbols": len({r[4] for r in usd}), "csv_sha256": sha(OUT)})
    if sha(OUT) != CSV_SHA:
        sys.exit(f"the trade file differs from the one the site was made from (SHA-256 {CSV_SHA}): check the rule")


if __name__ == "__main__":
    main()
