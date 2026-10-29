"""Universal importer, the column guess (mapping.js, JS only; plan B2).

The guess decides nothing the user does not see and confirm, so it is not mirrored in Python:
it is pinned by expected-guess files (tests/fixtures/guess_expected/), checked in Chromium, plus
the properties that must always hold (blocked columns never offered, the canary never out, a
date order never guessed, every guessed mapping accepted by the engine).

    DT_WRITE_GUESS=1 python3 -m pytest -q tests/test_mapping_guess.py   # rewrites guess_expected/
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

FIX = os.path.join(HERE, "fixtures")
GEXP = os.path.join(FIX, "guess_expected")
CANARY = "CANARY-ZQ7X"
WRITE = os.environ.get("DT_WRITE_GUESS") == "1"


def guess_cases():
    out = []
    for d in ("guess", "mapped", "presets", "paste"):
        for name in sorted(os.listdir(os.path.join(FIX, d))):
            if not name.endswith(".map.json"):
                out.append(d + "/" + name)
    return out


CASES = guess_cases()


def spec_of(rel):
    if rel.startswith("guess/"):
        with open(os.path.join(FIX, rel), "rb") as f:
            items = [{"b64": base64.b64encode(f.read()).decode()}]
    else:
        spec = E.case_spec(FIX, rel)
        items = [it if isinstance(it, dict) else {"b64": base64.b64encode(it).decode()} for it in spec["items"]]
    return json.dumps({"items": items})


@pytest.fixture(scope="module")
def page(browser, repo_server):
    ctx = browser.new_context()
    p = ctx.new_page()
    errors = []
    p.on("pageerror", lambda e: errors.append(str(e)))
    p.goto(repo_server + "/tests/harness.html")
    p.wait_for_function("document.getElementById('status').textContent === 'ready'")
    yield p
    assert not errors, errors
    ctx.close()


def inspect_js(page, rel, opts=None):
    return json.loads(page.evaluate("([s, o]) => window.inspectCase(s, o)", [spec_of(rel), opts]))


def run_mapping(page, rel, mapping):
    spec = json.loads(spec_of(rel))
    spec.update({"mapping": mapping, "presets": False})
    return json.loads(page.evaluate("s => window.runCase(s)", json.dumps(spec)))


@pytest.mark.parametrize("rel", CASES)
def test_guess_matches_expected(page, rel):
    got = inspect_js(page, rel)
    path = os.path.join(GEXP, rel.replace("/", "__") + ".json")
    if WRITE:
        os.makedirs(GEXP, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(got, f, indent=1, sort_keys=True, ensure_ascii=False)
            f.write("\n")
    with open(path, encoding="utf-8") as f:
        assert got == json.load(f), f"{rel}: the guess changed (DT_WRITE_GUESS=1 rewrites guess_expected/)"


@pytest.mark.parametrize("rel", CASES)
def test_guess_properties(page, rel):
    got = inspect_js(page, rel)
    assert CANARY not in json.dumps(got, ensure_ascii=False), rel
    if "error" in got:
        assert got["error"]["code"] in ("E_EMPTY", "E_PASTE_FORMAT", "E_ENCODING", "E_BAD_QUOTE"), got
        return
    peek, guess = got["peek"], got["guess"]
    blocked = [i for i, b in enumerate(peek["blocked"]) if b]
    for i in blocked:
        assert E.is_blocked(E.norm_header(peek["headers"][i]))
        assert all(r["cells"][i] is None for r in peek["rows"]), (rel, i)
        assert i not in [o["index"] for o in peek["options"]], (rel, i)
    assert len(peek["rows"]) <= 60 and len(got["signature"]) == 32
    if guess is None:
        return
    m = guess["mapping"]
    for f, v in m["cols"].items():
        for i in (v if isinstance(v, list) else [v] if v is not None else []):
            assert i not in blocked, (rel, f, i)
    # Never silent: an open date question leaves the date form unset, and the engine refuses it.
    if any(q["q"] == "date_order" for q in guess["questions"]):
        assert m["date_format"] is None
    # A guess with no open question and no field left to choose is a mapping the engine accepts.
    if not guess["questions"] and "choose" not in guess["badges"].values():
        out = run_mapping(page, rel, m)
        assert "error" not in out or out["error"]["code"] not in ("E_BAD_MAPPING", "E_MIXED_FILES"), (rel, out)


def test_presets_found_by_inspect(page):
    want = {"presets/ninjatrader_exec.csv": "ninjatrader_exec", "presets/ninjatrader_ambiguous_date.csv": "ninjatrader_exec",
            "presets/trading212_history.csv": "trading212_history", "presets/kraken_trades.csv": "kraken_trades",
            "presets/sierra_fills.txt": "sierra_fills", "presets/rithmic_orders.csv": "rithmic_orders",
            "presets/ctrader_history.csv": "ctrader_history", "presets/ctrader_statement.html": "ctrader_history",
            "presets/hyperliquid_fills.csv": "hyperliquid_fills", "paste/dxtrade_grid.txt": "dxtrade_orders"}
    for rel, pid in want.items():
        got = inspect_js(page, rel)
        assert got["preset"]["id"] == pid, rel
    amb = inspect_js(page, "presets/ninjatrader_ambiguous_date.csv")
    assert amb["preset"]["questions"] == [{"q": "date_order", "reason": "ask"}]
    assert amb["guess"]["questions"][0]["q"] == "date_order" and amb["guess"]["questions"][0]["readings"] == \
        {"dmy": "2026-02-03", "mdy": "2026-03-02"}
    assert inspect_js(page, "guess/orders_layout.csv")["preset"] is None


def test_hostile_headings_stay_text_and_duplicates_are_labelled(page):
    got = inspect_js(page, "guess/xss_and_duplicates.csv")
    labels = [o["label"] for o in got["peek"]["options"]]
    assert "<img src=x onerror=alert(1)>" in labels and "Time (1)" in labels and "Time (2)" in labels
    assert "Account" not in labels
    g = got["guess"]
    assert g["mapping"]["cols"]["date"] == 0 and g["mapping"]["cols"]["time"] == 2
    assert g["questions"][0]["q"] == "date_order"


def test_layout_and_value_guesses(page):
    assert inspect_js(page, "guess/orders_layout.csv")["guess"]["layout"] == "orders"
    rt = inspect_js(page, "guess/roundtrips_layout.csv")["guess"]
    assert rt["layout"] == "roundtrips" and rt["mapping"]["side_values"] == {"long": "buy", "short": "sell"}
    sv = inspect_js(page, "guess/side_values.csv")["guess"]
    assert sv["mapping"]["side_values"] == {"buy": "buy", "sell": "sell", "bto": "buy", "stc": "sell", "cdiv": "skip",
                                           "ach": "skip", "bought": "buy"}
    assert sv["side_checks"] == {"bto": "options", "stc": "options"}
    hl = inspect_js(page, "presets/hyperliquid_fills.csv")["guess"]
    assert hl["mapping"]["side_values"] == {"b": "buy", "a": "sell"} and hl["side_checks"] == {"a": "ask_side"}
    mixed = inspect_js(page, "guess/mixed_day_order.csv")["guess"]
    assert mixed["questions"] == [{"q": "date_order", "error": "mixed_order", "rows": [4, 7]}]   # file rows (F5)
    assert mixed["date"]["seen"] == "13/04/2026" and mixed["date"]["seen2"] == "04/13/2026"
    lone = inspect_js(page, "guess/lone_thousands.csv")["guess"]
    assert lone["questions"] == [{"q": "number_style", "example": "2,000"}]
    sign = inspect_js(page, "mapped/sign_mode.csv")["guess"]
    assert sign["mapping"]["side_from"] == "sign" and sign["badges"]["side"] == "check"
    nt = inspect_js(page, "presets/ninjatrader_exec.csv")["guess"]
    assert nt["futures_offer"] is True and (nt["date"]["format"], nt["date"]["reason"]) == ("mdy", "seen")
    assert nt["date"]["seen_row"] >= 2 and nt["date"]["seen2"] is None


def test_header_row_found_below_a_preamble_and_overridable(page):
    fid = inspect_js(page, "mapped/fidelity_like.csv")
    assert fid["peek"]["header_row"] == 6 and fid["peek"]["header_hits"] >= 3
    tos = inspect_js(page, "mapped/tos_like_sections.csv", {"header_row": 11})
    assert tos["peek"]["header_row"] == 11 and "Exec Time" in tos["peek"]["headers"]


def test_html_offers_the_largest_table_and_another_on_request(page):
    got = inspect_js(page, "mapped/html_three_tables.htm")
    assert got["peek"]["table"] == 2 and got["peek"]["tables"] == [{"table": 0, "rows": 2}, {"table": 1, "rows": 2},
                                                                   {"table": 2, "rows": 9}]
    assert got["guess"]["mapping"]["source"] == {"kind": "html", "table": 2}
    other = inspect_js(page, "mapped/html_three_tables.htm", {"table": 1})
    assert other["peek"]["table"] == 1 and other["peek"]["headers"] == ["Symbol", "Volume"]


def test_signature_uses_headings_only(page):
    sig = lambda h, d: page.evaluate("([h, d]) => window.signatureOf(h, d)", [h, d])
    a = sig(["Date", "Symbol", "Side"], ",")
    assert a == sig(["Side", "date", "SYMBOL"], ",") and len(a) == 32 and int(a, 16) >= 0
    assert a != sig(["Date", "Symbol", "Side"], ";") and a != sig(["Date", "Symbol", "Side", "Qty"], ",")
    assert inspect_js(page, "mapped/enc_utf8.csv")["signature"] == inspect_js(page, "mapped/enc_cp1252.csv")["signature"]


def test_headings_email_sends_the_heading_row_only(page):
    mail = lambda *a: json.loads(page.evaluate("s => window.headingsMail(s)", json.dumps(list(a))))
    ok = mail(["Date", "Symbol", "Side", "Qty", "Price"], "Webull", 5)
    assert ok["ok"] and ok["subject"] == "Header row: Webull"
    assert ok["body"] == "Platform: Webull\n\nDate\tSymbol\tSide\tQty\tPrice\n"
    assert ok["href"] == ("mailto:someone@example.org?subject=Header%20row%3A%20Webull&body=Platform%3A%20Webull%0A%0A"
                          "Date%09Symbol%09Side%09Qty%09Price%0A")
    assert mail(["Date", "U1234567", "Side"], "Webull", 5)["reason"] == "digits"
    assert mail(["Date", "10/2/26", "Side"], "Webull", 5)["reason"] == "data_cell"
    assert mail(["Date", "12.50", "Side"], "Webull", 5)["reason"] == "data_cell"
    assert mail(["Date", "$9", "Side"], "Webull", 5)["reason"] == "data_cell"
    assert mail(["Date", "Symbol", "Side"], "Webull", 2)["reason"] == "not_found"
    assert mail(["Date", "Symbol", "Side"], "Webull", 2, True)["ok"]
    assert mail(["Date", "x" * 61], "Webull", 5)["reason"] == "long_cell"
    assert mail(["Heading %d" % (i % 9) for i in range(120)], "Webull", 5)["reason"] == "too_long"
    assert mail(["Date", "Symbol", "Side"], "My broker", 5)["reason"] == "platform"
    assert mail(["Date", "user@x.com", "Side"], "Webull", 5, True)["reason"] == "data_cell"   # Tester F7
    assert mail(["Date", "Sym\tbol", "Side"], "Webull", 5, True)["reason"] == "data_cell"
