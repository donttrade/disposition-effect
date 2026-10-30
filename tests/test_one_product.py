"""29 Oct 2026 (owner): one product, the donttrade test, in two packages (Traders $39 once; Firms $0.50 per trader
account a month, $500 minimum, the $745 Pilot as the first month, credited). Everything else is free.
Pins the Architect plan's acceptance checks for batches 1-5 on the live-config build (paid_report on)."""
import json
import os
import re
import sys
from urllib.parse import parse_qs

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import build as B  # noqa: E402
import lint as L  # noqa: E402
from harvest_prices import allowed_amounts, amounts_in  # noqa: E402

PRICES = json.load(open(os.path.join(REPO, "site", "config", "prices.json"), encoding="utf-8"))
TOOL_PAGES = ["/tools/trade-stats/", "/tools/trading-heatmap/", "/tools/drawdown-calculator/",
              "/tools/prop-challenge-simulator/", "/tools/lot-size-calculator/", "/tools/risk-reward-calculator/"]


def html(built_site, path):
    return (built_site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8") if path != "/" \
        else (built_site["out"] / "index.html").read_text(encoding="utf-8")


def text(h):
    h = re.sub(r"(?s)<script.*?</script>|<style.*?</style>|<dialog.*?</dialog>", " ", h)
    return " ".join(re.sub(r"<[^>]+>", " ", h).split())


def all_pages(built_site):
    for p in sorted(built_site["out"].rglob("*.html")):
        yield "/" + str(p.relative_to(built_site["out"])), p.read_text(encoding="utf-8")


# ------------------------------------------------------------------ names
def test_usd_renders_cents_and_whole_dollars():
    assert B.usd(0.5) == "$0.50" and B.usd(745) == "$745" and B.usd(2500) == "$2,500" and B.usd(39) == "$39"
    assert B.usd_fr(0.5) == "0,50 $ US" and B.usd_fr(39) == "39,00 $ US"
    assert amounts_in("<p>$0.50</p>") == [0.5] and 0.5 in allowed_amounts(PRICES) and 500 in allowed_amounts(PRICES)


def test_the_old_name_is_gone_except_the_dated_history(built_site):
    for path, h in all_pages(built_site):
        hits = re.findall(r"(?i)habit report", text(h))
        if path == "/corrections/index.html":
            continue   # the dated method entry and the dated rename line
        assert not hits, path
    for path, h in all_pages(built_site):
        if path.startswith("/fr/"):
            assert not re.search(r"(?i)rapport d.habitudes", text(h)), path


def test_one_visible_name_for_the_example_report(built_site):
    for path, h in all_pages(built_site):
        if path in ("/corrections/index.html",) or path.startswith("/research/"):
            continue   # the frozen corrections log and study bodies
        t = text(h)
        for bad in ("sample report", "Sample report", "sample result", "Sample result", "Example result",
                    "sample test result", "Sample test result"):
            assert bad not in t, (path, bad)
    t = text(html(built_site, "/sample-report/"))
    assert "Example report" in t
    assert "<title>Example report — donttrade</title>" in html(built_site, "/sample-report/")


def test_dt1_is_always_named_with_its_descriptor(built_site):
    for path, h in all_pages(built_site):
        t = text(h)
        for m in re.finditer(r"\bDT-\d+\b", t):
            win = t[max(0, m.start() - 250):m.end() + 250]
            assert "the donttrade test" in win.lower() or "test donttrade" in win.lower(), (path, win)
    assert "DT-1" in text(html(built_site, "/corrections/"))
    assert "Method DT-1 of the donttrade test, a habit test on your own trades" in text(html(built_site, "/sample-report/"))


# ------------------------------------------------------------------ /pricing/: two packages
def test_pricing_shows_two_packages_and_one_stripe_link(built_site):
    h = html(built_site, "/pricing/")
    main = re.search(r"(?s)<main.*?</main>", h).group(0)
    assert len(re.findall(r'<section class="price-card[^"]*"', main)) == 2
    t = text(main)
    assert "One test. Two ways to buy it." in t and "Traders" in t and "Firms" in t
    assert "$0.50 per trader account a month" in t and "$500 monthly minimum" in t
    assert "The $745 Pilot is your first month" in t and "Its $745 counts toward your plan’s invoices" in t
    assert "15% off when you pay a year upfront" in t and "credited" not in t   # 30 Oct (Tester #4): one reading only
    assert len(re.findall(r'href="https://buy\.stripe\.com/', main)) == 1
    firm = re.search(r'(?s)<section class="price-card" id="firms".*?</section>', main).group(0)
    assert "buy.stripe.com" not in firm and 'href="/for-firms/#request"' in firm
    for a in ("firms", "copy-leader", "claims-test", "platforms", "researchers", "payment", "traders", "refunds",
              "history", "questions", "last-step"):
        assert f'id="{a}"' in h, a


def test_no_study_figure_or_sample_figure_on_pricing(built_site):
    t = text(html(built_site, "/pricing/"))
    allowed = allowed_amounts(PRICES)
    assert all(a in allowed for a in amounts_in(t))
    assert "76.1%" not in t and "2,262" not in t


# ------------------------------------------------------------------ "Free for everyone"
@pytest.mark.parametrize("path,present", [("/pricing/", True), ("/", True), ("/tools/", True), ("/for-firms/", False)])
def test_free_strip_placement(built_site, path, present):
    h = html(built_site, path)
    m = re.search(r'(?s)<section class="free-strip".*?</section>', h)
    assert bool(m) == present
    if m:
        s = m.group(0)
        assert "Free for everyone" in s and 'class="btn' not in s and "$" not in s
        assert not re.search(r"\d", text(s))


def test_every_tool_points_to_the_one_test_with_the_same_words(built_site):
    seen = set()
    for path in TOOL_PAGES:
        a = re.search(r'(?s)<aside class="notice notice-gap next-step".*?<p class="btn-row">.*?</p>', html(built_site, path))
        assert a, path
        t = text(a.group(0))
        seen.add(t)
        assert t.startswith("Is this habit real, or luck?") and "Take the test — $39" in t
        assert set(amounts_in(t)) == {39.0}
    assert len(seen) == 1, seen


# ------------------------------------------------------------------ firms
def test_retired_products_and_amounts_are_gone(built_site):
    retired = set(PRICES["retired_amounts"]["amounts"])
    for path, h in all_pages(built_site):
        t = text(h)
        assert not [a for a in amounts_in(t) if a in retired], path
        if path not in ("/terms/index.html", "/help/index.html"):   # the dated withdrawal line (and its quote)
            assert not re.search(r"\bSnapshot\b|\bOutcomes pack\b|\bMemo\b", t), path
    terms = text(html(built_site, "/terms/"))
    assert "Fixed-price firm engagements (Snapshot, Memo, Outcomes pack) were withdrawn on" in terms


def test_for_firms_says_one_habit_today_and_no_same_test_claim(built_site):
    t = text(html(built_site, "/for-firms/"))
    assert "One habit today, more being added." in t
    assert "the same test" not in t.lower()
    assert "$0.50 per trader account a month" in t and "$500 minimum" in t


def test_start_has_two_firm_choices_and_old_anchors(built_site):
    h = html(built_site, "/start/")
    choose = h[h.index('class="choice-list"'):h.index("</ul>", h.index('class="choice-list"'))]
    assert re.findall(r'data-choice="([a-z]+)"', choose) == ["pilot", "plan"]
    for a in ("snapshot", "memo", "outcomes"):
        assert re.search(rf'<section class="choice" id="plan"[^>]*>\s*<span class="old-anchor" id="snapshot">', h)
        assert f'id="{a}"' in h


@pytest.mark.parametrize("js", [True, False])
def test_old_memo_link_lands_on_the_plan_form_and_posts_plan(browser, built_site, js):
    ctx = browser.new_context(java_script_enabled=js, viewport={"width": 390, "height": 900})
    pg = ctx.new_page()
    posted = []
    pg.route("https://api.web3forms.com/**", lambda route: (posted.append(route.request.post_data or ""),
                                                             route.fulfill(status=200, body="ok")))
    pg.goto(built_site["url"] + ("/start/?product=memo" if js else "/start/?product=memo#memo"))
    pg.wait_for_timeout(200)
    assert pg.is_visible("#sf-plan")
    pg.fill("#sf-plan input[type=email]", "test-ignore@example.org")
    pg.fill("#sf-plan input[name=firm]", "TEST - ignore")
    pg.click("#sf-plan button[type=submit]")
    pg.wait_for_timeout(300)
    ctx.close()
    body = {k: v[0] for k, v in parse_qs(posted[0], keep_blank_values=True).items()}
    assert body["product"] == "plan"


def test_for_firms_form_maps_old_products_to_the_plan(browser, built_site):
    ctx = browser.new_context()
    pg = ctx.new_page()
    for old in ("snapshot", "memo", "outcomes"):
        pg.goto(built_site["url"] + f"/for-firms/?product={old}#request")
        assert pg.input_value("#ff input[name=product]") == "plan", old
    ctx.close()


# ------------------------------------------------------------------ terms
def test_terms_plan_section_and_versions(built_site):
    t = text(html(built_site, "/terms/"))
    for s in ("$0.50 per trader account per month, with a minimum of $500 a month",
              "monthly in arrears, by email, in USD, due within 15 days of the invoice date",
              "It ends at the end of the calendar month in which notice is given.",
              "Its $745 counts toward your plan’s invoices: if the monthly plan starts within 60 days of Pilot delivery, the $745 is deducted once from the plan’s invoices, starting with the first, until it is used up.",
              "the donttrade test, a habit test on your own trades: a one-off measurement"):
        assert s in t, s
    assert "called “Trial” before 29 Oct 2026" in t


def test_word_budgets_on_new_strings(built_site):
    h = html(built_site, "/pricing/")
    assert len(re.sub(r"<[^>]+>", "", re.search(r"<h1>(.*?)</h1>", h).group(1)).split()) <= 8
    for v in re.findall(r'<p class="pc-value">(.*?)</p>', h):
        assert len(v.split()) <= 12, v
    for b in set(re.findall(r'class="btn[^"]*"[^>]*>([^<]+)</a>', h)) | set(re.findall(r'<summary class="btn">([^<]+)</summary>', h)):
        assert len(b.replace("—", "").split()) <= 4, b
    strip = text(re.search(r'(?s)<section class="free-strip".*?</section>', h).group(0))
    assert L.lint_text(strip) == []


# ------------------------------------------------------------------ the report in two layers (owner, 29 Oct)
@pytest.mark.parametrize("width", [1280, 390])
def test_example_report_shows_two_layers_and_never_described_or_not_tested(browser, built_site, width):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/sample-report/")
    pg.wait_for_selector("#sample-out .habit")
    t = pg.inner_text("main")
    for bad in ("described", "Described", "not tested", "Not tested", "Unusually large"):
        assert bad not in t, bad
    n = pg.locator("#sample-out .habit").count()
    assert n == 5
    assert pg.locator("#sample-out .habit .layer-what h4").count() == 5 and pg.locator("#sample-out .habit .layer-luck h4").count() == 3
    assert "Large losses" in t and "Luck check coming" in t and "unlikely to be luck" in t and "Not clear yet" in t
    # stats round 2: size after a loss keeps "Luck check coming"; the hold gap and large losses are "Your numbers", no pill
    sec = pg.locator("#habit-size_up")
    assert sec.locator(".badge-coming").inner_text() == "Luck check coming" and sec.locator(".luck-why summary").inner_text() == "Why not yet"
    why = sec.locator(".luck-why p").text_content()
    assert why.startswith("In our tests on files built to have no real pattern") and "described" not in why
    assert pg.locator("#your-numbers h2").inner_text() == "Your numbers"
    assert pg.locator("#your-numbers .yn-why p").text_content() == ("These are facts from your file. We have not found a fair way "
                                                                   "to test them against luck yet.")
    for hid in ("hold_gap", "oversized_loss"):
        s2 = pg.locator(f"#your-numbers #habit-{hid}")
        assert s2.count() == 1 and s2.locator(".badge").count() == 0 and s2.locator(".layer-luck").count() == 0
    assert pg.locator("#sample-out .badge-coming").count() == 1 + 1   # the size-up section and its summary row
    tested = pg.evaluate("[...document.querySelectorAll('#sample-out .habit')].map(s => s.id)")
    assert tested.index("habit-tilt") < tested.index("habit-hold_gap")   # the tested habits come first
    # print shows every folded part, then folds them back
    pg.evaluate("window.dispatchEvent(new Event('beforeprint'))")
    assert pg.locator("#sample-out details:not([open])").count() == 0
    pg.evaluate("window.dispatchEvent(new Event('afterprint'))")
    assert pg.locator("#sample-out .luck-why[open]").count() == 0
    ctx.close()


def test_plain_rewords_every_described_or_not_tested_line(browser, built_site):
    """Every wording.js line that says "described" or "not tested" (V-launch, V-launch-size, the dates-only and
    spread lines, NONE_TESTED) comes out of report.js's plain() without those words; wording.js is unchanged."""
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/sample-report/")
    pg.wait_for_selector("#sample-out .habit")
    out = pg.evaluate("""async () => {
      const r = await import('/static/js/paid/report.js'), w = await import('/static/js/paid/wording.js');
      const T = 'All 12 trades in this file';
      const lines = [w.V_LAUNCH, w.V_LAUNCH_SIZE, w.NONE_TESTED, w.V_SPREAD0, w.vDatesOnly(T), w.sizeNotDescribed(T), w.datesP1(T),
        'Not tested: the holds of your losing and winning trades are spread very differently (x).'];
      return lines.map((s) => [s, r.plain(s)]);
    }""")
    ctx.close()
    for before, after in out:
        assert not re.search(r"(?i)\bdescribed\b|\bnot tested\b", after), (before, after)
        assert re.search(r"(?i)described|not tested", before), before
        assert L.lint_text(after) == [] and L.lint_text(after, "shown", paid=True) == [], after   # incl. banned:retired_name


# ------------------------------------------------------------------ Tester #3 (30 Oct): CLS under 0.05
CLS_INIT = ("window.__cls = 0; new PerformanceObserver((l) => { for (const e of l.getEntries()) if (!e.hadRecentInput) "
            "window.__cls += e.value; }).observe({type: 'layout-shift', buffered: true});")


@pytest.mark.parametrize("path", ["/sample-report/", "/welcome/", "/welcome/?session_id=cs_test_cls"])
@pytest.mark.parametrize("width", [1280, 390])
def test_js_drawn_pages_do_not_shift(browser, built_site, path, width):
    ctx = browser.new_context(viewport={"width": width, "height": 900})
    ctx.add_init_script(CLS_INIT)
    ctx.route("https://donttrade-api*/**", lambda r: r.fulfill(status=200, content_type="application/json", body='{"token": "x.y.z"}'))
    pg = ctx.new_page()
    pg.goto(built_site["url"] + path)
    pg.wait_for_load_state("networkidle")
    pg.wait_for_timeout(800)
    cls = pg.evaluate("window.__cls")
    ctx.close()
    assert cls < 0.05, (path, width, cls)


def test_could_be_luck_label_never_returns():
    """30 Oct (owner): the inconclusive verdict reads "Not clear yet" ("not clear yet" mid-sentence), never
    "could be luck", in the templates, the site scripts or the built docs/."""
    hits = []
    for rel in ("site/templates", "site/static/js", "docs"):
        root = os.path.join(REPO, rel)
        assert os.path.isdir(root), rel
        for dp, _, fns in os.walk(root):
            for fn in fns:
                p = os.path.join(dp, fn)
                try:
                    s = open(p, encoding="utf-8").read()
                except (UnicodeDecodeError, OSError):
                    continue
                if re.search(r"could\s+be\s+luck", s, re.I):
                    hits.append(os.path.relpath(p, REPO))
    assert hits == [], hits
