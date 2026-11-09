"""7 Nov 2026 (owner decision; ARCHITECT-PLAN-MANAGED-PAYMENTS-2026-11-07): the US$39 Revenge Trading Report is sold through
Stripe Managed Payments, Link (Stripe) being the merchant of record, so no personal name is published.

- [stripe] managed_payments = true: the seller rows of the sale (Before you pay, the traders' terms, the FR twins) name
  Link as seller and donttrade as service provider; the price/tax, payment, withdrawal and privacy words name Link; the
  owner's legal name is never pointed to; "No sales tax is charged" is gone.
- [stripe] tax_included says whether the Stripe price includes tax (true) or tax is added on top (false).
- A live build refuses the prices.json placeholder and the old non-Managed link (report39.non_managed_links).
- managed_payments = false: today's words, byte for byte (the non-Managed build is unchanged).
Every seller value here is the obviously fake fixture of test_legal.py.
"""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402
import lint as L  # noqa: E402
from test_legal import FAKE, FAKE_API, private_with  # noqa: E402

SITE_TOML = os.path.join(REPO, "site", "config", "site.toml")
PRICES = os.path.join(REPO, "site", "config", "prices.json")
OLD_LINK = "https://buy.stripe.com/eVq14m66H9Jw15a0Rwdwc04"
MP_LINK = "https://buy.stripe.com/fixtureMPzqx0000"


def committed_prices():
    with open(PRICES, encoding="utf-8") as f:
        return json.load(f)


def r39(d):
    return next(p for p in d["products"] if p["id"] == "report39")


def toml(tmp, name, managed=True, tax_included=True, drop_tax=False):
    src = open(SITE_TOML, encoding="utf-8").read()
    src = re.sub(r'(?m)^api_base = "[^"]*"', f'api_base = "{FAKE_API}"', src)
    src = re.sub(r"(?m)^(paid_report|trader_first_home) = (true|false)", r"\1 = true", src)
    src, n = re.subn(r"(?m)^managed_payments = (true|false)", f"managed_payments = {'true' if managed else 'false'}", src)
    assert n == 1
    if drop_tax:
        src, n = re.subn(r"(?m)^tax_included = (true|false)\n", "", src)
    else:
        src, n = re.subn(r"(?m)^tax_included = (true|false)", f"tax_included = {'true' if tax_included else 'false'}", src)
    assert n == 1
    p = tmp / name
    p.write_text(src, encoding="utf-8")
    return str(p)


def prices(tmp, name, live):
    d = committed_prices()
    r39(d)["stripe_link_live"] = live
    p = tmp / name
    p.write_text(json.dumps(d), encoding="utf-8")
    return str(p)


def build(tmp, name, **env):
    out = tmp / name
    e = {**os.environ, "DT_OUT": str(out), **env}
    e.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=e, capture_output=True, text=True)
    return r, out


def env_for(tmp, tag, live=MP_LINK, **kw):
    return {"DT_SITE_TOML": toml(tmp, f"{tag}.toml", **kw), "DT_PRICES_JSON": prices(tmp, f"{tag}.prices.json", live),
            "DT_PRIVATE_TOML": private_with(tmp, f"{tag}.private.toml")}


def text(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


@pytest.fixture(scope="module")
def mp(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mp")
    r, out = build(tmp, "on", **env_for(tmp, "on"))
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture(scope="module")
def mp_added(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("mpadd")
    r, out = build(tmp, "on", **env_for(tmp, "add", tax_included=False))
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture(scope="module")
def plain(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("nomp")
    r, out = build(tmp, "off", **env_for(tmp, "off", live=OLD_LINK, managed=False))
    assert r.returncode == 0, r.stderr
    return out


def read(out, rel):
    return (out / rel).read_text(encoding="utf-8")


# ------------------------------------------------------------------ the committed config and the link guard
def test_committed_config_is_managed_with_the_live_link_and_the_old_link_listed():
    # 8 Nov go-live: the placeholder was replaced by the founding Managed link (plink_1UZckbBI5xp0gJsLUbUWmz4Y).
    cfg = open(SITE_TOML, encoding="utf-8").read()
    assert re.search(r"(?m)^managed_payments = true$", cfg) and re.search(r"(?m)^tax_included = true$", cfg)
    r = r39(committed_prices())
    assert r["stripe_link_live"] == "https://buy.stripe.com/4gMcN4fHh9Jw8xCeImdwc06"
    assert r["non_managed_links"] == [OLD_LINK]


def test_live_build_refuses_the_placeholder_until_the_owner_sets_the_link(tmp_path):
    e = env_for(tmp_path, "pend", live=B.PENDING_MANAGED_LINK)
    r, _ = build(tmp_path, "pend", **e)
    assert r.returncode == 1 and "still the placeholder" in r.stderr and "go-live step 2" in r.stderr, r.stderr
    # no local-test escape opens it in a live build
    r, _ = build(tmp_path, "pend2", DT_ALLOW_NO_STRIPE_LINK="1", **e)
    assert r.returncode == 1


def test_live_build_refuses_the_old_non_managed_link_while_managed_payments_is_on(tmp_path):
    r, _ = build(tmp_path, "old", **env_for(tmp_path, "old", live=OLD_LINK))
    assert r.returncode == 1 and "a link without Managed Payments" in r.stderr, r.stderr
    # the same old link is fine with managed_payments off (today's site)
    r, _ = build(tmp_path, "oldoff", **env_for(tmp_path, "oldoff", live=OLD_LINK, managed=False))
    assert r.returncode == 0, r.stderr


def test_managed_payments_needs_tax_included(tmp_path):
    r, _ = build(tmp_path, "notax", **env_for(tmp_path, "notax", drop_tax=True))
    assert r.returncode == 1 and "needs tax_included" in r.stderr, r.stderr


# ------------------------------------------------------------------ the words
@pytest.mark.parametrize("rel", ["pricing/index.html", "before-you-pay/index.html", "terms/index.html"])
def test_sale_seller_rows_name_link_and_the_service_provider(mp, rel):
    t = text(read(mp, rel))
    assert "Seller Link, Stripe’s checkout service, as merchant of record." in t
    assert "“Sold through Link” or LINK.COM" in t
    assert f"Service provider {FAKE['seller_legal_name']}, doing business as donttrade (Ontario, Canada). donttrade makes and runs the report" in t


@pytest.mark.parametrize("rel", ["fr/avant-de-payer/index.html", "fr/conditions/index.html"])
def test_sale_seller_rows_fr(mp, rel):
    t = text(read(mp, rel))
    assert "Vendeur Link, le service de paiement de Stripe, à titre de marchand officiel (merchant of record)." in t
    assert f"Fournisseur du service {FAKE['seller_legal_name']}, faisant affaire sous le nom donttrade (Ontario, Canada)." in t


def test_no_page_points_to_the_owners_legal_name_or_says_no_sales_tax(mp):
    for root, _, files in os.walk(mp):
        for f in files:
            if f.endswith((".html", ".js")):
                h = open(os.path.join(root, f), encoding="utf-8").read()
                for bad in ("legal name is shown", "nom légal du propriétaire", "No sales tax is charged", "Aucune taxe de vente",
                            "no sales tax is charged"):
                    assert bad not in h, (bad, os.path.join(root, f))


def test_price_rows_tax_included(mp):
    byp = text(read(mp, "pricing/index.html"))
    # 8 Nov 2026 (owner): "then US$49" is hidden (prices.json rules.after_founding_shown = false)
    assert ("one time (founding price for the first 100 buyers). Any sales tax, VAT or GST is included in this price: "
            "Link works it out from your billing address and shows it on your receipt. Total: US$39.") in byp
    assert "Total US$39, any tax included, paid on Link’s secure page (Stripe)." in byp
    assert "Payment In full at checkout, on Link’s secure payment page, run by Stripe" in byp
    fr = text(read(mp, "fr/avant-de-payer/index.html"))
    assert "Taxes Les taxes de vente, la TVA ou la TPS applicables sont comprises dans le prix" in fr
    assert "39,00 $ US au total." in fr
    terms = text(read(mp, "terms/index.html"))
    assert "Any sales tax, VAT or GST is included in the price: Link, the merchant of record, charges it and pays it to the tax authorities." in terms


def test_price_rows_tax_added(mp_added):
    byp = text(read(mp_added, "pricing/index.html"))
    assert "Sales tax, VAT or GST may be added, depending on where you live" in byp and "Total: US$39 plus any such tax." in byp
    assert "Total US$39 plus any sales tax, VAT or GST, paid on Link’s secure page (Stripe)." in byp
    fr = text(read(mp_added, "fr/avant-de-payer/index.html"))
    assert "peuvent s’ajouter selon votre lieu de résidence" in fr and "plus les taxes applicables" in fr
    assert "may be added on top" in text(read(mp_added, "terms/index.html"))


def test_terms_reseller_link_support_and_withdrawal(mp):
    h = read(mp, "terms/index.html")
    t = text(h)
    assert 'id="reseller"' in h and "Link, Stripe’s checkout service, which sells it to you as merchant of record" in t
    assert 'id="link-support"' in h and 'href="https://support.link.com/"' in h
    assert "Link, as the merchant of record, applies the cooling-off rules where you live." in t
    assert "the field shown at checkout" not in t, "no waiver is collected at checkout any more"
    assert "in full at checkout, on Link’s secure payment page (run by Stripe)" in t
    fr = read(mp, "fr/conditions/index.html")
    assert 'id="revendeur"' in fr and 'id="soutien-link"' in fr and "délai de réflexion" in fr
    assert "le champ affiché au paiement" not in fr


def test_privacy_names_link_and_the_billing_address(mp):
    t = text(read(mp, "privacy/index.html"))
    assert "Link (Stripe) shows us the name, email address and billing address you enter at checkout. We do not use your billing address." in t
    assert "The Revenge Trading Report is sold through Link, Stripe’s checkout service, as merchant of record" in t
    fr = text(read(mp, "fr/confidentialite/index.html"))
    assert "adresse de facturation" in fr and "marchand officiel" in fr


def test_contact_rows_elsewhere_are_donttrade_not_link(mp):
    # privacy and the terms' Contact block describe the business, not the sale: the row is "Business", not "Seller" (one seller per page: Link), Link in one sentence
    for rel in ("privacy/index.html",):
        t = text(read(mp, rel))
        assert f"Business {FAKE['seller_legal_name']}, doing business as donttrade (Ontario, Canada)" in t
        assert "Seller" not in re.findall(r"<dt[^>]*>([^<]*)</dt>", read(mp, rel))
    contact = read(mp, "terms/index.html")
    block = contact[contact.index('id="seller"'):]
    assert "Service provider" not in block[:block.index("</dl>")]


def test_trade_name_only_rows(tmp_path):
    """private.toml seller_legal_name = "donttrade" (the owner's choice): no name anywhere, Link on the sale."""
    e = env_for(tmp_path, "tn")
    e["DT_PRIVATE_TOML"] = private_with(tmp_path, "tn.private.toml", seller_legal_name="donttrade")
    r, out = build(tmp_path, "tn", **e)
    assert r.returncode == 0, r.stderr
    t = text(read(out, "pricing/index.html"))
    assert "Service provider donttrade, a sole proprietorship (Ontario, Canada). donttrade makes and runs the report" in t
    priv = text(read(out, "privacy/index.html"))
    assert ("Business donttrade, a sole proprietorship (Ontario, Canada). The Revenge Trading Report is sold through Link, Stripe’s checkout "
            "service, as merchant of record.") in priv
    fr = text(read(out, "fr/confidentialite/index.html"))
    assert "Entreprise donttrade, entreprise individuelle (Ontario, Canada). Le rapport donttrade sur le revenge trading est vendu par l’intermédiaire de Link" in fr


def test_managed_build_lints_clean(mp, monkeypatch, tmp_path):
    monkeypatch.setenv("DT_PRIVATE_TOML", private_with(tmp_path, "lint.private.toml"))
    monkeypatch.setenv("DT_PRICES_JSON", prices(tmp_path, "lint.prices.json", MP_LINK))
    assert L.lint_build(str(mp), paid=True, analytics=True) == []


def test_non_managed_build_keeps_todays_words(plain):
    byp = text(read(plain, "pricing/index.html"))
    assert "No sales tax is charged. Total: US$39." in byp and "Payment Card, through Stripe's checkout page." in byp
    assert f"Seller {FAKE['seller_legal_name']}, doing business as donttrade (Ontario, Canada)" in byp
    assert "Service provider" not in byp and "Link’s" not in byp
    assert "Total US$39, paid on Stripe’s page." in byp
    terms = read(plain, "terms/index.html")
    assert 'id="reseller"' not in terms and 'id="link-support"' not in terms
    assert "the field shown at checkout" in text(terms)


def test_one_seller_row_per_page_and_the_pay_dialog_names_link(mp):
    """Manager S1/S2 (7 Nov): the terms name one seller (Link); the contact block is "Business". The pay dialog says
    before the click that the payment page is Link's, and carries no price next to it."""
    for rel, seller, other in (("terms/index.html", "Seller", "Business"), ("fr/conditions/index.html", "Vendeur", "Entreprise")):
        dts = re.findall(r"<dt[^>]*>([^<]*)</dt>", read(mp, rel))
        assert dts.count(seller) == 1 and other in dts, (rel, dts)
    for rel in ("pricing/index.html", "check/index.html", "index.html"):
        html = read(mp, rel)
        dlg = re.search(r'(?s)<dialog class="pay-dialog".*?</dialog>', html).group(0)
        assert "The payment page is run by Link (Stripe), the seller of record." in dlg
        line = re.search(r'<p class="pay-seller[^>]*>(.*?)</p>', dlg).group(1)
        assert "$" not in line and "US" not in line
    for rel in ("terms/index.html", "fr/conditions/index.html", "before-you-pay/index.html", "fr/avant-de-payer/index.html"):
        t = text(read(mp, rel))
        assert "provides the test" not in t and "fournit le test" not in t and "runs the test" not in t
        assert "exploite le test" not in t and "votre test a été fait" not in t
