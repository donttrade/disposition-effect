#!/usr/bin/env python3
"""lint.py — wording, flag and leak rules for the v2 site (and for report strings).

    python3 checks/lint.py site/_site                  # lint a build; flags read from the build
    python3 checks/lint.py site/_site --paid --pilot   # or state them; a mismatch is reported
    from lint import lint_text                                  # lint any text (report strings)

Rules (banned.toml): A3 banned words outside allowlisted negations/disclaimer; AI-tell
words; tally.so; "nothing leaves"-type claims when a paid flow exists; "no analytics"
when analytics is on; $ amounts not from prices.json; flag-gated strings with the paid
flag off (seller name/placeholders, trader Stripe links, Product JSON-LD, paid markup);
/dev/ in the build; secret patterns; the footer business line on every page exactly
once while a commerce flag is on (the full one, its address the private.toml one, only on
build.ADDRESS_LINE_PATHS; the short one without the address elsewhere), none while both are off.

Scope: every page the templates own (new design) gets the full rules. A page lifted word for
word from the pre-v2 site (steps 28–29, build.LIFTED_PATHS) gets the full rules on everything
outside its frozen body (head, meta, JSON-LD, header, footer), and on the frozen body
(<!--frozen:start-->…<!--frozen:end-->) the passthrough rules plus checks/compare.py: the
frozen text must equal the old page's word for word, so the exemption from the word list
covers only text that was already published and may not change (V2 plan: no sentence changes
to study bodies). Any other page still passed through from docs/ gets the passthrough rules.
"""
import json
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, HERE)

with open(os.path.join(HERE, "banned.toml"), "rb") as _f:
    RULES = tomllib.load(_f)


# Brand P1a Tester D1: the rules match the text as a browser shows it. Inside a phrase, a space matches
# any run of whitespace (line breaks and tabs in a template, double spaces: a browser folds them into one
# space) and hyphens ("beat-the-market"). An apostrophe matches ' and ’ ("you're", "you’re").
PHRASE_GAP = r"[\s\-‐‑]+"


def _phrase_re(p):
    """Whole-word match on both ends where the phrase starts/ends with a word character. A word that ends
    in * matches any ending (Tester D2: "skill*" = skills, skilled, skillset, skilfully...), as in [words_fr]."""
    parts = []
    for w in p.split(" "):
        star = w.endswith("*") and len(w) > 1
        esc = re.sub(r"['’]", lambda _: "['’]", re.escape(w[:-1] if star else w))
        parts.append(esc + (r"[^\W\d_]*" if star else ""))
    body = PHRASE_GAP.join(parts)
    left = r"(?<![A-Za-z0-9])" if re.match(r"\w", p) else ""
    right = r"(?![A-Za-z0-9])" if re.search(r"[\w*]$", p) else ""
    return re.compile(left + body + right, re.IGNORECASE)


WORDS = [(cat, w, _phrase_re(w)) for cat, ws in RULES["words"].items() for w in ws]
ALLOW = [_phrase_re(p) for p in RULES["allow"]["phrases"]]
ALLOW += [re.compile(p, re.IGNORECASE) for p in RULES["allow"].get("patterns", [])]
SECRETS = [re.compile(p) for p in RULES["secrets"]["patterns"]]
RESTORE_EMAIL = [re.compile(p, re.IGNORECASE) for p in RULES["claims"]["restore_email"]]
RESTORE_EMAIL_ALLOW = [re.compile(re.escape(p), re.IGNORECASE) for p in RULES["claims"]["restore_email_allow"]]


_W = RULES["claims"]
WAIVE = re.compile(r"(?<![\w])(?:" + "|".join(_W["waive_dispute_waive"]) + r")(?![\w])", re.IGNORECASE)
DISPUTE = re.compile(r"(?<![\w])(?:" + "|".join(_W["waive_dispute_target"]) + r")(?![\w])", re.IGNORECASE)
REASSURE = re.compile(r"(?:" + "|".join(_W["waive_dispute_reassure"]) + r")$", re.IGNORECASE)
_FILL_WORDS = [f for f in _W["waive_dispute_filler"] if not f.endswith("['’]")]
_FILL_ELIDED = [f for f in _W["waive_dispute_filler"] if f.endswith("['’]")]   # d' l' : no space after
_FILL = r"(?:(?:" + "|".join(_FILL_WORDS) + r")\s+|(?:" + "|".join(_FILL_ELIDED) + r")\s*)"
_NEG = "|".join((r"(?<![\w])" if re.fullmatch(r"\w+", n) else "") + n for n in _W["waive_dispute_negation"])  # n't: no boundary before
NEGATED_DISPUTE = re.compile(r"(?:" + _NEG + r")(?![\w])\s*" + _FILL + r"{0,3}?"
                             r"(?:" + "|".join(_W["waive_dispute_target"]) + r")(?![\w])", re.IGNORECASE)
FIXED_REFUSAL = re.compile(r"(?<![\w])(?:" + "|".join(_W["waive_dispute_fixed"]) + r")(?![\w])", re.IGNORECASE)
SENTENCE_END = re.compile(r"(?<=[.!?;:])\s+|\n+|\s+[•·]\s+")


def sentences(text):
    return [x for x in SENTENCE_END.split(text) if x.strip()]


def waive_dispute_claims(text, where):
    """Decision 21 Oct: no wording that asks a client to waive (give up, agree not to use) a
    dispute or chargeback right. Checked one sentence at a time (Tester delta D5), with the three
    rules in banned.toml: a waive-word and a dispute-word in one sentence (not after a reassurance
    such as "we never ask you to"), a negated dispute verb, or a fixed refusal."""
    out = []
    for sent in sentences(text):
        flat = " ".join(sent.split())
        hit = None
        if DISPUTE.search(flat):
            for m in WAIVE.finditer(flat):
                if not REASSURE.search(flat[:m.start()]):
                    hit = m
                    break
        hit = hit or NEGATED_DISPUTE.search(flat) or FIXED_REFUSAL.search(flat)
        if hit:
            out.append(("claim:waive_dispute", where, flat[:300]))
    return out


DATED_PRICING = [_phrase_re(p) for p in RULES["claims"]["dated_pricing"]]


SCARCITY = [re.compile(p, re.IGNORECASE) for p in RULES["claims"]["scarcity"]]


def scarcity_claims(text, where):
    """Owner decision 23 Oct: no "spots left", "only N left", countdown or urgency wording anywhere (a static
    "first 100 buyers" line is fine)."""
    return [("claim:scarcity", where, text[max(0, m.start() - 40):m.end() + 40].replace("\n", " "))
            for rx in SCARCITY for m in rx.finditer(text)]


def dated_pricing_claims(text, where, source=None):
    """Owner decision 21 Oct ~11:00: no "launch pricing" / "valid before <date>" wording, and no
    priceValidUntil in a page's JSON-LD (source: the raw page, when there is one)."""
    out = [("claim:dated_pricing", where, text[max(0, m.start() - 40):m.end() + 40].replace("\n", " "))
           for rx in DATED_PRICING for m in rx.finditer(text)]
    if source is not None and re.search(r"priceValidUntil", source, re.IGNORECASE):
        out.append(("claim:dated_pricing", where, "priceValidUntil in the page source"))
    return out


NOT_ON_SALE = [_phrase_re(p) for p in RULES["claims"]["not_on_sale"]]
NOT_ON_SALE_ALLOW = [re.compile(re.escape(p), re.IGNORECASE) for p in RULES["claims"]["not_on_sale_allow"]]


def not_on_sale_claims(text, where):
    """R5: with paid_report on, no page may say the report is not on sale or offer the waitlist."""
    for a in NOT_ON_SALE_ALLOW:
        text = a.sub(lambda m: " " * len(m.group(0)), text)
    return [("claim:not_on_sale", where, text[max(0, m.start() - 40):m.end() + 40].replace("\n", " "))
            for rx in NOT_ON_SALE for m in rx.finditer(text)]


TALLY = re.compile(r"(?<![A-Za-z0-9])tally(?![A-Za-z0-9])", re.IGNORECASE)


def tally_mentions(html, where):
    """B1: Tally is no longer used (the forms are Web3Forms), so the word may not appear anywhere
    in a page, visible or not, including tally.so links: checked in the raw HTML, in the readable
    text and in every decoded, percent-decoded URL attribute (NIT 1)."""
    from urllib.parse import unquote
    p = _parse(html)
    found = [m.group(0) for m in TALLY.finditer(html)]
    for v in p.urls:
        found += [m.group(0) for m in TALLY.finditer(normalise(unquote(v)))]
    found += [m.group(0) for m in TALLY.finditer(normalise("".join(p.text) + " " + " ".join(p.attrs)))]
    found += [m.group(0) for m in TALLY.finditer(meta_text(html))]
    return [("tally", where, f"“{w}”") for w in dict.fromkeys(found)][:1] if found else []


def restore_email_claims(text, where):
    """Restore-by-email is not in v1 (decision 20 Oct): any wording that offers it fails,
    on every page and in the paid scripts' messages. The listed negations are allowed."""
    for a in RESTORE_EMAIL_ALLOW:
        text = a.sub(lambda m: " " * len(m.group(0)), text)
    return [("claim:restore_email", where, m.group(0)) for rx in RESTORE_EMAIL for m in rx.finditer(text)]


_JS_ESC = re.compile(r"\\(?:x([0-9A-Fa-f]{2})|u\{([0-9A-Fa-f]{1,6})\}|u([0-9A-Fa-f]{4})|(.))", re.S)
_JS_SIMPLE = {"n": "\n", "t": "\t", "r": "\r", "b": "", "f": "", "v": "", "0": "", "\n": ""}


def _js_unescape(body):
    def one(m):
        code = m.group(1) or m.group(2) or m.group(3)
        if code:
            return chr(int(code, 16))
        c = m.group(4)
        return _JS_SIMPLE.get(c, c)
    return _JS_ESC.sub(one, body)


def js_strings(code):
    """The string literals of a script (comments dropped), with JS escapes decoded (\\x65,
    \\u0065, \\u{65}): the text a script can put on a page. In a template literal a ${'…'} or
    ${"…"} part is replaced by its text and any other ${…} part is dropped (NIT 1)."""
    out = []
    for m in re.finditer(r"//[^\n]*|/\*.*?\*/|'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`", code, re.S):
        tok = m.group(0)
        if tok[0] in "'\"":
            out.append(_js_unescape(tok[1:-1]))
        elif tok[0] == "`":
            body = re.sub(r"\$\{\s*(['\"])((?:(?!\1)[^\\]|\\.)*)\1\s*\}", lambda x: x.group(2), tok[1:-1])
            body = re.sub(r"\$\{[^}]*\}", "", body)
            out.append(_js_unescape(body))
    return normalise("\n".join(out))


# ------------------------------------------------------------------ text a person can read (NIT 1)
# The page is parsed (html.parser decodes every entity), so a banned word cannot hide behind an
# entity, a tag inside the word (Ta<span>lly</span>, <wbr>, an empty <b></b>, a comment), an
# invisible character (zero-width, soft hyphen: Unicode Cf, stripped), a compatibility form
# (full-width letters, NBSP: NFKC), a Cyrillic or Greek look-alike letter (folded to Latin) or
# a single-quoted attribute. Inline elements join their text; every other element is a break.
# Brand P1a Tester D3: label, img, svg (and the shapes inside it), picture/source and output are inline
# by default too, so "s<label>eal</label>", "s<img alt=''>eal" and "se<svg></svg>al" read "seal".
INLINE = frozenset("a abbr b bdi bdo cite code data del dfn em font i ins kbd mark nobr q s samp small span "
                   "strong sub sup time tt u var wbr label img svg g path use circle rect line polyline polygon "
                   "ellipse picture source output".split())
READ_ATTRS = ("alt", "title", "aria-label", "placeholder", "aria-description")
# D3: an <input>'s value is drawn on the page (the label of a button-type input, the text in a text box);
# not for the types that never show it as text
INPUT_VALUE_HIDDEN = frozenset("hidden checkbox radio file color range image password".split())
META_NAMES = re.compile(r"description|og:[\w:]+|twitter:[\w:]+", re.I)
CONFUSABLES = str.maketrans("АВЕКМНОРСТХаеорсухіјѕԁԛԝΑΒΕΖΗΙΚΜΝΟΡΤΥΧαοντ",
                            "ABEKMHOPCTXaeopcyxijsdqwABEZHIKMNOPTYXaovt")


def normalise(text):
    """Cf characters removed, NFKC, Cyrillic/Greek look-alikes folded to Latin."""
    import unicodedata
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return unicodedata.normalize("NFKC", text).translate(CONFUSABLES)


def _parse(html):
    """{text, attrs, meta, ld, urls}: the readable parts of a page, already decoded."""
    from html.parser import HTMLParser

    class P(HTMLParser):
        def __init__(self):
            super().__init__(convert_charrefs=True)
            self.text, self.attrs, self.meta, self.ld, self.urls = [], [], [], [], []
            self.skip = None   # inside <script>/<style>: (tag, is_ld)

        def handle_starttag(self, tag, attrs):
            a = {k.lower(): (v or "") for k, v in attrs}
            for k, v in a.items():
                if k in READ_ATTRS:
                    self.attrs.append(v)
                if k in ("href", "src", "action", "content", "srcset", "formaction", "data"):
                    self.urls.append(v)
            if tag == "input" and a.get("value") and a.get("type", "text").lower() not in INPUT_VALUE_HIDDEN:
                self.attrs.append(a["value"])
            if tag == "meta" and META_NAMES.fullmatch(a.get("name") or a.get("property") or ""):
                self.meta.append(a.get("content", ""))
            if tag in ("script", "style"):
                self.skip = (tag, tag == "script" and a.get("type", "").lower() == "application/ld+json")
                self._buf = []
                return
            if tag not in INLINE:
                self.text.append(" ")

        handle_startendtag = handle_starttag

        def handle_endtag(self, tag):
            if self.skip and tag == self.skip[0]:
                if self.skip[1]:
                    self.ld.append("".join(self._buf))
                self.skip = None
                return
            if tag not in INLINE:
                self.text.append(" ")

        def handle_data(self, data):
            if self.skip:
                self._buf.append(data)
            else:
                self.text.append(data)

    p = P()
    p.feed(html)
    p.close()
    return p


def visible_text(html):
    """The page text plus alt/title/aria-label/placeholder, decoded and normalised."""
    p = _parse(html)
    return normalise("".join(p.text) + " " + " ".join(p.attrs))


def meta_text(html):
    """Text that search engines and link previews show: <meta> description/og/twitter content
    and every string value in JSON-LD blocks, decoded and normalised."""
    p = _parse(html)
    parts = list(p.meta)
    for block in p.ld:
        try:
            data = json.loads(block)
        except ValueError:
            parts.append(block)  # not JSON: lint it as text rather than skip it
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, str):
                parts.append(x)
            elif isinstance(x, dict):
                stack.extend(x.values())
            elif isinstance(x, list):
                stack.extend(x)
    import html as _h
    return normalise(_h.unescape("\n".join(parts)))


def readable_text(html):
    """Everything a person or a search result can read on a page: visible text, alt/title/
    aria-label/placeholder, meta and og descriptions, JSON-LD strings."""
    return visible_text(html) + "\n" + meta_text(html)


FR_WORDS = [(w, re.compile(r"(?<![\w])" + re.escape(w.rstrip("*")) + (r"\w*" if w.endswith("*") else r"(?![\w])"),
                           re.IGNORECASE)) for w in RULES["words_fr"]["banned"]]


def strip_disclaimers(html):
    """Remove elements marked data-lint="disclaimer" (the French disclaimer blocks, FRENCH-LEGAL §8.3),
    the only places where conseil/recommand* may appear. Marked elements must not nest their own tag."""
    return re.sub(r'(?s)<(\w+)\b[^>]*\bdata-lint="disclaimer"[^>]*>.*?</\1>', " ", html)


def lint_text_fr(text, where="text"):
    """French banned words (FRENCH-LEGAL-AND-CHECKOUT-DRAFTS §8.3), outside disclaimer blocks."""
    out = []
    for w, rx in FR_WORDS:
        for m in rx.finditer(text):
            ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            out.append(("banned:fr", where, f"“{w}” in …{ctx}…"))
    return out


def word_hits(text, where, cats=None):
    """The [words] list (only the groups in cats, when given), outside the [allow] phrases."""
    out = []
    masked = text
    for a in ALLOW:
        masked = a.sub(lambda m: " " * len(m.group(0)), masked)
    for cat, w, rx in WORDS:
        if cats is not None and cat not in cats:
            continue
        for m in rx.finditer(masked):
            ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            out.append((f"banned:{cat}", where, f"“{w}” in …{ctx}…"))
    return out


# ARCHITECT-BRAND §1.5–1.6: the two brand groups. Tester D4: they also hold where a link preview or a
# feed reader shows the words, outside the frozen STUDY bodies (the only text that keeps "sealed").
BRAND_GROUPS = ("seal_words", "skill_claims")
STUDY_PAGE = re.compile(r"^/research/[^/]+/$")


def frozen_brand_problems(body, path):
    """A lifted page that is not a study (About, For researchers, the research index...): its frozen body
    is still word for word, but "seal" may not be in it (link and teaser text about the studies)."""
    if STUDY_PAGE.match(path):
        return []
    return word_hits(readable_text(body), path, ("seal_words",))


def feed_text(xml):
    """The text a feed reader shows: every element's text and CDATA, entities decoded twice (a summary
    may hold escaped HTML), tags of that HTML dropped, normalised."""
    import html as _h
    t = re.sub(r"(?s)<!\[CDATA\[(.*?)\]\]>", lambda m: _h.escape(m.group(1)), xml)
    t = re.sub(r"<[^>]+>", "\n", t)
    t = _h.unescape(_h.unescape(t))
    return normalise(re.sub(r"<[^>]+>", " ", t))


def feed_problems(xml, where):
    return word_hits(feed_text(xml), where, BRAND_GROUPS) if re.search(r"<(?:feed|rss)\b", xml) else []


def lint_text(text, where="text", paid=False, analytics=False, english=True):
    """Wording rules on plain text. Returns a list of (rule, where, detail).
    english=False (French pages) skips the English word list; lint_text_fr covers those pages."""
    out = word_hits(text, where) if english else []
    if True:  # D9: false next to the paid pipeline, so banned on every page, flag or not
        for c in RULES["claims"]["no_upload"]:
            if _phrase_re(c).search(text):
                out.append(("claim:no_upload", where, c))
    if analytics:
        for c in RULES["claims"]["no_analytics"]:
            if _phrase_re(c).search(text):
                out.append(("claim:no_analytics", where, c))
    out += restore_email_claims(text, where)
    out += waive_dispute_claims(text, where)
    out += dated_pricing_claims(text, where)
    out += scarcity_claims(text, where)
    out += free_forever_claims(text, where)
    return out


# Owner decision Q4 (21 Oct ~18:30): "free forever" applies only to the journal's local features, and the
# page says why (it runs on the visitor's device and costs us nothing to run). Any sentence with the claim
# must name the journal, and the same text must give the reason.
FREE_FOREVER = re.compile(r"\bfree[\s-]+forever\b", re.IGNORECASE)
FREE_FOREVER_REASON = "costs us nothing to run"


def free_forever_claims(text, where):
    out = []
    for s in sentences(text):
        if FREE_FOREVER.search(s) and "journal" not in s.lower():
            out.append(("claim:free_forever", where, f"“free forever” outside the journal: {s.strip()[:120]}"))
    if FREE_FOREVER.search(text) and FREE_FOREVER_REASON not in text:
        out.append(("claim:free_forever", where, f"“free forever” without its reason (“{FREE_FOREVER_REASON}”)"))
    return out


HERO_DASH = os.path.join(REPO, "site", "templates", "partials", "hero_dashboard.html")


def without_hero_dash(html, where):
    """The home hero (motion plan D1) is the free tool's own output on the synthetic sample file:
    its dollar figures are sample trade results, not prices. They are left out of the price check
    only on / and only when the block is byte-identical to the generated partial
    (checks/make_hero_dashboard.py), so an edited hero, or a price added to it, is checked as usual."""
    if where != "/":
        return html
    with open(HERO_DASH, encoding="utf-8") as f:
        body = f.read().split("#}", 1)[1].strip()
    html = html.replace(body, " ") if html.count(body) == 1 else html
    return without_showcase(html)


SHOWCASE_RE = re.compile(r'(?s)<table class="shot-table">.*?</table>')


def without_showcase(html):
    """The home showcase (25 Oct) shows the sample report's own dollar totals (site/config/sample-report.report.json,
    a made-up file). The table is left out of the price check only when it is the one table on / and every amount in
    it is one of the sample's dollar totals, so any other figure, or a price, put there is still checked."""
    tables = SHOWCASE_RE.findall(html)
    if len(tables) != 1:
        return html
    with open(os.path.join(REPO, "site", "config", "sample-report.report.json"), encoding="utf-8") as f:
        sample = {round(abs(h["dollars"]["amount"]), 2) for h in json.load(f)["habits"] if h.get("dollars")}
    from harvest_prices import amounts_in
    found = amounts_in(tables[0])
    if not found or any(round(a, 2) not in sample for a in found):
        return html
    return html.replace(tables[0], " ")


SAMPLE_OUT_RE = re.compile(r"(?s)<!--sample-out-->.*?<!--/sample-out-->")
# Tester M3 (sweep 1): only the pages that carry the previews, and only the two preview elements
SAMPLE_OUT_PATHS = frozenset({"/", "/tools/", "/tools/trade-stats/"})
SAMPLE_OUT_ELEMENT = re.compile(r'(?s)^<!--sample-out-->(?:<span class="tp tp-stats" aria-hidden="true">|'
                                r'<div class="shot-card">\s*<table class="mini-shot">)')


def tool_preview_amounts():
    """Every dollar figure the tools printed on the synthetic sample file, as captured by
    checks/make_tool_previews.py into site/config/tool_previews.json."""
    with open(os.path.join(REPO, "site", "config", "tool_previews.json"), encoding="utf-8") as f:
        text = json.dumps(json.load(f), ensure_ascii=False)
    from harvest_prices import amounts_in
    return {round(a, 2) for a in amounts_in(text.replace("−", "-"))}


def without_tool_previews(html, where=None):
    """25 Oct sweep: the tool cards and the tools-page mock show the free tools' own output on the synthetic
    sample file, between <!--sample-out--> and <!--/sample-out-->. Such a block is left out of the price
    check only when every dollar amount in it is one the tools printed on the sample file
    (site/config/tool_previews.json); a block with any other figure, or a price, is checked as usual. Only on
    SAMPLE_OUT_PATHS, and only when the block is one of the two preview elements (SAMPLE_OUT_ELEMENT)."""
    if where not in SAMPLE_OUT_PATHS:
        return html
    blocks = [b for b in SAMPLE_OUT_RE.findall(html) if SAMPLE_OUT_ELEMENT.match(b)]
    if not blocks:
        return html
    from harvest_prices import amounts_in
    allowed = tool_preview_amounts()
    for b in blocks:
        found = amounts_in(b)
        if all(round(a, 2) in allowed for a in found):
            html = html.replace(b, " ", 1)
    return html


KEY_NUM = re.compile(r'class="[^"]*\bkey-num\b')


def key_num_per_section(html, where):
    """ARCHITECT-BRAND §2.4: rust .key-num is "the finding", one per <section> at most."""
    out = []
    for i, sec in enumerate(re.findall(r"(?s)<section\b.*?</section>", html)):
        n = len(KEY_NUM.findall(sec))
        if n > 1:
            out.append(("key_num", where, f"{n} .key-num in one <section> (section {i + 1}); one at most"))
    return out


def lint_html(html, where, paid, analytics, allowed_amounts, private_values, commerce=None, pilot=False):
    """commerce: True when the seller block may appear (build.show_seller); defaults to paid or pilot."""
    commerce = (paid or pilot) if commerce is None else commerce
    french = bool(re.search(r'<html lang="fr', html))
    out = lint_text(readable_text(html), where, paid, analytics, english=not french)
    out += dated_pricing_claims("", where, html)   # priceValidUntil in JSON-LD (the phrases: lint_text)
    out += tally_mentions(html, where)
    out += key_num_per_section(html, where)
    if paid:
        out += not_on_sale_claims(readable_text(html), where)
    from harvest_prices import amounts_in
    for a in amounts_in(without_tool_previews(without_hero_dash(html, where), where)):
        if a not in allowed_amounts and a != 0:  # "$0" (free) is not a price
            out.append(("price_literal", where, f"${a:g} is not in prices.json"))
    for rx in SECRETS:
        if rx.search(html):
            out.append(("secret", where, rx.pattern))
    if not paid:
        if 'data-requires-flag="paid_report"' in html:
            out.append(("flag:paid_markup", where, "paid-only markup with paid_report = false"))
        if '"@type": "Product"' in html or '"@type":"Product"' in html:
            out.append(("flag:product_jsonld", where, "Product JSON-LD with paid_report = false"))
    if not pilot and 'data-requires-flag="pilot_checkout"' in html:
        out.append(("flag:pilot_markup", where, "pilot-checkout markup with pilot_checkout = false"))
    if not (pilot or paid) and "buy.stripe.com" in html:
        out.append(("flag:stripe_link", where, "a Stripe link with every commerce flag off"))
    if not commerce:
        # the mailing address may appear in the footer's business line (any commerce flag); the
        # legal name and phone, and the address anywhere else, only with the seller block
        rest = strip_business_line(html) if (paid or pilot) else html
        for v in private_values:
            if v and v in rest:
                out.append(("flag:seller_identity", where, "seller name/address/phone where the seller block is off"))
        if "data-seller-block" in html:
            out.append(("flag:seller_block", where, "seller disclosure markup where the seller block is off "
                        "(paid_report off, and pilot_checkout off or [legal] show_seller_for_pilot = false)"))
    out += placeholder_problems(html, where)
    if french:
        out += lint_text_fr(readable_text(strip_disclaimers(html)), where)
    if analytics is False and "cloudflareinsights" in html:
        out.append(("flag:beacon", where, "analytics beacon with analytics = false"))
    return out


PLACEHOLDER = re.compile(r"\[(SELLER|ADDRESS|PHONE) —")


def placeholder_problems(html, where):
    """Tester delta N6: a private.toml placeholder ("[ADDRESS — …]") is never published, whatever the
    flags (only a DT_ALLOW_PLACEHOLDERS build, local only, can hold one): every page, footer included."""
    if PLACEHOLDER.search(html):
        return [("flag:seller_placeholder", where, "a private.toml placeholder is in the page "
                 "(a DT_ALLOW_PLACEHOLDERS build: local only, never publish it)")]
    return []


def strip_business_line(html):
    """The page without its footer business-identification line (build.BUSINESS_ID_RE)."""
    import build
    return build.BUSINESS_ID_RE.sub(" ", html)


BUSINESS_LINE_TEXT = re.compile(r"^donttrade · Ontario, Canada · (?P<address>.+) · (?P<email>[^\s@·]+@[^\s@·]+)$")
BUSINESS_LINE_SHORT = re.compile(r"^donttrade · Ontario, Canada · (?P<email>[^\s@·]+@[^\s@·]+) · (?P<label>Business details|Coordonnées de l’entreprise)$")


def business_line_problems(html, where, commerce, private_values=()):
    """Decisions 21 and 25 Oct: with any commerce flag on, every page has exactly one business line.
    On build.ADDRESS_LINE_PATHS (where a buyer pays or reads the terms first: Visa 5.8.4.1, Ontario CPA
    disclosure before payment) it is "donttrade · Ontario, Canada · <mailing address> · <business email>",
    whose address is the private.toml one; on every other page "donttrade · Ontario, Canada · <business
    email> · Business details" (link to the terms' seller block), never with the address. With every
    commerce flag off, none. where: the page's path in the build ("/about/index.html") or its URL."""
    import build
    found = build.BUSINESS_ID_RE.findall(html)
    n = html.count(build.BUSINESS_ID_ATTR)
    if not commerce:
        return [("flag:business_line", where, "business line with every commerce flag off")] if n else []
    if n != 1 or len(found) != 1:
        return [("business_line", where, f"{n} business-identification line(s), expected exactly 1")]
    text = " ".join(normalise(re.sub(r"<[^>]+>", " ", __import__("html").unescape(found[0]))).split())
    full = build.business_line_full(build.url_of(where.lstrip("/")))
    if not full:
        m = BUSINESS_LINE_SHORT.fullmatch(text)
        if not m or 'data-business-id="short"' not in found[0]:
            return [("business_line", where, "not in the form 'donttrade · Ontario, Canada · <email> · Business details' "
                     f"(the address only on build.ADDRESS_LINE_PATHS): {text!r}")]
        href = build.BUSINESS_DETAILS["fr" if m.group("label") != "Business details" else "en"][0]
        if f'href="{href}"' not in found[0]:
            return [("business_line", where, f"its details link is not {href}")]
        if any(v and v in found[0] for v in private_values):
            return [("business_line", where, "the mailing address in the short business line")]
        return []
    m = BUSINESS_LINE_TEXT.fullmatch(text)
    if not m or 'data-business-id="full"' not in found[0]:
        return [("business_line", where, f"not in the form 'donttrade · Ontario, Canada · <address> · <email>': {text!r}")]
    if private_values and m.group("address") not in private_values:
        return [("business_line", where, "its address is not the private.toml premises_address")]
    return []


FROZEN_START, FROZEN_END = "<!--frozen:start-->", "<!--frozen:end-->"
FROZEN_RE = re.compile(r"(?s)<!--frozen:start-->(.*?)<!--frozen:end-->")


def split_frozen(html):
    """(the page without its frozen body, the frozen body or None)."""
    m = FROZEN_RE.search(html)
    if not m:
        return html, None
    import compare   # islands (compare.ISLAND_RE) are new markup: full rules, not the frozen ones
    islands = " ".join(compare.ISLAND_RE.findall(m.group(1)))
    return html[:m.start()] + " " + islands + " " + html[m.end():], compare.ISLAND_RE.sub("", m.group(1))


def lifted_problems(html, where, path, paid, analytics, amounts, priv, seller, pilot):
    """A lifted page: full rules outside the frozen body; inside it, the passthrough rules and
    word-for-word equality with the old page (compare.py baseline)."""
    import compare
    n = (html.count(FROZEN_START), html.count(FROZEN_END))
    if n != (1, 1):
        return [("frozen", where, f"a lifted page needs exactly one frozen body, found {n[0]} start / {n[1]} end markers")]
    rest, body = split_frozen(html)
    out = lint_html(rest, where, paid, analytics, amounts, priv, commerce=seller, pilot=pilot)
    out += passthrough_rules(body, where, analytics, paid)
    out += frozen_brand_problems(body, path)
    base = compare.baselines().get(path)
    if base is None:
        out.append(("frozen", where, "no checks/lifted-baseline entry for this lifted page"))
    else:
        out += [("frozen:" + what, where, detail) for what, detail in compare.diff_page(base, html, paid)]
    return out


def passthrough_rules(html, where, analytics, paid=False):
    """D9: the rules that must hold on passthrough pages too (the full word list waits for
    steps 28–29, which lift the study pages word for word): upload/analytics claims, the old
    regular-price wording and retired amounts, Tally."""
    out = []
    text = readable_text(html)
    for c in RULES["claims"]["no_upload"]:
        if _phrase_re(c).search(text):
            out.append(("claim:no_upload", where, c))
    if analytics:
        for c in RULES["claims"]["no_analytics"]:
            if _phrase_re(c).search(text):
                out.append(("claim:no_analytics", where, c))
    out += restore_email_claims(text, where)
    out += waive_dispute_claims(text, where)
    out += dated_pricing_claims(text, where, html)
    out += scarcity_claims(text, where)
    if paid:
        out += not_on_sale_claims(readable_text(html), where)
    for w in RULES["words"]["trial_cta"]:
        if _phrase_re(w).search(text):
            out.append(("banned:trial_cta", where, w))
    for w in RULES["words"]["regular_price"]:
        if _phrase_re(w).search(text):
            out.append(("banned:regular_price", where, w))
    with open(prices_path(), encoding="utf-8") as f:
        retired = set(json.load(f)["retired_amounts"]["amounts"])
    from harvest_prices import amounts_in
    for a in amounts_in(html):
        if a in retired:
            out.append(("price_literal", where, f"${a:g} is a retired price"))
    out += tally_mentions(html, where)
    return out


def prices_path():
    """The prices.json the build reads (DT_PRICES_JSON, else the committed one; Tester delta N3)."""
    return os.environ.get("DT_PRICES_JSON") or os.path.join(REPO, "site", "config", "prices.json")


def allowed_amounts():
    from harvest_prices import allowed_amounts as aa
    with open(prices_path(), encoding="utf-8") as f:
        return aa(json.load(f))


def private_toml_path():
    return os.environ.get("DT_PRIVATE_TOML") or os.path.join(REPO, "site", "config", "private.toml")


def read_private():
    """private.toml as a dict, or None when there is none. Read once per lint run (Tester delta N3).
    Lint reads it even with every flag off, on purpose: to prove none of its values leaked into a
    build that must not hold them (the BUILD never opens it with the flags off)."""
    p = private_toml_path()
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        return tomllib.load(f)


def private_values(fields=("seller_legal_name", "premises_address", "phone"), data=None):
    """The seller values to look for, from the same private.toml the build reads (DT_PRIVATE_TOML,
    else site/config/private.toml; Tester NIT 2), as written and as published (normalised)."""
    import build
    d = read_private() if data is None else data
    if not d:
        return []
    out = []
    for k in fields:
        v = d.get(k, "")
        if isinstance(v, str) and v.strip():
            out.append(v)
            norm = build.normalise_private(v)[0]
            if norm and norm != v:
                out.append(norm)
    return out


def owned_paths(paid, pilot=False, journal=False, analytics=False):
    import build
    # analytics: the Readiness Check's count pages (build.COUNT_EVENTS) exist only with [flags] analytics
    on = {"paid_report": paid, "pilot_checkout": pilot, "journal": journal, "analytics": analytics}
    out = []
    for p in build.PAGES:
        if p["requires_flag"] and not on[p["requires_flag"]]:
            continue
        out.append(p["path"])
    return out


def seller_allowed(paid, pilot):
    """build.show_seller for these flags, with the [legal] show_seller_for_pilot switch of the same
    site.toml the build reads (DT_SITE_TOML, else the committed one; Tester NIT 2)."""
    import build
    p = os.environ.get("DT_SITE_TOML") or os.path.join(REPO, "site", "config", "site.toml")
    cfg = build.read_toml(p, "site.toml")
    return build.show_seller({"flags": {"paid_report": paid, "pilot_checkout": pilot}, "legal": cfg["legal"]})


WARNINGS = []   # printed by main(): checks lint could not run (Tester delta N2)


# Free-launch condition C1 (21 Oct 2026): with [flags] free_badges off, no page and no shipped
# script outside the statistics engine (static/js/engine/, unchanged by rule) and the paid report
# (static/js/paid/, its own statistics) may carry the free tools' badges or their footnote.
# The neutral line ("A ‘real or noise’ check for this number is coming soon.") is allowed.
FREE_BADGE_STRINGS = (
    "Real or noise?", "Real-or-noise check", "real-or-noise result", "three real-or-noise checks",
    "Trade stats with a real-or-noise check", "trade stats with a real-or-noise check",
    "streaks, with a real-or-noise check", "file shows, with a real-or-noise check",
    "Three of the numbers get a real-or-noise check", "which numbers are more than noise",
    "1 time in 20", "1 file in 7", "badge-real", "badge-noise", "ts-noise-footnote", "Running the checks",
    "FREE_CHECKS_FOOTNOTE",
)
BADGE_EXEMPT = ("/static/js/engine/", "/static/js/paid/")


def free_badge_problems(s, where):
    if where.startswith(BADGE_EXEMPT):
        return []
    return [("flag:free_badges", where, f"{x!r} while free_badges = false") for x in FREE_BADGE_STRINGS if x in s]


SIGNATURE_JS = re.compile(r"^/static/js/(?:card/.+|(?:.+/)?(?:luck|ghost|guess)[\w.-]*)\.js$")


def signature_script(rel):
    """ARCHITECT-BRAND-AND-WRAPPED §1.5: scripts whose strings reach the page or a canvas without any
    HTML (static/js/card/, luck*.js, ghost*.js, guess*.js anywhere under static/js/): their string
    literals get the full page word list, skill_claims and seal_words included."""
    return SIGNATURE_JS.match(rel) is not None


def lint_build(out_dir, paid=False, analytics=False, pilot=False, seller=None, badges=False, journal=None):
    """seller: whether the seller block may appear; defaults to the committed switch (seller_allowed).
    badges: the build's free_badges flag (C1); off, free_badge_problems applies to every file."""
    import build
    problems = []
    if journal is None:   # the journal page is in the build only with [flags] journal (build.PAGES)
        journal = os.path.exists(build.out_file(out_dir, "/journal/"))
    seller = seller_allowed(paid, pilot) if seller is None else seller
    if os.path.isdir(os.path.join(out_dir, "dev")):
        problems.append(("dev_in_build", "/dev/", "dev pages are in the build"))
    amounts = allowed_amounts()
    WARNINGS.clear()
    data = read_private()
    priv = private_values(data=data or {})
    addresses = private_values(("premises_address",), data=data or {})
    if (paid or pilot) and data is None:   # Tester delta N2: say so instead of skipping the check silently
        WARNINGS.append(f"no private.toml at {private_toml_path()}: the footer line's address was NOT checked "
                        "against it (set DT_PRIVATE_TOML to the file the build used)")
    owned_rel = {"/" + os.path.relpath(build.out_file(out_dir, p), out_dir) for p in owned_paths(paid, pilot, journal, analytics)}
    lifted = set(build.lifted_paths_for(paid))   # C-12 final: a paid build's /sample-report/ is a template page
    for path in owned_paths(paid, pilot, journal, analytics):
        fp = build.out_file(out_dir, path)
        if not os.path.exists(fp):
            problems.append(("flags", path, "page missing: is the build made with these flags?"))
            continue
        with open(fp, encoding="utf-8") as f:
            html = f.read()
        if path in lifted:
            problems += lifted_problems(html, path, path, paid, analytics, amounts, priv, seller, pilot)
            continue
        if FROZEN_START in html or FROZEN_END in html:
            problems.append(("frozen", path, "a frozen-body marker on a page that is not lifted (build.LIFTED_PATHS)"))
        problems += lint_html(html, path, paid, analytics, amounts, priv, commerce=seller, pilot=pilot)
    # leaks and flag rules apply to EVERY file in the build, passthrough included
    for root, _, files in os.walk(out_dir):
        for name in files:
            if not name.endswith((".html", ".js", ".css", ".json", ".xml", ".txt")):
                continue
            fp = os.path.join(root, name)
            rel = "/" + os.path.relpath(fp, out_dir)
            with open(fp, encoding="utf-8", errors="replace") as f:
                s = f.read()
            for rx in SECRETS:
                if rx.search(s):
                    problems.append(("secret", rel, rx.pattern))
            if name.endswith(".html") and rel not in owned_rel:
                problems += passthrough_rules(s, rel, analytics, paid)
                problems += placeholder_problems(s, rel)
            if name.endswith(".xml"):   # Tester D4: feed titles and summaries are public copy
                problems += feed_problems(s, rel)
            if name == "answers-index.js":   # ARCHITECT-V3 A11: every answer unit passes the page wording rules
                problems += answer_index_problems(s, rel, paid, analytics)
            if name.endswith(".js"):
                problems += restore_email_claims(js_strings(s), rel)
                problems += waive_dispute_claims(js_strings(s), rel)
                problems += dated_pricing_claims(js_strings(s), rel)
                problems += scarcity_claims(js_strings(s), rel)
                if paid:  # a script can put text on a paid page too
                    problems += not_on_sale_claims(js_strings(s), rel)
                if rel.startswith("/static/js/journal/") or signature_script(rel):
                    # ARCHITECT-V3 J38: every journal string, as page text; ARCHITECT-BRAND §1.5: the same
                    # for the card, Luck Check, Guess vs Data and Ghost Trader scripts (canvas text has no HTML)
                    problems += lint_text(normalise(js_strings(s)), rel, paid, analytics)
            if name.endswith(".html"):
                problems += business_line_problems(s, rel, paid or pilot, addresses)
                url = rel[:-len("index.html")] if rel.endswith("/index.html") else rel
                why = build.motion_problem(s, url)  # motion plan: count-up only on the hero's sample tiles
                if why:
                    problems.append(("motion", rel, why))
            if not seller:
                rest = strip_business_line(s) if (paid or pilot) and name.endswith(".html") else s
                for v in priv:
                    if v and v in rest:
                        problems.append(("flag:seller_identity", rel, "private.toml value in the build, where the seller block is off"))
            if not analytics and "cloudflareinsights" in s:
                problems.append(("flag:beacon", rel, "analytics beacon"))
            if not badges and name.endswith((".html", ".js")):
                problems += free_badge_problems(s, rel)
    return problems


def answer_index_problems(js, where, paid=False, analytics=False):
    """The answer box index (build.answers_index_js): one JSON assignment; each unit's question and
    answer pass lint_text, and no unit comes from /research/."""
    m = re.fullmatch(r"(?s)//[^\n]*\nwindow\.DT_ANSWERS = (\{.*\});\n", js)
    if not m:
        return [("answers", where, "not a single window.DT_ANSWERS = {...}; assignment")]
    data = json.loads(m.group(1).replace("<\\/", "</"))
    out = []
    for u in data["units"]:
        out += lint_text(normalise(u["q"] + " " + u["a"]), f"{where}#{u['id']}", paid, analytics)
        if u["url"].startswith("/research/"):
            out.append(("answers", where, f"unit {u['id']} comes from /research/"))
    return out


def flags_of_build(out_dir):
    """Tester NIT 2: the flags a build was made with, read from the build itself: the paid-only
    and pilot-only pages exist only with their flag (build.verify enforces it), and the beacon
    only with analytics."""
    import build
    paid = os.path.exists(build.out_file(out_dir, "/welcome/"))
    pilot = os.path.exists(build.out_file(out_dir, "/start/pilot-thanks/"))
    home = build.out_file(out_dir, "/")
    analytics = os.path.exists(home) and "cloudflareinsights" in open(home, encoding="utf-8", errors="replace").read()
    # C1: the badge module is in the build only with free_badges (build.BADGES_JS)
    badges = os.path.exists(os.path.join(out_dir, "static", build.BADGES_JS))
    return {"paid": paid, "pilot": pilot, "analytics": analytics, "badges": badges}


def main(argv):
    out_dir = next((a for a in argv if not a.startswith("--")), os.path.join(REPO, "site", "_site"))
    if not os.path.isdir(out_dir):  # Tester NIT 16: one clear line, not 15 "page missing"
        print(f"lint: {out_dir}: no such directory (build first: ./site/run.sh build)")
        return 2
    found = flags_of_build(out_dir)
    given = {k: f"--{k}" in argv for k in found}
    if any(f"--{k}" in argv for k in found) or "--flags-from-args" in argv:
        wrong = [k for k in found if given[k] != found[k]]
        if wrong:
            for k in wrong:
                print(f"LINT {'flags':22} {out_dir}: --{k} {'given' if given[k] else 'missing'}, but the build "
                      f"{'has' if found[k] else 'has no'} {k} pages")
            print(f"lint: {len(wrong)} problem(s)")
            return 1
        flags = given
    else:
        flags = found
        print("lint: flags read from the build: " + ", ".join(f"{k}={'on' if v else 'off'}" for k, v in flags.items()))
    paid, analytics = flags["paid"], flags["analytics"]
    problems = lint_build(out_dir, paid, analytics, pilot=flags["pilot"], badges=flags["badges"])
    for w in WARNINGS:
        print("lint: WARNING: " + w)
    for rule, where, detail in problems:
        print(f"LINT {rule:22} {where}: {detail}")
    print("lint:", "PASS" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
