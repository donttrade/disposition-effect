"""The two old calculators' code fixes (21 Oct 2026): numbers read with the engine's rule, and
no box marked wrong before it has been typed in, left, or the form submitted.

  * numbers.js gives the same value as the engine (static/js/engine/csv.js resolveNumberStyle +
    parseNumber) for every input the engine accepts, and refuses every input it refuses; the only
    difference is the documented one for typed input: a space must group thousands ("4 2" refused).
  * "1,5" never becomes 15: it reads as 1.5, which is not a count, and says so next to the box.
  * "1,780" (one comma, 3 digits) and a lone "1.780" are ambiguous for the engine; the calculators'
    boxes take whole numbers only (readForm whole mode), where they can only mean 1780 (NIT N3).
  * first load: no aria-invalid, no visible message, in light and dark.
  * the v1 worked examples give the same figures (also in test_oldpages).
"""
import json
import os
import subprocess

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NUMBERS = os.path.join(REPO, "site", "static", "js", "legacy", "numbers.js")
ENGINE = os.path.join(REPO, "site", "static", "js", "engine", "csv.js")

SINGLE = ["", "0", "7", "1780", "-3", "+4", "12,5", "1,5", "0,25", "1,780", "12,780", "1,234,567", "1,234.5",
          "1.234,5", "1.234.567", "1.500", "0.125", "12.5", "1.5", ".5", "1,0,0", "1,,5", "abc", "1e3", "1 780",
          "1 780", "1 780", " 42 ", "4 2", "12 34", "1 780,5", "1 780.5", "−5", "1.2.3", "1,2.3",
          "Infinity", "NaN", "0x10", "1_000", "12,50", "1.000.000,25", "999,999,999"]
FORMS = [["1.500", "12,5"], ["1.500", "12.5"], ["1.500", "7"], ["1.500", "1.234.567"], ["1.500", "1,234,567"],
         ["12,5", "12.5"], ["12.5", "12,5"], ["1,780", "1.234.567"], ["420", "1780", "260", "2240"],
         ["420", "1,780", "260", "2,240"], ["1 000", "150", "170", "40", ""]]

PARITY = r"""
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
const [numbersPath, enginePath, casesJson] = process.argv.slice(1);   // node -e: no script path
const N = createRequire(import.meta.url)(numbersPath);
const E = await import(pathToFileURL(enginePath).href);
function engine(raws) {
  const rows = raws.map((x, i) => ({ row: i + 1, cells: [x] }));
  try {
    E.resolveNumberStyle([{ rows, map: { v: 0 }, fields: ['v'] }], null);
    return rows.map(r => { try { return { ok: true, value: E.parseNumber(r.cells[0], r.row, 'v') }; }
                           catch (e) { return { ok: false, code: e.code }; } });
  } catch (e) { return { file: e.code }; }
}
const out = [];
for (const raws of JSON.parse(casesJson)) out.push({ raws, engine: engine(raws), ours: N.readForm(raws) });
console.log(JSON.stringify(out));
"""


def _parity(cases):
    r = subprocess.run(["node", "--input-type=module", "-e", PARITY, NUMBERS, ENGINE, json.dumps(cases)],
                       capture_output=True, text=True, timeout=60)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def _spaced_badly(raw):
    import re
    t = raw.strip("   ")
    return bool(re.search(r"[   ]", t)) and not re.fullmatch(r"[+\-−]?\d{1,3}([   ]\d{3})+([.,]\d+)?", t)


def test_numbers_js_matches_the_engine_one_box_at_a_time():
    for case in _parity([[x] for x in SINGLE]):
        raw, ours = case["raws"][0], case["ours"][0]
        eng = case["engine"]
        if _spaced_badly(raw):
            assert ours == {"ok": False, "why": "space"}, (raw, ours)
            continue
        eng_ok = "file" not in eng and eng[0]["ok"]
        assert ours["ok"] == eng_ok, (raw, ours, eng)
        if eng_ok:
            assert ours["value"] == eng[0]["value"], (raw, ours, eng)


def test_numbers_js_matches_the_engine_across_a_form():
    for case in _parity(FORMS):
        raws, ours, eng = case["raws"], case["ours"], case["engine"]
        if "file" in eng:   # the engine refuses the whole file: at least one box is refused here
            assert any(not o["ok"] for o in ours), (raws, ours, eng)
            continue
        for raw, o, e in zip(raws, ours, eng):
            if _spaced_badly(raw):
                continue
            assert o["ok"] == e["ok"], (raws, o, e)
            if e["ok"]:
                assert o["value"] == e["value"], (raws, o, e)


def test_the_cases_that_matter():
    got = {c["raws"][0]: c["ours"][0] for c in _parity([[x] for x in ("1,5", "1,780", "1.780", "4 2", "1,0,0", "1 780")])}
    assert got["1,5"] == {"ok": True, "value": 1.5, "decimalComma": True}       # never 15
    assert got["1,780"] == {"ok": False, "why": "ambiguous_comma"}
    assert got["1.780"] == {"ok": False, "why": "ambiguous_dot"}
    assert got["4 2"] == {"ok": False, "why": "space"}
    assert got["1,0,0"] == {"ok": False, "why": "not_number"}
    assert got["1 780"]["value"] == 1780
    form = _parity([["1.500", "1.234.567"], ["1.500", "1,234,567"]])
    assert [o.get("value") for o in form[0]["ours"]] == [1500, 1234567]      # dots group thousands here
    assert [o.get("value") for o in form[1]["ours"]] == [1.5, 1234567]       # here the dot is a decimal point


# ------------------------------------------------------------------ in the browser, on the built pages
DC = "/tools/disposition-calculator/"
PR = "/tools/pass-rate-calculator/"
DC_IDS = ["#dc-rg", "#dc-pg", "#dc-rl", "#dc-pl"]
PR_IDS = ["#pr-started", "#pr-open", "#pr-passed", "#pr-paid", "#pr-traders"]


@pytest.fixture
def page(browser, built_site):
    ctx = browser.new_context(viewport={"width": 375, "height": 900})
    p = ctx.new_page()
    p.errors = []
    p.on("pageerror", lambda e: p.errors.append(str(e)))
    p.base = built_site["url"]
    yield p
    assert p.errors == []
    ctx.close()


def _state(p, ids):
    return p.evaluate("""ids => ids.map(s => { const el = document.querySelector(s), e = document.getElementById(el.id + '-err');
        return [el.getAttribute('aria-invalid'), e && !e.hidden ? e.textContent : ''] })""", ids)


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("path,ids,msg", [(DC, DC_IDS, "#dc-msg"), (PR, PR_IDS, "#pr-msg")])
def test_first_load_marks_nothing(browser, built_site, path, ids, msg, scheme):
    ctx = browser.new_context(viewport={"width": 375, "height": 900}, color_scheme=scheme)
    p = ctx.new_page()
    p.goto(built_site["url"] + path)
    p.wait_for_load_state("networkidle")
    assert all(s == [None, ""] for s in _state(p, ids)), _state(p, ids)
    assert p.inner_text(msg) == "" and not p.is_visible(msg)
    assert p.locator(".error:visible").count() == 0
    ctx.close()


def test_one_comma_five_is_refused_next_to_its_box_never_read_as_15(page):
    page.goto(page.base + DC)
    for sel, v in zip(DC_IDS, ["1,5", "10", "2", "10"]):
        page.fill(sel, v)
    assert page.evaluate("document.getElementById('dc-results').hidden")
    st = _state(page, DC_IDS)
    assert st[0][0] == "true" and "decimal" in st[0][1] and "whole numbers" in st[0][1], st
    assert all(s == [None, ""] for s in st[1:]), st
    assert "Realised gains" in page.inner_text("#dc-msg")
    assert page.get_attribute("#dc-rg", "aria-describedby").split() == ["dc-rg-err", "dc-msg"]


@pytest.mark.parametrize("raw,word", [("4 2", "space"), ("1,0,0", "not a number"), ("1,2.3", "not a number"),
                                      ("-3", "negative"), ("-1,780", "negative"), ("1000000000001", "too large")])
def test_ambiguous_or_wrong_input_gets_a_clear_message(page, raw, word):
    page.goto(page.base + DC)
    for sel, v in zip(DC_IDS, [raw, "10", "2", "10"]):
        page.fill(sel, v)
    assert page.evaluate("document.getElementById('dc-results').hidden"), raw
    assert word in _state(page, DC_IDS)[0][1], (raw, _state(page, DC_IDS))


# "1,780" / "1.780": ambiguous in general (the engine refuses them), but these boxes take whole
# numbers only, so 1780 is the only reading (launch NIT N3; the page's example is "1,780").
@pytest.mark.parametrize("raw", ["1780", "1 780", "1,234,567", "1.234.567", "1,780", "1.780"])
def test_unambiguous_thousands_are_read(page, raw):
    page.goto(page.base + DC)
    for sel, v in zip(DC_IDS, ["420", raw, "260", "2240"]):
        page.fill(sel, v)
    assert not page.evaluate("document.getElementById('dc-results').hidden"), raw
    want = int(raw.replace(",", "").replace(".", "").replace(" ", ""))
    assert page.inner_text("#dc-pgr") == f"{420 / (420 + want):.4f}"


def test_a_dot_is_decided_by_the_other_boxes(page):
    page.goto(page.base + DC)
    for sel, v in zip(DC_IDS, ["1.500", "1.234.567", "2", "10"]):   # dots group thousands elsewhere → 1500
        page.fill(sel, v)
    assert page.inner_text("#dc-pgr") == f"{1500 / (1500 + 1234567):.4f}"
    page.fill("#dc-pg", "1,234,567")                                # now the dot is a decimal point → 1.5
    assert page.evaluate("document.getElementById('dc-results').hidden")
    assert "decimals" in _state(page, DC_IDS)[0][1]


def test_typing_in_one_box_does_not_mark_the_empty_others(page):
    page.goto(page.base + DC)
    page.fill("#dc-rg", "420")
    assert all(s == [None, ""] for s in _state(page, DC_IDS)), _state(page, DC_IDS)
    page.focus("#dc-pg")
    page.keyboard.press("Tab")        # left empty: now it is checked
    st = _state(page, DC_IDS)
    assert st[1][0] == "true" and "empty" in st[1][1] and st[2] == [None, ""] and st[3] == [None, ""], st


@pytest.mark.parametrize("path,ids", [(DC, DC_IDS), (PR, PR_IDS)])
def test_submit_checks_every_box_and_clear_resets(page, path, ids):
    page.goto(page.base + path)
    url = page.url
    page.press(ids[0], "Enter")
    page.wait_for_timeout(100)
    assert page.url == url
    st = _state(page, ids)
    required = ids[:4]
    assert all(s[0] == "true" and "empty" in s[1] for s in st[:len(required)]), st
    if path == PR:
        assert st[4] == [None, ""], "Unique traders is optional"
    page.click("#dc-clear" if path == DC else "#pr-clear")
    assert all(s == [None, ""] for s in _state(page, ids))


def test_worked_examples_unchanged(page):
    import math
    page.goto(page.base + DC)
    page.click("#dc-example")
    got = {k: page.inner_text(f"#dc-{k}") for k in ("pgr", "plr", "ratio", "diff", "se", "t")}
    rg, pgn, rl, pl = 420, 1780, 260, 2240
    pgr, plr = rg / (rg + pgn), rl / (rl + pl)
    se = math.sqrt(pgr * (1 - pgr) / (rg + pgn) + plr * (1 - plr) / (rl + pl))
    assert got == {"pgr": f"{pgr:.4f}", "plr": f"{plr:.4f}", "ratio": f"{pgr/plr:.2f}",
                   "diff": f"{pgr-plr:.4f}", "se": f"{se:.4f}", "t": f"{(pgr-plr)/se:.2f}"}
    assert all(s == [None, ""] for s in _state(page, DC_IDS))
    page.goto(page.base + PR)
    page.click("#pr-example")
    got = {k: page.inner_text(f"#pr-{k}") for k in ("rate", "range", "perEval", "perFunded", "perTrader")}
    assert got == {"rate": "20.0%", "range": "17.0% to 32.0%", "perEval": "4.0%", "perFunded": "23.5%", "perTrader": "1.25"}
    # the example as the fine print writes it, with thousands commas, gives the same figures
    page.click("#pr-clear")
    for sel, v in zip(PR_IDS, ["1 000", "150", "170", "40", "800"]):
        page.fill(sel, v)
    assert page.inner_text("#pr-rate") == "20.0%"


def test_pass_rate_one_comma_five(page):
    page.goto(page.base + PR)
    for sel, v in zip(PR_IDS, ["1,5", "0", "0", "0", ""]):
        page.fill(sel, v)
    assert page.evaluate("document.getElementById('pr-results').hidden")
    assert "decimal" in _state(page, PR_IDS)[0][1]


def test_node_api_still_works():
    r = subprocess.run(["node", "-e", """
        const d = require(process.argv[1]), p = require(process.argv[2]);
        console.log(JSON.stringify([d.parseCount('1,5'), d.parseCount('1780'), d.parseCount(''), p.parseCount('', true),
                                    d.compute(420, 1780, 260, 2240).ok]));""",
                        os.path.join(REPO, "site/static/js/legacy/disposition-calculator.js"),
                        os.path.join(REPO, "site/static/js/legacy/pass-rate-calculator.js")],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    a, b, c, d, e = json.loads(r.stdout)
    assert a["ok"] is False and b == {"ok": True, "value": 1780} and c == {"ok": False, "error": "empty"}
    assert d == {"ok": True, "value": None} and e is True


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375])
@pytest.mark.parametrize("path,ids", [(DC, DC_IDS), (PR, PR_IDS)])
def test_axe_and_overflow_with_every_message_showing(browser, built_site, path, ids, width, scheme):
    import sys
    sys.path.insert(0, os.path.join(REPO, "checks"))
    from a11y import axe_violations, horizontal_overflow
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, bypass_csp=True)
    p = ctx.new_page()
    p.goto(built_site["url"] + path)
    p.wait_for_load_state("networkidle")
    for sel, v in zip(ids, ["1,5", "1,2,3", "4 2", "x", "-"]):
        p.fill(sel, v)
    assert p.locator(".error:visible").count() == len(ids)
    assert horizontal_overflow(p) == []
    assert axe_violations(p) == []
    ctx.close()


def test_pct_never_rounds_to_100_or_0_unless_exact():
    """Tester §12 (v1 test_pass_rate_never_rounds_to_100_when_some_failed): 19,999 passed of 20,000
    finished showed "100.0%"; 1 of 20,000 showed "0.0%"."""
    r = subprocess.run(["node", "-e", """
        global.dtNumbers = require(process.argv[1]); const p = require(process.argv[2]);
        const show = a => { const r = p.compute(...a); return [p.pct(r.passRateFinished), p.pct(r.rangeLow), p.pct(r.rangeHigh)]; };
        console.log(JSON.stringify([show([20000, 0, 19999, 0]), show([20000, 0, 1, 0]), show([1, 0, 0, 0]),
                                    show([1, 0, 1, 1]), show([1000, 150, 170, 40]), show([20000, 1, 19999, 0])]));""",
                        NUMBERS, os.path.join(REPO, "site/static/js/legacy/pass-rate-calculator.js")],
                       capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    a, b, c, d, e, f = json.loads(r.stdout)
    assert a == ["over 99.9%", "over 99.9%", "over 99.9%"]
    assert b == ["under 0.1%", "under 0.1%", "under 0.1%"]
    assert c == ["0.0%", "0.0%", "0.0%"] and d == ["100.0%", "100.0%", "100.0%"]    # exact: 0 of 1, 1 of 1
    assert e == ["20.0%", "17.0%", "32.0%"]                                           # the worked example
    assert f == ["100.0%", "over 99.9%", "100.0%"]           # 19,999 of 19,999 finished; the open one may fail


def test_pass_rate_19999_of_20000_in_the_page(page):
    page.goto(page.base + PR)
    for sel, v in zip(PR_IDS, ["20000", "0", "19999", "0", ""]):
        page.fill(sel, v)
    assert page.inner_text("#pr-rate") == "over 99.9%"
    assert page.inner_text("#pr-range") == "over 99.9% to over 99.9%"


def test_the_example_as_the_page_writes_it(page):
    """The fine print says "(420, 1,780, 260, 2,240)": typed that way it gives the example's figures."""
    page.goto(page.base + DC)
    for sel, v in zip(DC_IDS, ["420", "1,780", "260", "2,240"]):
        page.fill(sel, v)
    assert page.inner_text("#dc-pgr") == f"{420 / 2200:.4f}" and page.inner_text("#dc-plr") == f"{260 / 2500:.4f}"
    assert all(s == [None, ""] for s in _state(page, DC_IDS))


def test_whole_mode_in_node():
    got = [(g["ok"], g["value"]) for g in _parity_whole(["1,780", "1.780", "1,5", "12,780", "-1,780"])]
    assert got == [(True, 1780), (True, 1780), (True, 1.5), (True, 12780), (True, -1780)]   # 1.5 → "has decimals"


def _parity_whole(raws):
    r = subprocess.run(["node", "-e", "const N = require(process.argv[1]); console.log(JSON.stringify(process.argv.slice(2).map(x => N.readForm([x], {whole: true})[0])));",
                        NUMBERS, *raws], capture_output=True, text=True, timeout=30)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)
