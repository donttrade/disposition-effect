#!/usr/bin/env python3
"""The shipped copy of the real public-data trade file, with each ticker replaced by a neutral code.

    python3 -I checks/real_data/make_coded_csv.py           # writes checks/real_data/real-trades.coded.csv
    python3 -I checks/real_data/make_coded_csv.py --check   # recomputes and compares, writes nothing

The plan shows no tickers, and the "Try real public data" button on the four file tools loads this file, whose results
list symbols. So the Symbol column of checks/real_data/raw/real-trades.csv is replaced: each distinct ticker becomes
"Stock 01", "Stock 02", ... in order of first appearance in the file. Every other byte is unchanged, so every figure
the tools compute is the same (make_tool_real.py checks the engine's trades are identical). A change under CC BY 4.0
s.3(a)(1)(B): the credit line says "ticker names replaced with codes". The original file stays the provenance input,
but only in checks/real_data/raw/ (gitignored, made by fetch.py): the repo keeps its SHA-256 and this coded copy.
"""
import csv
import hashlib
import io
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "raw", "real-trades.csv")
OUT = os.path.join(HERE, "real-trades.coded.csv")


def coded(text):
    rows = list(csv.reader(io.StringIO(text, newline="")))
    head, body = rows[0], rows[1:]
    k = head.index("Symbol")
    codes = {}
    for r in body:
        codes.setdefault(r[k], None)
    width = max(2, len(str(len(codes))))
    codes = {s: f"Stock {i + 1:0{width}d}" for i, s in enumerate(codes)}
    # rewrite line by line so every other byte stays as it was (no re-quoting by the csv module)
    lines = text.split("\n")
    out = [lines[0]]
    for line, r in zip(lines[1:], body):
        cells = line.split(",")
        assert cells == r, "a quoted cell: rewrite by hand"
        cells[k] = codes[cells[k]]
        out.append(",".join(cells))
    out += lines[1 + len(body):]
    return "\n".join(out), codes


def main(argv):
    text = open(SRC, encoding="utf-8", newline="").read()
    new, codes = coded(text)
    if "--check" in argv:
        if open(OUT, encoding="utf-8", newline="").read() != new:
            sys.exit("real-trades.coded.csv differs from a fresh run")
        print("real-trades.coded.csv: matches a fresh run")
        return
    with open(OUT, "w", encoding="utf-8", newline="") as f:
        f.write(new)
    print(len(codes), "tickers coded ->", os.path.relpath(OUT), hashlib.sha256(new.encode()).hexdigest())


if __name__ == "__main__":
    main(sys.argv[1:])
