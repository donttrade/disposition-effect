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
      - a page without exactly one footer business line while a commerce flag is on, or with
        one while both are off (business_id_line(); decision 21 Oct),
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
Local-test escapes (ESCAPES): each opens ONE guard, prints a WARNING, and is refused when
[stripe] mode = "live". A paid build with well-formed values needs none of them.
  DT_ALLOW_PLACEHOLDERS=1    allow private.toml values that look like placeholders
  DT_ALLOW_LOCAL_API=1       allow a loopback http [worker] api_base
  DT_ALLOW_NO_STRIPE_LINK=1  allow a paid build without the report39 Payment Link
"""

import json
import os
import re
import unicodedata
import shutil
import sys
import tomllib

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


def address_problem(v):
    if not re.fullmatch(r"[^\W_]+(?:[ ,.'’#/-]+[^\W_]*)*\.?", v):
        return "an address may hold only letters, digits, spaces and , . - ' # /"
    m = ADDRESS.fullmatch(v)
    if not m:
        return "write it as: street number and street (or PO Box N), city, province code, postal code — e.g. 'PO Box 12, Town ON K1A 0B1'"
    street, city, prov, postal = m.group("street", "city", "prov", "postal")
    # Decision 21 Oct: a Canada Post box ("PO Box 1234 STN Main", "PO Box 1234, STN Main") or a
    # mailbox-store street address ("123 Street Rd #456") is the business mailing address.
    box = re.search(r"\b(?:P\.?\s?O\.?\s+)?Box\b\s*#?\s*([^\s,]*)", street, re.IGNORECASE)
    civic = re.search(r"\b\d+[A-Za-z]?\b", street)
    number = box.group(1) if box else (civic.group(0) if civic else "")
    if not re.fullmatch(r"\d+[A-Za-z]?", number) or int(re.match(r"\d+", number).group(0)) == 0:
        return "the street address needs a street number, or the PO Box its number"
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

# Pages owned by templates. path → template, metadata, and the flag that must be on.
PAGES = [
    {"template": "pages/home.html", "path": "/", "requires_flag": None,
     "title": "donttrade — behavioural measurement for trading firms",
     "description": "We measure the plan gap: how traders plan to act versus how they act. Fixed price, "
                    "public script, run on your own systems.", "og_image": "/assets/og/home.png",
     "updated": "2026-10-21"},
]

# Free tools (steps 10-12). connect-src stays 'none' (the csp_for default): these pages
# cannot send anything, which is what makes "your file is not uploaded" true.
PAGES += [
    {"template": "pages/tool-trade-stats.html", "path": "/tools/trade-stats/", "requires_flag": None,
     "modules": ["/static/js/tools/trade-stats.js"], "sample": True, "app": True, "updated": "2026-10-21",
     "crumb": "Trade stats from your own trade file",
     "title": "Free MT5 Report Analyzer: Trade Stats From Your File",
     "description": "Drop your MT5, MT4, IBKR or Tradovate file and get profit factor, expectancy, drawdown and "
                    "streaks, with a real-or-noise check. Runs in your browser."},
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
    {"template": "pages/tools-index.html", "path": "/tools/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Free tools", "itemlist": True,
     "title": "Free Trading Tools That Run in Your Browser",
     "description": "Free tools for your own trades: trade stats with a real-or-noise check, a prop-firm challenge "
                    "simulator, a lot size calculator and more. No sign-up."},
]

# Audience pages (step 14). Titles ≤ 60 and descriptions ≤ 155 characters (SEO-PLAN §3.1).
# Search terms behind these titles are from autocomplete only; volumes are UNVERIFIED.
FORM_JS = "/static/js/form-ref.js"
# The Product JSON-LD description (paid_report only): the same words as the pricing table row.
PRODUCT_TEXT = "Five habits measured in your own trades, with historical dollar figures, plus one re-test."
PAGES += [
    {"template": "pages/for-traders.html", "path": "/for-traders/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Individual traders", "og_image": "/assets/og/traders.png", "scripts": [FORM_JS],
     "title": "Trader Habit Report: Waitlist and Founding Price",
     "description": "A habit report built from your own MT5, IBKR or Tradovate file, with a real-or-noise check "
                    "for each tested habit. Coming soon; join the waitlist.",
     "if_paid": {"title": "Trader Habit Report: Founding Price",
                 "description": "A habit report built from your own MT5, IBKR or Tradovate file, with a "
                                "real-or-noise check for each tested habit. Founding price, one free re-test."}},
    {"template": "pages/for-firms.html", "path": "/for-firms/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Prop firms & brokers", "og_image": "/assets/og/firms.png", "scripts": [FORM_JS],
     "title": "Disposition-Effect Measurement for Prop Firms and Brokers",
     "description": "Fixed-price measurement of whether your traders sell winners more readily than losers: a "
                    "published script, run inside your own systems."},
]

# Forms and the pages around them (step 16). Thank-you pages are noindex and stay out of the sitemap.
PAGES += [
    {"template": "pages/start.html", "path": "/start/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Start here", "og_image": "/assets/og/start.png", "scripts": [FORM_JS],
     "title": "Start a Pilot, Apply to Partner or Join the Waitlist",
     "description": "Request a Pilot measurement, apply to partner as a journal or platform, or join the trader "
                    "waitlist. A short form or an email; no calls.",
     "if_paid": {"title": "Start a Pilot, Apply to Partner or Get the Habit Report",
                 "description": "Request a Pilot measurement, apply to partner as a journal or platform, or get "
                                "the trader habit report. A short form or an email; no calls."}},
    {"template": "pages/for-platforms.html", "path": "/for-platforms/", "requires_flag": None, "updated": "2026-10-21",
     "crumb": "Journals & platforms", "og_image": "/assets/og/platforms.png", "scripts": [FORM_JS],
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
     "question": "What does my own trade history show, and which numbers are more than noise?",
     "input": "Your trade file"},
    {"name": "Prop-firm challenge simulator", "href": "/tools/prop-challenge-simulator/",
     "question": "How would my past trading days have fared under a challenge’s rules?",
     "input": "Your trade file, or win rate and average win and loss; the rules"},
    {"name": "Lot size calculator", "href": "/tools/lot-size-calculator/",
     "question": "How many lots match the amount I chose to risk at this stop?",
     "input": "Balance, risk amount, stop distance, value per point"},
    {"name": "Disposition-effect calculator", "href": "/tools/disposition-calculator/",
     "question": "Were winning positions sold more readily than losing ones?",
     "input": "Four counts of positions sold and held"},
    {"name": "Pass-rate calculator (for firm operators)", "href": "/tools/pass-rate-calculator/",
     "question": "What are one cohort’s evaluation pass rate and payout rate?",
     "input": "Cohort counts"},
]

SAMPLE_CSV = os.path.join(SITE, "static", "samples", "demo-trades.csv")


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


def sample_csv():
    """The synthetic demo file, inlined into the page inside <script type="text/csv">.

    Inlined rather than fetched because the page's CSP is connect-src 'none'. The build
    refuses anything that could end the script element early."""
    with open(SAMPLE_CSV, encoding="utf-8") as f:
        text = f.read()
    if "<" in text or "&" in text:
        die("demo-trades.csv contains '<' or '&'; it cannot be inlined safely")
    return text


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
# Traders | Firms tabs (tabs.js) and the printable "Before you pay" block (print.js).
PAGES.append({"template": "pages/pricing.html", "path": "/pricing/", "requires_flag": None,
              "scripts_if_paid": ["/static/js/tabs.js", "/static/js/print.js"], "product": PRODUCT_TEXT,
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
        pages.append(page)
    return pages


def lifted_fragment(slug):
    with open(os.path.join(LIFTED_DIR, slug + ".html"), encoding="utf-8") as f:
        return f.read()


LIFTED = lifted_pages()
PAGES += LIFTED
LIFTED_PATHS = [p["path"] for p in LIFTED]

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
        parts.append("It stores your light/dark choice in your own browser and, if you buy the habit report, your "
                     "access key there too. For that report your browser sends only stripped trade numbers; our "
                     "server does not keep them, only scrambled fingerprints to check that a re-test is on the same "
                     "history. Your file itself is not uploaded.")
    else:
        parts.append("It stores only your light/dark choice, in your own browser.")
    if flags["paid_report"] or flags["pilot_checkout"]:
        parts.append("Card payments are handled by Stripe.")
    parts.append("Forms send what you type to Web3Forms, which emails it to us, and subscribing opens Substack; "
                 "their privacy policies apply.")
    return " ".join(parts)


# Decision 21 Oct (revised 09:00): with ANY commerce flag on, every page footer identifies the
# business: name, country/province, the mailing address from private.toml and the business email
# (Visa Core Rules 5.8.4.1 "address for Cardholder correspondence" + merchant country; CASL).
# The seller's legal name and phone stay in the seller block (show_seller). With every commerce
# flag off this line does not exist and private.toml is not read. One wording for template
# pages and passthrough pages. build.verify() and lint check every page has it exactly once.
BUSINESS_ID_ATTR = "data-business-id"
BUSINESS_ID_RE = re.compile(r"(?s)<p\b[^>]*\bdata-business-id\b[^>]*>.*?</p>")
BUSINESS_REGION = "Ontario, Canada"


def business_id_line(cfg, private, css_class=None):
    """The footer's business-identification paragraph, or "" with every commerce flag off."""
    import html as _h
    if not any(cfg["flags"][f] for f in COMMERCE_FLAGS):
        return ""
    address = private.get("premises_address")
    if not isinstance(address, str) or not address.strip():
        die("a commerce flag is on but there is no mailing address (private.toml premises_address) for the footer")
    email = cfg["site"]["contact_email"]
    cls = f' class="{css_class}"' if css_class else ""
    return (f"<p{cls} {BUSINESS_ID_ATTR}>{_h.escape(cfg['site']['name'])} · {BUSINESS_REGION} · "
            f"{_h.escape(address)} · <a href=\"mailto:{_h.escape(email)}\">{_h.escape(email)}</a></p>")


# Where the line goes in a passthrough page: just before the "who pays" paragraph, right
# under the contact line (every passthrough page has exactly one).
PASSTHROUGH_BUSINESS_ANCHOR = '  <p class="whopays">'


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


FLAGS = ("paid_report", "analytics", "trader_first_home", "pilot_checkout")
OPTIONAL_FLAGS = {"pilot_checkout": False}  # older site.toml files may lack the line


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
    "legal": ({"terms_version", "disclaimer_short", "disclaimer_long"},
              {"terms_version", "disclaimer_short", "disclaimer_long", "show_seller_for_pilot"}),
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


def load_config():
    toml_path = os.environ.get("DT_SITE_TOML") or os.path.join(SITE, "config", "site.toml")
    cfg = read_toml(toml_path, "site.toml")
    # DT_PRICES_JSON: another prices file (test builds plant a well-formed test link this way,
    # instead of editing the committed one). It is an input, not an escape: every check applies.
    prices_path = os.environ.get("DT_PRICES_JSON") or os.path.join(SITE, "config", "prices.json")
    with open(prices_path, encoding="utf-8") as f:
        prices = json.load(f)
    check_schema(cfg, toml_path)
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
    return cfg, prices, private


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


def usd_fr(n):
    """39,00 $ US — Québec style (FRENCH-LEGAL: amounts written « 79,00 $ US »)."""
    if n != int(n):
        die(f"price {n} is not a whole number of dollars")
    return "{:,}".format(int(n)).replace(",", "\u00a0") + ",00\u00a0$\u00a0US"


def csp_for(page, cfg):
    connect = page.get("connect_src", "'none'")
    if page.get("connect_worker"):
        connect = "'self' " + cfg["worker"]["api_base"]
    if cfg["flags"]["analytics"]:
        connect += " https://cloudflareinsights.com"
    script = "'self'" + (" https://static.cloudflareinsights.com" if cfg["flags"]["analytics"] else "")
    return ("default-src 'self'; script-src " + script + "; style-src 'self'; img-src 'self' data:; "
            "font-src 'self'; connect-src " + connect + "; worker-src 'self'; "
            "form-action 'self' https://api.web3forms.com" + "".join(" " + a for a in page.get("form_action", [])) +
            "; base-uri 'none'; object-src 'none'")


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


def jsonld(page, cfg, html, flags, products):
    """One @graph per page. No address, phone, rating or review anywhere (SEO-PLAN §3.2)."""
    base = cfg["site"]["base_url"]
    org = {"@id": base + "/#org"}
    graph = []
    if page["path"] == "/":
        graph.append({"@type": "WebSite", "@id": base + "/#website", "name": cfg["site"]["name"],
                      "url": base + "/", "publisher": org})
        graph.append({"@type": "Organization", "@id": base + "/#org", "name": cfg["site"]["name"],
                      "url": base + "/", "email": cfg["site"]["contact_email"], "sameAs": cfg["site"]["same_as"]})
    else:
        items = [("Home", base + "/")]
        if page.get("parent"):
            items.append((page["parent"][0], base + page["parent"][1]))
        elif page["path"].startswith("/tools/") and page["path"] != "/tools/":
            items.append(("Free tools", base + "/tools/"))
        items.append((page["crumb"], None))
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
        f.write("\n".join(robots) + "\n")


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


def verify(out, flags, seller=None, base_url=None):
    """seller: whether the seller block may appear (show_seller); defaults to any commerce flag."""
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
    # Decision 21 Oct: the footer business line, on every page exactly once under any commerce flag
    commerce = any(flags.get(f) for f in COMMERCE_FLAGS)
    for root, _, files in os.walk(out):
        for name in sorted(files):
            if name.endswith(".html"):
                fp = os.path.join(root, name)
                with open(fp, encoding="utf-8", errors="replace") as f:
                    text = f.read()
                n, m = text.count(BUSINESS_ID_ATTR), len(BUSINESS_ID_RE.findall(text))
                if commerce and (n != 1 or m != 1):
                    die(f"business line: {os.path.relpath(fp, out)} has {n} business-identification line(s), "
                        "expected exactly 1 while a commerce flag is on")
                if not commerce and n:
                    die(f"business line in {os.path.relpath(fp, out)} while every commerce flag is off")


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
        owned[os.path.relpath(out_file(out, page["path"]), out)] = page

    # 1. passthrough of every docs/ file a template does not own yet
    copy_tree_sorted(DOCS, out, skip=lambda rel: rel in owned)
    for rel in passthrough_pages(owned):
        fp = os.path.join(out, rel)
        with open(fp, encoding="utf-8") as f:
            text = f.read()
        text = fix_passthrough_chrome(text, rel, flags)
        text = add_business_line(text, rel, business_id_line(cfg, private))
        for old, new in PASSTHROUGH_FIXES.get(rel, []):
            if text.count(old) != 1:
                die(f"passthrough fix: {rel} no longer holds this sentence exactly once: {old!r}")
            text = text.replace(old, new)
        with open(fp, "w", encoding="utf-8", newline="") as f:
            f.write(text)
    for rel in sorted(set(PASSTHROUGH_FIXES) - set(passthrough_pages(owned))):
        # a template owns it (a lifted page carries its fixes in its fragment) or it is not in docs/
        die(f"passthrough fix: {rel} is not a passthrough page (owned by a template, or not in docs/)")
    # 2. static assets of the new design
    copy_tree_sorted(os.path.join(SITE, "static"), os.path.join(out, "static"),
                     skip=(None if flags["paid_report"] else (lambda rel: rel.startswith("js" + os.sep + "paid"))))
    # 3. dev pages, only on request; never bundled
    if os.environ.get("DT_DEV") == "1":
        copy_tree_sorted(os.path.join(SITE, "dev"), os.path.join(out, "dev"))

    env = Environment(loader=FileSystemLoader(os.path.join(SITE, "templates")), undefined=StrictUndefined,
                      autoescape=True, keep_trailing_newline=True)
    env.filters["usd"] = usd
    env.filters["usd_fr"] = usd_fr
    products = {p["id"]: p for p in prices["products"]}
    base_ctx = {"site": cfg["site"], "flags": flags, "nav": cfg["nav"], "footer": cfg["footer"],
                "legal": cfg["legal"], "forms": cfg["forms"], "analytics": cfg["analytics"],
                "worker": cfg["worker"], "prices": prices, "products": products, "private": private,
                "stripe_mode": cfg["stripe"]["mode"], "lift": lift_sections, "tools": TOOLS,
                "evidence": evidence(), "footer_privacy": footer_privacy(flags), "show_seller": show_seller(cfg),
                "business_id_line": Markup(business_id_line(cfg, private, "legal"))}
    built = []
    for rel, page in sorted(owned.items()):
        page = {"scripts": [], "modules": [], "og_image": "/assets/og/default.png", "lang": "en",
                "alternates": [], **page}
        if flags["paid_report"]:
            page["scripts"] = page["scripts"] + page.get("scripts_if_paid", [])
            page["alternates"] = page.get("alternates_if_paid", page["alternates"])
            page.update(page.get("if_paid", {}))  # R5: title/description that sell instead of "waitlist"
        extra = {"sample_csv": sample_csv()} if page.get("sample") else {}
        if page.get("lifted"):
            extra["lifted_html"] = Markup(lifted_fragment(page["lifted"]))
        html = env.get_template(page["template"]).render(page=page, csp=csp_for(page, cfg), **base_ctx, **extra)
        if html.count(LD_MARKER) != 1:
            die(f"{page['template']}: the JSON-LD marker must appear exactly once")
        html = html.replace(LD_MARKER, jsonld(page, cfg, html, flags, products))
        fp = os.path.join(out, rel)
        os.makedirs(os.path.dirname(fp), exist_ok=True)
        with open(fp, "w", encoding="utf-8", newline="\n") as f:
            f.write(html)
        built.append(page)
    write_sitemap_and_robots(out, cfg, built, flags)

    verify(out, flags, seller=show_seller(cfg), base_url=cfg["site"]["base_url"])
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
