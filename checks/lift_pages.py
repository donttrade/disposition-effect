#!/usr/bin/env python3
"""lift_pages.py — plan steps 28–29: lift the 20 old passthrough pages into the v2 templates.

    python3 checks/lift_pages.py            # (re)write the lifted fragments from docs/
    python3 checks/lift_pages.py --check    # exit 1 if the committed fragments differ from docs/

What it writes, per page (slug = the path with / → _, "404" for /404.html):
  site/templates/lifted/<slug>.html   the old page's <main> content, word for word
  site/templates/lifted/<slug>.json   head facts: title, description, og image, sitemap date,
                                      citation_* meta, the Article JSON-LD, scripts, crumb
  checks/lifted-baseline/<slug>.json  what the body must still say (compare.py): visible text,
                                      ids, links, tables and citation meta of the OLD page, with
                                      the documented LIFT_FIXES applied
  site/static/js/legacy/<name>.js     the two old calculators' inline scripts, byte for byte, except
                                      for a calculator in CODE_FIXED: its v1 script goes to
                                      checks/lifted-baseline/legacy-v1/<name>.js (the record) and
                                      the live file is maintained by hand (the dated code fixes)

The ONLY changes to the body markup are mechanical, forced by the v2 CSP
(script-src 'self'; style-src 'self': no inline script, style element, style attribute or
event handler can run):
  * style="…" attributes become ls-* classes (STYLE_CLASS; an unknown style fails loudly);
  * a <style> element in <main> is removed (its rules are in site.css, "lifted pages");
  * a <script> element in <main> is moved, unchanged, to site/static/js/legacy/;
  * onsubmit="return false" is removed (lifted.js stops those forms submitting).
plus the three text fixes in LIFT_FIXES, which the passthrough build already applied
(PASSTHROUGH_FIXES / PASSTHROUGH_CHROME before steps 28–29). compare.py proves that nothing
else in the visible text, ids, links, tables or citation meta changed.

This reads docs/ as it is before the step-30 bundle (old design). Once docs/ is replaced by
the build, the fragments are the source and this script refuses to run (it finds no old
header in docs/).
"""
import hashlib
import html as _h
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOCS = os.path.join(REPO, "docs")
FRAG_DIR = os.path.join(REPO, "site", "templates", "lifted")
BASE_DIR = os.path.join(HERE, "lifted-baseline")
JS_DIR = os.path.join(REPO, "site", "static", "js", "legacy")
sys.path.insert(0, HERE)

# path → (docs file, crumb, parent crumb or None, nav section or None)
PAGES = [
    ("/research/", "research/index.html", "Research", None, "/research/"),
    ("/research/disposition-effect/", "research/disposition-effect/index.html",
     "The disposition effect, 4,659 traders", ("Research", "/research/"), "/research/"),
    ("/research/insider-buying-edge/", "research/insider-buying-edge/index.html",
     "The insider-buying edge", ("Research", "/research/"), "/research/"),
    ("/research/portfolio-driven-disposition-effect/", "research/portfolio-driven-disposition-effect/index.html",
     "Portfolio-driven disposition effect", ("Research", "/research/"), "/research/"),
    ("/research/strategy-tests/", "research/strategy-tests/index.html",
     "50 trading strategies tested", ("Research", "/research/"), "/research/"),
    ("/research/swing-trading-strategies/", "research/swing-trading-strategies/index.html",
     "26 swing-trading strategies", ("Research", "/research/"), "/research/"),
    ("/research/volatility-scaled-momentum/", "research/volatility-scaled-momentum/index.html",
     "Volatility-scaled momentum", ("Research", "/research/"), "/research/"),
    ("/about/", "about/index.html", "About", None, "/about/"),
    ("/corrections/", "corrections/index.html", "Corrections", None, None),
    ("/independence/", "independence/index.html", "Independence", None, None),
    ("/for-researchers/", "for-researchers/index.html", "Researchers & press", None, None),
    ("/code/", "code/index.html", "Methods and code", None, None),
    ("/who-pays/", "who-pays/index.html", "Moved: Independence policy", None, None),
    ("/glossary/", "glossary/index.html", "Glossary", None, None),
    ("/plan-gap/", "plan-gap/index.html", "The plan gap", None, None),
    ("/sample-memo/", "sample-memo/index.html", "Sample memo and method", None, None),
    ("/sample-report/", "sample-report/index.html", "Sample trader report", None, None),
    ("/404.html", "404.html", "Not found", None, None),
    ("/tools/disposition-calculator/", "tools/disposition-calculator/index.html",
     "Disposition-effect calculator", ("Free tools", "/tools/"), "/tools/"),
    ("/tools/pass-rate-calculator/", "tools/pass-rate-calculator/index.html",
     "Prop-firm pass-rate calculator", ("Free tools", "/tools/"), "/tools/"),
]

# Inline styles (blocked by style-src 'self') → classes in site.css with the same effect.
STYLE_CLASS = {
    "max-width:var(--measure)": "ls-measure",
    "margin-top:-6px;margin-bottom:1em": "ls-mtn6",
    "min-width:720px": "ls-minw720",
    "margin-top:-8px": "ls-mtn8",
    "margin:0 0 10px;font-family:var(--font-ui)": "ls-mb10-ui",
    "font-family:var(--font-ui);font-size:.9375rem;color:var(--text-2)": "ls-note",
    "max-width:640px;margin:0 0 28px": "ls-panel",
    "margin:0 0 14px": "ls-mb14",
    "margin-top:12px;font-family:var(--font-ui);font-size:.875rem;color:var(--text-2)": "ls-prov-note",
    "margin:12px 0 0": "ls-mt12",
    "padding-top:0;margin:0 0 28px": "ls-also-top",
    "color:var(--text-2);margin:0": "ls-text2 ls-m0",
    "margin:0 0 8px": "ls-mb8",
    "margin:0 0 6px": "ls-mb6",
    "margin:0": "ls-m0",
    "margin:0 0 8px;padding:0;border:0;font-size:1.25rem": "ls-boxhead",
    "margin-top:24px": "ls-mt24",
}

# The text fixes the passthrough build already made (build.py PASSTHROUGH_FIXES and the
# PASSTHROUGH_CHROME "Start a trial" label, D3/D9). Exact text, each must occur exactly once.
LIFT_FIXES = {
    "/independence/": [
        ("The site header and footer link to Pricing and Start a trial on every page,",
         "The site header and footer link to Pricing and Start a Pilot on every page,"),
    ],
    "/code/": [
        ("Standard-library Python, no network calls; nothing leaves the machine it runs on.",
         "Standard-library Python with no network calls: the script itself sends nothing anywhere."),
    ],
    "/404.html": [
        ('<a href="/start/">Start a trial</a>', '<a href="/start/">Start a Pilot</a>'),
    ],
}

# Head text that breaks the v2 SEO rules (title ≤ 60, description 50–155 characters). Head
# only: the body is untouched. The old value is recorded in the page's json.
TITLE_FIX = {
    "/independence/": "Independence: who pays, and what the money does not buy",
    "/research/portfolio-driven-disposition-effect/": "Portfolio-driven disposition effect: headline corrected",
    "/research/swing-trading-strategies/": "26 swing-trading strategies, pre-registered: none survived",
}
DESC_FIX = {
    "/who-pays/": "This page has moved to the donttrade Independence policy: who pays, and what the money does not buy.",
    "/404.html": "Page not found on donttrade. Try Research, Pricing or Start a Pilot, or email us.",
}
LEGACY_JS = {"/tools/disposition-calculator/": "disposition-calculator.js",
             "/tools/pass-rate-calculator/": "pass-rate-calculator.js"}
# Code fixes (not text): the calculators' logic was frozen by steps 28–29; on 21 Oct 2026 the
# owner's pipeline fixed two recorded v1 defects in it (Manager §1.1): "1,5" read as 15 (now the
# engine's decimal rule, static/js/legacy/numbers.js) and every box marked invalid on first load.
# The page text is unchanged (compare.py). For these pages the lift writes the v1 inline script
# to LEGACY_V1_DIR, so the v1 code stays on record and --check still proves it is docs/'s, and
# the page loads numbers.js before its own script.
CODE_FIXED = {"/tools/disposition-calculator/": "2026-10-21", "/tools/pass-rate-calculator/": "2026-10-21"}
LEGACY_DEPS = ["/static/js/legacy/numbers.js"]
LEGACY_V1_DIR = os.path.join(HERE, "lifted-baseline", "legacy-v1")


class LiftError(Exception):
    pass


def slug(path):
    return "404" if path == "/404.html" else (path.strip("/").replace("/", "_") or "home")


def _attr(tag, name):
    m = re.search(r'\s' + name + r'="([^"]*)"', tag)
    return _h.unescape(m.group(1)) if m else None


def head_facts(html, path):
    head = html[:html.index("</head>")]
    def meta(attr, key):
        m = re.search(r'<meta ' + attr + r'="' + re.escape(key) + r'" content="([^"]*)"', head)
        return _h.unescape(m.group(1)) if m else None
    title = _h.unescape(re.search(r"<title>(.*?)</title>", head).group(1))
    desc = meta("name", "description")
    og = meta("property", "og:image")
    citation = [[_h.unescape(n), _h.unescape(c)] for n, c in
                re.findall(r'<meta name="(citation_[a-z_]+)" content="([^"]*)"', head)]
    ld = [json.loads(b) for b in re.findall(r'(?s)<script type="application/ld\+json">(.*?)</script>', head)]
    refresh = re.search(r'<meta http-equiv="refresh" content="0; url=([^"]+)">', head)
    canon = re.search(r'<link rel="canonical" href="([^"]+)">', head)
    return {"title": title, "description": desc, "og_image": og, "citation": citation, "ld": ld,
            "refresh": refresh.group(1) if refresh else None, "canonical": canon.group(1) if canon else None,
            "noindex": '<meta name="robots" content="noindex">' in head}


def sitemap_dates():
    with open(os.path.join(DOCS, "sitemap.xml"), encoding="utf-8") as f:
        return dict(re.findall(r"<loc>https://donttrade\.ca(/[^<]*)</loc><lastmod>([^<]+)</lastmod>", f.read()))


def old_main(html, rel):
    if '<header class="site">' not in html:
        raise LiftError(f"docs/{rel} has no old header: docs/ is no longer the pre-v2 site (after the bundle, "
                        "the lifted fragments are the source; this script is retired)")
    m = re.search(r'(?s)<main id="main">(.*)</main>', html)
    if not m:
        raise LiftError(f"docs/{rel}: no <main id=\"main\">")
    return m.group(1)


def apply_fixes(main, path):
    for old, new in LIFT_FIXES.get(path, []):
        if main.count(old) != 1:
            raise LiftError(f"{path}: fix text not found exactly once: {old!r}")
        main = main.replace(old, new)
    return main


def transform(main, path):
    """The CSP-forced markup changes. Returns (fragment, moved script or None)."""
    styles = re.findall(r"(?s)<style>.*?</style>", main)
    if styles and path not in LEGACY_JS:
        raise LiftError(f"{path}: a <style> element in <main> on a page that is not a calculator")
    main = re.sub(r"(?s)<style>.*?</style>", "", main)
    scripts = re.findall(r"(?s)<script>(.*?)</script>", main)
    if len(scripts) > 1 or re.search(r"<script\b(?!>)", main):
        raise LiftError(f"{path}: unexpected script elements in <main>")
    if scripts and path not in LEGACY_JS:
        raise LiftError(f"{path}: an inline script on a page with no legacy file name")
    main = re.sub(r"(?s)<script>.*?</script>", "", main)
    n = main.count(' onsubmit="return false"')
    main = main.replace(' onsubmit="return false"', "")
    if re.search(r"\son[a-z]+=", main):
        raise LiftError(f"{path}: an inline event handler other than onsubmit=\"return false\"")
    if n and path not in LEGACY_JS:
        raise LiftError(f"{path}: onsubmit on a page that is not a calculator")

    def restyle(m):
        tag = m.group(0)
        style = _attr(tag, "style")
        if style not in STYLE_CLASS:
            raise LiftError(f"{path}: no class for the inline style {style!r} (add it to STYLE_CLASS and site.css)")
        add = STYLE_CLASS[style]
        tag = re.sub(r'\sstyle="[^"]*"', "", tag, count=1)
        if re.search(r'\sclass="', tag):
            return re.sub(r'\sclass="([^"]*)"', lambda c: f' class="{c.group(1)} {add}"', tag, count=1)
        return re.sub(r"^<([a-zA-Z0-9]+)", lambda t: f'<{t.group(1)} class="{add}"', tag, count=1)
    main = re.sub(r'<[a-zA-Z][^>]*\sstyle="[^"]*"[^>]*>', restyle, main)
    return main, (scripts[0] if scripts else None)


def page_json(path, rel, crumb, parent, section, facts, dates, fragment):
    title = TITLE_FIX.get(path, facts["title"])
    desc = DESC_FIX.get(path, facts["description"])
    out = {"path": path, "source": "docs/" + rel, "crumb": crumb, "parent": parent, "section": section,
           "title": title, "description": desc,
           "og_image": facts["og_image"].replace("https://donttrade.ca", ""),
           "citation": facts["citation"]}
    if title != facts["title"]:
        out["title_was"] = facts["title"]
    if desc != facts["description"]:
        out["description_was"] = facts["description"]
    if facts["noindex"]:
        out["noindex"] = True
    else:
        out["updated"] = dates[path]
    if facts["refresh"]:
        out["redirect_to"] = facts["refresh"]
        if facts["canonical"] != "https://donttrade.ca" + facts["refresh"]:
            raise LiftError(f"{path}: the redirect stub's canonical is not its target")
    elif facts["canonical"] not in (None, "https://donttrade.ca" + path):
        raise LiftError(f"{path}: canonical {facts['canonical']} is not the page itself")
    if len(facts["ld"]) > 1:
        raise LiftError(f"{path}: more than one JSON-LD block")
    if facts["ld"]:
        art = dict(facts["ld"][0])
        if art.pop("@context") != "https://schema.org" or art["@type"] != "Article":
            raise LiftError(f"{path}: JSON-LD is not one schema.org Article")
        art.pop("author"), art.pop("publisher")  # → the site Organization node (build.jsonld)
        out["article"] = art
    if path in LEGACY_JS:
        out["scripts"] = (LEGACY_DEPS if path in CODE_FIXED else []) + ["/static/js/legacy/" + LEGACY_JS[path]]
    if 'action="https://donttrade.substack.com/subscribe"' in fragment:
        out["form_action"] = ["https://donttrade.substack.com"]
    return out


def lift(write=True):
    import compare
    dates = sitemap_dates()
    outputs = {}
    for path, rel, crumb, parent, section in PAGES:
        with open(os.path.join(DOCS, rel), encoding="utf-8") as f:
            html = f.read()
        main = old_main(html, rel)
        fixed = apply_fixes(main, path)
        fragment, script = transform(fixed, path)
        facts = head_facts(html, path)
        s = slug(path)
        meta = page_json(path, rel, crumb, list(parent) if parent else None, section, facts, dates, fragment)
        meta["source_sha256"] = hashlib.sha256(html.encode("utf-8")).hexdigest()
        base = compare.facts(fixed, citation=facts["citation"])
        base.update({"path": path, "source": "docs/" + rel, "source_sha256": meta["source_sha256"],
                     "fixes": [list(f) for f in LIFT_FIXES.get(path, [])]})
        outputs[os.path.join(FRAG_DIR, s + ".html")] = fragment
        outputs[os.path.join(FRAG_DIR, s + ".json")] = json.dumps(meta, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        outputs[os.path.join(BASE_DIR, s + ".json")] = json.dumps(base, ensure_ascii=False, indent=1, sort_keys=True) + "\n"
        if script is not None:
            where = LEGACY_V1_DIR if path in CODE_FIXED else JS_DIR
            outputs[os.path.join(where, LEGACY_JS[path])] = script.lstrip("\n")
    for p in LIFT_FIXES:
        if p not in {x[0] for x in PAGES}:
            raise LiftError(f"LIFT_FIXES names {p}, which is not a lifted page")
    diffs = []
    for fp, text in sorted(outputs.items()):
        cur = open(fp, encoding="utf-8").read() if os.path.exists(fp) else None
        if cur != text:
            diffs.append(os.path.relpath(fp, REPO))
            if write:
                os.makedirs(os.path.dirname(fp), exist_ok=True)
                with open(fp, "w", encoding="utf-8", newline="\n") as f:
                    f.write(text)
    return diffs


def main(argv):
    check = "--check" in argv
    try:
        diffs = lift(write=not check)
    except LiftError as e:
        print(f"LIFT FAILED: {e}", file=sys.stderr)
        return 1
    if check:
        for d in diffs:
            print(f"differs from docs/: {d}")
        print("lift check:", "PASS" if not diffs else f"{len(diffs)} file(s) differ")
        return 1 if diffs else 0
    print(f"lifted {len(PAGES)} pages; {len(diffs)} file(s) written")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
