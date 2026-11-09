"""Hardening round, 3 Nov (ARCHITECT-HARDENING-PLAN-2026-11-03 items 1-7, plus Tester R2 / Manager fixes A-D).

1 security headers (site/build.py headers_file -> _headers), 2 /favicon.ico, 3 the age clause (EN + FR),
4 the CASL unsubscribe lines (EN + FR) and the waitlist's withdrawal line, 5 early deletion or a copy (EN + FR),
6 one button label "Get the report for US$39", 7 campaign tags through the umami-clean.js before-send hook, with
data-exclude-search kept on the pages whose address can carry a secret.
A the footer's analytics sentence per page, B Threads on www.threads.com, C no data-umami-event-* property
(lint), D "for traders, the only paid product" on /about/ and /independence/.

No test reaches the network: the browser contexts route every outside host locally (conftest), and the real-tracker
tests use the pinned tests/fixtures/umami-script.js with gateway.umami.is answered in-process.
"""
import functools
import http.server
import json
import os
import re
import shutil
import sys
import threading
import urllib.parse

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")
DOCS = os.path.join(REPO, "docs")
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, SITE)
import build as B  # noqa: E402
import lint as L  # noqa: E402
from test_legal import PRIVACY_VERSION, TERMS_VERSION  # noqa: E402
from test_umami import TRACKER, _ok, _real_tracker_context  # noqa: E402


def _read(built_site, path):
    return open(B.out_file(str(built_site["out"]), path), encoding="utf-8").read()


def _pages(out):
    for d, _, files in os.walk(out):
        for f in files:
            if f.endswith(".html"):
                p = os.path.join(d, f)
                yield "/" + os.path.relpath(p, out).replace(os.sep, "/"), open(p, encoding="utf-8").read()


def _tpl(*parts):
    return open(os.path.join(SITE, "templates", *parts), encoding="utf-8").read()


# ================================================================== 1. security headers
def _rules(text):
    """{rule pattern: [(name, value)]} of a _headers file."""
    rules, cur = {}, None
    for ln in text.split("\n"):
        if not ln.strip() or ln.startswith("#"):
            continue
        if ln.startswith((" ", "\t")):
            k, v = ln.strip().split(":", 1)
            rules[cur].append((k.strip(), v.strip()))
        else:
            cur = ln.strip()
            rules[cur] = []
    return rules


def test_build_writes_the_headers_file(built_site):
    text = (built_site["out"] / "_headers").read_text(encoding="utf-8")
    assert text == B.headers_file()
    assert B.headers_problem(text) is None
    rules = _rules(text)
    assert len(rules) <= 100 and all(len(ln) <= 2000 for ln in text.split("\n"))
    assert rules["/*"] == B.SECURITY_HEADERS == [
        ("Strict-Transport-Security", "max-age=31536000"),
        ("X-Frame-Options", "SAMEORIGIN"),
        ("Content-Security-Policy", "frame-ancestors 'self'"),
        ("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")]
    assert "includeSubDomains" not in text and "preload" not in text
    for dup in ("X-Content-Type-Options", "Referrer-Policy", "Access-Control-Allow-Origin"):
        assert dup.lower() not in text.lower(), dup   # Pages already sends the first two; never the third
    assert rules["https://:project.pages.dev/*"] == [("X-Robots-Tag", "noindex")]
    assert rules["https://:version.:project.pages.dev/*"] == [("X-Robots-Tag", "noindex")]


def test_headers_problem_limits():
    assert B.headers_problem("/*\n  X: y\n") is None
    assert "101 rules" in B.headers_problem("".join(f"/p{i}\n  X: y\n" for i in range(101)))
    assert "over 2000 characters" in B.headers_problem("/*\n  X: " + "y" * 2001 + "\n")
    assert B.headers_problem("# only a comment\n") == "no rule"


def test_verify_refuses_a_build_without_headers(built_site, tmp_path):
    out = tmp_path / "_site"
    shutil.copytree(built_site["out"], out)
    os.remove(out / "_headers")
    with pytest.raises(B.BuildError, match="_headers missing"):
        B.verify(str(out), B.load_config()[0]["flags"])
    (out / "_headers").write_text("/*\n  X: " + "y" * 2001 + "\n", encoding="utf-8")
    with pytest.raises(B.BuildError, match="_headers: line 2 is over 2000"):
        B.verify(str(out), B.load_config()[0]["flags"])


class _WithHeaders(http.server.SimpleHTTPRequestHandler):
    """Applies the build's /* rule to every answer, as Cloudflare Pages does with docs/_headers."""
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def end_headers(self):
        for k, v in B.SECURITY_HEADERS:
            self.send_header(k, v)
        super().end_headers()

    def log_message(self, *a):
        pass


@pytest.fixture(scope="module")
def headers_host(built_site):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0),
                                          functools.partial(_WithHeaders, directory=str(built_site["out"])))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def _quiet_beacon(ctx):
    ctx.route("https://static.cloudflareinsights.com/**",
              lambda r: r.fulfill(status=200, content_type="text/javascript", body=""))
    return ctx


def test_with_the_headers_the_pay_dialog_still_reads_the_same_origin_frame(browser, headers_host):
    """SAMEORIGIN / frame-ancestors 'self', not DENY / 'none': pay.js frames /before-you-pay/ on the same origin."""
    ctx = _quiet_beacon(browser.new_context(viewport={"width": 1280, "height": 844}))
    pg = ctx.new_page()
    errors = []
    pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    pg.on("pageerror", lambda e: errors.append(str(e)))
    resp = pg.goto(headers_host + "/tools/trade-stats/")
    assert resp.headers.get("x-frame-options") == "SAMEORIGIN"
    assert resp.headers.get("content-security-policy") == "frame-ancestors 'self'"
    pg.wait_for_load_state("networkidle")
    pg.click(".hdr-cta")
    pg.click("#pay-dialog .pay-more > summary")
    pg.wait_for_selector("#pd-before-you-pay dl.byp", timeout=10000)
    rows = pg.eval_on_selector_all("#pd-before-you-pay dl.byp dt", "ds => ds.map(d => d.textContent.trim())")
    assert "Seller" in rows and "Refunds" in rows, rows
    assert errors == [], errors
    ctx.close()


def test_with_the_headers_another_site_cannot_frame_a_page(browser, headers_host):
    ctx = _quiet_beacon(browser.new_context())
    ctx.route("https://evil.example/**", lambda r: r.fulfill(
        status=200, content_type="text/html",
        body=f'<!doctype html><iframe src="{headers_host}/pricing/" width="600" height="400"></iframe>'))
    pg = ctx.new_page()
    pg.goto("https://evil.example/")
    pg.wait_for_timeout(1500)
    child = [f for f in pg.frames if f != pg.main_frame]
    assert len(child) == 1
    assert child[0].url.startswith("chrome-error://"), child[0].url
    ctx.close()


# ================================================================== 2. /favicon.ico
def test_favicon_ico_is_a_three_size_icon():
    from PIL import Image
    fp = os.path.join(DOCS, "favicon.ico")
    im = Image.open(fp)
    assert im.format == "ICO"
    assert set(im.info["sizes"]) == {(16, 16), (32, 32), (48, 48)}
    im.size = (32, 32)
    im.load()
    px = im.convert("RGBA")
    assert px.getpixel((0, 0))[3] == 0   # the rounded corner stays transparent
    edge = px.getpixel((3, 16))          # the tile itself, left of the letters: #1C1A17 (light mode)
    assert edge[3] == 255 and all(abs(a - b) <= 12 for a, b in zip(edge[:3], (0x1C, 0x1A, 0x17))), edge
    centre = px.getpixel((16, 16))
    assert any(all(abs(a - b) <= 12 for a, b in zip(centre[:3], c)) for c in ((0x1C, 0x1A, 0x17), (0xFB, 0xF8, 0xF3))), centre


def test_favicon_in_baseline_build_head_and_check_live(built_site):
    import check_live as C
    paths, _ = B.read_baseline()
    assert "/favicon.ico" in paths
    assert (built_site["out"] / "favicon.ico").read_bytes() == open(os.path.join(DOCS, "favicon.ico"), "rb").read()
    base = _tpl("base.html")
    ico = '<link rel="icon" href="/favicon.ico" sizes="32x32">'
    assert base.count(ico) == 1 and base.index(ico) < base.index('<link rel="icon" href="/assets/favicon.svg"')
    assert ico in _read(built_site, "/")
    assert "/favicon.ico" in C.EXTRA


# ================================================================== 3. age clause
AGE_EN = ("<li id=\"age\"><strong>Age:</strong> only adults can buy the Revenge Trading Report. By paying, you confirm that you "
          "are at least 18, and at least the age of majority where you live if that is higher (19 in some Canadian "
          "provinces and territories).</li>")
AGE_FR = ("<p id=\"majorite\"><strong>Âge :</strong> seules les personnes majeures peuvent acheter le rapport donttrade sur le revenge trading. En "
          "payant, vous confirmez avoir au moins 18 ans et avoir atteint l’âge de la majorité de votre lieu de "
          "résidence s’il est plus élevé (19 ans dans certaines provinces et certains territoires du Canada).</p>")


def test_age_clause_en_fr(built_site):
    terms = _read(built_site, "/terms/")
    traders = terms[terms.index('<h3 id="traders">'):]
    assert AGE_EN in traders and terms.count('id="age"') == 1
    fr = _read(built_site, "/fr/conditions/")
    assert AGE_FR in fr
    assert "TRANSLATOR CHECK (3 Nov, age" in _tpl("pages", "fr", "conditions.html")
    assert f"Version {TERMS_VERSION}." in terms and f"Version du {TERMS_VERSION}" in fr
    cfg = B.read_toml(os.path.join(SITE, "config", "site.toml"), "site.toml")
    assert TERMS_VERSION == cfg["legal"]["terms_date"] and cfg["legal"]["launch_date"] == "2026-10-29"


def test_lint_passes_on_the_build(built_site):
    f = L.flags_of_build(str(built_site["out"]))
    assert L.lint_build(str(built_site["out"]), f["paid"], f["analytics"], pilot=f["pilot"], badges=f["badges"]) == []


# ================================================================== 4. CASL
def test_unsubscribe_lines_en_fr(built_site):
    en = _read(built_site, "/privacy/")
    m = re.search(r'(?s)<li id="unsubscribe">(.*?)</li>', en)
    assert m
    li = m.group(1)
    email = B.read_toml(os.path.join(SITE, "config", "site.toml"), "site.toml")["site"]["contact_email"]
    assert "unsubscribe" in li and f'<a href="mailto:{email}">{email}</a>' in li and "10 business days" in li
    assert "mailing address" in li and "Substack’s own unsubscribe link" in li
    fr = _read(built_site, "/fr/confidentialite/")
    m = re.search(r'(?s)<p id="desabonnement">(.*?)</p>', fr)
    assert m and "désabonner" in m.group(1) and "10 jours ouvrables" in m.group(1)
    assert f'<a href="mailto:{email}">' in m.group(1)
    assert "TRANSLATOR CHECK (3 Nov, CASL)" in _tpl("pages", "fr", "confidentialite.html")
    # outside the paid_report if: in a free build too
    tpl = _tpl("pages", "privacy.html")
    use = tpl[tpl.index('<h2 id="use">'):tpl.index('<h2 id="client-data">')]
    i = use.index('id="unsubscribe"')
    assert use.rindex("{%- endif %}", 0, i) > use.rindex("{%- if flags.paid_report %}", 0, i)


def test_waitlist_form_names_how_to_withdraw_consent():
    """The waitlist form renders only with paid_report = false; a whole free build cannot be made from this tree
    (Tester R2 P10: docs/'s paid pages fail the passthrough chrome, on main too), so the partial is rendered alone."""
    from jinja2 import Environment, FileSystemLoader
    env = Environment(loader=FileSystemLoader(os.path.join(SITE, "templates")), autoescape=True)
    env.filters["usd"] = B.usd
    html = env.get_template("partials/form_waitlist.html").render(
        site={"contact_email": "hello@example.invalid"}, products={"report39": {"price_usd": 39}},
        forms={"endpoint": "https://api.example.invalid/submit", "trader_key": "k", "redirect_trader": "/thanks/"},
        heading_id="wl-h", flags={}, page={"path": "/for-traders/"})
    assert ("You can withdraw this consent at any time: reply “unsubscribe” to any email from us or write to "
            "hello@example.invalid.") in html


# ================================================================== 5. early deletion or a copy
def test_rights_any_time_en_fr(built_site):
    en = _read(built_site, "/privacy/")
    email = B.read_toml(os.path.join(SITE, "config", "site.toml"), "site.toml")["site"]["contact_email"]
    rights = en[en.index('id="rights"'):]
    rights = rights[:rights.index("</details>")]
    assert "You can ask us at any time to see, correct or delete your information" in rights
    assert "you do not have to wait for the deletion dates above" in rights
    assert f'<a href="mailto:{email}">{email}</a>, from the address you paid with if you bought the Revenge Trading Report' in rights
    assert "deleted when that period ends" in rights
    fr = _read(built_site, "/fr/confidentialite/")
    droits = fr[fr.index('id="droits"'):]
    droits = droits[:droits.index("</p>")]
    assert "en tout temps" in droits and "sans attendre les délais de suppression" in droits
    assert f'<a href="mailto:{email}">{email}</a>' in droits and "l’adresse utilisée pour payer" in droits
    assert "TRANSLATOR CHECK (3 Nov, early deletion)" in _tpl("pages", "fr", "confidentialite.html")
    assert f"version {PRIVACY_VERSION}" in en and f"Version du {PRIVACY_VERSION}" in fr


# ================================================================== 6. one button label
def test_button_label_without_a_dash(built_site):
    for path, html in _pages(built_site["out"]):
        assert "Take the test —" not in html and "Take the test &mdash;" not in html, path
    home = _read(built_site, "/")
    header = re.search(r"(?s)<header\b.*?</header>", home).group(0)
    assert header.count("Get the report for US$39") == 2   # the bar + the Menu
    for t in ("partials/header.html", "partials/trader_offer.html", "partials/tool_next_step.html",
              "partials/value_ladder.html", "pages/home.html", "pages/pricing.html"):
        assert "Take the test —" not in _tpl(*t.split("/")), t


# ================================================================== 7. campaign tags (umami-clean.js)
def test_strict_pages_match_lint():
    assert B.UMAMI_STRICT_PATHS == L.UMAMI_STRICT_PATHS == ("/welcome/", "/restore/", "/help/")
    assert B.umami_strict({"path": "/thanks/", "noindex": True})
    assert B.umami_strict({"path": "/help/"}) and not B.umami_strict({"path": "/tools/"})


def test_pinned_tracker_still_has_the_two_settings():
    src = open(TRACKER, encoding="utf-8").read()
    assert '"before-send"' in src and '"exclude-search"' in src


def _payloads(sent):
    return [json.loads(b)["payload"] for b in sent]


def _query(p):
    return urllib.parse.urlsplit(p["url"]).query


SITE_ORIGIN = "https://donttrade.ca"
TAGS = "utm_source=x&utm_medium=social&utm_campaign=launch&utm_content=20261103-a"


def test_tracker_keeps_only_the_four_campaign_tags(browser, built_site):
    sent = []
    ctx = _real_tracker_context(browser, built_site["out"], _ok(sent))
    pg = ctx.new_page()

    def visit(url, wait=True):
        del sent[:]
        pg.goto(SITE_ORIGIN + url)
        if wait:
            pg.wait_for_function("() => !!(window.umami && window.umami.track)")
        pg.wait_for_timeout(700)
        return _payloads(sent)

    # 1. /welcome/: the tracker drops the whole query (data-exclude-search), tags included
    got = visit("/welcome/?session_id=cs_live_SECRET&utm_source=x#t=SECRET")
    assert got and all(p["url"] == SITE_ORIGIN + "/welcome/" for p in got), got
    assert not [b for b in sent if "SECRET" in b or "session_id" in b]
    # 2. an ordinary page: the four tags, lowercased, in their order; nothing else
    got = visit("/?utm_source=X&utm_medium=social&utm_campaign=launch&utm_content=20261103-a&utm_term=zz"
                "&fbclid=SECRET&q=SECRET&session_id=SECRET#SECRET")
    views = [p for p in got if "name" not in p]
    assert len(views) == 1 and _query(views[0]) == TAGS, got
    assert not [b for b in sent if "SECRET" in b or "utm_term" in b or "fbclid" in b or "#" in b]
    # 6. pay-open on the tagged page carries only the four tags
    del sent[:]
    pg.locator("a[data-pay]:visible").first.click()
    pg.wait_for_timeout(500)
    ev = [p for p in _payloads(sent) if p.get("name") == "pay-open"]
    assert len(ev) == 1 and _query(ev[0]) == TAGS, _payloads(sent)
    # 4. from that page to /tools/: the referrer is the path alone
    del sent[:]
    pg.keyboard.press("Escape")
    pg.evaluate("location.href = '/tools/'")
    pg.wait_for_url(SITE_ORIGIN + "/tools/")
    pg.wait_for_function("() => !!(window.umami && window.umami.track)")
    pg.wait_for_timeout(700)
    views = [p for p in _payloads(sent) if "name" not in p]
    assert len(views) == 1 and views[0]["referrer"] == "/" and _query(views[0]) == "", views
    # 3. a value that is not a short lowercase tag (an email address) is dropped
    got = visit("/tools/?utm_source=a%20b%40mail.com")
    assert got and all(_query(p) == "" for p in got) and not [b for b in sent if "mail.com" in b], got
    # 5. /help/?q=: the typed question never leaves
    got = visit("/help/?q=SECRET")
    assert got and all(_query(p) == "" for p in got) and not [b for b in sent if "SECRET" in b], got
    ctx.close()


def test_hook_unit_in_chromium(browser, built_site):
    ctx = _real_tracker_context(browser, built_site["out"], _ok([]))
    pg = ctx.new_page()
    pg.goto(SITE_ORIGIN + "/tools/")
    pg.wait_for_function("() => typeof window.dtUmamiClean === 'function'")
    f = "([t, p]) => window.dtUmamiClean(t, p)"
    assert not pg.evaluate(f, ["identify", {"url": SITE_ORIGIN + "/"}])
    assert not pg.evaluate(f, ["event", None])
    assert not pg.evaluate(f, ["event", {"title": "x"}])            # no url
    assert not pg.evaluate(f, ["performance", {"url": SITE_ORIGIN + "/"}])
    out = pg.evaluate(f, ["event", {"url": SITE_ORIGIN + "/a/?utm_campaign=B&x=1#h", "referrer": "https://t.co/abc?x=1#y",
                                    "title": "T", "name": "pay-open"}])
    assert out == {"url": SITE_ORIGIN + "/a/?utm_campaign=b", "referrer": "https://t.co/abc", "title": "T",
                   "name": "pay-open"}
    out = pg.evaluate(f, ["event", {"url": SITE_ORIGIN + "/?utm_source=" + "a" * 65, "referrer": "/x/?q=1"}])
    assert out == {"url": SITE_ORIGIN + "/", "referrer": "/x/"}
    assert pg.evaluate(f, ["event", {"url": SITE_ORIGIN + "/", "referrer": ""}]) == {"url": SITE_ORIGIN + "/", "referrer": ""}
    ctx.close()


def test_without_the_hook_the_strict_pages_still_send_no_secret(browser, built_site):
    """Defense in depth: umami-clean.js answering 404 (a content blocker, say): /welcome/ keeps data-exclude-search,
    so its session id still never leaves."""
    sent = []
    ctx = _real_tracker_context(browser, built_site["out"], _ok(sent))
    ctx.route("https://donttrade.ca/static/js/umami-clean.js*", lambda r: r.fulfill(status=404, body=""))
    pg = ctx.new_page()
    pg.goto(SITE_ORIGIN + "/welcome/?session_id=cs_live_SECRET&utm_source=x#t=SECRET")
    pg.wait_for_function("() => !!(window.umami && window.umami.track)")
    pg.wait_for_timeout(800)
    assert pg.evaluate("typeof window.dtUmamiClean") == "undefined"
    assert sent and not [b for b in sent if "SECRET" in b or "session_id" in b], sent
    ctx.close()


def test_privacy_names_the_campaign_tags(built_site):
    en = _read(built_site, "/privacy/")
    fr = _read(built_site, "/fr/confidentialite/")
    assert ("It records the page address (without anything after “#”, and of what follows “?” only the campaign tags "
            "utm_source, utm_medium, utm_campaign and utm_content, which say which of our posts or emails a link came "
            "from), the page title") in en
    assert "without anything after “?” or “#”" not in en
    assert ("Il enregistre l’adresse de la page (sans ce qui suit « # », et de ce qui suit « ? » seulement les étiquettes "
            "de campagne utm_source, utm_medium, utm_campaign et utm_content") in fr
    assert "sans ce qui suit « ? » ou « # »" not in fr
    assert "TRANSLATOR CHECK (3 Nov, campaign tags)" in _tpl("pages", "fr", "confidentialite.html")


# ================================================================== A. the footer, per page
def test_footer_never_names_umami_where_it_does_not_run(built_site):
    umami_line = "Visits are counted with Cloudflare Web Analytics and Umami Cloud"
    seen = {"umami": 0, "no_umami": 0, "no_analytics": 0}
    for path, html in _pages(built_site["out"]):
        if "<footer" not in html:
            continue
        foot = html[html.index("<footer"):]
        runs = "cloud.umami.is/script.js" in html
        beacon = "static.cloudflareinsights.com/beacon.min.js" in html
        if runs:
            assert umami_line in foot, path
            seen["umami"] += 1
        else:
            assert umami_line not in foot and "Visits to this page are counted with Cloudflare Web Analytics and" \
                not in foot, path
            if beacon:
                assert "Visits to this page are counted with Cloudflare Web Analytics" in foot, path
                assert "Umami Cloud, which counts visits to other pages, does not run on this page." in foot, path
                seen["no_umami"] += 1
            else:
                assert "Visits to this page are not counted" in foot, path
                seen["no_analytics"] += 1
    assert seen["umami"] > 40 and seen["no_umami"] >= 1 and seen["no_analytics"] >= 1, seen
    assert "does not run on this page" in _read(built_site, "/report/")
    assert "Visits to this page are not counted" in _read(built_site, "/before-you-pay/")


def test_footer_privacy_cases():
    on = {"analytics": True, "paid_report": False, "pilot_checkout": False}
    assert "Umami" not in B.footer_privacy(on, False, {"path": "/report/", "no_umami": True})
    assert "Umami" not in B.footer_privacy(on, False, {"path": "/x/"})
    assert "Visits to this page are not counted; other pages are counted with Cloudflare Web Analytics, which sets no " \
           "cookie." in B.footer_privacy(on, False, {"path": "/before-you-pay/", "no_analytics": True})
    off = {**on, "analytics": False}
    assert B.footer_privacy(off, True, {"no_analytics": True}) == B.footer_privacy(off)   # "runs no analytics"
    assert B.footer_privacy(on, True) == B.footer_privacy(on, True, {"path": "/"})


# ================================================================== B. Threads
def test_threads_on_threads_com(built_site):
    for path, html in _pages(built_site["out"]):
        assert "threads.net" not in html, path
    home = _read(built_site, "/")
    assert '<a href="https://www.threads.com/@donttradestudy" rel="me noopener">' in home
    assert "www.threads.com" in B.CHANNEL_HOSTS and "www.threads.net" not in B.CHANNEL_HOSTS
    ld = re.search(r'<script type="application/ld\+json">(.*?)</script>', home).group(1)
    assert "https://www.threads.com/@donttradestudy" in ld


# ================================================================== C. no event property attribute
def test_lint_flags_a_planted_event_property(built_site, tmp_path):
    """Tester R2 I1: the mutation they ran (data-umami-event-rows on the readiness Run button) now fails lint, on a
    template page and on a lifted page's frozen body."""
    out = tmp_path / "_site"
    shutil.copytree(built_site["out"], out)
    f = L.flags_of_build(str(out))

    def lint():
        return [p for p in L.lint_build(str(out), f["paid"], f["analytics"], pilot=f["pilot"], badges=f["badges"])
                if p[0] == "flag:umami"]
    assert lint() == []
    fp = out / "tools" / "prop-challenge-simulator" / "index.html"
    clean = fp.read_text(encoding="utf-8")
    planted = clean.replace('data-umami-event="tool-run-readiness">Run the check',
                            'data-umami-event="tool-run-readiness" data-umami-event-rows="FILEDATA">Run the check')
    assert planted != clean
    fp.write_text(planted, encoding="utf-8")
    assert any("data-umami-event-rows" in d for _, _, d in lint()), lint()
    fp.write_text(clean, encoding="utf-8")
    assert lint() == []
    about = out / "about" / "index.html"
    clean = about.read_text(encoding="utf-8")
    about.write_text(clean.replace("<!--frozen:end-->", '<span data-umami-event-x="1"></span><!--frozen:end-->', 1),
                     encoding="utf-8")
    assert any(w == "/about/index.html" and "data-umami-event-*" in d for _, w, d in lint()), lint()
    about.write_text(clean, encoding="utf-8")


# ================================================================== D. the paid-product sentence
def test_paid_product_sentence_is_true_for_firms_too(built_site):
    for path in ("/about/", "/independence/"):
        html = _read(built_site, path)
        assert "the one paid product" not in html, path
        assert "the only paid product is <a href=\"/pricing/#traders\">the Revenge Trading Report</a>" in html, path
        assert re.search(r"[Ff]or traders,? the only paid product", html), path
    assert not os.path.exists(os.path.join(SITE, "templates", "pages", "fr", "a-propos.html"))
    assert not [n for n in os.listdir(os.path.join(SITE, "templates", "pages", "fr"))
                if "propos" in n or "independ" in n]   # no French twins to keep in step
