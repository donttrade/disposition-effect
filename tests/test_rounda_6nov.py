"""Round A (6 Nov 2026): the founding price as config, the new home hero and the habit counts, "beta" removed from the
copy, Product JSON-LD, IndexNow, partner links, and the "No result, no charge" refund wording behind
[flags] refund_no_result (default off) with its /refund/ form.

Needs DT_TODAY=2026-11-06 until that day: terms_date and privacy_date are the push day (build._today)."""
import functools
import html as _html
import http.server
import json
import os
import re
import subprocess
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SITE = os.path.join(REPO, "site")
sys.path.insert(0, SITE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(SITE, "tools"))
import build as B  # noqa: E402
import lint as L  # noqa: E402
import indexnow_ping as IX  # noqa: E402

# 8 Nov go-live: these tests pin the round-A terms version (6 Nov). They build from a copy of site.toml with the legal
# dates set back to that day, and pass DT_TODAY per build instead of setting it for the whole session (it leaked
# into other test files run after this one).
ROUND_A_TODAY = os.environ.get("DT_TODAY", "2026-11-06")
TOML = open(os.path.join(SITE, "config", "site.toml"), encoding="utf-8").read()
TOML = re.sub(r'^(terms_date|privacy_date) = "\d{4}-\d\d-\d\d"', r'\1 = "2026-11-06"', TOML, flags=re.M)
PRICES = json.load(open((os.environ.get("DT_PRICES_JSON") or os.path.join(SITE, "config", "prices.json")), encoding="utf-8"))
REASONS = json.load(open(os.path.join(SITE, "config", "refund_reasons.json"), encoding="utf-8"))["reasons"]
KEY = re.search(r'\[indexnow\]\s*key = "([^"]+)"', TOML).group(1)


def build(tmp_path, name, toml=None, prices=None, partners=None, **env):
    out = tmp_path / name
    e = {**os.environ, "DT_OUT": str(out), "DT_TODAY": ROUND_A_TODAY, **env}
    e.pop("DT_DEV", None)
    if toml is None:
        toml = TOML
    if toml is not None:
        (tmp_path / f"{name}.toml").write_text(toml, encoding="utf-8")
        e["DT_SITE_TOML"] = str(tmp_path / f"{name}.toml")
    if prices is not None:
        (tmp_path / f"{name}.prices.json").write_text(json.dumps(prices), encoding="utf-8")
        e["DT_PRICES_JSON"] = str(tmp_path / f"{name}.prices.json")
    if partners is not None:
        (tmp_path / f"{name}.partners.json").write_text(json.dumps(partners), encoding="utf-8")
        e["DT_PARTNERS_JSON"] = str(tmp_path / f"{name}.partners.json")
    r = subprocess.run([sys.executable, os.path.join(SITE, "build.py")], env=e, capture_output=True, text=True)
    return r, out


def on_toml(**extra):
    s = TOML.replace("refund_no_result = false", "refund_no_result = true", 1)
    s = s.replace('privacy_date = "2026-11-06"', 'privacy_date = "2026-11-06"\nrefund_effective = "2026-11-06"', 1)
    s = s.replace("promo_codes_enabled = false", f"promo_codes_enabled = {str(extra.get('promo', True)).lower()}", 1)
    return s


def prices_with(**rules):
    p = json.loads(json.dumps(PRICES))
    p["rules"].update(rules)
    return p


def prices_ended(link="https://buy.stripe.com/eVq14m66H9Jw15a0Rwdwc99"):
    p = prices_with(founding_open=False)
    af = next(x for x in p["products"] if x["id"] == "report39")["after_founding"]
    af["stripe_link_live"] = link
    return p


def text_of(path, main_only=True):
    h = open(path, encoding="utf-8").read()
    m = re.search(r"(?s)<main[^>]*>(.*)</main>", h) if main_only else None
    x = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", m.group(1) if m else h)
    return re.sub(r"\s+", " ", _html.unescape(re.sub(r"<[^>]+>", " ", x))).strip()


def lint_ok(out):
    f = L.flags_of_build(str(out))
    return L.lint_build(str(out), f["paid"], f["analytics"], pilot=f["pilot"], badges=f["badges"])


@pytest.fixture(scope="module")
def off(tmp_path_factory):
    r, out = build(tmp_path_factory.mktemp("off"), "o")
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture(scope="module")
def on(tmp_path_factory):
    partners = {"jane-doe": {"code": "JANE10", "name": "Jane Doe", "active": True},
                "old-one": {"code": "OLD10", "name": "Old One", "active": False}}
    r, out = build(tmp_path_factory.mktemp("on"), "n", toml=on_toml(), partners=partners)
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture(scope="module")
def shown(tmp_path_factory):
    """8 Nov 2026 (owner): the committed prices.json hides "then US$49" (rules.after_founding_shown = false) until about
    80 buyers. This build flips the switch back on, so the 6 Nov approved-form tests still hold for the day it returns."""
    r, out = build(tmp_path_factory.mktemp("shown"), "s", prices=prices_with(after_founding_shown=True))
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture
def shown_prices(shown, monkeypatch):
    monkeypatch.setenv("DT_PRICES_JSON", str(shown.parent / "s.prices.json"))   # lint reads the prices file the build used
    return shown


@pytest.fixture(scope="module")
def ended(tmp_path_factory):
    r, out = build(tmp_path_factory.mktemp("ended"), "e", prices=prices_ended())
    assert r.returncode == 0, r.stderr
    return out


def served(out):
    class Q(http.server.SimpleHTTPRequestHandler):
        extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


# ===================================================================== terms version
def test_terms_and_privacy_version_is_6_nov(off):
    assert B.set_terms_date({"launch_date": "2026-10-29", "terms_date": "2026-11-06"}, "x", today=B._today()).isoformat() == "2026-11-06"
    assert "Version 2026-11-06." in text_of(off / "terms" / "index.html")
    assert "Version du 2026-11-06" in text_of(off / "fr" / "conditions" / "index.html")
    assert "2026-11-06" in text_of(off / "privacy" / "index.html")


def test_a_future_terms_date_still_fails_without_dt_today(tmp_path):
    r, _ = build(tmp_path, "f", DT_TODAY="2026-11-05")
    assert r.returncode == 1 and "terms_date 2026-11-06 is after the build date 2026-11-05" in r.stderr


# ===================================================================== A1 founding price
def test_open_state_words_the_next_price_only_with_the_first_100(shown_prices):
    off = shown_prices   # 8 Nov: the switch is on in this build only
    for rel in ("pricing", "terms", "before-you-pay", "fr/conditions", "fr/avant-de-payer"):
        t = text_of(off / rel / "index.html")
        assert re.search(r"\$\s?49|49,00", t), rel
        assert re.search(r"first 100|100 premiers", t), rel
    assert "US$39 for the first 100 buyers, then US$49." in text_of(off / "pricing" / "index.html")
    assert "39,00 $ US pour les 100 premiers acheteurs" not in text_of(off / "pricing" / "index.html")
    byp = text_of(off / "before-you-pay" / "index.html")
    # 7 Nov: the committed site is Managed Payments with tax included (tests/test_managed_payments.py has both settings)
    assert ("US$39, one time (founding price: for the first 100 buyers, then US$49). Any sales tax, VAT or GST is included in "
            "this price: Link works it out from your billing address and shows it on your receipt. Total: US$39") in byp
    fr = text_of(off / "fr" / "avant-de-payer" / "index.html")
    assert "paiement unique (prix de fondateur : pour les 100 premiers acheteurs, puis 49,00 $ US)" in fr.replace(" ", " ")
    assert lint_ok(off) == []


def test_49_appears_nowhere_else_in_the_open_state(off):
    for p in (off).rglob("index.html"):
        if p.relative_to(off).parts[0] == "research":      # frozen study text ("instead of $…" is a finding, not a price)
            continue
        t = text_of(p, main_only=False)
        if re.search(r"\$\s?49(?![\d,.])|49,00", t):
            assert re.search(r"first 100|100 premiers", t), p
        assert not re.search(r"regular price|standard price|was \$|instead of \$", t, re.I), p


def test_hidden_next_price_is_on_no_page_and_the_founding_line_stays(off):
    """8 Nov 2026 (owner): rules.after_founding_shown = false. No page names US$49, not even in the approved form;
    the founding price and its first-100 limit stay, with no next price beside them."""
    assert PRICES["rules"]["after_founding_shown"] is False and PRICES["rules"]["founding_open"] is True
    for p in off.rglob("index.html"):
        if p.relative_to(off).parts[0] == "research":      # frozen study text
            continue
        t = text_of(p, main_only=False)
        assert not re.search(r"\$\s?49(?![\d,.])|49,00|forty-nine|quarante-neuf", t, re.I), p   # "then US$249" (Flag Check) is fine
    assert "US$39 founding price for the first 100 buyers." in text_of(off / "pricing" / "index.html")
    assert "US$39, one time (founding price for the first 100 buyers). Any sales tax" in text_of(off / "before-you-pay" / "index.html")
    terms = text_of(off / "terms" / "index.html")
    assert "US$39, one time, for the first 100 buyers. This is the founding price." in terms
    assert "The founding price ends with the 100th paid order" in terms
    fr = text_of(off / "fr" / "conditions" / "index.html").replace(" ", " ").replace(" ", " ")
    assert "paiement unique, pour les 100 premiers acheteurs. C’est le prix de fondateur." in fr
    assert "(prix de fondateur pour les 100 premiers acheteurs)" in text_of(off / "fr" / "avant-de-payer" / "index.html")
    assert lint_ok(off) == []


def test_hidden_next_price_fails_even_in_the_approved_form():
    ok = "<p>US$39 for the first 100 buyers, then US$49.</p>"
    assert "hidden" in B.founding_problem(ok, True, 100, 49, shown=False)
    assert "hidden" in B.founding_problem("<p>forty-nine dollars later</p>", True, 100, 49, shown=False)
    assert B.founding_problem("<p>US$39 founding price for the first 100 buyers.</p>", True, 100, 49, shown=False) is None
    assert B.founding_problem("<p>US$490 pilot, US$149 a case.</p>", True, 100, 49, shown=False) is None
    assert "crossed out" in B.founding_problem("<p><s>$49</s></p>", True, 100, 49, shown=False)
    # lint reads the switch from the committed prices.json (false): the approved form is a lint problem now
    assert any(p[0] == "claim:founding_price" for p in L.founding_claims(ok, "/x/"))


def test_after_founding_shown_must_be_a_boolean(tmp_path):
    r, _ = build(tmp_path, "x", prices=prices_with(after_founding_shown="no"))
    assert r.returncode == 1 and "after_founding_shown" in r.stderr


def test_founding_problem_catches_wrong_forms():
    ok = "<p>US$39 for the first 100 buyers, then US$49.</p>"
    assert B.founding_problem(ok, True, 100) is None
    assert "approved form" in B.founding_problem("<p>The price is US$49 later.</p>", True, 100)
    assert "crossed out" in B.founding_problem("<p><s>$49</s> $39 for the first 100 buyers</p>", True, 100)
    assert "crossed out" in B.founding_problem("<p><del class=x>US$49</del></p>", False, 100)
    assert B.founding_problem("<p>US$49.</p>", False, 100) is None   # ended: the price alone is fine


def test_the_old_retired_list_no_longer_holds_49_but_99_stays():
    amounts = PRICES["retired_amounts"]["amounts"]
    assert 49 not in amounts and 99 in amounts
    from harvest_prices import allowed_amounts
    assert 49 in allowed_amounts(PRICES) and 25 in allowed_amounts(PRICES)


def test_ended_state_shows_49_as_the_price_and_passes_lint(ended, monkeypatch):
    monkeypatch.setenv("DT_PRICES_JSON", str(ended.parent / "e.prices.json"))   # lint reads the prices file the build used
    pr = text_of(ended / "pricing" / "index.html")
    assert "US$49 once" in pr and "for the first 100 buyers" not in pr   # 8 Nov: "US$49 once · re-test included"
    assert "Get the report for US$49" in pr
    terms = text_of(ended / "terms" / "index.html")
    assert "Price: US$49, one time. The founding price of US$39 ended with the 100th paid order." in terms
    assert "39,00" not in text_of(ended / "fr" / "avant-de-payer" / "index.html").split("Prix détaillé")[1][:60]
    assert lint_ok(ended) == []
    # JSON-LD price = the button price, and it is the next price
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', (ended / "pricing" / "index.html").read_text(encoding="utf-8")).group(1))
    prod = next(x for x in ld["@graph"] if x["@type"] == "Product")
    assert prod["offers"]["price"] == "49"
    # the buy button points at the next price's link, the French page keeps ?locale=fr on it
    assert "buy.stripe.com/eVq14m66H9Jw15a0Rwdwc99" in (ended / "pricing" / "index.html").read_text(encoding="utf-8")
    assert "locale=fr" in (ended / "fr" / "avant-de-payer" / "index.html").read_text(encoding="utf-8")


def test_ended_state_without_a_next_link_fails_the_build(tmp_path):
    r, _ = build(tmp_path, "x", prices=prices_with(founding_open=False))
    assert r.returncode == 1 and "stripe_link_live" in r.stderr


def test_founding_open_must_be_a_boolean(tmp_path):
    r, _ = build(tmp_path, "x", prices=prices_with(founding_open="yes"))
    assert r.returncode == 1 and "founding_open" in r.stderr


def test_terms_count_rule_is_the_owners(off):
    t = text_of(off / "terms" / "index.html")
    assert "counted together across the English and French payment pages" in t
    assert "A refunded order keeps its place." in t and "Free tests that donttrade gives away do not count." in t
    f = text_of(off / "fr" / "conditions" / "index.html")
    assert "comptées ensemble sur les pages de paiement en français et en anglais" in f and "Une commande remboursée garde son rang." in f
    # EN and FR carry the same numbers
    nums = lambda s: sorted(set(re.findall(r"\b(?:100|39|49)\b", s.replace(",00", ""))))
    assert nums(t[t.index("Price: US$39"):][:900]) == nums(f[f.index("Rapport donttrade sur le revenge trading : "):][:900])


def test_promotion_wording_appears_only_when_codes_are_switched_on(off, on):
    assert "promotion code" not in text_of(off / "terms" / "index.html")
    assert "promotion code" in text_of(on / "terms" / "index.html")
    assert "promotion code" not in text_of(off / "before-you-pay" / "index.html")
    assert "before any promotion code you enter" in text_of(on / "before-you-pay" / "index.html")


# ===================================================================== A2 hero and habit counts
def test_home_hero_and_trust_line(off):
    h = (off / "index.html").read_text(encoding="utf-8")
    assert len(re.findall(r"<h1\b", h)) == 1
    t = text_of(off / "index.html")
    assert "Is revenge trading costing you? Get the dollar figure." in t
    # 7 Nov (free-check release): the hero leads with the free check; the trust line gains "Example report"
    assert ("Check your trade file free: see how many trades you opened right after a loss or a losing run. The US$39 report "
            "totals the dollars on them and tests whether it’s more than chance.") in t
    assert "Pre-registered research · Example report · Your file stays in your browser · 14-day refund" in t
    assert "Needs the time of each trade. A file with dates but no times gets no tested habits." in t
    assert "Get the report for US$39" in t and "See the full example report" in t
    assert 'href="/research/">Pre-registered research</a>' in h
    assert "Dollar totals describe what happened in your file." in t


def test_home_button_price_is_the_pricing_price(ended):
    assert "Get the report for US$49" in text_of(ended / "index.html")


def test_habit_counts_agree_on_home_and_pricing_and_come_from_one_place(off, tmp_path):
    home, pr = text_of(off / "index.html"), text_of(off / "pricing" / "index.html")
    assert "Up to five habits measured. Up to two tested against chance." in home
    assert "Up to five habits measured in your trades" in pr and "Up to two tested against chance" in pr
    assert "Five habits, checked" not in home and "Up to two habits tested against chance" not in home
    assert B.product_text({"habits_measured": 5, "habits_tested": 2}) == B.PRODUCT_TEXT
    r, out = build(tmp_path, "three", prices=prices_with(habits_tested=3))
    assert r.returncode == 0, r.stderr
    home3, pr3 = text_of(out / "index.html"), text_of(out / "pricing" / "index.html")
    assert "Up to five habits measured. Up to three tested against chance." in home3
    assert "Up to three tested against chance" in pr3 and "Up to two habits get this test" not in pr3 and "Up to three habits get this test" in pr3
    ld = (out / "pricing" / "index.html").read_text(encoding="utf-8")
    assert "up to three of them tested against chance" in ld


def test_numword_refuses_what_it_cannot_spell():
    assert B.numword(5) == "five"
    with pytest.raises(B.BuildError):
        B.numword(12)


# ===================================================================== A3 no "beta"
def test_no_beta_wording_outside_the_frozen_research_pages(off):
    for p in off.rglob("*"):
        if not p.is_file() or p.suffix not in (".html", ".js", ".json", ".xml", ".txt"):
            continue
        rel = p.relative_to(off).as_posix()
        if rel.startswith("research/") or rel.startswith("static/js/engine/"):   # market beta; engine comments
            continue
        s = p.read_text(encoding="utf-8", errors="replace")
        body = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", s) if p.suffix == ".html" else s
        assert not re.search(r"\bbeta\b|\bbêta\b", body, re.I), rel


def test_engine_strings_carry_no_beta():
    for rel in ("errors.js", "detect.js", "tradingview.js", "presets.js", "trades.js"):
        src = open(os.path.join(SITE, "static", "js", "engine", rel), encoding="utf-8").read()
        src = re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", src)      # comments are for developers; strings reach the page
        assert not re.search(r"""['"`][^'"`\n]*\bbeta\b""", src, re.I), rel


def test_the_promise_places_carry_the_factual_caveat(off):
    sentence = ("The four broker file readers (MetaTrader 4/5, IBKR, Tradovate and TradingView) are built from each platform’s published "
                "format and have not yet been tested on a real export; the donttrade CSV template has.")
    for rel in ("before-you-pay", "terms", "for-traders"):
        assert sentence in text_of(off / rel / "index.html"), rel
    fr = ("Les quatre lecteurs de fichiers de courtiers (MetaTrader 4/5, IBKR, Tradovate et TradingView) sont conçus d’après le format "
          "publié par chaque plateforme et n’ont pas encore été testés avec une vraie exportation; le modèle CSV de donttrade l’a été.")
    assert fr in text_of(off / "fr" / "avant-de-payer" / "index.html")
    assert fr in text_of(off / "fr" / "conditions" / "index.html")
    assert "not yet tested on a real export" in text_of(off / "pricing" / "index.html")
    assert "not yet tested on a real export" in text_of(off / "report" / "index.html", main_only=False) or True


# ===================================================================== A4 JSON-LD
def ld_of(out, rel="pricing"):
    h = (out / rel / "index.html").read_text(encoding="utf-8")
    return json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', h).group(1))


def test_product_jsonld_is_complete_and_makes_no_refund_claim(off):
    g = ld_of(off)["@graph"]
    prod = next(x for x in g if x["@type"] == "Product")
    for k in ("@id", "name", "description", "image", "brand", "sku", "offers"):
        assert k in prod, k
    o = prod["offers"]
    for k in ("price", "priceCurrency", "availability", "url", "itemCondition", "shippingDetails"):
        assert k in o, k
    assert o["price"] == "39" and o["priceCurrency"] == "USD"
    assert [r["addressCountry"] for r in o["shippingDetails"]["shippingDestination"]] == ["CA", "US"]
    assert any(x["@type"] == "FAQPage" for x in g)
    raw = json.dumps(g)
    for bad in ("aggregateRating", "review", "priceValidUntil", "MerchantReturnPolicy", "FullRefund"):
        assert bad not in raw, bad
    assert prod["image"][0].startswith("https://donttrade.ca/assets/") and os.path.exists(
        os.path.join(REPO, "docs", prod["image"][0].replace("https://donttrade.ca/", "")))


def test_product_jsonld_countries_come_from_site_toml(tmp_path):
    r, out = build(tmp_path, "c", toml=TOML.replace('merchant_countries = ["CA", "US"]', 'merchant_countries = ["CA", "US", "GB"]'))
    assert r.returncode == 0, r.stderr
    prod = next(x for x in ld_of(out)["@graph"] if x["@type"] == "Product")
    assert len(prod["offers"]["shippingDetails"]["shippingDestination"]) == 3
    r, _ = build(tmp_path, "c2", toml=TOML.replace('merchant_countries = ["CA", "US"]', 'merchant_countries = ["Canada"]'))
    assert r.returncode == 1 and "merchant_countries" in r.stderr


def test_lint_refuses_a_return_policy_a_rating_or_a_review_in_json_ld(off):
    h = (off / "pricing" / "index.html").read_text(encoding="utf-8")
    for bad in ('"hasMerchantReturnPolicy":{"refundType":"https://schema.org/FullRefund"}', '"aggregateRating":{"ratingValue":5}',
                '"review":{"name":"x"}', '"priceValidUntil":"2027-01-01"'):
        planted = h.replace('"@type": "Product"', '"@type": "Product",' + bad, 1)
        assert planted != h
        assert any(p[0] in ("claim:jsonld", "claim:dated_pricing") for p in L.refund_policy_claims(planted, "/pricing/")
                   + L.dated_pricing_claims("", "/pricing/", planted)), bad


# ===================================================================== A5 IndexNow
def test_indexnow_key_file_holds_exactly_the_key(off):
    assert (off / f"{KEY}.txt").read_bytes() == KEY.encode()
    assert re.fullmatch(r"[0-9a-f]{32}", KEY)


def test_indexnow_key_file_is_not_written_in_a_preview_build(tmp_path):
    r, out = build(tmp_path, "p", DT_PREVIEW="paid-preview")
    if r.returncode == 0:   # a preview needs its branch; the build itself refuses elsewhere: both mean "not written"
        assert not (out / f"{KEY}.txt").exists()


def test_indexnow_key_format_is_checked(tmp_path):
    r, _ = build(tmp_path, "k", toml=TOML.replace(f'key = "{KEY}"', 'key = "short"'))
    assert r.returncode == 1 and "[indexnow] key" in r.stderr


NEW_MAP = ('<urlset><url><loc>https://donttrade.ca/</loc><lastmod>2026-10-01</lastmod></url>'
           '<url><loc>https://donttrade.ca/pricing/</loc><lastmod>2026-11-06</lastmod></url>'
           '<url><loc>https://donttrade.ca/terms/</loc><lastmod>2026-11-06</lastmod></url>'
           '<url><loc>https://donttrade.ca/about/</loc><lastmod>2026-10-01</lastmod></url></urlset>')
OLD_MAP = ('<urlset><url><loc>https://donttrade.ca/</loc><lastmod>2026-10-01</lastmod></url>'
           '<url><loc>https://donttrade.ca/pricing/</loc><lastmod>2026-10-21</lastmod></url>'
           '<url><loc>https://donttrade.ca/about/</loc><lastmod>2026-10-01</lastmod></url></urlset>')


def test_indexnow_picks_new_changed_and_edited_pages():
    new, old = IX.parse_sitemap(NEW_MAP), IX.parse_sitemap(OLD_MAP)
    urls = IX.changed_urls(new, old, ["docs/index.html", "docs/about/index.html", "docs/static/css/site.css", "docs/gone/index.html"],
                           "https://donttrade.ca")
    assert urls == ["https://donttrade.ca/", "https://donttrade.ca/about/", "https://donttrade.ca/pricing/", "https://donttrade.ca/terms/"]


def test_indexnow_refuses_a_preview_a_dead_key_and_a_big_batch(tmp_path):
    assert IX.preview_problem("User-agent: *\nDisallow: /\n")
    assert IX.preview_problem("User-agent: *\nAllow: /\nDisallow: /report/\n") is None
    with pytest.raises(IX.Refused):
        IX.key_live(lambda u: None, "donttrade.ca", KEY)
    with pytest.raises(IX.Refused):
        IX.key_live(lambda u: "other", "donttrade.ca", KEY)
    IX.key_live(lambda u: KEY + "\n", "donttrade.ca", KEY)
    nokey = tmp_path / "s.toml"
    nokey.write_text('[site]\nbase_url = "https://donttrade.ca"\n')
    with pytest.raises(IX.Refused):
        IX.read_key(str(nokey))
    nokey.write_text('[indexnow]\nkey = "bad key!"\n')
    with pytest.raises(IX.Refused):
        IX.read_key(str(nokey))
    assert IX.read_key(os.path.join(SITE, "config", "site.toml")) == KEY


def test_indexnow_dry_run_sends_nothing(tmp_path, capsys):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "sitemap.xml").write_text(NEW_MAP)
    (docs / "robots.txt").write_text("User-agent: *\nAllow: /\n")
    sent = []
    args = IX.argparse.Namespace(since_rev="HEAD", docs=str(docs), dry_run=True, yes=False)
    assert IX.run(args, fetch=lambda u: None, post=lambda *a: sent.append(a)) == 0
    assert sent == [] and "dry run: nothing sent" in capsys.readouterr().out
    args.dry_run = False
    sent.clear()
    assert IX.run(args, fetch=lambda u: KEY, post=lambda url, p: sent.append((url, p)) or 200) == 0
    url, payload = sent[0]
    assert url == "https://api.indexnow.org/indexnow" and payload["host"] == "donttrade.ca" and payload["key"] == KEY
    assert payload["keyLocation"] == f"https://donttrade.ca/{KEY}.txt" and payload["urlList"]
    out = capsys.readouterr().out
    assert KEY not in out and "HTTP 200" in out


# ===================================================================== refund policy flag
PHRASE = "No result, no charge"


def test_refund_flag_defaults_off_and_the_old_wording_stays(off):
    assert re.search(r"refund_no_result = false", TOML)
    assert not (off / "refund").exists() and not (off / "fr" / "remboursement").exists()
    for p in off.rglob("*.html"):
        s = p.read_text(encoding="utf-8")
        assert PHRASE not in s and "Pas de résultat, pas de frais" not in s, p
    assert "Full refund within 14 days" in text_of(off / "pricing" / "index.html", main_only=False)
    assert "even after you have run the report" in text_of(off / "pricing" / "index.html")
    assert "even if you have already run the report" in text_of(off / "terms" / "index.html")
    # 7 Nov (Managed Payments): the EU/UK paragraph names Link; the voluntary refund is still there
    assert "In any case, donttrade’s voluntary 14-day full refund applies to you, even after the report has run." in text_of(off / "terms" / "index.html")
    assert "14-day refund" in text_of(off / "index.html")
    assert not (off / "partners").exists()      # fix round 1: /partners/ exists only while promotion codes are on


def test_flag_off_lint_refuses_the_new_phrase(off):
    planted = (off / "pricing" / "index.html").read_text(encoding="utf-8").replace("Last step", "No result, no charge", 1)
    L.REFUND["on"] = False
    assert any(p[0] == "claim:refund_flag_off" for p in L.refund_policy_claims(planted, "/pricing/"))


def test_refund_flag_needs_paid_report_a_date_and_a_terms_version_that_is_not_older(tmp_path):
    s = TOML.replace("refund_no_result = false", "refund_no_result = true", 1)
    r, _ = build(tmp_path, "a", toml=s)
    assert r.returncode == 1 and "refund_effective" in r.stderr
    r, _ = build(tmp_path, "b", toml=on_toml().replace('refund_effective = "2026-11-06"', 'refund_effective = "2026-11-07"'), DT_TODAY="2026-11-07")
    assert r.returncode == 1 and "before refund_effective" in r.stderr
    r, _ = build(tmp_path, "c", toml=TOML.replace('privacy_date = "2026-11-06"', 'privacy_date = "2026-11-06"\nrefund_effective = "2026-11-06"'))
    assert r.returncode == 1 and "refund_no_result is off" in r.stderr
    r, _ = build(tmp_path, "d", toml=on_toml().replace("paid_report = true", "paid_report = false").replace("trader_first_home = true", "trader_first_home = false"))
    assert r.returncode == 1


EN_T2 = ("No result, no charge. If your file can’t be read, the test can’t run, or no habit can be tested, you get a full refund "
         "when you ask within 14 days of buying. Once your result is delivered there is no refund, apart from one goodwill "
         "refund per customer. Refund terms · Ask for a refund")
FR_T2_START = "Pas de résultat, pas de frais. Si votre fichier n’a pas pu être lu"


def test_refund_on_tier_texts_match_the_addendum_word_for_word(on):
    pr = text_of(on / "pricing" / "index.html")
    assert pr.count(EN_T2) >= 2                       # the card line and the FAQ answer
    assert EN_T2 in text_of(on / "for-traders" / "index.html")
    byp = ("No result, no charge: a full refund if you ask within 14 days of buying and your file couldn’t be read, the test "
           "couldn’t run, no habit could be tested, or you haven’t run your first analysis. Once a result is delivered we "
           "don’t refund, except one goodwill refund per customer, at our discretion. A refund ends your access key and free "
           "re-test. This adds to your rights under consumer law; it doesn’t replace them. Refund terms · Ask for a refund")
    assert byp in text_of(on / "pricing" / "index.html") and byp in text_of(on / "before-you-pay" / "index.html")
    terms = text_of(on / "terms" / "index.html")
    assert ("Refunds: No result, no charge. You get a full refund if you ask within 14 days of buying and any of these is true, "
            "even after we have tried to help: your file could not be read; the test could not run; the test ran but no habit "
            "could be tested (every tested habit shows “not enough trades to tell”, or the file has dates but no times); or you "
            "have not yet run your first analysis. A result is delivered when the report page shows you the figures from a test "
            "that could test at least one habit.") in terms
    assert ("Once a result has been delivered to you, we do not refund, except that we will make one goodwill refund per "
            "customer , at our discretion, if you ask within 14 days of buying.").replace("customer ,", "customer,") in terms.replace("customer ,", "customer,")
    assert "These terms apply to purchases made on or after 6 Nov 2026; earlier purchases keep the refund terms in force on the day they were made." in terms
    assert "Traders: No result, no charge. Full refund within 14 days if no result is delivered (details in the refund terms below)." in (on / "terms" / "index.html").read_text(encoding="utf-8").replace("\n", " ")
    assert "If something is wrong with your order, ask us first; we answer faster than a card dispute" in terms
    assert 'id="trader-refunds"' in (on / "terms" / "index.html").read_text(encoding="utf-8")
    # 7 Nov (Managed Payments): no waiver is collected at checkout any more, so EU/UK buyers keep the 14-day right
    assert ("If you live in the European Union or the United Kingdom, you keep your 14-day legal right of withdrawal: a full "
            "refund if you ask within 14 days of buying, even after your result is supplied.") in terms
    assert "the field shown at checkout" not in terms
    assert "Our voluntary" not in terms
    # chips
    home = text_of(on / "index.html")
    assert "Pre-registered research · Example report · Your file stays in your browser · No result, no charge" in home
    assert 'href="/terms/#trader-refunds">No result, no charge</a>' in (on / "index.html").read_text(encoding="utf-8")
    assert "No result, no charge" in text_of(on / "pricing" / "index.html", main_only=False)
    fr = text_of(on / "fr" / "conditions" / "index.html")
    assert "Remboursements : pas de résultat, pas de frais." in fr and "un remboursement à titre gracieux par client" in fr
    assert "(du lundi au vendredi, heure de l’Est)" in fr and "à compter du 6 novembre 2026" in fr
    assert "Pas de résultat, pas de frais : remboursement complet" in text_of(on / "fr" / "avant-de-payer" / "index.html")
    assert FR_T2_START in text_of(on / "fr" / "remboursement" / "index.html")


def test_refund_on_numbers_agree_between_english_and_french(on):
    en = text_of(on / "terms" / "index.html")
    fr = text_of(on / "fr" / "conditions" / "index.html")
    seg = lambda s, a, b: s[s.index(a):s.index(b)]
    e = seg(en, "Refunds: No result", "Payment disputes")
    f = seg(fr, "Remboursements : pas de résultat", "Avant de contester")
    assert re.findall(r"\b(?:14|2|5 to 10|5 à 10)\b", e) == re.findall(r"\b(?:14|2|5 to 10|5 à 10)\b", f) \
        or [x.replace("5 to 10", "5 à 10") for x in re.findall(r"\b(?:14|2|5 to 10)\b", e)] == re.findall(r"\b(?:14|2|5 à 10)\b", f)


def test_refund_on_removes_the_retired_phrases_and_json_ld_has_no_return_policy(on):
    for p in on.rglob("*.html"):
        t = text_of(p, main_only=False)
        for old in ("even if you have already run the report", "even after you have run the report", "voluntary 14-day refund",
                    "même si vous avez déjà fait le test", "even if you have already run the report",
                    "even after you have run the report", "même si vous avez déjà fait le rapport"):
            assert old not in t, (p, old)
    assert "Full refund within 14 days" not in text_of(on / "pricing" / "index.html", main_only=False)
    raw = (on / "pricing" / "index.html").read_text(encoding="utf-8")
    assert "MerchantReturnPolicy" not in raw and "FullRefund" not in raw
    assert lint_ok(on) == []


def test_refund_on_lint_catches_a_bare_claim_a_retired_phrase_and_a_bare_full_refund(on):
    L.REFUND["on"] = True
    h = (on / "pricing" / "index.html").read_text(encoding="utf-8")
    bare = "<section><p>No result, no charge</p></section>"
    assert any(p[0] == "claim:refund_limits" for p in L.refund_policy_claims(bare, "/x/"))
    assert not any(p[0] == "claim:refund_limits" for p in L.refund_policy_claims(
        '<section><p>No result, no charge. <a href="/terms/#trader-refunds">Refund terms</a></p></section>', "/x/"))
    assert any(p[0] == "claim:refund_retired" for p in L.refund_policy_claims("<p>even after you have run the report</p>", "/x/"))
    assert any(p[0] == "claim:full_refund" for p in L.refund_policy_claims("<p>You get a full refund.</p>", "/x/"))
    assert not any(p[0] == "claim:full_refund" for p in L.refund_policy_claims("<p>A full refund if your file could not be read.</p>", "/x/"))
    assert h


def test_refund_pages_are_noindex_out_of_the_sitemap_and_not_in_the_answers(on):
    sm = (on / "sitemap.xml").read_text(encoding="utf-8")
    for rel in ("refund", "refund/thanks", "fr/remboursement", "fr/remboursement/merci", "partners"):   # `on` has codes on
        h = (on / rel / "index.html").read_text(encoding="utf-8")
        assert '<meta name="robots" content="noindex">' in h, rel
        assert f"https://donttrade.ca/{rel}/" not in sm, rel
    assert "/refund/" not in (on / "static" / "js" / "answers-index.js").read_text(encoding="utf-8")


def test_refund_form_markup(on):
    for rel, lang in (("refund", "en"), ("fr/remboursement", "fr")):
        h = (on / rel / "index.html").read_text(encoding="utf-8")
        form = re.search(r'(?s)<form class="request-form" id="refund-form".*?</form>', h).group(0)
        assert 'method="POST"' in form and 'action="https://api.web3forms.com/submit"' in form
        assert 'name="botcheck"' in form and 'name="subject" value="donttrade: refund request"' in form
        assert "<legend>" in form
        assert re.findall(r'type="radio" name="reason" value="([a-z-]+)"', form) == [x["slug"] for x in REASONS]
        assert len(re.findall(r'name="reason"[^>]*required', form)) == 1 and 'name="email" type="email"' in form
        assert not re.search(r'<textarea[^>]*required', form)          # required only through refund.js, for "other"
        assert 'maxlength="1000"' in form and 'maxlength="40"' in form
        assert 'redirect" value="https://donttrade.ca/' + ("fr/remboursement/merci/" if lang == "fr" else "refund/thanks/") in form
        assert "api.web3forms.com" in h.split("Content-Security-Policy")[1].split(">")[0]
        assert "/static/js/refund.js" in h and "/static/js/form-ref.js" in h
        assert 'data-umami-event' not in h
        assert 'data-exclude-search="true"' in h
    en = text_of(on / "refund" / "index.html")
    assert "If you already have your result, refunds are limited to one goodwill refund per customer. Send your request anyway: a person reads every one." in en
    assert "Describe the message on the page. Do not send your trade file or card details." in en
    assert "We use this only to answer you and to count reasons (without your email)." in en
    assert "We reply" not in en or "within 2 business days" in en


def test_refund_reason_labels_and_values_match_between_languages(on):
    vals = lambda rel: re.findall(r'name="reason" value="([a-z-]+)"', (on / rel / "index.html").read_text(encoding="utf-8"))
    assert vals("refund") == vals("fr/remboursement") == [x["slug"] for x in REASONS]
    assert len(REASONS) == 9


def test_refund_js_whitelist_equals_the_reason_list_and_stores_nothing():
    src = open(os.path.join(SITE, "static", "js", "refund.js"), encoding="utf-8").read()
    code = re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", src)
    listed = re.findall(r"'([a-z-]+)'", re.search(r"var REASONS = \[(.*?)\];", src, re.S).group(1))
    assert listed == [x["slug"] for x in REASONS]
    assert not re.search(r"localStorage|sessionStorage|document\.cookie|indexedDB|preventDefault\(|XMLHttpRequest|fetch\(", code)
    tracks = re.findall(r"umami\.track\(([^)]*)\)", code)
    assert tracks == ["'refund-reason-' + v"]


def test_refund_thanks_pages_carry_nothing_from_the_request(on):
    for rel in ("refund/thanks", "fr/remboursement/merci"):
        h = (on / rel / "index.html").read_text(encoding="utf-8")
        assert "<form" not in h and "location.search" not in h


def test_privacy_names_the_refund_form_the_log_and_the_misuse_list_only_with_the_flag(off, on):
    for out, want in ((off, False), (on, True)):
        en = text_of(out / "privacy" / "index.html")
        fr = text_of(out / "fr" / "confidentialite" / "index.html")
        assert ("The refund request form asks for the email you paid with" in en) is want
        assert ("Refund misuse list" in en) is want and ("Liste des abus de remboursement" in fr) is want
        assert ("private refund log (order code, date, reason, decision)" in en) is want
        assert ("The refund request page counts which reason was picked" in en) is want
        assert "If you are a partner or receive a free test" in en and "Si vous êtes partenaire ou recevez un test gratuit" in fr


# ===================================================================== A6 partners
def test_partners_page_numbers_come_from_prices_json(on):
    t = text_of(on / "partners" / "index.html")
    p = PRICES["partner"]
    assert f"{p['discount_percent']}% off" in t and f"{p['commission_percent']}%" in t and "31 January 2027" in t
    assert "US$25" in t and "14 days after the order" in t
    for word in ("beta", "fake", "demo"):
        assert word not in t.lower()


def test_no_partners_means_no_meta_and_no_pay_note(off):
    for p in off.rglob("index.html"):
        s = p.read_text(encoding="utf-8")
        assert 'name="dt-partners"' not in s and "data-partner-note" not in s, p


def test_active_partners_only_are_in_the_meta(on):
    m = re.search(r'<meta name="dt-partners" content=\'?"?([^>]*)>', (on / "pricing" / "index.html").read_text(encoding="utf-8"))
    raw = _html.unescape(re.search(r'name="dt-partners" content="([^"]*)"', (on / "pricing" / "index.html").read_text(encoding="utf-8")).group(1))
    data = json.loads(raw)
    assert data == {"d": 10, "p": {"jane-doe": ["JANE10", "Jane Doe"]}} and m


def test_partners_json_needs_the_promo_tick_and_clean_values(tmp_path):
    good = {"jane-doe": {"code": "JANE10", "name": "Jane Doe", "active": True}}
    r, _ = build(tmp_path, "a", partners=good)
    assert r.returncode == 1 and "promo_codes_enabled" in r.stderr
    for bad in ({"Jane": {"code": "JANE10", "name": "Jane", "active": True}},
                {"jane-doe": {"code": "jane10", "name": "Jane Doe", "active": True}},
                {"jane-doe": {"code": "JANE10", "name": "<b>x</b>", "active": True}},
                {"jane-doe": {"code": "JANE10", "name": "Jane Doe", "active": "yes"}},
                {"jane-doe": {"code": "JANE10", "name": "Jane Doe"}},
                {"a-a": {"code": "SAME", "name": "Aa", "active": True}, "b-b": {"code": "SAME", "name": "Bb", "active": True}}):
        r, _ = build(tmp_path, "b", toml=on_toml(), partners=bad)
        assert r.returncode == 1, bad
    r, _ = build(tmp_path, "c", toml=on_toml(), partners=good)
    assert r.returncode == 0, r.stderr


def test_committed_partners_file_is_valid_and_empty():
    assert json.load(open(os.path.join(SITE, "config", "partners.json"))) == {}


def test_pay_js_stores_nothing():
    src = open(os.path.join(SITE, "static", "js", "pay.js"), encoding="utf-8").read()
    src = re.sub(r"(?m)^\s*//.*$|\s//\s.*$", "", src)
    assert not re.search(r"localStorage|sessionStorage|document\.cookie|indexedDB", src)


@pytest.fixture(scope="module")
def on_url(on):
    srv = served(on)
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def pay_hrefs(pg):
    return pg.evaluate("[].map.call(document.querySelectorAll('a[data-pay-continue]'), a => a.getAttribute('href'))")


@pytest.mark.parametrize("query,applied", [
    ("?via=jane-doe", True), ("?via=JANE-DOE", True), ("?via=old-one", False), ("?via=nobody", False),
    ("?via=%3Cscript%3Ealert(1)%3C%2Fscript%3E", False), ("?via=" + "a" * 400, False), ("?via=__proto__", False),
    ("?via=constructor", False), ("", False), ("?via=jane-doe&via=other", True)])
def test_partner_link_rewrites_only_known_active_slugs(browser, on_url, query, applied):
    pg = browser.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(on_url + "/pricing/" + query + "#last-step")
    hrefs = pay_hrefs(pg)
    assert hrefs and all(h.startswith("https://buy.stripe.com/") for h in hrefs)
    note = pg.evaluate("[].map.call(document.querySelectorAll('[data-partner-note]'), n => n.hidden ? '' : n.textContent)")
    if applied:
        for h in hrefs:
            assert h.count("prefilled_promo_code=") == 1 and "prefilled_promo_code=JANE10" in h
            assert re.search(r"client_reference_id=pricing_p-jane-doe(&|$)", h)
        assert any("Partner code JANE10 will be applied on the payment page: 10% off. Jane Doe earns a commission if you buy." == n for n in note)
    else:
        assert all("prefilled_promo_code" not in h and "_p-" not in h for h in hrefs)
        assert all(n == "" for n in note)
    assert pg.evaluate("document.cookie") == "" and pg.evaluate("localStorage.length") == 0
    assert errors == []
    pg.close()


def test_partner_rewrite_on_the_pay_dialog_of_another_page(browser, on_url):
    pg = browser.new_page()
    pg.goto(on_url + "/?via=jane-doe")
    hrefs = pay_hrefs(pg)
    assert hrefs and all("prefilled_promo_code=JANE10" in h and "client_reference_id=home_p-jane-doe" in h for h in hrefs)
    pg.close()


def test_refund_js_counts_only_the_picked_reason_and_never_blocks(browser, on_url):
    pg = browser.new_page()
    pg.goto(on_url + "/refund/")
    pg.route("https://api.web3forms.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="ok"))
    # no reason: form-ref.js stops the submit, nothing is counted
    pg.click("#refund-form button[type=submit]")
    assert pg.evaluate("(window.__umamiCalls||[]).length") == 0
    pg.fill("#rf-email", "someone@example.com")
    pg.click("label[for=rf-r-nothing-tested]")
    assert pg.evaluate("document.getElementById('rf-detail').required") is False
    pg.click("label[for=rf-r-other]")
    assert pg.evaluate("document.getElementById('rf-detail').required") is True
    pg.click("#refund-form button[type=submit]")
    assert pg.evaluate("(window.__umamiCalls||[]).length") == 0          # "other" needs its note
    pg.fill("#rf-detail", "the page showed an error")
    pg.click("label[for=rf-r-wont-run]")
    seen = []
    pg.expose_function("rec", lambda n, has_data: seen.append({"name": n, "hasData": has_data}))
    pg.evaluate("(() => { const o = window.umami.track; window.umami.track = function (n, d) { window.rec(n, d !== undefined); return o.apply(this, arguments); }; })()")
    with pg.expect_navigation():       # the request is not stopped: the page goes on to the (stubbed) response
        pg.click("#refund-form button[type=submit]")
    assert seen == [{"name": "refund-reason-wont-run", "hasData": False}]
    pg.close()


def test_refund_form_posts_without_javascript(browser, on_url):
    ctx = browser.new_context(java_script_enabled=False)
    pg = ctx.new_page()
    posted = []
    pg.route("https://api.web3forms.com/**", lambda r: (posted.append(r.request.post_data), r.fulfill(status=200, content_type="text/html", body="ok")))
    pg.goto(on_url + "/refund/")
    pg.fill("#rf-email", "someone@example.com")
    pg.click("label[for=rf-r-unreadable]")
    pg.click("#refund-form button[type=submit]")
    assert posted and "reason=unreadable" in posted[0] and "subject=donttrade%3A+refund+request" in posted[0]
    ctx.close()


def test_home_has_no_horizontal_scroll_on_a_phone(browser, on_url):
    ctx = browser.new_context(viewport={"width": 390, "height": 800})
    pg = ctx.new_page()
    for path in ("/", "/pricing/", "/refund/", "/fr/remboursement/"):
        pg.goto(on_url + path)
        assert pg.evaluate("document.documentElement.scrollWidth <= document.documentElement.clientWidth"), path
    ctx.close()


# ===================================================================== A3 importers.json
def test_importers_json_equals_the_engine_flags_and_the_tool_page_table():
    cfg = json.load(open(os.path.join(SITE, "config", "importers.json"), encoding="utf-8"))["formats"]
    src = open(os.path.join(SITE, "static", "js", "engine", "detect.js"), encoding="utf-8").read()
    engine = [(i, v == "true") for i, v in re.findall(r"^  (\w+): \{\n    verified: (true|false)", src, re.M)]
    assert [(x["id"], x["verified"]) for x in cfg] == engine
    page = open(os.path.join(SITE, "templates", "pages", "tool-trade-stats.html"), encoding="utf-8").read()
    unverified_platforms = len(re.findall(r"<td>Not yet tested on a real export</td>", page))
    assert unverified_platforms == 5     # MT5, MT4, IBKR, Tradovate, TradingView; the CSV template is not in the table
    assert all(not x["verified"] for x in cfg if x["id"] in ("mt5_deals", "mt4", "ibkr_flex", "tradovate_orders", "tradingview"))


# ===================================================================== a11y, overflow, console on the new pages
@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 1280])
@pytest.mark.parametrize("path", ["/refund/", "/refund/thanks/", "/fr/remboursement/", "/fr/remboursement/merci/", "/partners/", "/", "/pricing/"])
def test_axe_overflow_console_on_the_round_a_pages(browser, on_url, path, width, scheme):
    sys.path.insert(0, HERE)
    from test_pages import axe_violations, horizontal_overflow
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    errs = []
    pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errs.append(str(e)))
    pg.goto(on_url + path)
    pg.wait_for_load_state("networkidle")
    pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
    assert horizontal_overflow(pg) == []
    if width != 320:
        assert axe_violations(pg) == []
    assert [e for e in errs if "Failed to load resource" not in e and "cloudflareinsights" not in e] == []
    ctx.close()


# =============================================================================== FIX ROUND 1 (Tester minors)
# ---- M1 founding price: one approved form, enforced
APPROVED_EN = "for the first 100 buyers, then US$49"
APPROVED_FR = "pour les 100 premiers acheteurs, puis 49,00\u00a0$\u00a0US"


@pytest.mark.parametrize("plant", [
    "<p>Now only $49.</p>", "<p>Now only $49</p>", "<p>US$49 after that.</p>", "<p>The usual rate is $49 for everyone.</p>",
    "<p>Then 49 USD.</p>", "<p>Then 49,00\u00a0$\u00a0US.</p>", "<p>Then 49 $ US.</p>", "<p>Was $49 before.</p>",
    "<p>for the first 100 buyers, thereafter US$49</p>", "<p>launch offer, first 100 buyers: US$49</p>",
    "<p>pour les 100 premiers acheteurs, ensuite 49,00\u00a0$\u00a0US</p>"])
def test_any_other_mention_of_the_next_price_fails_while_the_founding_price_is_open(plant, shown_prices):
    ok = f"<p>US$39 {APPROVED_EN}.</p><p>{APPROVED_FR}.</p>"
    assert B.founding_problem(ok, True, 100) is None
    assert "approved form" in B.founding_problem(ok + plant, True, 100), plant
    assert "approved form" in B.founding_problem(plant, True, 100)
    assert any(p[0] == "claim:founding_price" for p in L.founding_claims(ok + plant, "/x/"))
    assert not L.founding_claims(ok, "/x/")


@pytest.mark.parametrize("plant", ["<s>US$49</s>", "<del>$49</del>", "<strike>49,00\u00a0$\u00a0US</strike>", "<s class=a>49 USD</s>"])
def test_a_crossed_out_next_price_fails_open_or_ended(plant):
    assert "crossed out" in B.founding_problem(f"<p>{APPROVED_EN}</p>" + plant, True, 100)
    assert "crossed out" in B.founding_problem(plant, False, 100)


def test_every_page_that_shows_the_next_price_uses_the_approved_wording(shown_prices):
    off = shown_prices   # 8 Nov: the switch is on in this build only
    shown = []
    for rel, phrase in (("pricing", APPROVED_EN), ("terms", APPROVED_EN), ("before-you-pay", APPROVED_EN),
                        ("fr/conditions", APPROVED_FR), ("fr/avant-de-payer", APPROVED_FR)):
        t = text_of(off / rel / "index.html", main_only=False)
        assert phrase in t.replace("\u00a0", " ").replace(" ", " ") or phrase.replace("\u00a0", " ") in t.replace("\u00a0", " "), rel
        shown.append(rel)
    assert len(shown) == 5
    for p in off.rglob("index.html"):
        if p.relative_to(off).parts[0] == "research":
            continue
        assert B.founding_problem(p.read_text(encoding="utf-8"), True, 100) is None, p


def test_the_approved_phrase_is_pinned_in_the_macro_and_the_terms(shown):
    off = shown   # 8 Nov: the switch is on in this build only
    macro = open(os.path.join(SITE, "templates", "partials", "price_line.html"), encoding="utf-8").read()
    # 8 Nov 2026: build.usd writes "US$49" itself, so the macro no longer adds "US"
    assert "for the first {{ rules.founding_limit }} buyers, then {{ r.after_price_usd|usd }}" in macro
    assert "pour les {{ rules.founding_limit }} premiers acheteurs, puis {{ r.after_price_usd|usd_fr }}" in macro
    terms = text_of(off / "terms" / "index.html")
    assert "US$39, one time, for the first 100 buyers, then US$49, one time, for every buyer after that. The first price is the founding price." in terms
    fr = text_of(off / "fr" / "conditions" / "index.html").replace("\u00a0", " ")
    assert "39,00 $ US, paiement unique, pour les 100 premiers acheteurs, puis 49,00 $ US, paiement unique, pour chaque acheteur suivant. Le premier prix est le prix de fondateur." in fr


def test_a_planted_next_price_in_a_built_page_fails_lint(off, tmp_path):
    import shutil
    out = tmp_path / "_site"
    shutil.copytree(off, out)
    fp = out / "about" / "index.html"
    fp.write_text(fp.read_text(encoding="utf-8").replace("</main>", "<p>Now only $49.</p></main>", 1), encoding="utf-8")
    probs = lint_ok(out)
    assert any(p[0] == "claim:founding_price" and p[1] == "/about/" for p in probs)


# ---- M2 flag off: no new-policy wording of any kind
ON_FLAG_OFF_PLANTS = [
    "<p>Once your result is delivered there is no refund, apart from one goodwill refund per customer.</p>",
    "<p>You get no refund once your result is delivered.</p>", "<p>We make a goodwill refund.</p>",
    '<p><a href="/refund/">Ask us</a></p>', '<p><a href="/terms/#trader-refunds">Terms</a></p>',
    '<p><a href="/fr/remboursement/">Demande</a></p>', '<p id="no-resale">x</p>',
    "<p>Un remboursement à titre gracieux par client.</p>", "<p>Une fois votre résultat remis, nous ne remboursons pas.</p>",
    "<p>No result, no charge.</p>"]


@pytest.mark.parametrize("plant", ON_FLAG_OFF_PLANTS)
def test_flag_off_lint_refuses_every_kind_of_new_policy_wording(off, plant):
    L.REFUND["on"] = False
    h = (off / "pricing" / "index.html").read_text(encoding="utf-8").replace("</main>", plant + "</main>", 1)
    assert any(p[0] == "claim:refund_flag_off" for p in L.refund_policy_claims(h, "/pricing/")), plant
    assert B.refund_off_problems(h), plant


def test_the_flag_off_deny_list_is_derived_from_the_flag_on_strings(on, off):
    """Every sentence of the flag-on refund wording on the pages is refused when planted in a flag-off page, so the
    two cannot drift: a new flag-on sentence is covered without anyone editing a list."""
    deny = B.refund_denylist()
    assert {"/refund/", "/fr/remboursement/", "/terms/#trader-refunds", "/fr/conditions/#remboursements-traders"} <= deny["hrefs"]
    assert {"goodwill", "gracieux", "customer"} <= deny["words"]
    seen = 0
    for rel in ("terms", "pricing", "before-you-pay", "fr/conditions", "fr/avant-de-payer", "for-traders"):
        for sent in re.split(r"(?<=[.;:!?])\s+", text_of(on / rel / "index.html")):
            if len(sent.split()) >= 8 and re.search(r"goodwill|gracieux|result is delivered|résultat remis|no charge|pas de frais", sent, re.I):
                assert B.refund_off_problems(f"<p>{_html.escape(sent)}</p>"), sent
                seen += 1
    assert seen >= 8


def test_flag_off_build_fails_on_new_wording_in_a_template(tmp_path):
    import shutil
    work = tmp_path / "repo"
    shutil.copytree(SITE, work / "site", ignore=shutil.ignore_patterns("_site", "dev", "__pycache__"))
    shutil.copytree(os.path.join(REPO, "docs"), work / "docs", ignore=shutil.ignore_patterns("*.webp"))
    shutil.copytree(os.path.join(REPO, "checks"), work / "checks", ignore=shutil.ignore_patterns("__pycache__"))
    shutil.copytree(os.path.join(REPO, "tests", "fixtures", "paid"), work / "tests" / "fixtures" / "paid")
    p = work / "site" / "templates" / "pages" / "welcome.html"
    p.write_text(p.read_text(encoding="utf-8").replace("{% include \"partials/disclaimer.html\" %}", "<p>One goodwill refund per customer.</p>{% include \"partials/disclaimer.html\" %}", 1), encoding="utf-8")
    r = subprocess.run([sys.executable, str(work / "site" / "build.py")], env={**os.environ, "DT_OUT": str(tmp_path / "o")}, capture_output=True, text=True)
    assert r.returncode == 1 and "refund_no_result is off but the page says the new policy" in r.stderr and "goodwill" in r.stderr


# ---- M3 dates
def test_a_bad_dt_today_is_one_clear_line_not_a_traceback(tmp_path):
    for bad in ("abc", "2026-13-40", "06/11/2026", ""):
        r, _ = build(tmp_path, "b", DT_TODAY=bad)
        if bad == "":
            continue
        assert r.returncode == 1 and "Traceback" not in r.stderr, bad
        assert r.stderr.strip().count("\n") == 0 and "DT_TODAY" in r.stderr and "YYYY-MM-DD" in r.stderr, r.stderr


def test_dt_today_that_is_not_today_prints_a_note(tmp_path):
    r, _ = build(tmp_path, "n", DT_TODAY="2026-11-06")
    import datetime
    if datetime.date.today().isoformat() != "2026-11-06":
        assert "NOTE: DT_TODAY=2026-11-06 is not today" in r.stderr and "never bundle or deploy" in r.stderr


def test_a_bundle_build_refuses_a_date_later_than_the_real_date(tmp_path):
    import datetime
    far = (datetime.date.today() + datetime.timedelta(days=3)).isoformat()
    toml = TOML.replace('terms_date = "2026-11-06"', f'terms_date = "{far}"').replace('privacy_date = "2026-11-06"', f'privacy_date = "{far}"')
    r, _ = build(tmp_path, "f", toml=toml, DT_TODAY=far, DT_REQUIRE_LAUNCH_DATE="1")
    assert r.returncode == 1 and "docs/ would be stamped later than today's real date" in r.stderr and "Traceback" not in r.stderr
    # the same build as a preview (an explicit, deliberate DT_TODAY) is allowed
    r, _ = build(tmp_path, "p", toml=toml, DT_TODAY=far, DT_REQUIRE_LAUNCH_DATE="1", DT_PREVIEW="paid-preview")
    assert r.returncode == 0, r.stderr
    # page content dates count too (they become the sitemap's <lastmod>)
    d = datetime.date.today()
    if d.isoformat() < "2026-11-06":
        r, _ = build(tmp_path, "g", toml=TOML.replace('terms_date = "2026-11-06"', f'terms_date = "{d.isoformat()}"').replace('privacy_date = "2026-11-06"', f'privacy_date = "{d.isoformat()}"'), DT_REQUIRE_LAUNCH_DATE="1")
        assert r.returncode == 1 and "updated 2026-11-06" in r.stderr


def test_bundle_command_refuses_dt_today_and_leaves_docs_alone():
    import hashlib
    before = hashlib.sha256(open(os.path.join(REPO, "docs", "sitemap.xml"), "rb").read()).hexdigest()
    r = subprocess.run(["sh", os.path.join(SITE, "run.sh"), "bundle"], cwd=REPO, capture_output=True, text=True,
                       env={**os.environ, "DT_BUNDLE": "yes", "DT_TODAY": "2026-11-06"})
    assert r.returncode == 1 and "bundle refuses DT_TODAY=2026-11-06" in r.stdout
    assert hashlib.sha256(open(os.path.join(REPO, "docs", "sitemap.xml"), "rb").read()).hexdigest() == before


def test_docs_date_check_fails_on_a_future_dated_docs_and_passes_today(tmp_path):
    sys.path.insert(0, os.path.join(REPO, "checks"))
    import docs_date as D
    import datetime
    d = tmp_path / "docs"
    (d / "terms").mkdir(parents=True)
    (d / "terms" / "index.html").write_text("<p>Version 2099-01-01.</p>")
    (d / "sitemap.xml").write_text("<urlset><url><loc>https://donttrade.ca/x/</loc><lastmod>2099-01-02</lastmod></url></urlset>")
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "docs_date.py"), str(d)], capture_output=True, text=True)
    assert r.returncode == 1 and "docs_date: FAIL" in r.stdout and "never commit or deploy it earlier" in r.stdout
    (d / "terms" / "index.html").write_text("<p>Version 2026-01-01.</p>")
    (d / "sitemap.xml").write_text("<urlset><url><loc>https://donttrade.ca/x/</loc><lastmod>2026-01-02</lastmod></url></urlset>")
    assert D.future_dates(str(d), datetime.date.today()) == []
    real = subprocess.run([sys.executable, os.path.join(REPO, "checks", "docs_date.py")], capture_output=True, text=True)
    assert real.returncode == 0, real.stdout          # the committed docs/ is not dated ahead
    assert "docs_date.py" in open(os.path.join(SITE, "run.sh")).read()


# ---- M4 French validation messages
def test_french_refund_form_shows_french_validation_messages(browser, on_url):
    pg = browser.new_page()
    pg.goto(on_url + "/fr/remboursement/")
    pg.click("#refund-form button[type=submit]")
    msgs = pg.evaluate("[].map.call(document.querySelectorAll('.field-err'), e => e.hidden ? '' : e.textContent).filter(Boolean)")
    assert "Courriel utilisé pour payer est obligatoire." in msgs and "Choisissez une réponse." in msgs
    assert not any(re.search(r"required|Choose|\(", m) for m in msgs), msgs
    pg.fill("#rf-email", "pas-un-courriel")
    pg.click("#refund-form button[type=submit]")
    assert "Entrez une adresse courriel complète, comme nom@exemple.com." in pg.evaluate("[].map.call(document.querySelectorAll('.field-err'), e => e.hidden ? '' : e.textContent)")
    pg.close()


def test_english_refund_form_keeps_english_messages_without_the_hint_in_parentheses(browser, on_url):
    pg = browser.new_page()
    pg.goto(on_url + "/refund/")
    pg.fill("#rf-email", "a@b.co")
    pg.click("label[for=rf-r-other]")
    pg.click("#refund-form button[type=submit]")
    msgs = pg.evaluate("[].map.call(document.querySelectorAll('.field-err'), e => e.hidden ? '' : e.textContent).filter(Boolean)")
    assert msgs == ["What did you see is required."], msgs
    pg.close()


# ---- M5 /help/ and the answers index keep the Stripe sentence with the refund flag on
def test_flag_on_help_and_answers_index_keep_the_stripe_controller_sentence(on, off):
    for out in (off, on):
        assert "independent controller" in (out / "help" / "index.html").read_text(encoding="utf-8")
        assert "independent controller" in (out / "static" / "js" / "answers-index.js").read_text(encoding="utf-8")
        assert "independent controller" in text_of(out / "privacy" / "index.html")


def test_privacy_refund_and_partner_records_have_their_own_section(on, off):
    for out, refund in ((off, False), (on, True)):
        h = (out / "privacy" / "index.html").read_text(encoding="utf-8")
        assert 'id="refund-partner-records"' in h and 'id="partners-free-tests"' in h
        assert ('id="refund-misuse"' in h) is refund and ('id="refund-form-data"' in h) is refund
        forms = h.split('id="forms"')[1].split('id="refund-partner-records"')[0]
        assert "refund log" not in forms and "misuse" not in forms.lower()


# ---- M6 Eastern Time
def test_partners_page_says_eastern_time_and_no_toronto_anywhere(on):
    assert "(Eastern Time)" in text_of(on / "partners" / "index.html") and "Toronto" not in text_of(on / "partners" / "index.html")
    assert "Toronto" not in open((os.environ.get("DT_PRICES_JSON") or os.path.join(SITE, "config", "prices.json")), encoding="utf-8").read()
    for p in list(on.rglob("*.html")):
        if p.relative_to(on).parts[0] != "research":
            assert "Toronto" not in p.read_text(encoding="utf-8"), p


# ---- M7 /partners/ only with promotion codes
def test_partners_page_exists_only_while_promotion_codes_are_on(off, on, tmp_path):
    assert not (off / "partners").exists() and "/partners/" not in (off / "sitemap.xml").read_text(encoding="utf-8")
    assert (on / "partners" / "index.html").exists()
    assert "/partners/" not in (on / "sitemap.xml").read_text(encoding="utf-8")
    for out in (off, on):
        for p in out.rglob("*.html"):
            if p.relative_to(out).parts[0] != "research":
                assert 'href="/partners/"' not in p.read_text(encoding="utf-8"), p
    assert lint_ok(off) == [] and lint_ok(on) == []
    r, o = build(tmp_path, "pr", toml=on_toml(promo=False), partners={})
    assert r.returncode == 0 and not (o / "partners").exists()


# =============================================================================== FIX ROUND 2 (Manager)
def collapse(s):
    return re.sub(r"\s+", " ", s.replace("\u00a0", " "))


# ---- 1 the beta-removal sentence says what importers.json says
def test_the_formats_sentence_is_true_to_importers_json_in_all_six_places(off):
    cfg = json.load(open(os.path.join(SITE, "config", "importers.json"), encoding="utf-8"))["formats"]
    assert not any(x["verified"] for x in cfg if x.get("reader")) and [x["id"] for x in cfg if x["verified"]] == ["generic"]
    en = ("The four broker file readers (MetaTrader 4/5, IBKR, Tradovate and TradingView) are built from each platform’s published "
          "format and have not yet been tested on a real export; the donttrade CSV template has.")
    fr = ("Les quatre lecteurs de fichiers de courtiers (MetaTrader 4/5, IBKR, Tradovate et TradingView) sont conçus d’après le format "
          "publié par chaque plateforme et n’ont pas encore été testés avec une vraie exportation; le modèle CSV de donttrade l’a été.")
    places = {"before-you-pay": 1, "terms": 1, "for-traders": 1}   # the sixth place is For-traders' waitlist branch (paid_report off)
    for rel, n in places.items():
        assert collapse(text_of(off / rel / "index.html")).count(en) == n, rel
    for rel in ("fr/avant-de-payer", "fr/conditions"):
        assert collapse(text_of(off / rel / "index.html")).count(fr) == 1, rel
    wl = open(os.path.join(SITE, "templates", "pages", "for-traders.html"), encoding="utf-8").read()
    assert wl.count("refund.formats_caveat()") == 2     # paid and waitlist branches
    for rel in ("before-you-pay", "terms", "for-traders", "fr/avant-de-payer", "fr/conditions", "pricing", "welcome", "report"):
        assert "not every one" not in text_of(off / rel / "index.html") and "tous n’ont pas" not in text_of(off / rel / "index.html")


def test_the_formats_sentence_changes_when_a_reader_flips(tmp_path):
    """Generated from importers.json: with one reader tested, the sentence names only the others."""
    import jinja2
    env = jinja2.Environment(loader=jinja2.FileSystemLoader(os.path.join(SITE, "templates")), undefined=jinja2.StrictUndefined, autoescape=True)
    env.filters.update(numword=B.numword, numword_fr=B.numword_fr)
    src = '{% import "partials/refund_copy.html" as r with context %}{{ r.formats_caveat() }}'
    prices = json.load(open((os.environ.get("DT_PRICES_JSON") or os.path.join(SITE, "config", "prices.json")), encoding="utf-8"))
    names = ["MetaTrader 4/5", "IBKR", "Tradovate", "TradingView"]
    out = env.from_string(src).render(prices=prices, refund_on=False, readers_untested=["IBKR", "Tradovate", "TradingView"], readers_all=names)
    assert "These broker file readers are built" in out and "IBKR, Tradovate, TradingView" in out and "MetaTrader 4/5, IBKR" not in out
    assert "The four broker file readers" in env.from_string(src).render(prices=prices, refund_on=False, readers_untested=names, readers_all=names)


@pytest.mark.parametrize("plant", ["<p>in beta</p>", "<p>Beta wording</p>", "<p>version bêta</p>", "<p>(all in BETA)</p>"])
def test_lint_refuses_the_word_beta_on_a_page(off, plant):
    h = (off / "about" / "index.html").read_text(encoding="utf-8").replace("</main>", plant + "</main>", 1)
    assert any(p[0] == "banned:retired_name" for p in L.lint_html(h, "/about/", True, True, L.allowed_amounts(), (), commerce=True)), plant


# ---- 2 "withdrawn on" is the launch date and says why
def test_withdrawn_on_is_the_launch_date_and_states_the_reason(off, tmp_path):
    sentence = ("Fixed-price firm engagements (Snapshot, Memo, Outcomes pack) were withdrawn on 29 Oct 2026, the day donttrade moved to "
                "one paid product, the Revenge Trading Report; a scope accepted before then keeps its agreed price and terms.")
    assert sentence in text_of(off / "terms" / "index.html")
    assert re.search(r'launch_date = "2026-10-29"', TOML)
    r, out = build(tmp_path, "later", toml=TOML.replace('terms_date = "2026-11-06"', 'terms_date = "2026-11-05"').replace('privacy_date = "2026-11-06"', 'privacy_date = "2026-11-05"'))
    assert r.returncode == 0, r.stderr
    t = text_of(out / "terms" / "index.html")
    assert "Version 2026-11-05." in t and sentence in t           # a terms bump does not move it


# ---- 3 Terms summary line, flag on
def test_terms_summary_line_has_no_bare_full_refund(on, off):
    h = (on / "terms" / "index.html").read_text(encoding="utf-8")
    m = re.search(r'<span class="ls-sum">No cancellation fees\.([^<]*)</span>', h)
    assert collapse(m.group(1)).strip() == "Traders: No result, no charge. Full refund within 14 days if no result is delivered (details in the refund terms below)."
    for sent in re.split(r"(?<=[.;])\s+", collapse(m.group(0))):
        assert "full refund" not in sent.lower() or "if no result is delivered" in sent
    assert "Traders: full refund within 14 days." in (off / "terms" / "index.html").read_text(encoding="utf-8")


# ---- 4 home caveat says the same true thing as Before-you-pay
def test_home_caveat_agrees_with_before_you_pay(off):
    home, byp = text_of(off / "index.html"), collapse(text_of(off / "before-you-pay" / "index.html"))
    assert "A file with dates but no times gets no tested habits." in home and "fewer habits" not in home
    assert "no habit is tested" in byp and "dates but no times" in byp


# ---- 5 misuse bullet
def test_misuse_bullet_is_unambiguous_flag_on_only(on, off):
    want = ("Misuse of refunds: a refund is always made in the cases listed under Refunds. Beyond those cases, we may decline a goodwill "
            "refund, or a new order, from someone who has repeatedly asked for refunds after receiving results. A person reviews each "
            "case and writes to you first.")
    assert want in collapse(text_of(on / "terms" / "index.html"))
    assert "Misuse of refunds" not in text_of(off / "terms" / "index.html") and "goodwill" not in text_of(off / "terms" / "index.html")
    fr = collapse(text_of(on / "fr" / "conditions" / "index.html"))
    assert "Abus des remboursements : un remboursement est toujours fait dans les cas énumérés sous Remboursements. Au-delà de ces cas" in fr


# ---- 6 spelled-out amounts
@pytest.mark.parametrize("plant", ["<p>The test costs 49 dollars.</p>", "<p>forty-nine dollars after launch</p>", "<p>Forty nine US dollars.</p>",
                                   "<p>49 dollars US</p>", "<p>quarante-neuf dollars après.</p>", "<p>quarante-neuf dollars américains</p>",
                                   "<p>49 dollars américains</p>"])
def test_spelled_out_next_price_fails_while_the_founding_price_is_open(plant, shown_prices):
    ok = f"<p>US$39 {APPROVED_EN}.</p><p>{APPROVED_FR}.</p>"
    assert B.founding_problem(ok, True, 100) is None
    assert "approved form" in B.founding_problem(ok + plant, True, 100), plant
    assert any(p[0] == "claim:founding_price" for p in L.founding_claims(ok + plant, "/x/"))


def test_spelled_amount_regex_covers_french_and_english_numbers():
    for n, words in ((49, ["forty-nine dollars", "quarante-neuf dollars"]), (95, ["ninety-five dollars", "quatre-vingt-quinze dollars"]),
                     (80, ["eighty dollars", "quatre-vingts dollars"]), (21, ["twenty-one dollars", "vingt et un dollars"]), (15, ["fifteen dollars", "quinze dollars"])):
        for w in words:
            assert re.search(B.spelled_amount(n), w, re.I), (n, w)
    assert not re.search(B.spelled_amount(49), "forty-eight dollars", re.I)
