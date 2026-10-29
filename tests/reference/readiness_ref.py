#!/usr/bin/env python3
"""Challenge Readiness Check engine: Python reference (standard library only).

The oracle that site/static/js/tools/prop-sim-core.js (simulate, whatIf, rankRules, groupDays),
habit-flags.js and challenge-presets.js are tested against (tests/test_readiness_engine.py). Written
from the rules in those files' headers and ARCHITECT-CHALLENGE-READINESS-2026-10-29 §2.2-§2.7.

Same rules as engine_ref.py: plain left-to-right float sums, mulberry32 with 32-bit arithmetic,
naive file times in ms. Time zones come from zoneinfo; offsets are read at the start of each
15-minute UTC bucket, as in the JS (Intl).
"""

import math
import os
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_ref as E  # noqa: E402

RUNS = 10000
DEFAULT_SEED = 20261022
STREAK_MIN = 2
NO_LIMIT_CAP = 250
METHOD_VERSION = {"legacy": "2026-10-22.prop-sim", "paired": "2026-10-29.r1"}
DRAWDOWNS = ("static", "trailing_eod", "trailing_trade")
PERSONAL_KEYS = ("stop_after_losses", "stop_at_day_loss", "stop_at_day_loss_amount", "max_trades",
                 "cooldown_s", "after_loss_factor")
FACTORS = (0.25, 0.5, 0.75)
MAX_PERSONAL = 2
SCREEN_RUNS = 2000
RANK_TOP = 3
RANK_MIN_POINTS = 3
RANK_GRID = [
    {"stop_after_losses": 1}, {"stop_after_losses": 2}, {"stop_after_losses": 3},
    {"stop_at_day_loss": 0.25}, {"stop_at_day_loss": 0.5}, {"stop_at_day_loss": 0.75},
    {"max_trades": 1}, {"max_trades": 2}, {"max_trades": 3}, {"max_trades": 5},
    {"cooldown_s": 300}, {"cooldown_s": 900}, {"cooldown_s": 1800},
    {"after_loss_factor": 0.5}, {"after_loss_factor": 0.25},
]
M32 = 0xFFFFFFFF


def imul(a, b):
    return (a * b) & M32


def mix32(a, b):
    h = (a & M32) ^ imul((b + 1) & M32, 0x9E3779B9)
    h = imul(h ^ (h >> 16), 0x85EBCA6B)
    h = imul(h ^ (h >> 13), 0xC2B2AE35)
    return h ^ (h >> 16)


def _num(v):
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _whole(v, lo, hi):
    return isinstance(v, int) and not isinstance(v, bool) and lo <= v <= hi or (
        isinstance(v, float) and v.is_integer() and lo <= v <= hi)


def _fail(msg):
    raise ValueError(msg)


MISSING = object()


def norm_rules(r):
    if not isinstance(r, dict):
        _fail("rules: missing")
    g = lambda k, d=MISSING: r.get(k, d)  # noqa: E731
    if not _num(g("target", None)) or r["target"] <= 0:
        _fail("rules: target is an amount above zero")
    if not _num(g("max_loss", None)) or r["max_loss"] <= 0:
        _fail("rules: max_loss is an amount above zero")
    dl = g("daily_loss")
    if dl is MISSING or (dl is not None and (not _num(dl) or dl <= 0)):
        _fail("rules: daily_loss is an amount above zero, or null for none")
    tl = g("time_limit")
    if tl is MISSING or (tl is not None and not _whole(tl, 1, 365)):
        _fail("rules: time_limit is a whole number of days from 1 to 365, or null for none")
    tr = g("trailing")
    if tr is not MISSING and not isinstance(tr, bool):
        _fail("rules: trailing is true or false")
    dd = g("drawdown", None)
    if dd is None:
        dd = "trailing_eod" if tr is True else "static"
    if dd not in DRAWDOWNS:
        _fail("rules: drawdown is static, trailing_eod or trailing_trade")
    stop = g("trail_stop_at", None)
    if stop is not None and (not _num(stop) or stop < 0):
        _fail("rules: trail_stop_at is an amount of zero or more, or null")
    c = g("consistency", None)
    if c is not None and (not _num(c) or not (0 < c <= 1)):
        _fail("rules: consistency is a share above 0 and at most 1, or null")
    md = g("min_days", 0)
    if not _whole(md, 0, 365):
        _fail("rules: min_days is a whole number from 0 to 365")
    kind = g("min_days_kind", "trading")
    if kind not in ("trading", "profitable"):
        _fail("rules: min_days_kind is trading or profitable")
    pm = g("profitable_day_min", 0)
    if not _num(pm) or pm < 0:
        _fail("rules: profitable_day_min is an amount of zero or more")
    cif = g("count_day_if", "any")
    if cif not in ("any", "nonzero"):
        _fail("rules: count_day_if is any or nonzero")
    tc = g("target_check", "eod")
    if tc not in ("eod", "intraday"):
        _fail("rules: target_check is eod or intraday")
    no_limit = tl is None
    return {"target": r["target"], "daily_loss": dl, "max_loss": r["max_loss"], "drawdown": dd, "trail_stop_at": stop,
            "consistency": c, "min_days": md, "min_days_kind": kind, "profitable_day_min": pm, "count_day_if": cif,
            "target_check": tc, "limit": NO_LIMIT_CAP if no_limit else tl, "no_limit": no_limit}


def check_input(p):
    if not isinstance(p, dict):
        _fail("simulate: missing input")
    if p.get("mode") not in ("file", "sequence", "manual"):
        _fail("simulate: mode is file, sequence or manual")
    if "runs" in p and not _whole(p["runs"], 1, 1000000):
        _fail("simulate: runs is a whole number from 1 to 1,000,000")
    if "seed" in p and not _whole(p["seed"], 0, 4294967295):
        _fail("simulate: seed is a whole number from 0 to 4294967295")
    if "stream" in p and p["stream"] not in ("legacy", "paired"):
        _fail("simulate: stream is legacy or paired")
    if p["mode"] == "manual":
        if not _num(p.get("win_rate")) or not 0 <= p["win_rate"] <= 1:
            _fail("simulate: win_rate is a share from 0 to 1")
        if not _num(p.get("avg_win")) or p["avg_win"] <= 0:
            _fail("simulate: avg_win is an amount above zero")
        if not _num(p.get("avg_loss")) or p["avg_loss"] <= 0:
            _fail("simulate: avg_loss is an amount above zero")
        if not _whole(p.get("trades_per_day"), 1, 50):
            _fail("simulate: trades_per_day is a whole number from 1 to 50")
        return
    days = p.get("days")
    if not isinstance(days, list) or not days:
        _fail("simulate: no trading days")
    for d in days:
        if not isinstance(d, list):
            _fail("simulate: each day is a list of trade results")
        for x in d:
            if not _num(x):
                _fail("simulate: every trade result is a finite number")


def personal_unavailable(p, x, r=None):
    if not x:
        return None
    r = r or norm_rules(p["rules"])
    if x.get("cooldown_s") is not None:
        if p.get("dates_only"):
            return "dates_only"
        if p["mode"] == "manual" or not p.get("open_s") or not p.get("close_s"):
            return "no_times"
    if x.get("stop_at_day_loss") is not None and r["daily_loss"] is None:
        return "no_daily"
    return None


def norm_personal(x, r):
    if not x:
        return None
    keys = [k for k, v in x.items() if v is not None]
    for k in keys:
        if k not in PERSONAL_KEYS:
            _fail(f"personal: unknown rule {k}")
    if not keys:
        return None
    if len(keys) > MAX_PERSONAL:
        _fail(f"personal: at most {MAX_PERSONAL} rules at once")
    q = {"stop_losses": 0, "stop_at": None, "max_trades": 0, "cooldown": -1, "factor": 1}
    if x.get("stop_after_losses") is not None:
        if not _whole(x["stop_after_losses"], 1, 10):
            _fail("personal: stop_after_losses is a whole number from 1 to 10")
        q["stop_losses"] = x["stop_after_losses"]
    if x.get("stop_at_day_loss") is not None:
        if not _num(x["stop_at_day_loss"]) or not 0.1 <= x["stop_at_day_loss"] <= 0.95:
            _fail("personal: stop_at_day_loss is a share from 0.1 to 0.95")
        if r["daily_loss"] is None:
            _fail("personal: stop_at_day_loss needs a daily loss limit")
        q["stop_at"] = x["stop_at_day_loss"] * r["daily_loss"]
    if x.get("stop_at_day_loss_amount") is not None:
        if x.get("stop_at_day_loss") is not None:
            _fail("personal: a share or an amount, not both")
        if not _num(x["stop_at_day_loss_amount"]) or x["stop_at_day_loss_amount"] <= 0:
            _fail("personal: stop_at_day_loss_amount is an amount above zero")
        q["stop_at"] = x["stop_at_day_loss_amount"]
    if x.get("max_trades") is not None:
        if not _whole(x["max_trades"], 1, 50):
            _fail("personal: max_trades is a whole number from 1 to 50")
        q["max_trades"] = x["max_trades"]
    if x.get("cooldown_s") is not None:
        if not _whole(x["cooldown_s"], 60, 14400) or x["cooldown_s"] % 60:
            _fail("personal: cooldown_s is whole minutes from 1 to 240")
        q["cooldown"] = x["cooldown_s"]
    if x.get("after_loss_factor") is not None:
        if x["after_loss_factor"] not in FACTORS:
            _fail("personal: after_loss_factor is 0.25, 0.5 or 0.75")
        q["factor"] = x["after_loss_factor"]
    return q


def _median_sorted(a):
    n = len(a)
    if not n:
        return None
    return a[(n - 1) // 2] if n % 2 else (a[n // 2 - 1] + a[n // 2]) / 2


def simulate(p):
    check_input(p)
    mode = p["mode"]
    seq, filem, manual = mode == "sequence", mode == "file", mode == "manual"
    runs = 1 if seq else (p.get("runs") or RUNS)
    seed = DEFAULT_SEED if p.get("seed") is None else p["seed"]
    stream = "none" if seq else (p.get("stream") or "legacy")
    shared = E.mulberry32(seed) if stream == "legacy" else None
    r = norm_rules(p["rules"])
    why0 = personal_unavailable(p, p.get("personal"), r)
    if why0:
        raise ValueError(why0)
    pers = norm_personal(p.get("personal"), r)
    days = None if manual else p["days"]
    n_days = len(days) if days else 0
    open_s = p.get("open_s") if pers and pers["cooldown"] >= 0 else None
    close_s = p.get("close_s") if pers and pers["cooldown"] >= 0 else None
    if open_s is not None:
        def same(x):
            return isinstance(x, list) and len(x) == n_days and all(
                isinstance(t, list) and len(t) == len(days[i]) and all(_num(v) for v in t) for i, t in enumerate(x))
        if not same(open_s) or not same(close_s):
            _fail("simulate: open_s and close_s hold one finite time per trade, day by day")
    intraday = r["target_check"] == "intraday"
    count_any = r["count_day_if"] == "any"
    profitable = r["min_days_kind"] == "profitable"
    daily, max_loss, stop_at = r["daily_loss"], r["max_loss"], r["trail_stop_at"]

    def floor_of(peak):
        return peak - max_loss if stop_at is None or peak - max_loss < stop_at else stop_at

    out = {"runs": runs, "pass": 0, "bust": 0, "timeout": 0, "bust_daily": 0, "bust_max": 0, "bust_after_streak": 0,
           "held_consistency": 0, "held_min_days": 0, "capped": False, "trades_seen": 0, "trades_left_out": 0,
           "mode": mode, "stream": stream, "method": METHOD_VERSION["paired" if stream == "paired" else "legacy"]}
    if seq:
        out["end"] = 0
    bust_at = {}
    drawn_losing = [0] * n_days
    pass_days, bust_days = [], []
    seen = left = 0
    seq_target, seq_pnl = None, []
    for k in range(runs):
        rand = E.mulberry32(mix32(seed, k)) if stream == "paired" else shared
        eq, peak, floor, loss_run, outcome, best, prof, tdays = 0.0, 0.0, floor_of(0.0), 0, "timeout", -math.inf, 0, 0
        held_c = held_m = False
        bust_day = 0
        busted = False
        d = 1
        while d <= r["limit"]:
            di = -1
            if filem:
                di = math.floor(rand() * n_days)
                day = days[di]
                n = len(day)
            elif seq:
                if d > n_days:
                    outcome = "end"
                    break
                di = d - 1
                day = days[di]
                n = len(day)
            else:
                day = None
                n = p["trades_per_day"]
            start = eq
            taken = losses = 0
            stopped = prev_loss = nz = False
            loss_closes = []
            for i in range(n):
                pnl = day[i] if day is not None else (p["avg_win"] if rand() < p["win_rate"] else -p["avg_loss"])
                seen += 1
                if pers:
                    if stopped or (pers["max_trades"] and taken >= pers["max_trades"]):
                        left += 1
                        continue
                    if open_s:
                        o = open_s[di][i]
                        if any(c <= o and o - c <= pers["cooldown"] for c in loss_closes):
                            left += 1
                            continue
                    if prev_loss and pers["factor"] != 1:
                        pnl *= pers["factor"]
                before = loss_run
                eq += pnl
                loss_run = loss_run + 1 if pnl < 0 else 0
                if pnl != 0:
                    nz = True
                why = None
                if daily is not None and eq <= start - daily:
                    why = "daily"
                elif eq <= floor:
                    why = "max"
                if why:
                    outcome = "bust"
                    out["bust_" + why] += 1
                    out["bust_after_streak"] += before >= STREAK_MIN
                    if not manual:
                        bust_at[(di, i)] = bust_at.get((di, i), 0) + 1
                        if eq - start < 0:
                            drawn_losing[di] += 1
                    bust_day = d
                    if seq:
                        out["why"] = why
                        seq_pnl.append(eq - start)
                    busted = True
                    break
                if r["drawdown"] == "trailing_trade" and eq > peak:
                    peak = eq
                    floor = floor_of(peak)
                if pers:
                    taken += 1
                    prev_loss = pnl < 0
                    if prev_loss:
                        losses += 1
                        if open_s:
                            loss_closes.append(close_s[di][i])
                    if pers["stop_losses"] and losses >= pers["stop_losses"]:
                        stopped = True
                    if pers["stop_at"] is not None and eq - start <= -pers["stop_at"]:
                        stopped = True
                if intraday and eq >= r["target"]:
                    if seq and seq_target is None:
                        seq_target = d
                    cur = eq - start
                    if profitable:
                        cnt = prof + (1 if cur > 0 and cur >= r["profitable_day_min"] else 0)
                    else:
                        cnt = tdays + (1 if count_any or nz else 0)
                    ok_m = cnt >= r["min_days"]
                    ok_c = r["consistency"] is None or (cur if cur > best else best) <= r["consistency"] * eq
                    if ok_m and ok_c:
                        break
                    held_m = held_m or not ok_m
                    held_c = held_c or not ok_c
            if busted:
                break
            day_pnl = eq - start
            if not manual and day_pnl < 0:
                drawn_losing[di] += 1
            if seq:
                seq_pnl.append(day_pnl)
            if r["drawdown"] == "trailing_eod" and eq > peak:
                peak = eq
                floor = floor_of(peak)
            if day_pnl > best:
                best = day_pnl
            if day_pnl > 0 and day_pnl >= r["profitable_day_min"]:
                prof += 1
            if count_any or nz:
                tdays += 1
            if eq >= r["target"]:
                if seq and seq_target is None:
                    seq_target = d
                ok_m = (prof if profitable else tdays) >= r["min_days"]
                ok_c = r["consistency"] is None or best <= r["consistency"] * eq
                if ok_m and ok_c:
                    outcome = "pass"
                    pass_days.append(d)
                    break
                held_m = held_m or not ok_m
                held_c = held_c or not ok_c
            d += 1
        if outcome == "bust":
            bust_days.append(bust_day)
        if outcome == "timeout" and r["no_limit"]:
            out["capped"] = True
        out["held_consistency"] += held_c
        out["held_min_days"] += held_m
        out[outcome] += 1
        if seq:
            out["outcome"] = outcome
            out["day"] = (pass_days[0] if outcome == "pass" else bust_day if outcome == "bust"
                          else min(d, r["limit"], n_days))
            out["target_day"] = seq_target
            out["day_pnl"] = seq_pnl
            if outcome != "bust":
                out["why"] = None
    out["trades_seen"] = seen
    out["trades_left_out"] = left
    out["median_pass_days"] = _median_sorted(sorted(pass_days))
    out["median_bust_days"] = _median_sorted(sorted(bust_days))
    if not manual:
        out["bust_at"] = [[di, i, c] for (di, i), c in sorted(bust_at.items())]
        out["drawn_losing"] = drawn_losing
    return out


FACTOR_WORDS = {0.25: "a quarter of", 0.5: "half", 0.75: "three quarters of"}


def _count(n, one, many):
    return f"{n} {one if n == 1 else many}"


def rule_label(x, fmt=str):
    if not x:
        return ""
    parts = []
    if x.get("stop_after_losses") is not None:
        parts.append(f"Stop for the day after {_count(x['stop_after_losses'], 'losing trade', 'losing trades')}")
    if x.get("stop_at_day_loss") is not None:
        parts.append(f"Stop for the day at {round(x['stop_at_day_loss'] * 100)}% of the daily loss limit")
    if x.get("stop_at_day_loss_amount") is not None:
        parts.append(f"Stop for the day at a day loss of {fmt(x['stop_at_day_loss_amount'])}")
    if x.get("max_trades") is not None:
        parts.append(f"At most {_count(x['max_trades'], 'trade', 'trades')} a day")
    if x.get("cooldown_s") is not None:
        parts.append(f"No new trade for {_count(x['cooldown_s'] // 60, 'minute', 'minutes')} after a loss")
    if x.get("after_loss_factor") is not None:
        parts.append(f"Count each trade after a loss at {FACTOR_WORDS[x['after_loss_factor']]} its result")
    return " + ".join(parts)


def what_if(p, personal):
    why = personal_unavailable(p, personal)
    if why:
        return {"unavailable": why}
    base = {**p, "stream": "paired", "personal": None}
    return {"before": simulate(base), "after": simulate({**base, "personal": personal}), "rule": personal,
            "label": rule_label(personal)}


def rank_rules(p, enabled=False):
    if enabled is not True:
        return {"enabled": False}
    r = norm_rules(p["rules"])
    runs = p.get("runs") or RUNS
    screen = min(SCREEN_RUNS, runs)
    base = {**p, "stream": "paired", "personal": None}
    before = simulate(base)
    before_s = before if screen == runs else simulate({**base, "runs": screen})
    grid = []
    for idx, rule in enumerate(RANK_GRID):
        why = personal_unavailable(p, rule, r)
        if why:
            grid.append({"idx": idx, "rule": rule, "unavailable": why})
            continue
        s = simulate({**base, "personal": rule, "runs": screen})
        grid.append({"idx": idx, "rule": rule, "label": rule_label(rule), "runs": screen, "pass": s["pass"],
                     "bust": s["bust"], "timeout": s["timeout"], "rise": s["pass"] - before_s["pass"]})
    tried = sum(1 for g in grid if "unavailable" not in g)
    top = sorted([g for g in grid if "unavailable" not in g and "after_loss_factor" not in g["rule"]],
                 key=lambda g: (-g["rise"], g["idx"]))[:RANK_TOP]
    ranked = []
    for g in top:
        a = simulate({**base, "personal": g["rule"]})
        if 100 * (a["pass"] - before["pass"]) >= RANK_MIN_POINTS * runs and a["bust"] <= before["bust"]:
            ranked.append({"idx": g["idx"], "rule": g["rule"], "label": g["label"],
                           "before": {k: before[k] for k in ("pass", "bust", "timeout")},
                           "after": {k: a[k] for k in ("pass", "bust", "timeout")}, "runs": runs})
    ranked.sort(key=lambda x: (-(x["after"]["pass"] - x["before"]["pass"]), x["idx"]))
    return {"enabled": True, "tried": tried, "grid": grid, "ranked": ranked, "before": before}


# ------------------------------------------------------------------ day grouping
DAY = 86400000
HOUR = 3600000
BUCKET = 900000
_zones = {}


def tz_offset(tz, utc_ms):
    if tz == "UTC":
        return 0
    at = (utc_ms // BUCKET) * BUCKET
    z = _zones.get(tz) or _zones.setdefault(tz, ZoneInfo(tz))
    return int(round(datetime.fromtimestamp(at / 1000, tz=z).utcoffset().total_seconds() * 1000))


def zoned_to_utc(naive_ms, tz):
    o1 = tz_offset(tz, naive_ms)
    g = naive_ms - o1
    o2 = tz_offset(tz, g)
    return g if o2 == o1 else naive_ms - o2


def file_to_utc(naive_ms, file_tz):
    if file_tz is None or file_tz == "UTC":
        return naive_ms
    if isinstance(file_tz, dict):
        return naive_ms - file_tz["offset_min"] * 60000
    if file_tz == "broker":
        return zoned_to_utc(naive_ms - 7 * HOUR, "America/New_York")
    return zoned_to_utc(naive_ms, file_tz)


def day_key(naive_ms, file_tz, day_start):
    if not day_start:
        return file_to_utc(naive_ms, file_tz) // DAY
    h = day_start["hour"] * HOUR
    if day_start["tz"] == "file":
        return (naive_ms - h) // DAY
    utc = file_to_utc(naive_ms, file_tz)
    off = tz_offset("America/New_York", utc) + 7 * HOUR if day_start["tz"] == "broker" else tz_offset(day_start["tz"], utc)
    return (utc + off - h) // DAY


def group_days(trades, file_tz=None, day_start=None):
    days, opens, closes, index, keys = [], [], [], [], []
    key, base = None, 0
    for i in sorted(range(len(trades)), key=lambda j: (trades[j]["close_ts"], j)):
        t = trades[i]
        k = day_key(t["close_ts"], file_tz, day_start)
        o = 60 * (t["open_ts"] // 60000)
        c = o + (t["hold_s"] if "hold_s" in t else (t["close_ts"] - t["open_ts"]) // 1000)
        if k != key:
            days.append([]); opens.append([]); closes.append([]); index.append([]); keys.append(k)
            key, base = k, c
        days[-1].append(t["pnl"]); opens[-1].append(o - base); closes[-1].append(c - base); index[-1].append(i)
    return {"days": days, "open_s": opens, "close_s": closes, "index": index, "keys": keys}


# ------------------------------------------------------------------ habit flags (habit-flags.js)
HABITS = ("reentry", "streak", "size_after_loss", "large_loss")
BIT = {"reentry": 1, "streak": 2, "size_after_loss": 4, "large_loss": 8}
NEEDS_TIMES = ("reentry", "size_after_loss")
REENTRY_S = 900
MIN_BREACH_DAYS = 5
MIN_BUSTS = 30
HIT_POINTS = 10


def _round_half_away(x):
    return math.floor(abs(x) + 0.5) * (1 if x >= 0 else -1)


def items_from_trades(trades):
    by_sym = {}
    for t in trades:
        by_sym.setdefault(t["symbol"], []).append(t["qty"])
    med = {s: E.median(q) for s, q in by_sym.items()}
    out = []
    for t in trades:
        o = 60 * (t["open_ts"] // 60000)
        hold = t["hold_s"] if "hold_s" in t else (t["close_ts"] - t["open_ts"]) // 1000
        m = med[t["symbol"]]
        out.append({"open": o, "close": o + hold, "p": _round_half_away(t["pnl"] * 100) / 100,
                    "q": _round_half_away(t["qty"] / m * 1000) / 1000 if m > 0 else 0})
    return out


def is_dates_only(trades):
    k = sum(1 for t in trades if t["open_ts"] % DAY == 0 and
            (t["hold_s"] if "hold_s" in t else (t["close_ts"] - t["open_ts"]) // 1000) % 86400 == 0)
    return len(trades) > 0 and 20 * k >= len(trades)


def _bisect_right(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        m = (lo + hi) >> 1
        if x < a[m]:
            hi = m
        else:
            lo = m + 1
    return lo


def _bisect_left(a, x):
    lo, hi = 0, len(a)
    while lo < hi:
        m = (lo + hi) >> 1
        if a[m] < x:
            lo = m + 1
        else:
            hi = m
    return lo


def habit_flags(items, dates_only=False):
    n = len(items)
    flags = [0] * n
    it = [{**t, "i": i} for i, t in enumerate(items)]
    by_close = sorted(it, key=lambda t: (t["close"], t["open"], t["i"]))
    by_open = sorted(it, key=lambda t: (t["open"], t["close"], t["i"]))
    closes = [t["close"] for t in by_close]
    streak, run = [], 0
    for t in by_close:
        run = run + 1 if t["p"] < 0 else 0
        streak.append(run)
    loss_items = [t for t in by_close if t["p"] < 0]
    lc = [t["close"] for t in loss_items]

    def prior(t):
        k = _bisect_right(closes, t["open"]) - 1
        while k >= 0 and by_close[k]["i"] == t["i"]:
            k -= 1
        return k

    for pos, t in enumerate(by_open):
        k = prior(t)
        if k >= 0 and streak[k] >= 2:
            flags[t["i"]] |= BIT["streak"]
        if dates_only:
            continue
        if pos > 0:
            m = _bisect_left(lc, t["open"] - REENTRY_S)
            while m < len(lc) and lc[m] <= t["open"]:
                if loss_items[m]["i"] != t["i"]:
                    flags[t["i"]] |= BIT["reentry"]
                    break
                m += 1
        if k >= 0 and by_close[k]["p"] < 0 and t["q"] >= 1.5:
            flags[t["i"]] |= BIT["size_after_loss"]
    med = E.median([-t["p"] for t in loss_items])
    if med is not None:
        for t in loss_items:
            if -t["p"] > 2 * med:
                flags[t["i"]] |= BIT["large_loss"]
    return flags


def count_flags(flags):
    return {h: sum(1 for f in flags if f & BIT[h]) for h in HABITS}


def day_flags(flags, index):
    return [[flags[i] for i in ix] for ix in index]


def _or_upto(f, last):
    m = 0
    for i in range(last + 1):
        m |= f[i]
    return m


def _status(share, base, n, lo, dates_only, h):
    if dates_only and h in NEEDS_TIMES:
        return "not_described"
    if n < lo or share is None or base is None:
        return "few"
    return "hit" if 100 * (share - base) >= HIT_POINTS - 1e-9 else "muted"


def real_breach_days(days, flags_by_day, daily_loss, dates_only=False):
    breach, other = [], []
    if daily_loss is not None:
        for j, d in enumerate(days):
            run = 0.0
            for i, x in enumerate(d):
                run += x
                if run <= -daily_loss:
                    breach.append((j, i))
                    break
    is_b = {j for j, _ in breach}
    for j, d in enumerate(days):
        if j in is_b:
            continue
        s = 0.0
        for x in d:
            s += x
        if s < 0:
            other.append(j)
    out = {"n_breach": len(breach), "n_other_losing": len(other), "breach_days": [j for j, _ in breach], "habits": {}}
    for h in HABITS:
        b = BIT[h]
        nb = sum(1 for j, at in breach if _or_upto(flags_by_day[j], at) & b)
        no = sum(1 for j in other if _or_upto(flags_by_day[j], len(flags_by_day[j]) - 1) & b)
        share = nb / len(breach) if breach else None
        base = no / len(other) if other else None
        out["habits"][h] = {"on_breach": nb, "on_other_losing": no, "share": share, "base": base,
                            "status": _status(share, base, len(breach), MIN_BREACH_DAYS, dates_only, h)}
    return out


def simulated_habits(res, flags_by_day, dates_only=False):
    drawn = 0
    for c in res["drawn_losing"]:
        drawn += c
    out = {"busts": res["bust"], "drawn_losing": drawn, "habits": {}}
    for h in HABITS:
        b = BIT[h]
        nb = sum(c for j, at, c in res["bust_at"] if _or_upto(flags_by_day[j], at) & b)
        nl = sum(c for j, c in enumerate(res["drawn_losing"])
                 if c and _or_upto(flags_by_day[j], len(flags_by_day[j]) - 1) & b)
        share = nb / res["bust"] if res["bust"] else None
        base = nl / drawn if drawn else None
        out["habits"][h] = {"on_busts": nb, "on_drawn_losing": nl, "share": share, "base": base,
                            "status": _status(share, base, res["bust"], MIN_BUSTS, dates_only, h)}
    return out


# ------------------------------------------------------------------ presets (challenge-presets.js)
SCALED = ("target", "daily_loss", "max_loss", "trail_stop_at", "profitable_day_min")


def preset_rules(preset, account_size=None):
    if not preset or preset["status"] == "not_quotable" or not preset.get("rules"):
        raise ValueError("preset: no rules to use")
    k = account_size / preset["account_size"] if preset["scale"] == "percent" and account_size else 1
    r = dict(preset["rules"])
    for f in SCALED:
        if r[f] is not None:
            r[f] = r[f] * k
    day_start = r.pop("day_start")
    return {"rules": r, "dayStart": day_start, "accountSize": preset["account_size"] if k == 1 else account_size,
            "unconfirmed": list(preset["unconfirmed"])}
