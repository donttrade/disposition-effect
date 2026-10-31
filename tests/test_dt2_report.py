"""DT-2 of the donttrade test on the report page (ARCHITECT-EVIDENCE-SCALE-AND-POWER-2026-10-31 §7 S1, §2.4, §2.5, §5.2,
§5.4, §10; ARCHITECT-SMALL-FILES-ADDENDUM-2026-10-31 §3, §6).

* W-1: every VERDICT_STRINGS entry passes the page word rules (paid) and banned.toml [verdict_hedges]; the lint rule
  itself catches a hedge planted in VERDICT_STRINGS and in a data-lint="verdict" passage (EN and FR).
* The truth table: 3 habits x {none, some, clear, too_few, dates_only} x {first report, re-test}, each cell drawn by the
  real report.js in Chromium from a report built on an engine golden. Each cell shows its pill (no digit in any pill),
  "Habit or chance?", the step line, the guard line under every Some and Clear number, the catch line under every No
  sign and Some sign, the re-test lines only on a re-test, and no hedge word anywhere in the verdict layer. Size after
  a loss is not shipped in DT-2: a report that gives it a step is refused, its dates-only cell renders as facts.
* Some sign is never the focus and never flagged (§2.4 items 2–3).
* Both a stats2f (DT-1) report and a DT-2 report render (dual accept; every committed fixture of each method).
* The small-file layout (addendum §3.1): the too-few habits in one line, the re-test reason from the catch line.
* The steps are the engine's: the cuts, the minimum and the family size are read from the report; a report with
  another Clear cut is refused.
The forged-report page test (REPORT_ERROR) is tests/test_report_error_line.py; the screens (360 px, axe) are
tests/test_dt2_screens.py."""
import glob
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
import lint as L  # noqa: E402

DT2_FIX = os.path.join(HERE, "fixtures", "paid-reports-dt2")
S2F_FIX = os.path.join(HERE, "fixtures", "paid-reports")
STEP = {"clear": "Clear sign", "some": "Some sign", "none": "No sign", "too_few": "Too few trades", "dates_only": "No check on this file"}
GUARD = "This counts how often chance alone does this. It is not the chance your habit is real."
# Retired display words (labels, headings, the more-trades lines): on no report of either method.
RETIRED_SHOWN = ["Not clear yet", "Unlikely to be luck", "could be luck", "Luck check coming", "Real or luck?", "luck check", "Why not yet",
                 "Not distinguishable", "not enough trades to tell", "more trades would give", "even odds"]
# Retired sentences: on no DT-2 report (a DT-1 report keeps its frozen sentences, wording-stats2f.js, for one release).
RETIRED_DT2 = RETIRED_SHOWN + ["distinguishable", "noise", "luck", "Not enough trades to tell", "described"]


def node(js, stdin=None):
    r = subprocess.run(["node", "--input-type=module", "-e", js], cwd=REPO, input=stdin, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def load(name, d=DT2_FIX):
    return json.load(open(os.path.join(d, name + ".report.json"), encoding="utf-8"))


# ------------------------------------------------------------------ W-1 and the lint rule

def verdict_strings():
    return node("import * as W from './site/static/js/paid/wording.js'; process.stdout.write(JSON.stringify(W.VERDICT_STRINGS));")


def test_w1_verdict_strings_pass_the_word_rules_and_the_hedge_rule():
    vs = verdict_strings()
    assert len(vs) >= 40
    for s in STEP.values():
        assert s in vs
    assert "Habit or chance?" in vs and GUARD in vs
    for t in vs:
        assert L.lint_text(t, "report", paid=True, analytics=True) == [], (t, L.lint_text(t, "report", paid=True, analytics=True))
        assert L.verdict_hedge_hits(t, "report") == [], t
    assert L.verdict_string_problems(os.path.join(REPO, "site/static/js/paid/wording.js"), "/static/js/paid/wording.js") == []


def test_the_hedge_rule_holds_every_word_the_owner_banned():
    words = ["may", "might", "maybe", "possibly", "perhaps", "unclear", "not clear", "could be", "likely", "unlikely", "luck", "noise",
             "distinguishable"]
    for w in words:
        assert L.verdict_hedge_hits(f"This result {w} holds.", "x"), w
    for w in ("proven", "confirmed", "definitely"):   # plan §9.4 item 9: overclaims
        assert L.verdict_hedge_hits(f"A {w} habit.", "x"), w
    for w in ("peut-être", "pourrait", "incertain", "pas clair"):   # plan R10
        assert L.verdict_hedge_hits(f"Le résultat {w} tenir.", "x", french=True), w
    # whole words: "sign" is not "signal", "chance" is not a hedge, "Clear sign" is not "not clear"
    assert L.verdict_hedge_hits("Clear sign. No sign. Some sign, short of clear. Chance alone.", "x") == []


def test_the_lint_refuses_a_hedge_in_verdict_strings_and_in_marked_page_text(tmp_path):
    src = open(os.path.join(REPO, "site/static/js/paid/wording.js"), encoding="utf-8").read()
    bad = src.replace("export const GUARD_LINE = 'This counts how often chance alone does this.",
                      "export const GUARD_LINE = 'This may be luck. This counts how often chance alone does this.")
    assert bad != src
    (tmp_path / "wording.js").write_text(bad, encoding="utf-8")
    hits = L.verdict_string_problems(str(tmp_path / "wording.js"), "/static/js/paid/wording.js")
    assert {h[0] for h in hits} == {"verdict:hedge"} and any("“may”" in h[2] for h in hits) and any("“luck*”" in h[2] for h in hits)
    html = '<html lang="en"><body><p data-lint="verdict">The result could be noise.</p></body></html>'
    assert [h[0] for h in L.verdict_hedge_hits(L.verdict_marked(html)[0], "x")] == ["verdict:hedge", "verdict:hedge"]
    fr = '<html lang="fr"><body><span data-lint="verdict">Le résultat pourrait être dû au hasard.</span></body></html>'
    assert L.verdict_hedge_hits(L.verdict_marked(fr)[0], "x", french=True)


# ------------------------------------------------------------------ the truth table, drawn in Chromium

# Builds each cell's report from the engine golden stats-r2__22-h0 (200 trades, revenge and tilt checked, No sign):
# the habit's state is set the way the engine sets it, then the counts and the focus are recomputed as the engine does.
CELLS_JS = r"""
async ({ base, cells }) => {
  const { renderReport } = await import('/site/static/js/paid/report.js');
  const W = await import('/site/static/js/paid/wording.js');
  const clone = (x) => JSON.parse(JSON.stringify(x));
  const by = (r, id) => r.habits.find((h) => h.id === id);
  function setState(r, id, st) {
    const h = by(r, id);
    if (st === 'dates_only') {
      r.dates_only = true; r.n_date_only_rows = r.n_rows; r.n_trades = r.n_rows;
      for (const x of r.habits) {
        if (x.id === 'revenge' || x.id === 'tilt') Object.assign(x, { status: 'dates_only', p_raw: null, p_holm: null, p_mean1: null, p_rank1: null, step: null,
          chance_per_100: null, chance_below_1: null, small_group: null, n_perm: null, measure_a: null, measure_b: null, effect: null, dollars: null,
          catch: null, catch_reason: 'dates_only', detail: null });
        if (x.id === 'size_up') Object.assign(x, { measure_a: null, measure_b: null, effect: null, dollars: null });
      }
      return;
    }
    if (st === 'too_few') { Object.assign(h, { status: 'too_few', n_a: 3, p_raw: null, p_holm: null, p_mean1: null, p_rank1: null, step: null, chance_per_100: null,
      chance_below_1: null, small_group: null, n_perm: null }); return; }
    // none: the gap runs the other way; none_gap: the habit's way, within chance (adjusted p 0.45); small_none: a smaller
    // group of 7 with an adjusted p of 0.12, which is No sign there (never Some, calibration fixes item 2); small_clear
    const p = { none: [0.6, 1], none_gap: [0.15, 0.45], some: [0.04, 0.12], clear: [0.002, 0.006], small_none: [0.04, 0.12], small_clear: [0.002, 0.006] }[st];
    const other = st === 'none', small = st.startsWith('small_');
    const step = { none_gap: 'none', small_none: 'none', small_clear: 'clear' }[st] || st;
    if (small) h.n_a = 7;
    Object.assign(h, { status: 'tested', p_raw: p[0], p_mean1: p[0], p_rank1: p[0] / 2, p_holm: p[1], step,
      chance_per_100: W.chancePer100(p[1], step, r.promise_per_100), chance_below_1: step === 'clear' && p[1] < 0.01, small_group: small,
      n_perm: h.n_perm || 10000, effect: other ? 2.5 : -6.5, measure_a: other ? 4 : -5, measure_b: 1.5 });
    if (h.dollars) h.dollars.amount = other ? 80 : -420;
  }
  function recount(r) {
    const t = r.habits.filter((h) => h.status === 'tested');
    r.n_tested = t.length; r.n_clear = t.filter((h) => h.step === 'clear').length; r.n_some = t.filter((h) => h.step === 'some').length;
    let best = null;
    for (const h of t) if (h.step === 'clear' && h.dollars.amount < 0 && (!best || h.dollars.amount < best.dollars.amount)) best = h;
    r.focus = best ? best.id : null;
  }
  const out = {};
  for (const [key, id, st, retest] of cells) {
    const r = clone(base);
    if (id === 'size_up' && st !== 'dates_only') {
      // size after a loss is not shipped in DT-2: a report that gives it a state of a checked habit is refused
      const h = by(r, 'size_up');
      if (st === 'too_few') Object.assign(h, { status: 'too_few' });
      else Object.assign(h, { status: 'tested', p_raw: 0.01, p_holm: 0.03, step: st, chance_per_100: 3, n_perm: 10000, effect: 1.4 });
    } else setState(r, id, st);
    recount(r);
    const div = document.createElement('div');
    document.body.append(div);
    let thrown = null;
    try { renderReport(r, div, retest ? { uses_left: 0 } : { uses_left: 1, retest: null }); } catch (e) { thrown = e.message; }
    const q = (sel) => [...div.querySelectorAll(sel)];
    const sec = div.querySelector('#habit-' + id);
    out[key] = { thrown,
      pills: q('.badge').map((b) => b.textContent),
      pill: sec && sec.querySelector('.layer-check .badge') ? sec.querySelector('.layer-check .badge').textContent : null,
      pillClass: sec && sec.querySelector('.layer-check .badge') ? sec.querySelector('.layer-check .badge').className : null,
      heading: sec && sec.querySelector('.layer-check h4') ? sec.querySelector('.layer-check h4').textContent : null,
      check: sec ? [...sec.querySelectorAll('.layer-check > p.habit-sentence, .layer-check > p.habit-guard')].map((p) => p.textContent) : [],
      lead: sec && sec.querySelector('.catch .habit-catch') ? sec.querySelector('.catch .habit-catch').textContent : null,
      table: sec && sec.querySelector('.catch-table') ? { caption: sec.querySelector('.catch-table caption').textContent,
        head: [...sec.querySelectorAll('.catch-table thead th')].map((t) => [t.textContent, t.getAttribute('scope')]),
        rows: [...sec.querySelectorAll('.catch-table tbody tr')].map((tr) => [tr.querySelector('th').textContent, tr.querySelector('th').getAttribute('scope'),
          tr.querySelector('.catch-val').textContent, tr.querySelector('.catch-fill').style.width, tr.querySelector('.catch-bar').getAttribute('aria-hidden')]) } : null,
      what: sec ? [...sec.querySelectorAll('.layer-what p.habit-sentence')].map((p) => p.textContent) : [],
      inFacts: !!div.querySelector('#your-numbers #habit-' + id),
      focus: q('#focus-lines p').map((p) => p.textContent),
      coverage: q('#coverage p').map((p) => p.textContent),
      retest: q('#retest-lines p').map((p) => p.textContent),
      rpRetest: !!div.querySelector('#rp-retest'),
      hit: q('.hs-verdict.is-hit .hs-of').map((x) => x.textContent),
      verdictText: q('.layer-check, #focus-lines, #coverage, #retest-lines, .hs-top, .hs-res').map((x) => x.textContent).join(' \n '),
      foot: div.lastElementChild ? div.lastElementChild.textContent : '' };
    div.remove();
  }
  return out;
}
"""
HABITS = ["revenge", "tilt", "size_up"]
STATES = ["none", "none_gap", "some", "clear", "small_none", "small_clear", "too_few", "dates_only"]
CELLS = [(f"{h}/{s}/{'retest' if rt else 'first'}", h, s, rt) for h in HABITS for s in STATES for rt in (False, True)]


@pytest.fixture(scope="module")
def table(browser, repo_server):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/site/static/js/paid/")
    out = page.evaluate(CELLS_JS, {"base": load("stats-r2__22-h0"), "cells": [list(c) for c in CELLS]})
    ctx.close()
    assert errors == []
    return out


def test_the_truth_table_has_every_cell(table):
    assert len(table) == 48 == len(HABITS) * len(STATES) * 2


@pytest.mark.parametrize("key,hid,st,retest", CELLS, ids=[c[0] for c in CELLS])
def test_truth_table_cell(table, key, hid, st, retest):
    c = table[key]
    if hid == "size_up" and st != "dates_only":
        assert c["thrown"] and "(DT-2)" in c["thrown"], c["thrown"]   # REPORT_ERROR on the page (test_report_error_line.py)
        return
    assert c["thrown"] is None, c["thrown"]
    for p in c["pills"]:
        assert not re.search(r"\d", p), p
        assert p in STEP.values(), p
    assert L.verdict_hedge_hits(c["verdictText"], key) == [], c["verdictText"]
    for bad in RETIRED_DT2:
        assert bad.lower() not in c["verdictText"].lower(), bad
    # re-test lines only on the re-test's own report; the re-test line only on a first report
    if retest:
        assert c["retest"][0].startswith("This re-test checks a longer history that includes your first file.")
        assert "at most 5 in 100 times" in c["retest"][0] and c["retest"][1] == "Steps can move between runs by chance alone."
        assert "DT-1 of the donttrade test" in c["retest"][2] and not c["rpRetest"]
    else:
        assert c["retest"] == [] and c["rpRetest"]
    assert c["foot"].startswith("Method DT-2 of the donttrade test (2026-10-31.stats3a)")
    if hid == "size_up":   # dates-only: size after a loss is facts, with the dates-only line
        assert c["inFacts"] and c["pill"] is None
        assert c["what"] and c["what"][0].startswith("No check on this file: all 200 trades in this file open at exactly 00:00")
        return
    if st == "dates_only":
        assert c["pill"] == STEP["dates_only"] and c["heading"] == "Habit or chance?"
        assert len(c["check"]) == 1 and c["check"][0].startswith("No check on this file: all 200 trades in this file open at exactly 00:00")
        assert c["check"][0].endswith("this habit depends on the order of trades within a day, which these rows do not show.")
        assert c["focus"][0].endswith("so the 3 habits that depend on the order of trades within a day get no check on this file.")
        return
    shown = {"none_gap": "none", "small_none": "none", "small_clear": "clear"}.get(st, st)
    assert c["pill"] == STEP[shown] and c["heading"] == "Habit or chance?"
    if st.startswith("small_"):   # a smaller group of 5-9: Clear sign or No sign, never Some sign
        assert "Some sign" not in c["pills"] and "badge-some" not in c["pillClass"]
        if st == "small_none":
            assert c["check"] == [f"No sign beyond chance in these 200 trades.",
                                  "With 7 trades in the smaller group, this check shows a Clear sign or no sign."]
            assert c["lead"] is not None and len(c["table"]["rows"]) == 3
        else:
            assert c["check"][0].startswith("Clear sign of this habit in these 200 trades.") and c["check"][1:] == [GUARD] and c["table"] is None
        return
    if st == "too_few":
        assert c["check"] == ["Too few trades to check: this habit compares two groups of at least 5 trades each, and this file has 3 and "
                              + ("148" if hid == "revenge" else "151") + "."]
        assert any(x.startswith("Too few trades to check: ") for x in c["coverage"])
        return
    first = c["check"][0]
    n = "200"
    if st == "clear":
        assert first == f"Clear sign of this habit in these {n} trades. In files with no real habit, a result this strong turns up fewer than 1 in 100 times, allowing for all 3 habits at once."
        assert c["check"][1:] == [GUARD] and c["table"] is None and c["lead"] is None   # no catch figure under a Clear sign
        assert len(c["hit"]) == 1 and "badge-clear" in c["pillClass"]
        assert c["focus"][0].startswith("Clear sign on 1 of 3 habits, some sign on 0.")
        assert c["focus"][1].startswith("Shown first: ")   # a Clear sign with a loss total is the focus
    elif st == "some":
        assert first == f"Some sign of this habit in these {n} trades, short of clear. In files with no real habit, a result this strong turns up at most 12 in 100 times, allowing for all 3 habits at once."
        assert c["check"][1:] == [GUARD]
        # never the focus and never flagged (§2.4 items 2-3)
        assert c["hit"] == [] and "badge-some" in c["pillClass"] and "badge-clear" not in c["pillClass"]
        assert c["focus"][0].startswith("Clear sign on 0 of 3 habits, some sign on 1.")
        assert c["focus"][1] == "No habit is shown first. A habit is shown first only when it has a Clear sign and its dollar total is a loss."
        assert not any(x.startswith("Shown first") for x in c["focus"])
    elif st == "none_gap":   # the card shows a gap the habit's way: the line says it is within chance, never "no sign of this habit"
        assert c["check"] == [f"No sign beyond chance in these {n} trades: a gap this size is common in files with no habit."]
    else:                    # the gap runs the other way
        what = "trades soon after a loss" if hid == "revenge" else "trades after 2 or more losses in a row"
        assert c["check"] == [f"No sign in these {n} trades: {what} did not do worse than your other trades."]
    if st != "clear":        # the catch figure: one lead line, then a labelled table, one row per size, bar = lower bound
        assert re.fullmatch(r"If the habit is real at \$\d+\.\d\d a trade and your next trades look like these, a file shows it as a Clear sign:", c["lead"]), c["lead"]
        t = c["table"]
        assert t["caption"] == "How often a file of each size shows this habit as a Clear sign"
        assert t["head"] == [["File size", "col"], ["Shown as a Clear sign", "col"]]
        assert [r[0] for r in t["rows"]] == ["200 trades (this file)", "400 trades", "800 trades"]
        for size, scope, val, width, hidden in t["rows"]:
            m = re.fullmatch(r"at least (\d+) in 10|fewer than 1 in 10", val)
            assert m and scope == "row" and hidden == "true", (size, val)
            assert width == f"{10 * int(m.group(1)) if m.group(1) else 0}%", (val, width)   # the bar never shows more than the words


# ------------------------------------------------------------------ dual accept: every committed report of each method

RENDER_ALL_JS = r"""
async (reps) => {
  const { renderReport } = await import('/site/static/js/paid/report.js');
  const out = {};
  for (const [k, rep] of Object.entries(reps)) {
    const div = document.createElement('div');
    document.body.append(div);
    try {
      renderReport(rep, div, { uses_left: 1, retest: null });
      out[k] = { text: div.innerText, pills: [...div.querySelectorAll('.badge')].map((b) => b.textContent),
        headings: [...div.querySelectorAll('.layer-check h4')].map((h) => h.textContent),
        verdict: [...div.querySelectorAll('.layer-check, #focus-lines, #coverage, .hs-top')].map((x) => x.textContent).join('\n'),
        foot: div.lastElementChild.textContent };
    } catch (e) { out[k] = { thrown: e.message }; }
    div.remove();
  }
  return out;
}
"""


@pytest.fixture(scope="module")
def all_rendered(browser, repo_server):
    reps = {}
    for d, tag in ((DT2_FIX, "dt2"), (S2F_FIX, "s2f")):
        for f in sorted(glob.glob(os.path.join(d, "*.report.json"))):
            reps[tag + ":" + os.path.basename(f)] = json.load(open(f, encoding="utf-8"))
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/site/static/js/paid/")
    out = page.evaluate(RENDER_ALL_JS, reps)
    ctx.close()
    assert errors == []
    return out


def test_every_dt2_and_stats2f_fixture_renders(all_rendered):
    dt2 = {k: v for k, v in all_rendered.items() if k.startswith("dt2:")}
    s2f = {k: v for k, v in all_rendered.items() if k.startswith("s2f:")}
    assert len(dt2) >= 30 and len(s2f) >= 10
    for k, v in all_rendered.items():
        assert "thrown" not in v, (k, v)
        assert all(h == "Habit or chance?" for h in v["headings"]), k
        for p in v["pills"]:
            assert not re.search(r"\d", p), (k, p)
        for bad in RETIRED_SHOWN:
            assert bad not in v["text"], (k, bad)
        assert "described" not in v["text"] and "not tested" not in v["text"].lower(), k
        assert L.lint_text(v["text"], k, paid=True) == [], (k, L.lint_text(v["text"], k, paid=True))
    for k, v in dt2.items():
        for bad in RETIRED_DT2:
            assert bad.lower() not in v["text"].lower(), (k, bad)
        assert set(v["pills"]) <= set(STEP.values()), k
        assert L.verdict_hedge_hits(v["verdict"], k) == [], k
        assert v["foot"].startswith("Method DT-2 of the donttrade test"), k
    for k, v in s2f.items():   # DT-1 results in their own words, never a DT-2 step
        assert set(v["pills"]) <= {"Beyond chance", "Within chance", "Too few trades", "No check on this file"}, (k, v["pills"])
        assert v["foot"].startswith("Method DT-1 of the donttrade test (2026-10-23.stats2f)"), k


def test_the_frozen_stats2f_wording_is_word_for_word_the_old_one():
    old = subprocess.run(["git", "show", "9d4bdde:site/static/js/paid/wording.js"], cwd=REPO, capture_output=True, text=True)
    if old.returncode != 0:
        pytest.skip("9d4bdde not in this clone")
    frozen = open(os.path.join(REPO, "site/static/js/paid/wording-stats2f.js"), encoding="utf-8").read()
    body = old.stdout[:old.stdout.index('// ---------------------------------------------------------------- "N more trades to tell"')]
    body = body.replace("import { POWER_TABLE } from './power-table.js';\n\n", "").rstrip() + "\n"
    assert frozen.endswith(body)


def test_the_old_site_refuses_a_dt2_report_and_the_new_one_refuses_an_unknown_method():
    out = node(r"""
import { readFileSync } from 'node:fs';
const F = await import('./site/static/js/paid/wording-stats2f.js');
const W = await import('./site/static/js/paid/wording.js');
const rep = JSON.parse(readFileSync('tests/fixtures/paid-reports-dt2/random.report.json', 'utf8'));
const run = (f) => { try { f(); return 'ok'; } catch (e) { return e.message; } };
process.stdout.write(JSON.stringify({ old: run(() => F.checkReport(rep)), now: run(() => W.checkReport(rep)),
  other: run(() => W.checkReport({ ...rep, method_version: '2026-11-30.stats4' })),
  cut: run(() => W.checkReport({ ...rep, step_cuts: [0.05, 0.2] })) }));
""")
    assert out["old"] == "wording: report method 2026-10-31.stats3a is not 2026-10-23.stats2f"
    assert out["now"] == "ok"
    assert out["other"] == "wording: report method 2026-11-30.stats4 is not 2026-10-31.stats3a (DT-2)"
    assert out["cut"] == "wording: step cuts [0.05,0.2] are not this method's [0.029,0.2] (DT-2)"


# ------------------------------------------------------------------ the engine's numbers, never typed

FORGE_JS = r"""
import { readFileSync } from 'node:fs';
const W = await import('./site/static/js/paid/wording.js');
const base = JSON.parse(readFileSync('tests/fixtures/paid-reports-dt2/stats__07-dayvol-trend_right_skew-220.report.json', 'utf8'));
const clone = () => JSON.parse(JSON.stringify(base));
const by = (r, id) => r.habits.find((h) => h.id === id);
const run = (f) => { try { return f(); } catch (e) { return 'THROW: ' + e.message; } };
const out = {};
out.ok = run(() => W.page1Lines(base));
let r = clone(); by(r, 'tilt').step = 'clear'; out.step_up = run(() => W.checkReport(r));
r = clone(); by(r, 'tilt').step = 'none'; out.step_down = run(() => W.checkReport(r));
r = clone(); by(r, 'tilt').chance_per_100 = 9; out.chance = run(() => W.checkReport(r));
r = clone(); by(r, 'tilt').effect = 3; out.direction = run(() => W.checkReport(r));
r = clone(); r.n_some = 1; out.count = run(() => W.checkReport(r));
r = clone(); r.focus = 'tilt'; out.focus = run(() => W.checkReport(r));
r = clone(); by(r, 'revenge').catch.at_least_10ths[2] = 10; out.catch = run(() => W.checkReport(r));
r = clone(); by(r, 'revenge').status = 'too_few'; out.too_few_p = run(() => W.checkReport(r));
r = clone(); by(r, 'hold_gap').status = 'tested'; out.hold = run(() => W.checkReport(r));
// the cuts, the minimum and the family are the report's: another Some cut or minimum changes the lines, not a constant
r = clone(); r.step_cuts = [0.029, 0.1]; out.some_cut = run(() => W.checkReport(r));
r = clone(); r.min_group = 7; by(r, 'revenge').status = 'too_few'; Object.assign(by(r, 'revenge'), { n_a: 6, p_raw: null, p_holm: null, p_mean1: null, p_rank1: null, step: null, chance_per_100: null, n_perm: null });
r.n_tested = 1; r.n_some = 1;
out.min7 = run(() => ({ cov: W.coverageLines(r), lines: W.habitLines(by(r, 'revenge'), r).check }));
process.stdout.write(JSON.stringify(out));
"""


def test_a_report_whose_steps_disagree_with_its_numbers_is_refused():
    o = node(FORGE_JS)
    assert o["ok"][0].startswith("Clear sign on 0 of 3 habits, some sign on 2.")
    assert o["step_up"].startswith("THROW: wording: tilt has step clear but p_holm") and o["step_down"].startswith("THROW: wording: tilt has step none")
    assert o["chance"].startswith("THROW: wording: tilt has chance 9 but p_holm")
    assert o["direction"].startswith("THROW: wording: tilt has step some but p_holm")   # Some from a gap not in the habit's way
    assert o["count"].startswith("THROW: wording: n_some 1 but 2 habits are some")
    assert o["focus"].startswith("THROW: wording: focus tilt but the Clear loss is null")
    assert o["catch"].startswith("THROW: wording: revenge has a malformed catch figure")
    assert o["too_few_p"].startswith("THROW: wording: revenge has status too_few and p_raw")
    assert o["hold"].startswith("THROW: wording: hold_gap has status tested")
    # a Some cut of 0.10 moves tilt (p_holm 0.11) to No sign, so the report's own step disagrees: refused, never reworded
    assert o["some_cut"].startswith("THROW: wording: ")
    # stats3a: the minimum is this method's 5; a report that claims this method with another minimum is refused
    assert o["min7"] == "THROW: wording: min_group 7 is not this method's 5 (DT-2)"


def test_no_step_number_is_typed_in_the_page_code():
    """The cuts, the minimums, the family size and the promises come from the report. wording.js holds this method's
    settings once, in METHOD_SETTINGS, used only to refuse a report that claims stats3a with other settings."""
    for f in ("site/static/js/paid/wording.js", "site/static/js/paid/report.js"):
        src = re.sub(r"//.*", "", open(os.path.join(REPO, f), encoding="utf-8").read())
        src = src[:src.index("const SAMPLE = ")] if "const SAMPLE = " in src else src   # VERDICT_STRINGS' sample values
        if f.endswith("wording.js"):
            block = re.search(r"export const METHOD_SETTINGS = Object\.freeze\(\{.*?\}\);", src, re.S)
            assert block and "0.029" in block.group(0) and "clear_report_and_retest: 5" in block.group(0)
            src = src.replace(block.group(0), "")
        for lit in ("0.029", "0.2,", "0.20", "min_group: 5", "at least 5 ", "at least 10 ", "all 3 ", "of 3 habits", "5 in 100", "3 in 100",
                    "20 in 100", "180", "1440"):
            assert lit not in src, (f, lit)


# ------------------------------------------------------------------ the small-file layout (addendum §3.1)

SMALL_JS = r"""
async ({ reps }) => {
  const { renderReport } = await import('/site/static/js/paid/report.js');
  const out = {};
  for (const [k, rep] of Object.entries(reps)) {
    const div = document.createElement('div');
    document.body.append(div);
    renderReport(rep, div, { uses_left: 1, retest: null });
    out[k] = { collapsed: div.querySelector('#too-few-all') ? div.querySelector('#too-few-all').textContent : null,
      sections: [...div.querySelectorAll('section.habit')].map((s) => s.id),
      reasons: [...div.querySelectorAll('.retest-reason')].map((p) => p.textContent) };
    div.remove();
  }
  return out;
}
"""


def test_small_files_collapse_too_few_habits_and_give_the_re_test_reason(browser, repo_server):
    reps = {k: load(k) for k in ("too_few", "stats__13-seq-skipped-60", "stats-r2__25-n30", "stats-r2__24-sametod", "random")}
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(repo_server + "/site/static/js/paid/")
    o = page.evaluate(SMALL_JS, {"reps": reps})
    ctx.close()
    # 20 trades, both too few: one line, no card for either
    assert o["too_few"]["collapsed"] == ("Too few trades to check: re-entering soon after a loss (0 trades soon after a loss, 19 others; the check "
                                         "needs 5 of each); trading after a losing streak (0 trades after 2 or more losses in a row, 19 others; "
                                         "the check needs 5 of each).")
    assert "habit-revenge" not in o["too_few"]["sections"] and "habit-tilt" not in o["too_few"]["sections"]
    # 60 trades: revenge too few (collapsed), tilt No sign with its re-test reason from the catch line
    assert o["stats__13-seq-skipped-60"]["collapsed"].startswith("Too few trades to check: re-entering soon after a loss (0 trades soon after")
    assert "habit-tilt" in o["stats__13-seq-skipped-60"]["sections"]
    assert o["stats__13-seq-skipped-60"]["reasons"] == ["For your re-test: when trades after 2 or more losses in a row end $6.30 worse each, files of "
                                                        "120 trades show it as a Clear sign at least 3 in 10 times, and 240 trades show it as a "
                                                        "Clear sign at least 4 in 10 times."]
    # 30 trades, both checked, No sign: nothing to collapse, a reason per habit
    assert o["stats-r2__25-n30"]["collapsed"] is None and len(o["stats-r2__25-n30"]["reasons"]) == 2
    # 63 trades: revenge too few, tilt checked (chance 63 in 100: No sign)
    assert o["stats-r2__24-sametod"]["collapsed"] and o["stats-r2__24-sametod"]["reasons"][0].endswith("at least 3 in 10 times.")
    # 400 trades: the full layout (every habit its own card, no re-test reason)
    assert o["random"]["collapsed"] is None and o["random"]["reasons"] == [] and "habit-revenge" in o["random"]["sections"]


# ------------------------------------------------------------------ the example report is the engine's, nothing re-picked

def test_the_example_report_is_dt2_and_its_steps_are_the_engines():
    rep = json.load(open(os.path.join(REPO, "site/config/sample-report.report.json"), encoding="utf-8"))
    assert rep["method_version"] == "2026-10-31.stats3a" and rep["method_label"] == "DT-2"
    # 31 Oct (buyer read-through): the built re-entry habit wins 20% of the time (was 25%), enough for a Clear sign under
    # DT-2; tilt is whatever the engine gives
    st = {h["id"]: (h["step"], h["chance_per_100"]) for h in rep["habits"]}
    assert st == {"hold_gap": (None, None), "revenge": ("clear", 2), "size_up": (None, None), "tilt": ("none", 100), "oversized_loss": (None, None)}
    assert rep["focus"] == "revenge" and rep["n_clear"] == 1 and rep["n_some"] == 0 and rep["n_trades"] == 304


# ------------------------------------------------------------------ stats3a (calibration fixes items 2, 4, 8)

STATS3A_JS = r"""
import { readFileSync } from 'node:fs';
const W = await import('./site/static/js/paid/wording.js');
const base = JSON.parse(readFileSync('tests/fixtures/paid-reports-dt2/stats__07-dayvol-trend_right_skew-220.report.json', 'utf8'));
const clone = () => JSON.parse(JSON.stringify(base));
const by = (r, id) => r.habits.find((h) => h.id === id);
const run = (f) => { try { return f(); } catch (e) { return 'THROW: ' + e.message; } };
const out = { table: {} };
// item 8: the shown number for each adjusted p, through the page's own check (tilt, smaller group 103)
for (const p of [0.0096, 0.0288, 0.0297, 0.04, 0.0501, 0.2]) {
  const r = clone(); const h = by(r, 'tilt');
  const step = p <= 0.029 ? 'clear' : 'some';
  Object.assign(h, { p_holm: p, p_raw: p / 3, p_mean1: p / 3, step, chance_per_100: W.chancePer100(p, step, r.promise_per_100), chance_below_1: step === 'clear' && p < 0.01 });
  r.n_clear = r.habits.filter((x) => x.step === 'clear').length; r.n_some = r.habits.filter((x) => x.step === 'some').length;
  r.focus = step === 'clear' ? 'tilt' : null;
  out.table[p] = run(() => W.habitLines(h, r).check[0]);
}
// a Some step with a smaller group of 5-9 is refused, whatever its numbers
let r = clone(); Object.assign(by(r, 'revenge'), { n_a: 8, small_group: true }); out.small_some = run(() => W.checkReport(r));
r = clone(); by(r, 'revenge').small_group = true; out.small_flag = run(() => W.checkReport(r));
r = clone(); by(r, 'tilt').chance_per_100 = 3; out.some_three = run(() => W.checkReport(r));
// every settings field is this method's, or the report is refused
for (const [k, v] of [['min_group', 10], ['some_min_group', 5], ['n_family', 2], ['step_cuts', [0.05, 0.2]],
  ['promise_per_100', { clear_run: 3, clear_report_and_retest: 8, some_run: 20 }], ['blocks', { rule: 'day' }]]) {
  r = clone(); r[k] = v; out['set_' + k] = run(() => W.checkReport(r));
}
r = clone(); r.method_version = '2026-10-30.stats3'; out.stats3 = run(() => W.checkReport(r));
// catch reasons: each has its line; a reason with a figure, or a figure missing its reason, is refused
for (const why of W.CATCH_REASONS) out['why_' + why] = W.catchReasonLine(why, '5,000');
r = clone(); by(r, 'tilt').catch = null; by(r, 'tilt').catch_reason = 'same_result';
out.same = run(() => W.habitLines(by(r, 'tilt'), r).check);
r = clone(); by(r, 'tilt').catch_reason = 'off'; out.both = run(() => W.checkReport(r));
r = clone(); by(r, 'tilt').catch = null; out.neither = run(() => W.checkReport(r));
r = clone(); by(r, 'tilt').catch = null; by(r, 'tilt').catch_reason = 'over_limit'; out.over_small = run(() => W.checkReport(r));
// the clock guard in "How this was measured"
r = clone(); r.blocks.clock_guard = true;
out.guard_on = W.methodLine(by(r, 'tilt'), undefined, r); out.guard_off = W.methodLine(by(base, 'tilt'), undefined, base);
process.stdout.write(JSON.stringify(out));
"""


def test_stats3a_numbers_small_groups_catch_reasons_and_the_clock_guard():
    o = node(STATS3A_JS)
    t = o["table"]
    # Clear always shows at most 3 in 100 (fewer than 1 below 0.01); Some always at least 4
    assert "turns up fewer than 1 in 100 times" in t["0.0096"] and t["0.0096"].startswith("Clear sign")
    assert "at most 3 in 100 times" in t["0.0288"] and t["0.0288"].startswith("Clear sign")
    assert "at most 4 in 100 times" in t["0.0297"] and t["0.0297"].startswith("Some sign")
    assert "at most 4 in 100 times" in t["0.04"] and "at most 6 in 100 times" in t["0.0501"] and "at most 20 in 100 times" in t["0.2"]
    for p, line in t.items():
        n = int(re.search(r"at most (\d+) in 100|fewer than (1) in 100", line).group(1) or 1)
        assert (n <= 3) == line.startswith("Clear sign"), (p, line)
    assert o["small_some"].startswith("THROW: wording: revenge has step some but") or "smaller group" in o["small_some"], o["small_some"]
    assert o["small_flag"].startswith("THROW: wording: revenge has small_group true")
    assert o["some_three"].startswith("THROW: wording: tilt has chance 3")
    for k in ("min_group", "some_min_group", "n_family", "step_cuts", "promise_per_100", "blocks"):
        assert o["set_" + k].startswith("THROW: wording: "), (k, o["set_" + k])
    assert o["stats3"] == "THROW: wording: report method 2026-10-30.stats3 is not 2026-10-31.stats3a (DT-2)"
    assert o["why_same_result"] == "No catch figure: every trade in this file has the same result."
    assert o["why_over_limit"] == "No catch figure: files over 5,000 trades get none."
    assert o["why_dates_only"] == "No catch figure: this file has dates but no times of day."
    assert o["why_no_trades"] == "No catch figure: this file has no trades to build one from."
    assert o["why_off"] == "No catch figure: this report was made without one."
    for k in ("why_same_result", "why_over_limit", "why_dates_only", "why_no_trades", "why_off"):
        assert L.verdict_hedge_hits(o[k], k) == [] and L.lint_text(o[k], k, paid=True) == []
    assert o["same"][-1] == "No catch figure: every trade in this file has the same result."
    assert o["both"].startswith("THROW: wording: tilt has a catch figure and the reason off")
    assert o["neither"].startswith("THROW: wording: tilt has no catch figure and the reason null")
    assert o["over_small"].startswith("THROW: wording: tilt has the catch reason over_limit on 220 trades")
    assert ("In this file, wins and losses differ sharply by time of day, so each trade was also kept within its 2-hour band of the "
            "clock when the results were reshuffled.") in o["guard_on"]
    assert "time of day" not in o["guard_off"] and "A session ends at a gap of 3 hours or more between opens and lasts at most 24 hours." in o["guard_off"]
