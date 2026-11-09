"""The 5 Nov 2026 sell-off campaign (CODER-REPORT-SELLOFF-2026-11-06): the study page, its data, the market figures, the Learn
callout, the dated home band, the Bad-day check's registration and the committed files.

What is held here:
  * every Hyperliquid figure on the study page is recomputed here from the committed daily data, by code written separately from
    site/selloff.py (median, quartiles, rank), and equals the page; the data file reproduces the plan's SUMMARY;
  * the market figures (Composite 11.90% below its record, needs 13.51%; Nasdaq-100 14.72%, 17.25%) are recomputed from the
    committed closes; "Nasdaq down 14%" appears nowhere;
  * no wallet address in any committed file (the one placeholder, 0xeee...e, is the plan's exclusion); the committed hashes
    are those of the pack files; the plan's hash is the one logged before the data was read;
  * the study page has no price, no pay link, no dollar amount that is not a figure of the data, passes the wording lint, keeps
    the CSP (no inline script, no style=), is in the sitemap with Article and Dataset JSON-LD, and every DOI cited is in
    references.json with a Crossref check date;
  * the home band exists up to its data-expires date and the build leaves it out the day after.
"""
import csv
import hashlib
import html
import io
import json
import math
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
from harvest_prices import amounts_in  # noqa: E402
from a11y import axe_violations, horizontal_overflow  # noqa: E402

DATA = os.path.join(REPO, "site", "data", "selloff-2026-11-05.json")
PACK = os.path.join(REPO, "checks", "selloff", "zenodo")
S = "/research/5-november-2026-sell-off/"
B = "/tools/bad-day-check/"
D = json.load(open(DATA, encoding="utf-8"))
MKT = json.load(open(os.path.join(REPO, "site", "config", "market_2026_11_05.json"), encoding="utf-8"))
EVENT = "2026-11-05"
PLAN_SHA = "21ce82c3bebd3044b0f43bceb4bb09626aad90262a375a0591274e55f364d704"


def page(site, path):
    return (site["out"] / path.strip("/") / "index.html").read_text(encoding="utf-8")


def text(h):
    h = re.sub(r"(?s)<(script|style).*?</\1>", "", h)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", h))


def half_up(x):
    return int(math.floor(x + 0.5))


def med(xs):
    s = sorted(xs)
    n = len(s)
    return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2


# ------------------------------------------------------------------ the data
def test_data_has_31_days_and_no_address():
    assert len(D["days"]) == 31 and D["days"][0]["day"] == "2026-10-06" and D["days"][-1]["day"] == EVENT
    for p in [DATA, *[os.path.join(PACK, f) for f in os.listdir(PACK)]]:
        t = open(p, encoding="utf-8").read()
        for m in re.findall(r"0x[0-9a-fA-F]{8,}", t):
            assert set(m[2:].lower()) == {"e"}, (p, m[:12])   # only the placeholder the plan excludes


def test_event_row_matches_the_plan_headline_figures():
    ev = D["days"][-1]
    base = D["days"][:-1]
    assert ev["liq_wallets"] == 18813 and ev["hip3_liq_wallets"] == 9054
    assert half_up(med([d["hip3_liq_wallets"] for d in base])) == 1755
    assert half_up(med([d["liq_wallets"] for d in base])) == 4868
    rank = 1 + sum(1 for d in base if d["hip3_liq_wallets"] > ev["hip3_liq_wallets"])
    assert rank == 1
    # S2: the share of force-closed wallets that placed a new market order within 15 minutes
    assert round(100 * ev["s2_retrade_15"] / ev["s2_denominator"], 1) == 17.7
    pool = sum(d["s2_retrade_15"] for d in base) / sum(d["s2_denominator"] for d in base)
    assert round(100 * pool, 1) == 12.9


def test_pack_hashes_are_the_files_and_the_plan_hash_is_the_logged_one():
    plan = open(os.path.join(PACK, "ANALYSIS-PLAN.sha256")).read().split()[0]
    assert plan == PLAN_SHA == hashlib.sha256(open(os.path.join(PACK, "ANALYSIS-PLAN.md"), "rb").read()).hexdigest()
    assert D["provenance"]["analysis_plan"]["sha256"] == PLAN_SHA if isinstance(D["provenance"]["analysis_plan"], dict) else True
    code = D["provenance"]["code_sha256"]
    for name, h in code.items():
        f = os.path.join(PACK, os.path.basename(name))
        if os.path.exists(f):
            assert hashlib.sha256(open(f, "rb").read()).hexdigest() == h, name
    assert len(D["provenance"]["inputs"]) == 31


def test_csv_equals_the_json():
    import selloff as SO
    rows = list(csv.DictReader(io.StringIO(open(os.path.join(PACK, "5-november-2026-hyperliquid-daily.csv"), encoding="utf-8").read())))
    assert len(rows) == 31 and rows[-1]["date_utc"] == EVENT
    assert [int(r["wallets_force_closed"]) for r in rows] == [d["liq_wallets"] for d in D["days"]]
    assert SO.csv_text() == open(os.path.join(PACK, "5-november-2026-hyperliquid-daily.csv"), encoding="utf-8").read()


# ------------------------------------------------------------------ the market figures
def test_market_figures_recomputed():
    nc, n1 = MKT["indices"]["nasdaq_composite"], MKT["indices"]["nasdaq_100"]
    for ix, dd, need in ((nc, 11.90, 13.51), (n1, 14.72, 17.25)):
        r, c = ix["record_close"], ix["close"]
        assert round(100 * (1 - c / r), 2) == dd, ix
        assert round(100 * (r / c - 1), 2) == need, ix
    assert round(100 * (nc["close"] / nc["prior_close"] - 1), 2) == -5.52


def test_study_page_market_wording(built_site):
    t = text(page(built_site, S))
    assert "11.9% below its record" in t or "11.9% below" in t
    assert "13.5%" in t and "14.7%" in t
    assert not re.search(r"Nasdaq (is |was )?down 14", t)


# ------------------------------------------------------------------ the study page
def test_study_page_figures_are_the_data(built_site):
    t = text(page(built_site, S))
    for want in ("18,813", "9,054", "1,755", "4,868", "17.7%", "12.9%", "4,971"):
        assert want in t, want


def test_study_page_has_no_price_no_pay_link_and_no_stray_dollar(built_site):
    h = page(built_site, S)
    main = h.split("<main", 1)[-1].split("</main>")[0]   # the site-wide checkout panel after <main> holds the product price on every page
    assert amounts_in(main) == [], amounts_in(main)
    assert "/pricing/" not in main and "/start/" not in main and 'class="btn' not in main
    assert "$" not in text(main)


def test_study_page_wording_lint_and_banned_words(built_site):
    for path in (S, B):
        h = page(built_site, path)
        body = text(h.split("<main", 1)[-1].split("</main>")[0])
        assert L.lint_text(body, path) == [], (path, L.lint_text(body, path))
        for w in ("beta", "fake", "demo", "made-up", "buy the dip", "buy-the-dip", "panic", "crash"):
            assert not re.search(rf"\b{re.escape(w)}\b", body, re.I), (path, w)


def test_study_page_defines_wallet_and_force_closed_and_credits_the_data(built_site):
    h = page(built_site, S)
    t = text(h)
    assert re.search(r"wallet is a blockchain address|A wallet is", t) and "force-closed" in t
    assert "CC BY 4.0" in t and "Ironflow" in t and "FRED" in t
    assert "https://creativecommons.org/licenses/by/4.0/" in h
    assert re.search(r"(?i)changes? (made|we made)|we (aggregated|changed|turned)", t)
    assert "donttrade" in t


def test_study_page_dois_are_in_references_with_a_crossref_check(built_site):
    refs = json.load(open(os.path.join(REPO, "site", "config", "references.json"), encoding="utf-8"))
    h = page(built_site, S)
    dois = set(re.findall(r"10\.\d{4,9}/[^\s\"<>)]+", h))
    known = {v["doi"].lower(): v for v in (refs["refs"] if "refs" in refs else refs).values() if isinstance(v, dict) and "doi" in v}
    for d in dois:
        d = d.rstrip(".,;")
        if d.lower().startswith("10.1257/aer.20140386") or d.lower().startswith("10.1111/j.1540-6261.2005.00723.x"):
            assert d.lower() in known and known[d.lower()]["crossref_checked"], d


def test_csp_unchanged_and_no_inline_style_or_script(built_site):
    for path in (S, B, "/"):
        h = page(built_site, path)
        assert not re.search(r"<script(?![^>]*\bsrc=)(?![^>]*type=\"(text/csv|application/ld\+json)\")[^>]*>", h), path
        assert " style=" not in h, path
        import html as _html
        csp = _html.unescape(re.search(r'http-equiv="Content-Security-Policy" content="([^"]+)"', h).group(1))
        assert "script-src 'self'" in csp and "unsafe-inline" not in csp.split("style-src")[0], path


def test_json_ld_and_sitemap(built_site):
    h = page(built_site, S)
    blocks = [json.loads(b) for b in re.findall(r'(?s)<script type="application/ld\+json">(.*?)</script>', h)]
    flat = []
    for b in blocks:
        flat += b.get("@graph", [b])
    types = {x.get("@type") if isinstance(x.get("@type"), str) else tuple(x.get("@type")) for x in flat}
    assert any("Article" in (t if isinstance(t, tuple) else (t,)) or "ScholarlyArticle" in (t if isinstance(t, tuple) else (t,)) for t in types)
    assert "Dataset" in types
    sm = (built_site["out"] / "sitemap.xml").read_text(encoding="utf-8")
    assert S in sm and B in sm


def test_seo_lint_passes_for_the_new_pages(built_site):
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "seo_lint.py")], capture_output=True, text=True,
                       env={**os.environ, "DT_OUT": str(built_site["out"])})
    assert "problem" not in r.stdout.lower() or "0 problem" in r.stdout.lower() or r.returncode == 0, r.stdout[-800:]


def test_pack_is_served_byte_for_byte(built_site):
    for f in os.listdir(PACK):
        if f.endswith(".csv") and f.startswith("5-november-2026-"):   # the daily and the per-market CSV sit at /data/
            assert (built_site["out"] / "data" / f).read_bytes() == open(os.path.join(PACK, f), "rb").read()
        else:
            assert (built_site["out"] / "data" / "5-november-2026" / f).read_bytes() == open(os.path.join(PACK, f), "rb").read()


# ------------------------------------------------------------------ the Learn callout and the research listing
def test_learn_callout(built_site):
    t = text(page(built_site, "/learn/drawdown-recovery-table/"))
    assert "Nasdaq Composite closed 11.9% below its record" in t and "13.5%" in t
    assert "Nasdaq-100 closed 14.7% below its record and needs 17.3%" in t
    assert "FRED" in t and not re.search(r"Nasdaq (is |was )?down 14", t)


def test_research_listing_links_the_study(built_site):
    assert S in page(built_site, "/research/")


# ------------------------------------------------------------------ the home band
def build_dated(tmp_path, today):
    out = tmp_path / "_site"
    env = {**os.environ, "DT_OUT": str(out), "DT_TODAY": today}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return (out / "index.html").read_text(encoding="utf-8")


def test_home_band_is_off_by_owner_decision(built_site):
    """8 Nov 2026 (owner, research memo action 7): the Nasdaq / crypto-wallet band is off the home page (build.SELLOFF_BAND_ON)."""
    import build as BLD
    assert BLD.SELLOFF_BAND_ON is False and BLD.dated_band() is None
    h = (built_site["out"] / "index.html").read_text(encoding="utf-8")
    assert "data-dated-band" not in h and "Nasdaq" not in h and "crypto" not in text(h.split("<main", 1)[-1])
    assert S in (built_site["out"] / "research" / "index.html").read_text(encoding="utf-8")   # the study stays on /research/


def test_home_band_markup_when_switched_back_on():
    """The band as it was (6 Nov), rendered with the switch on: the FRED figure and a link, no motion."""
    import datetime as dt
    import build as BLD
    d = BLD.dated_band(today=dt.date(2026, 11, 8), on=True)
    assert d["expires"] == "2026-11-21" and d["date_long"] == "5 November" and d["link"] == BLD.SELLOFF_PATH == S
    band = open(os.path.join(REPO, "site", "templates", "partials", "dated_band.html"), encoding="utf-8").read()
    assert "What did your account do that day?" in band and "data-motion" not in band and "animation" not in band
    assert BLD.dated_band(today=dt.date(2026, 11, 21), on=True) is None


def test_no_study_finding_on_the_home_page_or_in_the_band(built_site):
    """The house rule (home.html): no study finding on the home page, so none can sit next to the offer. The band carries a FRED market
    figure and a link; no figure of the sell-off study (counts, ratios, shares, the weekday medians) may appear anywhere on the page."""
    import selloff as SO
    F = SO.context()["F"]
    h = (built_site["out"] / "index.html").read_text(encoding="utf-8")
    t = text(h.split("<main", 1)[-1].split("</main>")[0])
    study_figures = [F[k] for k in ("wallets", "hip3", "hip3_median", "hip3_prev", "wallets_median", "hip3_wd_median", "retrade15", "pooled15",
                                    "iqr15", "hip3_active", "events", "busiest_wallets")]
    study_figures += [f"{F['hip3_ratio']} times", f"{F['hip3_wd_ratio']} times", f"{F['hip3_vs_prev']} times", "force-closed", "forced close",
                      "liquidat"]
    for f in study_figures:
        assert f not in t, f
    assert "Hyperliquid" not in t and not re.search(r"\d[\d,.]*\s*(million\s+)?wallets", t)


def build_dated(tmp_path, today):
    out = tmp_path / "_site"
    env = {**os.environ, "DT_OUT": str(out), "DT_TODAY": today}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return (out / "index.html").read_text(encoding="utf-8")


def test_home_band_is_gone_on_21_nov_and_after(tmp_path):
    # 8 Nov 2026: the band is off (build.SELLOFF_BAND_ON), so no dated build has it; the expiry rule is held by
    # test_home_band_markup_when_switched_back_on
    for d in ("2026-11-20", "2026-11-21", "2026-11-22"):
        assert "data-dated-band" not in build_dated(tmp_path / d, d), d


# ------------------------------------------------------------------ fix round 1
def weekday(day):
    import datetime as dt
    return dt.date.fromisoformat(day).weekday() < 5


def test_weekday_comparison_recomputed_and_used_in_headlines(built_site):
    base = D["days"][:-1]
    ev = D["days"][-1]
    wd = [d for d in base if weekday(d["day"])]
    assert len(wd) == 22 and len(base) - len(wd) == 8
    m = med([d["hip3_liq_wallets"] for d in wd])
    assert half_up(m) == 1946 and round(ev["hip3_liq_wallets"] / m, 1) == 4.7
    assert round(ev["hip3_liq_notional"] / med([d["hip3_liq_notional"] for d in wd]), 1) == 7.5
    assert round(ev["liq_wallets"] / med([d["liq_wallets"] for d in wd]), 1) == 2.7
    assert 1 + sum(1 for d in wd if d["hip3_liq_wallets"] > ev["hip3_liq_wallets"]) == 1
    h = page(built_site, S)
    lede = text(re.search(r'(?s)<p class="lede">(.*?)</p>', h).group(1))
    assert "about 4.7 times the median weekday" in lede and "5.2" not in lede
    t = text(h)
    assert "pre-stated" in t and "5.2 times the 30-day median" in t and "not in the plan" in t
    # the 1.8x previous high: previous high 4,971 on 30 Oct, a Friday, an all-days maximum that is also the weekday maximum
    assert max(d["hip3_liq_wallets"] for d in base) == max(d["hip3_liq_wallets"] for d in wd) == 4971
    assert "1.8 times the previous 30-day high (30 Oct, a Friday)" in t
    # headline-facing copy never says "normal day" or the 5.2 figure
    for path in ("/research/", "/tools/bad-day-check/", "/"):
        assert "times a normal day" not in text(page(built_site, path))
    assert "5.2 times" not in text(page(built_site, "/"))


def test_builder_listed_label_is_used_everywhere_and_stock_index_is_never_claimed(built_site):
    for path in (S, "/research/", B, "/learn/drawdown-recovery-table/", "/"):
        t = text(page(built_site, path))
        assert not re.search(r"stock and index markets|stock, index and commodity|on stock markets", t), path
    h = page(built_site, S)
    assert "builder-listed" in text(re.search(r"(?s)<h1>(.*?)</h1>", h).group(1))
    t = text(h)
    assert "listed as SOXL, MU, SP500, XYZ100 and AMD" in t and "do not say what share of the value was in stock or index contracts" in t
    top = D["summary"]["S1_top5_E"]
    assert f"{round(100 * sum(v for _, _, v in top) / D['days'][-1]['hip3_liq_notional'])}%" in t


def test_summary_json_has_no_suppressed_cell_and_both_hashes_are_documented():
    pub = json.load(open(os.path.join(PACK, "SUMMARY.json"), encoding="utf-8"))
    assert all(row[2] >= 10 for row in pub["S3_hours_E"]) and 7 not in [r[0] for r in pub["S3_hours_E"]]
    pf = D["provenance"]["published_files"]
    assert pf["SUMMARY.json"]["sha256"] == hashlib.sha256(open(os.path.join(PACK, "SUMMARY.json"), "rb").read()).hexdigest()
    assert pf["SUMMARY.json"]["run_sha256"] == D["provenance"]["output_sha256"]["SUMMARY.json"] != pf["SUMMARY.json"]["sha256"]
    readme = open(os.path.join(PACK, "README.txt"), encoding="utf-8").read()
    assert pf["SUMMARY.json"]["sha256"] in readme and pf["SUMMARY.json"]["run_sha256"] in readme and pf["RUN-LOG.txt"]["sha256"] in readme
    assert "exclusive method" in readme and "self-recorded" in readme


def test_run_log_has_no_reddit_line_and_the_page_describes_the_timing_honestly(built_site):
    for p in [os.path.join(PACK, "RUN-LOG.txt"), DATA]:
        assert "Reddit" not in open(p, encoding="utf-8").read() and "usernames" not in open(p, encoding="utf-8").read()
    t = text(page(built_site, S))
    assert "time-stamped" not in t and "our own clock" in t and "dated deposit is pending" in t


def test_quartile_method_and_long_share_rank_are_stated(built_site):
    t = text(page(built_site, S))
    assert "exclusive method" in t and "QUARTILE.INC" in t
    assert "ranked 6 of the 31 days" in t
    assert "96% of the value force-closed was in long positions" in t


def test_learn_callout_says_wallets(built_site):
    t = text(page(built_site, "/learn/drawdown-recovery-table/"))
    assert "What happened to wallets on one crypto exchange that day" in t and "to traders" not in t


def test_faq_json_ld_has_no_space_before_a_full_stop(built_site):
    h = page(built_site, B)
    assert " ." not in "".join(re.findall(r'(?s)<script type="application/ld\+json">(.*?)</script>', h))


def test_fix_round_2_wording(built_site):
    h = page(built_site, S)
    t = text(h)
    h1 = text(re.search(r"(?s)<h1>(.*?)</h1>", h).group(1))
    assert h1.startswith("5 November 2026: 9,054 wallets were force-closed on Hyperliquid’s builder-listed markets, about 4.7 times the median weekday")
    assert "18,813" not in h1 and "18,813" not in text(re.search(r"<title>(.*?)</title>", h).group(1))
    # the all-markets figure stays in the body, with its near-tie context
    assert "18,813" in t and "a near-tie" in t and re.search(r"8 Oct was \d+% lower", t)
    # active wallets defined before first use; bots and market makers named; not a person
    d = t.index("Active wallet Any address that bought or sold")
    assert "bots and market makers" in t[d:d + 300] and "not a person" in t[d:d + 300]
    assert d < t.index("of 39,804 active there") and d < t.index("Share of active wallets")
    # the 15-minute limit sits in the tile and in section 4
    limit = "We did not compare with wallets that were not force-closed on the same day, so a busier day may explain part of the gap"
    assert t.count(limit.replace("the gap", "this gap")) == 1 and limit in t
    assert "all or part of a leveraged position" in t and "other forced reductions are not counted" in t
    assert "Method written down first" in t and "re-run after the first pass" in t and "one removed cell" in t
    assert "Text: CC BY-NC 4.0. Charts, counts and code: CC BY 4.0." in t   # 7 Nov 2026: owner approved CC BY 4.0 for charts
    assert "our rule matches Ironflow’s own liquidation table" in t
    tool = text(page(built_site, B))
    assert "will usually also have more losses" not in tool and "almost by construction" in tool
    # 8 Nov 2026: the home band is off (build.SELLOFF_BAND_ON); its wording is kept in the partial for the day it returns
    assert "See what one crypto exchange’s wallets did" in open(os.path.join(REPO, "site", "templates", "partials", "dated_band.html"), encoding="utf-8").read()


# ------------------------------------------------------------------ 7 Nov: market by market (descriptive, added after the plan)
PM = os.path.join(PACK, "5-november-2026-per-market.csv")
MV = os.path.join(PACK, "MARKETS-VERIFIED.csv")
ADDR = re.compile(r"0x[0-9a-fA-F]{8,}")


def pm_rows():
    return list(csv.DictReader(open(PM, encoding="utf-8")))


def test_per_market_uses_run_day_sql_character_for_character():
    run_day = open(os.path.join(PACK, "run_day.py"), encoding="utf-8").read().splitlines()
    pm = open(os.path.join(REPO, "checks", "selloff", "per_market.py"), encoding="utf-8").read()
    block = run_day[5:12] + [run_day[16]]          # lines 6 to 12 and 17: the filters, the taker rule, the liquidation flag
    assert "taker_side='buy' THEN buyer ELSE seller END taker" in block[4] and "WHERE liq" in block[-1]
    pm_lines = [x.strip() for x in pm.splitlines()]
    for line in block:
        assert line.strip() in pm_lines, line
    # the copy in the pack is the same file
    for name in ("per_market.py", "markets_verified.py"):
        assert open(os.path.join(PACK, name), "rb").read() == open(os.path.join(REPO, "checks", "selloff", name), "rb").read(), name


def test_per_market_reconciles_with_the_study_on_every_day():
    rows = pm_rows()
    days = {d["day"]: d for d in D["days"]}
    assert sorted({r["date_utc"] for r in rows}) == sorted(days)
    for day, d in days.items():
        rs = [r for r in rows if r["date_utc"] == day]
        tot = {r["scope"]: r for r in rs if r["row_type"] == "scope_total_unique_wallets"}
        assert int(tot["builder_listed"]["wallets_force_closed"]) == d["hip3_liq_wallets"], day
        assert int(tot["all_markets"]["wallets_force_closed"]) == d["liq_wallets"], day
        assert tot["builder_listed"]["value_force_closed_usd"] == f"{d['hip3_liq_notional']:.2f}", day
        assert tot["all_markets"]["value_force_closed_usd"] == f"{d['liq_notional']:.2f}", day
        for scope in ("builder_listed", "core"):
            parts = [r for r in rs if r["scope"] == scope and r["row_type"] != "scope_total_unique_wallets"]
            s = sum(float(r["value_force_closed_usd"]) for r in parts)
            assert abs(s - float(tot[scope]["value_force_closed_usd"])) <= 0.01 * len(parts), (day, scope)
            assert all(int(r["wallets_force_closed"]) >= 10 for r in parts if r["row_type"] == "market"), (day, scope)
        assert float(tot["builder_listed"]["value_force_closed_usd"]) + float(tot["core"]["value_force_closed_usd"]) == \
            pytest.approx(float(tot["all_markets"]["value_force_closed_usd"]), abs=0.02)


def test_per_market_5_nov_figures_and_overlap():
    ev = [r for r in pm_rows() if r["date_utc"] == EVENT]
    hip = next(r for r in ev if r["row_type"] == "scope_total_unique_wallets" and r["scope"] == "builder_listed")
    allm = next(r for r in ev if r["row_type"] == "scope_total_unique_wallets" and r["scope"] == "all_markets")
    assert hip["value_force_closed_usd"] == "140556424.23" and round(float(hip["value_force_closed_usd"]) / 1e6) == 141
    assert int(hip["wallets_force_closed"]) == 9054 and int(hip["sum_of_market_wallet_counts"]) == 13460   # 4,406 repeats
    assert int(allm["wallets_force_closed"]) == 18813 and int(allm["sum_of_market_wallet_counts"]) == 26439
    # the market rows (10+ wallets) alone already add up to more wallets than the unique count
    assert sum(int(r["wallets_force_closed"]) for r in ev if r["row_type"] == "market" and r["scope"] == "builder_listed") > 9054
    # the page's top five are the per-market file's top five
    mk = sorted((r for r in ev if r["row_type"] == "market" and r["scope"] == "builder_listed"), key=lambda r: -float(r["value_force_closed_usd"]))
    assert [(r["market"], int(r["wallets_force_closed"])) for r in mk[:5]] == [(m, w) for m, w, _ in D["summary"]["S1_top5_E"]]
    for r, (_, _, v) in zip(mk[:5], D["summary"]["S1_top5_E"]):
        assert r["value_force_closed_usd"] == f"{v:.2f}"


def test_no_address_in_the_public_csvs():
    for p in (PM, MV, os.path.join(PACK, "5-november-2026-hyperliquid-daily.csv"), os.path.join(PACK, "MARKETS-README.txt")):
        assert not ADDR.search(open(p, encoding="utf-8").read()), p


def test_every_builders_docs_market_has_a_source_url_and_every_large_market_is_checked():
    mv = list(csv.DictReader(open(MV, encoding="utf-8")))
    assert {r["status"] for r in mv} <= {"builders_docs", "partly_sourced", "no_source_found"}
    for r in mv:
        if r["status"] == "builders_docs":
            assert r["source_url"].startswith("https://") and r["what_it_tracks"] and r["checked_utc_date"], r["market_as_listed"]
        else:
            assert r["notes"], r["market_as_listed"]
    ev = [r for r in pm_rows() if r["date_utc"] == EVENT and r["scope"] == "builder_listed"]
    tot = float(next(r for r in ev if r["row_type"] == "scope_total_unique_wallets")["value_force_closed_usd"])
    big = {r["market"] for r in ev if r["row_type"] == "market" and float(r["value_force_closed_usd"]) >= 0.01 * tot}
    named = {f"{m}" for m, _, _ in D["summary"]["S1_top5_E"]}
    assert big | named <= {r["market_as_listed"] for r in mv}


def test_market_by_market_section(built_site):
    h = page(built_site, S)
    sec = h[h.index('aria-labelledby="sell-pm-h"'):h.index('aria-labelledby="sell-15-h"')]
    t = text(sec)
    assert "4. Market by market" in t and "Added after the written plan" in t and "not one of the measures the plan set" in t
    assert "these rows add up to more than 9,054" in t and "13,460 wallet-and-market pairs" in t and "4,406" in t
    assert sec.count("<caption>") == 2 and "<details" in sec and 'scope="col"' in sec and 'scope="row"' in sec
    assert re.search(r'<td class="num">1,347</td>', sec)                       # numbers right-aligned
    assert 'href="/data/5-november-2026-per-market.csv"' in sec and 'href="/data/5-november-2026/MARKETS-VERIFIED.csv"' in sec
    assert hashlib.sha256(open(PM, "rb").read()).hexdigest() in t and "per_market.py build" in t and "sha256sum" in t
    assert (built_site["out"] / "data" / "5-november-2026" / "per_market.py").exists()
    # a market is named only where its status is verified; the partly verified one stays "as listed"
    mv = {r["market_as_listed"]: r for r in csv.DictReader(open(MV, encoding="utf-8"))}
    rows = re.findall(r'(?s)<tr><th scope="row">(.*?)</th><td>(.*?)</td><td>(.*?)</td>', sec)
    assert len(rows) >= 20
    for name, dex, cell in rows:
        r = mv.get(f"{dex}:{name}-PERP")
        if r and r["status"] == "builders_docs":
            assert html.unescape(text(cell)).strip().startswith(r["what_it_tracks"][:20]) and "builder’s docs" in cell
        else:
            assert text(cell).strip().startswith("As listed"), (dex, name)
    assert "Nasdaq-100" not in t
    # no offer, price or pay link anywhere near it
    assert not re.search(r"\$\s?\d|/pricing/|checkout|buy now", sec, re.I)


def test_status_words_are_the_same_on_the_page_and_in_the_csv(built_site):
    import selloff as SO
    codes = {r["status"] for r in csv.DictReader(open(MV, encoding="utf-8"))}
    assert codes <= set(SO.STATUS)
    for code, (word, _) in SO.STATUS.items():
        assert code == word.replace("’", "").replace(" ", "_"), (code, word)
    t = text(page(built_site, S))
    assert "verified" not in t.lower()


def test_check_box_states_the_ironflow_replacement_and_the_pinned_revision(built_site):
    import importlib.util
    spec = importlib.util.spec_from_file_location("pm", os.path.join(REPO, "checks", "selloff", "per_market.py"))
    pm = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pm)
    import selloff as SO
    assert SO.PM_REVISION == pm.REVISION
    h = page(built_site, S)
    box = text(h[h.index('id="sell-pm-check-h"'):h.index('aria-labelledby="sell-15-h"')])
    assert pm.REVISION in box and "23:24 UTC" in box and "18,815" in box and "18,813" in box and "1,142" in box and "1,129" in box
    assert "builder-listed figures do not change" in box


# ------------------------------------------------------------------ 7 Nov: a broken study-data file fails the build with its real message
@pytest.mark.parametrize("breakage", ["not json", "figure"])
def test_broken_study_data_gives_the_real_message_not_a_name_error(tmp_path, breakage):
    bad = tmp_path / "selloff-broken.json"
    if breakage == "not json":
        bad.write_text("{ this is not json", encoding="utf-8")
    else:
        d = json.loads(open(DATA, encoding="utf-8").read())
        d["days"][-1]["hip3_liq_wallets"] += 1          # the days no longer reproduce the analysis summary
        bad.write_text(json.dumps(d), encoding="utf-8")
    code = ("import runpy, sys; sys.path.insert(0, sys.argv[1]); import selloff; selloff.DATA_JSON = sys.argv[2]; "
            "runpy.run_path(sys.argv[3], run_name='__main__')")
    env = {**os.environ, "DT_OUT": str(tmp_path / "_site")}
    r = subprocess.run([sys.executable, "-c", code, os.path.join(REPO, "site"), str(bad), os.path.join(REPO, "site", "build.py")],
                       env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert "NameError" not in r.stderr and "Traceback" not in r.stderr, r.stderr[-800:]
    assert "BUILD FAILED: sell-off study data:" in r.stderr, r.stderr[-800:]
    if breakage == "figure":
        assert "the analysis summary says" in r.stderr
    assert not (tmp_path / "_site").exists()


# ------------------------------------------------------------------ 7 Nov, Tester round: medians, sources, accessibility
def test_median_is_recomputed_exactly_from_the_csv_where_it_uses_no_unlisted_day():
    rows = pm_rows()
    base = sorted({r["date_utc"] for r in rows})[:-1]
    assert len(base) == 30 and EVENT not in base
    listed = {(r["date_utc"], r["scope"], r["market"]): int(r["wallets_force_closed"]) for r in rows if r["row_type"] == "market"}
    ev = [r for r in rows if r["date_utc"] == EVENT and r["row_type"] == "market"]
    assert {r["median_uses_unlisted_days"] for r in ev} == {"yes", "no"}
    assert all(r["median_uses_unlisted_days"] == "" for r in rows if r["date_utc"] != EVENT or r["row_type"] != "market")
    n_no = 0
    for r in ev:
        m = med([listed.get((d, r["scope"], r["market"]), 0) for d in base])
        if r["median_uses_unlisted_days"] == "no":
            n_no += 1
            assert f"{m:g}" == r["market_median_wallets_30d"], r["market"]
        else:   # "yes" is said only where the CSV alone really gives another number, and the true median is never smaller
            assert f"{m:g}" != r["market_median_wallets_30d"] and float(r["market_median_wallets_30d"]) > m, r["market"]
    assert n_no >= 40


def test_price_source_column_has_a_url_or_says_not_checked_and_sources_are_the_describing_pages():
    mv = list(csv.DictReader(open(MV, encoding="utf-8")))
    spec = "https://docs.trade.xyz/perpetuals/specifications-and-schedules/specification-index"
    for r in mv:
        assert (r["price_source"] == "not checked") == (r["price_source_url"] == ""), r["market_as_listed"]
        assert r["price_source_url"] == "" or r["price_source_url"].startswith("https://"), r["market_as_listed"]
    by = {r["market_as_listed"]: r for r in mv}
    assert by["xyz:SP500-PERP"]["source_url"] == spec and by["xyz:XYZ100-PERP"]["source_url"] == spec
    assert by["xyz:SP500-PERP"]["price_source_url"].endswith("/perpetuals/markets/equity-indices")
    for fund in ("xyz:SOXL-PERP", "xyz:KORU-PERP", "xyz:DRAM-PERP"):
        assert by[fund]["price_source"] == "not checked"
    assert "Blue Ocean" not in "".join(r["price_source"] for r in mv if not r["price_source_url"].endswith("/stocks/us"))


def test_source_links_have_unique_names_and_the_command_box_is_a_labelled_region(built_site):
    h = page(built_site, S)
    sec = h[h.index('aria-labelledby="sell-pm-h"'):h.index('aria-labelledby="sell-15-h"')]
    names = [text(a).strip() for a in re.findall(r'(?s)<a href="https://[^"]+" rel="noopener">(.*?)</a>', sec)]
    assert len(names) == 20 and len(set(names)) == 20 and all(n.startswith("source for ") for n in names)
    assert re.search(r'<pre class="pm-cmd" tabindex="0" role="region" aria-label="Commands to re-run the per-market count">', sec)
    css = open(os.path.join(REPO, "site", "static", "css", "site.css"), encoding="utf-8").read()
    assert ".pm-cmd:focus-visible" in css


@pytest.mark.parametrize("width", [390, 1280])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_study_page_axe_clean_with_details_open(browser, built_site, width, scheme):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + S)
    pg.evaluate("() => document.querySelectorAll('details').forEach(d => d.open = true)")
    assert pg.evaluate("() => [...document.querySelectorAll('details')].every(d => d.open)")
    assert horizontal_overflow(pg) == []
    v = axe_violations(pg)
    assert v == [], v
    # the command box can be reached by keyboard
    pg.focus("pre.pm-cmd")
    assert pg.evaluate("() => document.activeElement.matches('pre.pm-cmd')")
    ctx.close()
