"""Step 22: the browser paid flow against the private dev server with a stubbed Stripe.

Needs ../dt-private (the paid-analysis server is not in this repo); skipped without it.
Checks: what the browser sends is only whitelisted keys, no symbol text, every `o`
smaller than the file span plus one week; the canary never leaves the browser;
blocked storage still shows the report and offers the restore file; an outage
shows "purchase safe, nothing counted".
"""
import functools
import http.server
import json
import os
import socket
import subprocess
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
# The paid-analysis server checkout. DT_PRIVATE_REPO picks one (the delivery plan's name); the default is
# ../dt-private. The report page renders only reports of the method its wording describes
# (wording.js METHOD_VERSION), so the server must be on the same method (R2: dt-private delivery-39).
PRIVATE = os.environ.get("DT_PRIVATE_REPO") or os.path.join(os.path.dirname(REPO), "dt-private")
sys.path.insert(0, os.path.join(HERE, "reference"))
import engine_ref as E  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.isdir(PRIVATE), reason="dt-private (server) not present")
# 40 trades: the server refuses a report on fewer than 30 (nothing is counted).
FIXTURE = os.path.join(HERE, "fixtures", "mt5", "deals_netting_40.htm")
SYMBOLS = ["EURUSD", "XAUUSD", "GBPUSD", "USDJPY"]
ROW_KEYS = {"o", "h", "d", "q", "p", "s", "f"}
REQ_KEYS = {"v", "token", "rows", "currency", "pgr_plr", "firm_name", "firm_consent"}


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


@pytest.fixture(scope="module")
def stack(tmp_path_factory):
    site_port, api_port = free_port(), free_port()
    site_origin, api = f"http://127.0.0.1:{site_port}", f"http://127.0.0.1:{api_port}"
    tmp = tmp_path_factory.mktemp("paid")
    toml = open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()
    toml = toml.replace("paid_report = false", "paid_report = true").replace("trader_first_home = false", "trader_first_home = true")
    toml = toml.replace('api_base = "http://127.0.0.1:8787"', f'api_base = "{api}"')
    (tmp / "site.toml").write_text(toml, encoding="utf-8")
    out = tmp / "site"
    from test_legal import prices_with_test_link, private_with
    # well-formed fake seller and Stripe test link; only the local dev server's http address needs an escape
    env = {**os.environ, "DT_SITE_TOML": str(tmp / "site.toml"), "DT_OUT": str(out),
           "DT_PRIVATE_TOML": private_with(tmp), "DT_PRICES_JSON": prices_with_test_link(tmp), "DT_ALLOW_LOCAL_API": "1"}
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", site_port), functools.partial(Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    dev = subprocess.Popen(["node", "--no-warnings", "src/adapters/dev-server.mjs"], cwd=PRIVATE,
                           env={**os.environ, "DT_FAKE_STRIPE": "1", "DT_PORT": str(api_port),
                                "DT_ALLOWED_ORIGINS": site_origin}, stdout=subprocess.PIPE, text=True)
    assert "dev server on" in dev.stdout.readline()
    yield {"site": site_origin, "api": api}
    dev.terminate()
    srv.shutdown()


def new_session(page, stack, sid):
    page.request.post(stack["api"] + "/__test/session", data=json.dumps({"id": sid}))
    return sid


def run_report(page, stack, sent):
    page.on("request", lambda req: sent.append(req))
    page.set_input_files("#rp-file", FIXTURE)
    page.wait_for_selector("#focus", timeout=30000)


def test_full_flow_sends_only_stripped_rows(browser, stack):
    ctx = browser.new_context()
    page = ctx.new_page()
    sid = new_session(page, stack, "cs_test_flow0000000001")
    page.goto(stack["site"] + "/welcome/?session_id=" + sid)
    page.wait_for_selector("#w-ready", state="visible")
    assert "session_id" not in page.url
    assert page.evaluate("localStorage.getItem('donttrade-access')")
    page.click("#w-report")
    page.wait_for_url("**/report/")
    assert "#t=" not in page.url  # the token is moved out of the address bar
    sent = []
    run_report(page, stack, sent)
    analyse = [r for r in sent if r.url.endswith("/analyse")]
    assert len(analyse) == 1
    body = json.loads(analyse[0].post_data)
    assert set(body) == REQ_KEYS
    assert all(set(row) == ROW_KEYS for row in body["rows"])
    raw = analyse[0].post_data
    for s in SYMBOLS + ["CANARY"]:
        assert s not in raw, s
    trades = E.parse_file(open(FIXTURE, "rb").read())["trades"]
    span_min = (max(t["close_ts"] for t in trades) - min(t["open_ts"] for t in trades)) // 60000
    assert all(row["o"] < span_min + 7 * 24 * 60 for row in body["rows"])
    for r in sent:
        assert r.url.startswith(stack["site"]) or r.url.startswith(stack["api"]), r.url
        assert "CANARY" not in (r.post_data or "") and "CANARY" not in r.url
    assert "CANARY" not in page.content()
    # the 40-trade MT5 file is coarse-time under stats2e (25% of its opens at one minute of the day): nothing tested
    assert "None of the patterns could be tested in this file, so this report describes them without a verdict." in page.inner_text("#focus")
    db = page.request.get(stack["api"] + "/__test/db").text()
    for s in SYMBOLS + ["CANARY"]:
        assert s not in db
    ctx.close()


def test_blocked_storage_still_shows_report_and_offers_restore(browser, stack):
    ctx = browser.new_context(accept_downloads=True)
    ctx.add_init_script("""
        Object.defineProperty(window, 'localStorage', {get() { throw new DOMException('blocked', 'SecurityError'); }});
        Object.defineProperty(window, 'indexedDB', {get() { throw new DOMException('blocked', 'SecurityError'); }});
    """)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    sid = new_session(page, stack, "cs_test_blocked0000001")
    page.goto(stack["site"] + "/welcome/?session_id=" + sid)
    page.wait_for_selector("#w-ready", state="visible")
    assert "blocks saving" in page.inner_text("#w-saved")
    with page.expect_download() as dl:
        page.click("#w-download")
    assert dl.value.suggested_filename == "donttrade-restore.html"
    page.click("#w-report")
    page.wait_for_url("**/report/")
    run_report(page, stack, [])
    with page.expect_download() as dl2:
        page.click("#rp-restore-file")
    assert dl2.value.suggested_filename == "donttrade-restore.html"
    assert not errors, errors
    ctx.close()


def test_outage_message(browser, stack):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.route("**/redeem", lambda route: route.abort())
    page.goto(stack["site"] + "/welcome/?session_id=cs_test_outage00000001")
    page.wait_for_selector("#w-error", state="visible")
    assert "purchase is safe and nothing was counted" in page.inner_text("#w-error-msg")
    ctx.close()


def test_restore_by_link_only(browser, stack):
    """Restore-by-email is not in v1 (decision 20 Oct): the link works, there is no email form or endpoint.
    Owner decision 21 Oct ~11:00 (manual restore = YES): the only mention of email is the manual-help line."""
    ctx = browser.new_context()
    page = ctx.new_page()
    sid = new_session(page, stack, "cs_test_restore0000001")
    page.goto(stack["site"] + "/welcome/?session_id=" + sid)
    page.wait_for_selector("#w-ready", state="visible")
    link = page.input_value("#w-link")
    fresh = browser.new_context()
    p2 = fresh.new_page()
    p2.goto(link)
    p2.wait_for_selector("#r-open", state="visible")
    assert "Access restored" in p2.inner_text("#r-status")
    assert p2.locator("input[type=email], #r-form").count() == 0
    main = p2.inner_text("main")
    manual = p2.inner_text("#r-manual")
    assert "email us from the address you paid with" in manual
    assert "email" not in main.replace(manual, "").lower()
    gone = p2.request.post(stack["api"] + "/restore", data=json.dumps({"email": "buyer@example.com"}),
                           headers={"content-type": "application/json", "origin": stack["site"]})
    assert gone.status == 404
    fresh.close()
    ctx.close()
