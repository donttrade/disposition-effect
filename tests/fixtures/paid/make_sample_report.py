#!/usr/bin/env python3
"""Delivery plan C-12 final (Tester T-3 T3-E): the /sample-report/ page of the paid build is a real habit report:
the server engine's output on a committed synthetic trade file, rendered by the real report.js.

    python3 tests/fixtures/paid/make_sample_report.py            # writes tests/fixtures/paid/sample-report.csv
    DT_PRIVATE_REPO=../dt-private python3 tests/fixtures/paid/make_sample_report.py --report
        # also writes site/config/sample-report.report.json: the CSV parsed and stripped by the reference engine
        # (salt "SAMPLE", symbols in sorted order), then analysed by dt-private's src/core/habits.mjs

The file is made up (fixed seed): one trader, two symbols, 60 weekdays, trades one after another from 09:30.
A trade opened within 15 minutes of a losing trade's close is built to do worse (a planted re-entry habit),
so the sample shows a tested habit. tests/test_sample_report_page.py checks the page against the engine."""
import datetime as dt
import json
import os
import random
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(os.path.dirname(HERE)))
CSV = os.path.join(HERE, "sample-report.csv")
REPORT = os.path.join(REPO, "site", "config", "sample-report.report.json")
SALT = "SAMPLE"


def make_csv():
    R = random.Random(20261023)
    lines = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    day = dt.date(2026, 6, 1)
    days = 0
    last_loss = False
    while days < 60:
        if day.weekday() < 5:
            days += 1
            t = dt.datetime.combine(day, dt.time(9, 30)) + dt.timedelta(minutes=R.randint(0, 20))
            for _ in range(R.randint(4, 7)):
                if t.hour >= 15:
                    break
                sym = R.choice(["EX-A", "EX-B"])
                long = R.random() < 0.55
                qty = R.choice([1, 1, 2, 2, 3])
                hold = dt.timedelta(minutes=R.randint(4, 75), seconds=R.randint(0, 59))
                revenge = last_loss and (t - last_close) <= dt.timedelta(minutes=15)
                win = R.random() < (0.25 if revenge else 0.55)
                move = round(R.uniform(1.0, 4.0) if win else -R.uniform(1.0, 3.5) * (2.5 if revenge else 1.0), 2)
                entry = round(R.uniform(80, 120), 2)
                exit_ = round(entry + (move if long else -move), 2)
                o, c = t, t + hold
                lines.append(f"{o.date()},{o.time()},{sym},{'Buy' if long else 'Sell'},{qty},{entry:.2f},USD,0.50")
                lines.append(f"{c.date()},{c.time()},{sym},{'Sell' if long else 'Buy'},{qty},{exit_:.2f},USD,0.50")
                last_loss, last_close = (move * qty - 1.0) < 0, c
                gap = R.randint(2, 10) if R.random() < 0.5 else R.randint(20, 55)
                t = c + dt.timedelta(minutes=gap, seconds=R.randint(0, 59))
        day += dt.timedelta(days=1)
    with open(CSV, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    return CSV


def stripped_rows():
    sys.path.insert(0, os.path.join(REPO, "tests", "reference"))
    import engine_ref as E
    res = E.run_fixture(open(CSV, "rb").read())
    assert "result" in res, res
    return E.strip_rows(res["result"]["trades"], SALT)["rows"]


def engine_report(private, rows):
    js = ("import { analyse } from './src/core/habits.mjs'; let s=''; process.stdin.on('data', (d) => { s += d; });"
          "process.stdin.on('end', () => { process.stdout.write(JSON.stringify(analyse({ rows: JSON.parse(s), currency: 'USD',"
          " pgr_plr: null }, 'sample'))); });")
    r = subprocess.run(["node", "--input-type=module", "-e", js], cwd=private, input=json.dumps(rows), capture_output=True,
                       text=True, check=True)
    return json.loads(r.stdout)


if __name__ == "__main__":
    make_csv()
    if "--report" in sys.argv:
        private = os.environ.get("DT_PRIVATE_REPO") or os.path.join(os.path.dirname(REPO), "dt-private")
        rep = engine_report(private, stripped_rows())
        with open(REPORT, "w", encoding="utf-8", newline="\n") as f:
            json.dump(rep, f, indent=1, sort_keys=True, ensure_ascii=False)
            f.write("\n")
        print("wrote", REPORT, rep["method_version"], rep["n_trades"], "trades; tested", rep["n_tested"], "focus", rep["focus"])
