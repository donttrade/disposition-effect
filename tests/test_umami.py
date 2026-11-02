"""Umami Cloud (2 Nov, owner decision: visitor funnels on the free Hobby plan) beside Cloudflare Web Analytics.

[analytics] umami_website_id switches it on (with [flags] analytics). The script loads on exactly the pages that
get the Cloudflare beacon (never /before-you-pay/ or the journal), with Do Not Track respected and the address
reduced to its path; the CSP gains cloud.umami.is (script) and gateway.umami.is (connect) only then. Funnel events:
data-umami-event on the Stripe links and the free tools' run buttons; pay-open (pay.js) and report-run (report.js)
by umami.track, because a buy link with the attribute would be followed by Umami's click handler instead of
opening the dialog, and /report/ runs on choosing the file (no Run button). The trader Stripe link carries
?client_reference_id=<page slug>. /privacy/ and /fr/confidentialite/ name Umami Cloud.
"""
import html as _h
import os
import re
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SITE = os.path.join(REPO, "site")
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, SITE)
import build as B  # noqa: E402
import lint as L  # noqa: E402

UMAMI_ID = "16c5fa53-e8fc-4c55-892a-5546e7d51830"
SCRIPT_TAG = re.compile(r'<script\b[^>]*src="https://cloud\.umami\.is/script\.js"[^>]*></script>')
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
        if beacon:
            with_beacon += 1
            assert len(tags) == 1, path
            t = tags[0]
            for a in (f'data-website-id="{UMAMI_ID}"', 'data-do-not-track="true"', 'data-exclude-search="true"',
                      'data-exclude-hash="true"', "defer"):
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
    assert with_beacon > 40 and without >= 1


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
    assert re.search(r'<a class="btn" href="https://buy\.stripe\.com/[^"]+" rel="noopener" data-umami-event="pay-continue">'
                     r'Continue to secure payment</a>', dialog)
    # a buy link must not carry the attribute: Umami's capture-phase handler would cancel pay.js and follow the link
    for path, html in _pages(out):
        for a in re.findall(r"<a\b[^>]*\bdata-pay\b[^>]*>", html):
            assert "data-umami-event" not in a, path
    pricing = read("/pricing/")
    assert pricing.count('data-umami-event="pay-continue"') >= 2   # the page's own pay step + the dialog
    assert 'data-umami-event="pay-continue">Continuer' in read("/fr/avant-de-payer/")
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
    assert names == {"pay-continue", "tool-run-readiness", "tool-run-importer", "tool-run-drawdown",
                     "tool-run-lot-size", "tool-run-risk-reward"}
    assert all(re.fullmatch(r"[a-z]+(-[a-z]+)*", n) for n in names)


def test_tracked_events_in_js():
    pay = open(os.path.join(SITE, "static", "js", "pay.js"), encoding="utf-8").read()
    rep = open(os.path.join(SITE, "static", "js", "paid", "report.js"), encoding="utf-8").read()
    assert pay.count("window.umami.track('pay-open')") == 1
    assert rep.count("window.umami.track('report-run')") == 1
    # a fixed name only: no second argument (no event data) anywhere
    for src in (pay, rep):
        assert not re.search(r"umami\.track\([^)]*,", src)


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
    assert "It never receives your file or anything in it." in en
    assert '<a href="https://umami.is/privacy">Umami’s privacy policy</a>' in en
    assert "Umami Cloud compte aussi les pages vues" in fr
    assert '<a href="https://umami.is/privacy">politique de confidentialité d’Umami</a>' in fr
    tpl = open(os.path.join(SITE, "templates", "pages", "fr", "confidentialite.html"), encoding="utf-8").read()
    assert "TRANSLATOR CHECK (2 Nov, Umami Cloud)" in tpl
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
    assert part.index("{%- if umami_on %}") < part.index("cloud.umami.is/script.js")


def test_bad_website_id_fails(tmp_path):
    r, _ = _build(tmp_path, _sub(r'^umami_website_id = ".*"$', 'umami_website_id = "not-a-uuid"'))
    assert r.returncode != 0
    assert "umami_website_id" in (r.stdout + r.stderr)


# ------------------------------------------------------------------ lint
TAG = ('<script defer src="https://cloud.umami.is/script.js" data-website-id="x" data-do-not-track="true" '
       'data-exclude-search="true" data-exclude-hash="true"></script>')
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
