"""Volatility-scaled momentum: real at factor scale, dead at five positions.

A pre-registered test of whether scaling cross-sectional momentum by its own
recent realised volatility survives the constraints of a small retail account.

    pip install -r requirements.txt
    python reproduce_volmom.py

PART A is survivorship-free and runs in about a minute: Kenneth French's
momentum factor, built from CRSP, which retains delisted firms. PART B is the
version a $750 five-position account could actually hold, and it needs ~10
minutes on first run to fetch monthly closes for 1,209 tickers. Both download
their own data. Nothing is shipped in this directory but code.

WHAT WAS FIXED BEFORE THE DATA WAS TOUCHED, and the whole point of the
exercise: three specifications, their parameters, the sample splits, the cost
model and seven numeric kill criteria were written down first. They are
reproduced in README.md verbatim. Two deviations were forced afterwards and
are named in the README rather than quietly absorbed.

THE RESULT IS NEGATIVE AND THAT IS THE FINDING. Part A passes. Part B fails
K5, K6 and K7 -- buy-and-hold SPY beat every specification on risk-adjusted
return over the holdout. No money was committed.
"""
from __future__ import annotations

import csv
import io
import json
import math
import os
import ssl
import statistics
import sys
import time
import urllib.request
import warnings
import zipfile

warnings.filterwarnings("ignore")

FRENCH = "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
MEMBERSHIP_URL = ("https://raw.githubusercontent.com/fja05680/sp500/master/"
                  "S%26P%20500%20Historical%20Components%20%26%20Changes%20"
                  "(Updated).csv")
CACHE = "cache"

# ---- fixed before the data was touched -----------------------------------
TARGET_VOL = 0.12          # Barroso & Santa-Clara's own annualised target
VOL_WINDOW_DAYS = 126      # their realised-variance window, in trading days
RANK_SKIP_MONTHS = 1       # 12-1 momentum: skip the most recent month
N_POSITIONS = 5            # CapLimits.max_positions
MIN_PRICE = 5.00           # CapLimits.min_price
DRAWDOWN_HALT = 0.10       # CapLimits.max_drawdown_halt_pct
BASE_COST = 0.0020         # round trip, charged on turnover
COST_GRID = (0.0010, 0.0020, 0.0050, 0.0100)
BONFERRONI_T = 2.394       # 3 specifications, alpha 0.05/3, two-sided
DELISTING = {"sell_at_last": 0.0, "crsp_minus30": -0.30, "total_loss": -1.00}

A_SPLIT = "198101"         # Part A: in-sample before, holdout from
B_SPLIT = "2013-01"        # Part B: in-sample before, holdout from


def _ctx():
    bundle = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    return ssl.create_default_context(cafile=bundle) if bundle else None


def fetch(url, timeout=90):
    kw = {"timeout": timeout}
    ctx = _ctx()
    if ctx is not None:
        kw["context"] = ctx
    return urllib.request.urlopen(url, **kw).read()


def french(name):
    raw = fetch(FRENCH + name)
    z = zipfile.ZipFile(io.BytesIO(raw))
    return z.read(z.namelist()[0]).decode("latin-1")


def parse_french(text, keylen):
    """{YYYYMM or YYYYMMDD: [floats]}. -99.99 and -999 mark missing."""
    out = {}
    for line in text.splitlines():
        parts = [c.strip() for c in line.split(",")]
        if len(parts) < 2 or not parts[0].isdigit() or len(parts[0]) != keylen:
            continue
        try:
            vals = [float(v) for v in parts[1:] if v != ""]
        except ValueError:
            continue
        if any(v <= -99.0 for v in vals):
            continue
        out[parts[0]] = vals
    return out


def stats(returns):
    n = len(returns)
    mu = statistics.mean(returns)
    sd = statistics.stdev(returns)
    equity = peak = 1.0
    mdd = 0.0
    halts = 0
    tripped = False
    for r in returns:
        equity *= (1.0 + r)
        if equity > peak:
            peak, tripped = equity, False
        draw = equity / peak - 1.0
        mdd = min(mdd, draw)
        if draw <= -DRAWDOWN_HALT and not tripped:
            halts += 1
            tripped = True
    z = [(r - mu) / sd for r in returns]
    return {
        "n": n,
        "ann": (1.0 + mu) ** 12 - 1.0,
        "vol": sd * math.sqrt(12.0),
        "sharpe": (mu / sd) * math.sqrt(12.0),
        "monthly_sharpe": mu / sd,
        "mdd": mdd,
        "worst": min(returns),
        "t": mu / (sd / math.sqrt(n)),
        "halts": halts,
        "skew": sum(x ** 3 for x in z) / n,
        "kurt": sum(x ** 4 for x in z) / n,      # raw Pearson; normal = 3
    }


def deflated_sharpe(sharpe, n_trials, var_trial_sharpes, n_obs, skew, kurt):
    """Bailey & Lopez de Prado (2014). `sharpe` is per-period, not annualised."""
    euler = 0.5772156649015329
    emax = math.sqrt(var_trial_sharpes) * (
        (1 - euler) * _ppf(1 - 1.0 / n_trials)
        + euler * _ppf(1 - 1.0 / (n_trials * math.e)))
    radicand = 1 - skew * sharpe + ((kurt - 1) / 4.0) * sharpe ** 2
    if radicand <= 0:
        return float("nan")
    se = math.sqrt(radicand / (n_obs - 1))
    return _cdf((sharpe - emax) / se)


def _cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _ppf(p):
    """Inverse normal CDF by bisection -- exact enough and keeps this stdlib."""
    lo, hi = -10.0, 10.0
    for _ in range(200):
        mid = (lo + hi) / 2.0
        if _cdf(mid) < p:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


# ============================================================ PART A =======
def part_a():
    """Survivorship-free mechanism test, 1927-2026, on Ken French's data."""
    print("=" * 74)
    print("PART A -- survivorship-free, Kenneth French (CRSP, keeps delisted firms)")
    print("=" * 74)

    mom_m = parse_french(french("F-F_Momentum_Factor_CSV.zip"), 6)
    mom_d = parse_french(french("F-F_Momentum_Factor_daily_CSV.zip"), 8)
    ff_m = parse_french(french("F-F_Research_Data_Factors_CSV.zip"), 6)

    months = sorted(set(mom_m) & set(ff_m))
    print("monthly WML observations: %d   %s -> %s"
          % (len(months), months[0], months[-1]))

    # S2 input: annualised realised vol of DAILY WML over the prior 126 days,
    # known at the END of month t-1 and used to scale month t. No look-ahead.
    dkeys = sorted(mom_d)
    dvals = [mom_d[k][0] / 100.0 for k in dkeys]
    vol_asof = {}
    cursor = 0
    for m in months:
        while cursor < len(dkeys) and dkeys[cursor][:6] <= m:
            cursor += 1
        window = dvals[max(0, cursor - VOL_WINDOW_DAYS):cursor]
        if len(window) == VOL_WINDOW_DAYS:
            daily_var = sum(r * r for r in window) / float(VOL_WINDOW_DAYS)
            vol_asof[m] = math.sqrt(252.0 * daily_var)

    # S3 input: cumulative market index against its own 10-month average,
    # both as of the end of month t-1.
    level = 1.0
    index = {}
    for m in months:
        level *= (1.0 + (ff_m[m][0] + ff_m[m][3]) / 100.0)   # Mkt-RF + RF
        index[m] = level
    above = {}
    for i, m in enumerate(months):
        if i >= 9:
            ma = sum(index[months[j]] for j in range(i - 9, i + 1)) / 10.0
            above[m] = index[m] > ma

    rows = []
    for i in range(1, len(months)):
        m, prev = months[i], months[i - 1]
        if prev not in vol_asof or prev not in above:
            continue
        wml = mom_m[m][0] / 100.0
        rows.append((m, wml,
                     wml * (TARGET_VOL / vol_asof[prev]),
                     wml if above[prev] else 0.0))
    print("usable months after warm-up: %d   %s -> %s\n"
          % (len(rows), rows[0][0], rows[-1][0]))

    names = ["S1 plain WML", "S2 vol-scaled", "S3 trend filter"]
    out = {}
    for label, keep in (("IN-SAMPLE 1927..1980", lambda x: x < A_SPLIT),
                        ("HOLDOUT   1981..2026", lambda x: x >= A_SPLIT)):
        sel = [r for r in rows if keep(r[0])]
        print("--- %s  (n=%d) ---" % (label, len(sel)))
        print("  %-17s %9s %9s %8s %9s %9s %8s"
              % ("spec", "ann ret", "ann vol", "Sharpe", "max DD", "worst mo", "t"))
        for c, name in enumerate(names, start=1):
            s = stats([r[c] for r in sel])
            out[(label, name)] = s
            print("  %-17s %8.2f%% %8.2f%% %8.2f %8.1f%% %8.1f%% %8.2f"
                  % (name, 100 * s["ann"], 100 * s["vol"], s["sharpe"],
                     100 * s["mdd"], 100 * s["worst"], s["t"]))
        print("")

    hold = [r for r in rows if r[0] >= A_SPLIT]
    msh = [stats([r[c] for r in hold])["monthly_sharpe"] for c in (1, 2, 3)]
    var_trials = statistics.variance(msh)
    print("--- holdout moments and the deflated Sharpe (3 trials) ---")
    for c, name in enumerate(names, start=1):
        s = stats([r[c] for r in hold])
        dsr = deflated_sharpe(s["monthly_sharpe"], 3, var_trials,
                              s["n"], s["skew"], s["kurt"])
        print("  %-17s skew %6.2f  kurtosis %6.2f  DSR %.4f"
              % (name, s["skew"], s["kurt"], dsr))

    s1 = out[("HOLDOUT   1981..2026", "S1 plain WML")]
    s2 = out[("HOLDOUT   1981..2026", "S2 vol-scaled")]
    print("\n--- Part A kill criteria ---")
    print("  K1a S2 holdout Sharpe >= 0.50 : %.2f  -> %s"
          % (s2["sharpe"], "PASS" if s2["sharpe"] >= 0.50 else "FAIL"))
    print("  K1b S2 beats S1 by >= 0.15    : %.2f  -> %s"
          % (s2["sharpe"] - s1["sharpe"],
             "PASS" if (s2["sharpe"] - s1["sharpe"]) >= 0.15 else "FAIL"))
    print("  significance threshold |t| >= %.3f (Bonferroni, 3 specs)\n"
          % BONFERRONI_T)
    return out


# ============================================================ PART B =======
def load_membership():
    path = os.path.join(CACHE, "sp500_membership.csv")
    if not os.path.exists(path):
        print("downloading the dated membership table (fja05680/sp500, MIT) ...")
        data = fetch(MEMBERSHIP_URL, timeout=120)
        with io.open(path, "wb") as fh:
            fh.write(data)
    rows = []
    with io.open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            rows.append((r["date"],
                         set(t for t in r["tickers"].split(",") if t)))
    rows.sort()
    return rows


def load_prices(universe):
    """Monthly closes per ticker. Cached; failures are CLASSIFIED, not lumped.

    A throttled request and a genuinely dataless ticker look identical in a
    bare try/except, and treating the first as the second is how a silent
    coverage gap gets published as a result.
    """
    path = os.path.join(CACHE, "monthly_closes.json")
    store = json.load(io.open(path)) if os.path.exists(path) else {"px": {}, "status": {}}
    todo = [t for t in universe if t not in store["status"]]
    if todo:
        import yfinance as yf
        print("fetching monthly closes for %d tickers (cached after this run) ..."
              % len(todo))
        for i, ticker in enumerate(todo, 1):
            state, series = "ERROR", None
            for attempt in (1, 2):
                try:
                    frame = yf.Ticker(ticker).history(
                        start="1996-01-01", end="2026-10-01", interval="1mo",
                        auto_adjust=True, raise_errors=True)
                    frame = frame.dropna(subset=["Close"])
                    if frame.empty:
                        state = "NO_DATA"
                    else:
                        state = "OK"
                        series = dict((str(ix)[:7], round(float(c), 6))
                                      for ix, c in zip(frame.index, frame["Close"]))
                    break
                except Exception as exc:
                    low = str(exc)[:120].lower()
                    throttled = any(k in low for k in
                                    ("rate", "429", "too many", "timeout", "curl"))
                    state = "THROTTLED" if throttled else "ERROR"
                    if not throttled or attempt == 2:
                        break
                    time.sleep(10)
            store["status"][ticker] = state
            if series:
                store["px"][ticker] = series
            if i % 100 == 0:
                json.dump(store, io.open(path, "w"))
                print("   %d/%d" % (i, len(todo)))
            time.sleep(0.15)
        json.dump(store, io.open(path, "w"))
    return store


def part_b():
    """The five-position, long-only version a small account could hold."""
    print("=" * 74)
    print("PART B -- five positions, long only, real costs and a 10% halt")
    print("=" * 74)
    if not os.path.isdir(CACHE):
        os.makedirs(CACHE)

    members = load_membership()
    ever = sorted(set(t for _, ts in members for t in ts))
    current = members[-1][1]
    print("membership: %d rows, %s -> %s, %d tickers ever, %d current"
          % (len(members), members[0][0], members[-1][0], len(ever), len(current)))

    store = load_prices(ever)
    px, status = store["px"], store["status"]

    ok_cur = sum(1 for t in current if status.get(t) == "OK")
    departed = set(ever) - current
    ok_dep = sum(1 for t in departed if status.get(t) == "OK")
    throttled = sum(1 for v in status.values() if v == "THROTTLED")
    print("\n--- COVERAGE, and this is the study's binding limitation ---")
    print("  current members : %4d of %4d OK (%5.1f%%)"
          % (ok_cur, len(current), 100.0 * ok_cur / len(current)))
    print("  departed members: %4d of %4d OK (%5.1f%%)"
          % (ok_dep, len(departed), 100.0 * ok_dep / len(departed)))
    print("  throttled anywhere: %d  (non-zero invalidates the coverage read)"
          % throttled)
    print("  The names free data cannot see are disproportionately the ones")
    print("  that failed, so every Part B return below is an UPPER BOUND.\n")

    months = sorted(set(m for v in px.values() for m in v))

    def price(ticker, month):
        return px.get(ticker, {}).get(month)

    def members_asof(ym):
        cut, best = ym + "-31", None
        for date, names in members:
            if date <= cut:
                best = names
            else:
                break
        return best or members[0][1]

    picks = {}
    coverage = []
    for i in range(13, len(months) - 1):
        form, hold = months[i], months[i + 1]
        index_now = members_asof(form)
        have = [t for t in index_now if price(t, form) is not None]
        coverage.append(100.0 * len(have) / len(index_now))
        candidates = []
        for t in have:
            old = price(t, months[i - 12])
            recent = price(t, months[i - RANK_SKIP_MONTHS])
            now = price(t, form)
            if not old or not recent or now is None or now < MIN_PRICE or old <= 0:
                continue
            candidates.append((recent / old - 1.0, t))
        candidates.sort(reverse=True)
        picks[hold] = [t for _, t in candidates[:N_POSITIONS]]

    hold_months = sorted(picks)
    print("  rebalances: %d  %s -> %s" % (len(hold_months),
                                          hold_months[0], hold_months[-1]))
    early = [c for c, m in zip(coverage, hold_months) if m < B_SPLIT]
    late = [c for c, m in zip(coverage, hold_months) if m >= B_SPLIT]
    print("  median index coverage: in-sample %.1f%%, holdout %.1f%%\n"
          % (statistics.median(early), statistics.median(late)))
    return picks, hold_months, months, price


def part_b_returns(picks, hold_months, months, price):
    """Returns, costs, the 10% halt, and the three delisting assumptions."""
    gross, turnover, previous = [], [], set()
    for m in hold_months:
        names = picks[m]
        i = months.index(m)
        if not names:
            gross.append(dict((k, 0.0) for k in DELISTING))
            turnover.append(0.0)
            previous = set()
            continue
        acc = dict((k, []) for k in DELISTING)
        for t in names:
            entry, exit_ = price(t, months[i - 1]), price(t, m)
            for key, delisted_return in DELISTING.items():
                if entry and exit_ and entry > 0:
                    acc[key].append(exit_ / entry - 1.0)
                elif entry and entry > 0:
                    acc[key].append(delisted_return)
                else:
                    acc[key].append(0.0)
        gross.append(dict((k, sum(v) / len(v)) for k, v in acc.items()))
        held = set(names)
        turnover.append(len(held ^ previous) / (2.0 * N_POSITIONS)
                        if previous else 1.0)
        previous = held

    # S2's scale: trailing 12 MONTHLY returns, annualised. A DECLARED
    # DEVIATION -- the pre-registration specified 126 DAILY returns, and Part
    # B has monthly closes only. A 12-observation estimate is far noisier, so
    # S2 is scaled more weakly here than in Part A. Leverage capped at 3x.
    scale = []
    for k in range(len(gross)):
        window = [g["crsp_minus30"] for g in gross[max(0, k - 12):k]]
        if len(window) < 12:
            scale.append(None)
            continue
        sd = statistics.stdev(window) * math.sqrt(12.0)
        scale.append(min(TARGET_VOL / sd, 3.0) if sd > 0 else None)

    # S3: own price above its own 10-MONTH average. Also a declared
    # deviation -- the pre-registration said a 200-day average.
    s3 = []
    for m in hold_months:
        i = months.index(m)
        keep = []
        for t in picks[m]:
            history = [price(t, months[j]) for j in range(i - 10, i)]
            history = [h for h in history if h]
            now = price(t, months[i - RANK_SKIP_MONTHS])
            if len(history) == 10 and now and now > sum(history) / 10.0:
                keep.append(t)
        if not keep:
            s3.append(0.0)
            continue
        rs = []
        for t in keep:
            entry, exit_ = price(t, months[i - 1]), price(t, m)
            rs.append(exit_ / entry - 1.0 if entry and exit_ and entry > 0 else 0.0)
        s3.append(sum(rs) / len(rs))

    return gross, turnover, scale, s3


def spy_series():
    path = os.path.join(CACHE, "spy_monthly.json")
    if os.path.exists(path):
        return json.load(io.open(path))
    import yfinance as yf
    frame = yf.Ticker("SPY").history(start="1996-01-01", end="2026-10-01",
                                     interval="1mo", auto_adjust=True)
    frame = frame.dropna(subset=["Close"])
    out = dict((str(ix)[:7], round(float(c), 6))
               for ix, c in zip(frame.index, frame["Close"]))
    json.dump(out, io.open(path, "w"))
    return out


def report_part_b(hold_months, gross, turnover, scale, s3):
    spy = spy_series()
    ordered = sorted(spy)

    def build(spec, cost, delist="crsp_minus30"):
        out = []
        for k in range(len(hold_months)):
            if spec == "S1":
                r, tn = gross[k][delist], turnover[k]
            elif spec == "S2":
                w = scale[k]
                r, tn = (0.0, 0.0) if w is None else (w * gross[k][delist],
                                                      turnover[k] * w)
            else:
                r, tn = s3[k], turnover[k]
            out.append(r - cost * 2.0 * tn)
        return out

    print("mean monthly turnover %.1f%%  -> about %.1f trades/month at %d positions\n"
          % (100 * statistics.mean(turnover),
             2 * N_POSITIONS * statistics.mean(turnover), N_POSITIONS))

    results = {}
    for label, keep in (("IN-SAMPLE 1997..2012", lambda m: m < B_SPLIT),
                        ("HOLDOUT   2013..2026", lambda m: m >= B_SPLIT)):
        idx = [k for k, m in enumerate(hold_months) if keep(m)]
        print("--- %s  (n=%d) ---" % (label, len(idx)))
        print("  %-4s %-7s %9s %8s %9s %6s %6s"
              % ("spec", "cost", "ann ret", "Sharpe", "max DD", "t", "halts"))
        for spec in ("S1", "S2", "S3"):
            for cost in COST_GRID:
                s = stats([build(spec, cost)[k] for k in idx])
                if cost == BASE_COST:
                    results[(label, spec)] = s
                print("  %-4s %6.2f%% %8.2f%% %8.2f %8.1f%% %6.2f %6d"
                      % (spec, 100 * cost, 100 * s["ann"], s["sharpe"],
                         100 * s["mdd"], s["t"], s["halts"]))
        bench = stats([spy[m] / spy[ordered[ordered.index(m) - 1]] - 1.0
                       for m in (hold_months[k] for k in idx)])
        results[(label, "SPY")] = bench
        print("  %-4s %6s  %8.2f%% %8.2f %8.1f%% %6.2f %6d"
              % ("SPY", "-", 100 * bench["ann"], bench["sharpe"],
                 100 * bench["mdd"], bench["t"], bench["halts"]))
        print("")

    hold_idx = [k for k, m in enumerate(hold_months) if m >= B_SPLIT]
    print("--- the delisting assumption, holdout, S1 at the base cost ---")
    for key in ("sell_at_last", "crsp_minus30", "total_loss"):
        s = stats([build("S1", BASE_COST, key)[k] for k in hold_idx])
        print("  %-14s ann %7.2f%%  Sharpe %5.2f  halts %d"
              % (key, 100 * s["ann"], s["sharpe"], s["halts"]))

    print("\n--- breakeven round-trip cost (holdout, t falls below %.3f) ---"
          % BONFERRONI_T)
    breakeven = {}
    for spec in ("S1", "S2", "S3"):
        lo, hi = 0.0, 0.20
        for _ in range(60):
            mid = (lo + hi) / 2.0
            if stats([build(spec, mid)[k] for k in hold_idx])["t"] >= BONFERRONI_T:
                lo = mid
            else:
                hi = mid
        breakeven[spec] = lo
        print("  %-4s %6.3f%%" % (spec, 100 * lo))

    print("\n--- KILL CRITERIA, holdout, %.2f%% cost ---" % (100 * BASE_COST))
    holdout = "HOLDOUT   2013..2026"
    bench = results[(holdout, "SPY")]
    verdicts = []
    for spec in ("S1", "S2", "S3"):
        s = results[(holdout, spec)]
        checks = [("K4 Sharpe>=0.30", s["sharpe"] >= 0.30),
                  ("K5 beats SPY", s["ann"] > bench["ann"]),
                  ("K6 halts<=3", s["halts"] <= 3),
                  ("K7 breakeven>=0.50%", breakeven[spec] >= 0.0050)]
        verdicts.append(all(ok for _, ok in checks))
        print("  %-4s %s" % (spec, "  ".join(
            "%s %s" % (n, "PASS" if ok else "FAIL") for n, ok in checks)))
    print("\n  VERDICT: %s"
          % ("a specification passed every criterion" if any(verdicts)
             else "NO specification passed. No money moves."))


def main():
    part_a()
    picks, hold_months, months, price = part_b()
    gross, turnover, scale, s3 = part_b_returns(picks, hold_months, months, price)
    report_part_b(hold_months, gross, turnover, scale, s3)
    return 0


if __name__ == "__main__":
    sys.exit(main())
