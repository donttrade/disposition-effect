"""Page-side items from the 21 Oct fix round (CODER-FIX-REPORT-v2-2026-10-21, "Not fixed here"):

D9   wording lint covers passthrough pages (upload/analytics claims, regular price, retired
     amounts, Tally); /code/'s "nothing leaves" is fixed at build time, docs/ untouched.
D10b no standard price anywhere; prices.json has no standard_price_usd field.
D12  a paid build fails unless [worker] api_base is https (loopback http only in an explicit
     local test build); no http://127.0.0.1 in a real build.
D2   /report/ re-test line and the .ics text say "export the same account from the same start
     date as your first file".
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
import lint as L  # noqa: E402
import build as B  # noqa: E402
from test_legal import build, paid_env, prices_with_test_link, private_with, toml_with  # noqa: E402

PHRASE = "export the same account from the same start date as your first file"


# ------------------------------------------------------------------ D9
def test_code_page_copy_fixed_in_build_not_in_docs(built_site):
    built = (built_site["out"] / "code" / "index.html").read_text(encoding="utf-8")
    docs = open(os.path.join(REPO, "docs", "code", "index.html"), encoding="utf-8").read()
    assert "nothing leaves" not in built.lower() and "sends nothing anywhere" in built
    assert "nothing leaves the machine it runs on" in docs  # docs/ is replaced only at step 30


def test_no_upload_claims_on_any_page(built_site):
    for p in built_site["out"].rglob("*.html"):
        text = L.visible_text(p.read_text(encoding="utf-8", errors="replace")).lower()
        for c in ("nothing leaves", "nothing is uploaded", "never leaves your browser"):
            assert c not in text, (p, c)


def test_lint_covers_passthrough_pages(tmp_path):
    r, out = build(tmp_path, "x")
    assert r.returncode == 0
    assert L.lint_build(str(out)) == []
    page = out / "glossary" / "index.html"  # a passthrough page
    page.write_text(page.read_text(encoding="utf-8").replace("</main>", "<p>Nothing is uploaded. Standard prices after launch: $49.</p></main>"),
                    encoding="utf-8")
    rules = {r for r, where, _ in L.lint_build(str(out)) if where == "/glossary/index.html"}
    assert {"claim:no_upload", "banned:regular_price", "price_literal"} <= rules
    # with analytics on, the old footers' "runs no analytics" is caught on passthrough pages
    assert any(r == "claim:no_analytics" for r, _, _ in L.lint_build(str(out), analytics=True))


def test_passthrough_fix_fails_loudly_when_the_sentence_is_gone(tmp_path, monkeypatch):
    monkeypatch.setitem(B.PASSTHROUGH_FIXES, os.path.join("about", "index.html"), [("no such sentence", "x")])
    monkeypatch.setenv("DT_OUT", str(tmp_path / "o"))
    with pytest.raises(B.BuildError, match="passthrough fix"):
        B.build()


# ------------------------------------------------------------------ D10b
def test_prices_json_has_no_standard_price():
    raw = open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8").read()
    assert "standard_price" not in raw
    d = json.loads(raw)
    assert all("standard_price_usd" not in p for p in d["products"])
    assert next(p for p in d["products"] if p["id"] == "report39")["price_usd"] == 39


def test_no_standard_price_wording_flag_off_or_on(built_site, tmp_path):
    r, on = build(tmp_path, "on", **paid_env(tmp_path))
    assert r.returncode == 0, r.stderr
    for out in (built_site["out"], on):
        for p in out.rglob("*.html"):
            text = L.visible_text(p.read_text(encoding="utf-8", errors="replace"))
            assert not re.search(r"standard (price|after launch)|regular price|\$\s?49\b|\$\s?99\b", text, re.I), p
    assert "$39 founding price for the first 100 buyers" in L.visible_text((on / "pricing" / "index.html").read_text())


# ------------------------------------------------------------------ D12
def _api_toml(tmp, api):
    p = toml_with(tmp, "api.toml", paid_report=True, trader_first_home=True)
    src = open(p, encoding="utf-8").read()
    src = re.sub(r'(?m)^api_base = "[^"]*"', f'api_base = "{api}"', src)
    open(p, "w", encoding="utf-8").write(src)
    return p


@pytest.mark.parametrize("api,env,ok", [
    ("http://127.0.0.1:8787", {}, False),                              # the committed default: never in a real build
    ("http://127.0.0.1:8787", {"DT_ALLOW_LOCAL_API": "1"}, True),      # explicit local test build
    ("http://api.example.com", {"DT_ALLOW_LOCAL_API": "1"}, False),    # non-loopback http: never
    ("https://localhost:8787", {}, False),
    ("https://api.donttrade.ca", {}, True),
])
def test_paid_build_needs_https_api(tmp_path, api, env, ok):
    # report39 has no Stripe test link in the committed prices.json; a copy with one is passed in
    e = {"DT_SITE_TOML": _api_toml(tmp_path, api), "DT_PRIVATE_TOML": private_with(tmp_path),
         "DT_PRICES_JSON": prices_with_test_link(tmp_path), **env}
    r, out = build(tmp_path, "b", **e)
    if not ok:
        assert r.returncode == 1 and "api_base" in r.stderr, r.stderr
        return
    assert r.returncode == 0, r.stderr
    report = (out / "report" / "index.html").read_text(encoding="utf-8")
    assert f'<meta name="dt-api" content="{api}">' in report and api in report
    if api.startswith("https://"):
        for p in out.rglob("*.html"):
            assert "127.0.0.1" not in p.read_text(encoding="utf-8", errors="replace"), p


# ------------------------------------------------------------------ D2
def test_retest_wording_on_page_and_in_ics():
    js = os.path.join(REPO, "site", "static", "js", "paid", "retest-copy.js")
    code = ("import(process.argv[1]).then(m => { process.stdout.write(JSON.stringify("
            "{line: m.RETEST_LINE, ics: m.ics(new Date('2026-10-22T12:00:00Z'))})); });")
    r = subprocess.run(["node", "--input-type=module", "-e", code, "file://" + js], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    d = json.loads(r.stdout)
    assert PHRASE in d["line"] and "30 to 60 days" in d["line"]
    lines = d["ics"].split("\r\n")
    assert all(len(x.encode("utf-8")) <= 75 for x in lines)
    unfolded = d["ics"].replace("\r\n ", "")
    desc = next(x for x in unfolded.split("\r\n") if x.startswith("DESCRIPTION:"))
    assert PHRASE in desc.replace("\\,", ",") and "DTSTART;VALUE=DATE:20261121" in unfolded
    report_js = open(os.path.join(REPO, "site", "static", "js", "paid", "report.js"), encoding="utf-8").read()
    assert "RETEST_LINE" in report_js and "from './retest-copy.js'" in report_js
    assert not L.lint_text(d["line"]) and not L.lint_text(desc)
