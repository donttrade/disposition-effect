"""Bad-day check: Python reference (standard library only) for site/static/js/tools/bad-day-core.js.

Written from the rules in that file's header, using the Challenge Readiness reference for the four habit flags (readiness_ref.py)
and the engine's tested median. A trade counts on the day it closed (after a whole-hour shift); a typical day is the median of the
other days with trades, shown only with MIN_OTHER_DAYS or more.
"""
import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import engine_ref as E  # noqa: E402
import readiness_ref as R  # noqa: E402

MIN_OTHER_DAYS = 10
KEYS = ("n", "net", "largest_loss", "reentry", "streak", "size_after_loss", "large_loss")


def day_of(ts_ms, shift):
    return (datetime(1970, 1, 1, tzinfo=timezone.utc) + timedelta(milliseconds=ts_ms + shift * 3600000)).strftime("%Y-%m-%d")


def per_day(trades, shift=0):
    items = R.items_from_trades(trades)
    dates_only = R.is_dates_only(trades)
    flags = R.habit_flags(items, dates_only)
    days = {}
    for t, f in zip(trades, flags):
        d = day_of(t["close_ts"], shift)
        r = days.setdefault(d, {"date": d, "n": 0, "net": 0.0, "largest_loss": 0.0, "reentry": 0, "streak": 0,
                                "size_after_loss": 0, "large_loss": 0})
        r["n"] += 1
        r["net"] += t["pnl"]
        if t["pnl"] < 0 and -t["pnl"] > r["largest_loss"]:
            r["largest_loss"] = -t["pnl"]
        for h in ("reentry", "streak", "size_after_loss", "large_loss"):
            if f & R.BIT[h]:
                r[h] += 1
    for r in days.values():
        r["net"] = round(r["net"] * 100) / 100
        r["largest_loss"] = round(r["largest_loss"] * 100) / 100
    return days, sorted(days), dates_only


def bad_day(trades, shift=0, requested=()):
    days, order, dates_only = per_day(trades, shift)
    missing = [d for d in requested if d not in days]
    chosen = [d for d in requested if d in days]
    fell_back = False
    if not chosen and order:
        worst = order[0]
        for d in order:
            if days[d]["net"] < days[worst]["net"]:
                worst = d
        chosen, fell_back = [worst], True
    others = [d for d in order if d not in chosen]
    typical = None
    if len(others) >= MIN_OTHER_DAYS:
        typical = {k: E.median([days[d][k] for d in others]) for k in KEYS}
    return {"datesOnly": dates_only, "missing": missing, "fellBack": fell_back, "chosen": [days[d] for d in chosen],
            "n_days": len(order), "n_other": len(others), "typical": typical}
