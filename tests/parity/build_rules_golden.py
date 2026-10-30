#!/usr/bin/env python3
"""Batch F3: builds partner/parity/rules_golden.json, the proof that partner/dt1_outcomes.replay() gives the
Challenge Readiness engine's sequence-mode result (prop-sim-core.js simulate, and its Python reference
readiness_ref.simulate) on at least 100 post-T0 sequences: the outcome, the rule broken, the day and the trade.

Usage (Claude Code, repo root; the readiness checkout is read, never written):
  python3 -B tests/parity/build_rules_golden.py [--readiness ../readiness] [--write]
"""
import argparse
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, os.path.join(REPO, "partner"))
import dt1_outcomes as O  # noqa: E402

GOLDEN = os.path.join(REPO, "partner", "parity", "rules_golden.json")
SEED = 20261031
TARGET_NONE = 1e15     # R* has no profit target: one no account reaches


def corpus():
    rng = random.Random(SEED)
    seqs = []
    for k in range(160):
        size = rng.choice((1.0, 5000.0, 25000.0, 100000.0))
        dd = ("static", "trailing_eod", "trailing_trade")[k % 3]
        n_days = rng.randint(1, 30)
        vol = size * rng.uniform(0.002, 0.03)
        drift = rng.uniform(-0.3, 0.2) * vol
        days = []
        for _ in range(n_days):
            n = rng.randint(1, 12)
            days.append([round(rng.gauss(drift, vol), 2 if size > 1 else 6) for _ in range(n)])
        if k % 17 == 0:   # an exact-boundary loss: equity lands exactly on the daily limit
            days[0] = [-0.05 * size]
        if k % 19 == 0:   # exactly on the max-loss floor across two days
            days[:2] = [[-0.04 * size], [-0.06 * size]]
        daily = None if k % 11 == 0 else 0.05 * size
        stop = 0.0 if (dd != "static" and k % 4 == 0) else None
        rules = {"target": TARGET_NONE, "max_loss": 0.10 * size, "daily_loss": daily, "time_limit": None,
                 "drawdown": dd, "trail_stop_at": stop}
        seqs.append({"id": "seq:%d" % k, "days": days, "rules": rules})
    return seqs


def run_js(readiness, seqs):
    core = os.path.join(readiness, "site", "static", "js", "tools", "prop-sim-core.js")
    with tempfile.TemporaryDirectory() as td:
        p = os.path.join(td, "c.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"sequences": seqs}, fh)
        res = subprocess.run(["node", os.path.join(HERE, "rules_parity.mjs"), core, p], capture_output=True,
                             text=True, check=True)
    return json.loads(res.stdout)


def run_ref(readiness, seqs):
    sys.path.insert(0, os.path.join(readiness, "tests", "reference"))
    import readiness_ref as R  # noqa: E402
    out = []
    for s in seqs:
        r = R.simulate({"mode": "sequence", "days": s["days"], "rules": s["rules"]})
        out.append({"id": s["id"], "outcome": r["outcome"], "why": r["why"], "day": r["day"], "bust_at": r["bust_at"]})
    return out


def ours(s):
    r = s["rules"]
    x = O.replay(s["days"], r["daily_loss"], r["max_loss"], r["drawdown"], r["trail_stop_at"])
    return {"id": s["id"], "outcome": x["outcome"], "why": x["why"], "day": x["day"],
            "bust_at": [[x["at"][0], x["at"][1], 1]] if x["at"] else []}


def check(readiness):
    seqs = corpus()
    js = run_js(readiness, seqs)
    ref = run_ref(readiness, seqs)
    bad = []
    for s, a, b in zip(seqs, js, ref):
        o = ours(s)
        for k in ("outcome", "why", "day", "bust_at"):
            if not (o[k] == a[k] == b[k]):
                bad.append((s["id"], k, o[k], a[k], b[k]))
    return seqs, js, bad


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--readiness", default=os.path.join(REPO, "..", "readiness"))
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args()
    seqs, js, bad = check(a.readiness)
    busts = sum(1 for x in js if x["outcome"] == "bust")
    sys.stdout.write("sequences %d (busts %d: daily %d, max %d), disagreements %d\n" % (
        len(seqs), busts, sum(1 for x in js if x["why"] == "daily"), sum(1 for x in js if x["why"] == "max"),
        len(bad)))
    for b in bad[:10]:
        sys.stdout.write("  %r\n" % (b,))
    if bad or len(seqs) < 100:
        return 1
    if a.write:
        doc = {"what": "R* labeller parity: post-T0 day sequences, rules, and prop-sim-core.js simulate's "
                       "sequence-mode result, which partner/dt1_outcomes.replay must reproduce.",
               "prop_sim_core_sha256": sha(os.path.join(a.readiness, "site", "static", "js", "tools",
                                                        "prop-sim-core.js")),
               "readiness_ref_sha256": sha(os.path.join(a.readiness, "tests", "reference", "readiness_ref.py")),
               "sequences": [dict(s, expected=e) for s, e in zip(seqs, js)]}
        with open(GOLDEN, "w", encoding="utf-8") as fh:
            json.dump(doc, fh, indent=0, sort_keys=True)
            fh.write("\n")
        sys.stdout.write("wrote %s\n" % os.path.relpath(GOLDEN, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main())
