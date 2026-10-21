"""Owner decisions revised 21 Oct ~09:00 ET (V2-BUILD-PLAN "DECISIONS REVISED"; detail and exact
sentences in DECISIONS-RESEARCH-2026-10-21.md).

1. Business identification: with ANY commerce flag on, every page footer shows
   "donttrade · Ontario, Canada · <mailing address> · <business email>". The legal name and phone
   stay paid_report-only. With every commerce flag off nothing changes and private.toml is not read.
   PO box (Canada Post) and mailbox-store street addresses are accepted.

Every value here is an obviously fake fixture.
"""
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402
import lint as L  # noqa: E402
from test_legal import FAKE, all_html, build, paid_env, private_with, same_tree, toml_with  # noqa: E402

BOX = "PO Box 4417 STN Main, Zzqxville ON K9Z 9Z9"   # Canada Post style, with a station qualifier
EMAIL = "donttrade.research@gmail.com"                # [site] contact_email, the business email
LINE_TEXT = f"donttrade · Ontario, Canada · {BOX} · {EMAIL}"


def _text(fragment):
    return " ".join(re.sub(r"<[^>]+>", " ", fragment).split())


def _flag_env(tmp, combo):
    if combo == "pilot":
        env = {"DT_SITE_TOML": toml_with(tmp, "pilot.toml", pilot_checkout=True)}
    elif combo == "paid":
        env = paid_env(tmp)
    else:
        env = paid_env(tmp, pilot_checkout=True)
    env["DT_PRIVATE_TOML"] = private_with(tmp, f"{combo}-private.toml", premises_address=BOX)
    return env


@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    out = {}
    for combo in ("pilot", "paid", "both"):
        tmp = tmp_path_factory.mktemp("dec-" + combo)
        env = _flag_env(tmp, combo)
        r, o = build(tmp, "out", **env)
        assert r.returncode == 0, r.stderr
        out[combo] = (o, env)
    return out


# ------------------------------------------------------------------ 1. the address shape
@pytest.mark.parametrize("addr", [
    "PO Box 4417 STN Main, Zzqxville ON K9Z 9Z9",
    "PO Box 4417, STN Main, Zzqxville ON K9Z 9Z9",       # before: "1234," was read as the box number
    "PO Box 4417 Stn Main, Zzqxville ON K9Z 9Z9, Canada",
    "P.O. Box 4417 Stn. A, Zzqxville, ON K9Z 9Z9",
    "PO Box 4417 RPO Zzqx Centre, Zzqxville ON K9Z 9Z9",
    "PO Box #4417, Zzqxville ON K9Z 9Z9",
    "123 Zzqx Street Rd #456, Zzqxville ON K9Z 9Z9",     # mailbox store (UPS Store style)
    "123 Zzqx Street Rd, #456, Zzqxville ON K9Z 9Z9",
    "123 Zzqx Street Rd Suite 456, Zzqxville ON K9Z 9Z9",
])
def test_po_box_and_mailbox_addresses_are_accepted(addr):
    assert B.seller_problem("premises_address", addr) is None


@pytest.mark.parametrize("addr", [
    "PO Box, Zzqxville ON K9Z 9Z9", "PO Box STN Main, Zzqxville ON K9Z 9Z9", "PO Box 0 STN Main, Zzqxville ON K9Z 9Z9",
    "PO Box 4417 STN Main Zzqxville ON K9Z 9Z9", "PO Box 4417 STN Main, Zzqxville ON Z9Z 9Z9",
])
def test_malformed_box_addresses_are_still_refused(addr):
    assert B.seller_problem("premises_address", addr)


# ------------------------------------------------------------------ 1. flag off: unchanged, private.toml not read
def test_flag_off_does_not_read_private_toml_and_has_no_business_line(tmp_path):
    r1, a = build(tmp_path, "a")
    bad = tmp_path / "broken.toml"
    bad.write_text("this is = = not toml [[[", encoding="utf-8")
    r2, b = build(tmp_path, "b", DT_PRIVATE_TOML=str(bad))                       # unreadable: never opened
    r3, c = build(tmp_path, "c", DT_PRIVATE_TOML=str(tmp_path / "missing.toml"))  # absent: fine too
    assert r1.returncode == r2.returncode == r3.returncode == 0, (r2.stderr, r3.stderr)
    assert same_tree(str(a), str(b)) and same_tree(str(a), str(c))
    text = "".join(all_html(a).values())
    assert "data-business-id" not in text and "Ontario, Canada ·" not in text
    assert L.lint_build(str(a)) == []


# ------------------------------------------------------------------ 1. any commerce flag: every page, exactly once
@pytest.mark.parametrize("combo", ["pilot", "paid", "both"])
def test_every_page_has_the_business_line_once(builds, combo):
    out, _ = builds[combo]
    pages = all_html(out)
    assert len(pages) >= 35
    for rel, h in pages.items():
        found = B.BUSINESS_ID_RE.findall(h)
        assert len(found) == 1, rel
        assert _text(found[0]) == LINE_TEXT, (rel, _text(found[0]))
        assert f'<a href="mailto:{EMAIL}">{EMAIL}</a>' in found[0], rel
        # inside the footer, right under the contact line
        foot = h[h.rindex("<footer"):]
        assert found[0] in foot, rel
        assert foot.index(found[0]) < foot.index("Firms pay for fixed-scope measurements"), rel


def test_pilot_alone_shows_no_legal_name_or_phone(builds):
    out, _ = builds["pilot"]
    for rel, h in all_html(out).items():
        assert FAKE["seller_legal_name"] not in h and FAKE["phone"] not in h, rel
        assert "data-seller-block" not in h, rel
        assert BOX not in B.BUSINESS_ID_RE.sub("", h), rel   # the address only in the business line


def test_paid_still_shows_the_full_seller_block(builds):
    out, _ = builds["paid"]
    h = (out / "pricing" / "index.html").read_text(encoding="utf-8")
    assert "data-seller-block" in h and FAKE["seller_legal_name"] in h and FAKE["phone"] in h


@pytest.mark.parametrize("combo", ["pilot", "paid", "both"])
def test_flag_builds_lint_clean(builds, combo, monkeypatch):
    out, env = builds[combo]
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    pilot = combo in ("pilot", "both")
    paid = combo in ("paid", "both")
    assert L.lint_build(str(out), paid=paid, pilot=pilot) == []


# ------------------------------------------------------------------ 1. loud failures
def test_verify_fails_when_a_page_loses_its_line(builds, tmp_path):
    import shutil
    out, _ = builds["pilot"]
    copy = tmp_path / "copy"
    shutil.copytree(out, copy)
    fp = copy / "about" / "index.html"
    fp.write_text(B.BUSINESS_ID_RE.sub("", fp.read_text(encoding="utf-8")), encoding="utf-8")
    flags = {"paid_report": False, "pilot_checkout": True, "analytics": False}
    with pytest.raises(B.BuildError, match="business line: about/index.html has 0"):
        B.verify(str(copy), flags, seller=False)
    problems = L.lint_build(str(copy), pilot=True)
    assert ("business_line", "/about/index.html", "0 business-identification line(s), expected exactly 1") in problems


def test_lint_flags_a_line_in_a_flag_off_build_and_a_wrong_address(builds, tmp_path):
    line = B.business_id_line({"flags": {"paid_report": False, "pilot_checkout": True},
                               "site": {"name": "donttrade", "contact_email": EMAIL}}, {"premises_address": BOX})
    assert L.business_line_problems("<footer>" + line + "</footer>", "/x/", commerce=False) == [
        ("flag:business_line", "/x/", "business line with every commerce flag off")]
    assert L.business_line_problems("<footer>" + line + "</footer>", "/x/", True, [BOX]) == []
    other = line.replace("4417", "4418")
    assert L.business_line_problems(other, "/x/", True, [BOX])[0][0] == "business_line"
    assert L.business_line_problems(line + line, "/x/", True, [BOX])[0][2].startswith("2 business")
    assert L.business_line_problems(line.replace("Ontario, Canada", "Canada"), "/x/", True, [BOX])[0][0] == "business_line"


def test_passthrough_page_without_the_footer_anchor_fails_the_build(monkeypatch):
    monkeypatch.setattr(B, "PASSTHROUGH_BUSINESS_ANCHOR", "  <p class=\"no-such-anchor\">")
    with pytest.raises(B.BuildError, match="business line: .* expected 1"):
        B.add_business_line("<footer></footer>", "x/index.html", "<p data-business-id>…</p>")
    assert B.add_business_line("unchanged", "x/index.html", "") == "unchanged"   # flags off: no change


def test_business_line_without_an_address_fails_loudly():
    cfg = {"flags": {"paid_report": False, "pilot_checkout": True}, "site": {"name": "donttrade", "contact_email": EMAIL}}
    with pytest.raises(B.BuildError, match="no mailing address"):
        B.business_id_line(cfg, {})
    assert B.business_id_line({**cfg, "flags": {"paid_report": False, "pilot_checkout": False}}, {}) == ""
