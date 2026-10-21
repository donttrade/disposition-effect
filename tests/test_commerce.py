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
    r, out = build(tmp, "on", DT_SITE_TOML=flag_toml(tmp), DT_PRIVATE_TOML=EXAMPLE, DT_ALLOW_PLACEHOLDERS="1")
    assert r.returncode == 0, r.stderr
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
    for item in ["Supplier", "Business address", "Phone", "Email", "Technical requirements", "No sales tax is charged",
                 "currency conversion fee", "Card, through Stripe", "Right after payment", "re-test", "20,000 trades",
                 "Refunds", "$39 USD", "[SELLER — lawyer to confirm]", "[PHONE — pending]"]:
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
def test_pricing_tabs_axe_and_keyboard(browser, paid_site, color):
    ctx = browser.new_context(color_scheme=color, viewport={"width": 375, "height": 900}, bypass_csp=True)
    page = ctx.new_page()
    page.goto(paid_site["url"] + "/pricing/")
    assert page.get_attribute("#tab-traders", "aria-selected") == "true"
    assert page.is_visible("#before-you-pay") and page.is_hidden("#panel-firms")
    page.focus("#tab-traders")
    page.keyboard.press("ArrowRight")
    assert page.get_attribute("#tab-firms", "aria-selected") == "true" and page.is_visible("#firms")
    assert horizontal_overflow(page) == []
    assert axe_violations(page) == []
    page.goto(paid_site["url"] + "/pricing/#firms")
    assert page.get_attribute("#tab-firms", "aria-selected") == "true"
    page.goto(paid_site["url"] + "/pricing/#copy-leader")
    assert page.get_attribute("#tab-firms", "aria-selected") == "true"
    page.goto(paid_site["url"] + "/")
    assert "See where your trades leave your plan." in page.inner_text("h1")
    assert axe_violations(page) == []
    ctx.close()


def test_stripe_link_comes_from_prices_json(tmp_path):
    import json
    import shutil
    prices = os.path.join(REPO, "site/config/prices.json")
    backup = tmp_path / "prices.bak"
    shutil.copyfile(prices, backup)
    try:
        d = json.load(open(prices))
        for p in d["products"]:
            if p["id"] == "report39":
                p["stripe_link_test"] = "https://buy.stripe.com/test_00000000000000"
        json.dump(d, open(prices, "w"), indent=2)
        r, out = build(tmp_path, "s", DT_SITE_TOML=flag_toml(tmp_path), DT_PRIVATE_TOML=EXAMPLE, DT_ALLOW_PLACEHOLDERS="1")
        assert r.returncode == 0, r.stderr
        html = (out / "pricing/index.html").read_text()
        assert 'href="https://buy.stripe.com/test_00000000000000"' in html and "Test mode" in html
    finally:
        shutil.copyfile(backup, prices)
