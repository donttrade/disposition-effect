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
