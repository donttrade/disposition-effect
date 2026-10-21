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


# ------------------------------------------------------------------ D3: every stated window number = paid_terms.json
TERMS = json.load(open(os.path.join(REPO, "site", "config", "paid_terms.json"), encoding="utf-8"))
OPENS, CLOSES = TERMS["retest_opens_days_after_first_report"], TERMS["retest_closes_days_after_first_report"]
KEY, KEY_FR = TERMS["key_days_after_purchase"], TERMS["key_days_after_first_report"]
KEEP, GRACE = TERMS["prints_keep_days_after_first_report"], TERMS["tracker_prints_grace_days"]
N = r"(\d+)"
# page → [(pattern with the numbers as groups, the numbers it must state)]. Each must occur at least once.
STATEMENTS = {
    "/terms/": [(rf"one re-test, which opens {N} days after your first report and closes {N} days after it", (OPENS, CLOSES)),
                (rf"Your key is valid for {N} days after purchase, or until {N} days after your first report", (KEY, KEY_FR))],
    "/fr/conditions/": [(rf"Le nouveau test est offert de {N} à {N} jours après votre premier rapport", (OPENS, CLOSES)),
                        (rf"valide {N} jours après l’achat, ou jusqu’à {N} jours après votre premier rapport", (KEY, KEY_FR))],
    "/fr/avant-de-payer/": [(rf"à partir de {N} jours et jusqu’à {N} jours après votre premier rapport", (OPENS, CLOSES)),
                            (rf"valide {N} jours après l’achat, ou jusqu’à {N} jours après votre premier rapport", (KEY, KEY_FR))],
    "/pricing/": [(rf"One re-test is included, to run {N} to {N} days after your first report", (OPENS, CLOSES)),
                  (rf"Access lasts {N} days after purchase, or until {N} days after your first report", (KEY, KEY_FR))],
    "/privacy/": [(rf"or {N} days after your first report, whichever comes first", (KEEP,)),
                  (rf"delete them {N} days after it ends", (GRACE,))],
}
# Anywhere on any page: a stated re-test window must be the server's.
SWEEP = [rf"re-test[^.]{{0,80}}?\b{N} to {N} days", rf"nouveau test[^.]{{0,80}}?\bde {N} à {N} jours",
         rf"à partir de {N} jours et jusqu’à {N} jours"]


def statement_problems(path, text):
    out = []
    for pat, want in STATEMENTS.get(path, []):
        found = [tuple(int(x) for x in m.groups()) for m in re.finditer(pat, text)]
        if not found:
            out.append((path, "missing", pat))
        out += [(path, f, want) for f in found if f != want]
    for pat in SWEEP:
        out += [(path, tuple(int(x) for x in m.groups()), (OPENS, CLOSES)) for m in re.finditer(pat, text)
                if tuple(int(x) for x in m.groups()) != (OPENS, CLOSES)]
    return out


def test_d3_paid_terms_json_is_consistent():
    assert KEEP == CLOSES + TERMS["prints_buffer_days"]
    assert KEY_FR == KEEP and CLOSES > OPENS > 0


@pytest.fixture(scope="module")
def both_build(tmp_path_factory):
    from test_legal import build, paid_env
    tmp = tmp_path_factory.mktemp("delta-d3")
    r, out = build(tmp, "out", **paid_env(tmp, pilot_checkout=True))
    assert r.returncode == 0, r.stderr
    return out


def _visible(out, path):
    return " ".join(L.visible_text((out / path.strip("/") / "index.html").read_text(encoding="utf-8")).split())


def test_d3_every_page_states_the_window_and_key_of_paid_terms_json(both_build):
    problems = []
    for path in STATEMENTS:
        problems += statement_problems(path, _visible(both_build, path))
    for p in both_build.rglob("*.html"):
        rel = "/" + str(p.parent.relative_to(both_build)).strip(".") + "/"
        problems += [x for x in statement_problems(rel.replace("//", "/"), " ".join(L.visible_text(p.read_text(encoding="utf-8")).split()))
                     if x[1] != "missing"]
    assert problems == []


def test_d3_the_checker_catches_the_testers_mutations():
    # mutate.sh terms_close / fr_window: "60→90" on /terms/ and "30 à 60 → 30 à 90" on /fr/conditions/
    terms = ("one re-test, which opens 30 days after your first report and closes 90 days after it. "
             "Your key is valid for 90 days after purchase, or until 75 days after your first report")
    assert statement_problems("/terms/", terms)
    fr = ("Le nouveau test est offert de 30 à 90 jours après votre premier rapport. "
          "valide 90 jours après l’achat, ou jusqu’à 75 jours après votre premier rapport")
    assert statement_problems("/fr/conditions/", fr)
    assert statement_problems("/home/", "one free re-test 30 to 90 days after your first report")
    assert statement_problems("/terms/", "") and statement_problems("/terms/", "")[0][1] == "missing"


def test_d3_report_page_line_states_paid_terms_json():
    d = node("import(process.argv[1]).then(m => process.stdout.write(JSON.stringify({line: m.RETEST_LINE})));")
    m = re.search(rf"re-test on the same account, {N} to {N} days after your first report", d["line"])
    assert m and (int(m.group(1)), int(m.group(2))) == (OPENS, CLOSES)
