"""Golden test: the JS engine in Chromium equals the Python reference on every fixture.

Counts, codes and strings must match exactly; floats to within 1e-9 relative.
Run under three time zones and the de-DE locale: the engine reads times as naive
UTC and never uses the browser's locale, so nothing may change.
"""
import base64
import json
import math
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "reference"))
import engine_ref as E  # noqa: E402

FIX = os.path.join(HERE, "fixtures")
EXP = os.path.join(FIX, "expected")
CONTEXTS = [("UTC", "en-US"), ("America/Toronto", "en-CA"), ("Asia/Kolkata", "en-IN"), ("Europe/Berlin", "de-DE")]


def same(a, b, path="$"):
    """Deep equality; floats within 1e-9 relative. Returns '' or a description."""
    if isinstance(a, bool) or isinstance(b, bool):
        return "" if a is b else f"{path}: {a!r} != {b!r}"
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        if a == b or math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12):
            return ""
        return f"{path}: {a!r} != {b!r}"
    if isinstance(a, dict) and isinstance(b, dict):
        if set(a) != set(b):
            return f"{path}: keys {sorted(set(a) ^ set(b))}"
        for k in a:
            d = same(a[k], b[k], f"{path}.{k}")
            if d:
                return d
        return ""
    if isinstance(a, list) and isinstance(b, list):
        if len(a) != len(b):
            return f"{path}: length {len(a)} != {len(b)}"
        for i, (x, y) in enumerate(zip(a, b)):
            d = same(x, y, f"{path}[{i}]")
            if d:
                return d
        return ""
    return "" if a == b else f"{path}: {a!r} != {b!r}"


def comparable(res):
    """Drop the human message text (JS has wording, the reference has codes only)."""
    res = json.loads(json.dumps(res))
    if "error" in res:
        res["error"].pop("message", None)
    else:
        for w in res["result"]["warnings"]:
            w.pop("message", None)
    return res


@pytest.fixture(scope="module", params=CONTEXTS, ids=[c[0] for c in CONTEXTS])
def engine_page(request, browser, repo_server):
    tz, locale = request.param
    ctx = browser.new_context(timezone_id=tz, locale=locale)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/tests/harness.html")
    page.wait_for_function("document.getElementById('status').textContent === 'ready'")
    # Chromium may report a zone by its legacy alias (Asia/Calcutta), so check the offset.
    offsets = {"UTC": 0, "America/Toronto": 240, "Asia/Kolkata": -330, "Europe/Berlin": -120}
    assert page.evaluate("new Date(Date.UTC(2026, 8, 1)).getTimezoneOffset()") == offsets[tz]
    yield page
    assert not errors, errors
    ctx.close()


def run_js(page, data):
    return json.loads(page.evaluate("b => window.runEngine(b)", base64.b64encode(data).decode()))


@pytest.mark.parametrize("rel", E.fixture_paths(FIX))
def test_js_matches_reference(engine_page, rel):
    with open(os.path.join(FIX, rel), "rb") as f:
        data = f.read()
    with open(os.path.join(EXP, rel.replace("/", "__") + ".json"), encoding="utf-8") as f:
        want = json.load(f)
    assert want == E.run_fixture(data), "expected/*.json is stale: rerun engine_ref.py --expected"
    raw = run_js(engine_page, data)
    got = comparable(raw)
    diff = same(got, comparable(want))
    assert not diff, f"{rel}: {diff}"
    # with the human messages: an error or warning text never repeats account/name cells (D5)
    assert "CANARY" not in json.dumps(raw), rel


@pytest.mark.parametrize("rel", E.fixture_paths(FIX))
def test_strip_rows_match_reference(engine_page, rel):
    """Step 22: the browser's StrippedRows equal the reference (fixed salt, identity symbol order)."""
    with open(os.path.join(FIX, rel), "rb") as f:
        data = f.read()
    got = json.loads(engine_page.evaluate("([b, s]) => window.stripFixture(b, s)", [base64.b64encode(data).decode(), "SALT-1"]))
    want = E.run_fixture(data)
    if "error" in want:
        assert got is None
        return
    exp = E.strip_rows(want["result"]["trades"], "SALT-1")
    diff = same(got, exp)
    assert not diff, diff
    allowed = {"o", "h", "d", "q", "p", "s", "f"}
    assert all(set(r) == allowed for r in got["rows"])


def test_no_closed_trades_message_names_the_cause(engine_page):
    """Tester D8: the message used to say "every position is still open" whatever the cause."""
    with open(os.path.join(FIX, "errors", "no_closed_skipped_sides.csv"), "rb") as f:
        msg = run_js(engine_page, f.read())["error"]["message"]
    assert "2 rows were skipped (bad side: 2)" in msg, msg
    assert "still open" not in msg, msg
    one = run_js(engine_page, b"Date,Time,Symbol,Side,Quantity,Price\n2026-01-05,09:30:00,AAA,Buy,1,100\n")
    assert "1 position is still open at the end of the file" in one["error"]["message"], one
