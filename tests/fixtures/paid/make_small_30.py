#!/usr/bin/env python3
"""S4 (small-file facts and challenge check): a hand-built 30-trade file with facts worked out by hand.

    python3 tests/fixtures/paid/make_small_30.py      # writes tests/fixtures/paid/small-30.csv

One symbol, one contract, no fees, long trades only (P&L = exit − entry, entry 200), 5 weekdays from Mon 1 Jun 2026, 6 trades
a day: trade k of a day opens at 09:30 + 15 min × (k − 1) and closes 10 minutes later (times in UTC).
The expected facts are in tests/test_small_facts.py (EXPECT_30)."""
import datetime as dt
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CSV = os.path.join(HERE, "small-30.csv")
DAYS = [
    [140, -20, 130, -10, 125, 115],     # Mon 1 Jun: +480
    [-50, -60, -70, -80, -90, 20],      # Tue 2 Jun: -330, at the daily limit (300 on a 10,000 FTMO 1-Step) at trade 11
    [300, 10, -15, 35, 5, 20],          # Wed 3 Jun: +355
    [-40, -40, 100, -25, -40, -30],     # Thu 4 Jun: -75
    [10, -120, -100, -90, 150, 300],    # Fri 5 Jun: +150, reaches -300 exactly at trade 28
]


def make_csv():
    lines = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    for i, day in enumerate(DAYS):
        d = dt.date(2026, 6, 1) + dt.timedelta(days=i)
        for k, pnl in enumerate(day):
            o = dt.datetime.combine(d, dt.time(9, 30)) + dt.timedelta(minutes=15 * k)
            c = o + dt.timedelta(minutes=10)
            lines.append(f"{o.date()},{o.time()},EX-A,Buy,1,200.00,USD,0.00")
            lines.append(f"{c.date()},{c.time()},EX-A,Sell,1,{200 + pnl:.2f},USD,0.00")
    with open(CSV, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return CSV


if __name__ == "__main__":
    print("wrote", make_csv())
