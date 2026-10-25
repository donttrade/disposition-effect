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


@pytest.fixture(scope="module")
def ask_builds(tmp_path_factory, ask_site):
    """MR-4 is about the box: the ask_box = true builds (the box is off by default for launch, 25 Oct)."""
    tmp = tmp_path_factory.mktemp("mr-ask")
    r, paid = _build(tmp, "paid")
    assert r.returncode == 0, r.stderr
    toml = tmp / "paid.toml"
    src, n = re.subn(r"(?m)^ask_box = false", "ask_box = true", toml.read_text(encoding="utf-8"))
    assert n == 1
    toml.write_text(src, encoding="utf-8")
    import subprocess
    env = {**os.environ, "DT_SITE_TOML": str(toml), "DT_PRIVATE_TOML": str(tmp / "paid-private.toml"),
           "DT_PRICES_JSON": str(tmp / "paid-prices.json"), "DT_OUT": str(paid), "DT_DEV": ""}
    for k in ("DT_ALLOW_PLACEHOLDERS", "DT_ALLOW_LOCAL_API", "DT_ALLOW_NO_STRIPE_LINK", "DT_PREVIEW"):
        env.pop(k, None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return {"free": ask_site["out"], "paid": paid}


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
        # 25 Oct: Code left the header menu for the footer's Transparency group
        assert "Study scripts, and which are still to come" not in h
        assert re.search(r'aria-label="Transparency"><h2>Transparency</h2><ul>.*?href="/code/"', h, re.S)
        # /code/ lists the published study scripts and those still to follow ("To be published with the study")
        assert "To be published with the study" in text_of(out, "code/index.html")


# ------------------------------------------------------------------ MR-3
LIMITS = ("the closed trades in your file: the latest 20,000 rows at most, leaving out trades opened more than about 10 "
          "years before your latest trade or held longer than 3,650 days.")


def test_mr3_ladder_states_both_file_limits(builds):
    for name, out in builds.items():
        lead = "The report reads " if name == "paid" else "The report will read "
        for rel in ("for-traders/index.html", "pricing/index.html"):
            t = text_of(out, rel)
            assert lead + LIMITS in t and "every closed trade" not in t, (name, rel)
    # the numbers are the browser's own (paid/strip.js)
    js = open(os.path.join(REPO, "site", "static", "js", "paid", "strip.js"), encoding="utf-8").read()
    assert "MAX_ROWS = 20000;" in js and "MAX_HOLD_S = 86400 * 3650;" in js and "519 weeks (about 10 years)" in js
    assert L.lint_text(lead + LIMITS) == [] and L.lint_text("The report reads " + LIMITS, "mr3", paid=True) == []


# ------------------------------------------------------------------ MR-4
ASK_LINE = ("Answers are quoted from this site’s own pages. Your question is never sent anywhere: it is matched in your "
            "browser, and without JavaScript, Ask opens the list of every answer instead.")


def test_mr4_no_answer_box_field_has_a_name_and_the_line_says_so(ask_builds):
    for out in ask_builds.values():
        for rel in ("index.html", "help/index.html", "tools/trade-stats/index.html", "pricing/index.html"):
            h = raw(out, rel)
            for box in re.findall(r"(?s)<search class=\"answer-box\".*?</search>", h):
                assert "name=" not in re.sub(r'<meta[^>]*>', "", box), rel
            assert ASK_LINE in text_of(out, rel), rel
    assert L.lint_text(ASK_LINE) == []


@pytest.mark.parametrize("mode", ["no-js", "engine-blocked", "js"])
def test_mr4_the_typed_question_never_leaves_the_browser(browser, ask_site, mode):
    built_site = ask_site
    ctx = browser.new_context(viewport={"width": 1280, "height": 900}, java_script_enabled=(mode != "no-js"))
    pg = ctx.new_page()
    urls = []
    pg.on("request", lambda r: urls.append(r.url))
    if mode == "engine-blocked":   # answers.js fails to load: ask.js falls back to form.submit()
        pg.route("**/static/js/answers.js*", lambda route: route.abort())
    pg.goto(built_site["url"] + "/help/#ask")
    pg.wait_for_load_state("networkidle")
    pg.fill("#ask-q", "zqxsecret question")
    pg.click("#ask button[type=submit]")
    pg.wait_for_timeout(800)
    pg.wait_for_load_state()
    assert not [u for u in urls if "zqxsecret" in u or "q=" in u], urls
    if mode != "js":
        assert re.search(r"/help/\??(#.*)?$", pg.url), pg.url
    ctx.close()
