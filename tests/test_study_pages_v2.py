"""Study-page improvements (7 Nov 2026, RESEARCH-IMPROVE-STUDY-PAGES): the lead chart, the per-study share card, chart downloads,
the feed and press page, the email box, the journalists block and the study pages without the pay dialog.
Items are added one commit at a time; each section below is headed by its item."""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import selloff as SO  # noqa: E402
from a11y import axe_violations  # noqa: E402

S = "/research/5-november-2026-sell-off/"


def page(site, path):
    return open(os.path.join(site["out"], path.strip("/"), "index.html"), encoding="utf-8").read()


def figure(h, fid):
    m = re.search(r'(?s)<figure class="chart sell-chart[^"]*" id="' + fid + r'".*?</figure>', h)
    assert m, fid
    return m.group(0)


# ------------------------------------------------------------------ item 1: the lead chart under the key numbers
def test_lead_chart_sits_directly_under_the_key_numbers(built_site):
    h = page(built_site, S)
    keys = h.index('id="sell-keys-h"')
    lead = h.index('id="fig-hip3-daily"')
    assert keys < lead < h.index('id="sell-what-h"')
    between = h[h.index("</dl>", keys):lead]
    assert len(re.findall(r"<h[1-6]", between)) == 0       # nothing but the scope line stands between them
    assert h.count('id="fig-hip3-daily"') == 1


def test_every_chart_title_states_its_finding_and_the_source_is_inside_the_svg(built_site):
    h = page(built_site, S)
    F = SO.context()["F"]
    titles = {"fig-hip3-daily": [F["hip3"], "most of 31 days"], "fig-all-daily": [F["wallets"], "near-tie"],
              "fig-hourly": [F["session_share"], "US stock-market hours"]}
    for fid, needles in titles.items():
        fig = figure(h, fid)
        title = re.search(r'<p class="fig-title">(.*?)</p>', fig).group(1)
        assert all(n in title for n in needles), (fid, title)
        svg = re.search(r"(?s)<svg.*?</svg>", fig).group(0)
        assert "Source: Ironflow" in svg and SO.PAGE_URL in svg, fid          # printed inside the drawing
        assert "<script" not in fig and "style=" not in fig


# 7 Nov (D3): 1.6 became 1.65: "Updated 7 November 2026" in the meta line adds a line on a phone (the limit that matters is 2 screens)
@pytest.mark.parametrize("width,height,limit", [(390, 844, 1.65), (1440, 900, 1.0)])
def test_lead_chart_starts_in_the_first_screens(browser, built_site, width, height, limit):
    pg = browser.new_page(viewport={"width": width, "height": height})
    pg.goto(built_site["url"] + S)
    top = pg.evaluate("() => document.getElementById('fig-hip3-daily').getBoundingClientRect().top / innerHeight")
    assert top <= limit, top
    pg.close()


@pytest.mark.parametrize("width,height", [(390, 844), (1280, 800)])
def test_study_page_axe(browser, built_site, width, height):
    ctx = browser.new_context(viewport={"width": width, "height": height}, bypass_csp=True)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + S)
    assert axe_violations(pg) == []
    ctx.close()


# ------------------------------------------------------------------ the chart licence (7 Nov 2026: owner approved CC BY 4.0 for charts)
def test_chart_licence_is_cc_by_in_every_image_and_the_text_stays_non_commercial(built_site):
    h = page(built_site, S)
    assert SO.CHART_CREDIT == "Chart: donttrade.ca (CC BY 4.0)"
    for fid in ("fig-hip3-daily", "fig-all-daily", "fig-hourly"):
        assert SO.CHART_CREDIT in figure(h, fid)
    assert "Text: CC BY-NC 4.0. Charts, counts and code: CC BY 4.0." in h
    assert "Chart: donttrade, CC BY-NC" not in h


# ------------------------------------------------------------------ item 2: the per-study share card
def test_og_card_exists_is_referenced_and_has_its_own_alt(built_site):
    from PIL import Image
    f = os.path.join(REPO, "docs", "assets", "og", "selloff.png")
    assert os.path.getsize(f) <= 300 * 1024
    assert Image.open(f).size == (1200, 630)
    assert os.path.exists(os.path.join(built_site["out"], "assets", "og", "selloff.png"))
    h = page(built_site, S)
    assert '<meta property="og:image" content="https://donttrade.ca/assets/og/selloff.png">' in h
    alt = SO.short_title(SO.context()["F"]).rstrip(".") + ". Bar chart of 31 days."
    assert f'<meta property="og:image:alt" content="{alt}">' in h and f'<meta name="twitter:image:alt" content="{alt}">' in h
    assert "wallets" in alt and "$" not in alt


def test_og_card_source_holds_no_price_or_offer():
    import make_study_assets as M
    doc = M.card_html("Study · 6 Nov 2026 · wallets, not people", SO.short_title(SO.context()["F"]), "<svg></svg>", "Data: Ironflow, CC BY 4.0")
    low = doc.lower()
    assert "$" not in doc and "us$" not in low and "pricing" not in low and not re.search(r"\btests?\b", low)
    assert "<script" not in low


# ------------------------------------------------------------------ item 3: chart downloads and permalinks
FIGS = ("fig-hip3-daily", "fig-all-daily", "fig-hourly")


def test_each_chart_has_png_svg_csv_and_a_permalink_that_resolve(built_site):
    h = page(built_site, S)
    for fid in FIGS:
        fig = figure(h, fid)
        links = re.findall(r'<li><a href="([^"]+)"( download)?>([^<]+)</a></li>', fig.split('class="fig-tools"')[1])
        assert [l[2] for l in links] == ["PNG image", "SVG", "Data (CSV)", "Link to this chart"], fid
        for href, dl, _ in links[:3]:
            assert dl and os.path.exists(os.path.join(built_site["out"], href.lstrip("/"))), href
        assert links[3][0] == "#" + fid and h.count(f'id="{fid}"') == 1


def test_chart_svg_is_self_contained_and_carries_title_source_url_and_licence(built_site):
    ctx = SO.context()
    for fg in ctx["figs"]:
        svg = open(os.path.join(built_site["out"], "assets", "charts", "selloff", fg["id"] + ".svg"), encoding="utf-8").read()
        assert fg["title"].replace("&", "&amp;") in svg and "Source: Ironflow" in svg and SO.PAGE_URL in svg and SO.CHART_CREDIT in svg
        assert not re.search(r"<style|<script|href=|url\(|var\(|style=", svg)       # no CSS, no script, no external reference
        assert "role=\"img\"" in svg and "<desc" in svg
        import xml.dom.minidom
        xml.dom.minidom.parseString(svg)


def test_chart_png_matches_its_svg_and_is_the_right_size(built_site):
    from PIL import Image
    d = os.path.join(REPO, "docs", "assets", "charts", "selloff")
    import hashlib
    for fg in SO.context()["figs"]:
        png = os.path.join(d, fg["id"] + ".png")
        svg = open(os.path.join(built_site["out"], "assets", "charts", "selloff", fg["id"] + ".svg"), "rb").read()
        assert open(os.path.join(d, fg["id"] + ".src.sha256")).read().strip() == hashlib.sha256(svg).hexdigest(), \
            f"{fg['id']}: the chart changed; run python3 checks/make_study_assets.py --study selloff"
        w, hgt = Image.open(png).size
        m = re.search(rb'viewBox="0 0 (\d+) (\d+)"', svg)
        assert (w, hgt) == (2 * int(m.group(1)), 2 * int(m.group(2)))
        assert os.path.getsize(png) <= 350 * 1024


def test_hourly_csv_is_the_chart_data(built_site):
    import csv
    rows = list(csv.DictReader(open(os.path.join(built_site["out"], "data", "5-november-2026-hyperliquid-hourly.csv"), encoding="utf-8")))
    assert [r["hour_utc"] for r in rows] == [f"{k:02d}" for k in range(24)]
    data = SO.load()["event"]["hourly"]
    for r, h in zip(rows, data):
        if h["suppressed"]:
            assert r["value_force_closed_usd"] == "" and r["wallets_force_closed"] == "" and "fewer than 10" in r["note"]
        else:
            assert float(r["value_force_closed_usd"]) == round(h["value"], 2) and int(r["wallets_force_closed"]) == h["wallets"]


def test_chart_download_row_has_big_targets(browser, built_site):
    pg = browser.new_page(viewport={"width": 390, "height": 844})
    pg.goto(built_site["url"] + S)
    boxes = pg.locator("#fig-hip3-daily .fig-tools a").evaluate_all("els => els.map(e => e.getBoundingClientRect().height)")
    assert len(boxes) == 4 and all(b >= 44 for b in boxes)
    pg.close()


# ------------------------------------------------------------------ item 4: feed, press page, sitemap, dates
def text_of(path, site):
    return open(os.path.join(site["out"], path), encoding="utf-8").read()


def test_feed_has_the_sell_off_entry_once_and_keeps_every_older_entry(built_site):
    feed = text_of("feed.xml", built_site)
    eid = "tag:donttrade.github.io,2026-11-06:study/research/5-november-2026-sell-off/"
    assert feed.count(eid) == 1 and feed.count("<entry>") == 14        # the 13 entries of docs/feed.xml and this one
    old = open(os.path.join(REPO, "docs", "feed.xml"), encoding="utf-8").read()
    assert old.count("<entry>") in (13, 14)
    m = re.search(r"(?s)<entry>\s*<title>([^<]*)</title>\s*<id>" + re.escape(eid) + r"</id>.*?<published>([^<]+)</published>\s*<updated>([^<]+)</updated>", feed)
    assert m and SO.short_title(SO.context()["F"]) in m.group(1)
    assert m.group(2) == "2026-11-06T00:00:00Z" and m.group(3) == "2026-11-07T00:00:00Z"
    assert "<updated>2026-11-07T00:00:00Z</updated>\n  <author>" in feed
    entry = re.search(r"(?s)<entry>\s*<title>Study: " + re.escape(SO.short_title(SO.context()["F"])) + r".*?</entry>", feed).group(0)
    assert "$" not in entry and "pricing" not in entry.lower() and "wallets, not people" in entry


def test_press_page_lists_the_study_and_its_files(built_site):
    h = page(built_site, "/for-researchers/")
    main = h[h.index("<main"):h.index("</main>")]
    assert f'href="{S}"' in main
    for href in (SO.CSV_PATH, SO.HOURLY_CSV_PATH, SO.PM_CSV_PATH, "/data/5-november-2026-per-market.csv"):
        assert f'href="{href}"' in main and os.path.exists(os.path.join(built_site["out"], href.lstrip("/"))), href
    assert "except those of the 5 Nov 2026 study, which are CC BY 4.0" in main
    assert main.count("<!--island:start-->") == 2


def test_sitemap_lastmod_and_article_dates_follow_the_content_date(built_site):
    sm = text_of("sitemap.xml", built_site)
    assert f"<loc>https://donttrade.ca{S}</loc><lastmod>2026-11-07</lastmod>" in sm
    assert "<loc>https://donttrade.ca/for-researchers/</loc><lastmod>2026-11-07</lastmod>" in sm
    assert "<loc>https://donttrade.ca/research/disposition-effect/</loc><lastmod>2026-11-06</lastmod>" in sm   # unchanged pages keep theirs
    h = page(built_site, S)
    assert '<meta property="og:type" content="article">' in h
    assert '<meta property="article:published_time" content="2026-11-06">' in h and '<meta property="article:modified_time" content="2026-11-07">' in h
    ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', h, re.S).group(1))
    art = next(n for n in ld["@graph"] if "ScholarlyArticle" in (n["@type"] if isinstance(n["@type"], list) else [n["@type"]]))
    assert art["dateModified"] == "2026-11-07" and art["datePublished"] == "2026-11-06"
    assert "identifier" not in art and "sameAs" not in art        # the owner uploads the DOI later: a missing DOI is accepted
    assert "doi.org/10.5281" not in h


def test_no_page_is_dated_after_the_machine_date():
    import build as B
    assert B.future_dated(B.load_config()[0]) == []


# ------------------------------------------------------------------ item 5: the email box at the end of each study
LIFTED_STUDIES = ["/research/disposition-effect/", "/research/insider-buying-edge/", "/research/portfolio-driven-disposition-effect/",
                  "/research/strategy-tests/", "/research/swing-trading-strategies/", "/research/volatility-scaled-momentum/"]


def test_sell_off_study_ends_with_the_substack_box_and_allows_only_that_form_host(built_site):
    h = page(built_site, S)
    box = re.search(r'(?s)<section class="sell-sec study-subscribe".*?</section>', h).group(0)
    assert 'action="https://donttrade.substack.com/subscribe" method="get"' in box and 'type="email"' in box and "required" in box
    assert h.index('id="sell-own-h"') < h.index('id="sell-mail-h"') < h.index('id="sell-refs-h"')
    assert not re.search(r"\$|US\$|price|pricing|buy|\d", re.sub(r"<[^>]+>", " ", box)), box     # the words and numbers of the box: none is a price or a figure
    import html as _html
    csp = _html.unescape(re.search(r'Content-Security-Policy" content="([^"]+)"', h).group(1))
    assert re.search(r"form-action [^;]*https://donttrade\.substack\.com", csp) and "script-src 'self' https://static" in csp
    assert "style=" not in box and "<script" not in box


@pytest.mark.parametrize("path", LIFTED_STUDIES)
def test_older_studies_already_end_with_the_same_box(built_site, path):
    h = page(built_site, path)
    body = h[h.index("<main"):h.index("</main>")]
    i = body.index('action="https://donttrade.substack.com/subscribe"')
    assert "Email me the next study" in body[i:i + 600] and len(body) - i < 2000      # the study's last block, not a footer link


# ------------------------------------------------------------------ item 6: for journalists
def test_for_journalists_block_has_facts_files_and_contact(built_site):
    h = page(built_site, S)
    sec = re.search(r'(?s)<section class="sell-sec" id="press".*?</section>', h).group(0)
    P = SO.context()["press"]
    import html as _html
    txt = _html.unescape(sec)
    for q in P["quotable"] + P["notes"] + [P["summary"]]:
        assert q in txt, q
    assert "A wallet is an address, not a person" in P["summary"]
    assert 'mailto:research@donttrade.ca?subject=Press' in sec and ">research@donttrade.ca<" in sec
    assert 'href="/assets/press/selloff.zip" download' in sec
    for fid in FIGS:
        for ext in ("png", "svg"):
            assert f'href="/assets/charts/selloff/{fid}.{ext}" download' in sec
    for href in re.findall(r'href="(/[^"#]+)"', sec):
        assert os.path.exists(os.path.join(built_site["out"], href.lstrip("/"))), href
    assert h.index('id="sell-own-h"') < h.index('id="press"') < h.index('id="sell-mail-h"')
    assert "Chart: donttrade.ca (CC BY 4.0)" in sec
    assert "$" not in sec and "pricing" not in sec.lower() and "/pricing/" not in sec


def test_press_facts_use_only_numbers_the_page_already_prints(built_site):
    h = page(built_site, S)
    key = h[h.index('id="sell-keys-h"'):h.index('id="sell-what-h"')]
    key_text = re.sub(r"<[^>]+>", " ", key)
    import html as _html
    key_text = _html.unescape(key_text)
    P = SO.context()["press"]
    for q in P["quotable"] + [P["summary"]]:
        for tok in re.findall(r"\d[\d,.]*%?", q):
            tok = tok.rstrip(".,")
            if tok in ("2026", "5", "30", "31", "15"):      # the date, the day counts and the 15-minute window
                continue
            assert tok in key_text, (tok, q)


def test_press_zip_holds_the_files_and_they_are_the_published_ones(built_site):
    import zipfile
    zf = zipfile.ZipFile(os.path.join(REPO, "docs", "assets", "press", "selloff.zip"))
    assert zf.testzip() is None
    assert sorted(zf.namelist()) == sorted(SO.PRESS_ZIP_FILES)
    assert os.path.getsize(os.path.join(REPO, "docs", "assets", "press", "selloff.zip")) <= 5 * 1024 * 1024
    ctx = SO.context()
    readme, one = SO.press_texts(ctx, "https://donttrade.ca")
    assert zf.read("README.txt").decode() == readme and zf.read("ONE-PAGE-SUMMARY.txt").decode() == one
    assert "Chart: donttrade.ca (CC BY 4.0)" in readme and "Study text: CC BY-NC 4.0" in readme
    assert len(one.splitlines()) <= 40 and "research@donttrade.ca" in one
    for name in ("5-november-2026-hyperliquid-daily.csv", "5-november-2026-hyperliquid-hourly.csv", "5-november-2026-per-market.csv"):
        assert zf.read("data/" + name) == open(os.path.join(built_site["out"], "data", name), "rb").read(), name
    for fg in ctx["figs"]:
        assert zf.read(f"charts/{fg['id']}.png") == open(os.path.join(REPO, "docs", "assets", "charts", "selloff", fg["id"] + ".png"), "rb").read()
    assert zf.read("ANALYSIS-PLAN.md") == open(os.path.join(SO.PACK_DIR, "ANALYSIS-PLAN.md"), "rb").read()
    assert ctx["plan_sha"] in readme
    assert "pricing" not in (readme + one).lower() and "$" not in readme + one
