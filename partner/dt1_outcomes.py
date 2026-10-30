#!/usr/bin/env python3
"""Outcome labels and the B4 headroom for the prediction study (version 1.0).

Imported by prediction_test.py. It opens no file, writes nothing and prints nothing.

Where the code comes from
  replay() is the sequence-mode path of simulate() in the Challenge Readiness Check's Python reference
  `tests/reference/readiness_ref.py` (branch `readiness`, SHA-256
  97bc9eadfedc1a916fab5170116758b276d0ec14060f0aac1f2e1faca9c3528c), lines 243-378, with what sequence mode
  with no profit target and no personal rule never reaches removed: random draws, the target checks,
  personal rules, the consistency and minimum-day counters. Every kept line is copied as written.
  day_key() is the `day_start["tz"] == "file"` branch of day_key() (lines 503-508) and group_days()
  follows lines 514-527: trades are grouped by the day their CLOSE falls in. partner/parity/rules_golden.json
  proves replay() gives prop-sim-core.js simulate({mode: 'sequence'}) on the same days.

Times are whole seconds on the study's clock (the sealed day offset already applied), so a day is
floor((close - day_start) / 86400).

  firm_label     O1 / O3 from the firm's own risk-system record (firm mode)
  rule_label     O1 from rule set R* replayed after T0, plus O2 (50% drawdown) (rule mode)
  headroom       B4: (equity at T0 - the max-loss floor at T0) / the max-loss amount
"""

import math

DAY_S = 86400
STREAK_MIN = 2                 # readiness_ref.py line 24 (kept for the copied bust bookkeeping)
R_STAR = {"daily_share": 0.05, "max_share": 0.10, "drawdown": "static"}
O2_SHARE = 0.5
BREACH = ("daily", "max")
OUTCOMES = ("daily", "max", "other_rule", "passed", "closed_no_breach", "active")
DRAWDOWNS = ("static", "trailing_eod", "trailing_trade")   # readiness_ref.py line 27


def day_key(t_s, day_start_s):
    """readiness_ref.py lines 503-508, the day_start tz == "file" branch, in seconds."""
    return (t_s - day_start_s) // DAY_S


def group_days(trades, day_start_s):
    """Per-day lists of P&L in close order (readiness_ref.py group_days, lines 514-527). trades carry
    close_s and pnl (float). Returns (days, index) where index[d][i] is the trade's position in `trades`."""
    days, index = [], []
    key = None
    for i in sorted(range(len(trades)), key=lambda j: (trades[j]["close_s"], j)):
        k = day_key(trades[i]["close_s"], day_start_s)
        if k != key:
            days.append([])
            index.append([])
            key = k
        days[-1].append(trades[i]["pnl"])
        index[-1].append(i)
    return days, index


def replay(days, daily, max_loss, drawdown, stop_at):
    """Sequence mode with no target (readiness_ref.py simulate, lines 243-378, the kept lines verbatim).
    Returns {outcome: 'bust' | 'end', why: 'daily' | 'max' | None, day (1-based), at: (day index, trade index),
    eq, peak, floor}: eq/peak/floor are the state after the last trade replayed."""

    def floor_of(peak):
        return peak - max_loss if stop_at is None or peak - max_loss < stop_at else stop_at

    n_days = len(days)
    eq, peak, floor, loss_run, outcome = 0.0, 0.0, floor_of(0.0), 0, "timeout"
    bust_day = 0
    at = None
    why = None
    d = 1
    while True:
        if d > n_days:
            outcome = "end"
            break
        di = d - 1
        day = days[di]
        n = len(day)
        start = eq
        busted = False
        for i in range(n):
            pnl = day[i]
            eq += pnl
            loss_run = loss_run + 1 if pnl < 0 else 0
            why = None
            if daily is not None and eq <= start - daily:
                why = "daily"
            elif eq <= floor:
                why = "max"
            if why:
                outcome = "bust"
                bust_day = d
                at = (di, i)
                busted = True
                break
            if drawdown == "trailing_trade" and eq > peak:
                peak = eq
                floor = floor_of(peak)
        if busted:
            break
        if drawdown == "trailing_eod" and eq > peak:
            peak = eq
            floor = floor_of(peak)
        d += 1
    return {"outcome": outcome, "why": why if outcome == "bust" else None,
            "day": bust_day if outcome == "bust" else min(d, n_days), "at": at, "eq": eq, "peak": peak,
            "floor": floor}


def headroom(window, max_loss, drawdown, stop_at, day_start_s):
    """B4 from W alone: replay W from the account's start with no daily limit (a daily breach inside W would
    already be E1) and read (eq - floor) / max_loss after trade 30."""
    days, _ = group_days(window, day_start_s)
    r = replay(days, None, max_loss, drawdown, stop_at)
    return (r["eq"] - r["floor"]) / max_loss


def _in_window(t, t0, t1):
    return t0 < t <= t1


def firm_label(acc, t0, outcome_days):
    """O1 and O3 from the firm's record. acc: {outcome, outcome_time (s or None), data_end (s)}.
    Returns {o1: 1 | 0 | None (censored), o3: 1 | 0 | None (not ended / not a challenge end)}."""
    t1 = t0 + outcome_days * DAY_S
    out, ot, end = acc["outcome"], acc["outcome_time"], acc["data_end"]
    if out in BREACH and ot is not None and _in_window(ot, t0, t1):
        o1 = 1
    elif out == "passed" and ot is not None and _in_window(ot, t0, t1):
        o1 = 0
    elif out in ("other_rule", "closed_no_breach") and ot is not None and _in_window(ot, t0, t1):
        o1 = None                                     # ended inside the window without a breach: censored
    elif end >= t1 and (ot is None or ot > t1 or out == "active"):
        o1 = 0                                        # observed for the whole 30 days with no breach
    else:
        o1 = None
    if out in ("daily", "max", "other_rule") and ot is not None and ot > t0:
        o3 = 1
    elif out == "passed" and ot is not None and ot > t0:
        o3 = 0
    else:
        o3 = None
    return {"o1": o1, "o3": o3}


def rule_label(after, t0, outcome_days, size, data_end, day_start_s):
    """O1 under R* (5% daily, 10% static max loss of `size`, no target) and O2 (equity size + closed P&L
    falls 50% or more below its running peak), both on trades closed in (T0, T0 + outcome_days]. A trade is
    {close_s, pnl}. Censored (None) when there is no breach and the data end before the window does."""
    t1 = t0 + outcome_days * DAY_S
    win = [t for t in after if _in_window(t["close_s"], t0, t1)]
    days, _ = group_days(win, day_start_s)
    r = replay(days, R_STAR["daily_share"] * size, R_STAR["max_share"] * size, R_STAR["drawdown"], None)
    observed = data_end >= t1
    o1 = 1 if r["outcome"] == "bust" else (0 if observed else None)
    eq = peak = size
    hit = False
    for t in sorted(win, key=lambda x: x["close_s"]):
        eq += t["pnl"]
        if eq > peak:
            peak = eq
        if eq <= (1 - O2_SHARE) * peak:
            hit = True
            break
    o2 = 1 if hit else (0 if observed else None)
    return {"o1": o1, "o2": o2, "why": r["why"]}


def is_finite(x):
    return x is not None and math.isfinite(x)
