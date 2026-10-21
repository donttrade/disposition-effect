"""Fixes for the delta Tester's findings (TESTER-REPORT-delta-decisions-2026-10-21: D1–D6, N1–N12)
and the Manager's review (MANAGER-REVIEW-v2-2026-10-21: /redeem rate limit is server-side;
launch_date, the old calculators' CSP and the manual-restore wording are here).

Tests named "..._tester_repro" are the Tester's repros from /home/claude/tester-delta/ (that folder
is never modified), copied here and adapted only where the fix changed the interface. Every value
is an obviously fake fixture.
"""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402
import lint as L  # noqa: E402

RETEST_JS = os.path.join(REPO, "site", "static", "js", "paid", "retest-copy.js")
DAY = 86400


def node(code):
    r = subprocess.run(["node", "--input-type=module", "-e", code, "file://" + RETEST_JS],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def window_for(first_iso):
    """The window the server returns for a first report at first_iso (opens +30 d, closes +60 d)."""
    import datetime as dt
    t = int(dt.datetime.fromisoformat(first_iso.replace("Z", "+00:00")).timestamp())
    return {"opens_at": t + 30 * DAY, "closes_at": t + 60 * DAY}, t


def ics_for(first_iso):
    w, t = window_for(first_iso)
    code = (f"import(process.argv[1]).then(m => process.stdout.write(JSON.stringify("
            f"{{ics: m.ics({json.dumps(w)}, new Date({(t + 40) * 1000})), "
            f"line: m.retestLine({json.dumps(w)}, {t + 40})}})));")
    d = node(code)
    return d["ics"], d["line"], w


# ------------------------------------------------------------------ D1: .ics and server agree
@pytest.mark.parametrize("first_iso,start,shown", [
    ("2026-11-01T15:00:00Z", "20261201T150000Z", "2026-12-01 15:00 UTC"),
    ("2026-11-01T23:30:00Z", "20261201T233000Z", "2026-12-01 23:30 UTC"),   # 07:30 the next day in UTC+8
    ("2026-11-01T23:30:07Z", "20261201T233007Z", "2026-12-01 23:31 UTC"),   # shown rounded UP
])
def test_d1_ics_starts_at_the_servers_opening_instant_tester_repro(first_iso, start, shown):
    # ics-check.mjs, adapted: ics() now takes the server's window instead of "now"
    ics, line, w = ics_for(first_iso)
    unfolded = ics.replace("\r\n ", "")
    assert f"DTSTART:{start}\r\n" in unfolded, unfolded
    assert "VALUE=DATE" not in ics, "never an all-day (local calendar day) event"
    assert re.search(r"DTEND:\d{8}T\d{6}Z", unfolded)
    desc = next(x for x in unfolded.split("\r\n") if x.startswith("DESCRIPTION:")).replace("\\,", ",")
    for text in (desc, line):
        assert f"opens at {shown}" in text, text
        assert "in 30 days, 0 hours" in text, text
        assert "opens on" not in text
    assert all(len(x.encode("utf-8")) <= 75 for x in ics.split("\r\n"))
    assert not L.lint_text(line) and not L.lint_text(desc)


def test_d1_no_reminder_without_a_server_window():
    d = node("import(process.argv[1]).then(m => process.stdout.write(JSON.stringify({"
             "none: m.ics(null), bad: m.ics({opens_at: 5, closes_at: 4}), line: m.retestLine(null)})));")
    assert d["none"] is None and d["bad"] is None
    assert "30 to 60 days after your first report" in d["line"]


def test_d1_report_page_uses_the_servers_window_and_hides_the_reminder_after_the_retest():
    js = open(os.path.join(REPO, "site", "static", "js", "paid", "report.js"), encoding="utf-8").read()
    assert "retest: r.json.retest" in js and "ics(win)" in js
    assert "ics()" not in js, "the .ics is never built from the browser's own clock"
