"""Hybrid "Start a Pilot" block behind pilot_checkout (default OFF).

3 fields (work email*, firm*, what to measure) + a required "I've read the Pilot scope and
terms" box → Web3Forms with the FIRMS key, hidden product=pilot, page, botcheck honeypot →
/start/pilot-thanks/, which shows the Stripe Pilot link from prices.json and a mailto
fallback. Works with JS off. Never next to a study finding. Seller values are fake fixtures.
"""
import functools
import http.server
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from urllib.parse import parse_qs

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
import lint as L  # noqa: E402
from a11y import axe_violations, horizontal_overflow  # noqa: E402
from test_legal import FAKE, build, private_with, toml_with  # noqa: E402

FIRM_KEY = "f8fdba04-71bb-4856-b700-01ac6796c252"
PRICES = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
PILOT = next(p for p in PRICES["products"] if p["id"] == "pilot")
PILOT_PAGES = ["/start/", "/for-firms/"]


class _Q(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def pilot_site(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("pilot")
    r, out = build(tmp, "on", DT_SITE_TOML=toml_with(tmp, pilot_checkout=True), DT_PRIVATE_TOML=private_with(tmp))
    assert r.returncode == 0, r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Q, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


def html(out, path):
    return (out / path.strip("/") / "index.html").read_text(encoding="utf-8")


def test_flag_off_has_no_pilot_checkout(built_site):
    for p in built_site["out"].rglob("*.html"):
        h = p.read_text(encoding="utf-8", errors="replace")
        assert 'id="pc"' not in h and "pilot-thanks" not in h and "buy.stripe.com" not in h, p
    assert not (built_site["out"] / "start" / "pilot-thanks").exists()


def test_flag_on_build_lints_clean(pilot_site):
    assert L.lint_build(str(pilot_site["out"]), pilot=True) == []


@pytest.mark.parametrize("path", PILOT_PAGES)
def test_block_fields(pilot_site, path):
    h = html(pilot_site["out"], path)
    form = re.search(r'(?s)<form class="request-form" id="pc".*?</form>', h).group(0)
    fields = re.findall(r'<(?:input|textarea)[^>]*\bname="([^"]+)"', form)
    assert fields == ["access_key", "subject", "from_name", "redirect", "product", "page", "ref", "botcheck",
                      "email", "firm", "message", "read_scope_and_terms"]
    assert f'name="access_key" value="{FIRM_KEY}"' in form and 'name="product" value="pilot"' in form
    assert 'name="redirect" value="https://donttrade.ca/start/pilot-thanks/"' in form
    assert re.search(r'<input id="pc-read"[^>]*type="checkbox"[^>]*required', form)
    assert 'checked' not in re.search(r'<input id="pc-read"[^>]*>', form).group(0)
    assert 'href="/terms/#trial"' in form and 'href="/for-firms/#what-it-costs"' in form


@pytest.mark.parametrize("path", PILOT_PAGES)
def test_no_study_finding_next_to_the_offer(pilot_site, path):
    """The section holding the block, and the sections either side of it, carry no finding."""
    h = html(pilot_site["out"], path)
    sections = re.findall(r"(?s)<section\b.*?</section>", h)
    i = next(k for k, s in enumerate(sections) if 'id="pc"' in s)
    near = " ".join(sections[max(0, i - 1):i + 2])
    text = re.sub(r"<[^>]+>", " ", near)
    assert not re.search(r"\d+(\.\d+)?\s?%|PGR|PLR|4,659|76\.1", text), text[:300]


@pytest.mark.parametrize("path", PILOT_PAGES)
def test_posts_with_javascript_off_only_when_box_ticked(browser, pilot_site, path):
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 375, "height": 900})
    pg = ctx.new_page()
    posted = []

    def handle(route):
        posted.append(route.request.post_data or "")
        route.fulfill(status=200, body="ok")
    pg.route("https://api.web3forms.com/**", handle)
    pg.goto(pilot_site["url"] + path + "?ref=x1")
    pg.fill("#pc-email", "test-ignore@example.com")
    pg.fill("#pc-firm", "TEST - ignore")
    pg.click("#pc button[type=submit]")  # box unticked: the browser blocks the submit
    pg.wait_for_timeout(300)
    assert posted == []
    pg.check("#pc-read")
    pg.click("#pc button[type=submit]")
    pg.wait_for_timeout(500)
    ctx.close()
    assert len(posted) == 1
    body = {k: v[0] for k, v in parse_qs(posted[0], keep_blank_values=True).items()}
    assert body["access_key"] == FIRM_KEY and body["product"] == "pilot" and body["page"] == path
    assert body["read_scope_and_terms"] == "yes" and "botcheck" not in body
    assert body["redirect"] == "https://donttrade.ca/start/pilot-thanks/"


def test_thanks_page_shows_stripe_link_mailto_and_seller(pilot_site):
    h = html(pilot_site["out"], "/start/pilot-thanks/")
    assert f'href="{PILOT["stripe_link_live"]}"' in h
    assert re.search(r'href="mailto:[^"]+\?subject=', h)
    for v in FAKE.values():
        assert v in h
    assert '<meta name="robots" content="noindex">' in h
    assert "pilot-thanks" not in (pilot_site["out"] / "sitemap.xml").read_text()
    terms = html(pilot_site["out"], "/terms/")
    assert 'id="pilot-card"' in terms and "refunded in full" in terms
    text = re.sub(r"<[^>]+>", " ", html(pilot_site["out"], "/for-firms/"))
    assert "sent only after you accept the scope" not in text  # the card sentence switched with the flag


@pytest.mark.parametrize("path", PILOT_PAGES + ["/start/pilot-thanks/"])
def test_axe_keyboard(browser, pilot_site, path):
    for scheme in ("light", "dark"):
        ctx = browser.new_context(viewport={"width": 375, "height": 900}, color_scheme=scheme, bypass_csp=True)
        pg = ctx.new_page()
        pg.goto(pilot_site["url"] + path)
        pg.evaluate("document.querySelectorAll('details').forEach(d => d.open = true)")
        assert horizontal_overflow(pg) == []
        assert axe_violations(pg) == []
        ctx.close()
    if path != "/start/pilot-thanks/":
        ctx = browser.new_context(viewport={"width": 1280, "height": 900})
        pg = ctx.new_page()
        pg.goto(pilot_site["url"] + path)
        pg.focus("#pc-email")
        seen = []
        for _ in range(12):
            seen.append(pg.evaluate("document.activeElement.id || document.activeElement.tagName"))
            pg.keyboard.press("Tab")
        assert seen[:3] == ["pc-email", "pc-firm", "pc-what"] and "pc-read" in seen
        ctx.close()


def test_pilot_checkout_needs_a_live_stripe_link(tmp_path):
    prices = os.path.join(REPO, "site", "config", "prices.json")
    backup = tmp_path / "prices.bak"
    shutil.copyfile(prices, backup)
    try:
        d = json.load(open(prices))
        for p in d["products"]:
            if p["id"] == "pilot":
                p["stripe_link_live"] = None
        json.dump(d, open(prices, "w"), indent=2)
        r, _ = build(tmp_path, "x", DT_SITE_TOML=toml_with(tmp_path, pilot_checkout=True),
                     DT_PRIVATE_TOML=private_with(tmp_path))
        assert r.returncode == 1 and "stripe_link_live" in r.stderr
    finally:
        shutil.copyfile(backup, prices)


def test_pilot_markup_planted_with_flag_off_fails(tmp_path):
    sys.path.insert(0, os.path.join(REPO, "site"))
    import build as B
    r, out = build(tmp_path, "y")
    assert r.returncode == 0
    (out / "about" / "index.html").write_text('<form data-requires-flag="pilot_checkout"></form>')
    cfg, _, _ = B.load_config()
    with pytest.raises(B.BuildError, match="pilot-checkout markup"):
        B.verify(str(out), cfg["flags"])
