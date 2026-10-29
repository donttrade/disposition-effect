"""Importer fix round (TESTER-REPORT-IMPORTER-ENGINE-2026-10-29): the tester's hostile files.

tests/fixtures/tester/ and tester_multi/ are the tester's own synthetic files (gen.py), kept as
regression fixtures. Every one runs as a case in test_engine_mapped.py (known formats and presets,
JS = Python) and as a pinned guess in test_mapping_guess.py. Here: each file through the guess and
the mapping it gives, in Chromium and in the Python reference, and one check per finding.
"""
import base64
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, HERE)
import engine_ref as E  # noqa: E402
from test_engine_golden import comparable, same  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
TDIR = os.path.join(FIX, "tester")
FILES = sorted(os.listdir(TDIR)) + ["../tester2/" + n for n in sorted(os.listdir(os.path.join(FIX, "tester2")))]


def item(name):
    path = os.path.normpath(os.path.join(TDIR, name))
    if name.endswith(".paste.txt"):
        with open(path, encoding="utf-8") as f:
            return {"paste": f.read()}
    with open(path, "rb") as f:
        return f.read()


def js_item(it):
    return it if isinstance(it, dict) else {"b64": base64.b64encode(it).decode()}


@pytest.fixture(scope="module")
def page(browser, repo_server):
    ctx = browser.new_context(timezone_id="America/Toronto", locale="en-CA")
    p = ctx.new_page()
    errors = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    p.goto(repo_server + "/tests/harness.html")
    p.wait_for_function("document.getElementById('status').textContent === 'ready'")
    yield p
    assert not errors, errors
    ctx.close()


def inspect(page, name, opts=None):
    spec = json.dumps({"items": [js_item(item(name))]})
    return json.loads(page.evaluate("([s, o]) => window.inspectCase(s, o)", [spec, opts]))


def run_js(page, items, mapping=None):
    spec = json.dumps({"items": [js_item(i) for i in items], "mapping": mapping, "presets": False})
    return json.loads(page.evaluate("s => window.runCase(s)", spec))


def guessed(page, name, **changes):
    g = inspect(page, name)
    m = g["guess"]["mapping"]
    m.update(changes)
    return g, m


@pytest.mark.parametrize("name", FILES)
def test_guessed_mapping_reads_alike_in_js_and_python(page, name):
    g = inspect(page, name)
    if "error" in g or g["guess"] is None:
        return
    m = g["guess"]["mapping"]
    js = run_js(page, [item(name)], m)
    py = E.run_case_items([item(name)], m)
    diff = same(comparable(js), comparable(py))
    assert not diff, (name, diff)
    assert "CANARY" not in json.dumps(js)


# ----------------------------------------------------------------- one check per finding

def test_f1_blank_cells_in_a_spaced_paste_never_shift_columns(page):
    g, m = guessed(page, "p_blank_cells.paste.txt")
    r = run_js(page, [item("p_blank_cells.paste.txt")], m)["result"]
    assert all(1 < e["price"] < 2 for e in r["executions"])   # never the Swap column's -0.5
    assert E.run_files([item("p_spaces_misaligned.paste.txt")])["error"] == {"code": "E_PASTE_ALIGN", "row": 2,
                                                                             "column": None}


def test_f2_unquoted_thousands_are_refused_never_read_as_1_and_000(page):
    for name in ("n_lone_1234.csv", "n_currency.csv"):
        out = run_js(page, [item(name)])
        assert out["error"]["code"] == "E_NO_CLOSED_TRADES" and "split number: 20" in out["error"]["message"], name
        q = inspect(page, name)["guess"]["questions"]
        assert q[0] == {"q": "split_number", "rows": [2, 3, 4, 5, 6], "n": 20}, name


def test_f3_fills_with_other_ids_are_not_overlap():
    two = E.run_case(FIX, "tester_multi/mf_ident_acct")["result"]
    assert "W_OVERLAP_ROWS" not in [w["code"] for w in two["warnings"]]
    assert len(two["executions"]) == 4
    over = E.run_case(FIX, "tester_multi/mf_auto_overlap")["result"]
    full = E.run_case(FIX, "tester_multi/mf_full")["result"]
    assert [(t["open_ts"], t["pnl"]) for t in over["trades"]] == [(t["open_ts"], t["pnl"]) for t in full["trades"]]
    assert {w["code"]: w["n"] for w in over["warnings"]} == {"W_OVERLAP_ROWS": 6}


def test_f5_footers_do_not_derail_the_guess_and_rows_are_real(page):
    for name in ("h_preamble.csv", "p_footer3.paste.txt"):
        g = inspect(page, name)["guess"]
        assert g["mapping"]["date_format"] == "ymd" and g["questions"] == [], name
        assert g["badges"]["date"] == "matched", name
    for name in ("d_mixed_formats.csv", "d_both_orders_conflict.csv", "d_ambiguous_slash.csv"):
        q = inspect(page, name)["guess"]["questions"][0]
        rows = q.get("rows", [q.get("row")])
        assert rows and all(isinstance(r, int) and r >= 2 for r in rows), (name, q)


def test_f6_durations_mixed_dates_offsets_and_years(page):
    g = inspect(page, "h_duration_time.csv")["guess"]
    assert g["mapping"]["cols"]["time"] is None
    _, m = guessed(page, "d_mixed_dateonly.csv")
    r = run_js(page, [item("d_mixed_dateonly.csv")], m)["result"]
    codes = {w["code"]: w["n"] for w in r["warnings"]}
    assert codes["W_SOME_DATES_ONLY"] == 4
    for t in r["trades"]:   # a day-level trade has no time of day at either end
        assert (t["open_ts"] % 86400000 == 0 and t["close_ts"] % 86400000 == 0) or t["hold_s"] % 86400 != 0
    for name in ("d_mixed_offsets.csv", "d_mixed_offsets2.csv"):
        _, m = guessed(page, name)
        r = run_js(page, [item(name)], m)["result"]
        assert r["tz_label"] == "as in the file; order and hold times use each row's UTC offset", name
        assert all(t["hold_s"] == 3600 for t in r["trades"]), name   # 09:30 EST vs 09:30 EDT: an hour apart
    g, m = guessed(page, "d_year99.csv")
    assert g["guess"]["questions"][0]["q"] == "two_digit_year"
    assert run_js(page, [item("d_year99.csv")], m)["error"]["code"] == "E_BAD_DATE"
    m["year_base"] = 1900
    assert run_js(page, [item("d_year99.csv")], m)["result"]["trades"][0]["open_ts"] < 946684800000
    _, m = guessed(page, "d_year2.csv")
    assert run_js(page, [item("d_year2.csv")], m)["result"]["trades"][0]["open_ts"] > 1767225600000   # 2026


def test_f8_one_column_one_field_and_other_languages(page):
    _, m = guessed(page, "h_side_bs.csv")
    price = m["cols"]["price"]
    m["cols"]["fees"] = [price, price, price]
    assert run_js(page, [item("h_side_bs.csv")], m)["error"]["code"] == "E_BAD_MAPPING"
    for name, side in (("h_es.csv", {"compra": "buy", "venta": "sell"}), ("h_de.csv", {"kauf": "buy", "verkauf": "sell"})):
        g = inspect(page, name)["guess"]
        assert all(g["mapping"]["cols"][f] is not None for f in ("date", "time", "symbol", "side", "qty", "price")), name
        assert g["mapping"]["side_values"] == side, name


# ----------------------------------------------------------------- round 2 (TESTER-REPORT-IMPORTER-ENGINE-R2)
R2 = "../tester2/"


def test_r2_n1_a_refused_fill_never_leaves_a_phantom_short(page):
    for mapping in (None, guessed(page, R2 + "w_one_refused_buy.csv")[1]):
        r = run_js(page, [item(R2 + "w_one_refused_buy.csv")], mapping)["result"]
        assert [t["dir"] for t in r["trades"]] == ["long"], mapping
        codes = {w["code"]: w["n"] for w in r["warnings"]}
        assert codes["W_REFUSED_FILLS"] == 5 and r["skipped"] == {"split_number": 1}
        assert "W_OPEN_POSITIONS" not in codes


def test_r2_n2_summary_rows_of_any_width_stay_out_of_the_guess(page):
    for name in ("ft_4cells_date.csv", "ft_5cells_dates.csv", "ft_disclaimer.csv", "ft_subtotal_midfile.csv",
                 "ft_two_footers.csv", "ft_total_fills.csv", "ft_3cells_numbers.csv", "ft_4.csv", "ft_sub.csv"):
        g = inspect(page, R2 + name)["guess"]
        cols = g["mapping"]["cols"]
        assert (cols["date"], cols["time"], g["mapping"]["date_format"]) == (0, 1, "ymd"), name
        assert g["questions"] == [], (name, g["questions"])


def test_r2_n3_durations_by_value_and_midnight_clocks_kept(page):
    clock = inspect(page, R2 + "du_real_midnight_clock.csv")["guess"]
    assert clock["mapping"]["cols"]["time"] == 1 and clock["questions"] == []
    _, m = guessed(page, R2 + "du_real_midnight_clock.csv")
    r = run_js(page, [item(R2 + "du_real_midnight_clock.csv")], m)["result"]
    assert r["dates_only"] is False and r["trades"][0]["hold_s"] == 60
    for name in ("du_hours_1_to_5.csv", "du_00mmss_after_qty.csv"):
        g = inspect(page, R2 + name)["guess"]
        assert g["mapping"]["cols"]["time"] is None and g["badges"]["time"] == "check", name
        assert g["questions"][0]["q"] == "time_or_duration" and g["questions"][0]["row"] == 2, name
    assert inspect(page, R2 + "du_units.csv")["guess"]["mapping"]["cols"]["time"] is None
    assert inspect(page, R2 + "du_duration_header.csv")["guess"]["mapping"]["cols"]["time"] == 1


def test_r2_n4_identifiers_blocked():
    for h in ("orderid", "beneficiary", "counterparty", "sender", "login", "bank", "routingnumber", "sortcode",
              "telegram", "discord", "handle", "cell", "contact", "referralcode"):
        assert E.is_blocked(h), h
    assert not E.is_blocked("txid") and not E.is_blocked("positionid") and not E.is_blocked("cancelled")
