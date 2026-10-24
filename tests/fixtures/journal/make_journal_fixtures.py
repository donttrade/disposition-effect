"""Overlapping-export fixtures for the journal import (ARCHITECT-V3 J2 / Tester J6, J7).

full.csv: Jan-Apr 2026, one closed round trip per row (the generic round-trip format).
a.csv: the Jan-Mar rows; b.csv: the Feb-Apr rows (they overlap by Feb-Mar).
twins.csv: two identical trades inside one file, plus one more (J7).
possible.csv: a.csv's first trade with another close price (J8, a possible duplicate).
Deterministic: run it again and the files are byte-identical.
"""
import datetime as dt
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD = "Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees\n"
rng = random.Random(20261021)
rows = []
t = dt.datetime(2026, 1, 5, 9, 0)
while t < dt.datetime(2026, 4, 30):
    if t.weekday() < 5:
        for _ in range(rng.randint(1, 4)):
            o = t + dt.timedelta(minutes=rng.randint(0, 400))
            c = o + dt.timedelta(minutes=rng.randint(5, 180))
            sym = rng.choice(["EURUSD", "XAUUSD", "US500"])
            d = rng.choice(["Long", "Short"])
            p = {"EURUSD": 1.08, "XAUUSD": 2350.0, "US500": 5200.0}[sym]
            op = round(p * (1 + rng.uniform(-0.01, 0.01)), 5)
            cp = round(op * (1 + rng.uniform(-0.003, 0.003)), 5)
            rows.append((o, c, sym, d, rng.choice([1, 2, 5]), op, cp, 1.5))
    t += dt.timedelta(days=1)
rows.sort()


def line(r):
    return f"{r[0]:%Y-%m-%d %H:%M:%S},{r[1]:%Y-%m-%d %H:%M:%S},{r[2]},{r[3]},{r[4]},{r[5]},{r[6]},{r[7]}\n"


def write(name, rs):
    with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="") as f:
        f.write(HEAD + "".join(line(r) for r in rs))


write("full.csv", rows)
write("a.csv", [r for r in rows if r[1] < dt.datetime(2026, 4, 1)])
write("b.csv", [r for r in rows if r[1] >= dt.datetime(2026, 2, 1)])
write("twins.csv", [rows[0], rows[0], rows[1]])
first = rows[0]
write("possible.csv", [(first[0], first[1], first[2], first[3], first[4], first[5], round(first[6] * 1.001, 5), first[7])])
