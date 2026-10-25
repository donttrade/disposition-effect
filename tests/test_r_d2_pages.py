"""Architect ruling R-D2 (23 Oct), H-3: under method 2026-10-23.stats2b the hold gap is described, not tested, so
no built page, EN or FR, in the free, badges or paid build, still says four habits can be tested; the hold-gap row
of the home and /for-traders/ habits tables says so; /sample-report/'s lead says "up to three"; /fr/avant-de-payer/
says "jusqu’à trois" and marks the hold gap "(décrite, non testée dans cette version)". The ledes no longer say each
pattern is tested (their own example, the hold gap, is not).

R-D3 (23 Oct), I-3: under method 2026-10-23.stats2c size after a loss is described, not tested, too, so no built page
says three can be tested ("tests up to three", "test up to three", "of the 3 habits", "jusqu’à trois"); the ledes and
/sample-report/ say "up to two"; the size-after-a-loss row says "(described, not tested in this version)"; the FR page
says "jusqu’à deux" and marks both items "(décrite, non testée dans cette version)"."""
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
              "tests whether each pattern is more than noise", "test whether each pattern is more than noise",
              # R-D3 I-3
              "tests up to three", "test up to three", "of the 3 habits", "jusqu’à trois", "tests each one for noise",
              # R-D3 I-3b (the lot-size line no longer says the report checks this)
              "whether your size changes after a loss",
              # R-D3 addendum I-6 (the report page's old citation prefix)
              "Published research on this pattern"]
ROW = "Did you hold losing trades longer than winning ones? (described, not tested in this version)"
SIZE_ROW = "Was the trade after a loss larger than the trade after a win? (described, not tested in this version)"
COUNT = "tests up to two of these habits against chance in this version."
COUNT_SOON = "test up to two of these habits against chance in this version."
FR = ("par rapport aux gagnantes (décrite, non testée dans cette version); ",
      "l’augmentation de la taille après des pertes (décrite, non testée dans cette version); ",
      "Il en teste jusqu’à deux par rapport au hasard")


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
    for s in ("tests up to three", "test up to three", "of the 3 habits", "jusqu’à trois",   # R-D3 I-3
              "whether your size changes after a loss"):                                     # R-D3 I-3b
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
        assert "Size after a loss " + SIZE_ROW in t, (flavour, rel)   # R-D3
        assert t.count("(described, not tested in this version)") == 2, (flavour, rel)
        assert "(described, not tested)" in t, (flavour, rel)   # the oversized-loss row, in parallel
    ft = text_of(out, os.path.join("for-traders", "index.html"))
    assert COUNT in ft or COUNT_SOON in ft
    if flavour == "paid":   # QA 25 Oct: the home lede glosses "against chance" on first use
        assert COUNT.replace("chance in", "chance (could the pattern be luck?) in") in text_of(out, "index.html") and COUNT in ft
    for s in (ROW, SIZE_ROW, COUNT, COUNT_SOON):
        assert lint_text(s) == [] and lint_text(s, "rd2", paid=True) == []


def test_sample_report_lead_and_fr_page(builds):
    lead = ("This is a research figure from public data. It is not the trader report: the report covers five habits in "
            "your own file, tests up to two of them against chance, and shows no percentile.")
    assert lead in text_of(builds["free"], os.path.join("sample-report", "index.html"))
    # C-12 final (T-3 T3-E): the paid build's /sample-report/ is a real sample report (tests/test_sample_report_page.py)
    assert "A sample habit report, from a made-up trade file" in text_of(builds["paid"], os.path.join("sample-report", "index.html"))
    fr = open(os.path.join(builds["paid"], "fr", "avant-de-payer", "index.html"), encoding="utf-8").read()
    for s in FR:
        assert s in fr
    assert "quatre" not in visible_text(fr) and "jusqu’à trois" not in visible_text(fr)


# ------------------------------------------------------------------ R-D3 I-3b: the offer wording (owner's decision)
# Each value line states: five habits measured and described in your own file with the dollar totals of the matching
# trades; up to two tested against chance in this version; one re-test 30 to 60 days after the first report. Where the
# re-test is described, the version sentence follows, its "corrections page" linked to /corrections/.
RETEST = ("Your re-test runs on the version of the report that is live when you run it; every change is dated on the "
          "corrections page.")
RETEST_HTML = ('Your re-test runs on the version of the report that is live when you run it; every change is dated on the '
               '<a href="/corrections/">corrections page</a>.')
# QA 25 Oct: "plan" and "tested against chance" glossed on first use
HOME_LEDE = ("Drop your broker export. Get a report on up to five habits in your trades, with the dollar total of each.")   # sweep 2 hero
FT_LEDE = ("It measures and describes up to five habits in your own past trades, like opening a new trade soon after a loss, with the "
           "dollar totals of the matching trades, and tests up to two of these habits against chance in this version. It "
           "includes one re-test 30 to 60 days after your first report. It doesn’t tell you what to trade.")
FT_LEDE_SOON = ("It will measure and describe up to five habits in your own past trades, like opening a new trade soon after a loss, "
                "with the dollar totals of the matching trades, and test up to two of these habits against chance in this "
                "version. It will include one re-test 30 to 60 days after your first report. It will not tell you what to trade.")
PRODUCT = ("Up to five habits measured and described in your own trades, with the dollar totals of the matching trades; up to two of "
           "them tested against chance in this version; plus one re-test 30 to 60 days after your first report.")
BYP = ("a report on habits in your own past trades, built from a trade file you choose. It measures and describes up to five "
       "habits, with the dollar totals of the matching trades, and tests up to two of them against chance in this version. "
       "It includes one re-test 30 to 60 days after your first report. It describes what happened; it does not tell you "
       "what to trade.")
LOT = ("Sizing on paper is one thing. The habit report describes, from your own trade file when it has times of day, your median size after a loss "
       "and after a win, and what trades after a loss at 1.5 times your usual size or more totalled. It measures and "
       "describes up to five habits with the dollar totals of the matching trades, tests up to two of them against chance in this "
       "version, and includes one re-test 30 to 60 days after your first report.")
LOT_SOON = ("Sizing on paper is one thing. We’re building a habit report that describes, from your own trade file when it has times of day, your median "
            "size after a loss and after a win, and what trades after a loss at 1.5 times your usual size or more totalled. It "
            "will measure and describe up to five habits with the dollar totals of the matching trades, test up to two of them "
            "against chance in this version, and include one re-test 30 to 60 days after your first report.")
FR_FACTS = ("Pour chacune, quand le fichier le permet, il totalise les montants réalisés des transactions en cause. Il en teste jusqu’à deux par rapport au "
            "hasard dans cette version : pour chacune, il indique si l’écart se distingue du hasard.",
            "Comprend un nouveau test gratuit, de 30 à 60 jours plus tard.",
            "Votre nouveau test est fait avec la version du rapport en ligne au moment où vous le lancez; chaque changement est "
            "daté, en anglais, sur la page des corrections.")
DATES_RESTRICTION = ("If 5% or more of a file's rows open at exactly 00:00 and are held a whole number of days, as in exports "
                     "with dates but no times, no habit is tested, and the habits that depend on the order of trades within a "
                     "day (re-entering soon after a loss, size after a loss, trading after a losing run) are not described.")
NO_PROMISE = ["coming soon", "will be tested", "tested later", "later version", "next version", "founding edition"]


def raw(out, rel):
    return open(os.path.join(out, rel), encoding="utf-8").read()


NEXT_TYPED = ("The habit report reads your trade file It looks for up to five habits in your "   # owner Q3, 25 Oct: the heading names the report
              "own trades, testing up to two of them against chance. $39, one re-test included, refund within 14 days.")


def test_i3b_exact_offer_lines_on_each_page(builds):
    paid, free = builds["paid"], builds["free"]
    assert HOME_LEDE in text_of(paid, "index.html")
    assert FT_LEDE in text_of(paid, os.path.join("for-traders", "index.html"))
    assert FT_LEDE_SOON in text_of(free, os.path.join("for-traders", "index.html"))
    pr = text_of(paid, os.path.join("pricing", "index.html"))
    assert PRODUCT in pr and BYP in pr
    assert DATES_RESTRICTION in pr and "A tested habit with fewer than 30 trades in either group" in pr   # T-3 T3-A, T3-B
    assert lint_text(DATES_RESTRICTION) == [] and lint_text(DATES_RESTRICTION, "t3a", paid=True) == []
    # owner, 25 Oct: a paid tool page's one offer is partials/tool_next_step.html; its teaser box is left out
    lot_paid = text_of(paid, os.path.join("tools", "lot-size-calculator", "index.html"))
    assert LOT not in lot_paid and NEXT_TYPED in lot_paid
    assert LOT_SOON in text_of(free, os.path.join("tools", "lot-size-calculator", "index.html"))
    fr = re.sub(r"\s+", " ", visible_text(raw(paid, os.path.join("fr", "avant-de-payer", "index.html"))))
    for s in FR_FACTS:
        assert s in fr, s
    for s in (HOME_LEDE, FT_LEDE, FT_LEDE_SOON, PRODUCT, BYP, LOT, LOT_SOON, RETEST, NEXT_TYPED):
        assert lint_text(s) == [] and lint_text(s, "i3b", paid=True) == [], s


def test_i3b_the_version_sentence_sits_where_the_re_test_is_described_and_links_corrections(builds):
    paid = builds["paid"]
    for rel in ("pricing/index.html", "for-traders/index.html", "index.html"):
        h = re.sub(r"\s+", " ", raw(paid, rel))
        assert RETEST_HTML in h, rel
    pr = re.sub(r"\s+", " ", raw(paid, "pricing/index.html"))
    # 25 Oct sweep: no value ladder on /pricing/; the re-test answer and Before you pay carry the sentence
    assert pr.count(RETEST_HTML) == 2, "the re-test answer and Before you pay"
    assert os.path.exists(os.path.join(paid, "corrections", "index.html"))
    fr = re.sub(r"\s+", " ", raw(paid, "fr/avant-de-payer/index.html"))
    assert 'daté, en anglais, sur la <a href="/corrections/" hreflang="en">page des corrections</a>.' in fr
    for out in (paid, builds["free"]):
        ft = re.sub(r"\s+", " ", raw(out, "for-traders/index.html"))
        assert RETEST_HTML in ft


def test_i3b_product_text_is_the_same_everywhere(builds):
    sys.path.insert(0, os.path.join(REPO, "site"))
    import importlib
    build = importlib.import_module("build")
    assert build.PRODUCT_TEXT == PRODUCT
    h = raw(builds["paid"], "pricing/index.html")
    assert "<p>" + PRODUCT + "</p>" in h   # 25 Oct sweep: the answer to "What exactly do I get?" on /pricing/
    ld = [m for m in re.findall(r'<script type="application/ld\+json">(.*?)</script>', h, re.S) if '"Product"' in m]
    assert ld and all(PRODUCT in m for m in ld)
    seen = []
    for root, _, files in os.walk(builds["paid"]):
        for f in files:
            if f.endswith((".html", ".json", ".js", ".xml", ".txt")):
                t = open(os.path.join(root, f), encoding="utf-8", errors="replace").read()
                if "five habits measured and described" in t.lower():
                    seen.append(os.path.relpath(os.path.join(root, f), builds["paid"]))
                    assert "Five habits measured in your own trades, with historical dollar figures" not in t
    # merge into delivery-39 (24 Oct): v3's /help/ page and its answers index quote /pricing/ word for word
    assert sorted(seen) == ["help/index.html", "pricing/index.html", "static/js/answers-index.js"], seen


@pytest.mark.parametrize("flavour", ["free", "badges", "paid"])
def test_i3b_no_promise_that_hold_gap_or_size_up_will_be_tested(builds, flavour):
    out = builds[flavour]
    for rel in ("index.html", "for-traders/index.html", "pricing/index.html", "tools/lot-size-calculator/index.html",
                "fr/avant-de-payer/index.html"):
        p = os.path.join(out, rel)
        if not os.path.exists(p):
            continue
        t = re.sub(r"\s+", " ", visible_text(open(p, encoding="utf-8").read())).lower()
        for bad in NO_PROMISE:
            if bad == "coming soon" and flavour != "paid":
                continue   # off sale, the pages say the report itself is coming soon
            assert bad not in t, (flavour, rel, bad)
