"""Umami Cloud (2 Nov, owner decision: visitor funnels on the free Hobby plan) beside Cloudflare Web Analytics.

[analytics] umami_website_id switches it on (with [flags] analytics). The script loads on exactly the pages that
get the Cloudflare beacon (never /before-you-pay/ or the journal), with Do Not Track respected and the address
reduced to its path; the CSP gains cloud.umami.is (script) and gateway.umami.is (connect) only then. Funnel events:
data-umami-event on the free tools' run buttons only (buttons that neither navigate nor submit anywhere);
pay-open and pay-continue by umami.track in pay.js, because on a link Umami's own click handler cancels the click
and follows it only once its gateway request settles (a slow gateway would hold up the buy link or the payment).
Never on /report/ (owner rule, 2 Nov: the page that reads the buyer's file). data-domains="donttrade.ca": local,
test and preview copies count nothing. The trader Stripe link carries ?client_reference_id=<page slug>.
/privacy/ and /fr/confidentialite/ name Umami Cloud.

No test loads the live script or reaches gateway.umami.is: conftest's browser answers both with stand-ins, and the
tests of what the tracker really sends use the pinned copy tests/fixtures/umami-script.js, with the built site
served at https://donttrade.ca/ by a Playwright route.
"""
import html as _h
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, SITE)
import build as B  # noqa: E402
import lint as L  # noqa: E402

UMAMI_ID = "16c5fa53-e8fc-4c55-892a-5546e7d51830"
SCRIPT_TAG = re.compile(r'<script\b[^>]*src="https://cloud\.umami\.is/script\.js"[^>]*></script>')
NO_UMAMI = {"/report/index.html"}   # beacon, but never Umami (owner rule 2 Nov)
EVENTS = {"pay-open", "pay-continue", "tool-run-readiness", "tool-run-importer", "tool-run-drawdown",
          "tool-run-lot-size", "tool-run-risk-reward"}
ATTR_EVENTS = EVENTS - {"pay-open", "pay-continue"}
TRACKER = os.path.join(REPO, "tests", "fixtures", "umami-script.js")
CSP_RE = re.compile(r'http-equiv="Content-Security-Policy" content="([^"]+)"')


def _pages(out):
    for d, _, files in os.walk(out):
        for f in files:
            if f.endswith(".html"):
                p = os.path.join(d, f)
                yield "/" + os.path.relpath(p, out).replace(os.sep, "/"), open(p, encoding="utf-8").read()


def _csp(html):
    m = CSP_RE.search(html)
    return _h.unescape(m.group(1)) if m else ""


def _build(tmp_path, edit):
    src = open(os.path.join(SITE, "config", "site.toml"), encoding="utf-8").read()
    src = edit(src)
    (tmp_path / "site.toml").write_text(src, encoding="utf-8")
    out = tmp_path / "_site"
    env = {**os.environ, "DT_OUT": str(out), "DT_SITE_TOML": str(tmp_path / "site.toml")}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(SITE, "build.py")], env=env, capture_output=True, text=True)
    return r, out


def _sub(pattern, repl):
    def edit(src):
        new, n = re.subn(pattern, repl, src, count=1, flags=re.M)
        assert n == 1, pattern
        return new
    return edit


# ------------------------------------------------------------------ the default build (Umami on)
def test_setting_is_on_in_site_toml():
    cfg = B.read_toml(os.path.join(SITE, "config", "site.toml"), "site.toml")
    assert cfg["analytics"]["umami_website_id"] == UMAMI_ID
    assert B.umami_on(cfg)


def test_umami_exactly_where_the_beacon_is(built_site):
    with_beacon = without = 0
    for path, html in _pages(built_site["out"]):
        beacon = "static.cloudflareinsights.com/beacon.min.js" in html
        tags = SCRIPT_TAG.findall(html)
        csp = _csp(html)
        if beacon and path not in NO_UMAMI:
            with_beacon += 1
            assert len(tags) == 1, path
            t = tags[0]
            for a in (f'data-website-id="{UMAMI_ID}"', 'data-do-not-track="true"', 'data-exclude-search="true"',
                      'data-exclude-hash="true"', 'data-domains="donttrade.ca"', "defer"):
                assert a in t, (path, a)
            for a in ("data-errors", "data-performance", "data-host-url", "data-umami-event-"):
                assert a not in t, (path, a)
            if csp:
                script = re.search(r"script-src ([^;]+)", csp).group(1).split()
                connect = re.search(r"connect-src ([^;]+)", csp).group(1).split()
                assert "https://cloud.umami.is" in script, path
                assert "https://gateway.umami.is" in connect, path
                assert "'none'" not in connect, path   # CSP3: never 'none' beside a host
        else:
            without += 1
            assert not tags, path
            assert "umami.is" not in csp, path
    assert with_beacon > 40 and without >= 2


def test_report_page_has_the_beacon_but_no_umami(built_site):
    """Owner rule (2 Nov): the paid report page, which reads the buyer's file, runs no third-party analytics
    beyond the Cloudflare beacon it already had: no Umami script, no Umami host in its CSP."""
    html = open(B.out_file(str(built_site["out"]), "/report/"), encoding="utf-8").read()
    assert "static.cloudflareinsights.com/beacon.min.js" in html
    assert "cloud.umami.is" not in html and "gateway.umami.is" not in html and "umami.is" not in _csp(html)
    rep = open(os.path.join(SITE, "static", "js", "paid", "report.js"), encoding="utf-8").read()
    assert "umami" not in rep   # no report-run


@pytest.mark.parametrize("path", ["/before-you-pay/"])
def test_analytics_free_pages_have_no_umami(built_site, path):
    html = open(B.out_file(str(built_site["out"]), path), encoding="utf-8").read()
    assert "cloud.umami.is" not in html and "gateway.umami.is" not in html
    assert "cloudflareinsights" not in html
    assert B.journal_problem(html.replace("</head>", '<script src="https://cloud.umami.is/script.js"></script></head>'),
                             path) is not None


def test_journal_guard_refuses_umami():
    planted = ('<meta http-equiv="Content-Security-Policy" content="connect-src \'none\'; form-action \'none\';">'
               '<script defer src="https://cloud.umami.is/script.js"></script>')
    assert "loads analytics" in (B.journal_problem(planted, "/journal/") or "")


def test_event_attributes(built_site):
    out = str(built_site["out"])
    read = lambda p: open(B.out_file(out, p), encoding="utf-8").read()  # noqa: E731
    home = read("/")
    dialog = re.search(r'(?s)<dialog class="pay-dialog".*?</dialog>', home).group(0)
    assert re.search(r'<a class="btn" href="https://buy\.stripe\.com/[^"]+" rel="noopener" data-pay-continue>'
                     r'Continue to secure payment</a>', dialog)
    # no link carries the attribute: Umami's capture-phase handler cancels a link's click and follows it only once
    # its gateway request settles. Only <button>s (which navigate nowhere) do.
    for path, html in _pages(out):
        for tag in re.findall(r"<(\w+)\b[^>]*\bdata-umami-event=", html):
            assert tag == "button", (path, tag)
        for a in re.findall(r'<a\b[^>]*href="https://buy\.stripe\.com/[^"]*"[^>]*>', html):
            assert "data-pay-continue" in a, (path, a)   # every Stripe link counts pay-continue through pay.js
    pricing = read("/pricing/")
    assert pricing.count("data-pay-continue") >= 2   # the page's own pay step + the dialog
    assert "data-pay-continue>Continuer" in read("/fr/avant-de-payer/")
    ps = read("/tools/prop-challenge-simulator/")
    assert re.search(r'id="ps-run" type="submit" data-umami-event="tool-run-readiness"', ps)
    assert re.search(r'id="ps-stale-run" type="button" data-umami-event="tool-run-readiness"', ps)
    assert re.search(r'id="ps-paste-btn" type="button" data-umami-event="tool-run-importer"', ps)
    for path, name in [("/tools/drawdown-calculator/", "drawdown"), ("/tools/lot-size-calculator/", "lot-size"),
                       ("/tools/risk-reward-calculator/", "risk-reward")]:
        assert f'type="submit" data-umami-event="tool-run-{name}">Calculate</button>' in read(path), path
    names = set()
    for _, html in _pages(out):
        names.update(re.findall(r'data-umami-event="([^"]+)"', html))
    assert names == ATTR_EVENTS
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", n) for n in names)


def test_tracked_events_in_js():
    pay = open(os.path.join(SITE, "static", "js", "pay.js"), encoding="utf-8").read()
    rep = open(os.path.join(SITE, "static", "js", "paid", "report.js"), encoding="utf-8").read()
    assert pay.count("window.umami.track('pay-open')") == 1
    assert pay.count("window.umami.track('pay-continue')") == 1
    assert "umami" not in rep
    # a fixed name only: no second argument (no event data) anywhere
    assert not re.search(r"umami\.track\([^)]*,", pay)
    js = os.path.join(SITE, "static", "js")
    for d, _, files in os.walk(js):
        for f in files:
            src = open(os.path.join(d, f), encoding="utf-8", errors="ignore").read()
            if os.path.join(d, f) != os.path.join(js, "pay.js"):
                assert "umami" not in src, f


def test_pay_ref_slug():
    assert B.pay_ref("/") == "home"
    assert B.pay_ref("/tools/trade-stats/") == "tools-trade-stats"
    assert B.pay_ref("/fr/avant-de-payer/") == "fr-avant-de-payer"
    assert B.pay_ref("/a b/é/") == "a-b--"
    assert len(B.pay_ref("/" + "x" * 300 + "/")) == 200
    assert B.with_client_ref(None, "/") is None
    assert B.with_client_ref("https://buy.stripe.com/abc", "/pricing/") == \
        "https://buy.stripe.com/abc?client_reference_id=pricing"
    assert B.with_client_ref("https://buy.stripe.com/abc?locale=fr", "/x/") == \
        "https://buy.stripe.com/abc?locale=fr&client_reference_id=x"


def test_every_stripe_link_names_its_page(built_site):
    import json
    prices = json.load(open(os.path.join(SITE, "config", "prices.json"), encoding="utf-8"))
    link = next(p for p in prices["products"] if p["id"] == "report39")["stripe_link_live"]
    seen = 0
    for path, html in _pages(built_site["out"]):
        page = path[:-len("index.html")] if path.endswith("/index.html") else path
        for href in re.findall(r'href="(https://buy\.stripe\.com/[^"]+)"', html):
            href = _h.unescape(href)
            if not href.startswith(link):
                continue
            seen += 1
            m = re.fullmatch(re.escape(link) + r"\?(?:locale=fr&)?client_reference_id=([A-Za-z0-9_-]{1,200})", href)
            assert m, (path, href)
            assert m.group(1) == B.pay_ref(page), (path, href)
    assert seen > 40


# ------------------------------------------------------------------ privacy
def test_privacy_names_umami(built_site):
    out = str(built_site["out"])
    en = open(B.out_file(out, "/privacy/"), encoding="utf-8").read()
    fr = open(B.out_file(out, "/fr/confidentialite/"), encoding="utf-8").read()
    assert "Page views and some button clicks are also counted with Umami Cloud, which sets no cookie" in en
    assert "the page title, the site you came from" in en
    assert ("From your IP address it works out an approximate location (country, region and city). Its analytics "
            "records hold that location, not the IP address, though Umami’s own security and operations logs may "
            "record the address.") in en
    assert "It never receives your file or anything in it, and it does not run on /report/" in en
    assert "il déduit un emplacement approximatif (pays, région et ville)" in fr and "le titre de la page" in fr
    assert "il ne fonctionne pas sur /report/" in fr
    assert '<a href="https://umami.is/privacy">Umami’s privacy policy</a>' in en
    assert "Umami Cloud compte aussi les pages vues" in fr
    assert '<a href="https://umami.is/privacy">politique de confidentialité d’Umami</a>' in fr
    tpl = open(os.path.join(SITE, "templates", "pages", "fr", "confidentialite.html"), encoding="utf-8").read()
    assert "TRANSLATOR CHECK (2 Nov, Umami Cloud" in tpl
    # the privacy version moves to [legal] privacy_date; the terms version does not
    assert "version 2026-11-02" in en and "Version du 2026-11-02" in fr
    terms = open(B.out_file(out, "/terms/"), encoding="utf-8").read()
    assert "2026-11-02" not in terms
    footer = B.footer_privacy({"analytics": True, "paid_report": True, "pilot_checkout": False}, True)
    want = "Visits are counted with Cloudflare Web Analytics and Umami Cloud, which also counts some button clicks; neither sets a cookie."
    assert want in footer
    assert want in en   # every page's footer


def test_privacy_date_rules():
    legal = {"privacy_version": "2026-10-29"}
    import datetime as dt
    assert B.set_privacy_date(dict(legal), "t") is None   # optional
    lg = {**legal, "privacy_date": "2026-11-02"}
    B.set_privacy_date(lg, "t", today=dt.date(2026, 11, 2))
    assert lg["privacy_version"] == "2026-11-02"
    lg = {"privacy_version": "2026-12-01", "privacy_date": "2026-11-02"}
    B.set_privacy_date(lg, "t", today=dt.date(2026, 12, 1))
    assert lg["privacy_version"] == "2026-12-01"   # the later one wins
    with pytest.raises(B.BuildError):
        B.set_privacy_date({**legal, "privacy_date": "2099-01-01"}, "t")
    with pytest.raises(B.BuildError):
        B.set_privacy_date({**legal, "privacy_date": "2 Nov"}, "t")


# ------------------------------------------------------------------ the setting off, analytics off, bad id
def test_umami_off_when_the_setting_is_empty(tmp_path):
    r, out = _build(tmp_path, _sub(r'^umami_website_id = ".*"$', 'umami_website_id = ""'))
    assert r.returncode == 0, r.stderr
    beacon = 0
    for path, html in _pages(out):
        assert "cloud.umami.is" not in html and "gateway.umami.is" not in html, path
        assert "Umami" not in html, path   # privacy and footer wording too
        beacon += "cloudflareinsights" in html
    assert beacon > 40   # Cloudflare stays as it was


def _cfg(analytics, uid):
    return {"flags": {"analytics": analytics}, "analytics": {"cf_beacon_token": "t", "umami_website_id": uid},
            "worker": {"api_base": "https://api.example"}}


@pytest.mark.parametrize("analytics,uid,want", [(True, UMAMI_ID, True), (True, "", False), (False, UMAMI_ID, False)])
def test_csp_hosts_only_when_umami_is_on(analytics, uid, want):
    """A whole analytics = false build fails today on the Readiness Check's count pages in docs/ (passthrough),
    so the off cases are checked on the CSP builder and the base template's guard."""
    cfg = _cfg(analytics, uid)
    assert B.umami_on(cfg) is want
    for page in ({"path": "/tools/"}, {"path": "/report/", "connect_worker": True},
                 {"path": "/tools/disposition-calculator/"}):
        csp = B.csp_for(page, cfg)
        assert ("https://cloud.umami.is" in csp) is want, (page, csp)
        assert ("https://gateway.umami.is" in csp) is want, (page, csp)
        assert ("cloudflareinsights" in csp) is analytics, (page, csp)
    assert "umami" not in B.csp_for({"path": "/before-you-pay/", "no_analytics": True}, cfg)
    base = open(os.path.join(SITE, "templates", "base.html"), encoding="utf-8").read()
    assert '{%- if flags.analytics and not page.get("no_analytics") %}{% include "partials/analytics.html" %}' in base
    part = open(os.path.join(SITE, "templates", "partials", "analytics.html"), encoding="utf-8").read()
    assert part.index('{%- if umami_on and not page.get("no_umami") %}') < part.index("cloud.umami.is/script.js")


def test_bad_website_id_fails(tmp_path):
    r, _ = _build(tmp_path, _sub(r'^umami_website_id = ".*"$', 'umami_website_id = "not-a-uuid"'))
    assert r.returncode != 0
    assert "umami_website_id" in (r.stdout + r.stderr)


# ------------------------------------------------------------------ lint
TAG = ('<script defer src="https://cloud.umami.is/script.js" data-website-id="x" data-do-not-track="true" '
       'data-exclude-search="true" data-exclude-hash="true" data-domains="donttrade.ca"></script>')
BEACON = '<script defer src="https://static.cloudflareinsights.com/beacon.min.js"></script>'


def _rules(html, analytics=True):
    return [w for r, _, w in L.umami_problems(html, "/x/", analytics)]


def test_lint_umami_rules():
    assert _rules(BEACON + TAG) == []
    assert _rules(TAG) == ["Umami Cloud script on a page without the Cloudflare beacon"]
    assert "Umami Cloud script with analytics = false" in _rules(BEACON + TAG, analytics=False)
    assert "Umami Cloud script without data-do-not-track=\"true\"" in _rules(BEACON + TAG.replace(' data-do-not-track="true"', ""))
    assert "Umami Cloud script without data-exclude-search=\"true\"" in _rules(BEACON + TAG.replace(' data-exclude-search="true"', ""))
    assert "Umami Cloud script with data-errors" in _rules(BEACON + TAG.replace("<script ", '<script data-errors="true" '))
    assert "Umami Cloud script 2 times" in _rules(BEACON + TAG + TAG)
    assert "Umami Cloud script without data-domains=\"donttrade.ca\"" in _rules(BEACON + TAG.replace(' data-domains="donttrade.ca"', ""))


# ------------------------------------------------------------------ in Chromium: pay-open, without the network
def test_buy_link_opens_the_dialog_and_counts_pay_open(browser, built_site):
    """Umami's script is answered locally by a stand-in that records track() calls."""
    ctx = browser.new_context()
    ctx.route("https://static.cloudflareinsights.com/**",
              lambda r: r.fulfill(status=200, content_type="text/javascript", body=""))
    ctx.route("https://cloud.umami.is/**", lambda r: r.fulfill(
        status=200, content_type="text/javascript",
        body="window.umami={track:function(n,d){(window.__ev=window.__ev||[]).push([n,d===undefined])}};"))
    ctx.route("https://gateway.umami.is/**", lambda r: r.abort())
    page = ctx.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
    page.goto(built_site["url"] + "/tools/")
    page.wait_for_function("() => !!(window.umami && window.umami.track)")
    page.locator("a[data-pay]:visible").first.click()
    assert page.locator("#pay-dialog").evaluate("d => d.open")
    assert page.evaluate("window.__ev") == [["pay-open", True]]
    assert page.url.endswith("/tools/")
    assert not [e for e in errors if "Content Security Policy" in e], errors
    ctx.close()


# ------------------------------------------------------------------ the real tracker (pinned copy), offline
TYPES = {".html": "text/html", ".js": "text/javascript", ".css": "text/css", ".json": "application/json",
         ".svg": "image/svg+xml", ".png": "image/png", ".woff2": "font/woff2", ".xml": "application/xml",
         ".txt": "text/plain", ".csv": "text/csv", ".ico": "image/x-icon", ".webmanifest": "application/manifest+json"}
SITE_KEYS = {"website", "screen", "language", "hostname", "url", "title", "referrer", "name"}


def _real_tracker_context(browser, out, gateway):
    """A context where https://donttrade.ca/ is the built site (so data-domains lets the tracker count),
    cloud.umami.is is the pinned tracker, gateway.umami.is is `gateway`, and nothing else leaves the machine."""
    ctx = browser.new_context()
    ctx.route("**/*", lambda r: r.abort())   # everything not routed below: no network at all

    def site(r):
        u = urllib.parse.urlsplit(r.request.url)
        fp = os.path.join(str(out), u.path.lstrip("/"))
        if os.path.isdir(fp):
            fp = os.path.join(fp, "index.html")
        if not os.path.isfile(fp):
            return r.fulfill(status=404, body="")
        r.fulfill(status=200, body=open(fp, "rb").read(),
                  content_type=TYPES.get(os.path.splitext(fp)[1], "application/octet-stream"))
    ctx.route("https://donttrade.ca/**", site)
    ctx.route("https://static.cloudflareinsights.com/**",
              lambda r: r.fulfill(status=200, content_type="text/javascript", body=""))
    ctx.route("https://cloud.umami.is/**", lambda r: r.fulfill(
        status=200, content_type="text/javascript", body=open(TRACKER, encoding="utf-8").read()))
    ctx.route("https://gateway.umami.is/**", gateway)
    return ctx


def _ok(sent):
    def handler(r):
        sent.append(r.request.post_data or "")
        r.fulfill(status=200, content_type="application/json", body="{}")
    return handler


def test_umami_sends_only_the_path_title_referrer_and_event_name(browser, built_site):
    """What the real tracker posts, from the stubbed /api/send: no file content, no query string or hash, and in
    each payload only the page address (path), title, referrer and event name (with an empty data object for an
    attribute event), beside the tracker's own fixed
    fields (website ID, hostname, screen size, language). Never anything on /report/."""
    sent = []
    ctx = _real_tracker_context(browser, built_site["out"], _ok(sent))
    ctx.route("https://buy.stripe.com/**", lambda r: r.fulfill(status=200, content_type="text/html", body="<p>s</p>"))
    pg = ctx.new_page()
    base = "https://donttrade.ca"
    pg.goto(base + "/welcome/?session_id=cs_live_SECRETSESSION#t=SECRETTOKEN")
    pg.wait_for_timeout(800)
    pg.goto(base + "/tools/trade-stats/")
    marker = "ZQSECRETFILEMARKER"
    pg.set_input_files("#ts-file", files=[{"name": f"{marker}.csv", "mimeType": "text/csv", "buffer": (
        "symbol,side,open_time,close_time,qty,open_price,close_price,profit\n"
        f"{marker},buy,2026-01-02 10:00,2026-01-02 11:00,1,100,101,1\n").encode()}])
    pg.wait_for_timeout(800)
    pg.goto(base + "/tools/drawdown-calculator/")
    pg.locator('button[data-umami-event="tool-run-drawdown"]').click()
    pg.wait_for_timeout(800)
    pg.goto(base + "/report/#t=SECRETTOKEN")
    pg.wait_for_timeout(800)
    pg.goto(base + "/")
    pg.wait_for_function("() => !!(window.umami && window.umami.track)")
    pg.locator("a[data-pay]:visible").first.click()
    pg.wait_for_timeout(500)
    pg.locator("#pay-dialog a[data-pay-continue]").click()
    pg.wait_for_url("https://buy.stripe.com/**")
    pg.wait_for_timeout(500)
    ctx.close()

    assert sent
    names, paths = set(), set()
    for body in sent:
        for leak in ("SECRET", marker, "session_id", "?", "#"):
            assert leak not in body, (leak, body)
        msg = json.loads(body)
        assert set(msg) == {"type", "payload"} and msg["type"] == "event", body
        p = msg["payload"]
        assert set(p) - {"data"} <= SITE_KEYS and p.get("data", {}) == {}, body   # an attribute event: data {}
        assert p["hostname"] == "donttrade.ca"
        u = urllib.parse.urlsplit(p["url"])
        assert (u.scheme, u.netloc, u.query, u.fragment) == ("https", "donttrade.ca", "", ""), body
        assert p["referrer"] == "" or p["referrer"].startswith("/"), body   # same-site: a path, never a query
        if "name" in p:
            assert p["name"] in EVENTS, body
            names.add(p["name"])
        else:
            paths.add(u.path)
    assert {"pay-open", "pay-continue", "tool-run-drawdown"} <= names
    assert {"/welcome/", "/tools/trade-stats/", "/"} <= paths
    assert "/report/" not in paths and not any("/report/" in b for b in sent)


def test_a_slow_gateway_never_delays_the_stripe_click(browser, built_site):
    """B1: gateway.umami.is answering only after 8 s does not hold up "Continue to secure payment" (< 1 s)."""
    pending = []
    ctx = _real_tracker_context(browser, built_site["out"], lambda r: pending.append((time.monotonic(), r)))
    stripe = []

    def buy(r):
        stripe.append(time.monotonic())
        r.fulfill(status=200, content_type="text/html", body="<p>stripe</p>")
    ctx.route("https://buy.stripe.com/**", buy)
    pg = ctx.new_page()
    pg.goto("https://donttrade.ca/")
    pg.wait_for_function("() => !!(window.umami && window.umami.track)")
    pg.locator("a[data-pay]:visible").first.click()
    assert pg.locator("#pay-dialog").evaluate("d => d.open")
    t0 = time.monotonic()
    pg.locator("#pay-dialog a[data-pay-continue]").click(no_wait_after=True)
    pg.wait_for_url("https://buy.stripe.com/**", timeout=5000)
    assert stripe and stripe[0] - t0 < 1.0, stripe[0] - t0
    assert pg.url.startswith("https://buy.stripe.com/") and "client_reference_id=home" in pg.url
    sent = [json.loads(r.request.post_data)["payload"].get("name") for _, r in pending]
    assert "pay-continue" in sent and "pay-open" in sent, sent   # counted, still waiting on the gateway
    pg.wait_for_timeout(max(0, 8000 - int(1000 * (time.monotonic() - pending[0][0]))))
    for _, r in pending:   # the gateway answers, 8 s late
        try:
            r.fulfill(status=200, content_type="application/json", body="{}")
        except Exception:
            pass   # the page that sent it has gone
    ctx.close()


def test_off_donttrade_ca_the_tracker_counts_nothing(browser, built_site):
    """data-domains="donttrade.ca": a local copy (127.0.0.1) with the real tracker sends no request at all."""
    sent = []
    ctx = browser.new_context()
    ctx.route("https://static.cloudflareinsights.com/**",
              lambda r: r.fulfill(status=200, content_type="text/javascript", body=""))
    ctx.route("https://cloud.umami.is/**", lambda r: r.fulfill(
        status=200, content_type="text/javascript", body=open(TRACKER, encoding="utf-8").read()))
    ctx.route("https://gateway.umami.is/**", _ok(sent))
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/tools/drawdown-calculator/")
    pg.wait_for_function("() => !!(window.umami && window.umami.track)")
    pg.locator('button[data-umami-event="tool-run-drawdown"]').click()
    pg.wait_for_timeout(800)
    ctx.close()
    assert sent == []
