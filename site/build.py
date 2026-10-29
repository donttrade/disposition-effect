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
  DT_REQUIRE_LAUNCH_DATE=1 fail if [legal] launch_date is empty (./site/run.sh bundle sets it)
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
import os
import re
import unicodedata
import shutil
import sys
import tomllib

from html.parser import HTMLParser as _HTMLParser

from jinja2 import Environment, FileSystemLoader, StrictUndefined
from markupsafe import Markup

SITE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(SITE)
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
ANSWER_SECTION_SKIP = {"faq-h", "ladder-h", "history"}
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
PAGES = [
    {"template": "pages/home.html", "path": "/", "requires_flag": None, "scripts": [MOTION_JS],
     "title": "donttrade - free trading tools and research on trader habits",
     "description": "Free in-browser tools: trade stats, prop challenge odds, drawdown and risk-reward. "
                    "Research on how traders behave. For firms: fixed-price measurement.",
     "og_image": "/assets/og/home.png",
     "updated": "2026-10-21"},
]

# Free tools (steps 10-12). connect-src stays 'none' (the csp_for default): these pages
# cannot send anything, which is what makes "your file is not uploaded" true.
PAGES += [
    {"template": "pages/tool-trade-stats.html", "path": "/tools/trade-stats/", "requires_flag": None,
     "modules": ["/static/js/tools/trade-stats.js"], "sample": True, "app": True, "updated": "2026-10-21",
     "crumb": "Trade stats from your own trade file",
     "title": "Free MT5 Report Analyzer: Trade Stats From Your File",
     "description": "Drop your MT5, MT4, IBKR, Tradovate or TradingView file and get profit factor, expectancy, "
                    "drawdown and streaks. Runs in your browser.",
     "if_badges": {"description": "Drop your MT5, MT4, IBKR, Tradovate or TradingView file: profit factor, expectancy, "
                                  "drawdown and streaks, with a real-or-noise check. Runs in your browser."}},
    {"template": "pages/tool-prop-sim.html", "path": "/tools/prop-challenge-simulator/", "requires_flag": None,
     "modules": ["/static/js/tools/prop-sim.js"], "sample": True, "app": True, "updated": "2026-10-21",
     "crumb": "Prop-firm challenge simulator",
     "title": "Prop Firm Challenge Simulator on Your Own Trades",
     "description": "Replay 10,000 challenges built from your own past trading days under the rules you enter. "
                    "Pass, bust and time-out shares, fully explained. Free."},
    {"template": "pages/tool-lot-size.html", "path": "/tools/lot-size-calculator/", "requires_flag": None,
     "modules": ["/static/js/tools/lot-size.js"], "app": True, "updated": "2026-10-21",
     "crumb": "Lot size calculator",
     "title": "Lot Size Calculator: Forex, Gold, Indices and Futures",
     "description": "Work out position size in lots from your balance, risk amount and stop distance. Shows the "
                    "formula with your numbers and the loss after rounding."},
    # Batch 2 (V2-BUILD-PLAN free-tools list; SEO-PLAN T4, T5, T9). Descriptive only in every build:
    # no "real or noise" check runs on these pages, so they carry no if_badges copy.
    {"template": "pages/tool-risk-reward.html", "path": "/tools/risk-reward-calculator/", "requires_flag": None,
     "modules": ["/static/js/tools/risk-reward.js"], "app": True, "updated": "2026-10-21",
     "crumb": "Risk-reward calculator",
     "title": "Risk-Reward Calculator With Break-Even Win Rate",
     "description": "Enter entry, stop and target to get your R multiple, the win rate that breaks even, and the "
                    "expectancy per trade in R, with every formula shown. Free."},
    {"template": "pages/tool-drawdown.html", "path": "/tools/drawdown-calculator/", "requires_flag": None,
     "modules": ["/static/js/tools/drawdown.js"], "sample": True, "app": True, "updated": "2026-10-21",
     "crumb": "Drawdown and recovery calculator",
     "title": "Drawdown Recovery Calculator and Max Drawdown Report",
     "description": "How much gain recovers a drawdown, plus your own largest drawdown, longest drawdown and "
                    "recovery times from your trade file. Free, in your browser."},
    {"template": "pages/tool-heatmap.html", "path": "/tools/trading-heatmap/", "requires_flag": None,
     "modules": ["/static/js/tools/heatmap.js"], "sample": True, "app": True, "updated": "2026-10-21",
     "crumb": "Your trades by hour and weekday",
     "title": "Trading Heatmap of Your Trades by Hour and Weekday",
     "description": "See your own results, win rate and trade count by the hour and weekday each trade opened, "
                    "from your trade file, in the time zone you choose. Free."},
    {"template": "pages/tools-index.html", "path": "/tools/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Free tools", "itemlist": True,
     "title": "Free Trading Tools That Run in Your Browser",
     "description": "Free tools for your own trades: trade stats from your own file, a prop-firm challenge "
                    "simulator, a lot size calculator and more. No sign-up.",
     "if_badges": {"description": "Free tools for your own trades: trade stats with a real-or-noise check, a "
                                  "prop-firm challenge simulator, a lot size calculator and more. No sign-up."}},
]

# Audience pages (step 14). Titles ≤ 60 and descriptions ≤ 155 characters (SEO-PLAN §3.1).
# Search terms behind these titles are from autocomplete only; volumes are UNVERIFIED.
FORM_JS = "/static/js/form-ref.js"
# The Product JSON-LD description (paid_report only): the same words as the pricing table row.
# R-D3 I-3b: the same text as the /pricing/ row (the JSON-LD Product description; tests/test_r_d2_pages.py checks both)
PRODUCT_TEXT = "Up to five habits measured and described in your own trades, with the dollar totals of the matching trades; up to two of them tested against chance in this version; plus one re-test 30 to 60 days after your first report."
PAGES += [
    {"template": "pages/for-traders.html", "path": "/for-traders/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Individual traders", "og_image": "/assets/og/traders.png", "scripts": [FORM_JS, MOTION_JS],
     "title": "Trader Habit Report: Waitlist and Founding Price",
     "description": "A habit report from your own MT5, IBKR, Tradovate or TradingView file, with a real-or-noise "
                    "check for each tested habit. Coming soon; join the waitlist.",
     "if_paid": {"title": "Trader Habit Report: Founding Price",
                 "description": "A habit report from your own MT5, IBKR, Tradovate or TradingView file, with a "
                                "real-or-noise check for each tested habit. Founding price, one free re-test."}},
    {"template": "pages/for-firms.html", "path": "/for-firms/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Prop firms & brokers", "og_image": "/assets/og/firms.png", "scripts": [FORM_JS, MOTION_JS],
     "title": "Disposition-Effect Measurement for Prop Firms and Brokers",
     "description": "Fixed-price measurement of whether your traders sell winners more readily than losers: a "
                    "published script, run inside your own systems."},
]

# Forms and the pages around them (step 16). Thank-you pages are noindex and stay out of the sitemap.
PAGES += [
    {"template": "pages/start.html", "path": "/start/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Start here", "og_image": "/assets/og/start.png", "scripts": [FORM_JS, START_JS],
     "title": "Start a Pilot, Apply to Partner or Join the Waitlist",
     "description": "Request a Pilot measurement, apply to partner as a journal or platform, or join the trader "
                    "waitlist. A short form or an email; no calls.",
     "if_paid": {"title": "Start a Pilot, Apply to Partner or Get the Habit Report",
                 "description": "Request a Pilot measurement, apply to partner as a journal or platform, or get "
                                "the trader habit report. A short form or an email; no calls."}},
    {"template": "pages/for-platforms.html", "path": "/for-platforms/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Journals & platforms", "og_image": "/assets/og/platforms.png", "scripts": [FORM_JS, MOTION_JS],
     "title": "Behavioural Measurement for Trading Journals and Platforms",
     "description": "Show users how readily they close winning versus losing trades, with a public script run in "
                    "your own product. Free licence for the first three partners."},
    {"template": "pages/start-thanks.html", "path": "/start/thanks/", "requires_flag": None, "noindex": True,
     "crumb": "Thank you", "title": "Request received — donttrade",
     "description": "Your request reached donttrade. You get a reply within 1 business day, Eastern Time, Monday to Friday."},
    {"template": "pages/trader-thanks.html", "path": "/for-traders/thanks/", "requires_flag": None, "noindex": True,
     "crumb": "Thank you", "title": "You are on the waitlist — donttrade",
     "description": "You joined the donttrade trader waitlist. Nothing is charged; one email when the report launches.",
     "if_paid": {"title": "Thank you — donttrade",
                 "description": "Thank you. The donttrade habit report for traders is on sale now."}},
    {"template": "pages/thanks.html", "path": "/thanks/", "requires_flag": None, "noindex": True,
     "crumb": "Thank you", "title": "Thank you — donttrade",
     "description": "Your message reached donttrade. Firms get a reply within 1 business day; traders get one email at launch.",
     "if_paid": {"description": "Your message reached donttrade. Firms get a reply within 1 business day."}},
]

# Legal pages (step 17). The French versions (/fr/…) exist only with paid_report on; the
# hreflang pair is declared only then (alternates_if_paid).
PAGES += [
    {"template": "pages/privacy.html", "path": "/privacy/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Privacy", "alternates_if_paid": [("en", "/privacy/"), ("fr", "/fr/confidentialite/"), ("x-default", "/privacy/")],
     "title": "Privacy Notice — donttrade",
     "description": "What donttrade collects and why: no cookies, free tools that read your file in your browser, "
                    "Web3Forms forms, Gmail, Stripe and your rights."},
    {"template": "pages/terms.html", "path": "/terms/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Terms", "alternates_if_paid": [("en", "/terms/"), ("fr", "/fr/conditions/"), ("x-default", "/terms/")],
     "title": "Terms, Refunds and the Pilot — donttrade",
     "description": "Payment, delivery, refund and Pilot terms for donttrade engagements, and the current status of "
                    "the trader report, in plain language."},
]

# French versions (FRENCH-LEGAL-AND-CHECKOUT-DRAFTS §8.1), habit report only, behind the same
# commerce flag as the English consumer clauses. Unreviewed drafts: lawyer + legal translator first.
PAGES += [
    {"template": "pages/fr/avant-de-payer.html", "path": "/fr/avant-de-payer/", "requires_flag": "paid_report",
     "lang": "fr", "crumb": "Avant de payer", "updated": "2026-10-21", "scripts": ["/static/js/print.js"],
     "alternates": [("fr", "/fr/avant-de-payer/"), ("en", "/pricing/"), ("x-default", "/pricing/")],
     "title": "Avant de payer : Rapport d’habitudes — donttrade",
     "description": "Ce que vous acceptez avant de payer le Rapport d’habitudes : vendeur, prix en dollars américains, "
                    "exigences techniques, remboursements et restrictions."},
    {"template": "pages/fr/conditions.html", "path": "/fr/conditions/", "requires_flag": "paid_report",
     "lang": "fr", "crumb": "Conditions", "updated": "2026-10-21",
     "alternates": [("fr", "/fr/conditions/"), ("en", "/terms/"), ("x-default", "/terms/")],
     "title": "Conditions de service et de vente — donttrade",
     "description": "Conditions du Rapport d’habitudes donttrade : prix, paiement, livraison, nouveau test, "
                    "remboursements et droit de rétractation."},
    {"template": "pages/fr/confidentialite.html", "path": "/fr/confidentialite/", "requires_flag": "paid_report",
     "lang": "fr", "crumb": "Confidentialité", "updated": "2026-10-21",
     "alternates": [("fr", "/fr/confidentialite/"), ("en", "/privacy/"), ("x-default", "/privacy/")],
     "title": "Politique de confidentialité — donttrade",
     "description": "Ce que donttrade recueille et pourquoi : aucun témoin, fichier lu dans votre navigateur, "
                    "chiffres épurés pour le rapport payant, et vos droits."},
]
PAID_ONLY_PATHS_FR = ["/fr/avant-de-payer/", "/fr/conditions/", "/fr/confidentialite/"]

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
    {"template": "pages/help.html", "path": "/help/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Questions", "scripts": ["/static/js/answers.js", "/static/js/answer-ui.js"], "title": "Questions: Prices, Refunds, Files and Privacy",
     "description": "Every answer on donttrade in one place: prices, refunds, what the free tools do with your file, "
                    "privacy and the terms, each with a link to its page."},
]

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
    {"name": "Trade stats", "href": "/tools/trade-stats/",
     "short": "Your trade file → win rate, net result and streaks.", "preview": "stats", "icon": "stats",   # 25 Oct sweep: the card line and preview
     "question": "What does my own trade history show?",
     "question_if_badges": "What does my own trade history show, and which numbers are more than noise?",
     "input": "Your trade file"},
    {"name": "Trading heatmap", "href": "/tools/trading-heatmap/",
     "short": "Your trade file → your results by hour and weekday.", "preview": "heat", "icon": "windows",   # 25 Oct sweep: the card line and preview
     "question": "How did my own trades turn out by the hour and weekday they opened?",
     "input": "Your trade file"},
    {"name": "Drawdown and recovery calculator", "href": "/tools/drawdown-calculator/",
     "short": "A drawdown or your file → how deep and how long.", "preview": "dd", "icon": "split",   # 25 Oct sweep: the card line and preview
     "question": "What gain recovers a drawdown, and how deep and long were mine?",
     "input": "A drawdown in percent, or your trade file"},
    {"name": "Prop-firm challenge simulator", "href": "/tools/prop-challenge-simulator/",
     "short": "Your file and a challenge’s rules → pass, bust or out of time.", "preview": "prop", "icon": "flag",   # 25 Oct sweep: the card line and preview
     "question": "How would my past trading days have fared under a challenge’s rules?",
     "input": "Your trade file, or win rate and average win and loss; the rules"},
    {"name": "Lot size calculator", "href": "/tools/lot-size-calculator/",
     "short": "Balance, risk and stop → the lot size.", "preview": "", "icon": "scale",   # 25 Oct sweep: the card line and preview
     "question": "How many lots match the amount I chose to risk at this stop?",
     "input": "Balance, risk amount, stop distance, value per point"},
    {"name": "Risk-reward calculator", "href": "/tools/risk-reward-calculator/",
     "short": "Entry, stop and target → the break-even win rate.", "preview": "", "icon": "percent",   # 25 Oct sweep: the card line and preview
     "question": "At what win rate does this reward-to-risk ratio break even, and what is the expectancy in R?",
     "input": "Entry, stop and target, or the ratio; optionally a win rate"},
    {"name": "Disposition-effect calculator", "href": "/tools/disposition-calculator/",
     "short": "Four counts → did you sell winners sooner than losers?", "preview": "", "icon": "hourglass",   # 25 Oct sweep: the card line and preview
     "question": "Were winning positions sold more readily than losing ones?",
     "input": "Four counts of positions sold and held"},
    {"name": "Pass-rate calculator (for firm operators)", "href": "/tools/pass-rate-calculator/",
     "short": "Cohort counts → pass and payout rate. For firms.", "preview": "", "icon": "check",   # 25 Oct sweep: the card line and preview
     "question": "What are one cohort’s evaluation pass rate and payout rate?",
     "input": "Cohort counts"},
]


def tools_for(flags):
    """TOOLS with each row's question for this build (C1: no "more than noise" without free_badges)."""
    return [{**{k: v for k, v in t.items() if k != "question_if_badges"},
             "question": t.get("question_if_badges", t["question"]) if flags["free_badges"] else t["question"]}
            for t in TOOLS]


SAMPLE_CSV = os.path.join(SITE, "static", "samples", "demo-trades.csv")
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


def report_methods():
    """The habit report's dated method versions for /corrections/#report-method (the Lead's decision, 23 Oct:
    the re-test sentence says every change is dated there). DT_REPORT_METHODS_JSON reads another file (tests).
    Fails when the page's METHOD_VERSION has no entry, so no build can promise a dated log it does not show."""
    path = os.environ.get("DT_REPORT_METHODS_JSON") or REPORT_METHODS_JSON
    with open(path, encoding="utf-8") as f:
        entries = json.load(f)["entries"]
    out = []
    for e in entries:
        if sorted(e) != ["date", "method", "text"] or not re.fullmatch(r"2[0-9]{3}-[0-9]{2}-[0-9]{2}", e["date"]) \
                or not re.fullmatch(r"[0-9]{4}-[0-9]{2}-[0-9]{2}\.[a-z0-9]+", e["method"]) or not e["text"].strip():
            die(f"report methods: malformed entry {e!r} ({path})")
        y, mo, d = (int(x) for x in e["date"].split("-"))
        out.append({**e, "date_text": f"{d} {MONTHS[mo - 1]} {y}"})
    if [e["date"] for e in out] != sorted((e["date"] for e in out), reverse=True):
        die(f"report methods: entries must be newest first ({path})")
    if len({e["method"] for e in out}) != len(out):
        die(f"report methods: a method is listed twice ({path})")
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
    """The synthetic demo file, inlined into the page inside <script type="text/csv">.

    Inlined rather than fetched because the page's CSP is connect-src 'none'. The build
    refuses anything that could end the script element early."""
    with open(SAMPLE_CSV, encoding="utf-8") as f:
        text = f.read()
    if "<" in text or "&" in text:
        die("demo-trades.csv contains '<' or '&'; it cannot be inlined safely")
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
    if path not in JOURNAL_PATHS:
        return None
    if "cloudflareinsights" in html:
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
     "description": "Your donttrade habit report is ready."},
    {"template": "pages/restore.html", "path": "/restore/", "requires_flag": "paid_report", "connect_worker": True,
     "noindex": True, "crumb": "Restore access", "modules": ["/static/js/paid/restore.js"], "title": "Restore access — donttrade",
     "description": "Reopen your donttrade habit report on this browser."},
    {"template": "pages/report.html", "path": "/report/", "requires_flag": "paid_report", "connect_worker": True,
     "noindex": True, "crumb": "Your habit report", "modules": ["/static/js/paid/report.js"], "title": "Your habit report — donttrade",
     "description": "Your donttrade habit report, built from your own trade file."},
]
PAGES += PAID_PAGES
# /pricing/ (step 15): one template. Flag off: sections stacked, firms first. Flag on:
# The printable "Before you pay" block (print.js). 25 Oct sweep: traders only, no Traders | Firms tabs.
PAGES.append({"template": "pages/pricing.html", "path": "/pricing/", "requires_flag": None,
              "scripts_if_paid": ["/static/js/print.js"], "product": PRODUCT_TEXT,
              # Tester D6: the reverse of /fr/avant-de-payer/'s alternates, so the pair counts
              "alternates_if_paid": [("en", "/pricing/"), ("fr", "/fr/avant-de-payer/"), ("x-default", "/pricing/")],
              "crumb": "Pricing", "updated": "2026-10-21", "og_image": "/assets/og/pricing.png",
              "title": "Pricing: Published Prices for Firms and Traders",
              "description": "Published prices in USD for prop firms, brokers, trading platforms and traders, the "
                             "same for everyone and fixed in writing before anyone sees data."})

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
    "/about/": [("There’s no name on it on purpose: every study",
                 "No author name is published here, on purpose (" + _SELLER_WHERE + "): every study")],
    "/code/": [("There is no name on this site; the scripts are what you check instead.",
                "No author name is published on this site (" + _SELLER_WHERE + "); the scripts are what you check "
                "instead.")],
    # 29 Oct (owner): sample data is labelled with the one word "Example", never "made-up"
    "/tools/disposition-calculator/": [
        ('id="dc-example">Fill a made-up example</button>', 'id="dc-example">Try with example data</button>'),
        ("The example (420, 1,780, 260, 2,240) is made-up. It is not real trading data.",
         "Example data: 420, 1,780, 260 and 2,240.")],
    "/tools/pass-rate-calculator/": [
        ('id="pr-example">Fill a made-up example</button>', 'id="pr-example">Try with example data</button>'),
        ("The example (1,000 started, 150 open, 170 passed, 40 paid, 800 traders) is made-up. It is not a real firm’s data.",
         "Example data: 1,000 started, 150 open, 170 passed, 40 paid, 800 traders.")],
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
        pages.append(page)
    return pages


def lifted_fragment(slug):
    with open(os.path.join(LIFTED_DIR, slug + ".html"), encoding="utf-8") as f:
        return f.read()


LIFTED = lifted_pages()
PAGES += LIFTED
LIFTED_PATHS = [p["path"] for p in LIFTED]

# Delivery plan C-12 final (Tester T-3 T3-E): with paid_report on, /sample-report/ is no longer the lifted research
# figure but a real habit report: dt-private's analyse() on a committed synthetic file
# (site/config/sample-report.report.json, made by tests/fixtures/paid/make_sample_report.py), rendered by the real
# report.js. The lifted page stays in flag-off builds, where its lead already says it is not the trader report.
PAID_REPLACES_LIFTED = ("/sample-report/",)
SAMPLE_REPORT_JSON = os.path.join(SITE, "config", "sample-report.report.json")
SAMPLE_PAGE = {"template": "pages/sample-report.html", "path": "/sample-report/", "requires_flag": None,
               "modules": ["/static/js/paid/sample.js"], "crumb": "Sample habit report", "og_image": "/assets/og/sample-report.png",
               "title": "Example habit report — donttrade", "sample_report": True,
               "description": "An example of the paid habit report: the report's own engine and page, run on example data. "
                              "Not advice.", "updated": "2026-10-23"}


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
PAID_ONLY_PATHS = PAID_APP_PATHS + PAID_ONLY_PATHS_FR


# The footer's privacy sentences. One wording for template pages (partials/footer.html) and
# passthrough pages (PASSTHROUGH_CHROME), so the two can never disagree with /privacy/.
def footer_privacy(flags):
    if flags["analytics"]:
        parts = ["This site sets no cookies. Visits are counted with Cloudflare Web Analytics, which sets no cookie."]
    else:
        parts = ["This site sets no cookies and runs no analytics."]
    if flags["paid_report"]:
        # D4: true once /welcome/ keeps the access key (localStorage and IndexedDB)
        # NIT 13: complete, matching /privacy/#report (the fingerprints kept for the re-test match)
        # C-14: the server keeps more than fingerprints (a purchase record, hourly counters; /privacy/#report),
        # so "only" now bounds what is kept OF the trade numbers, not what the server keeps.
        parts.append("It stores your light/dark choice in your own browser and, if you buy the habit report, your "
                     "access key there too. For that report your browser sends our server only stripped trade "
                     "numbers. The server does not keep them: of those numbers it keeps only a scrambled fingerprint "
                     "of each trade row from your first report, to match a re-test to the same history. Your file "
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
    "/fr/avant-de-payer/", "/fr/conditions/", "/fr/confidentialite/"})
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
    # R5: the old nav says the trader report is "coming soon"; with paid_report on it is sold
    ('Individual traders <span class="soon">coming soon</span></a>', trader_nav_label, 2),  # desktop nav + mobile menu
]


def fix_passthrough_chrome(text, rel, flags):
    for old, new, expected in PASSTHROUGH_CHROME:
        n = text.count(old)
        if (expected is None and n < 1) or (expected is not None and n != expected):
            die(f"passthrough chrome: {rel} holds {old!r} {n} time(s), expected {expected or 'at least 1'}")
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


FLAGS = ("paid_report", "analytics", "trader_first_home", "pilot_checkout", "free_badges", "journal", "ask_box")
OPTIONAL_FLAGS = {"pilot_checkout": False, "free_badges": False, "journal": False, "ask_box": False}  # older site.toml files may lack the line
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
    "analytics": ({"cf_beacon_token"}, {"cf_beacon_token"}),
    "stripe": ({"mode"}, {"mode"}),
    "forms": ({"endpoint", "firm_key", "trader_key", "redirect_firm", "redirect_trader"}, None),
    "worker": ({"api_base"}, {"api_base"}),
    "legal": ({"launch_date", "cloudflare_pages_since", "disclaimer_short", "disclaimer_long"},
              {"launch_date", "cloudflare_pages_since", "disclaimer_short", "disclaimer_long",
               "show_seller_for_pilot"}),
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
    "DT_ALLOW_NO_STRIPE_LINK": "no Stripe Payment Link for the habit report",
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


def set_launch_date(legal, toml_path, today=None):
    """Manager C3: [legal] launch_date (YYYY-MM-DD; empty = the build date) dates every launch
    statement. Sets legal.terms_version (ISO, the terms/privacy version) and legal.launch_human
    ("23 Oct 2026"). A future date fails: no page may state a date that has not come yet.
    DT_REQUIRE_LAUNCH_DATE=1 (./site/run.sh bundle) refuses an empty one."""
    import datetime as dt
    today = today or dt.date.today()
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
    today = today or dt.date.today()
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


CHANNEL_HOSTS = {"x.com", "github.com", "donttrade.substack.com", "www.linkedin.com", "www.tiktok.com", "www.youtube.com",
                 "www.instagram.com"}
CHANNEL_FIELDS = ("id", "name", "url", "text", "icon", "rel_me")
BRAND_ICONS = ("x", "github", "substack", "tiktok", "instagram", "youtube")


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
    set_hosting_date(cfg["legal"], toml_path)
    cfg["site"].setdefault("manual_restore", True)
    if type(cfg["site"]["manual_restore"]) is not bool:
        die(f"[site] manual_restore must be true or false, not {cfg['site']['manual_restore']!r} ({toml_path})")
    flags = cfg["flags"]
    check_flags(flags, toml_path)
    if flags["trader_first_home"] != flags["paid_report"]:
        die(f"flag mismatch: trader_first_home={flags['trader_first_home']} must equal "
            f"paid_report={flags['paid_report']} ({toml_path})")
    if flags["analytics"] and not cfg["analytics"]["cf_beacon_token"]:
        die("analytics = true but [analytics] cf_beacon_token is empty")
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


def usd(n):
    """$745, $2,500 — prices are whole dollars on this site."""
    if n != int(n):
        die(f"price {n} is not a whole number of dollars")
    return "${:,}".format(int(n))


def isodate(human):
    """"23 Oct 2026" -> "2026-10-23" (the price-history rows are written in the human form)."""
    import datetime as dt
    return dt.datetime.strptime(human, "%d %b %Y").date().isoformat()


def usd_fr(n):
    """39,00 $ US — Québec style (FRENCH-LEGAL: amounts written « 79,00 $ US »)."""
    if n != int(n):
        die(f"price {n} is not a whole number of dollars")
    return "{:,}".format(int(n)).replace(",", "\u00a0") + ",00\u00a0$\u00a0US"


def csp_for(page, cfg):
    if os.path.join(page["path"].strip("/"), "index.html") in PASSTHROUGH_CSP_PAGES:
        # Manager C4 after the merge of steps 28–29: the lifted old calculators keep the strict
        # no-network policy they had as passthrough pages (connect, worker and form-action 'none'),
        # now without 'unsafe-inline'. With analytics on, the beacon host is the only addition,
        # as on every other tool page (plan DoD: "connect-src 'none' (or the beacon host only)").
        a = cfg["flags"]["analytics"]
        return ("default-src 'self'; script-src 'self'" + (" https://static.cloudflareinsights.com" if a else "") +
                "; style-src 'self'; img-src 'self' data:; font-src 'self'; connect-src 'none'" +
                (" https://cloudflareinsights.com" if a else "") +
                "; worker-src 'none'; form-action 'none'; base-uri 'none'; object-src 'none'")
    connect = page.get("connect_src", "'none'")
    if page.get("connect_worker"):
        connect = "'self' " + cfg["worker"]["api_base"]
    beacon = cfg["flags"]["analytics"] and not page.get("no_analytics")   # D12: never on the journal
    if beacon:
        connect += " https://cloudflareinsights.com"
    script = "'self'" + (" https://static.cloudflareinsights.com" if beacon else "")
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


def jsonld(page, cfg, html, flags, products):
    """One @graph per page. No address, phone, rating or review anywhere (SEO-PLAN §3.2)."""
    base = cfg["site"]["base_url"]
    org = {"@id": base + "/#org"}
    graph = []
    if page["path"] == "/":
        graph.append({"@type": "WebSite", "@id": base + "/#website", "name": cfg["site"]["name"],
                      "url": base + "/", "publisher": org})
        graph.append({"@type": "Organization", "@id": base + "/#org", "name": cfg["site"]["name"],
                      "url": base + "/", "email": cfg["site"]["contact_email"], "sameAs": [c["url"] for c in cfg["channels"]]})
    else:
        items = [(n, base + u if u else None) for n, u in crumb_items(page)]
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, **({"item": u} if u else {})}
            for i, (n, u) in enumerate(items)]})
    if page.get("article"):  # lifted study pages: their old Article, by the site Organization
        graph.append({**page["article"], "author": org, "publisher": org})
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
        r = products["report39"]
        graph.append({"@type": "Product", "name": r["name"], "description": page["product"], "brand": org,
                      "offers": {"@type": "Offer", "price": str(int(r["price_usd"])), "priceCurrency": "USD",
                                 "availability": "https://schema.org/InStock", "url": base + page["path"]}})
    faq = faq_from(html)
    if faq:
        graph.append({"@type": "FAQPage", "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}} for q, a in faq]})
    data = json.dumps({"@context": "https://schema.org", "@graph": graph}, ensure_ascii=False, sort_keys=True)
    return '<script type="application/ld+json">' + data.replace("</", "<\\/") + "</script>"


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
        robots += [f"Disallow: {p}" for p in PAID_APP_PATHS]
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


def build():
    cfg, prices, private = load_config()
    flags = cfg["flags"]
    out = os.environ.get("DT_OUT") or os.path.join(SITE, "_site")
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)

    owned = {}
    for page in PAGES:
        if page["requires_flag"] and not flags[page["requires_flag"]]:
            continue
        if flags["paid_report"] and page.get("lifted") and page["path"] in PAID_REPLACES_LIFTED:
            page = SAMPLE_PAGE   # C-12 final: the real sample report replaces the lifted research figure
        owned[os.path.relpath(out_file(out, page["path"]), out)] = page

    check_hero_dashboard()

    # 1. passthrough of every docs/ file a template does not own yet. docs/static/ is the last bundle's
    # copy of site/static/ (step 30), never a source: skipped, so a file deleted from site/static/
    # (the old hero .webp images, motion plan) does not come back from docs/.
    copy_tree_sorted(DOCS, out, skip=lambda rel: rel in owned or rel.startswith("static" + os.sep))
    for rel in passthrough_pages(owned):
        fp = os.path.join(out, rel)
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        text = fix_passthrough_chrome(text, rel, flags)
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
                or (not flags["journal"] and (rel.startswith(JOURNAL_JS_DIR) or rel == os.path.join("css", "journal.css"))))   # ARCHITECT-V3 D7: out of the build until approved
    copy_tree_sorted(os.path.join(SITE, "static"), os.path.join(out, "static"), skip=static_left_out)
    # 3. dev pages, only on request; never bundled
    if os.environ.get("DT_DEV") == "1":
        copy_tree_sorted(os.path.join(SITE, "dev"), os.path.join(out, "dev"))

    env = Environment(loader=FileSystemLoader(os.path.join(SITE, "templates")), undefined=StrictUndefined,
                      autoescape=True, keep_trailing_newline=True)
    env.filters["usd"] = usd
    env.filters["usd_fr"] = usd_fr
    env.filters["isodate"] = isodate
    env.globals["crumb_items"] = crumb_items
    products = {p["id"]: p for p in prices["products"]}
    nav = nav_for(cfg["nav"], flags)
    base_ctx = {"site": cfg["site"], "flags": flags, "nav": nav, "nav_current": lambda pg: nav_current(nav, pg),
                "footer": cfg["footer"], "vt_pages": VT_PAGES, "mkt_pages": MOTION_PAGES, "channels": cfg["channels"],
                "legal": cfg["legal"], "forms": cfg["forms"], "analytics": cfg["analytics"],
                "worker": cfg["worker"], "prices": prices, "products": products, "private": private,
                "stripe_mode": cfg["stripe"]["mode"], "lift": lift_sections, "tools": tools_for(flags),
                "tool_previews": tool_previews(), "evidence": evidence(), "latest": latest(), "footer_privacy": footer_privacy(flags), "show_seller": show_seller(cfg),
                "strings": read_toml(os.path.join(SITE, "config", "strings.toml"), "strings.toml"),
                "paid_method": paid_method(),
                "report_link_fr": report_link_fr(products["report39"], cfg["stripe"]["mode"]),
                "preview": preview_name()}
    built, rendered = [], []

    def render(rel, page, **more):
        page = {"scripts": [], "modules": [], "og_image": "/assets/og/default.png", "lang": "en",
                "alternates": [], **page}
        if flags["paid_report"]:
            page["scripts"] = page["scripts"] + page.get("scripts_if_paid", [])
            page["alternates"] = page.get("alternates_if_paid", page["alternates"])
            page.update(page.get("if_paid", {}))  # R5: title/description that sell instead of "waitlist"
        if flags["free_badges"]:
            page.update(page.get("if_badges", {}))  # C1: the copy that names the free check
        if not flags["ask_box"]:
            page["scripts"] = [s for s in page["scripts"] if s not in ASK_SCRIPTS]
        extra = {"sample_csv": sample_csv()} if page.get("sample") else {}
        if page.get("sample_report") or (page["path"] in ("/", "/for-traders/") and flags["paid_report"]):  # 25 Oct: the home showcase; sweep 2: the report card on /for-traders/
            rep_ = sample_report()
            extra["sample_report"] = rep_
            extra["sample_report_json"] = Markup(json.dumps(rep_, sort_keys=True, ensure_ascii=False).replace("</", "<\\/"))
        if page.get("lifted"):
            extra["lifted_html"] = Markup(paid_lifted(page["path"], lifted_fragment(page["lifted"]), flags["paid_report"]))
            if page["path"] == "/corrections/":
                extra["report_methods"] = report_methods()
        line = Markup(business_id_line(cfg, private, "legal", url=page["path"], lang=page["lang"]))
        html = env.get_template(page["template"]).render(page=page, csp=csp_for(page, cfg), business_id_line=line,
                                                         **base_ctx, **extra, **more)
        if not page.get("lifted"):
            html = add_faq_ids(html)   # Q-A1: a stable id per FAQ question (lifted pages keep their frozen ids)
        if html.count(LD_MARKER) != 1:
            die(f"{page['template']}: the JSON-LD marker must appear exactly once")
        html = html.replace(LD_MARKER, jsonld(page, cfg, html, flags, products))
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
    version_assets(out, left_out=static_left_out)

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
