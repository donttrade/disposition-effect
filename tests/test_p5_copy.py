"""Delivery plan C-11 (P-5): "not stored" never appears without the fingerprint that is kept.

One source (site/config/strings.toml [p5] long / short) is used on /for-traders/, the home page (list item
and FAQ), /report/ and the pricing "Before you pay" technical row. The build fails on any block element
that says "not stored" / "not kept" / "never stored" / "ne sont pas conservés" without "fingerprint" /
"empreinte" in the same element."""
import os
import re
import shutil
import subprocess
import sys
import tomllib

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
from lint import lint_text, readable_text, visible_text  # noqa: E402
import build as B  # noqa: E402

S = tomllib.load(open(os.path.join(REPO, "site", "config", "strings.toml"), "rb"))["p5"]


def norm(t):
    return re.sub(r"\s+", " ", t.replace("’", "'")).strip()


def test_the_two_source_strings_are_the_plans_and_pass_the_lint():
    assert S["long"] == ("Your browser sends our server only stripped trade numbers: open and close times, buy or sell, relative "
                         "size, the realised result and a random symbol number. No name, account number or ticker is sent. The "
                         "numbers are not kept; we keep only a scrambled fingerprint of each trade row from your first report, so "
                         "a re-test can be matched to the same history, and we delete it on the dates in our privacy notice.")
    assert S["short"] == ("It sends our server only stripped trade numbers. Those are not kept; only a scrambled fingerprint of "
                          "each trade is kept, for the re-test.")
    for t in S.values():
        assert lint_text(t) == [] and lint_text(t, "p5", paid=True) == [], (t, lint_text(t, "p5", paid=True))
        assert B.storage_claim_problems(f"<p>{t}</p>", "src") == []


@pytest.mark.parametrize("bad", [
    "<li>Your browser sends stripped numbers, which are not stored.</li>",
    "<p>They are <strong>never stored</strong> anywhere.</p>",
    "<dd>Ces chiffres ne sont pas conservés.</dd>",
    "<details><summary>Where?</summary><p>The numbers are not kept.</p></details><p>We keep a fingerprint.</p>",
    "<div><p>Not kept.</p><p>A fingerprint is kept.</p></div>",   # qualifier in a sibling, not in the element
])
def test_planted_storage_claims_are_caught(bad):
    probs = B.storage_claim_problems("<html><body>" + bad + "</body></html>", "planted.html")
    assert len(probs) == 1, probs          # the innermost element only, not each ancestor
    assert "without the fingerprint that is kept" in probs[0]


@pytest.mark.parametrize("ok", [
    "<p>The numbers are not kept; we keep only a scrambled fingerprint.</p>",
    "<dd>Ces chiffres ne sont pas conservés; nous gardons seulement des empreintes brouillées.</dd>",
    "<p>Nothing is uploaded.</p>",
    "<script>const s = 'not stored';</script><p>Fine.</p>",
])
def test_qualified_or_absent_claims_pass(ok):
    assert B.storage_claim_problems(ok, "ok.html") == []


def test_the_build_fails_on_a_planted_page(built_site, tmp_path):
    out = tmp_path / "_site"
    shutil.copytree(built_site["out"], out)
    (out / "planted").mkdir()
    (out / "planted" / "index.html").write_text("<!doctype html><html><body><p>Your trades are not stored.</p></body></html>", encoding="utf-8")
    flags = B.load_config()[0]["flags"]
    with pytest.raises(B.BuildError, match="P-5 storage claim: planted/index.html"):
        B.verify(str(out), flags)


@pytest.fixture(scope="module")
def paid_build(tmp_path_factory):
    from test_legal import prices_with_test_link, private_with
    tmp = tmp_path_factory.mktemp("p5paid")
    toml = open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()
    toml = toml.replace("paid_report = false", "paid_report = true").replace("trader_first_home = false", "trader_first_home = true")
    (tmp / "site.toml").write_text(toml, encoding="utf-8")
    out = tmp / "site"
    env = {**os.environ, "DT_SITE_TOML": str(tmp / "site.toml"), "DT_OUT": str(out), "DT_PRIVATE_TOML": private_with(tmp),
           "DT_PRICES_JSON": prices_with_test_link(tmp), "DT_ALLOW_LOCAL_API": "1"}
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out


def page_text(out, rel, read=visible_text):
    return norm(read(open(os.path.join(out, rel), encoding="utf-8").read()))


def test_the_pages_render_the_source_strings_paid_build(paid_build):
    long_, short = norm(S["long"]), norm(S["short"])
    assert page_text(paid_build, "for-traders/index.html").count(long_) == 1
    home = page_text(paid_build, "index.html")
    assert home.count(short) == 1 and home.count(long_) == 1           # list item + FAQ answer
    assert page_text(paid_build, "index.html", readable_text).count(long_) == 2   # and the FAQPage JSON-LD answer
    assert page_text(paid_build, "report/index.html").count(long_) == 1
    pricing = open(os.path.join(paid_build, "pricing", "index.html"), encoding="utf-8").read()
    byp = pricing[pricing.index('id="before-you-pay"'):]
    byp = byp[:byp.index("</section>")]
    assert long_ in norm(readable_text("<div " + byp + "</div>"))
    for rel in ("index.html", "for-traders/index.html", "report/index.html", "pricing/index.html"):
        t = page_text(paid_build, rel, readable_text)
        assert "not stored" not in t, rel
        assert lint_text(t, rel, paid=True) == [], (rel, lint_text(t, rel, paid=True))


def test_the_free_build_renders_the_source_string_and_no_bare_claim(built_site):
    t = page_text(built_site["out"], "for-traders/index.html")
    assert norm(S["long"]) in t and "not stored" not in t
    for root, _, files in os.walk(built_site["out"]):
        for n in files:
            if n.endswith(".html"):
                assert B.storage_claim_problems(open(os.path.join(root, n), encoding="utf-8").read(), n) == [], n
