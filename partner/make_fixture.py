#!/usr/bin/env python3
"""Write a SYNTHETIC fixture CSV with a planted disposition effect.

Nothing here is real data. Accounts and positions are random hex labels.
Each account holds 8 positions whose mark-to-market pnl follows a random
walk. On a random ~30% of days an account is "in the mood to sell"; on such a
day each winner is closed with probability GAIN_SELL_PROB and each loser with
the lower LOSS_SELL_PROB, so gains are realised more readily than losses.
Every open position is marked (closed=0) on every day; the analysis script's
conditioning rule then discards the days with no sale. Because only days with
at least one sale are kept, the measured ratios come out higher than the raw
sell probabilities; the values below are tuned so that the measured result is
about PGR 0.22 and PLR 0.11 (an unmistakable 2:1 effect).

Deterministic: same --seed gives a byte-identical file. Uses a private
random.Random(seed), never the global generator.

Usage:  python3 make_fixture.py --out fixture.csv --seed 7
"""

import argparse
import csv
import datetime
import random

N_ACCOUNTS = 30
N_POSITIONS = 8
N_DAYS = 60
START_DATE = datetime.date(2024, 1, 2)
SELL_DAY_PROB = 0.30
GAIN_SELL_PROB = 0.10
LOSS_SELL_PROB = 0.05
STEP_SCALE = 10.0


def step(rng):
    """Approximately normal daily move (sum of 12 uniforms, minus 6), scaled.
    Built from rng.random() only, which is stable across Python versions."""
    return (sum(rng.random() for _ in range(12)) - 6.0) * STEP_SCALE


def money(x):
    """Round to cents and avoid printing '-0.00'."""
    return "%.2f" % (round(x, 2) + 0.0)


def build_rows(seed):
    rng = random.Random(seed)

    used = set()

    def new_id(prefix):
        while True:
            label = "%s_%08x" % (prefix, rng.getrandbits(32))
            if label not in used:
                used.add(label)
                return label

    accounts = [new_id("acct") for _ in range(N_ACCOUNTS)]
    # per account: list of [position_id, running_pnl]
    book = {a: [[new_id("pos"), 0.0] for _ in range(N_POSITIONS)] for a in accounts}

    rows = []
    for day in range(N_DAYS):
        date = (START_DATE + datetime.timedelta(days=day)).isoformat()
        for acct in accounts:
            sell_day = rng.random() < SELL_DAY_PROB
            positions = book[acct]
            for i in range(len(positions)):
                pos = positions[i]
                pos[1] += step(rng)
                pnl_text = money(pos[1])
                value = float(pnl_text)
                closing = False
                if sell_day:
                    draw = rng.random()
                    if value > 0 and draw < GAIN_SELL_PROB:
                        closing = True
                    elif value < 0 and draw < LOSS_SELL_PROB:
                        closing = True
                rows.append([acct, date, pos[0], "1" if closing else "0", pnl_text])
                if closing:
                    # a fresh position replaces it from the next day on
                    positions[i] = [new_id("pos"), 0.0]
    return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--out", required=True, help="path of the CSV to write")
    parser.add_argument("--seed", type=int, default=7, help="RNG seed (default 7)")
    args = parser.parse_args()

    rows = build_rows(args.seed)
    with open(args.out, "w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerow(["account_id", "date", "position_id", "closed", "pnl"])
        writer.writerows(rows)
    print("wrote %d synthetic rows to %s (seed %d)" % (len(rows), args.out, args.seed))


if __name__ == "__main__":
    main()
