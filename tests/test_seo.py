"""SEO basics for every template-owned page (SEO-PLAN-AND-TOOL-PAGES §3; V2 step 26 for the
pages built so far): unique title and description within length, canonical = own URL and
unique, OG image tags, JSON-LD that parses and matches the visible FAQ word for word, no
address/phone/rating/review in structured data, sitemap and robots.

Keyword volumes in the SEO plan are UNVERIFIED; nothing here (or on a page) claims one.
"""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402

BASE = "https://donttrade.ca"
FLAG_OFF = [p for p in B.PAGES if not p["requires_flag"]]


def read(site, path):
    return (site["out"] / B.out_file("", path).lstrip("/")).read_text(encoding="utf-8")


def head_meta(html):
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    canon = re.findall(r'<link rel="canonical" href="([^"]+)"', html)
    return title, desc, canon


def graph(html):
    blocks = re.findall(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert len(blocks) == 1
    return json.loads(blocks[0])["@graph"]


@pytest.mark.parametrize("page", FLAG_OFF, ids=lambda p: p["path"])
def test_head_tags(built_site, page):
    html = read(built_site, page["path"])
    title, desc, canon = head_meta(html)
    assert 10 <= len(title) <= 60, (title, len(title))
    assert 50 <= len(desc) <= 155, (desc, len(desc))
    # a redirect stub (/who-pays/, meta refresh) names its target as canonical, as it always has
    assert canon == [BASE + page.get("redirect_to", page["path"])]
    for tag in ("og:title", "og:description", "og:url", "og:image", "og:image:width", "og:image:height", "og:image:alt"):
        assert f'property="{tag}"' in html, tag
    assert f'<meta property="og:url" content="{BASE + page["path"]}">' in html


def test_titles_descriptions_canonicals_unique(built_site):
    seen = {"title": {}, "desc": {}, "canon": {}}
    for page in FLAG_OFF:
        t, d, c = head_meta(read(built_site, page["path"]))
        for k, v in (("title", t), ("desc", d), ("canon", c[0])):
            if k == "canon" and page.get("redirect_to"):
                continue  # the stub shares its target's canonical on purpose
            assert v not in seen[k], (k, v, page["path"], seen[k].get(v))
            seen[k][v] = page["path"]


@pytest.mark.parametrize("page", FLAG_OFF, ids=lambda p: p["path"])
def test_jsonld_parses_and_is_honest(built_site, page):
    html = read(built_site, page["path"])
    g = graph(html)
    def keys(o):
        if isinstance(o, dict):
            for k, v in o.items():
                yield k
                yield from keys(v)
        elif isinstance(o, list):
            for v in o:
                yield from keys(v)
    found = set(keys(g))
    for banned in ("aggregateRating", "review", "address", "telephone"):
        assert banned not in found, banned
    assert "Product" not in {n["@type"] for n in g}
    types = {n["@type"] for n in g}
    if page["path"] == "/":
        assert {"WebSite", "Organization"} <= types
    else:
        assert "BreadcrumbList" in types
    if page.get("app"):
        assert "WebApplication" in types
    # FAQPage: the same questions and answers as the visible <details>, word for word
    faq = B.faq_from(html)
    if faq:
        fp = next(n for n in g if n["@type"] == "FAQPage")
        assert [(q["name"], q["acceptedAnswer"]["text"]) for q in fp["mainEntity"]] == faq
        visible = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
        import html as H
        visible = H.unescape(visible)
        for q, a in faq:
            assert q in visible and a in visible


def test_sitemap_and_robots(built_site):
    sm = (built_site["out"] / "sitemap.xml").read_text(encoding="utf-8")
    locs = re.findall(r"<loc>([^<]+)</loc><lastmod>(\d{4}-\d{2}-\d{2})</lastmod>", sm)
    paths = [l[len(BASE):] for l, _ in locs]
    assert len(paths) == len(set(paths))
    for page in FLAG_OFF:
        if page.get("noindex"):
            assert page["path"] not in paths
            assert '<meta name="robots" content="noindex">' in read(built_site, page["path"])
        else:
            assert page["path"] in paths
            assert dict(zip(paths, (d for _, d in locs)))[page["path"]] == page["updated"]
    for bad in ("/welcome/", "/restore/", "/report/", "/thanks/", "/404.html"):
        assert bad not in paths
    robots = (built_site["out"] / "robots.txt").read_text(encoding="utf-8")
    assert robots.startswith("User-agent: *\nAllow: /\n") and robots.rstrip().endswith("Sitemap: https://donttrade.ca/sitemap.xml")
    assert "Disallow" not in robots  # flag off: the paid pages are not built at all
