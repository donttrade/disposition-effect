"""SEO round 1 (6 Nov 2026), ARCHITECT-PLAN-SEO phase 1: one block of tests per item (numbers as in the plan's section 10),
plus the IndexNow script fix, the French hreflang pair, the robots.txt change and the learn_nav flag.

Computed tables are recomputed here a second way (exact fractions, a count of every sequence), never by calling the
function under test. Network tests (doi.org, Zenodo, Crossref) run only with DT_ONLINE=1 and are skipped otherwise.
"""
import functools
import html as H
import http.server
import itertools
import json
import os
import re
import ssl
import subprocess
import sys
import threading
from fractions import Fraction

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.join(REPO, "site", "tools"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import build as B  # noqa: E402
import learn_tables as LT  # noqa: E402
import seo_lint  # noqa: E402

BASE = "https://donttrade.ca"
CONFIG = os.path.join(REPO, "site", "config")
STUDIES = {s["path"]: s for s in json.load(open(os.path.join(CONFIG, "studies.json"), encoding="utf-8"))["studies"]}
ONLINE = os.environ.get("DT_ONLINE") == "1"


# ------------------------------------------------------------------ builds
def build(tmp_path, name="site", toml_edit=None):
    out = tmp_path / name
    env = {**os.environ, "DT_OUT": str(out)}
    env.pop("DT_DEV", None)
    if toml_edit:
        src = open(os.path.join(CONFIG, "site.toml"), encoding="utf-8").read()
        for old, new in toml_edit:
            assert old in src, old
            src = src.replace(old, new, 1)
        t = tmp_path / (name + ".toml")
        t.write_text(src, encoding="utf-8")
        env["DT_SITE_TOML"] = str(t)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture(scope="module")
def site(tmp_path_factory):
    return build(tmp_path_factory.mktemp("seo1"))


def page(site, path):
    rel = path.lstrip("/")
    return (site / (rel + "index.html" if rel.endswith("/") or not rel else rel)).read_text(encoding="utf-8")


def ld(html):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert len(blocks) == 1
    return json.loads(blocks[0])["@graph"]


def kinds(node):
    return node["@type"] if isinstance(node["@type"], list) else [node["@type"]]


def text(fragment):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def main_of(html):
    return re.search(r"(?s)<main\b.*?</main>", html).group(0)


# ------------------------------------------------------------------ 1. related links
RELATED = json.load(open(os.path.join(CONFIG, "related.json"), encoding="utf-8"))["pages"]


@pytest.mark.parametrize("path", sorted(RELATED))
def test_related_block_is_on_the_page_and_links_exist(site, path):
    h = page(site, path)
    aside = re.search(r'(?s)<aside class="wrap related".*?</aside>', h).group(0)
    assert re.findall(r'<a href="([^"]+)">', aside) == [r["href"] for r in RELATED[path]]
    assert 3 <= len(RELATED[path]) <= 5
    for r in RELATED[path]:
        tgt = r["href"].split("#")[0]
        assert os.path.exists(site / (tgt.lstrip("/") + "index.html")), r
        assert '<meta name="robots" content="noindex">' not in page(site, tgt)
        if "#" in r["href"]:
            assert f'id="{r["href"].split("#")[1]}"' in page(site, tgt), r


def test_related_block_is_inside_main_and_after_the_content(site):
    h = page(site, "/tools/drawdown-calculator/")
    m = main_of(h)
    assert m.index('id="related-h"') > m.index("<h1") and re.search(r"</aside>\s*</main>$", m)


def test_tools_index_has_no_related_block_and_stays_in_budget(site):
    import gzip
    h = page(site, "/tools/")
    assert 'class="wrap related"' not in h
    assert len(gzip.compress(main_of(h).encode(), 9)) <= 12 * 1024 + 256


def test_disposition_calculator_is_linked_from_its_study(site):
    study = page(site, "/research/disposition-effect/")
    assert 'href="/tools/disposition-calculator/"' in re.search(r'(?s)<aside class="wrap related".*?</aside>', study).group(0)


def test_every_indexable_study_tool_learn_and_glossary_page_has_three_contextual_inlinks(site):
    assert [p for p in seo_lint.seo_problems(str(site)) if p[0] == "seo:related"] == []


def test_a_related_target_that_is_not_built_fails_the_build():
    pages = {"/tools/": {"path": "/tools/"}, "/gone/": {"path": "/gone/", "noindex": True}}
    with pytest.raises(B.BuildError):
        B.related_for("/tools/trade-stats/", pages)   # its targets are not in this fake build


# ------------------------------------------------------------------ 2. study citation layer
def test_every_study_entry_is_a_zenodo_doi_for_a_built_page():
    assert len(STUDIES) == 4
    for path, st in STUDIES.items():
        assert st["doi"] == "10.5281/zenodo." + st["zenodo_id"]
        assert os.path.exists(os.path.join(REPO, "site", "templates", "lifted", "research_" + path.strip("/").split("/")[-1] + ".html"))


@pytest.mark.parametrize("path", sorted(STUDIES))
def test_study_page_carries_doi_everywhere(site, path):
    st, h = STUDIES[path], page(site, path)
    head = h[:h.index("</head>")]
    assert f'<meta name="citation_doi" content="{st["doi"]}">' in head
    assert f'<meta name="citation_public_url" content="{BASE + path}">' in head
    assert H.unescape(re.search(r'<meta name="citation_title" content="([^"]*)"', head).group(1)) == st["title"]
    cite = re.search(r'(?s)<details class="studycite".*?</details>', h).group(0)
    assert f'href="https://doi.org/{st["doi"]}"' in cite
    apa = text(re.search(r'(?s)<p class="studycite-apa">(.*?)</p>', cite).group(1))
    assert apa == f"donttrade. ({st['published'][:4]}). {st['title']} [Preprint]. Zenodo. https://doi.org/{st['doi']}" == B.apa_line(st)
    bib = H.unescape(re.search(r"(?s)<code>(.*?)</code>", cite).group(1))
    assert bib == B.bibtex_entry(st) and f"doi = {{{st['doi']}}}" in bib
    # the island is in the frozen body, after the header lines and before the first figure, and outside the comparison
    assert "<!--island:start--><details class=\"studycite\"" in h
    assert h.index("studycite") > h.index("<h1") and h.index("studycite") < h.index("Funding:")
    g = ld(h)
    art = next(n for n in g if "ScholarlyArticle" in kinds(n))
    assert kinds(art) == ["Article", "ScholarlyArticle"]
    assert art["identifier"] == {"@type": "PropertyValue", "propertyID": "DOI", "value": st["doi"]}
    assert art["sameAs"] == "https://doi.org/" + st["doi"]


def test_bibtex_escapes_the_percent_sign():
    bib = B.bibtex_entry(STUDIES["/research/disposition-effect/"])
    assert "76.1\\% of 4,659" in bib and "% of" not in bib.replace("\\%", "")


def test_disposition_study_cites_its_dataset_and_papers(site):
    art = next(n for n in ld(page(site, "/research/disposition-effect/")) if "ScholarlyArticle" in kinds(n))
    assert [d["sameAs"] for d in art["isBasedOn"]] == ["https://doi.org/10.7910/DVN/NI6SBJ"]
    assert [c["sameAs"] for c in art["citation"]] == ["https://doi.org/10.1111/0022-1082.00072",
                                                      "https://doi.org/10.1111/j.1540-6261.1985.tb05002.x"]
    h = page(site, "/research/disposition-effect/")
    assert "https://doi.org/10.7910/DVN/NI6SBJ" in h and "CC0 1.0" in h


def test_the_headline_string_is_one_string_everywhere(site):
    """Page H1, citation_title, Zenodo title (config), the cite box, llms.txt and the ScholarlyArticle name agree."""
    llms = (site / "llms.txt").read_text(encoding="utf-8")
    for path, st in STUDIES.items():
        h = page(site, path)
        h1 = text(re.search(r"(?s)<h1[^>]*>(.*?)</h1>", h).group(1))
        assert h1.rstrip(".") == st["title"], path
        assert f"[{st['title']}]({BASE + path})" in llms
        art = next(n for n in ld(h) if "ScholarlyArticle" in kinds(n))
        assert art["name"] == st["title"]
    # the 4,659 / 4,731 pair is labelled the same way in the page description and in llms.txt
    d = re.search(r'<meta name="description" content="([^"]*)"', page(site, "/research/disposition-effect/")).group(1)
    assert "4,659 eligible traders (of 4,731)" in d
    assert "4,659 eligible retail traders" in llms and "4,731 traders were in the data" in llms


def test_the_study_key_numbers_are_on_the_study_page(site):
    t = text(page(site, "/research/disposition-effect/"))
    assert "76.1%" in t and "3,547 of 4,659" in t and "74.9–77.3%" in t
    assert "94%" in text(page(site, "/research/insider-buying-edge/")) and "470,754" in text(page(site, "/research/insider-buying-edge/"))


def test_baselines_hold_the_new_highwire_lines():
    import compare
    for path, st in STUDIES.items():
        base = compare.baselines()[path]["citation"]
        assert base[-2:] == [["citation_doi", st["doi"]], ["citation_public_url", BASE + path]]


def test_frozen_bodies_are_unchanged(site):
    import compare
    assert compare.compare_site(str(site)) == []


@pytest.mark.skipif(not ONLINE, reason="network: DT_ONLINE=1")
def test_online_dois_resolve_and_match_zenodo():
    import urllib.request
    ctx = ssl.create_default_context()

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, *a, **k):
            return None
    opener = urllib.request.build_opener(NoRedirect, urllib.request.HTTPSHandler(context=ctx))
    for st in STUDIES.values():
        try:
            opener.open(urllib.request.Request("https://doi.org/" + st["doi"], headers={"User-Agent": "donttrade-tests/1.0"}))
            raise AssertionError("expected a redirect")
        except urllib.error.HTTPError as e:
            assert e.code == 302 and "zenodo.org" in e.headers["Location"], st["doi"]
        rec = json.load(urllib.request.urlopen(f"https://zenodo.org/api/records/{st['zenodo_id']}", context=ctx))
        assert rec["doi"] == st["doi"] and rec["metadata"]["title"] == st["title"]
        assert any(BASE + st["path"] == r["identifier"] for r in rec["metadata"]["related_identifiers"])


@pytest.mark.skipif(not ONLINE, reason="network: DT_ONLINE=1")
def test_online_references_match_crossref():
    import urllib.request
    refs = json.load(open(os.path.join(CONFIG, "references.json"), encoding="utf-8"))["refs"]
    for r in refs.values():
        m = json.load(urllib.request.urlopen(urllib.request.Request(f"https://api.crossref.org/works/{r['doi']}",
                                             headers={"User-Agent": "donttrade-tests/1.0 (mailto:donttrade.research@gmail.com)"})))["message"]
        assert m["title"][0].lower() == r["title"].lower() or m["title"][0].lower().replace(":", "") == r["title"].lower().replace(":", "")
        assert m["container-title"][0] == r["journal"] and m["volume"] == r["volume"] and m["issue"] == r["issue"]
        assert m["page"].replace("–", "-") == r["pages"].replace("–", "-") and m["issued"]["date-parts"][0][0] == r["year"]


def test_learn_and_glossary_dois_are_all_in_the_verified_list(site):
    ok = seo_lint.verified_dois()
    for path in ("/learn/", "/learn/drawdown-recovery-table/", "/learn/losing-streak-probability/", "/glossary/"):
        for doi in re.findall(r'href="https://doi\.org/([^"]+)"', main_of(page(site, path))):
            assert H.unescape(doi) in ok or path == "/glossary/", (path, doi)
    assert [p for p in seo_lint.seo_problems(str(site)) if p[0] == "seo:doi"] == []


def test_a_doi_that_is_not_in_the_list_is_caught(site, tmp_path):
    out = tmp_path / "bad"
    import shutil
    shutil.copytree(site, out)
    f = out / "learn" / "losing-streak-probability" / "index.html"
    f.write_text(f.read_text(encoding="utf-8").replace("10.1080/07468342.1990.11973306", "10.1234/not-checked"), encoding="utf-8")
    assert any(p[0] == "seo:doi" for p in seo_lint.seo_problems(str(out)))


# ------------------------------------------------------------------ 3. Dataset JSON-LD
@pytest.mark.parametrize("path,n", [("/research/disposition-effect/", 1), ("/research/insider-buying-edge/", 1),
                                    ("/learn/drawdown-recovery-table/", 1), ("/learn/losing-streak-probability/", 1)])
def test_dataset_jsonld_points_at_a_real_csv(site, path, n):
    sets = [x for x in ld(page(site, path)) if x["@type"] == "Dataset"]
    assert len(sets) == n
    for d in sets:
        url = d["distribution"][0]["contentUrl"]
        assert d["distribution"][0]["encodingFormat"] == "text/csv" and url.startswith(BASE + "/data/")
        assert (site / url[len(BASE) + 1:]).read_text(encoding="utf-8").count("\n") > 2
        assert d["isPartOf"]["@id"] == BASE + path + "#article" and d["license"].startswith("https://creativecommons.org/")


# ------------------------------------------------------------------ 4. hreflang, robots, French pair
def test_french_before_you_pay_pairs_with_the_english_twin(site):
    fr, en = page(site, "/fr/avant-de-payer/"), page(site, "/before-you-pay/")
    for h in (fr, en):
        langs = dict(re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">', h))
        assert langs["fr"] == BASE + "/fr/avant-de-payer/" and langs["en"] == BASE + "/before-you-pay/"
        assert langs["x-default"] == BASE + "/before-you-pay/"
        assert '<meta name="robots" content="noindex">' in h
    assert 'href="/before-you-pay/" hreflang="en"' in fr and 'href="/fr/avant-de-payer/" hreflang="fr"' in en


def test_pricing_no_longer_declares_a_french_alternate(site):
    assert "hreflang" not in re.search(r"(?s)<head>.*?</head>", page(site, "/pricing/")).group(0)


def test_terms_and_privacy_pairs_are_untouched(site):
    for en, fr in (("/terms/", "/fr/conditions/"), ("/privacy/", "/fr/confidentialite/")):
        assert f'hreflang="fr" href="{BASE + fr}"' in page(site, en)
        assert f'hreflang="en" href="{BASE + en}"' in page(site, fr)


def test_robots_no_longer_blocks_before_you_pay(site):
    r = (site / "robots.txt").read_text(encoding="utf-8")
    assert "/before-you-pay/" not in r
    assert r.splitlines()[:6] == ["User-agent: *", "Allow: /", "Disallow: /welcome/", "Disallow: /restore/", "Disallow: /report/",
                                  "Disallow: /tools/prop-challenge-simulator/e/"]
    assert '<meta name="robots" content="noindex">' in page(site, "/before-you-pay/")
    assert "/before-you-pay/" not in (site / "sitemap.xml").read_text(encoding="utf-8")
    assert "/fr/avant-de-payer/" not in (site / "sitemap.xml").read_text(encoding="utf-8")


def test_lint_catches_a_robots_blocked_hreflang_target_and_an_indexable_page_naming_a_noindex_one(site, tmp_path):
    import shutil
    out = tmp_path / "bad"
    shutil.copytree(site, out)
    r = out / "robots.txt"
    r.write_text(r.read_text(encoding="utf-8").replace("Disallow: /welcome/", "Disallow: /welcome/\nDisallow: /before-you-pay/"), encoding="utf-8")
    assert any(p[0] == "seo:hreflang" and "robots.txt" in p[2] for p in seo_lint.seo_problems(str(out)))
    # the OLD mispairing: the indexable /pricing/ naming the noindex French page
    f = out / "pricing" / "index.html"
    f.write_text(f.read_text(encoding="utf-8").replace('<link rel="canonical"', f'<link rel="alternate" hreflang="fr" href="{BASE}/fr/avant-de-payer/">\n<link rel="canonical"', 1), encoding="utf-8")
    assert any(p[0] == "seo:hreflang" and "noindex" in p[2] for p in seo_lint.seo_problems(str(out)))


def test_the_build_still_refuses_a_one_sided_hreflang(site, tmp_path):
    import shutil
    out = tmp_path / "oneway"
    shutil.copytree(site, out)
    f = out / "before-you-pay" / "index.html"
    f.write_text(re.sub(r'<link rel="alternate" hreflang="[^"]+" href="[^"]+">\n?', "", f.read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(B.BuildError):
        B.check_language_pairs(str(out), BASE)


# ------------------------------------------------------------------ 5. llms.txt
def test_llms_txt_is_plain_text_and_every_url_is_built_and_indexable(site):
    t = (site / "llms.txt").read_text(encoding="utf-8")
    assert t.startswith("# donttrade\n\n> ") and "Not investment advice; not a registered adviser." in t
    sm = set(re.findall(r"<loc>" + re.escape(BASE) + r"(/[^<]*)</loc>", (site / "sitemap.xml").read_text(encoding="utf-8")))
    urls = re.findall(r"\]\((https://[^)]+)\)", t)
    assert len(urls) >= 20
    for u in urls:
        assert u[len(BASE):] in sm and os.path.exists(site / (u[len(BASE) + 1:] + "index.html")), u
    for tool in B.TOOLS:
        assert BASE + tool["href"] in urls
    for lp in B.LEARN_PATHS:
        assert BASE + lp in urls
    for st in STUDIES.values():
        assert f"DOI {st['doi']}" in t
    assert t.count("DOI ") == 4   # the two strategy studies have none, and the file does not invent one
    assert "pre-registered research" not in t   # not every study was pre-registered


# ------------------------------------------------------------------ 6. Organization JSON-LD
def test_organization_has_logo_and_the_visible_about_line(site):
    org = next(n for n in ld(page(site, "/")) if n["@type"] == "Organization")
    assert org["logo"]["url"] == BASE + "/assets/logo-512.png"
    from PIL import Image
    assert Image.open(site / "assets" / "logo-512.png").size == (512, 512)
    assert text(re.search(r'(?s)<p class="lede[^"]*">(.*?)</p>', page(site, "/about/")).group(1)).startswith(org["description"])
    assert org["description"] == B.ABOUT_LINE and "one person" in org["description"]
    for forbidden in ("foundingDate", "address", "telephone", "legalName"):
        assert forbidden not in org


# ------------------------------------------------------------------ 7. footer and the learn_nav flag
def test_footer_links_for_researchers_on_every_page_and_learn_is_off_by_default(site):
    n = 0
    for fp in site.rglob("index.html"):
        h = fp.read_text(encoding="utf-8")
        if '<footer class="site-footer">' not in h:
            continue
        foot = re.search(r'(?s)<footer class="site-footer">.*?</footer>', h).group(0)
        assert 'href="/for-researchers/"' in foot, fp
        assert 'href="/learn/"' in foot, fp   # 6 Nov: learn_nav ON (owner approved SEO; footer-first)
        n += 1
    assert n >= 5
    toml = open(os.path.join(CONFIG, "site.toml"), encoding="utf-8").read()
    assert re.search(r"(?m)^learn_nav = true\b", toml)


def test_learn_nav_flag_adds_only_the_footer_column(tmp_path, site):
    on = site   # 6 Nov: the default build has learn_nav ON; build the OFF variant to compare
    site = build(tmp_path, "learn_off", [("learn_nav = true", "learn_nav = false")])
    for p in ("/", "/tools/trade-stats/", "/learn/"):
        h_on, h_off = page(on, p), page(site, p)
        foot_on = re.search(r'(?s)<footer class="site-footer">.*?</footer>', h_on).group(0)
        assert '<h2>Learn</h2>' in foot_on and 'href="/learn/"' in foot_on and 'href="/learn/drawdown-recovery-table/"' in foot_on
        assert '<h2>Learn</h2>' not in h_off
    # the header nav never got a Learn link either way, and the pages are the same
    assert 'href="/learn/"' not in re.search(r'(?s)<header class="site-header">.*?</header>', page(on, "/")).group(0)
    assert page(on, "/learn/drawdown-recovery-table/").replace(re.search(r'(?s)<footer class="site-footer">.*?</footer>', page(on, "/learn/drawdown-recovery-table/")).group(0), "") == \
        page(site, "/learn/drawdown-recovery-table/").replace(re.search(r'(?s)<footer class="site-footer">.*?</footer>', page(site, "/learn/drawdown-recovery-table/")).group(0), "")
    assert seo_lint.seo_problems(str(on)) == []


def test_learn_pages_exist_and_are_in_the_sitemap_with_the_flag_off(site):
    sm = (site / "sitemap.xml").read_text(encoding="utf-8")
    for p in B.LEARN_PATHS:
        pg = next(x for x in B.PAGES if x["path"] == p)
        assert f"<loc>{BASE}{p}</loc><lastmod>{pg['updated']}</lastmod>" in sm
    assert len(B.LEARN_PATHS) == 3


# ------------------------------------------------------------------ 8. titles and descriptions
EXPECT_TITLES = {
    "/research/": "Research: Trader Behaviour, Markets and Strategy Tests",
    "/tools/trade-stats/": "Trade Stats for Your File: Win Rate, Profit Factor, Drawdown",
    "/glossary/": "Trading Psychology and Risk Glossary: Terms Explained",
    "/tools/disposition-calculator/": "Disposition Effect Calculator: Do You Sell Winners Early?",
    "/tools/pass-rate-calculator/": "Prop Firm Pass Rate Calculator for Firm Operators",
    "/tools/prop-challenge-simulator/": "Prop Firm Challenge Simulator: Readiness Check on Your Days",
    "/for-researchers/": "For Researchers and Press: Data, Code, DOIs — donttrade",
    "/learn/": "Learn: Trading Habits, Risk Math and the Evidence",
}


@pytest.mark.parametrize("path,title", sorted(EXPECT_TITLES.items()))
def test_new_titles(site, path, title):
    h = page(site, path)
    assert re.search(r"<title>(.*?)</title>", h).group(1) == H.escape(title, quote=False) and len(title) <= 60


def test_simulator_title_is_under_60_and_its_h1_is_unchanged(site):
    assert len("Prop Firm Challenge Simulator: Readiness Check on Your Days") == 59
    assert text(re.search(r"(?s)<h1[^>]*>(.*?)</h1>", page(site, "/tools/prop-challenge-simulator/")).group(1)) == "Challenge Readiness Check"


def test_code_description_is_now_long_enough(site):
    d = re.search(r'<meta name="description" content="([^"]*)"', page(site, "/code/")).group(1)
    assert 70 <= len(d) <= 155 and d.startswith("Where each study")


def test_every_title_and_description_is_in_range_and_unique(site):
    assert [p for p in seo_lint.seo_problems(str(site)) if p[0] in ("seo:title", "seo:meta")] == []


def test_the_research_title_makes_no_claim_the_studies_do_not_back(site):
    # not every study is pre-registered and not every one has code and a DOI: the title and description do not say so
    h = page(site, "/research/")
    head = re.search(r"(?s)<head>.*?</head>", h).group(0)
    assert "Pre-Registered" not in head and "every donttrade study with data, code and a DOI" not in head.lower()
    assert "Trader Behaviour, Markets and Strategy Tests" in head


def test_sample_report_title_is_not_changed_until_the_real_report_ships(site):
    # "Example Trading Habit Report on Real Public Data" is true only once the realreport branch is merged
    assert "<title>Example report — donttrade</title>" in page(site, "/sample-report/")


# ------------------------------------------------------------------ 9. WebApplication + FAQPage on the two calculators
@pytest.mark.parametrize("path", ["/tools/disposition-calculator/", "/tools/pass-rate-calculator/"])
def test_calculators_have_webapplication_and_a_matching_visible_faq(site, path):
    h = page(site, path)
    g = ld(h)
    assert {"BreadcrumbList", "WebApplication", "FAQPage"} <= {n["@type"] for n in g}
    faq = B.faq_from(h)
    assert len(faq) == 5
    node = next(n for n in g if n["@type"] == "FAQPage")
    assert [(q["name"], q["acceptedAnswer"]["text"]) for q in node["mainEntity"]] == faq
    vis = text(h)
    for q, a in faq:
        assert q in vis and a in vis
    # the FAQ sits outside the frozen body on the lifted page
    if "disposition" in path:
        assert h.index("faq-h") > h.index("<!--frozen:end-->")


# ------------------------------------------------------------------ 10. Open Graph cards
CARDS = ["tool-stats", "tool-prop", "tool-lot", "tool-rr", "tool-dd", "tool-heat", "tool-disp", "tool-pass",
         "tools", "glossary", "learn", "learn-drawdown", "learn-streaks"]


@pytest.mark.parametrize("name", CARDS)
def test_og_card_file(name):
    from PIL import Image
    fp = os.path.join(REPO, "docs", "assets", "og", name + ".png")
    assert os.path.getsize(fp) < 300 * 1024
    assert Image.open(fp).size == (1200, 630)


def test_pages_point_at_their_own_card(site):
    for path, card in (("/tools/trade-stats/", "tool-stats"), ("/tools/prop-challenge-simulator/", "tool-prop"),
                       ("/tools/lot-size-calculator/", "tool-lot"), ("/tools/risk-reward-calculator/", "tool-rr"),
                       ("/tools/drawdown-calculator/", "tool-dd"), ("/tools/trading-heatmap/", "tool-heat"),
                       ("/tools/disposition-calculator/", "tool-disp"), ("/tools/pass-rate-calculator/", "tool-pass"),
                       ("/tools/", "tools"), ("/glossary/", "glossary"), ("/learn/", "learn"),
                       ("/learn/drawdown-recovery-table/", "learn-drawdown"), ("/learn/losing-streak-probability/", "learn-streaks")):
        h = page(site, path)
        assert f'<meta property="og:image" content="{BASE}/assets/og/{card}.png">' in h, path
        assert (site / "assets" / "og" / (card + ".png")).exists()
    assert "default.png" not in page(site, "/tools/trade-stats/")


def test_card_text_has_no_numbers():
    # the text of every card is a tool name and its card line, or the fixed lines in make_seo_assets.specs
    src = open(os.path.join(REPO, "checks", "make_seo_assets.py"), encoding="utf-8").read()
    fixed = re.findall(r'\("(?:tools|glossary|learn|learn-drawdown|learn-streaks)\.png", "([^"]*)", "([^"]*)", None\)', src)
    assert len(fixed) == 5 and not any(re.search(r"\d", t + s) for t, s in fixed)
    assert not any(re.search(r"\d", t["name"] + t["short"]) for t in B.TOOLS)


# ------------------------------------------------------------------ 11. glossary
OLD_IDS = ["disposition-effect", "pgr", "plr", "paper", "realised", "qualifying", "orphan", "denominator", "interval", "t", "form4"]
NEW_IDS = ["win-rate", "profit-factor", "expectancy", "r-multiple", "break-even-win-rate", "max-drawdown", "drawdown-duration",
           "recovery-gain", "position-size", "lot", "point-value", "risk-of-ruin", "loss-aversion", "sunk-cost", "revenge-trading",
           "tilt", "overtrading", "martingale", "averaging-down", "trailing-drawdown", "daily-drawdown", "pre-registration"]


def test_glossary_anchor_list_and_jsonld(site):
    h = page(site, "/glossary/")
    ids = re.findall(r'<dt id="([^"]+)">', h)
    assert ids == OLD_IDS + NEW_IDS and len(set(ids)) == len(ids) == 33
    g = ld(h)
    terms = [n for n in g if n["@type"] == "DefinedTerm"]
    assert [t["url"].split("#")[1] for t in terms] == ids
    sets = [n for n in g if n["@type"] == "DefinedTermSet"]
    assert len(sets) == 1 and len(sets[0]["hasDefinedTerm"]) == len(ids)
    for t in terms:
        assert 40 < len(t["description"]) and t["inDefinedTermSet"] == {"@id": BASE + "/glossary/#set"}
    # the twelve frozen terms are untouched (compare.py also holds them)
    import compare
    assert [d for d in compare.compare_site(str(site)) if d[0] == "/glossary/"] == []


def test_glossary_is_over_thirty_terms_and_the_island_is_inside_the_frozen_body(site):
    h = page(site, "/glossary/")
    assert "<!--island:start--><h2 id=\"trading-risk-terms\">" in h
    assert h.index("trading-risk-terms") > h.index("<!--frozen:start-->") and h.index("<!--frozen:end-->") > h.index("trading-risk-terms")


GLOSS = {t["id"]: t for t in json.load(open(os.path.join(CONFIG, "glossary_terms.json"), encoding="utf-8"))["terms"]}
JS = os.path.join(REPO, "site", "static", "js")
# each formula in the glossary, with the line(s) of the tool's own code that compute it (all must be present)
FORMULA_CODE = {
    "win-rate": [("engine/stats.js", "win_rate: (wins + losses) ? wins / (wins + losses) : null")],
    "profit-factor": [("engine/stats.js", "profit_factor: losses ? gp / -gl : NO_LOSSES")],
    "expectancy": [("engine/stats.js", "expectancy: n ? total / n : null"), ("tools/risk-reward.js", "winRate * r - (1 - winRate)")],
    "break-even-win-rate": [("tools/risk-reward.js", "const breakEven = 1 / (1 + r);")],
    "recovery-gain": [("tools/drawdown-core.js", "return d / (1 - d);")],
    "position-size": [("tools/lot-size.js", "const perLot = stop * vpp;"), ("tools/lot-size.js", "const lots = riskAmount / perLot;")],
    "revenge-trading": [("tools/habit-flags.js", "export const REENTRY_S = 900;")],
}


@pytest.mark.parametrize("term", sorted(FORMULA_CODE))
def test_glossary_formula_matches_the_tools_code(term):
    for rel, snippet in FORMULA_CODE[term]:
        assert snippet in open(os.path.join(JS, rel), encoding="utf-8").read(), (term, rel)


def test_glossary_formulas_say_what_the_code_says():
    f = {k: GLOSS[k].get("formula", "") for k in GLOSS}
    assert f["win-rate"] == "win rate = winning trades ÷ (winning trades + losing trades)"
    assert f["profit-factor"] == "profit factor = gross profit ÷ gross loss"
    assert f["break-even-win-rate"] == "break-even win rate = 1 ÷ (1 + R)"
    assert f["recovery-gain"].startswith("recovery gain = d ÷ (1 − d)")
    assert f["position-size"] == "position size = amount risked ÷ (stop distance × value per point for one lot)"
    assert "15 minutes" in GLOSS["revenge-trading"]["text"]   # 900 s, as habit-flags.js (REENTRY_S)
    allowed = ("100,000", "15 minutes", "1R", "(1979)", "(1985)", "Above 1,")
    for g in GLOSS.values():
        t = g["text"]
        for a in allowed:
            t = t.replace(a, "")
        assert not re.search(r"\d", t), (g["id"], "an example number in a glossary term: only the lot size, the 15-minute window, 1R, a profit factor above 1 and the two papers years")


def test_glossary_links_and_sources_resolve(site):
    refs = json.load(open(os.path.join(CONFIG, "references.json"), encoding="utf-8"))["refs"]
    for t in GLOSS.values():
        if "source" in t:
            assert t["source"]["ref"] in refs
        for key in ("measured_in", "see_also"):
            for m in t.get(key, []):
                tgt = m["href"].split("#")[0]
                assert os.path.exists(site / (tgt.lstrip("/") + "index.html")), (t["id"], m)


def test_glossary_wording_is_not_advice():
    blob = " ".join(g["text"] for g in GLOSS.values()).lower()
    for w in ("you should", "we recommend", "best ", "must ", "need to", "improve", "signal"):
        assert w not in blob, w


# ------------------------------------------------------------------ 12. /learn/ hub and template contract
@pytest.mark.parametrize("path", sorted(B.LEARN_PATHS))
def test_learn_template_contract(site, path):
    h = page(site, path)
    m = main_of(h)
    assert len(re.findall(r"<h1[\s>]", h)) == 1
    ans = re.search(r'(?s)</h1>\s*<section id="answer"[^>]*>\s*<p>(.*?)</p>', m)
    assert ans and 40 <= len(text(ans.group(1)).split()) <= 60
    assert len({u for u, _ in seo_lint.internal_links(m)} - {path}) >= 3
    assert "not investment advice" in text(h)   # the footer disclaimer
    assert f"Updated {B.longdate(next(p for p in B.PAGES if p['path'] == path)['updated'])}" in text(m)
    assert not re.search(r'\sstyle="', h) and not re.search(r"<script(?![^>]*\bsrc=)(?![^>]*application/ld\+json)[^>]*>", h)
    assert not re.search(r"\son[a-z]+=\"", h)
    assert "script-src &#39;self&#39;" in h
    assert [p for p in seo_lint.seo_problems(str(site)) if p[0] == "seo:learn" and p[1] == path] == []


def test_learn_hub_is_a_collection_and_articles_have_article_faq_and_breadcrumb(site):
    assert {n["@type"] for n in ld(page(site, "/learn/"))} == {"BreadcrumbList", "CollectionPage", "ItemList"}
    items = next(n for n in ld(page(site, "/learn/")) if n["@type"] == "ItemList")["itemListElement"]
    assert [i["url"] for i in items] == [BASE + "/learn/drawdown-recovery-table/", BASE + "/learn/losing-streak-probability/"]
    for p in ("/learn/drawdown-recovery-table/", "/learn/losing-streak-probability/"):
        g = ld(page(site, p))
        assert {"Article", "FAQPage", "BreadcrumbList", "Dataset"} <= {n["@type"] for n in g}
        art = next(n for n in g if n["@type"] == "Article")
        pg = next(x for x in B.PAGES if x["path"] == p)
        assert art["datePublished"] == "2026-11-06" and art["dateModified"] == pg["updated"] and art["headline"] == pg["h1"]
        crumbs = next(n for n in g if n["@type"] == "BreadcrumbList")["itemListElement"]
        assert [c["name"] for c in crumbs] == ["Home", "Learn", pg["crumb"]]
        faq = B.faq_from(page(site, p))
        assert faq and [(q["name"], q["acceptedAnswer"]["text"]) for q in next(n for n in g if n["@type"] == "FAQPage")["mainEntity"]] == faq


def test_learn_pages_do_not_describe_ways_to_stop_a_habit(site):
    for p in B.LEARN_PATHS:
        t = text(main_of(page(site, p))).lower()
        for w in ("how to stop", "stop revenge", "cooling-off", "cool off", "you should", "we recommend", "best strategy",
                  "best lot size", "how much to risk", "guaranteed", "accurate", "beta", "fake", "demo", "made-up"):
            assert w not in t, (p, w)


def test_learn_citations_are_links_to_dois_with_a_checked_date(site):
    h = page(site, "/learn/losing-streak-probability/")
    refs = json.load(open(os.path.join(CONFIG, "references.json"), encoding="utf-8"))["refs"]
    r = refs["schilling1990"]
    assert f'href="https://doi.org/{r["doi"]}"' in h and "confirmed with Crossref on 6 November 2026" in text(h)
    assert "The longest run of heads" in text(h) and r["journal"] in text(h) and r["crossref_checked"] == "2026-11-06"


# ------------------------------------------------------------------ 13. the computed tables, recomputed a second way
def exact_run_prob(n, win_pct, k):
    """P(at least one run of k losses in n trades) by the recurrence a_m = a_(m-1) - p q^k a_(m-k-1) (exact fractions)."""
    p, q = Fraction(win_pct, 100), 1 - Fraction(win_pct, 100)
    a = [Fraction(1)] * (k) + [1 - q ** k]            # a_0 .. a_(k-1) = 1, a_k = 1 - q^k
    for m in range(k + 1, n + 1):
        a.append(a[m - 1] - p * q ** k * a[m - k - 1])
    return 1 - (a[n] if n >= k else Fraction(1))


def brute_run_prob(n, win_pct, k):
    p, q = win_pct / 100, 1 - win_pct / 100
    total = 0.0
    for seq in itertools.product("WL", repeat=n):
        run = best = 0
        for c in seq:
            run = run + 1 if c == "L" else 0
            best = max(best, run)
        if best >= k:
            pr = 1.0
            for c in seq:
                pr *= q if c == "L" else p
            total += pr
    return total


@pytest.mark.parametrize("n,w,k", [(n, w, k) for n in (3, 5, 8, 12, 16) for w in (30, 50, 70) for k in (2, 3, 4, 5)])
def test_streak_probability_matches_a_count_of_every_sequence(n, w, k):
    assert LT.prob_run_at_least(n, w, k) == pytest.approx(brute_run_prob(n, w, k), abs=1e-12)
    assert float(exact_run_prob(n, w, k)) == pytest.approx(brute_run_prob(n, w, k), abs=1e-12)


def test_every_cell_of_the_streak_tables_matches_the_exact_recurrence():
    for n in LT.TRADE_COUNTS:
        for w in LT.WIN_RATES:
            for k in LT.RUN_LENGTHS:
                assert LT.prob_run_at_least(n, w, k) == pytest.approx(float(exact_run_prob(n, w, k)), abs=1e-12), (n, w, k)


def test_the_architect_checkpoint_value():
    # 21 Oct note: over 100 fair trials, P(longest run of losses >= 5) = 0.810
    assert round(float(exact_run_prob(100, 50, 5)), 3) == 0.810 and round(LT.prob_run_at_least(100, 50, 5), 3) == 0.810


def test_recovery_gain_matches_the_closed_form_and_inverts():
    for d in LT.DRAWDOWNS:
        g = Fraction(d, 100) / (1 - Fraction(d, 100))
        assert LT.recovery_gain(d) == pytest.approx(float(g) * 100, abs=1e-9)
        assert (1 - Fraction(d, 100)) * (1 + g) == 1          # a gain of g on what is left gets back to exactly the high


def test_periods_table_is_the_smallest_whole_number_of_periods():
    for d in LT.PERIOD_DRAWDOWNS:
        for g in LT.PERIOD_GAINS:
            n = LT.periods_to_recover(d, g)
            need = 1 / (1 - Fraction(d, 100))
            f = 1 + Fraction(str(g)) / 100
            assert f ** n >= need and (n == 1 or f ** (n - 1) < need), (d, g, n)


def test_streak_cost_matches_repeated_multiplication():
    for f in LT.COST_FRACTIONS:
        for k in LT.RUN_LENGTHS:
            bal = Fraction(1)
            for _ in range(k):
                bal *= 1 - Fraction(f, 100)
            assert LT.streak_cost(f, k) == pytest.approx(float((1 - bal) * 100), abs=1e-9)


def test_enumeration_is_every_sequence_once():
    e = LT.enumerate_runs(3, 2)
    assert sorted(x["seq"] for x in e) == sorted("".join(s) for s in itertools.product("WL", repeat=3))
    assert sum(x["hit"] for x in e) / len(e) == LT.prob_run_at_least(3, 50, 2) == 0.375


def test_built_page_tables_are_the_computed_ones(site):
    dd = page(site, "/learn/drawdown-recovery-table/")
    rows = re.findall(r'<tr><th scope="row">(\d+)%</th><td>([\d,.]+%)</td></tr>', dd)
    assert [(int(a), b) for a, b in rows] == [(d, f"{float(Fraction(d, 100) / (1 - Fraction(d, 100)) * 100):,.1f}%") for d in LT.DRAWDOWNS]
    ans = text(re.search(r'<section id="answer".*?</section>', dd, re.S).group(0))
    assert "10% takes a gain of 11.1%" in ans and "50% takes 100%" in ans
    st = page(site, "/learn/losing-streak-probability/")
    for n in LT.TRADE_COUNTS:
        tbl = re.search(rf'(?s)<caption>{n} trades: chance of a run of at least</caption>.*?</table>', st).group(0)
        cells = re.findall(r'<tr><th scope="row">(\d+)%</th><td>([^<]+)</td><td>([^<]+)</td><td>([^<]+)</td></tr>', tbl)
        assert len(cells) == len(LT.WIN_RATES)
        for w, *vals in cells:
            for k, v in zip(LT.RUN_LENGTHS, vals):
                p = float(exact_run_prob(n, int(w), k))
                want = "<0.1%" if p * 100 < 0.05 else ">99.9%" if p * 100 > 99.95 else f"{p * 100:.1f}%"
                assert H.unescape(v) == want, (n, w, k)
    assert "81.0%" in text(st) and "4.4%" in text(st)   # the answer block, from the table's own cells


def test_csv_downloads_are_the_tables(site):
    rec = (site / "data" / "drawdown-recovery.csv").read_text(encoding="utf-8").splitlines()
    assert rec[0].startswith("drawdown_percent,gain_needed_percent,periods_at_0.5_percent_per_period") and len(rec) == 1 + len(LT.DRAWDOWNS)
    for line, d in zip(rec[1:], LT.DRAWDOWNS):
        cells = line.split(",")
        assert int(cells[0]) == d and float(cells[1]) == pytest.approx(d / (100 - d) * 100, abs=1e-4)
    stk = (site / "data" / "losing-streak-probability.csv").read_text(encoding="utf-8").splitlines()
    assert stk[0] == "win_rate_percent,trades,run_of_losses_at_least,probability" and len(stk) == 1 + 9 * 3 * 3
    for line in stk[1:]:
        w, n, k, p = line.split(",")
        assert float(p) == pytest.approx(float(exact_run_prob(int(n), int(w), int(k))), abs=1e-6)
    assert (site / "data" / "disposition-pgr-plr.csv").exists()   # the studies' CSVs still pass through


def test_the_page_never_gives_a_probability_of_exactly_zero_or_one(site):
    st = text(page(site, "/learn/losing-streak-probability/"))
    assert not re.search(r"(?<![.\d<>])(?:0|100)(?:\.0)?%\s*(?:chance|probability)", st)


# ------------------------------------------------------------------ 14. sitemap and the lint additions catch planted faults
def test_the_whole_build_passes_the_seo_lint(site):
    assert seo_lint.seo_problems(str(site)) == []


def planted(site, tmp_path, rel, fn):
    import shutil
    out = tmp_path / "plant"
    if out.exists():
        shutil.rmtree(out)
    shutil.copytree(site, out)
    f = out / rel
    f.write_text(fn(f.read_text(encoding="utf-8")), encoding="utf-8")
    return seo_lint.seo_problems(str(out))


def test_lint_catches_a_second_h1(site, tmp_path):
    probs = planted(site, tmp_path, "tools/trade-stats/index.html", lambda h: h.replace("<main", "<h1>Two</h1><main", 1))
    assert any(p[0] == "seo:h1" for p in probs)


def test_lint_catches_bad_jsonld(site, tmp_path):
    probs = planted(site, tmp_path, "glossary/index.html", lambda h: h.replace('"@graph"', '"@graph" broken', 1))
    assert any(p[0] == "seo:jsonld" for p in probs)


def test_lint_catches_a_default_card_on_a_tool_page(site, tmp_path):
    probs = planted(site, tmp_path, "tools/trade-stats/index.html", lambda h: h.replace("/assets/og/tool-stats.png", "/assets/og/default.png"))
    assert any(p[0] == "seo:og" for p in probs)


def test_lint_catches_a_long_title_and_a_short_description(site, tmp_path):
    probs = planted(site, tmp_path, "learn/index.html", lambda h: re.sub(r"<title>.*?</title>", "<title>" + "x" * 70 + "</title>", h))
    assert any(p[0] == "seo:title" for p in probs)
    probs = planted(site, tmp_path, "learn/index.html", lambda h: re.sub(r'(<meta name="description" content=")[^"]*', r"\1short", h, count=1))
    assert any(p[0] == "seo:meta" for p in probs)


def test_lint_catches_a_learn_page_with_a_long_answer_block_advice_and_no_updated_line(site, tmp_path):
    probs = planted(site, tmp_path, "learn/index.html", lambda h: h.replace("Learn explains", "You should read this. " + "word " * 40 + "Learn explains", 1))
    assert any(p[0] == "seo:learn" and "answer block" in p[2] for p in probs) and any("you should" in p[2] for p in probs)
    probs = planted(site, tmp_path, "learn/index.html", lambda h: h.replace("Updated 6 November 2026", "", 1))
    assert any(p[0] == "seo:learn" and "Updated" in p[2] for p in probs)


def test_lint_catches_a_llms_url_that_is_not_built_and_a_dataset_that_is_missing(site, tmp_path):
    probs = planted(site, tmp_path, "llms.txt", lambda t: t + "- [x](https://donttrade.ca/nowhere/)\n")
    assert any(p[0] == "seo:llms" for p in probs)
    import shutil
    out = tmp_path / "plant2"
    shutil.copytree(site, out)
    (out / "data" / "drawdown-recovery.csv").unlink()
    assert any(p[0] == "seo:dataset" for p in seo_lint.seo_problems(str(out)))


def test_lint_catches_too_few_contextual_inlinks(site, tmp_path):
    import shutil
    out = tmp_path / "plant3"
    shutil.copytree(site, out)
    for fp in out.rglob("index.html"):
        h = fp.read_text(encoding="utf-8")
        h2 = re.sub(r'(?s)(<main\b.*?</main>)', lambda m: m.group(1).replace('href="/learn/losing-streak-probability/"', 'href="/x/"'), h)
        if h2 != h:
            fp.write_text(h2, encoding="utf-8")
    assert any(p[0] == "seo:related" and p[1] == "/learn/losing-streak-probability/" for p in seo_lint.seo_problems(str(out)))


def test_lint_py_runs_the_seo_checks_on_a_real_build(site):
    import lint
    probs = lint.lint_build(str(site), paid=True, analytics=True, pilot=False, badges=False)
    assert probs == [] or all(p[0] != "seo" and not p[0].startswith("seo:") for p in probs)


# ------------------------------------------------------------------ IndexNow script
def test_indexnow_sends_a_plain_descriptive_user_agent_not_pythons(tmp_path):
    import indexnow_ping as IX
    seen = []

    class H_(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            seen.append(self.headers.get("User-Agent"))
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"thekey")

        def do_POST(self):
            seen.append(self.headers.get("User-Agent"))
            self.rfile.read(int(self.headers.get("Content-Length", 0)))
            self.send_response(202)
            self.end_headers()

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H_)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/thekey.txt"
        assert IX.http_get(url) == "thekey"
        assert IX.http_post(url, {"a": 1}) == 202
    finally:
        srv.shutdown()
    assert seen == [IX.USER_AGENT, IX.USER_AGENT]
    assert IX.USER_AGENT == "donttrade-indexnow/1.0 (+https://donttrade.ca)" and "python" not in IX.USER_AGENT.lower()


def test_indexnow_honours_ssl_cert_file(tmp_path):
    import indexnow_ping as IX
    bundle = ssl.get_default_verify_paths().cafile or ""
    if not bundle or not os.path.exists(bundle):
        pytest.skip("no system CA bundle to take one certificate from")
    pem = re.search(r"-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----", open(bundle, encoding="ascii", errors="ignore").read(), re.S).group(0)
    one = tmp_path / "one.pem"
    one.write_text(pem + "\n", encoding="ascii")
    ctx = IX.ssl_context({"SSL_CERT_FILE": str(one)})
    assert ctx.cert_store_stats()["x509_ca"] == 1 and ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname
    assert IX.ssl_context({}).verify_mode == ssl.CERT_REQUIRED
    with pytest.raises(IX.Refused):
        IX.ssl_context({"SSL_CERT_FILE": str(tmp_path / "missing.pem")})
    assert IX.main(["--dry-run"]) in (0, 2)   # reachable without the network: it only reads the files


def test_indexnow_key_check_uses_the_agent_through_run(tmp_path):
    import indexnow_ping as IX
    calls = []
    IX.key_live(lambda u: calls.append(u) or "k\n", "donttrade.ca", "k")
    assert calls == ["https://donttrade.ca/k.txt"]


# ------------------------------------------------------------------ fix round 1: public statements must be exactly true
PREREG = {"/research/portfolio-driven-disposition-effect/", "/research/volatility-scaled-momentum/",
          "/research/swing-trading-strategies/", "/research/strategy-tests/"}


def test_pre_registered_never_describes_a_study_that_was_not():
    """A related entry may say 'pre-registered' only for a pre-registered study, and only on a page that does not call
    its own study (disposition, insider) the same kind."""
    for src, items in RELATED.items():
        for r in items:
            if "pre-registered" in (r["label"] + " " + r["why"]).lower():
                assert r["href"] in PREREG, (src, r)
                assert "another pre-registered" not in r["why"].lower(), (src, r)


def test_related_text_does_not_promise_data_code_and_a_doi_for_every_study():
    for src, items in RELATED.items():
        for r in items:
            w = r["why"].lower()
            assert not ("every study" in w and "doi" in w and "where published" not in w), (src, r)


def test_learn_pages_claim_listing_on_code_only_if_code_lists_the_script(site):
    code = page(site, "/code/")
    assert "site/learn_tables.py" in code and "Scripts that build this site" in code
    for p in B.LEARN_PATHS:
        if "listed on" in page(site, p):
            assert "learn_tables.py" in code


def test_code_description_claims_nothing_untrue(site):
    d = re.search(r'<meta name="description" content="([^"]*)"', page(site, "/code/")).group(1)
    assert "each result" not in d and "Free licences" not in d and "not yet public" in d


def test_sitemap_lastmod_moves_for_changed_pages(site):
    sm = (site / "sitemap.xml").read_text(encoding="utf-8")
    for p in ["/glossary/", "/code/", "/research/", "/tools/trade-stats/", "/tools/drawdown-calculator/",
              "/research/disposition-effect/", "/research/strategy-tests/", "/tools/disposition-calculator/"]:
        assert f"<loc>{BASE}{p}</loc><lastmod>2026-11-06</lastmod>" in sm, p
    # 7 Nov: the press page gained the sell-off study's entries (build.LIFTED_UPDATED), so its content date moved with them
    assert f"<loc>{BASE}/for-researchers/</loc><lastmod>2026-11-07</lastmod>" in sm


def test_glossary_lede_does_not_overclaim_sources(site):
    t = text(page(site, "/glossary/"))
    assert "have no single formal definition" in t


# ------------------------------------------------------------------ fix round 2
def test_related_text_does_not_say_scripts_exist_for_every_study():
    for src, items in RELATED.items():
        for r in items:
            assert "scripts behind every study" not in r["why"].lower(), (src, r)
            if r["href"] == "/code/":
                assert "where published" in r["why"], (src, r)


def test_plan_gap_does_not_say_every_script_is_public(site):
    t = text(page(site, "/plan-gap/"))
    assert "Every study, its script and every correction" not in t
    assert "the scripts for two studies are not yet public" in t
    assert 'href="/corrections/"' in main_of(page(site, "/plan-gap/"))


# ------------------------------------------------------------------ fix round 3
def test_trade_stats_title_and_meta_do_not_headline_platform_readers(site):
    h = page(site, "/tools/trade-stats/")
    title = re.search(r"<title>(.*?)</title>", h).group(1)
    desc = re.search(r'<meta name="description" content="([^"]*)"', h).group(1)
    assert title == "Trade Stats for Your File: Win Rate, Profit Factor, Drawdown" and len(title) <= 60
    assert len(desc) <= 155 and "runs in your browser" in desc.lower()
    for w in ("MT5", "MT4", "IBKR", "Tradovate", "TradingView"):
        assert w not in title and w not in desc, w
    assert "Not yet tested on a real export" in text(h)   # the page body keeps its honest caveat


def test_loss_share_table_has_no_ten_percent_row_and_is_still_computed(site):
    assert LT.COST_FRACTIONS == (1, 2, 5)
    t = page(site, "/learn/losing-streak-probability/")
    tbl = re.search(r"(?s)<caption>Fall from the high after a run of losses.*?</table>", t).group(0)
    assert re.findall(r'<th scope="row">(\d+)%</th>', tbl) == ["1", "2", "5"]


def test_plan_gap_fix_is_logged_on_corrections_and_in_the_feed(site):
    c = page(site, "/corrections/")
    row = re.search(r"(?s)<tr><td>6 Nov 2026</td><td><a href=\"/plan-gap/\">.*?</tr>", c).group(0)
    assert "Author, site review" in row and "not yet public" in row
    feed = (site / "feed.xml").read_text(encoding="utf-8")
    assert "tag:donttrade.github.io,2026-11-06:correction-7" in feed and "<updated>2026-11-07T00:00:00Z</updated>\n  <author>" in feed   # 7 Nov: the feed's date is its newest entry's (the sell-off study)


# ------------------------------------------------------------------ fix round 4
def test_no_page_says_made_up_fake_or_demo(site):
    """The owner's wording rule, on every built page's visible text (frozen study bodies included since 6 Nov)."""
    rx = re.compile(r"\b(made-up|made up|fake|demo)\b", re.I)
    for fp in site.rglob("*.html"):
        h = re.sub(r"(?s)<(script|style)\b.*?</\1>", " ", fp.read_text(encoding="utf-8"))
        assert not rx.search(text(h)), (str(fp.relative_to(site)), rx.search(text(h)).group(0))
