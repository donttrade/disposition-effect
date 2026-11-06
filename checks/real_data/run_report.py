#!/usr/bin/env python3
"""The donttrade test's own engine on the real public-data account -> site/config/tool_real.report.json.

A PRIVATE-REPO STEP, run by hand (the public repo never runs the paid engine, as with
tests/fixtures/paid/make_sample_report.py --report):
  1. checks/real_data/raw/real-trades.csv parsed by this repo's reference engine (tests/reference/engine_ref.py,
     the Python mirror of the browser engine);
  2. engine_ref.strip_rows(trades, salt) -> the stripped rows, the only data the paid test ever sends;
  3. the paid engine, src/core/habits.mjs analyse(), from the private repo at the commit whose METHOD_VERSION equals
     site/static/js/paid/wording.js (the build refuses the JSON otherwise).
Both repos are read only: Python runs with -B, node writes nothing.

    DT_PRIVATE_REPO=../dt2-private PYTHONDONTWRITEBYTECODE=1 python3 -B checks/real_data/run_report.py
"""
import hashlib
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
PRIVATE = os.environ.get("DT_PRIVATE_REPO", os.path.join(REPO, "..", "dt2-private"))
CSV = os.path.join(HERE, "raw", "real-trades.csv")
OUT = os.path.join(REPO, "site", "config", "tool_real.report.json")
SALT = "REALDATA"
sys.path.insert(0, os.path.join(REPO, "tests", "reference"))
import engine_ref as E  # noqa: E402


def git_head(repo):
    return subprocess.run(["git", "-C", repo, "rev-parse", "--short", "HEAD"], capture_output=True, text=True).stdout.strip()


def site_method():
    with open(os.path.join(REPO, "site", "static", "js", "paid", "wording.js"), encoding="utf-8") as f:
        return re.search(r"^export const METHOD_VERSION = '([^']+)';$", f.read(), re.M).group(1)


def main():
    data = open(CSV, "rb").read()
    res = E.run_fixture(data)
    assert "result" in res, res
    rows = E.strip_rows(res["result"]["trades"], SALT)["rows"]
    js = ("import { analyse, METHOD_VERSION } from '" + os.path.join(os.path.abspath(PRIVATE), "src/core/habits.mjs") + "';"
          "let s=''; process.stdin.on('data', (d) => { s += d; });"
          "process.stdin.on('end', () => { const r = analyse({ rows: JSON.parse(s), currency: 'USD', pgr_plr: null }, 'realdata');"
          " process.stdout.write(JSON.stringify(r)); });")
    r = subprocess.run(["node", "--input-type=module", "-e", js], cwd=HERE, input=json.dumps(rows),
                       capture_output=True, text=True, check=True)
    rep = json.loads(r.stdout)
    if rep.get("method_version") != site_method():
        sys.exit(f"the private engine is method {rep.get('method_version')}, the site accepts {site_method()}")
    rep["_provenance"] = {"csv_sha256": hashlib.sha256(data).hexdigest(), "site_repo_commit": git_head(REPO),
                          "engine_repo_commit": git_head(PRIVATE), "salt": SALT,
                          "engine_ref": "tests/reference/engine_ref.py", "engine": "src/core/habits.mjs analyse()"}
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        json.dump(rep, f, indent=1, sort_keys=True, ensure_ascii=False)
        f.write("\n")
    print(rep["method_version"], rep["n_trades"], "trades; tested", rep["n_tested"], "->", os.path.relpath(OUT, REPO))


if __name__ == "__main__":
    main()
