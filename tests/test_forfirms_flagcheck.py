"""8 Nov 2026: /for-firms/ leads with Flag Check (PLAN-FORFIRMS-FLAGCHECK.md; research memo 00-DECISION-MEMO action 1).

Flag Check is one flagged payout case, sold by email reply and invoice: no Stripe link and no card checkout. Its
amounts live in prices.json "flagcheck" and harvest_prices.allowed_amounts accepts them. The free study, the US$745
Pilot and the US$0.50-per-account plan stay lower on the page under "Measure your whole book"."""
import copy
import json
import os
import re
import sys
from urllib.parse import parse_qs, unquote, urlsplit

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks"))
from harvest_prices import FLAGCHECK_AMOUNT_KEYS, allowed_amounts, amounts_in  # noqa: E402

PRICES = json.load(open((os.environ.get("DT_PRICES_JSON") or os.path.join(REPO, "site", "config", "prices.json")),
                        encoding="utf-8"))
FC = PRICES["flagcheck"]
PRODUCTS = {p["id"]: p for p in PRICES["products"]}


def html(built_site, path):
    return (built_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")


def text(h):
    h = re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<dialog.*?</dialog>", " ", h)
    return " ".join(re.sub(r"<[^>]+>", " ", h).split())


def main_of(h):
    return re.search(r"(?s)<main.*?</main>", h).group(0)


def upper(h):
    """The Flag Check part of /for-firms/: everything in <main> above "Measure your whole book"."""
    m = main_of(h)
    return m[:m.index('id="whole-book"')]


# ------------------------------------------------------------------ prices.json and the harvest
def test_flagcheck_prices_are_the_memo_ladder():
    assert (FC["case_founding_usd"], FC["case_founding_cases"], FC["case_list_usd"]) == (149, 10, 249)
    assert (FC["pilot_usd"], FC["pilot_cases"], FC["pilot_firms"]) == (490, 5, 3)
    assert (FC["monthly_usd"], FC["monthly_cases"], FC["extra_case_usd"]) == (990, 15, 59)
    assert FC["contact"] == "research@donttrade.ca"
    assert "flagcheck" not in PRODUCTS   # invoiced: never a product, so never a Stripe link or JSON-LD offer
    assert PRODUCTS["pilot"]["price_usd"] == 745 and PRODUCTS["plan"]["price_usd"] == 0.5   # kept, lower on the page


def test_harvest_accepts_flagcheck_amounts_and_still_refuses_a_stray_one():
    ok = allowed_amounts(PRICES)
    for k in FLAGCHECK_AMOUNT_KEYS:
        assert FC[k] in ok, k
    assert 4000 not in ok and 199 not in ok
    # counts, hours and days are not dollar amounts
    assert FC["report_hours"] not in ok and FC["intake_hours"] not in ok
    # removing the flagcheck block removes its amounts (nothing hard-coded)
    p = copy.deepcopy(PRICES)
    del p["flagcheck"]
    assert not {149, 249, 490, 990} & allowed_amounts(p)


# ------------------------------------------------------------------ /for-firms/
def test_for_firms_leads_with_flag_check(built_site):
    h = html(built_site, "/for-firms/")
    assert re.search(r'<h1 id="ff-h">An independent check on a flagged payout</h1>', h)
    assert h.count("<h1") == 1
    t = text(upper(h))
    assert "Does the flag beat coincidence?" in t
    assert f"US${FC['case_founding_usd']} a case for the first {FC['case_founding_cases']} cases, then US${FC['case_list_usd']}" in t
    # Flag Check comes before every whole-book offer
    m = main_of(h)
    assert m.index("Flag Check") < m.index('id="whole-book"') < m.index('id="study-status"') < m.index('id="what-it-costs"')
    assert "<title>Flag Check" in h


def test_for_firms_price_ladder_from_prices_json(built_site):
    t = text(upper(html(built_site, "/for-firms/")))
    for s in (f"US${FC['case_founding_usd']} a case", f"US${FC['pilot_usd']} once", f"US${FC['monthly_usd']} a month",
              f"Founding price for the first {FC['case_founding_cases']} cases, then US${FC['case_list_usd']}",
              "Five cases within 30 days", "For the first three firms",
              f"All US${FC['pilot_usd']} credited to the monthly plan if it starts within {FC['pilot_credit_days']} days",
              f"Up to {FC['monthly_cases']} cases a month", f"US${FC['extra_case_usd']} a case after that",
              f"due in {FC['payment_days']} days", f"within {FC['report_hours']} hours of a complete file",
              "Prices in US$"):
        assert s in t, s
    assert set(amounts_in(t)) <= allowed_amounts(PRICES)
    assert len(re.findall(r'<section class="price-card[^"]*"', upper(html(built_site, "/for-firms/")))) == 3


def test_flag_check_is_sold_by_email_not_stripe(built_site):
    h = html(built_site, "/for-firms/")
    up = upper(h)
    assert "buy.stripe.com" not in up and "data-pay" not in up
    mailtos = re.findall(r'href="(mailto:[^"]+)"', up)
    assert len(mailtos) >= 3
    for href in mailtos:
        u = urlsplit(href.replace("&amp;", "&"))
        assert u.path == "research@donttrade.ca", href
        q = parse_qs(u.query)
        assert q["subject"] == ["Flag Check: [your firm]"], href
    body = parse_qs(urlsplit(mailtos[0].replace("&amp;", "&")).query)["body"][0]
    assert "do not attach trader data" in body.lower()
    # the form alternative posts product=flagcheck, fixed (never relabelled by ?product=)
    form = re.search(r'(?s)<form class="request-form" id="fc".*?</form>', up).group(0)
    assert re.search(r'name="product" value="flagcheck">', form)
    assert "gmail" not in up


def test_no_trader_pay_button_on_for_firms(built_site):
    h = html(built_site, "/for-firms/")
    header = re.search(r'(?s)<header class="site-header">.*?</header>', h).group(0)
    assert "data-pay" not in header and "Get the report for" not in header
    assert "Get the report for" not in text(h)


def test_method_and_verdicts_in_plain_words(built_site):
    t = text(upper(html(built_site, "/for-firms/")))
    for s in ("within 30 seconds", "sizes within 20%", "at least 5 matches", "at least half",
              "who traded first?", "at least 8 matches", "no known link", "written down on 7 Nov 2026",
              "Supported", "Not supported", "Cannot tell",
              "account code, time in UTC, symbol, side and size",
              "We never need names, emails, logins, IP addresses or balances",
              "We promise no verdict", "billed like any other",
              "It does not decide why anyone traded, or whether a rule was broken",
              "No firm has bought a Flag Check yet", "there is no specimen report yet"):
        assert s in t, s
    assert "Inconclusive" not in t   # one verdict set everywhere: Supported / Not supported / Cannot tell
    assert "guarantee" not in t.lower()


def test_no_invented_proof_on_for_firms(built_site):
    t = text(html(built_site, "/for-firms/"))
    for bad in ("testimonial", "trusted by", "our clients include", "case study", "1 in 4", "bind prop firms",
                "€150", "4,000"):
        assert bad.lower() not in t.lower(), bad


def test_whole_book_offers_stay_lower_on_the_page(built_site):
    h = html(built_site, "/for-firms/")
    m = main_of(h)
    low = text(m[m.index('id="whole-book"'):])
    assert "Measure your whole book" in low
    assert "US$0.50 per trader account a month" in low and "US$500 minimum" in low   # 8 Nov: one format, "US$39"
    assert f"Start a {PRODUCTS['pilot']['name']}: US$745" in low and "US$745 USD" not in low
    assert "One habit today, more being added." in low and "The study is free." in low
    for a in ("study-status", "study-request", "study-price", "what-it-costs", "copy-leader", "claims-test",
              "request", "faq-h", "flagcheck", "flagcheck-how", "flagcheck-price", "flagcheck-send", "whole-book"):
        assert len(re.findall(rf'id="{a}"', h)) == 1, a


def test_for_firms_has_no_inline_script_or_style(built_site):
    h = html(built_site, "/for-firms/")
    assert not re.search(r"<script(?![^>]*\bsrc=)[^>]*>", h.split("</head>", 1)[1])
    assert " style=" not in h
    csp = re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', h).group(1).replace("&#39;", "'")
    script_src = re.search(r"script-src ([^;]+)", csp).group(1).split()
    assert script_src[0] == "'self'" and "'unsafe-inline'" not in script_src   # the rest: the site-wide analytics hosts
    assert "'unsafe-inline'" not in re.search(r"style-src ([^;]+)", csp).group(1)


# ------------------------------------------------------------------ /pricing/ firm line
def test_pricing_firm_line_points_to_for_firms(built_site):
    """8 Nov 2026 (owner, trust fixes): the Flag Check card that the 17:00 run put on /pricing/ is replaced by one line to
    /for-firms/, where every firm price is. No Flag Check amount on /pricing/, in the line or the FAQ."""
    h = html(built_site, "/pricing/")
    firm = re.search(r'(?s)<p class="firm-line" id="firms">.*?</p>', main_of(h)).group(0)
    t = text(firm)
    assert "flagged payout cases" in t and 'href="/for-firms/"' in firm and "buy.stripe.com" not in firm
    faq = text(re.search(r"(?s)<summary>What does a firm pay\?</summary>.*?</details>", h).group(0))
    assert 'href="/for-firms/#flagcheck-price"' in re.search(r"(?s)<summary>What does a firm pay\?</summary>.*?</details>", h).group(0)
    for k in ("case_founding_usd", "case_list_usd", "pilot_usd", "monthly_usd", "extra_case_usd"):
        assert f"US${FC[k]}" not in text(main_of(h)), k
    assert "$" not in faq


# ------------------------------------------------------------------ phone width
@pytest.mark.parametrize("width", [320, 375])
def test_for_firms_fits_a_phone(browser, built_site, width):
    ctx = browser.new_context(viewport={"width": width, "height": 800})
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(built_site["url"] + "/for-firms/")
    over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
    assert over <= 0, f"{over}px of sideways scroll at {width}px"
    # the three price cards stack in one column, the case card first
    tops = pg.eval_on_selector_all("section[aria-labelledby='flagcheck-price'] .price-card","els => els.map(e => e.getBoundingClientRect().top)")
    assert len(tops) == 3 and tops == sorted(tops)
    assert pg.is_visible("#flagcheck a.btn[href^='mailto:']")
    assert errors == []
    ctx.close()
