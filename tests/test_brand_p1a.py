"""ARCHITECT-BRAND-AND-WRAPPED-PLAN-2026-10-21, phase P1a: bold rust, the dark hero band, social links.

* wording (§1.5–1.6): the skill_claims and seal_words groups fail on a planted hit, in page text and in
  the strings of the card / Luck Check / Guess vs Data / Ghost Trader scripts; the listed negations pass;
  the reworded firm copy holds no "seal"; the frozen research bodies keep theirs (passthrough rules).
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import build as B  # noqa: E402
import lint as L  # noqa: E402

AMOUNTS = L.allowed_amounts()


def page(built_site, path):
    return (built_site["out"] / B.out_file("", path).lstrip("/")).read_text(encoding="utf-8")


def rules(html):
    return {r for r, _, _ in L.lint_html(html, "/x/", False, False, AMOUNTS, [])}


# ------------------------------------------------------------------ wording (§1.5, §1.6)
@pytest.mark.parametrize("text,rule", [
    ("<p>A sealed method.</p>", "banned:seal_words"),
    ("<p>That test is sealed.</p>", "banned:seal_words"),
    ("<p>Our seal on every report.</p>", "banned:seal_words"),
    ("<p>The donttrade seal of approval.</p>", "banned:seal_words"),
    ("<p>Hash-sealed in advance.</p>", "banned:seal_words"),
    ("<p>Your skill shows.</p>", "banned:skill_claims"),
    ("<p>A skilled trader.</p>", "banned:skill_claims"),
    ("<p>Skilful exits.</p>", "banned:skill_claims"),
    ("<p>Real talent.</p>", "banned:skill_claims"),
    ("<p>You beat the market.</p>", "banned:skill_claims"),
    ("<p>You were luckier than most.</p>", "banned:skill_claims"),
    ("<p>Not an unlucky trader.</p>", "banned:skill_claims"),
    ("<p>So you are good at this.</p>", "banned:skill_claims"),
    ("<p>Trade like a pro trader.</p>", "banned:skill_claims"),
])
def test_wording_groups_catch_a_planted_word(text, rule):
    assert rule in rules(text), rules(text)


@pytest.mark.parametrize("text", [
    "<p>Not an audit and not an assurance engagement. No regulatory status, no badge or seal.</p>",
    "<p>It is not investment advice. It is not an audit, and we issue no badge or seal.</p>",
    "<p>Seals are animals. Sealant is a word too.</p>",       # whole words only
    "<p>Reproduce this result: LC1-7F3A-C21E</p>",
])
def test_wording_negations_and_lookalikes_pass(text):
    assert not {r for r in rules(text) if r.startswith("banned:")}, rules(text)


def test_reworded_firm_copy_and_the_build_lint_clean(built_site):
    for path in ("/for-firms/", "/pricing/", "/terms/"):
        text = L.readable_text(page(built_site, path))
        assert re.findall(r"(?i)\bseal(?:ed|s)?\b", text.replace("no badge or seal", "")) == [], path
    ff = L.readable_text(page(built_site, "/for-firms/"))
    assert "A method fixed in advance." in ff
    assert "That test is fingerprinted with a SHA-256 hash, recorded, and then run once, as written." in ff
    assert "runs the same pre-registered test again on a later period." in ff
    pr = L.readable_text(page(built_site, "/pricing/"))
    assert "a pre-registered test, fingerprinted before any data is seen, checks" in pr
    assert "running the same pre-registered test again on a later period." in pr
    probs = [p for p in L.lint_build(str(built_site["out"])) if p[0] in ("banned:seal_words", "banned:skill_claims")]
    assert probs == []


def test_frozen_research_bodies_keep_their_words_and_heads_do_not():
    # the frozen bodies are exempt (passthrough rules + compare.py); the head descriptions are public copy
    body = open(os.path.join(REPO, "site", "templates", "lifted", "about.html"), encoding="utf-8").read()
    assert "sealed pre-registration" in body
    import json
    for slug in ("research_strategy-tests", "research_swing-trading-strategies"):
        meta = json.load(open(os.path.join(REPO, "site", "templates", "lifted", slug + ".json"), encoding="utf-8"))
        assert not re.search(r"(?i)seal", meta["description"]) and re.search(r"(?i)sealed", meta["description_was"])
        assert 50 <= len(meta["description"]) <= 155


SIGNATURE_RELS = ["static/js/card/card.js", "static/js/tools/luck-check.js", "static/js/engine/luck.js",
                  "static/js/luck-home.js", "static/js/tools/guess.js", "static/js/journal/ghost.js"]


def test_signature_script_strings_are_linted(built_site, tmp_path):
    tmp = tmp_path / "site"
    shutil.copytree(built_site["out"], tmp)
    words = {"skilled": "banned:skill_claims", "sealed": "banned:seal_words", "verified": "banned:assurance"}
    for rel in SIGNATURE_RELS:
        fp = tmp / rel
        fp.parent.mkdir(parents=True, exist_ok=True)
        fp.write_text("".join(f"export const T{i} = `Your result is ${{'{w}'}}.`;\n" for i, w in enumerate(words)),
                      encoding="utf-8")
    probs = L.lint_build(str(tmp))
    for rel in SIGNATURE_RELS:
        got = {p[0] for p in probs if p[1] == "/" + rel}
        assert set(words.values()) <= got, (rel, got)


def test_other_scripts_keep_the_narrower_scan():
    assert not L.signature_script("/static/js/tools/trade-stats.js")
    assert not L.signature_script("/static/js/motion.js")
    assert L.signature_script("/static/js/card/card-ui.js")


def test_nav_text_refuses_the_new_groups(tmp_path):
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    for word in ("sealed", "skilled"):
        bad = src.replace('desc = "Totals from your trade file"', f'desc = "Totals, {word}"', 1)
        assert bad != src
        (tmp_path / "site.toml").write_text(bad, encoding="utf-8")
        r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], capture_output=True, text=True,
                           env={**os.environ, "DT_OUT": str(tmp_path / "o"), "DT_SITE_TOML": str(tmp_path / "site.toml")})
        assert r.returncode == 1 and "banned word" in r.stderr and word in r.stderr, r.stderr
