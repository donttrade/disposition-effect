"""Free-check batch G guards (ARCHITECT-PLAN-FREE-CHECK-AND-HOOK-2026-11-07, section 6, batch G).

The free pages count habits; the dollar total of a habit and its test against chance are the report's. Held here:
  1. trade-stats, the bad-day check and the Challenge Readiness Check show no dollar figure next to any of the five habits,
     on a real fixture file, through the real pages;
  2. free_badges stays off while the paid report holds a habit the free pages must not badge (the build refuses it);
  3. /check/ is linked from the home hero (as the primary button, with the report beside it), the pricing card (with the free-check-first
     line) and the tool next-step box, and is NOT linked inside the /tools/ index <main>, whose gzip budget is 12,544 B;
  4. the footer hook line, the pricing scope line and the home title and description of a build with the report on sale.
"""
import gzip
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
from test_free_check import csvs, open_page  # noqa: E402,F401  (csvs is a fixture)

HABIT = re.compile(r"re-?enter|revenge|after (a |2 or more |two or more )?(losing )?(run|streak|loss)|size after|bigger size|held (losers |losing trades )?longer|hold gap|oversized|large loss|losses over", re.I)
MONEY = re.compile(r"[$€£¥]|\b(?:USD|CAD|EUR|GBP|dollars?)\b|\d\.\d\d\b|\d,\d{3}\b")


def html(site, path):
    return (site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")


def main_of(h):
    return h.split("<main", 1)[-1].split("</main>")[0]


# ------------------------------------------------------------------ 3, 4: where /check/ is linked

def test_the_home_hero_leads_with_the_free_check_and_keeps_the_report_beside_it(built_site):
    h = html(built_site, "/") if False else (built_site["out"] / "index.html").read_text(encoding="utf-8")
    hero = re.search(r'(?s)<h1 id="hero">.*?<p class="small">', h).group(0)
    btns = re.findall(r'<a class="btn" href="([^"]+)"[^>]*>([^<]+)</a>', hero)
    assert btns == [("/check/", "Check my trades free")], btns                       # one primary button
    assert re.search(r'<a href="/pricing/#last-step">Get the report for \$\d+</a>', hero)   # the report is the text link beside it
    assert "Check your trade file free" in hero


def test_the_home_title_and_description_when_the_report_is_on_sale(built_site):
    h = (built_site["out"] / "index.html").read_text(encoding="utf-8")
    assert "<title>The Revenge Trading Report and free check · donttrade</title>" in h
    assert 'content="Revenge trading, measured in your own trades. Free check in your browser;' in h


def test_the_pricing_card_names_the_report_gives_the_scope_and_sends_the_visitor_to_the_check_first(built_site):
    h = html(built_site, "/pricing/")
    assert re.search(r'<h2 id="pc-report-h">The Revenge Trading Report</h2>', h)
    assert re.search(r'<p class="pc-scope">Re-entering after a loss and trading after a losing run, tested against chance, plus three more habits around losses, totalled in dollars\.</p>', h)
    assert re.search(r'<a href="/check/">Run the free check first</a>', h)


@pytest.mark.parametrize("path", ["/tools/trade-stats/", "/tools/bad-day-check/", "/tools/prop-challenge-simulator/"])
def test_the_tool_next_step_links_to_the_check(built_site, path):
    h = html(built_site, path)
    aside = re.search(r'(?s)<aside class="notice notice-gap next-step".*?</aside>', h).group(0)
    assert '<a href="/check/">Check my trades free</a>' in aside and aside.count("/pricing/#last-step") == 1


def test_the_footer_carries_the_hook_line_on_every_paid_page(built_site):
    for path in ("/", "/pricing/", "/check/", "/tools/"):
        h = (built_site["out"] / path.strip("/") / "index.html") if path != "/" else built_site["out"] / "index.html"
        assert "Revenge trading, measured in your own trades.</p>" in h.read_text(encoding="utf-8").split("<footer", 1)[-1], path


def test_the_tools_index_main_holds_no_link_to_the_check_and_stays_in_its_gzip_budget(built_site):
    m = main_of(html(built_site, "/tools/"))
    assert "/check/" not in m
    assert len(gzip.compress(m.encode("utf-8"), 9)) <= 12544, len(gzip.compress(m.encode("utf-8"), 9))


# ------------------------------------------------------------------ 2: the badges flag

def test_free_badges_cannot_be_turned_on_while_the_paid_report_holds_the_hold_gap():
    import build as B
    assert "hold_gap" in B.PAID_ONLY_HABITS
    assert B.leak_guard_problem({"free_badges": True, "paid_report": True}) and "hold_gap" in B.leak_guard_problem({"free_badges": True, "paid_report": True})
    assert B.leak_guard_problem({"free_badges": False, "paid_report": True}) is None
    # the one narrow test-suite escape is not an exit for a real build: a real build has no DT_OUT scratch directory with the variable set
    assert B.leak_guard_problem({"free_badges": True, "paid_report": True}, test_build=False)
    assert B.leak_guard_problem({"free_badges": True, "paid_report": True}, test_build=True) is None
    src = open(os.path.join(REPO, "site", "build.py"), encoding="utf-8").read()
    assert "problem = leak_guard_problem(flags, " in src                              # the build calls it, so the refusal is real


# ------------------------------------------------------------------ 1: no per-habit dollar figure on the free tools

def blocks(pg, root):
    return pg.eval_on_selector_all(f"{root} tr, {root} li, {root} p, {root} dd, {root} figcaption, {root} summary, {root} h3, {root} h4",
                                   "els => els.map(e => e.innerText.replace(/\\s+/g, ' ').trim())")


def bad(texts):
    return [t for t in texts if HABIT.search(t) and MONEY.search(t)]


def test_trade_stats_shows_no_habit_dollar_figure(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site, bypass_csp=True)
    pg.goto(built_site["url"] + "/tools/trade-stats/")
    pg.set_input_files("#ts-file", csvs["plain"])
    pg.wait_for_selector("#ts-out:not([hidden])", timeout=90000)
    pg.wait_for_timeout(1500)
    t = blocks(pg, "#ts-out")
    assert len(t) > 5 and bad(t) == [], bad(t)
    ctx.close()


def test_bad_day_check_shows_no_habit_dollar_figure(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site, bypass_csp=True)
    pg.goto(built_site["url"] + "/tools/bad-day-check/")
    pg.set_input_files("#bd-file", csvs["plain"])
    pg.wait_for_selector("#bd-out:not([hidden])", timeout=90000)
    t = blocks(pg, "#bd-out")
    assert len(t) > 3 and bad(t) == [], bad(t)
    ctx.close()


def test_challenge_readiness_check_shows_no_habit_dollar_figure(browser, built_site, csvs):
    ctx, pg, log = open_page(browser, built_site, bypass_csp=True)
    pg.goto(built_site["url"] + "/tools/prop-challenge-simulator/")
    for sel, v in {"#ps-account": "10000", "#ps-target": "300", "#ps-daily": "40", "#ps-maxloss": "300", "#ps-days": "60"}.items():
        pg.fill(sel, v)
    pg.set_input_files("#ps-file", csvs["plain"])
    pg.wait_for_selector("#ps-file-status:text-matches('^Read ')", timeout=90000)
    pg.click("#ps-run")
    pg.wait_for_selector("#ps-out:not([hidden])", timeout=90000)
    t = blocks(pg, "#ps-out") + blocks(pg, "#ps-whatif")
    assert len(t) > 3 and bad(t) == [], bad(t)
    ctx.close()


def test_the_detector_has_teeth():
    assert bad(["Re-entering within 15 minutes of a loss: 38 trades, 120.50 in total"])
    assert bad(["Trading after a losing run: $412"])
    assert bad(["Losses over 2 times your median loss: 14 trades"]) == []          # a count is fine
    assert bad(["Longest losing streak 6 trades, −168.43 pts"]) == []             # a streak is not one of the five habits
