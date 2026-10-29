#!/usr/bin/env python3
"""Write SYNTHETIC trades.csv and accounts.csv for prediction_test.py, with planted answers.

Nothing here is real data. Accounts are random hex labels, and every trade is drawn from the model below.
Deterministic: the same arguments give byte-identical files (a private random.Random(seed); its random(),
gauss(), randint(), choice(), sample(), shuffle(), getrandbits(), uniform() and expovariate() sequences are
stable across Python 3 versions).

Each synthetic trader has a hidden "impulsivity" z ~ N(0, 1) that sets the chance of re-entering within
15 minutes after a loss, the size multiplier after a loss, the chance of carrying on after 2 losses in a
row, and how much longer losers are held. Each trader also has a base trade rate, a win rate, win and loss
sizes and their own volatility, driven by g ~ N(0, 1).

Worlds (ARCHITECT-PREDICTION-STUDY-2026-10-30 section 5.1):
  L  planted logistic: breach ~ Bernoulli(logistic(a + b z)), with b set so that AUC(z) = 0.70
  M  mechanical: breaches come from replaying the trades under the account's own rules
  0  null: breaches depend on g only, and g is independent of z
  C  confounded: z drives g (g = 0.8 z + 0.6 e), and breaches depend on g only
  K  look-ahead canary: breach depends on a hidden k (logistic(-1.2 + 3 k)); k = 1 accounts trade at 0.25x
     size AFTER trade 30, and a breach falls in days 20-30 after T0 (so most later trades stay in the file)
  E  exclusions: world L plus planted E1-E7 cases, with the exact expected counts in the truth file

Usage (plain Terminal or Claude Code):
  python3 -I partner/make_fixture_prediction.py --out DIR [--world L] [--accounts 600] [--seed 7]
writes DIR/trades.csv, DIR/accounts.csv and DIR/truth.txt (the planted counts; never read by the test).
The README's expected output uses the defaults with PREREG-PREDICTION-EXAMPLE.md.
"""

import argparse
import math
import random

DAY = 86400
START = 1767225600 + 7 * 3600          # 2026-01-01 07:00 on the study clock (UTC+02:00 in the example block)
PERIOD_DAYS = 59                       # accounts start between 1 Jan and 28 Feb 2026
OFFSET_TEXT = "+02:00"
OFFSET_S = 2 * 3600
WINDOW = 30
OUTCOME_DAYS = 30
PREVALENCE = 0.35
AUC_Z = 0.70


def logistic(x):
    return 1.0 / (1.0 + math.exp(-x))


def _auc_of_logistic(a, b):
    """AUC of z for y ~ Bernoulli(logistic(a + b z)), z ~ N(0, 1), by quadrature on a grid."""
    zs = [-7 + 14 * i / 4000 for i in range(4001)]
    f = [math.exp(-z * z / 2) for z in zs]
    p = [logistic(a + b * z) for z in zs]
    w1 = [fi * pi for fi, pi in zip(f, p)]
    w0 = [fi * (1 - pi) for fi, pi in zip(f, p)]
    s1, s0 = sum(w1), sum(w0)
    cum0 = 0.0
    auc = 0.0
    for i in range(len(zs)):
        auc += w1[i] * (cum0 + 0.5 * w0[i])
        cum0 += w0[i]
    return auc / (s1 * s0), s1 / (s1 + s0)


def _alpha_for(b, prev):
    lo, hi = -10.0, 10.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if _auc_of_logistic(mid, b)[1] < prev:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def planted_coefficients(auc=AUC_Z, prev=PREVALENCE):
    """(a, b) with AUC(z) = auc and P(breach) = prev."""
    lo, hi = 0.0, 5.0
    for _ in range(50):
        mid = (lo + hi) / 2
        if _auc_of_logistic(_alpha_for(mid, prev), mid)[0] < auc:
            lo = mid
        else:
            hi = mid
    b = (lo + hi) / 2
    return _alpha_for(b, prev), b


_COEF = {}


def coef(world):
    if world not in _COEF:
        if world in ("L", "E"):
            _COEF[world] = planted_coefficients()
        else:
            _COEF[world] = (_alpha_for(1.0, PREVALENCE), 1.0)
    return _COEF[world]


def iso(t):
    """Study-clock seconds -> ISO-8601 text with the example block's offset."""
    s = t
    days, rem = divmod(s, DAY)
    # civil-from-days (Howard Hinnant), proleptic Gregorian
    z = days + 719468
    era = (z if z >= 0 else z - 146096) // 146097
    doe = z - era * 146097
    yoe = (doe - doe // 1460 + doe // 36524 - doe // 146096) // 365
    y = yoe + era * 400
    doy = doe - (365 * yoe + yoe // 4 - yoe // 100)
    mp = (5 * doy + 2) // 153
    d = doy - (153 * mp + 2) // 5 + 1
    m = mp + 3 if mp < 10 else mp - 9
    y = y + 1 if m <= 2 else y
    return "%04d-%02d-%02dT%02d:%02d:%02d%s" % (y, m, d, rem // 3600, (rem % 3600) // 60, rem % 60, OFFSET_TEXT)


def money(x):
    v = round(x, 2)
    return "%.2f" % (0.0 if v == 0 else v)


def trader(rng, world):
    z = rng.gauss(0, 1)
    e = rng.gauss(0, 1)
    g = 0.8 * z + 0.6 * e if world == "C" else e
    return {
        "z": z, "g": g, "k": 1 if (world == "K" and rng.random() < 0.5) else 0,
        "A": rng.choice((10000, 25000, 50000, 100000)),
        "sigma": (0.0075 if world == "M" else 0.0045) * math.exp(0.35 * g),
        "rate": rng.uniform(2.5, 6.0),
        "win_p": rng.uniform(0.42, 0.55),
        "rr": rng.uniform(0.8, 1.5),
        "p_re": logistic(-1.2 + 1.0 * z),
        "size_mult": math.exp(0.35 * z),
        "p_cont": logistic(0.3 + 1.0 * z),
        "hold_mult": math.exp(0.35 * z),
        "syms": rng.sample(("EURUSD", "GBPUSD", "XAUUSD", "NAS100", "US30", "USDJPY"), rng.randint(1, 3)),
        "base": rng.choice((0.1, 0.5, 1.0, 2.0, 5.0)),
        "drawdown": rng.choice(("static",) * 7 + ("trailing_eod",) * 2 + ("trailing_trade",)),
    }


def poisson(rng, lam):
    L, k, p = math.exp(-lam), 0, 1.0
    while True:
        p *= rng.random()
        if p <= L:
            return k
        k += 1


def trades_for(rng, tr, start, until, dates_only=False, all_wins=False):
    """Trades opened from `start` to `until` (study-clock seconds)."""
    out = []
    day0 = start // DAY
    d = day0 + (1 if dates_only else 0)     # a dates-only trade opens at 00:00, so from the next day
    prev_loss = False
    while d * DAY < until:
        wd = (d + 3) % 7          # Monday = 0
        if wd >= 5:
            d += 1
            continue
        n = poisson(rng, tr["rate"])
        t = d * DAY + 8 * 3600 + rng.randint(0, 3600)
        if d == day0:
            t = max(t, start + 60)
        run = 0
        for _ in range(n):
            if dates_only:
                op = d * DAY
                hold = DAY * rng.randint(1, 3)
            else:
                op = t
                hold = int(60 + rng.expovariate(1 / 900.0))
            win = all_wins or rng.random() < tr["win_p"]
            if not win and not dates_only:
                hold = int(hold * tr["hold_mult"])
            if op >= until:
                break
            sym = rng.choice(tr["syms"])
            mult = tr["size_mult"] * math.exp(rng.gauss(0, 0.15)) if prev_loss else math.exp(rng.gauss(0, 0.1))
            size = max(0.01, round(tr["base"] * mult, 2))
            unit = size / tr["base"]
            scale = tr["A"] * tr["sigma"] * rng.uniform(0.5, 1.5) * unit
            pnl = scale * tr["rr"] if win else -scale
            out.append({"open_s": op, "close_s": op + hold, "symbol": sym, "direction": rng.choice(("long", "short")),
                        "size": size, "pnl": round(pnl, 2)})
            prev_loss = pnl < 0
            run = run + 1 if pnl < 0 else 0
            if dates_only:
                break
            close = op + hold
            if prev_loss and rng.random() < tr["p_re"]:
                t = close + rng.randint(30, 840)
            else:
                t = close + int(60 + rng.expovariate(1 / 2700.0))
            if run >= 2 and rng.random() > tr["p_cont"]:
                break
            if t >= (d + 1) * DAY - 3600:
                break
        d += 1
    return out


def t0_of(trades):
    closes = sorted(t["close_s"] for t in trades)
    return closes[WINDOW - 1] if len(closes) >= WINDOW else None


def mechanical(trades, tr):
    """World M: replay under the account's rules (5% daily, 10% max of A, the account's drawdown kind, day
    boundary 00:00) and a 10% target checked at the end of a day. Returns (outcome, time)."""
    A = tr["A"]
    daily, mx, target = 0.05 * A, 0.10 * A, 0.10 * A
    eq = peak = 0.0
    floor = -mx
    day = None
    start = 0.0
    for t in sorted(trades, key=lambda x: x["close_s"]):
        k = t["close_s"] // DAY
        if k != day:
            if day is not None:
                if tr["drawdown"] == "trailing_eod" and eq > peak:
                    peak, floor = eq, eq - mx
                if eq >= target:
                    return "passed", (day + 1) * DAY - 1
            day, start = k, eq
        eq += t["pnl"]
        if eq <= start - daily:
            return "daily", t["close_s"]
        if eq <= floor:
            return "max", t["close_s"]
        if tr["drawdown"] == "trailing_trade" and eq > peak:
            peak, floor = eq, eq - mx
    return None, None


def account(rng, world, start, special=None):
    tr = trader(rng, world)
    horizon = start + 75 * DAY
    trades = trades_for(rng, tr, start, horizon, dates_only=special == "E2", all_wins=special == "E3")
    if world == "K" and tr["k"]:
        order = sorted(range(len(trades)), key=lambda i: trades[i]["close_s"])
        for i in order[WINDOW:]:
            t = trades[i]
            t["size"] = max(0.01, round(t["size"] * 0.25, 2))
            t["pnl"] = round(t["pnl"] * 0.25, 2)
    t0 = t0_of(trades)
    rec = {"start": start, "A": tr["A"], "drawdown": tr["drawdown"], "z": tr["z"], "abuse": special == "E5",
           "bot": special == "E6"}
    if special == "E1short":
        cut = sorted(t["close_s"] for t in trades)[WINDOW - 5]
        trades = [t for t in trades if t["close_s"] <= cut]
        rec.update(outcome="active", ot=None, end=cut + DAY)
        return rec, trades
    if t0 is None:
        raise RuntimeError("generator: an ordinary account with fewer than 30 trades")
    if special == "E1breach":
        closes = sorted(t["close_s"] for t in trades)
        ot = closes[rng.randint(9, WINDOW - 2)]
        trades = [t for t in trades if t["close_s"] <= ot]
        rec.update(outcome=rng.choice(("daily", "max")), ot=ot, end=ot)
        return rec, trades
    if special == "E4":
        end = t0 + rng.randint(1, OUTCOME_DAYS - 1) * DAY
        trades = [t for t in trades if t["close_s"] <= end]
        rec.update(outcome="active", ot=None, end=end)
        return rec, trades
    w_end = t0 + OUTCOME_DAYS * DAY
    if world == "M":
        out, ot = mechanical(trades, tr)
        if out is None or ot > w_end:
            out, ot = "active", None
    else:
        a, b = coef(world)
        x = {"L": tr["z"], "E": tr["z"], "0": tr["g"], "C": tr["g"], "K": tr["k"]}[world]
        if world == "K":
            a, b = -1.2, 3.0
        y = rng.random() < logistic(a + b * x)
        if y:
            ot = t0 + rng.randint(20 * DAY if world == "K" else 60, OUTCOME_DAYS * DAY)
            out = rng.choice(("daily", "max"))
        elif rng.random() < 0.15:
            ot = t0 + rng.randint(60, OUTCOME_DAYS * DAY)
            out = "passed"
        else:
            out, ot = "active", None
    if ot is not None:
        trades = [t for t in trades if t["close_s"] <= ot]
        end = ot
    else:
        end = w_end + DAY
        trades = [t for t in trades if t["close_s"] <= end]
    rec.update(outcome=out, ot=ot, end=end)
    return rec, trades


def make_world(world, n_accounts, seed):
    """Returns (accounts, trades, truth). accounts: list of dicts; trades: list of (account_id, trade)."""
    rng = random.Random(seed)
    specials = [None] * n_accounts
    if world == "E":
        plan = [("E1breach", 0.20), ("E1short", 0.03), ("E2", 0.02), ("E3", 0.02), ("E4", 0.10), ("E5", 0.05),
                ("E6", 0.02)]
        k = 0
        for name, share in plan:
            for _ in range(int(round(share * n_accounts))):
                specials[k] = name
                k += 1
        rng.shuffle(specials)
    accs, trades = [], []
    for i in range(n_accounts):
        start = START + rng.randint(0, PERIOD_DAYS * DAY - 8 * 3600)
        acc_id = "%016x" % rng.getrandbits(64)
        rec, tl = account(rng, world, start, specials[i])
        rec["id"] = acc_id
        rec["special"] = specials[i]
        rec["key"] = ""
        accs.append(rec)
        for t in tl:
            trades.append((acc_id, t))
    truth = {"read": n_accounts}
    if world == "E":
        ordinary = [a for a in accs if a["special"] is None]
        ordinary.sort(key=lambda a: a["start"])
        n_pairs = int(round(0.03 * n_accounts))
        for j in range(n_pairs):
            first, later = ordinary[2 * j], ordinary[2 * j + 1]
            key = "t%06d" % j
            first["key"] = later["key"] = key
        truth.update({"E1": sum(1 for a in accs if a["special"] in ("E1breach", "E1short")),
                      "E1_breached_before_t0": sum(1 for a in accs if a["special"] == "E1breach"),
                      "E2": specials.count("E2"), "E3": specials.count("E3"), "E4": specials.count("E4"),
                      "E5": specials.count("E5"), "E6": specials.count("E6"), "E7": n_pairs})
        truth["eligible"] = n_accounts - sum(truth[k] for k in ("E1", "E2", "E3", "E4", "E5", "E6", "E7"))
    rng.shuffle(trades)          # firms export in any order; the script must not rely on it
    return accs, trades, truth


def csv_text(accs, trades):
    tl = ["account_id,open_time,close_time,symbol,direction,size,pnl"]
    for acc, t in trades:
        tl.append("%s,%s,%s,%s,%s,%s,%s" % (acc, iso(t["open_s"]), iso(t["close_s"]), t["symbol"], t["direction"],
                                            "%.2f" % t["size"], money(t["pnl"])))
    al = ["account_id,start_time,start_balance,daily_loss,max_loss,drawdown,trail_stop_at,outcome,outcome_time,"
          "data_end_time,trader_key,abuse_flag,bot_flag"]
    for a in accs:
        al.append("%s,%s,%d,%s,%s,%s,,%s,%s,%s,%s,%d,%d" % (
            a["id"], iso(a["start"]), a["A"], money(0.05 * a["A"]), money(0.10 * a["A"]), a["drawdown"],
            a["outcome"], "" if a["ot"] is None else iso(a["ot"]), iso(a["end"]), a["key"], a["abuse"], a["bot"]))
    return "\n".join(tl) + "\n", "\n".join(al) + "\n"


def write(out_dir, world, n_accounts, seed):
    accs, trades, truth = make_world(world, n_accounts, seed)
    t, a = csv_text(accs, trades)
    sep = "" if out_dir.endswith("/") else "/"
    with open(out_dir + sep + "trades.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write(t)
    with open(out_dir + sep + "accounts.csv", "w", encoding="utf-8", newline="") as fh:
        fh.write(a)
    with open(out_dir + sep + "truth.txt", "w", encoding="utf-8", newline="") as fh:
        for k in sorted(truth):
            fh.write("%s = %s\n" % (k, truth[k]))
    return truth


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description="Write synthetic trades.csv and accounts.csv (planted answers).")
    ap.add_argument("--out", required=True, help="an existing folder")
    ap.add_argument("--world", default="L", choices=("L", "M", "0", "C", "K", "E"))
    ap.add_argument("--accounts", type=int, default=600)
    ap.add_argument("--seed", type=int, default=7)
    a = ap.parse_args()
    write(a.out, a.world, a.accounts, a.seed)
