"""Fixes for the delta Tester's findings (TESTER-REPORT-delta-decisions-2026-10-21: D1–D6, N1–N12)
and the Manager's review (MANAGER-REVIEW-v2-2026-10-21: /redeem rate limit is server-side;
launch_date, the old calculators' CSP and the manual-restore wording are here).

Tests named "..._tester_repro" are the Tester's repros from /home/claude/tester-delta/ (that folder
is never modified), copied here and adapted only where the fix changed the interface. Every value
is an obviously fake fixture.
"""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402
import lint as L  # noqa: E402

RETEST_JS = os.path.join(REPO, "site", "static", "js", "paid", "retest-copy.js")
DAY = 86400


def node(code):
    r = subprocess.run(["node", "--input-type=module", "-e", code, "file://" + RETEST_JS],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def window_for(first_iso):
    """The window the server returns for a first report at first_iso (opens +30 d, closes +60 d)."""
    import datetime as dt
    t = int(dt.datetime.fromisoformat(first_iso.replace("Z", "+00:00")).timestamp())
    return {"opens_at": t + 30 * DAY, "closes_at": t + 60 * DAY}, t


def ics_for(first_iso):
    w, t = window_for(first_iso)
    code = (f"import(process.argv[1]).then(m => process.stdout.write(JSON.stringify("
            f"{{ics: m.ics({json.dumps(w)}, new Date({(t + 40) * 1000})), "
            f"line: m.retestLine({json.dumps(w)}, {t + 40})}})));")
    d = node(code)
    return d["ics"], d["line"], w


# ------------------------------------------------------------------ D1: .ics and server agree
@pytest.mark.parametrize("first_iso,start,shown", [
    ("2026-11-01T15:00:00Z", "20261201T150000Z", "2026-12-01 15:00 UTC"),
    ("2026-11-01T23:30:00Z", "20261201T233000Z", "2026-12-01 23:30 UTC"),   # 07:30 the next day in UTC+8
    ("2026-11-01T23:30:07Z", "20261201T233007Z", "2026-12-01 23:31 UTC"),   # shown rounded UP
])
def test_d1_ics_starts_at_the_servers_opening_instant_tester_repro(first_iso, start, shown):
    # ics-check.mjs, adapted: ics() now takes the server's window instead of "now"
    ics, line, w = ics_for(first_iso)
    unfolded = ics.replace("\r\n ", "")
    assert f"DTSTART:{start}\r\n" in unfolded, unfolded
    assert "VALUE=DATE" not in ics, "never an all-day (local calendar day) event"
    assert re.search(r"DTEND:\d{8}T\d{6}Z", unfolded)
    desc = next(x for x in unfolded.split("\r\n") if x.startswith("DESCRIPTION:")).replace("\\,", ",")
    for text in (desc, line):
        assert f"opens at {shown}" in text, text
        assert "in 30 days, 0 hours" in text, text
        assert "opens on" not in text
    assert all(len(x.encode("utf-8")) <= 75 for x in ics.split("\r\n"))
    assert not L.lint_text(line) and not L.lint_text(desc)


def test_d1_no_reminder_without_a_server_window():
    d = node("import(process.argv[1]).then(m => process.stdout.write(JSON.stringify({"
             "none: m.ics(null), bad: m.ics({opens_at: 5, closes_at: 4}), line: m.retestLine(null)})));")
    assert d["none"] is None and d["bad"] is None
    assert "30 to 60 days after your first report" in d["line"]


def test_d1_report_page_uses_the_servers_window_and_hides_the_reminder_after_the_retest():
    js = open(os.path.join(REPO, "site", "static", "js", "paid", "report.js"), encoding="utf-8").read()
    assert "retest: r.json.retest" in js and "ics(win)" in js
    assert "ics()" not in js, "the .ics is never built from the browser's own clock"


# ------------------------------------------------------------------ D3: every stated window number = paid_terms.json
TERMS = json.load(open(os.path.join(REPO, "site", "config", "paid_terms.json"), encoding="utf-8"))
OPENS, CLOSES = TERMS["retest_opens_days_after_first_report"], TERMS["retest_closes_days_after_first_report"]
KEY, KEY_FR = TERMS["key_days_after_purchase"], TERMS["key_days_after_first_report"]
KEEP, GRACE = TERMS["prints_keep_days_after_first_report"], TERMS["tracker_prints_grace_days"]
N = r"(\d+)"
# page → [(pattern with the numbers as groups, the numbers it must state)]. Each must occur at least once.
STATEMENTS = {
    "/terms/": [(rf"one re-test, which opens {N} days after your first report and closes {N} days after it", (OPENS, CLOSES)),
                (rf"Your key is valid for {N} days after purchase, or until {N} days after your first report", (KEY, KEY_FR))],
    "/fr/conditions/": [(rf"Le nouveau test est offert de {N} à {N} jours après votre premier rapport", (OPENS, CLOSES)),
                        (rf"valide {N} jours après l’achat, ou jusqu’à {N} jours après votre premier rapport", (KEY, KEY_FR))],
    "/fr/avant-de-payer/": [(rf"à partir de {N} jours et jusqu’à {N} jours après votre premier rapport", (OPENS, CLOSES)),
                            (rf"valide {N} jours après l’achat, ou jusqu’à {N} jours après votre premier rapport", (KEY, KEY_FR))],
    "/pricing/": [(rf"One re-test is included, to run {N} to {N} days after your first report", (OPENS, CLOSES)),
                  (rf"Access lasts {N} days after purchase, or until {N} days after your first report", (KEY, KEY_FR))],
    "/privacy/": [(rf"or {N} days after your first report, whichever comes first", (KEEP,)),
                  (rf"delete them {N} days after it ends", (GRACE,))],
}
# Anywhere on any page: a stated re-test window must be the server's.
SWEEP = [rf"re-test[^.]{{0,80}}?\b{N} to {N} days", rf"nouveau test[^.]{{0,80}}?\bde {N} à {N} jours",
         rf"à partir de {N} jours et jusqu’à {N} jours"]


def statement_problems(path, text):
    out = []
    for pat, want in STATEMENTS.get(path, []):
        found = [tuple(int(x) for x in m.groups()) for m in re.finditer(pat, text)]
        if not found:
            out.append((path, "missing", pat))
        out += [(path, f, want) for f in found if f != want]
    for pat in SWEEP:
        out += [(path, tuple(int(x) for x in m.groups()), (OPENS, CLOSES)) for m in re.finditer(pat, text)
                if tuple(int(x) for x in m.groups()) != (OPENS, CLOSES)]
    return out


def test_d3_paid_terms_json_is_consistent():
    assert KEEP == CLOSES + TERMS["prints_buffer_days"]
    assert KEY_FR == KEEP and CLOSES > OPENS > 0


@pytest.fixture(scope="module")
def both_build(tmp_path_factory):
    from test_legal import build, paid_env
    tmp = tmp_path_factory.mktemp("delta-d3")
    r, out = build(tmp, "out", **paid_env(tmp, pilot_checkout=True))
    assert r.returncode == 0, r.stderr
    return out


def _visible(out, path):
    return " ".join(L.visible_text((out / path.strip("/") / "index.html").read_text(encoding="utf-8")).split())


def test_d3_every_page_states_the_window_and_key_of_paid_terms_json(both_build):
    problems = []
    for path in STATEMENTS:
        problems += statement_problems(path, _visible(both_build, path))
    for p in both_build.rglob("*.html"):
        rel = "/" + str(p.parent.relative_to(both_build)).strip(".") + "/"
        problems += [x for x in statement_problems(rel.replace("//", "/"), " ".join(L.visible_text(p.read_text(encoding="utf-8")).split()))
                     if x[1] != "missing"]
    assert problems == []


def test_d3_the_checker_catches_the_testers_mutations():
    # mutate.sh terms_close / fr_window: "60→90" on /terms/ and "30 à 60 → 30 à 90" on /fr/conditions/
    terms = ("one re-test, which opens 30 days after your first report and closes 90 days after it. "
             "Your key is valid for 90 days after purchase, or until 75 days after your first report")
    assert statement_problems("/terms/", terms)
    fr = ("Le nouveau test est offert de 30 à 90 jours après votre premier rapport. "
          "valide 90 jours après l’achat, ou jusqu’à 75 jours après votre premier rapport")
    assert statement_problems("/fr/conditions/", fr)
    assert statement_problems("/home/", "one free re-test 30 to 90 days after your first report")
    assert statement_problems("/terms/", "") and statement_problems("/terms/", "")[0][1] == "missing"


def test_d3_report_page_line_states_paid_terms_json():
    d = node("import(process.argv[1]).then(m => process.stdout.write(JSON.stringify({line: m.RETEST_LINE})));")
    m = re.search(rf"re-test on the same account, {N} to {N} days after your first report", d["line"])
    assert m and (int(m.group(1)), int(m.group(2))) == (OPENS, CLOSES)


# ------------------------------------------------------------------ D5: claim:waive_dispute, sentence by sentence
D5_EVASIONS = [   # the Tester's 18 that got through, word for word (report D5)
    "You will not dispute this payment with your bank.",
    "You may not initiate a chargeback.",
    "You must not open a dispute with your card issuer.",
    "No chargebacks: all sales are final.",
    "You relinquish any right to a chargeback.",
    "You forfeit any right to a chargeback.",
    "You surrender any right to a chargeback.",
    "You abandon any claim to contest the charge.",
    "Payment is final and cannot be disputed.",
    "This payment is non-disputable.",
    "You agree to never dispute.",
    "You agree you will not dispute.",
    "You consent to not disputing this charge.",
    "By paying you waive, to the fullest extent permitted by applicable law and without limitation of any kind "
    "whatsoever, any dispute.",
    "Vous acceptez de ne pas contester ce paiement.",
    "Vous vous engagez à ne pas demander de rétrofacturation.",
    "Aucune contestation de paiement ne sera acceptée.",
    "Vous ne pourrez pas contester la transaction auprès de votre banque.",
]
D5_MORE = ["You forgo any dispute.", "You give up any chargeback right.", "You can't dispute this charge.",
           "You won’t file a chargeback.", "Do not dispute this payment.", "Vous renoncez à contester ce paiement.",
           "Vous n’allez pas contester ce paiement.", "Vous ne devez jamais ouvrir de litige.",
           "We waive nothing. You waive " + "x " * 60 + "every dispute right."]


@pytest.mark.parametrize("bad", D5_EVASIONS + D5_MORE)
def test_d5_lint_catches_the_evasions_tester_repro(bad):
    html = f'<html lang="en"><body><main><p>{bad}</p></main></body></html>'
    assert any(p[0] == "claim:waive_dispute" for p in L.lint_html(html, "/x/", False, False, {745}, [], pilot=True)), bad
    assert any(p[0] == "claim:waive_dispute" for p in L.passthrough_rules(html, "/x/", False)), bad
    assert L.waive_dispute_claims(L.js_strings("const m = " + json.dumps(bad) + ";"), "/x.js"), bad


@pytest.mark.parametrize("ok", [
    # N1: the Tester's compliant reassurance
    "Nothing here limits your right to dispute a charge with your bank. We never ask you to waive it.",
    "We never ask you to waive your right to dispute a charge.",
    "You do not have to give up your right to dispute a charge.",
    "This does not affect your right to dispute a charge with your bank.",
    "If we cannot resolve a dispute, it goes to the courts of Ontario.",
    "We can’t help with disputes about a firm.",
    "The evidence is indisputable.",
    "En cas de litige, les tribunaux de l’Ontario sont compétents.",
    "Nous ne pouvons pas vous aider avec un litige concernant une firme.",
])
def test_d5_no_false_positive_on_compliant_wording(ok):
    assert L.waive_dispute_claims(L.normalise(ok), "/x/") == []


def test_d5_sentences_split_on_punctuation_lines_and_bullets():
    assert L.sentences("A dispute. We waive it.\nNext; one · two") == ["A dispute.", "We waive it.", "Next;", "one", "two"]


# ------------------------------------------------------------------ D6 + N5: the address needs a civic or box number
@pytest.mark.parametrize("addr", [
    "Zzqx Street Rd #456, Zzqxville ON K9Z 9Z9",          # the Tester's two (D6): a unit, no civic number
    "Zzqx Street Rd Suite 456, Zzqxville ON K9Z 9Z9",
    "Zzqx Street Rd Unit 456, Zzqxville ON K9Z 9Z9",
    "Zzqx Street Rd PMB 456, Zzqxville ON K9Z 9Z9",
    "Suite 4, Qqvendor Road, Zzqxville ON K9Z 9Z9",
    "0 Qqvendor Road, Zzqxville ON K9Z 9Z9",
    "PO Box 12345678901234567890, Zzqxville ON K9Z 9Z9",  # N5: an absurd box number
    "PO Box 4417 PO Box 9999, Zzqxville ON K9Z 9Z9",      # N5: two boxes
    "PO Box STN Main 4417, Zzqxville ON K9Z 9Z9",
])
def test_d6_an_address_without_its_civic_or_box_number_is_refused_tester_repro(addr):
    assert B.seller_problem("premises_address", addr), addr


@pytest.mark.parametrize("addr", [
    "123 Street Rd #456, Zzqxville ON K9Z 9Z9",            # the mailbox-store format of the ruling
    "123 Zzqx Street Rd Suite 456, Zzqxville ON K9Z 9Z9",
    "Suite 4, 12 Qqvendor Road, Zzqxville ON K9Z 9Z9",     # unit first, as its own part
    "456-123 Zzqx Street Rd, Zzqxville ON K9Z 9Z9",        # Canada Post unit-civic
    "#456-123 Zzqx Street Rd, Zzqxville ON K9Z 9Z9",       # N5: was refused for the leading #
    "1 Box Rd, Zzqxville ON K9Z 9Z9",                      # N5: was read as a PO box
    "123, rue Zzqx, Zzqxville QC H9Z 9Z9",                 # FR: civic number, comma, street
    "PO Box 4417 STN Main, Zzqxville ON K9Z 9Z9",
    "CP 4417 Succ. Centre-ville, Zzqxville QC H9Z 9Z9",
    "C.P. 4417, Zzqxville QC H9Z 9Z9",
    "Case postale 4417, Zzqxville QC H9Z 9Z9",
    "P.O.Box 4417, Zzqxville ON K9Z 9Z9",
])
def test_d6_civic_and_box_addresses_are_accepted(addr):
    assert B.seller_problem("premises_address", addr) is None, (addr, B.seller_problem("premises_address", addr))


# ------------------------------------------------------------------ Manager C3: one launch_date, never in the future
def _toml_launch(tmp, value, extra=""):
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    src, n = re.subn(r'(?m)^launch_date = "[^"]*"', f'launch_date = "{value}"{extra}', src)
    assert n == 1
    p = tmp / f"launch-{value or 'empty'}.toml"
    p.write_text(src, encoding="utf-8")
    return str(p)


LAUNCH_PAGES = ["/pricing/", "/for-firms/", "/start/", "/terms/"]


def test_c3_launch_date_dates_every_launch_statement(tmp_path):
    from test_legal import build
    r, out = build(tmp_path, "set", DT_SITE_TOML=_toml_launch(tmp_path, "2026-10-20"))
    assert r.returncode == 0, r.stderr
    # QA 25 Oct: the rename note stays only in the terms and the price-history row (/pricing/)
    for path in ("/pricing/", "/terms/"):
        assert "called “Trial” before 20 Oct 2026" in _visible(out, path), path
    for path in ("/for-firms/", "/start/"):
        assert "called “Trial”" not in _visible(out, path), path
    assert "<td>20 Oct 2026</td>" in (out / "pricing" / "index.html").read_text(encoding="utf-8")
    assert "Version 2026-10-20." in _visible(out, "/terms/")
    assert "Version 2026-10-24." in _visible(out, "/privacy/")  # T0: the hosting date is later
    for t in ("for-firms", "start", "pricing", "terms"):
        src = open(os.path.join(REPO, "site", "templates", "pages", t + ".html"), encoding="utf-8").read()
        assert "22 Oct 2026" not in src and "2026-10-2" not in src, t


def test_c3_empty_launch_date_is_the_build_date(tmp_path):
    import datetime as dt
    from test_legal import build
    r, out = build(tmp_path, "empty", DT_SITE_TOML=_toml_launch(tmp_path, ""))
    assert r.returncode == 0, r.stderr
    d = dt.date.today()
    assert f"Version {d.isoformat()}." in _visible(out, "/terms/")
    assert f"called “Trial” before {d.day} {B.MONTHS[d.month - 1]} {d.year}" in _visible(out, "/pricing/")


@pytest.mark.parametrize("value,env,msg", [
    ("2099-01-01", {}, "after the build date"),
    ("2026-02-30", {}, "not a real date"),
    ("23 Oct 2026", {}, "not YYYY-MM-DD"),
    ("", {"DT_REQUIRE_LAUNCH_DATE": "1"}, "set it to the push day"),
])
def test_c3_a_future_bad_or_missing_launch_date_fails_the_build(tmp_path, value, env, msg):
    from test_legal import build
    r, _ = build(tmp_path, "bad", DT_SITE_TOML=_toml_launch(tmp_path, value), **env)
    assert r.returncode == 1 and msg in r.stderr, r.stderr


def test_c3_the_old_terms_version_key_is_refused(tmp_path):
    from test_legal import build
    r, _ = build(tmp_path, "old", DT_SITE_TOML=_toml_launch(tmp_path, "2026-10-20", '\nterms_version = "2026-10-23"'))
    assert r.returncode == 1 and "terms_version is not a known key" in r.stderr, r.stderr


def test_c3_bundle_requires_the_launch_date():
    sh = open(os.path.join(REPO, "site", "run.sh"), encoding="utf-8").read()
    assert "DT_REQUIRE_LAUNCH_DATE=1 python3 site/build.py" in sh[sh.index("bundle)"):]


# ------------------------------------------------------------------ T0 (QUICKWINS §2): hosting is Cloudflare Pages
def _toml_hosting(tmp, value):
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    src, n = re.subn(r'(?m)^cloudflare_pages_since = "[^"]*"', f'cloudflare_pages_since = "{value}"', src)
    assert n == 1
    p = tmp / f"hosting-{value or 'empty'}.toml"
    p.write_text(src, encoding="utf-8")
    return str(p)


def test_t0_privacy_pages_say_cloudflare_pages_since_the_move(tmp_path):
    from test_legal import build, paid_env
    r, out = build(tmp_path, "paid", **paid_env(tmp_path))
    assert r.returncode == 0, r.stderr
    en, fr = _visible(out, "/privacy/"), _visible(out, "/fr/confidentialite/")
    assert "The site is hosted on Cloudflare Pages; before 24 Oct 2026 it was hosted on GitHub Pages." in en
    assert "Cloudflare receives visitors’ IP addresses to deliver the pages and protect the site" in en
    assert "le site est hébergé sur Cloudflare Pages; avant le 24 octobre 2026, il l’était sur GitHub Pages." in fr
    for page in (en, fr):
        assert "is hosted on GitHub Pages" not in page and "hébergé sur GitHub Pages" not in page
    for h in ((out / "privacy" / "index.html").read_text(encoding="utf-8"),
              (out / "fr" / "confidentialite" / "index.html").read_text(encoding="utf-8")):
        assert 'href="https://www.cloudflare.com/privacypolicy/"' in h
        assert "github-general-privacy-statement" not in h
    assert "Substack and Cloudflare are mostly in the United States" in en
    # Lead (Tester LOW): the privacy notice's version is the hosting date; the terms keep launch_date
    assert en.count("version 2026-10-24.") + en.count("Version 2026-10-24.") == 2
    assert "Version du 2026-10-24." in fr
    assert "Version 2026-10-21." in _visible(out, "/terms/") and "Version du 2026-10-21." in _visible(out, "/fr/conditions/")
    r, off = build(tmp_path, "off")
    assert r.returncode == 0, r.stderr
    p = _visible(off, "/privacy/")
    assert "The site is hosted on Cloudflare Pages; before 24 Oct 2026 it was hosted on GitHub Pages." in p
    assert "Substack and Cloudflare are mostly in the United States" in p


@pytest.mark.parametrize("value,msg", [
    ("", "not empty"),
    ("2099-01-01", "after the build date"),
    ("2026-02-30", "not a real date"),
    ("24 Oct 2026", "not YYYY-MM-DD"),
])
def test_t0_an_empty_future_or_bad_hosting_date_fails_the_build(tmp_path, value, msg):
    from test_legal import build
    r, _ = build(tmp_path, "bad", DT_SITE_TOML=_toml_hosting(tmp_path, value))
    assert r.returncode == 1 and "cloudflare_pages_since" in r.stderr and msg in r.stderr, r.stderr


# ------------------------------------------------------------------ Owner 21 Oct ~11:00: no dated / launch pricing
@pytest.mark.parametrize("bad", [
    "Launch pricing, valid for engagements signed before 31 March 2027.",
    "Firm prices are launch pricing.",
    "These launch prices end soon.",
    "Prices valid until 31 March 2027.",
    "Offer valid before 1 April.",
    "Tarif de lancement pour les firmes.",
    "Prix valables jusqu’au 31 mars 2027.",
])
def test_owner_lint_refuses_dated_or_launch_pricing(bad):
    html = f'<html lang="en"><body><main><p>{bad}</p></main></body></html>'
    assert any(p[0] == "claim:dated_pricing" for p in L.lint_html(html, "/x/", False, False, {745}, [], pilot=True)), bad
    assert any(p[0] == "claim:dated_pricing" for p in L.passthrough_rules(html, "/x/", False)), bad
    assert L.dated_pricing_claims(L.js_strings("const m = " + json.dumps(bad) + ";"), "/x.js"), bad


def test_owner_lint_refuses_price_valid_until_in_json_ld():
    ld = '<script type="application/ld+json">{"offers": {"@type": "Offer", "price": "39", "priceValidUntil": "2027-03-31"}}</script>'
    html = f'<html lang="en"><head>{ld}</head><body><main><p>Hi.</p></main></body></html>'
    assert any(p[0] == "claim:dated_pricing" for p in L.lint_html(html, "/x/", False, False, {39}, []))
    assert any(p[0] == "claim:dated_pricing" for p in L.passthrough_rules(html, "/x/", False))


def test_owner_no_ok_wording_is_refused():
    for ok in ("Four of these gates had to be redesigned before they could work.",
               "Your first Snapshot at an introductory price, one per firm.",
               "Firm prices are in US dollars (USD), before any applicable sales tax."):
        assert L.dated_pricing_claims(L.normalise(ok), "/x/") == [], ok


def test_owner_launch_pricing_is_gone_from_every_build_and_prices_json(both_build, tmp_path):
    from test_legal import build
    r, off = build(tmp_path, "off")
    assert r.returncode == 0, r.stderr
    for out in (off, both_build):
        for p in out.rglob("*.html"):
            h = p.read_text(encoding="utf-8")
            t = L.visible_text(h)
            assert not re.search(r"(?i)launch pric|31 March 2027|priceValidUntil", h + t), p
    prices = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
    assert "launch_valid_until" not in prices and "2027-03-31" not in json.dumps(prices)
    pricing = (off / "pricing" / "index.html").read_text(encoding="utf-8")
    assert "Firm prices are in US dollars (USD), before any applicable sales tax." in L.visible_text(pricing)
    assert "The end date once shown with the firm prices is removed" in L.visible_text(pricing)


# ------------------------------------------------------------------ Manager / owner: manual restore wording
MANUAL = "If your access link stops working, email us from the address you paid with and we’ll send a new one."


def _paid_toml_manual(tmp, value):
    from test_legal import paid_env
    env = paid_env(tmp)
    src = open(env["DT_SITE_TOML"], encoding="utf-8").read()
    src, n = re.subn(r"(?m)^manual_restore = true$", f"manual_restore = {value}", src)
    assert n == 1
    p = tmp / f"manual-{value}.toml"
    p.write_text(src, encoding="utf-8")
    env["DT_SITE_TOML"] = str(p)
    return env


def test_manual_restore_on_by_default_says_email_us_never_not_offered(both_build):
    welcome = _visible(both_build, "/welcome/")
    assert MANUAL in welcome and "restore by email is not offered" not in welcome
    assert MANUAL.replace("email us", "email us") in _visible(both_build, "/restore/")
    terms = _visible(both_build, "/terms/")
    assert "they are the only automatic way to reopen your purchase in another browser. " + MANUAL in terms
    assert "écrivez-nous depuis l’adresse utilisée pour payer" in _visible(both_build, "/fr/conditions/")
    for p in both_build.rglob("*.html"):
        assert "restore by email is not offered" not in p.read_text(encoding="utf-8"), p
    import tomllib
    assert tomllib.load(open(os.path.join(REPO, "site", "config", "site.toml"), "rb"))["site"]["manual_restore"] is True


def test_manual_restore_false_keeps_the_old_wording_and_lints_clean(tmp_path, monkeypatch):
    from test_legal import build
    env = _paid_toml_manual(tmp_path, "false")
    r, out = build(tmp_path, "off", **env)
    assert r.returncode == 0, r.stderr
    assert "restore by email is not offered" in _visible(out, "/welcome/")
    assert "they are the only way to reopen your purchase in another browser." in _visible(out, "/terms/")
    for p in out.rglob("*.html"):
        assert "from the address you paid with" not in L.visible_text(p.read_text(encoding="utf-8")), p
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    assert L.lint_build(str(out), paid=True) == []


def test_manual_restore_must_be_a_boolean(tmp_path):
    from test_legal import build
    r, _ = build(tmp_path, "bad", **_paid_toml_manual(tmp_path, '"yes"'))
    assert r.returncode == 1 and "manual_restore must be true or false" in r.stderr, r.stderr


def test_manual_restore_sentence_passes_the_restore_email_rule():
    assert not L.restore_email_claims(L.normalise(MANUAL), "/welcome/")


# ------------------------------------------------------------------ Manager C4: every tool page blocks outgoing requests
TOOL_PAGES = ["/tools/trade-stats/", "/tools/prop-challenge-simulator/", "/tools/lot-size-calculator/",
              "/tools/disposition-calculator/", "/tools/pass-rate-calculator/",
              "/tools/risk-reward-calculator/", "/tools/drawdown-calculator/", "/tools/trading-heatmap/"]  # tools batch 2


def _csp(html):
    import html as _h
    m = re.search(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)"', html)
    return _h.unescape(m.group(1)) if m else None


def test_c4_every_tool_page_has_a_csp_with_no_connections(built_site):
    for path in TOOL_PAGES:
        csp = _csp((built_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8"))
        assert csp, path
        d = dict((x.split(" ", 1) + [""])[:2] for x in (y.strip() for y in csp.split(";")))
        assert d["connect-src"] == "'none'", (path, csp)
        assert d["default-src"] == "'self'" and "http" not in d["script-src"], (path, csp)
    tools = [p for p in (built_site["out"] / "tools").iterdir() if (p / "index.html").exists()]
    assert sorted("/tools/" + p.name + "/" for p in tools) == sorted(TOOL_PAGES), "a new tool page: add it here"


@pytest.mark.parametrize("path,example,out_id", [("/tools/disposition-calculator/", "#dc-example", "#dc-t"),
                                                 ("/tools/pass-rate-calculator/", "#pr-example", "#pr-rate")])
def test_c4_old_calculators_still_work_and_cannot_send(browser, built_site, path, example, out_id):
    page = browser.new_page()
    errors = []
    page.on("console", lambda m: errors.append(m.text) if "Content Security Policy" in m.text else None)
    page.goto(built_site["url"] + path)
    page.click(example)
    assert page.inner_text(out_id).strip() not in ("", "—"), "the calculator still computes"
    blocked = page.evaluate("""async () => { const out = [];
        for (const u of ['/x.json', 'https://example.com/x']) { try { await fetch(u); out.push('sent ' + u); } catch (e) { out.push('blocked'); } }
        try { navigator.sendBeacon('/beacon', 'x') ? out.push('beacon queued') : out.push('blocked'); } catch (e) { out.push('blocked'); }
        return out; }""")
    page.close()
    assert blocked[:2] == ["blocked", "blocked"], blocked
    assert not [e for e in errors if "fetch" not in e.lower() and "beacon" not in e.lower() and "connect" not in e.lower()], errors


# ------------------------------------------------------------------ NITs N2, N3, N6, N7
def _pilot_build(tmp):
    from test_legal import build, private_with, toml_with
    priv = private_with(tmp, premises_address="PO Box 4417 STN Main, Zzqxville ON K9Z 9Z9")
    r, out = build(tmp, "p", DT_SITE_TOML=toml_with(tmp, pilot_checkout=True), DT_PRIVATE_TOML=priv)
    assert r.returncode == 0, r.stderr
    return out, priv


def test_n2_lint_warns_when_it_cannot_check_the_address(tmp_path):
    out, _ = _pilot_build(tmp_path)
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "lint.py"), str(out)], capture_output=True, text=True,
                       env={**os.environ, "DT_PRIVATE_TOML": str(tmp_path / "nonexistent.toml")})
    assert "lint: WARNING: no private.toml at" in r.stdout and "NOT checked" in r.stdout, r.stdout


def test_n3_lint_reads_the_builds_prices_json(tmp_path, monkeypatch):
    p = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
    for x in p["products"]:
        if x["id"] == "pilot":
            x["price_usd"] = 845
    f = tmp_path / "prices.json"
    f.write_text(json.dumps(p), encoding="utf-8")
    monkeypatch.setenv("DT_PRICES_JSON", str(f))
    assert 845 in L.allowed_amounts()
    calls = []
    real = L.read_private
    monkeypatch.setattr(L, "read_private", lambda: calls.append(1) or real())
    L.lint_build(os.path.join(REPO, "site", "_site"))
    assert len(calls) == 1, "private.toml read once per run"


def test_n6_a_placeholder_is_flagged_on_every_page_footer_included(tmp_path, monkeypatch):
    from test_legal import build, private_with, toml_with
    priv = private_with(tmp_path, premises_address="[ADDRESS — virtual mailbox pending]")
    r, out = build(tmp_path, "ph", DT_SITE_TOML=toml_with(tmp_path, pilot_checkout=True), DT_PRIVATE_TOML=priv,
                   DT_ALLOW_PLACEHOLDERS="1")
    assert r.returncode == 0, r.stderr
    monkeypatch.setenv("DT_PRIVATE_TOML", priv)
    where = {w for rule, w, d in L.lint_build(str(out), pilot=True) if rule == "flag:seller_placeholder"}
    pages = list(out.rglob("*.html"))
    assert len(where) == len(pages) >= 36, (len(where), len(pages))
    assert all("never publish" in d for rule, w, d in L.lint_build(str(out), pilot=True) if rule == "flag:seller_placeholder")


def test_n7_the_refund_clause_describes_the_pilot_checkbox(tmp_path):
    out, _ = _pilot_build(tmp_path)
    for path in ("/start/", "/for-firms/"):
        h = (out / path.strip("/") / "index.html").read_text(encoding="utf-8")
        m = re.search(r'<input[^>]*id="pc-read"[^>]*>', h)
        assert m, path
        ids = re.search(r'aria-describedby="([^"]*)"', m.group(0)).group(1).split()
        assert "pc-refund" in ids and "pc-read-links" in ids, (path, ids)
        assert 'id="pc-refund"' in h
