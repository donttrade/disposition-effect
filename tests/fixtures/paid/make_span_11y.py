#!/usr/bin/env python3
"""Writes span_11y.csv: 420 round trips over about 11.5 years (delivery plan C-10 browser test).
Deterministic (no randomness): a trade every 10 days at 10:00 + (i % 5) h, held 600 + 37 * (i % 9) s, two
symbols, wins and losses mixed. The first ~1.5 years fall outside the server's 10-year window."""
import datetime as dt
import os

HERE = os.path.dirname(os.path.abspath(__file__))
start = dt.datetime(2014, 1, 6, 10, 0, 0)
lines = ["Open Time,Close Time,Symbol,Direction,Volume,Open Price,Close Price,Fees"]
for i in range(420):
    o = start + dt.timedelta(days=10 * i, hours=i % 5)
    c = o + dt.timedelta(seconds=600 + 37 * (i % 9))
    win = (i * 7) % 11 < 5
    px = 100 + (i % 13)
    close = px + (1 + (i % 4) * 0.25) * (1 if win else -1)
    lines.append(f"{o:%Y-%m-%d %H:%M:%S},{c:%Y-%m-%d %H:%M:%S},{'AAA' if i % 2 else 'BBB'},Long,{10 + i % 3},{px:.2f},{close:.2f},0")
with open(os.path.join(HERE, "span_11y.csv"), "w", encoding="utf-8", newline="\n") as f:
    f.write("\n".join(lines) + "\n")
