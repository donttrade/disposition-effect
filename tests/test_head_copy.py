"""Head copy (title, description, OG/Twitter) for link previews and crawlers.

* the home page reads trader-first (free tools, research on trader habits) with firms last; title <= 60
  chars, description 120-160, and og:title / og:description / twitter:description carry the same text;
* every built page (template-owned and lifted) has a non-empty title unique across the site and a
  description of at most 160 chars;
* no title or description holds an advice / grading word (list below, whole words, plural forms too).
  Three published descriptions say "Not a signal" / "Not advice" as a negation; they are xfail(strict)
  until their copy is reworded, so a rewrite that clears the word turns the case into a reminder to drop it.
"""
import html as H
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402

HOME_TITLE = "donttrade - free trading tools and research on trader habits"
HOME_DESC = ("Free in-browser tools: trade stats, prop challenge odds, drawdown and risk-reward. "
             "Research on how traders behave. For firms: fixed-price measurement.")

WORDS = ("advice", "recommend", "should", "fix", "coach", "must", "need to", "signal", "improve", "mentor",
         "certified", "verified", "audited", "seal")
BANNED = re.compile(r"\b(?:" + "|".join(re.escape(w) for w in WORDS) + r")(?:s|es)?\b", re.I)

# published descriptions that use a listed word as a negation; copy left as is (owner's call)
KNOWN = {
    "research/strategy-tests/index.html": "signal",          # "... Not a strategy or signal."
    "research/swing-trading-strategies/index.html": "signal",  # "... Not a strategy or a signal."
    "sample-report/index.html": "advice",                     # "... Not a customer. Not advice."
}


def _first(pattern, text):
    m = re.search(pattern, text, re.S)
    return H.unescape(m.group(1)).strip() if m else None


def head(text):
    return {
        "title": _first(r"<title>(.*?)</title>", text),
        "desc": _first(r'<meta name="description" content="([^"]*)"', text),
        "og_title": _first(r'<meta property="og:title" content="([^"]*)"', text),
        "og_desc": _first(r'<meta property="og:description" content="([^"]*)"', text),
        "tw_desc": _first(r'<meta name="twitter:description" content="([^"]*)"', text),
    }


def all_pages(site):
    out = site["out"]
    pages = {str(p.relative_to(out)): head(p.read_text(encoding="utf-8")) for p in sorted(out.rglob("*.html"))}
    assert "index.html" in pages and len(pages) > 20, sorted(pages)
    return pages


def test_home_source_holds_the_new_copy():
    home = next(p for p in B.PAGES if p["path"] == "/")
    assert home["title"] == HOME_TITLE
    assert home["description"] == HOME_DESC


def test_home_head(built_site):
    h = all_pages(built_site)["index.html"]
    assert h["title"] == HOME_TITLE and len(h["title"]) <= 60, (h["title"], len(h["title"]))
    assert h["desc"] == HOME_DESC and 120 <= len(h["desc"]) <= 160, (h["desc"], len(h["desc"]))
    assert h["og_title"] == h["title"]
    assert h["og_desc"] == h["desc"]
    assert h["tw_desc"] == h["desc"]
    assert "behavioural measurement for trading firms" not in (built_site["out"] / "index.html").read_text(
        encoding="utf-8")


def test_every_page_title_and_description(built_site):
    seen = {}
    for rel, h in all_pages(built_site).items():
        assert h["title"], (rel, "empty or missing <title>")
        assert h["title"] not in seen, (rel, h["title"], "same title as", seen.get(h["title"]))
        seen[h["title"]] = rel
        assert h["desc"] is not None, (rel, "no meta description")
        assert len(h["desc"]) <= 160, (rel, h["desc"], len(h["desc"]))
        # the home copy belongs to the home page only
        if rel != "index.html":
            assert h["title"] != HOME_TITLE and h["desc"] != HOME_DESC, rel


def test_no_advice_words_in_titles_or_descriptions(built_site):
    for rel, h in all_pages(built_site).items():
        if rel in KNOWN:
            continue
        for field in ("title", "desc"):
            assert not BANNED.search(h[field] or ""), (rel, field, h[field], BANNED.findall(h[field] or ""))


@pytest.mark.parametrize("rel", sorted(KNOWN))
@pytest.mark.xfail(strict=True, reason="published description uses the word as a negation; copy not reworded")
def test_no_advice_words_known_negations(built_site, rel):
    h = all_pages(built_site)[rel]
    for field in ("title", "desc"):
        assert not BANNED.search(h[field] or ""), (rel, field, h[field])


@pytest.mark.parametrize("text", ["Not advice.", "We recommend it.", "You should", "A coach", "you must",
                                  "you need to", "Signals", "improve it", "mentors", "certified", "verified",
                                  "audited", "Seal", "a fix", "fixes"])
def test_word_list_catches(text):
    assert BANNED.search(text), text


@pytest.mark.parametrize("text", [HOME_TITLE, HOME_DESC, "fixed-price", "prefix", "sealant", "needed"])
def test_word_list_leaves_alone(text):
    assert not BANNED.search(text), text
