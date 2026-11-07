#!/usr/bin/env python3
"""selloff.py: the figures, charts and CSV of /research/5-november-2026-sell-off/ (6 Nov 2026).

Every number on that page is made here from site/data/selloff-2026-11-05.json (aggregate counts only, written by
checks/selloff/make_selloff_data.py) and site/config/market_2026_11_05.json (through learn_tables.market_view).
Nothing is typed into the template. The statistics are the ones ANALYSIS-PLAN.md fixed before any data row was read:
the baseline is the 30 UTC days 2026-10-06 to 2026-11-04; the median and quartiles are those of statistics.quantiles
(n=4, exclusive method), and the rank counts how many of the 31 days are higher than the event day, plus one.

context() recomputes every measure from the per-day rows and FAILS if one differs from the `summary` block the analysis
printed, so a hand-edited data file cannot drift from its own days. tests/test_selloff.py recomputes them a second way.
"""
import csv
import datetime as dt
import io
import json
import math
import os
import statistics as st
from zoneinfo import ZoneInfo

SITE = os.path.dirname(os.path.abspath(__file__))
DATA_JSON = os.path.join(SITE, "data", "selloff-2026-11-05.json")
PACK_DIR = os.path.join(os.path.dirname(SITE), "checks", "selloff", "zenodo")
CSV_PATH = "/data/5-november-2026-hyperliquid-daily.csv"
PACK_URL = "/data/5-november-2026/"
PACK_FILES = ("README.txt", "ANALYSIS-PLAN.md", "ANALYSIS-PLAN.sha256", "RUN-LOG.txt", "run_day.py", "summarize.py", "s3_exact.py",
              "SUMMARY.json", "S3_exact.json",
              # 7 Nov: the market-by-market breakdown (descriptive, added after the plan) and the check of what each market tracks
              "per_market.py", "markets_verified.py", "MARKETS-VERIFIED.csv", "MARKETS-README.txt")
PM_CSV = "5-november-2026-per-market.csv"       # served at /data/ like the daily CSV, byte for byte from the pack
PM_CSV_PATH = "/data/" + PM_CSV
PM_REVISION = "8e0c2f593fdbf324772db734747ccfce597f3b80"   # ironflow/hyperliquid-trades commit the study read (per_market.REVISION)
# 7 Nov: counts from Ironflow's REPLACED files (main at 23d731e9, 6 Nov 23:24 UTC), made with per_market.py's count step; only
# these two days changed among the five replaced files (6, 10, 11 Oct; 4, 5 Nov). Builder-listed figures unchanged on all five.
REUPLOAD = {"2026-11-05": 18815, "2026-10-10": 1142}
PM_TOP = 15                                      # rows shown before the <details>
MIN_CELL = 10                                    # ANALYSIS-PLAN.md section 7
CSV_COLUMNS = ("date_utc", "wallets_force_closed", "value_force_closed_usd", "active_wallets", "share_of_active_force_closed",
               "hip3_markets_wallets_force_closed", "hip3_markets_value_force_closed_usd", "long_share_of_value",
               "wallets_in_new_order_count_15min", "wallets_in_new_order_count_60min", "wallets_in_new_order_denominator",
               "new_order_within_15min_share", "new_order_within_60min_share")
CUT_UTC = (14, 30), (21, 0)          # the US cash session, 9:30 a.m. to 4 p.m. New York time (EST on 5 Nov)


class SellOffError(Exception):
    pass


def load(path=None):
    with open(path or DATA_JSON, encoding="utf-8") as f:
        return json.load(f)


# ------------------------------------------------------------------ the pre-stated statistics
def measure(days, event, fn):
    """E value, baseline median / quartiles / min / max, ratio and rank among all the days up to the event day."""
    vals = {d["day"]: fn(d) for d in days if d["day"] <= event}
    base = {k: v for k, v in vals.items() if k != event}
    b = sorted(base.values())
    q = st.quantiles(b, n=4)
    e = vals[event]
    med = st.median(b)
    return {"E": e, "median": med, "q1": q[0], "q3": q[2], "min": b[0], "max": b[-1],
            "ratio": e / med if med else None, "rank": 1 + sum(v > e for v in vals.values()),
            "max_day": max(base, key=lambda k: base[k]), "n_base": len(b), "n_all": len(vals)}


def share(num, den):
    return lambda d: d[num] / d[den]


MEASURES = {
    "P1": ("P1_liq_wallets", lambda d: d["liq_wallets"]),
    "P2": ("P2_liq_notional", lambda d: d["liq_notional"]),
    "P3": ("P3_share_active_liquidated", lambda d: d["liq_wallets"] / d["active_wallets"]),
    "S1w": ("S1_hip3_liq_wallets", lambda d: d["hip3_liq_wallets"]),
    "S1n": ("S1_hip3_liq_notional", lambda d: d["hip3_liq_notional"]),
    "S5": ("S5_liq_events", lambda d: d["liq_events"]),
    "S2_15": ("S2_retrade_15_daily", lambda d: d["s2_retrade_15"] / d["s2_denominator"]),
    "S2_60": ("S2_retrade_60_daily", lambda d: d["s2_retrade_60"] / d["s2_denominator"]),
    "active": ("active_wallets", lambda d: d["active_wallets"]),
    "long": (None, lambda d: d["liq_notional_long"] / d["liq_notional"]),
}


def stats_block(data):
    ev = data["event_day"]
    days = data["days"]
    base = [d for d in days if d["day"] != ev]
    if len(base) != data["baseline"]["days"] or min(d["day"] for d in base) != data["baseline"]["first"] \
            or max(d["day"] for d in base) != data["baseline"]["last"]:
        raise SellOffError("the baseline is not the 30 days 2026-10-06 to 2026-11-04")
    out = {k: measure(days, ev, fn) for k, (_, fn) in MEASURES.items()}
    ed = next(d for d in days if d["day"] == ev)
    out["pooled_15"] = sum(d["s2_retrade_15"] for d in base) / sum(d["s2_denominator"] for d in base)
    out["pooled_60"] = sum(d["s2_retrade_60"] for d in base) / sum(d["s2_denominator"] for d in base)
    out["event"] = ed
    # Not pre-stated (fix round 1): the same four measures against the 22 weekdays among the 30 days before. 5 Nov was a Thursday and the
    # builder-listed markets are much quieter at weekends, so the weekday median is the fairer "normal". The page labels it as an extra.
    wd = {}
    is_wd = lambda day: dt.date.fromisoformat(day).weekday() < 5   # noqa: E731
    if not is_wd(ev):
        raise SellOffError("the event day is not a weekday")
    for k in ("P1", "P2", "S1w", "S1n"):
        fn = MEASURES[k][1]
        b = [fn(d) for d in base if is_wd(d["day"])]
        m = st.median(b)
        wd[k] = {"median": m, "ratio": fn(ed) / m, "n": len(b), "max": max(b), "rank": 1 + sum(v > fn(ed) for v in b)}
    out["wd"] = wd
    out["n_weekend"] = sum(1 for d in base if not is_wd(d["day"]))
    # 6 Nov: replaces the unsupported "close to idle at weekends" with the weekend numbers themselves.
    we = sorted((d["hip3_liq_wallets"], d["day"]) for d in base if not is_wd(d["day"]))
    out["we_hip3"] = {"median": st.median(v for v, _ in we), "max": we[-1][0], "max_day": we[-1][1]}
    return out


def check_against_summary(data, S):
    """The analysis printed its own summary; the days must reproduce it."""
    summ = data["summary"]
    def close(a, b, what):
        if not math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-9):
            raise SellOffError(f"{what}: the days give {a!r}, the analysis summary says {b!r}")
    for k, (name, _) in MEASURES.items():
        if name is None:
            continue
        s = summ[name]
        m = S[k]
        for a, b in (("E", "E"), ("median", "median"), ("q1", "q1"), ("q3", "q3"), ("min", "min"), ("max", "max")):
            close(m[a], s[b], f"{name}.{b}")
        close(m["ratio"], s["ratio_E_over_median"], f"{name}.ratio")
        if m["rank"] != s["rank_of_31"] or m["max_day"] != s["max_day_baseline"]:
            raise SellOffError(f"{name}: rank or highest baseline day differs from the analysis summary")
    close(S["pooled_15"], summ["S2_retrade_15_pooled_baseline"], "pooled 15 min")
    close(S["pooled_60"], summ["S2_retrade_60_pooled_baseline"], "pooled 60 min")
    ed = S["event"]
    for k in ("s2_denominator", "s2_retrade_15", "s2_retrade_60"):
        if ed[k] != summ["S2_E_counts"][k]:
            raise SellOffError(f"S2 count {k} differs from the analysis summary")
    close(S["long"]["E"], summ["S4_long_share_E"], "long share")
    close(S["long"]["median"], summ["S4_long_share_baseline_median"], "long share median")
    if ed["hip3_active_wallets"] != summ["hip3_active_E"]:
        raise SellOffError("HIP-3 active wallets differ from the analysis summary")
    s3 = data["event"]["s3_exact"]
    close(s3["us_session_notional"] / s3["total"], s3["us_session_share"], "US session share")
    close(s3["total"], ed["liq_notional"], "S3 total against the day's force-closed value")


# ------------------------------------------------------------------ number formats
def i(x):
    """A whole number with thousands separators; halves round up (a median of 1,754.5 prints 1,755)."""
    return f"{int(math.floor(x + 0.5)):,}"


def sig3(x):
    """Three significant figures, no trailing zeros dropped past the point that matter: 283.2 -> '283', 57.5 -> '57.5', 3.31 -> '3.31'."""
    if x == 0:
        return "0"
    d = 2 - int(math.floor(math.log10(abs(x))))
    r = round(x, d)
    return f"{r:,.{max(d, 0)}f}"


def musd(x):
    """US dollars as millions, 3 significant figures, no dollar sign (the lint reads '$283' as a price)."""
    return sig3(x / 1e6)


def pct(x, dp=1):
    return f"{100 * x:.{dp}f}%"


def times(x):
    return f"{x:.1f}"


def day_label(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%b')}"


def day_long(iso):
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B')} {d.year}"


def weekday_long(iso):
    return dt.date.fromisoformat(iso).strftime("%A")


def ny_time(utc_label):
    """'2026-11-05 15:00' (UTC) -> '10:00 a.m.' New York time (zoneinfo, so the daylight-saving date is not typed)."""
    t = dt.datetime.strptime(utc_label, "%Y-%m-%d %H:%M").replace(tzinfo=dt.timezone.utc).astimezone(ZoneInfo("America/New_York"))
    h = t.hour % 12 or 12
    return f"{h}:{t.minute:02d} {'a.m.' if t.hour < 12 else 'p.m.'}", t


# ------------------------------------------------------------------ charts (inline SVG, drawn at build time)
W, H = 420, 214
PL, PR, PT, PB = 46, 412, 14, 176


def nice_step(top):
    for step in (1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500, 1000, 2000, 2500, 5000, 10000, 20000):
        if top / step <= 4.0001:
            return step
    return top / 4


def ticks_for(top, fmt):
    step = nice_step(top)
    n = int(math.ceil(top / step - 1e-9))
    hi = step * n
    return hi, [{"v": step * k, "label": fmt(step * k)} for k in range(n + 1)]


def bar_chart(items, fmt, alt, label_every=None, highlight=None, shade=None):
    """items: [(label, value or None, tooltip)]. Returns the geometry the template draws."""
    vals = [v for _, v, _ in items if v is not None]
    hi, ticks = ticks_for(max(vals), fmt)
    n = len(items)
    slot = (PR - PL) / n
    bw = max(slot - 2, 2)
    y_of = lambda v: PB - (PB - PT) * v / hi
    bars = []
    for k, (label, v, tip) in enumerate(items):
        x = PL + k * slot + (slot - bw) / 2
        bars.append({"x": round(x, 1), "w": round(bw, 1), "y": round(y_of(v), 1) if v is not None else PB,
                     "h": round(PB - y_of(v), 1) if v is not None else 0, "tip": tip, "event": k == highlight,
                     "cx": round(x + bw / 2, 1), "label": label if (label_every and (k % label_every == 0 or k == n - 1) and not (k == n - 1 and (n - 1) % label_every and (n - 1) % label_every < 3)) else None})
    return {"w": W, "h": H, "pl": PL, "pr": PR, "pt": PT, "pb": PB, "ticks": [{"y": round(y_of(t["v"]), 1), "label": t["label"]} for t in ticks],
            "bars": bars, "shade": shade, "ly": PB + 16, "median_y": None, "top": hi, "alt": alt}


def hours_shade(first, last_end):
    """x range of the hours [first, last_end) in a 24-bar hourly chart, as (x, width)."""
    slot = (PR - PL) / 24
    return round(PL + first * slot, 1), round((last_end - first) * slot, 1)


# ------------------------------------------------------------------ the context the template prints
def row(label, key, S, fmt, kind="count", note=None):
    m = S[key]
    return {"label": label, "e": fmt(m["E"]), "median": fmt(m["median"]), "iqr": f"{fmt(m['q1'])} to {fmt(m['q3'])}",
            "range": f"{fmt(m['min'])} to {fmt(m['max'])}", "ratio": times(m["ratio"]) if m["ratio"] is not None else "",
            "rank": m["rank"], "note": note}


def context(data=None):
    data = data or load()
    S = stats_block(data)
    check_against_summary(data, S)
    ev = data["event_day"]
    days = data["days"]
    E = S["event"]
    base = [d for d in days if d["day"] != ev]
    P1, P2, P3, S1w, S1n, S5, S2_15, S2_60, LONG = (S[k] for k in ("P1", "P2", "P3", "S1w", "S1n", "S5", "S2_15", "S2_60", "long"))

    # the two next-highest days across all markets, as a share below the event day
    by_w = sorted(base, key=lambda d: -d["liq_wallets"])[:2]
    runner = [{"day": day_label(d["day"]), "wallets": i(d["liq_wallets"]), "below": f"{100 * (1 - d['liq_wallets'] / E['liq_wallets']):.0f}%"} for d in by_w]
    prev_high_hip3 = max(base, key=lambda d: d["hip3_liq_wallets"])
    quiet = max(base, key=lambda d: d["s2_retrade_15"] / d["s2_denominator"])   # the baseline day with the highest share

    s3 = data["event"]["s3_exact"]
    busiest = s3["top15"][0]
    t_start, t_dt = ny_time(busiest[0])
    t_end = (t_dt + dt.timedelta(minutes=15))
    t_end_s = f"{(t_end.hour % 12 or 12)}:{t_end.minute:02d} {'a.m.' if t_end.hour < 12 else 'p.m.'}"
    # the session cut is stated in UTC and New York time; check the zone offset instead of typing it
    open_ny = dt.datetime(2026, 11, 5, *CUT_UTC[0], tzinfo=dt.timezone.utc).astimezone(ZoneInfo("America/New_York"))
    close_ny = dt.datetime(2026, 11, 5, *CUT_UTC[1], tzinfo=dt.timezone.utc).astimezone(ZoneInfo("America/New_York"))
    assert (open_ny.hour, open_ny.minute, close_ny.hour) == (9, 30, 16)

    F = {
        "wallets": i(E["liq_wallets"]), "wallets_median": i(P1["median"]), "wallets_ratio": times(P1["ratio"]),
        "hip3": i(E["hip3_liq_wallets"]), "hip3_median": i(S1w["median"]), "hip3_prev": i(prev_high_hip3["hip3_liq_wallets"]),
        "hip3_prev_day": day_label(prev_high_hip3["day"]), "hip3_ratio": times(S1w["ratio"]),
        "hip3_prev_weekday": weekday_long(prev_high_hip3["day"]),
        "hip3_vs_prev": times(E["hip3_liq_wallets"] / prev_high_hip3["hip3_liq_wallets"]), "hip3_active": i(E["hip3_active_wallets"]),
        "wd_n": S["wd"]["S1w"]["n"], "we_n": S["n_weekend"],
        "hip3_we_median": i(S["we_hip3"]["median"]), "hip3_we_max": i(S["we_hip3"]["max"]),
        "hip3_we_max_day": dt.date.fromisoformat(S["we_hip3"]["max_day"]).strftime("%A %-d %b"),
        "hip3_wd_median": i(S["wd"]["S1w"]["median"]), "hip3_wd_ratio": times(S["wd"]["S1w"]["ratio"]),
        "hip3_value_wd_ratio": times(S["wd"]["S1n"]["ratio"]), "wallets_wd_median": i(S["wd"]["P1"]["median"]),
        "wallets_wd_ratio": times(S["wd"]["P1"]["ratio"]), "value_wd_ratio": times(S["wd"]["P2"]["ratio"]),
        "hip3_wd_rank": S["wd"]["S1w"]["rank"], "hip3_wd_vs_max": times(E["hip3_liq_wallets"] / S["wd"]["S1w"]["max"]),
        "long_rank": LONG["rank"], "long_min": pct(LONG["min"], 0), "long_max": pct(LONG["max"], 0),
        "hip3_value": musd(E["hip3_liq_notional"]), "hip3_value_ratio": times(S1n["ratio"]),
        "value": musd(E["liq_notional"]), "value_ratio": times(P2["ratio"]), "value_median": musd(P2["median"]),
        "value_rank": P2["rank"], "long": pct(LONG["E"], 0), "long_median": pct(LONG["median"], 0),
        "active": i(E["active_wallets"]), "share_active": pct(P3["E"]), "share_active_median": pct(P3["median"]),
        "retrade15": pct(S2_15["E"]), "retrade15_n": i(E["s2_retrade_15"]), "retrade_den": i(E["s2_denominator"]),
        "pooled15": pct(S["pooled_15"]), "median15": pct(S2_15["median"]), "iqr15": f"{pct(S2_15['q1'])} to {pct(S2_15['q3'])}",
        "retrade60": pct(S2_60["E"]), "retrade60_n": i(E["s2_retrade_60"]), "pooled60": pct(S["pooled_60"]),
        "quiet_day": day_label(quiet["day"]), "quiet_share": pct(quiet["s2_retrade_15"] / quiet["s2_denominator"]),
        "quiet_wallets": i(int(math.floor(quiet["liq_wallets"] / 100 + 0.5)) * 100), "quiet_rank_note": S2_15["rank"],
        "events": i(E["liq_events"]), "events_median": i(S5["median"]),
        "session_share": pct(s3["us_session_share"], 0), "session_value": musd(s3["us_session_notional"]), "session_wallets": i(s3["us_session_wallets"]),
        "busiest_from": t_start, "busiest_to": t_end_s, "busiest_value": musd(busiest[1]), "busiest_wallets": i(busiest[2]),
        "cash_open": f"{open_ny.hour}:{open_ny.minute:02d} a.m.", "cash_close": f"{close_ny.hour - 12} p.m.",
        "cash_utc": f"{CUT_UTC[0][0]}:{CUT_UTC[0][1]:02d} to {CUT_UTC[1][0]}:{CUT_UTC[1][1]:02d} UTC",
        "v1_prec": pct(data["summary"]["V1"]["precision"]), "v1_rec": pct(data["summary"]["V1"]["recall"]),
        "v1_days": data["summary"]["V1"]["days"], "v1_wm": i(data["summary"]["V1"]["events_wm"]), "v1_mine": i(data["summary"]["V1"]["mine_wm"]),
        "event_long": day_long(ev), "event_short": day_label(ev), "event_weekday": weekday_long(ev),
        "base_first": day_label(data["baseline"]["first"]), "base_last": day_label(data["baseline"]["last"]),
    }

    rows = [
        row("Wallets force-closed, all markets", "P1", S, i),
        row("Value force-closed, all markets (millions of US dollars)", "P2", S, musd),
        row("Share of active wallets that were force-closed", "P3", S, pct),
        row("Wallets force-closed on builder-listed (HIP-3) markets", "S1w", S, i),
        row("Value force-closed on those markets (millions of US dollars)", "S1n", S, musd),
        row("Force-closed positions (wallet, market and block counted once)", "S5", S, i),
        row("Share of force-closed wallets that placed a new market order within 15 minutes", "S2_15", S, pct),
        row("The same within 60 minutes", "S2_60", S, pct),
    ]

    # charts
    c1 = bar_chart([(day_label(d["day"]), d["liq_wallets"], f"{day_long(d['day'])}: {i(d['liq_wallets'])} wallets force-closed") for d in days],
                   lambda v: f"{int(v / 1000)}k" if v else "0",
                   f"Bar chart of wallets force-closed on each of 31 days, {F['base_first']} to {F['event_short']}. {F['event_short']}: {F['wallets']}, the highest. Median of the 30 days before: {F['wallets_median']}. The same numbers are in the table below.",
                   label_every=6, highlight=len(days) - 1)
    c2 = bar_chart([(day_label(d["day"]), d["hip3_liq_wallets"], f"{day_long(d['day'])}: {i(d['hip3_liq_wallets'])} wallets force-closed on builder-listed (HIP-3) markets") for d in days],
                   lambda v: (f"{v / 1000:g}k" if v else "0"),
                   f"Bar chart of wallets force-closed on builder-listed (HIP-3) markets on each of 31 days. {F['event_short']}: {F['hip3']}, the highest. Median of the 30 days before: {F['hip3_median']}. The same numbers are in the table below.",
                   label_every=6, highlight=len(days) - 1)
    hours = data["event"]["hourly"]
    c3 = bar_chart([(f"{h['hour_utc']:02d}", (h["value"] / 1e6 if h["value"] is not None else None),
                     (f"{h['hour_utc']:02d}:00 to {h['hour_utc']:02d}:59 UTC: {musd(h['value'])} million US dollars force-closed, {i(h['wallets'])} wallets"
                      if h["value"] is not None else f"{h['hour_utc']:02d}:00 UTC: fewer than 10 wallets, not shown")) for h in hours],
                   lambda v: f"{v:g}" if v else "0",
                   f"Bar chart of the value force-closed in each hour of {F['event_short']} (UTC), in millions of US dollars. The busiest hours are inside the US stock-market session, which is shaded: {F['session_share']} of the day's value fell inside it. The same numbers are in the table below.",
                   label_every=6)
    sx, sw = hours_shade(CUT_UTC[0][0] + CUT_UTC[0][1] / 60, CUT_UTC[1][0] + CUT_UTC[1][1] / 60)
    c3["shade"] = {"x": sx, "w": sw}
    c1["median_y"] = round(PB - (PB - PT) * P1["median"] / c1["top"], 1)
    c2["median_y"] = round(PB - (PB - PT) * S1w["median"] / c2["top"], 1)
    suppressed = [h["hour_utc"] for h in hours if h["suppressed"]]

    top5 = []
    for name, wallets, value in data["summary"]["S1_top5_E"]:
        builder, _, market = name.partition(":")
        top5.append({"market": market, "builder": builder, "wallets": i(wallets), "value": musd(value)})

    t5 = sum(v for _, _, v in data["summary"]["S1_top5_E"]) / E["hip3_liq_notional"]
    names = [t["market"].removesuffix("-PERP") for t in top5]
    top5_names = ", ".join(names[:-1]) + " and " + names[-1]
    top5_share = f"{100 * t5:.0f}%"

    day_rows = [{"date": d["day"], "label": day_label(d["day"]), "wallets": i(d["liq_wallets"]), "value": musd(d["liq_notional"]),
                 "hip3": i(d["hip3_liq_wallets"]), "event": d["day"] == ev} for d in days]
    hour_rows = [{"hour": f"{h['hour_utc']:02d}", "value": musd(h["value"]) if h["value"] is not None else "fewer than 10 wallets",
                  "wallets": i(h["wallets"]) if h["wallets"] is not None else "–"} for h in hours]

    return {"F": F, "rows": rows, "runner": runner, "top5": top5, "top5_names": top5_names, "top5_share": top5_share, "c1": c1, "c2": c2, "c3": c3, "suppressed": suppressed,
            "day_rows": day_rows, "hour_rows": hour_rows, "prov": data["provenance"], "source": data["source"],
            "plan_sha": data["provenance"]["analysis_plan"]["sha256"], "plan_logged": data["provenance"]["analysis_plan"]["logged_utc"],
            "csv_url": CSV_PATH, "pack_url": PACK_URL, "pack_files": PACK_FILES, "n_inputs": len(data["provenance"]["inputs"]),
            "event_input_sha": next(x["sha256"] for x in data["provenance"]["inputs"] if x["day"] == ev),
            "pm": permarket(E, ev, {d["day"]: d for d in days}), "S": S}


# ------------------------------------------------------------------ market by market (descriptive, added after the plan)
# The CSV's status codes are the page's words (7 Nov, coordinator decision 2), so readers see one set of words.
STATUS = {"builders_docs": ("builder’s docs", "badge-ver"), "partly_sourced": ("partly sourced", "badge-part"),
          "no_source_found": ("no source found", "badge-none")}


def _sha(path):
    import hashlib
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def permarket(E, ev, by_day):
    """The 'Market by market' section from checks/selloff/zenodo/5-november-2026-per-market.csv and MARKETS-VERIFIED.csv.
    FAILS the build unless the rows add up to the study's own figures: the builder-listed values sum to the day's force-closed
    value there, the unique-wallet total is the page's wallet count, and the same for all markets."""
    pm_file = os.path.join(PACK_DIR, PM_CSV)
    rows = [r for r in csv.DictReader(open(pm_file, encoding="utf-8")) if r["date_utc"] == ev]
    tot = {r["scope"]: r for r in rows if r["row_type"] == "scope_total_unique_wallets"}
    hip, allm = tot["builder_listed"], tot["all_markets"]
    if int(hip["wallets_force_closed"]) != E["hip3_liq_wallets"] or int(allm["wallets_force_closed"]) != E["liq_wallets"]:
        raise SellOffError("per-market totals: unique wallets differ from the study's figures")
    if not math.isclose(float(hip["value_force_closed_usd"]), E["hip3_liq_notional"], abs_tol=0.01) or \
            not math.isclose(float(allm["value_force_closed_usd"]), E["liq_notional"], abs_tol=0.01):
        raise SellOffError("per-market totals: value differs from the study's figures")
    for scope, t in (("builder_listed", hip), ("all_markets", allm)):
        parts = [r for r in rows if r["row_type"] != "scope_total_unique_wallets" and (scope == "all_markets" or r["scope"] == scope)]
        if any(r["row_type"] == "markets_under_10_wallets_combined" and not r["value_force_closed_usd"] for r in parts):
            raise SellOffError("per-market: a combined small-market row is blank, so the rows cannot be added up")
        s = sum(float(r["value_force_closed_usd"]) for r in parts)
        if abs(s - float(t["value_force_closed_usd"])) > 0.01 * len(parts):
            raise SellOffError(f"per-market: the {scope} rows add up to {s:.2f}, not {t['value_force_closed_usd']}")
    verified = {r["market_as_listed"]: r for r in csv.DictReader(open(os.path.join(PACK_DIR, "MARKETS-VERIFIED.csv"), encoding="utf-8"))}
    total_v = float(hip["value_force_closed_usd"])
    mk = sorted((r for r in rows if r["scope"] == "builder_listed" and r["row_type"] == "market"),
                key=lambda r: -float(r["value_force_closed_usd"]))
    table = []
    for r in mk:
        v = float(r["value_force_closed_usd"])
        m30 = float(r["market_median_wallets_30d"])
        chk = verified.get(r["market"])
        st_label, st_cls = STATUS[chk["status"]] if chk else ("not checked", "badge-none")
        table.append({"market": r["market"].partition(":")[2].removesuffix("-PERP"), "builder": r["dex"],
                      "wallets": i(int(r["wallets_force_closed"])), "value": musd(v) if v >= 5000 else "under 0.01",
                      "share": pct(v / total_v, 2) if v / total_v >= 0.0001 else "under 0.01%", "long": pct(float(r["long_share_of_value"]), 0),
                      "median": f"{m30:,.1f}".removesuffix(".0"), "ratio": times(float(r["ratio_5nov_to_median"])) if r["ratio_5nov_to_median"] else "–",
                      "tracks": chk["what_it_tracks"] if chk and chk["status"] == "builders_docs" else "",
                      "status": st_label, "status_cls": st_cls, "src": chk["source_url"] if chk else None})
    small = next(r for r in rows if r["scope"] == "builder_listed" and r["row_type"] == "markets_under_10_wallets_combined")
    n_checked = len(verified)
    counts = {k: sum(1 for x in verified.values() if x["status"] == k) for k in STATUS}
    if any(x["status"] == "builders_docs" and not x["source_url"].startswith("https://") for x in verified.values()):
        raise SellOffError("MARKETS-VERIFIED.csv: a builders_docs row has no source URL")
    return {"top": table[:PM_TOP], "rest": table[PM_TOP:], "n_markets": len(table),
            "med_unlisted": sum(1 for r in mk if r["median_uses_unlisted_days"] == "yes"),
            "small_n": small["market"].split()[0], "small_value": musd(float(small["value_force_closed_usd"])),
            "small_pairs": i(int(small["sum_of_market_wallet_counts"])) if small["sum_of_market_wallet_counts"] else "",
            "unique": i(int(hip["wallets_force_closed"])), "pairs": i(int(hip["sum_of_market_wallet_counts"])),
            "overlap": i(int(hip["sum_of_market_wallet_counts"]) - int(hip["wallets_force_closed"])),
            "all_unique": i(int(allm["wallets_force_closed"])), "all_pairs": i(int(allm["sum_of_market_wallet_counts"])),
            "all_overlap": i(int(allm["sum_of_market_wallet_counts"]) - int(allm["wallets_force_closed"])),
            "value": musd(total_v), "csv_url": PM_CSV_PATH, "csv_sha": _sha(pm_file), "verified_url": PACK_URL + "MARKETS-VERIFIED.csv",
            "readme_url": PACK_URL + "MARKETS-README.txt", "script_url": PACK_URL + "per_market.py", "n_checked": n_checked,
            "counts": counts, "revision": PM_REVISION,
            "reupload": [{"day": day_label(d), "new": i(n), "published": i(by_day[d]["liq_wallets"])} for d, n in sorted(REUPLOAD.items(), reverse=True)], "checked_on": next(iter(verified.values()))["checked_utc_date"]}


# ------------------------------------------------------------------ the CSV download
def csv_text(data=None):
    data = data or load()
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(CSV_COLUMNS)
    for d in data["days"]:
        w.writerow([d["day"], d["liq_wallets"], f"{d['liq_notional']:.2f}", d["active_wallets"], f"{d['liq_wallets'] / d['active_wallets']:.6f}",
                    d["hip3_liq_wallets"], f"{d['hip3_liq_notional']:.2f}", f"{d['liq_notional_long'] / d['liq_notional']:.6f}",
                    d["s2_retrade_15"], d["s2_retrade_60"], d["s2_denominator"],
                    f"{d['s2_retrade_15'] / d['s2_denominator']:.6f}", f"{d['s2_retrade_60'] / d['s2_denominator']:.6f}"])
    return out.getvalue()


if __name__ == "__main__":
    print(csv_text())
