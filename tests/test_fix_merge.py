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
