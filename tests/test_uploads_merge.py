"""S3 (ARCHITECT-EVIDENCE-SCALE-AND-POWER §7 S3; TESTER-REPORT-S3 B1-B4, M1, M3, M4, M6, m1-m3, m9, m10): /report/ reads
several files of one platform as one history.

Unit (node and Chromium, merge.js): every file is read on its own, so two accounts never share a position book (B2);
files that share rows are one account, read together, overlap counted once; an MT5 positions report and a deals
report are read without losing either (B3); the copy collapse across accounts (5:00 merges, 5:01 does not, one
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
LINE_30 = "30 trades in one file matched a trade in another file within 5 minutes and were counted once."
LINE_1 = "1 trade in one file matched a trade in another file within 5 minutes and was counted once."
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
        "copies: r.copies, overlap: r.overlap, groups: r.groups, notes: r.notes, "
        "trades: r.trades.map((t) => [t.symbol, t.dir, t.open_ts, t.close_ts, t.qty, Math.round(t.pnl * 100) / 100])};")


def read(paths):
    return node(READ + f"out(shape(readAll({json.dumps(paths)}.map(F))));")


def read_text(texts):
    return node(READ + f"out(shape(readAll({json.dumps(texts)}.map(T))));")


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
    # 60 + 45 trades: the 30 copies at a lag of 0 to 5 minutes are counted once; the 5 at 6 minutes and the 10 CL are not
    assert (r["n"], r["copies"], r["groups"]) == (75, 30, 2)
    b = {(t[0], t[1], t[2]): t for t in read([B])["trades"]}
    got = {(t[0], t[1], t[2]): t for t in r["trades"]}
    a_sorted = sorted(one["trades"], key=lambda t: t[2])
    for i, lead in enumerate(a_sorted[:35]):
        k = (lead[0], lead[1], lead[2])
        lag = (i // 5 if i < 30 else 6) * 60000
        copy = b[(lead[0], lead[1], lead[2] + lag)]
        if i < 30:   # one trade: the leader's times, quantity and P&L summed
            assert got[k][4] == lead[4] + copy[4] and abs(got[k][5] - (lead[5] + copy[5])) < 0.011, i
            assert (got[k][2], got[k][3]) == (lead[2], lead[3])
            if lag:
                assert (copy[0], copy[1], copy[2]) not in got, i
        else:        # 6 minutes: both stay, unchanged
            assert got[k] == lead and got[(copy[0], copy[1], copy[2])] == copy, i
    # trades 58 and 59 of acct_a: same symbol and direction, 1 minute apart, in the same file: never collapsed
    p58, p59 = a_sorted[58], a_sorted[59]
    assert p59[2] - p58[2] == 60000 and got[(p58[0], p58[1], p58[2])] == p58 and got[(p59[0], p59[1], p59[2])] == p59
    assert [t[3] for t in r["trades"]] == sorted(t[3] for t in r["trades"])


def test_collapse_rule_edges():
    """Synthetic trades: the 5-minute window on both ends (inclusive), one account, three accounts, symbol and
    direction, and date-only trades (Tester M3: they never collapse)."""
    js = READ + """
    const M = 60000, D = 86400000, TR = (sym, dir, o, c, qty, pnl, file) => ({ symbol: sym, dir, open_ts: o, close_ts: c,
      hold_s: (c - o) / 1000, qty, pnl, pnl_gross: pnl, fees: 0, fills_n: 2, _f: file });
    const of = (t) => new Set(t._f);
    const run = (ts) => { const r = collapseCopies(ts, of); return [r.collapsed, r.trades.length, r.trades.map((t) => [t.qty, t.pnl])]; };
    const t0 = 20000 * D + 9 * 3600000;
    out({
      at5: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + 5 * M, t0 + 15 * M, 2, 7, [1])]),
      open501: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + 5 * M + 1000, t0 + 15 * M, 2, 7, [1])]),
      close501: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0, t0 + 15 * M + 1000, 2, 7, [1])]),
      same_file: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0, t0 + 10 * M, 2, 7, [0])]),
      three: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + M, t0 + 11 * M, 2, 7, [1]), TR('X', 'long', t0 + 2 * M, t0 + 12 * M, 3, 11, [2])]),
      two_in_b: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'long', t0 + 3 * M, t0 + 13 * M, 2, 7, [1]), TR('X', 'long', t0 + M, t0 + 11 * M, 3, 11, [1])]),
      symbol: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('Y', 'long', t0, t0 + 10 * M, 2, 7, [1])]),
      dir: run([TR('X', 'long', t0, t0 + 10 * M, 1, 5, [0]), TR('X', 'short', t0, t0 + 10 * M, 2, 7, [1])]),
      date_only: run([TR('X', 'long', 20000 * D, 20002 * D, 1, 5, [0]), TR('X', 'long', 20000 * D, 20002 * D, 2, 7, [1])]),
      lines: [copyLine(1), copyLine(30), copyLine(100000)],
    });"""
    r = node(js)
    assert r["at5"] == [1, 1, [[3, 12]]]
    assert r["open501"][:2] == [0, 2] and r["close501"][:2] == [0, 2]
    assert r["same_file"][:2] == [0, 2]
    assert r["three"] == [2, 1, [[6, 23]]]
    assert r["two_in_b"] == [1, 2, [[4, 16], [2, 7]]]   # one per other account, nearest first
    assert r["symbol"][:2] == [0, 2] and r["dir"][:2] == [0, 2]
    assert r["date_only"][:2] == [0, 2]
    assert r["lines"] == [LINE_1, LINE_30, LINE_30.replace("30 trades", "100,000 trades")]


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
    assert (r["n"], r["copies"], r["overlap"], r["groups"]) == (80, 0, 20, 1)
    # the overlapping trades are in both acct_a files (one account), and their acct_b copies still collapse once
    r3 = read([A, A2, B])
    assert (r3["n"], r3["copies"], r3["groups"]) == (95, 30, 2)
    # the same file twice: every row overlaps, nothing collapses
    r2 = read([A, A])
    assert (r2["n"], r2["copies"], r2["overlap"]) == (60, 0, 60)


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
    """Tester B3 and B2 on MT5 HTML (the engine needs DOMParser): a positions report and a deals report of two accounts
    keep every trade of both; two deals reports keep both books. Before: 3 and 5 trades."""
    page = browser.new_page()
    page.goto(repo_server + "/tests/harness.html")
    names = ["positions_hedging.htm", "deals_netting_40.htm", "deals_hedging.htm", "deals_netting.htm"]
    files = {n: list(open(os.path.join(MT5, n), "rb").read()) for n in names}
    got = page.evaluate("""async (files) => {
        const m = await import('/site/static/js/paid/merge.js');
        const b = (n) => new Uint8Array(files[n]);
        const n = (xs) => { const r = m.readAll(xs.map(b), xs); return r.error ? r.error.code + ': ' + r.error.message : [r.trades.length, r.groups,
          Math.round(r.trades.reduce((s, t) => s + t.pnl, 0) * 100) / 100]; };
        return { pos: n(['positions_hedging.htm']), deals40: n(['deals_netting_40.htm']), both: n(['positions_hedging.htm', 'deals_netting_40.htm']),
          rev: n(['deals_netting_40.htm', 'positions_hedging.htm']), h: n(['deals_hedging.htm']), nt: n(['deals_netting.htm']),
          hn: n(['deals_hedging.htm', 'deals_netting.htm']) };
    }""", files)
    page.close()
    assert got["pos"][0] == 3 and got["deals40"][0] == 40
    for k in ("both", "rev"):
        assert isinstance(got[k], list), got[k]
        assert got[k][:2] == [43, 2] and abs(got[k][2] - (got["pos"][2] + got["deals40"][2])) < 0.011, got
    assert got["hn"][:2] == [got["h"][0] + got["nt"][0], 2], got


def deals_with_extra(n_extra):
    """deals_hedging.htm (one account's deals) with n_extra more GBPUSD round trips appended: the same account's
    deals report, holding more trades than that account's positions report (positions_hedging.htm) shows."""
    src = open(os.path.join(MT5, "deals_hedging.htm"), encoding="utf-8").read()
    last = src.index("</tr>", src.index("<td>3004</td>")) + len("</tr>")
    rows = []
    for i in range(n_extra):
        d, h = 2 + i // 4, 9 + 2 * (i % 4)
        for k, (side, io, price, profit) in enumerate((("buy", "in", "1.27000", "0.00"), ("sell", "out", "1.27100", "10.00"))):
            rows.append(f"<tr><td>2026.09.{d:02d} {h + k:02d}:00:00</td><td>{5000 + 2 * i + k}</td><td>GBPUSD</td><td>{side}</td><td>{io}</td>"
                        f"<td>1.00</td><td>{price}</td><td>{6000 + 2 * i + k}</td><td>0.00</td><td>0.00</td><td>0.00</td><td>{profit}</td>"
                        f"<td>5 000.00</td><td></td></tr>")
    return src[:last] + "".join(rows) + src[last:]


def test_a_report_type_that_loses_trades_is_refused_by_name(browser, repo_server):
    """Tester B3, same account: an MT5 positions report and a deals report of ONE account share deals, so they are read
    together; that reading keeps the positions report only. When it gives fewer trades than the deals report alone,
    both files are refused by name, never dropped. With nothing lost, they read as one account."""
    page = browser.new_page()
    page.goto(repo_server + "/tests/harness.html")
    files = {"positions_hedging.htm": list(open(os.path.join(MT5, "positions_hedging.htm"), "rb").read()),
             "deals_more.htm": list(deals_with_extra(4).encode()), "deals_hedging.htm": list(open(os.path.join(MT5, "deals_hedging.htm"), "rb").read())}
    got = page.evaluate("""async (files) => {
        const m = await import('/site/static/js/paid/merge.js');
        const r = (xs) => { const x = m.readAll(xs.map((n) => new Uint8Array(files[n])), xs);
          return x.error ? [x.error.code, x.error.message] : [x.trades.length, x.groups]; };
        return { more: r(['deals_more.htm']), lost: r(['positions_hedging.htm', 'deals_more.htm']),
          same: r(['positions_hedging.htm', 'deals_hedging.htm']) };
    }""", files)
    page.close()
    assert got["more"] == [5, 1]
    assert got["lost"] == ["E_FILES_DISAGREE", "positions_hedging.htm and deals_more.htm share rows, but read together they give "
                           "fewer trades than one of them alone. Export them as the same kind of report and add them again."]
    assert got["same"] == [3, 1]


def test_new_strings_pass_lint_and_are_definite():
    js = READ + "import * as M from './site/static/js/paid/merge.js'; out([M.SMALL_NOTICE, M.WAIT_LINE, M.UPLOAD_HINT, M.MIXED_UNITS, M.overlapLine(1), M.overlapLine(20), M.disagreeLine(['a.csv', 'b.csv'])]);"
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


def staged(page, n, files, timeout=30000):
    page.wait_for_function("([n, k]) => { const c = document.getElementById('rp-count'), b = document.getElementById('rp-run');"
                           " return c && c.textContent === `${n} trades from ${k} ${k === 1 ? 'file' : 'files'}.` && !b.disabled; }",
                           arg=[n, files], timeout=timeout)


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
    assert live == f"75 trades from 2 files. {NOTICE} Press Run to send." and page.get_attribute("#rp-live", "role") == "status"
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
    assert page.inner_text("#rp-count").strip() == "75 trades from 2 files."
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
    assert page.inner_text("#rp-count").strip() == "75 trades from 2 files." and page.is_visible("#rp-small")
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
    assert page.inner_text("#rp-count").strip() == "75 trades from 2 files." and page.is_enabled("#rp-run")
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
    """Tester M4: rows in two files are counted once, and the panel says so before anything is sent."""
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [A, A2])
    staged(page, 80, 2)
    assert "20 rows were in more than one file and were counted once." in page.inner_text("#rp-notes")
    ctx.close()


def test_phone_width_has_no_overflow(browser, site):
    from a11y import horizontal_overflow
    ctx, page, log = report_page(browser, site, width=390)
    page.set_input_files("#rp-file", [A, B])
    staged(page, 75, 2)
    assert horizontal_overflow(page) == []
    ctx.close()
