#!/usr/bin/env python3
"""make_selloff_data.py: site/data/selloff-2026-11-05.json from the analysis outputs (6 Nov 2026).

Keeps ONLY aggregate fields (counts, sums, shares). It refuses to write if any key or value looks like a wallet address
(0x followed by 40 hex digits, or any 0x hex string of 8+ digits other than the dataset's placeholder address), and
it checks every hash it records against the file it came from:

  * ANALYSIS-PLAN.md against ANALYSIS-PLAN.sha256 (the plan was logged and hashed before any data row was read);
  * SUMMARY.json, S3_exact.json and the 31 per-day files against out/OUTPUT.sha256;
  * the 31 input-file hashes are copied from RUN-LOG.txt (the Parquet files themselves are not in this repository).

Usage: python3 checks/selloff/make_selloff_data.py [--src /home/claude/proj/selloff] [--out site/data/selloff-2026-11-05.json]
Cells under 10 wallets are suppressed (ANALYSIS-PLAN.md section 7): an hour of 5 Nov with fewer than 10 force-closed wallets
is written with null value and null wallets.
"""
import argparse
import hashlib
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
EVENT_DAY = "2026-11-05"
PLACEHOLDER = "0x" + "e" * 40          # the dataset's placeholder address, not a wallet
ADDR = re.compile(r"0x[0-9a-fA-F]{8,}")
MIN_CELL = 10
DAY_FIELDS = ("day", "perp_trades", "active_wallets", "liq_wallets", "liq_notional", "liq_notional_long", "liq_events",
              "hip3_liq_wallets", "hip3_liq_notional", "hip3_active_wallets", "s2_denominator", "s2_retrade_15", "s2_retrade_60")


def sha(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def addresses_in(obj):
    """Every string in the structure (keys and values) that looks like a wallet address."""
    found = []
    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                walk(k); walk(v)
        elif isinstance(x, (list, tuple)):
            for v in x:
                walk(v)
        elif isinstance(x, str):
            found.extend(m for m in ADDR.findall(x) if m.lower() != PLACEHOLDER)
    walk(obj)
    return found


def published_summary_text(text):
    """SUMMARY.json as published: the hourly cell(s) with fewer than MIN_CELL wallets are removed (plan section 7). The run's own file keeps them;
    both hashes are recorded (provenance.published_files) and the pack README says so."""
    obj = json.loads(text)
    obj["S3_hours_E"] = [row for row in obj.get("S3_hours_E", []) if row[2] >= MIN_CELL]
    return json.dumps(obj, indent=1, ensure_ascii=False) + "\n"


def published_run_log_text(text):
    """RUN-LOG.txt as published: the one cleanup line that names unrelated work is removed (it is not part of this study)."""
    return "".join(line for line in text.splitlines(True) if "Reddit" not in line)


def build(src):
    out_dir = os.path.join(src, "out")
    plan_sha = open(os.path.join(src, "ANALYSIS-PLAN.sha256")).read().split()[0]
    if sha(os.path.join(src, "ANALYSIS-PLAN.md")) != plan_sha:
        sys.exit("ANALYSIS-PLAN.md does not match ANALYSIS-PLAN.sha256")
    outputs = {}
    for line in open(os.path.join(out_dir, "OUTPUT.sha256")):
        h, name = line.split()
        name = name.replace("out/", "", 1)
        if sha(os.path.join(out_dir, name)) != h:
            sys.exit(f"{name} does not match out/OUTPUT.sha256")
        outputs[name] = h
    inputs, notes = [], []
    run_log_raw = open(os.path.join(src, "RUN-LOG.txt")).read()
    for line in published_run_log_text(run_log_raw).splitlines():
        p = line.split()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", p[0]) and len(p) == 3 and re.fullmatch(r"[0-9a-f]{64}", p[1]):
            inputs.append({"day": p[0], "sha256": p[1], "bytes": int(p[2])})
        else:
            notes.append(line.strip())
    summary = load(os.path.join(out_dir, "SUMMARY.json"))
    s3 = load(os.path.join(out_dir, "S3_exact.json"))
    days = []
    for name in sorted(n for n in os.listdir(out_dir) if re.fullmatch(r"\d{4}-\d{2}-\d{2}\.json", n)):
        r = load(os.path.join(out_dir, name))
        days.append({k: r[k] for k in DAY_FIELDS})
        if r["day"] == EVENT_DAY:
            event_raw = r
    if [d["day"] for d in days] != [i["day"] for i in inputs] or len(days) != 31:
        sys.exit("the per-day outputs and the logged input hashes are not the same 31 days")
    hourly = []
    for hour, value, wallets in event_raw["hourly_liq_notional"]:
        hourly.append({"hour_utc": hour, "value": None if wallets < MIN_CELL else value, "wallets": None if wallets < MIN_CELL else wallets,
                       "suppressed": wallets < MIN_CELL})
    summary_raw = open(os.path.join(out_dir, "SUMMARY.json"), encoding="utf-8").read()
    pub = published_summary_text(summary_raw)
    published = {
        "SUMMARY.json": {"sha256": hashlib.sha256(pub.encode("utf-8")).hexdigest(), "run_sha256": outputs["SUMMARY.json"],
                         "edit": "the hourly cell for hour 07 UTC (fewer than 10 wallets) is removed; nothing else changes"},
        "RUN-LOG.txt": {"sha256": hashlib.sha256(published_run_log_text(run_log_raw).encode("utf-8")).hexdigest(),
                        "edit": "one cleanup line that named unrelated work is removed; every input hash and every timestamp is kept"}}
    summary = {k: v for k, v in summary.items() if k not in ("daily", "S3_hours_E")}
    code = {n: sha(os.path.join(src, n)) for n in ("run_day.py", "summarize.py", "s3_exact.py")}
    data = {
        "_about": "Aggregate counts only, made by checks/selloff/make_selloff_data.py from the outputs of the pre-stated analysis "
                  "(checks/selloff/zenodo/ANALYSIS-PLAN.md). No wallet address is in this file: the script refuses to write one. "
                  "Cells under 10 wallets are suppressed. site/selloff.py recomputes every statistic from `days` and fails the build "
                  "if it differs from `summary`; tests/test_selloff.py recomputes them a second way.",
        "event_day": EVENT_DAY,
        "baseline": {"first": "2026-10-06", "last": "2026-11-04", "days": 30},
        "source": {"name": "Ironflow (ironflow.sh), Hyperliquid trades and liquidations", "licence": "CC BY 4.0",
                   "licence_url": "https://creativecommons.org/licenses/by/4.0/",
                   "trades_url": "https://huggingface.co/datasets/ironflow/hyperliquid-trades",
                   "liquidations_url": "https://huggingface.co/datasets/ironflow/hyperliquid-liquidations",
                   "read_on": "2026-11-06"},
        "provenance": {"analysis_plan": {"file": "ANALYSIS-PLAN.md", "sha256": plan_sha, "logged_utc": "2026-11-06T19:44:00Z"},
                       "inputs": inputs, "output_sha256": outputs, "code_sha256": code, "run_log": notes,
                       "published_files": published},
        "days": days,
        "event": {"hourly": hourly, "s3_exact": s3},
        "summary": summary,
    }
    bad = addresses_in(data)
    if bad:
        sys.exit(f"refusing to write: {len(bad)} string(s) look like wallet addresses")
    return data


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/home/claude/proj/selloff")
    ap.add_argument("--out", default=os.path.join(REPO, "site", "data", "selloff-2026-11-05.json"))
    a = ap.parse_args(argv)
    data = build(a.src)
    os.makedirs(os.path.dirname(a.out), exist_ok=True)
    with open(a.out, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print(f"wrote {os.path.relpath(a.out, REPO)}: {len(data['days'])} days, {len(data['provenance']['inputs'])} input hashes")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
