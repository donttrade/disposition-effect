#!/usr/bin/env python3
"""Batch F2: builds partner/parity/dt1_golden.json, the proof that partner/dt1_features.py gives the paid
engine's numbers.

For every window in the corpus (at least 300), the strip is done ONCE here in Python. Then:
  * the private engine habits.mjs analyse(req, 'parity', {nPerm: 1}) runs on the rows (node, read-only);
  * the private Python mirror habits_ref.analyse runs on the same rows (bytecode writing off);
  * dt1_features.features_from_rows runs on them.
For every habit, n_a, n_b and dollars.n_trades must agree exactly, and measure_a, measure_b and effect to
1e-12 relative. The six F values derived from the engine's output must equal dt1_features' F values.
Only then is the golden file (inputs + expected F1-F6 + the engine's counts) written. It ships in the public
repo, so tests/test_prediction.py can check the public script without the private engine.

Usage (Claude Code, repo root; the private repo is read, never written):
  python3 -B tests/parity/build_dt1_golden.py [--private ../delivery-39-private] [--write]
Without --write it only checks.
"""
import argparse
import hashlib
import json
import math
import os
import random
import subprocess
import sys
import tempfile
from decimal import Decimal

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "partner"))
import dt1_features as F  # noqa: E402

GOLDEN = os.path.join(REPO, "partner", "parity", "dt1_golden.json")
SEED = 20261030
REL = 1e-12
T0 = 1_717_200_000 - (1_717_200_000 % 86400)    # a UTC midnight


# ------------------------------------------------------------------ corpus

def rand_window(rng, kind):
    """Raw trades for one account (30-40 of them, so merging still leaves >= 30)."""
    n_sym = 1 if kind == "one_symbol" else rng.randint(2, 5)
    syms = ["S%d" % k for k in range(n_sym)]
    p_loss = {"no_winners": 1.0, "no_losers": 0.0}.get(kind, rng.uniform(0.3, 0.7))
    reentry = rng.uniform(0, 0.6)
    t = T0 + rng.randint(0, 6) * 86400 + rng.randint(6, 10) * 3600 + rng.randint(0, 59) * 60
    out = []
    last_loss_close = None
    n = rng.randint(34, 40) + (16 if kind == "merges" else 0)
    while len(out) < n:
        sym = rng.choice(syms)
        d = rng.choice((1, -1))
        if kind == "tie900" and last_loss_close is not None and rng.random() < 0.5:
            op = last_loss_close + rng.choice((899, 900, 901, 960))
        elif last_loss_close is not None and rng.random() < reentry:
            op = last_loss_close + rng.randint(0, 1200)
        else:
            op = t + rng.randint(600, 4 * 3600)
        hold = rng.choice((0, 30, rng.randint(60, 7200), rng.randint(43200, 200000))) if rng.random() < 0.2 \
            else rng.randint(60, 5400)
        r = rng.random()
        if r < 0.05:
            pnl = Decimal(0)
        else:
            mag = Decimal(rng.randint(1, 50000)) / Decimal(100)
            if rng.random() < 0.08:
                mag *= 5
            pnl = -mag if rng.random() < p_loss else mag
        size = Decimal(rng.choice((1, 1, 2, 3, 5, 10))) * Decimal(rng.choice(("0.01", "0.1", "1")))
        if rng.random() < 0.15:
            size *= 2
        out.append({"open_s": op, "close_s": op + hold, "symbol": sym, "direction": d, "size": size, "pnl": pnl})
        if kind == "merges" and rng.random() < 0.3:
            # a partial fill: the same symbol, direction and open minute
            op2 = op - (op % 60) + rng.randint(0, 59)
            out.append({"open_s": op2, "close_s": op2 + rng.randint(30, 3000), "symbol": sym, "direction": d,
                        "size": size, "pnl": -pnl if rng.random() < 0.3 else pnl})
        if pnl < 0:
            last_loss_close = op + hold
        t = max(t, op)
    if kind == "near_dates_only":
        day = (T0 // 86400 + 3) * 86400
        out[5] = {"open_s": day, "close_s": day + 86400, "symbol": syms[0], "direction": 1, "size": Decimal(1),
                  "pnl": Decimal("-12.5")}
    return out


def private_fixture_windows(private):
    """Windows of 30 merged rows from the engine's own test fixtures that carry times (all of them do)."""
    fx = os.path.join(private, "tests", "fixtures")
    names = ["planted.json", "planted_revenge.json", "random.json", "too_few.json"]
    for sub in ("stats", "stats-r2"):
        d = os.path.join(fx, sub)
        if os.path.isdir(d):
            names += [os.path.join(sub, x) for x in sorted(os.listdir(d)) if x.endswith(".json")
                      and not x.startswith("architect")]
    out = []
    for name in names:
        with open(os.path.join(fx, name), encoding="utf-8") as fh:
            req = json.load(fh)
        rows = req.get("rows") or []
        if not rows or F.is_dates_only(rows):
            continue
        m = F.merge_rows(rows)
        items, by_close, _bo, _c, _s = F.prepare(m)
        for start in range(0, max(1, len(by_close) - 29), 30):
            if start + 30 > len(by_close):
                break
            keep = sorted(t["i"] for t in by_close[start:start + 30])
            win = [m[i] for i in keep]
            if not F.is_dates_only(win):
                out.append(("fixture:" + name + ":" + str(start), [dict(r) for r in win]))
            if len(out) > 400:
                return out
    return out


def build_corpus(private):
    rng = random.Random(SEED)
    wins = []
    kinds = ["random"] * 200 + ["merges"] * 40 + ["tie900"] * 40 + ["no_winners"] * 10 + ["no_losers"] * 10 + \
        ["one_symbol"] * 20 + ["near_dates_only"] * 10
    for k, kind in enumerate(kinds):
        raw = rand_window(rng, kind)
        w = F.account_window(raw)
        if w["status"] != "ok":
            continue
        wins.append(("gen:%s:%d" % (kind, k), w["rows"]))
    # rows fed to the engine with duplicate (s, d, o) keys, so merge_rows itself is compared too
    for k in range(20):
        raw = rand_window(rng, "random")
        w = F.account_window(raw)
        if w["status"] != "ok":
            continue
        rows = [dict(r) for r in w["rows"]]
        dup = dict(rows[3])
        dup["p"] = round(dup["p"] / 3, 2)
        dup["h"] += 120
        rows.append(dup)
        wins.append(("gen:dupkey:%d" % k, rows))
    wins += private_fixture_windows(private)
    return [{"id": i, "rows": r} for i, r in wins]


# ------------------------------------------------------------------ comparison

def features_from_engine(h):
    """F1-F6 from the engine's habit numbers (the definitions of plan section 2.5)."""
    rv, tl, su, ov, hg = h["revenge"], h["tilt"], h["size_up"], h["oversized_loss"], h["hold_gap"]

    def lg(x):
        return math.log(x) if (x is not None and x > 0) else None
    return {
        "reentry_share": rv["n_a"] / (rv["n_a"] + rv["n_b"]) if rv["n_a"] + rv["n_b"] else None,
        "streak_share": tl["n_a"] / (tl["n_a"] + tl["n_b"]) if tl["n_a"] + tl["n_b"] else None,
        "size_after_loss_ratio": lg(su["effect"]) if (su["n_a"] and su["n_b"] and su["measure_a"]
                                                      and su["measure_b"]) else None,
        "size_after_loss_share": su["dollars_n_trades"] / su["n_a"] if su["n_a"] else None,
        "large_loss_share": ov["measure_a"] if ov["n_b"] else None,
        "hold_gap_ratio": lg(hg["effect"]) if (hg["n_a"] and hg["n_b"] and hg["measure_a"]
                                               and hg["measure_b"]) else None,
    }


def close(a, b):
    if a is None or b is None:
        return a is None and b is None
    if a == b:
        return True
    return abs(a - b) <= REL * max(abs(a), abs(b))


def python_mirror(private, rows):
    os.environ.setdefault("DT_PUBLIC_REPO", REPO)
    sys.path.insert(0, os.path.join(private, "reference"))
    import habits_ref as H  # noqa: E402
    rep = H.analyse({"rows": rows, "currency": "USD"}, "parity", n_perm=1)
    return {h["id"]: {"n_a": h["n_a"], "n_b": h["n_b"], "measure_a": h["measure_a"], "measure_b": h["measure_b"],
                      "effect": h["effect"],
                      "dollars_n_trades": None if h["dollars"] is None else h["dollars"]["n_trades"]}
            for h in rep["habits"]}


def compare(private, corpus):
    engine = os.path.join(private, "src", "core", "habits.mjs")
    with tempfile.TemporaryDirectory() as td:
        cp = os.path.join(td, "corpus.json")
        with open(cp, "w", encoding="utf-8") as fh:
            json.dump({"windows": corpus}, fh)
        res = subprocess.run(["node", os.path.join(HERE, "dt1_parity.mjs"), engine, cp], capture_output=True,
                             text=True, check=True)
    js = json.loads(res.stdout)
    if js["method_version"] != F.ENGINE_METHOD:
        raise SystemExit("engine method %s, features copied from %s" % (js["method_version"], F.ENGINE_METHOD))
    bad = []
    golden = []
    for w, e in zip(corpus, js["windows"]):
        assert w["id"] == e["id"]
        f, counts = F.features_from_rows(w["rows"])
        py = python_mirror(private, w["rows"])
        for hid, h in e["habits"].items():
            for k in ("n_a", "n_b", "dollars_n_trades"):
                if h[k] != py[hid][k]:
                    bad.append((w["id"], hid, k, "js vs python mirror"))
            for k in ("measure_a", "measure_b", "effect"):
                if not close(h[k], py[hid][k]):
                    bad.append((w["id"], hid, k, "js vs python mirror"))
        ours = {"revenge": counts["revenge"], "tilt": counts["tilt"]}
        for hid in ours:
            if (e["habits"][hid]["n_a"], e["habits"][hid]["n_b"]) != ours[hid]:
                bad.append((w["id"], hid, "groups", "js vs dt1_features"))
        if e["n_trades"] != counts["n_trades"]:
            bad.append((w["id"], "n_trades", "", "js vs dt1_features"))
        fe = features_from_engine(e["habits"])
        for k in F.FEATURES:
            if not close(fe[k], f[k]):
                bad.append((w["id"], k, (fe[k], f[k]), "F value"))
        golden.append({"id": w["id"], "rows": w["rows"], "expected": f, "engine": e["habits"],
                       "n_trades": e["n_trades"]})
    return bad, golden, js["method_version"]


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--private", default=os.path.join(REPO, "..", "delivery-39-private"))
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    corpus = build_corpus(a.private)
    bad, golden, method = compare(a.private, corpus)
    n_undef = {k: sum(1 for g in golden if g["expected"][k] is None) for k in F.FEATURES}
    sys.stdout.write("windows %d, disagreements %d\nundefined per feature %s\n" % (len(golden), len(bad), n_undef))
    for b in bad[:20]:
        sys.stdout.write("  %r\n" % (b,))
    if bad or len(golden) < 300:
        return 1
    if a.write:
        doc = {"what": "DT-1 parity golden file: engine rows of 30-trade windows, the F1-F6 values "
                       "partner/dt1_features.py must give, and the paid engine's (habits.mjs) habit numbers.",
               "engine_method": method,
               "engine_sha256": sha(os.path.join(a.private, "src", "core", "habits.mjs")),
               "habits_ref_sha256": sha(os.path.join(a.private, "reference", "habits_ref.py")),
               "dt1_features_sha256": sha(os.path.join(REPO, "partner", "dt1_features.py")),
               "tolerance": {"counts": "exact", "measures": REL},
               "windows": golden}
        with open(GOLDEN, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=0, sort_keys=True)
            fh.write("\n")
        sys.stdout.write("wrote %s (%s)\n" % (os.path.relpath(GOLDEN, REPO), sha(GOLDEN)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
