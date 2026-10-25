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
    ctx.route("**/tools/file-worker.js?v=*", lambda r: r.fulfill(**body))
    page.goto(built_site["url"] + (TS if tool == "ts" else PS))
    page.set_input_files(f"#{tool}-file", os.path.join(GEN, "ninety_trades.csv"))
    box = "#ts-error" if tool == "ts" else "#ps-file-error"
    page.wait_for_selector(box + ":not([hidden])", timeout=40000)   # silent: the 20 s start timeout
    ui = _ui(page, tool)
    text = page.inner_text(box)
    # then the worker comes back, and "Try again" reads the same file
    ctx.unroute("**/tools/file-worker.js?v=*")
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
        page.wait_for_selector("#ts-out:not([hidden])", timeout=30000)   # C1: the table only with free_badges
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


# ------------------------------------------------------------------ R5: a paid build sells; nothing says "not on sale"
@pytest.fixture(scope="module")
def paid_site(tmp_path_factory):
    import functools
    import http.server
    import threading
    from conftest import _Quiet
    from test_legal import build, paid_env
    tmp = tmp_path_factory.mktemp("r2-paid")
    r, out = build(tmp, "on", **paid_env(tmp))
    assert r.returncode == 0, r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


def _html_files(out):
    for root, _, files in os.walk(out):
        for n in files:
            if n.endswith(".html"):
                fp = os.path.join(root, n)
                yield "/" + os.path.relpath(fp, out), open(fp, encoding="utf-8").read()


def test_r5_no_page_of_a_paid_build_says_not_on_sale(paid_site):
    # the Tester's grep: "Not on sale yet\|Coming soon; join the waitlist\|Join the waitlist — $39", widened
    hits = [(rel, d) for rel, h in _html_files(paid_site["out"]) for _, _, d in L.not_on_sale_claims(L.readable_text(h), rel)]
    assert hits == []


@pytest.mark.parametrize("path", ["/tools/trade-stats/", "/tools/lot-size-calculator/", "/tools/prop-challenge-simulator/",
                                  "/for-traders/", "/start/", "/for-traders/thanks/"])
def test_r5_trader_blocks_sell_in_a_paid_build(paid_site, path):
    h = open(os.path.join(paid_site["out"], path.strip("/"), "index.html"), encoding="utf-8").read()
    assert 'href="/pricing/#last-step">Get the habit report — $39</a>' in h   # af52207: buy buttons open the pay panel
    assert 'product" value="waitlist"' not in h and 'id="wl"' not in h   # the waitlist form is gone
    assert "/for-traders/#waitlist" not in h


def test_r5_flag_off_build_keeps_the_waitlist(built_site):
    for path in ("tools/trade-stats", "tools/lot-size-calculator", "tools/prop-challenge-simulator", "for-traders"):
        h = open(os.path.join(built_site["out"], path, "index.html"), encoding="utf-8").read()
        assert "Join the waitlist — $39 founding price" in h and "Not on sale yet" in h, path
        assert 'data-on-sale="false"' in h or path == "for-traders"


def test_r5_passthrough_nav_drops_coming_soon_only_when_paid(paid_site, built_site):
    # steps 28–29: /about/ (lifted) has the v2 header, whose trader link never says "coming soon"
    for out in (paid_site["out"], built_site["out"]):
        h = open(os.path.join(out, "about", "index.html"), encoding="utf-8").read()
        nav = h[h.index('<nav class="site-nav"'):h.index("</nav>")]
        assert "coming soon" not in nav.lower() and 'href="/for-traders/"' in nav
    paid = open(os.path.join(paid_site["out"], "about", "index.html"), encoding="utf-8").read()
    assert 'Individual traders <span class="soon">coming soon</span>' not in paid


def test_r5_paid_metadata_and_faq_jsonld(paid_site):
    h = open(os.path.join(paid_site["out"], "for-traders", "index.html"), encoding="utf-8").read()
    meta = L.meta_text(h)
    assert "waitlist" not in meta.lower() and "launch date" not in meta.lower() and "How do I buy it?" in meta


def test_r5_tool_teaser_script_wording_follows_the_offer(browser, paid_site, built_site):
    # owner, 25 Oct: a paid build has no teaser box; partials/tool_next_step.html is the one offer, the same
    # words before and after a run (never the visitor's numbers). The flag-off build keeps the waitlist teaser.
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(paid_site["url"] + TS)
    before = page.inner_text(".next-step")
    page.click("#ts-sample-btn")
    page.wait_for_selector("#ts-out:not([hidden])", timeout=60000)
    page.wait_for_timeout(300)
    assert page.locator("#ts-teaser").count() == 0
    assert page.inner_text(".next-step") == before and before.startswith("Want to go one level deeper?")
    assert page.evaluate("document.querySelector('#ts-out').nextElementSibling.classList.contains('next-step')")
    ctx.close()
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + TS)
    assert page.locator(".next-step").count() == 0
    page.click("#ts-sample-btn")
    page.wait_for_selector("#ts-teaser:not([hidden])", timeout=60000)
    assert "We're building a habit report" in page.inner_text("#ts-teaser")
    ctx.close()


@pytest.mark.parametrize("plant", ["<p>Not on sale yet.</p>", "<p>Join the wait&#108;ist</p>",
                                   '<meta name="description" content="Coming soon; join the waitlist.">'])
def test_r5_lint_fails_a_paid_build_that_says_waitlist(paid_site, tmp_path, plant):
    import shutil
    out = tmp_path / "site"
    shutil.copytree(paid_site["out"], out)
    for rel in ("tools/trade-stats/index.html", "about/index.html"):   # a template page and a lifted page
        fp = out / rel
        fp.write_text(fp.read_text(encoding="utf-8").replace("</head>", plant + "</head>", 1).replace("<main", plant + "<main", 1), encoding="utf-8")
    problems = L.lint_build(str(out), paid=True)
    where = {w for r, w, _ in problems if r == "claim:not_on_sale"}
    assert {"/tools/trade-stats/", "/about/"} <= where, problems


# ------------------------------------------------------------------ R6: the French legal pages promise what the English ones do
LEGAL_PAIRS = [("pricing", "fr/avant-de-payer"), ("terms", "fr/conditions"), ("privacy", "fr/confidentialite")]
# (English promise, French promise): each pair is on both pages of a language pair, or on neither
PROMISES = [
    (r"we (email|send) you a copy|copy of (this summary|the terms) by email|confirmation email",
     r"envoyons par courriel une copie|courriel de confirmation|copie de ce résumé"),
    (r"privacy breach creates a real risk of significant harm to you, we tell you", r"incident de confidentialité présente un risque de préjudice sérieux pour vous, nous vous en avisons"),
    (r"down for more than 24 hours, we refund you on request", r"interrompu plus de 24 heures, nous vous remboursons sur demande"),
    (r"a person reviews it and writes to you before anything is paused", r"une personne examine la situation et vous écrit avant toute suspension"),
    (r"We reply within 30 days", r"Nous répondons dans les 30 jours"),
]


def _text(out, rel):
    return re.sub(r"\s+", " ", L.visible_text(open(os.path.join(out, rel, "index.html"), encoding="utf-8").read()))


@pytest.mark.parametrize("en,fr", LEGAL_PAIRS)
def test_r6_french_and_english_make_the_same_promises(paid_site, en, fr):
    te, tf = _text(paid_site["out"], en), _text(paid_site["out"], fr)
    for pe, pf in PROMISES:
        assert bool(re.search(pe, te, re.I)) == bool(re.search(pf, tf, re.I)), (en, fr, pe, pf)


def test_r6_no_terms_copy_email_is_promised_for_the_39_report(paid_site):
    # TESTER R6 repro: fr/avant-de-payer "Votre copie" row and fr/conditions §11
    for rel in ("pricing", "terms", "welcome", "fr/avant-de-payer", "fr/conditions", "fr/confidentialite"):
        t = _text(paid_site["out"], rel)
        assert not re.search(PROMISES[0][0] + "|" + PROMISES[0][1] + "|Votre copie", t, re.I), rel


# ------------------------------------------------------------------ NIT 1: the wording checker reads what a person reads
# lint_evasion.py: every variant renders (in a browser) as the banned text
EVADE_TALLY = ["Forms open on Tally.", "TALLY forms", "T&#97;lly forms", "&#x54;ally forms", "Ta&#108;&#108;y",
               "Ta<span>lly</span> forms", "Tal<b></b>ly forms", "Tal<wbr>ly forms", "Tal­ly forms", "Tal&shy;ly forms",
               "Ta​lly forms", "Tаlly forms", "Tal<!-- -->ly forms", '<a href="https://tally.so/r/x">form</a>',
               '<a href="https://t&#97;lly.so/r/x">form</a>', '<a href="https://%74ally.so/r/x">form</a>', "ＴＡＬＬＹ forms"]
EVADE_RESTORE = ["You can restore by email.", "RESTORE BY EMAIL any time.", "Restore by e&#109;ail any time.",
                 "Restore by <b>email</b> any time.", "Restore by e<span>mail</span> any time.", "Restore by e<wbr>mail.",
                 "Restore by e­mail.", "Restore by e​mail.", "Restore by email.", "Restore&nbsp;by&nbsp;email.",
                 "Get your access back by email.", "Lost it? We can email you a new link.", "Recover the report via e-mail.",
                 "Restore using your email address.", "Restore it by emailing us.",
                 "Restore by email is not offered. Restore by email here instead."]
EVADE_ADVICE = ["This is advice.", "We RECOMMEND it.", "We rec&#111;mmend it.", "We re<b>commend</b> it.",
                "We recom<span>mend</span> it.", "We recom­mend it.", "We recom&shy;mend it.", "We recom​mend it.",
                "We recоmmend it.", "<a href='/' aria-label='our advice'>x</a>", "<a href=/ title=advice>x</a>",
                "This is not advice: you should buy now.", "Results are certified.", "Results are ver&#105;fied.",
                "You sho<i>uld</i> sell.", "We ｒｅｃｏｍｍｅｎｄ it."]
EVADE_HEAD = ['<meta name="description" content="We recommend you should buy this.">',
              '<meta property="og:description" content="We recommend you should buy this.">',
              '<meta name="twitter:description" content="We rec&#111;mmend it.">',
              '<meta content="We recommend it." name="description">',
              '<script type="application/ld+json">{"@type":"WebPage","description":"We recommend you should buy this."}</script>',
              '<script type="application/ld+json">{"@graph":[{"@type":"FAQPage","mainEntity":[{"acceptedAnswer":{"text":"We recommend it."}}]}]}</script>']


def _plant(html, snippet, head=False):
    if head:
        return html.replace("</head>", snippet + "</head>", 1)
    i = html.find("</main>")
    return html[:i] + "<p>" + snippet + "</p>" + html[i:]


@pytest.fixture(scope="module")
def pages(built_site, paid_site):
    rd = lambda out, rel: open(os.path.join(out, rel), encoding="utf-8").read()  # noqa: E731
    return {"owned": rd(built_site["out"], "for-traders/index.html"), "pass": rd(built_site["out"], "about/index.html"),
            "welcome": rd(paid_site["out"], "welcome/index.html")}


def _owned(html, paid=False):
    return L.lint_html(html, "/x/", paid, False, L.allowed_amounts(), [])


@pytest.mark.parametrize("snippet", EVADE_TALLY)
@pytest.mark.parametrize("kind", ["owned", "pass"])
def test_nit1_tally_evasions_are_caught(pages, kind, snippet):
    html = _plant(pages[kind], snippet)
    found = _owned(html) if kind == "owned" else L.passthrough_rules(html, "/about/index.html", False)
    assert any(r == "tally" for r, _, _ in found), snippet


@pytest.mark.parametrize("snippet", EVADE_RESTORE)
@pytest.mark.parametrize("kind", ["welcome", "pass"])
def test_nit1_restore_by_email_evasions_are_caught(pages, kind, snippet):
    html = _plant(pages[kind], snippet)
    found = _owned(html, paid=True) if kind == "welcome" else L.passthrough_rules(html, "/about/index.html", False, True)
    assert any(r == "claim:restore_email" for r, _, _ in found), snippet


@pytest.mark.parametrize("snippet", EVADE_ADVICE)
def test_nit1_adviser_word_evasions_are_caught(pages, snippet):
    assert any(r.startswith("banned:") for r, _, _ in _owned(_plant(pages["owned"], snippet))), snippet


@pytest.mark.parametrize("snippet", EVADE_HEAD)
def test_nit1_meta_og_and_jsonld_text_is_linted(pages, snippet):
    assert any(r.startswith("banned:") for r, _, _ in _owned(_plant(pages["owned"], snippet, head=True))), snippet


@pytest.mark.parametrize("expr", ["'Restore by email any time'", "'Restore by ' + 'email'", "'Restore by \\u0065mail'",
                                  "`Restore by ${'email'}`", "'Restore by \\x65mail'", "'Restore by \\u{65}mail'",
                                  "['Restore','by','email'].join(' ')", "`Get your access back by ${x} email`"])
def test_nit1_js_string_evasions_are_caught(expr):
    assert L.restore_email_claims(L.js_strings(f"const _planted = {expr};"), "welcome.js"), expr


def test_nit1_clean_builds_still_pass(built_site, paid_site, monkeypatch):
    assert L.lint_build(str(built_site["out"])) == []
    # delta N2: lint is told which private.toml the paid build used (paid_env wrote it beside the build)
    monkeypatch.setenv("DT_PRIVATE_TOML", str(paid_site["out"].parent / "paid-private.toml"))
    assert L.lint_build(str(paid_site["out"]), paid=True) == []


# ------------------------------------------------------------------ NIT 7: no dead "Try again" on /welcome/
@pytest.mark.parametrize("query", ["", "?session_id=", "?session_id"])
def test_nit7_welcome_without_a_session_shows_no_retry_button(browser, paid_site, query):
    ctx = browser.new_context()
    page = ctx.new_page()
    requests = []
    page.on("request", lambda r: requests.append(r.url) if "/redeem" in r.url else None)
    page.goto(paid_site["url"] + "/welcome/" + query)
    page.wait_for_selector("#w-error:not([hidden])")
    visible = page.is_visible("#w-retry")
    msg = page.inner_text("#w-error")
    ctx.close()
    assert not visible and "No checkout was found" in msg and requests == []


# ------------------------------------------------------------------ NIT 3, 4: site.toml shape errors are BUILD FAILED lines
def _toml_edit(tmp, sub, repl, **flags):
    from test_legal import toml_with
    p = toml_with(tmp, "edited.toml", **flags)
    src = open(p, encoding="utf-8").read()
    new, n = re.subn(sub, repl, src, flags=re.M)
    assert n, sub
    open(p, "w", encoding="utf-8").write(new)
    return p


@pytest.mark.parametrize("sub,repl,flags,expect", [
    (r"^\[flags\]\n(?:[a-z_]+ = .*\n)+", "", {}, "no [flags] table"),                                     # NIT 3
    (r'^api_base = .*\n', "", {"paid_report": True, "trader_first_home": True}, "[worker] api_base is missing"),  # NIT 3
    (r"^show_seller_for_pilot = false", "show_seller_for_pilt = true", {}, "show_seller_for_pilt is not a known key"),  # NIT 4
    (r"^\[stripe\]\n", "[stripe]\nmdoe = \"live\"\n", {}, "mdoe is not a known key"),
])
def test_nit3_nit4_site_toml_shape_errors_fail_cleanly(tmp_path, sub, repl, flags, expect):
    from test_legal import build
    r, _ = build(tmp_path, "o", DT_SITE_TOML=_toml_edit(tmp_path, sub, repl, **flags))
    assert r.returncode == 1 and "BUILD FAILED" in r.stderr and expect in r.stderr and "Traceback" not in r.stderr, r.stderr


# ------------------------------------------------------------------ NIT 5: api_base IDN TLD and port; NBSP phone
@pytest.mark.parametrize("api,ok", [("https://api.xn--p1ai", True), ("https://api.zzqx-fixture.xn--p1ai:8443", True),
                                    ("https://api.zzqx-fixture.ca:00443", False), ("https://api.zzqx-fixture.ca:0443", False),
                                    ("https://api.zzqx-fixture.ca:443", True), ("https://api.xn--", False),
                                    ("https://10.0.0.1", False)])
def test_nit5_api_base_idn_tld_and_port_leading_zero(api, ok):
    assert (B.api_base_problem(api) is None) == ok, (api, B.api_base_problem(api))


def test_nit5_phone_with_nbsp_is_accepted_and_published_plain():
    assert B.seller_problem("phone", "+1 555 555 0234") is None
    assert B.normalise_private("+1 555 555 0234")[0] == "+1 555 555 0234"


# ------------------------------------------------------------------ NIT 9: ?product=pilot never retags the enquiry forms
@pytest.fixture(scope="module")
def pilot_site(tmp_path_factory):
    import functools
    import http.server
    import threading
    from conftest import _Quiet
    from test_legal import build, private_with, toml_with
    tmp = tmp_path_factory.mktemp("r2-pilot")
    r, out = build(tmp, "p", DT_SITE_TOML=toml_with(tmp, pilot_checkout=True), DT_PRIVATE_TOML=private_with(tmp))
    assert r.returncode == 0, r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


# v3: /start/ has no enquiry form any more; each product section has a fixed product (C3), so a URL saying
# "pilot" cannot turn a Snapshot, Memo or Outcomes request into a Pilot request either
@pytest.mark.parametrize("path,form,expect", [("/start/?product=pilot#memo", "#sf-memo", "memo"),
                                              ("/for-firms/?product=pilot", "#ff", "enquiry"),
                                              ("/start/?product=PILOT#snapshot", "#sf-snapshot", "snapshot"),
                                              ("/start/?product=memo#outcomes", "#sf-outcomes", "outcomes")])
def test_nit9_enquiry_form_refuses_pilot_from_the_url(browser, pilot_site, path, form, expect):
    from urllib.parse import parse_qs
    ctx = browser.new_context()
    pg = ctx.new_page()
    posted = []
    pg.route("https://api.web3forms.com/**", lambda route: (posted.append(route.request.post_data or ""),
                                                             route.fulfill(status=200, body="ok")))
    pg.goto(pilot_site["url"] + path)
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")  # the enquiry form sits in a <details>
    pg.fill(form + " input[type=email]", "test-ignore@example.org")
    pg.fill(form + " input[name=firm]", "TEST - ignore")
    pg.click(form + " button[type=submit]")
    pg.wait_for_timeout(400)
    ctx.close()
    assert len(posted) == 1
    assert parse_qs(posted[0])["product"][0] == expect


def test_nit9_flag_off_firm_form_still_takes_pilot(browser, built_site):
    from test_fix_merge import _post
    assert _post(browser, built_site["url"] + "/start/?product=pilot#pilot", "#sf-pilot")["product"] == "pilot"


# ------------------------------------------------------------------ NIT 2, 16: lint reads the same config as the build
def _lint_cli(*args, **env):
    return subprocess.run([sys.executable, os.path.join(REPO, "checks", "lint.py"), *args],
                          capture_output=True, text=True, env={**os.environ, **env})


def test_nit2_lint_uses_dt_site_toml_seller_switch(tmp_path):
    from test_legal import build, private_with, toml_with
    toml = _toml_edit(tmp_path, r"^show_seller_for_pilot = false", "show_seller_for_pilot = true", pilot_checkout=True)
    priv = private_with(tmp_path)
    r, out = build(tmp_path, "ps", DT_SITE_TOML=toml, DT_PRIVATE_TOML=priv)
    assert r.returncode == 0, r.stderr
    assert "data-seller-block" in (out / "privacy" / "index.html").read_text(encoding="utf-8")
    r = _lint_cli(str(out), DT_SITE_TOML=toml, DT_PRIVATE_TOML=priv)
    assert r.returncode == 0 and "PASS" in r.stdout, r.stdout   # before: 3 false flag:seller_block problems


def test_nit2_lint_reads_dt_private_toml_and_names_the_switch(tmp_path):
    from test_legal import FAKE, build, private_with, toml_with
    toml, priv = toml_with(tmp_path, pilot_checkout=True), private_with(tmp_path)
    r, out = build(tmp_path, "p", DT_SITE_TOML=toml, DT_PRIVATE_TOML=priv)
    assert r.returncode == 0, r.stderr
    fp = out / "about" / "index.html"
    fp.write_text(fp.read_text(encoding="utf-8").replace("</main>", f"<p>{FAKE['premises_address']}</p><p data-seller-block></p></main>"),
                  encoding="utf-8")
    r = _lint_cli(str(out), DT_SITE_TOML=toml, DT_PRIVATE_TOML=priv)
    assert r.returncode == 1 and "flag:seller_identity" in r.stdout, r.stdout
    assert "every commerce flag off" not in r.stdout


def test_nit16_lint_on_a_missing_directory_is_one_clear_line(tmp_path):
    r = _lint_cli(str(tmp_path / "nonexistent"))
    assert r.returncode == 2 and "no such directory" in r.stdout and "page missing" not in r.stdout, r.stdout


# ------------------------------------------------------------------ NIT 8, 13: welcome and footer wording
def test_nit8_welcome_does_not_assume_a_stripe_receipt():
    js = open(os.path.join(REPO, "site", "static", "js", "paid", "welcome.js"), encoding="utf-8").read()
    assert "receipt" not in L.js_strings(js).lower()
    assert "with the date and amount of your payment" in js


def test_nit13_paid_footer_mentions_the_kept_fingerprints(paid_site):
    line = B.footer_privacy({"paid_report": True, "pilot_checkout": False, "analytics": False})
    # C-14 (23 Oct): "only" now bounds what is kept of the trade numbers (the server keeps other records too)
    assert "does not keep them: of those numbers it keeps only a scrambled fingerprint" in line
    privacy = L.visible_text((paid_site["out"] / "privacy" / "index.html").read_text(encoding="utf-8"))
    assert "scrambled fingerprints of the trades in your first report" in privacy   # what the footer now points at
    assert line in (paid_site["out"] / "about" / "index.html").read_text(encoding="utf-8")


# ------------------------------------------------------------------ Extra: CNH (offshore yuan, written by IBKR)
CNH_FIX = os.path.join(HERE, "fixtures", "ibkr", "cnh_offshore_yuan.csv")


def test_cnh_is_on_the_reference_list_and_read_as_a_currency():
    sys.path.insert(0, os.path.join(HERE, "reference"))
    import engine_ref as E
    assert "CNH" in E.ISO_CURRENCIES and "CNY" in E.ISO_CURRENCIES and E.ISO_CURRENCIES == sorted(E.ISO_CURRENCIES)
    r = E.parse_file(open(CNH_FIX, "rb").read())
    assert r["currency_groups"] == {"CNH": 2} and {t["pnl_unit"] for t in r["trades"]} == {"CNH"}
    assert "W_CURRENCY_IGNORED" not in {w["code"] for w in r["warnings"]}   # before: the column was ignored, unit "points"


def test_cnh_file_on_the_trade_stats_page(browser, built_site):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + TS)
    page.set_input_files("#ts-file", CNH_FIX)
    page.wait_for_selector("#ts-out:not([hidden])", timeout=30000)
    text = page.inner_text("#ts-out")
    ctx.close()
    assert "Amounts are in CNH." in text and "2 closed trades" in text and "price points" not in text


def test_cnh_on_the_server_list_too():
    src = open(os.path.join(REPO, "..", "dt-private", "src", "core", "currencies.mjs"), encoding="utf-8").read() \
        if os.path.isdir(os.path.join(REPO, "..", "dt-private")) else None
    if src is None:
        pytest.skip("dt-private not present next to this checkout")
    assert "'CLP', 'CNH', 'CNY'," in src
