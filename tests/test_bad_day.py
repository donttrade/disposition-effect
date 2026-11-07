"""The Bad-day check (/tools/bad-day-check/; CODER-REPORT-SELLOFF-2026-11-06 step K6).

  * bad-day-core.js equals tests/reference/bad_day_ref.py (separate Python, on the Challenge Readiness reference's habit flags)
    on seeded random trades, on every sample file that parses in checks/real_data, with and without a time shift;
  * a hand-made file gives hand-worked numbers: 12 ordinary days (2 trades, +2 each) and a bad day (3 losses in a row, 2
    re-entries within 15 minutes, 2 trades after two losses in a row, a largest loss of 5, net -11);
  * edges: a day with no trades, a file of one day (no typical day), 9 and 10 other days (the typical-day threshold), a trade at
    23:30 that moves to the next day with a +1 hour shift, a dates-only file, ?d= parsing (invalid, repeated, more than 5);
  * in Chromium: the page reads a file, shows the table, never uploads, no console output, no horizontal scroll at 320, 390 and
    1280, axe clean in both themes, the real public-data button works.
"""
import json
import os
import random
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, os.path.join(REPO, "site"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402
import lint as L  # noqa: E402
import engine_ref as E  # noqa: E402
import bad_day_ref as REF  # noqa: E402

B = "/tools/bad-day-check/"
RUN = os.path.join(HERE, "reference", "bad_day_run.mjs")
REAL = os.path.join(REPO, "checks", "real_data", "real-trades.coded.csv")
DAY_MS = 86400000


def run_js(cases):
    r = subprocess.run(["node", RUN], input=json.dumps({"cases": cases}), capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(r.stdout)


def same(a, b):
    """The JS result equals the reference (floats to the cent; missing/None alike)."""
    assert a["datesOnly"] == b["datesOnly"] and a["missing"] == b["missing"] and a["fellBack"] == b["fellBack"]
    assert a["n_days"] == b["n_days"] and a["n_other"] == b["n_other"]
    assert [c["date"] for c in a["chosen"]] == [c["date"] for c in b["chosen"]]
    for x, y in zip(a["chosen"], b["chosen"]):
        for k in REF.KEYS:
            assert abs(x[k] - y[k]) < 1e-9, (k, x, y)
    if b["typical"] is None:
        assert a["typical"] is None
    else:
        for k in REF.KEYS:
            assert abs(a["typical"][k] - b["typical"][k]) < 1e-9, k


def trade(i, open_ms, hold_s, pnl, qty=1, sym="AAA"):
    return {"id": f"t{i}", "symbol": sym, "open_ts": open_ms, "close_ts": open_ms + hold_s * 1000, "hold_s": hold_s, "qty": qty, "pnl": pnl,
            "pnl_unit": "USD"}


def random_trades(seed, days=40, per=8):
    rnd = random.Random(seed)
    base = 1788220800000   # 2026-09-01 00:00 UTC
    out = []
    for d in range(days):
        for _ in range(rnd.randint(0, per)):
            o = base + d * DAY_MS + rnd.randint(8 * 3600, 22 * 3600) * 1000
            out.append(trade(len(out), o, rnd.choice([60, 300, 900, 2400, 7200]), round(rnd.gauss(0, 40), 2),
                             rnd.choice([1, 1, 1, 2, 3]), rnd.choice("AB")))
    out.sort(key=lambda t: t["close_ts"])
    return out


@pytest.mark.parametrize("seed", range(6))
def test_core_equals_reference_on_random_files(seed):
    tr = random_trades(seed)
    days = sorted({REF.day_of(t["close_ts"], 0) for t in tr})
    cases = [{"trades": tr, "shiftHours": s, "requested": rq} for s in (0, 3, -5, 14) for rq in
             ([], [days[3]], [days[0], days[-1], "2030-01-01"], days[:5])]
    got = run_js(cases)
    for c, g in zip(cases, got):
        same(g, REF.bad_day(c["trades"], c["shiftHours"], c["requested"]))


def test_core_equals_reference_on_the_real_public_file():
    tr = E.parse_file(open(REAL, "rb").read())["trades"]
    days = sorted({REF.day_of(t["close_ts"], 0) for t in tr})
    cases = [{"trades": tr, "shiftHours": s, "requested": rq} for s in (0, 7) for rq in ([], days[len(days) // 2:len(days) // 2 + 2], ["2026-11-05"])]
    for c, g in zip(cases, run_js(cases)):
        same(g, REF.bad_day(tr, c["shiftHours"], c["requested"]))


def hand_trades(other_days=12):
    out = []
    base = 1792368000000   # 2026-10-19 00:00 UTC
    for d in range(other_days):
        day = base + d * DAY_MS
        out.append(trade(len(out), day + 9 * 3600000 + 1800000, 600, 1))
        out.append(trade(len(out), day + 11 * 3600000, 600, 1))
    bad = base + 17 * DAY_MS   # 2026-11-05
    for o, hold, p in ((9.5, 600, -5), (9.75, 600, -4), (10, 600, -3), (13, 600, 1)):
        out.append(trade(len(out), int(bad + o * 3600000), hold, p))
    return out


def test_hand_worked_numbers():
    assert REF.day_of(hand_trades()[-1]["close_ts"], 0) == "2026-11-05"
    r = run_js([{"trades": hand_trades(), "shiftHours": 0, "requested": ["2026-11-05"]}])[0]
    d = r["chosen"][0]
    assert (d["n"], d["net"], d["largest_loss"], d["reentry"], d["streak"], d["size_after_loss"], d["large_loss"]) == (4, -11, 5, 2, 2, 0, 0)
    assert r["typical"] == {"n": 2, "net": 2, "largest_loss": 0, "reentry": 0, "streak": 0, "size_after_loss": 0, "large_loss": 0}
    assert r["n_other"] == 12 and not r["fellBack"] and r["missing"] == []
    same(r, REF.bad_day(hand_trades(), 0, ["2026-11-05"]))


def test_empty_request_picks_the_lowest_net_day_and_missing_day_is_reported():
    r = run_js([{"trades": hand_trades(), "shiftHours": 0, "requested": []},
                {"trades": hand_trades(), "shiftHours": 0, "requested": ["2026-12-25"]}])
    assert r[0]["chosen"][0]["date"] == "2026-11-05" and r[0]["fellBack"]
    assert r[1]["missing"] == ["2026-12-25"] and r[1]["fellBack"] and r[1]["chosen"][0]["date"] == "2026-11-05"


def test_typical_day_needs_ten_other_days():
    nine = run_js([{"trades": hand_trades(9), "shiftHours": 0, "requested": ["2026-11-05"]}])[0]
    ten = run_js([{"trades": hand_trades(10), "shiftHours": 0, "requested": ["2026-11-05"]}])[0]
    assert nine["n_other"] == 9 and nine["typical"] is None
    assert ten["n_other"] == 10 and ten["typical"]["n"] == 2
    one = run_js([{"trades": hand_trades(0), "shiftHours": 0, "requested": ["2026-11-05"]}])[0]
    assert one["n_days"] == 1 and one["typical"] is None


def test_a_late_trade_moves_to_the_next_day_with_a_shift():
    tr = [trade(0, 1793000000000 - (1793000000000 % DAY_MS) + 23 * 3600000 + 600000, 1200, 7)]   # closes 23:30 on its day
    day = REF.day_of(tr[0]["close_ts"], 0)
    nxt = REF.day_of(tr[0]["close_ts"], 1)
    assert day != nxt
    a, b = run_js([{"trades": tr, "shiftHours": 0, "requested": [day]}, {"trades": tr, "shiftHours": 1, "requested": [day]}])
    assert a["chosen"][0]["date"] == day and not a["fellBack"]
    assert b["missing"] == [day] and b["chosen"][0]["date"] == nxt


def test_dates_only_file_has_no_time_rows_in_the_core_and_matches_the_reference():
    tr = [trade(i, 1792368000000 + i * DAY_MS, 86400, p) for i, p in enumerate([-5, -5, -5, 4, -5, -5, 3, 2, 1, 1, 1, 1, 1, 2])]
    r = run_js([{"trades": tr, "shiftHours": 0, "requested": []}])[0]
    assert r["datesOnly"] is True and all(c["reentry"] == 0 and c["size_after_loss"] == 0 for c in r["chosen"])
    same(r, REF.bad_day(tr, 0, []))


def test_parse_days():
    js = """import { parseDays } from '/home/claude/selloff/site/static/js/tools/bad-day-core.js';
    console.log(JSON.stringify([parseDays('2026-11-05, 2026-11-05;2026-11-06 nope 2026-02-30'), parseDays(''), parseDays(null),
      parseDays('2026-01-01,2026-01-02,2026-01-03,2026-01-04,2026-01-05,2026-01-06')]));"""
    js = js.replace("/home/claude/selloff", REPO)
    r = subprocess.run(["node", "--input-type=module", "-e", js], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    a, b, c, d = json.loads(r.stdout)
    assert a == ["2026-11-05", "2026-11-06"] and b == [] and c == [] and len(d) == 5


# ------------------------------------------------------------------ the page
HAND_CSV = None


def hand_csv(tmp_path, other_days=12):
    rows = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    def pair(day, t1, t2, p_open, p_close):
        rows.append(f"{day},{t1},AAA,Buy,1,{p_open},USD,0")
        rows.append(f"{day},{t2},AAA,Sell,1,{p_close},USD,0")
    import datetime as dt
    d0 = dt.date(2026, 10, 19)
    for k in range(other_days):
        day = (d0 + dt.timedelta(days=k)).isoformat()
        pair(day, "09:30:00", "09:40:00", 100, 101)
        pair(day, "11:00:00", "11:10:00", 100, 101)
    for t1, t2, c in (("09:30:00", "09:40:00", 95), ("09:45:00", "09:55:00", 96), ("10:00:00", "10:10:00", 97), ("13:00:00", "13:10:00", 101)):
        pair("2026-11-05", t1, t2, 100, c)
    p = tmp_path / "bad_day_hand.csv"
    p.write_text("\n".join(rows) + "\n", encoding="utf-8")
    return str(p)


def open_page(browser, site, path, width=1280, scheme="light", **kw):
    ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme, **kw)
    pg = ctx.new_page()
    log = {"requests": [], "console": []}
    pg.on("request", lambda r: log["requests"].append(r.url))
    pg.on("console", lambda m: log["console"].append(m.text))
    pg.on("pageerror", lambda e: log["console"].append(str(e)))
    pg.goto(site["url"] + path)
    pg.wait_for_load_state("networkidle")
    return ctx, pg, log


def table_rows(pg):
    return {r.locator("th").inner_text(): [c.inner_text() for c in r.locator("td").all()] for r in pg.locator("#bd-out table tbody tr").all()}


def test_page_reads_a_file_and_shows_the_day_beside_the_typical_day(browser, built_site, tmp_path):
    ctx, pg, log = open_page(browser, built_site, B + "?d=2026-11-05,2026-02-30,x")
    assert pg.input_value("#bd-days") == "2026-11-05"   # the address fills the box with its valid dates only
    log["requests"].clear()
    pg.set_input_files("#bd-file", hand_csv(tmp_path))
    pg.wait_for_selector("#bd-out:not([hidden])")
    rows = table_rows(pg)
    assert rows["Trades"] == ["4", "2"]
    assert rows["Net result"] == ["−$11.00", "+$2.00"]
    assert rows["Largest loss"] == ["−$5.00", "none"]
    assert rows["Trades opened within 15 minutes of a loss"] == ["2", "0"]
    assert rows["Trades opened after 2 or more losses in a row"] == ["2", "0"]
    assert "Counted, not judged" in pg.inner_text("#bd-out")
    assert all(u.startswith(built_site["url"] + "/static/") for u in log["requests"]), log["requests"]
    assert log["console"] == [] and ctx.cookies() == []
    body = pg.inner_text("main")
    assert not re.search(r"\b(NaN|Infinity|undefined|null)\b", body) and L.lint_text(body, B) == []
    # a second date typed in the box redraws without reading the file again
    pg.fill("#bd-days", "2026-11-05, 2026-10-19")
    pg.press("#bd-days", "Enter")
    assert pg.locator("#bd-out table thead th").count() == 4
    ctx.close()


def test_page_with_a_missing_day_and_with_too_short_a_file(browser, built_site, tmp_path):
    ctx, pg, log = open_page(browser, built_site, B + "?d=2026-03-01")
    pg.set_input_files("#bd-file", hand_csv(tmp_path))
    pg.wait_for_selector("#bd-out:not([hidden])")
    note = pg.inner_text("#bd-notes")
    assert "No closed trades in this file on 1 Mar 2026" in note and "lowest net result" in note
    ctx.close()
    ctx, pg, log = open_page(browser, built_site, B + "?d=2026-11-05")
    (tmp_path / "x").mkdir()
    pg.set_input_files("#bd-file", hand_csv(tmp_path / "x", other_days=5))
    pg.wait_for_selector("#bd-out:not([hidden])")
    assert "needs at least 10 other days" in pg.inner_text("#bd-out")
    ctx.close()


def test_real_public_data_button(browser, built_site):
    ctx, pg, log = open_page(browser, built_site, B + "?d=2026-11-05")
    pg.click("#bd-sample-btn")
    pg.wait_for_selector("#bd-out:not([hidden])")
    assert "No closed trades in this file on 5 Nov 2026" in pg.inner_text("#bd-notes")
    assert pg.locator("#bd-out table tbody tr").count() >= 5
    assert log["console"] == []
    ctx.close()


@pytest.mark.parametrize("width", [320, 390, 1280])
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_no_overflow_and_axe_clean_before_and_after_a_file(browser, built_site, tmp_path, width, scheme):
    ctx, pg, log = open_page(browser, built_site, B + "?d=2026-11-05", width=width, scheme=scheme, bypass_csp=True)
    assert horizontal_overflow(pg) == []
    assert axe_violations(pg) == [], axe_violations(pg)
    pg.set_input_files("#bd-file", hand_csv(tmp_path))
    pg.wait_for_selector("#bd-out:not([hidden])")
    assert horizontal_overflow(pg) == []
    assert axe_violations(pg) == [], axe_violations(pg)
    ctx.close()


def test_page_structure_and_wording(built_site):
    h = (built_site["out"] / "tools" / "bad-day-check" / "index.html").read_text(encoding="utf-8")
    main = h.split("<main", 1)[-1].split("</main>")[0]
    assert " style=" not in h
    assert "data-umami" not in main or "data-umami-event" in main
    t = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", main))
    assert re.search(r"(?i)\bnot (investment )?advice|does not recommend", t)
    assert "Counted, not judged" not in t   # that note is drawn with the result, not printed before a file is read
    assert L.lint_text(t, B) == []


def test_live_region_follows_changes_and_field_hints(browser, built_site, tmp_path):
    """Fix round 1 (F7 to F9): a change of days or shift is announced with the new figures; the days box takes '-' and ','; the shift
    hint gives the direction and the no-daylight-saving limit."""
    ctx, pg, log = open_page(browser, built_site, B + "?d=2026-11-05")
    assert pg.get_attribute("#bd-days", "inputmode") == "text"
    hint = pg.inner_text("#bd-shift-hint")
    assert "adds the hours you choose" in hint and "no daylight-saving adjustment" in hint
    assert pg.locator("#bd-shift option", has_text="+1 hour").count() == 1 and pg.locator("#bd-shift option", has_text="−1 hour").count() == 1
    pg.set_input_files("#bd-file", hand_csv(tmp_path))
    pg.wait_for_selector("#bd-out:not([hidden])")
    pg.locator("#tool-live", has_text="5 Nov 2026").wait_for(state="attached")
    assert "4 trades" in pg.inner_text("#tool-live")
    pg.select_option("#bd-shift", "14")   # the 10:10 and 13:10 closes move to 6 Nov: 2 trades are left on 5 Nov
    pg.locator("#tool-live", has_text="Updated").wait_for(state="attached")
    live = pg.inner_text("#tool-live")
    assert live.startswith("Updated") and "2 trades" in live
    assert log["console"] == []
    ctx.close()
