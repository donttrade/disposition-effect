"""Universal importer, engine side (plan B1/B2): mapped columns, presets, pastes, several files.

The JS engine in Chromium must equal the Python reference on every case in
tests/fixtures/{mapped,presets,paste,multi,auto} (written by make_mapped.py), in the same four
time zones and locales as the golden test; the readers they share are compared vector by vector
under node. No case holds a real row; the canary CANARY-ZQ7X sits in every account, name, user,
wallet and note cell and must never come out.
"""
import base64
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, HERE)
import engine_ref as E  # noqa: E402
from test_engine_golden import CONTEXTS, comparable, same  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
EXP = os.path.join(FIX, "expected")
CASES = E.case_paths(FIX)
CANARY = "CANARY-ZQ7X"


def node(expr, imports="index"):
    """Evaluate a JS expression with the engine modules imported as I (index), C (csv), M (mapped),
    P (presets), D (detect), X (errors); returns its JSON value."""
    code = ("const [I, C, M, P, D, X] = await Promise.all(['index', 'csv', 'mapped', 'presets', 'detect', 'errors']"
            ".map((n) => import('./site/static/js/engine/' + n + '.js')));"
            f"process.stdout.write(JSON.stringify({expr}));")
    out = subprocess.run(["node", "--input-type=module", "-e", code], cwd=REPO, capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


def spec_json(rel):
    spec = E.case_spec(FIX, rel)
    items = [it if isinstance(it, dict) else {"b64": base64.b64encode(it).decode()} for it in spec["items"]]
    return json.dumps({"items": items, "mapping": spec["mapping"], "presets": spec["presets"]})


@pytest.fixture(scope="module", params=CONTEXTS, ids=[c[0] for c in CONTEXTS])
def engine_page(request, browser, repo_server):
    tz, locale = request.param
    ctx = browser.new_context(timezone_id=tz, locale=locale)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/tests/harness.html")
    page.wait_for_function("document.getElementById('status').textContent === 'ready'")
    yield page
    assert not errors, errors
    ctx.close()


def expected(rel):
    with open(os.path.join(EXP, rel.replace("/", "__") + ".json"), encoding="utf-8") as f:
        return json.load(f)


# ----------------------------------------------------------------- JS = Python on every case

@pytest.mark.parametrize("rel", CASES)
def test_case_matches_reference(engine_page, rel):
    want = expected(rel)
    assert want == E.run_case(FIX, rel), "expected/*.json is stale: rerun engine_ref.py --expected tests/fixtures"
    raw = json.loads(engine_page.evaluate("s => window.runCase(s)", spec_json(rel)))
    diff = same(comparable(raw) if "question" not in raw else raw, comparable(want) if "question" not in want else want)
    assert not diff, f"{rel}: {diff}"
    assert CANARY not in json.dumps(raw, ensure_ascii=False), rel


def test_every_case_has_its_expected_file_and_no_other():
    names = {n for n in os.listdir(EXP) if n.split("__")[0] in E.CASE_DIRS}
    assert names == {rel.replace("/", "__") + ".json" for rel in CASES}


# ----------------------------------------------------------------- the tables both sides share

def test_presets_blocklist_and_constants_equal():
    got = node("[P.PRESETS, M.BLOCKED, M.STATUS_KEEP, M.MAP_FIELDS, M.LAYOUTS, C.DATE_FORMATS, M.MAPPED_TZ, "
               "P.PRESET_SEARCH_ROWS, P.PRESET_AFTER, M.MAX_FEE_COLUMNS]")
    assert got == [E.PRESETS, E.BLOCKED, E.STATUS_KEEP, E.MAP_FIELDS, E.LAYOUTS, E.DATE_FORMATS, E.MAPPED_TZ,
                   E.PRESET_SEARCH_ROWS, E.PRESET_AFTER, E.MAX_FEE_COLUMNS]


def test_no_preset_or_signature_reads_a_blocked_column():
    for p in E.PRESETS:
        heads = list(p["match"])
        for v in p["cols"].values():
            heads += v if isinstance(v, list) else [v]
        for h in heads:
            assert not E.is_blocked(h), (p["id"], h)
    for sig in E.SIGNATURES.values():
        for aliases in sig["fields"].values():
            for a in aliases:
                assert not E.is_blocked(a.split("#")[0]), a
    for h in ("account", "accountid", "accountdisplayname", "tradeaccount", "acctno", "name", "owner", "user", "uid",
              "walletaddress", "address", "email", "emailaddress", "phone", "clientid", "traderid", "comment",
              "comments", "notes", "remarks",
              # Tester F7
              "tradehash", "txhash", "transactionhash", "transactionid", "depositaddress", "toaddress", "fromaddress",
              "receivingaddress", "iban", "customerid", "customer", "clientname", "tradername", "legalname",
              "displayname", "nickname", "cardnumber", "ssn", "taxid", "mobile", "mail", "ipaddress", "publickey",
              "signature", "ordercomment", "tradecomment", "memo", "description",
              # Tester round 2, N4
              "orderid", "beneficiary", "counterparty", "sender", "login", "bank", "bankname",
              "routingnumber", "sortcode", "telegram", "discord", "handle", "cell", "contact", "referralcode"):
        assert E.is_blocked(h), h
    for h in ("symbol", "price", "quantity", "commission", "txid", "ordertxid", "instrument", "contractname", "time",
              "filledquantity", "fillprice", "side", "status", "notescodes", "cancelled", "canceled", "ordertype"):
        assert not E.is_blocked(h), h


def test_each_preset_reads_its_required_fields_from_its_match_headings():
    for p in E.PRESETS:
        req = E._LAYOUT_FIELDS[p["layout"]]["required"]
        for f in req:
            assert p["cols"].get(f) in p["match"], (p["id"], f)
        assert set(p["cols"]) <= set(E.MAP_FIELDS), p["id"]
        assert p["source"].startswith(("OFFICIAL", "3RD")), p["id"]


def test_every_preset_auto_maps_a_fixture_and_only_its_own():
    seen = {}
    for rel in CASES:
        want = expected(rel)
        if "result" in want and want["result"].get("preset"):
            seen.setdefault(want["result"]["preset"], []).append(rel)
    assert set(seen) == {p["id"] for p in E.PRESETS}, sorted({p["id"] for p in E.PRESETS} - set(seen))
    for pid, rels in seen.items():
        for rel in rels:
            src = E.read_rows(E.case_spec(FIX, rel)["items"][0])
            hits = [p["id"] for p in E.PRESETS if E.preset_mapping(p, src)]
            assert hits == [pid], (rel, hits)


def test_a_preset_with_an_ambiguous_date_asks_and_never_guesses():
    want = expected("presets/ninjatrader_ambiguous_date.csv")
    assert want == {"question": {"preset": "ninjatrader_exec", "questions": [{"q": "date_order", "reason": "ask"}]}}


def test_sierra_log_is_read_by_its_preset_on_every_path(engine_page):
    """Its headings fit the IBKR Flex signature (checked before generic). Tester F4: runFile, which
    every page calls, now goes through the preset flow, so the log is Sierra fills everywhere; the
    known formats alone (E._parse_with, no mapping) still read it as IBKR, unchanged."""
    with open(os.path.join(FIX, "presets", "sierra_fills.txt"), "rb") as f:
        data = f.read()
    assert E._parse_with([data], None)["format"] == "ibkr_flex"
    want = expected("presets/sierra_fills.txt")
    assert want["result"]["preset"] == "sierra_fills" and E.run_files([data]) == {"result": want["result"]}
    got = json.loads(engine_page.evaluate("b => window.parseOnly(b)", base64.b64encode(data).decode()))
    assert comparable(got) == comparable({"result": want["result"]})
    first = got["result"]["trades"][0]
    assert first["qty"] == 1 and first["entry_vwap"] == 5900


# ----------------------------------------------------------------- what the cases show

def test_encodings_give_one_result():
    base = expected("mapped/enc_utf8.csv")
    for name in ("enc_utf8_bom", "enc_utf16le_bom", "enc_utf16le_nobom", "enc_cp1252"):
        assert expected(f"mapped/{name}.csv") == base, name


def test_overlapping_files_count_each_fill_once():
    one = expected("multi/one_file_for_comparison")["result"]
    two = expected("multi/overlap")["result"]
    assert [(t["symbol"], t["open_ts"], t["close_ts"], t["pnl"]) for t in two["trades"]] == \
           [(t["symbol"], t["open_ts"], t["close_ts"], t["pnl"]) for t in one["trades"]]
    assert {w["code"]: w["n"] for w in two["warnings"]} == {"W_OVERLAP_ROWS": 20}
    twice = expected("multi/same_file_twice")["result"]
    assert len(twice["trades"]) == 15 and {w["code"]: w["n"] for w in twice["warnings"]} == {"W_OVERLAP_ROWS": 30}
    # Two identical fills inside one file both stay (as before); the other file's single copy is the overlap.
    ident = expected("multi/identical_fills_in_one_file")["result"]
    codes = {w["code"]: w["n"] for w in ident["warnings"]}
    assert codes["W_DUPLICATE_ROWS"] == 1 and codes["W_OVERLAP_ROWS"] == 15
    pages = expected("multi/paste_pages")["result"]
    assert len(pages["trades"]) == 16 and {w["code"]: w["n"] for w in pages["warnings"]}["W_OVERLAP_ROWS"] == 8


def test_errors_in_several_files_name_the_file_by_place():
    assert expected("multi/error_in_second_file")["error"] == {"code": "E_BAD_NUMBER", "row": 5, "column": "qty", "file": 2}
    assert expected("multi/two_platforms")["error"]["code"] == "E_MIXED_FILES"
    assert expected("multi/mapped_other_platform")["error"] == {"code": "E_MIXED_FILES", "row": None, "column": None,
                                                                "file": 2}


def test_js_messages_for_files_xlsx_zip_and_mappings(engine_page):
    def run(rel):
        return json.loads(engine_page.evaluate("s => window.runCase(s)", spec_json(rel)))["error"]["message"]
    assert "(file 2 of 2, row 5, column qty)" in run("multi/error_in_second_file")
    assert "(file 2 of 2)" in run("multi/two_platforms")
    xlsx, zipped = run("auto/workbook.xlsx"), run("auto/export.zip")
    assert "Excel (.xlsx)" in xlsx and "Save it as CSV" in xlsx and "zip" not in xlsx
    assert "zip file. Open it and drop the CSV inside" in zipped and "xlsx" not in zipped
    assert run("mapped/stale_heading.csv").startswith("These column choices do not fit this file.")
    assert "date form you chose (month/day/year)" in run("mapped/mixed_iso_and_slash.csv")
    assert run("paste/single_spaces_only.txt").startswith("This paste has no columns we can split.")


def test_dates_only_files():
    for rel in ("mapped/fidelity_like.csv", "mapped/robinhood_like_newest_first.csv",
                "mapped/dates_only_newest_first.csv", "multi/mapped_overlap"):
        r = expected(rel)["result"]
        assert r["dates_only"] is True and r["warnings"][-1]["code"] == "W_DATES_ONLY", rel
    # A buy and a sell of one symbol on one date, newest first: the trade is long (chronoOrder).
    r = expected("mapped/dates_only_newest_first.csv")["result"]
    assert len(r["trades"]) == 30 and all(t["dir"] == "long" for t in r["trades"])
    assert expected("mapped/ampm_zone_labels.csv")["result"]["dates_only"] is False


def test_hostile_numbers_and_signs():
    px = lambda rel: [e["price"] for e in expected(rel)["result"]["executions"]]
    assert all(p >= 1000 for p in px("mapped/thousands_separators.csv"))
    assert expected("mapped/lone_comma_no_style.csv")["error"]["code"] == "E_BAD_NUMBER"
    assert all(p >= 1000 and p == int(p) for p in px("mapped/lone_comma_dot.csv"))
    assert all(1 < p < 10 for p in px("mapped/lone_comma_comma.csv"))
    assert expected("mapped/semicolon_dot3_no_style.csv")["error"]["code"] == "E_BAD_NUMBER"
    assert sorted(set(px("mapped/semicolon_dot3_comma_style.csv"))) == [1250, 1500]
    ex = expected("mapped/money_forms_sign_mode.csv")["result"]["executions"]
    assert all(abs(e["fee"] - 1.3) < 1e-12 for e in ex)
    assert [e["side"] for e in ex].count("sell") == 8 and all(e["price"] > 1000 for e in ex)
    sm = expected("mapped/sign_mode.csv")["result"]
    assert sm["skipped"] == {"zero_qty": 1}


# ----------------------------------------------------------------- shared readers, vector by vector

DATE_VECTORS = [
    ("2026-10-02 09:31:05", "ymd"), ("2026/10/02", "ymd"), ("2026.10.02 9:31", "ymd"), ("20261002", "ymd"),
    ("2026-10-02T09:31:05.123456Z", "ymd"), ("2026-10-02 09:31:05+02:00", "ymd"), ("2026-10-02 09:31:05 UTC", "ymd"),
    ("2026-10-02 09:31:05-0400", "ymd"), ("10/2/2026 9:31:05 PM EDT", "mdy"), ("10/2/2026 12:01 AM", "mdy"),
    ("10/2/2026 12:01 PM", "mdy"), ("10-2-26 13:00", "mdy"), ("2.10.2026 9:31:05", "dmy"), ("31/12/2026", "dmy"),
    ("31/12/2026", "mdy"), ("13/13/2026", "dmy"), ("2026-10-02", "mdy"), ("10/2/2026", "ymd"), ("45567.5", "excel"),
    ("45567 09:30", "excel"), ("45567.5 09:30", "excel"), ("59.5", "excel"), ("1727861465", "epoch_s"),
    ("1727861465.9", "epoch_s"), ("1727861465123", "epoch_ms"), ("1727861465123", "epoch_s"), ("", "ymd"),
    ("2026-02-30", "ymd"), ("13:00 PM 10/2/2026", "mdy"), ("10/2/2026 13:00 PM", "mdy"), ("2026-10-02 9:31pm", "ymd"),
    ("2026-10-02 GMT+2", "ymd"), ("Oct 2, 2026", "mdy"), ("1969-12-31", "ymd"), ("2101-01-01", "ymd"),
]


def py_date(raw, fmt):
    seen = {"zone": False}
    try:
        return {"ts": E.parse_date_fmt(raw, fmt, 3, "date", seen), "zone": seen["zone"]}
    except E.EngineError as e:
        return {"error": e.to_json()}


def test_parse_date_fmt_vectors_match():
    js = node("%s.map(([r, f]) => { const s = {zone: false}; try { return {ts: C.parseDateFmt(r, f, 3, 'date', s), "
              "zone: s.zone}; } catch (e) { return {error: {code: e.code, row: e.row, column: e.column}}; } })"
              % json.dumps(DATE_VECTORS))
    py = [py_date(r, f) for r, f in DATE_VECTORS]
    assert js == py
    assert py[0]["ts"] == 1790933465000 and py[8] == {"ts": 1790976665000, "zone": True}
    assert py[18]["ts"] == 1727870400000                    # Excel 45567.5 = 2 Oct 2024 12:00
    assert py[15]["error"]["code"] == "E_BAD_DATE" and py[21]["error"]["code"] == "E_BAD_DATE"


DETECT_VECTORS = [
    ["2026-10-02", "2026-10-03 09:00"], ["03/04/2026", "05/06/2026"], ["13/04/2026", "03/04/2026"],
    ["04/13/2026", "03/04/2026"], ["13/04/2026", "04/13/2026"], ["2026-10-02", "10/02/2026"], ["45567.5", "45568"],
    ["1727861465", "1727861466"], ["1727861465123"], ["", "  "], ["abc"], ["20261002", "20261003"],
    ["10/2/2026 9:31:05 PM EDT", "10/13/2026 1:00:00 AM EDT"],
]


def test_detect_date_format_vectors_match():
    js = node("%s.map((v) => C.detectDateFormat(v))" % json.dumps(DETECT_VECTORS))
    py = [E.detect_date_format(v) for v in DETECT_VECTORS]
    assert js == py
    assert [p["format"] or p["reason"] for p in py] == ["ymd", "ask", "dmy", "mdy", "mixed_order", "mixed", "excel",
                                                        "epoch_s", "epoch_ms", "empty", "mixed", "ymd", "mdy"]


MONEY_VECTORS = ["$1,234.50", "(12.30)", "12.30-", "−12.30", "-$12.30", "$-12.30", "12.30 USD", "USD 12.30",
                 "€ 12,30", "12,30 €", "₹1,000", "(-12)", "$", "-", "(", "()", "12.30", "ABC 12", "12 abc", "",
                 "+$5", "$ 5 USD", "(12.30 USD)"]


def test_money_clean_vectors_match():
    js = node("%s.map((v) => M.moneyClean(v))" % json.dumps(MONEY_VECTORS, ensure_ascii=False))
    py = [E.money_clean(v) for v in MONEY_VECTORS]
    assert js == py
    assert py[:9] == ["1,234.50", "-12.30", "-12.30", "-12.30", "-12.30", "-12.30", "12.30", "12.30", "12,30"]
    assert py[11] == "(-12)"   # a sign inside brackets is refused later by parseNumber


PASTE_VECTORS = [
    "a\tb\tc\n1\t2\t3\n", "Date              Symbol  Side\n2026-10-02 09:31  AAA     Buy\n", "a b c\n1 2 3\n", "a\nb\nc\n",
    "  \n\t\n", "menu\nA\tB\n\n1\t2\nfooter\n", "x\t\t\n\t\t\n1\t\t2\n",
    # fixed width: a blank cell stays blank (Tester F1); a right-aligned number wider than its heading;
    # a word under two headings (E_PASTE_ALIGN at its line); a short footer read as it is
    "Date        Qty  SL    Price\n2026-10-02  1          1.10\n2026-10-03  1    1.05  1.11\n",
    "Sym  Qty  Px\nAAA  10000  5\n", "Date  Symbol  Side\n2026-10-02 09:31  AAA  Buy\n",
    "A    B    C    D\n1    2    3    4\nTotal  4\n",
]


def py_paste(t):
    try:
        return [{"row": r["row"], "cells": r["cells"]} for r in E.from_paste(t)]
    except E.EngineError as e:
        return {"error": e.code}


def test_long_whitespace_runs_stay_fast():
    """Tester F8: clean() was quadratic on a long run of spaces (5.4 s for 200,000)."""
    t = node("(() => { const t0 = Date.now(); try { C.fromPaste(' '.repeat(400000) + 'a  b\\n1  2\\n'); } catch (e) { } "
             "C.clean(' '.repeat(2000000) + 'x' + ' '.repeat(2000000)); return Date.now() - t0; })()")
    assert t < 1500, t
    big = node("(() => { try { C.fromPaste('a\\tb\\n'.repeat(1500000)); } catch (e) { return e.code; } })()")
    assert big == "E_PASTE_TOO_LARGE"


def test_from_paste_vectors_match():
    js = node("%s.map((t) => { try { return C.fromPaste(t).map((r) => ({row: r.row, cells: r.cells})); } "
              "catch (e) { return {error: e.code}; } })" % json.dumps(PASTE_VECTORS))
    py = [py_paste(t) for t in PASTE_VECTORS]
    assert js == py
    assert py[1][1]["cells"] == ["2026-10-02 09:31", "AAA", "Buy"]
    assert py[7][1]["cells"] == ["2026-10-02", "1", "", "1.10"] and py[7][2]["cells"] == ["2026-10-03", "1", "1.05", "1.11"]
    assert py[8][1]["cells"] == ["AAA", "10000", "5"]
    assert py[9] == {"error": "E_PASTE_ALIGN"} and py[10][2]["cells"] == ["Total", "4", "", ""]
    assert py[2] == {"error": "E_PASTE_FORMAT"} and py[3] == {"error": "E_PASTE_FORMAT"} and py[4] == {"error": "E_EMPTY"}


def test_bad_mappings_are_refused_alike():
    base = {"v": 1, "layout": "fills", "header_row": 0, "cols": {"date": 0, "symbol": 1, "side": 2, "qty": 3, "price": 4},
            "headers": {"0": "date", "1": "symbol", "2": "side", "3": "qty", "4": "price"}, "date_format": "ymd"}
    bad = [
        {"v": 2}, {"layout": "trades"}, {"header_row": -1}, {"header_row": 1.5}, {"delimiter": "|"},
        {"cols": {"date": 0, "symbol": 1, "side": 2, "qty": 3}}, {"cols": {**base["cols"], "pnl": 5}},
        {"cols": {**base["cols"], "fees": [5, 6, 7, 8]}}, {"cols": {**base["cols"], "bogus": 1}},
        {"side_from": "sign", "layout": "roundtrips"}, {"side_values": {"buy": "long"}}, {"side_rules": [["regex", "b", "buy"]]},
        {"status_values": {"filled": "yes"}}, {"date_format": "dym"}, {"number_style": "space"}, {"currency": "usd"},
        {"tz": "local"}, {"preset": "../x"}, {"futures_sizes": "yes"}, {"source": {"kind": "pdf", "table": 0}},
        {"side_default": "buy"}, {"cols": {**base["cols"], "qty": True}}, {"year_base": 1950},
    ]
    good = [{}, {"side_from": "sign", "cols": {"date": 0, "symbol": 1, "qty": 3, "price": 4}}, {"cols": {**base["cols"], "fees": []}}]
    cases = [dict(base, **b) for b in bad] + [dict(base, **g) for g in good]
    js = node("%s.map((m) => { try { return M.checkMapping(m); } catch (e) { return e.code + ':' + e.column; } })"
              % json.dumps(cases))
    py = []
    for m in cases:
        try:
            py.append(E.check_mapping(m))
        except E.EngineError as e:
            py.append(f"{e.code}:{e.column}")
    assert js == py
    assert all(p.startswith("E_BAD_MAPPING") for p in py[:len(bad)]), py
    assert py[len(bad):] == ["column", "sign", "column"]


def test_200000_rows_over_three_files_and_one_more(engine_page):
    """Limits are in total (plan §2.4): 200,000 rows over three files read; 200,001 is E_TOO_LARGE."""
    def file_of(n, k):
        lines = ["Date,Time,Symbol,Side,Quantity,Price"]
        for i in range(n):
            s = (k * 100000 + i) * 60
            lines.append("2026-%02d-%02d,%02d:%02d:%02d,S%d,%s,1,%d" % (
                1 + (s // 86400 // 28) % 12, 1 + (s // 86400) % 28, (s // 3600) % 24, (s // 60) % 60, s % 60,
                i // 2 % 50, "Buy" if i % 2 == 0 else "Sell", 100 + i % 7))
        return ("\n".join(lines) + "\n").encode()
    files = [file_of(66668, 0), file_of(66666, 1), file_of(66666, 2)]
    spec = lambda fs: json.dumps({"items": [{"b64": base64.b64encode(f).decode()} for f in fs], "mapping": None,
                                  "presets": False})
    ok = json.loads(engine_page.evaluate("s => { const r = JSON.parse(window.runCase(s)); return JSON.stringify("
                                         "r.error ? r : {n: r.result.trades.length}); }", spec(files)))
    assert "n" in ok, ok
    files[2] = file_of(66667, 2)
    over = json.loads(engine_page.evaluate("s => window.runCase(s)", spec(files)))
    assert over["error"]["code"] == "E_TOO_LARGE" and "file" not in over["error"]


def test_python_total_row_cap(monkeypatch):
    monkeypatch.setattr(E, "MAX_ROWS", 10)
    f = lambda n: ("Date,Time,Symbol,Side,Quantity,Price\n" + "".join(
        "2026-01-05,09:%02d:00,AAA,%s,1,100\n" % (i, "Buy" if i % 2 == 0 else "Sell") for i in range(n))).encode()
    assert "result" in E.run_files([f(4), f(6)])
    assert E.run_files([f(4), f(7)])["error"]["code"] == "E_TOO_LARGE"
