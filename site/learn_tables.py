#!/usr/bin/env python3
"""learn_tables.py: the two computed tables on /learn/ (SEO round 1, 6 Nov 2026), made at build time.

Nothing here is typed in or copied from another page. site/build.py imports this module to render the tables and to
write the CSV downloads; tests/test_seo1.py recomputes every value a second way (an exact-fraction recurrence, a brute
force over every sequence for short runs, and the closed form for the recovery gain).

1. Drawdown recovery. A fall of d (a fraction of the account) is undone by a gain of d / (1 - d) on what is left.
   `periods_to_recover` is plain compound arithmetic for a steady gain g per period; real trading has no steady gain,
   so the page labels that table as arithmetic only.
2. Losing streaks. With a loss probability q = 1 - win rate on every trade, independent of the one before, the chance
   of at least one run of k or more losses in n trades comes from a run-length recurrence over the length of the
   current run of losses: after each trade the run grows by one on a loss and goes back to zero on a win, and the
   sequences that reach k are set aside. The chance of NO such run is the weight left in the other states.
"""
import csv
import datetime
import io
import json
import math
import os

# ---- the grids (the page shows exactly these; the tests read them from here) -----------------------------------
DRAWDOWNS = (1, 2, 3, 5, 10, 15, 20, 25, 30, 35, 40, 50, 60, 70, 75, 80, 90)   # percent
PERIOD_GAINS = (0.5, 1, 2, 5)                                                  # percent per period (arithmetic only)
PERIOD_DRAWDOWNS = (5, 10, 20, 30, 50, 70, 90)                                 # percent, rows of the periods table
WIN_RATES = (30, 35, 40, 45, 50, 55, 60, 65, 70)                               # percent
TRADE_COUNTS = (50, 100, 500)
RUN_LENGTHS = (5, 8, 10)
COST_FRACTIONS = (1, 2, 5)                                                 # percent of the account lost on each loss (arithmetic only)


def recovery_gain(d_percent):
    """The gain, in percent of the account left, that undoes a fall of d_percent: d / (1 - d)."""
    d = d_percent / 100.0
    if not 0 <= d < 1:
        raise ValueError("a drawdown is at least 0 and under 100 percent")
    return 100.0 * d / (1.0 - d)


def periods_to_recover(d_percent, gain_percent):
    """Whole periods of a steady gain (compounded) needed to get back a fall of d_percent."""
    d, g = d_percent / 100.0, gain_percent / 100.0
    if not 0 < d < 1 or g <= 0:
        raise ValueError("needs a drawdown between 0 and 100 percent and a positive gain")
    return math.ceil(math.log(1.0 / (1.0 - d)) / math.log(1.0 + g) - 1e-12)


def prob_run_at_least(n, win_rate_percent, k):
    """P(at least one run of k or more losses among n independent trades), loss chance 1 - win rate.

    The state is the length of the current run of losses (0 to k-1); a run that reaches k leaves the state space."""
    if n < 0 or k < 1:
        raise ValueError("n is at least 0 and k at least 1")
    q = 1.0 - win_rate_percent / 100.0
    p = 1.0 - q
    state = [0.0] * k
    state[0] = 1.0
    for _ in range(n):
        nxt = [0.0] * k
        nxt[0] = p * sum(state)              # a win sends every state back to a run of zero
        for j in range(k - 1):               # a loss lengthens the run; from k-1 it reaches k and is set aside
            nxt[j + 1] = q * state[j]
        state = nxt
    return 1.0 - sum(state)


def streak_cost(f_percent, k):
    """The fall, in percent of the starting balance, after k losses in a row that each take f_percent of what is left."""
    return 100.0 * (1.0 - (1.0 - f_percent / 100.0) ** k)


def enumerate_runs(n, k):
    """Every win/loss sequence of n trades: [{"seq": "LLW", "longest": 2, "hit": True}, ...] in the order W before L
    at each trade. With a win rate of 50 percent each is equally likely, so the share with a run of k or more losses
    is the answer to prob_run_at_least(n, 50, k): the page prints this list as its worked example."""
    out = []
    for i in range(2 ** n):
        seq = "".join("L" if (i >> (n - 1 - j)) & 1 else "W" for j in range(n))
        longest = max((len(r) for r in seq.split("W")), default=0)
        out.append({"seq": seq, "longest": longest, "hit": longest >= k})
    return out


def format_gain(x, prose=False):
    """A gain as a percentage with one decimal (the table); prose=True drops a trailing .0 ("100%", not "100.0%")."""
    out = f"{x:,.1f}"
    if prose and out.endswith(".0"):
        out = out[:-2]
    return out + "%"


def format_prob(x):
    """A probability as a reader sees it: one decimal, with the two ends stated as bounds, never rounded to 0 or 100."""
    pct = 100.0 * x
    if pct < 0.05:
        return "<0.1%"
    if pct > 99.95:
        return ">99.9%"
    return f"{pct:.1f}%"


def recovery_rows():
    return [{"drawdown_pct": d, "gain_pct": recovery_gain(d)} for d in DRAWDOWNS]


def periods_rows():
    return [{"drawdown_pct": d, "periods": [periods_to_recover(d, g) for g in PERIOD_GAINS]} for d in PERIOD_DRAWDOWNS]


def streak_tables():
    """{n: [{"win_rate": w, "probs": [p for each k in RUN_LENGTHS]}, ...]} for each n in TRADE_COUNTS."""
    return {n: [{"win_rate": w, "probs": [prob_run_at_least(n, w, k) for k in RUN_LENGTHS]} for w in WIN_RATES]
            for n in TRADE_COUNTS}


def recovery_csv():
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["drawdown_percent", "gain_needed_percent"] +
               [f"periods_at_{g:g}_percent_per_period" for g in PERIOD_GAINS])
    for r in recovery_rows():
        w.writerow([r["drawdown_pct"], f"{r['gain_pct']:.4f}"] + [periods_to_recover(r["drawdown_pct"], g) for g in PERIOD_GAINS])
    return out.getvalue()


def streak_csv():
    out = io.StringIO()
    w = csv.writer(out, lineterminator="\n")
    w.writerow(["win_rate_percent", "trades", "run_of_losses_at_least", "probability"])
    for n, rows in streak_tables().items():
        for r in rows:
            for k, p in zip(RUN_LENGTHS, r["probs"]):
                w.writerow([r["win_rate"], n, k, f"{p:.6f}"])
    return out.getvalue()


# ---- the closes of 5 November 2026 (config/market_2026_11_05.json; the dated callout on the drawdown article and the
# ---- sell-off study read these; the arithmetic is the table's own recovery_gain) --------------------------------
MARKET_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config", "market_2026_11_05.json")


def drawdown_from_record(close, record):
    """The fall, in percent of the record close, that the close is below it: 100 * (1 - close / record)."""
    if not (record > 0 and 0 < close <= record):
        raise ValueError("needs a close at or below a positive record")
    return 100.0 * (1.0 - close / record)


def day_change(close, prior):
    """The one-day change in percent."""
    return 100.0 * (close / prior - 1.0)


def _long_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B')}"


def market_view(path=None):
    """Closes, one-day changes, drawdowns from the record and the gain each needs (recovery_gain of the drawdown), for the
    indices in the market file. Raw floats under 'raw'; the strings the pages print under the other keys."""
    with open(path or MARKET_JSON, encoding="utf-8") as f:
        m = json.load(f)
    out = {"read_on": m["read_on"], "credit": m["source"]["credit"], "date": m["date"], "reported": m["reported"], "indices": {}}
    for key, x in m["indices"].items():
        v = {"name": x["name"], "series": x["series"], "url": x["url"], "close": f"{x['close']:,.2f}", "prior_close": f"{x['prior_close']:,.2f}",
             "change": day_change(x["close"], x["prior_close"])}
        v["change_text"] = f"{abs(v['change']):.2f}%"
        v["raw"] = {"close": x["close"], "prior_close": x["prior_close"], "change_pct": v["change"]}
        if "record_close" in x:
            dd = drawdown_from_record(x["close"], x["record_close"])
            need = recovery_gain(dd)
            v.update({"record": f"{x['record_close']:,.2f}", "record_date": _long_date(x["record_date"]), "drawdown": f"{dd:.1f}%",
                      "need": f"{need:.1f}%", "drawdown_2": f"{dd:.2f}", "need_2": f"{need:.2f}"})
            v["raw"].update({"record": x["record_close"], "drawdown_pct": dd, "need_pct": need})
        if "larger_fall_since" in x:
            v["larger_fall"] = {"date": _long_date(x["larger_fall_since"]["date"]) + " " + x["larger_fall_since"]["date"][:4],
                                "change_pct": x["larger_fall_since"]["change_pct"]}
        out["indices"][key] = v
    vix = out["indices"]["vix"]
    vix["points"] = f"{m['indices']['vix']['close'] - m['indices']['vix']['prior_close']:+.2f}"
    dj = out["indices"]["djia"]
    dj["points_text"] = f"{abs(m['indices']['djia']['close'] - m['indices']['djia']['prior_close']):,.2f}"
    return out


if __name__ == "__main__":   # python3 site/learn_tables.py: print both CSVs
    print(recovery_csv())
    print(streak_csv())
