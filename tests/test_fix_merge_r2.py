"""Regression tests for the v2-merge pages fix round 2 (TESTER-REPORT-v2-merge-pages-round2-2026-10-21).
One block per finding; repros copied from /home/claude/tester-merge/ (ps_followup*.py, fail3.py,
worker_test.py race, failmodes2.py, lint_evasion.py, nits_test.py) into tests/ and tests/repros/.
"""
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import lint as L  # noqa: E402,F401
import build as B  # noqa: E402,F401
from test_fix_merge import rows_file  # noqa: E402  (the Tester's rows100k.csv shape)

T30 = os.path.join(HERE, "repros", "t30.csv")   # garbage/t30.csv: 30 trades on 2 days
GEN = os.path.join(HERE, "fixtures", "generic")
PS = "/tools/prop-challenge-simulator/"
TS = "/tools/trade-stats/"
PS_RULES = [("#ps-target", "3000"), ("#ps-daily", "1000"), ("#ps-maxloss", "2000"), ("#ps-days", "30"),
            ("#ps-mindays", "5"), ("#ps-seed", "1")]   # ps_followup2.py


@pytest.fixture(scope="module")
def big_file(tmp_path_factory):
    return rows_file(tmp_path_factory.mktemp("r2") / "rows100k.csv", 50_000)


def _page(browser, built_site, path):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(built_site["url"] + path)
    return ctx, page, errors


def _ps_state(page):
    return page.evaluate("""() => ({run_disabled: document.getElementById('ps-run').disabled,
        status: document.getElementById('ps-file-status').textContent,
        file_error: document.getElementById('ps-file-error').hidden ? null : document.getElementById('ps-file-error').innerText,
        progress_hidden: document.getElementById('ps-progress').hidden,
        out_hidden: document.getElementById('ps-out').hidden,
        out: document.getElementById('ps-out').innerText,
        errors: document.getElementById('ps-errors').hidden ? null : document.getElementById('ps-errors').innerText})""")


# ------------------------------------------------------------------ R1: prop-sim Run never stays disabled
def test_r1_run_during_read_then_repick_runs_with_the_new_file(browser, built_site, big_file):
    # ps_followup2.py: Run while rows100k is read, then choose t30 -> Run stayed disabled for good
    ctx, page, errors = _page(browser, built_site, PS)
    for sel, v in PS_RULES:
        page.fill(sel, v)
    page.set_input_files("#ps-file", big_file)
    page.wait_for_timeout(300)
    page.click("#ps-run")
    page.wait_for_timeout(200)
    assert page.evaluate("() => document.getElementById('ps-run').disabled")   # waiting for the read: correct
    page.set_input_files("#ps-file", T30)
    page.wait_for_selector("#ps-out:not([hidden])", timeout=60000)
    st = _ps_state(page)
    ctx.close()
    assert not st["run_disabled"], st
    assert "30 closed trades on 2 trading days" in st["status"], st
    assert "30 trades)" in st["out"], st["out"][:300]    # the run used the newest file
    assert errors == []


@pytest.mark.parametrize("case", ["too_large", "empty_pick"])
def test_r1_cancelled_read_then_run_re_enables_run(browser, built_site, big_file, case):
    # worker_test.py race: toolarge_then_run / empty_pick_then_run (ps_followup.py: the 50 MB second way)
    ctx, page, errors = _page(browser, built_site, PS)
    for sel, v in PS_RULES:
        page.fill(sel, v)
    page.set_input_files("#ps-file", big_file)
    page.wait_for_timeout(300)
    page.click("#ps-run")              # waits for the read
    if case == "too_large":
        page.evaluate("""() => { const i = document.getElementById('ps-file'); const dt = new DataTransfer();
            dt.items.add(new File([new Uint8Array(51 * 1024 * 1024)], 'big.csv')); i.files = dt.files;
            i.dispatchEvent(new Event('change', {bubbles: true})); }""")
    else:
        page.set_input_files("#ps-file", [])
    page.wait_for_function("() => !document.getElementById('ps-run').disabled", timeout=10000)
    st = _ps_state(page)
    page.click("#ps-run")              # and Run works again: it asks for a file
    page.wait_for_selector("#ps-errors:not([hidden])", timeout=5000)
    st2 = _ps_state(page)
    ctx.close()
    assert st["progress_hidden"] and "Reading" not in st["status"], st
    if case == "too_large":
        assert st["file_error"] and "E_TOO_LARGE" in st["file_error"], st
    assert "Choose a trade file" in st2["errors"], st2
    assert errors == []


def test_r1_every_tool_page_uses_the_one_state_helper():
    tools = os.path.join(REPO, "site", "static", "js", "tools")
    for name in ("trade-stats.js", "prop-sim.js", "lot-size.js"):
        src = open(os.path.join(tools, name), encoding="utf-8").read()
        assert "from './tool-state.js'" in src, name
        assert "readTradeFile(" not in src, f"{name} reads files itself instead of through tool-state.js"


# ------------------------------------------------------------------ R2: a failing worker shows an error with a retry
WORKER_FAILURES = {   # fail3.py cases a-d and worker_test.py fail modes
    "404": dict(status=404, body="nope"),
    "throw": dict(status=200, content_type="text/javascript", body="self.onmessage = () => { throw new Error('boom'); };"),
    "crash": dict(status=200, content_type="text/javascript", body="self.onmessage = () => { self.postMessage({crash:'x'}); };"),
    "syntax": dict(status=200, content_type="text/javascript", body="this is not js((("),
    "wrong_id": dict(status=200, content_type="text/javascript", body="self.onmessage = () => { self.postMessage({id: -1, stage: 'parsing'}); };"),
}


def _ui(page, p):
    return page.evaluate("""(p) => { const g = (id) => { const e = document.getElementById(id); return e ? (e.hidden ? null : e.innerText) : '(none)'; };
        return {status: g(p + '-status'), file_status: g(p + '-file-status'), error: g(p + '-error'), file_error: g(p + '-file-error'),
                progress: g(p + '-progress'), out: g(p + '-out')}; }""", p)


@pytest.mark.parametrize("mode", list(WORKER_FAILURES) + ["silent"])
@pytest.mark.parametrize("tool", ["ts", "ps"])
def test_r2_worker_failure_is_shown_with_a_working_retry(browser, built_site, tool, mode):
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    body = WORKER_FAILURES.get(mode, dict(status=200, content_type="text/javascript", body="self.onmessage = () => {};"))
    ctx.route("**/tools/file-worker.js", lambda r: r.fulfill(**body))
    page.goto(built_site["url"] + (TS if tool == "ts" else PS))
    page.set_input_files(f"#{tool}-file", os.path.join(GEN, "ninety_trades.csv"))
    box = "#ts-error" if tool == "ts" else "#ps-file-error"
    page.wait_for_selector(box + ":not([hidden])", timeout=40000)   # silent: the 20 s start timeout
    ui = _ui(page, tool)
    text = page.inner_text(box)
    # then the worker comes back, and "Try again" reads the same file
    ctx.unroute("**/tools/file-worker.js")
    page.click(box + " [data-retry]")
    if tool == "ts":
        page.wait_for_selector("#ts-out:not([hidden])", timeout=30000)
        done = page.inner_text("#ts-out")
    else:
        page.wait_for_function("() => /closed trades? on/.test(document.getElementById('ps-file-status').textContent)", timeout=30000)
        done = page.inner_text("#ps-file-status")
    ctx.close()
    assert "could not be read in this browser" in text and "E_WORKER" in text, text
    assert ui["progress"] is None and not (ui["status"] or ui["file_status"] or "").startswith("Reading"), ui
    assert "90 closed trades" in done, done
    assert errors == [], errors   # shown on the page, not only as an uncaught error


def test_r2_bad_file_error_has_no_retry_button(browser, built_site):
    ctx, page, errors = _page(browser, built_site, TS)
    page.set_input_files("#ts-file", os.path.join(HERE, "fixtures", "errors", "empty.csv"))
    page.wait_for_selector("#ts-error:not([hidden])")
    assert page.query_selector("#ts-error [data-retry]") is None
    assert "E_EMPTY" in page.inner_text("#ts-error")
    ctx.close()


# ------------------------------------------------------------------ R3: only the latest pick may change the page
WORKER_COUNTER = """() => { window.__live = 0; window.__made = 0; const W = window.Worker;
  window.Worker = function (url, opts) { const w = new W(url, opts); if (String(url).includes('file-worker')) {
    window.__made++; window.__live++; const t = w.terminate.bind(w); let done = false;
    w.terminate = () => { if (!done) { done = true; window.__live--; } t(); }; } return w; };
  window.Worker.prototype = W.prototype; }"""
SLOW_FIRST = """() => { const orig = Blob.prototype.arrayBuffer; Blob.prototype.arrayBuffer = function () {
  const p = orig.call(this); return this.name === 'rows100k.csv' ? p.then(b => new Promise(r => setTimeout(() => r(b), 800))) : p; }; }"""


@pytest.mark.parametrize("tool", ["ts", "ps"])
def test_r3_slow_first_file_never_replaces_the_second(browser, built_site, big_file, tool):
    # worker_test.py race, case two_quickly_slow_first_read
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.add_init_script(f"({WORKER_COUNTER})()")
    page.goto(built_site["url"] + (TS if tool == "ts" else PS))
    page.evaluate(SLOW_FIRST)
    page.set_input_files(f"#{tool}-file", big_file)
    page.wait_for_timeout(100)
    page.set_input_files(f"#{tool}-file", T30)
    page.wait_for_timeout(4000)
    if tool == "ts":
        page.wait_for_selector("#ts-noise table", timeout=30000)
    shown = page.inner_text("#ts-out" if tool == "ts" else "#ps-file-status")
    made, live = page.evaluate("() => [window.__made, window.__live]")
    ctx.close()
    if tool == "ts":
        assert "30 closed trades from 60 fills" in shown, shown[:300]
    else:
        assert "30 closed trades on 2 trading days" in shown, shown
    assert "50,000" not in shown
    assert made == 1 and live == 0, (made, live)   # the slow pick never started a worker; none left running
    assert errors == []


@pytest.mark.parametrize("tool", ["ts", "ps"])
def test_r3_superseded_worker_is_terminated_mid_parse(browser, built_site, big_file, tool):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.add_init_script(f"({WORKER_COUNTER})()")
    page.goto(built_site["url"] + (TS if tool == "ts" else PS))
    page.set_input_files(f"#{tool}-file", big_file)
    page.wait_for_function("() => window.__made === 1", timeout=10000)
    page.set_input_files(f"#{tool}-file", T30)
    page.wait_for_function("() => window.__made === 2", timeout=10000)
    live_after_repick = page.evaluate("() => window.__live")
    ctx.close()
    assert live_after_repick == 1   # the first file's worker was terminated at once


def test_r3_worker_answers_carry_the_request_id():
    src = open(os.path.join(REPO, "site", "static", "js", "tools", "file-worker.js"), encoding="utf-8").read()
    assert "self.postMessage({ id, ...m }" in src
    assert re.search(r"self\.postMessage\((?!\{ id, \.\.\.m \})", src) is None, "a worker message without the request id"


# ------------------------------------------------------------------ NIT 6: >50 MB dropped during a read
def test_nit6_too_large_drop_during_read_clears_the_reading_status(browser, built_site, big_file):
    ctx, page, errors = _page(browser, built_site, TS)
    page.set_input_files("#ts-file", big_file)
    page.wait_for_timeout(500)
    page.evaluate("""() => { const dz = document.getElementById('ts-drop'); const dt = new DataTransfer();
      dt.items.add(new File([new Uint8Array(51 * 1024 * 1024)], 'big.csv', {type: 'text/csv'}));
      dz.dispatchEvent(new DragEvent('drop', {dataTransfer: dt, bubbles: true, cancelable: true})); }""")
    page.wait_for_selector("#ts-error:not([hidden])")
    page.wait_for_timeout(3000)
    ui = _ui(page, "ts")
    ctx.close()
    assert "E_TOO_LARGE" in ui["error"] and ui["status"] is None and ui["progress"] is None and ui["out"] is None, ui
    assert errors == []


# ------------------------------------------------------------------ R4: seller fields need a positive shape
# failmodes2.py NAME/PHONE/ADDR_VARIANTS: every "XX" line (built, should have failed), plus more
R4_BAD = {
    "seller_legal_name": [
        "SELLER", "Seller name", "Name", "Address", "PO Box", "test", "unknown", "NA", "n.a.", "(SELLER)", "«SELLER»",
        "［SELLER］", "T​BD", "TO­DO", "ТВD", "ХХХ", "Owner — lawyer to confirm", "Seller name lawyer-to-confirm",
        "Business name — pendng", "Legal name here", "not yet", "later", "asdf", "nil", "aaaa", "0000", "A", "ＴＢＤ",
        "Zzqx &amp; Qqvendor", "Zzqx\nHoldings", "ХХХ Holdings", "Zzqx Qqvеndor",   # Cyrillic е inside a Latin word
        "Zzqx‮Qqvendor Holdings", "Test Company", "Sample Vendor", "Zzqx Qqvendor‍"],
    "premises_address": [
        "TBD", "PO Box", "-", "Address", "ADDRESS — pending", "PO Box 9917, Qqvilletown ON Z9Z 9Z9",   # Z never first
        "PO Box 0, Zzqxville ON K9Z 9Z9", "Main Street, Zzqxville ON K9Z 9Z9", "PO Box 12, Zzqxville XQ K9Z 9Z9",
        "PO Box 12, Zzqxville ON k9z 9z9", "PO Box 12, Zzqxville ON K9Z9Z9", "PO Box 12, Zzqxville ON V9Z 9Z9",
        "PO Box 12, Zzqxville ON K9D 9Z9", "PO Box 12, TBD ON K9Z 9Z9", "PO Box 12 Zzqxville", "PO Box 12, Zzqx​ville ON K9Z 9Z9",
        "[ADDRESS — virtual mailbox pending]", "12 Fake Street, Zzqxville ON K9Z 9Z9", "«PO Box 12», Zzqxville ON K9Z 9Z9"],
    "phone": [
        "555", "0000000", "1111111", "+1 (000) 000-0000", "123-4567", "+1 555 555 5555", "+1 555 555 0199",
        "+1 555 555 0199 ext 12", "+1 555 555 0234​", "(911) 555-0234", "+1 555 911 0234", "+1 195 555 0234",
        "+44 20 7946 0000", "+1 555 555 02345", "[PHONE — pending]", "555-555-0234 call me"],
}
R4_GOOD = {
    "seller_legal_name": ["Zzqx Qqvendor Holdings", "Qqvendor Trading Ltd.", "Société Zzqx Inc.", "Mary-Jane O'Zzqx",
                          "Li Na", "Zzqx Qqvendor Holdings"],
    "premises_address": ["PO Box 9917, Zzqxville ON K9Z 9Z9", "P.O. Box 9917, Zzqxville ON K9Z 9Z9",
                         "Suite 4, 12 Qqvendor Road, Zzqxville ON K9Z 9Z9", "12A Qqvendor Road, St. Zzqx-Ville QC H9Z 9Z9, Canada"],
    "phone": ["+1 555 555 0234", "(555) 555-0234", "555.555.0234 ext 12", "1 555 555 0234", "+1 555 555 0234",
              "５５５ ５５５ ０２３４"],
}


@pytest.mark.parametrize("field,value", [(f, v) for f, vs in R4_BAD.items() for v in vs])
def test_r4_placeholder_shaped_values_are_refused(field, value):
    assert B.seller_problem(field, value), (field, value)


@pytest.mark.parametrize("field,value", [(f, v) for f, vs in R4_GOOD.items() for v in vs])
def test_r4_well_formed_fake_values_pass(field, value):
    assert B.seller_problem(field, value) is None, (field, value, B.seller_problem(field, value))


@pytest.mark.parametrize("flags", [dict(pilot_checkout=True), dict(paid_report=True, trader_first_home=True)],
                         ids=["pilot", "paid"])
@pytest.mark.parametrize("field,value", [("seller_legal_name", "SELLER"), ("seller_legal_name", "T​BD"),
                                         ("seller_legal_name", "ТВD"), ("premises_address", "PO Box"),
                                         ("phone", "0000000"), ("phone", "+1 (000) 000-0000")])
def test_r4_commerce_build_fails_on_second_way_placeholders(tmp_path, flags, field, value):
    # failmodes2.py: these built with rc=0 before the fix
    from test_legal import build, private_with, toml_with, FAKE_API
    extra = {"api": FAKE_API} if "paid_report" in flags else {}
    r, _ = build(tmp_path, "o", DT_SITE_TOML=toml_with(tmp_path, **extra, **flags),
                 DT_PRIVATE_TOML=private_with(tmp_path, **{field: value}))
    assert r.returncode == 1 and "BUILD FAILED" in r.stderr and field in r.stderr, r.stderr


def test_r4_published_value_is_the_normalised_one(tmp_path):
    from test_legal import build, private_with, toml_with
    r, out = build(tmp_path, "o", DT_SITE_TOML=toml_with(tmp_path, pilot_checkout=True),
                   DT_PRIVATE_TOML=private_with(tmp_path, phone="５５５ ５５５ ０２３４"))
    assert r.returncode == 0, r.stderr
    # pilot-only build with the seller switch off renders no seller block: check the value check_private returns
    assert B.check_private({"seller_legal_name": "Zzqx  Qqvendor Holdings", "premises_address": "PO Box 9917, Zzqxville ON K9Z 9Z9",
                            "phone": "５５５ ５５５ ０２３４"}, ["pilot_checkout"]) == {
        "seller_legal_name": "Zzqx Qqvendor Holdings", "premises_address": "PO Box 9917, Zzqxville ON K9Z 9Z9", "phone": "555 555 0234"}


def test_r4_example_placeholders_still_build_with_the_escape(tmp_path):
    from test_legal import build, toml_with
    r, _ = build(tmp_path, "o", DT_SITE_TOML=toml_with(tmp_path, pilot_checkout=True),
                 DT_PRIVATE_TOML=os.path.join(REPO, "site", "config", "private.example.toml"), DT_ALLOW_PLACEHOLDERS="1")
    assert r.returncode == 0 and "WARNING: DT_ALLOW_PLACEHOLDERS=1" in r.stderr, r.stderr
