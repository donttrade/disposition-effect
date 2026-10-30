"""Step 4 (lint part): every lint rule fails on one planted violation and passes the real build."""
import json
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
import lint as L  # noqa: E402

AMOUNTS = L.allowed_amounts()
DISCLAIMER = ("donttrade measures your own past trades. It is not investment advice, does not recommend any security, "
              "trade, size or exit, and is not registered as an adviser. Past results do not predict future results.")


def rules(html, paid=False, analytics=False, priv=()):
    return {r for r, _, _ in L.lint_html(html, "/x/", paid, analytics, AMOUNTS, list(priv))}


@pytest.mark.parametrize("html,rule", [
    ("<p>Our advice: hold.</p>", "banned:advice"),
    ("<p>We recommend this rule.</p>", "banned:recommend"),
    ("<p>You should close losers.</p>", "banned:directive"),
    ("<p>Fix your trading.</p>", "banned:directive"),
    ("<p>Your trading coach.</p>", "banned:coaching"),
    ("<p>Become profitable fast.</p>", "banned:promises"),
    ("<p>You lost $500 because of tilt.</p>", "banned:cause"),
    ("<p>Unlock your edge.</p>", "banned:ai_tells"),
    ("<p>The #1 journal.</p>", "banned:ai_tells"),
    ("<p>A certified result.</p>", "banned:assurance"),
    ("<p>Your figure, audited.</p>", "banned:assurance"),
    ("<p>Start the trial today.</p>", "banned:renamed"),
    ("<p>Standard prices after launch apply.</p>", "banned:regular_price"),
    ('<a href="https://tally.so/r/x">form</a>', "tally"),
    ("<p>Only $59 today.</p>", "price_literal"),
    ("<p>Then $49 after the founding offer.</p>", "price_literal"),  # retired 20 Oct: allowed nowhere
    ("<p>We help you improve.</p>", "banned:one_product"),           # 29 Oct (one product)
    ("<p>A buy signal.</p>", "banned:one_product"),
    ("<p>Your DT-1 score.</p>", "banned:one_product"),
    ("<p>Method DT-1 is live.</p>", "claim:dt_name_alone"),
    ("<p>key " + "sk_" + "live_abcdefgh1234</p>", "secret"),  # built at runtime so repo secret scans stay clean
    ('<div data-requires-flag="paid_report">x</div>', "flag:paid_markup"),
    ('<script type="application/ld+json">{"@type": "Product"}</script>', "flag:product_jsonld"),
    ("<p>[SELLER — lawyer to confirm]</p>", "flag:seller_placeholder"),
    ("<dl><dt data-seller-block>Seller</dt></dl>", "flag:seller_block"),
    ('<form data-requires-flag="pilot_checkout"></form>', "flag:pilot_markup"),
    ('<a href="https://buy.stripe.com/x">pay</a>', "flag:stripe_link"),
    ('<script src="https://static.cloudflareinsights.com/beacon.min.js"></script>', "flag:beacon"),
])
def test_planted_violation_fails(html, rule):
    assert rule in rules(html)


def test_claims_flip_with_flags():
    assert "claim:no_upload" in rules("<p>Nothing leaves your computer.</p>", paid=True)
    # fix D9 (21 Oct): these claims are false next to the paid pipeline, so they fail with the flag off too
    assert "claim:no_upload" in rules("<p>Nothing leaves your computer.</p>", paid=False)
    assert "claim:no_analytics" in rules("<p>This site runs no analytics.</p>", analytics=True)
    assert "flag:seller_identity" in rules("<p>Jane Q Seller</p>", priv=["Jane Q Seller"])


def test_allowlisted_negations_and_disclaimer_pass():
    ok = (f"<p>{DISCLAIMER}</p><p>Nothing here is investment advice.</p><p>Published price, $745, $0.50 and $500.</p>"
          "<p>Method DT-1 of the donttrade test, a habit test on your own trades.</p>")
    assert rules(ok) == set()


def test_real_build_passes():
    subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], check=True, capture_output=True)
    assert L.lint_build(os.path.join(REPO, "site", "_site")) == []


# 29 Oct (one product): every retired amount fails on a templated page and on a passthrough page.
RETIRED = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))["retired_amounts"]["amounts"]


def _money(a):
    return "${:,.2f}".format(a) if a != int(a) else "${:,}".format(int(a))


@pytest.mark.parametrize("amount", RETIRED)
def test_every_retired_amount_fails_on_a_templated_and_a_passthrough_page(amount):
    html = f"<p>It was {_money(amount)}.</p>"
    assert "price_literal" in rules(html), amount
    assert any(r == "price_literal" for r, _, _ in L.passthrough_rules(html, "/old/", False)), amount


def test_retired_products_are_gone_from_prices_json():
    d = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
    assert [p["id"] for p in d["products"]] == ["pilot", "plan", "report39"]
    assert "recheck" not in d["rules"]
    assert sorted(RETIRED) == sorted([49, 99, 79, 2500, 6000, 12000, 625, 1500, 3000, 186.25])


# 30 Oct (Tester #4): retired names and removed habit statuses fail on customer-visible text
@pytest.mark.parametrize("text", ["Get the habit report today.", "A Snapshot of your book.", "Ask about a Memo.", "The Outcomes pack.",
                                  "The Habit Tracker is back.", "Try the demo.", "A fake trader.", "Some made-up numbers.",
                                  "This is not a real trader.", "Size after a loss: described, not tested.", "This pattern is not tested.",
                                  "So this pattern is described here without a verdict."])
def test_retired_names_fail(text):
    assert "banned:retired_name" in rules(f"<p>{text}</p>"), text


@pytest.mark.parametrize("text", ["Fixed-price firm engagements (Snapshot, Memo, Outcomes pack) were withdrawn on 29 Oct 2026; a scope "
                                  "accepted before then keeps its agreed price and terms.",
                                  "A one-page memo, every month.", "A data snapshot of 16 Oct 2026.", "It describes your past trades."])
def test_retired_names_allow_the_withdrawn_line_and_ordinary_words(text):
    assert "banned:retired_name" not in rules(f"<p>{text}</p>"), text


def test_retired_names_do_not_apply_to_a_frozen_study_body():
    body = "<p>Scalping was not tested. A Memo from 1998 described the sample report.</p>"
    assert not [r for r in L.passthrough_rules(body, "/research/x/", False) if r[0] == "banned:retired_name"]
