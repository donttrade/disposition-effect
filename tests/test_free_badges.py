"""Free-launch condition C1 (21 Oct 2026): [flags] free_badges, a TOML boolean, default false.

Off (the committed site.toml and built_site): the free tools show only the descriptive numbers.
No verdict badge, no p, no "distinguishable"/"may be noise"/"not enough trades to tell", no footnote
about error rates, and (QA 25 Oct) no "coming soon" placeholder where each badge was. The badge module is not in the build and no check is run. Lint refuses the badge and
footnote strings in a flags-off build. On (badges_site): today's behaviour, which the existing
badge tests check (test_tool_trade_stats, test_wording_wiring, test_fix_merge NIT 5).
The statistics code (static/js/engine/) is unchanged.
"""
import os
import re
import shutil
import subprocess
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import lint as L  # noqa: E402
from a11y import axe_violations, horizontal_overflow  # noqa: E402

VERDICTS = ("distinguishable from noise", "may be noise", "not enough trades to tell", "Real or noise?",
            "1 time in 20", "1 file in 7", "p is the share", "Running the checks")


def _sample(browser, site, width=1280, scheme="light"):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, bypass_csp=True)
    page = ctx.new_page()
    urls = []
    page.on("request", lambda r: urls.append(r.url))
    page.goto(site["url"] + "/tools/trade-stats/")
    page.click("#ts-sample-btn")
    page.wait_for_selector("#ts-out:not([hidden])", timeout=60000)
    page.wait_for_selector("#ts-teaser:not([hidden])", timeout=60000)
    return ctx, page, urls


def test_committed_default_is_off():
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    assert re.search(r"(?m)^free_badges = false\b", src)


def test_off_shows_numbers_and_the_neutral_line_only(browser, built_site):
    ctx, page, urls = _sample(browser, built_site)
    text = page.inner_text("#ts-out")
    items = page.locator("#ts-noise li").all_inner_texts()
    teaser = page.inner_text("#ts-teaser-text")
    page.wait_for_timeout(500)
    ctx.close()
    assert items == [] and "coming soon" not in text, items   # QA 25 Oct: no placeholder line with badges off
    for v in VERDICTS:
        assert v not in text, v
    assert "noise" not in teaser.lower(), teaser
    assert "Profit factor" in text and "Win rate" in text      # the descriptive numbers are all there
    assert not [u for u in urls if "trade-stats-badges" in u or "noise-worker" in u], "no check runs"


def test_off_page_copy_and_files(built_site, badges_site):
    out = built_site["out"]
    assert not (out / "static" / "js" / "tools" / "trade-stats-badges.js").exists()
    assert (badges_site["out"] / "static" / "js" / "tools" / "trade-stats-badges.js").exists()
    ts = (out / "tools" / "trade-stats" / "index.html").read_text(encoding="utf-8")
    assert 'data-free-badges="false"' in ts and "What does the real-or-noise result mean?" not in ts
    assert "coming soon" not in ts   # QA 25 Oct
    on = (badges_site["out"] / "tools" / "trade-stats" / "index.html").read_text(encoding="utf-8")
    assert 'data-free-badges="true"' in on and "What does the real-or-noise result mean?" in on
    for page in ("tools", "pricing", "tools/lot-size-calculator", "for-traders", ""):
        h = (out / page / "index.html").read_text(encoding="utf-8")
        assert not L.free_badge_problems(h, "/" + page), page


def test_lint_passes_both_builds_and_catches_a_planted_footnote(built_site, badges_site, tmp_path):
    for site, word in ((built_site, "badges=off"), (badges_site, "badges=on")):
        r = subprocess.run([sys.executable, "checks/lint.py", str(site["out"])], cwd=REPO, capture_output=True, text=True)
        assert r.returncode == 0 and word in r.stdout and "lint: PASS" in r.stdout, r.stdout[-1500:]
    planted = tmp_path / "site"
    shutil.copytree(built_site["out"], planted)
    f = planted / "tools" / "index.html"
    f.write_text(f.read_text(encoding="utf-8").replace("</main>", "<p>about 1 time in 20</p></main>"), encoding="utf-8")
    js = planted / "static" / "js" / "tools" / "format.js"
    js.write_text(js.read_text(encoding="utf-8") + "\nconst x = 'Real or noise?';\n", encoding="utf-8")
    r = subprocess.run([sys.executable, "checks/lint.py", str(planted)], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 1 and "flag:free_badges       /tools/index.html" in r.stdout, r.stdout[-1500:]
    assert "/static/js/tools/format.js" in r.stdout


@pytest.mark.parametrize("value", ['"false"', '"true"', "0", "1"])
def test_flag_must_be_a_toml_boolean(tmp_path, value):
    from test_legal import build
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    p = tmp_path / "s.toml"
    p.write_text(re.sub(r"(?m)^free_badges = false", f"free_badges = {value}", src), encoding="utf-8")
    r, _ = build(tmp_path, "o", DT_SITE_TOML=str(p))
    assert r.returncode == 1 and "free_badges" in r.stderr and "TOML boolean" in r.stderr, r.stderr


def test_missing_flag_means_off(tmp_path):
    from test_legal import build
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    p = tmp_path / "s.toml"
    p.write_text(re.sub(r"(?m)^free_badges = false.*\n", "", src), encoding="utf-8")
    r, out = build(tmp_path, "o", DT_SITE_TOML=str(p))
    assert r.returncode == 0, r.stderr
    assert not (out / "static" / "js" / "tools" / "trade-stats-badges.js").exists()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 1280])
def test_off_axe_and_overflow_with_results(browser, built_site, width, scheme):
    ctx, page, _ = _sample(browser, built_site, width, scheme)
    assert horizontal_overflow(page) == []
    assert axe_violations(page) == []
    ctx.close()
