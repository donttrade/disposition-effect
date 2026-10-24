"""Delivery plan C-4 Part B: the paid pages in headless Chromium against the REHEARSAL Worker.

The Worker is dt-private's deploy bundle on workerd with a local D1 and a mock Stripe
(`node scripts/rehearse.mjs --serve`, in DT_PRIVATE_REPO). The site is a paid, test-mode build of
this checkout. "Pay" on /pricing/ goes to the mock checkout (a route on buy.stripe.com), which
lands on /welcome/?session_id=<a session the mock knows>.

Run: [plain Terminal] DT_PRIVATE_REPO=../dt-private ./site/run.sh test-paid-e2e   (dt-private on delivery-39, after npm ci)
Skipped when DT_PRIVATE_REPO has no rehearsal (scripts/rehearse.mjs) or no wrangler (node_modules).
The tests run in file order; the last one stops the Worker.
"""
import functools
import http.server
import json
import os
import socket
import subprocess
import threading
import urllib.request

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
PRIVATE = os.environ.get("DT_PRIVATE_REPO") or os.path.join(os.path.dirname(REPO), "dt-private")
UPLOAD = os.path.join(HERE, "fixtures", "e2e-upload.csv")
OUTAGE_START = "Your purchase is safe and nothing was counted."
SID = "cs_test_partb" + "0" * 12 + "e2e01"

pytestmark = pytest.mark.skipif(
    not (os.path.isfile(os.path.join(PRIVATE, "scripts", "rehearse.mjs"))
         and os.path.isdir(os.path.join(PRIVATE, "node_modules", "wrangler"))),
    reason="DT_PRIVATE_REPO has no rehearsal (dt-private delivery-39 with npm ci) ")


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


def control(api, path, data=None):
    req = urllib.request.Request(api + "/__rehearsal" + path, data=None if data is None else json.dumps(data).encode(),
                                 method="GET" if data is None else "POST", headers={"content-type": "application/json"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read() or b"null")


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    import sys
    sys.path.insert(0, HERE)
    from test_legal import prices_with_test_link, private_with
    site_port = free_port()
    site = f"http://127.0.0.1:{site_port}"
    sys.path.insert(0, HERE)
    from rehearsal_worker import ServeWorker   # Tester E16: own process group, stops with the test, no workerd left
    worker = ServeWorker(PRIVATE, [site])
    info = worker.info
    api = info["api"]
    tmp = tmp_path_factory.mktemp("partb")
    toml = open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()
    toml = toml.replace("paid_report = false", "paid_report = true").replace("trader_first_home = false", "trader_first_home = true")
    toml = toml.replace('api_base = "http://127.0.0.1:8787"', f'api_base = "{api}"')
    assert f'api_base = "{api}"' in toml
    (tmp / "site.toml").write_text(toml, encoding="utf-8")
    out = tmp / "site"
    env = {**os.environ, "DT_SITE_TOML": str(tmp / "site.toml"), "DT_OUT": str(out),
           "DT_PRIVATE_TOML": private_with(tmp), "DT_PRICES_JSON": prices_with_test_link(tmp), "DT_ALLOW_LOCAL_API": "1"}
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", site_port), functools.partial(Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    st = {"site": site, "api": api, "worker": worker, "versions": info["versions"], "pages": {}}
    yield st
    left = worker.stop()
    srv.shutdown()
    assert left == [], f"workerd children left running: {left}"


@pytest.fixture(scope="module")
def buyer(browser, stack):
    """One buyer's browser profile, kept across the steps (like one person on one device)."""
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    yield {"ctx": ctx, "page": page, "errors": errors}
    ctx.close()


def upload(page, path, wait="#rp-status"):
    page.set_input_files("#rp-file", path)


def wait_status(page, needle, timeout=60000):
    page.wait_for_function("(n) => { const s = document.getElementById('rp-status'); return s && !s.hidden && s.innerText.includes(n); }",
                           arg=needle, timeout=timeout)
    return page.inner_text("#rp-status")


def test_1_before_you_pay_visible_and_printable(buyer, stack):
    page = buyer["page"]
    page.goto(stack["site"] + "/pricing/#before-you-pay")
    byp = page.locator("#before-you-pay")
    assert byp.is_visible()
    assert page.evaluate("typeof window.print") == "function"
    assert page.locator("#before-you-pay [data-print]").count() == 1
    rows = page.eval_on_selector_all("#before-you-pay dl.byp dt", "ds => ds.map(d => d.textContent.trim())")
    for need in ("What you buy", "Price", "Refunds", "Restrictions"):
        assert need in rows, rows
    page.emulate_media(media="print")
    assert byp.is_visible()
    assert page.locator("#before-you-pay dl.byp").is_visible()          # the s. 32 table is kept in print
    assert not page.locator("#before-you-pay .no-print").is_visible()  # the Print button is not printed
    assert not page.locator(".site-header").first.is_visible()
    page.emulate_media(media="screen")


def test_2_pay_lands_on_welcome_with_a_restore_link(buyer, stack):
    page = buyer["page"]
    page.route("https://buy.stripe.com/**", lambda route: route.fulfill(
        status=302, headers={"location": f"{stack['api']}/__rehearsal/checkout?site={stack['site']}&id={SID}"}))
    page.goto(stack["site"] + "/pricing/")
    link = page.locator('a[href^="https://buy.stripe.com/test_"]').first
    link.click()
    page.wait_for_url("**/welcome/**")
    page.wait_for_selector("#w-ready", state="visible", timeout=30000)
    restore = page.input_value("#w-link")
    assert restore.startswith(stack["site"] + "/restore/#") and "t=" in restore, restore
    assert "session_id" not in page.url
    stack["pages"]["restore"] = restore


def test_3_report_from_the_upload_fixture(buyer, stack):
    page = buyer["page"]
    page.click("#w-report")
    page.wait_for_url("**/report/")
    upload(page, UPLOAD)
    page.wait_for_selector("#focus", timeout=60000)
    assert "One re-test left on this purchase." in page.inner_text("#rp-uses")
    st = control(stack["api"], "/state")
    assert [p["uses"] for p in st["purchases"]] == [1] and st["stray_fetches"] == 0, st


def test_4_retest_refused_early_with_the_date_line(buyer, stack):
    page = buyer["page"]
    page.reload()
    upload(page, UPLOAD)
    text = wait_status(page, "The re-test opens 30 days after your first report.")
    assert "Nothing was counted." in text and " UTC, in " in text, text
    assert [p["uses"] for p in control(stack["api"], "/state")["purchases"]] == [1]


def test_5_restore_link_in_a_new_browser_profile(browser, stack):
    ctx = browser.new_context()
    p2 = ctx.new_page()
    p2.goto(stack["pages"]["restore"])
    # wait for the answer itself: #r-open can count as visible before /refresh has answered
    p2.wait_for_function("() => document.getElementById('r-status').innerText.includes('Access restored')", timeout=30000)
    assert not p2.eval_on_selector("#r-open", "e => e.hidden")
    p2.click("#r-open")
    p2.wait_for_url("**/report/")
    assert "Access found on this device." in p2.inner_text("#rp-access")
    ctx.close()


def test_6_after_a_refund_report_shows_the_refunded_message(buyer, stack):
    assert control(stack["api"], "/refund", {"id": SID}) == {"webhook": 200}
    page = buyer["page"]
    page.reload()
    upload(page, UPLOAD)
    text = wait_status(page, "This purchase was refunded")
    assert "no longer opens a report" in text
    st = control(stack["api"], "/state")
    assert st["purchases"][0]["refunded"] == 1 and st["prints"] == 0, st


def test_7_unparseable_file_shows_the_parse_error_and_sends_nothing(browser, stack, tmp_path):
    bad = tmp_path / "not-a-trade-file.csv"
    bad.write_text("hello,world\nthis is not,a trade export\n", encoding="utf-8")
    sid = control(stack["api"], "/session", {"id": "cs_test_partbbadfile00000001"})["id"]
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(stack["site"] + "/welcome/?session_id=" + sid)
    page.wait_for_selector("#w-ready", state="visible", timeout=30000)
    page.click("#w-report")
    page.wait_for_url("**/report/")
    before = control(stack["api"], "/calls").get("/analyse", 0)
    state_before = control(stack["api"], "/state")
    sent = []
    page.on("request", lambda r: sent.append(r.url) if r.url.endswith("/analyse") else None)
    upload(page, str(bad))
    page.wait_for_function("() => { const s = document.getElementById('rp-status'); return s && !s.hidden && s.classList.contains('notice-error'); }", timeout=30000)
    msg = page.inner_text("#rp-status")
    assert msg.strip() and "Sending" not in msg, msg
    page.wait_for_timeout(500)
    assert control(stack["api"], "/calls").get("/analyse", 0) == before   # the Worker saw 0 /analyse calls
    assert sent == []
    st = control(stack["api"], "/state")
    assert st["first_runs"] == state_before["first_runs"] and [p["uses"] for p in st["purchases"]] == [p["uses"] for p in state_before["purchases"]]
    ctx.close()


def test_8_worker_stopped_report_and_welcome_show_the_outage_text(browser, buyer, stack):
    # A second buyer has access saved before the outage.
    sid = control(stack["api"], "/session", {"id": "cs_test_partboutage0000000001"})["id"]
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(stack["site"] + "/welcome/?session_id=" + sid)
    page.wait_for_selector("#w-ready", state="visible", timeout=30000)
    assert stack["worker"].stop() == []   # Tester E16: no workerd left behind
    page.goto(stack["site"] + "/report/")
    upload(page, UPLOAD)
    text = wait_status(page, OUTAGE_START)
    assert "try again" in text.lower()
    p3 = ctx.new_page()
    p3.goto(stack["site"] + "/welcome/?session_id=cs_test_partboutage0000000002")
    p3.wait_for_selector("#w-error", state="visible", timeout=30000)
    assert OUTAGE_START in p3.inner_text("#w-error-msg")
    assert p3.locator("#w-retry").is_visible() and "Try again" in p3.inner_text("#w-retry")
    assert not buyer["errors"], buyer["errors"]
    ctx.close()
