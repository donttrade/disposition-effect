"""The firm-rules library (site/config/challenge_rules.json, ARCHITECT-CHALLENGE-READINESS §3, §8.3).

Offline only: the schema, a quote for every value (or the field listed as unconfirmed), dates, the
30 / 45-day freshness rules on fake dates, plain links, alphabetical order with no default, and every
usable preset running through both engines. checks/check_rules.py --online re-reads the pages.
"""
import copy
import json
import os
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

DEMO = os.path.join(REPO, "site", "static", "samples", "demo-trades.csv")
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


def test_every_value_has_a_quote_or_is_unconfirmed(lib):
    for p in lib["presets"]:
        if p["status"] == "not_quotable":
            assert p["rules"] is None and p["reason"]
            continue
        quoted = {f for s in p["sources"] for q in s["quotes"] for f in q["fields"]}
        for f in C.QUOTED_FIELDS:
            if f == "trail_stop_at" and p["rules"]["drawdown"] == "static":
                continue
            assert f in quoted or f in p["unconfirmed"], (p["id"], f)
        assert (p["status"] == "complete") == (not p["unconfirmed"])


def test_fully_quoted_presets(lib):
    complete = sorted(p["id"] for p in lib["presets"] if p["status"] == "complete")
    assert complete == ["ftmo-1-step", "ftmo-2-step-challenge", "fundednext-stellar-1-step", "fundednext-stellar-2-step-phase-1"]


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
    p = next(x for x in bad["presets"] if x["status"] == "complete")
    for s in p["sources"]:
        for q in s["quotes"]:
            q["fields"] = [f for f in q["fields"] if f != "target"]
    assert any("target has no quote" in x for x in C.validate(bad, READ_ON))
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
    top = next(p for p in lib["presets"] if p["id"] == "topstep-50k-trading-combine")
    t = R.preset_rules(top, 100000)
    assert (t["rules"]["target"], t["rules"]["max_loss"], t["rules"]["trail_stop_at"]) == (3000, 2000, 0)
    with pytest.raises(ValueError):
        R.preset_rules(next(p for p in lib["presets"] if p["status"] == "not_quotable"))
