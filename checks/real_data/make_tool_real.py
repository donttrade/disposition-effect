#!/usr/bin/env python3
"""Every figure the /tools/ page and the tool-page displays show, from REAL public data, into site/config/tool_real.json.

    PYTHONDONTWRITEBYTECODE=1 python3 -B checks/real_data/make_tool_real.py          # writes the JSON
    PYTHONDONTWRITEBYTECODE=1 python3 -B checks/real_data/make_tool_real.py --check  # recomputes, compares, writes nothing

The site build reads the committed JSON only (no network, no paid engine), as with tool_previews.json.

Inputs (each hashed into the JSON's "inputs"; all committed except the first, which holds the real tickers):
  checks/real_data/raw/real-trades.csv   fetch.py + make_real_csv.py, from the Mendeley xlsx; CC BY 4.0; gitignored
  checks/real_data/tools-printed.json    run_tools.cjs: what the free tool pages themselves printed on that file
  checks/real_data/eurusd.json           calc_eurusd.py, from the Federal Reserve Board's H.10 file (public domain)
  site/config/tool_real.report.json      run_report.py: the donttrade test's engine on the same file (private step)
  site/config/challenge_rules.json       the Readiness Check's firm-rules library (its first entry is the rule)

How each figure is made, and what it must equal (any mismatch stops the script):
  * the trades: tests/reference/engine_ref.py parses the CSV (the browser engine's tested mirror);
  * trade stats, drawdown, heatmap, Readiness Check and the disposition calculator: the tools' own JS cores, run in
    node (tool_run.mjs), so nothing is re-implemented; each must equal what the tool page printed;
  * the fan: whole past days drawn at random (the tool's method, its own seeded stream here because simulate() keeps
    no paths); its pass and bust counts must sit within Monte Carlo error of simulate()'s;
  * the $39 block rows: the report JSON, mapped to words as site/static/js/paid/report.js does.
SELECTION RULES (fixed before any result was looked at) are written into the JSON's "rules" and printed on the page.
"""
import datetime as dt
import hashlib
import json
import math
import os
import random
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
CONFIG = os.path.join(REPO, "site", "config")
OUT = os.path.join(CONFIG, "tool_real.json")
CSV = os.path.join(HERE, "raw", "real-trades.csv")
PRINTED = os.path.join(HERE, "tools-printed.json")
EURUSD = os.path.join(HERE, "eurusd.json")
REPORT = os.path.join(CONFIG, "tool_real.report.json")
RULES_LIB = os.path.join(CONFIG, "challenge_rules.json")
CODED = os.path.join(HERE, "real-trades.coded.csv")   # the shipped copy: tickers replaced with codes
SCRIPTS = ("fetch.py", "make_real_csv.py", "make_coded_csv.py", "calc_eurusd.py", "run_tools.cjs", "run_report.py", "tool_run.mjs",
           "make_tool_real.py")
MENDELEY_SHA = "000dbad9f8ed661f7991ad72b3af29f11e9cda2d5a50162f34bf289f78373bcb"
ODEAN = [13883, 79658, 11930, 110348]   # Odean (1998) Table I, entire year: RG, PG, RL, PL (checked in the paper)
FAN_PATHS, FAN_DAYS, FAN_SEED = 60, 30, 20261022
sys.path.insert(0, os.path.join(REPO, "tests", "reference"))
import engine_ref as E  # noqa: E402

# The attribution and the rules, word for word as the page prints them (Architect plan A.1 and A.2).
CREDITS = {
    "account": "Laramee, R. (2025). Stock Transactions Dataset. Mendeley Data, V1. doi:10.17632/k4tnk2nggv.1. Licensed "
               "CC BY 4.0. Changes: we kept the dataset’s market buys and sells (its combined, split-adjusted sheet) and "
               "turned them into a trade file, with ticker names replaced with codes; results are price gains in US "
               "dollars before fees, FX and dividends. "
               "Selection: the whole dataset, one anonymous investor; not picked by result. The dataset’s authors do "
               "not endorse donttrade.",
    "fx": "Board of Governors of the Federal Reserve System, H.10 Foreign Exchange Rates, euro, noon buying rates in New "
          "York (public domain): federalreserve.gov/releases/h10/hist/dat00_eu.htm.",
    "odean": "Odean, T. (1998). Are investors reluctant to realize their losses? Journal of Finance 53(5), 1775–1798, "
             "Table I, entire year. doi:10.1111/0022-1082.00072.",
}
RULES = {
    "account": "The whole dataset: every market buy and sell in its combined, split-adjusted sheet, in time order, US "
               "dollar rows only. Nothing is picked by result.",
    # 6 Nov fix round 2 (Manager item 7): why this dataset
    "why_account": "It is the only openly licensed, fill-level record of one real account we found.",
    "readiness": "One-phase challenge rules, the first rule set in our library, shown without the firm’s name: "
                 "$100,000; 10% target; 5% daily loss; 10% maximum loss (static); at least 3 trading days; no time "
                 "limit stated, so none is applied. The file’s times are read as UTC, because the dataset states no time zone, and a "
                 "trading day ends at midnight UTC+3, the rule’s own day boundary.",
    "fx": "The calendar month before the month of the H.10 file’s latest rate, so that the month is complete. Shown for "
          "scale only: no entry, stop, target or size is taken from it.",
    "odean": "Odean’s four published counts for the entire year, typed into the calculator. They follow the "
             "calculator’s counting rule (days with a sale).",
    "heatmap": "The tool names no best or worst cell, so neither does the preview. Hours are as in the file, which "
               "states no time zone; hours with no trades are left out.",
    "pass_rate": "No firm publishes cohort counts we can show, so this preview shows the formulas and an empty funnel, "
                 "and no invented counts.",
}


def sha256(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def money(v):
    """The tools' money format (static/js/tools/format.js money with sign): −$1,234.56, +$1,234.56, $0.00."""
    v = round(v, 2)
    return ("−$" if v < 0 else "+$" if v > 0 else "$") + f"{abs(v):,.2f}"


def pct1(x):
    return f"{x * 100:.1f}%"


def trades_of(csv_bytes):
    res = E.run_fixture(csv_bytes)
    if "result" not in res:
        sys.exit(f"the reference engine refused the CSV: {res}")
    return res


def tool_run(trades, preset, range_=True):
    keep = [{k: t[k] for k in ("open_ts", "close_ts", "hold_s", "pnl")} for t in trades]
    r = subprocess.run(["node", os.path.join(HERE, "tool_run.mjs")], input=json.dumps(
        {"trades": keep, "preset": preset, "account_size": preset["account_size"], "odean": ODEAN, "range": range_}),
        capture_output=True, text=True, check=True, cwd=HERE)
    return json.loads(r.stdout)


def replay(days, rnd, target, daily, max_loss, min_days, cap=250):
    """One replay by the Readiness Check's rules (static floor, daily loss from the day's start, target at end of day
    with min_days trading days), keeping the end-of-day equity path."""
    eq, path = 0.0, [0.0]
    for n in range(1, cap + 1):
        start = eq
        for p in days[rnd.randrange(len(days))]:
            eq += p
            if eq - start <= -daily:
                return "daily", path + [eq], n
            if eq <= -max_loss:
                return "max", path + [eq], n
        path.append(eq)
        if eq >= target and n >= min_days:
            return "pass", path, n
    return "timeout", path, cap


def fan(days, rules, sim, runs=10000):
    rnd = random.Random(FAN_SEED)
    out = [replay(days, rnd, rules["target"], rules["daily_loss"], rules["max_loss"], rules["min_days"]) for _ in range(runs)]
    counts = {k: sum(1 for o, _, _ in out if o == k) for k in ("pass", "daily", "max", "timeout")}
    tool = {"pass": sim["pass"], "daily": sim["bust_daily"], "max": sim["bust_max"], "timeout": sim["timeout"]}
    for k in tool:   # within 4 Monte Carlo standard errors (+2) of simulate()'s count
        p = tool[k] / runs
        tol = 4 * math.sqrt(max(p * (1 - p), 1 / runs) * runs) + 2
        assert abs(counts[k] - tool[k]) <= tol, ("fan vs simulate()", k, counts[k], tool[k], tol)
    def at(path, d):   # a replay that stopped keeps its final value
        return path[min(d, len(path) - 1)]
    pct = {}
    for q in (5, 50, 95):
        pct[f"p{q}"] = [round(sorted(at(p, d) for _, p, _ in out)[round(q / 100 * (runs - 1))]) for d in range(FAN_DAYS + 1)]
    return {"replays": runs, "seed": FAN_SEED, "counts": counts, "counts_simulate": tool,
            "paths": [[round(v) for v in p[:FAN_DAYS + 1]] for _, p, _ in out[:FAN_PATHS]],
            "outcomes": [o for o, _, _ in out[:FAN_PATHS]], "end_days": [n for _, _, n in out[:FAN_PATHS]], **pct}


REPORT_NAMES = {"oversized_loss": "Large losses"}   # report.js NAMES: the page's visible label
FACTS_ONLY = ("hold_gap", "oversized_loss")         # report.js FACTS_ONLY: "Your numbers", no luck check promised
VERDICT = {"distinguishable": "Distinguishable from noise", "not_distinguishable": "Not distinguishable from noise",
           "too_few": "Not enough trades to tell", "withheld": "Can’t check on this file", "coming": "Luck check coming"}


def report_result(h):
    """report.js badge(): the same mapping and words (sentence case, as in a table cell)."""
    if h["id"] in FACTS_ONLY:
        return "Your numbers"
    v = h["verdict"]
    if v == "descriptive" or (v == "withheld" and h.get("withheld") == "not_calibrated"):
        v = "coming"
    return VERDICT[v]


NAMES_LOWER = {"hold_gap": "holding losers longer than winners", "revenge": "re-entering soon after a loss",
               "size_up": "size after a loss", "tilt": "trading after a losing streak", "oversized_loss": "large losses"}


def report_why(h):
    """Why a habit got no luck check on this file, in the report's own terms (report.js, wording.js)."""
    if h["id"] in FACTS_ONLY:
        return "the test has no fair luck check for this habit yet, so it shows the facts"
    if h["verdict"] == "too_few":
        return (f"the check compares two groups of at least 30 trades each, and this file has {h['n_a']} and "
                f"{h['n_b']}")
    if h["verdict"] == "descriptive" or (h["verdict"] == "withheld" and h.get("withheld") == "not_calibrated"):
        return "its luck check is still being calibrated"
    if h["verdict"] == "withheld":
        return "it can’t be checked on this file"
    return None   # tested: the result column says how it came out


def months_of(ts_ms):
    return dt.datetime.fromtimestamp(ts_ms / 1000, dt.UTC).strftime("%b %Y")


def assemble(range_=True):
    csv_bytes = open(CSV, "rb").read()
    printed, fx, rep, lib = load(PRINTED), load(EURUSD), load(REPORT), load(RULES_LIB)
    csv_sha = hashlib.sha256(csv_bytes).hexdigest()
    assert printed["csv_sha256"] == csv_sha, "tools-printed.json was made from another CSV: rerun run_tools.cjs"
    assert rep["_provenance"]["csv_sha256"] == csv_sha, "tool_real.report.json was made from another CSV: rerun run_report.py"
    res = trades_of(csv_bytes)
    trades, st = res["result"]["trades"], res["stats"]
    # positions still open at the file's end: no exit, so no result; the tools leave them out (realised trades only)
    open_n = next(w["n"] for w in res["result"]["warnings"] if w["code"] == "W_OPEN_POSITIONS")
    # the shipped copy (make_coded_csv.py) must give the engine exactly the same trades, fills and figures
    coded = trades_of(open(CODED, "rb").read())
    keys = ("open_ts", "close_ts", "hold_s", "pnl", "qty", "dir")
    assert [tuple(t[k] for k in keys) for t in coded["result"]["trades"]] == [tuple(t[k] for k in keys) for t in trades]
    assert coded["stats"] == st and len(coded["result"]["executions"]) == len(res["result"]["executions"])
    preset = next(p for p in lib["presets"] if p["status"] != "not_quotable")
    assert preset["id"] == printed["prop_rule"]["preset_id"], (preset["id"], printed["prop_rule"])
    run = tool_run(trades, preset, range_)

    # --- trade stats and the equity curve (closed-trade equity in the engine's close order)
    ts = printed["trade_stats"]
    rows = dict(ts["rows"])
    mine = {"trades": str(st["n"]), "net": money(st["net_pnl"]), "win_rate": pct1(st["win_rate"]),
            "profit_factor": f"{st['profit_factor']:.2f}", "mean": money(st["expectancy"]),
            "largest_drawdown": money(-st["max_drawdown_abs"])}
    for k, v in mine.items():
        assert ts[k] == v, ("trade stats", k, ts[k], v)
    streak = f"{st['max_consec_losses']['n']} trades, {money(st['max_consec_losses']['pnl'])}"
    assert rows["Longest losing streak"] == streak, (rows["Longest losing streak"], streak)
    curve = [c["equity"] for c in run["dd"]["curve"]]   # closed-trade equity, the drawdown tool's own
    assert [c["ts"] for c in run["dd"]["curve"]] == sorted(c["ts"] for c in run["dd"]["curve"])
    assert len(curve) == st["n"] and abs(curve[-1] - st["net_pnl"]) < 1e-6
    deep = run["dd"]["summary"]["deepest"]
    assert abs(deep["depth"] - st["max_drawdown_abs"]) < 1e-6

    # --- drawdown: the tool's own episodes; the strings it printed
    longest = run["dd"]["summary"]["longest_trades"]
    high = run["dd"]["summary"]["high"]
    final = run["dd"]["summary"]["final_equity"]
    dd = {"largest": money(-deep["depth"]), "longest_trades": f"{longest['trades']} trades",
          "longest_days": f"{run['dd']['summary']['longest_days']['days']:,} calendar days", "current": money(final - high)}
    dtext = printed["drawdown"]["text"]
    assert printed["drawdown"]["largest"] == dd["largest"]
    for k in ("longest_trades", "longest_days", "current"):
        assert dd[k] in dtext, ("drawdown", k, dd[k])

    # --- heatmap: the printed rows (hours with trades), the tool's own level() for each cell
    hm = printed["heatmap"]
    grid, levels = run["hm"]["grid"], run["hm"]["levels"]
    hrows = []
    for r in hm["rows"]:
        h = int(r["hour"][:2])
        lv = []
        for wd, cell in enumerate(r["cells"]):
            g = grid[wd][h]
            if cell is None:
                assert g["n"] == 0, ("heatmap", r["hour"], wd)
                lv.append(None)
            else:
                assert cell == [money(g["total"]), f"{g['n']} trade{'s' if g['n'] != 1 else ''}"], ("heatmap", cell, g)
                lv.append(levels[wd][h])
        hrows.append({"hour": r["hour"], "levels": lv})
    assert all(levels[wd][h] is None for wd in range(5, 7) for h in range(24)), "weekend trades: the preview shows Mon-Fri"
    n_cells = sum(1 for r in hrows for v in r["levels"] if v is not None)
    n_tr = sum(grid[wd][int(r["hour"][:2])]["n"] for r in hrows for wd in range(5))
    assert n_tr == st["n"] and run["hm"]["n_small"] == run["hm"]["cells"] == n_cells, (n_tr, run["hm"])
    heat = {"cols": hm["cols"], "rows": hrows,
            "readout": f"{n_tr} trades in {n_cells} of {len(hrows) * 5} cells; every cell has fewer than 30 trades"}

    # --- Readiness Check: simulate() and the real-order sequence; the strings the tool printed
    sim, seq = run["sim"], run["seq"]
    days = run["days"]
    ex = printed["prop_expert"]
    m = re.search(r"Passed\t([\d,]+)\t([\d.]+%)\t(± [\d.]+%)", ex)
    assert int(m.group(1).replace(",", "")) == sim["pass"], (m.group(0), sim)
    assert f"{sim['bust_daily']:,}" in ex and f"{sim['bust_max']:,}" in ex
    assert re.search(r"Median trading days to bust\n(\d+)", ex).group(1) == str(sim["median_bust_days"])
    assert m.group(3) == f"± {run['mc']['pass'] * 100:.1f}%", (m.group(3), run["mc"])
    assert f"({len(days)} days, {st['n']} trades)" in printed["prop_sim"]["text"]
    rule = {"max": "maximum loss", "daily": "daily loss limit"}[seq["why"]]
    assert seq["outcome"] == "bust" and f"first broke the {rule} on day {seq['day']}." in printed["prop_sim"]["text"]
    rng = re.search(r"Passed\t([\d.]+% to [\d.]+%)", printed["prop_range"]).group(1)
    if run["range"] is not None:
        lo, hi = run["range"]["shares"]["pass"]
        assert rng == f"{lo * 100:.1f}% to {hi * 100:.1f}%", (rng, run["range"])
    cum, path = 0.0, []
    for d in days[:seq["day"]]:
        cum += sum(d)
        path.append(round(cum, 2))
    r_ = run["rules"]
    readiness = {"label": printed["prop_sim"]["label"], "replays": sim["runs"], "runs_passed": sim["pass"],
                 "share_passed": m.group(2), "mc_error": m.group(3), "range_pass": rng, "days": len(days),
                 "min_days_needed": 30, "busts_daily": sim["bust_daily"], "busts_max": sim["bust_max"],
                 "median_bust_days": sim["median_bust_days"], "first_break": {"day": seq["day"], "rule": rule},
                 "real_order_path": path, "account_size": preset["account_size"],
                 # 6 Nov fix round 2 (Manager): the result is never shown beside a real firm's name
                 "context": "This investor held stocks for months to years and never took a challenge, so the result "
                            "shows how the tool reads a real file, not how challenge traders do.",
                 "target": r_["target"], "daily_loss": r_["daily_loss"], "max_loss": r_["max_loss"],
                 "min_days": r_["min_days"], "drawdown": r_["drawdown"], "day_start": run["dayStart"]}
    assert (preset["account_size"], r_["target"], r_["daily_loss"], r_["max_loss"], r_["drawdown"], r_["min_days"]) == \
        (100000, 10000, 5000, 10000, "static", 3), "the first rule set changed: rewrite RULES['readiness']"
    fan_ = fan(days, r_, sim)

    # --- disposition: the calculator's own compute() on Odean's counts, as it printed them
    o = run["odean"]
    txt = printed["disposition_tool"]["results"]
    assert printed["disposition_tool"]["inputs"] == ODEAN
    shown = {"pgr": f"{o['pgr']:.4f}", "plr": f"{o['plr']:.4f}", "ratio": f"{o['ratio']:.2f}", "diff": f"{o['diff']:.4f}",
             "se": f"{o['se']:.4f}", "t": f"{o['t']:.2f}"}
    for k, v in shown.items():
        assert "\n" + v + "\n" in txt + "\n", ("disposition", k, v)
    half = lambda p, n: 1.96 * math.sqrt(p * (1 - p) / n)   # normal-approximation 95% band of a share
    odean = {**shown, "counts": ODEAN, "reading": o["reading"], "pgr_f": o["pgr"], "plr_f": o["plr"],
             "band_pgr_pp": f"{half(o['pgr'], o['gainsDen']) * 100:.2f}", "band_plr_pp": f"{half(o['plr'], o['lossesDen']) * 100:.2f}",
             "ci_pgr": [round(o["pgr"] - half(o["pgr"], o["gainsDen"]), 4), round(o["pgr"] + half(o["pgr"], o["gainsDen"]), 4)],
             "ci_plr": [round(o["plr"] - half(o["plr"], o["lossesDen"]), 4), round(o["plr"] + half(o["plr"], o["lossesDen"]), 4)]}

    # --- the $39 block: the test's summary on the same account
    report = {"method_version": rep["method_version"], "engine_commit": rep["_provenance"]["engine_repo_commit"],
              "n_trades": rep["n_trades"], "n_tested": rep["n_tested"],
              "rows": [{"id": h["id"], "habit": REPORT_NAMES.get(h["id"], h["name"]), "result": report_result(h),
                        "trades": h["dollars"]["n_trades"], "total": money(h["dollars"]["amount"]),
                        "why": report_why(h), "name_lower": NAMES_LOWER[h["id"]]} for h in rep["habits"]]}
    assert report["n_trades"] == st["n"]

    # --- EURUSD, for scale (calc_eurusd.py's month)
    ser = fx["series"]
    assert fx["low"] == min(ser) and fx["high"] == max(ser) and fx["range_pips"] == round((max(ser) - min(ser)) * 10000)
    assert fx["first"] == ser[0] and fx["last"] == ser[-1]
    eurusd = {k: fx[k] for k in ("month", "month_label", "days", "low", "high", "range_pips", "avg_daily_move_pips",
                                 "series", "file_last_date", "lot_fact", "first", "last")}
    eurusd["direction"] = "fell" if fx["last"] < fx["first"] else "rose" if fx["last"] > fx["first"] else "ended where it began"

    closes = [c["ts"] for c in run["dd"]["curve"]]
    k = 8
    pnl = [t["pnl"] for t in trades]   # the engine's (close-time) order, as the tools read them
    out = {
        "about": "Generated by checks/real_data/make_tool_real.py from real public data; do not edit by hand.",
        "inputs": {
            "checks/real_data/raw/real-trades.csv": {"sha256": csv_sha, "from": "Stock Transactions Dataset, Mendeley Data V1, "
                                                 "doi:10.17632/k4tnk2nggv.1, CC BY 4.0", "raw_sha256": MENDELEY_SHA,
                                                 "kept": "not committed (real tickers): checks/real_data/fetch.py downloads the xlsx and rebuilds it"},
            "checks/real_data/real-trades.coded.csv": {"sha256": sha256(CODED), "from": "checks/real_data/raw/real-trades.csv, "
                                                       "ticker names replaced with codes (make_coded_csv.py); shipped "
                                                       "behind the tools' “Try real public data” button"},
            "checks/real_data/tools-printed.json": {"sha256": sha256(PRINTED), "printed_by": "the free tool pages at "
                                                    "origin/main 696c324 (run_tools.cjs)"},
            "checks/real_data/eurusd.json": {"sha256": sha256(EURUSD), "raw_sha256": fx["raw_sha256"],
                                             "from": "Federal Reserve Board H.10, dat00_eu.htm (public domain)"},
            "site/config/tool_real.report.json": {"sha256": sha256(REPORT), "engine_commit": report["engine_commit"],
                                                  "method_version": report["method_version"]},
            "site/config/challenge_rules.json": {"sha256": sha256(RULES_LIB), "entry": preset["id"]},
            "odean-1998": {"sha256_of_pdf_read": "022ccc2eb81788489af6908ba139dd7dbe9ccd737bb70551d9b66c35b1e68c2d",
                           "note": "Table I counts typed in; the PDF is not stored"},
        },
        "scripts": {f"checks/real_data/{n}": sha256(os.path.join(HERE, n)) for n in SCRIPTS},
        "credits": CREDITS, "rules": RULES,
        "account": {"fills": len(res["result"]["executions"]),
                    "trades": st["n"], "first_close": dt.datetime.fromtimestamp(closes[0] / 1000, dt.UTC).date().isoformat(),
                    "last_close": dt.datetime.fromtimestamp(closes[-1] / 1000, dt.UTC).date().isoformat(),
                    "period": f"{months_of(closes[0])} to {months_of(closes[-1])}", "open_positions": open_n,
                    "realised_only": f"The {open_n} positions still open at the end of the file are left out; the "
                                     "results cover realised trades only."},
        "trade_stats": {**mine, "longest_losing_streak": streak, "hold_ratio": rows["Losing hold ÷ winning hold"]},
        "curve": [round(v, 2) for v in curve], "curve_close_month": [months_of(c) for c in closes],
        "curve_peak_trade": deep["peak_i"] + 1, "curve_trough_trade": deep["trough_i"] + 1,
        "curve_high": round(high, 2), "curve_low": round(min(curve), 2),
        "slices": [round(sum(pnl[i * k:(i + 1) * k]), 2) for i in range(len(pnl) // k)],
        "drawdown": dd, "heatmap": heat, "readiness": readiness, "fan": fan_, "odean": odean, "eurusd": eurusd,
        "report": report,
    }
    assert out["curve_low"] == round(curve[deep["trough_i"]], 2)
    return out


def dump(d):
    return json.dumps(d, ensure_ascii=False, indent=1, sort_keys=True) + "\n"


def main(argv):
    new = assemble(range_=True)
    text = dump(new)
    if "--check" in argv:
        cur = open(OUT, encoding="utf-8").read() if os.path.exists(OUT) else ""
        if cur != text:
            sys.exit("site/config/tool_real.json differs from a fresh run: rerun make_tool_real.py")
        print("tool_real.json: matches a fresh run")
        return
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.write(text)
    print("wrote", os.path.relpath(OUT, REPO), len(text), "bytes, sha256", hashlib.sha256(text.encode()).hexdigest()[:16])


if __name__ == "__main__":
    main(sys.argv[1:])
