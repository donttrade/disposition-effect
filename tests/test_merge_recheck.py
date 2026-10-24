"""Tester merge re-check (24 Oct, report §11) on the preview-combined merge: the wording items MR-1..MR-5.

MR-1: the /for-traders/ comparison row says which code is public (the study scripts, as /code/ counts them) and
that the habit report's engine is not.
MR-5: a paid build names the seller, so its /about/ and /code/ no longer say "there is no name"; a free build keeps
the old line word for word, and the paid swap is the only frozen-body difference compare.py and lint accept."""
import os
import re
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402
import compare as C  # noqa: E402
import lint as L  # noqa: E402
from lint import visible_text  # noqa: E402
from test_c14_legal_copy import FAKE, _build  # noqa: E402


@pytest.fixture(scope="module")
def builds(tmp_path_factory, built_site):
    r, paid = _build(tmp_path_factory.mktemp("mr"), "paid")
    assert r.returncode == 0, r.stderr
    return {"free": built_site["out"], "paid": paid}


def text_of(out, rel):
    return re.sub(r"\s+", " ", visible_text(open(os.path.join(out, rel), encoding="utf-8").read()))


def raw(out, rel):
    return open(os.path.join(out, rel), encoding="utf-8").read()


# ------------------------------------------------------------------ MR-1
def test_mr1_comparison_row_names_the_public_scripts_and_the_private_engine(builds):
    ev = B.evidence()
    row = (f"Shows its method and code Rarely The method, yes. The scripts behind {ev['scripts_public']} of the "
           f"{ev['studies']} studies are public (Methods and code); the habit report’s own engine is not")
    for out in builds.values():
        t = text_of(out, "for-traders/index.html")
        assert row in t and "Shows the method and the code" not in t
        # the same counts as /code/'s own lede
        assert f"The scripts behind {ev['scripts_public']} of the {ev['studies']} studies are public" in text_of(out, "code/index.html")


# ------------------------------------------------------------------ MR-5
FREE_ABOUT = "There’s no name on it on purpose: every study names the script"
FREE_CODE = "There is no name on this site; the scripts are what you check instead."
SELLER = ("the seller’s legal name is given for buyers in Before you pay, the terms and the privacy notice")
PAID_ABOUT = "No author name is published here, on purpose (" + SELLER + "): every study names the script"
PAID_CODE = "No author name is published on this site (" + SELLER + "); the scripts are what you check instead."


def test_mr5_free_build_keeps_the_old_lines(builds):
    free = builds["free"]
    assert FREE_ABOUT in text_of(free, "about/index.html") and FREE_CODE in text_of(free, "code/index.html")
    assert "No author name" not in text_of(free, "about/index.html") + text_of(free, "code/index.html")
    assert "why there is no name on it" in raw(free, "about/index.html")


def test_mr5_paid_build_says_where_the_seller_is_named_and_names_no_one_else(builds):
    paid = builds["paid"]
    a, c = text_of(paid, "about/index.html"), text_of(paid, "code/index.html")
    assert PAID_ABOUT in a and PAID_CODE in c
    for t in (a, c):
        assert "no name on" not in t.lower() and FAKE["seller_legal_name"] not in t
    ah = raw(paid, "about/index.html")
    assert "why there is no name on it" not in ah and "why no author name is published" in ah
    assert 'href="/pricing/#before-you-pay"' in raw(paid, "code/index.html")
    # the three places the sentence points to do name the seller in a paid build
    for rel in ("pricing/index.html", "terms/index.html", "privacy/index.html"):
        assert FAKE["seller_legal_name"] in raw(paid, rel), rel
    assert 'id="before-you-pay"' in raw(paid, "pricing/index.html")


def test_mr5_compare_and_lint_accept_only_the_listed_swaps(builds, tmp_path):
    paid = builds["paid"]
    assert C.compare_site(str(paid)) == []
    t = tmp_path / "t"
    shutil.copytree(paid, t)
    fp = t / "code" / "index.html"
    fp.write_text(fp.read_text(encoding="utf-8").replace("the scripts are what you check instead",
                                                         "the scripts are what you trust instead"), encoding="utf-8")
    assert [p for p in C.compare_site(str(t)) if p[0] == "/code/"]
    assert [p for p in L.lint_build(str(t), paid=True) if p[0].startswith("frozen")]


def test_mr5_a_swap_that_no_longer_matches_fails_the_build():
    with pytest.raises(B.BuildError, match="paid lifted swap"):
        B.paid_lifted("/code/", "<p>changed text</p>", True)
    assert B.paid_lifted("/code/", "<p>changed text</p>", False) == "<p>changed text</p>"


# ------------------------------------------------------------------ MR-2
def test_mr2_nav_code_line_matches_what_code_lists(builds):
    for out in builds.values():
        h = raw(out, "index.html")
        assert "Every script, public" not in h
        assert "Study scripts, and which are still to come" in h
        # /code/ lists the published study scripts and those still to follow ("To be published with the study")
        assert "To be published with the study" in text_of(out, "code/index.html")
