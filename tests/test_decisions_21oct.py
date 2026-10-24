"""Owner decisions revised 21 Oct ~09:00 ET (V2-BUILD-PLAN "DECISIONS REVISED"; detail and exact
sentences in DECISIONS-RESEARCH-2026-10-21.md).

1. Business identification: with ANY commerce flag on, every page footer shows
   "donttrade · Ontario, Canada · <mailing address> · <business email>". The legal name and phone
   stay paid_report-only. With every commerce flag off nothing changes and private.toml is not read.
   PO box (Canada Post) and mailbox-store street addresses are accepted.

Every value here is an obviously fake fixture.
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402
import lint as L  # noqa: E402
from test_legal import FAKE, all_html, build, paid_env, private_with, same_tree, toml_with  # noqa: E402

BOX = "PO Box 4417 STN Main, Zzqxville ON K9Z 9Z9"   # Canada Post style, with a station qualifier
EMAIL = "donttrade.research@gmail.com"                # [site] contact_email, the business email
LINE_TEXT = f"donttrade · Ontario, Canada · {BOX} · {EMAIL}"


def _text(fragment):
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).split())


def _flag_env(tmp, combo):
    if combo == "pilot":
        env = {"DT_SITE_TOML": toml_with(tmp, "pilot.toml", pilot_checkout=True)}
    elif combo == "paid":
        env = paid_env(tmp)
    else:
        env = paid_env(tmp, pilot_checkout=True)
    env["DT_PRIVATE_TOML"] = private_with(tmp, f"{combo}-private.toml", premises_address=BOX)
    return env


@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    out = {}
    for combo in ("pilot", "paid", "both"):
        tmp = tmp_path_factory.mktemp("dec-" + combo)
        env = _flag_env(tmp, combo)
        r, o = build(tmp, "out", **env)
        assert r.returncode == 0, r.stderr
        out[combo] = (o, env)
    return out


# ------------------------------------------------------------------ 1. the address shape
@pytest.mark.parametrize("addr", [
    "PO Box 4417 STN Main, Zzqxville ON K9Z 9Z9",
    "PO Box 4417, STN Main, Zzqxville ON K9Z 9Z9",       # before: "1234," was read as the box number
    "PO Box 4417 Stn Main, Zzqxville ON K9Z 9Z9, Canada",
    "P.O. Box 4417 Stn. A, Zzqxville, ON K9Z 9Z9",
    "PO Box 4417 RPO Zzqx Centre, Zzqxville ON K9Z 9Z9",
    "PO Box #4417, Zzqxville ON K9Z 9Z9",
    "123 Zzqx Street Rd #456, Zzqxville ON K9Z 9Z9",     # mailbox store (UPS Store style)
    "123 Zzqx Street Rd, #456, Zzqxville ON K9Z 9Z9",
    "123 Zzqx Street Rd Suite 456, Zzqxville ON K9Z 9Z9",
])
def test_po_box_and_mailbox_addresses_are_accepted(addr):
    assert B.seller_problem("premises_address", addr) is None


@pytest.mark.parametrize("addr", [
    "PO Box, Zzqxville ON K9Z 9Z9", "PO Box STN Main, Zzqxville ON K9Z 9Z9", "PO Box 0 STN Main, Zzqxville ON K9Z 9Z9",
    "PO Box 4417 STN Main Zzqxville ON K9Z 9Z9", "PO Box 4417 STN Main, Zzqxville ON Z9Z 9Z9",
])
def test_malformed_box_addresses_are_still_refused(addr):
    assert B.seller_problem("premises_address", addr)


# ------------------------------------------------------------------ 1. flag off: unchanged, private.toml not read
def test_flag_off_does_not_read_private_toml_and_has_no_business_line(tmp_path):
    r1, a = build(tmp_path, "a")
    bad = tmp_path / "broken.toml"
    bad.write_text("this is = = not toml [[[", encoding="utf-8")
    r2, b = build(tmp_path, "b", DT_PRIVATE_TOML=str(bad))                       # unreadable: never opened
    r3, c = build(tmp_path, "c", DT_PRIVATE_TOML=str(tmp_path / "missing.toml"))  # absent: fine too
    assert r1.returncode == r2.returncode == r3.returncode == 0, (r2.stderr, r3.stderr)
    assert same_tree(str(a), str(b)) and same_tree(str(a), str(c))
    text = "".join(all_html(a).values())
    assert "data-business-id" not in text and "Ontario, Canada ·" not in text
    assert L.lint_build(str(a)) == []


# ------------------------------------------------------------------ 1. any commerce flag: every page, exactly once
@pytest.mark.parametrize("combo", ["pilot", "paid", "both"])
def test_every_page_has_the_business_line_once(builds, combo):
    out, _ = builds[combo]
    pages = all_html(out)
    assert len(pages) >= 35
    for rel, h in pages.items():
        found = B.BUSINESS_ID_RE.findall(h)
        assert len(found) == 1, rel
        assert _text(found[0]) == LINE_TEXT, (rel, _text(found[0]))
        assert f'<a href="mailto:{EMAIL}">{EMAIL}</a>' in found[0], rel
        # inside the footer, right under the contact line
        foot = h[h.rindex("<footer"):]
        assert found[0] in foot, rel
        assert foot.index(found[0]) < foot.index("Firms pay for fixed-scope measurements"), rel


def test_pilot_alone_shows_no_legal_name_or_phone(builds):
    out, _ = builds["pilot"]
    for rel, h in all_html(out).items():
        assert FAKE["seller_legal_name"] not in h and FAKE["phone"] not in h, rel
        assert "data-seller-block" not in h, rel
        assert BOX not in B.BUSINESS_ID_RE.sub("", h), rel   # the address only in the business line


def test_paid_still_shows_the_full_seller_block(builds):
    out, _ = builds["paid"]
    h = (out / "pricing" / "index.html").read_text(encoding="utf-8")
    assert "data-seller-block" in h and FAKE["seller_legal_name"] in h and FAKE["phone"] in h


@pytest.mark.parametrize("combo", ["pilot", "paid", "both"])
def test_flag_builds_lint_clean(builds, combo, monkeypatch):
    out, env = builds[combo]
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    pilot = combo in ("pilot", "both")
    paid = combo in ("paid", "both")
    assert L.lint_build(str(out), paid=paid, pilot=pilot) == []


# ------------------------------------------------------------------ 1. loud failures
def test_verify_fails_when_a_page_loses_its_line(builds, tmp_path):
    import shutil
    out, _ = builds["pilot"]
    copy = tmp_path / "copy"
    shutil.copytree(out, copy)
    fp = copy / "about" / "index.html"
    fp.write_text(B.BUSINESS_ID_RE.sub("", fp.read_text(encoding="utf-8")), encoding="utf-8")
    flags = {"paid_report": False, "pilot_checkout": True, "analytics": False}
    with pytest.raises(B.BuildError, match="business line: about/index.html has 0"):
        B.verify(str(copy), flags, seller=False)
    problems = L.lint_build(str(copy), pilot=True)
    assert ("business_line", "/about/index.html", "0 business-identification line(s), expected exactly 1") in problems


def test_lint_flags_a_line_in_a_flag_off_build_and_a_wrong_address(builds, tmp_path):
    line = B.business_id_line({"flags": {"paid_report": False, "pilot_checkout": True},
                               "site": {"name": "donttrade", "contact_email": EMAIL}}, {"premises_address": BOX})
    assert L.business_line_problems("<footer>" + line + "</footer>", "/x/", commerce=False) == [
        ("flag:business_line", "/x/", "business line with every commerce flag off")]
    assert L.business_line_problems("<footer>" + line + "</footer>", "/x/", True, [BOX]) == []
    other = line.replace("4417", "4418")
    assert L.business_line_problems(other, "/x/", True, [BOX])[0][0] == "business_line"
    assert L.business_line_problems(line + line, "/x/", True, [BOX])[0][2].startswith("2 business")
    assert L.business_line_problems(line.replace("Ontario, Canada", "Canada"), "/x/", True, [BOX])[0][0] == "business_line"


def test_passthrough_page_without_the_footer_anchor_fails_the_build(monkeypatch):
    monkeypatch.setattr(B, "PASSTHROUGH_BUSINESS_ANCHOR", "  <p class=\"no-such-anchor\">")
    with pytest.raises(B.BuildError, match="business line: .* expected 1"):
        B.add_business_line("<footer></footer>", "x/index.html", "<p data-business-id>…</p>")
    assert B.add_business_line("unchanged", "x/index.html", "") == "unchanged"   # flags off: no change


def test_business_line_without_an_address_fails_loudly():
    cfg = {"flags": {"paid_report": False, "pilot_checkout": True}, "site": {"name": "donttrade", "contact_email": EMAIL}}
    with pytest.raises(B.BuildError, match="no mailing address"):
        B.business_id_line(cfg, {})
    assert B.business_id_line({**cfg, "flags": {"paid_report": False, "pilot_checkout": False}}, {}) == ""


# ------------------------------------------------------------------ 2. Pilot refund clause
# The exact sentence (owner decision 21 Oct ~09:00); the amount is rendered from prices.json.
def refund_sentence(price):
    return ("If the scope is not confirmed in writing by both of us within 10 business days of payment, we refund the "
            f"full US${price:,} by the end of the next business day, without being asked.")


PRICES = __import__("json").load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
PILOT_PRICE = next(p for p in PRICES["products"] if p["id"] == "pilot")["price_usd"]
SENTENCE = refund_sentence(PILOT_PRICE)


def _page(out, path):
    return (out / path.strip("/") / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("path", ["/start/", "/for-firms/"])
@pytest.mark.parametrize("combo", ["pilot", "both"])
def test_refund_clause_sits_right_above_the_required_box(builds, combo, path):
    h = _page(builds[combo][0], path)
    form = re.search(r'(?s)<form class="request-form" id="pc".*?</form>', h).group(0)
    m = re.search(r'(?s)<p class="small" id="pc-refund">(.*?)</p>\s*<div class="check field"><input id="pc-read"[^>]*required', form)
    assert m, "the clause is not the element right before the required box"
    assert _text(m.group(1)) == "Automatic refund: " + SENTENCE


@pytest.mark.parametrize("combo", ["pilot", "both"])
def test_refund_clause_in_terms_pilot_section_and_on_the_thanks_page(builds, combo):
    out = builds[combo][0]
    terms = _page(out, "/terms/")
    section = terms[terms.index('<h2 id="trial">'):terms.index('<h2 id="cancellation">')]
    li = re.search(r'(?s)<li id="pilot-refund">(.*?)</li>', section)
    assert li and _text(li.group(1)) == "Automatic refund if the scope isn’t confirmed: " + SENTENCE
    thanks = _page(out, "/start/pilot-thanks/")
    p = re.search(r'(?s)<p id="pilot-refund">(.*?)</p>', thanks)
    assert p and _text(p.group(1)) == "Automatic refund: " + SENTENCE
    assert thanks.index('id="pilot-refund"') < thanks.index("buy.stripe.com")   # read before the Pay button
    for h in (terms, thanks):
        assert "If we can’t agree the scope with you" not in h                   # the vaguer wording is gone


def test_refund_amount_comes_from_prices_json(tmp_path):
    import json
    d = json.loads(json.dumps(PRICES))
    for p in d["products"]:
        if p["id"] == "pilot":
            p["price_usd"] = 845
    prices = tmp_path / "prices.json"
    prices.write_text(json.dumps(d), encoding="utf-8")
    r, out = build(tmp_path, "o", DT_SITE_TOML=toml_with(tmp_path, pilot_checkout=True),
                   DT_PRIVATE_TOML=private_with(tmp_path, premises_address=BOX), DT_PRICES_JSON=str(prices))
    assert r.returncode == 0, r.stderr
    for path in ("/start/", "/for-firms/", "/terms/", "/start/pilot-thanks/"):
        text = _text(_page(out, path))
        assert refund_sentence(845) in text and "US$745" not in text, path


def test_refund_clause_is_pilot_checkout_only(builds, built_site):
    # v3 A3 (ARCHITECT-V3-PLAN §c.6) gives each /start/ product its own "what happens next" steps, so the
    # Snapshot (turnaround 10 business days in prices.json) promises delivery "within 10 business days of
    # payment and a clean run", the same delivery wording as /for-firms/. That is a delivery time, not the
    # refund clause, so only that exact continuation is set aside; the clause itself is matched in full.
    clause = re.compile(r"within 10 business days of payment(?! and a clean run)")
    for out in (built_site["out"], builds["paid"][0]):
        for rel, h in all_html(out).items():
            assert not clause.search(h), rel
            assert "not confirmed in writing by both of us" not in h and 'id="pilot-refund"' not in h, rel


def test_terms_version_was_bumped_for_these_legal_edits(built_site):
    # Manager C3: the version is [legal] launch_date (empty = the build date), never a future date
    # T0: /privacy/ carries the later of that and [legal] cloudflare_pages_since (the hosting change)
    from test_legal import TERMS_VERSION as v, PRIVACY_VERSION as pv
    assert re.fullmatch(r"\d{4}-\d{2}-\d{2}", v) and pv == max(v, "2026-10-24")
    for path, want in (("/terms/", v), ("/privacy/", pv)):
        assert f"Version {want}." in _page(built_site["out"], path), path


# ------------------------------------------------------------------ 2. lint: never ask to waive dispute rights
@pytest.mark.parametrize("bad", [
    "By paying you agree to waive your right to dispute this charge.",
    "Chargebacks are waived once the scope is sent.",
    "You waive any chargeback.",
    "The client agrees not to dispute the payment with its bank.",
    "You agree not to initiate a charge-back.",
    "You give up the right to contest the charge with your card issuer.",
    "Vous renoncez à toute rétrofacturation.",
    "Le client renonce à contester le paiement.",
])
def test_lint_refuses_waiving_dispute_rights(bad):
    html = f'<html lang="en"><body><main><p>{bad}</p></main></body></html>'
    problems = L.lint_html(html, "/x/", False, False, {745}, [], pilot=True)
    assert any(p[0] == "claim:waive_dispute" for p in problems), (bad, problems)
    assert any(p[0] == "claim:waive_dispute" for p in L.passthrough_rules(html, "/x/", False))
    assert L.waive_dispute_claims(L.js_strings(f"const m = '{bad}';"), "/x.js")


@pytest.mark.parametrize("ok", [
    SENTENCE,
    "These terms are governed by the laws of the Province of Ontario, and disputes go to the courts of Ontario.",
    "We can’t help with disputes about a firm.",
    "The credit has no cash value and cannot be transferred.",
])
def test_lint_waive_rule_has_no_false_positive(ok):
    assert L.waive_dispute_claims(L.normalise(ok), "/x/") == []


# ------------------------------------------------------------------ 3. re-test fingerprint retention (privacy page)
PRIVACY_SENTENCE = (
    "To check that a re-test uses the same trading history as your first report, we keep a scrambled fingerprint of "
    "each trade row (a keyed hash: it cannot be turned back into your trades without our secret key, but it is still "
    "linked to your purchase). We delete these fingerprints as soon as your included re-test has run, or 75 days after "
    "your first report, whichever comes first. If you have an active Habit Tracker, we keep them while it is active and "
    "delete them 15 days after it ends.")


@pytest.mark.parametrize("combo", ["paid", "both"])
def test_privacy_states_the_retention_rule_word_for_word(builds, combo):
    h = _page(builds[combo][0], "/privacy/")
    section = h[h.index('<h2 id="report">'):h.index('<h2 id="forms">')]
    p = re.search(r'(?s)<p id="fingerprints">(.*?)</p>', section)
    assert p and _text(p.group(1)) == PRIVACY_SENTENCE
    assert "90 days" not in _text(section)


def test_retention_sentence_only_where_the_paid_report_exists(builds, built_site):
    for out in (built_site["out"], builds["pilot"][0]):
        assert "fingerprint" not in _page(out, "/privacy/")


def test_french_privacy_section_is_marked_translation_pending(builds):
    src = open(os.path.join(REPO, "site", "templates", "pages", "fr", "confidentialite.html"), encoding="utf-8").read()
    assert "TRANSLATION PENDING" in src and "do not machine-translate" in src
    fr = _page(builds["paid"][0], "/fr/confidentialite/")
    assert "75" not in _text(fr) and "TRANSLATION PENDING" not in fr     # nothing machine-translated, no marker shown


# ------------------------------------------------------------------ ruling #2: the key's end
# The server (dt-private, KEY_AFTER_FIRST_REPORT_DAYS) moves the key's end at the first report to
# max(purchase + 90 days, first report + 75 days). Every page that states how long access lasts says so.
KEY_EN_TERMS = "Your key is valid for 90 days after purchase, or until 75 days after your first report if that is later."
KEY_EN_PRICING = "Access lasts 90 days after purchase, or until 75 days after your first report if that is later."
KEY_FR = ("Votre clé d’accès est valide 90 jours après l’achat, ou jusqu’à 75 jours après votre premier rapport "
          "si cette date est plus tardive.")


@pytest.mark.parametrize("path,sentence", [("/terms/", KEY_EN_TERMS), ("/pricing/", KEY_EN_PRICING),
                                           ("/fr/conditions/", KEY_FR), ("/fr/avant-de-payer/", KEY_FR)])
def test_key_lifetime_matches_the_server_rule(builds, path, sentence):
    text = _text(_page(builds["paid"][0], path))
    assert sentence in text
    for old in ("valid for 90 days.", "Access lasts 90 days.", "valide 90 jours.", "valide 90 jours après l’achat. "):
        assert old not in text
    assert "TRANSLATOR CHECK" not in text
