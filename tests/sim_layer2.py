#!/usr/bin/env python3
"""Batch S3: Layer 2 synthetic study, end to end through the real script (plan section 5.1).

Every replication writes firm-format trades.csv and accounts.csv with partner/make_fixture_prediction.py,
reads them with prediction_test.read_inputs (the firm's parsing and refusals) and runs the script's own
classify -> analyse_full -> verdict. The robustness block is skipped in replications (it does not enter a
verdict); a few replications per world are also run through the command line, and their VERDICT line must
equal the in-process verdict.

  W-L  planted logistic (AUC of z = 0.70)  recovery and CI coverage of DT-1's population AUC
  W-M  mechanical breaches                  the same, on the realistic path
  W-0  null                                 H1 false-pass rate (limit 3.6%), AUC about 0.50
  W-C  confounded through volatility        H2 false-pass rate (the plan revises B0 if above 5%)
  W-K  look-ahead canary                    a whole-file size normaliser (mutant) moves the AUC; the real
                                            within-W script does not
  W-E  exclusions                           the E1-E7 counts equal the generator's ground truth exactly

The population AUC of DT-1 for W-L and W-M comes from a POP_N-account run of the same world, computed in
process by pop_auc() (the same feature, label and score functions; equivalence with classify() is checked
on 3,000 accounts first). It is cached in tests/fixtures/generated/ (synthetic, git-ignored).

Usage (Claude Code, repo root; about an hour on 2 cores):
  python3 -B tests/sim_layer2.py [--quick] [--procs 2] > research/prediction-study/S3-raw.md
"""
import argparse
import json
import math
import multiprocessing
import os
import random
import subprocess
import sys
import tempfile
import time
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "partner"))
import dt1_features as F  # noqa: E402
import dt1_outcomes as O  # noqa: E402
import make_fixture_prediction as G  # noqa: E402
import prediction_metrics as M  # noqa: E402
import prediction_test as P  # noqa: E402

EXAMPLE = os.path.join(REPO, "partner", "PREREG-PREDICTION-EXAMPLE.md")
CACHE = os.path.join(REPO, "tests", "fixtures", "generated")
SEED = 20261101
WORLDS = {"L": 600, "M": 900, "0": 600, "C": 600, "K": 600}
REPS = {"L": 200, "M": 200, "0": 300, "C": 300, "K": 40}
QUICK_REPS = {"L": 12, "M": 12, "0": 12, "C": 12, "K": 6}
POP_N = 200000
CLI_CHECKS = 2


def prereg_text(n):
    return open(EXAMPLE, encoding="utf-8").read().replace("accounts_in_period = 600", "accounts_in_period = %d" % n)


def params_for(n):
    return P.parse_sealed_block(prereg_text(n).splitlines())


# ------------------------------------------------------------------ the look-ahead mutant

def mutant_account_window(trades, window=F.WINDOW):
    """dt1_features.account_window, except q is normalised by each symbol's median size over the WHOLE file
    (what strip.js does for the paid report), so trades after trade 30 leak into the features."""
    merged = F.merge_raw(trades)
    order = F.order_by_close(merged)
    if len(order) < window:
        return {"status": "short", "n_trades": len(order)}
    w = [merged[i] for i in sorted(order[:window])]
    rows = F.strip_window(w)
    sizes = {}
    for t in merged:
        sizes.setdefault(t["symbol"], []).append(float(t["size"]))
    med = {s: F.median(v) for s, v in sizes.items()}
    for r, t in zip(rows, w):
        m = med[t["symbol"]]
        r["q"] = F._half_away_3dp(float(t["size"]) / m) if m > 0 else 0.0
    t0 = merged[order[window - 1]]["close_s"]
    if F.is_dates_only(rows):
        return {"status": "dates_only", "t0": t0}
    f, counts = F.features_from_rows(rows)
    return {"status": "ok", "rows": rows, "features": f, "counts": counts, "t0": t0,
            "window": [merged[i] for i in order[:window]], "after": [merged[i] for i in order[window:]]}


# ------------------------------------------------------------------ one replication through the script

def replicate(job):
    world, n, seed, mutant, cli = job
    params, fp = params_for(n)
    with tempfile.TemporaryDirectory() as td:
        truth = G.write(td, world, n, seed)
        pp = os.path.join(td, "prereg.md")
        with open(pp, "w", encoding="utf-8") as fh:
            fh.write(prereg_text(n))
        order, accounts, trades = P.read_inputs(os.path.join(td, "trades.csv"), os.path.join(td, "accounts.csv"),
                                                params)
        real = F.account_window
        if mutant:
            F.account_window = mutant_account_window
        try:
            rec, recs = P.classify(order, accounts, trades, params, int(params["window_trades"]))
        finally:
            F.account_window = real
        res = P.analyse_full(params, recs, int(fp[:16], 16)) \
            if min(rec["breaches"], rec["survivors"]) >= int(params["min_each"]) else None
        v = P.verdict(params, rec, res)
        cli_v = None
        if cli:
            r = subprocess.run([sys.executable, "-I", os.path.join(REPO, "partner", "prediction_test.py"),
                                os.path.join(td, "trades.csv"), os.path.join(td, "accounts.csv"), pp],
                               capture_output=True, text=True)
            cli_v = [ln for ln in r.stdout.splitlines() if ln.startswith("VERDICT: ")][0][9:]
    out = {"world": world, "seed": seed, "mutant": mutant, "rec": rec, "verdict": v, "cli_verdict": cli_v,
           "truth": truth}
    if res is not None:
        out.update(auc=res["h1"]["auc"], lo=res["h1"]["lo"], hi=res["h1"]["hi"], h2=res["h2"]["passed"],
                   h1_pass=res["h1"]["lo"] > float(params["pass_lower"]),
                   d_auc=res["h2"]["delta"]["diff"] if res["h2"]["fit"] == "ok" else None)
    return out


# ------------------------------------------------------------------ population AUC

def _to_script(acc_rec, tl, row):
    trades = [{"open_s": t["open_s"], "close_s": t["close_s"], "symbol": t["symbol"],
               "direction": 1 if t["direction"] == "long" else -1, "size": Decimal("%.2f" % t["size"]),
               "pnl": Decimal(G.money(t["pnl"])), "row": 0} for t in tl]
    a = {"start": acc_rec["start"], "balance": Decimal(acc_rec["A"]), "daily": Decimal(G.money(0.05 * acc_rec["A"])),
         "max_loss": Decimal(G.money(0.10 * acc_rec["A"])), "drawdown": acc_rec["drawdown"], "stop": None,
         "outcome": acc_rec["outcome"], "outcome_time": acc_rec["ot"], "data_end": acc_rec["end"],
         "trader_key": None, "abuse": False, "bot": False, "row": row}
    return a, trades


def pop_chunk(job):
    """Features and labels for one chunk of a population (no DT-1 yet: percentiles need the whole population)."""
    world, start_i, n, seed = job
    rng = random.Random(seed)
    params, _ = params_for(1)
    out = []
    for i in range(n):
        start = G.START + rng.randint(0, G.PERIOD_DAYS * G.DAY - 8 * 3600)
        rec, tl = G.account(rng, world, start)
        a, trades = _to_script(rec, tl, start_i + i)
        ot = a["outcome_time"]
        if ot is not None:
            trades = [t for t in trades if t["close_s"] <= ot]
        w = F.account_window(trades, F.WINDOW)
        if w["status"] != "ok" or (ot is not None and ot <= w["t0"]):
            continue
        if F.n_defined(w["features"]) < F.MIN_FEATURES:
            continue
        y = O.firm_label(a, w["t0"], int(params["outcome_days"]))["o1"]
        if y is None:
            continue
        out.append((y, [w["features"][k] for k in F.FEATURES]))
    return out


def pop_auc(world, n, procs):
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "prediction-pop-%s-%d.json" % (world, n))
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    chunk = 5000
    jobs = [(world, k, min(chunk, n - k), SEED + 7_000_000 + 1000 * ord(world) + k // chunk)
            for k in range(0, n, chunk)]
    with multiprocessing.Pool(procs) as pool:
        parts = pool.map(pop_chunk, jobs)
    rows = [r for p in parts for r in p]
    feats = [dict(zip(F.FEATURES, f)) for _y, f in rows]
    s = F.dt1_scores(feats)
    y = [r[0] for r in rows]
    res = {"world": world, "n": n, "eligible": len(rows), "breaches": sum(y), "auc": M.auc_only(s, y)}
    res["feature_auc"] = {}
    for k in F.FEATURES:
        idx = [i for i in range(len(rows)) if feats[i][k] is not None]
        res["feature_auc"][k] = M.auc_only([feats[i][k] for i in idx], [y[i] for i in idx])
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(res, fh)
    return res


def pop_matches_classify(world, n=3000):
    """pop_chunk's eligibility and labels equal prediction_test.classify's on the same accounts."""
    rng_seed = SEED + 99
    params, _ = params_for(n)
    rng = random.Random(rng_seed)
    order, accounts, trades = [], {}, {}
    for i in range(n):
        start = G.START + rng.randint(0, G.PERIOD_DAYS * G.DAY - 8 * 3600)
        rec, tl = G.account(rng, world, start)
        a, tr = _to_script(rec, tl, i)
        acc = "a%d" % i
        order.append(acc)
        accounts[acc] = a
        trades[acc] = tr
    _rec, recs = P.classify(order, accounts, trades, params, F.WINDOW)
    mine = pop_chunk((world, 0, n, rng_seed))
    return [(r["y"], [r["w"]["features"][k] for k in F.FEATURES]) for r in recs] == mine


# ------------------------------------------------------------------ the report

def summarise(world, runs, pop):
    ok = [r for r in runs if "auc" in r]
    R = len(ok)
    aucs = [r["auc"] for r in ok]
    mean = sum(aucs) / R
    sd = math.sqrt(sum((a - mean) ** 2 for a in aucs) / (R - 1)) if R > 1 else 0.0
    s = {"world": world, "reps": len(runs), "measured": R, "mean_auc": mean, "sd_auc": sd,
         "mean_lo": sum(r["lo"] for r in ok) / R, "mean_hi": sum(r["hi"] for r in ok) / R,
         "h1_pass": sum(r["h1_pass"] for r in ok) / R, "h2_pass": sum(r["h2"] for r in ok) / R,
         "verdict_pass": sum(r["verdict"].startswith("PASS") for r in runs) / len(runs),
         "breaches": sum(r["rec"]["breaches"] for r in runs) / len(runs),
         "survivors": sum(r["rec"]["survivors"] for r in runs) / len(runs),
         "cli_agree": all(r["cli_verdict"] in (None, r["verdict"]) for r in runs),
         "verdicts": {}}
    for r in runs:
        s["verdicts"][r["verdict"]] = s["verdicts"].get(r["verdict"], 0) + 1
    if pop is not None:
        s["pop_auc"] = pop["auc"]
        s["coverage"] = sum(r["lo"] <= pop["auc"] <= r["hi"] for r in ok) / R
        s["bias"] = mean - pop["auc"]
        s["bias_mcse"] = sd / math.sqrt(R)
    return s


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--procs", type=int, default=2)
    ap.add_argument("--pop", type=int, default=POP_N)
    a = ap.parse_args()
    t_start = time.time()
    reps = QUICK_REPS if a.quick else REPS
    pop_n = 20000 if a.quick else a.pop
    w = sys.stdout.write
    w("# S3 raw results (%s)\n\n" % ("quick" if a.quick else "full"))
    w("pop_chunk equals classify on 3,000 accounts: W-L %s, W-M %s\n\n" % (pop_matches_classify("L"),
                                                                       pop_matches_classify("M")))
    pops = {k: pop_auc(k, pop_n, a.procs) for k in ("L", "M")}
    for k, p in pops.items():
        w("population W-%s: %d accounts, %d eligible, %d breaches, DT-1 AUC %.4f; features %s\n" % (
            k, p["n"], p["eligible"], p["breaches"], p["auc"],
            ", ".join("%s %.3f" % (f, v) for f, v in p["feature_auc"].items())))
    w("\n")
    jobs = []
    for i, world in enumerate(("L", "M", "0", "C", "K")):
        for r in range(reps[world]):
            seed = SEED + 100000 * (i + 1) + r
            jobs.append((world, WORLDS[world], seed, False, r < CLI_CHECKS))
            if world == "K":
                jobs.append((world, WORLDS[world], seed, True, False))
    jobs.append(("E", 1000, SEED + 999, False, True))
    with multiprocessing.Pool(a.procs) as pool:
        runs = pool.map(replicate, jobs, chunksize=1)
    summ = []
    for world in ("L", "M", "0", "C"):
        summ.append(summarise(world, [r for r in runs if r["world"] == world], pops.get(world)))
    summ.append(summarise("K", [r for r in runs if r["world"] == "K" and not r["mutant"]], None))
    summ.append(summarise("K-mutant", [r for r in runs if r["world"] == "K" and r["mutant"]], None))
    for s in summ:
        w("%s\n" % json.dumps(s, sort_keys=True))
    e = [r for r in runs if r["world"] == "E"][0]
    rec = e["rec"]
    match = all(rec[k] == e["truth"][k] for k in e["truth"] if k in rec)
    w("\nW-E reconciliation %s\nW-E truth %s\nW-E exact match: %s; CLI verdict agrees: %s\n" % (
        json.dumps(rec, sort_keys=True), json.dumps(e["truth"], sort_keys=True), match,
        e["cli_verdict"] == e["verdict"]))
    w("\nseeds: replications SEED %d + 100000 * world index + replication; populations SEED + 7000000 + "
      "1000 * ord(world) + chunk\nrun time %.0f s\n" % (SEED, time.time() - t_start))
    return 0


if __name__ == "__main__":
    sys.exit(main())
