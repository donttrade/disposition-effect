"""v3 home (ARCHITECT-V3 §c.3-§c.4, steps A5-A6): Tester invariants H1-H10 (H11-H13 come with step H1,
the hero calendar). Traders first, the firm door on the first screen, free tools, research, a no-offer
buffer, the value ladder (no firm price on home), for firms, questions, latest.
"""
import json
import os
import re
import sys

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import build as B  # noqa: E402
import lint as L  # noqa: E402

PRICES = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))


def _home(site):
    return (site["out"] / "index.html").read_text(encoding="utf-8")


def _main(html):
    return re.search(r"(?s)<main[^>]*>(.*)</main>", html).group(1)


def _sections(html):
    return re.findall(r"(?s)<section\b.*?</section>", _main(html))


def _text(fragment):
    return " ".join(L.visible_text(fragment).split())


# ------------------------------------------------------------------ H1: both doors on the first screen
@pytest.mark.parametrize("vp", [{"width": 1280, "height": 800}, {"width": 375, "height": 812}], ids=["1280", "375"])
def test_h1_trader_and_firm_doors_on_the_first_screen(browser, built_site, vp):
    for kw in ({}, {"java_script_enabled": False}):
        ctx = browser.new_context(viewport=vp, **kw)
        pg = ctx.new_page()
        pg.goto(built_site["url"] + "/")
        for sel in ("main a.btn[href='/tools/trade-stats/']", "main .firm-door a[href='/start/?product=pilot#pilot']"):
            box = pg.locator(sel).first.bounding_box()
            assert box and box["y"] + box["height"] <= vp["height"], (sel, box)
        assert pg.locator("main .firm-door a", has_text="Start a Pilot").count() == 1
        ctx.close()


# ------------------------------------------------------------------ H2: no firm price on home
def test_h2_no_firm_price_and_the_39_only_as_founding_waitlist(built_site):
    html = _home(built_site)
    text = _text(_main(html))
    for p in PRICES["products"]:
        if p["audience"] == "firm":
            assert B.usd(p["price_usd"]) not in html, p["id"]
    r = next(p for p in PRICES["products"] if p["id"] == "report39")
    for m in re.finditer(re.escape(B.usd(r["price_usd"])), text):
        around = text[max(0, m.start() - 80):m.end() + 120].lower()
        assert "founding price" in around and "waitlist" in around, around


# ------------------------------------------------------------------ H3, H4: order and the finding's neighbours
def test_h3_h4_order_and_the_finding_has_quiet_neighbours(built_site):
    html = _home(built_site)
    secs = _sections(html)
    ids = [re.search(r'aria-labelledby="([^"]+)"', s).group(1) for s in secs]
    assert ids == ["hero", "tools-h", "finding-h", "trust-h", "ladder-h", "how-h", "faq-h", "latest-h"]
    i = ids.index("finding-h")
    ev = B.evidence()
    for s in (secs[i - 1], secs[i + 1]):
        t = _text(s)
        assert 'class="btn' not in s and "$" not in t and ev["finding"]["pct"] not in t and "%" not in t, t[:200]
        assert "Start a Pilot" not in t and "waitlist" not in t.lower()
    # the only finding on the page is in the research section
    assert _text(_main(html)).count(ev["finding"]["pct"]) == 1


# ------------------------------------------------------------------ H5, H6: the value ladder
def test_h5_ladder_wording(built_site):
    secs = {re.search(r'aria-labelledby="([^"]+)"', s).group(1): s for s in _sections(_home(built_site))}
    t = _text(secs["ladder-h"])
    assert "do not tell you what to trade" in t
    assert L.lint_text(t, "ladder") == []
    for bad in ("improve", "better results", "make you", "become", "profitable", "free forever"):
        assert bad not in t.lower(), bad   # journal off: no "free forever" anywhere


def test_h6_ladder_firm_price_on_pricing_only(built_site):
    pilot = next(p for p in PRICES["products"] if p["id"] == "pilot")
    pricing = (built_site["out"] / "pricing" / "index.html").read_text(encoding="utf-8")
    lad = re.search(r'(?s)<section class="section ladder".*?</section>', pricing).group(0)
    plan = next(p for p in PRICES["products"] if p["id"] == "plan")   # 29 Oct (one product)
    assert f"{B.usd(plan['minimum_usd'])}</span> a month" in lad and "Snapshot" not in lad
    home = re.search(r'(?s)<section class="section ladder".*?</section>', _home(built_site)).group(0)
    assert B.usd(pilot["price_usd"]) not in home and "For firms: the test on your whole book" in home


def test_h5_free_forever_lint_rule():
    assert L.free_forever_claims("Every tool here is free forever.", "x")
    assert L.free_forever_claims("The journal is free forever.", "x")   # without its reason
    assert L.free_forever_claims("The journal is free forever: it runs on your device, so it costs us nothing to run.", "x") == []


# ------------------------------------------------------------------ H7: Latest band from its sources
def test_h7_latest_dates_equal_their_sources(built_site):
    secs = {re.search(r'aria-labelledby="([^"]+)"', s).group(1): s for s in _sections(_home(built_site))}
    band = secs["latest-h"]
    lt = B.latest()
    # newest study: the max datePublished of the research pages
    arts = []
    for name in os.listdir(B.LIFTED_DIR):
        if name.startswith("research_") and name.endswith(".json"):
            m = json.load(open(os.path.join(B.LIFTED_DIR, name), encoding="utf-8"))
            arts.append((m["article"]["datePublished"], m["path"]))
    d, url = max(arts)
    assert lt["study"]["url"] == url and lt["study"]["date"] == B.human_date(d)
    assert f'<span class="when">{lt["study"]["date"]}</span>' in band and f'href="{url}"' in band
    # newest correction: the latest date in the /corrections/ table
    corr = (built_site["out"] / "corrections" / "index.html").read_text(encoding="utf-8")
    # merge into delivery-39 (24 Oct): only the log's own table (the first one in the frozen body); the habit
    # report's method-versions table sits after <!--frozen:end--> and is not the corrections log
    corr = re.search(r"(?s)<!--frozen:start-->.*?<table.*?</table>", corr).group(0)
    dates = re.findall(r"<tr><td>(\d{1,2} [A-Z][a-z]{2} \d{4})</td>", corr)
    import datetime as dt
    newest = max(dates, key=lambda x: dt.datetime.strptime(x, "%d %b %Y"))
    assert lt["correction"]["date"] == newest and f'<span class="when">{newest}</span>' in band
    if lt["commit"] and lt["commit"]["url"]:
        assert re.fullmatch(r"https://github\.com/donttrade/disposition-effect/commit/[0-9a-f]{40}", lt["commit"]["url"])
        assert f'href="{lt["commit"]["url"]}"' in band
    elif lt["commit"]:   # brand Tester D5: a commit on no remote branch is named, never linked
        assert "/commit/" not in band and f'<code>{lt["commit"]["short"]}</code>' in band


# ------------------------------------------------------------------ H8: no new animation kinds on home
def test_h8_no_looping_or_rotating_motion_on_home(browser, built_site):
    ctx = browser.new_context(viewport={"width": 1280, "height": 800})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    names = set()
    for _ in range(20):
        names |= set(pg.evaluate("() => document.getAnimations().map(a => a.animationName || a.transitionProperty)"))
        pg.mouse.wheel(0, 400)
        pg.wait_for_timeout(80)
    pg.wait_for_timeout(1500)
    assert names <= {"dt-wipe", "opacity", "transform"}, names
    assert pg.evaluate("document.getAnimations().filter(a => a.effect.getComputedTiming().iterations !== 1).length") == 0
    ctx.close()


# ------------------------------------------------------------------ H10: the comparison row follows the journal flag
def test_h10_comparison_row_follows_the_journal_flag(tmp_path, built_site):
    assert 'id="cmp-h"' not in _home(built_site)
    off = _text((built_site["out"] / "for-traders" / "index.html").read_text(encoding="utf-8"))
    assert "No: it reads the export your platform already makes" in off
    from test_legal import build, toml_with
    r, out = build(tmp_path, "j", DT_SITE_TOML=toml_with(tmp_path, journal=True))
    assert r.returncode == 0, r.stderr
    on = (out / "for-traders" / "index.html").read_text(encoding="utf-8")
    t = _text(on)
    assert "No: it reads the export" not in t and "the free journal keeps them in your browser" in t
    lad = _text(re.search(r'(?s)<section class="section ladder".*?</section>', on).group(0))
    assert "The journal is free forever" in lad and "costs us nothing to run" in lad
    assert L.free_forever_claims(lad, "ladder") == []
