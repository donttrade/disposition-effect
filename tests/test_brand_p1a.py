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
    # whole words only. (Until 22 Oct this case was "Seals are animals. Sealant is a word too."; Tester D2
    # made every form of "seal" fail, the animal included, since the site never needs either word.)
    "<p>Zeal and resale are fine; so is the kill switch, and a sea lane.</p>",
    "<p>No badge or seals.</p>",                               # the negation covers the plural (D2 note)
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
    assert "pre-registered" not in pr   # 25 Oct sweep: /pricing/ is for traders; the firm tests are on /for-firms/
    probs = [p for p in L.lint_build(str(built_site["out"])) if p[0] in ("banned:seal_words", "banned:skill_claims")]
    assert probs == []


def test_frozen_research_bodies_keep_their_words_and_heads_do_not():
    # the frozen STUDY bodies are exempt (passthrough rules + compare.py); the head descriptions are public
    # copy, and so (Tester D4, 22 Oct) is the study link/teaser text on the other lifted pages
    body = open(os.path.join(REPO, "site", "templates", "lifted", "research_swing-trading-strategies.html"),
                encoding="utf-8").read()
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


# ------------------------------------------------------------------ brand Tester D1-D5 (22 Oct): the bypasses
def banned(html):
    return {r for r in rules(html) if r.startswith("banned:")}


@pytest.mark.parametrize("text,rule", [
    # D1: a browser folds whitespace into one space, so a phrase wrapped in a template is the same phrase
    ("<p>beat the\n    market</p>", "banned:skill_claims"),
    ("<p>beat  the market</p>", "banned:skill_claims"),
    ("<p>you\n are good</p>", "banned:skill_claims"),
    ("<p>you are  good</p>", "banned:skill_claims"),
    ("<p>pro\ttrader</p>", "banned:skill_claims"),
    ("<p>beat-the-market</p>", "banned:skill_claims"),
    ("<p>beat‑the‑market</p>", "banned:skill_claims"),        # non-breaking hyphens
    ("<p>The seal  of\napproval.</p>", "banned:seal_words"),
    ("<p>Picked as best\nfor you.</p>", "banned:recommend"),          # every multi-word entry, not only P1a's
    ("<p>You need\n  to sell.</p>", "banned:directive"),
])
def test_d1_whitespace_and_hyphens_inside_a_phrase(text, rule):
    assert rule in banned(text), banned(text)


def test_d1_allow_phrases_hold_across_a_line_break_too():
    assert banned("<p>This is not\n   investment advice.</p>") == set()
    assert banned("<p>No regulatory status, no badge\n or seal.</p>") == set()


@pytest.mark.parametrize("text,rule", [
    ("<p>Skills matter.</p>", "banned:skill_claims"),
    ("<p>Your skills show.</p>", "banned:skill_claims"),
    ("<p>Skillset.</p>", "banned:skill_claims"),
    ("<p>Skillfully done.</p>", "banned:skill_claims"),
    ("<p>Skilfully done.</p>", "banned:skill_claims"),
    ("<p>Talents.</p>", "banned:skill_claims"),
    ("<p>Unskilled.</p>", "banned:skill_claims"),
    ("<p>The luckiest file.</p>", "banned:skill_claims"),
    ("<p>Beats the market.</p>", "banned:skill_claims"),
    ("<p>Beating the market.</p>", "banned:skill_claims"),
    ("<p>It beat the markets.</p>", "banned:skill_claims"),
    ("<p>Pro traders use it.</p>", "banned:skill_claims"),
    ("<p>You're good at this.</p>", "banned:skill_claims"),
    ("<p>You’re good.</p>", "banned:skill_claims"),
    ("<p>Two seals of approval.</p>", "banned:seal_words"),
    ("<p>Results sealing in advance.</p>", "banned:seal_words"),
    ("<p>Unsealed data.</p>", "banned:seal_words"),
    ("<p>Resealed.</p>", "banned:seal_words"),
])
def test_d2_plurals_and_word_forms(text, rule):
    assert rule in banned(text), banned(text)


@pytest.mark.parametrize("text", [
    "<p>s<label>eal</label>ed</p>", "<p>s<img alt=''>eal</p>", "<p>se<svg></svg>al</p>",
    "<p>se<svg aria-hidden='true'><path d='M0 0h1'/></svg>aled</p>", "<p>se<picture></picture>aled</p>",
    "<form><input value='sealed'></form>", "<form><input type='submit' value='Sealed'></form>",
    "<form><input type='button' value='Your skills'></form>",
])
def test_d3_words_split_by_inline_tags_and_input_values(text):
    assert banned(text) & {"banned:seal_words", "banned:skill_claims"}, banned(text)


@pytest.mark.parametrize("text", [
    "<p>se<br>aled</p>", "<p>s<div>ealed</div></p>",       # two words on screen, so not a hit (by design)
    "<form><input type='hidden' name='k' value='sealed'></form>", "<form><input type='checkbox' value='sealed'></form>",
])
def test_d3_real_breaks_and_unseen_values_pass(text):
    assert banned(text) == set(), banned(text)


def test_d4_no_seal_in_feed_or_study_link_text(built_site):
    feed = (built_site["out"] / "feed.xml").read_text(encoding="utf-8")
    assert not re.search(r"(?i)\bseal", L.feed_text(feed))
    assert "Study: Swing-trading strategies under hashed pre-registration, a negative result (16 Oct 2026)" in feed
    for path in ("/about/", "/for-researchers/", "/research/"):
        assert not re.search(r"(?i)\b(?:un|re)?seal", L.readable_text(page(built_site, path))), path
    assert "26 rules tested under hashed pre-registration;" in L.readable_text(page(built_site, "/about/"))
    assert L.readable_text(page(built_site, "/research/")).count("each fingerprinted with a hash before any result") == 2
    # the study pages themselves keep their published words
    assert "sealed pre-registration" in L.readable_text(page(built_site, "/research/swing-trading-strategies/"))


def test_d4_lint_reads_the_feed_and_non_study_frozen_bodies():
    xml = ('<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><entry><title>A sealed\n test</title>'
           '<summary type="html">&lt;p&gt;Your skills&lt;/p&gt;</summary></entry></feed>')
    assert {p[0] for p in L.feed_problems(xml, "/feed.xml")} == {"banned:seal_words", "banned:skill_claims"}
    assert L.feed_problems("<urlset><url><loc>https://donttrade.ca/sealed/</loc></url></urlset>", "/sitemap.xml") == []
    body = "<p>26 rules tested under sealed pre-registration.</p>"
    for path in ("/about/", "/for-researchers/", "/research/", "/independence/"):
        assert [p[0] for p in L.frozen_brand_problems(body, path)] == ["banned:seal_words"], path
    assert L.frozen_brand_problems(body, "/research/swing-trading-strategies/") == []
    assert L.frozen_brand_problems("<p>We issue no badge, seal or certificate.</p>", "/independence/") == []


def test_d4_lint_fails_a_build_with_seal_back_in_the_feed_or_about(built_site, tmp_path):
    tmp = tmp_path / "site"
    shutil.copytree(built_site["out"], tmp)
    fp = tmp / "feed.xml"
    fp.write_text(fp.read_text(encoding="utf-8").replace("under hashed pre-registration", "under sealed pre-registration"),
                  encoding="utf-8")
    probs = [p for p in L.lint_build(str(tmp)) if p[0] == "banned:seal_words"]
    assert [p[1] for p in probs] == ["/feed.xml"], probs


def test_d4_feed_fix_survives_a_bundle_and_fails_loudly_when_lost(tmp_path, monkeypatch):
    (old, new), = B.PASSTHROUGH_FILE_FIXES["feed.xml"]
    for text in (f"<feed>{old}</feed>", f"<feed>{new}</feed>"):          # before and after a bundle
        (tmp_path / "feed.xml").write_text(text, encoding="utf-8")
        B.apply_file_fixes(str(tmp_path))
        assert (tmp_path / "feed.xml").read_text(encoding="utf-8") == f"<feed>{new}</feed>"
    (tmp_path / "feed.xml").write_text("<feed><title>Something else</title></feed>", encoding="utf-8")
    with pytest.raises(B.BuildError, match="neither the old nor the new text"):
        B.apply_file_fixes(str(tmp_path))


def _git(repo, *a):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.invalid", *a],
                          capture_output=True, text=True, check=True).stdout.strip()


def test_d5_commit_on_remote_reads_the_remote_tracking_refs(tmp_path):
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "a")
    a = _git(tmp_path, "rev-parse", "HEAD")
    assert not B.commit_on_remote(a, repo=str(tmp_path))                 # never pushed
    _git(tmp_path, "update-ref", "refs/remotes/origin/main", a)
    assert B.commit_on_remote(a, repo=str(tmp_path))
    _git(tmp_path, "commit", "-q", "--allow-empty", "-m", "b")
    assert not B.commit_on_remote(_git(tmp_path, "rev-parse", "HEAD"), repo=str(tmp_path))   # ahead of origin
    assert not B.commit_on_remote("0" * 40, repo=str(tmp_path))


@pytest.mark.parametrize("on_remote", [True, False])
def test_d5_latest_links_only_a_commit_on_the_remote(monkeypatch, on_remote):
    monkeypatch.setattr(B, "commit_on_remote", lambda sha, repo=None: on_remote)
    c = B.latest()["commit"]
    assert c and re.fullmatch(r"[0-9a-f]{7}", c["short"])
    assert c["url"] == (B.COMMIT_URL + c["sha"] if on_remote else None)


def test_d5_built_home_never_links_an_unpushed_commit(built_site):
    home = page(built_site, "/")
    sha = subprocess.run(["git", "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
    if B.commit_on_remote(sha):
        assert f'href="{B.COMMIT_URL}{sha}"' in home
    else:
        assert "/commit/" not in home and f"This site was built from commit <code>{sha[:7]}</code>" in home


# ------------------------------------------------------------------ the dark band (§2.2–2.4): T-AA, T-BAND, T-RM (static part)
sys.path.insert(0, os.path.join(REPO, "checks"))
import contrast as C  # noqa: E402

CSS = open(os.path.join(REPO, "site", "static", "css", "site.css"), encoding="utf-8").read()


def test_band_tokens_pass_aa_in_both_dark_blocks():
    # owner, 25 Oct: in light the band keeps the page tokens (C.PAIRS measure them); the charcoal set is dark-only
    light, dark, media = C.blocks(CSS)
    assert not [k for k in C.tokens(light) if k.startswith("band-")]
    for block in (dark, media):
        t = C.tokens(block)
        for fg, bg, need, why in C.BAND_PAIRS:
            assert C.ratio(t[fg], t[bg]) >= need, (fg, bg, why)
        assert all(v.upper() != "#9A3B1C" for k, v in t.items() if k.startswith("band-"))


def test_contrast_check_refuses_light_rust_on_the_band(tmp_path, monkeypatch):
    bad = CSS.replace("--band-rust: #E07A52;", "--band-rust: #9A3B1C;", 1)
    assert bad != CSS
    light, media, dark = C.blocks(bad)
    t = C.tokens(media)
    assert C.ratio(t["band-rust"], t["band-bg"]) < 4.5


def test_band_has_no_animation_and_hides_motifs_in_forced_colors_and_print():
    i = CSS.index("the dark hero band (ARCHITECT-BRAND-AND-WRAPPED")
    j = CSS.index("/* ------------------------------------------------------------------ motion")
    band = CSS[i:j]
    assert not re.search(r"\b(animation|transition)(-[a-z]+)?\s*:", band)
    assert re.search(r"forced-colors: active\) \{ \.band::before, \.band::after \{ display: none; \}", band)
    assert re.search(r"(?s)@media print \{.*\.band::before, \.band::after \{ display: none; \}", band)


def test_home_hero_is_the_band(built_site):
    html = page(built_site, "/")
    m = re.search(r'<section class="band hero motif-grid motif-axis" aria-labelledby="hero" data-band>', html)
    assert m, "home hero is not the band"
    assert 'id="hero"' in html[m.end():m.end() + 2000]
    assert "style=" not in html[m.start():m.start() + 20000].split("</section>")[0]


def test_h2_tick_only_on_marketing_pages(built_site):
    for path in ("/", "/for-firms/", "/for-traders/", "/for-platforms/"):
        assert '<main id="main" class="mkt">' in page(built_site, path), path
    for path in ("/about/", "/tools/trade-stats/", "/pricing/"):
        assert 'class="mkt"' not in page(built_site, path), path


def test_one_key_num_per_section():
    one = '<section><p class="display key-num">61%</p></section><section><p class="key-num">2</p></section>'
    two = '<section><p class="key-num">61%</p><p class="key-num">2</p></section>'
    assert "key_num" not in rules(one)
    assert "key_num" in rules(two)


# ------------------------------------------------------------------ social links (§2.6): T-SOC1, T-SOC2
import tomllib  # noqa: E402

TOML = os.path.join(REPO, "site", "config", "site.toml")
CHANNELS = [c["url"] for c in tomllib.load(open(TOML, "rb"))["channels"]]
EXPECTED = ["https://donttrade.substack.com", "https://x.com/donttradestudy", "https://github.com/donttrade",
            "https://www.tiktok.com/@donttradestudy", "https://www.instagram.com/donttradestudy/",
            "https://www.youtube.com/@donttradestudy"]
NAMES = ["Substack", "X", "GitHub", "TikTok", "Instagram", "YouTube"]


def follow_links(html):
    nav = re.search(r'(?s)<nav aria-label="Follow donttrade">.*?</nav>', html).group(0)
    return re.findall(r'<a href="([^"]+)" rel="([^"]+)">(.*?)</a>', nav)


def test_soc1_footer_follow_is_exactly_the_official_accounts(built_site):
    for path in ("/", "/about/", "/tools/trade-stats/"):
        links = follow_links(page(built_site, path))
        assert [h for h, _, _ in links] == EXPECTED == CHANNELS, path
        for href, rel, inner in links:
            assert {"me", "noopener"} <= set(rel.split())
            assert '<svg aria-hidden="true" focusable="false"' in inner
            name = re.sub(r"<[^>]+>", "", re.sub(r"(?s)<svg.*?</svg>", "", inner))
            assert name.split()[0] in NAMES, name
        assert [re.sub(r"<[^>]+>", "", re.sub(r"(?s)<svg.*?</svg>", "", i)).split()[0] for _, _, i in links] == NAMES
    nav = re.search(r'(?s)<nav aria-label="Follow donttrade">.*?</nav>', page(built_site, "/")).group(0)
    assert "target=" not in nav
    # inline SVG only: no third-party script, image, iframe or embed in the Follow column
    assert not re.search(r"<(?:script|img|iframe|object|embed|link)\b", nav), nav
    assert "Where to find this" in page(built_site, "/about/")
    about = page(built_site, "/about/").split("<!--frozen:end-->")[1]
    assert ("donttrade.substack.com</a>, <a href=\"https://x.com/donttradestudy\" rel=\"me noopener\">x.com/donttradestudy</a>, "
            "<a href=\"https://github.com/donttrade\" rel=\"me noopener\">github.com/donttrade</a>, "
            "<a href=\"https://www.tiktok.com/@donttradestudy\" rel=\"me noopener\">tiktok.com/@donttradestudy</a>, "
            "<a href=\"https://www.instagram.com/donttradestudy/\" rel=\"me noopener\">instagram.com/donttradestudy</a> and "
            "<a href=\"https://www.youtube.com/@donttradestudy\" rel=\"me noopener\">youtube.com/@donttradestudy</a>. ") in about


def test_soc1_every_brand_icon_is_drawn_inline():
    src = open(os.path.join(REPO, "site", "templates", "partials", "icons.html"), encoding="utf-8").read()
    brand = src[src.index("{%- set BRAND = {"):src.index("{%- macro brand")]
    for name in B.BRAND_ICONS:
        assert re.search(r'"%s": \'<path d="[^"]+"/>\',' % name, brand), name
    assert {c["icon"] for c in tomllib.load(open(TOML, "rb"))["channels"]} <= set(B.BRAND_ICONS)


def test_soc2_about_sentence_and_same_as_match_the_footer(built_site):
    about = page(built_site, "/about/")
    m = re.search(r"(?s)<h2>Where to find this</h2>\s*<p>(.*?)</p>", about)
    assert m and about.index("<!--frozen:end-->") < m.start()
    assert re.findall(r'href="([^"]+)" rel="me noopener"', m.group(1)) == [h for h, _, _ in follow_links(about)]
    import json
    orgs = [node for blob in re.findall(r'(?s)<script type="application/ld\+json">(.*?)</script>', page(built_site, "/"))
            for node in json.loads(blob).get("@graph", []) if node.get("@type") == "Organization"]
    assert orgs and all(o["sameAs"] == EXPECTED for o in orgs), orgs


def _build_with(tmp_path, src):
    (tmp_path / "site.toml").write_text(src, encoding="utf-8")
    return subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], capture_output=True, text=True,
                          env={**os.environ, "DT_OUT": str(tmp_path / "o"), "DT_SITE_TOML": str(tmp_path / "site.toml")})


def test_soc2_another_channel_changes_all_three_places(tmp_path):
    # a made-up extra account in a temp site.toml only (not an account donttrade has)
    src = open(TOML, encoding="utf-8").read()
    extra = ('[[channels]]\nid = "li"\nname = "LinkedIn"\nurl = "https://www.linkedin.com/company/dt-made-up-test"\n'
             'text = "linkedin.com/company/dt-made-up-test"\nicon = "x"\nrel_me = true\n\n[[footer]]\nheading = "Traders"')
    r = _build_with(tmp_path, src.replace('[[footer]]\nheading = "Traders"', extra, 1))
    assert r.returncode == 0, r.stderr
    out = tmp_path / "o"
    home = (out / "index.html").read_text(encoding="utf-8")
    about = (out / "about" / "index.html").read_text(encoding="utf-8")
    url = "https://www.linkedin.com/company/dt-made-up-test"
    assert [h for h, _, _ in follow_links(home)][-1] == url
    assert f'<a href="{url}" rel="me noopener">' in about.split("<!--frozen:end-->")[1].split("</p>")[0]
    assert f'"{url}"' in home.split('"sameAs"')[1].split("]")[0]


@pytest.mark.parametrize("old,new,msg", [
    ('url = "https://x.com/donttradestudy"', 'url = "http://x.com/donttradestudy"', "https://"),
    ('url = "https://x.com/donttradestudy"', 'url = "https://twitter.com/donttradestudy"', "host"),
    ('text = "x.com/donttradestudy"', 'text = "TODO"', "placeholder"),
    ('icon = "x"', 'icon = "mastodon"', "icon"),
    ('url = "https://www.instagram.com/donttradestudy/"', 'url = "https://instagram.com.attacker.net/donttradestudy/"', "host"),
    ('url = "https://www.tiktok.com/@donttradestudy"', 'url = "http://www.tiktok.com/@donttradestudy"', "https://"),
])
def test_soc2_bad_channels_fail_the_build(tmp_path, old, new, msg):
    src = open(TOML, encoding="utf-8").read()
    bad = src.replace(old, new, 1)
    assert bad != src
    r = _build_with(tmp_path, bad)
    assert r.returncode == 1 and msg in r.stderr, r.stderr
