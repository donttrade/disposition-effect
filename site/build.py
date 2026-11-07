#!/usr/bin/env python3
"""donttrade v2 site build: site.toml + prices.json + Jinja2 templates → site/_site/.

Rules (V2-BUILD-PLAN, STRUCTURE and step 3):
  * Every page of today's docs/ that no template owns is copied through unchanged, so the
    output always holds every baseline URL. Since steps 28–29 every docs/ HTML page is owned
    (the 20 old pages are lifted templates, LIFTED); non-HTML files (PDFs, CSVs, charts, OG
    images, feed.xml) still pass through, and any new docs/ HTML page would pass through under
    the loud chrome guard (fix_passthrough_chrome).
  * The build FAILS LOUDLY (exit 1, with the reason) on:
      - a path in checks/urls-baseline.txt missing from the output,
      - an externally linked id (path#id in the baseline) missing from its page,
      - trader_first_home != paid_report, or analytics on without a beacon token,
      - a paid-only page or paid-flagged markup in the output while paid_report is off,
      - a page without exactly one footer business line while a commerce flag is on (the full one,
        with the address, only on ADDRESS_LINE_PATHS; the short one elsewhere), or with one while
        both are off (business_id_line(); decisions 21 and 25 Oct),
      - a private.toml value without the shape of a real one while a commerce flag is on
        (seller_problem(); DT_ALLOW_PLACEHOLDERS=1 skips only this check, for local test builds),
      - a malformed site.toml or private.toml (a BUILD FAILED line, not a traceback).
  * Output is deterministic: sorted walks, no timestamps, so two builds are byte-identical.

Environment:
  DT_DEV=1                 also build site/dev/ (styleguide, sniffer) into _site/dev/
  DT_SITE_TOML=path        use another site.toml (test builds with flags on)
  DT_OUT=path              write somewhere other than site/_site
  DT_BASELINE=path         use another URL baseline (tests plant a missing URL this way)
  DT_PRIVATE_TOML=path     read private.toml from elsewhere (flag-on test builds)
  DT_PRICES_JSON=path      read prices.json from elsewhere (test builds plant a test link)
  DT_REPORT_METHODS_JSON=path  read report_methods.json from elsewhere (tests plant a missing entry)
  DT_REQUIRE_LAUNCH_DATE=1 fail if [legal] launch_date or terms_date is empty (./site/run.sh bundle sets it)
  DT_PREVIEW=<name>        a preview build (delivery plan C-17; name = the Pages branch, e.g. paid-preview,
                           live-check): every page gets <meta name="robots" content="noindex,nofollow"> and a
                           "Preview, not the live site" band, and robots.txt disallows everything
Local-test escapes (ESCAPES): each opens ONE guard, prints a WARNING, and is refused when
[stripe] mode = "live". A paid build with well-formed values needs none of them.
  DT_ALLOW_PLACEHOLDERS=1    allow private.toml values that look like placeholders
  DT_ALLOW_LOCAL_API=1       allow a loopback http [worker] api_base
  DT_ALLOW_NO_STRIPE_LINK=1  allow a paid build without the report39 Payment Link
"""

import hashlib
import json
import math
import os
import re
import unicodedata
import shutil
import sys
import tomllib

from html.parser import HTMLParser as _HTMLParser

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

import learn_tables as LT   # 6 Nov (SEO round 1): the computed tables on /learn/ (site/learn_tables.py)

SITE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SITE)
sys.path.insert(0, SITE)
import tool_real  # noqa: E402  (6 Nov, tools redesign B2: the real-data displays' geometry)
import selloff as SO  # noqa: E402  (6 Nov, the sell-off study: its figures, charts and CSV)
DOCS = os.path.join(REPO, "docs")
BASELINE = os.environ.get("DT_BASELINE") or os.path.join(REPO, "checks", "urls-baseline.txt")

PAID_FLAG_MARKER = 'data-requires-flag="paid_report"'
# Flags that put a sale on the site. Either one makes the build read private.toml, and
# the seller disclosure block render; with both off, private.toml is never opened.
COMMERCE_FLAGS = ("paid_report", "pilot_checkout")
PRIVATE_FIELDS = ("seller_legal_name", "premises_address", "phone")
LD_MARKER = "<!--jsonld-->"
# B2: what counts as "still a placeholder" in private.toml. Case-insensitive; any bracket or
# dash style. A value matching any of these fails a commerce build loudly.
PLACEHOLDER_WORDS = re.compile(
    r"(?<![a-z0-9])(tbd|tbc|todo|fixme|xx+|lorem|ipsum|example|placeholder|dummy|fake|changeme|"
    r"n/a|none|null|pending|to confirm|lawyer to confirm|fill in|fill me in|your (legal )?name|"
    r"your address|your phone)(?![a-z0-9])", re.IGNORECASE)
PLACEHOLDER_BRACKETS = re.compile(r"[\[\]{}<>]")                     # [SELLER — …], {name}, <address>
PLACEHOLDER_LABEL = re.compile(r"^\W*(seller|name|address|phone)\b\s*[-–—:]", re.IGNORECASE)  # "SELLER - …"
INVISIBLE = re.compile(r"[\s\u200b-\u200d\u2060\ufeff]+")


def placeholder_reason(value):
    """Why a private.toml value is not a real value, or None. Strings only; callers check type."""
    bare = INVISIBLE.sub("", value)
    if not bare:
        return "it is empty"
    if not re.search(r"[A-Za-z0-9]", bare):
        return "it has no letter or digit"
    if PLACEHOLDER_BRACKETS.search(value):
        return "it contains a bracket ([ ] { } < >), the placeholder style"
    m = PLACEHOLDER_WORDS.search(value)
    if m:
        return f"it contains the placeholder word {m.group(0)!r}"
    if PLACEHOLDER_LABEL.search(value):
        return "it starts with a field label and a dash, the placeholder style"
    return None


# R4: the seller fields must have a positive shape, not merely avoid a blocklist. Each value is
# NFKC-normalised first (full-width letters, NBSP, ligatures become plain text), and a value
# holding an invisible or control character (Unicode Cf/Cc: zero-width, soft hyphen, bidi
# marks, newlines) is refused outright, so a placeholder cannot hide behind one.
PLACEHOLDER_TOKENS = frozenset("""
    seller vendor name legal business company owner here later not yet unknown none null nil
    test testing tbd tbc todo fixme example sample placeholder lorem ipsum dummy fake changeme demo
    pending confirm lawyer your my asdf qwerty foo address phone province postal po box tel fax
""".split())
# Cyrillic and Greek letters that look like Latin ones, for the token check only (ТВD, ХХХ)
CONFUSABLES = str.maketrans("АВЕКМНОРСТХаеорсухіјѕԁԛԝΑΒΕΖΗΙΚΜΝΟΡΤΥΧαοντ",
                            "ABEKMHOPCTXaeopcyxijsdqwABEZHIKMNOPTYXaovt")
PROVINCES = {"AB": "T", "BC": "V", "MB": "R", "NB": "E", "NL": "A", "NS": "B", "NT": "X", "NU": "X",
             "ON": "KLMNP", "PE": "C", "QC": "GHJ", "SK": "S", "YT": "Y"}  # code → postal first letters
POSTAL = re.compile(r"[ABCEGHJ-NPRSTVXY]\d[ABCEGHJ-NPRSTV-Z] \d[ABCEGHJ-NPRSTV-Z]\d")  # A1A 1A1, no D F I O Q U
NAME_WORD = re.compile(r"[^\W\d_]+(?:['’-][^\W\d_]+)*\.?")      # letters, inner - or ', optional "Inc."
ADDRESS = re.compile(r"(?P<street>.+?),\s*(?P<city>[^,\d]+?),?\s+(?P<prov>[A-Z]{2})\s+(?P<postal>\S{3} \S{3})(?:,?\s+Canada)?")
PHONE_CHARS = re.compile(r"(?P<main>\+?[0-9()./ -]+?)(?:\s*(?:ext\.?|x)\s*(?P<ext>\d{1,6}))?", re.IGNORECASE)


def normalise_private(value):
    """(NFKC text with runs of spaces collapsed, None) or (None, why)."""
    for ch in value:
        if unicodedata.category(ch) in ("Cf", "Cc", "Zl", "Zp"):
            return None, f"it holds an invisible or control character (U+{ord(ch):04X})"
    return " ".join(unicodedata.normalize("NFKC", value).split()), None


def _scripts(word):
    return {unicodedata.name(ch, "?").split(" ")[0] for ch in word if ch.isalpha()}


def _token_problem(words):
    for w in words:
        if len(_scripts(w)) > 1:
            return f"the word {w!r} mixes alphabets (a look-alike letter)"
        bare = w.rstrip(".").translate(CONFUSABLES).lower()
        if bare in PLACEHOLDER_TOKENS or re.fullmatch(r"x+", bare):
            return f"{w!r} is a placeholder word, not part of a real value"
        if len(bare) >= 2 and len(set(bare)) == 1:
            return f"{w!r} is one letter repeated"
    return None


def name_problem(v):
    words = v.split(" ")
    for w in words:
        if not NAME_WORD.fullmatch(w):
            return f"{w!r} is not a word of letters (a legal name is letters, with - or ' inside a word)"
    if sum(len(w.rstrip(".")) >= 2 for w in words) < 2:
        return "a legal name needs at least two words of two or more letters"
    return _token_problem(words)


# Decision 21 Oct: a Canada Post box ("PO Box 1234 STN Main", "PO Box 1234, STN Main", FR "CP 1234
# Succ. Centre-ville") or a mailbox-store street address ("123 Street Rd #456") is the business
# mailing address. Tester delta D6: a street address needs its CIVIC number, at the start of a
# part of the street (a unit alone, "Street Rd #456", is not an address); a unit may come before it
# as its own part ("Suite 4, 12 Road") or joined to it ("456-123 Road", "#456-123 Road").
BOX_WORD = r"(?:P\.?\s?O\.?\s?Box|Box|C\.?\s?P\.?|Case\s+postale)"
BOX_START = re.compile(BOX_WORD + r"(?=[\s#\d]|$)\s*#?\s*(?P<n>[^\s,]*)", re.IGNORECASE)
BOX_ANYWHERE = re.compile(r"(?<![\w.])(?:P\.?\s?O\.?\s?Box|C\.?\s?P\.|Case\s+postale)(?![\w])", re.IGNORECASE)
CIVIC_START = re.compile(r"#?(?:\d{1,6}[A-Za-z]?-)?(?P<n>\d{1,6})[A-Za-z]?(?:\s+1/2)?\s+(?=\S*[^\W\d_]|$)")


def street_problem(street):
    parts = [p.strip() for p in street.split(",") if p.strip()]
    if len(BOX_ANYWHERE.findall(street)) > 1:
        return "the address names more than one PO Box"
    for p in parts:
        b = BOX_START.match(p)
        if b:
            n = b.group("n")
            if not re.fullmatch(r"\d{1,6}", n) or int(n) == 0:
                return "the PO Box needs its number (1 to 6 digits, not 0), right after 'PO Box'"
            return None
    for i, p in enumerate(parts):
        c = CIVIC_START.match(p + " ")
        if c and int(c.group("n")) > 0 and (c.end() < len(p) + 1 or (i + 1 < len(parts) and re.match(r"[^\W\d_]", parts[i + 1]))):
            return None   # "123 Street Rd", or FR "123, rue Principale"
    return ("the street address needs its civic (street) number at the start, e.g. '123 Street Rd #456': "
            "a unit, suite or mailbox number alone is not enough")


def address_problem(v):
    if not re.fullmatch(r"#?[^\W_]+(?:[ ,.'’#/-]+[^\W_]*)*\.?", v):   # may start "#456-123 …" (N5)
        return "an address may hold only letters, digits, spaces and , . - ' # /"
    m = ADDRESS.fullmatch(v)
    if not m:
        return "write it as: street number and street (or PO Box N), city, province code, postal code — e.g. 'PO Box 12, Town ON K1A 0B1'"
    street, city, prov, postal = m.group("street", "city", "prov", "postal")
    why = street_problem(street)
    if why:
        return why
    city_words = city.split(" ")
    if not all(NAME_WORD.fullmatch(w) for w in city_words) or not any(len(w.rstrip(".")) >= 2 for w in city_words):
        return f"{city!r} is not a city name"
    if prov not in PROVINCES:
        return f"{prov!r} is not a Canadian province or territory code (ON, QC, BC, …)"
    if not POSTAL.fullmatch(postal):
        return f"{postal!r} is not a well-formed postal code (A1A 1A1, capitals, one space)"
    if postal[0] not in PROVINCES[prov]:
        return f"postal code {postal} does not belong to {prov}"
    return _token_problem([w for w in re.split(r"[\s,]+", street + " " + city) if w and not w[0].isdigit()
                           and w.lower().strip(".") not in ("po", "p.o", "box")])


def phone_problem(v):
    m = PHONE_CHARS.fullmatch(v)
    if not m:
        return "a phone number may hold only digits, spaces and + ( ) - . /, and an extension (ext 12)"
    main = m.group("main")
    if "+" in main and not main.startswith("+1"):
        return "only a North American number (+1) is accepted"
    d = re.sub(r"\D", "", main)
    if len(d) == 11 and d[0] == "1":
        d = d[1:]
    if len(d) != 10:
        return "a North American phone number has 10 digits (area code and number)"
    npa, nxx, line = d[:3], d[3:6], d[6:]
    if len(set(d)) == 1:
        return "every digit is the same"
    if npa[0] in "01" or npa[1] == "9" or npa[1:] == "11":
        return f"{npa} is not a valid area code"
    if nxx[0] in "01" or nxx[1:] == "11":
        return f"{nxx} is not a valid exchange"
    if nxx == "555" and line.startswith("01"):
        return "555-01xx numbers are reserved for fiction"
    return None


FIELD_SHAPE = {"seller_legal_name": name_problem, "premises_address": address_problem, "phone": phone_problem}


def seller_problem(field, value):
    """Why `value` is not a real `field` value, or None. Strings only; callers check type."""
    norm, why = normalise_private(value)
    if why:
        return why
    return placeholder_reason(norm) or FIELD_SHAPE[field](norm)


def check_private(private, on):
    """Seller fields (O. Reg. 17/05 s. 32) must be real values under either commerce flag
    (seller_problem). Returns the fields as published: NFKC text, spaces collapsed. The check
    alone can be skipped with DT_ALLOW_PLACEHOLDERS=1 (local test builds only)."""
    out = dict(private)
    for k in PRIVATE_FIELDS:
        v = private.get(k)
        if not isinstance(v, str) or not INVISIBLE.sub("", v):
            die(f"{', '.join(on)} = true but private.toml is missing {k} (or it is empty)")
        why = seller_problem(k, v)
        if why and not escape("DT_ALLOW_PLACEHOLDERS"):
            die(f"private.toml {k} is not a real value yet: {why}. Fill it in "
                "(or set DT_ALLOW_PLACEHOLDERS=1 for a local test build only)")
        if not why:
            out[k] = normalise_private(v)[0]
    return out

# Motion plan (21 Oct 2026): motion.js (fade-up, hero wipe, count-up) loads on these 4 marketing pages
# only; verify() refuses it anywhere else, and refuses motion markup on a page without it.
MOTION_JS = "/static/js/motion.js"
MOTION_PAGES = {"/", "/for-firms/", "/for-traders/", "/for-platforms/"}
# ARCHITECT-V3 B6, C8: the cross-document view transition (vt.css) on the motion pages and /start/ only;
# verify() refuses vt.css on any other page and @view-transition in any other stylesheet.
VT_CSS = "/static/css/vt.css"
VT_PAGES = MOTION_PAGES | {"/start/"}
START_JS = "/static/js/start-chooser.js"

# ------------------------------------------------------------------ answer box index (ARCHITECT-V3 §c.5, Q-A1)
# Built from the RENDERED pages, so a unit's answer is the page's own text, word for word: every FAQ
# <details>, the /pricing/, /terms/ and /privacy/ sections with ids, the tool pages' FAQs, the glossary
# and the /start/ "What happens next" steps. Never /research/* (no study figure may sit next to an offer,
# and an answer can hold a price), thank-you and other noindex pages, flag-off pages or French pages.
# Shipped as a script (window.DT_ANSWERS = …), not fetched JSON: every page keeps connect-src 'none'.
ANSWERS_JS = "/static/js/answers-index.js"
# [flags] ask_box = false (launch, 25 Oct): no page loads these; /help/ still lists every unit.
ASK_SCRIPTS = ("/static/js/ask.js", "/static/js/answers.js", "/static/js/answer-ui.js")
ANSWERS_MAX = 150 * 1024
ANSWER_MAX_CHARS = 700
ANSWER_SKIP = ("/research/", "/fr/", "/help/")
ANSWER_SECTIONS = {"/pricing/": "price", "/terms/": "terms", "/privacy/": "privacy"}
# 6 Nov (Round A7): "last-step-h" is the pay panel's chip list; as an answer it would repeat the short refund claim without
# its limits (the chip is a link in the page, plain text in a blockquote), so it is not an answer unit.
ANSWER_SECTION_SKIP = {"faq-h", "ladder-h", "history", "last-step-h"}
INLINE_TAGS = frozenset("a abbr b bdi bdo cite code data del dfn em font i ins kbd mark nobr q s samp small span "
                        "strong sub sup time tt u var wbr".split())   # = checks/lint.py INLINE


def plain(fragment):
    """Readable text of an HTML fragment: inline elements join, every other element is a break
    (the same rule as checks/lint.py visible_text), whitespace collapsed."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.out, self.skip = [], 0

        def handle_starttag(self, tag, attrs):
            if tag in ("script", "style"):
                self.skip += 1
            elif tag not in INLINE_TAGS:
                self.out.append(" ")

        def handle_endtag(self, tag):
            if tag in ("script", "style"):
                self.skip -= 1
            elif tag not in INLINE_TAGS:
                self.out.append(" ")

        def handle_data(self, data):
            if not self.skip:
                self.out.append(data)
    p = P()
    p.feed(fragment)
    p.close()
    return " ".join("".join(p.out).split())


def slug(text, n=60):
    t = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "-", t).strip("-")[:n].strip("-") or "x"


FAQ_SECTION_RE = re.compile(r'(?s)(<section[^>]*aria-labelledby="faq-h"[^>]*>)(.*?)(</section>)')


def add_faq_ids(html):
    """Each FAQ <details> gets a stable id (q-<slug of its question>), so an answer can link to it."""
    m = FAQ_SECTION_RE.search(html)
    if not m:
        return html
    seen = set(re.findall(r'\sid="([^"]+)"', html))

    def one(d):
        base = "q-" + slug(plain(d.group(1)))
        i, new = 2, base
        while new in seen:
            new, i = f"{base}-{i}", i + 1
        seen.add(new)
        return f'<details id="{new}"><summary>{d.group(1)}</summary>'
    body = re.sub(r"<details><summary>(.*?)</summary>", one, m.group(2))
    return html[:m.start(2)] + body + html[m.end(2):]


def cut_answer(text):
    """≤ ANSWER_MAX_CHARS, cut after a sentence end, then " …" (the source link carries the rest)."""
    if len(text) <= ANSWER_MAX_CHARS:
        return text
    head = text[:ANSWER_MAX_CHARS]
    k = max(head.rfind(". "), head.rfind("? "), head.rfind(": "))
    return (head[:k + 1] if k > 200 else head.rsplit(" ", 1)[0]) + " …"


def answer_units(rendered, private=None):
    """[(page, html)] → the index units {id, q, a, url, section, kind, updated}. Dies on a unit whose
    anchor is not on its page, or whose text holds a finding number from evidence().
    QA3 25 Oct: a unit quoting the seller's name, address or phone, or the "called Trial" rename note,
    is left out, so /help/ and the answer index never repeat them (they stay on their own pages)."""
    units, ids = [], set()
    keep_out = [v for v in ((private or {}).get(k) for k in PRIVATE_FIELDS) if isinstance(v, str) and v.strip()]
    keep_out.append("called \u201cTrial\u201d")
    ev = evidence()
    bad_numbers = [ev["finding"]["pct"], re.search(r"[\d,]{4,}", ev["finding"]["rest"]).group(0)]

    def add(page, kind, q, a, anchor, where):
        if any(v in a or v in q for v in keep_out):
            return
        a = cut_answer(a)
        if not q or not a:
            return
        uid = slug(f"{kind}-{page['path'].strip('/') or 'home'}-{q}", 90)
        while uid in ids:
            uid += "-2"
        ids.add(uid)
        units.append({"id": uid, "q": q, "a": a, "url": page["path"] + "#" + anchor,
                      "section": where, "kind": kind, "updated": page.get("updated", "")})

    for page, html in rendered:
        path = page["path"]
        if (page.get("noindex") or page.get("redirect_to") or path.startswith(ANSWER_SKIP)
                or page.get("lang", "en") != "en" or path.endswith(".html")):
            continue
        main = re.search(r"(?s)<main[^>]*>(.*)</main>", html).group(1)
        crumb = "Home" if path == "/" else page.get("crumb") or page["title"]
        m = FAQ_SECTION_RE.search(main)
        if m:
            kind = "tool" if path.startswith("/tools/") else "faq"
            for did, q, a in re.findall(r'(?s)<details id="([^"]+)">\s*<summary>(.*?)</summary>(.*?)</details>', m.group(2)):
                add(page, kind, plain(q), plain(a), did, f"{crumb}, Questions")
        if path in ANSWER_SECTIONS:
            heads = list(re.finditer(r'(?s)<h([23])\b[^>]*\sid="([^"]+)"[^>]*>(.*?)</h\1>', main))
            for k, h in enumerate(heads):
                if h.group(2) in ANSWER_SECTION_SKIP or (m and m.start(2) <= h.start() < m.end(2)):
                    continue
                end = heads[k + 1].start() if k + 1 < len(heads) else len(main)
                body = main[h.end():end]
                body = FAQ_SECTION_RE.sub("", body)
                body = re.sub(r'(?s)<span class="ls-sum">.*?</span>', "", body)   # sweep 3: the fold's one-line summary is not the answer
                q = plain(h.group(3))
                add(page, ANSWER_SECTIONS[path], q, plain(body), h.group(2), f"{crumb}, {q}")
        if path == "/glossary/":
            for did, q, a in re.findall(r'(?s)<dt id="([^"]+)">(.*?)</dt>\s*<dd>(.*?)</dd>', main):
                add(page, "glossary", plain(q), plain(a), did, f"Glossary, {plain(q)}")
        if path == "/start/":
            s = re.search(r'(?s)<section class="choice" id="([a-z]+)".*?<h3>(What happens next)</h3>\s*(<ol.*?</ol>)', main)
            if s:
                add(page, "faq", s.group(2), plain(s.group(3)), s.group(1), "Start here, What happens next")
    for u in units:
        path, anchor = u["url"].split("#", 1)
        html = dict((p["path"], h) for p, h in rendered)[path]
        if not re.search(r'\sid="' + re.escape(anchor) + '"', html):
            die(f"answer index: {u['url']} has no such anchor on its page")
        for n in bad_numbers:
            if n in u["a"] or n in u["q"]:
                die(f"answer index: unit {u['id']} holds the study figure {n!r} (no finding next to an offer)")
    return units


def answers_index_js(units, cfg):
    # 25 Oct sweep: the home page has no FAQ any more; the out-of-scope reply is the pricing page's
    advice = [u["id"] for u in units if u["url"] in ("/#q-is-this-advice", "/pricing/#q-is-this-investment-advice")]
    if not advice:
        die("answer index: the FAQ 'Is this investment advice?' on /pricing/ (the out-of-scope reply) is missing")
    data = {"version": 1, "built": cfg["legal"]["terms_version"], "advice": advice[0],
            "disclaimer": cfg["legal"]["disclaimer_short"], "synonyms": cfg.get("answers", {}).get("synonyms", {}),
            "units": units}
    js = ("// answers-index.js: built by site/build.py from the pages' own text (ARCHITECT-V3 §c.5). Data only.\n"
          "window.DT_ANSWERS = " + json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
          .replace("</", "<\\/") + ";\n")
    if len(js.encode("utf-8")) > ANSWERS_MAX:
        die(f"answer index is {len(js.encode('utf-8'))} bytes, over the {ANSWERS_MAX}-byte budget")
    return js


# Pages owned by templates. path → template, metadata, and the flag that must be on.
# Challenge Readiness Check counting (ARCHITECT-CHALLENGE-READINESS §7, Revision 2): with [flags] analytics on, the
# check page loads one of these tiny pages in a hidden same-origin frame when a step finishes, at most once per page
# load, so the live Cloudflare Web Analytics beacon counts the step as a page view of that path. The frame URL is the
# path only: no query, no fragment, nothing from the file. No other tracker. noindex, disallowed in robots.txt.
COUNT_BASE = "/tools/prop-challenge-simulator/e/"
COUNT_EVENTS = ("ran", "ran-sample", "whatif", "expert", "export", "card")
CHALLENGE_RULES_JSON = os.path.join(SITE, "config", "challenge_rules.json")
PAGES = [
    {"template": "pages/home.html", "path": "/", "requires_flag": None, "scripts": [MOTION_JS, "/static/js/band-expiry.js"],
     "title": "donttrade - free trading tools and research on trader habits",
     "description": "Free in-browser tools: trade stats, prop challenge odds, drawdown and risk-reward. "
                    "Research on how traders behave. For firms: fixed-price measurement.",
     "og_image": "/assets/og/home.png",
     "updated": "2026-11-06"},
]

# Free tools (steps 10-12). connect-src stays 'none' (the csp_for default): these pages
# cannot send anything, which is what makes "your file is not uploaded" true.
# 6 Nov (tools redesign B2, ARCHITECT-PLAN-TOOLS-REDESIGN-2026-11-06): every tool page and /tools/ load tools.css (the
# glyphs, the dark display, the /tools/ rack) and tools-index.js (play-once motion, the /tools/ scope); "glyph" names
# the page's mark (partials/tool_glyphs.html). TOOL_PAGE_EXTRA is added to each tool page's dict below.
TOOLS_CSS = "/static/css/tools.css"
TOOLS_JS = "/static/js/tools-index.js"
TOOL_GLYPHS = {"/tools/trade-stats/": "stats", "/tools/prop-challenge-simulator/": "prop",
               "/tools/lot-size-calculator/": "lot", "/tools/risk-reward-calculator/": "rr",
               "/tools/drawdown-calculator/": "dd", "/tools/trading-heatmap/": "heat",
               "/tools/disposition-calculator/": "disp", "/tools/pass-rate-calculator/": "pass",
               "/tools/bad-day-check/": "badday"}
PAGES += [
    {"template": "pages/tool-trade-stats.html", "path": "/tools/trade-stats/", "requires_flag": None,
     "modules": ["/static/js/tools/trade-stats.js"], "sample": True, "app": True, "updated": "2026-11-06",
     "crumb": "Trade stats from your own trade file",
     "title": "Trade Stats for Your File: Win Rate, Profit Factor, Drawdown",
     "description": "Win rate, profit factor, expectancy, drawdown and streaks from your own trade file. It runs in your browser and your file is not uploaded. Free.",
     "if_badges": {"description": "Win rate, profit factor, expectancy, drawdown and streaks from your own trade file, with a "
                                  "real-or-noise check. Runs in your browser and your file is not uploaded."}},
    {"template": "pages/tool-prop-sim.html", "path": "/tools/prop-challenge-simulator/", "requires_flag": None,
     "modules": ["/static/js/tools/prop-sim.js"], "sample": True, "app": True, "updated": "2026-11-06",
     "presets": True, "crumb": "Challenge Readiness Check",
     "title": "Prop Firm Challenge Simulator: Readiness Check on Your Days",   # 6 Nov (SEO round 1, owner-approved): the query phrase the page's search evidence supports, 59 characters; the H1 stays "Challenge Readiness Check"
     "description": "Replay your past trading days 10,000 times under a prop firm's published rules or your own: "
                    "pass, bust and time-out shares. Free, in your browser."},
    {"template": "pages/tool-lot-size.html", "path": "/tools/lot-size-calculator/", "requires_flag": None,
     "modules": ["/static/js/tools/lot-size.js"], "app": True, "updated": "2026-11-06",
     "crumb": "Lot size calculator",
     "title": "Lot Size Calculator: Forex, Gold, Indices and Futures",
     "description": "Work out position size in lots from your balance, risk amount and stop distance. Shows the "
                    "formula with your numbers and the loss after rounding."},
    # Batch 2 (V2-BUILD-PLAN free-tools list; SEO-PLAN T4, T5, T9). Descriptive only in every build:
    # no "real or noise" check runs on these pages, so they carry no if_badges copy.
    {"template": "pages/tool-risk-reward.html", "path": "/tools/risk-reward-calculator/", "requires_flag": None,
     "modules": ["/static/js/tools/risk-reward.js"], "app": True, "updated": "2026-11-06",
     "crumb": "Risk-reward calculator",
     "title": "Risk-Reward Calculator With Break-Even Win Rate",
     "description": "Enter entry, stop and target to get your R multiple, the win rate that breaks even, and the "
                    "expectancy per trade in R, with every formula shown. Free."},
    {"template": "pages/tool-drawdown.html", "path": "/tools/drawdown-calculator/", "requires_flag": None,
     "modules": ["/static/js/tools/drawdown.js"], "sample": True, "app": True, "updated": "2026-11-06",
     "crumb": "Drawdown and recovery calculator",
     "title": "Drawdown Recovery Calculator and Max Drawdown Report",
     "description": "How much gain recovers a drawdown, plus your own largest drawdown, longest drawdown and "
                    "recovery times from your trade file. Free, in your browser."},
    {"template": "pages/tool-heatmap.html", "path": "/tools/trading-heatmap/", "requires_flag": None,
     "modules": ["/static/js/tools/heatmap.js"], "sample": True, "app": True, "updated": "2026-11-06",
     "crumb": "Your trades by hour and weekday",
     "title": "Trading Heatmap of Your Trades by Hour and Weekday",
     "description": "See your own results, win rate and trade count by the hour and weekday each trade opened, "
                    "from your trade file, in the time zone you choose. Free."},
    {"template": "pages/tool-bad-day.html", "path": "/tools/bad-day-check/", "requires_flag": None,
     "modules": ["/static/js/tools/bad-day.js"], "sample": True, "app": True, "updated": "2026-11-06",
     "crumb": "Bad-day check", "check_days_default": "", "study_path": "/research/5-november-2026-sell-off/",
     "title": "Bad-Day Check: Your Trades on One Day Beside a Typical Day",
     "description": "Pick a day, such as 5 November 2026, and see your trades, net result, largest loss and quick "
                    "re-entries beside your typical day. Free, in your browser."},
    {"template": "pages/tools-index.html", "path": "/tools/", "requires_flag": None, "updated": "2026-11-06",
     "crumb": "Free tools", "itemlist": True, "styles": [TOOLS_CSS], "scripts": [TOOLS_JS], "og_image": "/assets/og/tools.png",
     "title": "Free Trading Tools That Run in Your Browser",
     "description": "Free tools for your own trades: trade stats from your file, a Challenge Readiness "
                    "Check for prop-firm rules, a lot size calculator and more. No sign-up.",
     "if_badges": {"description": "Free tools for your own trades: trade stats with a real-or-noise check, a "
                                  "Challenge Readiness Check, a lot size calculator and more. No sign-up."}},
]

# Audience pages (step 14). Titles ≤ 60 and descriptions ≤ 155 characters (SEO-PLAN §3.1).
# Search terms behind these titles are from autocomplete only; volumes are UNVERIFIED.
FORM_JS = "/static/js/form-ref.js"
# The Product JSON-LD description (paid_report only): the same words as the pricing table row.
# R-D3 I-3b: the same text as the /pricing/ row (the JSON-LD Product description; tests/test_r_d2_pages.py checks both)
PRODUCT_TEXT_FMT = "Up to {measured} habits measured in your own trades, with the dollar totals of the matching trades; up to {tested} of them tested against chance in this version; plus one re-test 30 to 60 days after your first result."


def product_text(rules):
    """6 Nov (Round A2): the two numbers come from prices.json rules.habits_measured / habits_tested, so the pricing
    row, the Product JSON-LD and the home page cannot disagree. When the engine tests three habits, change one number."""
    return PRODUCT_TEXT_FMT.format(measured=numword(rules["habits_measured"]), tested=numword(rules["habits_tested"]))


PRODUCT_TEXT = PRODUCT_TEXT_FMT.format(measured="five", tested="two")   # the committed default; a test holds product_text equal to it
PAGES += [
    {"template": "pages/for-traders.html", "path": "/for-traders/", "requires_flag": None, "updated": "2026-11-06",
     "crumb": "Individual traders", "og_image": "/assets/og/traders.png", "scripts": [FORM_JS, MOTION_JS],
     "title": "The donttrade Test for Traders: Waitlist",
     "description": "The donttrade test, a habit test on your own MT5, IBKR, Tradovate or TradingView file, with a "
                    "real-or-noise check for each tested habit. Coming soon; join the waitlist.",
     "if_paid": {"title": "The donttrade Test for Traders",
                 "description": "The donttrade test, a habit test on your own MT5, IBKR, Tradovate or TradingView file, "
                                "with a real-or-noise check. One price, re-test included."}},
    {"template": "pages/for-firms.html", "path": "/for-firms/", "requires_flag": None, "updated": "2026-11-05",
     "crumb": "Prop firms & brokers", "og_image": "/assets/og/default.png", "scripts": [FORM_JS, MOTION_JS],
     "title": "Free Study for Prop Firms and Brokers",
     "description": "Run our free, pre-registered study on your past accounts. Only totals leave your machine, and "
                    "you see the result first. No firm has run it yet."},
]

# Forms and the pages around them (step 16). Thank-you pages are noindex and stay out of the sitemap.
PAGES += [
    {"template": "pages/start.html", "path": "/start/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Start here", "og_image": "/assets/og/start.png", "scripts": [FORM_JS, START_JS],
     "title": "Start a Pilot, Apply to Partner or Join the Waitlist",
     "description": "Request a Pilot measurement, apply to partner as a journal or platform, or join the trader "
                    "waitlist. A short form or an email; no calls.",
     "if_paid": {"title": "Start a Pilot, Apply to Partner or Take the Test",
                 "description": "Request a Pilot measurement, apply to partner as a journal or platform, or get "
                                "the donttrade test. A short form or an email; no calls."}},
    {"template": "pages/for-platforms.html", "path": "/for-platforms/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Journals & platforms", "og_image": "/assets/og/platforms.png", "scripts": [FORM_JS, MOTION_JS],
     "title": "Behavioural Measurement for Trading Journals and Platforms",
     "description": "Show users how readily they close winning versus losing trades, with a public script run in "
                    "your own product. Free licence for the first three partners."},
    {"template": "pages/start-thanks.html", "path": "/start/thanks/", "requires_flag": None, "noindex": True,
     "crumb": "Thank you", "title": "Request received — donttrade",
     "description": "Your request reached donttrade. You get a reply within 1 business day, Eastern Time, Monday to Friday."},
    {"template": "pages/study-thanks.html", "path": "/for-firms/study-thanks/", "requires_flag": None, "noindex": True,
     "crumb": "Thank you", "title": "Study request received — donttrade",
     "description": "Your study request reached donttrade. We reply from research@donttrade.ca."},
    {"template": "pages/trader-thanks.html", "path": "/for-traders/thanks/", "requires_flag": None, "noindex": True,
     "crumb": "Thank you", "title": "You are on the waitlist — donttrade",
     "description": "You joined the donttrade trader waitlist. Nothing is charged; one email when the report launches.",
     "if_paid": {"title": "Thank you — donttrade",
                 "description": "Thank you. The donttrade test for traders is on sale now."}},
    {"template": "pages/thanks.html", "path": "/thanks/", "requires_flag": None, "noindex": True,
     "crumb": "Thank you", "title": "Thank you — donttrade",
     "description": "Your message reached donttrade. Firms get a reply within 1 business day; traders get one email at launch.",
     "if_paid": {"description": "Your message reached donttrade. Firms get a reply within 1 business day."}},
]
PAGES += [
    {"template": "pages/count-stub.html", "path": COUNT_BASE + name + "/", "requires_flag": "analytics", "noindex": True,
     "no_ask": True, "crumb": "Counted", "title": f"Counted: {name} — donttrade",
     "description": f"A page the Challenge Readiness Check loads so the site's cookie-free analytics count one step: {name}."}
    for name in COUNT_EVENTS
]

# Legal pages (step 17). The French versions (/fr/…) exist only with paid_report on; the
# hreflang pair is declared only then (alternates_if_paid).
PAGES += [
    {"template": "pages/privacy.html", "path": "/privacy/", "requires_flag": None, "updated": "2026-11-06",
     "crumb": "Privacy", "alternates_if_paid": [("en", "/privacy/"), ("fr", "/fr/confidentialite/"), ("x-default", "/privacy/")],
     "title": "Privacy Notice — donttrade",
     "description": "What donttrade collects and why: no cookies, free tools that read your file in your browser, "
                    "Web3Forms forms, Gmail, Stripe and your rights."},
    {"template": "pages/terms.html", "path": "/terms/", "requires_flag": None, "updated": "2026-11-06",
     "crumb": "Terms", "alternates_if_paid": [("en", "/terms/"), ("fr", "/fr/conditions/"), ("x-default", "/terms/")],
     "title": "Terms, Refunds and the Pilot — donttrade",
     "description": "Payment, delivery and refund terms for the donttrade test, the Pilot and the monthly plan for "
                    "firms, in plain language."},
]

# French versions (FRENCH-LEGAL-AND-CHECKOUT-DRAFTS §8.1), donttrade test only, behind the same
# commerce flag as the English consumer clauses. Unreviewed drafts: lawyer + legal translator first.
PAGES += [
    {"template": "pages/fr/avant-de-payer.html", "path": "/fr/avant-de-payer/", "requires_flag": "paid_report",
     "lang": "fr", "crumb": "Avant de payer", "updated": "2026-11-06", "scripts": ["/static/js/print.js"], "noindex": True,
     "alternates": [("fr", "/fr/avant-de-payer/"), ("en", "/before-you-pay/"), ("x-default", "/before-you-pay/")],
     "title": "Avant de payer : test donttrade — donttrade",
     "description": "Ce que vous acceptez avant de payer le test donttrade : vendeur, prix en dollars américains, "
                    "exigences techniques, remboursements et restrictions."},
    {"template": "pages/fr/conditions.html", "path": "/fr/conditions/", "requires_flag": "paid_report",
     "lang": "fr", "crumb": "Conditions", "updated": "2026-11-06",
     "alternates": [("fr", "/fr/conditions/"), ("en", "/terms/"), ("x-default", "/terms/")],
     "title": "Conditions de service et de vente — donttrade",
     "description": "Conditions du test donttrade : prix, paiement, livraison, nouveau test, "
                    "remboursements et droit de rétractation."},
    {"template": "pages/fr/confidentialite.html", "path": "/fr/confidentialite/", "requires_flag": "paid_report",
     "lang": "fr", "crumb": "Confidentialité", "updated": "2026-11-06",
     "alternates": [("fr", "/fr/confidentialite/"), ("en", "/privacy/"), ("x-default", "/privacy/")],
     "title": "Politique de confidentialité — donttrade",
     "description": "Ce que donttrade recueille et pourquoi : aucun témoin, fichier lu dans votre navigateur, "
                    "chiffres épurés pour le test payant, et vos droits."},
]
PAID_ONLY_PATHS_FR = ["/fr/avant-de-payer/", "/fr/conditions/", "/fr/confidentialite/"]

# Refund request pages and the partner terms (6 Nov, Round A6/A8). The refund pages exist only with [flags]
# refund_no_result; all are noindex, out of the sitemap, and the partner page is linked from nowhere (the plan keeps it
# and the codes unannounced until the live test-mode run passes). The refund form posts to Web3Forms (the default
# form-action) and its thank-you page is the form's `redirect`.
PAGES += [
    {"template": "pages/refund.html", "path": "/refund/", "requires_flag": "refund_no_result", "noindex": True,
     "no_ask": True, "crumb": "Ask for a refund", "scripts": [FORM_JS, "/static/js/refund.js"],
     "title": "Ask for a refund — donttrade",
     "description": "Ask for a refund of the donttrade test. A person reads every request and replies within 2 business days."},
    {"template": "pages/refund-thanks.html", "path": "/refund/thanks/", "requires_flag": "refund_no_result", "noindex": True,
     "no_ask": True, "crumb": "Thank you", "title": "Refund request received — donttrade",
     "description": "Your refund request reached donttrade. You get a reply within 2 business days, Eastern Time, Monday to Friday."},
    {"template": "pages/fr/remboursement.html", "path": "/fr/remboursement/", "requires_flag": "refund_no_result",
     "noindex": True, "no_ask": True, "lang": "fr", "crumb": "Demander un remboursement",
     "scripts": [FORM_JS, "/static/js/refund.js"], "title": "Demander un remboursement — donttrade",
     "description": "Demandez le remboursement du test donttrade. Une personne lit chaque demande et répond dans les 2 jours ouvrables."},
    {"template": "pages/fr/remboursement-merci.html", "path": "/fr/remboursement/merci/", "requires_flag": "refund_no_result",
     "noindex": True, "no_ask": True, "lang": "fr", "crumb": "Merci", "title": "Demande de remboursement reçue — donttrade",
     "description": "Votre demande de remboursement est arrivée chez donttrade. Réponse dans les 2 jours ouvrables, heure de l’Est."},
    {"template": "pages/partners.html", "path": "/partners/", "requires_flag": "paid_report", "requires_promo": True, "noindex": True,
     "no_ask": True, "crumb": "Partners", "title": "Partners — donttrade",
     "description": "How partners work with donttrade: a code for the buyer, a commission for the partner, and the rules for both."},
]

# The free Trading Journal (ARCHITECT-V3 §d, J3; [flags] journal). connect-src 'none' (the default),
# form-action 'none', and no analytics even when the analytics flag is on (D12, journal_problem): the page
# cannot send anything. No header answer box there either (it is a form).
JOURNAL_PATHS = ["/journal/"]
JOURNAL_CSS = "/static/css/journal.css"   # only on the journal pages; left out of a flag-off build
PAGES += [
    {"template": "pages/journal.html", "path": "/journal/", "requires_flag": "journal", "sample": True, "app": True,
     "modules": ["/static/js/journal/main.js"], "styles": [JOURNAL_CSS], "no_forms": True, "no_analytics": True, "no_ask": True,
     "updated": "2026-10-21", "crumb": "Free trading journal", "parent": ("Free tools", "/tools/"),
     "title": "Free Trading Journal and P&L Calendar, No Sign-Up",
     "description": "A free trading journal and P&L calendar for MT5, MT4, IBKR, Tradovate and TradingView files. "
                    "No account: trades stay in this browser, with a backup you keep."},
]

# /help/ (ARCHITECT-V3 §c.5, Q-A1): every answer unit, grouped; the answer box's no-JS landing page.
# Rendered after every other page, from their HTML (build.answer_units).
PAGES += [
    {"template": "pages/help.html", "path": "/help/", "requires_flag": None, "updated": "2026-11-06",
     "crumb": "Questions", "scripts": ["/static/js/answers.js", "/static/js/answer-ui.js"], "title": "Questions: Prices, Refunds, Files and Privacy",
     "description": "Every answer on donttrade in one place: prices, refunds, what the free tools do with your file, "
                    "privacy and the terms, each with a link to its page."},
]

# The prediction study's results page (ARCHITECT-PREDICTION-STUDY-2026-10-30 §6.1, batch R1; [flags]
# prediction_results, off until the OSF registration is posted). Every verdict's wording is in the template
# before any firm runs; the page shows the one the result's verdict names, with the numbers from the script's
# --json output (site/config/prediction_result.json, or DT_PREDICTION_RESULT). No result file = "results pending".
PREDICTION_PATH = "/research/does-the-test-predict/"
PREDICTION_VERDICTS = ("NOT MEASURED", "FAIL: does not predict usefully", "FAIL: adds nothing", "PASS: meets target",
                       "PASS: below target", "INCONCLUSIVE")
PAGES += [
    {"template": "pages/research-prediction.html", "path": PREDICTION_PATH, "requires_flag": "prediction_results",
     "prediction": True, "updated": "2026-10-30", "crumb": "Does the test predict?", "parent": ("Research", "/research/"),
     "title": "Does the donttrade Test Predict Prop-Challenge Breaches? A Pre-Registered Study",
     "description": "A pre-registered study of past prop-firm accounts: do habits in the first 30 trades rank the "
                    "accounts that broke a loss rule in the next 30 days? The plan, the code and every result."},
]


def prediction_context():
    """The study facts (site/config/prediction_study.json) and, if it exists, one result (the script's --json
    output, wrapped as {"runs": [...], "pooled": {...} or null, "verdict": ...}), plus the chart geometry."""
    sp = os.environ.get("DT_PREDICTION_STUDY") or os.path.join(SITE, "config", "prediction_study.json")
    with open(sp, encoding="utf-8") as f:
        study = json.load(f)
    if not study.get("osf_url") or not study.get("registered_on"):
        die("prediction_results is on, but prediction_study.json has no osf_url or registered_on: the page goes "
            "live only after the OSF registration is posted")
    rp = os.environ.get("DT_PREDICTION_RESULT") or os.path.join(SITE, "config", "prediction_result.json")
    result = None
    if os.path.exists(rp):
        with open(rp, encoding="utf-8") as f:
            result = json.load(f)
        if result.get("verdict") not in PREDICTION_VERDICTS:
            die(f"{rp}: verdict must be one of: {', '.join(PREDICTION_VERDICTS)}")
        if not result.get("runs"):
            die(f"{rp}: no runs")
        for run in result["runs"]:
            if run.get("dt_version") != "DT-1" or run.get("script") != "prediction_test.py":
                die(f"{rp}: a run is not prediction_test.py output for DT-1")
    chart = None
    if result and result["verdict"] != "NOT MEASURED" and len(result["runs"]) == 1 and "deciles" in result["runs"][0]:
        run = result["runs"][0]
        rates = [d["breaches"] / d["n"] for d in run["deciles"]]
        top = max(0.1, math.ceil(max(rates) * 10) / 10)
        n = len(rates)
        bw = 360 / n
        bars = [{"x": 48 + i * bw + 1, "w": bw - 2, "h": 160 * r / top, "y": 180 - 160 * r / top, "rate": r,
                 "label": (str(d["first"]) if d["first"] == d["last"] else f"{d['first']}-{d['last']}"),
                 "n": d["n"], "breaches": d["breaches"]} for i, (r, d) in enumerate(zip(rates, run["deciles"]))]
        ticks = [{"y": 180 - 160 * k / 4, "v": top * k / 4} for k in range(5)]
        cal = None
        full = (run.get("calibration") or {}).get("Full model (B0 + DT-1)")
        if full:
            cal = [{"cx": 48 + 200 * b["mean_pred"], "cy": 220 - 200 * b["observed"], "p": b["mean_pred"],
                    "o": b["observed"], "n": b["n"]} for b in full["bands"]]
        chart = {"bars": bars, "ticks": ticks, "cal": cal}
    return {"study": study, "result": result, "chart": chart, "verdicts": PREDICTION_VERDICTS}


# Hybrid "Start a Pilot" (pilot_checkout, default off): the thank-you page with the Stripe link.
PAGES += [
    {"template": "pages/pilot-thanks.html", "path": "/start/pilot-thanks/", "requires_flag": "pilot_checkout",
     "noindex": True, "crumb": "Pay for the Pilot", "title": "Pilot request received — donttrade",
     "description": "Your Pilot request reached donttrade. Pay by card now through Stripe, or wait for the written "
                    "scope and pay by invoice."},
]
PILOT_ONLY_PATHS = ["/start/pilot-thanks/"]
PILOT_FLAG_MARKER = 'data-requires-flag="pilot_checkout"'

# The /tools/ index rows: tool, the question it answers, input, Open (plan step 12).
TOOLS = [
    {"name": "Trade stats", "href": "/tools/trade-stats/", "glyph": "stats", "group": "file",
     "short": "Your trade file → win rate, net result and streaks.", "preview": "stats", "icon": "stats",   # 25 Oct sweep: the card line and preview
     "question": "What does my own trade history show?",
     "question_if_badges": "What does my own trade history show, and which numbers are more than noise?",
     "input": "Your trade file"},
    {"name": "Trading heatmap", "href": "/tools/trading-heatmap/", "glyph": "heat", "group": "file",
     "short": "Your trade file → your results by hour and weekday.", "preview": "heat", "icon": "windows",   # 25 Oct sweep: the card line and preview
     "question": "How did my own trades turn out by the hour and weekday they opened?",
     "input": "Your trade file"},
    {"name": "Drawdown and recovery calculator", "href": "/tools/drawdown-calculator/", "glyph": "dd", "group": "file",
     "short": "A drawdown or your file → how deep and how long.", "preview": "dd", "icon": "split",   # 25 Oct sweep: the card line and preview
     "question": "What gain recovers a drawdown, and how deep and long were mine?",
     "input": "A drawdown in percent, or your trade file"},
    {"name": "Challenge Readiness Check", "href": "/tools/prop-challenge-simulator/", "glyph": "prop", "group": "file",
     "short": "Your file and a firm’s rules → pass, bust or out of time.", "preview": "prop", "icon": "flag",   # 25 Oct sweep: the card line and preview
     "question": "How would my past trading days have fared under a challenge’s rules?",
     "input": "Your trade file, or win rate and average win and loss; the rules"},
    {"name": "Bad-day check", "href": "/tools/bad-day-check/", "glyph": "badday", "group": "file",
     "short": "Your file and a date → that day beside a typical one.", "preview": "badday", "icon": "list",
     "question": "How did one day compare with my typical day?",
     "input": "Your trade file and a date"},
    {"name": "Lot size calculator", "href": "/tools/lot-size-calculator/", "glyph": "lot", "group": "calc",
     "short": "Balance, risk and stop → the lot size.", "preview": "", "icon": "scale",   # 25 Oct sweep: the card line and preview
     "question": "How many lots match the amount I chose to risk at this stop?",
     "input": "Balance, risk amount, stop distance, value per point"},
    {"name": "Risk-reward calculator", "href": "/tools/risk-reward-calculator/", "glyph": "rr", "group": "calc",
     "short": "Entry, stop and target → the break-even win rate.", "preview": "", "icon": "percent",   # 25 Oct sweep: the card line and preview
     "question": "At what win rate does this reward-to-risk ratio break even, and what is the expectancy in R?",
     "input": "Entry, stop and target, or the ratio; optionally a win rate"},
    {"name": "Disposition-effect calculator", "href": "/tools/disposition-calculator/", "glyph": "disp", "group": "calc",
     "short": "Four counts → did you sell winners sooner than losers?", "preview": "", "icon": "hourglass",   # 25 Oct sweep: the card line and preview
     "question": "Were winning positions sold more readily than losing ones?",
     "input": "Four counts of positions sold and held"},
    {"name": "Pass-rate calculator (for firm operators)", "href": "/tools/pass-rate-calculator/", "glyph": "pass", "group": "firm",
     "short": "Cohort counts → pass and payout rate. For firms.", "preview": "", "icon": "check",   # 25 Oct sweep: the card line and preview
     "question": "What are one cohort’s evaluation pass rate and payout rate?",
     "input": "Cohort counts"},
]


# 6 Nov (owner): the pass-rate calculator rebuilt as a native template (it was a lifted page until then); and
# every tool page gets its glyph, tools.css and tools-index.js (TOOL_GLYPHS, above).
PAGES += [
    {"template": "pages/tool-pass-rate.html", "path": "/tools/pass-rate-calculator/", "requires_flag": None,
     "scripts": ["/static/js/legacy/numbers.js", "/static/js/tools/pass-rate.js"], "app": True, "updated": "2026-11-06",
     "crumb": "Prop-firm pass-rate calculator",
     "title": "Prop Firm Pass Rate Calculator for Firm Operators",
     "description": "Free: a prop-firm evaluation pass rate and payout rate for one cohort, computed correctly. Runs in "
                    "your browser; your numbers are never sent."},
]
for _p in PAGES:
    if _p["path"] in TOOL_GLYPHS:
        _p.update({"glyph": TOOL_GLYPHS[_p["path"]], "styles": _p.get("styles", []) + [TOOLS_CSS],
                   "scripts": _p.get("scripts", []) + [TOOLS_JS],
                   "og_image": f"/assets/og/tool-{TOOL_GLYPHS[_p['path']]}.png"})   # 6 Nov (SEO round 1): one card per tool



# /learn/ (6 Nov, SEO round 1, ARCHITECT-PLAN-SEO phase 1 items 12 and 13). Plain explanations that measure and do not advise:
# every table is computed by site/learn_tables.py when the site is built, every DOI is in config/references.json (checked
# against Crossref), and nothing on these pages says what to do. The hub and both articles are in the sitemap and linked
# from the related blocks and the tool pages; the footer's Learn column waits on [flags] learn_nav (default off).
# "h1" and "learn" are read by the templates and by jsonld(); "published" is the first day, "updated" the content date
# (the sitemap lastmod and the Article dateModified, changed only when the content changes).
LEARN_HUB = "/learn/"
LEARN_LICENSE = "https://creativecommons.org/licenses/by-nc/4.0/"
PAGES += [
    {"template": "pages/learn-hub.html", "path": "/learn/", "requires_flag": None, "updated": "2026-11-06",
     "crumb": "Learn", "og_image": "/assets/og/learn.png", "learn": {"kind": "hub", "published": "2026-11-06"},
     "h1": "Learn: trading habits, risk math and the evidence",
     "title": "Learn: Trading Habits, Risk Math and the Evidence",
     "description": "Plain explanations of trading habits and risk math, each with sources and a free way to measure it in your own trades."},
    {"template": "pages/learn-drawdown.html", "path": "/learn/drawdown-recovery-table/", "requires_flag": None,
     "updated": "2026-11-06", "crumb": "Drawdown recovery table", "parent": ("Learn", LEARN_HUB),
     "og_image": "/assets/og/learn-drawdown.png",
     "h1": "Drawdown recovery table: the gain that gets an account back",
     "learn": {"kind": "article", "published": "2026-11-06", "refs": [],
               "datasets": [{"name": "Drawdown recovery table", "csv": "/data/drawdown-recovery.csv",
                             "description": "For falls of 1% to 90%: the gain on the smaller balance that undoes the fall, and the periods a steady gain per period would take. Computed by site/learn_tables.py."}]},
     "title": "Drawdown Recovery Table: Gain Needed to Get Back",
     "description": "The gain that gets an account back after a drawdown of 1% to 90%, computed at build time, plus max drawdown vs duration and why platforms differ."},
    {"template": "pages/learn-streaks.html", "path": "/learn/losing-streak-probability/", "requires_flag": None,
     "updated": "2026-11-06", "crumb": "Losing streak probability", "parent": ("Learn", LEARN_HUB),
     "og_image": "/assets/og/learn-streaks.png",
     "h1": "Losing streak probability: how many losses in a row to expect",
     "learn": {"kind": "article", "published": "2026-11-06", "refs": ["schilling1990"],
               "datasets": [{"name": "Losing streak probability table", "csv": "/data/losing-streak-probability.csv",
                             "description": "The chance of a run of 5, 8 or 10 or more losses in 50, 100 and 500 trades at win rates of 30% to 70%, assuming independent trades. Computed by site/learn_tables.py."}]},
     "title": "Losing Streak Probability: Losses in a Row by Win Rate",
     "description": "The chance of 5, 8 or 10 losses in a row at win rates from 30% to 70%, computed with a run-length recurrence, and when streaks are not random."},
]
LEARN_PATHS = [p["path"] for p in PAGES if p["path"].startswith("/learn/")]

# The 5 November 2026 sell-off (ARCHITECT-PLAN-SELLOFF-2026-11-06; CODER-REPORT-SELLOFF-2026-11-06). One study page, built from
# site/data/selloff-2026-11-05.json through site/selloff.py and site/config/market_2026_11_05.json through learn_tables.market_view,
# so no figure is typed in a template. It carries no price and no buy link (no study figure next to an offer). The Bad-day check
# (BADDAY_PATH) is the free tool it points to. SELLOFF_PUBLISHED is the day the figures were made: the build refuses a content date
# later than the real date (future_dated), so a later deploy day does not move it; change it only with a dated update.
SELLOFF_PATH = "/research/5-november-2026-sell-off/"
BADDAY_PATH = "/tools/bad-day-check/"
SELLOFF_PUBLISHED = "2026-11-06"
SELLOFF_REFS = ("imas2016", "coval2005")
SELLOFF_CHECK_DAYS = "2026-11-05,2026-11-06"
_SELL = []


def selloff_ctx():
    if not _SELL:
        try:
            _SELL.append(SO.context())
        except (SO.SellOffError, OSError, KeyError, ValueError) as e:
            die(f"sell-off study data: {e}")
    return _SELL[0]


SELLOFF_BAND_EXPIRES = "2026-11-21"   # the home band's last day (owner decision, plan section d)


def dated_band(today=None):
    """The home band's text, or None on SELLOFF_BAND_EXPIRES and after (fix round 1, F4: gone in a build dated 21 Nov and later).
    It holds the FRED market figure only; no study figure may sit on the home page (tests/test_selloff.py)."""
    import datetime as dt
    today = today or _today()
    if today >= dt.date.fromisoformat(SELLOFF_BAND_EXPIRES):
        return None
    F = selloff_ctx()["F"]
    nc = LT.market_view()["indices"]["nasdaq_composite"]
    return {"expires": SELLOFF_BAND_EXPIRES, "date_label": F["event_long"], "date_long": "5 November", "nasdaq": f"{abs(nc['raw']['change_pct']):.1f}%",
            "link": SELLOFF_PATH}


def selloff_page():
    F = selloff_ctx()["F"]
    h1 = (f"{F['event_long']}: {F['hip3']} wallets were force-closed on Hyperliquid’s builder-listed markets, about {F['hip3_wd_ratio']} times the median weekday")
    return {"template": "pages/research-selloff-2026-11-05.html", "path": SELLOFF_PATH, "requires_flag": None, "selloff": True,
            "updated": SELLOFF_PUBLISHED, "published": SELLOFF_PUBLISHED, "crumb": f"{F['event_short']} 2026 sell-off",
            "parent": ("Research", "/research/"), "og_image": "/assets/og/selloff.png", "h1": h1,
            "check_path": BADDAY_PATH, "check_days": SELLOFF_CHECK_DAYS,
            "dek": (f"On the Nasdaq Composite’s largest one-day fall since April 2025, forced closes on the builder-listed markets of one crypto "
                    f"exchange ran at about {F['hip3_wd_ratio']} times the median weekday. We counted them with a method we wrote down first."),
            "citation": [["citation_title", h1], ["citation_author", "donttrade"],
                         ["citation_publication_date", SELLOFF_PUBLISHED.replace("-", "/")]],
            "title": f"{F['event_short']} 2026 Sell-Off: {F['hip3']} Hyperliquid Wallets Force-Closed",
            "description": (f"On {F['event_short']} 2026, {F['hip3']} Hyperliquid wallets were force-closed on builder-listed markets, about "
                            f"{F['hip3_wd_ratio']} times the median weekday. Method set down first, open data.")}


PAGES += [selloff_page()]

# Config the SEO round reads (config/studies.json, related.json, glossary_terms.json, references.json).
RESEARCH_LIST_END = re.compile(r'(?s)</li>\s*(?=</ul>\s*<h2 id="sample-report">)')   # the end of /research/'s list of all studies
STUDIES_JSON = os.path.join(SITE, "config", "studies.json")
RELATED_JSON = os.path.join(SITE, "config", "related.json")
GLOSSARY_JSON = os.path.join(SITE, "config", "glossary_terms.json")
REFERENCES_JSON = os.path.join(SITE, "config", "references.json")
DOI_RE = re.compile(r"10\.\d{4,9}/[^\s\"<>]+")
ABOUT_LINE = ("donttrade is one person measuring the plan gap: the difference between how traders plan to act and how they "
              "actually act, from account-level data.")   # the first sentence of /about/ (the Organization description; checked in build())
ORG_LOGO = "/assets/logo-512.png"   # 512 x 512, made by checks/make_seo_assets.py from assets/favicon.svg


def _load_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def studies():
    """{path: study} from studies.json (the four studies that have a Zenodo DOI), with the datasets they rest on resolved."""
    cfg = _load_json(STUDIES_JSON)
    out = {}
    for st in cfg["studies"]:
        if not re.fullmatch(r"10\.5281/zenodo\.\d+", st["doi"]) or not st["doi"].endswith(st["zenodo_id"]):
            die(f"studies.json: {st['path']} has a DOI that is not its Zenodo record's ({st['doi']!r})")
        st = dict(st)
        st["based_on"] = [dict(cfg["datasets"][k], key=k) for k in st["based_on"]]
        out[st["path"]] = st
    return out


def references():
    return _load_json(REFERENCES_JSON)["refs"]


def apa_line(st):
    """APA 7 style, for the cite box: author (the site), year, title [Preprint], repository, DOI link."""
    year = st["published"][:4]
    return f"donttrade. ({year}). {st['title']} [Preprint]. Zenodo. https://doi.org/{st['doi']}"


def bibtex_entry(st):
    def esc(t):
        return t.replace("\\", "\\textbackslash{}").replace("%", "\\%").replace("&", "\\&").replace("#", "\\#").replace("_", "\\_")
    key = "donttrade" + st["published"][:4] + st["slug"]
    return ("@misc{" + key + ",\n  author = {{donttrade}},\n  title = {" + esc(st["title"]) + "},\n  year = {" + st["published"][:4] +
            "},\n  publisher = {Zenodo},\n  doi = {" + st["doi"] + "},\n  url = {https://doi.org/" + st["doi"] + "}\n}")


def related_for(path, pages_by_path):
    """The Related block's entries for this page (config/related.json). Every target must be a page this build
    publishes and indexes (no noindex, no missing flag): a link to a page that is not there fails the build."""
    cfg = _load_json(RELATED_JSON)["pages"]
    out = []
    for r in cfg.get(path, []):
        target = r["href"].split("#")[0]
        pg = pages_by_path.get(target)
        if pg is None or pg.get("noindex"):
            die(f"related.json: {path} links {r['href']}, which this build does not publish as an indexable page")
        if target == path:
            die(f"related.json: {path} links itself")
        out.append(r)
    return out


def glossary_terms():
    return _load_json(GLOSSARY_JSON)["terms"]


def learn_context():
    """What the /learn/ templates print: every figure comes from site/learn_tables.py, none is typed in."""
    gains = {r["drawdown_pct"]: r["gain_pct"] for r in LT.recovery_rows()}
    streaks = LT.streak_tables()
    return {
        "lt": LT,
        "recovery": [{"d": r["drawdown_pct"], "gain": LT.format_gain(r["gain_pct"])} for r in LT.recovery_rows()],
        "gain_for": lambda d: LT.format_gain(gains[d], prose=True),   # in sentences: "25%", "100%"
        "period_gains": LT.PERIOD_GAINS,
        "periods": [{"d": r["drawdown_pct"], "n": r["periods"]} for r in LT.periods_rows()],
        "streak_tables": [{"n": n, "rows": [{"w": r["win_rate"], "cells": [LT.format_prob(x) for x in r["probs"]]} for r in rows]}
                          for n, rows in streaks.items()],
        "run_lengths": LT.RUN_LENGTHS,
        "prob_for": lambda n, w, k: LT.format_prob(LT.prob_run_at_least(n, w, k)),
        "streak_cost": [{"f": f, "cells": [f"{LT.streak_cost(f, k):.1f}%" for k in LT.RUN_LENGTHS]} for f in LT.COST_FRACTIONS],
        "enum": LT.enumerate_runs(3, 2),
        "enum_prob": LT.format_prob(LT.prob_run_at_least(3, 50, 2)),
        "win_rates": LT.WIN_RATES, "trade_counts": LT.TRADE_COUNTS,
        "dd_min": LT.DRAWDOWNS[0], "dd_max": LT.DRAWDOWNS[-1],
    }


def write_learn_data(out):
    """/data/*.csv for the two /learn/ tables, from the same functions the page tables use."""
    d = os.path.join(out, "data")
    os.makedirs(d, exist_ok=True)
    for name, text in (("drawdown-recovery.csv", LT.recovery_csv()), ("losing-streak-probability.csv", LT.streak_csv())):
        with open(os.path.join(d, name), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)


def write_selloff_data(out):
    """/data/5-november-2026-hyperliquid-daily.csv (from the same rows the page's tables use) and /data/5-november-2026/, the plan,
    its hash, the code, the run log (the 31 input hashes) and the outputs, copied byte for byte from checks/selloff/zenodo/."""
    d = os.path.join(out, "data")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, os.path.basename(SO.CSV_PATH)), "w", encoding="utf-8", newline="\n") as f:
        f.write(SO.csv_text())
    pack = os.path.join(d, os.path.basename(SO.PACK_URL.rstrip("/")))
    os.makedirs(pack, exist_ok=True)
    for name in SO.PACK_FILES:
        src = os.path.join(SO.PACK_DIR, name)
        if not os.path.exists(src):
            die(f"sell-off pack: checks/selloff/zenodo/{name} is missing (run checks/selloff/make_zenodo_pack.py)")
        shutil.copyfile(src, os.path.join(pack, name))
    # 7 Nov: the market-by-market CSV sits next to the daily CSV, byte for byte from the pack (its SHA-256 is printed on the page)
    src = os.path.join(SO.PACK_DIR, SO.PM_CSV)
    if not os.path.exists(src):
        die(f"sell-off pack: checks/selloff/zenodo/{SO.PM_CSV} is missing (run checks/selloff/per_market.py build)")
    shutil.copyfile(src, os.path.join(d, SO.PM_CSV))


def tools_for(flags):
    """TOOLS with each row's question for this build (C1: no "more than noise" without free_badges)."""
    return [{**{k: v for k, v in t.items() if k != "question_if_badges"},
             "question": t.get("question_if_badges", t["question"]) if flags["free_badges"] else t["question"]}
            for t in TOOLS]


SAMPLE_CSV = os.path.join(SITE, "static", "samples", "example-trades.csv")
TOOL_PREVIEWS_JSON = os.path.join(SITE, "config", "tool_previews.json")


def tool_previews():
    """The tool cards' preview numbers (25 Oct sweep): the tools' own results on the sample file, captured by
    checks/make_tool_previews.py. Refuses to build when the sample file changed since they were captured."""
    with open(TOOL_PREVIEWS_JSON, encoding="utf-8") as f:
        tp = json.load(f)
    with open(SAMPLE_CSV, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    if tp.get("sample_sha256") != sha:
        die(f"{TOOL_PREVIEWS_JSON} was captured from another sample file: rerun python3 checks/make_tool_previews.py")
    return tp



def tool_real_data():
    """6 Nov (tools redesign B2): the real public data behind /tools/ and the tool-page displays,
    site/config/tool_real.json (checks/real_data/make_tool_real.py). Refused when its shipped trade file or the test's report
    changed since it was made, or when that report's method is not the one the report page accepts."""
    data = tool_real.load()
    # 6 Nov fix round 2: the file with the real tickers (checks/real_data/raw/real-trades.csv) is not committed, so
    # the build checks the coded copy it ships; make_tool_real.py --check recomputes from the original where fetched.
    with open(tool_real.TOOL_REAL_REPORT_JSON, "rb") as f:
        rep_bytes = f.read()
    ins = data["inputs"]
    with open(REAL_SAMPLE_CSV, "rb") as f:   # the shipped copy, tickers replaced with codes
        if ins["checks/real_data/real-trades.coded.csv"]["sha256"] != hashlib.sha256(f.read()).hexdigest():
            die("checks/real_data/real-trades.coded.csv changed since tool_real.json was made: rerun "
                "checks/real_data/make_coded_csv.py and make_tool_real.py")
    if ins["site/config/tool_real.report.json"]["sha256"] != hashlib.sha256(rep_bytes).hexdigest():
        die("site/config/tool_real.json was made from another tool_real.report.json: rerun checks/real_data/make_tool_real.py")
    if data["report"]["method_version"] != page_method_version():
        die(f"site/config/tool_real.json: the real account's report is method {data['report']['method_version']}, the "
            f"report page accepts {page_method_version()}: rerun checks/real_data/run_report.py and make_tool_real.py")
    return data


def evidence():
    """Numbers for the homepage evidence strip and finding block, read from today's pages
    (the same sources the v1 self-count test reads), so the home page cannot drift from
    them. Fails loudly if a source page changes shape or the counts disagree."""
    # Since steps 28–29 these pages are template-owned: read their lifted bodies (the source
    # of the built pages), not docs/, which the step-30 bundle replaces.
    main_of = lifted_fragment
    studies = sorted(set(re.findall(r'href="(/research/[a-z0-9-]+/)"', main_of("research"))))
    corr = main_of("corrections")
    t = re.search(r"(?s)<table.*?<tbody>(.*?)</tbody>", corr)
    if not t:
        die("evidence: no corrections table in site/templates/lifted/corrections.html")
    corrections = len(re.findall(r"<tr\b", t.group(1)))
    m = re.search(r"The scripts behind (\d+) of the (\d+) studies are public", main_of("code"))
    if not m:
        die("evidence: the 'scripts behind N of the M studies' sentence is gone from site/templates/lifted/code.html")
    if int(m.group(2)) != len(studies):
        die(f"evidence: /code/ says {m.group(2)} studies but /research/ lists {len(studies)}")
    sentence = "76.1% of 4,659 retail traders realised their gains more readily than their losses."
    if sentence not in main_of("research_disposition-effect"):
        die("evidence: the finding sentence is no longer on /research/disposition-effect/ word for word")
    return {"studies": len(studies), "corrections": corrections, "scripts_public": int(m.group(1)),
            "finding": {"pct": "76.1%", "rest": sentence[len("76.1% "):], "url": "/research/disposition-effect/"}}


REPORT_METHODS_JSON = os.path.join(SITE, "config", "report_methods.json")
WORDING_JS = os.path.join(SITE, "static", "js", "paid", "wording.js")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def page_method_version():
    """The METHOD_VERSION the paid report page accepts (wording.js), which must equal the Worker's (smoke D-6)."""
    with open(WORDING_JS, encoding="utf-8") as f:
        m = re.search(r"^export const METHOD_VERSION = '([0-9]{4}-[0-9]{2}-[0-9]{2}\.[a-z0-9]+)';$", f.read(), re.M)
    if not m:
        die("report methods: no METHOD_VERSION line in site/static/js/paid/wording.js")
    return m.group(1)


def challenge_presets():
    """The firm-rules library for the Readiness Check (checks/check_rules.py): the build fails on any library problem,
    warns about presets last checked more than 30 days ago, and leaves out those more than 45 days old and the ones
    that cannot be quoted. DT_TODAY (yyyy-mm-dd) sets the date (tests). Only what the page uses goes in."""
    import importlib.util
    spec = importlib.util.spec_from_file_location("check_rules", os.path.join(REPO, "checks", "check_rules.py"))
    cr = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cr)
    lib = cr.load(CHALLENGE_RULES_JSON)
    import datetime
    today = _today()
    probs = cr.validate(lib, today)
    if probs:
        die("challenge rules: " + "; ".join(probs[:5]) + (" …" if len(probs) > 5 else ""))
    warn, _ = cr.freshness(lib, today)
    for pid in warn:
        print(f"NOTE: challenge rules: {pid} was last checked more than {cr.WARN_DAYS} days ago (hidden after {cr.HIDE_DAYS})")
    out = []
    for p in cr.shown(lib, today):
        y, mo, d = (int(x) for x in p["last_checked"].split("-"))
        out.append({"id": p["id"], "firm": p["firm"], "program": p["program"], "account_size": p["account_size"],
                    "scale": p["scale"], "status": p["status"], "rules": p["rules"], "not_modelled": p["not_modelled"],
                    "not_stated": cr.not_stated(p), "last_checked": p["last_checked"],
                    "read_text": f"{d} {MONTHS[mo - 1]} {y}", "url": p["sources"][0]["url"],
                    # S4: the unit the rules are stated in, and every source page (not only the first)
                    "currency": p.get("currency"), "urls": list(dict.fromkeys(s["url"] for s in p["sources"]))})
    return {"rules_lib": lib["rules_lib"], "presets": out, "firms": sorted({p["firm"] for p in out}, key=str.lower)}


def report_methods_renamed():
    """The dated rename line under the method table (29 Oct: the habit report became the donttrade test), or None."""
    path = os.environ.get("DT_REPORT_METHODS_JSON") or REPORT_METHODS_JSON
    with open(path, encoding="utf-8") as f:
        r = json.load(f).get("renamed")
    if r is None:
        return None
    if sorted(r) != ["date", "text"] or not re.fullmatch(r"2[0-9]{3}-[0-9]{2}-[0-9]{2}", r["date"]) or not r["text"].strip():
        die(f"report methods: malformed renamed {r!r} ({path})")
    y, mo, d = (int(x) for x in r["date"].split("-"))
    return {**r, "date_text": f"{d} {MONTHS[mo - 1]} {y}"}


def report_methods():
    """The donttrade test's dated method versions for /corrections/#report-method (the Lead's decision, 23 Oct:
    the re-test sentence says every change is dated there). DT_REPORT_METHODS_JSON reads another file (tests).
    Fails when the page's METHOD_VERSION has no entry, so no build can promise a dated log it does not show."""
    path = os.environ.get("DT_REPORT_METHODS_JSON") or REPORT_METHODS_JSON
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)["entries"]
    out = []
    for e in entries:
        # 29 Oct (owner): a method version may carry a short public name, "DT-1"; the page always pairs it
        # with a descriptor of the test (lint: claim:dt_name_alone).
        if sorted(set(e) - {"name"}) != ["date", "method", "text"] or not re.fullmatch(r"2[0-9]{3}-[0-9]{2}-[0-9]{2}", e["date"]) \
                or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.[a-z0-9]+", e["method"]) or not e["text"].strip() \
                or ("name" in e and not re.fullmatch(r"DT-[1-9][0-9]*", e["name"])):
            die(f"report methods: malformed entry {e!r} ({path})")
        y, mo, d = (int(x) for x in e["date"].split("-"))
        out.append({**e, "date_text": f"{d} {MONTHS[mo - 1]} {y}"})
    if [e["date"] for e in out] != sorted((e["date"] for e in out), reverse=True):
        die(f"report methods: entries must be newest first ({path})")
    if len({e["method"] for e in out}) != len(out):
        die(f"report methods: a method is listed twice ({path})")
    names = [e["name"] for e in out if "name" in e]
    if len(set(names)) != len(names):
        die(f"report methods: a method name is used twice ({path})")
    mv = page_method_version()
    if mv not in {e["method"] for e in out}:
        die(f"report methods: the report page's METHOD_VERSION {mv} has no dated entry in {path} "
            "(the re-test sentence promises one on /corrections/)")
    return out
def human_date(iso):
    """2026-10-17 → 17 Oct 2026."""
    y, m, d = (int(x) for x in iso.split("-"))
    return f"{d} {MONTHS[m - 1]} {y}"


COMMIT_URL = "https://github.com/donttrade/disposition-effect/commit/"


def commit_on_remote(sha, repo=None):
    """True when a remote-tracking branch (refs/remotes/*, as of the last fetch) contains the commit, so
    the GitHub commit page exists. Read from the local refs only: no network, and the build stays
    deterministic for one repo state. False when git cannot tell."""
    import subprocess
    try:
        r = subprocess.run(["git", "-C", repo or REPO, "for-each-ref", "--contains", sha, "--format=%(refname)",
                            "refs/remotes"], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.SubprocessError):
        return False
    return r.returncode == 0 and any(x and not x.endswith("/HEAD") for x in r.stdout.split())


def latest():
    """ARCHITECT-V3 §c.3 section 8, H7: the home "Latest" band, every date read from its source at build
    time: the newest study (its Article datePublished in the lifted page data), the newest row of the
    /corrections/ table, and the commit the site was built from (omitted when git is unavailable).
    The commit date, not the build date, so two builds of one commit stay byte-identical."""
    import subprocess
    studies = []
    for name in sorted(os.listdir(LIFTED_DIR)):
        if name.startswith("research_") and name.endswith(".json"):
            with open(os.path.join(LIFTED_DIR, name), encoding="utf-8") as f:
                m = json.load(f)
            if m.get("article", {}).get("datePublished"):
                studies.append((m["article"]["datePublished"], m["article"].get("headline") or m["crumb"], m["path"]))
    if not studies:
        die("latest: no study with a datePublished in site/templates/lifted/research_*.json")
    s_date, s_title, s_url = max(studies)
    t = re.search(r"(?s)<table.*?<tbody>(.*?)</tbody>", lifted_fragment("corrections"))
    rows = [re.match(r"(?s)\s*<td>(\d{1,2} [A-Z][a-z]{2} \d{4})</td>", r) for r in re.findall(r"(?s)<tr\b[^>]*>(.*?)</tr>", t.group(1))]
    if not rows or not all(rows):
        die("latest: a /corrections/ row does not start with a 'D Mon YYYY' date cell")
    def key(h):
        d, mon, y = h.split(" ")
        return (int(y), MONTHS.index(mon), int(d))
    c_date = max((r.group(1) for r in rows), key=key)
    commit = None
    try:
        r = subprocess.run(["git", "-C", REPO, "log", "-1", "--format=%H %cs"], capture_output=True, text=True, timeout=10)
        if r.returncode == 0 and re.fullmatch(r"[0-9a-f]{40} \d{4}-\d{2}-\d{2}", r.stdout.strip()):
            sha, day = r.stdout.split()
            # brand Tester D5: link only a commit GitHub has; otherwise the text stays, without the link
            on_remote = commit_on_remote(sha)
            commit = {"sha": sha, "short": sha[:7], "date": human_date(day),
                      "url": COMMIT_URL + sha if on_remote else None}
            if not on_remote:   # a NOTE, not a WARNING: WARNING means an escape guard was opened (D10)
                print(f"NOTE: latest: commit {sha[:7]} is on no remote branch, so the home page names it without "
                      "a link (push it, fetch, and build again to link it)", file=sys.stderr)
    except (OSError, subprocess.SubprocessError):
        commit = None
    return {"study": {"date": human_date(s_date), "title": s_title, "url": s_url},
            "correction": {"date": c_date, "url": "/corrections/"}, "commit": commit}


def sample_csv():
    """The synthetic example file, inlined into the page inside <script type="text/csv">.

    Inlined rather than fetched because the page's CSP is connect-src 'none'. The build
    refuses anything that could end the script element early."""
    with open(SAMPLE_CSV, encoding="utf-8") as f:
        text = f.read()
    if "<" in text or "&" in text:
        die("example-trades.csv contains '<' or '&'; it cannot be inlined safely")
    return text


# 6 Nov (owner rule "real public data, no worked examples"; Tester F12): the four file tools' "Try with real public
# data" button loads the real public-data account (checks/real_data/real-trades.coded.csv, a coded copy of the file every /tools/ figure is
# made from, CC BY 4.0), inlined the same way. The journal keeps the synthetic file (flag-off, not a /tools/ page);
# home's hero and cards keep tool_previews.json (the synthetic file) until /sample-report/ and home are switched.
# Its tickers are replaced with neutral codes ("Stock 01", ...; checks/real_data/make_coded_csv.py): the plan shows no
# tickers, and every other byte is the same, so every figure is too.
REAL_SAMPLE_CSV = os.path.join(REPO, "checks", "real_data", "real-trades.coded.csv")
REAL_SAMPLE_PATHS = ("/tools/trade-stats/", "/tools/trading-heatmap/", "/tools/drawdown-calculator/",
                     "/tools/prop-challenge-simulator/", "/tools/bad-day-check/")
REAL_SAMPLE_URL = "/static/samples/real-trades.csv"


def real_sample_csv():
    with open(REAL_SAMPLE_CSV, encoding="utf-8") as f:
        text = f.read()
    if "<" in text or "&" in text:
        die("real-trades.coded.csv contains '<' or '&'; it cannot be inlined safely")
    return text


# Motion plan D1 (21 Oct 2026): the home hero is a DOM capture of /tools/trade-stats/ on the sample
# file (checks/make_hero_dashboard.py). The partial records the sample's SHA-256; a different sample
# means the hero shows numbers the tool no longer prints, so the build stops until it is re-captured.
HERO_DASH = os.path.join(SITE, "templates", "partials", "hero_dashboard.html")


def hero_dashboard_body():
    """The partial's HTML as it lands in a page (the Jinja header comment renders to nothing)."""
    with open(HERO_DASH, encoding="utf-8") as f:
        return f.read().split("#}", 1)[1].strip()


def motion_problem(html, path):
    """Motion plan build guard: motion.js only on MOTION_PAGES; motion markup only with motion.js;
    data-count only inside the generated hero (count-up is for its 6 sample tiles, never a real figure)."""
    has_js = re.search(f'<script src="{re.escape(MOTION_JS)}(?:\\?v=[0-9a-f]{{8}})?" defer></script>', html) is not None
    if has_js and path not in MOTION_PAGES:
        return f"motion.js on {path}, which is not one of MOTION_PAGES"
    for marker in ("data-reveal", "data-count", "hero-dash"):
        if marker in html and not has_js:
            return f"{path} holds {marker} but does not load motion.js"
    if "data-count" in html.replace(hero_dashboard_body(), ""):
        return f"{path}: data-count outside the generated hero dashboard"
    return None


def vt_problem(html, path):
    """C8: vt.css only on VT_PAGES; the view-transition name only where vt.css is loaded."""
    has = re.search(f'<link rel="stylesheet" href="{re.escape(VT_CSS)}(?:\\?v=[0-9a-f]{{8}})?">', html) is not None
    if has and path not in VT_PAGES:
        return f"vt.css on {path}, which is not one of VT_PAGES"
    if "vt-start" in html and not has:
        return f"{path} names a view transition (vt-start) without vt.css"
    return None


def vt_css_problem(out):
    for root, _, files in os.walk(os.path.join(out, "static")):
        for name in sorted(files):
            if name.endswith(".css") and name != "vt.css":
                with open(os.path.join(root, name), encoding="utf-8") as f:
                    if "@view-transition" in f.read():
                        return f"@view-transition in {name}: only vt.css may opt pages in (C8)"
    return None


def journal_problem(html, path):
    """D12 / J10: the journal pages load no analytics and keep connect-src and form-action 'none'."""
    import html as _h
    loads = "cloudflareinsights" in html or "umami.is" in html
    if path in PAID_DETAILS_PATHS and loads:
        return f"{path} loads analytics (the pay dialog's details source never does: it is not a pageview)"
    if path not in JOURNAL_PATHS:
        return None
    if loads:
        return f"{path} loads analytics (the journal page never does: ARCHITECT-V3 D12)"
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', html)
    csp = _h.unescape(csp.group(1)) if csp else ""
    if "connect-src 'none';" not in csp or "form-action 'none';" not in csp:
        return f"{path}: its CSP must keep connect-src 'none' and form-action 'none'"
    return None


def check_hero_dashboard():
    with open(HERO_DASH, encoding="utf-8") as f:
        m = re.search(r"sample-sha256: ([0-9a-f]{64})\b", f.read())
    with open(SAMPLE_CSV, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    if not m:
        die("hero_dashboard.html records no sample-sha256: re-run python3 checks/make_hero_dashboard.py")
    if m.group(1) != sha:
        die(f"hero_dashboard.html was captured from a different sample ({m.group(1)[:12]}…, now {sha[:12]}…): "
            "re-run python3 checks/make_hero_dashboard.py")


# Tester N5 (motion fixes, 21 Oct 2026): cache-busting. The host sends max-age=600, so for 10 minutes after a
# deploy new HTML could run with the old cached CSS/JS. Every CSS/JS URL the build emits gets ?v=<first 8 hex of
# the SHA-256 of the file as served>. Module imports (and module-worker URLs) between our own scripts get the
# same query, and a script's hash covers its rewritten imports, so a change deep in the engine changes the URL of
# every module above it: a page never mixes old and new modules either.
# (data-index-src= and data-js-src=, the answer box's lazy scripts, end in src=" and are versioned too)
ASSET_REF_RE = re.compile(r'((?:src|href)=")(/static/[^"?#]+\.(?:js|css))(")')
JS_SPEC_RE = re.compile(r"""(\bfrom\s*|\bimport\s*\(?\s*|\bnew URL\(\s*)(['"])(\.{1,2}/[^'"?#\s]+\.js)\2""")
UNVERSIONED_RE = re.compile(r'(?:src|href)="/static/[^"]+\.(?:js|css)(?:#[^"]*)?"')


def set_ranked_flag(path, on):
    """[flags] whatif_ranked → the copied engine's WHATIF_RANKED (dies if the source line is not there once)."""
    with open(path, encoding="utf-8") as f:
        text = f.read()
    if text.count(RANKED_LINE) != 1 or text.count("WHATIF_RANKED = ") != 1:
        die(f"whatif_ranked: {RANKED_JS} must hold the line {RANKED_LINE!r} exactly once")
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text.replace(RANKED_LINE, f"export const WHATIF_RANKED = {'true' if on else 'false'};"))


def asset_version(data):
    return hashlib.sha256(data).hexdigest()[:8]


def version_assets(out, left_out=lambda rel: False):
    """Rewrite the built site in place: relative imports in out/static/**/*.js, then every /static/*.js|css
    URL in every HTML page. Returns {url: version}. Dies on an import cycle or a reference to a missing file,
    except an import of a file this build leaves out on purpose (left_out(path under static/), e.g. the
    free-badge module behind its flag), which stays as written: the code only loads it when the flag is on."""
    static = os.path.join(out, "static")
    final, versions, active = {}, {}, set()

    def js(fp):
        if fp in final:
            return final[fp]
        if fp in active:
            die(f"cache-busting: import cycle through {os.path.relpath(fp, out)}")
        active.add(fp)
        with open(fp, encoding="utf-8") as f:
            text = f.read()

        def dep(m):
            target = os.path.normpath(os.path.join(os.path.dirname(fp), m.group(3)))
            if not os.path.isfile(target):
                if left_out(os.path.relpath(target, static)):
                    return m.group(0)
                die(f"cache-busting: {os.path.relpath(fp, out)} imports {m.group(3)}, which is not in the build")
            return f"{m.group(1)}{m.group(2)}{m.group(3)}?v={asset_version(js(target))}{m.group(2)}"
        final[fp] = JS_SPEC_RE.sub(dep, text).encode("utf-8")
        active.discard(fp)
        return final[fp]

    for root, dirs, files in os.walk(static):
        dirs.sort()
        for name in sorted(files):
            fp = os.path.join(root, name)
            url = "/" + os.path.relpath(fp, out).replace(os.sep, "/")
            if name.endswith(".js"):
                versions[url] = asset_version(js(fp))
            elif name.endswith(".css"):
                with open(fp, "rb") as f:
                    versions[url] = asset_version(f.read())
    for fp, data in final.items():
        with open(fp, "wb") as f:
            f.write(data)

    def ref(m, page):
        if m.group(2) not in versions:
            die(f"cache-busting: {page} references {m.group(2)}, which is not in the build")
        return f"{m.group(1)}{m.group(2)}?v={versions[m.group(2)]}{m.group(3)}"
    for root, dirs, files in os.walk(out):
        dirs.sort()
        for name in sorted(files):
            if name.endswith(".html"):
                fp = os.path.join(root, name)
                with open(fp, encoding="utf-8") as f:
                    html = f.read()
                new = ASSET_REF_RE.sub(lambda m: ref(m, os.path.relpath(fp, out)), html)
                if new != html:
                    with open(fp, "w", encoding="utf-8", newline="") as f:
                        f.write(new)
    return versions


def unversioned_problem(html):
    m = UNVERSIONED_RE.search(html)
    return f"unversioned asset URL {m.group(0)} (cache-busting: version_assets)" if m else None


PAID_PAGES = [
    {"template": "pages/welcome.html", "path": "/welcome/", "requires_flag": "paid_report", "connect_worker": True,
     "noindex": True, "crumb": "Thank you", "modules": ["/static/js/paid/welcome.js"], "title": "Thank you — donttrade",
     "description": "Your donttrade test result is ready."},
    {"template": "pages/restore.html", "path": "/restore/", "requires_flag": "paid_report", "connect_worker": True,
     "noindex": True, "crumb": "Restore access", "modules": ["/static/js/paid/restore.js"], "title": "Restore access — donttrade",
     "description": "Reopen your donttrade test result on this browser."},
    {"template": "pages/report.html", "path": "/report/", "requires_flag": "paid_report", "connect_worker": True,
     "presets": True,  # S4: the firm-rules library for the rule check
     "no_umami": True,  # owner rule 2 Nov: no analytics beyond the Cloudflare beacon on the page that reads the file
     "noindex": True, "crumb": "Your test result", "modules": ["/static/js/paid/report.js"], "title": "Your test result — donttrade",
     "description": "Your donttrade test result, from your own trade file."},
]
PAGES += PAID_PAGES
# /pricing/ (step 15): one template. Flag off: sections stacked, firms first. Flag on:
# The printable "Before you pay" block (print.js). 25 Oct sweep: traders only, no Traders | Firms tabs.
PAGES.append({"template": "pages/pricing.html", "path": "/pricing/", "requires_flag": None,
              "scripts_if_paid": ["/static/js/print.js"], "product": PRODUCT_TEXT,
              # 6 Nov (SEO round 1): /pricing/ no longer declares the French page as its alternate. The French "Avant de
              # payer" is the twin of /before-you-pay/ (below), not of /pricing/; the old pair named the wrong English page.
              "crumb": "Pricing", "updated": "2026-11-06", "og_image": "/assets/og/pricing.png",
              "title": "Pricing: Published Prices for Firms and Traders",
              "description": "Published prices in USD for prop firms, brokers, trading platforms and traders, the "
                             "same for everyone and fixed in writing before anyone sees data."})
# /before-you-pay/ (29 Oct): the pay dialog's "Full details before you pay" is copied from this page (static/js/pay.js,
# a hidden same-origin frame), not from /pricing/, so opening it is not counted as a /pricing/ pageview. No analytics
# (as the journal), noindex (not disallowed in robots.txt since 6 Nov: see write_sitemap_and_robots), on ADDRESS_LINE_PATHS (the block names the
# seller). The block is partials/before_you_pay.html, the same one /pricing/ shows.
PAID_DETAILS_PATHS = ["/before-you-pay/"]
PAGES.append({"template": "pages/before-you-pay.html", "path": "/before-you-pay/", "requires_flag": "paid_report",
              "noindex": True, "no_analytics": True, "no_ask": True, "scripts": ["/static/js/print.js"],
              # 6 Nov (SEO round 1): the true English twin of /fr/avant-de-payer/. Both are noindex (a legal summary, not a
              # search page); robots.txt no longer blocks this one, so a crawler can read the noindex and the pair.
              "alternates": [("en", "/before-you-pay/"), ("fr", "/fr/avant-de-payer/"), ("x-default", "/before-you-pay/")],
              "crumb": "Before you pay", "title": "Before you pay — donttrade",
              "description": "What you agree to before paying for the donttrade test: seller, price, "
                             "files, restrictions and refunds."})

# Lifted pages (plan steps 28–29): the 20 pages that passed through from docs/ in the old design.
# checks/lift_pages.py copied each old <main> word for word into site/templates/lifted/<slug>.html
# (only the CSP-forced markup changes: style attributes → ls-* classes, inline scripts → files)
# and its head facts into <slug>.json. Each renders through pages/lifted.html inside a
# <!--frozen:start-->…<!--frozen:end--> region; checks/compare.py proves the visible text, ids,
# links, tables and citation meta equal the old page's, and lint holds the frozen region to the
# passthrough rules (its words may not change) and everything around it to the full list.
LIFTED_DIR = os.path.join(SITE, "templates", "lifted")
LIFTED_JS = "/static/js/lifted.js"


# Tester merge re-check MR-5 (24 Oct): a paid build names the seller (Before you pay, the terms and the privacy
# notice, s. 32), so the frozen "no name" lines of /about/ and /code/ are not true there. In a paid_report build
# only, each (old, new) pair replaces old (exactly once) in the page's frozen body; a free build keeps the old
# page word for word. checks/compare.py and lint undo the same pairs before comparing a paid build with
# checks/lifted-baseline/, so these are the only frozen-body differences a paid build may have. No other name
# is added: the author stays unnamed.
_SELLER_WHERE = ('the seller’s legal name is given for buyers in <a href="/pricing/#before-you-pay">Before you pay</a>, '
                 'the terms and the privacy notice')
PAID_LIFTED_SWAPS = {
    # 2 Nov (owner): with the donttrade test on sale, "Readers pay nothing" is out of date. A free build keeps it.
    # 3 Nov (Tester R2 I3, Manager): "for traders, the only paid product", since the sentence before says firms pay too.
    "/independence/": [("Readers pay nothing; the newsletter is free.",
                        "The research, the newsletter and the free tools cost readers nothing; for traders, the only "
                        "paid product is <a href=\"/pricing/#traders\">the donttrade test</a>.")],
    "/about/": [("There’s no name on it on purpose: every study",
                 "No author name is published here, on purpose (" + _SELLER_WHERE + "): every study"),
                # 2 Nov (owner): as on /independence/, with the donttrade test on sale. A free build keeps both.
                ('<span class="ls-sum">Firms pay for measurements. Readers pay nothing.</span>',
                 '<span class="ls-sum">Firms pay for measurements. The research and free tools cost readers nothing.</span>'),
                ("Firms pay for fixed-scope measurements of their own data; readers pay nothing; no firm can change a number.",
                 "Firms pay for fixed-scope measurements of their own data; the research and free tools cost readers "
                 "nothing, and for traders the only paid product is <a href=\"/pricing/#traders\">the donttrade "
                 "test</a>; no firm can change a number.")],
    "/code/": [("There is no name on this site; the scripts are what you check instead.",
                "No author name is published on this site (" + _SELLER_WHERE + "); the scripts are what you check "
                "instead."),
               # 29 Oct (owner): one visible name for /sample-report/, "Example report"
               ('<td><a href="/sample-report/">Sample trader report</a></td>', '<td><a href="/sample-report/">Example report</a></td>'),
               # 29 Oct (one product): the licence comes with the firm plan and the Pilot (partner/LICENSING.md)
               ("businesses need a licence, included in every engagement.",
                "businesses need a licence, included with the firm plan and the Pilot.")],
    # 29 Oct (owner): one visible name for /sample-report/, "Example report". In a paid build that page is the
    # donttrade test's own engine on example data, not the lifted research figure this sentence described.
    "/research/": [('<h2 id="sample-report">Sample trader report</h2>', '<h2 id="sample-report">Example report</h2>'),
                   ("What the coming trader report looks like, run on one real trader from the same public CC0 panel as "
                    "the disposition-effect study, chosen by a rule fixed before any individual result was looked at. "
                    "<a href=\"/sample-report/\">Read the sample report →</a>",
                    "What the donttrade test’s result looks like, from its own engine, run on example data. "
                    "<a href=\"/sample-report/\">Read the example report →</a>")],
    # 29 Oct (owner): sample data was labelled "Example data" here. 6 Nov (owner: real public data only): the
    # disposition calculator's frozen body now fills Odean's (1998) published counts in every build (a dated
    # correction in its baseline), and the pass-rate calculator is a template page with no invented example.
}
PAID_LIFTED_DESCRIPTIONS = {   # the same, for the page description (head only, outside the frozen body)
    "/about/": "Who writes donttrade, what the plan gap is and how it is measured, why no author name is published, "
               "and what this is not.",
}


def paid_lifted(path, html, paid):
    """The lifted fragment for this build: PAID_LIFTED_SWAPS applied in a paid_report build."""
    if not paid:
        return html
    for old, new in PAID_LIFTED_SWAPS.get(path, []):
        if html.count(old) != 1:
            die(f"paid lifted swap: {path} no longer holds this sentence exactly once: {old!r}")
        html = html.replace(old, new)
    return html


def lifted_pages():
    pages = []
    for name in sorted(os.listdir(LIFTED_DIR)) if os.path.isdir(LIFTED_DIR) else []:
        if not name.endswith(".json"):
            continue
        with open(os.path.join(LIFTED_DIR, name), encoding="utf-8") as f:
            m = json.load(f)
        page = {"template": "pages/lifted.html", "path": m["path"], "requires_flag": None,
                "lifted": name[:-len(".json")], "main_class": "lifted", "feeds": True,
                "crumb": m["crumb"], "title": m["title"], "description": m["description"],
                "og_image": m["og_image"], "citation": m["citation"],
                "scripts": [LIFTED_JS] + m.get("scripts", [])}
        for k in ("updated", "noindex", "redirect_to", "article", "form_action", "parent", "section"):
            if m.get(k):
                page[k] = m[k]
        if m["path"] in PAID_LIFTED_DESCRIPTIONS:
            page["if_paid"] = {"description": PAID_LIFTED_DESCRIPTIONS[m["path"]]}
        if m["path"] in TOOL_GLYPHS:   # 6 Nov (B2): the glyph and the real-data display, in pages/lifted.html's header
            page.update({"glyph": TOOL_GLYPHS[m["path"]], "styles": [TOOLS_CSS], "scripts": page["scripts"] + [TOOLS_JS],
                         "og_image": f"/assets/og/tool-{TOOL_GLYPHS[m['path']]}.png", "app": True})   # SEO round 1: its own card; WebApplication + FAQ JSON-LD
        pages.append(page)
    return pages


def lifted_fragment(slug):
    with open(os.path.join(LIFTED_DIR, slug + ".html"), encoding="utf-8") as f:
        return f.read()


LIFTED = lifted_pages()
PAGES += LIFTED
LIFTED_PATHS = [p["path"] for p in LIFTED]

# Delivery plan C-12 final (Tester T-3 T3-E): with paid_report on, /sample-report/ is no longer the lifted research
# figure but a real donttrade test: dt-private's analyse() on a committed synthetic file
# (site/config/sample-report.report.json, made by tests/fixtures/paid/make_sample_report.py), rendered by the real
# report.js. The lifted page stays in flag-off builds, where its lead already says it is not the donttrade test.
PAID_REPLACES_LIFTED = ("/sample-report/",)
SAMPLE_REPORT_JSON = os.path.join(SITE, "config", "sample-report.report.json")
SAMPLE_PAGE = {"template": "pages/sample-report.html", "path": "/sample-report/", "requires_flag": None,
               "modules": ["/static/js/paid/sample.js"], "crumb": "Example report", "og_image": "/assets/og/default.png",
               "title": "Example report — donttrade", "sample_report": True, "presets": True, "sample_trades": True,
               "description": "An example report of the donttrade test: the test's own engine and page, run on example data. "
                              "Not advice.", "updated": "2026-10-23"}


# S4: the committed trade file the sample report was made from (make_sample_report.py writes it; the sample report's
# golden test checks the report is the engine's output on it). The example page reads it with the report page's own
# engine for the facts and the rule check. Inlined (the page's CSP has connect-src 'none').
SAMPLE_REPORT_CSV = os.path.join(REPO, "tests", "fixtures", "paid", "sample-report.csv")


def sample_report_trades():
    with open(SAMPLE_REPORT_CSV, encoding="utf-8") as f:
        text = f.read()
    if "<" in text or "&" in text:
        die("sample-report.csv contains '<' or '&'; it cannot be inlined safely")
    return text


def lifted_paths_for(paid):
    """The lifted pages of a build with this paid flag (lint and compare.py use it)."""
    return [p for p in LIFTED_PATHS if not (paid and p in PAID_REPLACES_LIFTED)]


def sample_report():
    """The sample page's report, refused unless its method is the one the report page accepts."""
    with open(SAMPLE_REPORT_JSON, encoding="utf-8") as f:
        rep = json.load(f)
    if rep.get("method_version") != page_method_version():
        die(f"sample report: {SAMPLE_REPORT_JSON} is method {rep.get('method_version')}, the report page accepts "
            f"{page_method_version()}: rerun tests/fixtures/paid/make_sample_report.py --report")
    return rep

# Paths that may exist only when paid_report = true.
PAID_APP_PATHS = ["/welcome/", "/restore/", "/report/"]  # noindex, and disallowed in robots.txt
PAID_ONLY_PATHS = PAID_APP_PATHS + PAID_DETAILS_PATHS + PAID_ONLY_PATHS_FR


# The footer's privacy sentences. One wording for template pages (partials/footer.html) and
# passthrough pages (PASSTHROUGH_CHROME), so the two can never disagree with /privacy/.
# 3 Nov (Tester R2 / Manager): per page, so a page Umami (no_umami: /report/) or all analytics (no_analytics:
# /before-you-pay/, the journal) does not run on never says its visits are counted with it.
def footer_privacy(flags, umami=False, page=None):
    page = page or {}
    if flags["analytics"] and page.get("no_analytics"):
        parts = ["This site sets no cookies. Visits to this page are not counted; other pages are counted with "
                 + ("Cloudflare Web Analytics and Umami Cloud, neither of which sets a cookie." if umami
                    else "Cloudflare Web Analytics, which sets no cookie.")]
    elif flags["analytics"]:
        parts = ["This site sets no cookies. Visits are counted with Cloudflare Web Analytics, which sets no cookie."]
        if umami and page.get("no_umami"):
            parts = ["This site sets no cookies. Visits to this page are counted with Cloudflare Web Analytics, which "
                     "sets no cookie; Umami Cloud, which counts visits to other pages, does not run on this page."]
        elif umami:
            parts = ["This site sets no cookies. Visits are counted with Cloudflare Web Analytics and Umami Cloud, "
                     "which also counts some button clicks; neither sets a cookie."]
    else:
        parts = ["This site sets no cookies and runs no analytics."]
    if flags["paid_report"]:
        # D4: true once /welcome/ keeps the access key (localStorage and IndexedDB)
        # NIT 13: complete, matching /privacy/#report (the fingerprints kept for the re-test match)
        # C-14: the server keeps more than fingerprints (a purchase record, hourly counters; /privacy/#report),
        # so "only" now bounds what is kept OF the trade numbers, not what the server keeps.
        parts.append("It stores your light/dark choice in your own browser and, if you buy the donttrade test, your "
                     "access key there too. For that test your browser sends our server only stripped trade "
                     "numbers. The server does not keep them: of those numbers it keeps only a scrambled fingerprint "
                     "of each trade row from your first result, to match a re-test to the same history. Your file "
                     "itself is not uploaded.")
    else:
        parts.append("It stores only your light/dark choice, in your own browser.")
    if flags["paid_report"] or flags["pilot_checkout"]:
        parts.append("Card payments are handled by Stripe.")
    parts.append("Forms send what you type to Web3Forms, which emails it to us, and subscribing opens Substack; "
                 "their privacy policies apply.")
    return " ".join(parts)


# Decision 21 Oct (revised 09:00), narrowed 25 Oct (owner: "feels very open for customers"): with
# ANY commerce flag on, every page footer identifies the business, in one of two forms.
# The FULL line (name, country/province, the mailing address from private.toml, the business email)
# is on the pages where a buyer pays, or reads the terms before paying, or contacts us about a
# payment (ADDRESS_LINE_PATHS): Visa Core Rules 5.8.4.1 "address for Cardholder correspondence" +
# merchant country, shown where the cardholder transacts; Ontario Consumer Protection Act (O. Reg.
# 17/05 s. 32) disclosure before payment; CASL (the address with the contact pages). Every other
# page has the SHORT line (name, region, email, a link to the seller block on the terms), so no
# page is without the business's identity and none repeats the address needlessly.
# The seller's legal name and phone stay in the seller block (show_seller). With every commerce
# flag off neither line exists and private.toml is not read. One wording for template pages and
# passthrough pages. build.verify() and lint check every page has the right one exactly once.
BUSINESS_ID_ATTR = "data-business-id"
BUSINESS_ID_RE = re.compile(r"(?s)<p\b[^>]*\bdata-business-id\b[^>]*>.*?</p>")
BUSINESS_REGION = "Ontario, Canada"
ADDRESS_LINE_PATHS = frozenset({
    # 25 Oct (owner): only where a buyer pays or reads the terms and privacy notice
    "/pricing/", "/terms/", "/privacy/",
    "/fr/avant-de-payer/", "/fr/conditions/", "/fr/confidentialite/",
    # 29 Oct: the pay dialog's details source (PAID_DETAILS_PATHS): the Before-you-pay block, alone
    "/before-you-pay/"})
# The short line's link to the seller block: id="seller" in the terms' Contact section (the seller rows
# whenever show_seller; the full footer line is on that page in any commerce build). French pages exist
# only with paid_report, so the French link is used only then. verify() checks the target id exists.
BUSINESS_DETAILS = {"en": ("/terms/#seller", "Business details"),
                    "fr": ("/fr/conditions/#seller", "Coordonnées de l’entreprise")}
SELLER_ANCHOR = 'id="seller"'



def url_of(rel):
    """A built file's relative path → its URL ("about/index.html" → "/about/")."""
    url = "/" + rel.replace(os.sep, "/")
    return url[:-len("index.html")] if url.endswith("/index.html") or url == "/index.html" else url


def business_line_full(url):
    """Whether the page at this URL carries the full business line (with the mailing address)."""
    return url in ADDRESS_LINE_PATHS


def business_id_line(cfg, private, css_class=None, url=None, lang="en"):
    """The footer's business-identification paragraph for the page at url, or "" with every commerce
    flag off. The full form (with the address) on ADDRESS_LINE_PATHS, the short form elsewhere."""
    import html as _h
    if not any(cfg["flags"][f] for f in COMMERCE_FLAGS):
        return ""
    address = private.get("premises_address")
    if not isinstance(address, str) or not address.strip():
        die("a commerce flag is on but there is no mailing address (private.toml premises_address) for the footer")
    email = cfg["site"]["contact_email"]
    cls = f' class="{css_class}"' if css_class else ""
    mail = f"<a href=\"mailto:{_h.escape(email)}\">{_h.escape(email)}</a>"
    head = f"{_h.escape(cfg['site']['name'])} · {BUSINESS_REGION} · "
    if url is None or business_line_full(url):
        return f"<p{cls} {BUSINESS_ID_ATTR}=\"full\">{head}{_h.escape(address)} · {mail}</p>"
    href, label = BUSINESS_DETAILS["fr" if lang == "fr" and cfg["flags"]["paid_report"] else "en"]
    return f"<p{cls} {BUSINESS_ID_ATTR}=\"short\">{head}{mail} · <a href=\"{href}\">{label}</a></p>"


# Where the line goes in a passthrough page: just before the "who pays" paragraph, right
# under the contact line (every passthrough page has exactly one).
PASSTHROUGH_BUSINESS_ANCHOR = '  <p class="whopays">'


def passthrough_lang(text):
    m = re.search(r'<html[^>]*\slang="([a-z]+)', text)
    return m.group(1) if m else "en"


def add_business_line(text, rel, line):
    if not line:
        return text
    n = text.count(PASSTHROUGH_BUSINESS_ANCHOR)
    if n != 1:
        die(f"business line: {rel} holds the footer anchor {PASSTHROUGH_BUSINESS_ANCHOR.strip()!r} {n} time(s), expected 1")
    return text.replace(PASSTHROUGH_BUSINESS_ANCHOR, "  " + line + "\n" + PASSTHROUGH_BUSINESS_ANCHOR)


def trader_nav_label(flags):
    if flags["paid_report"]:
        return "Individual traders</a>"
    return 'Individual traders <span class="soon">coming soon</span></a>'


# Site-wide chrome on a passthrough page (the old header and footer), fixed at build time.
# Steps 28–29 lifted all 20 old pages, so today no page passes through and this is a guard:
# a docs/ HTML page that no template owns must still carry the old chrome exactly, or the build
# fails loudly. (old, new(flags), expected count per page; None = at least once).
OLD_FOOTER_PRIVACY = ("This site sets no cookies and runs no analytics; it stores only your light/dark choice, in your "
                      "own browser. Forms open on Tally and subscribing opens Substack; their privacy policies apply.")
PASSTHROUGH_CHROME = [
    (OLD_FOOTER_PRIVACY, footer_privacy, 1),   # B1: the forms are Web3Forms, not Tally
    # D3: Trial was renamed Pilot (22 Oct 2026). Labels only; every href and anchor is unchanged.
    ("Firms: start a trial</a>", "Firms: start a Pilot</a>", 2),        # desktop nav + mobile menu
    (">Firms: trial</a>", ">Firms: Pilot</a>", 1),                       # mobile header button
    ('<a href="/start/">Start a trial</a>', '<a href="/start/">Start a Pilot</a>', None),  # footer (+ 404 body)
    # R5: the old nav says the donttrade test is "coming soon"; with paid_report on it is sold
    ('Individual traders <span class="soon">coming soon</span></a>', trader_nav_label, 2),  # desktop nav + mobile menu
]


def fix_passthrough_chrome(text, rel, flags, umami=False):
    for old, new, expected in PASSTHROUGH_CHROME:
        n = text.count(old)
        if (expected is None and n < 1) or (expected is not None and n != expected):
            die(f"passthrough chrome: {rel} holds {old!r} {n} time(s), expected {expected or 'at least 1'}")
        if new is footer_privacy:
            new = footer_privacy(flags, umami)
        text = text.replace(old, new(flags) if callable(new) else new)
    return text


# Exact-text copy fixes applied to passthrough pages. docs/ stays untouched; the build fails
# if a sentence is no longer there exactly once. Empty since steps 28–29: the two fixes it held
# (/independence/ "Start a Pilot", /code/ "sends nothing anywhere") are LIFT_FIXES in
# checks/lift_pages.py, part of the lifted text. The mechanism stays for any page still passed through.
PASSTHROUGH_FIXES = {}

# The same for non-HTML files that pass through (brand Tester D4, 22 Oct): feed.xml's entry titles are
# public copy (feed readers show them), so "sealed" goes, as on the lifted pages (checks/lift_pages.py
# LIFT_FIXES). docs/ stays untouched. Once a bundle has put the new text into docs/, the old text is gone
# and the fix is already in place; the build fails only if neither text is there exactly once.
PASSTHROUGH_FILE_FIXES = {
    "feed.xml": [
        ("<title>Study: Swing-trading strategies under sealed pre-registration, a negative result (16 Oct 2026)</title>",
         "<title>Study: Swing-trading strategies under hashed pre-registration, a negative result (16 Oct 2026)</title>"),
    ],
}


def apply_file_fixes(out):
    for rel, fixes in PASSTHROUGH_FILE_FIXES.items():
        fp = os.path.join(out, rel)
        if not os.path.exists(fp):
            die(f"passthrough file fix: {rel} is not in the build (not in docs/)")
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        for old, new in fixes:
            if text.count(old) == 1:
                text = text.replace(old, new)
            elif text.count(new) != 1:
                die(f"passthrough file fix: {rel} holds neither the old nor the new text exactly once: {old!r}")
        with open(fp, "w", encoding="utf-8", newline="") as f:
            f.write(text)


# Manager C4: /privacy/ (and the home FAQ, /for-traders/) say the free tool pages "block outgoing
# requests". The template tool pages do (csp_for); the two old calculators, passed through from docs/
# until steps 28–29, get the same guard here: a CSP meta with connect-src 'none' and nothing from
# another origin. Their inline script and onsubmit handler need 'unsafe-inline' for scripts and their
# style attributes for styles; neither lets the page send anything (connect-src and form-action 'none').
# Since steps 28–29 both are lifted template pages: csp_for gives them the same directives without
# 'unsafe-inline', and the build fails if either path is neither a template page nor in docs/.
# 6 Nov: the pass-rate calculator is a native template page now (pages/tool-pass-rate.html); it keeps this policy.
PASSTHROUGH_CSP = ("default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; "
                   "img-src 'self' data:; font-src 'self'; connect-src 'none'; worker-src 'none'; "
                   "form-action 'none'; base-uri 'none'; object-src 'none'")
PASSTHROUGH_CSP_PAGES = (os.path.join("tools", "disposition-calculator", "index.html"),
                         os.path.join("tools", "pass-rate-calculator", "index.html"))


def add_passthrough_csp(text, rel):
    if rel not in PASSTHROUGH_CSP_PAGES:
        return text
    if "Content-Security-Policy" in text or text.count("<meta charset") != 1:
        die(f"passthrough CSP: {rel} must hold exactly one <meta charset> and no CSP of its own")
    i = text.index(">", text.index("<meta charset")) + 1
    return text[:i] + f'\n<meta http-equiv="Content-Security-Policy" content="{PASSTHROUGH_CSP}">' + text[i:]


def passthrough_pages(owned):
    """Relative paths of the docs/ HTML pages that no template owns (copied through)."""
    pages = []
    for root, dirs, files in os.walk(DOCS):
        dirs.sort()
        for name in sorted(files):
            rel = os.path.relpath(os.path.join(root, name), DOCS)
            if name.endswith(".html") and rel not in owned:
                pages.append(rel)
    return pages


class BuildError(Exception):
    pass


def die(msg):
    raise BuildError(msg)


FLAGS = ("paid_report", "analytics", "trader_first_home", "pilot_checkout", "free_badges", "journal", "ask_box", "whatif_ranked",
         "prediction_results", "refund_no_result", "learn_nav")
OPTIONAL_FLAGS = {"pilot_checkout": False, "free_badges": False, "journal": False, "ask_box": False,
                  "whatif_ranked": False, "prediction_results": False, "learn_nav": False,
                  "refund_no_result": False}  # older site.toml files may lack the line
# ARCHITECT-CHALLENGE-READINESS §2.7.3: [flags] whatif_ranked switches the ranked "Biggest changes on your past
# days" rules. Off until a Canadian securities lawyer clears the strings. The build writes the flag into the
# copied engine (prop-sim-core.js), whose source line must read exactly RANKED_LINE.
RANKED_JS = os.path.join("js", "tools", "prop-sim-core.js")
RANKED_LINE = "export const WHATIF_RANKED = false;"
RANK_JS = os.path.join("js", "tools", "prop-sim-rank.js")   # the ranked rules and their strings: only with the flag
# Free-launch condition C1 (21 Oct 2026): free_badges turns on the free tools' "real or noise"
# badges and their footnote, which the Architect is redesigning. Off (the committed default): the
# free tools show only the descriptive numbers, static/js/tools/trade-stats-badges.js is left out
# of the build, and every page's copy drops the check (BADGE_COPY, the if_badges overrides).
BADGES_JS = os.path.join("js", "tools", "trade-stats-badges.js")
JOURNAL_JS_DIR = os.path.join("js", "journal") + os.sep


# ------------------------------------------------------------------ nav (ARCHITECT-V3 §c.2, D1-D3)
# site.toml [[nav]]: a group with [[nav.items]] is a drop-down, one without is a plain link. The nav never
# shows a price, a % or a study number (D3): every label and description is refused here if it holds a
# digit, "$", "%" or a banned.toml word, so the header can never sit a finding next to an offer.
BANNED_TOML = os.path.join(REPO, "checks", "banned.toml")
NAV_TEXT_BAD = re.compile(r"[0-9$%]")
NAV_ICONS = ("journal", "stats", "flag", "scale", "hourglass", "list", "split", "doc", "code", "check", "bookmark",
             "building", "swap", "windows", "percent", "shield")


def banned_words():
    with open(BANNED_TOML, "rb") as f:
        words = tomllib.load(f)["words"]
    return [w for ws in words.values() for w in ws]


def nav_problem(nav):
    """Why the [[nav]] data breaks the nav rules, or None."""
    if not isinstance(nav, list) or not nav:
        return "[[nav]] is empty"
    # the matcher checks/lint.py uses, so "seal*" stems, wrapped phrases and hyphens mean the same here
    # (brand Tester D1/D2, 22 Oct); lint imports this module only inside functions, so no import cycle
    if os.path.join(REPO, "checks") not in sys.path:
        sys.path.insert(0, os.path.join(REPO, "checks"))
    from lint import _phrase_re
    banned = [(w, _phrase_re(w)) for w in banned_words()]
    for g in nav:
        texts = [g.get("label", "")]
        for it in g.get("items", []) + g.get("foot", []):
            for k in ("label", "href"):
                if not isinstance(it.get(k), str) or not it[k]:
                    return f"nav item {it!r} has no {k}"
            texts += [it["label"], it.get("desc", ""), it.get("label_if_paid", "")]
            if it.get("requires_flag") and it["requires_flag"] not in FLAGS:
                return f"nav item {it['label']!r}: requires_flag {it['requires_flag']!r} is not a flag"
            if "items" in g and it in g["items"] and it.get("icon") not in NAV_ICONS:
                return f"nav item {it['label']!r}: icon {it.get('icon')!r} is not in partials/icons.html"
        for t in texts:
            if NAV_TEXT_BAD.search(t):
                return f"nav text {t!r} holds a digit, '$' or '%' (the nav never shows a price, % or number)"
            for w, rx in banned:
                if rx.search(t):
                    return f"nav text {t!r} holds the banned word {w!r} (checks/banned.toml)"
    return None


def nav_for(nav, flags):
    """[[nav]] as this build renders it: items behind an off flag dropped, label_if_paid applied."""
    def keep(it):
        return not it.get("requires_flag") or flags[it["requires_flag"]]

    def label(it):
        return {**it, "label": it.get("label_if_paid", it["label"]) if flags["paid_report"] else it["label"]}
    return [{**g, "items": [label(i) for i in g.get("items", []) if keep(i)],
             "foot": [label(i) for i in g.get("foot", []) if keep(i)]} for g in nav]


def footer_for(footer, flags):
    """[[footer]] as this build renders it: a column with requires_flag is dropped while that flag is off
    (6 Nov, SEO round 1: the Learn column waits on [flags] learn_nav)."""
    return [{k: v for k, v in col.items() if k != "requires_flag"}
            for col in footer if not col.get("requires_flag") or flags[col["requires_flag"]]]


def nav_current(nav, page):
    """The label of the nav group the page belongs to: the group listing the page itself, else the
    group whose section is the page's (lifted pages' "section"), else the group whose href starts the path."""
    path = page["path"]
    for g in nav:
        if any(i["href"] == path for i in g["items"] + g["foot"]) or g["href"] == path:
            return g["label"]
    for g in nav:
        if page.get("section") and g["href"] == page.get("section"):
            return g["label"]
    for g in nav:
        if g["href"] != "/" and path.startswith(g["href"]):
            return g["label"]
    return None


def show_seller(cfg):
    """Tester D2: whether this build renders the seller block (legal name, address, phone).
    Always with paid_report; with pilot_checkout alone only if [legal] show_seller_for_pilot."""
    f = cfg["flags"]
    return bool(f["paid_report"] or (f["pilot_checkout"] and cfg["legal"].get("show_seller_for_pilot", False)))


def check_flags(flags, toml_path):
    """D9: every flag is a real TOML boolean. A quoted "false" is a non-empty string, which
    Python reads as true, so it would switch the feature ON: fail instead. Unknown keys (a typo
    such as paid_reprot) fail too, so a flag can't be silently ignored."""
    for k, v in OPTIONAL_FLAGS.items():
        flags.setdefault(k, v)
    for k in sorted(flags):
        if k not in FLAGS:
            die(f"[flags] {k} is not a known flag ({', '.join(FLAGS)}) in {toml_path}")
    for k in FLAGS:
        if k not in flags:
            die(f"[flags] {k} is missing from {toml_path}")
        if type(flags[k]) is not bool:
            die(f"[flags] {k} = {flags[k]!r} must be true or false without quotes (a TOML boolean) in {toml_path}")


# NIT 3 + 4: the shape of site.toml. A missing table or key is a BUILD FAILED line, not a
# KeyError traceback; an unknown key in a closed table (a typo such as show_seller_for_pilt)
# fails instead of being silently ignored. "flags" is checked by check_flags.
SITE_SCHEMA = {
    "site": ({"name", "base_url", "contact_email", "reply_promise"}, None),
    "flags": (set(), None),
    "analytics": ({"cf_beacon_token"}, {"cf_beacon_token", "umami_website_id"}),
    "stripe": ({"mode"}, {"mode", "promo_codes_enabled"}),
    "forms": ({"endpoint", "firm_key", "trader_key", "redirect_firm", "redirect_trader"}, None),
    "worker": ({"api_base"}, {"api_base"}),
    "legal": ({"launch_date", "terms_date", "cloudflare_pages_since", "disclaimer_short", "disclaimer_long"},
              {"launch_date", "terms_date", "cloudflare_pages_since", "disclaimer_short", "disclaimer_long",
               "show_seller_for_pilot", "privacy_date", "refund_effective"}),
}  # table: (required keys, every allowed key or None when the table is open)


def check_schema(cfg, toml_path):
    for table, (required, allowed) in SITE_SCHEMA.items():
        t = cfg.get(table)
        if not isinstance(t, dict):
            die(f"site.toml has no [{table}] table ({toml_path})")
        for k in sorted(required - set(t)):
            die(f"[{table}] {k} is missing from {toml_path}")
        if allowed is not None:
            for k in sorted(set(t) - allowed):
                die(f"[{table}] {k} is not a known key ({', '.join(sorted(allowed))}) in {toml_path}: a typo?")
    for table in ("nav", "footer"):
        if not isinstance(cfg.get(table), list):
            die(f"site.toml has no [[{table}]] entries ({toml_path})")
    why = nav_problem(cfg["nav"])
    if why:
        die(f"{why} ({toml_path})")


# R-D1 D-6: the report method the paid wording accepts, read from the very constant checkMethod() uses, so
# the build cannot state a different one. The paid pages carry it as <meta name="dt-method">, and
# dt-private's scripts/smoke.mjs compares it with the Worker's /health method.
def paid_method():
    src = open(os.path.join(SITE, "static", "js", "paid", "wording.js"), encoding="utf-8").read()
    m = re.findall(r"^export const METHOD_VERSION = '([0-9a-z.-]+)';$", src, re.M)
    if len(m) != 1:
        raise SystemExit("build: site/static/js/paid/wording.js must define METHOD_VERSION exactly once")
    return m[0]


def read_toml(path, label):
    """tomllib.load, but a syntax error is a BUILD FAILED line, not a traceback (Tester NIT 1)."""
    try:
        with open(path, "rb") as f:
            return tomllib.load(f)
    except tomllib.TOMLDecodeError as e:
        die(f"{label} ({path}) is not valid TOML: {e}")


LOCAL_API_RE = re.compile(r"^http://(127\.0\.0\.1|localhost)(:\d{1,5})?$")
_LABEL = r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
# Origin only: https, a lowercase DNS name whose top-level domain is letters or xn-- punycode (so
# no IPv4 or IPv6 literal can match), an optional port, and nothing else: no path, query, space, quote,
# semicolon or other CSP syntax can reach the CSP meta or the dt-api meta.
# NIT 5: the top-level domain is letters, or an IDN TLD in punycode (xn--p1ai); a port has no
# leading zero (:00443 is refused).
_TLD = r"(?:[a-z]{2,63}|xn--[a-z0-9-]{1,59})"
PUBLIC_API_RE = re.compile(rf"https://((?:{_LABEL}\.)+{_TLD})(?::([1-9]\d{{0,4}}))?$")
# Special-use names (RFC 2606, 6761, 6762, 7686, 8375) that are never a public host.
RESERVED_TLDS = {"localhost", "local", "localdomain", "test", "example", "invalid", "internal", "lan", "home",
                 "arpa", "onion", "corp", "intranet", "private"}
RESERVED_DOMAINS = {"example.com", "example.net", "example.org"}


def api_base_problem(api):
    """Why [worker] api_base can't be used in a real paid build, or None."""
    if not isinstance(api, str):
        return "it is not a string"
    m = PUBLIC_API_RE.fullmatch(api)
    if not m:
        return ("it must be exactly https://<public host name>[:port], lowercase, with no path, query, "
                "spaces, quotes, semicolons or IP address")
    host, port = m.group(1), m.group(2)
    labels = host.split(".")
    if labels[-1] in RESERVED_TLDS or ".".join(labels[-2:]) in RESERVED_DOMAINS:
        return f"{host} is a reserved or local name, not a public host"
    if port is not None and not 1 <= int(port) <= 65535:
        return f"port {port} is out of range"
    return None


def check_api_base(api):
    """D12 + D8: the paid pages put [worker] api_base into their CSP connect-src and the dt-api
    meta, so a real paid build needs a public https origin (api_base_problem). A loopback http
    address is allowed only with DT_ALLOW_LOCAL_API=1 (local test builds); that variable allows
    nothing else, and no other variable allows it."""
    why = api_base_problem(api)
    if why is None:
        return
    if isinstance(api, str) and LOCAL_API_RE.fullmatch(api) and escape("DT_ALLOW_LOCAL_API"):
        return
    die(f"paid_report = true but [worker] api_base is {api!r}: {why} "
        "(a loopback http address only with DT_ALLOW_LOCAL_API=1, for local test builds)")


def warn(msg):
    print(f"WARNING: {msg}", file=sys.stderr)


# D10: each local-test escape opens exactly one guard. None of them is needed for a paid build
# with well-formed values, and none is accepted in a [stripe] mode = "live" build.
ESCAPES = {
    "DT_ALLOW_PLACEHOLDERS": "private.toml values that look like placeholders",
    "DT_ALLOW_LOCAL_API": "a loopback http [worker] api_base",
    "DT_ALLOW_NO_STRIPE_LINK": "no Stripe Payment Link for the donttrade test",
}
# Stripe Payment Links: https://buy.stripe.com/<id>; test-mode links carry "test_" (UNVERIFIED
# beyond the links seen so far; a link that differs fails loudly and this pattern is the place to fix).
STRIPE_LINK_RE = {"live": re.compile(r"https://buy\.stripe\.com/(?!test_)[A-Za-z0-9]{8,64}"),
                  "test": re.compile(r"https://buy\.stripe\.com/test_[A-Za-z0-9]{8,64}")}


_warned = set()


def escape(name):
    """True when the local-test escape `name` is set; says so once per build on stderr."""
    on = os.environ.get(name) == "1"
    if on and name not in _warned:
        _warned.add(name)
        warn(f"{name}=1 allows {ESCAPES[name]}: a local test build, not for publishing")
    return on


def check_stripe_link(link, mode, what):
    if not isinstance(link, str) or not STRIPE_LINK_RE[mode].fullmatch(link):
        die(f"{what}: {link!r} is not a Stripe {mode}-mode Payment Link (https://buy.stripe.com/"
            f"{'test_' if mode == 'test' else ''}…)")


MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


_DT_TODAY_NOTED = []


def real_today():
    """The machine's date, never DT_TODAY (the date guards on docs/ compare with this one)."""
    import datetime as dt
    return dt.date.today()


def _today():
    """The build date: today, or DT_TODAY (YYYY-MM-DD) for a build made ahead of a dated push (6 Nov round: the terms
    version is the push day, so a local build before it is made as of that day). A bad value is a one-line BUILD FAILED;
    a value that is not today prints a NOTE on stderr, once. Such a build is for tests and previews: ./site/run.sh bundle
    refuses it (docs/ is never stamped later than the real date unless it is a preview, DT_PREVIEW), and
    checks/docs_date.py fails ./site/run.sh check on a docs/ dated in the future."""
    import datetime as dt
    raw = os.environ.get("DT_TODAY")
    if not raw:
        return dt.date.today()
    try:
        d = dt.date.fromisoformat(raw)
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            raise ValueError(raw)
    except ValueError:
        die(f"DT_TODAY={raw!r} is not a date, YYYY-MM-DD (for example DT_TODAY=2026-11-06)")
    if d != dt.date.today() and not _DT_TODAY_NOTED:
        _DT_TODAY_NOTED.append(1)
        print(f"NOTE: DT_TODAY={raw} is not today ({dt.date.today().isoformat()}): this build is dated ahead. "
              "Use it for tests or a preview only; never bundle or deploy it.", file=sys.stderr)
    return d


def set_launch_date(legal, toml_path, today=None):
    """Manager C3: [legal] launch_date (YYYY-MM-DD; empty = the build date) dates every launch
    statement. Sets legal.terms_version (ISO, the terms/privacy version) and legal.launch_human
    ("23 Oct 2026"). A future date fails: no page may state a date that has not come yet.
    DT_REQUIRE_LAUNCH_DATE=1 (./site/run.sh bundle) refuses an empty one."""
    import datetime as dt
    today = today or _today()
    raw = legal.get("launch_date")
    if not isinstance(raw, str):
        die(f"[legal] launch_date must be a string, YYYY-MM-DD or empty ({toml_path})")
    if raw == "":
        if os.environ.get("DT_REQUIRE_LAUNCH_DATE") == "1":
            die(f"[legal] launch_date is empty: set it to the push day (YYYY-MM-DD) before bundling ({toml_path})")
        d = today
    else:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            die(f"[legal] launch_date {raw!r} is not YYYY-MM-DD ({toml_path})")
        try:
            d = dt.date.fromisoformat(raw)
        except ValueError:
            die(f"[legal] launch_date {raw!r} is not a real date ({toml_path})")
        if d > today:
            die(f"[legal] launch_date {raw} is after the build date {today.isoformat()}: pages would state a "
                f"date that has not come yet ({toml_path})")
    legal["terms_version"] = d.isoformat()
    legal["launch_human"] = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return d


def set_terms_date(legal, toml_path, today=None):
    """29 Oct (one product): [legal] terms_date (YYYY-MM-DD; empty = the build date) is the version of /terms/,
    /fr/conditions/ and (with cloudflare_pages_since) /privacy/, so a later legal edit moves the version without
    moving launch_date, which keeps dating "Pilot (called 'Trial' before <date>)". It must be on or after
    launch_date and not after the build date; DT_REQUIRE_LAUNCH_DATE=1 (./site/run.sh bundle) refuses an empty one.
    Call it after set_launch_date: it replaces legal.terms_version."""
    import datetime as dt
    today = today or _today()
    raw = legal.get("terms_date")
    if not isinstance(raw, str):
        die(f"[legal] terms_date must be a string, YYYY-MM-DD or empty ({toml_path})")
    if raw == "":
        if os.environ.get("DT_REQUIRE_LAUNCH_DATE") == "1":
            die(f"[legal] terms_date is empty: set it to the day of the terms change (YYYY-MM-DD) before bundling ({toml_path})")
        d = today
    else:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            die(f"[legal] terms_date {raw!r} is not YYYY-MM-DD ({toml_path})")
        try:
            d = dt.date.fromisoformat(raw)
        except ValueError:
            die(f"[legal] terms_date {raw!r} is not a real date ({toml_path})")
        if d > today:
            die(f"[legal] terms_date {raw} is after the build date {today.isoformat()}: pages would state a "
                f"date that has not come yet ({toml_path})")
    if legal.get("launch_date") and d.isoformat() < legal["launch_date"]:
        die(f"[legal] terms_date {d.isoformat()} is before launch_date {legal['launch_date']} ({toml_path})")
    legal["terms_version"] = d.isoformat()
    legal["terms_human"] = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    return d


MONTHS_FR = ("janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
             "novembre", "décembre")


def set_hosting_date(legal, toml_path, today=None):
    """T0 (ARCHITECT-SAAS-QUICKWINS §2): [legal] cloudflare_pages_since (YYYY-MM-DD, required, never
    empty) is the day the site moved from GitHub Pages to Cloudflare Pages, stated on /privacy/ and
    /fr/confidentialite/. Sets legal.cloudflare_pages_since_human ("24 Oct 2026") and
    legal.cloudflare_pages_since_fr ("24 octobre 2026"). A future date fails, as for launch_date.
    Also sets legal.privacy_version, the version of /privacy/ and /fr/confidentialite/: the later of the
    terms version (launch_date) and this date, because the hosting sentence changed the privacy notice
    only (the terms keep launch_date). Call it after set_launch_date."""
    import datetime as dt
    today = today or _today()
    raw = legal.get("cloudflare_pages_since")
    if not isinstance(raw, str) or raw == "":
        die(f"[legal] cloudflare_pages_since must be the day the site moved to Cloudflare Pages, YYYY-MM-DD, "
            f"not empty ({toml_path})")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        die(f"[legal] cloudflare_pages_since {raw!r} is not YYYY-MM-DD ({toml_path})")
    try:
        d = dt.date.fromisoformat(raw)
    except ValueError:
        die(f"[legal] cloudflare_pages_since {raw!r} is not a real date ({toml_path})")
    if d > today:
        die(f"[legal] cloudflare_pages_since {raw} is after the build date {today.isoformat()}: the privacy "
            f"pages would state a date that has not come yet ({toml_path})")
    legal["cloudflare_pages_since_human"] = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    legal["cloudflare_pages_since_fr"] = f"{d.day} {MONTHS_FR[d.month - 1]} {d.year}"
    legal["privacy_version"] = max(legal["terms_version"], d.isoformat())
    return d


def set_privacy_date(legal, toml_path, today=None):
    """2 Nov (Umami Cloud named on /privacy/): optional [legal] privacy_date, YYYY-MM-DD, the day of the latest
    edit to the privacy notice alone (/privacy/, /fr/confidentialite/). Like cloudflare_pages_since it moves only
    legal.privacy_version (the later of the two and the terms version), never the terms. A future date fails.
    Call it after set_hosting_date."""
    import datetime as dt
    today = today or _today()
    raw = legal.get("privacy_date", "")
    if raw == "":
        return None
    if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
        die(f"[legal] privacy_date {raw!r} is not YYYY-MM-DD ({toml_path})")
    try:
        d = dt.date.fromisoformat(raw)
    except ValueError:
        die(f"[legal] privacy_date {raw!r} is not a real date ({toml_path})")
    if d > today:
        die(f"[legal] privacy_date {raw} is after the build date {today.isoformat()}: the privacy pages would "
            f"state a version that has not come yet ({toml_path})")
    legal["privacy_version"] = max(legal["privacy_version"], d.isoformat())
    return d


PARTNER_SLUG_RE = re.compile(r"[a-z0-9-]{2,30}")
PARTNER_CODE_RE = re.compile(r"[A-Z0-9]{3,20}")
PARTNER_NAME_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 .&'’-]{0,58}[A-Za-z0-9.]")
INDEXNOW_KEY_RE = re.compile(r"[A-Za-z0-9-]{8,128}")
COUNTRY_RE = re.compile(r"[A-Z]{2}")


def apply_founding(prices, toml_path):
    """6 Nov (Round A1): the founding price is config. prices.json keeps report39 price_usd = the founding price and
    holds the next price in report39.after_founding; rules.founding_open says which one is current. Every template
    reads products.report39.price_usd, so with founding_open = false the build swaps in the next price and its links
    in memory (the file itself is edited only to flip the switch). Adds founding_price_usd and after_price_usd to
    the product for the one macro that words both (partials/price_line.html). Returns founding_open."""
    rules = prices["rules"]
    r = next(p for p in prices["products"] if p["id"] == "report39")
    open_ = rules.get("founding_open")
    if type(open_) is not bool:
        die("prices.json rules.founding_open must be true or false without quotes")
    af = r.get("after_founding")
    if not isinstance(af, dict) or type(af.get("price_usd")) not in (int, float) or isinstance(af.get("price_usd"), bool):
        die("prices.json report39.after_founding.price_usd (the price after the first founding buyers) is missing")
    if af["price_usd"] <= r["price_usd"]:
        die(f"prices.json: the price after the founding price ({af['price_usd']}) must be higher than {r['price_usd']}")
    r["founding_price_usd"], r["after_price_usd"] = r["price_usd"], af["price_usd"]
    for m in ("live", "test"):
        for suf in ("", "_fr"):
            link = af.get(f"stripe_link_{m}{suf}")
            if link:
                check_stripe_link(link, m, f"prices.json report39.after_founding.stripe_link_{m}{suf}")
    if not open_:
        for m in ("live", "test"):
            for suf in ("", "_fr"):
                r[f"stripe_link_{m}{suf}"] = af.get(f"stripe_link_{m}{suf}")
        r["price_usd"], r["founding"] = af["price_usd"], False
    return open_


def load_partners(cfg, toml_path):
    """6 Nov (Round A6): site/config/partners.json (DT_PARTNERS_JSON for tests), {slug: {code, name, active}}.
    Public by design. The slug is what a partner link carries (?via=<slug>); pay.js looks it up in the active entries
    only. A non-empty file needs [stripe] promo_codes_enabled = true, the owner's tick that the Payment Link takes
    promotion codes (a code Stripe ignores would promise a discount the buyer never gets)."""
    path = os.environ.get("DT_PARTNERS_JSON") or os.path.join(SITE, "config", "partners.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        die(f"{path}: partners.json must be an object, {{slug: {{code, name, active}}}}")
    codes = set()
    for slug, e in data.items():
        if not PARTNER_SLUG_RE.fullmatch(slug):
            die(f"partners.json: slug {slug!r} must be 2 to 30 of a-z, 0-9 and -")
        if not isinstance(e, dict) or set(e) != {"code", "name", "active"}:
            die(f"partners.json: {slug} must hold exactly code, name and active")
        if not isinstance(e["code"], str) or not PARTNER_CODE_RE.fullmatch(e["code"]):
            die(f"partners.json: {slug} code must be 3 to 20 of A-Z and 0-9")
        if not isinstance(e["name"], str) or not PARTNER_NAME_RE.fullmatch(e["name"]):
            die(f"partners.json: {slug} name must be 2 to 60 letters, digits, spaces and . & ' -")
        if type(e["active"]) is not bool:
            die(f"partners.json: {slug} active must be true or false")
        if e["code"] in codes:
            die(f"partners.json: code {e['code']} is used twice")
        codes.add(e["code"])
    if data and cfg["stripe"].get("promo_codes_enabled") is not True:
        die("partners.json lists partners but [stripe] promo_codes_enabled is not true: switch on Allow promotion codes "
            "on the Payment Link first, then set it (a code Stripe ignores promises a discount the buyer never gets)")
    return data


def check_round_a_settings(cfg, toml_path):
    """6 Nov (Round A): the small site.toml settings of the codes/pricing/refund round."""
    import datetime as dt
    site, legal, flags = cfg["site"], cfg["legal"], cfg["flags"]
    mc = site.setdefault("merchant_countries", ["CA", "US"])
    if (not isinstance(mc, list) or not mc or len(set(mc)) != len(mc)
            or any(not isinstance(c, str) or not COUNTRY_RE.fullmatch(c) for c in mc)):
        die(f"[site] merchant_countries must be a list of unique two-letter country codes, like [\"CA\", \"US\"] ({toml_path})")
    pc = cfg["stripe"].get("promo_codes_enabled", False)
    if type(pc) is not bool:
        die(f"[stripe] promo_codes_enabled must be true or false ({toml_path})")
    cfg["stripe"]["promo_codes_enabled"] = pc
    ix = cfg.get("indexnow")
    if ix is not None:
        if not isinstance(ix, dict) or set(ix) - {"key"} or not isinstance(ix.get("key"), str) or not INDEXNOW_KEY_RE.fullmatch(ix["key"]):
            die(f"[indexnow] key must be 8 to 128 of letters, digits and - ({toml_path})")
    # the refund policy switch: "No result, no charge" is worded on the site only while the owner has changed the
    # Stripe checkout text to match, so it needs its own effective date and a terms version no older than it
    raw = legal.get("refund_effective", "")
    legal["refund_effective_human"] = legal["refund_effective_fr"] = ""
    if flags["refund_no_result"]:
        if not flags["paid_report"]:
            die(f"[flags] refund_no_result = true needs paid_report = true ({toml_path})")
        if not isinstance(raw, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", raw):
            die(f"[flags] refund_no_result = true needs [legal] refund_effective = \"YYYY-MM-DD\", the day the new refund "
                f"terms and Stripe's checkout text go live ({toml_path})")
        try:
            d = dt.date.fromisoformat(raw)
        except ValueError:
            die(f"[legal] refund_effective {raw!r} is not a real date ({toml_path})")
        if d > _today():
            die(f"[legal] refund_effective {raw} is after the build date {_today().isoformat()} ({toml_path})")
        if legal["terms_version"] < raw:
            die(f"[legal] terms_date {legal['terms_version']} is before refund_effective {raw}: the refund wording is a "
                f"legal change, so the terms version must be that day or later ({toml_path})")
        legal["refund_effective_human"] = f"{d.day} {MONTHS[d.month - 1]} {d.year}"
        legal["refund_effective_fr"] = f"{d.day} {MONTHS_FR[d.month - 1]} {d.year}"
    elif raw:
        die(f"[legal] refund_effective is set but [flags] refund_no_result is off: remove the date or turn the flag on ({toml_path})")


CHANNEL_HOSTS = {"x.com", "github.com", "donttrade.substack.com", "www.linkedin.com", "www.tiktok.com", "www.youtube.com",
                 "www.instagram.com", "bsky.app", "www.threads.com", "mastodon.social"}
CHANNEL_FIELDS = ("id", "name", "url", "text", "icon", "rel_me")
BRAND_ICONS = ("x", "github", "substack", "tiktok", "instagram", "youtube", "bluesky", "threads", "mastodon")


def load_channels(cfg, toml_path):
    """ARCHITECT-BRAND §2.6: site.toml [[channels]] is the one list of official accounts."""
    if "same_as" in cfg["site"]:
        die(f"[site] same_as is replaced by [[channels]] ({toml_path})")
    chans = cfg.get("channels") or []
    if not chans:
        die(f"site.toml has no [[channels]] entries ({toml_path})")
    for c in chans:
        for f in CHANNEL_FIELDS:
            if f not in c:
                die(f"[[channels]] {c.get('id', '?')}: missing {f} ({toml_path})")
        for k, v in c.items():
            if isinstance(v, str):
                why = placeholder_reason(v)
                if why:
                    die(f"[[channels]] {c['id']}.{k}: {why} ({toml_path})")
        m = re.fullmatch(r"https://([^/]+)(/[^\s]*)?", c["url"])
        if not m:
            die(f"[[channels]] {c['id']}: url must be https:// ({c['url']!r})")
        if m.group(1) not in CHANNEL_HOSTS:
            die(f"[[channels]] {c['id']}: host {m.group(1)!r} is not an allowed channel host")
        if c["icon"] not in BRAND_ICONS:
            die(f"[[channels]] {c['id']}: icon {c['icon']!r} is not in partials/icons.html BRAND")
    return chans


def load_config():
    toml_path = os.environ.get("DT_SITE_TOML") or os.path.join(SITE, "config", "site.toml")
    cfg = read_toml(toml_path, "site.toml")
    # DT_PRICES_JSON: another prices file (test builds plant a well-formed test link this way,
    # instead of editing the committed one). It is an input, not an escape: every check applies.
    prices_path = os.environ.get("DT_PRICES_JSON") or os.path.join(SITE, "config", "prices.json")
    with open(prices_path, encoding="utf-8") as f:
        prices = json.load(f)
    check_schema(cfg, toml_path)
    load_channels(cfg, toml_path)
    set_launch_date(cfg["legal"], toml_path)
    set_terms_date(cfg["legal"], toml_path)
    set_hosting_date(cfg["legal"], toml_path)
    set_privacy_date(cfg["legal"], toml_path)
    mu = cfg["site"].get("mastodon_url", "")
    if not isinstance(mu, str) or (mu and not re.fullmatch(r"https://[a-z0-9.-]+/@[A-Za-z0-9_]+", mu)):
        die(f"[site] mastodon_url {mu!r} must be empty or https://<server>/@<name> ({toml_path})")
    cfg["site"].setdefault("manual_restore", True)
    if type(cfg["site"]["manual_restore"]) is not bool:
        die(f"[site] manual_restore must be true or false, not {cfg['site']['manual_restore']!r} ({toml_path})")
    flags = cfg["flags"]
    check_flags(flags, toml_path)
    check_round_a_settings(cfg, toml_path)
    if flags["trader_first_home"] != flags["paid_report"]:
        die(f"flag mismatch: trader_first_home={flags['trader_first_home']} must equal "
            f"paid_report={flags['paid_report']} ({toml_path})")
    if flags["analytics"] and not cfg["analytics"]["cf_beacon_token"]:
        die("analytics = true but [analytics] cf_beacon_token is empty")
    uid = cfg["analytics"].get("umami_website_id", "")
    if not isinstance(uid, str) or (uid and not UMAMI_ID_RE.fullmatch(uid)):
        die(f"[analytics] umami_website_id {uid!r} must be empty or an Umami website ID (a UUID) ({toml_path})")
    mode = cfg["stripe"]["mode"]
    if mode not in ("test", "live"):
        die(f"[stripe] mode must be test or live, not {mode!r}")
    if mode == "live":
        for name in ESCAPES:
            if os.environ.get(name) == "1":
                die(f"{name}=1 is for local test builds only; [stripe] mode = \"live\" refuses it")
    seller_switch = cfg["legal"].get("show_seller_for_pilot", False)
    if type(seller_switch) is not bool:
        die(f"[legal] show_seller_for_pilot = {seller_switch!r} must be true or false without quotes")
    private = {}
    on = [f for f in COMMERCE_FLAGS if flags[f]]
    if on:
        # Seller disclosure (O. Reg. 17/05 s. 32): legal name, premises address, phone. These come
        # ONLY from the gitignored private.toml, read ONLY while a commerce flag is on.
        p = os.environ.get("DT_PRIVATE_TOML") or os.path.join(SITE, "config", "private.toml")
        if not os.path.exists(p):
            die(f"{', '.join(on)} = true needs site/config/private.toml (copy private.example.toml)")
        private = check_private(read_toml(p, "private.toml"), on)
    if flags["paid_report"]:
        check_api_base(cfg["worker"]["api_base"])
    apply_founding(prices, toml_path)
    cfg["partners"] = load_partners(cfg, toml_path)
    products = {p["id"]: p for p in prices["products"]}
    if flags["pilot_checkout"]:
        if not products["pilot"]["stripe_link_live"]:
            die("pilot_checkout = true but prices.json has no stripe_link_live for the pilot")
        check_stripe_link(products["pilot"]["stripe_link_live"], "live", "prices.json pilot stripe_link_live")
    if flags["paid_report"]:
        link = products["report39"]["stripe_link_" + mode]
        if link:
            check_stripe_link(link, mode, f"prices.json report39 stripe_link_{mode}")
        elif not escape("DT_ALLOW_NO_STRIPE_LINK"):
            die(f"paid_report = true but prices.json has no stripe_link_{mode} for report39 "
                "(DT_ALLOW_NO_STRIPE_LINK=1 for a local test build only)")
        # C-14 (G16): a separate French Payment Link (its custom text is French). Optional: without one,
        # /fr/avant-de-payer/ uses the English link with ?locale=fr (report_link_fr).
        for m in ("live", "test"):
            fr = products["report39"].get(f"stripe_link_{m}_fr")
            if fr is not None:
                check_stripe_link(fr, m, f"prices.json report39 stripe_link_{m}_fr")
    return cfg, prices, private


def report_link_fr(product, mode):
    """The /fr/avant-de-payer/ pay link: stripe_link_<mode>_fr when set, else the English link with
    locale=fr (a documented Payment Link URL parameter: docs.stripe.com/payment-links/customize, read
    23 Oct 2026), else None (no link in this mode)."""
    fr = product.get(f"stripe_link_{mode}_fr")
    if fr:
        return fr
    en = product.get(f"stripe_link_{mode}")
    if not en:
        return None
    return en + ("&" if "?" in en else "?") + "locale=fr"


def pay_ref(path):
    """2 Nov (sale attribution): the page's slug as Stripe's client_reference_id, so the payment records which page
    the buyer paid from. "/" is home, "/tools/trade-stats/" tools-trade-stats. Stripe allows letters, digits, "-"
    and "_", up to 200 characters; nothing personal goes in it."""
    slug = path.strip("/").replace("/", "-") or "home"
    return re.sub(r"[^A-Za-z0-9_-]", "-", slug)[:200]


def with_client_ref(link, path):
    """The Payment Link with ?client_reference_id=<pay_ref(path)> (a Payment Link URL parameter), or None."""
    if not link:
        return link
    return link + ("&" if "?" in link else "?") + "client_reference_id=" + pay_ref(path)


def lift_sections(rel_path):
    """{id: html} for each <h2 id=...> section of an old docs/ page's <main>, verbatim.

    A section runs from its <h2 id> to the next <h2 id> (or the end of <main>). Key
    "_intro" holds what comes before the first one."""
    with open(os.path.join(DOCS, rel_path), encoding="utf-8") as f:
        html = f.read()
    m = re.search(r"(?s)<main[^>]*>(.*)</main>", html)
    if not m:
        die(f"lift: no <main> in docs/{rel_path}")
    main = m.group(1)
    cuts = [(mm.start(), mm.group(1)) for mm in re.finditer(r'<h2[^>]*\sid="([^"]+)"', main)]
    out = {"_intro": main[: cuts[0][0]] if cuts else main}
    for k, (start, sid) in enumerate(cuts):
        end = cuts[k + 1][0] if k + 1 < len(cuts) else len(main)
        out[sid] = main[start:end]
    return out


NUMWORDS = ("zero", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine")


NUMWORDS_FR = ("zéro", "un", "deux", "trois", "quatre", "cinq", "six", "sept", "huit", "neuf")


def numword_fr(n):
    """4 -> "quatre" (0 to 9)."""
    if type(n) is not int or not 0 <= n <= 9:
        die(f"numword_fr: {n!r} is not a whole number from 0 to 9")
    return NUMWORDS_FR[n]


def numword(n):
    """5 -> "five" (rules.habits_measured / habits_tested are written once, in prices.json, and spelled out on the pages)."""
    if type(n) is not int or not 0 <= n <= 9:
        die(f"numword: {n!r} is not a whole number from 0 to 9")
    return NUMWORDS[n]


def longdate(iso):
    """"2027-01-31" -> "31 January 2027"."""
    import datetime as dt
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B')} {d.year}"


IMPORTERS_JSON = os.path.join(SITE, "config", "importers.json")


def readers_untested():
    """[reader name] of the broker file readers not yet tested on a real export, from site/config/importers.json (a
    reader is untested while any of its formats has verified = false). Fix round 2: the beta-removal sentence says exactly
    this, so it changes when a format flips."""
    with open(IMPORTERS_JSON, encoding="utf-8") as f:
        fm = json.load(f)["formats"]
    names, out = [], []
    for x in fm:
        if x.get("reader") and x["reader"] not in names:
            names.append(x["reader"])
    return [n for n in names if any(not x["verified"] for x in fm if x.get("reader") == n)], names


def partners_meta(partners, prices):
    """The <meta name="dt-partners"> content for pay.js: the active partners only, as compact JSON, or "" (no tag).
    {"d": percent off, "p": {slug: [code, name]}}. Public by design; pay.js never reads a code from the URL."""
    active = {k: [v["code"], v["name"]] for k, v in sorted(partners.items()) if v["active"]}
    if not active:
        return ""
    return json.dumps({"d": prices["partner"]["discount_percent"], "p": active}, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"))


REFUND_REASONS_JSON = os.path.join(SITE, "config", "refund_reasons.json")


def refund_reasons():
    """site/config/refund_reasons.json: the nine reasons on /refund/ (slug, EN and FR label, class). The radios, the
    refund.js whitelist (a test holds them equal) and the Worker repo's summary script read this one list."""
    with open(REFUND_REASONS_JSON, encoding="utf-8") as f:
        data = json.load(f)
    slugs = [e["slug"] for e in data["reasons"]]
    if len(set(slugs)) != len(slugs) or any(not re.fullmatch(r"[a-z]+(?:-[a-z]+)*", x) for x in slugs):
        die("refund_reasons.json: slugs must be unique, lower case, words joined by -")
    for e in data["reasons"]:
        if set(e) != {"slug", "en", "fr", "class"} or e["class"] not in ("eligible", "check", "goodwill", "review"):
            die(f"refund_reasons.json: {e.get('slug')} needs exactly slug, en, fr and a known class")
    return data["reasons"]


def _cents(n):
    """A price in whole cents, or a build failure (29 Oct: the firm plan is $0.50 per trader account)."""
    c = round(n * 100)
    if abs(n * 100 - c) > 1e-6:
        die(f"price {n} is not a whole number of cents")
    return c


def usd(n):
    """$745, $2,500 — whole dollars without cents; $0.50 — a price with cents keeps both digits."""
    c = _cents(n)
    if c % 100 == 0:
        return "${:,}".format(c // 100)
    return "${:,}.{:02d}".format(c // 100, c % 100)


def isodate(human):
    """"23 Oct 2026" -> "2026-10-23" (the price-history rows are written in the human form)."""
    import datetime as dt
    return dt.datetime.strptime(human, "%d %b %Y").date().isoformat()


def usd_fr(n):
    """39,00 $ US — Québec style (FRENCH-LEGAL: amounts written « 79,00 $ US »); 0,50 $ US."""
    c = _cents(n)
    return "{:,}".format(c // 100).replace(",", "\u00a0") + ",{:02d}\u00a0$\u00a0US".format(c % 100)


BEACON_CONNECT = "https://cloudflareinsights.com"   # the analytics beacon's one connect-src host
BEACON_SCRIPT = "https://static.cloudflareinsights.com"
# Umami Cloud (2 Nov): the script's host and its one connect host (it posts to <host>/api/send), only with
# [analytics] umami_website_id set, on the pages that get the beacon.
UMAMI_SCRIPT = "https://cloud.umami.is"
UMAMI_CONNECT = "https://gateway.umami.is"
UMAMI_ID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def umami_on(cfg):
    return bool(cfg["flags"]["analytics"] and cfg["analytics"].get("umami_website_id"))


# Hardening plan item 7 (3 Nov): campaign tags. Umami keeps data-exclude-search="true" (the whole query dropped by
# the tracker itself, before any hook) on the pages whose address can carry a secret or typed text: /welcome/
# (?session_id=), /restore/, /help/ (the no-JavaScript ask form sends ?q=<typed question>) and every noindex page.
# Everywhere else the data-before-send hook static/js/umami-clean.js keeps only utm_source, utm_medium,
# utm_campaign and utm_content (short lowercase values) and drops the rest. checks/lint.py enforces the same set.
UMAMI_STRICT_PATHS = ("/welcome/", "/restore/", "/help/")
UMAMI_CLEAN_JS = "/static/js/umami-clean.js"


def umami_strict(page):
    return bool(page.get("noindex")) or page["path"] in UMAMI_STRICT_PATHS


def analytics_hosts(cfg, page=None):
    """(script-src hosts, connect-src hosts) that a page with analytics adds to its CSP. Umami's two hosts only
    with Umami on and never on a no_umami page (/report/)."""
    script, connect = [BEACON_SCRIPT], [BEACON_CONNECT]
    if umami_on(cfg) and not (page or {}).get("no_umami"):
        script.append(UMAMI_SCRIPT)
        connect.append(UMAMI_CONNECT)
    return script, connect


def csp_for(page, cfg):
    if os.path.join(page["path"].strip("/"), "index.html") in PASSTHROUGH_CSP_PAGES:
        # Manager C4 after the merge of steps 28–29: the lifted old calculators keep the strict
        # no-network policy they had as passthrough pages (connect, worker and form-action 'none'),
        # now without 'unsafe-inline'. With analytics on, the beacon host is the only addition,
        # as on every other tool page (plan DoD: "connect-src 'none' (or the beacon host only)").
        # 29 Oct: 'none' may not stand beside a host (CSP3; the browser ignores it and logs a console error on
        # every page), so with the beacon the directive is the beacon host alone, which is the same policy.
        a = cfg["flags"]["analytics"]
        sh, ch = analytics_hosts(cfg)
        return ("default-src 'self'; script-src 'self'" + ("".join(" " + h for h in sh) if a else "") +
                "; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src " +
                (" ".join(ch) if a else "'none'") +
                "; worker-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'")
    connect = page.get("connect_src", "'none'")
    if page.get("connect_worker"):
        connect = "'self' " + cfg["worker"]["api_base"]
    beacon = cfg["flags"]["analytics"] and not page.get("no_analytics")   # D12: never on the journal
    sh, ch = analytics_hosts(cfg, page)
    if beacon:   # never "'none' <host>": the browser ignores 'none' there and logs an error (CSP3)
        connect = " ".join(ch) if connect == "'none'" else connect + " " + " ".join(ch)
    script = "'self'" + ("".join(" " + h for h in sh) if beacon else "")
    forms = ("'none'" if page.get("no_forms") else
             "'self' https://api.web3forms.com" + "".join(" " + a for a in page.get("form_action", [])))
    return ("default-src 'self'; script-src " + script + "; style-src 'self'; img-src 'self' data:; "
            "font-src 'self'; connect-src " + connect + "; worker-src 'self'; "
            "form-action " + forms + "; base-uri 'none'; object-src 'none'")


# ------------------------------------------------------------------ SEO (SEO-PLAN §3)
def _text(fragment):
    import html as _h
    t = re.sub(r"<[^>]+>", " ", fragment)
    return re.sub(r"\s+", " ", _h.unescape(t)).strip()


def faq_from(html):
    """[(question, answer)] from the rendered FAQ section (the <section> labelled by #faq-h).

    Read from the page itself, so the FAQPage JSON-LD matches the visible text word for word."""
    m = re.search(r'(?s)<section[^>]*aria-labelledby="faq-h"[^>]*>(.*?)</section>', html)
    if not m:
        return []
    return [(_text(q), _text(a)) for q, a in
            re.findall(r"(?s)<details[^>]*>\s*<summary>(.*?)</summary>(.*?)</details>", m.group(1))]


def crumb_items(page):
    """Home > [parent] > this page, as (name, path or None). The JSON-LD BreadcrumbList and the visible
    breadcrumb (partials/crumbs.html, owner-approved Home link (c), NN/g "Homepage links") share it."""
    items = [("Home", "/")]
    if page.get("parent"):
        items.append((page["parent"][0], page["parent"][1]))
    elif page["path"].startswith("/tools/") and page["path"] != "/tools/":
        items.append(("Free tools", "/tools/"))
    items.append((page["crumb"], None))
    return items


PRODUCT_IMAGE = "/assets/product/donttrade-test-1200.png"     # the square product picture, when it exists
PRODUCT_IMAGE_FALLBACK = "/assets/og/pricing.png"            # 1200x630: validates, not ideal


def product_jsonld(page, cfg, r, org):
    """Round A4 (Google Merchant "invalid Product"): name, description, image, brand, sku, one Offer with price,
    currency, availability, item condition, url and digital shipping details (free, no delay) for each country in
    [site] merchant_countries. NOT here, on purpose: aggregateRating, review, priceValidUntil (lint holds all three
    out), and any hasMerchantReturnPolicy. Addendum 2.7 (6 Nov): the plan's FullRefund / 14 days block said "full
    refund" with no condition, which "No result, no charge" is not, so the markup carries no return policy at all.
    Price = the current price (the founding price while it is open, then the next one)."""
    base = cfg["site"]["base_url"]
    image = PRODUCT_IMAGE if os.path.exists(os.path.join(DOCS, PRODUCT_IMAGE.lstrip("/"))) else PRODUCT_IMAGE_FALLBACK
    if not os.path.exists(os.path.join(DOCS, image.lstrip("/"))):
        die(f"Product JSON-LD: the image {image} is missing from docs/")
    regions = [{"@type": "DefinedRegion", "addressCountry": c} for c in cfg["site"]["merchant_countries"]]
    zero = {"@type": "QuantitativeValue", "minValue": 0, "maxValue": 0, "unitCode": "DAY"}
    return {"@type": "Product", "@id": base + page["path"] + "#product", "name": r["name"],
            "description": page["product"], "image": [base + image], "brand": org, "sku": "donttrade-test",
            "offers": {"@type": "Offer", "price": str(int(r["price_usd"])), "priceCurrency": "USD",
                       "availability": "https://schema.org/InStock", "url": base + page["path"],
                       "itemCondition": "https://schema.org/NewCondition",
                       "shippingDetails": {"@type": "OfferShippingDetails",
                                           "shippingRate": {"@type": "MonetaryAmount", "value": "0", "currency": "USD"},
                                           "shippingDestination": regions,
                                           "deliveryTime": {"@type": "ShippingDeliveryTime", "handlingTime": zero,
                                                            "transitTime": dict(zero)}}}}


def doi_url(doi):
    return "https://doi.org/" + doi


def scholarly_ref(r):
    """A cited work as a ScholarlyArticle: only what references.json (Crossref-checked) holds."""
    return {"@type": "ScholarlyArticle", "name": r["title"], "datePublished": str(r["year"]),
            "isPartOf": {"@type": "Periodical", "name": r["journal"]}, "sameAs": doi_url(r["doi"]),
            "identifier": {"@type": "PropertyValue", "propertyID": "DOI", "value": r["doi"]}}


def dataset_nodes(page, base, org, items):
    """Dataset JSON-LD for each CSV a page offers (items: dicts with name, csv, description)."""
    return [{"@type": "Dataset", "@id": base + page["path"] + f"#dataset-{i + 1}", "name": d["name"],
             "description": d["description"], "license": LEARN_LICENSE, "creator": org, "isAccessibleForFree": True,
             "isPartOf": {"@id": base + page["path"] + "#article"}, "url": base + page["path"],
             "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": base + d["csv"]}]}
            for i, d in enumerate(items)]


def study_article(page, base, org, st, refs):
    """The study's old Article, now also a ScholarlyArticle with its DOI (identifier and sameAs), the dataset it
    rests on (isBasedOn) and the works it cites; the Article's own fields (dates, licence, image) are kept."""
    node = {**page["article"], "@id": base + page["path"] + "#article", "@type": ["Article", "ScholarlyArticle"],
            "name": st["title"], "author": org, "publisher": org,
            "identifier": {"@type": "PropertyValue", "propertyID": "DOI", "value": st["doi"]}, "sameAs": doi_url(st["doi"])}
    if st["based_on"]:
        node["isBasedOn"] = [{"@type": "Dataset", "name": d["name"], "sameAs": doi_url(d["doi"]), "license": d["license"],
                              "publisher": {"@type": "Organization", "name": d["publisher"]}} for d in st["based_on"]]
    if st["cites"]:
        node["citation"] = [scholarly_ref(refs[k]) for k in st["cites"]]
    return node


def selloff_nodes(page, base, org):
    """Article + ScholarlyArticle and Dataset for the sell-off study. No identifier/DOI until Zenodo mints one (then the study moves
    to config/studies.json and study_article takes over). The Dataset is our aggregate of Ironflow's CC BY 4.0 data: licence CC BY 4.0,
    isBasedOn the two source datasets, the CSV as its distribution."""
    sell = selloff_ctx()
    src = sell["source"]
    refs = references()
    url = base + page["path"]
    based = [{"@type": "Dataset", "name": n, "url": u, "license": src["licence_url"], "creator": {"@type": "Organization", "name": "Ironflow", "url": "https://ironflow.sh"}}
             for n, u in (("Hyperliquid Trades", src["trades_url"]), ("Hyperliquid Liquidations", src["liquidations_url"]))]
    art = {"@type": ["Article", "ScholarlyArticle"], "@id": url + "#article", "headline": page["h1"], "name": page["h1"],
           "description": page["description"], "datePublished": page["published"], "dateModified": page["updated"],
           "author": org, "publisher": org, "isAccessibleForFree": True, "license": LEARN_LICENSE, "image": base + page["og_image"],
           "mainEntityOfPage": url, "url": url, "isBasedOn": based, "citation": [scholarly_ref(refs[k]) for k in SELLOFF_REFS]}
    ds = {"@type": "Dataset", "@id": url + "#dataset-1",
          "name": "Hyperliquid forced closes, 6 October to 5 November 2026: daily counts",
          "description": "Daily counts of force-closed (liquidated) Hyperliquid perpetual-futures wallets, the value force-closed, and the share that placed a "
                         "new market order within 15 and 60 minutes, for the 31 UTC days 2026-10-06 to 2026-11-05. Aggregated from Ironflow's CC BY 4.0 data; no wallet address.",
          "license": src["licence_url"], "creator": org, "isAccessibleForFree": True, "temporalCoverage": "2026-10-06/2026-11-05",
          "isBasedOn": based, "isPartOf": {"@id": url + "#article"}, "url": url,
          "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": base + SO.CSV_PATH}]}
    ds2 = {"@type": "Dataset", "@id": url + "#dataset-2",
           "name": "Hyperliquid forced closes, 6 October to 5 November 2026: market by market",
           "description": "For each UTC day 2026-10-06 to 2026-11-05 and each perpetual market with 10 or more force-closed wallets: wallets "
                          "force-closed, value force-closed, fills and the long share, with day totals for reconciliation. Descriptive, added after "
                          "the analysis plan. Aggregated from Ironflow's CC BY 4.0 data; no wallet address.",
           "license": src["licence_url"], "creator": org, "isAccessibleForFree": True, "temporalCoverage": "2026-10-06/2026-11-05",
           "isBasedOn": based, "isPartOf": {"@id": url + "#article"}, "url": url + "#sell-pm-h",
           "distribution": [{"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": base + SO.PM_CSV_PATH}]}
    return [art, ds, ds2]


GLOSS_DT = re.compile(r'(?s)<dt id="([^"]+)"><dfn>(.*?)</dfn></dt><dd>(.*?)</dd>')


def glossary_graph(base, html):
    """DefinedTermSet for /glossary/: one DefinedTerm per <dt id> on the page (the frozen twelve and the added ones),
    its definition the <dd> text without the "Source:" line, so the data cannot drift from the visible text."""
    terms = []
    for tid, name, dd in GLOSS_DT.findall(html):
        dd = re.sub(r'(?s)<span class="(?:src|meas)">.*?</span>', "", dd)
        terms.append({"@type": "DefinedTerm", "@id": base + "/glossary/#" + tid, "name": _text(name), "description": _text(dd),
                      "url": base + "/glossary/#" + tid, "inDefinedTermSet": {"@id": base + "/glossary/#set"}})
    return [{"@type": "DefinedTermSet", "@id": base + "/glossary/#set", "name": "donttrade glossary",
             "url": base + "/glossary/", "hasDefinedTerm": [{"@id": t["@id"]} for t in terms]}] + terms


def jsonld(page, cfg, html, flags, products):
    """One @graph per page. No address, phone, rating or review anywhere (SEO-PLAN §3.2)."""
    base = cfg["site"]["base_url"]
    org = {"@id": base + "/#org"}
    graph = []
    if page["path"] == "/":
        graph.append({"@type": "WebSite", "@id": base + "/#website", "name": cfg["site"]["name"],
                      "url": base + "/", "publisher": org})
        graph.append({"@type": "Organization", "@id": base + "/#org", "name": cfg["site"]["name"],
                      "url": base + "/", "email": cfg["site"]["contact_email"], "sameAs": [c["url"] for c in cfg["channels"]],
                      "description": ABOUT_LINE,
                      "logo": {"@type": "ImageObject", "url": base + ORG_LOGO, "width": 512, "height": 512}})
    else:
        items = [(n, base + u if u else None) for n, u in crumb_items(page)]
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, **({"item": u} if u else {})}
            for i, (n, u) in enumerate(items)]})
    st = studies().get(page["path"])
    if page.get("article") and st:   # the four studies with a DOI (6 Nov, SEO round 1): Article + ScholarlyArticle
        graph.append(study_article(page, base, org, st, references()))
        graph += dataset_nodes(page, base, org, st["datasets"])
    elif page.get("selloff"):   # the sell-off study: Article + ScholarlyArticle (no DOI yet) and the Dataset of its CSV, CC BY 4.0 data credited
        graph += selloff_nodes(page, base, org)
    elif page.get("article"):  # lifted study pages: their old Article, by the site Organization
        graph.append({**page["article"], "author": org, "publisher": org})
    if page.get("learn"):
        lp = page["learn"]
        if lp["kind"] == "hub":
            graph.append({"@type": "CollectionPage", "@id": base + page["path"] + "#page", "name": page["h1"],
                          "description": page["description"], "url": base + page["path"], "isPartOf": {"@id": base + "/#website"},
                          "publisher": org})
            graph.append({"@type": "ItemList", "itemListElement": [
                {"@type": "ListItem", "position": i + 1, "name": pg["crumb"], "url": base + pg["path"]}
                for i, pg in enumerate(p for p in PAGES if p["path"].startswith("/learn/") and p["path"] != "/learn/")]})
        else:
            refs = references()
            art = {"@type": "Article", "@id": base + page["path"] + "#article", "headline": page["h1"],
                   "description": page["description"], "datePublished": lp["published"], "dateModified": page["updated"],
                   "author": org, "publisher": org, "isAccessibleForFree": True, "license": LEARN_LICENSE,
                   "image": base + page["og_image"], "mainEntityOfPage": base + page["path"], "url": base + page["path"]}
            if lp["refs"]:
                art["citation"] = [scholarly_ref(refs[k]) for k in lp["refs"]]
            graph.append(art)
            graph += dataset_nodes(page, base, org, lp["datasets"])
    if page["path"] == "/glossary/":
        graph += glossary_graph(base, html)
    if page.get("app"):
        graph.append({"@type": "WebApplication", "@id": base + page["path"] + "#app", "name": page["crumb"],
                      "url": base + page["path"], "applicationCategory": "FinanceApplication",
                      "operatingSystem": "Any (runs in a web browser)", "browserRequirements": "Requires JavaScript",
                      "isAccessibleForFree": True, "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
                      "publisher": org, "description": page["description"]})
    if page.get("itemlist"):
        graph.append({"@type": "ItemList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": t["name"], "url": base + t["href"]}
            for i, t in enumerate(TOOLS)]})
    if page.get("product") and flags["paid_report"]:
        graph.append(product_jsonld(page, cfg, products["report39"], org))
    faq = faq_from(html)
    if faq:
        graph.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, sort_keys=True)
    return '<script type="application/ld+json">' + data.replace("</", "<\\/") + "</script>"


_DENY_CACHE = {}
REFUND_MACRO_CALLS = ("r.chip()", "r.chip_fr()", "r.short()", "r.tier2()", "r.pricing_line()", "r.faq_answer()", "r.terms_item()", "r.terms_summary()",
                      "r.dispute_ask_first()", "r.misuse_item()", "r.eu_uk()", "r.byp_dd()", "r.formats_caveat()",
                      "f.terms_p()", "f.eu_uk()", "f.byp_dd()", "f.formats_caveat()")
DENY_GRAM = 4
# Words the flag-on wording has and the flag-off wording lacks, but that flag-off pages use for other things. Everything
# else that is flag-on-only (and said twice or more, 7+ letters: goodwill, customer, discretion, gracieux …) is denied.
# Phrases the flag-on wording repeats from text that flag-off pages already carry (the "not enough trades to tell" rule, the
# card-dispute sentence, the reply promise): a run of words inside one of these is not new refund wording.
DENY_NEUTRAL = ("not enough trades to tell the file has dates but no times a person reviews it and writes to you a refund or a lost "
                "payment dispute pas assez de transactions pour conclure affiche pas assez de transactions pour conclure "
                "auprès de l'émetteur de votre carte nous répondons dans les du lundi au vendredi "
                "habit shows not enough trades to tell these terms apply to the donttrade test bought for personal use")
DENY_WORD_OK = frozenset("delivered analysis request re-test purchases habitude analyse remboursons personne demander formulaire "
                         "demande répondons nouveau gratuit commande d'abord".split())


def _gram_words(html):
    import html as _h
    t = _h.unescape(re.sub(r"<[^>]+>", " ", html)).lower().replace("\u2019", "'")
    return re.findall(r"[a-zà-ÿ0-9'-]+", t)


def refund_denylist():
    """Fix round 1 (6 Nov): what a page may NOT say while [flags] refund_no_result is off, DERIVED from the flag-on
    strings so the two cannot drift. The refund macros (partials/refund_copy*.html) are rendered twice, flag on and flag
    off. Denied: every two-word run, every href and every id that the flag-on rendering has and the flag-off one has
    not ("goodwill refund", "no refund", "once your result", "apart from", the /refund/ and /fr/remboursement/ links,
    the #trader-refunds anchors, and the French twins). Runs of DENY_GRAM = 4 words catch whole phrases ("once your
    result is delivered"); single words catch short ones ("goodwill", "gracieux"): flag-on-only words of 7+ letters used
    twice or more, minus DENY_WORD_OK (a hand list of words flag-off pages use for other things; a new flag-on word is
    denied until someone decides). Returns {"grams", "words", "hrefs", "ids"}."""
    key = os.environ.get("DT_PRICES_JSON", "")
    if _DENY_CACHE.get("key") == key:
        return _DENY_CACHE
    with open(os.environ.get("DT_PRICES_JSON") or os.path.join(SITE, "config", "prices.json"), encoding="utf-8") as f:
        prices = json.load(f)
    env = Environment(loader=FileSystemLoader(os.path.join(SITE, "templates")), undefined=StrictUndefined, autoescape=True)
    env.filters["numword"], env.filters["numword_fr"], env.filters["usd"], env.filters["usd_fr"] = numword, numword_fr, usd, usd_fr
    legal = {"refund_effective_human": "1 Jan 2000", "refund_effective_fr": "1 janvier 2000"}
    src = ('{% import "partials/refund_copy.html" as r with context %}{% import "partials/refund_copy_fr.html" as f with context %}'
           + "".join("{{ " + c + " }}\n" for c in REFUND_MACRO_CALLS))
    out = {}
    ru = readers_untested()
    for on in (True, False):
        out[on] = env.from_string(src).render(prices=prices, legal=legal, refund_on=on, readers_untested=ru[0], readers_all=ru[1])
    grams = lambda h: set(zip(*[_gram_words(h)[i:] for i in range(DENY_GRAM)]))
    attr = lambda h, a: set(re.findall(a + r'="([^"]+)"', h))
    import collections
    on_count, off_words = collections.Counter(_gram_words(out[True])), set(_gram_words(out[False]))
    words = {w for w, c in on_count.items() if w not in off_words and len(w) >= 7 and c >= 2} - DENY_WORD_OK
    _DENY_CACHE.clear()
    _DENY_CACHE.update({"key": key, "grams": grams(out[True]) - grams(out[False]), "words": words, "hrefs": attr(out[True], "href") - attr(out[False], "href"),
                        "ids": attr(out[True], "id") - attr(out[False], "id")})
    return _DENY_CACHE


def refund_off_problems(html):
    """[what] a flag-off page says from the flag-on refund wording (see refund_denylist). Visible text, hrefs and ids."""
    deny = refund_denylist()
    found = []
    body = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", html)
    words = _gram_words(body)
    seen = {g for g in set(zip(*[words[i:] for i in range(DENY_GRAM)])) & deny["grams"] if " ".join(g) not in DENY_NEUTRAL}
    if seen:
        found.append("new refund wording: " + ", ".join(sorted('"' + " ".join(g) + '"' for g in seen)[:3]))
    loose = sorted(set(words) & deny["words"])
    if loose:
        found.append("new refund word: " + ", ".join(f'"{w}"' for w in loose[:4]))
    for h in sorted(deny["hrefs"]):
        if f'href="{h}"' in body:
            found.append(f"link to {h}")
    for i in sorted(deny["ids"]):
        if f'id="{i}"' in body:
            found.append(f"anchor #{i}")
    return found


_EN_UNITS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen "
             "eighteen nineteen").split()
_EN_TENS = "x x twenty thirty forty fifty sixty seventy eighty ninety".split()
_FR_UNITS = ("zéro un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize").split()
_FR_TENS = {2: "vingt", 3: "trente", 4: "quarante", 5: "cinquante", 6: "soixante"}


def spelled_amount(n):
    """Regex for the amount n (10 to 99) written in words before "dollars", English and French: "forty-nine dollars",
    "forty nine US dollars", "49 dollars", "quarante-neuf dollars américains". Fix round 2: the digit patterns missed these."""
    t, u = divmod(n, 10)
    en = _EN_UNITS[n] if n < 20 else _EN_TENS[t] + (r"[\s-]" + _EN_UNITS[u] if u else "")
    if n < 17:
        fr = _FR_UNITS[n]
    elif n < 20:
        fr = "dix-" + _FR_UNITS[u]
    elif t in _FR_TENS:
        fr = _FR_TENS[t] + ((r"(?:\s+et\s+|-)" + _FR_UNITS[u]) if u else "")
    else:   # 70 to 99
        base = "soixante" if t < 8 else "quatre-vingt"
        rest = (10 if t in (7, 9) else 0) + u
        fr = base + ((r"(?:\s+et\s+|-)" + (_FR_UNITS[rest] if rest < 17 else "dix-" + _FR_UNITS[rest - 10])) if rest else ("s" if t == 8 else ""))
    cur = r"(?:\s+(?:US|U\.S\.|canadian|american|américains?|canadiens?|états-unis))*\s+(?:dollars?|USD|\$)"
    return rf"\b(?:{n}|{en}|{fr}){cur}(?![\w])"


def founding_problem(html, open_, limit, after=49):
    """None, or why a rendered page words the price after the founding price wrongly (Round A1, fix round 1).
    While the founding price is open there is ONE approved form: "for the first N buyers, then US$49" (French: "pour les
    N premiers acheteurs, puis 49,00 $ US"). The check removes every use of that exact phrase and then fails on ANY other
    mention of the next price: a sentence-final "$49.", a bare "$49", "US$49 after that", "49 $ US", "49 USD", "was $49".
    It also fails when the next price is crossed out (<s>, <del>, <strike>), open or ended. Ended, the next price is the
    price, so only the crossed-out rule applies. Retired amounts and the words regular/standard price are checked by lint."""
    body = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", html)
    n = r"(?:\$\s?%d(?!\d)|(?<![\d,.])%d(?:[.,]00)?[\s\u00a0]*(?:\$|USD\b|US\b))" % (after, after)
    if re.search(r"(?is)<(?:s|del|strike)\b[^>]*>[^<]*" + n, body):
        return "the next price is crossed out (<s>, <del> or <strike>): it is never a reference price"
    if not open_:
        return None
    text = _text(body)
    approved = (rf"for the first {limit} buyers, then US\$[\s\u00a0]?{after}(?!\d)"
                rf"|pour les {limit} premiers acheteurs, puis {after},00[\s\u00a0]*\$[\s\u00a0]*US")
    rest = re.sub(approved, " ", text)
    m = re.search(n, rest) or re.search(spelled_amount(after), rest, re.I)
    if m:
        return (f"the next price appears outside the one approved form \"for the first {limit} buyers, then US${after}\" "
                f"(French: \"pour les {limit} premiers acheteurs, puis {after},00 $ US\"): …{rest[max(0, m.start() - 50):m.end() + 40].strip()}…")
    return None


# Security headers (hardening plan item 1, 3 Nov). Cloudflare Pages reads _headers from the root of the folder it
# serves (docs/). Every page keeps its full CSP in a <meta>; this header CSP holds frame-ancestors ONLY (a <meta>
# cannot set it), so it adds clickjacking protection and changes nothing else (each policy is enforced on its own).
# 'self'/SAMEORIGIN, not 'none'/DENY: pay.js loads /before-you-pay/ in a hidden same-origin iframe.
# HSTS one year, no includeSubDomains, no preload. Pages already sends nosniff and Referrer-Policy: not repeated.
SECURITY_HEADERS = [
    ("Strict-Transport-Security", "max-age=31536000"),
    ("X-Frame-Options", "SAMEORIGIN"),
    ("Content-Security-Policy", "frame-ancestors 'self'"),
    ("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()"),
]
HEADERS_MAX_RULES = 100      # Cloudflare Pages limits for _headers
HEADERS_MAX_LINE = 2000


def headers_file():
    lines = ["# Written by site/build.py (headers_file). Edit there, never docs/_headers.", "/*"]
    lines += [f"  {k}: {v}" for k, v in SECURITY_HEADERS]
    lines += ["", "https://:project.pages.dev/*", "  X-Robots-Tag: noindex",
              "", "https://:version.:project.pages.dev/*", "  X-Robots-Tag: noindex"]
    return "\n".join(lines) + "\n"


def headers_problem(text):
    """None, or why a _headers file breaks Cloudflare's limits (100 rules, 2,000 characters a line)."""
    lines = text.split("\n")
    rules = [ln for ln in lines if ln.strip() and not ln.startswith((" ", "\t", "#"))]
    if not rules:
        return "no rule"
    if len(rules) > HEADERS_MAX_RULES:
        return f"{len(rules)} rules (Cloudflare's limit is {HEADERS_MAX_RULES})"
    long_ = [i + 1 for i, ln in enumerate(lines) if len(ln) > HEADERS_MAX_LINE]
    if long_:
        return f"line {long_[0]} is over {HEADERS_MAX_LINE} characters"
    return None



ISLAND_OPEN, ISLAND_CLOSE = "<!--island:start-->", "<!--island:end-->"
META_P_RE = re.compile(r'(?s)<p class="meta">.*?</p>')


def insert_island(fragment, anchor, island, path):
    """Put new markup INSIDE a lifted page's frozen body, between island markers, right after the first match of
    `anchor` (a compiled regex, or the string "</dl>"). checks/compare.py leaves islands out of the comparison with the
    old page, so the frozen words are untouched; lint holds the island to the full page rules (lint.split_frozen)."""
    if isinstance(anchor, str):
        i = fragment.find(anchor)
        end = i + len(anchor) if i >= 0 else -1
    else:
        m = anchor.search(fragment)
        end = m.end() if m else -1
    if end < 0:
        die(f"{path}: the lifted body has no place for the island (anchor {getattr(anchor, 'pattern', anchor)!r})")
    return fragment[:end] + ISLAND_OPEN + island + ISLAND_CLOSE + fragment[end:]


def llms_txt(cfg, pages, studies_by_path):
    """/llms.txt (SEO plan 4.3): the site in plain text for agents, from the same config as the pages, so it cannot drift.
    Studies come from studies.json (the headline string and DOI each page shows), the rest from PAGES and TOOLS."""
    base = cfg["site"]["base_url"]
    by_path = {p["path"]: p for p in pages}
    lines = ["# donttrade", "",
             "> Independent research on how retail traders behave, with data and code where published, and free in-browser tools "
             "that measure habits in your own trade file. Not investment advice; not a registered adviser.", "",
             "## Studies (negative results included; DOIs where a study has one)"]
    for path in ("/research/disposition-effect/", "/research/portfolio-driven-disposition-effect/", "/research/insider-buying-edge/",
                 "/research/volatility-scaled-momentum/", "/research/strategy-tests/", "/research/swing-trading-strategies/", SELLOFF_PATH):
        pg = by_path.get(path)
        if pg is None:
            continue
        st = studies_by_path.get(path)
        if st:
            lines.append(f"- [{st['title']}]({base}{path}): {st['key_result']} DOI {st['doi']}")
        else:
            lines.append(f"- [{pg['title'].replace(' — donttrade', '')}]({base}{path}): {pg['description']}")
    lines += ["", "## Learn"]
    for pg in sorted((p for p in pages if p["path"].startswith("/learn/")), key=lambda p: LEARN_PATHS.index(p["path"])):
        if True:
            lines.append(f"- [{pg['title']}]({base}{pg['path']}): {pg['description']}")
    lines += ["", "## Free tools (run in your browser; your file is not uploaded)"]
    for t in TOOLS:
        lines.append(f"- [{t['name']}]({base}{t['href']}): {t['question']}")
    lines += ["", "## Reference"]
    for path, label in (("/glossary/", "Glossary"), ("/code/", "Methods and code"), ("/corrections/", "Corrections"),
                        ("/for-researchers/", "For researchers and press"), ("/research/", "All studies")):
        if path in by_path:
            lines.append(f"- [{label}]({base}{path})")
    return "\n".join(lines) + "\n"


def write_sitemap_and_robots(out, cfg, built_pages, flags):
    """sitemap.xml: today's entries (their dates kept), with template pages dated by their
    content date (page["updated"]), never the build date. Pages with noindex are left out.
    robots.txt: allow all; the paid-only pages are disallowed when they exist (and noindexed)."""
    base = cfg["site"]["base_url"]
    with open(os.path.join(DOCS, "sitemap.xml"), encoding="utf-8") as f:
        old = re.findall(r"<loc>" + re.escape(base) + r"(/[^<]*)</loc><lastmod>([^<]+)</lastmod>", f.read())
    dates = dict(old)
    order = [p for p, _ in old]
    index = {}
    for page in built_pages:
        if page.get("noindex"):
            dates.pop(page["path"], None)
            continue
        if "updated" not in page:
            die(f"page {page['path']} has no 'updated' content date for the sitemap")
        dates[page["path"]] = page["updated"]
        index[page["path"]] = True
    order += sorted(p for p in index if p not in order)
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    lines += [f"  <url><loc>{base}{p}</loc><lastmod>{dates[p]}</lastmod></url>" for p in order if p in dates]
    lines.append("</urlset>")
    with open(os.path.join(out, "sitemap.xml"), "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")
    robots = ["User-agent: *", "Allow: /"]
    if flags["paid_report"]:
        # 6 Nov (SEO round 1): /before-you-pay/ is noindex but no longer disallowed. A disallowed page's noindex is never
        # read (the crawler does not fetch it), and its hreflang pair with /fr/avant-de-payer/ must be readable.
        robots += [f"Disallow: {p}" for p in PAID_APP_PATHS]
    if flags["analytics"]:
        robots.append(f"Disallow: {COUNT_BASE}")
    robots.append(f"Sitemap: {base}/sitemap.xml")
    with open(os.path.join(out, "robots.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(PREVIEW_ROBOTS_TXT if preview_name() else "\n".join(robots) + "\n")


PREVIEW_NAME_RE = re.compile(r"[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?")
PREVIEW_ROBOTS_META = '<meta name="robots" content="noindex,nofollow">'
PREVIEW_BAND_ATTR = "data-preview-band"
PREVIEW_ROBOTS_TXT = "User-agent: *\nDisallow: /\n"


def preview_name():
    """C-17: the DT_PREVIEW name (a Pages branch name: lowercase letters, digits, inner hyphens), or None."""
    name = os.environ.get("DT_PREVIEW", "")
    if name == "":
        return None
    if not PREVIEW_NAME_RE.fullmatch(name):
        die(f"DT_PREVIEW={name!r} is not a branch-style name (lowercase letters, digits, inner hyphens, at most 40)")
    return name


def preview_problems(out, preview):
    """[problem]: a preview build has the robots meta and the band on every page and a Disallow-all robots.txt;
    any other build has none of them (passthrough pages included: they do not come from base.html)."""
    probs = []
    for root, _, files in os.walk(out):
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            rel = os.path.relpath(os.path.join(root, name), out)
            text = open(os.path.join(root, name), encoding="utf-8", errors="replace").read()
            n_meta, n_band = text.count(PREVIEW_ROBOTS_META), text.count(PREVIEW_BAND_ATTR)
            robots = len(re.findall(r'<meta name="robots"', text))
            if preview and (n_meta != 1 or n_band != 1 or robots != 1):
                probs.append(f"{rel}: preview build needs exactly one noindex,nofollow robots meta (found {n_meta} "
                             f"of {robots} robots metas) and one preview band (found {n_band})")
            if not preview and (n_meta or n_band):
                probs.append(f"{rel}: preview markup in a build without DT_PREVIEW")
    txt = open(os.path.join(out, "robots.txt"), encoding="utf-8").read()
    if preview and txt != PREVIEW_ROBOTS_TXT:
        probs.append("robots.txt of a preview build must disallow everything")
    if not preview and "Disallow: /\n" in txt:
        probs.append("robots.txt disallows the whole site in a build without DT_PREVIEW")
    return probs


def out_file(out, path):
    rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        rel += "index.html"
    return os.path.join(out, rel)


def copy_tree_sorted(src, dst, skip=None):
    for root, dirs, files in os.walk(src):
        dirs.sort()
        for name in sorted(files):
            s = os.path.join(root, name)
            rel = os.path.relpath(s, src)
            if skip and skip(rel):
                continue
            d = os.path.join(dst, rel)
            os.makedirs(os.path.dirname(d), exist_ok=True)
            shutil.copyfile(s, d)  # content only: no timestamps carried over


def read_baseline():
    paths, ids = [], []
    with open(BASELINE, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "#" in line:
                ids.append(tuple(line.split("#", 1)))
            else:
                paths.append(line)
    return paths, ids


ALT_RE = re.compile(r'<link rel="alternate" hreflang="([^"]+)" href="([^"]+)">')


def check_language_pairs(out, base_url):
    """Tester D6: hreflang only counts when it is reciprocal. Every page that declares
    alternates must be named back by each of them, and must carry a visible link (with
    hreflang) to each other-language version."""
    alts = {}
    for root, _, files in os.walk(out):
        for name in sorted(files):
            if name.endswith(".html"):
                fp = os.path.join(root, name)
                with open(fp, encoding="utf-8", errors="replace") as f:
                    html = f.read()
                found = ALT_RE.findall(html)
                if found:
                    path = "/" + os.path.relpath(fp, out).replace("index.html", "")
                    alts[path] = (found, html)
    for path, (found, html) in sorted(alts.items()):
        own = [h for lang, h in found if lang != "x-default"]
        if base_url + path not in own:
            die(f"hreflang: {path} does not list itself among its alternates")
        for lang, href in found:
            if lang == "x-default":
                continue
            other = href[len(base_url):] if href.startswith(base_url) else href
            if other == path:
                continue
            if other not in alts:
                die(f"hreflang: {path} names {other} ({lang}), which declares no alternates back")
            if base_url + path not in [h for _, h in alts[other][0]]:
                die(f"hreflang: {other} does not name {path} back (the pair is ignored by search engines)")
            body = html[html.find("<body"):]
            if not re.search(r'<a href="' + re.escape(other) + r'[#"][^>]*hreflang="' + re.escape(lang) + '"', body):
                die(f"language link: {path} has no visible link to its {lang} version {other}")


# Delivery plan C-11 (P-5): a page may say the trade numbers are not stored only next to the
# fingerprint that IS kept (/privacy/ discloses it). Any block element whose text holds one of
# STORAGE_CLAIMS must also hold one of STORAGE_QUALIFIERS; the build fails otherwise.
# C-14 (GET-PAID L7): the paid footer's and /privacy/'s "does not keep" and the French "ne conserve pas" /
# "non conservés" are the same claim, so they are held to the same rule.
STORAGE_CLAIMS = ("not stored", "not kept", "never stored", "ne sont pas conservés",
                  "does not keep", "doesn't keep", "ne conserve pas", "non conservé")
STORAGE_QUALIFIERS = ("fingerprint", "empreinte")
_BLOCK_TAGS = {"p", "li", "dd", "dt", "td", "th", "summary", "details", "figcaption", "blockquote", "h1", "h2", "h3",
               "h4", "h5", "h6", "div", "section", "article", "aside", "main", "header", "footer", "label", "legend",
               "caption", "body", "html"}


class _BlockText(_HTMLParser):
    """The text of every block element (with its descendants), skipping script and style."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.open, self.done, self.skip = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.skip += 1
        elif tag in _BLOCK_TAGS:
            self.open.append([tag, []])

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.skip = max(0, self.skip - 1)
        elif tag in _BLOCK_TAGS:
            for k in range(len(self.open) - 1, -1, -1):   # close the nearest open element of that tag
                if self.open[k][0] == tag:
                    for t, parts in self.open[k:][::-1]:
                        self.done.append((t, " ".join(parts)))
                    del self.open[k:]
                    break

    def handle_data(self, data):
        if not self.skip:
            for entry in self.open:
                entry[1].append(data)


def storage_claim_problems(html, where):
    p = _BlockText()
    p.feed(html)
    p.close()
    out, flagged = [], []
    for tag, text in p.done + [(t, " ".join(parts)) for t, parts in p.open]:   # inner elements close first
        t = re.sub(r"\s+", " ", text.replace("\u2019", "'")).lower().strip()
        claims = [c for c in STORAGE_CLAIMS if c in t]
        if not claims or any(q in t for q in STORAGE_QUALIFIERS):
            continue
        if any(f in t for f in flagged):
            continue   # an ancestor of an element already reported: report the innermost only
        flagged.append(t)
        out.append(f"{where}: <{tag}> says {claims[0]!r} without the fingerprint that is kept: {t[:200]}")
    return out


# C-14 (G14, G15): the paid-build legal lines. Each (path, id) must be on its page in a paid_report build,
# and on none of them in a free build. The ids carry the lines a lawyer reviews (LAWYER in the templates).
PAID_LEGAL_IDS = [("/privacy/", "buyer-details"), ("/terms/", "chargeback"), ("/terms/", "outage"),
                  ("/fr/confidentialite/", "donnees-acheteur"), ("/fr/conditions/", "contestation"),
                  ("/fr/conditions/", "panne")]
MANUAL_RESTORE_IDS = [("/terms/", "manual-restore"), ("/fr/conditions/", "restauration-manuelle")]
PROVIDERS_ABROAD = "are mostly in the United States"   # the /privacy/ providers sentence


def paid_legal_problems(out, cfg):
    """[problem] for the C-14 legal lines of this build (an empty list when they are right)."""
    flags, probs = cfg["flags"], []

    def page(path):
        fp = out_file(out, path)
        return open(fp, encoding="utf-8").read() if os.path.exists(fp) else None

    restore = MANUAL_RESTORE_IDS if cfg["site"].get("manual_restore", True) else []
    for path, i in PAID_LEGAL_IDS + MANUAL_RESTORE_IDS:
        html = page(path)
        has = html is not None and re.search(r'\sid="' + re.escape(i) + '"', html) is not None
        want = flags["paid_report"] and ((path, i) in PAID_LEGAL_IDS or (path, i) in restore)
        if has != want:
            probs.append(f"{path}#{i} is {'missing from' if want else 'in'} this build "
                         f"(paid_report = {str(flags['paid_report']).lower()}"
                         f"{', manual_restore = ' + str(bool(restore)).lower() if (path, i) in MANUAL_RESTORE_IDS else ''})")
    priv = page("/privacy/") or ""
    if flags["paid_report"]:
        if "pen name" in priv:
            probs.append("/privacy/ says \"pen name\" in a paid build: the seller is named there (G14)")
        li = re.findall(r"(?s)<li>((?:(?!</li>).)*" + re.escape(PROVIDERS_ABROAD) + r".*?)</li>", priv)
        if len(li) != 1 or "Cloudflare" not in li[0]:
            probs.append("/privacy/ providers sentence does not name Cloudflare in a paid build (the server runs there)")
    return probs


def verify(out, flags, seller=None, base_url=None):
    """seller: whether the seller block may appear (show_seller); defaults to any commerce flag."""
    storage = []
    for root, _, files in os.walk(out):
        for name in sorted(files):
            if name.endswith(".html"):
                fp = os.path.join(root, name)
                with open(fp, encoding="utf-8", errors="replace") as f:
                    storage += storage_claim_problems(f.read(), os.path.relpath(fp, out))
    if storage:
        die("P-5 storage claim: " + "; ".join(storage[:5]) + (f" (and {len(storage) - 5} more)" if len(storage) > 5 else ""))
    if base_url:
        check_language_pairs(out, base_url)
    if seller is None:
        seller = any(flags.get(f) for f in COMMERCE_FLAGS)
    hp = os.path.join(out, "_headers")   # hardening item 1: the security headers Cloudflare Pages reads
    if not os.path.isfile(hp):
        die("_headers missing from the build (headers_file)")
    with open(hp, encoding="utf-8") as f:
        why = headers_problem(f.read())
    if why:
        die(f"_headers: {why}")
    paths, ids = read_baseline()
    for p in paths:
        if not os.path.exists(out_file(out, p) if p.endswith("/") else os.path.join(out, p.lstrip("/"))):
            die(f"baseline URL missing from the build: {p}")
    for p, i in ids:
        with open(out_file(out, p), encoding="utf-8") as f:
            html = f.read()
        if not re.search(r'\sid="' + re.escape(i) + '"', html):
            die(f"externally linked id missing: {p}#{i}")
    if not seller:
        for root, _, files in os.walk(out):
            for name in sorted(files):
                if name.endswith(".html"):
                    fp = os.path.join(root, name)
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        if "data-seller-block" in f.read():
                            die(f"seller disclosure in {os.path.relpath(fp, out)} while this build must not show it "
                                "(paid_report off, and pilot_checkout off or [legal] show_seller_for_pilot = false)")
    if not flags.get("pilot_checkout"):
        for p in PILOT_ONLY_PATHS:
            if os.path.exists(out_file(out, p)):
                die(f"pilot-only page {p} is in the build while pilot_checkout = false")
        for root, _, files in os.walk(out):
            for name in sorted(files):
                if name.endswith(".html"):
                    fp = os.path.join(root, name)
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        if PILOT_FLAG_MARKER in f.read():
                            die(f"pilot-checkout markup in {os.path.relpath(fp, out)} while pilot_checkout = false")
    if not flags["paid_report"]:
        for p in PAID_ONLY_PATHS:
            if os.path.exists(out_file(out, p)):
                die(f"paid-only page {p} is in the build while paid_report = false")
        for root, _, files in os.walk(out):
            for name in files:
                if name.endswith(".html"):
                    fp = os.path.join(root, name)
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        if PAID_FLAG_MARKER in f.read():
                            die(f"paid-flagged markup in {os.path.relpath(fp, out)} while paid_report = false")
    for root, _, files in os.walk(out):  # motion plan guard (MOTION_PAGES) + cache-busting (every URL versioned)
        for name in sorted(files):
            if name.endswith(".html"):
                fp = os.path.join(root, name)
                with open(fp, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                url = "/" + os.path.relpath(fp, out).replace(os.sep, "/").replace("index.html", "")
                why = motion_problem(text, url) or vt_problem(text, url) or journal_problem(text, url) or unversioned_problem(text)
                if why:
                    die(why)
    why = vt_css_problem(out)
    if why:
        die(why)
    # Decision 21 Oct, narrowed 25 Oct: the footer business line, on every page exactly once under any
    # commerce flag: the full one (with the address) on ADDRESS_LINE_PATHS, the short one everywhere else
    commerce = any(flags.get(f) for f in COMMERCE_FLAGS)
    for root, _, files in os.walk(out):
        for name in sorted(files):
            if name.endswith(".html"):
                fp = os.path.join(root, name)
                with open(fp, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                n, m = text.count(BUSINESS_ID_ATTR), len(BUSINESS_ID_RE.findall(text))
                rel = os.path.relpath(fp, out)
                if commerce and (n != 1 or m != 1):
                    die(f"business line: {rel} has {n} business-identification line(s), "
                        "expected exactly 1 while a commerce flag is on")
                if commerce:
                    want = "full" if business_line_full(url_of(rel)) else "short"
                    if f'{BUSINESS_ID_ATTR}="{want}"' not in text:
                        die(f"business line: {rel} has the wrong business line, expected the {want} one "
                            "(the address only on build.ADDRESS_LINE_PATHS)")
                if not commerce and n:
                    die(f"business line in {os.path.relpath(fp, out)} while every commerce flag is off")
    if commerce:   # the short line's "Business details" links land on the seller block
        for href, _ in ([BUSINESS_DETAILS["en"]] + ([BUSINESS_DETAILS["fr"]] if flags.get("paid_report") else [])):
            fp = os.path.join(out, href.split("#")[0].strip("/"), "index.html")
            if not os.path.exists(fp) or open(fp, encoding="utf-8").read().count(SELLER_ANCHOR) != 1:
                die(f"business line: {href} has no single {SELLER_ANCHOR} for the footer's details link")


def future_dated(cfg):
    """[(what, date)] stamped later than the machine's real date: the terms and privacy versions, and the content
    dates that become the sitemap's <lastmod>. A bundle (docs/) must have none of them (6 Nov, fix round 1)."""
    rt = real_today().isoformat()
    found = [(k, cfg["legal"][k]) for k in ("terms_version", "privacy_version") if cfg["legal"][k] > rt]
    found += [(f"{pg['path']} updated", pg["updated"]) for pg in PAGES if pg.get("updated", "") > rt]
    return found


def build():
    cfg, prices, private = load_config()
    flags = cfg["flags"]
    if os.environ.get("DT_REQUIRE_LAUNCH_DATE") == "1" and not preview_name():
        ahead = future_dated(cfg)
        if ahead:
            die("docs/ would be stamped later than today's real date " + real_today().isoformat() + " ("
                + ", ".join(f"{k} {v}" for k, v in ahead[:4]) + (" …" if len(ahead) > 4 else "")
                + "): bundle on that day without DT_TODAY. Only a preview build (DT_PREVIEW) may be dated ahead.")
    out = os.environ.get("DT_OUT") or os.path.join(SITE, "_site")
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)

    owned = {}
    for page in PAGES:
        if page["requires_flag"] and not flags[page["requires_flag"]]:
            continue
        if page.get("requires_promo") and not cfg["stripe"]["promo_codes_enabled"]:
            continue   # fix round 1: /partners/ exists only while promotion codes are switched on (Round B codes are not live)
        if flags["paid_report"] and page.get("lifted") and page["path"] in PAID_REPLACES_LIFTED:
            page = SAMPLE_PAGE   # C-12 final: the real sample report replaces the lifted research figure
        owned[os.path.relpath(out_file(out, page["path"]), out)] = page

    check_hero_dashboard()
    real_ = {"real": tool_real_data()}   # 6 Nov (B2): the real-data figures and their drawing geometry, every page
    real_["rv"] = tool_real.view(real_["real"])

    # 1. passthrough of every docs/ file a template does not own yet. docs/static/ is the last bundle's
    # copy of site/static/ (step 30), never a source: skipped, so a file deleted from site/static/
    # (the old hero .webp images, motion plan) does not come back from docs/.
    copy_tree_sorted(DOCS, out, skip=lambda rel: rel in owned or rel.startswith("static" + os.sep))
    for rel in passthrough_pages(owned):
        fp = os.path.join(out, rel)
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        text = fix_passthrough_chrome(text, rel, flags, umami_on(cfg))
        text = add_passthrough_csp(text, rel)
        text = add_business_line(text, rel, business_id_line(cfg, private, url=url_of(rel),
                                                             lang=passthrough_lang(text)))
        for old, new in PASSTHROUGH_FIXES.get(rel, []):
            if text.count(old) != 1:
                die(f"passthrough fix: {rel} no longer holds this sentence exactly once: {old!r}")
            text = text.replace(old, new)
        with open(fp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    apply_file_fixes(out)
    for rel in sorted(set(PASSTHROUGH_FIXES) - set(passthrough_pages(owned))):
        # a template owns it (a lifted page carries its fixes in its fragment) or it is not in docs/
        die(f"passthrough fix: {rel} is not a passthrough page (owned by a template, or not in docs/)")
    for rel in PASSTHROUGH_CSP_PAGES:
        # Manager C4: the two old calculators never connect anywhere. Passed through, they get the
        # meta above; lifted (steps 28–29), csp_for gives them NO_NETWORK_CSP (no 'unsafe-inline').
        if rel not in passthrough_pages(owned) and rel not in owned:
            die(f"no-network CSP: {rel} is neither a template page nor a page in docs/")
    # 2. static assets of the new design
    def static_left_out(rel):
        return ((not flags["paid_report"] and rel.startswith("js" + os.sep + "paid"))
                or (not flags["free_badges"] and rel == BADGES_JS)
                or (not flags["whatif_ranked"] and rel == RANK_JS)
                or (not flags["journal"] and (rel.startswith(JOURNAL_JS_DIR) or rel == os.path.join("css", "journal.css"))))   # ARCHITECT-V3 D7: out of the build until approved
    copy_tree_sorted(os.path.join(SITE, "static"), os.path.join(out, "static"), skip=static_left_out)
    set_ranked_flag(os.path.join(out, "static", RANKED_JS), flags["whatif_ranked"])
    shutil.copyfile(REAL_SAMPLE_CSV, os.path.join(out, REAL_SAMPLE_URL.lstrip("/")))   # the download beside the button
    # 3. dev pages, only on request; never bundled
    if os.environ.get("DT_DEV") == "1":
        copy_tree_sorted(os.path.join(SITE, "dev"), os.path.join(out, "dev"))

    env = Environment(loader=FileSystemLoader(os.path.join(SITE, "templates")), undefined=StrictUndefined,
                      autoescape=True, keep_trailing_newline=True)
    env.filters["usd"] = usd
    env.filters["usd_fr"] = usd_fr
    env.filters["isodate"] = isodate
    env.filters["numword"] = numword
    env.filters["numword_fr"] = numword_fr
    env.filters["longdate"] = longdate
    env.globals["crumb_items"] = crumb_items
    products = {p["id"]: p for p in prices["products"]}
    nav = nav_for(cfg["nav"], flags)
    base_ctx = {"site": cfg["site"], "flags": flags, "nav": nav, "nav_current": lambda pg: nav_current(nav, pg),
                "footer": footer_for(cfg["footer"], flags), "vt_pages": VT_PAGES, "mkt_pages": MOTION_PAGES, "channels": cfg["channels"],
                "legal": cfg["legal"], "forms": cfg["forms"], "analytics": cfg["analytics"],
                "worker": cfg["worker"], "prices": prices, "products": products, "private": private,
                "stripe_mode": cfg["stripe"]["mode"], "lift": lift_sections, "tools": tools_for(flags),
                "tool_previews": tool_previews(), "evidence": evidence(), "latest": latest(), "umami_on": umami_on(cfg), "umami_strict": umami_strict, "show_seller": show_seller(cfg),
                "strings": read_toml(os.path.join(SITE, "config", "strings.toml"), "strings.toml"),
                "paid_method": paid_method(),
                "method_name": next((e.get("name") for e in report_methods() if e["method"] == page_method_version()), None),
                "preview": preview_name(), "founding_open": prices["rules"]["founding_open"],
                "partners_meta": partners_meta(cfg["partners"], prices),
                "refund_on": flags["refund_no_result"], "refund_reasons": refund_reasons(),
                "stripe_promo": cfg["stripe"]["promo_codes_enabled"],
                "readers_untested": readers_untested()[0], "readers_all": readers_untested()[1]}
    built, rendered = [], []
    pages_by_path = {pg["path"]: pg for pg in owned.values()}
    STUDIES, REFS = studies(), references()
    for pth in STUDIES:   # a study entry for a page this build does not publish is a typo
        if pth not in pages_by_path:
            die(f"studies.json: {pth} is not a page of this build")
    if ABOUT_LINE not in lifted_fragment("about"):
        die("ABOUT_LINE (the Organization description) is no longer the first sentence of /about/: update both together")
    if not os.path.exists(os.path.join(DOCS, ORG_LOGO.lstrip("/"))):
        die(f"Organization logo {ORG_LOGO} is missing from docs/ (run checks/make_seo_assets.py)")

    def render(rel, page, **more):
        page = {"scripts": [], "modules": [], "og_image": "/assets/og/default.png", "lang": "en",
                "alternates": [], **page}
        if page.get("product"):
            page["product"] = product_text(prices["rules"])   # Round A2: one source for the habit counts
        if flags["paid_report"]:
            page["scripts"] = page["scripts"] + page.get("scripts_if_paid", [])
            page["alternates"] = page.get("alternates_if_paid", page["alternates"])
            page.update(page.get("if_paid", {}))  # R5: title/description that sell instead of "waitlist"
        if flags["free_badges"]:
            page.update(page.get("if_badges", {}))  # C1: the copy that names the free check
        if not flags["ask_box"]:
            page["scripts"] = [s for s in page["scripts"] if s not in ASK_SCRIPTS]
        extra = {"sample_csv": real_sample_csv() if page["path"] in REAL_SAMPLE_PATHS else sample_csv()} if page.get("sample") else {}
        extra.update(real_)
        # the trader Stripe link, built here only: every page's copy names the page it is on (client_reference_id)
        extra["pay_link"] = with_client_ref(products["report39"]["stripe_link_" + cfg["stripe"]["mode"]], page["path"])
        extra["report_link_fr"] = with_client_ref(report_link_fr(products["report39"], cfg["stripe"]["mode"]), page["path"])
        if page.get("presets"):
            lib_ = challenge_presets()
            extra["presets"] = lib_
            extra["presets_json"] = Markup(json.dumps(lib_, sort_keys=True, ensure_ascii=False).replace("</", "<\\/"))
        if page.get("sample_trades"):
            extra["sample_trades_csv"] = sample_report_trades()
        if page.get("prediction"):
            extra["prediction"] = prediction_context()
        if page.get("sample_report") or (page["path"] in ("/", "/for-traders/") and flags["paid_report"]):  # 25 Oct: the home showcase; sweep 2: the report card on /for-traders/
            rep_ = sample_report()
            extra["sample_report"] = rep_
            extra["sample_report_json"] = Markup(json.dumps(rep_, sort_keys=True, ensure_ascii=False).replace("</", "<\\/"))
        extra["related"] = related_for(page["path"], pages_by_path)   # 6 Nov (SEO round 1): the Related block
        st = STUDIES.get(page["path"])
        extra["study"] = st
        if st:   # Highwire meta (Google Scholar): the DOI and the public URL, after the page's own citation_* lines
            page["citation"] = list(page.get("citation", [])) + [["citation_doi", st["doi"]],
                                                                 ["citation_public_url", cfg["site"]["base_url"] + page["path"]]]
        if page.get("learn"):
            extra.update(learn_context())
            extra["learn_refs"] = {k: REFS[k] for k in page["learn"].get("refs", [])}
            if page["path"] == "/learn/drawdown-recovery-table/":
                extra["mkt"] = LT.market_view()   # the dated callout: closes of 5 Nov 2026, computed by learn_tables
        if page["path"] == "/":
            extra["dated_band"] = dated_band()
        if page.get("selloff"):
            extra["sell"] = selloff_ctx()
            extra["mkt"] = LT.market_view()
            extra["study_refs"] = {k: REFS[k] for k in SELLOFF_REFS}
            extra["study_refs_checked"] = max(REFS[k]["crossref_checked"] for k in SELLOFF_REFS)
        if page["path"] == "/glossary/":
            extra["glossary_terms"] = glossary_terms()
        if page.get("lifted"):
            frag = paid_lifted(page["path"], lifted_fragment(page["lifted"]), flags["paid_report"])
            if st:   # "Cite this study" under the study's header lines, as an island: the frozen words stay as they were
                frag = insert_island(frag, META_P_RE, env.get_template("partials/cite_study.html").render(study=st, site=cfg["site"],
                                     apa=apa_line(st), bibtex=bibtex_entry(st)), page["path"])
            if page["path"] == "/glossary/":   # the trading and risk terms, after the twelve study terms
                frag = insert_island(frag, "</dl>", env.get_template("partials/glossary_more.html").render(terms=extra["glossary_terms"], refs=REFS), page["path"])
            if page["path"] == "/research/":   # the newest study, last in the chronological list, as an island (the frozen words stay as they were)
                frag = insert_island(frag, RESEARCH_LIST_END, env.get_template("partials/selloff_listing.html").render(
                    sell=selloff_ctx(), mkt=LT.market_view(), page={"path": SELLOFF_PATH, "published": SELLOFF_PUBLISHED}), page["path"])
            if page["path"] == "/code/":   # the site's own table script, which the /learn/ pages cite
                frag = insert_island(frag, "</table></div>", env.get_template("partials/code_more.html").render(), page["path"])
            extra["lifted_html"] = Markup(frag)
            if page["path"] == "/corrections/":
                extra["report_methods"] = report_methods()
                extra["report_methods_renamed"] = report_methods_renamed()
        extra["footer_privacy"] = footer_privacy(flags, umami_on(cfg), page)   # per page (no_umami, no_analytics)
        line = Markup(business_id_line(cfg, private, "legal", url=page["path"], lang=page["lang"]))
        html = env.get_template(page["template"]).render(page=page, csp=csp_for(page, cfg), business_id_line=line,
                                                         **base_ctx, **extra, **more)
        if not page.get("lifted"):
            html = add_faq_ids(html)   # Q-A1: a stable id per FAQ question (lifted pages keep their frozen ids)
        if html.count(LD_MARKER) != 1:
            die(f"{page['template']}: the JSON-LD marker must appear exactly once")
        html = html.replace(LD_MARKER, jsonld(page, cfg, html, flags, products))
        if not flags["refund_no_result"] and not page.get("lifted"):
            off = refund_off_problems(html)
            if off:
                die(f"{page['path']}: refund_no_result is off but the page says the new policy: " + "; ".join(off))
        why = founding_problem(html, prices["rules"]["founding_open"], prices["rules"]["founding_limit"],
                               products["report39"]["after_founding"]["price_usd"])
        if why:
            die(f"{page['path']}: {why}")
        fp = os.path.join(out, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        built.append(page)
        rendered.append((page, html))

    later = {rel: page for rel, page in owned.items() if page["path"] == "/help/"}
    for rel, page in sorted(owned.items()):
        if rel not in later:
            render(rel, page)
    units = answer_units(rendered, private)
    with open(os.path.join(out, ANSWERS_JS.lstrip("/")), "w", encoding="utf-8", newline="\n") as f:
        f.write(answers_index_js(units, cfg))
    for rel, page in sorted(later.items()):
        render(rel, page, answer_units=units)
    write_sitemap_and_robots(out, cfg, built, flags)
    write_learn_data(out)
    write_selloff_data(out)
    with open(os.path.join(out, "llms.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(llms_txt(cfg, [pg for pg in built if not pg.get("noindex")], STUDIES))
    with open(os.path.join(out, "_headers"), "w", encoding="utf-8", newline="\n") as f:
        f.write(headers_file())
    version_assets(out, left_out=static_left_out)
    ix = cfg.get("indexnow")
    if ix and not preview_name():
        # Round A5: IndexNow ownership file, <key>.txt at the site root, holding the key and nothing else. The key is
        # public by design. Not in a preview build (a preview is noindex and must not be announced to search engines).
        with open(os.path.join(out, ix["key"] + ".txt"), "w", encoding="utf-8", newline="") as f:
            f.write(ix["key"])
    elif ix and os.path.exists(os.path.join(out, ix["key"] + ".txt")):
        os.remove(os.path.join(out, ix["key"] + ".txt"))   # docs/ carries it from the last bundle: a preview build must not

    verify(out, flags, seller=show_seller(cfg), base_url=cfg["site"]["base_url"])
    legal = paid_legal_problems(out, cfg)
    if legal:
        die("paid legal copy (C-14): " + "; ".join(legal))
    prev = preview_problems(out, preview_name())
    if prev:
        die("preview build (C-17): " + "; ".join(prev[:5]) + (f" (and {len(prev) - 5} more)" if len(prev) > 5 else ""))
    return out


def main():
    try:
        out = build()
    except BuildError as e:
        print(f"BUILD FAILED: {e}", file=sys.stderr)
        return 1
    print(f"built {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
