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
once while a commerce flag is on (and its address the private.toml one), none while both are off.

Scope: the pages that templates own (new design). Passthrough pages are lifted word
for word in steps 28–29 and are linted from then on; until then the old pages are
covered by the v1 site tests.
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


def _phrase_re(p):
    # whole-word match on both ends where the phrase starts/ends with a word character
    left = r"(?<![A-Za-z0-9])" if re.match(r"\w", p) else ""
    right = r"(?![A-Za-z0-9])" if re.search(r"\w$", p) else ""
    return re.compile(left + re.escape(p) + right, re.IGNORECASE)


WORDS = [(cat, w, _phrase_re(w)) for cat, ws in RULES["words"].items() for w in ws]
ALLOW = [_phrase_re(p) for p in RULES["allow"]["phrases"]]
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
INLINE = frozenset("a abbr b bdi bdo cite code data del dfn em font i ins kbd mark nobr q s samp small span "
                   "strong sub sup time tt u var wbr".split())
READ_ATTRS = ("alt", "title", "aria-label", "placeholder", "aria-description")
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


def lint_text(text, where="text", paid=False, analytics=False, english=True):
    """Wording rules on plain text. Returns a list of (rule, where, detail).
    english=False (French pages) skips the English word list; lint_text_fr covers those pages."""
    out = []
    masked = text
    for a in ALLOW:
        masked = a.sub(lambda m: " " * len(m.group(0)), masked)
    for cat, w, rx in (WORDS if english else []):
        for m in rx.finditer(masked):
            ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            out.append((f"banned:{cat}", where, f"“{w}” in …{ctx}…"))
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
    return out


def lint_html(html, where, paid, analytics, allowed_amounts, private_values, commerce=None, pilot=False):
    """commerce: True when the seller block may appear (build.show_seller); defaults to paid or pilot."""
    commerce = (paid or pilot) if commerce is None else commerce
    french = bool(re.search(r'<html lang="fr', html))
    out = lint_text(readable_text(html), where, paid, analytics, english=not french)
    out += tally_mentions(html, where)
    if paid:
        out += not_on_sale_claims(readable_text(html), where)
    from harvest_prices import amounts_in
    for a in amounts_in(html):
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
        if re.search(r"\[(SELLER|ADDRESS|PHONE) —", html):
            out.append(("flag:seller_placeholder", where, "seller placeholder where the seller block is off"))
        if "data-seller-block" in html:
            out.append(("flag:seller_block", where, "seller disclosure markup where the seller block is off "
                        "(paid_report off, and pilot_checkout off or [legal] show_seller_for_pilot = false)"))
    if french:
        out += lint_text_fr(readable_text(strip_disclaimers(html)), where)
    if analytics is False and "cloudflareinsights" in html:
        out.append(("flag:beacon", where, "analytics beacon with analytics = false"))
    return out


def strip_business_line(html):
    """The page without its footer business-identification line (build.BUSINESS_ID_RE)."""
    import build
    return build.BUSINESS_ID_RE.sub(" ", html)


BUSINESS_LINE_TEXT = re.compile(r"^donttrade · Ontario, Canada · (?P<address>.+) · (?P<email>[^\s@·]+@[^\s@·]+)$")


def business_line_problems(html, where, commerce, private_values=()):
    """Decision 21 Oct: with any commerce flag on, every page has exactly one business line,
    "donttrade · Ontario, Canada · <mailing address> · <business email>", whose address is the
    private.toml one; with every commerce flag off, none."""
    import build
    found = build.BUSINESS_ID_RE.findall(html)
    n = html.count(build.BUSINESS_ID_ATTR)
    if not commerce:
        return [("flag:business_line", where, "business line with every commerce flag off")] if n else []
    if n != 1 or len(found) != 1:
        return [("business_line", where, f"{n} business-identification line(s), expected exactly 1")]
    text = " ".join(normalise(re.sub(r"<[^>]+>", " ", __import__("html").unescape(found[0]))).split())
    m = BUSINESS_LINE_TEXT.fullmatch(text)
    if not m:
        return [("business_line", where, f"not in the form 'donttrade · Ontario, Canada · <address> · <email>': {text!r}")]
    if private_values and m.group("address") not in private_values:
        return [("business_line", where, "its address is not the private.toml premises_address")]
    return []


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
    if paid:
        out += not_on_sale_claims(readable_text(html), where)
    for w in RULES["words"]["trial_cta"]:
        if _phrase_re(w).search(text):
            out.append(("banned:trial_cta", where, w))
    for w in RULES["words"]["regular_price"]:
        if _phrase_re(w).search(text):
            out.append(("banned:regular_price", where, w))
    with open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8") as f:
        retired = set(json.load(f)["retired_amounts"]["amounts"])
    from harvest_prices import amounts_in
    for a in amounts_in(html):
        if a in retired:
            out.append(("price_literal", where, f"${a:g} is a retired price"))
    out += tally_mentions(html, where)
    return out


def allowed_amounts():
    from harvest_prices import allowed_amounts as aa
    with open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8") as f:
        return aa(json.load(f))


def private_values(fields=("seller_legal_name", "premises_address", "phone")):
    """The seller values to look for, from the same private.toml the build reads (DT_PRIVATE_TOML,
    else site/config/private.toml; Tester NIT 2), as written and as published (normalised)."""
    import build
    p = os.environ.get("DT_PRIVATE_TOML") or os.path.join(REPO, "site", "config", "private.toml")
    if not os.path.exists(p):
        return []
    with open(p, "rb") as f:
        d = tomllib.load(f)
    out = []
    for k in fields:
        v = d.get(k, "")
        if isinstance(v, str) and v.strip():
            out.append(v)
            norm = build.normalise_private(v)[0]
            if norm and norm != v:
                out.append(norm)
    return out


def owned_paths(paid, pilot=False):
    import build
    on = {"paid_report": paid, "pilot_checkout": pilot}
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


def lint_build(out_dir, paid=False, analytics=False, pilot=False, seller=None):
    """seller: whether the seller block may appear; defaults to the committed switch (seller_allowed)."""
    import build
    problems = []
    seller = seller_allowed(paid, pilot) if seller is None else seller
    if os.path.isdir(os.path.join(out_dir, "dev")):
        problems.append(("dev_in_build", "/dev/", "dev pages are in the build"))
    amounts = allowed_amounts()
    priv = private_values()
    addresses = private_values(("premises_address",))
    owned_rel = {"/" + os.path.relpath(build.out_file(out_dir, p), out_dir) for p in owned_paths(paid, pilot)}
    for path in owned_paths(paid, pilot):
        fp = build.out_file(out_dir, path)
        if not os.path.exists(fp):
            problems.append(("flags", path, "page missing: is the build made with these flags?"))
            continue
        with open(fp, encoding="utf-8") as f:
            problems += lint_html(f.read(), path, paid, analytics, amounts, priv, commerce=seller, pilot=pilot)
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
            if name.endswith(".js"):
                problems += restore_email_claims(js_strings(s), rel)
                problems += waive_dispute_claims(js_strings(s), rel)
                if paid:  # a script can put text on a paid page too
                    problems += not_on_sale_claims(js_strings(s), rel)
            if name.endswith(".html"):
                problems += business_line_problems(s, rel, paid or pilot, addresses)
            if not seller:
                rest = strip_business_line(s) if (paid or pilot) and name.endswith(".html") else s
                for v in priv:
                    if v and v in rest:
                        problems.append(("flag:seller_identity", rel, "private.toml value in the build, where the seller block is off"))
            if not analytics and "cloudflareinsights" in s:
                problems.append(("flag:beacon", rel, "analytics beacon"))
    return problems


def flags_of_build(out_dir):
    """Tester NIT 2: the flags a build was made with, read from the build itself: the paid-only
    and pilot-only pages exist only with their flag (build.verify enforces it), and the beacon
    only with analytics."""
    import build
    paid = os.path.exists(build.out_file(out_dir, "/welcome/"))
    pilot = os.path.exists(build.out_file(out_dir, "/start/pilot-thanks/"))
    home = build.out_file(out_dir, "/")
    analytics = os.path.exists(home) and "cloudflareinsights" in open(home, encoding="utf-8", errors="replace").read()
    return {"paid": paid, "pilot": pilot, "analytics": analytics}


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
    problems = lint_build(out_dir, paid, analytics, pilot=flags["pilot"])
    for rule, where, detail in problems:
        print(f"LINT {rule:22} {where}: {detail}")
    print("lint:", "PASS" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
