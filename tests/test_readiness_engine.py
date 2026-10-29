"""Challenge Readiness Check engine (ARCHITECT-CHALLENGE-READINESS-2026-10-29 R1, R2, R2b).

Hand-worked cases for every rule type (§8.1 A-I, §8.8 W0-W7) on BOTH the Python reference
(tests/reference/readiness_ref.py) and the browser engine (prop-sim-core.js, habit-flags.js); the JS
equals the reference on a grid of the new fields; the old parameters give the old output (golden);
habit flags on hand fixtures and against the paid engine (habits.mjs, when dt-private is present);
the ranked rules (built, switched off); and the wording of every engine string.
"""
import json
import math
import os
import random
import re
import subprocess
import sys
from datetime import datetime, timezone

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, HERE)
import engine_ref as E  # noqa: E402
import readiness_ref as R  # noqa: E402
from test_tool_prop_sim import RULES, simulate_py, demo_days  # noqa: E402

DEMO = os.path.join(REPO, "site", "static", "samples", "example-trades.csv")
CORE = "/site/static/js/tools/prop-sim-core.js"
HAB = "/site/static/js/tools/habit-flags.js"


# ------------------------------------------------------------------ helpers
def ms(s):
    """'2026-10-27 21:30' as naive ms (file time read as if UTC, like the engine)."""
    return int(datetime.strptime(s, "%Y-%m-%d %H:%M").replace(tzinfo=timezone.utc).timestamp() * 1000)


def rules(**kw):
    base = {"target": 1000, "daily_loss": None, "max_loss": 10000, "time_limit": None, "min_days": 0}
    base.update(kw)
    return base


def seq_p(days, **rkw):
    rk = dict(rkw)
    rk.setdefault("time_limit", len(days))
    return {"mode": "sequence", "days": days, "rules": rules(**rk)}


@pytest.fixture(scope="module")
def page(browser, repo_server):
    ctx = browser.new_context(timezone_id="America/Toronto")   # the engine never reads the browser's zone
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.goto(repo_server + "/tests/harness.html")
    pg.wait_for_function("document.getElementById('status').textContent === 'ready'")
    yield pg
    assert not errors, errors
    ctx.close()


def js(page, fn, *args):
    """Call an export of prop-sim-core.js (or habit-flags.js with 'hab.' prefix) with JSON args."""
    return page.evaluate("""async ([fn, args, core, hab]) => {
        const c = await import(core); const h = await import(hab);
        const f = fn.startsWith('hab.') ? h[fn.slice(4)] : c[fn];
        const r = f(...args);
        return JSON.parse(JSON.stringify(r, (k, v) => (v instanceof Uint8Array ? Array.from(v) : v)));
    }""", [fn, list(args), CORE, HAB])


def both(page, fn_js, fn_py, *args):
    a = js(page, fn_js, *args)
    b = fn_py(*args)
    b = json.loads(json.dumps(b))
    assert a == b, (fn_js, a, b)
    return a


def sim(page, p):
    return both(page, "simulate", R.simulate, p)


# ------------------------------------------------------------------ §8.1 rule engine, hand-worked (sequence mode)
def test_A_static_vs_eod_trailing(page):
    d = [[80], [-60], [-50]]
    s = sim(page, seq_p(d, max_loss=100, time_limit=3, drawdown="static"))
    assert (s["outcome"], s["day"]) == ("timeout", 3)
    t = sim(page, seq_p(d, max_loss=100, time_limit=3, drawdown="trailing_eod"))
    assert (t["outcome"], t["day"], t["why"]) == ("bust", 3, "max")
    old = sim(page, seq_p(d, max_loss=100, time_limit=3, trailing=True))   # the old field means trailing_eod
    assert (old["outcome"], old["day"]) == ("bust", 3)


def test_B_eod_vs_per_trade_trailing(page):
    d = [[80, -40], [-65]]
    e = sim(page, seq_p(d, max_loss=100, time_limit=2, drawdown="trailing_eod"))
    assert e["outcome"] == "timeout"
    t = sim(page, seq_p(d, max_loss=100, time_limit=2, drawdown="trailing_trade"))
    assert (t["outcome"], t["day"], t["why"]) == ("bust", 2, "max")


def test_C_trailing_lock(page):
    d = [[150], [30], [-170], [-15]]
    a = sim(page, seq_p(d, max_loss=100, time_limit=4, drawdown="trailing_eod"))
    assert (a["outcome"], a["day"], a["why"]) == ("bust", 3, "max")
    b = sim(page, seq_p(d, max_loss=100, time_limit=4, drawdown="trailing_eod", trail_stop_at=0))
    assert (b["outcome"], b["day"], b["why"]) == ("bust", 4, "max")
    c = sim(page, seq_p(d, max_loss=100, time_limit=4, drawdown="trailing_trade", trail_stop_at=0))
    assert (c["outcome"], c["day"]) == ("bust", 4)


def trade(open_s, close_s, pnl, symbol="X", qty=1.0):
    o, c = ms(open_s), ms(close_s)
    return {"open_ts": o, "close_ts": c, "hold_s": (c - o) // 1000, "pnl": pnl, "symbol": symbol, "qty": qty}


def group(page, trades, file_tz=None, day_start=None):
    a = js(page, "groupDays", trades, {"fileTz": file_tz, "dayStart": day_start})
    b = R.group_days(trades, file_tz, day_start)
    assert a == json.loads(json.dumps(b)), (a, b)
    return a


D1 = [trade("2026-10-27 21:00", "2026-10-27 21:30", -60), trade("2026-10-27 22:00", "2026-10-27 22:30", -60)]


def test_D1_daily_reset_us_futures(page):
    r = rules(daily_loss=100, max_loss=10000, time_limit=5)
    utc = group(page, D1)
    assert utc["days"] == [[-60, -60]]
    assert sim(page, {"mode": "sequence", "days": utc["days"], "rules": r})["why"] == "daily"
    chi = group(page, D1, "UTC", {"tz": "America/Chicago", "hour": 17})
    assert chi["days"] == [[-60], [-60]]
    assert sim(page, {"mode": "sequence", "days": chi["days"], "rules": r})["outcome"] == "end"
    pra = group(page, D1, "UTC", {"tz": "Europe/Prague", "hour": 0})   # CET after 25 Oct: 22:30 and 23:30
    assert pra["days"] == [[-60, -60]]
    assert sim(page, {"mode": "sequence", "days": pra["days"], "rules": r})["why"] == "daily"
    # the old call (no options) is the UTC calendar day, as before
    assert js(page, "tradingDays", D1) == [[-60, -60]]


def test_D2_dst(page):
    chi = {"tz": "America/Chicago", "hour": 17}
    k = lambda s: js(page, "dayKey", ms(s), "UTC", chi)  # noqa: E731
    kp = lambda s: R.day_key(ms(s), "UTC", chi)  # noqa: E731
    for s in ("2026-11-03 22:30", "2026-11-03 20:00", "2026-10-27 22:30", "2026-10-27 20:00"):
        assert k(s) == kp(s)
    # 3 Nov (CST, UTC-6): 22:30 UTC is 16:30, the same trading day as 20:00 UTC (14:00)
    assert k("2026-11-03 22:30") == k("2026-11-03 20:00")
    # 27 Oct (CDT, UTC-5): 22:30 UTC is 17:30, the NEXT trading day
    assert k("2026-10-27 22:30") == k("2026-10-27 20:00") + 1


def test_D3_file_time_zone(page):
    t = [trade("2026-10-26 22:00", "2026-10-26 23:30", 10), trade("2026-10-27 01:00", "2026-10-27 01:30", 20)]
    assert group(page, t)["days"] == [[10], [20]]                          # UTC: two days
    assert group(page, t, {"offset_min": 120})["days"] == [[10, 20]]        # GMT+2: 21:30 and 23:30 UTC on 26 Oct
    assert group(page, t, "Europe/Athens")["days"] == [[10, 20]]            # EET after 25 Oct is GMT+2
    # broker server time: New York + 7 h, so GMT+3 on 27 Oct (EDT) and GMT+2 on 3 Nov (EST)
    assert js(page, "fileToUtc", ms("2026-10-27 02:30"), "broker") == ms("2026-10-26 23:30")
    assert js(page, "fileToUtc", ms("2026-11-03 01:30"), "broker") == ms("2026-11-02 23:30")
    assert R.file_to_utc(ms("2026-10-27 02:30"), "broker") == ms("2026-10-26 23:30")
    assert R.file_to_utc(ms("2026-11-03 01:30"), "broker") == ms("2026-11-02 23:30")
    # the firm's day on the file's own clock (MT5 server midnight)
    assert group(page, t, {"offset_min": 120}, {"tz": "file", "hour": 0})["days"] == [[10], [20]]


def test_D_dst_gap_and_overlap_agree(page):
    # wall-clock times that do not exist (spring forward) or exist twice (fall back) in New York
    for s in ("2026-03-08 02:30", "2026-11-01 01:30", "2026-03-08 03:00", "2026-11-01 02:00"):
        assert js(page, "zonedToUtc", ms(s), "America/New_York") == R.zoned_to_utc(ms(s), "America/New_York"), s


def test_E_consistency_ftmo_style(page):
    d = [[90], [20], [40], [50]]
    e = sim(page, seq_p(d, target=100, consistency=0.5, time_limit=4))
    assert (e["outcome"], e["day"], e["held_consistency"], e["target_day"]) == ("pass", 4, 1, 2)
    n = sim(page, seq_p(d, target=100, time_limit=4))
    assert (n["outcome"], n["day"], n["held_consistency"]) == ("pass", 2, 0)


def test_E2_consistency_equality_passes(page):
    e = sim(page, seq_p([[90], [30], [-20], [80]], target=100, consistency=0.5, time_limit=4))
    assert (e["outcome"], e["day"]) == ("pass", 4)


def test_E3_topstep_form(page):
    a = sim(page, seq_p([[2000], [1000]], target=3000, consistency=0.55, time_limit=5))
    assert (a["outcome"], a["held_consistency"]) == ("end", 1)
    b = sim(page, seq_p([[2000], [1000], [700]], target=3000, consistency=0.55, time_limit=5))
    assert (b["outcome"], b["day"]) == ("pass", 3)


def test_F_limit_equality_busts(page):
    f = sim(page, seq_p([[-100]], daily_loss=100))
    assert (f["outcome"], f["why"], f["bust_daily"]) == ("bust", "daily", 1)


def test_G_profitable_days(page):
    g = sim(page, seq_p([[400], [30], [60], [60]], target=500, min_days_kind="profitable", min_days=3,
                        profitable_day_min=50, time_limit=4))
    assert (g["outcome"], g["day"]) == ("pass", 4)
    h = sim(page, seq_p([[400], [30], [40], [60]], target=500, min_days_kind="profitable", min_days=3,
                        profitable_day_min=50, time_limit=4))
    assert (h["outcome"], h["held_min_days"]) == ("timeout", 1)
    t = sim(page, seq_p([[400], [30], [40], [60]], target=500, min_days=3, time_limit=4))  # trading days: passes
    assert (t["outcome"], t["day"]) == ("pass", 4)


def test_H_no_time_limit_is_capped(page):
    h = sim(page, seq_p([[1]] * 300, time_limit=None))
    assert (h["outcome"], h["day"], h["capped"]) == ("timeout", 250, True)
    assert R.NO_LIMIT_CAP == 250 and js(page, "normRules", rules())["limit"] == 250


def test_I_daily_before_max(page):
    i = sim(page, seq_p([[-50]], daily_loss=50, max_loss=50))
    assert (i["why"], i["bust_daily"], i["bust_max"]) == ("daily", 1, 0)


def test_min_trading_days_hold(page):
    m = sim(page, seq_p([[600], [10]], target=500, min_days=3, time_limit=2))
    assert (m["outcome"], m["held_min_days"]) == ("timeout", 1)


# ------------------------------------------------------------------ golden: the old parameters give the old output
LEGACY_KEYS = ("runs", "pass", "bust", "timeout", "bust_daily", "bust_max", "bust_after_streak", "mode", "median_pass_days")


@pytest.mark.parametrize("seed", [20261022, 7, 4294967295])
@pytest.mark.parametrize("ri", range(len(RULES)))
def test_golden_python(seed, ri):
    p = {"mode": "file", "days": demo_days(), "rules": RULES[ri], "seed": seed, "runs": 3000}
    old = simulate_py(p)
    new = R.simulate(p)
    for k in old:
        assert new[k] == old[k], (k, new[k], old[k])
    assert new["stream"] == "legacy" and new["trades_left_out"] == 0


@pytest.mark.parametrize("ri", range(len(RULES)))
def test_golden_js_file_and_manual(page, ri):
    p = {"mode": "file", "days": demo_days(), "rules": RULES[ri], "seed": 20261022, "runs": 10000}
    old = simulate_py(p)
    new = js(page, "simulate", p)
    assert {k: new[k] for k in LEGACY_KEYS} == {k: old.get(k, new[k]) for k in LEGACY_KEYS}
    m = {"mode": "manual", "win_rate": 0.48, "avg_win": 90, "avg_loss": 70, "trades_per_day": 3,
         "rules": RULES[ri], "seed": 7, "runs": 10000}
    old_m, new_m = simulate_py(m), js(page, "simulate", m)
    for k in old_m:
        assert new_m[k] == old_m[k], k


# ------------------------------------------------------------------ JS = Python across a grid of the new fields
GRID = [
    rules(target=600, daily_loss=250, max_loss=500, time_limit=60, min_days=5),
    rules(target=400, max_loss=300, drawdown="trailing_trade", time_limit=30),
    rules(target=400, max_loss=300, drawdown="trailing_eod", trail_stop_at=0, time_limit=None, consistency=0.5),
    rules(target=300, daily_loss=150, max_loss=500, drawdown="trailing_trade", trail_stop_at=50, consistency=0.3,
          min_days_kind="profitable", min_days=3, profitable_day_min=20, time_limit=90),
    rules(target=250, daily_loss=120, max_loss=400, consistency=0.55, min_days=2, time_limit=None),
]


def demo_grouped():
    trades = E.parse_file(open(DEMO, "rb").read())["trades"]
    return trades, R.group_days(trades)


@pytest.mark.parametrize("stream", ["legacy", "paired"])
@pytest.mark.parametrize("gi", range(len(GRID)))
def test_grid_file_mode_js_equals_python(page, gi, stream):
    _, g = demo_grouped()
    p = {"mode": "file", "days": g["days"], "rules": GRID[gi], "seed": 11, "runs": 2000, "stream": stream}
    out = sim(page, p)
    assert out["pass"] + out["bust"] + out["timeout"] == 2000
    assert out["bust_daily"] + out["bust_max"] == out["bust"]
    assert sum(c for _, _, c in out["bust_at"]) == out["bust"]


@pytest.mark.parametrize("personal", [
    {"stop_after_losses": 2}, {"stop_at_day_loss": 0.5}, {"max_trades": 3}, {"cooldown_s": 900},
    {"after_loss_factor": 0.5}, {"stop_after_losses": 1, "cooldown_s": 300}, {"max_trades": 2, "after_loss_factor": 0.25},
    {"stop_at_day_loss_amount": 60},
])
def test_whatif_grid_js_equals_python(page, personal):
    _, g = demo_grouped()
    p = {"mode": "file", "days": g["days"], "open_s": g["open_s"], "close_s": g["close_s"], "seed": 5, "runs": 2000,
         "rules": rules(target=300, daily_loss=None if "stop_at_day_loss_amount" in personal else 120, max_loss=400,
                        time_limit=60)}
    w = both(page, "whatIf", lambda a, b: {**R.what_if(a, b), "label": R.rule_label(b)}, p, personal)
    assert w["label"] == R.rule_label(personal)
    assert w["before"]["trades_left_out"] == 0
    assert w["after"]["trades_seen"] >= w["after"]["trades_left_out"]


def test_manual_mode_whatif_and_paired_parity(page):
    p = {"mode": "manual", "win_rate": 0.45, "avg_win": 80, "avg_loss": 60, "trades_per_day": 5, "seed": 3, "runs": 2000,
         "rules": rules(target=500, daily_loss=150, max_loss=600, time_limit=40)}
    both(page, "whatIf", lambda a, b: {**R.what_if(a, b), "label": R.rule_label(b)}, p, {"stop_after_losses": 2})
    assert js(page, "whatIf", p, {"cooldown_s": 900})["unavailable"] == "no_times"


# ------------------------------------------------------------------ §8.8 what-if, hand-worked
def one_day(page, day, personal, **rkw):
    p = seq_p([day], **rkw)
    p.update({k: v for k, v in rkw.items() if k in ("open_s", "close_s")})
    return sim(page, {**p, "personal": personal}), sim(page, p)


def test_W0_empty_rule_is_identical_on_every_run(page):
    _, g = demo_grouped()
    p = {"mode": "file", "days": g["days"], "seed": 9, "runs": 3000, "rules": GRID[0]}
    for personal in (None, {}, {"max_trades": None}):
        w = js(page, "whatIf", p, personal)
        assert w["before"] == w["after"]
        assert w["before"]["stream"] == "paired" and w["before"]["method"] == R.METHOD_VERSION["paired"]
    # pairing: run k's draws depend on (seed, k) only, so the first 500 runs of a 3,000-run batch are
    # exactly a 500-run batch, with or without a rule that changes the runs' lengths
    for personal in (None, {"stop_after_losses": 1}):
        q = {**p, "stream": "paired", "personal": personal}
        small, big = R.simulate({**q, "runs": 500}), R.simulate({**q, "runs": 3000})
        assert small["pass"] <= big["pass"] and small["bust"] <= big["bust"]
    assert js(page, "mix32", 20261022, 0) == R.mix32(20261022, 0)
    assert [js(page, "mix32", 4294967295, k) for k in (0, 1, 9999)] == [R.mix32(4294967295, k) for k in (0, 1, 9999)]


def test_W1_stop_after_two_losses(page):
    w, base = one_day(page, [-10, -10, -30, 50], {"stop_after_losses": 2})
    assert w["day_pnl"] == [-20] and base["day_pnl"] == [0] and w["trades_left_out"] == 2


def test_W2_stop_at_half_the_daily_limit(page):
    w, base = one_day(page, [-30, -30, 80], {"stop_at_day_loss": 0.5}, daily_loss=100)
    assert w["day_pnl"] == [-60] and base["day_pnl"] == [20] and w["trades_left_out"] == 1


def test_W3_max_trades(page):
    w, base = one_day(page, [5, 5, 5, -40], {"max_trades": 3})
    assert w["day_pnl"] == [15] and base["day_pnl"] == [-25]


def test_W4_cooldown(page):
    t = [trade("2026-10-27 09:00", "2026-10-27 09:05", -20), trade("2026-10-27 09:10", "2026-10-27 09:20", -30),
         trade("2026-10-27 09:25", "2026-10-27 09:30", 40)]
    g = group(page, t)
    p = {"mode": "sequence", "days": g["days"], "open_s": g["open_s"], "close_s": g["close_s"], "rules": rules(time_limit=1)}
    w = sim(page, {**p, "personal": {"cooldown_s": 900}})
    assert w["day_pnl"] == [20] and w["trades_left_out"] == 1   # T2 out (5 min); T3 in (20 min after T1's close)
    # T2's own loss never starts a cool-down: T3 opens 5 minutes after T2's close and is still taken
    assert sim(page, p)["day_pnl"] == [-10]


def test_W5_after_loss_factor(page):
    w, base = one_day(page, [-20, 40, -10, -10], {"after_loss_factor": 0.5})
    assert w["day_pnl"] == [-15] and base["day_pnl"] == [0] and w["trades_left_out"] == 0


def test_W6_stop_after_one_loss_avoids_the_daily_bust(page):
    w, base = one_day(page, [-30, -30], {"stop_after_losses": 1}, daily_loss=50)
    assert (base["outcome"], base["why"]) == ("bust", "daily")
    assert w["outcome"] == "timeout" and w["day_pnl"] == [-30]


def test_W7_cooldown_on_dates_only_never_runs_silently(page):
    p = {"mode": "sequence", "days": [[-5, -5]], "open_s": [[0, 0]], "close_s": [[0, 0]], "dates_only": True,
         "rules": rules(time_limit=1)}
    w = js(page, "whatIf", p, {"cooldown_s": 900})
    assert w["unavailable"] == "dates_only" and w["message"] == "Not available for files with dates but no times."
    assert R.what_if(p, {"cooldown_s": 900})["unavailable"] == "dates_only"
    with pytest.raises(Exception):
        js(page, "simulate", {**p, "personal": {"cooldown_s": 900}})


def test_whatif_rule_limits(page):
    p = seq_p([[1]])
    for bad in ({"stop_after_losses": 0}, {"stop_at_day_loss": 0.5}, {"max_trades": 51}, {"cooldown_s": 90},
                {"after_loss_factor": 0.3}, {"stop_after_losses": 1, "max_trades": 1, "after_loss_factor": 0.5},
                {"no_such_rule": 1}):
        with pytest.raises(Exception):
            js(page, "simulate", {**p, "personal": bad, "open_s": [[0]], "close_s": [[0]]})
    assert js(page, "personalUnavailable", p, {"stop_at_day_loss": 0.5}) == "no_daily"


def test_rule_labels(page):
    cases = {
        json.dumps({"stop_after_losses": 1}): "Stop for the day after 1 losing trade",
        json.dumps({"stop_at_day_loss": 0.5}): "Stop for the day at 50% of the daily loss limit",
        json.dumps({"max_trades": 3}): "At most 3 trades a day",
        json.dumps({"cooldown_s": 900}): "No new trade for 15 minutes after a loss",
        json.dumps({"after_loss_factor": 0.5}): "Count each trade after a loss at half its result",
        json.dumps({"stop_after_losses": 2, "max_trades": 1}): "Stop for the day after 2 losing trades + At most 1 trade a day",
    }
    for k, want in cases.items():
        x = json.loads(k)
        assert js(page, "ruleLabel", x) == want == R.rule_label(x)


# ------------------------------------------------------------------ ranked rules (built, switched off)
def test_ranked_is_off_by_default(page):
    assert page.evaluate(f"import('{CORE}').then(m => m.WHATIF_RANKED)") is False
    p = {"mode": "sequence", "days": [[1]], "rules": rules(time_limit=1)}
    assert js(page, "rankRules", p) == {"enabled": False} == R.rank_rules(p)
    assert js(page, "rankRules", p, {"enabled": 1}) == {"enabled": False}
    src = open(os.path.join(REPO, "site", "static", "js", "tools", "prop-sim-worker.js"), encoding="utf-8").read()
    assert "enabled: WHATIF_RANKED" in src and "enabled: true" not in src


RANKED_SRC = "export const WHATIF_RANKED = false;"


def test_ranked_flag_comes_from_site_toml(built_site, tmp_path):
    """[flags] whatif_ranked (default false) is written into the built engine; true only when the flag is."""
    core = os.path.join(REPO, "site", "static", "js", "tools", "prop-sim-core.js")
    assert open(core, encoding="utf-8").read().count(RANKED_SRC) == 1
    toml = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    assert re.search(r"^whatif_ranked = false\b", toml, re.M)
    off = (built_site["out"] / "static" / "js" / "tools" / "prop-sim-core.js").read_text(encoding="utf-8")
    assert RANKED_SRC in off and "WHATIF_RANKED = true" not in off
    on_toml = tmp_path / "site.toml"
    on_toml.write_text(re.sub(r"^whatif_ranked = false", "whatif_ranked = true", toml, flags=re.M), encoding="utf-8")
    out = tmp_path / "_site"
    env = {**os.environ, "DT_OUT": str(out), "DT_SITE_TOML": str(on_toml)}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    on = (out / "static" / "js" / "tools" / "prop-sim-core.js").read_text(encoding="utf-8")
    assert "export const WHATIF_RANKED = true;" in on and RANKED_SRC not in on
    worker = (out / "static" / "js" / "tools" / "prop-sim-worker.js").read_text(encoding="utf-8")
    worker_off = (built_site["out"] / "static" / "js" / "tools" / "prop-sim-worker.js").read_text(encoding="utf-8")
    assert worker != worker_off   # the worker imports the engine with its own cache-busting version


def test_ranked_only_max_one_trade_changes_the_result(page):
    days = [[50, -10, 5]] * 4
    p = {"mode": "file", "days": days, "open_s": [[0, 100000, 200000]] * 4, "close_s": [[10, 100010, 200010]] * 4,
         "seed": 1, "runs": 2000, "rules": rules(target=250, max_loss=10000, time_limit=5)}
    a = js(page, "rankRules", p, {"enabled": True})
    b = R.rank_rules(p, enabled=True)
    assert a == json.loads(json.dumps(b))
    assert [x["rule"] for x in a["ranked"]] == [{"max_trades": 1}]
    assert a["ranked"][0]["before"]["pass"] == 0 and a["ranked"][0]["after"]["pass"] == 2000
    assert a["tried"] == 12   # 15 in the grid; the three "% of the daily limit" rules need a daily limit
    assert all(g.get("unavailable") == "no_daily" for g in a["grid"] if "stop_at_day_loss" in g["rule"])


def test_ranked_never_lists_the_size_rule(page):
    p = {"mode": "file", "days": [[-10, -20, 100]], "seed": 1, "runs": 1000,
         "rules": rules(target=30, daily_loss=25, max_loss=10000, time_limit=1)}
    a = js(page, "rankRules", p, {"enabled": True})
    assert a == json.loads(json.dumps(R.rank_rules(p, enabled=True)))
    factor = [g for g in a["grid"] if g["rule"] == {"after_loss_factor": 0.5}][0]
    assert factor["rise"] == 1000          # it would rank first...
    assert a["ranked"] == []               # ...but the size rule is never ranked, and nothing else rose 3 points
    assert all(g["unavailable"] == "no_times" for g in a["grid"] if "cooldown_s" in g["rule"])


# ------------------------------------------------------------------ §8.2 habits
def hab(page, items, dates_only=False):
    a = js(page, "hab.habitFlags", items, {"datesOnly": dates_only})
    b = R.habit_flags(items, dates_only)
    assert a == b, (a, b)
    return a


def it(open_, close, p, q=1.0):
    return {"open": open_, "close": close, "p": p, "q": q}


def test_flag_reentry_boundary(page):
    # the loss closes at 1000 s; the next trade opens 899 s / 900 s / 901 s later
    for gap, want in ((899, 1), (900, 1), (901, 0)):
        f = hab(page, [it(0, 1000, -5), it(1000 + gap, 1000 + gap + 60, 3)])
        assert (f[1] & 1) == want, gap
        assert not f[0] & 1            # the losing trade itself is not counted


def test_flag_streak_boundary(page):
    two = hab(page, [it(0, 10, -1), it(20, 30, -1), it(40, 50, 2)])
    one = hab(page, [it(0, 10, 3), it(20, 30, -1), it(40, 50, 2)])
    assert two[2] & 2 and not one[2] & 2


def test_flag_size_after_loss_boundary(page):
    a = hab(page, [it(0, 10, -1), it(20, 30, 1, q=1.5)])
    b = hab(page, [it(0, 10, -1), it(20, 30, 1, q=1.49)])
    c = hab(page, [it(0, 10, 1), it(20, 30, 1, q=3)])
    assert a[1] & 4 and not b[1] & 4 and not c[1] & 4


def test_flag_large_loss_boundary(page):
    f = hab(page, [it(0, 1, -10), it(2, 3, -10), it(4, 5, -10), it(6, 7, -21), it(8, 9, -20)])
    assert [bool(x & 8) for x in f] == [False, False, False, True, False]   # median 10: 21 > 20, 20 is not


def test_dates_only_not_described(page):
    day = 86400000
    trades = [{"open_ts": k * day, "close_ts": (k + 1) * day, "hold_s": 86400, "pnl": p, "symbol": "X", "qty": 1}
              for k, p in enumerate([-5, -5, -5, 4, -5, -5])]
    assert js(page, "hab.isDatesOnly", trades) is True and R.is_dates_only(trades)
    items = R.items_from_trades(trades)
    assert js(page, "hab.itemsFromTrades", trades) == items
    f = hab(page, items, dates_only=True)
    assert not any(x & (1 | 4) for x in f) and any(x & 2 for x in f)
    days = [[t["pnl"]] for t in trades]
    out = js(page, "hab.realBreachDays", days, [[x] for x in f], 5, {"datesOnly": True})
    assert out["habits"]["reentry"]["status"] == "not_described" == out["habits"]["size_after_loss"]["status"]


def test_attribution_breach_days(page):
    # flag-X (re-entry) days hold losses big enough to breach; the other losing days are small and unflagged
    days, flags = [], []
    for _ in range(6):
        days.append([-40, -70, 30]); flags.append([0, 1, 2])      # breach on trade 2; the streak bit sits after it
    for _ in range(4):
        days.append([-10, 5]); flags.append([0, 0])
    a = js(page, "hab.realBreachDays", days, flags, 100)
    b = R.real_breach_days(days, flags, 100)
    assert a == json.loads(json.dumps(b))
    assert a["n_breach"] == 6 and a["n_other_losing"] == 4
    assert a["habits"]["reentry"]["share"] == 1 and a["habits"]["reentry"]["status"] == "hit"
    assert a["habits"]["streak"]["on_breach"] == 0     # a flag after the breaching trade never counts
    few = js(page, "hab.realBreachDays", days[:4] + days[6:], flags[:4] + flags[6:], 100)
    assert few["n_breach"] == 4 and few["habits"]["reentry"]["status"] == "few"


def test_simulated_habits_js_equals_python(page):
    trades, g = demo_grouped()
    items = R.items_from_trades(trades)
    f = R.habit_flags(items)
    fd = R.day_flags(f, g["index"])
    p = {"mode": "file", "days": g["days"], "seed": 2, "runs": 3000, "rules": GRID[0], "stream": "paired"}
    res = R.simulate(p)
    a = js(page, "hab.simulatedHabits", res, fd)
    b = R.simulated_habits(res, fd)
    assert a == json.loads(json.dumps(b))
    assert js(page, "hab.habitFlags", js(page, "hab.itemsFromTrades", trades)) == f
    real = js(page, "hab.realBreachDays", g["days"], fd, 250)
    assert real == json.loads(json.dumps(R.real_breach_days(g["days"], fd, 250)))


def private_repo():
    """The dt-private checkout whose habits.mjs method equals the site's (run.sh test-worker's rule)."""
    want = re.search(r"^export const METHOD_VERSION = '(.*)';$", open(os.path.join(
        REPO, "site", "static", "js", "paid", "wording.js"), encoding="utf-8").read(), re.M).group(1)
    for p in (os.environ.get("DT_PRIVATE_REPO"), os.path.join(REPO, "..", "dt-private"),
              os.path.join(REPO, "..", "delivery-39-private")):
        f = os.path.join(p or "", "src", "core", "habits.mjs")
        if p and os.path.exists(f) and f"export const METHOD_VERSION = '{want}';" in open(f, encoding="utf-8").read():
            return os.path.abspath(p)
    return None


def test_parity_with_paid_habits_engine():
    """§2.3: reentry = habits.mjs revenge group A, streak = tilt group A, on files the report does not merge."""
    priv = private_repo()
    if not priv:
        pytest.skip("no dt-private checkout with the site's habits method")
    names = ("planted_revenge.json", "planted.json", "random.json")
    fixtures = [f for f in (os.path.join(priv, "tests", "fixtures", n) for n in names) if os.path.exists(f)]
    assert fixtures
    script = ("import { analyse } from '" + os.path.join(priv, "src", "core", "habits.mjs") + "';\n"
              "import fs from 'node:fs';\n"
              "const out = {};\n"
              "for (const f of process.argv.slice(1)) { const r = analyse(JSON.parse(fs.readFileSync(f, 'utf8')), 'test', { nPerm: 1 });\n"
              "  out[f] = Object.fromEntries(r.habits.map((h) => [h.id, h.n_a])); }\n"
              "console.log(JSON.stringify(out));\n")
    res = subprocess.run(["node", "--input-type=module", "-e", script, *fixtures], capture_output=True, text=True, cwd=priv)
    assert res.returncode == 0, res.stderr
    paid = json.loads(res.stdout)
    checked = 0
    for f in fixtures:
        rows = json.load(open(f))["rows"]
        keys = [(r["s"], r["d"], r["o"]) for r in rows]
        if len(set(keys)) != len(keys):
            continue   # the report merges these rows; the free flags keep one per trade (documented)
        items = [{"open": 60 * r["o"], "close": 60 * r["o"] + r["h"], "p": r["p"], "q": r["q"]} for r in rows]
        c = R.count_flags(R.habit_flags(items))
        assert (c["reentry"], c["streak"]) == (paid[f]["revenge"], paid[f]["tilt"]), f
        checked += 1
    assert checked


# ------------------------------------------------------------------ wording of every engine string
BRIEF_BANNED = re.compile(r"\b(recommend\w*|should|fix\w*|coach\w*|must|need to|signal\w*|improv\w*|mentor\w*|"
                          r"certified|verified|audited|seal\w*)\b", re.IGNORECASE)
ADVICE = re.compile(r"\badvice\b", re.IGNORECASE)


def engine_strings(page):
    return page.evaluate("""async ([core, hab]) => {
        const c = await import(core); const h = await import(hab);
        const labels = c.RANK_GRID.map((x) => c.ruleLabel(x));
        for (const x of [{stop_at_day_loss_amount: 50}, {cooldown_s: 60}, {after_loss_factor: 0.75}]) labels.push(c.ruleLabel(x));
        return [...Object.values(c.WHATIF_TEXT), ...Object.values(h.HABIT_TEXT), ...labels,
          ...['dates_only', 'no_times', 'no_daily'].map(c.unavailableText)];
    }""", [CORE, HAB])


def test_engine_strings_pass_the_wording_rules(page):
    import lint as L
    strings = engine_strings(page)
    assert len(strings) > 20
    for s in strings:
        assert not BRIEF_BANNED.search(s), s
        assert not ADVICE.search(re.sub(r"not investment advice", "", s, flags=re.IGNORECASE)), s
        assert not re.search(r"\b(you will|your chances|odds|best rule|to pass|edge|beat)\b", s, re.IGNORECASE), s
        assert L.lint_text(s, "engine") == [], s
    caveat = page.evaluate(f"import('{CORE}').then(m => m.WHATIF_TEXT.caveat)")
    assert caveat.endswith("Not investment advice.")


# ------------------------------------------------------------------ Tester round 1 (F2, F4, F5, F3)
def test_target_intraday_vs_end_of_day(page):
    # [+1200, -300], target 1000: intraday passes on the first trade; end of day it does not
    i = sim(page, seq_p([[1200, -300]], target=1000, target_check="intraday"))
    e = sim(page, seq_p([[1200, -300]], target=1000))
    assert (i["outcome"], i["day"], i["day_pnl"]) == ("pass", 1, [1200])
    assert e["outcome"] == "timeout" and e["target_day"] is None
    # [+1200, -1800] with max loss 500: intraday passes before the loss; end of day busts
    i = sim(page, seq_p([[1200, -1800]], target=1000, max_loss=500, target_check="intraday"))
    e = sim(page, seq_p([[1200, -1800]], target=1000, max_loss=500))
    assert i["outcome"] == "pass" and (e["outcome"], e["why"]) == ("bust", "max")
    # a breach before the target is a bust either way
    for tc in ("intraday", "eod"):
        b = sim(page, seq_p([[-600, 1700]], target=1000, daily_loss=500, target_check=tc))
        assert (b["outcome"], b["why"]) == ("bust", "daily"), tc


def test_target_intraday_counts_today_and_holds(page):
    # min 2 trading days: day 1 reaches the target intraday but is held; day 2 passes on its first trade
    a = sim(page, seq_p([[1200, -100], [10, -5000]], target=1000, min_days=2, target_check="intraday"))
    assert (a["outcome"], a["day"], a["held_min_days"], a["day_pnl"]) == ("pass", 2, 1, [1100, 10])
    # consistency 0.5: the best day so far includes today's running P&L
    # day 2: +500 → 1100, best 600 > 550 (held); +100 → 1200, best 600 <= 600 (passes on that trade)
    c = sim(page, seq_p([[600], [500, 100, -900]], target=1000, consistency=0.5, target_check="intraday"))
    assert (c["outcome"], c["day"], c["held_consistency"], c["day_pnl"], c["trades_seen"]) == ("pass", 2, 1, [600, 600], 3)
    h = sim(page, seq_p([[600], [450, 300]], target=1000, consistency=0.5, target_check="intraday"))
    assert (h["outcome"], h["held_consistency"]) == ("timeout", 1)   # 600 > 525, then 750 > 675


def test_count_day_if_nonzero(page):
    d = [[0], [50], [0, 0], [60]]
    a = sim(page, seq_p(d, target=100, min_days=3))                         # any traded day counts
    n = sim(page, seq_p(d, target=100, min_days=3, count_day_if="nonzero"))  # only days with a non-zero result
    assert (a["outcome"], a["day"]) == ("pass", 4)
    assert (n["outcome"], n["held_min_days"]) == ("timeout", 1)
    n2 = sim(page, seq_p(d + [[0, 5]], target=100, min_days=3, count_day_if="nonzero"))
    assert (n2["outcome"], n2["day"]) == ("pass", 5)


def test_broker_day_start(page):
    br = {"tz": "broker", "hour": 0}
    # broker midnight is 17:00 New York: 21:30Z on 27 Oct (EDT) is 00:30 broker time, the next day;
    # 21:30Z on 1 Dec (EST) is 23:30 broker time, the same day as 20:00Z
    for a, b, same in (("2026-10-27 20:00", "2026-10-27 21:30", False), ("2026-12-01 20:00", "2026-12-01 21:30", True)):
        ka, kb = js(page, "dayKey", ms(a), "UTC", br), js(page, "dayKey", ms(b), "UTC", br)
        assert (ka, kb) == (R.day_key(ms(a), "UTC", br), R.day_key(ms(b), "UTC", br))
        assert (ka == kb) == same, (a, b)


def test_group_days_sorts_by_close(page):
    t = [trade("2026-10-27 10:00", "2026-10-27 11:00", 2), trade("2026-10-26 10:00", "2026-10-26 11:00", 1),
         trade("2026-10-27 09:00", "2026-10-27 09:30", 3)]
    g = group(page, t)
    assert g["days"] == [[1], [3, 2]] and g["index"] == [[1], [2, 0]]


R_OK = {"target": 100, "daily_loss": None, "max_loss": 100, "time_limit": 10}
BAD_RULES = [
    ({"target": float("nan")}, "rules: target is an amount above zero"),
    ({"target": -5}, "rules: target is an amount above zero"),
    ({"max_loss": None}, "rules: max_loss is an amount above zero"),
    ({"max_loss": float("inf")}, "rules: max_loss is an amount above zero"),
    ({"daily_loss": -5}, "rules: daily_loss is an amount above zero, or null for none"),
    ({"daily_loss": float("nan")}, "rules: daily_loss is an amount above zero, or null for none"),
    ({"time_limit": float("nan")}, "rules: time_limit is a whole number of days from 1 to 365, or null for none"),
    ({"time_limit": 0}, "rules: time_limit is a whole number of days from 1 to 365, or null for none"),
    ({"time_limit": 1000}, "rules: time_limit is a whole number of days from 1 to 365, or null for none"),
    ({"time_limit": 2.5}, "rules: time_limit is a whole number of days from 1 to 365, or null for none"),
    ({"min_days": -1}, "rules: min_days is a whole number from 0 to 365"),
    ({"min_days": 1.5}, "rules: min_days is a whole number from 0 to 365"),
    ({"trail_stop_at": -1}, "rules: trail_stop_at is an amount of zero or more, or null"),
    ({"consistency": 0}, "rules: consistency is a share above 0 and at most 1, or null"),
    ({"consistency": float("nan")}, "rules: consistency is a share above 0 and at most 1, or null"),
    ({"profitable_day_min": -1}, "rules: profitable_day_min is an amount of zero or more"),
    ({"drawdown": "trailing"}, "rules: drawdown is static, trailing_eod or trailing_trade"),
    ({"trailing": "yes"}, "rules: trailing is true or false"),
    ({"count_day_if": "always"}, "rules: count_day_if is any or nonzero"),
    ({"target_check": "now"}, "rules: target_check is eod or intraday"),
]


def js_error(page, fn, *args):
    return page.evaluate("""async ([fn, args, core]) => {
        const c = await import(core);
        try { c[fn](...args); return null; } catch (e) { return e.message; }
    }""", [fn, list(args), CORE])


def py_error(f, *args):
    try:
        f(*args)
    except ValueError as e:
        return str(e)
    return None


@pytest.mark.parametrize("bad,msg", BAD_RULES, ids=[m.split(":")[1].split()[0] + str(i) for i, (_, m) in enumerate(BAD_RULES)])
def test_bad_rules_are_rejected_in_both_engines(page, bad, msg):
    p = {"mode": "sequence", "days": [[1]], "rules": {**R_OK, **bad}}
    assert js_error(page, "simulate", p) == msg == py_error(R.simulate, p)


def test_missing_required_rules_are_rejected(page):
    for k, msg in (("daily_loss", "rules: daily_loss is an amount above zero, or null for none"),
                   ("time_limit", "rules: time_limit is a whole number of days from 1 to 365, or null for none"),
                   ("target", "rules: target is an amount above zero"), ("max_loss", "rules: max_loss is an amount above zero")):
        r = {kk: v for kk, v in R_OK.items() if kk != k}
        p = {"mode": "sequence", "days": [[1]], "rules": r}
        assert js_error(page, "simulate", p) == msg == py_error(R.simulate, p), k


BAD_INPUT = [
    ({"mode": "random"}, "simulate: mode is file, sequence or manual"),
    ({"runs": 0}, "simulate: runs is a whole number from 1 to 1,000,000"),
    ({"seed": -1}, "simulate: seed is a whole number from 0 to 4294967295"),
    ({"seed": float("nan")}, "simulate: seed is a whole number from 0 to 4294967295"),
    ({"stream": "other"}, "simulate: stream is legacy or paired"),
    ({"days": []}, "simulate: no trading days"),
    ({"days": [[1, float("nan")]]}, "simulate: every trade result is a finite number"),
    ({"days": [5]}, "simulate: each day is a list of trade results"),
    ({"mode": "manual", "win_rate": 1.5, "avg_win": 1, "avg_loss": 1, "trades_per_day": 1}, "simulate: win_rate is a share from 0 to 1"),
    ({"mode": "manual", "win_rate": 0.5, "avg_win": -1, "avg_loss": 1, "trades_per_day": 1}, "simulate: avg_win is an amount above zero"),
    ({"mode": "manual", "win_rate": 0.5, "avg_win": 1, "avg_loss": float("nan"), "trades_per_day": 1}, "simulate: avg_loss is an amount above zero"),
    ({"mode": "manual", "win_rate": 0.5, "avg_win": 1, "avg_loss": 1, "trades_per_day": 0}, "simulate: trades_per_day is a whole number from 1 to 50"),
    ({"personal": {"cooldown_s": 900}, "open_s": [[0, 1]], "close_s": [[0]]}, "simulate: open_s and close_s hold one finite time per trade, day by day"),
    ({"personal": {"stop_at_day_loss_amount": float("inf")}}, "personal: stop_at_day_loss_amount is an amount above zero"),
    ({"personal": {"stop_after_losses": float("nan")}}, "personal: stop_after_losses is a whole number from 1 to 10"),
    ({"personal": {"max_trades": -2}}, "personal: max_trades is a whole number from 1 to 50"),
]


@pytest.mark.parametrize("bad,msg", BAD_INPUT, ids=[str(i) for i in range(len(BAD_INPUT))])
def test_bad_input_is_rejected_in_both_engines(page, bad, msg):
    p = {"mode": "file", "days": [[1]], "rules": R_OK, "runs": 10, **bad}
    assert js_error(page, "simulate", p) == msg == py_error(R.simulate, p)


# ------------------------------------------------------------------ Expert details: uncertainty
def test_mc_error_formula(page):
    for p_, n in ((0.5, 10000), (0.31, 10000), (0.02, 2000)):
        want = 1.96 * math.sqrt(p_ * (1 - p_) / n)
        assert abs(js(page, "mcError", p_, n) - want) < 1e-15 and abs(R.mc_error(p_, n) - want) < 1e-15
    assert round(R.mc_error(0.5, 10000), 4) == 0.0098


def test_day_resample_range_js_equals_python_and_holds_the_point(page):
    _, g = demo_grouped()
    p = {"mode": "file", "days": g["days"], "open_s": g["open_s"], "close_s": g["close_s"], "seed": 4, "rules": GRID[0]}
    a = js(page, "dayResampleRange", p, {"B": 20, "inner": 300, "personal": {"stop_after_losses": 1}})
    b = R.day_resample_range(p, B=20, inner=300, personal={"stop_after_losses": 1})
    assert a == json.loads(json.dumps(b))
    assert a == js(page, "dayResampleRange", p, {"B": 20, "inner": 300, "personal": {"stop_after_losses": 1}})  # reproducible
    point = R.simulate({**p, "runs": 3000, "stream": "paired"})
    for k in ("pass", "bust", "timeout"):
        lo, hi = a["shares"][k]
        assert lo <= hi and lo - 0.02 <= point[k] / 3000 <= hi + 0.02, (k, lo, point[k] / 3000, hi)
