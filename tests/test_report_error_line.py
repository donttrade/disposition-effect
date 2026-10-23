"""R-D1 D-2: when wording.js refuses a report (here a stats1 report: checkMethod throws), /report/ shows
exactly the report-error line, with site.toml's contact_email written in at build time, and nothing else
from the report: no habit name, no number, no "$". The Worker is a Playwright route (no server needed)."""
import functools
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading
import tomllib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import lint_text  # noqa: E402
from test_legal import prices_with_test_link, private_with  # noqa: E402

CONTACT = tomllib.load(open(os.path.join(REPO, "site/config/site.toml"), "rb"))["site"]["contact_email"]
EXPECTED = ("This report could not be shown, so nothing from it is displayed. "
            f"To tell us, email {CONTACT} from the address you paid with.")
API = "http://127.0.0.1:9"  # never reached: every call is routed
HABIT_WORDS = ["Holding", "Re-entering", "Size after", "Trading more", "Oversized", "hold_gap", "revenge", "size_up", "tilt"]


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("rperr")
    toml = open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()
    toml = toml.replace("paid_report = false", "paid_report = true").replace("trader_first_home = false", "trader_first_home = true")
    toml = toml.replace('api_base = "http://127.0.0.1:8787"', f'api_base = "{API}"')
    (tmp / "site.toml").write_text(toml, encoding="utf-8")
    out = tmp / "site"
    env = {**os.environ, "DT_SITE_TOML": str(tmp / "site.toml"), "DT_OUT": str(out), "DT_PRIVATE_TOML": private_with(tmp),
           "DT_PRICES_JSON": prices_with_test_link(tmp), "DT_ALLOW_LOCAL_API": "1"}
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"origin": f"http://127.0.0.1:{port}", "out": out}
    srv.shutdown()


def fake_token():
    import base64
    payload = {"v": 1, "sku": "report39", "pk": "a" * 32, "salt": "b" * 32, "iat": 1, "exp": 4102444800}
    b = base64.urlsafe_b64encode(json.dumps(payload).encode()).decode().rstrip("=")
    return b + ".c2ln"


def test_the_built_page_carries_the_contact_email_from_site_toml(site):
    html = open(os.path.join(site["out"], "report/index.html"), encoding="utf-8").read()
    assert f'<meta name="dt-contact" content="{CONTACT}">' in html
    js = open(os.path.join(REPO, "site/static/js/paid/report.js"), encoding="utf-8").read()
    assert CONTACT not in js  # injected at build time, not typed in the script


def test_a_stats1_report_shows_exactly_the_error_line_and_nothing_from_the_report(browser, site):
    rep = json.load(open(os.path.join(HERE, "fixtures", "paid-reports", "random.report.json"), encoding="utf-8"))
    rep["method_version"] = "2026-10-21.stats1"   # an R1 Worker's report
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.route(API + "/analyse", lambda route: route.fulfill(status=200, content_type="application/json",
                                                             body=json.dumps({"report": rep, "uses_left": 1})))
    page.goto(site["origin"] + "/report/#t=" + fake_token())
    page.set_input_files("#rp-file", os.path.join(HERE, "fixtures", "e2e-upload.csv"))
    page.wait_for_function("() => { const s = document.getElementById('rp-status'); return s && !s.hidden && s.classList.contains('notice-error'); }",
                           timeout=30000)
    status = page.inner_text("#rp-status").strip()
    assert status == EXPECTED
    assert page.inner_text("#rp-out").strip() == ""
    assert page.eval_on_selector("#rp-out", "e => e.children.length") == 0
    area = status + page.inner_text("#rp-out")
    assert "receipt" not in area.lower()
    assert "$" not in area and not re.search(r"\d", area)
    for w in HABIT_WORDS:
        assert w not in area, w
    assert not errors, errors
    ctx.close()


def test_the_line_passes_lint():
    assert lint_text(EXPECTED) == []
    assert lint_text(EXPECTED, "paid-report", paid=True) == []
