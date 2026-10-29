#!/usr/bin/env python3
"""Write site/static/samples/example-trades.csv: the synthetic "Try with example data" for the
free dashboard (and the homepage screenshot).

    python3 checks/make_demo_trades.py          # rewrite the file
    python3 checks/make_demo_trades.py --check  # exit 1 if the committed file differs

SYNTHETIC: made-up trades from a seeded generator, not a real trader. The symbols are
fictional (EX-A, EX-B, EX-C) so the file can never be read as a real account.

What it is built to show (so every panel of the dashboard has something to say):
  * 160 round trips over about 16 weeks, generic template layout, USD, $1 fee per fill;
  * losing trades held much longer than winning ones (the hold-time check comes out
    "distinguishable from noise");
  * a slightly positive mean result that the expectancy check calls "may be noise";
  * one planted run of 6 losing trades.
Deterministic: Python's random.Random(seed) gives the same sequence on every platform.
"""
import datetime as dt
import os
import random
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "site", "static", "samples", "example-trades.csv")
SEED = 20261021
N = 160
SYMBOLS = {"EX-A": 48.0, "EX-B": 112.0, "EX-C": 23.5}   # 29 Oct (owner): no "demo" anywhere


def make():
    rnd = random.Random(SEED)
    day = dt.date(2026, 6, 1)  # a Monday
    lines = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    prices = dict(SYMBOLS)
    made = 0
    planted = set(range(97, 103))  # trades 97..102 are the planted losing run
    while made < N:
        if day.weekday() >= 5:
            day += dt.timedelta(days=1)
            continue
        # up to 2 trades a day, one after the other, so no symbol is ever open twice
        t = dt.datetime.combine(day, dt.time(9, 35)) + dt.timedelta(minutes=rnd.randint(0, 40))
        for _ in range(rnd.choice((1, 2, 2))):
            if made >= N:
                break
            sym = rnd.choice(sorted(SYMBOLS))
            px = prices[sym]
            qty = rnd.choice((20, 25, 30, 40, 50))
            long_ = rnd.random() < 0.65
            win = (made not in planted) and rnd.random() < 0.52
            if win:
                hold = rnd.randint(6, 45)                # winners closed fast
                move = rnd.uniform(0.6, 2.4) / 100
            else:
                hold = rnd.randint(25, 160)              # losers held longer
                move = -rnd.uniform(0.5, 2.0) / 100
            exit_px = px * (1 + move) if long_ else px * (1 - move)
            close = t + dt.timedelta(minutes=hold, seconds=rnd.randint(0, 59))
            side_in, side_out = ("Buy", "Sell") if long_ else ("Sell", "Buy")
            lines.append(f"{t:%Y-%m-%d},{t:%H:%M:%S},{sym},{side_in},{qty},{px:.2f},USD,1.00")
            lines.append(f"{close:%Y-%m-%d},{close:%H:%M:%S},{sym},{side_out},{qty},{exit_px:.2f},USD,1.00")
            prices[sym] = round(exit_px * (1 + rnd.uniform(-0.004, 0.004)), 2)
            t = close + dt.timedelta(minutes=rnd.randint(10, 50))
            made += 1
        day += dt.timedelta(days=1)
    return "\n".join(lines) + "\n"


def main(argv):
    text = make()
    if "--check" in argv:
        with open(OUT, encoding="utf-8") as f:
            same = f.read() == text
        print("example-trades.csv:", "up to date" if same else "DIFFERS from the generator")
        return 0 if same else 1
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print(f"wrote {OUT} ({text.count(chr(10)) - 1} fills)")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
