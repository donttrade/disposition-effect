"""Writes the S3 merged-upload fixtures (CSV template, round-trip form) next to this script. Deterministic.

acct_a.csv          60 trades, ES/NQ, 30 minutes apart. Trades 58 and 59 are the same symbol and direction, opened
                    and closed 1 minute apart IN THE SAME FILE (they never collapse).
acct_b.csv          45 trades: copies of acct_a trades 0-29 at half size with a lag of 0,3,6,9,12,15 minutes (5 each; all
                    collapse: the window is 15 minutes), copies of trades 30-34 at a lag of 16 minutes (none collapse;
                    they are the 5 near-copies, 15 to 60 minutes apart), and 10 CL trades of its own.
acct_a_overlap.csv  acct_a's trades 40-59 again (an overlapping export: counted once) plus 20 new ES trades.
acct_c.csv          25 GC trades of its own: acct_a + acct_b + acct_c = 60 + 45 - 30 + 25 = 100 trades.
"""
import datetime as dt
import os

HERE = os.path.dirname(os.path.abspath(__file__))
HEAD = "Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees\n"
T0 = dt.datetime(2026, 9, 1, 9, 0)


def row(o, c, sym, d, q, p0, p1, fee):
    f = "%Y-%m-%d %H:%M:%S"
    return f"{o.strftime(f)},{c.strftime(f)},{sym},{d},{q},{p0:.2f},{p1:.2f},{fee:.2f}\n"


def move(i):
    return ((i * 37) % 23 - 11) * 0.75   # a fixed spread of wins and losses


def a_trades():
    out = []
    for i in range(60):
        o = T0 + dt.timedelta(days=i // 10, minutes=30 * (i % 10))
        if i == 59:
            o = out[58][0] + dt.timedelta(minutes=1)
        sym = "ES" if i % 2 == 0 else "NQ"
        if i == 59:
            sym = out[58][2]
        d = "Long" if i % 4 < 2 else "Short"
        if i == 59:
            d = out[58][3]
        p0 = 5000.0 + i
        out.append((o, o + dt.timedelta(minutes=12), sym, d, 2, p0, p0 + move(i), 1.0))
    return out


def write(name, rows):
    with open(os.path.join(HERE, name), "w", encoding="utf-8", newline="") as fh:
        fh.write(HEAD + "".join(row(*r) for r in rows))


def main():
    a = a_trades()
    write("acct_a.csv", a)
    b = []
    for i in range(35):
        lag = dt.timedelta(minutes=3 * (i // 5) if i < 30 else 16)
        o, c, sym, d, q, p0, p1, fee = a[i]
        b.append((o + lag, c + lag, sym, d, 1, p0, p1, 0.5))
    for j in range(10):
        o = T0 + dt.timedelta(days=j, hours=6)
        b.append((o, o + dt.timedelta(minutes=20), "CL", "Long", 1, 70.0, 70.0 + move(j + 5) / 10, 0.5))
    write("acct_b.csv", b)
    extra = []
    for j in range(20):
        o = T0 + dt.timedelta(days=8 + j // 10, minutes=30 * (j % 10))
        extra.append((o, o + dt.timedelta(minutes=9), "ES", "Long", 2, 5100.0 + j, 5100.0 + j + move(j + 3), 1.0))
    write("acct_a_overlap.csv", a[40:] + extra)
    c = []
    for j in range(25):
        o = T0 + dt.timedelta(days=j % 10, hours=7, minutes=2 * j)
        c.append((o, o + dt.timedelta(minutes=15), "GC", "Short", 1, 2400.0, 2400.0 + move(j + 7), 0.8))
    write("acct_c.csv", c)


if __name__ == "__main__":
    main()
