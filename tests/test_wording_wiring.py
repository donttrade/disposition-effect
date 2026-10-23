"""The statistics amendment's wording, wired into the pages (CODER-WIRING-REPORT-2026-10-21).

* /report/: renderReport() (report.js) shows the R2 §9.1-9.2 sentences from wording.js
  (ARCHITECT-STATS-AMENDMENT-R2; method 2026-10-23.stats2c since ruling R-D3, so hold_gap is always
  withheld / not_calibrated and shows M1, V-launch and M3, and size_up is always withheld / not_calibrated
  and shows M1 and V-launch-size): the page-1 headline, the focus line or N0 with one reason line per
  distinguishable habit, the coverage lines (2 habits, plus the fixed hold-gap and size-up lines); each
  tested habit's lines; the method line with the habit's OWN n_perm (D-4).
  No fixed "10,000 shuffles" or "testing four habits" claim is left.
* /tools/trade-stats/: a guarded expectancy check shows the §7.2 sentence; the D-9 footnote
  is under the three checks; the method text says the mean result is resampled.
* The whole build (pages, JSON-LD, scripts) carries none of the old method claims.
"""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
import lint as L  # noqa: E402

# Free-launch condition C1: the badges are off by default (site.toml free_badges = false). These
# tests are about the badges, so this module runs on the badges build (conftest.badges_site);
# tests/test_free_badges.py covers the default build.
@pytest.fixture(scope="session")
def built_site(badges_site):
    return badges_site


GUARD = json.load(open(os.path.join(HERE, "fixtures", "noise", "guard_vectors.json"), encoding="utf-8"))

# Synthetic Reports with the server's field names (dt-private tests/fixtures/expected/*.report.json).
RENDER_JS = r"""
async (cases) => {
  const { renderReport } = await import('/site/static/js/paid/report.js');
  const names = { hold_gap: 'Holding losers longer than winners', revenge: 'Re-entering soon after a loss',
    size_up: 'Size after a loss', tilt: 'Trading after a losing streak', oversized_loss: 'Losses much larger than your usual loss' };
  const labels = { hold_gap: 'Losing trades held longer than your median winning hold', revenge: "Trades opened within 15 minutes of a losing trade's close",
    size_up: 'Trades after a loss at 1.5 times your usual size or more', tilt: 'Trades taken after 2 or more losses in a row',
    oversized_loss: 'Losses more than twice your median loss' };
  const MED = ['hold_gap', 'size_up'];
  const H = (id, nMed, nSeq, o) => ({ id, name: names[id], question: 'Q ' + id + '?', n_a: 40, n_b: 90,
    measure_a: id === 'hold_gap' ? 5400 : id === 'size_up' ? 1.6 : -12.5, measure_b: id === 'hold_gap' ? 1800 : id === 'size_up' ? 1.0 : 3.25,
    effect: id === 'hold_gap' ? 3 : id === 'size_up' ? 1.6 : -15.75, p_raw: 0.0004, p_holm: 0.0016, verdict: 'distinguishable', direction: 'habit',
    method: id === 'hold_gap' ? 'earlier comparable trades (symbol, holding period, direction, time of day)'
      : id === 'size_up' ? 'local rank (symbol, holding period, direction, time of day)' : 'within-day sequence shuffle (mean and rank)',
    n_perm: MED.includes(id) ? nMed : nSeq, n_a_compared: MED.includes(id) ? 38 : null, n_b_compared: MED.includes(id) ? 85 : null,
    ...(id === 'hold_gap' ? { verdict: 'withheld', withheld: 'not_calibrated', p_raw: null, p_holm: null, n_perm: null, direction: null,
      share_a: null, share_b: null, n_a_compared: null, n_b_compared: null, spread_ratio: null, n_long_a: 0, n_long_b: 0 } : {}),
    ...(id === 'size_up' ? { verdict: 'withheld', withheld: 'not_calibrated', p_raw: null, p_holm: null, n_perm: null, direction: null,
      share: null, n_a_compared: null, n_b_compared: null } : {}), ...(id === 'revenge' || id === 'tilt' ? { p_mean: 0.0004, p_rank: 0.0003 } : {}),
    detail: id === 'tilt' ? { streak3_n: 12, streak3_mean: -20 } : null, research_ref: null,
    dollars: { label: labels[id], amount: -500, n_trades: 40 }, ...o });
  const OVR = { id: 'oversized_loss', name: names.oversized_loss, question: 'Q?', n_a: 10, n_b: null, measure_a: 0.05, measure_b: 0.3,
    effect: -40, p_raw: null, p_holm: null, verdict: 'descriptive', direction: null, method: null, n_perm: null,
    n_a_compared: null, n_b_compared: null, detail: null, research_ref: null, dollars: { label: labels.oversized_loss, amount: -900, n_trades: 10 } };
  const all = ['hold_gap', 'revenge', 'size_up', 'tilt'];
  const R = (c) => {
    const habits = all.map((id) => H(id, c.nMed, c.nSeq, (c.over || {})[id] || {})).concat([OVR]);
    return { v: 1, currency: 'USD', disclaimer: 'donttrade measures your own past trades. It is not investment advice, does not recommend any security, trade, size or exit, and is not registered as an adviser. Past results do not predict future results.',
      engine_commit: 'test', rule_library_version: 'test', rule_library: ['Rule one.', 'Rule two.'], method_version: '2026-10-23.stats2c',
      n_trades: c.n, period_weeks: 10, pgr_plr: null, focus: c.focus,
      n_tested: habits.filter((h) => h.p_raw !== null).length, n_distinguishable: habits.filter((h) => h.verdict === 'distinguishable').length, habits };
  };
  const out = {};
  for (const [k, c] of Object.entries(cases)) {
    const div = document.createElement('div');
    document.body.append(div);
    renderReport(R(c), div, {});
    const sec = (id) => (div.querySelector('#' + id) || { innerText: '' }).innerText;
    out[k] = { text: div.innerText, page1: sec('focus'), coverage: sec('coverage'),
      habit: Object.fromEntries(all.concat(['oversized_loss']).map((id) => [id, sec('habit-' + id)])),
      method: [...div.querySelectorAll('.habit-method')].map((p) => p.textContent) };
    div.remove();
  }
  return out;
}
"""

ND = {"verdict": "not_distinguishable", "p_raw": 0.4, "p_holm": 1.0}
TF = {"verdict": "too_few", "p_raw": None, "p_holm": None, "n_perm": None, "n_a": 12}
# hold_gap (R-D2) and size_up (R-D3) are withheld / not_calibrated in every case (stats2c)
CASES = {
    # 20,000 rows: N_MED = 5,000 and N_SEQ = 2,000 (D-4)
    "big_focus": {"n": 20000, "nMed": 5000, "nSeq": 2000, "focus": "revenge",
                  "over": {"tilt": ND}},
    # 6,000 rows: N_MED = 10,000, N_SEQ = floor(40,000,000 / 6,000) = 6,666
    "mid_opposite": {"n": 6000, "nMed": 10000, "nSeq": 6666, "focus": None,
                     "over": {"tilt": {"direction": "opposite", "effect": 4}, "revenge": ND}},
    "too_few": {"n": 300, "nMed": 10000, "nSeq": 10000, "focus": None,
                "over": {"revenge": TF, "tilt": ND}},
    # PLAN CONFLICT §7.1: revenge distinguishable in its own direction, but its trades totalled a gain
    "own_gain": {"n": 300, "nMed": 10000, "nSeq": 10000, "focus": None,
                 "over": {"revenge": {"dollars": {"label": "Trades opened within 15 minutes of a losing trade's close",
                                                  "amount": 120, "n_trades": 40}},
                          "tilt": ND}},
    "none": {"n": 300, "nMed": 10000, "nSeq": 10000, "focus": None,
             "over": {k: ND for k in ("revenge", "tilt")}},
    # R-D2: hold_gap described, with trades held 12 hours or more (M3)
    "launch_m3": {"n": 300, "nMed": 10000, "nSeq": 10000, "focus": None,
                  "over": {"hold_gap": {"n_long_a": 2, "n_long_b": 1}, "revenge": ND, "tilt": ND}},
}
V_LAUNCH = ("Not tested in this version of the report. In our tests on files built to have no real pattern, this test reported "
            "a gap in more than 1 file in 20, the rate it is designed for, when a large win or loss changed how long the next "
            "trades were held. So this pattern is described here without a verdict.")
HG_LINE = "Holding losers longer than winners is described, not tested, in this version of the report."
V_LAUNCH_SIZE = ("Not tested in this version of the report. In our tests on files built to have no real pattern, this test "
                 "reported a gap in more than 1 file in 20, the rate it is designed for, in files that mix several symbols whose "
                 "sizes and results both follow the time of day. So this pattern is described here without a verdict.")
SU_LINE = "Size after a loss is described, not tested, in this version of the report."
STALE = ["10,000 shuffles", "Holm correction for testing four", "testing four habits", "Permutation test on past data"]


@pytest.fixture(scope="module")
def rendered(browser, repo_server):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/site/static/js/paid/")
    out = page.evaluate(RENDER_JS, CASES)
    ctx.close()
    assert errors == []
    return out


def test_method_line_carries_the_scaled_permutation_counts(rendered):
    big = rendered["big_focus"]
    assert ("The results were reshuffled within each day 2,000 times (days with a single trade are grouped with nearby such "
            "days).") in big["method"][0]
    assert big["method"][1].startswith("Compared with your other trades from the same day. The results were reshuffled within each day 2,000 times")
    assert len(big["method"]) == 2          # hold_gap (R-D2) and size_up (R-D3) are not tested: no method line
    assert all("after adjusting for the 2 patterns tested (Holm)" in m for m in big["method"])
    assert not any("each trade's hold is first ranked" in m or "each trade's size is first ranked" in m
                   for case in rendered.values() for m in case["method"])
    mid = rendered["mid_opposite"]["method"]
    assert "6,666 times" in mid[0] and "6,666 times" in mid[1]
    for case in rendered.values():
        for s in STALE:
            assert s not in case["text"], s
    # too_few and withheld habits have no method line (no test ran)
    assert len(rendered["too_few"]["method"]) == 1
    assert len(rendered["launch_m3"]["method"]) == 2


def test_page_one_uses_the_amendment_lines(rendered):
    p1 = rendered["big_focus"]["page1"]
    assert ("1 of the 2 patterns tested in this file is distinguishable from noise. Each verdict is adjusted for testing 2 "
            "patterns at once. In our tests on files built to have no real pattern, at least one pattern showed as "
            "distinguishable in about 1 report in 20 or fewer.") in p1
    assert ("Shown first: Re-entering soon after a loss. Trades opened within 15 minutes of a losing trade's close totalled "
            "−$500.00 (historical).") in p1
    assert [x for x in rendered["big_focus"]["coverage"].splitlines() if x.strip()] == [
        "2 of the 2 habits could be tested. Each one compares two groups of at least 30 trades.", HG_LINE, SU_LINE]
    for k, case in rendered.items():        # every stats2c page 1 carries the fixed hold-gap and size-up lines once each
        assert case["page1"].count(HG_LINE) == 1 and case["page1"].count(SU_LINE) == 1, k
    # the old page said "No pattern ... distinguishable" whenever focus was null: false here
    opp = rendered["mid_opposite"]["page1"]
    assert "No pattern in this file is distinguishable from noise." not in opp
    assert "No pattern is shown first. A pattern is shown first only when its gap is distinguishable from noise" in opp
    assert ("Trading after a losing streak: trades taken after 2 or more losses in a row did better than your other trades, "
            "the other way round from the pattern's name.") in opp
    own = rendered["own_gain"]["page1"]      # R2 §9.1 N-gain (replaces the pending NO_LOSS_ONE)
    assert ("Re-entering soon after a loss: trades opened within 15 minutes of a losing trade's close did worse than your "
            "other trades, but its dollar figure (trades opened within 15 minutes of a losing trade's close) totalled +$120.00 "
            "(historical), which is not a loss.") in own
    assert "No pattern in this file is distinguishable" not in own and "did not total a loss" not in own
    none = rendered["none"]["page1"]
    assert "No pattern in this file is distinguishable from noise." in none
    assert "That does not show the patterns are absent; it means this file cannot tell them apart from chance." in none
    assert "Not tested: Re-entering soon after a loss." in rendered["too_few"]["coverage"]
    assert "1 of the 2 habits could be tested." in rendered["too_few"]["coverage"]
    assert "Size after a loss" not in rendered["too_few"]["coverage"].replace(SU_LINE, "")


def test_each_habit_shows_its_sentences(rendered):
    h = rendered["big_focus"]["habit"]
    assert "Trades opened within 15 minutes of a losing trade's close averaged −$12.50 per trade; your other trades averaged +$3.25." in h["revenge"]
    assert "This gap is distinguishable from noise, after adjusting for the 2 patterns tested." in h["revenge"]
    assert "Your losing trades were held a median of 1h 30m; your winning trades a median of 30m 0s." in h["hold_gap"]
    assert V_LAUNCH in h["hold_gap"] and "not tested" in h["hold_gap"]                 # badge and V-launch
    assert "Compared with similar trades opened just before it" not in h["hold_gap"]    # no M2 (R-D2)
    assert "distinguishable from noise" not in h["hold_gap"] and "Held 12 hours" not in h["hold_gap"]
    assert "Losing trades held longer than your median winning hold: 40 trades, totalling" in h["hold_gap"]   # dollars stay
    # R-D3: size_up shows M1, the "not tested" badge, V-launch-size and its dollar figure; no M2, no verdict
    assert "Your median size after a loss was 1.60× your median size after a win." in h["size_up"]
    assert V_LAUNCH_SIZE in h["size_up"] and "not tested" in h["size_up"]
    assert h["size_up"].index("median size after a loss was") < h["size_up"].index(V_LAUNCH_SIZE)
    assert "size rank" not in h["size_up"] and "distinguishable from noise" not in h["size_up"] and "reshuffled" not in h["size_up"]
    assert "Trades after a loss at 1.5 times your usual size or more: 40 trades, totalling" in h["size_up"]   # dollars stay
    assert "Losers were held 3.00 times as long as winners." not in h["hold_gap"]      # shown only when tested
    assert "After 3 or more losses in a row: 12 trades" in h["tilt"]
    assert "Share of all loss dollars: 30.0%" in h["oversized_loss"]                   # descriptive habit unchanged
    assert "Not tested" not in h["oversized_loss"] and "reshuffled" not in h["oversized_loss"]
    t = rendered["mid_opposite"]["habit"]["tilt"]
    assert "It runs the opposite way to this pattern's name." in t
    tf = rendered["too_few"]["habit"]
    assert ("Not enough trades to tell: this pattern compares two groups of at least 30 trades each, and this file has 12 "
            "and 90.") in tf["revenge"]
    assert "Not enough trades to tell" not in tf["size_up"] and V_LAUNCH_SIZE in tf["size_up"]
    assert "averaged" not in tf["revenge"]                                             # the too_few sentence replaces both
    w = rendered["launch_m3"]["habit"]["hold_gap"]
    assert V_LAUNCH in w and "Held 12 hours or more: 2 of your 40 losing trades and 1 of your 90 winning trades." in w
    assert w.index("held a median of") < w.index(V_LAUNCH) < w.index("Held 12 hours or more")   # M1, V-launch, M3
    assert "Losers were held" not in w and "reshuffled" not in w                       # no test ran: no ratio line, no method line
    assert "Not tested: Holding losers" not in rendered["launch_m3"]["coverage"] and HG_LINE in rendered["launch_m3"]["coverage"]


def test_rendered_report_text_passes_the_paid_lint(rendered):
    for k, case in rendered.items():
        assert L.lint_text(case["text"], k, paid=True) == [], k
        for bad in ("NaN", "Infinity", "undefined", "null"):
            assert bad not in case["text"], (k, bad)


# ------------------------------------------------------------------ free dashboard

def roundtrip_csv(pnls, path):
    """A round-trip CSV whose trades have exactly these P&Ls (qty 1, one per hour, held 10 min)."""
    lines = ["Open Time,Close Time,Symbol,Direction,Volume,Open Price,Close Price,Currency"]
    for i, p in enumerate(pnls):
        day, hour = divmod(i, 8)
        d = f"2026-{9 + day // 28:02d}-{1 + day % 28:02d}"
        lines.append(f"{d} {9 + hour:02d}:00:00,{d} {9 + hour:02d}:10:00,SPY,Long,1,1000.00,{1000 + p:.2f},USD")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


def free_page(browser, built_site, csv):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + "/tools/trade-stats/")
    page.set_input_files("#ts-file", csv)
    page.wait_for_selector("#ts-noise table", timeout=90000)
    return ctx, page


@pytest.mark.parametrize("i", [1, 32])
def test_free_page_shows_the_guard_sentence_and_footnote(browser, built_site, tmp_path, i):
    exp = GUARD["expected"][i]
    ctx, page = free_page(browser, built_site, roundtrip_csv(GUARD["vectors"][i], tmp_path / f"g{i}.csv"))
    row = page.inner_text('#ts-noise tr[data-check="expectancy"]')
    guard = page.locator("#ts-noise .ts-guard").all_inner_texts()
    foot = page.inner_text("#ts-noise-footnote")
    text = page.inner_text("#ts-noise")
    ctx.close()
    assert "not enough trades to tell" in row
    assert len(guard) == 1 and guard[0].startswith("Not enough trades to tell. ")
    if exp["guard"] == "skew_small_n":
        assert f"this check waits for at least {exp['n_needed']} trades" in guard[0]
    else:
        assert "With one more trade the size of this file's largest loss (−$147.76)" in guard[0]
    assert foot.startswith("Each check is run on its own.") and "up to about 1 file in 7 in our tests." in foot
    assert "resampled for the mean result" in text and "share of shuffles" not in text
    assert L.lint_text(text, "free-guard") == []


def test_free_page_without_a_guard_has_the_footnote_only(browser, built_site):
    ctx, page = free_page(browser, built_site, os.path.join(HERE, "fixtures", "generic", "ninety_trades.csv"))
    n_guard = page.locator("#ts-noise .ts-guard").count()
    foot = page.inner_text("#ts-noise-footnote")
    ctx.close()
    assert n_guard == 0 and foot.startswith("Each check is run on its own.")


# ------------------------------------------------------------------ the build as a whole

# R-D2 H-3: the "four tested" claims are stale too (hold_gap is described, not tested, under stats2b).
STALE_BUILD = ["10,000 shuffles", "shuffles your own trades", "Holm correction for testing four", "tests five habits",
               "random signs", "shuffled copies of your own trades", "share of shuffles", "“may be noise”, or",
               "tests up to four", "of the 4 patterns", "jusqu’à quatre", "tests four of them"]


def test_no_stale_method_claim_anywhere_in_the_build(built_site):
    hits = []
    for root, _, files in os.walk(built_site["out"]):
        if os.sep + "research" + os.sep in root + os.sep:   # passthrough research ledgers (v1 docs/)
            continue
        for n in files:
            if not n.endswith((".html", ".js", ".json", ".xml", ".txt")):
                continue
            s = open(os.path.join(root, n), encoding="utf-8", errors="replace").read()
            hits += [(os.path.relpath(os.path.join(root, n), built_site["out"]), p) for p in STALE_BUILD if p in s]
    assert hits == []


def test_trade_stats_faq_jsonld_matches_the_new_method_text(built_site):
    h = (built_site["out"] / "tools" / "trade-stats" / "index.html").read_text(encoding="utf-8")
    blocks = [json.loads(b.replace("<\\/", "</")) for b in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S)]
    faq = [n for b in blocks for n in b.get("@graph", [b]) if n.get("@type") == "FAQPage"]
    assert faq, "no FAQPage JSON-LD"
    ans = {q["name"]: q["acceptedAnswer"]["text"] for q in faq[0]["mainEntity"]}
    a = ans["What does the real-or-noise result mean?"]
    assert "shuffled for the hold-time and streak checks and resampled for the mean result" in a
    assert "a few very large trades make up most of a short file" in a
