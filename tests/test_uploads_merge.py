"""S3 (ARCHITECT-EVIDENCE-SCALE-AND-POWER §7 S3; TESTER-REPORT-S3 B1-B4, M1, M3, M4, M6, m1-m3, m9, m10): /report/ reads
several files of one platform as one history.

Unit (node and Chromium, merge.js): every file is read on its own, so two accounts never share a position book (B2);
files that share rows are one account, read together, overlap counted once; an MT5 positions report and a deals
report are read without losing either (B3); the copy collapse across accounts (15:00 merges, 15:01 does not, one
account never, date-only trades never); currencies refused when they differ (M1); the server's trade count (B4);
the 20,000-row cap after the merge.
Page (Chromium, the Worker is a Playwright route, everything off the page's origin aborted): choosing files only
stages them, and only Run sends (B1), at any count; the small-file notice below 100 trades as the server counts
them, not at 100; the screen-reader line (M6); picks while busy (m1); an outage keeps the files (m2); removing one
file re-counts (m9); the page-1 copy line; the network log; no test build carries the live Worker URL.
Fixtures: tests/fixtures/paid/copy (make_copy_fixtures.py), and files written by the tests."""
import functools
import glob
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import lint_text  # noqa: E402
from test_legal import prices_with_test_link, private_with, with_api  # noqa: E402

COPY = os.path.join(HERE, "fixtures", "paid", "copy")
A, B, A2, C = (os.path.join(COPY, n) for n in ("acct_a.csv", "acct_b.csv", "acct_a_overlap.csv", "acct_c.csv"))
OTHER_PLATFORM = os.path.join(HERE, "fixtures", "generic", "basic.csv")
MT5 = os.path.join(HERE, "fixtures", "mt5")
API = "http://127.0.0.1:9"  # never reached: every call is routed
BODY_KEYS = {"v", "token", "rows", "currency", "pgr_plr", "firm_name", "firm_consent"}

NOTICE = "Files this size mostly show No sign for habits. You still get every dollar total and your rule check."
WAIT = "Nothing is sent until you press Run. Adding files does not use a run."
HINT = "Add all your accounts and months: more trades, clearer answers."
LINE_30 = "30 trades in one file matched a trade in another file within 15 minutes and were counted once."
NEAR_5 = "5 more trades match a trade in another file 15 to 60 minutes apart; they are counted as separate trades."
LINE_1 = "1 trade in one file matched a trade in another file within 15 minutes and was counted once."
MIXED_UNITS = ("These files report results in different currencies or units, so they cannot be added up. "
               "Add the files of one currency at a time.")
HEDGES = ("may", "might", "maybe", "unclear", "could be", "possibly")
FILL_HEAD = "Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"
RT_HEAD = "Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees"


def node(js):
    r = subprocess.run(["node", "--input-type=module", "-e", js], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


READ = ("import { readAll, collapseCopies, copyLine, serverTradeCount } from './site/static/js/paid/merge.js';"
        "import { stripRows } from './site/static/js/paid/strip.js';"
        "import fs from 'node:fs';"
        "const F = (p) => new Uint8Array(fs.readFileSync(p));"
        "const T = (s) => new TextEncoder().encode(s);"
        "const out = (x) => process.stdout.write(JSON.stringify(x));"
        "const shape = (r) => r.error ? {error: r.error.code, message: r.error.message, file: r.file} : {n: r.trades.length, "
        "copies: r.copies, near: r.near, overlap: r.overlap, groups: r.groups, notes: r.notes, question: r.question, "
        "facts: Math.round(r.factsTrades.reduce((a, t) => a + t.pnl, 0) * 100) / 100, nfacts: r.factsTrades.length, "
        "accounts: r.accounts.map((a) => [a.name, a.trades.length]), "
        "ftrades: r.factsTrades.map((t) => [t.symbol, t.dir, t.open_ts, t.close_ts, t.qty, Math.round(t.pnl * 100) / 100]), "
        "trades: r.trades.map((t) => [t.symbol, t.dir, t.open_ts, t.close_ts, t.qty, Math.round(t.pnl * 100) / 100])};")


def read(paths, one=None):
    return node(READ + f"out(shape(readAll({json.dumps(paths)}.map(F), {json.dumps([os.path.basename(x) for x in paths])}, "
                f"{{ oneAccount: {json.dumps(one)} }})));")


def read_text(texts, names=None, one=None):
    return node(READ + f"out(shape(readAll({json.dumps(texts)}.map(T), {json.dumps(names or [])}, {{ oneAccount: {json.dumps(one)} }})));")


# ---------------------------------------------------------------- unit: merge.js


def test_fixtures_are_what_the_generator_writes(tmp_path):
    import shutil
    for n in os.listdir(COPY):
        shutil.copy(os.path.join(COPY, n), tmp_path / n)
    subprocess.run([sys.executable, str(tmp_path / "make_copy_fixtures.py")], check=True)
    for n in ("acct_a.csv", "acct_b.csv", "acct_a_overlap.csv", "acct_c.csv"):
        assert (tmp_path / n).read_text() == open(os.path.join(COPY, n)).read(), n


def test_collapse_on_two_files():
    one = read([A])
    r = read([A, B])
    assert (one["n"], one["copies"]) == (60, 0)
    # 60 + 45 trades: the 30 copies at a lag of 0 to 15 minutes are counted once; the 5 at 16 minutes (near-copies,
    # counted) and the 10 CL are not
    assert (r["n"], r["copies"], r["near"], r["groups"]) == (75, 30, 5, 2)
    b = {(t[0], t[1], t[2]): t for t in read([B])["trades"]}
    got = {(t[0], t[1], t[2]): t for t in r["trades"]}
    a_sorted = sorted(one["trades"], key=lambda t: t[2])
    for i, lead in enumerate(a_sorted[:35]):
        k = (lead[0], lead[1], lead[2])
        lag = (3 * (i // 5) if i < 30 else 16) * 60000
        copy = b[(lead[0], lead[1], lead[2] + lag)]
        if i < 30:   # one trade: the leader's times, quantity and P&L summed
            assert got[k][4] == lead[4] + copy[4] and abs(got[k][5] - (lead[5] + copy[5])) < 0.011, i
            assert (got[k][2], got[k][3]) == (lead[2], lead[3])
            if lag:
                assert (copy[0], copy[1], copy[2]) not in got, i
        else:        # 16 minutes: both stay, unchanged
            assert got[k] == lead and got[(copy[0], copy[1], copy[2])] == copy, i
    # trades 58 and 59 of acct_a: same symbol and direction, 1 minute apart, in the same file: never collapsed
    p58, p59 = a_sorted[58], a_sorted[59]
    assert p59[2] - p58[2] == 60000 and got[(p58[0], p58[1], p58[2])] == p58 and got[(p59[0], p59[1], p59[2])] == p59
    assert [t[3] for t in r["trades"]] == sorted(t[3] for t in r["trades"])


def test_collapse_rule_edges():
    """Synthetic trades: the 15-minute window on both ends (inclusive: 15:00 merges, 15:01 does not), one account, three accounts, symbol and
    direction, and date-only trades (Tester M3: they never collapse)."""
    js = READ + """
    const M = 60000, D = 86400000, TR = (sym, dir, o, c, qty, pnl, file) => ({ symbol: sym, dir, open_ts: o, close_ts: c,
      hold_s: (c - o) / 1000, qty, pnl, pnl_gross: pnl, fees: 0, fills_n: 2, _f: file });
    const of = (t) => new Set(t._f);
    const run = (ts) => { const r = collapseCopies(ts, of); return [r.collapsed, r.trades.length, r.trades.map((t) => [t.qty, t.pnl])]; };
    const t0 = 20000 * D + 9 * 3600000;
    out({
      at15: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + 15 * M, t0 + 25 * M, 2, 7, [1])]),
      open1501: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + 15 * M + 1000, t0 + 25 * M, 2, 7, [1])]),
      close1501: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0, t0 + 25 * M + 1000, 2, 7, [1])]),
      at5: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + 5 * M, t0 + 15 * M, 2, 7, [1])]),
      same_file: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0, t0 + 10 * M, 2, 7, [0])]),
      three: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + M, t0 + 11 * M, 2, 7, [1]), TR('X', 'long', t0 + 2 * M, t0 + 12 * M, 3, 11, [2])]),
      two_in_b: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + 3 * M, t0 + 13 * M, 2, 7, [1]), TR('X', 'long', t0 + M, t0 + 11 * M, 3, 11, [1])]),
      symbol: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('Y', 'long', t0, t0 + 10 * M, 2, 7, [1])]),
      dir: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'short', t0, t0 + 10 * M, 2, 7, [1])]),
      date_only: run([TR('X', 'long', 20000 * D, 20002 * D, 1, 5, [0]), TR('X', 'long', 20000 * D, 20002 * D, 2, 7, [1])]),
      lines: [copyLine(1), copyLine(30), copyLine(100000)],
      near: (await import('./site/static/js/paid/merge.js')).nearLine(5),
    });"""
    r = node(js)
    assert r["at15"] == [1, 1, [[3, 12]]] and r["at5"] == [1, 1, [[3, 12]]]
    assert r["open1501"][:2] == [0, 2] and r["close1501"][:2] == [0, 2]
    assert r["same_file"][:2] == [0, 2]
    assert r["three"] == [2, 1, [[6, 23]]]
    assert r["two_in_b"] == [1, 2, [[4, 16], [2, 7]]]   # one per other account, nearest first
    assert r["symbol"][:2] == [0, 2] and r["dir"][:2] == [0, 2]
    assert r["date_only"][:2] == [0, 2]
    assert r["lines"] == [LINE_1, LINE_30, LINE_30.replace("30 trades", "100,000 trades")] and r["near"] == NEAR_5


def test_date_only_files_never_collapse():
    """Tester M3: two date-only files (dates, no times) with the same symbol and direction on the same days."""
    a = "\n".join([RT_HEAD, "2026-09-01,2026-09-03,AAPL,Long,10,100,101,0", "2026-09-04,2026-09-08,AAPL,Long,10,100,99,0"]) + "\n"
    b = "\n".join([RT_HEAD, "2026-09-01,2026-09-03,AAPL,Long,5,100,101,0", "2026-09-04,2026-09-08,AAPL,Long,5,100,99,0"]) + "\n"
    r = read_text([a, b])
    assert (r["n"], r["copies"]) == (4, 0), r


def test_two_accounts_trading_one_symbol_stay_two_books():
    """Tester B2: account A long ES 09:00-09:20 (+10), account B short ES 09:05-09:15 (+2), fill template. One pooled
    book made up two long trades; read per account, each keeps its own trade."""
    a = "\n".join([FILL_HEAD, "2026-09-01,09:00:00,ES,Buy,1,100,USD,0", "2026-09-01,09:20:00,ES,Sell,1,110,USD,0"]) + "\n"
    b = "\n".join([FILL_HEAD, "2026-09-01,09:05:00,ES,Sell,1,105,USD,0", "2026-09-01,09:15:00,ES,Buy,1,103,USD,0"]) + "\n"
    one_a, one_b, both = read_text([a]), read_text([b]), read_text([a, b])
    assert one_a["trades"] == [["ES", "long", 1788253200000, 1788254400000, 1, 10]]
    assert one_b["trades"] == [["ES", "short", 1788253500000, 1788254100000, 1, 2]]
    assert (both["n"], both["copies"], both["groups"]) == (2, 0, 2)
    assert sorted(map(tuple, both["trades"])) == sorted(map(tuple, one_a["trades"] + one_b["trades"]))
    # copies on a fill format: B copies A's long 2 minutes later at half size; read per account, the rule sees both
    c = "\n".join([FILL_HEAD, "2026-09-01,09:02:00,ES,Buy,0.5,100,USD,0", "2026-09-01,09:22:00,ES,Sell,0.5,110,USD,0"]) + "\n"
    cp = read_text([a, c])
    assert (cp["n"], cp["copies"]) == (1, 1) and cp["trades"][0][4:] == [1.5, 15]


def test_overlap_rows_counted_once():
    r = read([A, A2])
    # no account column, no ID: the dates overlap and the overlapping rows match, so "one account" by default
    assert (r["n"], r["copies"], r["overlap"], r["groups"]) == (80, 0, 20, 1)
    assert r["question"] == {"default": True, "answer": True}
    # mixed, no IDs: two exports of A (one account, one book) plus B (dates overlap, rows differ: another account)
    r3 = read([A, A2, B])
    assert (r3["n"], r3["copies"], r3["groups"], r3["overlap"]) == (95, 30, 2, 20)
    assert r3["accounts"] == [["acct_a.csv + acct_a_overlap.csv", 80], ["acct_b.csv", 45]]
    # the same file twice: every row overlaps
    r2 = read([A, A])
    assert (r2["n"], r2["copies"], r2["overlap"], r2["groups"]) == (60, 0, 60, 1)


def test_two_platforms_and_two_currencies_refused():
    r = read([A, OTHER_PLATFORM])
    assert r["error"] == "E_MIXED_FILES" and r["message"].startswith("These files have different columns.") and r["file"] == 1
    usd = "\n".join([FILL_HEAD, "2026-09-01,09:00:00,ES,Buy,1,100,USD,0", "2026-09-01,09:20:00,ES,Sell,1,110,USD,0"]) + "\n"
    eur = "\n".join([FILL_HEAD, "2026-09-02,09:00:00,DAX,Buy,1,100,EUR,0", "2026-09-02,09:20:00,DAX,Sell,1,110,EUR,0"]) + "\n"
    m = read_text([usd, eur])
    assert m["error"] == "E_MIXED_UNITS" and m["message"] == MIXED_UNITS


def test_server_trade_count_follows_the_servers_merge():
    """Tester B4: rows with the same symbol index, direction and open minute are one trade on the server
    (dt-private habits.mjs mergeRows); date-only rows count one by one; a dates-only file is not merged."""
    js = READ + """
    const r = (o, h, d = 1, s = 0) => ({ o, h, d, s, q: 1, p: 1, f: 'x' });
    const partial = []; for (let i = 0; i < 80; i++) { partial.push(r(60 + 30 * i, 600)); if (i < 40) partial.push(r(60 + 30 * i, 900)); }
    const dates = []; for (let i = 0; i < 10; i++) { dates.push(r(1440 * i, 86400)); dates.push(r(1440 * i, 86400)); }
    out([partial.length, serverTradeCount(partial), serverTradeCount([r(60, 600, 1, 0), r(60, 600, -1, 0), r(60, 600, 1, 1), r(61, 600)]),
      serverTradeCount(dates), serverTradeCount([])]);"""
    assert node(js) == [120, 80, 4, 20, 0]


def test_row_cap_after_the_merge():
    js = READ + """
    const head = 'Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees\\n';
    const p = (n) => String(n).padStart(2, '0');
    const file = (sym, n) => { let s = head; for (let i = 0; i < n; i++) {
      const d = new Date(Date.UTC(2020, 0, 1) + i * 3600000);
      const f = (x) => `${x.getUTCFullYear()}-${p(x.getUTCMonth() + 1)}-${p(x.getUTCDate())} ${p(x.getUTCHours())}:${p(x.getUTCMinutes())}:00`;
      s += `${f(d)},${f(new Date(d.getTime() + 600000))},${sym},Long,1,100,${100 + (i % 7) - 3},0\\n`; }
      return new TextEncoder().encode(s); };
    const r = readAll([file('AAA', 12000), file('BBB', 12000)]);
    const s = await stripRows(r.trades, 'salt');
    out([r.trades.length, r.copies, s.rows.length, s.limited]);"""
    assert node(js) == [24000, 0, 20000, True]


def test_mt5_reports_in_the_browser(browser, repo_server):
    """Tester B2/B3 on MT5 HTML (the engine needs DOMParser): deals reports of two accounts keep both books (1 + 5
    trades; one pooled book gave 5); of one account, one book. A positions report and a deals report are never mixed, in either order, and the line names both files:
    one account's two reports read the same position differently (summed as copies, its P&L doubled)."""
    page = browser.new_page()
    page.goto(repo_server + "/tests/harness.html")
    names = ["positions_hedging.htm", "deals_netting_40.htm", "deals_hedging.htm", "deals_netting.htm"]
    files = {n: list(open(os.path.join(MT5, n), "rb").read()) for n in names}
    # the fixtures share one account line; a second account is the same report with another account number
    other = open(os.path.join(MT5, "deals_netting.htm"), encoding="utf-8").read()
    assert other.count("99887766") == 2   # the title and the "Account:" line
    files["deals_netting_other.htm"] = list(other.replace("99887766", "11223344").encode())
    got = page.evaluate("""async (files) => {
        const m = await import('/site/static/js/paid/merge.js');
        const b = (n) => new Uint8Array(files[n]);
        const n = (xs) => { const r = m.readAll(xs.map(b), xs); return r.error ? [r.error.code, r.error.message] : [r.trades.length, r.groups,
          Math.round(r.trades.reduce((s, t) => s + t.pnl, 0) * 100) / 100]; };
        return { h: n(['deals_hedging.htm']), nt: n(['deals_netting.htm']), hn: n(['deals_hedging.htm', 'deals_netting_other.htm']),
          same: n(['deals_hedging.htm', 'deals_netting.htm']),
          both: n(['positions_hedging.htm', 'deals_netting_40.htm']), rev: n(['deals_netting_40.htm', 'positions_hedging.htm']),
          posdeals: n(['positions_hedging.htm', 'deals_hedging.htm']) };
    }""", files)
    page.close()
    # two accounts (their "Account:" lines differ): two books, 1 + 5 trades
    assert got["hn"][:2] == [got["h"][0] + got["nt"][0], 2] and abs(got["hn"][2] - got["h"][2] - got["nt"][2]) < 0.011, got
    # one account (the same "Account:" line): one book, as the engine reads several files of one account
    assert got["same"][1] == 1, got
    line = ("positions_hedging.htm is an MT5 positions report and {d} is an MT5 deals report. "
            "Add reports of one kind: all positions reports, or all deals reports.")
    assert got["both"] == ["E_MIXED_FILES", line.format(d="deals_netting_40.htm")]
    assert got["rev"] == ["E_MIXED_FILES", line.format(d="deals_netting_40.htm")]
    assert got["posdeals"] == ["E_MIXED_FILES", line.format(d="deals_hedging.htm")]


def test_tradovate_group_trading_keeps_each_accounts_book():
    """Tester re-test R2: APEX-1 and APEX-2 share one group-traded entry fill at 09:00 (same second, price and size);
    B is then traded on its own. One shared fill once joined the two files into one position book (3 trades, B's
    short gone). Each file's own fills make its own trades: together they are A's 2 trades and B's 2."""
    h = "Account,B/S,Contract,Product,avgPrice,filledQty,Fill Time,Status"
    f = lambda acct, rows: h + "\n" + "\n".join(acct + "," + r for r in rows) + "\n"   # noqa: E731
    a = f("APEX-1", [" Buy,ESZ6,ES,5000.00,1,09/01/2026 09:00:00,Filled", " Sell,ESZ6,ES,5010.00,1,09/01/2026 09:20:00,Filled",
                     " Buy,ESZ6,ES,5000.00,1,09/01/2026 11:00:00,Filled", " Sell,ESZ6,ES,5004.00,1,09/01/2026 11:30:00,Filled"])
    b = f("APEX-2", [" Buy,ESZ6,ES,5000.00,1,09/01/2026 09:00:00,Filled", " Sell,ESZ6,ES,5003.00,1,09/01/2026 09:10:00,Filled",
                     " Sell,ESZ6,ES,5005.00,1,09/01/2026 11:05:00,Filled", " Buy,ESZ6,ES,5003.00,1,09/01/2026 11:15:00,Filled"])
    one_a, one_b, both = read_text([a]), read_text([b]), read_text([a, b])
    assert [(t[1], t[5]) for t in one_a["trades"]] == [("long", 500), ("long", 200)]
    assert [(t[1], t[5]) for t in one_b["trades"]] == [("long", 150), ("short", 100)]
    # two books: every account's own trades, as each file alone gives them (B's short kept, nothing made up)
    assert (both["groups"], both["overlap"], both["nfacts"], both["facts"]) == (2, 0, 4, 950)
    assert sorted(map(tuple, both["ftrades"])) == sorted(map(tuple, one_a["trades"] + one_b["trades"]))
    # for the habit checks, the two 09:00 longs (open 0, close 10 minutes apart: within 15) are one trade
    assert (both["n"], both["copies"]) == (3, 1)
    # the generic fill template, one shared fill: the same, and the dollar total is the two files' own totals
    g1 = "\n".join([FILL_HEAD, "2026-09-01,09:00:00,ES,Buy,1,100,USD,0", "2026-09-01,09:20:00,ES,Sell,1,110,USD,0",
                    "2026-09-01,11:00:00,ES,Buy,1,100,USD,0", "2026-09-01,11:30:00,ES,Sell,1,105,USD,0"]) + "\n"
    g2 = "\n".join([FILL_HEAD, "2026-09-01,09:00:00,ES,Buy,1,100,USD,0", "2026-09-01,09:10:00,ES,Sell,1,103,USD,0",
                    "2026-09-01,11:05:00,ES,Sell,1,105,USD,0", "2026-09-01,11:15:00,ES,Buy,1,104,USD,0"]) + "\n"
    gg = read_text([g1, g2])
    assert (gg["groups"], gg["nfacts"], gg["facts"], gg["n"], gg["copies"]) == (2, 4, 19, 3, 1)


def test_months_with_no_overlap_ask_and_one_account_joins_the_edge():
    """Two monthly exports with no account column, no ID and no overlap: nothing tells, so the buyer is asked, with
    "separate accounts" preset (no evidence). Separate: the position open across the month edge is left out, and
    said. One account: one book, and that position is a trade."""
    sep = "\n".join([FILL_HEAD, "2026-09-29,10:00:00,ES,Buy,1,100,USD,0", "2026-09-29,10:20:00,ES,Sell,1,104,USD,0",
                     "2026-09-30,15:00:00,ES,Buy,1,100,USD,0"]) + "\n"
    oct_ = "\n".join([FILL_HEAD, "2026-10-01,09:00:00,ES,Sell,1,103,USD,0", "2026-10-02,10:00:00,ES,Buy,1,100,USD,0",
                      "2026-10-02,10:20:00,ES,Sell,1,101,USD,0"]) + "\n"
    r = read_text([sep, oct_], ["sep.csv", "oct.csv"])
    assert r["question"] == {"default": False, "answer": False}
    assert (r["n"], r["groups"]) == (2, 2) and "2 positions were open at the start or end of an account’s files and were left out." in r["notes"]
    one = read_text([sep, oct_], ["sep.csv", "oct.csv"], one=True)
    assert (one["n"], one["groups"], one["facts"]) == (3, 1, 8) and one["question"] == {"default": False, "answer": True}
    assert one["accounts"] == [["sep.csv + oct.csv", 3]]


TV_HEAD = "Account,B/S,Contract,Product,avgPrice,filledQty,Fill Time,Status"


def tv(acct, rows):
    return TV_HEAD + "\n" + "\n".join(acct + "," + r for r in rows) + "\n"


SEP = [" Buy,ESZ6,ES,5000.00,1,09/14/2026 10:00:00,Filled", " Sell,ESZ6,ES,5005.00,1,09/16/2026 10:00:00,Filled",
       " Buy,ESZ6,ES,5000.00,1,09/20/2026 10:00:00,Filled", " Sell,ESZ6,ES,5002.00,1,09/20/2026 10:30:00,Filled"]
SEP15_OCT15 = [" Sell,ESZ6,ES,5005.00,1,09/16/2026 10:00:00,Filled", " Buy,ESZ6,ES,5000.00,1,09/20/2026 10:00:00,Filled",
               " Sell,ESZ6,ES,5002.00,1,09/20/2026 10:30:00,Filled", " Buy,ESZ6,ES,5000.00,1,10/05/2026 10:00:00,Filled",
               " Sell,ESZ6,ES,4999.00,1,10/05/2026 10:30:00,Filled"]


def test_overlapping_months_of_one_account_are_one_book():
    """Tester re-test 2 R4 (r5.mjs): APEX-1's Sep export and its 15 Sep-15 Oct export. The Account column says one
    account, so the two files are one book with the shared fills counted once: 3 trades, $300 (read apart: 4 trades,
    two of them made-up shorts, $700). No question is asked."""
    r = read_text([tv("APEX-1", SEP), tv("APEX-1", SEP15_OCT15)], ["sep.csv", "sep15-oct15.csv"])
    assert (r["n"], r["groups"], r["overlap"], r["facts"], r["question"]) == (3, 1, 3, 300, None)
    assert [t[1] for t in r["trades"]] == ["long", "long", "long"]


def test_exact_copy_keeps_both_accounts_dollars():
    """Tester re-test 2 R5 (r3.mjs): APEX-1 and APEX-2 with the same group-traded trade. The dollar facts add both
    accounts ($1,000); the habit checks see one trade (copies 1)."""
    same = [" Buy,ESZ6,ES,5000.00,1,09/01/2026 09:00:00,Filled", " Sell,ESZ6,ES,5010.00,1,09/01/2026 09:20:00,Filled"]
    r = read_text([tv("APEX-1", same), tv("APEX-2", same)], ["apex1.csv", "apex2.csv"])
    assert (r["n"], r["copies"], r["groups"], r["overlap"], r["nfacts"], r["facts"]) == (1, 1, 2, 0, 2, 1000)
    assert r["trades"][0][5] == 1000 and r["question"] is None


def test_mixed_two_months_of_a_and_one_file_of_b():
    """Two exports of APEX-1 (one account, one book: $300) plus APEX-2 trading on its own: two accounts, each its own
    book; nothing of B is pooled with A."""
    b = [" Buy,ESZ6,ES,5000.00,1,09/16/2026 09:00:00,Filled", " Sell,ESZ6,ES,5003.00,1,09/16/2026 09:30:00,Filled",
         " Sell,ESZ6,ES,5004.00,1,09/22/2026 11:00:00,Filled", " Buy,ESZ6,ES,5001.00,1,09/22/2026 11:20:00,Filled"]
    alone = read_text([tv("APEX-2", b)])
    r = read_text([tv("APEX-1", SEP), tv("APEX-2", b), tv("APEX-1", SEP15_OCT15)], ["sep.csv", "b.csv", "sep15-oct15.csv"])
    assert (r["groups"], r["overlap"], r["question"]) == (2, 3, None)
    assert r["accounts"] == [["sep.csv + sep15-oct15.csv", 3], ["b.csv", 2]]
    assert r["facts"] == 300 + alone["facts"] and alone["facts"] == 300
    assert sorted(t[1] for t in r["trades"]) == ["long", "long", "long", "long", "short"]


def test_new_strings_pass_lint_and_are_definite():
    js = READ + ("import * as M from './site/static/js/paid/merge.js'; import * as V from './site/static/js/paid/small-facts-view.js';"
                 "out([M.SMALL_NOTICE, M.WAIT_LINE, M.UPLOAD_HINT, M.MIXED_UNITS, M.overlapLine(1), M.overlapLine(20), M.mt5MixLine('a.htm', 'b.htm'),"
                 " M.edgeLine(1), M.edgeLine(3), M.accountsLine(1, 2), M.accountsLine(2, 3), M.filesLabel(1, 2), M.filesLabel(2, 1),"
                 " M.ACCOUNT_QUESTION, M.ACCOUNT_ONE, M.ACCOUNT_SEPARATE, M.nearLine(1), M.nearLine(5), V.SF_TEXT.acct, V.SF_TEXT.one_account, V.SF_LINES.combined(2),"
                 " V.SF_LINES.checked('a.csv')]);")
    got = node(js)
    assert got[:4] == [NOTICE, WAIT, HINT, MIXED_UNITS]
    for t in got + [LINE_1, LINE_30, "Run anyway", "Run the test", "Add more files", "Remove these files", "Your files"]:
        assert lint_text(t) == [] and lint_text(t, "report", paid=True) == [], t
        low = " " + t.lower() + " "
        for h in HEDGES:
            assert f" {h} " not in low and f" {h}." not in low, (t, h)


def test_no_test_build_carries_the_live_worker():
    """Tester S3 network safety: a fixed-string api_base swap keeps the LIVE Worker URL in a test build. Every test
    sets api_base through a regex on the line (test_legal.with_api or re.sub/re.subn), never str.replace."""
    bad = []
    for f in glob.glob(os.path.join(HERE, "*.py")):
        src = open(f, encoding="utf-8").read()
        for m in re.finditer(r"\.replace\(\s*['\"]api_base", src):
            bad.append(f"{os.path.basename(f)}:{src[:m.start()].count(chr(10)) + 1}")
    assert bad == [], bad
    live = re.search(r'(?m)^api_base = "([^"]*)"', open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()).group(1)
    assert with_api(f'x = 1\napi_base = "{live}"\n', API) == f'x = 1\napi_base = "{API}"\n'


# ---------------------------------------------------------------- the page


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("s3")
    toml = with_api(open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read(), API)   # never the live API
    for a, b in (("paid_report = false", "paid_report = true"), ("trader_first_home = false", "trader_first_home = true"),
                 ('mode = "live"', 'mode = "test"')):
        toml = toml.replace(a, b)
    (tmp / "site.toml").write_text(toml, encoding="utf-8")
    out = tmp / "site"
    env = {**os.environ, "DT_SITE_TOML": str(tmp / "site.toml"), "DT_OUT": str(out), "DT_PRIVATE_TOML": private_with(tmp),
           "DT_PRICES_JSON": prices_with_test_link(tmp), "DT_ALLOW_LOCAL_API": "1"}
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    html = (out / "report" / "index.html").read_text(encoding="utf-8")
    assert "workers.dev" not in html and f'<meta name="dt-api" content="{API}">' in html
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"origin": f"http://127.0.0.1:{port}", "out": out, "tmp": tmp}
    srv.shutdown()


def fake_token():
    import base64
    payload = {"v": 1, "sku": "report39", "pk": "a" * 32, "salt": "b" * 32, "iat": 1, "exp": 4102444800}
    return base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=") + ".c2ln"


def report_page(browser, site, width=1280, analyse_status=200):
    rep = json.load(open(os.path.join(HERE, "fixtures", "paid-reports", "random.report.json"), encoding="utf-8"))
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    log = {"posts": [], "requests": [], "errors": [], "aborted": [], "status": [analyse_status]}
    page.on("pageerror", lambda e: log["errors"].append(str(e)))
    page.on("request", lambda r: log["requests"].append(r))

    def route(rt):
        url = rt.request.url
        if url.startswith(site["origin"]):
            return rt.continue_()
        if url == API + "/analyse":
            log["posts"].append(rt.request)
            st = log["status"][0]
            return rt.fulfill(status=st, content_type="application/json",
                              body=json.dumps({"report": rep, "uses_left": 1}) if st == 200 else "{}")
        log["aborted"].append(url)          # donttrade.ca, the Worker, Stripe, the analytics beacon: never reached
        return rt.abort()
    page.route("**/*", route)
    page.goto(site["origin"] + "/report/#t=" + fake_token())
    page.wait_for_selector("#rp-access:has-text('Access found')")
    return ctx, page, log


def count_line(n, files, accounts):
    return (f"{n} {'trade' if n == 1 else 'trades'}: {accounts} {'account' if accounts == 1 else 'accounts'}, "
            f"{files} {'file' if files == 1 else 'files'}.")


def staged(page, n, files, accounts=None, timeout=30000):
    """Waits for the panel's count line: "{n} trades: {a} account(s), {k} file(s)." (by detected accounts)."""
    pat = "^" + re.escape(count_line(n, files, 1)).replace("1\\ account,", r"\d+\ accounts?,") + "$" if accounts is None \
        else "^" + re.escape(count_line(n, files, accounts)) + "$"
    page.wait_for_function("(p) => { const c = document.getElementById('rp-count'), b = document.getElementById('rp-run');"
                           " return c && new RegExp(p).test(c.textContent) && !b.disabled; }", arg=pat, timeout=timeout)


def visible(page, sel):
    return [b for b in page.query_selector_all(sel) if (b.bounding_box() or {}).get("width", 0) > 0]


def click_run(page):
    visible(page, "#rp-run")[0].click()
    page.wait_for_selector("#focus", timeout=30000)


def generic_file(tmp, n, sym="ES", day0=1, name=None, partial=0):
    """n positions, 20 minutes apart; the first `partial` of them closed in two rows (same open minute)."""
    p = tmp / (name or f"t{n}{sym}{partial}.csv")
    rows = [RT_HEAD]
    for i in range(n):
        h, m = divmod(i * 20, 60)
        d, hh = day0 + h // 8, 9 + h % 8
        o = f"2026-09-{d:02d} {hh:02d}:{m:02d}:00"
        if i < partial:
            rows.append(f"{o},2026-09-{d:02d} {hh:02d}:{m + 5:02d}:00,{sym},Long,1,100,{100 + (i * 7) % 11 - 5},0")
        rows.append(f"{o},2026-09-{d:02d} {hh:02d}:{m + 10:02d}:00,{sym},Long,1,100,{100 + (i * 5) % 9 - 4},0")
    p.write_text("\n".join(rows) + "\n")
    return str(p)


def test_picker_takes_several_files_and_shows_the_hint(browser, site):
    ctx, page, log = report_page(browser, site)
    assert page.get_attribute("#rp-file", "multiple") is not None
    assert page.inner_text("#rp-hint").strip() == HINT
    assert page.inner_text("#pick-h").strip() == "Choose your trade files"
    assert "TradingView Order History" in page.inner_text("label[for=rp-file]")
    page.set_input_files("#rp-file", [A, B])
    staged(page, 75, 2)
    assert page.eval_on_selector_all("#rp-files .rp-name", "ls => ls.map((l) => l.textContent)") == ["acct_a.csv", "acct_b.csv"]
    assert not log["errors"]
    ctx.close()


def test_two_150_trade_files_one_at_a_time_spend_one_run(browser, site):
    """Tester B1: choosing a file never sends, whatever its size; only Run does, once."""
    f1 = generic_file(site["tmp"], 150, "ES", 1, "big_es.csv")
    f2 = generic_file(site["tmp"], 150, "NQ", 1, "big_nq.csv")
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", f1)
    staged(page, 150, 1)
    assert page.is_hidden("#rp-small") and page.inner_text("#rp-run").strip() == "Run the test"
    page.wait_for_timeout(800)
    assert log["posts"] == []
    with page.expect_file_chooser() as fc:
        visible(page, "#rp-add")[0].click()
    assert fc.value.is_multiple()
    fc.value.set_files(f2)
    staged(page, 300, 2)
    page.wait_for_timeout(800)
    assert log["posts"] == []
    assert page.inner_text("#rp-picked").count(WAIT) == 1
    click_run(page)
    page.wait_for_timeout(500)
    assert len(log["posts"]) == 1 and len(json.loads(log["posts"][0].post_data)["rows"]) == 300
    ctx.close()


def test_notice_waits_and_run_anyway_sends_one_post(browser, site):
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [A, B])
    staged(page, 75, 2)
    txt = page.inner_text("#rp-picked")
    assert NOTICE in txt and WAIT in txt and page.inner_text("#rp-run").strip() == "Run anyway"
    # Tester M6: the one live line says the count, the notice and that Run sends; focus is on the panel
    live = page.text_content("#rp-live")
    assert live == f"75 trades: 2 accounts, 2 files. {NOTICE} Press Run to send." and page.get_attribute("#rp-live", "role") == "status"
    assert page.evaluate("document.activeElement.id") == "rp-picked-h"
    page.wait_for_timeout(1500)
    assert log["posts"] == [] and page.is_hidden("#rp-status")          # waiting spends nothing
    page.fill("#rp-firm", "Acme")                                      # read when the run starts
    click_run(page)
    for _ in range(2):                                                 # more presses send nothing more
        if visible(page, "#rp-run"):
            visible(page, "#rp-run")[0].click()
    page.wait_for_timeout(500)
    assert len(log["posts"]) == 1
    body = json.loads(log["posts"][0].post_data)
    assert set(body) == BODY_KEYS and len(body["rows"]) == 75 and body["firm_name"] == "Acme"
    for r in body["rows"]:
        assert set(r) == {"o", "h", "d", "q", "p", "s", "f"}
    post = log["posts"][0].post_data
    for s in ("acct_a", "acct_b", "ES", "NQ", "CL"):
        assert f'"{s}' not in post and s + ".csv" not in post, s
    # the network log: the page's own files, the one POST, and aborted calls that carry nothing from the files
    for r in log["requests"]:
        if r.url.startswith(site["origin"]) or r.url == API + "/analyse":
            continue
        assert r.url in log["aborted"], r.url
        for s in ("acct_a", "acct_b", ".csv", "5000.00", "ES,"):
            assert s not in (r.post_data or "") and s not in r.url, (r.url, s)
    assert [r.method for r in log["requests"] if r.url == API + "/analyse"] == ["POST"]
    assert page.inner_text("#copy-rows").strip() == LINE_30
    assert page.inner_text("#near-rows").strip() == NEAR_5
    assert page.is_hidden("#rp-picked")
    assert lint_text(page.inner_text("#focus"), "report", paid=True) == []
    assert not log["errors"]
    ctx.close()


def test_adding_files_recounts_and_removing_one_recounts(browser, site):
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", A)
    staged(page, 60, 1)
    page.set_input_files("#rp-file", B)
    staged(page, 75, 2)
    page.set_input_files("#rp-file", A)                     # the same file again: no change
    page.wait_for_timeout(500)
    assert page.inner_text("#rp-count").strip() == "75 trades: 2 accounts, 2 files."
    page.set_input_files("#rp-file", C)                     # 60 + 45 − 30 + 25 = 100: no notice, still waits for Run
    staged(page, 100, 3)
    assert page.is_hidden("#rp-small") and page.inner_text("#rp-run").strip() == "Run the test"
    visible(page, "#rp-files .rp-remove")[1].click()       # remove acct_b.csv (Tester m9)
    staged(page, 85, 2)
    assert page.eval_on_selector_all("#rp-files .rp-name", "ls => ls.map((l) => l.textContent)") == ["acct_a.csv", "acct_c.csv"]
    assert page.is_visible("#rp-small") and log["posts"] == []
    click_run(page)
    assert len(log["posts"]) == 1 and len(json.loads(log["posts"][0].post_data)["rows"]) == 85
    assert not log["errors"]
    ctx.close()


def test_two_picks_while_reading_are_both_kept(browser, site):
    """Tester m1: a file chosen while the earlier one is still being read waits its turn."""
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", A)
    page.set_input_files("#rp-file", B)
    staged(page, 75, 2)
    ctx.close()


def test_another_platform_or_currency_is_refused_and_the_list_stays(browser, site):
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [A, B])
    staged(page, 75, 2)
    page.set_input_files("#rp-file", OTHER_PLATFORM)
    page.wait_for_selector("#rp-status.notice-error", timeout=30000)
    assert page.inner_text("#rp-status").startswith("These files have different columns.")
    assert page.inner_text("#rp-count").strip() == "75 trades: 2 accounts, 2 files." and page.is_visible("#rp-small")
    click_run(page)
    assert len(json.loads(log["posts"][0].post_data)["rows"]) == 75
    ctx.close()
    usd = site["tmp"] / "usd.csv"
    usd.write_text("\n".join([FILL_HEAD, "2026-09-01,09:00:00,ES,Buy,1,100,USD,0", "2026-09-01,09:20:00,ES,Sell,1,110,USD,0"]) + "\n")
    eur = site["tmp"] / "eur.csv"
    eur.write_text("\n".join([FILL_HEAD, "2026-09-02,09:00:00,DAX,Buy,1,100,EUR,0", "2026-09-02,09:20:00,DAX,Sell,1,110,EUR,0"]) + "\n")
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [str(usd), str(eur)])
    page.wait_for_selector("#rp-status.notice-error", timeout=30000)
    assert page.inner_text("#rp-status").strip() == MIXED_UNITS and page.is_hidden("#rp-picked") and log["posts"] == []
    ctx.close()


def test_an_outage_keeps_the_files(browser, site):
    """Tester m2: no run was spent, so the staged files stay and Run works again."""
    ctx, page, log = report_page(browser, site, analyse_status=503)
    page.set_input_files("#rp-file", [A, B])
    staged(page, 75, 2)
    visible(page, "#rp-run")[0].click()
    page.wait_for_selector("#rp-status.notice-error", timeout=30000)
    assert page.inner_text("#rp-count").strip() == "75 trades: 2 accounts, 2 files." and page.is_enabled("#rp-run")
    log["status"][0] = 200
    click_run(page)
    assert len(log["posts"]) == 2
    ctx.close()


@pytest.mark.parametrize("n,partial,trades,notice", [(99, 0, 99, True), (100, 0, 100, False), (101, 0, 101, False),
                                                     (80, 40, 80, True), (100, 20, 100, False)])
def test_notice_below_100_trades_as_the_server_counts_them(browser, site, n, partial, trades, notice):
    """Tester B4: 80 positions, 40 closed in two parts, are 120 rows and 80 trades: the notice shows, and the count
    line says 80. 100 positions with 20 partial closes (120 rows) are 100 trades: no notice."""
    f = generic_file(site["tmp"], n, partial=partial)
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", f)
    staged(page, trades, 1)
    assert page.is_visible("#rp-small") == notice
    assert page.inner_text("#rp-run").strip() == ("Run anyway" if notice else "Run the test")
    page.wait_for_timeout(300)
    assert log["posts"] == []
    click_run(page)
    assert len(json.loads(log["posts"][0].post_data)["rows"]) == n + partial
    assert page.query_selector("#copy-rows") is None       # one file: no copy line
    ctx.close()


def test_drop_of_several_files(browser, site):
    ctx, page, log = report_page(browser, site)
    files = [{"name": os.path.basename(p), "text": open(p).read()} for p in (A, B)]
    page.evaluate("""(files) => { const dt = new DataTransfer();
        for (const f of files) dt.items.add(new File([f.text], f.name, { type: 'text/csv' }));
        document.getElementById('rp-drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); }""", files)
    staged(page, 75, 2)
    assert page.eval_on_selector_all("#rp-files li", "ls => ls.length") == 2 and log["posts"] == []
    ctx.close()


def test_overlap_line_before_the_run(browser, site):
    """Rows in two files of one account are counted once, and the panel says so before the run."""
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [A, A2])
    staged(page, 80, 2, 1)
    assert "20 rows were in more than one file of one account and were counted once." in page.inner_text("#rp-notes")
    ctx.close()


def test_phone_width_has_no_overflow(browser, site):
    from a11y import horizontal_overflow
    ctx, page, log = report_page(browser, site, width=390)
    page.set_input_files("#rp-file", [A, B])
    staged(page, 75, 2)
    assert horizontal_overflow(page) == []
    ctx.close()


RULE_A, RULE_B = os.path.join(COPY, "rule_a.csv"), os.path.join(COPY, "rule_b_copy.csv")


def test_rule_check_is_one_account_at_a_time(browser, site):
    """Tester re-test R1: two USD copy accounts (rule_a.csv, rule_b_copy.csv: 30 trades each, 1-minute lag), each losing
    $800 on day 4, each under Earn2Trade Gauntlet Mini 50K's $1,100 daily loss limit. Added together they read as a
    breach (−$1,600). The rule check replays one account (file) at a time, the first by default, never the sum; the
    facts and page 1 say they combine 2 accounts."""
    ctx, page, log = report_page(browser, site, width=390)
    page.set_input_files("#rp-file", [RULE_A, RULE_B])
    staged(page, 30, 2)
    click_run(page)
    assert page.inner_text("#accounts-line").strip() == ("These results combine 2 accounts from 2 files. Dollar totals add every account’s "
                                                         "trades; the habit checks count a trade copied between accounts within 15 minutes once. "
                                                         "The rule check covers one account at a time.")
    assert page.inner_text("#sf-combined").strip() == "Combined across 2 accounts: every account’s trades are added, copies included."
    assert page.inner_text("#sf-one-account").startswith("The rule check covers one account at a time")
    assert page.eval_on_selector_all("#sf-acct option", "os => os.map((o) => o.textContent)") == ["rule_a.csv", "rule_b_copy.csv"]
    assert page.input_value("#sf-acct") == "0"
    page.select_option("#sf-preset", "earn2trade-gauntlet-mini-50k")
    page.wait_for_selector("#sf-out #sf-first")
    first = page.inner_text("#sf-out")
    assert "broke" not in first and "1,600" not in first, first
    assert "reached neither the target nor a loss limit" in first, first
    assert page.inner_text("#sf-acct-checked").strip() == "Account checked: rule_a.csv."
    page.select_option("#sf-acct", "1")
    page.wait_for_timeout(300)
    second = page.inner_text("#sf-out")
    assert page.inner_text("#sf-acct-checked").strip() == "Account checked: rule_b_copy.csv."
    assert "broke" not in second and "1,600" not in second, second
    from a11y import horizontal_overflow
    assert horizontal_overflow(page) == []
    assert not log["errors"]
    ctx.close()


def test_rule_file_alone_has_no_account_choice(browser, site):
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", RULE_A)
    staged(page, 30, 1)
    click_run(page)
    assert page.query_selector("#sf-acct") is None and page.query_selector("#accounts-line") is None
    assert page.query_selector("#sf-combined") is None
    ctx.close()


def test_the_account_question_when_the_files_do_not_say(browser, site):
    """No account column and no ID (the CSV template): acct_a.csv and its overlapping re-export. The panel asks one
    question, preset to "One account" (dates overlap, rows match); tapping "Separate accounts" reads them again as two
    accounts (the shared trades become copies). Nothing is sent until Run, once."""
    ctx, page, log = report_page(browser, site, width=390)
    page.set_input_files("#rp-file", [A, A2])
    staged(page, 80, 2, 1)
    assert page.is_visible("#rp-acct-q") and page.inner_text("#rp-acct-q legend").strip() == "Are these files from one account or separate accounts?"
    assert page.is_checked("#rp-acct-one") and not page.is_checked("#rp-acct-sep")
    assert "Are these files from one account or separate accounts?" in page.text_content("#rp-live")
    page.check("#rp-acct-sep")
    staged(page, 80, 2, 2)
    assert page.is_checked("#rp-acct-sep") and log["posts"] == []
    page.check("#rp-acct-one")
    staged(page, 80, 2, 1)
    from a11y import horizontal_overflow
    assert horizontal_overflow(page) == []
    click_run(page)
    assert len(log["posts"]) == 1
    assert page.inner_text("#accounts-line").strip() == "These results read 2 files as 1 account."
    assert page.query_selector("#sf-acct") is None and page.query_selector("#sf-combined") is None
    ctx.close()


def test_files_with_an_account_column_are_not_asked(browser, site):
    """Tester re-test 2 R4/R6 on the page: two Tradovate exports of APEX-1 read as "1 account, 2 files", no question."""
    f1, f2 = site["tmp"] / "sep.csv", site["tmp"] / "sep15-oct15.csv"
    f1.write_text(tv("APEX-1", SEP))
    f2.write_text(tv("APEX-1", SEP15_OCT15))
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [str(f1), str(f2)])
    staged(page, 3, 2, 1)
    assert page.is_hidden("#rp-acct-q")
    assert "3 rows were in more than one file of one account and were counted once." in page.inner_text("#rp-notes")
    ctx.close()
