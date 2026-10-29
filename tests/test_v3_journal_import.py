"""Journal import and dedupe (ARCHITECT-V3 §d.4, step J2): Tester invariants J5-J9 on the engine fixtures.

Each format's fixtures go through the unchanged engine (runFile) and keys.forJournal, then import.plan/commit
into IndexedDB (tests/journal-harness.html). Re-importing adds nothing; overlapping exports union exactly.
"""
import os

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FIX = os.path.join(REPO, "tests", "fixtures")


def _fixtures():
    out = []
    for fmt in ("mt5", "mt4", "ibkr", "tradovate", "tradingview", "generic", "generic_roundtrip"):
        for name in sorted(os.listdir(os.path.join(FIX, fmt))):
            if name.endswith((".csv", ".htm", ".html")):
                out.append(f"tests/fixtures/{fmt}/{name}")
    return out


@pytest.fixture(scope="module")
def jctx(browser, repo_server):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(repo_server + "/tests/journal-harness.html")
    pg.wait_for_function("document.getElementById('status').textContent === 'ready'")
    yield pg
    ctx.close()


def _fresh(pg):
    pg.evaluate("async () => { const db = await JS.open(); await JS.wipe(db); db.close(); }")


def test_j5_reimporting_any_fixture_adds_nothing(jctx):
    ran = 0
    for path in _fixtures():
        _fresh(jctx)
        first = jctx.evaluate("p => importFixture(p, 'A')", path)
        if "error" in first or "problem" in first:
            continue   # an error fixture (the engine refuses it): nothing to import
        again = jctx.evaluate("p => importFixture(p, 'A')", path)
        assert first["added"] == first["total"] - first["possible"], (path, first)
        assert "problem" in again or (again["added"] == 0 and again["dupes"] == first["added"]), (path, first, again)
        ran += 1
    assert ran >= 25


def test_j6_overlapping_exports_union_equals_the_single_export(jctx):
    _fresh(jctx)
    a = jctx.evaluate("importFixture('tests/fixtures/journal/a.csv', 'A')")
    b = jctx.evaluate("importFixture('tests/fixtures/journal/b.csv', 'A')")
    full = jctx.evaluate("parseFixture('tests/fixtures/journal/full.csv')")
    st = jctx.evaluate("async () => { const s = await JS.loadAll(await JS.open()); return s.trades.map(t => t.k.split(':')[1]).sort(); }")
    assert b["dupes"] > 0 and a["added"] + b["added"] == len(full["trades"])
    assert st == sorted(t["h"] for t in full["trades"])
    # B re-imported into a second account is independent of A
    c = jctx.evaluate("importFixture('tests/fixtures/journal/b.csv', 'B')")
    assert c["dupes"] == 0 and c["added"] == b["added"] + b["dupes"]


def test_j7_identical_trades_in_one_file_are_both_kept(jctx):
    _fresh(jctx)
    r = jctx.evaluate("importFixture('tests/fixtures/journal/twins.csv', 'A')")
    assert r["total"] == 3 and r["added"] == 3
    again = jctx.evaluate("importFixture('tests/fixtures/journal/twins.csv', 'A')")
    assert again["added"] == 0 and again["dupes"] == 3


def test_j8_possible_duplicate_is_skipped_by_default_and_can_be_kept(jctx):
    _fresh(jctx)
    jctx.evaluate("importFixture('tests/fixtures/journal/a.csv', 'A')")
    r = jctx.evaluate("importFixture('tests/fixtures/journal/possible.csv', 'A')")
    assert r["possible"] == 1 and r["added"] == 0
    r2 = jctx.evaluate("""async () => { const db = await JS.open(); const st = await JS.loadAll(db);
      const parsed = await parseFixture('tests/fixtures/journal/possible.csv');
      const p = JI.plan(st, parsed, st.accounts[0]);
      return {list: p.possible.map(x => [x.trade.symbol, x.existing.symbol, x.trade.pnl !== x.existing.pnl]),
              res: (await JI.commit(db, p, parsed, 'possible.csv', [p.possible[0].i])).added}; }""")
    assert r2["list"][0][0] == r2["list"][0][1] and r2["list"][0][2] and r2["res"] == 1


def test_j9_undo_restores_the_prior_totals(jctx):
    _fresh(jctx)
    jctx.evaluate("importFixture('tests/fixtures/journal/a.csv', 'A')")
    before = jctx.evaluate("async () => { const s = await JS.loadAll(await JS.open()); return [s.trades.length, s.trades.reduce((x, t) => x + t.pnl, 0)]; }")
    b = jctx.evaluate("importFixture('tests/fixtures/journal/b.csv', 'A')")
    jctx.evaluate("id => JS.open().then(db => JS.undoImport(db, id))", b["imp"])
    after = jctx.evaluate("async () => { const s = await JS.loadAll(await JS.open()); return [s.trades.length, s.trades.reduce((x, t) => x + t.pnl, 0)]; }")
    assert after[0] == before[0] and abs(after[1] - before[1]) < 1e-6


def test_j2_unit_mismatch_is_refused_with_the_stated_message(jctx):
    _fresh(jctx)
    jctx.evaluate("importFixture('tests/fixtures/journal/a.csv', 'A')")
    r = jctx.evaluate("""async () => { const db = await JS.open(); const st = await JS.loadAll(db);
      const parsed = await parseFixture('tests/fixtures/journal/b.csv'); parsed.pnl_unit = 'EUR';
      return JI.plan(st, parsed, st.accounts[0]).problem; }""")
    assert r.startswith("This account’s results are in ") and r.endswith("Add it to another account.") and "EUR" in r


def test_j2_worker_gives_the_same_keys_as_the_page(jctx):
    for path in ("tests/fixtures/journal/full.csv", "tests/fixtures/mt5/deals.csv", "tests/fixtures/ibkr/activity_flex.csv"):
        page = jctx.evaluate("p => parseFixture(p)", path)
        work = jctx.evaluate("p => parseInWorker(p)", path)
        assert [t["h"] for t in work["result"]["trades"]] == [t["h"] for t in page["trades"]], path
    html = jctx.evaluate("parseInWorker('tests/fixtures/mt5/deals_netting.htm')")
    assert html.get("needsPage") is True


# The engine commits made after the journal (motion), each a new reader the journal did not need to change.
# The universal importer (B1/B2) adds readers beside it; one file through runFile() reads as before,
# with dates_only and n_date_only added to the result (the journal does not read them yet).
ENGINE_COMMITS_SINCE_MOTION = ("Engine: TradingView Order History parser",
                               "Engine: mapped columns, several files, pasted tables, dates_only",
                               "Engine: eight timed presets, synthetic importer fixtures",
                               "Engine: the column guess for the mapper",
                               # the importer's fix round (Tester report 29 Oct): one file still reads as
                               # before, except a Sierra log (now its preset) and the wide-row warning
                               "Paste: fixed-width columns", "Rows wider than the heading",
                               "Several files: the overlap key", "runFile goes through the preset flow",
                               "Guess: footers and short rows", "Dates: day level for rows without a time",
                               "Block list widened",
                               # round 2 (Tester report 30 Oct)
                               "A refused wide fill leaves out the fills that depend on it",
                               "Block list: the identifiers left from round 2",
                               "Guess: summary rows by what they hold")


def test_j13_engine_and_file_worker_untouched():
    import subprocess
    paths = ["--", "site/static/js/engine", "site/static/js/tools/file-worker.js"]
    r = subprocess.run(["git", "-C", REPO, "diff", "--stat", "HEAD"] + paths, capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout
    r = subprocess.run(["git", "-C", REPO, "log", "--format=%s", "motion..HEAD"] + paths, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert all(s.startswith(ENGINE_COMMITS_SINCE_MOTION) for s in r.stdout.splitlines()), r.stdout
