"""Delivery plan C-10 (Tester Final D4): a file spanning more than 10 years. The browser keeps the last
10 years (as the 20,000-row cap keeps the latest trades), says so before sending, and the server analyses
it; a direct call with an older row gets span_too_long (dt-private tests/span.test.mjs). Needs the R2
server: DT_PRIVATE_REPO=<dt-private on delivery-39>."""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(HERE), "checks"))
sys.path.insert(0, os.path.join(HERE, "reference"))
import engine_ref as E  # noqa: E402
from lint import lint_text  # noqa: E402
from test_paid_flow import PRIVATE, stack  # noqa: E402,F401  (module-scoped stack fixture)
from test_report_page import open_report  # noqa: E402

import pytest  # noqa: E402

pytestmark = pytest.mark.skipif(not os.path.isdir(PRIVATE), reason="dt-private (server) not present")
SPAN = os.path.join(HERE, "fixtures", "paid", "span_11y.csv")
MAX_O = 60 * 24 * 7 * 520
# R-D1 D-4: the exact texts.
SERVER_MSG = "This file has a trade opened more than 520 weeks (about 10 years) after the start of its first trade's week, or a trade held longer than 3,650 days. Nothing was counted. Export a shorter period and try again."
LINE_56 = ("Left out: 56 trades opened more than 519 weeks (about 10 years) before this file's latest trade, or held longer "
           "than 3,650 days.")
LINE_1 = ("Left out: 1 trade opened more than 519 weeks (about 10 years) before this file's latest trade, or held longer "
          "than 3,650 days.")


def test_reference_trim_keeps_the_last_10_years():
    trades = E.parse_file(open(SPAN, "rb").read())["trades"]
    s = E.strip_rows(trades, "SALT")
    assert (len(trades), len(s["rows"]), s["span_left_out"]) == (420, 364, 56)
    assert max(r["o"] for r in s["rows"]) <= MAX_O and not s["limited"]
    years = (trades[-1]["open_ts"] - trades[0]["open_ts"]) / (365.25 * 86400000)
    assert 11.4 < years < 11.6


def test_browser_trims_says_so_before_sending_and_the_report_renders(browser, stack):
    ctx, page = open_report(browser, stack, "cs_test_span11y000001")
    sent = []
    page.on("request", lambda r: sent.append(r) if r.url.endswith("/analyse") else None)
    page.set_input_files("#rp-file", SPAN)
    page.wait_for_selector("#focus", timeout=60000)
    status = page.text_content("#rp-status")
    text = page.inner_text("#rp-out")
    ctx.close()
    line = LINE_56
    assert status.startswith(line + " Sending 364 stripped trade rows"), status    # shown before the request
    assert line in text                                                            # and on page 1
    body = json.loads(sent[-1].post_data)
    assert len(body["rows"]) == 364 and max(r["o"] for r in body["rows"]) <= MAX_O
    ref = E.strip_rows(E.parse_file(open(SPAN, "rb").read())["trades"], "x")["rows"]
    key = lambda r: (r["o"], r["h"], r["d"], r["q"], r["p"])  # noqa: E731  (s is a random index, f is salted)
    assert sorted(map(key, body["rows"])) == sorted(map(key, ref))


def test_the_new_strings_pass_the_lint():
    for t in (LINE_56, LINE_1, SERVER_MSG):
        assert lint_text(t) == [] and lint_text(t, "span", paid=True) == [], t
    src = open(os.path.join(PRIVATE, "src", "core", "app.mjs"), encoding="utf-8").read()
    assert f'span_too_long: "{SERVER_MSG}"' in src, "the server's message is the one R-D1 D-4 gives"


def test_span_line_at_1_and_56():
    js = ("import { spanLine } from './site/static/js/paid/strip.js';"
          "process.stdout.write(JSON.stringify([spanLine(1), spanLine(56)]));")
    import subprocess
    r = subprocess.run(["node", "--input-type=module", "-e", js], cwd=os.path.dirname(HERE), capture_output=True, text=True, check=True)
    assert json.loads(r.stdout) == [LINE_1, LINE_56]
