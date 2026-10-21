#!/usr/bin/env python3
"""donttrade v2 site build: site.toml + prices.json + Jinja2 templates → site/_site/.

Rules (V2-BUILD-PLAN, STRUCTURE and step 3):
  * Every page of today's docs/ that no template owns yet is copied through
    unchanged, so the output always holds every baseline URL.
  * The build FAILS LOUDLY (exit 1, with the reason) on:
      - a path in checks/urls-baseline.txt missing from the output,
      - an externally linked id (path#id in the baseline) missing from its page,
      - trader_first_home != paid_report, or analytics on without a beacon token,
      - a paid-only page or paid-flagged markup in the output while paid_report is off,
      - a placeholder left in private.toml when paid_report is on
        (unless DT_ALLOW_PLACEHOLDERS=1, for local test builds only).
  * Output is deterministic: sorted walks, no timestamps, so two builds are byte-identical.

Environment:
  DT_DEV=1                 also build site/dev/ (styleguide, sniffer) into _site/dev/
  DT_SITE_TOML=path        use another site.toml (test builds with flags on)
  DT_OUT=path              write somewhere other than site/_site
  DT_ALLOW_PLACEHOLDERS=1  allow private.toml placeholders (local test mode only)
  DT_BASELINE=path         use another URL baseline (tests plant a missing URL this way)
  DT_PRIVATE_TOML=path     read private.toml from elsewhere (flag-on test builds)
"""

import json
import os
import re
import shutil
import sys
import tomllib

from jinja2 import Environment, FileSystemLoader, StrictUndefined

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
PLACEHOLDER_RE = re.compile(r"\[[A-Z ]+ — [^\]]+\]")

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
                    "for each habit. Coming soon; join the waitlist."},
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
                    "waitlist. A short form or an email; no calls."},
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
     "description": "You joined the donttrade trader waitlist. Nothing is charged; one email when the report launches."},
    {"template": "pages/thanks.html", "path": "/thanks/", "requires_flag": None, "noindex": True,
     "crumb": "Thank you", "title": "Thank you — donttrade",
     "description": "Your message reached donttrade. Firms get a reply within 1 business day; traders get one email at launch."},
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
    def main_of(rel):
        with open(os.path.join(DOCS, rel), encoding="utf-8") as f:
            return f.read()
    studies = sorted(set(re.findall(r'href="(/research/[a-z0-9-]+/)"', main_of("research/index.html"))))
    corr = main_of("corrections/index.html")
    t = re.search(r"(?s)<table.*?<tbody>(.*?)</tbody>", corr)
    if not t:
        die("evidence: no corrections table in docs/corrections/index.html")
    corrections = len(re.findall(r"<tr\b", t.group(1)))
    m = re.search(r"The scripts behind (\d+) of the (\d+) studies are public", main_of("code/index.html"))
    if not m:
        die("evidence: the 'scripts behind N of the M studies' sentence is gone from docs/code/index.html")
    if int(m.group(2)) != len(studies):
        die(f"evidence: /code/ says {m.group(2)} studies but /research/ lists {len(studies)}")
    sentence = "76.1% of 4,659 retail traders realised their gains more readily than their losses."
    if sentence not in main_of("research/disposition-effect/index.html"):
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
              "crumb": "Pricing", "updated": "2026-10-21", "og_image": "/assets/og/pricing.png",
              "title": "Pricing: Published Prices for Firms and Traders",
              "description": "Published prices in USD for prop firms, brokers, trading platforms and traders, the "
                             "same for everyone and fixed in writing before anyone sees data."})

# Paths that may exist only when paid_report = true.
PAID_APP_PATHS = ["/welcome/", "/restore/", "/report/"]  # noindex, and disallowed in robots.txt
PAID_ONLY_PATHS = PAID_APP_PATHS + PAID_ONLY_PATHS_FR


class BuildError(Exception):
    pass


def die(msg):
    raise BuildError(msg)


def load_config():
    toml_path = os.environ.get("DT_SITE_TOML") or os.path.join(SITE, "config", "site.toml")
    with open(toml_path, "rb") as f:
        cfg = tomllib.load(f)
    with open(os.path.join(SITE, "config", "prices.json"), encoding="utf-8") as f:
        prices = json.load(f)
    flags = cfg["flags"]
    if flags["trader_first_home"] != flags["paid_report"]:
        die(f"flag mismatch: trader_first_home={flags['trader_first_home']} must equal "
            f"paid_report={flags['paid_report']} ({toml_path})")
    if flags["analytics"] and not cfg["analytics"]["cf_beacon_token"]:
        die("analytics = true but [analytics] cf_beacon_token is empty")
    flags.setdefault("pilot_checkout", False)
    private = {}
    on = [f for f in COMMERCE_FLAGS if flags[f]]
    if on:
        # Seller disclosure (O. Reg. 17/05 s. 32): legal name, premises address, phone. These come
        # ONLY from the gitignored private.toml, read ONLY while a commerce flag is on.
        p = os.environ.get("DT_PRIVATE_TOML") or os.path.join(SITE, "config", "private.toml")
        if not os.path.exists(p):
            die(f"{', '.join(on)} = true needs site/config/private.toml (copy private.example.toml)")
        with open(p, "rb") as f:
            private = tomllib.load(f)
        for k in PRIVATE_FIELDS:
            if not isinstance(private.get(k), str) or not private[k].strip():
                die(f"{', '.join(on)} = true but private.toml is missing {k} (or it is empty)")
            if PLACEHOLDER_RE.search(private[k]) and os.environ.get("DT_ALLOW_PLACEHOLDERS") != "1":
                die(f"private.toml {k} still holds a placeholder; fill it in "
                    "(or set DT_ALLOW_PLACEHOLDERS=1 for a local test build only)")
    if flags["pilot_checkout"]:
        pilot = next(p for p in prices["products"] if p["id"] == "pilot")
        if not pilot["stripe_link_live"]:
            die("pilot_checkout = true but prices.json has no stripe_link_live for the pilot")
    if flags["paid_report"]:
        mode = cfg["stripe"]["mode"]
        if mode not in ("test", "live"):
            die(f"[stripe] mode must be test or live, not {mode!r}")
        for p in prices["products"]:
            if p["requires_flag"] == "paid_report" and p["id"] == "report39":
                if not p["stripe_link_" + mode] and os.environ.get("DT_ALLOW_PLACEHOLDERS") != "1":
                    die(f"paid_report = true but prices.json has no stripe_link_{mode} for report39")
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
            "form-action 'self' https://api.web3forms.com; base-uri 'none'; object-src 'none'")


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
        if page["path"].startswith("/tools/") and page["path"] != "/tools/":
            items.append(("Free tools", base + "/tools/"))
        items.append((page["crumb"], None))
        graph.append({"@type": "BreadcrumbList", "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "name": n, **({"item": u} if u else {})}
            for i, (n, u) in enumerate(items)]})
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


def verify(out, flags):
    paths, ids = read_baseline()
    for p in paths:
        if not os.path.exists(out_file(out, p) if p.endswith("/") else os.path.join(out, p.lstrip("/"))):
            die(f"baseline URL missing from the build: {p}")
    for p, i in ids:
        with open(out_file(out, p), encoding="utf-8") as f:
            html = f.read()
        if not re.search(r'\sid="' + re.escape(i) + '"', html):
            die(f"externally linked id missing: {p}#{i}")
    if not any(flags.get(f) for f in COMMERCE_FLAGS):
        for root, _, files in os.walk(out):
            for name in sorted(files):
                if name.endswith(".html"):
                    fp = os.path.join(root, name)
                    with open(fp, encoding="utf-8", errors="replace") as f:
                        if "data-seller-block" in f.read():
                            die(f"seller disclosure in {os.path.relpath(fp, out)} while every commerce flag is off")
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
                "evidence": evidence()}
    built = []
    for rel, page in sorted(owned.items()):
        page = {"scripts": [], "modules": [], "og_image": "/assets/og/default.png", "lang": "en",
                "alternates": [], **page}
        if flags["paid_report"]:
            page["scripts"] = page["scripts"] + page.get("scripts_if_paid", [])
            page["alternates"] = page.get("alternates_if_paid", page["alternates"])
        extra = {"sample_csv": sample_csv()} if page.get("sample") else {}
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

    verify(out, flags)
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
