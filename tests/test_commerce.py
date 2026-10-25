"""Step 24: flag-gated commerce — Before you pay, pricing tabs, trader-first home, Stripe test link."""
import functools
import http.server
import os
import subprocess
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import lint as L  # noqa: E402
from test_legal import FAKE, FAKE_TEST_LINK, paid_env  # noqa: E402

EXAMPLE = os.path.join(REPO, "site/config/private.example.toml")


def flag_toml(tmp):
    src = open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()
    src = src.replace("paid_report = false", "paid_report = true").replace("trader_first_home = false", "trader_first_home = true")
    p = tmp / "site.toml"
    p.write_text(src, encoding="utf-8")
    return str(p)


def build(tmp, name, **env):
    out = tmp / name
    e = {**os.environ, "DT_OUT": str(out), **env}
    e.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=e, capture_output=True, text=True)
    return r, out


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def paid_site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("commerce")
    r, out = build(tmp, "on", **paid_env(tmp))  # well-formed fake values: no escape variable (D10)
    assert r.returncode == 0, r.stderr
    assert "WARNING" not in r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


def test_flag_on_with_placeholders_fails_without_allow(tmp_path):
    r, _ = build(tmp_path, "x", DT_SITE_TOML=flag_toml(tmp_path), DT_PRIVATE_TOML=EXAMPLE)
    assert r.returncode == 1 and ("placeholder" in r.stderr or "stripe_link" in r.stderr)


def test_flag_on_build_passes_lint(paid_site):
    assert L.lint_build(str(paid_site["out"]), paid=True) == []


def test_before_you_pay_has_every_l1_item(paid_site):
    html = (paid_site["out"] / "pricing/index.html").read_text()
    for item in ["Seller", "Business address", "Phone", "Email", "Technical requirements", "No sales tax is charged",
                 "currency conversion fee", "Card, through Stripe", "Right after payment", "re-test", "20,000 rows",
                 "Refunds", "$39 USD", FAKE["seller_legal_name"], FAKE["phone"]]:
        assert item in html, item
    for pid in ["firms", "copy-leader", "claims-test", "platforms", "traders", "researchers", "payment", "refunds",
                "history", "questions"]:
        assert f'id="{pid}"' in html, pid


def test_flag_off_outputs_have_no_commerce(tmp_path):
    r, out = build(tmp_path, "off")
    assert r.returncode == 0
    allhtml = "".join(p.read_text(errors="replace") for p in out.rglob("*.html"))
    for bad in ["Before you pay", "[SELLER", "See where your trades leave your plan", 'role="tablist"', "/welcome/", "/report/"]:
        assert bad not in allhtml, bad
    pricing = (out / "pricing/index.html").read_text()
    assert 'role="tab' not in pricing and "tabs.js" not in pricing and "print.js" not in pricing
    assert pricing.index('id="firms"') < pricing.index('id="traders"')  # stacked, firms first


@pytest.mark.parametrize("color", ["light", "dark"])
def test_pricing_traders_only_axe_and_pay_panel(browser, built_site, color):
    # 25 Oct sweep (owner): /pricing/ is for traders only; firm prices are on /for-firms/, and every old firm
    # anchor lands on the one line that links there. The pay panel and its disclosure are unchanged.
    ctx = browser.new_context(color_scheme=color, viewport={"width": 375, "height": 900}, bypass_csp=True)
    page = ctx.new_page()
    page.goto(built_site["url"] + "/pricing/")
    assert page.locator('[role="tab"]').count() == 0 and page.locator("#panel-firms").count() == 0
    assert page.is_hidden("#before-you-pay")   # in the "Last step" panel
    page.click("#last-step > summary")
    assert page.is_visible("#before-you-pay") and page.locator("#last-step a[href*='buy.stripe.com']").count() == 2
    assert horizontal_overflow(page) == []
    assert axe_violations(page) == []
    for anchor in ("firms", "copy-leader", "claims-test", "platforms", "researchers", "payment"):
        assert page.locator(f"#firms #{anchor}, p#{anchor}").count() == 1, anchor
    assert page.get_attribute("#firms a", "href") == "/for-firms/#what-it-costs"
    page.goto(built_site["url"] + "/")
    assert "See the habits in your trade history." in page.inner_text("h1")
    assert axe_violations(page) == []
    ctx.close()


def test_stripe_link_comes_from_prices_json(paid_site):
    html = (paid_site["out"] / "pricing/index.html").read_text()
    assert f'href="{FAKE_TEST_LINK}"' in html and "Test mode" in html and "Payment link not set yet" not in html
