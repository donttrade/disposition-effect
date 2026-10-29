#!/usr/bin/env python3
"""DT-1 habit features from one account's first 30 trades (the prediction study, version 1.0).

Imported by prediction_test.py. It opens no file, writes nothing and prints nothing.

Where the code comes from
  The group and median functions below are VERBATIM copies from the donttrade engine's Python mirror
  `reference/habits_ref.py` (private repo, METHOD_VERSION 2026-10-23.stats2f, file SHA-256
  87e6e16b6834a8f22c9016714614f939d5e4453b3d3e35f2f55e73afd07002d1). Each copy names its source lines.
  `median` is copied from the public `tests/reference/engine_ref.py` (SHA-256
  6491d9dd3c0db092737ad5f18fc50d41b8b672a30748621627893d4ac5b551ab), lines 3387-3394.
  The permutation tests, Holm correction and report text are NOT copied: the study uses no p-value
  from the engine. The habit definitions themselves are already public (habit-flags.js and the site).
  partner/parity/dt1_golden.json proves these functions give the engine's (habits.mjs) numbers.

The within-W strip (the one change from strip.js)
  strip.js divides each size by that symbol's median size in the WHOLE file, which would let trades
  after the 30th leak into the features (a look-ahead). Here q = size / that symbol's median size
  WITHIN W, the first 30 trades, and nothing after trade 30 is read.

The six features (every one coded so that higher = more of the habit)
  F1 reentry_share          revenge_groups: n_a / (n_a + n_b)
  F2 streak_share           tilt_groups: n_a / (n_a + n_b); undefined when n_a + n_b = 0
  F3 size_after_loss_ratio  size_up: log(median q after a loss / median q after a win); undefined when
                            either group is empty or either median is 0
  F4 size_after_loss_share  size_up: after-loss trades with q >= 1.5, divided by n_a; undefined when n_a = 0
  F5 large_loss_share       oversized: the share of W's trades that are losses above 2x the median loss;
                            undefined when W has no loss
  F6 hold_gap_ratio         hold_gap: log(median hold of losers / median hold of winners); undefined when
                            there is no loser or no winner, or either median is 0
  DT-1 = the mean of the defined features' mid-rank percentiles among the scored accounts (dt1_scores).
"""

import bisect
import decimal
import math

DT_VERSION = "DT-1"
ENGINE_METHOD = "2026-10-23.stats2f"
WINDOW = 30
MIN_FEATURES = 3
FEATURES = ("reentry_share", "streak_share", "size_after_loss_ratio", "size_after_loss_share",
            "large_loss_share", "hold_gap_ratio")
REVENGE_S = 900          # habits_ref.py line 86
HOLD_LONG = 43200        # habits_ref.py line 98


# ---------------------------------------------------------------- verbatim copies

def median(xs):
    # engine_ref.py lines 3387-3394 (verbatim)
    if not xs:
        return None
    v = sorted(xs)
    k = len(v) // 2
    if len(v) % 2:
        return v[k]
    return (v[k - 1] + v[k]) / 2


def add(xs):
    # habits_ref.py lines 160-164 (verbatim)
    s = 0.0
    for v in xs:
        s += v
    return s


def _round_half_up(x):
    # habits_ref.py lines 179-181 (verbatim)
    """Math.round: the nearest integer, halves toward +infinity."""
    return math.floor(x + 0.5)


def is_date_only_row(r):
    # habits_ref.py lines 184-186 (verbatim)
    """R-D3 addendum 3: opens at 00:00 and is held a whole number of days (0 included)."""
    return r["o"] % 1440 == 0 and r["h"] % 86400 == 0


def count_date_only(rows):
    # habits_ref.py lines 189-190 (verbatim)
    return sum(1 for r in rows if is_date_only_row(r))


def is_dates_only(rows):
    # habits_ref.py lines 193-195 (verbatim)
    """Date-only rows are 5% or more of the rows (20 * k >= n); an empty file is not dates-only."""
    return len(rows) > 0 and 20 * count_date_only(rows) >= len(rows)


def merge_rows(rows):
    # habits_ref.py lines 208-227 (verbatim)
    """R-D3 addendum I-5: rows sharing (s, d, o) become one trade; a row alone in its key is returned as is."""
    at, groups = {}, []
    for i, r in enumerate(rows):
        k = ("date-only", i) if is_date_only_row(r) else (r["s"], r["d"], r["o"])   # R-D3 addendum 3 rule 5
        if k not in at:
            at[k] = len(groups)
            groups.append([r])
        else:
            groups[at[k]].append(r)
    out = []
    for g in groups:
        if len(g) == 1:
            out.append(g[0])
            continue
        cents = sum(_round_half_up(r["p"] * 100) for r in g)
        thou = sum(_round_half_up(r["q"] * 1000) for r in g)
        out.append({"o": g[0]["o"], "h": max(r["h"] for r in g), "d": g[0]["d"], "q": thou / 1000, "p": cents / 100,
                    "s": g[0]["s"], "f": g[0]["f"]})
    return out


def prepare(rows):
    # habits_ref.py lines 230-247 (verbatim)
    """Section 3.1: R1's items plus s, d, the file's calendar day, the minute of the day and cls."""
    items = []
    for i, r in enumerate(rows):
        op = 60 * r["o"]
        day = r["o"] // 1440
        items.append({"i": i, "o": r["o"], "open": op, "close": op + r["h"], "h": r["h"], "q": r["q"], "p": r["p"],
                      "s": r["s"], "d": r["d"], "day": day, "tod": r["o"] - 1440 * day,
                      "cls": 1 if r["h"] >= HOLD_LONG else 0})
    by_close = sorted(items, key=lambda t: (t["close"], t["open"], t["i"]))
    by_open = sorted(items, key=lambda t: (t["open"], t["close"], t["i"]))
    closes = [t["close"] for t in by_close]
    streak = []
    run = 0
    for t in by_close:
        run = run + 1 if t["p"] < 0 else 0
        streak.append(run)
    return items, by_close, by_open, closes, streak


def prior_index(t, by_close, closes):
    # habits_ref.py lines 254-259 (verbatim)
    """Index in by_close of the latest trade closed at or before t opened, excluding t itself."""
    k = bisect.bisect_right(closes, t["open"]) - 1
    while k >= 0 and by_close[k]["i"] == t["i"]:
        k -= 1
    return k


def ratio(a, b):
    # habits_ref.py lines 806-807 (verbatim)
    return (a / b) if (a is not None and b is not None and b > 0) else None


def revenge_groups(by_open, by_close):
    # habits_ref.py lines 845-860 (verbatim)
    loss_closes = [t for t in by_close if t["p"] < 0]
    lc = [t["close"] for t in loss_closes]
    a, b = [], []
    for k, t in enumerate(by_open):
        if k == 0:
            continue  # the first trade has nothing before it
        m = bisect.bisect_left(lc, t["open"] - REVENGE_S)
        hit = False
        while m < len(lc) and lc[m] <= t["open"]:
            if loss_closes[m]["i"] != t["i"]:
                hit = True
                break
            m += 1
        (a if hit else b).append(t)
    return a, b


def tilt_groups(by_open, by_close, closes, streak):
    # habits_ref.py lines 909-921 (verbatim)
    a, b, a3 = [], [], []
    for t in by_open:
        k = prior_index(t, by_close, closes)
        if k < 0:
            continue
        if streak[k] >= 2:
            a.append(t)
            if streak[k] >= 3:
                a3.append(t)
        else:
            b.append(t)
    return a, b, a3


def size_up_groups(by_open, by_close, closes):
    # habits_ref.py lines 873-889, the group and median part of size_up() (verbatim apart from the
    # function boundary; the habit() record, the test and the trace are dropped)
    a, b, pool, flags = [], [], [], []
    for t in by_open:
        k = prior_index(t, by_close, closes)
        if k < 0:
            continue
        pp = by_close[k]["p"]
        if pp < 0:
            a.append(t)
            pool.append(t)
            flags.append(1)
        elif pp > 0:
            b.append(t)
            pool.append(t)
            flags.append(0)
    ma = median([t["q"] for t in a])
    mb = median([t["q"] for t in b])
    big = [t for t in a if t["q"] >= 1.5]   # line 889: the dollars items of size_up
    return a, b, ma, mb, ratio(ma, mb), big


def oversized_parts(by_close):
    # habits_ref.py lines 935-943, oversized() without the habit() record (verbatim apart from the return)
    losses = [t for t in by_close if t["p"] < 0]
    med = median([-t["p"] for t in losses])
    big = [t for t in losses if med is not None and -t["p"] > 2 * med]
    n = len(by_close)
    loss_total = add([-t["p"] for t in losses])
    share_trades = len(big) / n if n else None
    share_dollars = (add([-t["p"] for t in big]) / loss_total) if loss_total > 0 else None
    return losses, big, share_trades, share_dollars, med


def hold_gap_parts(by_close):
    # habits_ref.py lines 811-816, the median part of hold_gap() (verbatim apart from the return)
    losers = [t for t in by_close if t["p"] < 0]
    winners = [t for t in by_close if t["p"] > 0]
    ma = median([t["h"] for t in losers])
    mb = median([t["h"] for t in winners])
    dollars = [t for t in losers if mb is not None and t["h"] > mb]
    return losers, winners, ma, mb, ratio(ma, mb), dollars


# ---------------------------------------------------------------- the within-W strip

def _half_away_2dp(x):
    """P&L rounded to the cent, half away from zero (strip.js round2). x is a Decimal."""
    return float(x.quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_HALF_UP))


def _half_away_3dp(x):
    """strip.js round3 on a float: Math.floor(|x| * 1000 + 0.5) / 1000, keeping the sign."""
    return math.floor(abs(x) * 1000 + 0.5) * (1 if x >= 0 else -1) / 1000


def _o_minutes(open_s):
    return open_s // 60


def merge_raw(trades):
    """Raw trades -> merged trades, as habits.mjs mergeRows does: the same symbol, direction and open minute
    become one trade (P&L and size summed exactly, the longest hold kept, the first one's place kept). A
    date-only trade (opens at 00:00 and is held whole days) is never merged.
    trades: dicts {open_s, close_s, symbol, direction (+1/-1), size (Decimal), pnl (Decimal)} in input order;
    open_s and close_s are whole seconds on the study's clock (the sealed day offset applied)."""
    at, groups = {}, []
    for i, t in enumerate(trades):
        o = _o_minutes(t["open_s"])
        h = t["close_s"] - t["open_s"]
        k = ("date-only", i) if (o % 1440 == 0 and h % 86400 == 0) else (t["symbol"], t["direction"], o)
        if k not in at:
            at[k] = len(groups)
            groups.append([t])
        else:
            groups[at[k]].append(t)
    out = []
    for g in groups:
        o = _o_minutes(g[0]["open_s"])
        h = max(t["close_s"] - t["open_s"] for t in g)
        size = g[0]["size"]
        pnl = g[0]["pnl"]
        for t in g[1:]:
            size += t["size"]
            pnl += t["pnl"]
        # the engine's own derived times: open = the open minute, close = open + the hold
        out.append({"o_abs": o, "h": h, "open_s": 60 * o, "close_s": 60 * o + h, "symbol": g[0]["symbol"],
                    "direction": g[0]["direction"], "size": size, "pnl": pnl, "n_raw": len(g)})
    return out


def order_by_close(merged):
    """The engine's by_close order: (close, open, input position)."""
    return sorted(range(len(merged)), key=lambda i: (merged[i]["close_s"], merged[i]["open_s"], i))


def strip_window(window):
    """Engine rows {o h d q p s f} for W (already merged, in input order). q uses medians WITHIN W only."""
    min_o = min(t["o_abs"] for t in window)
    day = min_o // 1440
    weekday = (day + 3) % 7                      # 1970-01-01 was a Thursday; Monday = 0 (strip.js weekAnchor)
    anchor = (day - weekday) * 1440
    sizes, sym_index = {}, {}
    for t in window:
        if t["symbol"] not in sym_index:
            sym_index[t["symbol"]] = len(sym_index)
        sizes.setdefault(t["symbol"], []).append(float(t["size"]))
    med = {s: median(v) for s, v in sizes.items()}
    rows = []
    for t in window:
        m = med[t["symbol"]]
        q = _half_away_3dp(float(t["size"]) / m) if m > 0 else 0.0
        rows.append({"o": t["o_abs"] - anchor, "h": t["h"], "d": t["direction"], "q": q,
                     "p": _half_away_2dp(t["pnl"]), "s": sym_index[t["symbol"]], "f": ""})
    return rows


# ---------------------------------------------------------------- features

def _log_or_none(x):
    return math.log(x) if (x is not None and x > 0) else None


def features_from_rows(rows):
    """F1-F6 (None = undefined) plus the engine group counts, from engine rows of one window."""
    rows = merge_rows(rows)
    items, by_close, by_open, closes, streak = prepare(rows)
    ra, rb = revenge_groups(by_open, by_close)
    ta, tb, _ta3 = tilt_groups(by_open, by_close, closes, streak)
    sa, sb, sma, smb, seff, sbig = size_up_groups(by_open, by_close, closes)
    losses, obig, oshare, _odollars, _omed = oversized_parts(by_close)
    hl, hw, hma, hmb, heff, _hd = hold_gap_parts(by_close)
    f = {
        "reentry_share": len(ra) / (len(ra) + len(rb)) if (ra or rb) else None,
        "streak_share": len(ta) / (len(ta) + len(tb)) if (ta or tb) else None,
        "size_after_loss_ratio": (_log_or_none(seff) if (sa and sb and sma and smb) else None),
        "size_after_loss_share": len(sbig) / len(sa) if sa else None,
        "large_loss_share": oshare if losses else None,
        "hold_gap_ratio": (_log_or_none(heff) if (hl and hw and hma and hmb) else None),
    }
    counts = {"revenge": (len(ra), len(rb)), "tilt": (len(ta), len(tb)), "size_up": (len(sa), len(sb), len(sbig)),
              "oversized": (len(obig), len(losses)), "hold_gap": (len(hl), len(hw)), "n_trades": len(rows)}
    return f, counts


def account_window(trades, window=WINDOW):
    """One account's raw trades -> {status, ...}. status: 'short' (fewer than `window` merged trades),
    'dates_only' (E2), or 'ok' with rows, features, the window's trades and the trades after it."""
    merged = merge_raw(trades)
    order = order_by_close(merged)
    if len(order) < window:
        return {"status": "short", "n_trades": len(order)}
    w_idx = sorted(order[:window])               # W in input order (the engine's first-appearance order)
    w = [merged[i] for i in w_idx]
    rows = strip_window(w)
    if is_dates_only(rows):
        return {"status": "dates_only"}
    f, counts = features_from_rows(rows)
    t0 = merged[order[window - 1]]["close_s"]
    after = [merged[i] for i in order[window:]]
    w_close = [merged[i] for i in order[:window]]
    return {"status": "ok", "rows": rows, "features": f, "counts": counts, "t0": t0, "window": w_close,
            "after": after}


def n_defined(f):
    return sum(1 for k in FEATURES if f[k] is not None)


def _midrank_pct(values):
    """Mid-rank percentile on a 0-1 scale: (mid-rank - 0.5) / n, ties sharing the average rank."""
    n = len(values)
    order = sorted(range(n), key=lambda i: values[i])
    out = [0.0] * n
    i = 0
    while i < n:
        j = i + 1
        while j < n and values[order[j]] == values[order[i]]:
            j += 1
        r = (i + 1 + j) / 2.0
        for k in range(i, j):
            out[order[k]] = (r - 0.5) / n
        i = j
    return out


def dt1_scores(feature_list):
    """DT-1 for each account (a list of feature dicts, each with >= MIN_FEATURES defined): the mean of its
    defined features' mid-rank percentiles, each percentile taken among the accounts where that feature
    is defined. Nothing is fitted."""
    n = len(feature_list)
    pct = [[] for _ in range(n)]
    for k in FEATURES:
        idx = [i for i in range(n) if feature_list[i][k] is not None]
        if not idx:
            continue
        p = _midrank_pct([feature_list[i][k] for i in idx])
        for i, v in zip(idx, p):
            pct[i].append(v)
    return [sum(v) / len(v) if v else None for v in pct]
