"""S3 (ARCHITECT-EVIDENCE-SCALE-AND-POWER §7 S3): /report/ reads several files of one platform as one history.

Unit (node, merge.js): the copy collapse on the 2-file fixture (copies within 5 minutes collapse, a 6-minute lag
does not, same-file rows never collapse), the overlap (rows in two files counted once, never collapsed with a copy of
themselves), E_MIXED_FILES, the 20,000-row cap after the merge.
Page (Chromium, the Worker is a Playwright route): the small-file notice below 100 trades and not at 100; "Run
anyway" sends exactly one /analyse POST with the old body keys; adding files re-counts; waiting sends nothing;
the page-1 copy line; nothing but the one POST leaves the page.
Fixtures: tests/fixtures/paid/copy (make_copy_fixtures.py)."""
import functools
import http.server
import json
import os
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
from test_legal import prices_with_test_link, private_with  # noqa: E402

COPY = os.path.join(HERE, "fixtures", "paid", "copy")
A, B, A2, C = (os.path.join(COPY, n) for n in ("acct_a.csv", "acct_b.csv", "acct_a_overlap.csv", "acct_c.csv"))
OTHER_PLATFORM = os.path.join(HERE, "fixtures", "generic", "basic.csv")
API = "http://127.0.0.1:9"  # never reached: every call is routed
BODY_KEYS = {"v", "token", "rows", "currency", "pgr_plr", "firm_name", "firm_consent"}

NOTICE = "Files this size mostly show No sign for habits. You still get every dollar total and your rule check."
WAIT = "Adding files does not use your run."
HINT = "Add all your accounts and months: more trades, clearer answers."
LINE_30 = "30 trades in one file matched a trade in another file within 5 minutes and were counted once."
LINE_1 = "1 trade in one file matched a trade in another file within 5 minutes and was counted once."
HEDGES = ("may", "might", "maybe", "unclear", "could be", "possibly")


def node(js):
    r = subprocess.run(["node", "--input-type=module", "-e", js], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


READ = ("import { readFiles, collapseCopies, originsOf, copyLine } from './site/static/js/paid/merge.js';"
        "import { stripRows } from './site/static/js/paid/strip.js';"
        "import fs from 'node:fs';"
        "const F = (p) => new Uint8Array(fs.readFileSync(p));"
        "const out = (x) => process.stdout.write(JSON.stringify(x));")


def read(paths):
    return node(READ + f"const r = readFiles({json.dumps(paths)}.map(F));"
                "out(r.error ? {error: r.error.code, message: r.error.message} : {merged: r.result.trades.length, "
                "copies: r.copies, warnings: r.result.warnings.map((w) => [w.code, w.n]), "
                "trades: r.trades.map((t) => [t.symbol, t.dir, t.open_ts, t.close_ts, t.qty, Math.round(t.pnl * 100) / 100])});")


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
    assert (one["merged"], one["copies"]) == (60, 0)
    # 60 + 45 rows: the 30 copies at a lag of 0 to 5 minutes are counted once; the 5 at 6 minutes and the 10 CL are not
    assert (r["merged"], r["copies"], len(r["trades"])) == (105, 30, 75)
    a = {(t[0], t[1], t[2]): t for t in one["trades"]}
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
    assert p59[2] - p58[2] == 60000 and got[(p58[0], p58[1], p58[2])] == a[(p58[0], p58[1], p58[2])]
    assert got[(p59[0], p59[1], p59[2])] == p59
    # close-time order is kept
    assert [t[3] for t in r["trades"]] == sorted(t[3] for t in r["trades"])


def test_collapse_rule_edges():
    """Synthetic trades: the 5-minute window on both ends (inclusive), same-file rows, a shared (overlap) trade,
    three accounts, symbol and direction."""
    js = READ + """
    const M = 60000, T = (sym, dir, o, c, qty, pnl, file) => ({ symbol: sym, dir, open_ts: o, close_ts: c, qty, pnl,
      pnl_gross: pnl, fees: 0, fills_n: 2, _f: file });
    const of = (t) => new Set(t._f);
    const run = (ts) => { const r = collapseCopies(ts, of); return [r.collapsed, r.trades.length, r.trades.map((t) => [t.qty, t.pnl])]; };
    out({
      at5: run([T('X', 'long', 0, 10 * M, 1, 5, [0]), T('X', 'long', 5 * M, 15 * M, 2, 7, [1])]),
      open6: run([T('X', 'long', 0, 10 * M, 1, 5, [0]), T('X', 'long', 5 * M + 1, 15 * M, 2, 7, [1])]),
      close6: run([T('X', 'long', 0, 10 * M, 1, 5, [0]), T('X', 'long', 0, 15 * M + 1, 2, 7, [1])]),
      same_file: run([T('X', 'long', 0, 10 * M, 1, 5, [0]), T('X', 'long', 0, 10 * M, 2, 7, [0])]),
      shared: run([T('X', 'long', 0, 10 * M, 1, 5, [0, 1]), T('X', 'long', M, 11 * M, 2, 7, [1])]),
      shared_other: run([T('X', 'long', 0, 10 * M, 1, 5, [0, 1]), T('X', 'long', M, 11 * M, 2, 7, [2])]),
      no_file: run([T('X', 'long', 0, 10 * M, 1, 5, []), T('X', 'long', M, 11 * M, 2, 7, [1])]),
      three: run([T('X', 'long', 0, 10 * M, 1, 5, [0]), T('X', 'long', M, 11 * M, 2, 7, [1]), T('X', 'long', 2 * M, 12 * M, 3, 11, [2])]),
      two_in_b: run([T('X', 'long', 0, 10 * M, 1, 5, [0]), T('X', 'long', 3 * M, 13 * M, 2, 7, [1]), T('X', 'long', M, 11 * M, 3, 11, [1])]),
      symbol: run([T('X', 'long', 0, 10 * M, 1, 5, [0]), T('Y', 'long', 0, 10 * M, 2, 7, [1])]),
      dir: run([T('X', 'long', 0, 10 * M, 1, 5, [0]), T('X', 'short', 0, 10 * M, 2, 7, [1])]),
      lines: [copyLine(1), copyLine(30)],
    });"""
    r = node(js)
    assert r["at5"] == [1, 1, [[3, 12]]]
    assert r["open6"][:2] == [0, 2] and r["close6"][:2] == [0, 2]
    assert r["same_file"][:2] == [0, 2]
    assert r["shared"][:2] == [0, 2]                 # the shared trade is in file 1 too: same file as its "copy"
    assert r["shared_other"] == [1, 1, [[3, 12]]]
    assert r["no_file"][:2] == [0, 2]
    assert r["three"] == [2, 1, [[6, 23]]]
    assert r["two_in_b"] == [1, 2, [[4, 16], [2, 7]]]   # one per other file, nearest first
    assert r["symbol"][:2] == [0, 2] and r["dir"][:2] == [0, 2]
    assert r["lines"] == [LINE_1, LINE_30]


def test_overlap_rows_counted_once():
    r = read([A, A2])
    assert (r["merged"], r["copies"]) == (80, 0) and ["W_OVERLAP_ROWS", 20] in r["warnings"]
    # the overlapping trades are in both acct_a files, and their acct_b copies still collapse once
    r3 = read([A, A2, B])
    assert (r3["merged"], r3["copies"], len(r3["trades"])) == (125, 30, 95)
    # the same file twice: every row overlaps, nothing collapses
    assert (lambda x: (x["merged"], x["copies"]))(read([A, A])) == (60, 0)


def test_two_platforms_refused():
    r = read([A, OTHER_PLATFORM])
    assert r["error"] == "E_MIXED_FILES" and r["message"].startswith("These files have different columns.")


def test_row_cap_after_the_merge():
    js = READ + """
    const head = 'Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees\\n';
    const p = (n) => String(n).padStart(2, '0');
    const file = (sym, n) => { let s = head; for (let i = 0; i < n; i++) {
      const d = new Date(Date.UTC(2020, 0, 1) + i * 3600000);
      const f = (x) => `${x.getUTCFullYear()}-${p(x.getUTCMonth() + 1)}-${p(x.getUTCDate())} ${p(x.getUTCHours())}:${p(x.getUTCMinutes())}:00`;
      s += `${f(d)},${f(new Date(d.getTime() + 600000))},${sym},Long,1,100,${100 + (i % 7) - 3},0\\n`; }
      return new TextEncoder().encode(s); };
    const r = readFiles([file('AAA', 12000), file('BBB', 12000)]);
    const s = await stripRows(r.trades, 'salt');
    out([r.trades.length, r.copies, s.rows.length, s.limited]);"""
    assert node(js) == [24000, 0, 20000, True]


def test_new_strings_pass_lint_and_are_definite():
    js = READ + "import * as M from './site/static/js/paid/merge.js'; out([M.SMALL_NOTICE, M.SMALL_WAIT, M.UPLOAD_HINT]);"
    assert node(js) == [NOTICE, WAIT, HINT]
    for t in (NOTICE, WAIT, HINT, LINE_1, LINE_30, "Run anyway", "Add more files", "Remove these files"):
        assert lint_text(t) == [] and lint_text(t, "report", paid=True) == [], t
        low = " " + t.lower() + " "
        for h in HEDGES:
            assert f" {h} " not in low and f" {h}." not in low, (t, h)


# ---------------------------------------------------------------- the page


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("s3")
    toml = open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()
    import re
    toml, n = re.subn(r'(?m)^api_base = "[^"]*"', f'api_base = "{API}"', toml)   # never the live API
    assert n == 1
    for a, b in (("paid_report = false", "paid_report = true"), ("trader_first_home = false", "trader_first_home = true"),
                 ('mode = "live"', 'mode = "test"')):
        toml = toml.replace(a, b)
    (tmp / "site.toml").write_text(toml, encoding="utf-8")
    out = tmp / "site"
    env = {**os.environ, "DT_SITE_TOML": str(tmp / "site.toml"), "DT_OUT": str(out), "DT_PRIVATE_TOML": private_with(tmp),
           "DT_PRICES_JSON": prices_with_test_link(tmp), "DT_ALLOW_LOCAL_API": "1"}
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
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


def report_page(browser, site, width=1280):
    rep = json.load(open(os.path.join(HERE, "fixtures", "paid-reports", "random.report.json"), encoding="utf-8"))
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    page = ctx.new_page()
    log = {"posts": [], "requests": [], "errors": []}
    page.on("pageerror", lambda e: log["errors"].append(str(e)))
    page.on("request", lambda r: log["requests"].append(r))

    def analyse(route):
        log["posts"].append(route.request)
        route.fulfill(status=200, content_type="application/json", body=json.dumps({"report": rep, "uses_left": 1}))
    page.route(API + "/analyse", analyse)
    # the site's existing page analytics (site.toml [analytics]), on main before S3: aborted here, never reached
    page.route("https://*cloudflareinsights.com/**", lambda route: route.abort())
    page.goto(site["origin"] + "/report/#t=" + fake_token())
    page.wait_for_selector("#rp-access:has-text('Access found')")
    return ctx, page, log


def wait_notice(page, n):
    page.wait_for_selector(f"#rp-small-n:has-text('{n} trades.')", state="visible", timeout=30000)


def visible_buttons(page, sel):
    return [b for b in page.query_selector_all(sel) if (b.bounding_box() or {}).get("width", 0) > 0]


def test_picker_takes_several_files_and_shows_the_hint(browser, site):
    ctx, page, log = report_page(browser, site)
    assert page.get_attribute("#rp-file", "multiple") is not None
    assert page.inner_text("#rp-hint").strip() == HINT
    assert "TradingView Order History" in page.inner_text("label[for=rp-file]")
    page.set_input_files("#rp-file", [A, B])
    wait_notice(page, 75)
    assert page.inner_text("#rp-count").strip() == "75 trades from 2 files."
    assert page.eval_on_selector_all("#rp-files li", "ls => ls.map((l) => l.textContent)") == ["acct_a.csv", "acct_b.csv"]
    assert not log["errors"]
    ctx.close()


def test_notice_waits_and_run_anyway_sends_one_post(browser, site):
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [A, B])
    wait_notice(page, 75)
    txt = page.inner_text("#rp-small")
    assert NOTICE in txt and WAIT in txt and "Run anyway" in txt and "Add more files" in txt
    page.wait_for_timeout(1500)
    assert log["posts"] == [] and page.is_hidden("#rp-status")          # waiting spends nothing
    page.fill("#rp-firm", "Acme")                                      # read when the run starts
    visible_buttons(page, "#rp-run-anyway")[0].click()
    page.wait_for_selector("#focus", timeout=30000)
    assert len(log["posts"]) == 1
    body = json.loads(log["posts"][0].post_data)
    assert set(body) == BODY_KEYS and len(body["rows"]) == 75 and body["firm_name"] == "Acme"
    for r in body["rows"]:
        assert set(r) == {"o", "h", "d", "q", "p", "s", "f"}
    post = log["posts"][0].post_data
    for s in ("acct_a", "acct_b", "ES", "NQ", "CL"):
        assert f'"{s}' not in post and s + ".csv" not in post, s
    # the network log: the page's own files, and the one POST
    beacon = [r for r in log["requests"] if r.url.split("/")[2].endswith("cloudflareinsights.com")]
    for r in beacon:   # the existing analytics carry nothing from the files
        for s in ("acct_a", "acct_b", ".csv", "5000.00", "ES,"):
            assert s not in (r.post_data or "") and s not in r.url, (r.url, s)
    others = [r for r in log["requests"] if not r.url.startswith(site["origin"]) and r.url != API + "/analyse" and r not in beacon]
    assert others == [], [r.url for r in others]
    assert [r.method for r in log["requests"] if r.url == API + "/analyse"] == ["POST"]
    assert page.inner_text("#copy-rows").strip() == LINE_30
    assert page.is_hidden("#rp-small")
    assert lint_text(page.inner_text("#focus"), "report", paid=True) == []
    assert not log["errors"]
    ctx.close()


def test_adding_files_recounts_and_runs_at_100(browser, site):
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", A)
    wait_notice(page, 60)
    with page.expect_file_chooser() as fc:
        visible_buttons(page, "#rp-add")[0].click()
    assert fc.value.is_multiple()
    fc.value.set_files(B)
    wait_notice(page, 75)
    assert page.inner_text("#rp-count").strip() == "75 trades from 2 files." and log["posts"] == []
    page.set_input_files("#rp-file", A)                     # the same file again: no change
    page.wait_for_timeout(500)
    assert page.inner_text("#rp-count").strip() == "75 trades from 2 files."
    page.set_input_files("#rp-file", C)                     # 60 + 45 − 30 + 25 = 100: no notice, the run starts
    page.wait_for_selector("#focus", timeout=30000)
    assert len(log["posts"]) == 1 and len(json.loads(log["posts"][0].post_data)["rows"]) == 100
    assert page.is_hidden("#rp-small")
    assert not log["errors"]
    ctx.close()


def test_another_platform_is_refused_and_the_list_stays(browser, site):
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [A, B])
    wait_notice(page, 75)
    page.set_input_files("#rp-file", OTHER_PLATFORM)
    page.wait_for_selector("#rp-status.notice-error", timeout=30000)
    assert page.inner_text("#rp-status").startswith("These files have different columns.")
    assert page.inner_text("#rp-count").strip() == "75 trades from 2 files." and page.is_visible("#rp-small")
    visible_buttons(page, "#rp-run-anyway")[0].click()
    page.wait_for_selector("#focus", timeout=30000)
    assert len(json.loads(log["posts"][0].post_data)["rows"]) == 75
    ctx.close()


def test_remove_these_files_starts_again(browser, site):
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", [A, B])
    wait_notice(page, 75)
    visible_buttons(page, "#rp-clear")[0].click()
    assert page.is_hidden("#rp-small") and page.is_hidden("#rp-picked")
    page.set_input_files("#rp-file", A)
    wait_notice(page, 60)
    assert page.inner_text("#rp-count").strip() == "60 trades from 1 file." and log["posts"] == []
    ctx.close()


def generic_file(tmp, n):
    p = tmp / f"t{n}.csv"
    rows = ["Open Time,Close Time,Symbol,Direction,Quantity,Open Price,Close Price,Fees"]
    for i in range(n):
        h, m = divmod(i * 20, 60)
        rows.append(f"2026-09-{1 + h // 8:02d} {9 + h % 8:02d}:{m:02d}:00,2026-09-{1 + h // 8:02d} {9 + h % 8:02d}:{m + 10:02d}:00,"
                    f"ES,Long,1,100,{100 + (i * 7) % 11 - 5},0")
    p.write_text("\n".join(rows) + "\n")
    return str(p)


@pytest.mark.parametrize("n,notice", [(99, True), (100, False), (101, False)])
def test_notice_below_100_only(browser, site, n, notice):
    f = generic_file(site["tmp"], n)
    ctx, page, log = report_page(browser, site)
    page.set_input_files("#rp-file", f)
    if notice:
        wait_notice(page, n)
        page.wait_for_timeout(500)
        assert log["posts"] == []
    else:
        page.wait_for_selector("#focus", timeout=30000)
        assert page.is_hidden("#rp-small") and len(log["posts"]) == 1
        assert len(json.loads(log["posts"][0].post_data)["rows"]) == n
        assert page.query_selector("#copy-rows") is None       # one file: no copy line
    ctx.close()


def test_drop_of_several_files(browser, site):
    ctx, page, log = report_page(browser, site)
    files = [{"name": os.path.basename(p), "text": open(p).read()} for p in (A, B)]
    page.evaluate("""(files) => { const dt = new DataTransfer();
        for (const f of files) dt.items.add(new File([f.text], f.name, { type: 'text/csv' }));
        document.getElementById('rp-drop').dispatchEvent(new DragEvent('drop', { dataTransfer: dt, bubbles: true, cancelable: true })); }""", files)
    wait_notice(page, 75)
    assert page.eval_on_selector_all("#rp-files li", "ls => ls.length") == 2
    ctx.close()


def test_phone_width_has_no_overflow(browser, site):
    from a11y import horizontal_overflow
    ctx, page, log = report_page(browser, site, width=390)
    page.set_input_files("#rp-file", [A, B])
    wait_notice(page, 75)
    assert horizontal_overflow(page) == []
    ctx.close()
