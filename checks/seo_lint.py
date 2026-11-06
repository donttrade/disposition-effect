#!/usr/bin/env python3
"""seo_lint.py (6 Nov 2026, SEO round 1): the site-wide SEO checks of ARCHITECT-PLAN-SEO phase 1, run by checks/lint.py on
every build (lint_build) and callable alone:

    python3 checks/seo_lint.py [site/_site]

Each check returns (rule, where, detail) tuples, as lint.py does.

  seo:h1               an indexable page has exactly one <h1>
  seo:jsonld           every JSON-LD block of every page parses, and a page has one @graph block
  seo:title / seo:meta title 10 to 60 characters, description 70 to 155, each unique among the indexable pages
  seo:og               an indexable tool page, /tools/, /glossary/ and every /learn/ page has its own card, not default.png
  seo:related          every Related target exists, is indexable, and its #anchor exists; a tool, study, /learn/ and
                       glossary page has at least 3 contextual inlinks (links inside another page's <main>)
  seo:hreflang         a hreflang target is neither robots-disallowed nor noindex while the page naming it is indexable
  seo:llms             every URL in /llms.txt is built and in the sitemap (so indexable)
  seo:learn            a /learn/ page: one H1, an answer block of 40 to 60 words, at least 3 links in <main>, an updated date
                       equal to the sitemap lastmod, and none of the claim-lint phrases below
  seo:dataset          a Dataset's contentUrl is a file in the build
  seo:logo             the Organization logo is a file of at least 112 x 112 pixels
  seo:doi              a DOI linked from a /learn/ page or the glossary additions is in config/references.json or studies.json
"""
import html as _html
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))

BASE = "https://donttrade.ca"
LD_RE = re.compile(r'<script type="application/ld\+json">(.*?)</script>', re.S)
MAIN_RE = re.compile(r"(?s)<main\b.*?</main>")
HREF_RE = re.compile(r'<a\b[^>]*?\bhref="([^"]+)"')
INLINK_MIN = 3
INLINK_PREFIXES = ("/tools/", "/research/", "/learn/")
INLINK_PATHS = ("/glossary/",)
# the claim lint for /learn/ (ARCHITECT-PLAN-SEO section 9): advice phrasing is out, whatever the surrounding sentence
LEARN_BANNED = ("you should", "we recommend", "best strategy", "best lot size", "how much to risk", "guaranteed", "accurate",
                "exact result", "beta", "fake", "demo", "made-up", "made up")
LEARN_WORD_RE = {w: re.compile(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", re.I) for w in LEARN_BANNED}


def _read(path):
    with open(path, encoding="utf-8", errors="replace") as f:
        return f.read()


def page_file(out, path):
    rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return os.path.join(out, rel)


def sitemap_paths(out):
    fp = os.path.join(out, "sitemap.xml")
    if not os.path.exists(fp):
        return []
    return re.findall(r"<loc>" + re.escape(BASE) + r"(/[^<]*)</loc>", _read(fp))


def robots_disallows(out):
    fp = os.path.join(out, "robots.txt")
    if not os.path.exists(fp):
        return []
    return [m.strip() for m in re.findall(r"(?mi)^Disallow:\s*(\S*)", _read(fp)) if m.strip()]


def text_of(fragment):
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", fragment))).strip()


def head_of(html):
    title = re.search(r"<title>(.*?)</title>", html, re.S)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html)
    og = re.search(r'<meta property="og:image" content="([^"]*)"', html)
    return (_html.unescape(title.group(1)) if title else "", _html.unescape(desc.group(1)) if desc else "", og.group(1) if og else "")


def internal_links(fragment):
    """The internal link targets in a fragment, as (path, fragment-id or None)."""
    out = []
    for href in HREF_RE.findall(fragment):
        href = _html.unescape(href)
        if href.startswith(BASE):
            href = href[len(BASE):]
        if not href.startswith("/") or href.startswith("//"):
            continue
        path, _, frag = href.partition("#")
        path = path.split("?")[0]
        out.append((path, frag or None))
    return out


def ids_of(html):
    return set(re.findall(r'\sid="([^"]+)"', html))


def seo_problems(out):
    import build
    problems = []
    paths = sitemap_paths(out)
    if not paths:
        return [("seo", "/sitemap.xml", "no sitemap in the build")]
    pages = {p: _read(page_file(out, p)) for p in paths if os.path.exists(page_file(out, p))}
    for p in paths:
        if p not in pages:
            problems.append(("seo:sitemap", p, "a sitemap URL that is not in the build"))

    # ---- one H1, titles and descriptions
    seen_t, seen_d = {}, {}
    for p, h in sorted(pages.items()):
        if p == "/404.html":
            continue
        n = len(re.findall(r"<h1[\s>]", h))
        if n != 1:
            problems.append(("seo:h1", p, f"{n} <h1> elements, expected exactly 1"))
        title, desc, og = head_of(h)
        if not 10 <= len(title) <= 60:
            problems.append(("seo:title", p, f"title is {len(title)} characters (10 to 60): {title!r}"))
        if not 70 <= len(desc) <= 155:
            problems.append(("seo:meta", p, f"description is {len(desc)} characters (70 to 155)"))
        if "/for-firms/" in p and "?" in p:
            continue
        for what, val, seen in (("title", title, seen_t), ("meta", desc, seen_d)):
            if val in seen:
                problems.append((f"seo:{what}", p, f"same {what} as {seen[val]}"))
            seen[val] = p
        tool_page = p.startswith("/tools/") and p.count("/") >= 3 or p in ("/tools/", "/glossary/") or p.startswith("/learn/")
        if tool_page and og.endswith("/assets/og/default.png"):
            problems.append(("seo:og", p, "the default Open Graph card on a tool, glossary or /learn/ page"))
        if tool_page:
            m = re.search(r"/assets/og/[^/]+$", og)
            if not m or not os.path.exists(os.path.join(out, "assets", "og", os.path.basename(og))):
                problems.append(("seo:og", p, f"the card {og} is not in the build"))

    # ---- JSON-LD on every built page
    for root, _, files in os.walk(out):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            fp = os.path.join(root, name)
            rel = "/" + os.path.relpath(fp, out)
            h = _read(fp)
            blocks = LD_RE.findall(h)
            for b in blocks:
                try:
                    json.loads(b)
                except ValueError as e:
                    problems.append(("seo:jsonld", rel, f"JSON-LD does not parse: {e}"))
            if len(blocks) > 1:
                problems.append(("seo:jsonld", rel, f"{len(blocks)} JSON-LD blocks (one @graph per page)"))

    # ---- related blocks and contextual inlinks
    inlinks = {p: set() for p in pages}
    for src, h in pages.items():
        m = MAIN_RE.search(h)
        if not m:
            continue
        for tgt, frag in internal_links(m.group(0)):
            if tgt in inlinks and tgt != src:
                inlinks[tgt].add(src)
            if tgt in pages and frag and frag not in ids_of(pages[tgt]):
                problems.append(("seo:related", src, f"links {tgt}#{frag}, which has no such id"))
    for p in pages:
        if (p.startswith(INLINK_PREFIXES) and p != "/tools/" or p in INLINK_PATHS) and len(inlinks[p]) < INLINK_MIN:
            problems.append(("seo:related", p, f"{len(inlinks[p])} contextual inlinks (links inside another page's <main>), "
                             f"at least {INLINK_MIN} expected"))
    rel_cfg = os.path.join(REPO, "site", "config", "related.json")
    if os.path.exists(rel_cfg):
        for src, items in json.load(open(rel_cfg, encoding="utf-8"))["pages"].items():
            for r in items:
                tgt = r["href"].split("#")[0]
                if tgt not in pages:
                    problems.append(("seo:related", src, f"related target {tgt} is not an indexable page of the build"))
                aside = re.search(r'(?s)<aside class="wrap related".*?</aside>', pages.get(src, ""))
                if src in pages and (not aside or f'href="{r["href"]}"' not in aside.group(0)):
                    problems.append(("seo:related", src, f"related link {r['href']} is not on the built page"))

    # ---- hreflang
    dis = robots_disallows(out)
    for root, _, files in os.walk(out):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            fp = os.path.join(root, name)
            rel = "/" + os.path.relpath(fp, out).replace("index.html", "")
            h = _read(fp)
            alts = re.findall(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">', h)
            if not alts:
                continue
            self_noindex = '<meta name="robots" content="noindex' in h
            for lang, href in alts:
                tgt = href[len(BASE):] if href.startswith(BASE) else href
                if any(tgt.startswith(d) for d in dis):
                    problems.append(("seo:hreflang", rel, f"hreflang {lang} target {tgt} is disallowed in robots.txt"))
                tf = page_file(out, tgt)
                if os.path.exists(tf) and not self_noindex and '<meta name="robots" content="noindex' in _read(tf):
                    problems.append(("seo:hreflang", rel, f"indexable page names {tgt} (noindex) as its {lang} alternate"))

    # ---- llms.txt
    lf = os.path.join(out, "llms.txt")
    if not os.path.exists(lf):
        problems.append(("seo:llms", "/llms.txt", "missing"))
    else:
        txt = _read(lf)
        for url in re.findall(r"\]\((https://[^)]+)\)", txt):
            tgt = url[len(BASE):] if url.startswith(BASE) else None
            if tgt is None or tgt not in set(paths):
                problems.append(("seo:llms", "/llms.txt", f"{url} is not an indexable page of the build"))

    # ---- /learn/ template and claim lint
    for p in sorted(pages):
        if not p.startswith("/learn/"):
            continue
        h = pages[p]
        main = MAIN_RE.search(h).group(0)
        m = re.search(r'(?s)<h1[^>]*>.*?</h1>\s*<section id="answer"[^>]*>\s*<p>(.*?)</p>', main)
        if not m:
            problems.append(("seo:learn", p, 'no <section id="answer"> with a paragraph straight after the H1'))
        else:
            n = len(text_of(m.group(1)).split())
            if not 40 <= n <= 60:
                problems.append(("seo:learn", p, f"the answer block is {n} words (40 to 60)"))
        if len({t for t, _ in internal_links(main)} - {p}) < 3:
            problems.append(("seo:learn", p, "fewer than 3 internal links in <main>"))
        lm = re.search(r"<loc>" + re.escape(BASE + p) + r"</loc><lastmod>([^<]+)</lastmod>", _read(os.path.join(out, "sitemap.xml")))
        if f"Updated {_long_date(lm.group(1))}" not in text_of(main) if lm else True:
            problems.append(("seo:learn", p, "no visible 'Updated <date>' equal to the sitemap lastmod"))
        visible = text_of(main)
        for w, rx in LEARN_WORD_RE.items():
            if rx.search(visible):
                problems.append(("seo:learn", p, f"claim lint: {w!r}"))
        for m2 in re.finditer(r'href="https://doi\.org/([^"]+)"', main):
            problems += _doi_problem(p, m2.group(1))

    # ---- the glossary's added terms: DOIs
    if "/glossary/" in pages:
        for m2 in re.finditer(r'href="https://doi\.org/([^"]+)"', pages["/glossary/"]):
            doi = _html.unescape(m2.group(1))
            if doi not in _frozen_glossary_dois():
                problems += _doi_problem("/glossary/", doi)

    # ---- Dataset contentUrl and the Organization logo
    for p, h in pages.items():
        for b in LD_RE.findall(h):
            try:
                g = json.loads(b).get("@graph", [])
            except ValueError:
                continue
            for node in g:
                if node.get("@type") == "Dataset":
                    for d in node.get("distribution", []):
                        u = d.get("contentUrl", "")
                        if not u.startswith(BASE + "/") or not os.path.isfile(os.path.join(out, u[len(BASE) + 1:])):
                            problems.append(("seo:dataset", p, f"Dataset contentUrl {u} is not a file in the build"))
                if node.get("@type") == "Organization":
                    logo = node.get("logo")
                    u = logo.get("url") if isinstance(logo, dict) else logo
                    fp = os.path.join(out, (u or "")[len(BASE) + 1:]) if (u or "").startswith(BASE + "/") else None
                    if not fp or not os.path.isfile(fp):
                        problems.append(("seo:logo", p, f"Organization logo {u} is not a file in the build"))
                    else:
                        from PIL import Image
                        w, hgt = Image.open(fp).size
                        if min(w, hgt) < 112:
                            problems.append(("seo:logo", p, f"Organization logo is {w}x{hgt}, at least 112x112 expected"))
    return problems


def _long_date(iso):
    import datetime as dt
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B')} {d.year}"


_FROZEN_DOIS = []


def _frozen_glossary_dois():
    """The DOIs the twelve frozen glossary terms already link (not ours to restrict)."""
    if not _FROZEN_DOIS:
        t = _read(os.path.join(REPO, "site", "templates", "lifted", "glossary.html"))
        _FROZEN_DOIS.extend(_html.unescape(x) for x in re.findall(r'href="https://doi\.org/([^"]+)"', t))
    return _FROZEN_DOIS


def verified_dois():
    refs = json.load(open(os.path.join(REPO, "site", "config", "references.json"), encoding="utf-8"))["refs"]
    stu = json.load(open(os.path.join(REPO, "site", "config", "studies.json"), encoding="utf-8"))
    ok = {r["doi"] for r in refs.values()} | {s["doi"] for s in stu["studies"]} | {d["doi"] for d in stu["datasets"].values()}
    return ok


def _doi_problem(where, doi):
    doi = _html.unescape(doi)
    if doi not in verified_dois():
        return [("seo:doi", where, f"doi:{doi} is not in config/references.json (Crossref-checked) or studies.json")]
    return []


def main(argv):
    out = argv[0] if argv else os.path.join(REPO, "site", "_site")
    probs = seo_problems(out)
    for rule, where, detail in probs:
        print(f"SEO  {rule:14} {where}: {detail}")
    print("seo_lint:", "PASS" if not probs else f"{len(probs)} problem(s)")
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
