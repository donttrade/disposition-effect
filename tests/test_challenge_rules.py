"""The firm-rules library (site/config/challenge_rules.json, ARCHITECT-CHALLENGE-READINESS §3, §8.3).

Offline only: the schema, a quote for every value (or the field listed as unconfirmed), dates, the
30 / 45-day freshness rules on fake dates, plain links, alphabetical order with no default, and every
usable preset running through both engines. checks/check_rules.py --online re-reads the pages.
"""
import copy
import json
import os
import re
import sys
from datetime import date, timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, HERE)
import check_rules as C  # noqa: E402
import engine_ref as E  # noqa: E402
import readiness_ref as R  # noqa: E402

DEMO = os.path.join(REPO, "site", "static", "samples", "example-trades.csv")
READ_ON = date(2026, 10, 29)


@pytest.fixture(scope="module")
def lib():
    return C.load()


def test_library_validates(lib):
    assert C.validate(lib, READ_ON) == []
    assert C.validate(lib) == []          # and today: nothing dated in the future


def test_ten_firms_each_with_a_dated_source(lib):
    firms = sorted({p["firm"] for p in lib["presets"]})
    assert len(firms) == 10, firms
    for p in lib["presets"]:
        assert p["sources"] and all(s["read_on"] and s["url"].startswith("https://") for s in p["sources"])
        assert p["last_checked"] == "2026-10-29" and p["checked_by"]


def test_every_value_is_quoted_or_not_stated(lib):
    for p in lib["presets"]:
        if p["status"] == "not_quotable":
            assert p["rules"] is None and p["reason"]
            continue
        backing = {}
        for s in p["sources"]:
            for q in s["quotes"]:
                assert q["section"] and C.RULE_SECTION.search(q["section"]), (p["id"], q)
                for f in q["fields"]:
                    backing.setdefault(f, []).append(q["text"])
        for f in C.QUOTED_FIELDS:
            v = p["rules"][f]
            if v == C.NOT_STATED:
                assert f not in backing, (p["id"], f)
            elif C.relevant(f, p["rules"]):
                assert f in backing, (p["id"], f)
                for t in C.support_terms(f, v, p):     # the value (or key term) is inside a quote
                    assert any(re.search(t, C.norm(q), re.I) for q in backing[f]), (p["id"], f, t)
        assert (p["status"] == "complete") == (not C.not_stated(p))


def test_no_preset_is_complete_and_the_gaps_are_named(lib):
    # Tester F1: absence values are "not stated" unless a rules sentence says so
    gaps = {p["id"]: C.not_stated(p) for p in lib["presets"] if p["status"] != "not_quotable"}
    assert all(p["status"] == "partial" for p in lib["presets"] if p["status"] != "not_quotable")
    assert gaps["ftmo-1-step"] == ["min_days", "time_limit"]
    assert gaps["ftmo-2-step-challenge"] == ["consistency", "time_limit"]
    assert gaps["fundednext-stellar-1-step"] == ["target_check", "consistency"]
    assert "day_start" in gaps["the5ers-high-stakes-step-1"] and "drawdown" in gaps["the5ers-high-stakes-step-1"]


def test_target_timing_and_day_counting_fields(lib):
    by = {p["id"]: p for p in lib["presets"]}
    assert by["ftmo-1-step"]["rules"]["target_check"] == "intraday"
    assert by["fundednext-stellar-2-step-phase-1"]["rules"]["count_day_if"] == "non-zero P&L"
    assert by["ftmo-2-step-challenge"]["rules"]["count_day_if"] == "any trade"
    for p in lib["presets"]:
        if p["status"] == "not_quotable":
            continue
        if p["rules"]["target_check"] == C.NOT_STATED:   # Tester F2: an unknown rule is listed under not_modelled
            assert any(x.startswith("whether the target counts") for x in p["not_modelled"]), p["id"]


def test_day_boundaries_come_from_quoted_text(lib):
    by = {p["id"]: p for p in lib["presets"]}
    for p in lib["presets"]:
        if p["status"] != "not_quotable":
            assert p["rules"]["day_start"] == C.NOT_STATED or p["rules"]["day_start"]["tz"] != "file", p["id"]
    assert by["fundednext-stellar-1-step"]["rules"]["day_start"] == {"tz": "broker", "hour": 0}
    assert by["the5ers-high-stakes-step-1"]["rules"]["day_start"] == C.NOT_STATED
    assert by["alpha-capital-group-alpha-pro-10-phase-1"]["rules"]["day_start"] == {"tz": "Etc/GMT-3", "hour": 0}
    for pid in ("blue-guardian-1-step-standard", "blue-guardian-2-step-standard-phase-1"):
        assert any("5pm EST" in q["text"] for s in by[pid]["sources"] for q in s["quotes"])
        assert any("EST" in x and "interpretation" in x for x in by[pid]["not_modelled"])
    assert any("GMT+2" in x for x in by["fundednext-stellar-1-step"]["not_modelled"])


def test_weak_quotes_fail(lib):
    def first(bad, pid):
        return next(x for x in bad["presets"] if x["id"] == pid)
    # a slogan under a call to action does not back a value
    bad = copy.deepcopy(lib)
    p = first(bad, "ftmo-2-step-challenge")
    p["rules"]["time_limit"] = None
    p["sources"][0]["quotes"].append({"fields": ["time_limit"], "section": "Start Trading With FTMO Today", "text": "No time limit"})
    assert any("not a rules section" in x for x in C.validate(bad, READ_ON))
    # a quote that does not hold the value
    bad = copy.deepcopy(lib)
    p = first(bad, "fundednext-stellar-1-step")
    p["rules"]["consistency"] = None
    p["sources"][0]["quotes"].append({"fields": ["consistency"], "section": "Profit Target",
                                      "text": "Every rule, every condition, published before you start your challenge."})
    assert any("no quote for consistency states" in x for x in C.validate(bad, READ_ON))
    # a value without a quote, and a "not stated" value with one
    bad = copy.deepcopy(lib)
    first(bad, "ftmo-1-step")["rules"]["min_days"] = 0
    assert any("min_days = 0 has no quote" in x for x in C.validate(bad, READ_ON))
    bad = copy.deepcopy(lib)
    p = first(bad, "ftmo-1-step")
    p["rules"]["target_check"] = C.NOT_STATED
    assert any("target_check is 'not stated' but a quote backs it" in x for x in C.validate(bad, READ_ON))
    bad = copy.deepcopy(lib)
    first(bad, "fundednext-stellar-1-step")["rules"]["day_start"] = {"tz": "file", "hour": 0}
    assert any("day_start is {tz, hour}" in x for x in C.validate(bad, READ_ON))


def test_quote_must_sit_under_its_section():
    filler = "<p>" + "x " * 1500 + "</p>"
    page = ("<h2>Profit Target</h2><p>The target is 10%.</p>" + filler + "<footer><p>No time limit</p></footer>")
    text = C.page_text(page)
    assert C.quote_in_section(text, "Profit Target", "The target is 10%.")
    assert not C.quote_in_section(text, "Profit Target", "No time limit")      # on the page, but far from its heading
    src = {"quotes": [{"section": "Profit Target", "text": "No time limit"}]}
    assert C.check_source(src, page) == ("quote missing", ["No time limit"])
    assert C.check_source(src, "<title>Just a moment...</title>")[0] == "open by hand"


def test_freshness_on_fake_dates(lib):
    assert C.freshness(lib, READ_ON + timedelta(days=30)) == ([], [])
    warn, hidden = C.freshness(lib, READ_ON + timedelta(days=31))
    assert len(warn) == len(lib["presets"]) and hidden == []
    warn, hidden = C.freshness(lib, READ_ON + timedelta(days=46))
    assert warn == [] and len(hidden) == len(lib["presets"])
    assert C.shown(lib, READ_ON + timedelta(days=45)) and C.shown(lib, READ_ON + timedelta(days=46)) == []
    assert all(p["status"] != "not_quotable" for p in C.shown(lib, READ_ON))


def test_future_dates_and_missing_quotes_fail(lib):
    bad = copy.deepcopy(lib)
    bad["presets"][0]["last_checked"] = "2099-01-01"
    assert any("in the future" in x for x in C.validate(bad, READ_ON))
    bad = copy.deepcopy(lib)
    p = next(x for x in bad["presets"] if x["id"] == "ftmo-1-step")
    for s in p["sources"]:
        for q in s["quotes"]:
            q["fields"] = [f for f in q["fields"] if f != "target"]
    assert any("target = 10000 has no quote" in x for x in C.validate(bad, READ_ON))
    bad = copy.deepcopy(lib)
    bad["presets"][0]["sources"][0]["url"] += "?ref=abc"
    assert any("tracking" in x for x in C.validate(bad, READ_ON))
    bad = copy.deepcopy(lib)
    bad["presets"].reverse()
    assert any("alphabetical" in x for x in C.validate(bad, READ_ON))


def test_plain_links_alphabetical_no_default(lib):
    for p in lib["presets"]:
        for s in p["sources"]:
            u = s["url"].lower()
            assert not any(t in u for t in ("?", "#", "ref=", "aff", "utm_", "coupon")), u
        assert "default" not in p
    order = [(p["firm"].lower(), p["program"].lower()) for p in lib["presets"]]
    assert order == sorted(order)
    assert "default" not in lib


def test_quotes_found_by_the_checker_normaliser():
    text = C.page_text("<p>Stellar <bdi>⁦1⁩</bdi>-Step: <b>3%</b> of initial&nbsp;balance</p><li>Next</li>")
    assert C.quote_found(text, "Stellar 1-Step: 3% of initial balance")
    assert not C.quote_found(text, "of initial balance Next Stellar")


def usable(lib):
    return [p for p in lib["presets"] if p["status"] != "not_quotable"]


def test_presets_run_through_both_engines(lib, browser, repo_server):
    trades = E.parse_file(open(DEMO, "rb").read())["trades"]
    ctx = browser.new_context()
    pg = ctx.new_page()
    pg.goto(repo_server + "/tests/harness.html")
    for p in usable(lib):
        for size in (None, 25000):
            want = R.preset_rules(p, size)
            got = pg.evaluate("""async ([p, size]) => (await import('/site/static/js/tools/challenge-presets.js')).presetRules(p, size)""", [p, size])
            assert got == json.loads(json.dumps(want)), p["id"]
            # the demo file's P&L is in dollars of a small account: scale it so the presets' limits bite
            scaled = [{**t, "pnl": t["pnl"] * 40} for t in trades]
            g = R.group_days(scaled, "UTC", want["dayStart"])
            gj = pg.evaluate("""async ([t, ds]) => (await import('/site/static/js/tools/prop-sim-core.js')).groupDays(t, {fileTz: 'UTC', dayStart: ds})""",
                             [scaled, want["dayStart"]])
            assert gj == json.loads(json.dumps(g)), p["id"]
            q = {"mode": "sequence", "days": g["days"], "rules": want["rules"]}
            sj = pg.evaluate("""async (q) => (await import('/site/static/js/tools/prop-sim-core.js')).simulate(q)""", q)
            assert sj == json.loads(json.dumps(R.simulate(q))), p["id"]
            f = {**q, "mode": "file", "runs": 500, "seed": 3, "stream": "paired"}
            fj = pg.evaluate("""async (q) => (await import('/site/static/js/tools/prop-sim-core.js')).simulate(q)""", f)
            assert fj == json.loads(json.dumps(R.simulate(f))), p["id"]
    ctx.close()


def test_percent_presets_scale_and_fixed_presets_do_not(lib):
    ftmo = next(p for p in lib["presets"] if p["id"] == "ftmo-1-step")
    r = R.preset_rules(ftmo, 50000)
    assert (r["rules"]["target"], r["rules"]["daily_loss"], r["rules"]["max_loss"]) == (5000, 1500, 5000)
    assert r["dayStart"] == {"tz": "Europe/Prague", "hour": 0}
    assert r["rules"]["target_check"] == "intraday" and r["notStated"] == ["min_days", "time_limit"]
    assert (r["rules"]["min_days"], r["rules"]["time_limit"]) == (0, None)    # defaults for what is not stated
    fn = R.preset_rules(next(p for p in lib["presets"] if p["id"] == "fundednext-stellar-1-step"))
    assert fn["rules"]["count_day_if"] == "nonzero" and fn["rules"]["target_check"] == "eod" and fn["rules"]["consistency"] is None
    top = next(p for p in lib["presets"] if p["id"] == "topstep-50k-trading-combine")
    t = R.preset_rules(top, 100000)
    assert (t["rules"]["target"], t["rules"]["max_loss"], t["rules"]["trail_stop_at"]) == (3000, 2000, 0)
    with pytest.raises(ValueError):
        R.preset_rules(next(p for p in lib["presets"] if p["status"] == "not_quotable"))
