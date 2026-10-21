#!/usr/bin/env python3
"""lint.py — wording, flag and leak rules for the v2 site (and for report strings).

    python3 checks/lint.py site/_site [--paid] [--analytics]   # lint a build
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


def visible_text(html):
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    html = re.sub(r"(?s)<!--.*?-->", " ", html)
    # attribute text people read: alt, title, aria-label, placeholder, content of description
    attrs = " ".join(re.findall(r'(?:alt|title|aria-label|placeholder)="([^"]*)"', html))
    text = re.sub(r"<[^>]+>", " ", html)
    import html as _h
    return _h.unescape(text + " " + attrs)


def lint_text(text, where="text", paid=False, analytics=False):
    """Wording rules on plain text. Returns a list of (rule, where, detail)."""
    out = []
    masked = text
    for a in ALLOW:
        masked = a.sub(lambda m: " " * len(m.group(0)), masked)
    for cat, w, rx in WORDS:
        for m in rx.finditer(masked):
            ctx = text[max(0, m.start() - 40):m.end() + 40].replace("\n", " ")
            out.append((f"banned:{cat}", where, f"“{w}” in …{ctx}…"))
    if paid:
        for c in RULES["claims"]["no_upload"]:
            if _phrase_re(c).search(text):
                out.append(("claim:no_upload", where, c))
    if analytics:
        for c in RULES["claims"]["no_analytics"]:
            if _phrase_re(c).search(text):
                out.append(("claim:no_analytics", where, c))
    return out


def lint_html(html, where, paid, analytics, allowed_amounts, private_values):
    out = lint_text(visible_text(html), where, paid, analytics)
    if "tally.so" in html:
        out.append(("tally", where, "tally.so"))
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
        for v in private_values:
            if v and v in html:
                out.append(("flag:seller_identity", where, "seller name/address/phone with paid_report = false"))
        if re.search(r"\[(SELLER|ADDRESS|PHONE) —", html):
            out.append(("flag:seller_placeholder", where, "seller placeholder with paid_report = false"))
    if analytics is False and "cloudflareinsights" in html:
        out.append(("flag:beacon", where, "analytics beacon with analytics = false"))
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


def owned_paths(paid):
    import build
    out = []
    for p in build.PAGES:
        if p["requires_flag"] and not paid:
            continue
        out.append(p["path"])
    return out


def lint_build(out_dir, paid=False, analytics=False):
    import build
    problems = []
    if os.path.isdir(os.path.join(out_dir, "dev")):
        problems.append(("dev_in_build", "/dev/", "dev pages are in the build"))
    amounts = allowed_amounts()
    priv = private_values()
    for path in owned_paths(paid):
        fp = build.out_file(out_dir, path)
        with open(fp, encoding="utf-8") as f:
            problems += lint_html(f.read(), path, paid, analytics, amounts, priv)
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
            if not paid:
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
    problems = lint_build(out_dir, paid, analytics)
    for rule, where, detail in problems:
        print(f"LINT {rule:22} {where}: {detail}")
    print("lint:", "PASS" if not problems else f"{len(problems)} problem(s)")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
