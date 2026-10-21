#!/usr/bin/env python3
"""lint.py — wording, flag and leak rules for the v2 site (and for report strings).

    python3 checks/lint.py site/_site [--paid] [--analytics] [--pilot]   # lint a build
    from lint import lint_text                                  # lint any text (report strings)

Rules (banned.toml): A3 banned words outside allowlisted negations/disclaimer; AI-tell
words; tally.so; "nothing leaves"-type claims when a paid flow exists; "no analytics"
when analytics is on; $ amounts not from prices.json; flag-gated strings with the paid
flag off (seller name/placeholders, trader Stripe links, Product JSON-LD, paid markup);
/dev/ in the build; secret patterns.

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


TALLY = re.compile(r"(?<![A-Za-z0-9])tally(?![A-Za-z0-9])", re.IGNORECASE)


def tally_mentions(html, where):
    """B1: Tally is no longer used (the forms are Web3Forms), so the word may not appear anywhere
    in a page, visible or not, including tally.so links."""
    return [("tally", where, html[max(0, m.start() - 30):m.end() + 30].replace("\n", " ")) for m in TALLY.finditer(html)]


def restore_email_claims(text, where):
    """Restore-by-email is not in v1 (decision 20 Oct): any wording that offers it fails,
    on every page and in the paid scripts' messages. The listed negations are allowed."""
    for a in RESTORE_EMAIL_ALLOW:
        text = a.sub(lambda m: " " * len(m.group(0)), text)
    return [("claim:restore_email", where, m.group(0)) for rx in RESTORE_EMAIL for m in rx.finditer(text)]


def js_strings(code):
    """The string literals of a script (comments dropped): the text a script can put on a page."""
    out = []
    for m in re.finditer(r"//[^\n]*|/\*.*?\*/|'(?:[^'\\\n]|\\.)*'|\"(?:[^\"\\\n]|\\.)*\"|`(?:[^`\\]|\\.)*`", code, re.S):
        tok = m.group(0)
        if tok[0] in "'\"`":
            out.append(tok[1:-1])
    return "\n".join(out)


def visible_text(html):
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    # attribute text people read: alt, title, aria-label, placeholder, content of description
    attrs = " ".join(re.findall(r'(?:alt|title|aria-label|placeholder)="([^"]*)"', html))
    text = re.sub(r"<[^>]+>", " ", html)
    import html as _h
    return _h.unescape(text + " " + attrs)


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
    return out


def lint_html(html, where, paid, analytics, allowed_amounts, private_values, commerce=None, pilot=False):
    """commerce: True when the seller block may appear (build.show_seller); defaults to paid or pilot."""
    commerce = (paid or pilot) if commerce is None else commerce
    french = bool(re.search(r'<html lang="fr', html))
    out = lint_text(visible_text(html), where, paid, analytics, english=not french)
    out += tally_mentions(html, where)
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
        for v in private_values:
            if v and v in html:
                out.append(("flag:seller_identity", where, "seller name/address/phone with paid_report = false"))
        if re.search(r"\[(SELLER|ADDRESS|PHONE) —", html):
            out.append(("flag:seller_placeholder", where, "seller placeholder with paid_report = false"))
        if "data-seller-block" in html:
            out.append(("flag:seller_block", where, "seller disclosure markup with every commerce flag off"))
    if french:
        out += lint_text_fr(visible_text(strip_disclaimers(html)), where)
    if analytics is False and "cloudflareinsights" in html:
        out.append(("flag:beacon", where, "analytics beacon with analytics = false"))
    return out


def passthrough_rules(html, where, analytics):
    """D9: the rules that must hold on passthrough pages too (the full word list waits for
    steps 28–29, which lift the study pages word for word): upload/analytics claims, the old
    regular-price wording and retired amounts, Tally."""
    out = []
    text = visible_text(html)
    for c in RULES["claims"]["no_upload"]:
        if _phrase_re(c).search(text):
            out.append(("claim:no_upload", where, c))
    if analytics:
        for c in RULES["claims"]["no_analytics"]:
            if _phrase_re(c).search(text):
                out.append(("claim:no_analytics", where, c))
    out += restore_email_claims(text, where)
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


def private_values():
    p = os.path.join(REPO, "site", "config", "private.toml")
    if not os.path.exists(p):
        return []
    with open(p, "rb") as f:
        d = tomllib.load(f)
    return [d.get(k, "") for k in ("seller_legal_name", "premises_address", "phone")]


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
    """build.show_seller for these flags, with the committed [legal] show_seller_for_pilot switch."""
    import build
    cfg = build.read_toml(os.path.join(REPO, "site", "config", "site.toml"), "site.toml")
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
    owned_rel = {"/" + os.path.relpath(build.out_file(out_dir, p), out_dir) for p in owned_paths(paid, pilot)}
    for path in owned_paths(paid, pilot):
        fp = build.out_file(out_dir, path)
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
                problems += passthrough_rules(s, rel, analytics)
            if name.endswith(".js"):
                problems += restore_email_claims(js_strings(s), rel)
            if not seller:
                for v in priv:
                    if v and v in s:
                        problems.append(("flag:seller_identity", rel, "private.toml value in the build"))
            if not analytics and "cloudflareinsights" in s:
                problems.append(("flag:beacon", rel, "analytics beacon"))
    return problems


def main(argv):
    out_dir = argv[0] if argv else os.path.join(REPO, "site", "_site")
    paid = "--paid" in argv
    analytics = "--analytics" in argv
    problems = lint_build(out_dir, paid, analytics, pilot="--pilot" in argv)
    for rule, where, detail in problems:
        print(f"LINT {rule:22} {where}: {detail}")
    print("lint:", "PASS" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
