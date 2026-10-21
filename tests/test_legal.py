"""Step 17 and the legal-copy fixes of 21 Oct.

- /privacy/ and /terms/: old ids kept, Tally gone, Pilot rename, no standard/regular price.
- Seller disclosure (O. Reg. 17/05 s. 32): rendered ONLY from private.toml, and only while a
  commerce flag (paid_report or pilot_checkout) is on; the build fails loudly when one is on
  and private.toml lacks a field. With both off the output is byte-identical whatever
  private.toml holds. Every value here is an obviously fake fixture.
- French terms/privacy/"Before you pay" exist only with paid_report on, lang="fr", hreflang
  pairs, French lint clean, axe clean.
- No restore-by-email anywhere.
"""
import filecmp
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
from a11y import axe_violations, horizontal_overflow  # noqa: E402

# Obviously fake but well-formed (R4): two words of letters, a PO box in a made-up town with a
# well-formed Ontario postal code, and a 555 area code that is not in service.
FAKE = {"seller_legal_name": "Zzqx Qqvendor Holdings", "premises_address": "PO Box 9917, Zzqxville ON K9Z 9Z9",
        "phone": "+1 555 555 0234"}
SITE_TOML = os.path.join(REPO, "site", "config", "site.toml")
# [legal] launch_date (Manager C3): the terms version and every launch-dated statement; empty = the build date
_LAUNCH = B.set_launch_date(dict(__import__("tomllib").load(open(SITE_TOML, "rb"))["legal"]), SITE_TOML)
TERMS_VERSION = _LAUNCH.isoformat()
LAUNCH_HUMAN = f"{_LAUNCH.day} {B.MONTHS[_LAUNCH.month - 1]} {_LAUNCH.year}"


# Well-formed fake values for a paid build that needs no escape variable (Tester D10).
FAKE_API = "https://api.fixture-zqx.ca"
FAKE_TEST_LINK = "https://buy.stripe.com/test_fixture0000zqx"


def toml_with(tmp, name="site.toml", api=None, **flags):
    src = open(SITE_TOML, encoding="utf-8").read()
    if api is not None:
        src, n = re.subn(r'(?m)^api_base = "[^"]*"', 'api_base = "' + api + '"', src)
        assert n == 1
    for k, v in flags.items():
        src, n = re.subn(rf"(?m)^{k} = (true|false)", f"{k} = {'true' if v else 'false'}", src)
        assert n == 1, k
    p = tmp / name
    p.write_text(src, encoding="utf-8")
    return str(p)


def private_with(tmp, name="private.toml", **over):
    vals = {**FAKE, **over}
    p = tmp / name
    p.write_text("".join(f'{k} = "{v}"\n' for k, v in vals.items() if v is not None), encoding="utf-8")
    return str(p)


def prices_with_test_link(tmp, link=FAKE_TEST_LINK):
    """A copy of prices.json with a report39 test Payment Link (the committed file has none yet)."""
    import json
    d = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
    for p in d["products"]:
        if p["id"] == "report39":
            p["stripe_link_test"] = link
    out = tmp / "prices.json"
    out.write_text(json.dumps(d, indent=2), encoding="utf-8")
    return str(out)


def paid_env(tmp, **flags):
    """Env for a paid build with well-formed fake values and NO escape variable."""
    return {"DT_SITE_TOML": toml_with(tmp, "paid.toml", api=FAKE_API, paid_report=True, trader_first_home=True, **flags),
            "DT_PRIVATE_TOML": private_with(tmp, "paid-private.toml"), "DT_PRICES_JSON": prices_with_test_link(tmp)}


def build(tmp, name, **env):
    out = tmp / name
    e = {**os.environ, "DT_OUT": str(out), **env}
    e.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=e, capture_output=True, text=True)
    return r, out


def same_tree(a, b):
    cmp = filecmp.dircmp(a, b)
    stack = [cmp]
    while stack:
        c = stack.pop()
        if c.left_only or c.right_only or c.diff_files or c.funny_files:
            return False
        # dircmp compares shallowly by stat; compare bytes
        for f in c.same_files:
            if open(os.path.join(c.left, f), "rb").read() != open(os.path.join(c.right, f), "rb").read():
                return False
        stack.extend(c.subdirs.values())
    return True


def all_html(out):
    return {str(p.relative_to(out)): p.read_text(encoding="utf-8", errors="replace") for p in out.rglob("*.html")}


@pytest.fixture(scope="module")
def paid(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("legal-paid")
    r, out = build(tmp, "on", **paid_env(tmp))
    assert r.returncode == 0, r.stderr
    return out


# ------------------------------------------------------------------ flag off
def test_flag_off_is_byte_identical_whatever_private_toml_holds(tmp_path):
    r1, a = build(tmp_path, "a")
    r2, b = build(tmp_path, "b", DT_PRIVATE_TOML=private_with(tmp_path))
    src = open(SITE_TOML, encoding="utf-8").read().replace("pilot_checkout = false", "")
    (tmp_path / "noflag.toml").write_text(src, encoding="utf-8")
    r3, c = build(tmp_path, "c", DT_SITE_TOML=str(tmp_path / "noflag.toml"))
    assert r1.returncode == r2.returncode == r3.returncode == 0
    assert same_tree(str(a), str(b)) and same_tree(str(a), str(c))
    text = "".join(all_html(a).values())
    for v in FAKE.values():
        assert v not in text
    assert "data-seller-block" not in text and not (a / "fr").exists()


def test_flag_off_legal_pages(built_site):
    for path, ids in {"/terms/": ["prices", "payment", "delivery", "trial", "cancellation", "refunds", "traders",
                                  "publication", "not-advice", "liability", "agreement", "law", "contact"],
                      "/privacy/": []}.items():
        html = (built_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")
        for i in ids:
            assert f'id="{i}"' in html, (path, i)
        assert "tally" not in html.lower() and f"Version {TERMS_VERSION}" in html
        assert not re.search(r"standard price|after launch|\$49|\$99|restore by email", html, re.I)
    privacy = (built_site["out"] / "privacy" / "index.html").read_text(encoding="utf-8")
    assert "Web3Forms" in privacy and "pen name" in privacy and "runs no analytics" in privacy
    terms = (built_site["out"] / "terms" / "index.html").read_text(encoding="utf-8")
    assert "waitlist only for now: nothing is sold" in terms and f"Pilot (called “Trial” before {LAUNCH_HUMAN})" in terms


def test_no_tally_anywhere_in_the_build(built_site):
    for rel, html in all_html(built_site["out"]).items():
        assert "tally.so" not in html, rel


def test_seller_block_planted_with_commerce_off_fails(tmp_path):
    r, out = build(tmp_path, "x")
    assert r.returncode == 0
    (out / "about" / "index.html").write_text("<dl><dt data-seller-block>Seller</dt></dl>")
    cfg, _, _ = B.load_config()
    with pytest.raises(B.BuildError, match="seller disclosure"):
        B.verify(str(out), cfg["flags"])


# ------------------------------------------------------------------ commerce flags fail loudly
@pytest.mark.parametrize("flags", [dict(paid_report=True, trader_first_home=True), dict(pilot_checkout=True)],
                         ids=["paid_report", "pilot_checkout"])
@pytest.mark.parametrize("missing", ["seller_legal_name", "premises_address", "phone"])
def test_commerce_flag_needs_every_private_field(tmp_path, flags, missing):
    toml = toml_with(tmp_path, **flags)
    r, _ = build(tmp_path, "m", DT_SITE_TOML=toml, DT_PRIVATE_TOML=private_with(tmp_path, **{missing: None}),
                 DT_ALLOW_PLACEHOLDERS="1")
    assert r.returncode == 1 and missing in r.stderr, r.stderr
    r, _ = build(tmp_path, "e", DT_SITE_TOML=toml, DT_PRIVATE_TOML=private_with(tmp_path, "e.toml", **{missing: " "}),
                 DT_ALLOW_PLACEHOLDERS="1")
    assert r.returncode == 1 and "empty" in r.stderr, r.stderr


def test_commerce_flag_without_private_toml_fails(tmp_path):
    r, _ = build(tmp_path, "n", DT_SITE_TOML=toml_with(tmp_path, pilot_checkout=True),
                 DT_PRIVATE_TOML=str(tmp_path / "does-not-exist.toml"))
    assert r.returncode == 1 and "private.toml" in r.stderr


# ------------------------------------------------------------------ flag on
def test_seller_values_come_from_private_toml(paid):
    html = all_html(paid)
    for rel in ("pricing/index.html", "terms/index.html", "privacy/index.html", "fr/conditions/index.html",
                "fr/confidentialite/index.html", "fr/avant-de-payer/index.html"):
        for v in FAKE.values():
            assert v in html[rel], (rel, v)
    tracked = subprocess.run(["git", "grep", "-l", "-e", FAKE["seller_legal_name"], "--", "site", "checks", "docs"],
                             cwd=REPO, capture_output=True, text=True).stdout
    assert tracked == ""  # the fixture value lives only in this test


def test_flag_on_lint_and_wording(paid, monkeypatch):
    monkeypatch.setenv("DT_PRIVATE_TOML", str(paid.parent / "paid-private.toml"))   # delta N2: the build's file
    assert L.lint_build(str(paid), paid=True) == []
    for rel, h in all_html(paid).items():
        assert not re.search(r"standard price|after launch:|restore by email</a>|\$49|\$99", h, re.I), rel
    restore = (paid / "restore" / "index.html").read_text(encoding="utf-8")
    assert "type=\"email\"" not in restore and "r-form" not in restore
    assert "beta" in (paid / "pricing" / "index.html").read_text(encoding="utf-8")


def test_french_pages(paid):
    pairs = {"fr/conditions/": "/terms/", "fr/confidentialite/": "/privacy/", "fr/avant-de-payer/": "/pricing/"}
    for fr, en in pairs.items():
        h = (paid / fr / "index.html").read_text(encoding="utf-8")
        assert h.startswith('<!doctype html>\n<html lang="fr">')
        assert f'hreflang="en" href="https://donttrade.ca{en}"' in h and f'hreflang="fr" href="https://donttrade.ca/{fr}"' in h
        assert "39,00 $ US" in h or fr != "fr/avant-de-payer/"
        assert "restaurer" not in h  # no French restore-by-email page
        assert not L.lint_text_fr(L.visible_text(L.strip_disclaimers(h)))
    terms = (paid / "terms" / "index.html").read_text(encoding="utf-8")
    assert 'hreflang="fr" href="https://donttrade.ca/fr/conditions/"' in terms
    assert 'id="remboursements"' in (paid / "fr/conditions/index.html").read_text(encoding="utf-8")
    robots = (paid / "robots.txt").read_text()
    assert "Disallow: /fr/" not in robots and "Disallow: /report/" in robots


def test_french_lint_catches_planted_words():
    assert L.lint_text_fr("Vous devriez couper vos pertes.")
    assert L.lint_text_fr("Un rapport garanti.")
    assert L.lint_text_fr("Nous recommandons ceci.")
    html = '<html lang="fr"><p data-lint="disclaimer">Ce n’est pas un conseil en placement.</p></html>'
    assert not L.lint_text_fr(L.visible_text(L.strip_disclaimers(html)))


@pytest.mark.parametrize("path", ["/fr/conditions/", "/fr/confidentialite/", "/fr/avant-de-payer/", "/terms/", "/privacy/"])
def test_flag_on_legal_pages_axe(browser, paid, path):
    import functools
    import http.server
    import threading

    class Q(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(Q, directory=str(paid)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        for scheme in ("light", "dark"):
            ctx = browser.new_context(viewport={"width": 375, "height": 900}, color_scheme=scheme, bypass_csp=True)
            pg = ctx.new_page()
            pg.goto(f"http://127.0.0.1:{srv.server_address[1]}{path}")
            assert horizontal_overflow(pg) == []
            assert axe_violations(pg) == []
            ctx.close()
    finally:
        srv.shutdown()
