"""Regression tests for the v2-merge pages fix round (TESTER-REPORT-v2-merge-pages-2026-10-21
and the engine Tester's F-D6). One block per finding; repros copied from /home/claude/tester-merge/.
"""
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import lint as L  # noqa: E402
import build as B  # noqa: E402


# ------------------------------------------------------------------ F-D6: no restore by email
@pytest.mark.parametrize("text", [
    'Lost it? Restore by email with the address you paid with.',   # the F-D6 wording
    "Restore access via e-mail.",
    "Restore-by-email: type the email you paid with.",
    "We email you a restore link.",
    "To restore, enter the email address you paid with.",
])
def test_restore_by_email_wording_fails_lint(text):
    assert any(r == "claim:restore_email" for r, _, _ in L.lint_text(text))
    assert any(r == "claim:restore_email" for r, _, _ in L.passthrough_rules(f"<main><p>{text}</p></main>", "/x/", False))


@pytest.mark.parametrize("text", [
    "Save the link or the file now: there is no account, and restore by email is not offered.",
    "Open the restore link or restore file you saved after paying.",
])
def test_restore_link_wording_passes_lint(text):
    assert not [r for r in L.lint_text(text) if r[0] == "claim:restore_email"]


def test_paid_scripts_are_checked_for_restore_email_strings():
    paid = os.path.join(REPO, "site", "static", "js", "paid")
    for name in sorted(os.listdir(paid)):
        code = open(os.path.join(paid, name), encoding="utf-8").read()
        assert L.restore_email_claims(L.js_strings(code), name) == [], name
    planted = "// Restore-by-email is not in v1\nmsg('Lost it? Restore by email with the address you paid with.');"
    assert L.restore_email_claims(L.js_strings(planted), "x.js")


def test_welcome_template_offers_only_the_link():
    html = open(os.path.join(REPO, "site", "templates", "pages", "welcome.html"), encoding="utf-8").read()
    assert not L.restore_email_claims(L.visible_text(html), "welcome.html")
    assert "address you paid with" not in html


# ------------------------------------------------------------------ owner's first name not in tracked files
def test_owner_first_name_not_in_tracked_files():
    name = "".join(map(chr, (82, 101, 105, 110, 101)))  # built at run time so this file does not hold it
    r = subprocess.run(["git", "grep", "-n", "-I", "-w", name], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 1, r.stdout  # 1 = no match


# ------------------------------------------------------------------ B1: no "Tally" anywhere; one footer privacy line
def test_b1_no_tally_word_anywhere(built_site):
    # repro: grep -l "Forms open on Tally" -r <build>
    for p in built_site["out"].rglob("*"):
        if p.suffix in (".html", ".js", ".xml", ".txt", ".json"):
            assert not re.search(r"(?i)\btally\b", p.read_text(encoding="utf-8", errors="replace")), p


def test_b1_footer_privacy_line_names_web3forms_on_every_page(built_site):
    line = B.footer_privacy({"analytics": False, "paid_report": False, "pilot_checkout": False})
    assert "Web3Forms" in line and "Tally" not in line
    pages = [p for p in built_site["out"].rglob("*.html") if "<footer" in p.read_text(encoding="utf-8")]
    assert len(pages) >= 35
    for p in pages:
        assert line in p.read_text(encoding="utf-8"), p


def test_b1_lint_catches_the_word_tally(built_site, tmp_path):
    from test_legal import build
    r, out = build(tmp_path, "t")
    assert r.returncode == 0 and L.lint_build(str(out)) == []
    page = out / "glossary" / "index.html"  # passthrough
    page.write_text(page.read_text(encoding="utf-8").replace("</main>", "<p>Forms open on Tally.</p></main>"), encoding="utf-8")
    tpl = out / "privacy" / "index.html"    # template page
    tpl.write_text(tpl.read_text(encoding="utf-8").replace("</main>", "<p>Our forms (tally) …</p></main>"), encoding="utf-8")
    hits = {where for rule, where, _ in L.lint_build(str(out)) if rule == "tally"}
    assert hits == {"/glossary/index.html", "/privacy/"}


def test_b1_passthrough_chrome_mismatch_fails_the_build(tmp_path, monkeypatch):
    monkeypatch.setattr(B, "PASSTHROUGH_CHROME", B.PASSTHROUGH_CHROME + [("no such footer text", "x", 1)])
    monkeypatch.setenv("DT_OUT", str(tmp_path / "o"))
    with pytest.raises(B.BuildError, match="passthrough chrome"):
        B.build()


# ------------------------------------------------------------------ B2: placeholder detection, either commerce flag
B2_PLACEHOLDERS = [
    "[SELLER - lawyer to confirm]", "[Seller — lawyer to confirm]", "SELLER — lawyer to confirm",   # failmodes.sh
    "TBD", "TODO", "XXX", "tbc", "xxxx", "Lorem ipsum", "example seller", "PLACEHOLDER", "{seller}", "<name>",
    "Seller - see lawyer", "Name: John", "pending", "lawyer to confirm", "  ", "​", "---",
]


@pytest.mark.parametrize("value", B2_PLACEHOLDERS)
def test_b2_placeholder_values_are_detected(value):
    assert B.placeholder_reason(value) or not value.strip("​ ")


@pytest.mark.parametrize("value", ["Fixture Seller Zqx Holdings", "PO Box 0000, Fixturetown ON A0A 0A0",
                                   "Suite 4 (rear), 12 Fixture Road", "+1 555 0100"])
def test_b2_real_looking_values_pass(value):
    assert B.placeholder_reason(value) is None


def _priv(tmp, **vals):
    base = {"seller_legal_name": "Fixture Seller Zqx Holdings", "premises_address": "PO Box 0000, Fixturetown ON A0A 0A0",
            "phone": "+1 555 0100", **vals}
    p = tmp / "p.toml"
    p.write_text("".join(f'{k} = "{v}"\n' for k, v in base.items()), encoding="utf-8")
    return str(p)


@pytest.mark.parametrize("flags", [dict(pilot_checkout=True), dict(paid_report=True, trader_first_home=True)],
                         ids=["pilot_checkout", "paid_report"])
@pytest.mark.parametrize("field,value", [("seller_legal_name", "[SELLER - lawyer to confirm]"),
                                         ("seller_legal_name", "SELLER — lawyer to confirm"),
                                         ("premises_address", "TBD"), ("phone", "XXX"), ("phone", "555")])
def test_b2_commerce_build_fails_on_placeholder(tmp_path, flags, field, value):
    # repro: failmodes.sh "pilot: …" lines — these built with rc=0 before the fix
    from test_legal import build, toml_with
    r, _ = build(tmp_path, "o", DT_SITE_TOML=toml_with(tmp_path, **flags), DT_PRIVATE_TOML=_priv(tmp_path, **{field: value}))
    assert r.returncode == 1 and "BUILD FAILED" in r.stderr and field in r.stderr, r.stderr


def test_b2_malformed_private_toml_is_a_build_failure_not_a_traceback(tmp_path):
    from test_legal import build, toml_with
    bad = tmp_path / "bad.toml"
    bad.write_text('seller_legal_name = "unterminated\n', encoding="utf-8")
    r, _ = build(tmp_path, "o", DT_SITE_TOML=toml_with(tmp_path, pilot_checkout=True), DT_PRIVATE_TOML=str(bad))
    assert r.returncode == 1 and "BUILD FAILED" in r.stderr and "Traceback" not in r.stderr, r.stderr


# ------------------------------------------------------------------ D9: flags are real booleans
def _flag_toml(tmp, line_re, repl):
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    src, n = re.subn(line_re, repl, src, flags=re.M)
    assert n == 1
    p = tmp / "flags.toml"
    p.write_text(src, encoding="utf-8")
    return str(p)


@pytest.mark.parametrize("flag,value", [("pilot_checkout", '"false"'), ("pilot_checkout", '"yes"'), ("paid_report", '"false"'),
                                        ("analytics", "0"), ("trader_first_home", '"true"'), ("pilot_checkout", "1")])
def test_d9_flag_that_is_not_a_boolean_fails(tmp_path, flag, value):
    # repro: sed 's/^pilot_checkout = false/pilot_checkout = "false"/' site.toml — read as ON before the fix,
    # even with a complete private.toml present
    from test_legal import build
    toml = _flag_toml(tmp_path, rf"^{flag} = (true|false)", f"{flag} = {value}")
    r, out = build(tmp_path, "o", DT_SITE_TOML=toml, DT_PRIVATE_TOML=_priv(tmp_path))
    assert r.returncode == 1 and f"[flags] {flag}" in r.stderr and "boolean" in r.stderr, r.stderr
    assert not (out / "start" / "pilot-thanks").exists()


def test_d9_unknown_flag_fails(tmp_path):
    from test_legal import build
    toml = _flag_toml(tmp_path, r"^analytics = false", "analytics = false\npaid_reprot = true")
    r, _ = build(tmp_path, "o", DT_SITE_TOML=toml)
    assert r.returncode == 1 and "paid_reprot is not a known flag" in r.stderr, r.stderr


# ------------------------------------------------------------------ D8: api_base is a public https origin
D8_BAD = ["https://", "https://[::1]:8787", "https://0.0.0.0", "https://192.168.0.10", "https://10.1.2.3:443",
          "https://api.example.com; script-src *", "https://api.example.com/path?q", "https://api.donttrade.ca/",
          "https://api.donttrade.ca 'unsafe-inline'", 'https://api.donttrade.ca"', "https://localhost:8787",
          "https://api.localhost", "https://x.local", "https://api.test-fake.example", "https://api.example.com",
          "HTTPS://api.donttrade.ca", "https://API.donttrade.ca", "https://api.donttrade.ca:99999", " https://api.donttrade.ca",
          "http://api.donttrade.ca", "https://api.donttrade.ca\n"]


@pytest.mark.parametrize("api", D8_BAD)
def test_d8_bad_api_base_is_refused(api):
    assert B.api_base_problem(api)


@pytest.mark.parametrize("api", ["https://api.donttrade.ca", "https://dt-api.workers.dev", "https://api.donttrade.ca:8443"])
def test_d8_public_https_origin_is_accepted(api):
    assert B.api_base_problem(api) is None


@pytest.mark.parametrize("api,env", [("https://api.example.com; script-src *", {}),
                                     ("https://192.168.0.10", {"DT_ALLOW_LOCAL_API": "1"}),
                                     ("https://", {"DT_ALLOW_PLACEHOLDERS": "1"}),
                                     ("http://127.0.0.1:8787", {"DT_ALLOW_PLACEHOLDERS": "1"})])
def test_d8_paid_build_fails_and_writes_nothing_into_csp(tmp_path, api, env):
    # repro: failmodes.out — these passed the api check; the CSP got "…; script-src * 'unsafe-inline'"
    from test_legal import build, toml_with
    toml = toml_with(tmp_path, paid_report=True, trader_first_home=True)
    src = re.sub(r'(?m)^api_base = "[^"]*"', 'api_base = ' + __import__("json").dumps(api), open(toml).read())
    open(toml, "w").write(src)
    r, out = build(tmp_path, "o", DT_SITE_TOML=toml, DT_PRIVATE_TOML=_priv(tmp_path), **env)
    assert r.returncode == 1 and "api_base" in r.stderr, r.stderr
    assert not (out / "report").exists()


# ------------------------------------------------------------------ D10: escapes split; a well-formed paid build needs none
def test_d10_well_formed_paid_build_needs_no_escape(tmp_path):
    from test_legal import FAKE_API, FAKE_TEST_LINK, paid_env
    out = tmp_path / "o"
    env = {k: v for k, v in os.environ.items() if not k.startswith("DT_")}  # no escape from the caller's shell
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")],
                       env={**env, **paid_env(tmp_path), "DT_OUT": str(out)}, capture_output=True, text=True)
    assert r.returncode == 0 and "WARNING" not in r.stderr, r.stderr
    pricing = (out / "pricing" / "index.html").read_text(encoding="utf-8")
    assert FAKE_TEST_LINK in pricing and "Payment link not set yet" not in pricing
    assert f'content="{FAKE_API}"' in (out / "report" / "index.html").read_text(encoding="utf-8")


@pytest.mark.parametrize("escape,still_fails_on", [
    ("DT_ALLOW_PLACEHOLDERS", "api_base"),        # placeholders allowed, the local api is not
    ("DT_ALLOW_LOCAL_API", "placeholder"),        # the local api allowed, placeholders are not
    ("DT_ALLOW_NO_STRIPE_LINK", "placeholder"),
])
def test_d10_each_escape_opens_one_guard_only(tmp_path, escape, still_fails_on):
    # repro: before the fix DT_ALLOW_PLACEHOLDERS=1 also allowed http://127.0.0.1 and the missing Stripe link
    from test_legal import build, toml_with
    toml = toml_with(tmp_path, paid_report=True, trader_first_home=True)  # committed api_base: http://127.0.0.1:8787
    priv = os.path.join(REPO, "site", "config", "private.example.toml")   # placeholders
    r, _ = build(tmp_path, "o", DT_SITE_TOML=toml, DT_PRIVATE_TOML=priv, **{escape: "1"})
    assert r.returncode == 1 and still_fails_on in r.stderr, r.stderr


def test_d10_missing_link_needs_its_own_escape(tmp_path):
    from test_legal import FAKE_API, build, private_with, toml_with
    toml = toml_with(tmp_path, api=FAKE_API, paid_report=True, trader_first_home=True)
    r, _ = build(tmp_path, "o", DT_SITE_TOML=toml, DT_PRIVATE_TOML=private_with(tmp_path), DT_ALLOW_PLACEHOLDERS="1",
                 DT_ALLOW_LOCAL_API="1")
    assert r.returncode == 1 and "stripe_link_test" in r.stderr
    r, out = build(tmp_path, "p", DT_SITE_TOML=toml, DT_PRIVATE_TOML=private_with(tmp_path), DT_ALLOW_NO_STRIPE_LINK="1")
    assert r.returncode == 0 and "WARNING: DT_ALLOW_NO_STRIPE_LINK=1" in r.stderr, r.stderr


@pytest.mark.parametrize("link", ["https://buy.stripe.com/eVq6oGgLl1d04hmfMqdwc00",   # a live link in test mode
                                  "http://buy.stripe.com/test_abcdefgh", "https://buy.stripe.com.evil.ca/test_abcdefgh",
                                  "https://buy.stripe.com/test_abc def", "javascript:alert(1)"])
def test_d10_malformed_test_link_fails(tmp_path, link):
    from test_legal import build, paid_env, prices_with_test_link
    env = paid_env(tmp_path)
    env["DT_PRICES_JSON"] = prices_with_test_link(tmp_path, link)
    r, _ = build(tmp_path, "o", **env)
    assert r.returncode == 1 and "Payment Link" in r.stderr, r.stderr


def test_d10_escapes_refused_in_live_mode(tmp_path):
    from test_legal import build, paid_env
    env = paid_env(tmp_path)
    src = open(env["DT_SITE_TOML"], encoding="utf-8").read().replace('mode = "test"', 'mode = "live"')
    open(env["DT_SITE_TOML"], "w", encoding="utf-8").write(src)
    r, _ = build(tmp_path, "o", **env, DT_ALLOW_PLACEHOLDERS="1")
    assert r.returncode == 1 and "live" in r.stderr, r.stderr


# ------------------------------------------------------------------ D1: the partner form's product is fixed (+ NIT 8, 9)
def _post(browser, url, form):
    from urllib.parse import parse_qs
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    posted = []
    pg.route("https://api.web3forms.com/**", lambda route: (posted.append(route.request.post_data or ""),
                                                             route.fulfill(status=200, body="ok")))
    pg.goto(url)
    pg.fill(form + " input[type=email]", "test-ignore@example.org")
    pg.fill(form + " input[name=firm]", "TEST - ignore")
    pg.click(form + " button[type=submit]")
    pg.wait_for_timeout(400)
    ctx.close()
    assert len(posted) == 1
    return {k: v[0] for k, v in parse_qs(posted[0], keep_blank_values=True).items()}


@pytest.mark.parametrize("path,form", [("/for-platforms/?product=memo#apply", "#fp"),
                                       ("/start/?product=copy-leader#platform", "#sp"),
                                       ("/start/?product=platform#platform", "#sp")])
def test_d1_partner_form_ignores_product_in_url(browser, built_site, path, form):
    # repro: forms_test.py — /for-platforms/?product=memo sent product=memo before the fix
    body = _post(browser, built_site["url"] + path, form)
    assert body["product"] == "platform" and body["subject"] == "donttrade: partner application"


def test_d1_firm_form_still_takes_product_but_not_platform(browser, built_site):
    assert _post(browser, built_site["url"] + "/start/?product=memo#firm", "#sf")["product"] == "memo"
    assert _post(browser, built_site["url"] + "/start/?product=platform#firm", "#sf")["product"] == "pilot"


def test_nit8_partner_mailto_subject(built_site):
    html = (built_site["out"] / "for-platforms" / "index.html").read_text(encoding="utf-8")
    assert "subject=Partner%20application" in html and "Pilot request" not in html


def test_nit9_general_enquiry_form_is_not_tagged_snapshot(tmp_path):
    from test_legal import build, private_with, toml_with
    r, out = build(tmp_path, "p", DT_SITE_TOML=toml_with(tmp_path, pilot_checkout=True), DT_PRIVATE_TOML=private_with(tmp_path))
    assert r.returncode == 0, r.stderr
    for page, fid in (("start", "sf"), ("for-firms", "ff")):
        html = (out / page / "index.html").read_text(encoding="utf-8")
        form = html[html.index(f'id="{fid}"'):]
        form = form[:form.index("</form>")]
        assert 'name="product" value="enquiry"' in form, page


# ------------------------------------------------------------------ D2: seller block only with paid_report (one switch)
def _pilot_build(tmp_path, name, switch=None):
    from test_legal import build, private_with, toml_with
    toml = toml_with(tmp_path, f"{name}.toml", pilot_checkout=True)
    if switch is not None:
        src = open(toml, encoding="utf-8").read()
        src, n = re.subn(r"(?m)^show_seller_for_pilot = false", f"show_seller_for_pilot = {switch}", src)
        assert n == 1
        open(toml, "w", encoding="utf-8").write(src)
    return build(tmp_path, name, DT_SITE_TOML=toml, DT_PRIVATE_TOML=private_with(tmp_path))


def test_d2_pilot_only_build_shows_no_seller_identity(tmp_path):
    # repro: grep -l "Test Seller ZZQX" -r b-pilot → privacy, terms, start/pilot-thanks before the fix
    from test_legal import FAKE
    r, out = _pilot_build(tmp_path, "p")
    assert r.returncode == 0, r.stderr
    for p in out.rglob("*.html"):
        h = p.read_text(encoding="utf-8")
        assert "data-seller-block" not in h, p
        for v in FAKE.values():
            assert v not in h, (p, v)
    assert L.lint_build(str(out), pilot=True) == []


def test_d2_switch_is_one_line_and_shows_the_seller(tmp_path):
    from test_legal import FAKE
    r, out = _pilot_build(tmp_path, "s", switch="true")
    assert r.returncode == 0, r.stderr
    for page in ("start/pilot-thanks", "terms", "privacy"):
        h = (out / page / "index.html").read_text(encoding="utf-8")
        assert FAKE["seller_legal_name"] in h and "data-seller-block" in h, page


def test_d2_switch_must_be_a_boolean(tmp_path):
    r, _ = _pilot_build(tmp_path, "b", switch='"no"')
    assert r.returncode == 1 and "show_seller_for_pilot" in r.stderr


def test_d2_planted_seller_block_in_pilot_only_build_fails_verify(tmp_path):
    r, out = _pilot_build(tmp_path, "v")
    assert r.returncode == 0
    (out / "about" / "index.html").write_text("<dl><dt data-seller-block>Seller</dt></dl>")
    with pytest.raises(B.BuildError, match="seller disclosure"):
        B.verify(str(out), {"paid_report": False, "pilot_checkout": True, "analytics": False}, seller=False)


# ------------------------------------------------------------------ D5: the trader-first home (paid_report) is complete
FINDING_RE = re.compile(r"76\.1|4,659|more readily than|1\.61|1\.78|none survived|None passed|0 of 32", re.I)  # adjacency.py


@pytest.fixture(scope="module")
def paid_site(tmp_path_factory):
    import functools
    import http.server
    import threading
    from conftest import _Quiet
    from test_legal import build, paid_env
    tmp = tmp_path_factory.mktemp("merge-paid")
    r, out = build(tmp, "on", **paid_env(tmp))
    assert r.returncode == 0, r.stderr
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


def test_d5_paid_home_has_the_founding_offer(paid_site):
    text = L.visible_text((paid_site["out"] / "index.html").read_text(encoding="utf-8"))
    assert "See where your trades leave your plan." in text
    assert "$39 founding price for the first 100 buyers." in text
    assert "One time, in US dollars, with one free re-test 30 to 60 days later." in text
    assert "Get the habit report — $39" in text and "What the report measures" in text and "How it works" in text
    assert not FINDING_RE.search(text)  # no study finding anywhere on the page, so none next to an offer


def test_d5_paid_home_prices_come_from_prices_json(tmp_path):
    import json
    from test_legal import build, paid_env
    env = paid_env(tmp_path)
    d = json.load(open(env["DT_PRICES_JSON"], encoding="utf-8"))
    next(p for p in d["products"] if p["id"] == "report39")["price_usd"] = 41
    d["rules"]["founding_limit"], d["rules"]["trader_refund_days"] = 77, 21
    open(env["DT_PRICES_JSON"], "w", encoding="utf-8").write(json.dumps(d))
    r, out = build(tmp_path, "o", **env)
    assert r.returncode == 0, r.stderr
    text = L.visible_text((out / "index.html").read_text(encoding="utf-8"))
    assert "$41 founding price for the first 77 buyers." in text and "within 21 days of buying" in text
    assert "$39" not in text


@pytest.mark.parametrize("width", [375, 1280])
@pytest.mark.parametrize("color", ["light", "dark"])
def test_d5_paid_home_axe_and_overflow(browser, paid_site, width, color):
    from a11y import axe_violations, horizontal_overflow
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=color, bypass_csp=True)  # axe is injected
    page = ctx.new_page()
    page.goto(paid_site["url"] + "/")
    assert horizontal_overflow(page) == [] and axe_violations(page) == []
    ctx.close()


# ------------------------------------------------------------------ D4: footers tell the truth about storage, per flag
def test_d4_paid_footers_describe_the_token_and_stripped_numbers(paid_site):
    # repro: grep -c "stores only your light/dark choice" b-paid/about/index.html → 1 before the fix
    flags = {"paid_report": True, "pilot_checkout": False, "analytics": False}
    line = B.footer_privacy(flags)
    assert "access key" in line and "stripped trade numbers" in line and "does not keep" in line
    pages = [p for p in paid_site["out"].rglob("*.html") if "<footer" in p.read_text(encoding="utf-8")]
    assert len(pages) >= 40
    for p in pages:
        h = p.read_text(encoding="utf-8")
        assert "stores only your light/dark choice" not in h, p
        assert line in h, p


def test_d4_analytics_build_footers_drop_no_analytics(tmp_path):
    from test_legal import build, toml_with
    toml = toml_with(tmp_path, analytics=True)
    src = open(toml, encoding="utf-8").read().replace('cf_beacon_token = ""', 'cf_beacon_token = "fixture0token"')
    open(toml, "w", encoding="utf-8").write(src)
    r, out = build(tmp_path, "a", DT_SITE_TOML=toml)
    assert r.returncode == 0, r.stderr
    for p in out.rglob("*.html"):
        h = p.read_text(encoding="utf-8")
        if "<footer" in h:
            assert "runs no analytics" not in L.visible_text(h[h.index("<footer"):]), p


# ------------------------------------------------------------------ D6: reciprocal hreflang + visible language links
PAIRS = [("/pricing/", "/fr/avant-de-payer/"), ("/terms/", "/fr/conditions/"), ("/privacy/", "/fr/confidentialite/")]


def _alts(out, path):
    return dict(B.ALT_RE.findall((out / path.strip("/") / "index.html").read_text(encoding="utf-8")))


@pytest.mark.parametrize("en,fr", PAIRS)
def test_d6_pairs_are_reciprocal_with_visible_links(paid_site, en, fr):
    # repro: sc-both.json — /pricing/ had hreflang=[] while /fr/avant-de-payer/ pointed en at it
    base = "https://donttrade.ca"
    out = paid_site["out"]
    assert _alts(out, en) == {"en": base + en, "fr": base + fr, "x-default": base + en}
    assert _alts(out, fr) == {"fr": base + fr, "en": base + en, "x-default": base + en}
    en_html = (out / en.strip("/") / "index.html").read_text(encoding="utf-8")
    fr_html = (out / fr.strip("/") / "index.html").read_text(encoding="utf-8")
    assert re.search(rf'<a href="{re.escape(fr)}"[^>]*hreflang="fr"', en_html)
    assert re.search(rf'<a href="{re.escape(en)}[#"][^>]*hreflang="en"', fr_html)


def test_d6_flag_off_pages_declare_no_alternates(built_site):
    for en, _ in PAIRS:
        assert _alts(built_site["out"], en) == {}


def test_d6_one_sided_pair_fails_the_build_check(paid_site, tmp_path):
    import shutil
    out = tmp_path / "copy"
    shutil.copytree(paid_site["out"], out)
    p = out / "pricing" / "index.html"
    p.write_text(re.sub(r'<link rel="alternate"[^>]*>\n?', "", p.read_text(encoding="utf-8")), encoding="utf-8")
    with pytest.raises(B.BuildError, match="hreflang"):
        B.check_language_pairs(str(out), "https://donttrade.ca")


# ------------------------------------------------------------------ D3: Trial → Pilot labels on the passthrough pages
def test_d3_no_trial_call_to_action_anywhere(built_site):
    # repro: words.py — 98 "trial" hits on the 20 passthrough pages, "Firms: start a trial" in the header
    for p in built_site["out"].rglob("*.html"):
        t = L.visible_text(p.read_text(encoding="utf-8")).lower()
        for w in ("start a trial", "firms: trial", "start a trial on every page"):
            assert w not in t, (p, w)


def test_d3_pilot_labels_keep_urls_and_anchors(built_site):
    pt = B.passthrough_pages({os.path.relpath(B.out_file("/x", p["path"]), "/x") for p in B.PAGES if not p["requires_flag"]})
    assert len(pt) == 20
    attr = re.compile(r'\s(?:href|id)="([^"]*)"')
    for rel in pt:
        built = (built_site["out"] / rel).read_text(encoding="utf-8")
        docs = open(os.path.join(REPO, "docs", rel), encoding="utf-8").read()
        assert attr.findall(built) == attr.findall(docs), rel  # every href and id, in order, unchanged
        assert built.count("Firms: start a Pilot") == 2 and built.count(">Firms: Pilot<") == 1, rel


def test_d3_lint_catches_trial_cta_on_passthrough(tmp_path):
    from test_legal import build
    r, out = build(tmp_path, "t")
    page = out / "glossary" / "index.html"
    page.write_text(page.read_text(encoding="utf-8").replace("</main>", "<p><a href='/start/'>Start a trial</a></p></main>"),
                    encoding="utf-8")
    assert any(rule == "banned:trial_cta" for rule, where, _ in L.lint_build(str(out)) if where == "/glossary/index.html")


# ------------------------------------------------------------------ D7: a 100k-row file never freezes the page
GAP_PROBE = ("() => { window.__gaps = []; let last = performance.now(); window.__raf = true;"
             " const tick = (t) => { if (t - last > 200) window.__gaps.push(Math.round(t - last)); last = t;"
             " if (window.__raf) requestAnimationFrame(tick); }; requestAnimationFrame(tick); }")  # tools_test.py


def rows_file(path, trades):
    """The Tester's garbage/rows100k.csv shape: generic CSV, one buy and one sell per trade."""
    import datetime as dt
    import random
    rnd = random.Random(20261021)
    t0 = dt.datetime(2020, 1, 2, 9, 30)
    lines = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    for i in range(trades):
        a, b = t0 + dt.timedelta(minutes=10 * i), t0 + dt.timedelta(minutes=10 * i + 5)  # never overlapping
        px = round(100 + rnd.uniform(-5, 5), 2)
        out = round(px + rnd.uniform(-2, 2), 2)
        sym = "DEMO-" + "ABC"[i % 3]
        lines.append(f"{a:%Y-%m-%d},{a:%H:%M:%S},{sym},Buy,10,{px},USD,1.00")
        lines.append(f"{b:%Y-%m-%d},{b:%H:%M:%S},{sym},Sell,10,{out},USD,1.00")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return str(path)


@pytest.mark.parametrize("tool,inp,done", [
    ("/tools/trade-stats/", "#ts-file", "() => !!document.querySelector('#ts-noise table') || !document.getElementById('ts-error').hidden"),
    ("/tools/prop-challenge-simulator/", "#ps-file", "() => /closed trades? on|error code/.test(document.getElementById('ps-file-status').textContent)"),
])
def test_d7_100k_rows_keep_the_main_thread_free(browser, built_site, tmp_path, tool, inp, done):
    f = rows_file(tmp_path / "rows100k.csv", 50_000)
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(built_site["url"] + tool)
    page.evaluate(GAP_PROBE)
    page.set_input_files(inp, f)
    page.wait_for_timeout(250)
    progress = page.evaluate("() => { const e = document.querySelector('.progress-line'); return !!e && !e.hidden && !!e.querySelector('progress'); }")
    page.wait_for_function(done, timeout=240000)
    page.evaluate("() => { window.__raf = false; }")
    gaps = page.evaluate("() => window.__gaps")
    text = page.inner_text("main")
    ctx.close()
    assert errors == []
    assert progress, "no progress shown while the file was read"
    assert gaps == [], f"main thread blocked: {gaps} ms"   # before the fix: 3050 ms
    n = int(re.search(r"([\d,]+) closed trades", text).group(1).replace(",", ""))
    assert n == 50_000, n


def test_d7_200001_rows_refused_without_freezing(browser, built_site, tmp_path):
    p = tmp_path / "rows200001.csv"
    p.write_text("Date,Time,Symbol,Side,Quantity,Price,Currency,Fees\n" +
                 "".join(f"2025-01-02,09:30:00,DEMO-A,{'Buy' if i % 2 == 0 else 'Sell'},10,100.00,USD,1.00\n" for i in range(200_001)),
                 encoding="utf-8")
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + "/tools/trade-stats/")
    page.evaluate(GAP_PROBE)
    page.set_input_files("#ts-file", str(p))
    page.wait_for_selector("#ts-error:not([hidden])", timeout=60000)
    gaps = page.evaluate("() => window.__gaps")
    text = page.inner_text("#ts-error")
    ctx.close()
    assert "E_TOO_LARGE" in text and gaps == [], gaps   # before the fix: 1867 ms


def test_d7_html_report_still_read_on_the_page(browser, built_site):
    # DOMParser does not exist in a worker, so an MT5 HTML report is parsed on the page
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + "/tools/trade-stats/")
    page.set_input_files("#ts-file", os.path.join(REPO, "tests", "fixtures", "mt5", "deals_netting_40.htm"))
    page.wait_for_selector("#ts-noise table", timeout=90000)
    assert "MetaTrader 5 report" in page.inner_text("#ts-out")
    ctx.close()


def test_d7_prop_sim_run_waits_for_a_file_still_being_read(browser, built_site, tmp_path):
    f = rows_file(tmp_path / "rows20k.csv", 20_000)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + "/tools/prop-challenge-simulator/")
    page.set_input_files("#ps-file", f)
    for sel, v in (("#ps-target", "100"), ("#ps-maxloss", "100"), ("#ps-days", "10")):
        page.fill(sel, v)
    page.click("#ps-run")  # before the read has finished
    page.wait_for_selector("#ps-out:not([hidden])", timeout=180000)
    assert page.is_hidden("#ps-errors")
    ctx.close()


# ------------------------------------------------------------------ NIT 4: singular in the prop-sim file status
def test_nit4_one_trade_one_day_reads_singular(browser, built_site, tmp_path):
    f = rows_file(tmp_path / "one.csv", 1)
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + "/tools/prop-challenge-simulator/")
    page.set_input_files("#ps-file", f)
    page.wait_for_function("() => /closed trades? on/.test(document.getElementById('ps-file-status').textContent)")
    text = page.inner_text("#ps-file-status")
    ctx.close()
    assert "1 closed trade on 1 trading day." in text, text


# ------------------------------------------------------------------ NIT 5: no losses → no "may be noise" streak label
def test_nit5_no_losing_trades_streak_label(browser, built_site):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + "/tools/trade-stats/")
    page.set_input_files("#ts-file", os.path.join(REPO, "tests", "fixtures", "generic", "no_losses.csv"))
    page.wait_for_selector("#ts-noise table", timeout=90000)
    row = page.inner_text('[data-check="longest_losing_streak"]')
    ctx.close()
    assert "no losing trades" in row and "may be noise" not in row, row


# ------------------------------------------------------------------ NIT 6: tiny lot-size results are not shown as 0
def _lots(browser, built_site, fields):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(built_site["url"] + "/tools/lot-size-calculator/")
    for sel, v in fields.items():
        page.fill(sel, v)
    page.click("#ls-form button[type=submit]")
    page.wait_for_selector("#ls-out:not([hidden])")
    out = {k: page.inner_text(f'[data-k="{k}"]') for k in ("lots", "risk_at")}
    out["pct"] = page.inner_text('[data-k="risk_pct"]') if page.locator('[data-k="risk_pct"]').count() else None
    out["tiny"] = page.locator("#ls-tiny").count() == 1
    ctx.close()
    return out


def test_nit6_tiny_risk_is_not_rounded_to_zero(browser, built_site):
    # repro: tools_test.py lot size — risk 0.0000001 showed "0.0000 lots / 0.00" with no notice
    r = _lots(browser, built_site, {"#ls-risk": "0.0000001", "#ls-stop": "40", "#ls-vpp": "1"})
    assert r["lots"] == "under 0.0001 lots" and r["risk_at"] == "under 0.01" and r["tiny"], r
    # risk .5 on a 25,000 balance showed "0.00%"
    r = _lots(browser, built_site, {"#ls-risk": "0.5", "#ls-balance": "25000", "#ls-stop": "40", "#ls-vpp": "1"})
    assert r["pct"] == "under 0.01%", r


# ------------------------------------------------------------------ NIT 7: pricing tabs follow same-page hash changes
def test_nit7_hashchange_switches_the_pricing_tab(browser, paid_site):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(paid_site["url"] + "/pricing/")
    assert page.get_attribute("#tab-traders", "aria-selected") == "true"
    page.evaluate("location.hash = 'firms'")
    page.wait_for_function("() => document.getElementById('tab-firms').getAttribute('aria-selected') === 'true'")
    page.evaluate("location.hash = 'copy-leader'")  # an id inside the Firms panel keeps Firms
    assert page.get_attribute("#tab-firms", "aria-selected") == "true"
    page.go_back()
    page.go_back()
    page.wait_for_function("() => document.getElementById('tab-traders').getAttribute('aria-selected') === 'true'")
    page.evaluate("location.hash = 'traders'")
    assert page.is_visible("#before-you-pay")
    ctx.close()


# ------------------------------------------------------------------ NIT 11: the processor list reads as one list
def test_nit11_privacy_processor_list(built_site, paid_site):
    off = L.visible_text((built_site["out"] / "privacy" / "index.html").read_text(encoding="utf-8"))
    on = L.visible_text((paid_site["out"] / "privacy" / "index.html").read_text(encoding="utf-8"))
    assert "Web3Forms, Google, GitHub, Stripe and Substack are mostly in the United States" in off
    assert "Web3Forms, Google, GitHub, Stripe, Substack and Cloudflare are mostly in the United States" in on


# ------------------------------------------------------------------ NIT 13, 14, 15: paid welcome and Pilot thanks copy
def test_nit13_welcome_does_not_rely_on_the_receipt_link(paid_site):
    js = open(os.path.join(REPO, "site", "static", "js", "paid", "welcome.js"), encoding="utf-8").read()
    assert "use the link in your Stripe receipt" not in js and "email us (address below)" in js
    html = (paid_site["out"] / "welcome" / "index.html").read_text(encoding="utf-8")
    err = html[html.index('id="w-error"'):]
    assert 'href="mailto:donttrade.research@gmail.com?subject=' in err[:err.index("</section>")]


def test_nit14_15_pilot_thanks_links_and_direct_visit_note(tmp_path):
    r, out = _pilot_build(tmp_path, "t")
    assert r.returncode == 0, r.stderr
    h = (out / "start" / "pilot-thanks" / "index.html").read_text(encoding="utf-8")
    assert 'href="/terms/#pilot-card"' in h and 'href="/terms/#trial"' not in h
    assert "Reached this page without sending the Pilot form?" in h and 'href="/start/?product=pilot#firm"' in h


# ------------------------------------------------------------------ NIT 2: lint reads the build's flags
def _lint_cli(*args):
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "lint.py"), *args], capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def test_nit2_lint_infers_flags_from_the_build(built_site, paid_site, tmp_path):
    rc, out = _lint_cli(str(built_site["out"]))
    assert rc == 0 and "paid=off, pilot=off" in out, out
    rc, out = _lint_cli(str(paid_site["out"]))
    assert rc == 0 and "paid=on, pilot=off" in out, out
    r, pilot = _pilot_build(tmp_path, "l")
    rc, out = _lint_cli(str(pilot))  # before: 4 false problems without --pilot
    assert rc == 0 and "pilot=on" in out, out


def test_nit2_wrong_flags_are_one_clear_problem_not_a_traceback(built_site, paid_site):
    rc, out = _lint_cli(str(built_site["out"]), "--paid")  # before: FileNotFoundError on /fr/
    assert rc == 1 and "Traceback" not in out and "--paid given, but the build has no paid pages" in out, out
    rc, out = _lint_cli(str(paid_site["out"]), "--pilot")
    assert rc == 1 and "--paid missing" in out and "--pilot given" in out, out
