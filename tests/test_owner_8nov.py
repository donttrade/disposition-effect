"""Owner decisions of 8 Nov 2026 (binding), research memo 00-DECISION-MEMO actions 6 and 7 (trust fixes).

What is held here (the US$49 switch is in test_rounda_6nov.py, the /check/ hand-off line in test_free_check.py,
the home band in test_selloff.py, the /for-firms/ Flag Check page in test_forfirms_flagcheck.py):
  1. one public contact address, research@donttrade.ca: site.contact_email, and no built page names the old gmail address;
  2. no firm price on /pricing/: one line links to /for-firms/, every old firm anchor still lands, no firm amount;
  3. one price format on English pages, "US$39": never a bare "$39", never "US$39 USD", never "USUS".
"""
import html as _html
import json
import os
import re
import sys
import tomllib

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402

CONTACT = "research@donttrade.ca"
OLD = "donttrade.research@gmail.com"
PRICES = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
PROD = {p["id"]: p for p in PRICES["products"]}
FC = PRICES["flagcheck"]


def text(h):
    h = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", h)
    return re.sub(r" ([.,;:])", r"\1", " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", h)).split()))


def pages(out):
    for p in sorted(out.rglob("*.html")):
        yield p, p.read_text(encoding="utf-8")


# ------------------------------------------------------------------ 1. one contact address
def test_contact_email_is_research_at_donttrade():
    cfg = tomllib.load(open(os.path.join(REPO, "site", "config", "site.toml"), "rb"))
    assert cfg["site"]["contact_email"] == CONTACT


def test_no_built_page_names_the_gmail_address(built_site):
    found = [str(p.relative_to(built_site["out"])) for p, h in pages(built_site["out"]) if OLD in h]
    assert found == [], found
    for rel in ("index.html", "pricing/index.html", "terms/index.html", "privacy/index.html", "about/index.html",
                "for-researchers/index.html", "404.html"):
        fp = built_site["out"] / rel
        if fp.exists():
            assert CONTACT in fp.read_text(encoding="utf-8"), rel


def test_no_template_or_lifted_baseline_names_the_gmail_address():
    for top in ("site/templates", "checks/lifted-baseline", "site/config", "site/static/js"):
        for root, _, files in os.walk(os.path.join(REPO, top)):
            for f in files:
                if f.endswith((".html", ".json", ".toml", ".js")):
                    assert OLD not in open(os.path.join(root, f), encoding="utf-8").read(), os.path.join(root, f)


# ------------------------------------------------------------------ 2. firm prices off /pricing/
def test_pricing_has_no_firm_price_and_one_line_to_for_firms(built_site):
    h = (built_site["out"] / "pricing" / "index.html").read_text(encoding="utf-8")
    main = re.search(r"(?s)<main[^>]*>(.*)</main>", h).group(1)
    t = text(main)
    firm_amounts = {PROD["pilot"]["price_usd"], PROD["plan"]["price_usd"], PROD["plan"]["minimum_usd"],
                    FC["case_founding_usd"], FC["case_list_usd"], FC["pilot_usd"], FC["monthly_usd"], FC["extra_case_usd"]}
    shown = {float(a.replace(",", "")) for a in re.findall(r"\$\s?([0-9][0-9,]*(?:\.[0-9]+)?)", t)}
    assert not shown & {float(a) for a in firm_amounts}, shown
    line = re.findall(r'(?s)<p class="firm-line" id="firms">.*?</p>', main)
    assert len(line) == 1 and 'href="/for-firms/"' in line[0], line
    assert "Firms: independent checks of flagged payout cases, and measurement of a whole book, are on For firms." in t
    assert len(re.findall(r'<section class="price-card[^"]*"', main)) == 1   # the trader report only
    for a in ("firms", "copy-leader", "claims-test", "platforms", "researchers", "payment", "traders", "refunds",
              "history", "questions", "last-step"):
        assert f'id="{a}"' in h, a
    assert "Two ways to buy it" not in t and "One report. One price." in t
    assert "Firm prices are on For firms." in t   # the FAQ answer
    assert len(re.findall(r'href="https://buy\.stripe\.com/', main)) == 1   # still the one trader link


# ------------------------------------------------------------------ 3. one price format
def test_usd_filter_is_the_one_format():
    assert B.usd(39) == "US$39" and B.usd(0.5) == "US$0.50" and B.usd(2500) == "US$2,500" and B.usd(745.0) == "US$745"


def test_templates_never_double_the_currency():
    for root, _, files in os.walk(os.path.join(REPO, "site", "templates")):
        for f in files:
            s = open(os.path.join(root, f), encoding="utf-8").read()
            assert not re.search(r"US\{\{[^{}]*\|usd \}\}|\|usd \}\} ?USD\b|\|usd ~ \" USD", s), f


def test_english_pages_show_prices_only_as_us_dollars(built_site):
    """Every price outside the frozen lifted bodies, /research/ (study text) and the free tools' worked examples is "US$…".
    French pages keep the Quebec form ("39,00 $ US", build.usd_fr)."""
    out = built_site["out"]
    bad = {}
    for p, h in pages(out):
        rel = str(p.relative_to(out))
        if rel.startswith(("research/", "fr/", "tools/", "learn/", "dev/")):
            continue
        h = re.sub(r"(?s)<!--frozen:start-->.*<!--frozen:end-->", " ", h)
        t = text(h)
        hits = re.findall(r".{0,25}(?:(?<!US)(?<![−+\-\w])\$\s?\d[\d,.]*|USUS|US\$[\d,.]+ USD).{0,10}", t)
        if hits:
            bad[rel] = hits[:3]
    assert bad == {}, bad
    pr = text((out / "pricing" / "index.html").read_text(encoding="utf-8"))
    assert "Get the report for US$39" in pr and "US$39 once · re-test included" in pr
