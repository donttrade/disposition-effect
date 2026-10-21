"""Steps 13–17: the template-owned pages (home, for-traders, for-firms, pricing, start,
for-platforms, thank-you pages, privacy, terms).

Shared checks for every page: axe 0 serious/critical in both themes with every <details>
open, no horizontal overflow at 320/375/1280, every internal link and #anchor resolves
in the build, no console errors, title 10–70 and description 50–160 characters, one h1.
Page-specific checks follow below.
"""
import os
import re
import sys
from html.parser import HTMLParser

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import build as B  # noqa: E402
from test_legal import LAUNCH_HUMAN  # noqa: E402  (Manager C3: [legal] launch_date)

PAGES = ["/", "/for-traders/", "/for-firms/", "/pricing/", "/start/", "/for-platforms/", "/start/thanks/",
         "/for-traders/thanks/", "/thanks/", "/privacy/", "/terms/"]
# Links to anchors that the NEXT step builds. Each step that builds one removes it here.
FORWARD = set()

# Every id of today's page that must survive the rebuild (checks/urls-baseline.txt lists the
# externally linked ones; these are all ids on the old pages, minus "main" which base.html has).
OLD_IDS = {
    "/for-traders/": ["founding"],
    "/for-firms/": ["what-it-costs", "copy-leader", "claims-test"],
    "/start/": ["firm", "platform", "trader"],
    "/pricing/": ["firms", "copy-leader", "claims-test", "platforms", "traders", "researchers", "payment",
                  "refunds", "history", "questions"],
}
# v1 rule (checks/tests/test_site_content.py): an assurance word only in a sentence with a negation.
V1_BANNED = re.compile(r"\b(certif(?:ied|ication|y)|verif(?:ied|ication|y)|audit(?:ed|s)?)\b(?!/)", re.I)
V1_NEG = re.compile(r"\b(not|never|no one|nothing|don[’']t|no longer|nor|isn[’']t|without|no)\b", re.I)


def visible(html):
    import html as H
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", html))).strip()


def html_of(site, path):
    return (site["out"] / B.out_file("", path).lstrip("/")).read_text(encoding="utf-8")


class _Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.hrefs, self.ids, self.h1 = [], set(), 0

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if "id" in a:
            self.ids.add(a["id"])
        if tag == "h1":
            self.h1 += 1
        for k in ("href", "src", "srcset", "action"):
            if a.get(k):
                self.hrefs.append(a[k])


def parse(html):
    p = _Links()
    p.feed(html)
    return p


@pytest.mark.parametrize("path", PAGES)
def test_internal_links_and_anchors_resolve(built_site, path):
    page = parse(html_of(built_site, path))
    assert page.h1 == 1
    bad = []
    for h in page.hrefs:
        if h.startswith(("http://", "https://", "mailto:", "data:")) or h in FORWARD:
            continue
        target, _, frag = h.partition("#")
        target = target.split("?")[0]
        if target == "":
            if frag and frag not in page.ids:
                bad.append(h)
            continue
        fp = built_site["out"] / target.lstrip("/")
        if target.endswith("/"):
            fp = fp / "index.html"
        if not fp.exists():
            bad.append(h)
        elif frag and fp.suffix == ".html" and not re.search(r'\sid="' + re.escape(frag) + '"', fp.read_text(encoding="utf-8")):
            bad.append(h)
    assert bad == []


@pytest.mark.parametrize("path", PAGES)
def test_title_description_lengths(built_site, path):
    html = html_of(built_site, path)
    title = re.search(r"<title>(.*?)</title>", html).group(1)
    desc = re.search(r'<meta name="description" content="([^"]*)"', html).group(1)
    assert 10 <= len(title) <= 70 and 50 <= len(desc) <= 160, (len(title), len(desc))


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 1280])
@pytest.mark.parametrize("path", PAGES)
def test_axe_overflow_console(browser, built_site, path, width, scheme):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.on("response", lambda r: errs.append(f"HTTP {r.status} {r.url}") if r.status >= 400 else None)
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("networkidle")
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert horizontal_overflow(pg) == []
    if width != 320:  # axe once per theme per layout is enough; 320 is checked for overflow
        assert axe_violations(pg) == []
    assert errs == []
    ctx.close()


# ------------------------------------------------------------------ step 13: home
def test_home_numbers_come_from_data(built_site):
    html = html_of(built_site, "/")
    ev = B.evidence()
    assert f"{ev['studies']} published studies" in html
    assert f"Scripts public for {ev['scripts_public']} of {ev['studies']}" in html
    assert f"{ev['corrections']} corrections, dated and logged" in html
    study = (built_site["out"] / "research" / "disposition-effect" / "index.html").read_text(encoding="utf-8")
    finding = ev["finding"]["pct"] + " " + ev["finding"]["rest"]
    assert finding in study  # word for word on the study page
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))
    assert ev["finding"]["pct"] in text and ev["finding"]["rest"] in text


def test_home_has_no_firm_prices_and_the_trader_cta(built_site):
    html = html_of(built_site, "/")
    prices = __import__("json").load(open(os.path.join(REPO, "site", "config", "prices.json")))
    for p in prices["products"]:
        if p["audience"] == "firm":
            assert B.usd(p["price_usd"]) not in html, p["id"]
    assert "Join the waitlist — $39 founding price" in html
    assert not re.search(r"\btrial\b", re.sub(r"<[^>]+>", " ", html), re.I)
    assert "standard" not in html.lower() or "after launch" not in html.lower()


OLD_HERO_ALT = ("The free trade-stats dashboard on the synthetic sample file: 160 closed trades, a net result of plus "
                "277.95 US dollars, win rate 51.9%, profit factor 1.14, and an equity and drawdown chart.")


def test_home_hero_is_the_real_dashboard_capture(browser, built_site):
    """Motion plan I21 (+ I10's markup half): the hero is the tool's own markup, captured on the current
    sample, with the tool's numbers, no free-badge text, no ids, and no OS-only <picture> source."""
    import hashlib
    from lint import FREE_BADGE_STRINGS
    part = open(os.path.join(REPO, "site", "templates", "partials", "hero_dashboard.html"), encoding="utf-8").read()
    sha = hashlib.sha256(open(os.path.join(REPO, "site", "static", "samples", "demo-trades.csv"), "rb").read()).hexdigest()
    assert re.search(r"sample-sha256: ([0-9a-f]{64})", part).group(1) == sha
    body = part.split("#}", 1)[1]
    assert " id=" not in body and not [x for x in FREE_BADGE_STRINGS if x in body]
    assert len(part.encode("utf-8")) <= 8 * 1024
    html = html_of(built_site, "/")
    assert html.count('class="hero-dash"') == 1 and "<picture" not in html and "<source" not in html
    assert f'role="img" aria-label="{OLD_HERO_ALT}"' in html
    assert "Sample data, not a real trader." in html
    assert not (built_site["out"] / "static" / "img").exists(), "the old hero .webp images are gone"
    hero = re.findall(r"<dd data-count[^>]*>([^<]*)</dd>", html)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/tools/trade-stats/")
    pg.click("#ts-sample-btn")
    pg.wait_for_selector("#ts-out dl.stats dd")
    tool = pg.eval_on_selector_all("#ts-out dl.stats dd", "ds => ds.map(d => d.textContent)")
    ctx.close()
    assert hero == tool and len(hero) == 6, (hero, tool)


# ------------------------------------------------------------------ shared wording checks
@pytest.mark.parametrize("path", PAGES)
def test_wording_rules(built_site, path):
    text = visible(html_of(built_site, path))
    for sent in re.split(r"(?<=[.!?])\s+", text):
        if V1_BANNED.search(sent):
            assert V1_NEG.search(sent), sent
    # "Trial" only in the formerly line; no regular-price wording; no competitor price talk
    for m in re.finditer(r"\btrial\b", text, re.I):
        assert f"called “Trial” before {LAUNCH_HUMAN}" in text[max(0, m.start() - 10):m.end() + 30], text[m.start() - 60:m.end() + 60]
    assert not re.search(r"standard (prices?|after launch)|regular price|\$49|\$99", text, re.I)


@pytest.mark.parametrize("path", sorted(OLD_IDS))
def test_old_ids_kept(built_site, path):
    ids = parse(html_of(built_site, path)).ids
    assert set(OLD_IDS[path]) <= ids


# ------------------------------------------------------------------ step 14 (+16): forms
# v3 (ARCHITECT-V3 §c.6): /start/ has one form per firm product, each in its own section (#pilot, #memo, …)
FORM_PAGES = {"/for-traders/": "#wl", "/for-firms/": "#ff", "/start/#pilot": "#sf-pilot", "/start/#memo": "#sf-memo",
              "/start/#platform": "#sp",
              "/start/#trader": "#wl", "/for-platforms/": "#fp"}
FIRM_KEY = "f8fdba04-71bb-4856-b700-01ac6796c252"
TRADER_KEY = "54d01baf-5e02-4d93-988c-16cf5487732d"


def _fill(pg, form):
    for el in pg.query_selector_all(form + " input[required], " + form + " textarea[required]"):
        t = el.get_attribute("type")
        if t == "email":
            el.fill("test-ignore@example.com")
        elif t == "checkbox":
            el.check()
        elif t == "radio":
            el.check()
        else:
            el.fill("TEST - ignore")


@pytest.mark.parametrize("path", sorted(FORM_PAGES))
def test_form_posts_with_javascript_off(browser, built_site, path):
    """The form POSTs to Web3Forms with JS off, with key, redirect, product, page, ref and honeypot."""
    form = FORM_PAGES[path]
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 375, "height": 900})
    pg = ctx.new_page()
    posted = []

    def handle(route):
        posted.append(route.request.post_data or "")
        route.fulfill(status=200, body="ok")
    pg.route("https://api.web3forms.com/**", handle)
    base, _, frag = path.partition("#")
    pg.goto(built_site["url"] + base + "?ref=x1" + ("#" + frag if frag else ""))
    _fill(pg, form)
    pg.click(form + " button[type=submit]")
    pg.wait_for_timeout(500)
    ctx.close()
    assert len(posted) == 1
    from urllib.parse import parse_qs
    body = {k: v[0] for k, v in parse_qs(posted[0], keep_blank_values=True).items()}
    assert body["access_key"] == (TRADER_KEY if form == "#wl" else FIRM_KEY)
    assert body["page"] == base and "botcheck" not in body  # unticked honeypot is not sent
    assert body["redirect"].startswith("https://donttrade.ca/") and body["redirect"].endswith("/thanks/")
    assert body["product"] in ("waitlist", "pilot", "platform", "memo") and body["ref"] == ""  # JS off: defaults


@pytest.mark.parametrize("path", sorted(FORM_PAGES))
def test_form_ref_capture_and_fields(browser, built_site, path):
    form = FORM_PAGES[path]
    base, _, frag = path.partition("#")
    html = html_of(built_site, base)
    assert "tally.so" not in html
    ctx = browser.new_context(viewport={"width": 375, "height": 900})
    pg = ctx.new_page()
    hash_ = "#" + frag if frag else ""
    pg.goto(built_site["url"] + base + "?ref=report&product=copy-leader" + hash_)
    assert pg.input_value(form + " input[name=ref]") == "report"
    if form in ("#ff", "#sf-pilot", "#sf-memo", "#sp", "#fp"):
        # the /for-firms/ form takes ?product=; the partner form (Tester D1) and the /start/ product forms (v3 C3) are fixed
        fixed = {"#sp": "platform", "#fp": "platform", "#sf-pilot": "pilot", "#sf-memo": "memo"}
        assert pg.input_value(form + " input[name=product]") == fixed.get(form, "copy-leader")
        f = form.lstrip("#")
        assert pg.get_attribute(f"#{f}-email", "autocomplete") == "email"
        assert pg.get_attribute(f"#{f}-firm", "autocomplete") == "organization"
        assert pg.get_attribute(f"#{f}-role", "autocomplete") == "organization-title"
    else:
        assert not pg.is_checked("#wl-consent") and pg.get_attribute("#wl-consent", "required") is not None
    # botcheck honeypot present and hidden; every visible field has a label; targets >= 44 px
    assert pg.locator(form + " input[name=botcheck]").count() == 1 and not pg.is_visible(form + " input[name=botcheck]")
    for el in pg.query_selector_all(form + " input:not([type=hidden]):not([name=botcheck]), " + form + " textarea"):
        assert pg.locator(f"label[for='{el.get_attribute('id')}']").count() == 1
    for el in pg.query_selector_all(form + " button, " + form + " input[type=email], " + form + " input[type=text]"):
        assert el.bounding_box()["height"] >= 44
    assert pg.locator("a[href^='mailto:']").count() >= 1
    pg.goto(built_site["url"] + base + "?ref=<script>" + hash_)
    assert pg.input_value(form + " input[name=ref]") == ""
    ctx.close()


def test_for_firms_pilot_rename_and_prices(built_site):
    html = html_of(built_site, "/for-firms/")
    text = visible(html)
    assert f"Pilot (called “Trial” before {LAUNCH_HUMAN})" in text
    assert text.count("Trial") == 1
    assert "Start a Pilot — $745 USD" in text
    assert "Card payments are accepted through a secure Stripe link, sent only after you accept the scope." in text
    assert "buy.stripe.com" not in html  # pilot_checkout off


def test_for_traders_waitlist_and_privacy_wording(built_site):
    text = visible(html_of(built_site, "/for-traders/"))
    assert "Join the waitlist — $39 founding price" in text
    assert "$39 founding price for the first 100 buyers" in text
    assert "beta" in text and "not uploaded" in text
    for bad in ("nothing leaves", "never leaves", "anonymous"):
        assert bad not in text.lower()


# ------------------------------------------------------------------ step 15: pricing
def test_pricing_prices_match_prices_json(built_site):
    import json
    prices = json.load(open(os.path.join(REPO, "site", "config", "prices.json")))
    html = html_of(built_site, "/pricing/")
    rows = re.findall(r'<tr><th scope="row">([^<]+)</th>.*?<td class="num">([^<]+)</td></tr>', html, re.S)
    by_name = {p["name"]: B.usd(p["price_usd"]) for p in prices["products"] if p["audience"] == "firm"}
    assert {n: v for n, v in rows if n in by_name} == by_name
    text = visible(html)
    assert "$1,500 for a Memo" in text  # 25% of the Memo price, computed from the rule
    assert "$39 founding price for the first 100 buyers" in text
    assert 'role="tablist"' not in html and "Before you pay" not in text


# ------------------------------------------------------------------ step 16: thank-you pages
def test_form_redirects_land_on_built_thank_you_pages(built_site):
    for path in ("/start/", "/for-traders/", "/for-firms/", "/for-platforms/"):
        for url in re.findall(r'name="redirect" value="([^"]+)"', html_of(built_site, path)):
            target = url.replace("https://donttrade.ca", "")
            assert (built_site["out"] / target.lstrip("/") / "index.html").exists(), url
    assert "within 1 business day" in visible(html_of(built_site, "/start/thanks/"))
    assert "Nothing is charged" in visible(html_of(built_site, "/for-traders/thanks/"))


def test_home_finding_not_next_to_an_offer(built_site):
    html = html_of(built_site, "/")
    sections = re.findall(r"(?s)<section\b.*?</section>", html)
    i = next(k for k, s in enumerate(sections) if "76.1%" in s)
    for s in (sections[i - 1], sections[i + 1]):
        t = visible(s)
        assert "$" not in t and "Start a Pilot" not in t and "waitlist" not in t.lower(), t[:200]
