"""Architect ruling R-D2 (23 Oct), H-3: under method 2026-10-23.stats2b the hold gap is described, not tested, so
no built page, EN or FR, in the free, badges or paid build, still says four habits can be tested; the hold-gap row
of the home and /for-traders/ habits tables says so; /sample-report/'s lead says "up to three"; /fr/avant-de-payer/
says "jusqu’à trois" and marks the hold gap "(décrite, non testée dans cette version)". The ledes no longer say each
pattern is tested (their own example, the hold gap, is not)."""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import lint_text, visible_text  # noqa: E402
from test_c14_legal_copy import _build  # noqa: E402
from test_wording_wiring import STALE_BUILD  # noqa: E402

STALE_R_D2 = ["tests up to four", "of the 4 patterns", "jusqu’à quatre", "tests four of them",
              "tests whether each pattern is more than noise", "test whether each pattern is more than noise"]
ROW = "Did you hold losing trades longer than winning ones? (described, not tested in this version)"
LEDE = "like holding losing trades longer than winning ones, and tests up to three of these habits against chance."
FR = ("par rapport aux gagnantes (décrite, non testée dans cette version); ", "Il en teste jusqu’à trois par rapport au hasard")


@pytest.fixture(scope="module")
def builds(tmp_path_factory, built_site, badges_site):
    r, paid = _build(tmp_path_factory.mktemp("rd2"), "paid")
    assert r.returncode == 0, r.stderr
    return {"free": built_site["out"], "badges": badges_site["out"], "paid": paid}


def text_of(out, rel):
    return re.sub(r"\s+", " ", visible_text(open(os.path.join(out, rel), encoding="utf-8").read()))


def test_the_three_stale_strings_are_on_the_stale_build_list():
    for s in ("tests up to four", "of the 4 patterns", "jusqu’à quatre"):
        assert s in STALE_BUILD


@pytest.mark.parametrize("flavour", ["free", "badges", "paid"])
def test_no_built_file_says_four_can_be_tested(builds, flavour):
    out = str(builds[flavour])
    hits, n = [], 0
    for root, _, files in os.walk(out):
        if os.sep + "research" + os.sep in root + os.sep:   # passthrough research ledgers (v1 docs/)
            continue
        for f in files:
            if f.endswith((".html", ".js", ".json", ".xml", ".txt")):
                n += 1
                s = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
                hits += [(os.path.relpath(os.path.join(root, f), out), p) for p in STALE_R_D2 if p in s]
    assert n > 50 and hits == [], hits
    if flavour == "paid":
        assert os.path.exists(os.path.join(out, "fr", "avant-de-payer", "index.html"))   # FR is in the scan


@pytest.mark.parametrize("flavour", ["free", "paid"])
def test_habit_tables_and_ledes(builds, flavour):
    out = builds[flavour]
    for rel in ("index.html", os.path.join("for-traders", "index.html")):
        t = text_of(out, rel)
        if rel == "index.html" and flavour == "free":
            continue   # the flag-off home is not the trader home
        assert "Hold gap " + ROW in t, (flavour, rel)
        assert t.count("(described, not tested in this version)") == 1, (flavour, rel)
        assert "(described, not tested)" in t, (flavour, rel)   # the oversized-loss row, in parallel
    ft = text_of(out, os.path.join("for-traders", "index.html"))
    assert LEDE in ft or "like holding losing trades longer than winning ones, and test up to three of these habits against chance." in ft
    if flavour == "paid":
        assert LEDE in text_of(out, "index.html")
    for s in (ROW, LEDE):
        assert lint_text(s) == [] and lint_text(s, "rd2", paid=True) == []


def test_sample_report_lead_and_fr_page(builds):
    lead = ("This is a research figure from public data. It is not the trader report: the report covers five habits in "
            "your own file, tests up to three of them against chance, and shows no percentile.")
    for flavour in ("free", "paid"):
        assert lead in text_of(builds[flavour], os.path.join("sample-report", "index.html")), flavour
    fr = open(os.path.join(builds["paid"], "fr", "avant-de-payer", "index.html"), encoding="utf-8").read()
    for s in FR:
        assert s in fr
    assert "quatre" not in visible_text(fr)
