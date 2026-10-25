"""The merge of v2-oldpages (plan steps 28–29) into v2-merge (21 Oct 2026).

Both branches changed how the old pages are built. These tests hold the merged result to BOTH:
  * every lifted page carries the footer business-identification line exactly once under any
    commerce flag, and none with every commerce flag off (decision 21 Oct, revised 09:00);
  * [legal] launch_date drives the dated launch statements, and changing it never touches a
    lifted page's frozen body (compare.py stays at 0 differences);
  * the two old calculators keep Manager C4's strict no-network CSP (connect, worker and
    form-action 'none'), now without 'unsafe-inline' since they are template pages;
  * compare.py: the study text is byte-identical in every flag build;
  * a PASSTHROUGH_FIXES entry for a template-owned page fails loudly.
"""
import html as _h
import json
import os
import re
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build as B  # noqa: E402
from test_legal import FAKE_API, build, prices_with_test_link, private_with, toml_with  # noqa: E402

CALCS = ("/tools/disposition-calculator/", "/tools/pass-rate-calculator/")


def _file(out, path):
    return out / (path.strip("/") + ("/index.html" if path.endswith("/") else ""))


def _csp(text):
    m = re.findall(r'<meta http-equiv="Content-Security-Policy" content="([^"]*)"', text)
    assert len(m) == 1
    return dict((x.split(" ", 1) + [""])[:2] for x in (y.strip() for y in _h.unescape(m[0]).split(";")))


def _flag_build(tmp, name, launch="2026-10-20", **flags):
    toml = toml_with(tmp, name + ".toml", api=FAKE_API if flags.get("paid_report") else None, **flags)
    src = open(toml, encoding="utf-8").read()
    src, n = re.subn(r'(?m)^launch_date = "[^"]*"', f'launch_date = "{launch}"', src)
    assert n == 1
    if flags.get("analytics"):
        src = re.sub(r'(?m)^cf_beacon_token = ""', 'cf_beacon_token = "0123456789abcdef0123456789abcdef"', src)
    open(toml, "w", encoding="utf-8").write(src)
    env = {"DT_SITE_TOML": toml, "DT_PRIVATE_TOML": private_with(tmp, name + "-private.toml"),
           "DT_PRICES_JSON": prices_with_test_link(tmp)}
    r, out = build(tmp, name, **env)
    assert r.returncode == 0, r.stderr
    return out, env


COMBOS = [dict(paid_report=p, trader_first_home=p, pilot_checkout=q) for p in (False, True) for q in (False, True)]


@pytest.mark.parametrize("flags", COMBOS, ids=lambda f: f"paid{int(f['paid_report'])}-pilot{int(f['pilot_checkout'])}")
def test_every_flag_combo_lifted_pages_business_line_csp_compare_lint(tmp_path, flags):
    out, env = _flag_build(tmp_path, "b", **flags)
    commerce = flags["paid_report"] or flags["pilot_checkout"]
    assert len(B.LIFTED_PATHS) == 20
    for path in B.LIFTED_PATHS:
        text = _file(out, path).read_text(encoding="utf-8")
        assert text.count("data-business-id") == (1 if commerce else 0), path
        if commerce:
            line = B.BUSINESS_ID_RE.search(text).group(0)
            assert "Ontario, Canada" in line and "mailto:" in line, path
    for path in CALCS:
        d = _csp(_file(out, path).read_text(encoding="utf-8"))
        assert d["connect-src"] == "'none'" and d["worker-src"] == "'none'" and d["form-action"] == "'none'", d
        assert "unsafe-inline" not in d["script-src"] + d["style-src"], d
    e = {**os.environ, **env}
    c = subprocess.run([sys.executable, "checks/compare.py", str(out)], cwd=REPO, env=e, capture_output=True, text=True)
    assert c.returncode == 0 and "0 differences" in c.stdout, c.stdout + c.stderr
    lint = subprocess.run([sys.executable, "checks/lint.py", str(out)], cwd=REPO, env=e, capture_output=True, text=True)
    assert lint.returncode == 0, lint.stdout[-2000:]


def test_analytics_on_calculators_allow_only_the_beacon(tmp_path):
    out, _ = _flag_build(tmp_path, "a", analytics=True)
    for path in CALCS:
        d = _csp(_file(out, path).read_text(encoding="utf-8"))
        assert d["connect-src"] == "'none' https://cloudflareinsights.com", d
        assert d["worker-src"] == "'none'" and d["form-action"] == "'none'", d


def test_launch_date_drives_dates_and_leaves_lifted_bodies_alone(tmp_path):
    a, _ = _flag_build(tmp_path, "d1", launch="2026-10-20", pilot_checkout=True)
    b, _ = _flag_build(tmp_path, "d2", launch="2026-10-19", pilot_checkout=True)
    # QA 25 Oct: /start/ no longer carries the dated rename note (it stays in /terms/ and the /pricing/ history)
    for p, wa, wb in (("/terms/", "2026-10-20", "2026-10-19"), ("/pricing/", "20 Oct 2026", "19 Oct 2026")):
        assert wa in _file(a, p).read_text(encoding="utf-8") and wb in _file(b, p).read_text(encoding="utf-8"), p
    frozen = re.compile(r"(?s)<!--frozen:start-->.*<!--frozen:end-->")
    for path in B.LIFTED_PATHS:
        fa = frozen.search(_file(a, path).read_text(encoding="utf-8")).group(0)
        fb = frozen.search(_file(b, path).read_text(encoding="utf-8")).group(0)
        assert fa == fb, path


def test_a_passthrough_fix_for_a_lifted_page_fails_loudly(tmp_path, monkeypatch):
    rel = os.path.join("about", "index.html")
    monkeypatch.setattr(B, "PASSTHROUGH_FIXES", {rel: [("x", "y")]})
    monkeypatch.setenv("DT_OUT", str(tmp_path / "o"))
    with pytest.raises(B.BuildError, match="not a passthrough page"):
        B.build()


def test_the_no_network_guard_names_only_real_pages():
    owned = {os.path.join(p.strip("/"), "index.html") for p in B.LIFTED_PATHS if p.endswith("/")}
    for rel in B.PASSTHROUGH_CSP_PAGES:
        assert rel in owned, rel
