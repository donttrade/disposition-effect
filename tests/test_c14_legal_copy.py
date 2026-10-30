"""Delivery plan C-14 (G14, G15, G16): paid-build legal copy drafts.

- /privacy/ in a paid build: no "pen name"; the buyer-details line (what Stripe shows us, what for, where it is
  kept, for how long); Cloudflare in the providers sentence. FR: the same line (#donnees-acheteur).
- /terms/ in a paid build: the chargeback line (#chargeback), the outage line (#outage), the manual restore line
  (#manual-restore, only with [site] manual_restore = true). FR: #contestation, #panne, #restauration-manuelle.
- The footer's "does not keep" (GET-PAID L7) and the French "ne conserve pas" / "non conservés" fall under the C-11
  storage rule: the fingerprint that is kept is named in the same element.
- The French Payment Link: report39 stripe_link_<mode>_fr when set, else the English link with ?locale=fr.
- build.paid_legal_problems() fails the build when any of these is missing from a paid build or present in a free one.
Every value here is an obviously fake fixture (tests/test_legal.py FAKE)."""
import json
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
from lint import lint_text  # noqa: E402
import build as B  # noqa: E402

SITE_TOML = os.path.join(REPO, "site", "config", "site.toml")
PRICES = os.path.join(REPO, "site", "config", "prices.json")
FAKE = {"seller_legal_name": "Zzqx Qqvendor Holdings", "premises_address": "PO Box 9917, Zzqxville ON K9Z 9Z9",
        "phone": "+1 555 555 0234"}
TEST_LINK = "https://buy.stripe.com/test_fixture0000zqx"
TEST_LINK_FR = "https://buy.stripe.com/test_fixturefr00zqx"

CHARGEBACK = ("Payment disputes: if you dispute the payment with your card issuer and the dispute is decided in your "
              "favour, your access key stops working, as after a refund.")
OUTAGE = ("If our server is down, your purchase is not lost and no analysis is counted. If the service is down for "
          "more than 24 hours, we refund you on request, in full.")
# The first sentence is the one /welcome/ and /restore/ show (tests/test_delta_fixes.py MANUAL), kept word for word.
RESTORE = ("If your access link stops working, email us from the address you paid with and we’ll send a new one. "
           "We send it by hand, and only to the email address on the payment.")
BUYER = ("If you buy the donttrade test: Stripe shows us the name and email address you enter at checkout. We use them "
         "only to send you the copy of your agreement, to answer your emails (a refund, a new access link) and to deal "
         "with a payment dispute. If you dispute the payment with your card issuer, we may give Stripe the dates of "
         "your purchase and of your analyses, and the number of analyses used, as evidence. Our emails with you stay "
         "in our Gmail inbox, and a private list of sales (the checkout code, the date, your name and email, and the "
         "dates we sent the copy of your agreement or a refund) is kept on our own computer, not on our server. Both are kept for the "
         "same period as purchase records (below).")
FOOTER_PAID = ("It stores your light/dark choice in your own browser and, if you buy the donttrade test, your access key "
               "there too. For that test your browser sends our server only stripped trade numbers. The server does "
               "not keep them: of those numbers it keeps only a scrambled fingerprint of each trade row from your first "
               "result, to match a re-test to the same history. Your file itself is not uploaded.")


def norm(t):
    return re.sub(r"\s+", " ", t.replace("’", "'")).strip()


def _build(tmp, name, paid=True, manual_restore=True, fr_link=None, analytics=False, extra_env=None):
    src = open(SITE_TOML, encoding="utf-8").read()
    if paid:
        src = re.sub(r"(?m)^paid_report = false", "paid_report = true", src)
        src = re.sub(r"(?m)^trader_first_home = false", "trader_first_home = true", src)
        src = re.sub(r'(?m)^api_base = "[^"]*"', 'api_base = "https://api.fixture-zqx.ca"', src)
    if not manual_restore:
        src, n = re.subn(r"(?m)^manual_restore = true", "manual_restore = false", src)
        assert n == 1
    toml = tmp / f"{name}.toml"
    toml.write_text(src, encoding="utf-8")
    priv = tmp / f"{name}-private.toml"
    priv.write_text("".join(f'{k} = "{v}"\n' for k, v in FAKE.items()), encoding="utf-8")
    d = json.load(open(PRICES, encoding="utf-8"))
    for p in d["products"]:
        if p["id"] == "report39":
            p["stripe_link_test"] = TEST_LINK
            p["stripe_link_test_fr"] = fr_link
    prices = tmp / f"{name}-prices.json"
    prices.write_text(json.dumps(d), encoding="utf-8")
    out = tmp / name
    env = {**os.environ, "DT_SITE_TOML": str(toml), "DT_PRIVATE_TOML": str(priv), "DT_PRICES_JSON": str(prices),
           "DT_OUT": str(out), "DT_DEV": ""}
    for k in ("DT_ALLOW_PLACEHOLDERS", "DT_ALLOW_LOCAL_API", "DT_ALLOW_NO_STRIPE_LINK", "DT_PREVIEW"):
        env.pop(k, None)
    env.update(extra_env or {})
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    return r, out


def page(out, path):
    return open(B.out_file(str(out), path), encoding="utf-8").read()


@pytest.fixture(scope="module")
def paid(tmp_path_factory):
    r, out = _build(tmp_path_factory.mktemp("c14"), "paid")
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture(scope="module")
def free(tmp_path_factory):
    r, out = _build(tmp_path_factory.mktemp("c14"), "free", paid=False)
    assert r.returncode == 0, r.stderr
    return out


def test_paid_terms_lines_exact(paid):
    t = page(paid, "/terms/")
    assert norm(re.sub(r"<[^>]+>", "", re.search(r'(?s)<li id="chargeback">(.*?)</li>', t).group(1))) == norm(CHARGEBACK)
    assert norm(re.sub(r"<[^>]+>", "", re.search(r'(?s)<li id="outage">(.*?)</li>', t).group(1))) == norm(OUTAGE)
    assert norm(re.search(r'(?s)<span id="manual-restore">(.*?)</span>', t).group(1)) == norm(RESTORE)


def test_paid_privacy_buyer_line_pen_name_and_cloudflare(paid):
    p = page(paid, "/privacy/")
    assert norm(re.sub(r"<[^>]+>", "", re.search(r'(?s)<li id="buyer-details">(.*?)</li>', p).group(1))) == norm(BUYER)
    assert "pen name" not in p
    li = [x for x in re.findall(r"(?s)<li>(.*?)</li>", p) if B.PROVIDERS_ABROAD in x]
    assert len(li) == 1 and "Cloudflare" in li[0], li
    # "same period as purchase records (below)": the period it points to is stated below it, once
    assert p.index('id="buyer-details"') < p.index("kept for as long as Canadian tax law requires (six years)")
    # the server paragraph names the fingerprint in the same element as "does not keep"
    assert "of those numbers it keeps only a scrambled fingerprint of each trade row from your first result" in p


def test_paid_french_lines(paid):
    c, p, a = page(paid, "/fr/conditions/"), page(paid, "/fr/confidentialite/"), page(paid, "/fr/avant-de-payer/")
    for html, i in ((c, "contestation"), (c, "panne"), (c, "restauration-manuelle"), (p, "donnees-acheteur")):
        assert re.search(r'\sid="' + i + '"', html), i
    assert "tranchée en votre faveur, votre clé d’accès cesse de fonctionner" in c
    assert "nous vous en enverrons un nouveau. Nous l’envoyons à la main, et seulement à l’adresse courriel du paiement" in c
    assert "nous vous remboursons sur demande, en entier." in c
    assert "il n’en garde que des empreintes brouillées" in p
    assert "non conservés; seules des empreintes brouillées" in p
    # R-D1.3(c): not all five habits are tested; R-D3 I-3: up to two. 29 Oct (owner, stats round 2): the hold gap is
    # "facts from your file" and size after a loss has a luck check coming; never "décrite, non testée"
    assert "Il teste cinq habitudes" not in a and "Il couvre cinq habitudes" in a and "Il en teste jusqu’à deux" in a
    assert "jusqu’à quatre" not in a and "aux gagnantes (faits tirés de votre fichier);" in a
    assert "après des pertes (vérification du hasard à venir);" in a and "non testée" not in a and "décrite" not in a


def test_paid_footer_line_exact_and_qualified(paid):
    f = B.footer_privacy({"analytics": False, "paid_report": True, "pilot_checkout": False})
    assert FOOTER_PAID in f
    assert B.storage_claim_problems(f"<p>{f}</p>", "footer") == []
    assert FOOTER_PAID in norm(page(paid, "/").replace("&#39;", "'"))


@pytest.mark.parametrize("s", [CHARGEBACK, OUTAGE, RESTORE, BUYER, FOOTER_PAID])
def test_new_english_strings_pass_the_lint(s):
    assert lint_text(s) == [] and lint_text(s, "c14", paid=True) == [], lint_text(s, "c14", paid=True)


@pytest.mark.parametrize("bad", [
    "<p class=\"legal\">Our server does not keep them. Your file is not uploaded.</p>",
    "<p>The server doesn’t keep the numbers.</p>",
    "<p>Il vous renvoie le rapport et ne conserve pas ces chiffres.</p>",
    "<li>chiffres de transactions envoyés pour l’analyse payante : non conservés;</li>",
])
def test_new_storage_phrases_are_caught_without_the_fingerprint(bad):
    probs = B.storage_claim_problems("<html><body>" + bad + "</body></html>", "planted.html")
    assert len(probs) == 1 and "without the fingerprint that is kept" in probs[0], probs


def test_french_link_falls_back_to_english_with_locale(paid):
    a = page(paid, "/fr/avant-de-payer/")
    assert f'href="{TEST_LINK}?locale=fr"' in a
    assert B.report_link_fr({"stripe_link_live": "https://buy.stripe.com/abc12345?x=1"}, "live") == \
        "https://buy.stripe.com/abc12345?x=1&locale=fr"
    assert B.report_link_fr({"stripe_link_live": None, "stripe_link_live_fr": None}, "live") is None
    assert B.report_link_fr({"stripe_link_test": TEST_LINK}, "test") == TEST_LINK + "?locale=fr"   # older prices.json


def test_french_link_field_is_used_and_checked(tmp_path):
    r, out = _build(tmp_path, "frlink", fr_link=TEST_LINK_FR)
    assert r.returncode == 0, r.stderr
    a = page(out, "/fr/avant-de-payer/")
    assert f'href="{TEST_LINK_FR}"' in a and "locale=fr" not in a
    assert f'href="{TEST_LINK}"' in page(out, "/pricing/")      # the English page keeps the English link
    r, _ = _build(tmp_path, "frbad", fr_link="https://buy.stripe.com/live0000fixturezqx")   # a live link in test mode
    assert r.returncode == 1 and "stripe_link_test_fr" in r.stderr, r.stderr


def test_free_build_has_none_of_the_paid_lines(free):
    for path, i in B.PAID_LEGAL_IDS + B.MANUAL_RESTORE_IDS:
        fp = B.out_file(str(free), path)
        assert not os.path.exists(fp) or f'id="{i}"' not in open(fp, encoding="utf-8").read(), (path, i)
    p = page(free, "/privacy/")
    assert "pen name" in p                                     # unchanged while nothing is sold
    li = [x for x in re.findall(r"(?s)<li>(.*?)</li>", p) if B.PROVIDERS_ABROAD in x]
    assert len(li) == 1 and "Cloudflare" in li[0]           # T0: Cloudflare Pages hosts every build since 24 Oct
    assert B.paid_legal_problems(str(free), {"flags": {"paid_report": False}, "site": {"manual_restore": True}}) == []


def test_manual_restore_off_drops_the_line(tmp_path):
    r, out = _build(tmp_path, "norestore", manual_restore=False)
    assert r.returncode == 0, r.stderr
    assert 'id="manual-restore"' not in page(out, "/terms/")
    assert 'id="restauration-manuelle"' not in page(out, "/fr/conditions/")
    assert 'id="chargeback"' in page(out, "/terms/")


def test_planted_omissions_fail_the_paid_check(paid, tmp_path):
    cfg = {"flags": {"paid_report": True}, "site": {"manual_restore": True}}
    assert B.paid_legal_problems(str(paid), cfg) == []
    out = tmp_path / "copy"
    shutil.copytree(paid, out)
    t = B.out_file(str(out), "/terms/")
    open(t, "w", encoding="utf-8").write(open(t, encoding="utf-8").read().replace('id="chargeback"', ""))
    p = B.out_file(str(out), "/privacy/")
    html = open(p, encoding="utf-8").read().replace("Web3Forms, Google, GitHub, Stripe, Substack and Cloudflare",
                                                    "Web3Forms, Google, GitHub, Stripe and Substack")
    open(p, "w", encoding="utf-8").write(html.replace("Who we are</h2>", "Who we are</h2><p>published under a pen name</p>"))
    probs = B.paid_legal_problems(str(out), cfg)
    assert any("/terms/#chargeback is missing" in x for x in probs), probs
    assert any("pen name" in x for x in probs), probs
    assert any("Cloudflare" in x for x in probs), probs
    # manual_restore = false while the line is still there
    probs = B.paid_legal_problems(str(paid), {"flags": {"paid_report": True}, "site": {"manual_restore": False}})
    assert any("/terms/#manual-restore is in this build" in x for x in probs), probs
