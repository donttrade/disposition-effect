"""/start/ chooser (ARCHITECT-V3 §c.6, steps A3-A4): Tester invariants C1-C9.

A3 (JS off): the chooser lists prices.json's firm products in order; #<id> shows only that product's
section (CSS :target), each with a fixed product. A4 (JS on): start-chooser.js moves the hash inside
a view transition (when allowed), moves focus, handles ?product= without a hash and Back.
"""
import json
import os
import re
import sys
from urllib.parse import parse_qs

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import build as B  # noqa: E402
from a11y import axe_violations, horizontal_overflow  # noqa: E402

PRICES = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
FIRM = [p for p in PRICES["products"] if p["audience"] == "firm"]
IDS = [p["id"] for p in FIRM]
SHOWN = "() => [...document.querySelectorAll('.choice')].filter(s => getComputedStyle(s).display !== 'none').map(s => s.id)"
LIST_SHOWN = "() => getComputedStyle(document.querySelector('.chooser')).display !== 'none'"


def _start(built_site):
    return (built_site["out"] / "start" / "index.html").read_text(encoding="utf-8")


def _main_text(html):
    m = re.search(r"(?s)<main[^>]*>(.*)</main>", html).group(1)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m))


# ------------------------------------------------------------------ C1: from prices.json, in order
def test_c1_chooser_lists_the_firm_products_in_order_with_their_prices(built_site):
    html = _start(built_site)
    choose = html[html.index('class="choice-list"'):html.index("</ul>", html.index('class="choice-list"'))]
    assert re.findall(r'data-choice="([a-z]+)"', choose) == IDS
    for p in FIRM:
        assert f'<span class="cl-name">{p["name"]}</span> <span class="cl-price">{B.usd(p["price_usd"])} USD</span>' in choose
        assert f'{p["turnaround_days"]} business days' in choose
        assert f'id="{p["id"]}"' in html and f'<h2 id="{p["id"]}-h" tabindex="-1">{p["name"]} — {B.usd(p["price_usd"])} USD</h2>' in html


def test_c1_changing_a_price_in_prices_json_changes_the_page(tmp_path):
    from test_legal import build
    d = json.loads(json.dumps(PRICES))
    for p in d["products"]:
        if p["id"] == "memo":
            p["price_usd"] = 6100
    (tmp_path / "prices.json").write_text(json.dumps(d), encoding="utf-8")
    r, out = build(tmp_path, "s", DT_PRICES_JSON=str(tmp_path / "prices.json"))
    # lint is the guard for "no other number": a literal $6,000 left anywhere would be caught there
    assert r.returncode == 0, r.stderr
    html = (out / "start" / "index.html").read_text(encoding="utf-8")
    assert "$6,100 USD" in html and "$6,000" not in html


def test_c1_no_literal_price_in_the_template():
    src = open(os.path.join(REPO, "site", "templates", "pages", "start.html"), encoding="utf-8").read()
    assert not re.search(r"\$\s?\d", src)


# ------------------------------------------------------------------ C2: JS off, :target
@pytest.mark.parametrize("pid", IDS)
def test_c2_no_js_hash_shows_only_that_product(browser, built_site, pid):
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 375, "height": 812})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + f"/start/?product={pid}#{pid}")
    assert pg.evaluate(SHOWN) == [pid]
    assert pg.evaluate("document.querySelector('.choice:target').id") == pid
    assert not pg.evaluate(LIST_SHOWN), "the list hides while a product is shown (:has)"
    assert pg.input_value(f"#sf-{pid} input[name=product]") == pid
    assert pg.get_attribute(f"#sf-{pid} input[name=product]", "data-from-query") is None
    assert horizontal_overflow(pg) == []
    ctx.close()


def test_c2_no_js_plain_start_and_old_anchors(browser, built_site):
    ctx = browser.new_context(java_script_enabled=False, viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/start/")
    assert pg.evaluate(SHOWN) == [] and pg.evaluate(LIST_SHOWN)
    for anchor, sel in (("firm", "#firm"), ("platform", "#sp"), ("trader", "#wl")):
        pg.goto(built_site["url"] + "/start/#" + anchor)
        assert pg.is_visible(sel), anchor
        assert pg.evaluate(SHOWN) == []
    # a choice is a plain link: clicking it with JS off shows that section; "Change" returns to the list
    pg.goto(built_site["url"] + "/start/")
    pg.click("a[data-choice=snapshot]")
    assert pg.evaluate(SHOWN) == ["snapshot"]
    pg.click("#snapshot .choice-back")
    assert pg.evaluate(SHOWN) == [] and pg.evaluate(LIST_SHOWN)
    ctx.close()


# ------------------------------------------------------------------ C3: each form posts its own fixed product
@pytest.mark.parametrize("pid", IDS)
def test_c3_each_form_posts_its_own_product(browser, built_site, pid):
    other = "pilot" if pid != "pilot" else "memo"
    ctx = browser.new_context(java_script_enabled=False)
    pg = ctx.new_page()
    posted = []
    pg.route("https://api.web3forms.com/**", lambda route: (posted.append(route.request.post_data or ""),
                                                             route.fulfill(status=200, body="ok")))
    pg.goto(built_site["url"] + f"/start/?product={other}#{pid}")
    form = f"#sf-{pid}"
    assert pg.get_attribute(f"{form} input[type=email]", "required") is not None
    assert pg.get_attribute(f"{form} input[name=firm]", "required") is not None
    pg.fill(f"{form} input[type=email]", "test-ignore@example.org")
    pg.fill(f"{form} input[name=firm]", "TEST - ignore")
    pg.click(f"{form} button[type=submit]")
    pg.wait_for_timeout(300)
    ctx.close()
    body = {k: v[0] for k, v in parse_qs(posted[0], keep_blank_values=True).items()}
    assert body["product"] == pid and body["access_key"] == "f8fdba04-71bb-4856-b700-01ac6796c252"
    assert "botcheck" not in body and body["page"] == "/start/"


def test_c3_with_js_the_url_never_relabels_a_product_form(browser, built_site):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/start/?product=pilot#memo")
    pg.wait_for_load_state("networkidle")
    assert pg.input_value("#sf-memo input[name=product]") == "memo"
    ctx.close()


# ------------------------------------------------------------------ C4: pilot_checkout
def test_c4_pilot_checkout_puts_the_card_block_in_pilot(tmp_path):
    from test_fix_merge import _pilot_build
    r, out = _pilot_build(tmp_path, "pc")
    assert r.returncode == 0, r.stderr
    html = (out / "start" / "index.html").read_text(encoding="utf-8")
    pilot = html[html.index('id="pilot"'):html.index('id="snapshot"')]
    assert 'id="pc"' in pilot and 'data-requires-flag="pilot_checkout"' in pilot and 'id="sf-pilot"' not in pilot
    assert "Automatic refund" in pilot
    for pid in IDS[1:]:
        assert f'id="sf-{pid}"' in html and f'name="product" value="{pid}">' in html
    from test_legal import build
    r2, out2 = build(tmp_path, "off")
    assert r2.returncode == 0
    assert 'id="pc"' not in (out2 / "start" / "index.html").read_text(encoding="utf-8")


# ------------------------------------------------------------------ C5: no study figure, no pressure
def test_c5_no_finding_no_badge_no_urgency(built_site):
    html = _start(built_site)
    text = _main_text(html)
    ev = B.evidence()
    assert ev["finding"]["pct"] not in text and "4,659" not in text and "76.1" not in text
    for p in FIRM:   # the only % on the page: payment terms ("50% on acceptance; …")
        text = text.replace(p["payment_terms"], "")
    assert "%" not in text, text
    for bad in ("most popular", "popular", "best value", "limited time", "only today", "hurry", "left at this price",
                "countdown", "<s>", "<del>", "line-through"):
        assert bad not in html.lower(), bad


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 1280])
def test_start_axe_and_overflow(browser, built_site, scheme, width):
    ctx = browser.new_context(viewport={"width": width, "height": 800}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    for h in ("", "#pilot", "#outcomes"):
        pg.goto(built_site["url"] + "/start/" + h)
        pg.wait_for_load_state("networkidle")
        assert horizontal_overflow(pg) == []
        assert axe_violations(pg) == [], (h, width, scheme)
        if not h:
            for b in pg.eval_on_selector_all("a.choice-link", "as => as.map(a => a.getBoundingClientRect().height)"):
                assert b >= 44
    ctx.close()


# ------------------------------------------------------------------ C6, C7: JS on
VT_SPY = """window.__vt = 0; if (document.startViewTransition) { const o = document.startViewTransition.bind(document);
  document.startViewTransition = cb => { __vt++; return o(cb); }; }"""


@pytest.mark.parametrize("mode", ["vt", "no-vt", "reduce"])
def test_c6_c7_choice_shows_section_moves_focus_and_back_returns(browser, built_site, mode):
    kw = {"reduced_motion": "reduce"} if mode == "reduce" else {}
    ctx = browser.new_context(viewport={"width": 1280, "height": 800}, bypass_csp=True, **kw)   # wait_for_function evals
    ctx.add_init_script("delete Document.prototype.startViewTransition;" if mode == "no-vt" else VT_SPY)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/start/")
    pg.wait_for_load_state("networkidle")
    pg.click("a[data-choice=memo]")
    pg.wait_for_function("location.hash === '#memo'")
    pg.wait_for_timeout(400)   # the view transition (280 ms) ends
    assert pg.evaluate(SHOWN) == ["memo"] and not pg.evaluate(LIST_SHOWN)
    assert pg.evaluate("document.activeElement.id") == "memo-h"
    if mode == "vt":
        assert pg.evaluate("__vt") == 1
    elif mode == "reduce":
        assert pg.evaluate("__vt") == 0
        assert pg.evaluate("document.getAnimations().length") == 0, "no ::view-transition under reduced motion"
    pg.go_back()
    pg.wait_for_function("location.hash === ''")
    pg.wait_for_timeout(100)
    assert pg.evaluate(SHOWN) == [] and pg.evaluate(LIST_SHOWN)
    assert pg.evaluate("document.activeElement.getAttribute('data-choice')") == "memo"
    # "Change" goes back to the list the same way
    pg.click("a[data-choice=outcomes]")
    pg.wait_for_function("location.hash === '#outcomes'")
    pg.click("#outcomes .choice-back")
    pg.wait_for_function("location.hash === '#firm'")
    pg.wait_for_timeout(400)
    assert pg.evaluate(SHOWN) == [] and pg.evaluate("document.activeElement.getAttribute('data-choice')") == "outcomes"
    ctx.close()


# ------------------------------------------------------------------ C8: vt.css scope
def test_c8_vt_css_only_on_motion_pages_and_start(built_site):
    out = built_site["out"]
    seen = set()
    for root, _, files in os.walk(out):
        for name in files:
            fp = os.path.join(root, name)
            s = open(fp, encoding="utf-8", errors="replace").read()
            if name.endswith(".html"):
                path = "/" + os.path.relpath(fp, out).replace(os.sep, "/").replace("index.html", "")
                if "/static/css/vt.css" in s:
                    seen.add(path)
            elif name.endswith(".css") and name != "vt.css":
                assert "@view-transition" not in s and "view-transition-name" not in s, name
    assert seen == B.VT_PAGES
    vt = (out / "static" / "css" / "vt.css").read_text(encoding="utf-8")
    assert vt.index("@media (prefers-reduced-motion: no-preference)") < vt.index("@view-transition {")
    assert B.vt_problem('<link rel="stylesheet" href="/static/css/vt.css?v=0123abcd">', "/pricing/")
    assert B.vt_problem('<div class="vt-start">', "/")
    assert B.vt_problem('<link rel="stylesheet" href="/static/css/vt.css?v=0123abcd"><div class="vt-start">', "/start/") is None


# ------------------------------------------------------------------ C9: ?product= without a hash
@pytest.mark.parametrize("q,expect", [("snapshot", ["snapshot"]), ("memo", ["memo"]), ("nope", []), ("PILOT", [])])
def test_c9_product_query_without_hash(browser, built_site, q, expect):
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/start/")
    base = pg.evaluate("history.length")
    pg2 = ctx.new_page()
    pg2.goto(built_site["url"] + f"/start/?product={q}")
    pg2.wait_for_load_state("networkidle")
    assert pg2.evaluate(SHOWN) == expect
    assert pg2.evaluate("history.length") == base, "replace, not a new history entry"
    ctx.close()


def test_a4_start_chooser_budget():
    assert os.path.getsize(os.path.join(REPO, "site", "static", "js", "start-chooser.js")) <= 2560
