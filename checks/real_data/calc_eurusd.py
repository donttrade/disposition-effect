#!/usr/bin/env python3
"""Real EURUSD facts for the lot-size preview: one past month of the euro, shown for scale. Not a setup.

Source: Board of Governors of the Federal Reserve System, H.10 Foreign Exchange Rates, historical rates for the
        euro (US dollars per euro, noon buying rates in New York), https://www.federalreserve.gov/releases/h10/hist/dat00_eu.htm
        "Unless otherwise indicated, information on Board's website is in the public domain and may be copied and
        distributed without permission. Please cite to the Board as the source of the information."
        (FRED republishes the series, but FRED's terms restrict caching and commercial use, so the Board is used.)
RULE (fixed in advance; revised 6 Nov after the tools 1-4 teardown, section 8.1):
  * The calendar month before the month of the file's last rate (so the month is surely complete): its lowest and highest noon rate, the range in pips, and the
    average absolute day-to-day move in pips. These are past facts given for scale.
  * No entry, stop, target, lot count or R is derived from them: the stop and the risk are the reader's choices, and a
    level picked from market data would read as a suggestion (the site does not recommend any trade, size or exit).
  * Contract fact shown beside it: one standard lot of EURUSD is 100,000 euros, so 1 pip (0.0001) is 10 US dollars.
    python3 -I checks/real_data/fetch.py --accept-new-h10 && python3 -I checks/real_data/calc_eurusd.py
Run by hand to refresh (never at build time); writes checks/real_data/eurusd.json, which make_tool_real.py reads. The
page names the month the JSON holds. The raw file's SHA-256 is kept in the JSON (the file changes weekly).
"""
import datetime as dt
import hashlib
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
RAW = os.path.join(HERE, "raw", "h10-hist-dat00_eu.htm")
MON = {m: i + 1 for i, m in enumerate("JAN FEB MAR APR MAY JUN JUL AUG SEP OCT NOV DEC".split())}


def load():
    t = open(RAW, encoding="utf-8", errors="replace").read()
    out = []
    for d, v in re.findall(r"<th[^>]*>\s*(\d{1,2}-[A-Z]{3}-\d{2})\s*</th>\s*<td[^>]*>\s*([0-9.]+|ND)\s*</td>", t):
        if v != "ND":
            day, mon, yy = d.split("-")
            out.append((dt.date(2000 + int(yy), MON[mon], int(day)), float(v)))
    return sorted(out)


def main():
    rates = load()
    last = rates[-1][0]
    # the latest month whose last business day is in the file and is followed by a later month's rate
    y, m = (last.year, last.month - 1) if last.month > 1 else (last.year - 1, 12)
    month = [(d, v) for d, v in rates if d.year == y and d.month == m]
    lo, hi = min(v for _, v in month), max(v for _, v in month)
    moves = [abs(month[i][1] - month[i - 1][1]) for i in range(1, len(month))]
    out = {"source": "Federal Reserve Board H.10, euro, noon buying rates in New York",
           "url": "https://www.federalreserve.gov/releases/h10/hist/dat00_eu.htm",
           "licence": "Public domain (Board website notice); cite the Board",
           "raw_sha256": hashlib.sha256(open(RAW, "rb").read()).hexdigest(), "file_last_date": last.isoformat(),
           "month": f"{y}-{m:02d}", "month_label": dt.date(y, m, 1).strftime("%B %Y"), "days": len(month),
           "low": lo, "high": hi, "range_pips": round((hi - lo) * 10000), "avg_daily_move_pips": round(sum(moves) / len(moves) * 10000, 1),
           "first": month[0][1], "last": month[-1][1],
           "series": [v for _, v in month],
           "lot_fact": {"lot_units_eur": 100000, "usd_per_pip": 10}}
    with open(os.path.join(HERE, "eurusd.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(out, f, indent=1)
        f.write("\n")
    print({k: out[k] for k in ("month_label", "days", "low", "high", "range_pips", "avg_daily_move_pips", "first", "last")})


if __name__ == "__main__":
    main()
