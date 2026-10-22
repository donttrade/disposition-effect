"""Journal storage (ARCHITECT-V3 §d.2-§d.6, step J1): Tester invariants J1-J4 (and J9's storage half).

Drives site/static/js/journal/store.js through tests/journal-harness.html in Chromium (repo_server).
"""
import json

import pytest

SETUP = """
window.mk = (acc, imp, n, base = 0) => Array.from({length: n}, (_, i) => ({
  k: acc + ':' + imp + ':' + (base + i), symbol: i % 2 ? 'XAUUSD' : 'EURUSD', dir: i % 3 ? 'long' : 'short',
  open_ts: Date.UTC(2026, 7, 1) + (base + i) * 3600e3, close_ts: Date.UTC(2026, 7, 1) + (base + i) * 3600e3 + 1800e3,
  hold_s: 1800, qty: 0.5, entry: 2400 + i, exit: 2401 + i, pnl: ((i * 37) % 11) - 5, pnl_gross: ((i * 37) % 11) - 4,
  fees: 1, pnl_unit: 'USD', fills_n: 2}));
window.acc = (id) => ({id, name: 'MT5 account ' + id, unit: 'USD', format: 'mt5', tz_label: 'broker server time',
  created: '2026-10-21T00:00:00Z', archived: false});
window.imp = (id, account_id) => ({id, account_id, file_name: 'ReportHistory.html', format: 'mt5', verified_format: false,
  imported_at: '2026-10-21T00:00:00Z', n_trades_in_file: 0, n_skipped_dupe: 0, n_possible_dupe_kept: 0, warnings: [],
  date_from: '2026-08-01', date_to: '2026-08-31'});
"""


@pytest.fixture
def jpage(browser, repo_server):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(repo_server + "/tests/journal-harness.html")
    pg.wait_for_function("document.getElementById('status').textContent === 'ready'")
    pg.evaluate(SETUP)
    yield pg
    ctx.close()


def test_j1_fresh_db_schema_and_stores(jpage):
    r = jpage.evaluate("""async () => { const db = await JS.open(); const out = {v: db.version, s: [...db.objectStoreNames].sort()};
      const st = await JS.loadAll(db); db.close(); return {...out, empty: st.trades.length === 0 && st.accounts.length === 0}; }""")
    assert r["v"] == 1 and r["s"] == sorted(["meta", "accounts", "imports", "chunks", "notes", "days", "lists"]) and r["empty"]


def test_j1_two_tabs_see_an_import_within_1s(browser, repo_server):
    ctx = browser.new_context()
    a, b = ctx.new_page(), ctx.new_page()
    for p in (a, b):
        p.goto(repo_server + "/tests/journal-harness.html")
        p.wait_for_function("document.getElementById('status').textContent === 'ready'")
        p.evaluate(SETUP)
    b.evaluate("() => { window.__seen = []; JS.onChange(c => __seen.push([c, performance.now()])); }")
    a.evaluate("""async () => { const db = await JS.open(); await JS.addImport(db, {account: acc('a_1'), imp: imp('i_1', 'a_1'), trades: mk('a_1', 'i_1', 50)}); }""")
    b.wait_for_function("__seen.length > 0", timeout=1000)
    n = b.evaluate("async () => { const db = await JS.open(); const s = await JS.loadAll(db); return s.trades.length; }")
    assert n == 50
    ctx.close()


def test_j1_chunks_hold_at_most_1000_trades(jpage):
    r = jpage.evaluate("""async () => { const db = await JS.open();
      await JS.addImport(db, {account: acc('a_1'), imp: imp('i_1', 'a_1'), trades: mk('a_1', 'i_1', 2500)});
      const tx = db.transaction('chunks'); const all = await new Promise(r => { const q = tx.objectStore('chunks').getAll(); q.onsuccess = () => r(q.result); });
      const st = await JS.loadAll(db);
      return {sizes: all.map(c => c.trades.length), ids: all.map(c => c.id), n: st.trades.length, imp: st.imports[0].chunk_ids.length}; }""")
    assert r["sizes"] == [1000, 1000, 500] and r["n"] == 2500 and r["imp"] == 3
    assert r["ids"][0] == "a_1:i_1:0000"


def test_j2_add_import_is_atomic(jpage):
    r = jpage.evaluate("""async () => { const db = await JS.open(); const t = mk('a_1', 'i_1', 1500);
      t[1400].symbol = () => 1;   // cannot be cloned: the second chunk's put throws mid-transaction
      let err = null; try { await JS.addImport(db, {account: acc('a_1'), imp: imp('i_1', 'a_1'), trades: t}); } catch (e) { err = String(e); }
      const st = await JS.loadAll(db);
      return {err, trades: st.trades.length, imports: st.imports.length, accounts: st.accounts.length}; }""")
    assert r["err"] and r["trades"] == 0 and r["imports"] == 0 and r["accounts"] == 0


def test_j9_undo_removes_exactly_that_import_and_its_notes(jpage):
    r = jpage.evaluate("""async () => { const db = await JS.open();
      await JS.addImport(db, {account: acc('a_1'), imp: imp('i_1', 'a_1'), trades: mk('a_1', 'i_1', 30)});
      await JS.addImport(db, {account: null, imp: imp('i_2', 'a_1'), trades: mk('a_1', 'i_2', 1200, 100)});
      await JS.putNote(db, {k: 'a_1:i_2:105', account_id: 'a_1', setup: 'pullback', tags: [], mistakes: [], note: 'x'});
      await JS.putNote(db, {k: 'a_1:i_1:3', account_id: 'a_1', setup: null, tags: ['london'], mistakes: [], note: ''});
      const removed = await JS.undoImport(db, 'i_2');
      const st = await JS.loadAll(db);
      return {removed, n: st.trades.length, imps: st.imports.map(i => i.id), notes: st.notes.map(n => n.k)}; }""")
    assert r == {"removed": 1200, "n": 30, "imps": ["i_1"], "notes": ["a_1:i_1:3"]}


def test_j20_sparse_notes_and_limits(jpage):
    r = jpage.evaluate("""async () => { const db = await JS.open();
      await JS.putNote(db, {k: 'a:1', account_id: 'a', setup: 'x', tags: [], mistakes: [], note: ''});
      await JS.putNote(db, {k: 'a:1', account_id: 'a', setup: null, tags: [], mistakes: [], note: ''});   // emptied → removed
      let long = null; try { await JS.putNote(db, {k: 'a:2', account_id: 'a', note: 'x'.repeat(5001)}); } catch (e) { long = String(e); }
      let big = null; try { await JS.putList(db, 'tag', ['x'.repeat(41)]); } catch (e) { big = String(e); }
      const st = await JS.loadAll(db); return {notes: st.notes.length, long, big, lists: st.lists}; }""")
    assert r["notes"] == 0 and "5000" in r["long"] and "40" in r["big"]
    assert r["lists"] == {"setup": [], "tag": [], "mistake": []}   # J21: lists start empty


FULL = """async () => { const db = await JS.open();
  await JS.addImport(db, {account: acc('a_1'), imp: imp('i_1', 'a_1'), trades: mk('a_1', 'i_1', 1100)});
  await JS.addImport(db, {account: acc('a_2'), imp: imp('i_2', 'a_2'), trades: mk('a_2', 'i_2', 40)});
  await JS.putNote(db, {k: 'a_1:i_1:7', account_id: 'a_1', setup: 'pullback', tags: ['london', 'news'], mistakes: ['moved stop'], note: 'late entry'});
  await JS.putDay(db, {account_id: 'a_1', date: '2026-08-01', note: 'tired'});
  await JS.putList(db, 'setup', ['pullback']); await JS.putList(db, 'tag', ['london', 'news']); await JS.putList(db, 'mistake', ['moved stop']);
  return db; }"""
STRIP = "s => JSON.stringify({accounts: s.accounts, imports: s.imports.map(({chunk_ids, ...i}) => i), trades: s.trades, notes: s.notes.map(({updated, ...n}) => n), days: s.days.map(({updated, ...d}) => d), lists: s.lists})"


def test_j3_backup_wipe_restore_is_deep_equal(jpage):
    r = jpage.evaluate(f"""async () => {{ const db = await ({FULL})(); const strip = {STRIP};
      const before = await JS.loadAll(db); const b = await JS.serialize(before);
      const text = JSON.stringify(b); const v = await JS.validate(text);
      await JS.wipe(db); const empty = (await JS.loadAll(db)).trades.length;
      const res = await JS.restore(db, v.data, 'replace'); const after = await JS.loadAll(db);
      return {{ok: v.ok, sha: v.shaOk, empty, same: strip(before) === strip(after), counts: b.counts, name: JS.backupName(new Date('2026-10-21T12:00:00Z')), res}}; }}""")
    assert r["ok"] and r["sha"] and r["empty"] == 0 and r["same"], r
    assert r["counts"] == {"accounts": 2, "imports": 2, "trades": 1140, "notes": 1, "days": 1}
    assert r["name"] == "donttrade-journal-2026-10-21.json"


def test_j3_bad_files_give_readable_answers(jpage):
    r = jpage.evaluate(f"""async () => {{ const db = await ({FULL})(); const b = await JS.serialize(await JS.loadAll(db));
      const changed = JSON.parse(JSON.stringify(b)); changed.trades[0].pnl = 999;
      const v2 = JSON.parse(JSON.stringify(b)); v2.version = 2;
      const broken = JSON.parse(JSON.stringify(b)); broken.trades[3].close_ts = 'yesterday';
      return {{changed: await JS.validate(JSON.stringify(changed)), v2: await JS.validate(JSON.stringify(v2)),
              junk: await JS.validate('{{not json'), other: await JS.validate('{{"format": "x"}}'),
              broken: await JS.validate(JSON.stringify(broken))}}; }}""")
    assert r["changed"]["ok"] and r["changed"]["shaOk"] is False   # the page asks "Restore anyway?"
    assert not r["v2"]["ok"] and r["v2"]["newer"] and "newer version of this page" in r["v2"]["problems"][0]
    assert not r["junk"]["ok"] and "not readable JSON" in r["junk"]["problems"][0]
    assert not r["other"]["ok"] and "not a donttrade journal backup" in r["other"]["problems"][0]
    assert not r["broken"]["ok"] and r["broken"]["problems"] == ["Trade 4 is damaged."]


def test_j4_merge_adds_only_new_keys_and_keeps_existing_notes(jpage):
    r = jpage.evaluate(f"""async () => {{ const db = await ({FULL})();
      const b = await JS.serialize(await JS.loadAll(db));
      // the journal changes after the backup: one trade's note is rewritten, one import is undone
      await JS.putNote(db, {{k: 'a_1:i_1:7', account_id: 'a_1', setup: 'breakout', tags: [], mistakes: [], note: 'rewritten'}});
      await JS.undoImport(db, 'i_2');
      const res = await JS.restore(db, b, 'merge');
      const st = await JS.loadAll(db);
      return {{res, n: st.trades.length, note: st.notes.find(n => n.k === 'a_1:i_1:7').note, imps: st.imports.length}}; }}""")
    assert r["res"]["trades"] == 40 and r["n"] == 1140 and r["imps"] == 2
    assert r["note"] == "rewritten" and r["res"]["conflicts"] == [{"kind": "note", "k": "a_1:i_1:7"}]
    # merging the same file again adds nothing
    r2 = jpage.evaluate("""async () => { const db = await JS.open(); const b = await JS.serialize(await JS.loadAll(db));
      const res = await JS.restore(db, b, 'merge'); return [res.trades, res.notes, res.days, (await JS.loadAll(db)).trades.length]; }""")
    assert r2 == [0, 0, 0, 1140]


def test_j32_wipe_empties_everything(jpage):
    r = jpage.evaluate(f"""async () => {{ const db = await ({FULL})(); await JS.wipe(db); const s = await JS.loadAll(db);
      return [s.trades.length, s.accounts.length, s.imports.length, s.notes.length, s.days.length, s.meta]; }}""")
    assert r == [0, 0, 0, 0, 0, None]


def test_j33_store_uses_no_localstorage_and_no_network():
    import os
    src = open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "site", "static", "js", "journal",
                            "store.js"), encoding="utf-8").read()
    for bad in ("localStorage", "sessionStorage", "fetch(", "XMLHttpRequest", "sendBeacon", "document.cookie", "WebSocket"):
        assert bad not in src, bad


# ---- store v2 hook (ARCHITECT-BRAND §6.1b): a later version's step runs on a v1 journal and keeps everything
STEP2 = "{...JS.MIGRATIONS, 2(db) { db.createObjectStore('plans', {keyPath: 'k'}); }}"


def test_store_migration_hook_upgrades_v1_in_place(jpage):
    r = jpage.evaluate(f"""async () => {{ const db = await ({FULL})(); const strip = {STRIP};
      const before = await JS.loadAll(db); db.close();
      const db2 = await JS.open(JS.DB_NAME, 2, {STEP2});
      const after = await JS.loadAll(db2);
      const out = {{v: db2.version, stores: [...db2.objectStoreNames].sort(), same: strip(before) === strip(after),
                   schema1: before.meta && before.meta.schema, schema2: after.meta && after.meta.schema}};
      db2.close(); return out; }}""")
    assert r["v"] == 2 and "plans" in r["stores"] and r["same"], r
    assert r["schema1"] == 1 and r["schema2"] == 2, r


def test_store_missing_migration_step_refuses_and_keeps_v1(jpage):
    r = jpage.evaluate(f"""async () => {{ const db = await ({FULL})(); const n = (await JS.loadAll(db)).trades.length; db.close();
      let err = null; try {{ (await JS.open(JS.DB_NAME, 3, {STEP2})).close(); }} catch (e) {{ err = String(e && e.message || e); }}
      const db1 = await JS.open(); const out = {{err, v: db1.version, n, n2: (await JS.loadAll(db1)).trades.length}}; db1.close(); return out; }}""")
    assert r["err"] and r["v"] == 1 and r["n"] == r["n2"] == 1140, r


def test_backup_v1_file_restores_through_a_v2_step(jpage):
    r = jpage.evaluate(f"""async () => {{ const db = await ({FULL})(); const b = await JS.serialize(await JS.loadAll(db));
      const text = JSON.stringify(b);
      const v = await JS.validate(text, 2, {{2: (d) => ({{...d, version: 2, plans: []}})}});
      const gap = await JS.validate(text, 2, {{}});
      const same = await JS.validate(text);
      return {{ok: v.ok, sha: v.shaOk, ver: v.data && v.data.version, plans: v.data && v.data.plans, trades: v.data && v.data.trades.length,
              gap, sameOk: same.ok && same.shaOk && same.data.version === 1}}; }}""")
    assert r["ok"] and r["sha"] and r["ver"] == 2 and r["plans"] == [] and r["trades"] == 1140, r
    assert not r["gap"]["ok"] and "older version" in r["gap"]["problems"][0]
    assert r["sameOk"]
