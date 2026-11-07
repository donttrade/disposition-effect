#!/usr/bin/env python3
"""make_zenodo_pack.py: checks/selloff/zenodo/, the files the owner uploads to Zenodo (to mint the DOI) and that the site serves
byte for byte under /data/5-november-2026/ (site/selloff.py PACK_FILES).

Copies, unchanged, from the analysis folder: ANALYSIS-PLAN.md, ANALYSIS-PLAN.sha256, run_day.py, summarize.py, s3_exact.py,
out/S3_exact.json. Two copies carry one documented edit each (fix round 1): SUMMARY.json without its under-10-wallet hourly cell, and
RUN-LOG.txt without the one line that named unrelated work (both hashes are in the README and the data file). Writes README.txt and the daily CSV (from site/selloff.py). The scripts and
the plan are not edited: their hashes are in the data file and the plan's hash was recorded before any data row was read.
Usage: python3 checks/selloff/make_zenodo_pack.py [--src /home/claude/proj/selloff]
"""
import argparse
import hashlib
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(REPO, "site"))
import selloff as SO  # noqa: E402
sys.path.insert(0, HERE)
import make_selloff_data as MD  # noqa: E402

DEST = os.path.join(HERE, "zenodo")
COPY = {"ANALYSIS-PLAN.md": "ANALYSIS-PLAN.md", "ANALYSIS-PLAN.sha256": "ANALYSIS-PLAN.sha256", "RUN-LOG.txt": "RUN-LOG.txt",
        "run_day.py": "run_day.py", "summarize.py": "summarize.py", "s3_exact.py": "s3_exact.py",
        "out/SUMMARY.json": "SUMMARY.json", "out/S3_exact.json": "S3_exact.json"}

README = """5 November 2026: Hyperliquid forced closes against the 30 days before
==================================================================

What this is
  The files behind https://donttrade.ca/research/5-november-2026-sell-off/ : the analysis plan (written and hashed before the data was
  opened; the time is our own clock's, self-recorded, and the hash is published here and in ANALYSIS-PLAN.sha256, with a dated deposit
  pending), the code that made the counts, the run log (it holds the SHA-256 of each of the 31 daily input files), and the outputs.
  The daily counts as a CSV are in 5-november-2026-hyperliquid-daily.csv.

What is NOT here
  The input files themselves (Ironflow's daily Parquet files, about 150 MB each) and any wallet address. Every file here holds counts only.
  Dated note, 6 Nov 2026 23:24 UTC: after this study ran, Ironflow replaced 5 of the 31 daily trade files, so today's files from the
  dataset's main branch do not match the SHA-256 values in RUN-LOG.txt. Download the files this study read from dataset revision
  8e0c2f593fdbf324772db734747ccfce597f3b80 of ironflow/hyperliquid-trades:
  https://huggingface.co/datasets/ironflow/hyperliquid-trades/resolve/8e0c2f593fdbf324772db734747ccfce597f3b80/data/<YYYY-MM-DD>.parquet
  On the replaced files the builder-listed figures are unchanged; all-markets wallets become 18,815 for 5 Nov (published 18,813) and
  1,142 for 10 Oct (published 1,129). The published figures stay as the run made them.
  To re-run, download the same files from that revision, check each SHA-256 against RUN-LOG.txt, and run run_day.py, summarize.py and
  s3_exact.py. The scripts name the folders of the machine they were run on (/home/claude/...); change those paths first. The scripts and the plan are published
  unchanged, so that their hashes (in RUN-LOG.txt and on the study page) stay true.

Edits to two published copies (everything else is byte for byte what the run made)
  SUMMARY.json: the one hourly cell with fewer than 10 wallets (hour 07 UTC on 5 November) is removed, as the plan's section 7 says small
    cells are not published. SHA-256 of the file as the run made it: @SUMMARY_RUN@
    SHA-256 of the file published here: @SUMMARY_PUB@
  RUN-LOG.txt: one cleanup line that named unrelated work is removed. All 31 input hashes and every timestamp are kept.
    SHA-256 of the file published here: @RUNLOG_PUB@

How the numbers are made
  "Middle half" is the first to third quartile of the 30 daily values by the exclusive method (Python statistics.quantiles(n=4)). Excel's
  QUARTILE.INC and numpy's default method give slightly different ends. Medians and ranks are the same in every program.
  The plan's comparison is the median of all 30 days before, weekends included. The page also shows the median of the 22 weekdays
  among them (5 November was a Thursday); that comparison is not in the plan and is labelled so.

Order of events (UTC, 6 November 2026)
  19:44  ANALYSIS-PLAN.md logged; its SHA-256 is in ANALYSIS-PLAN.sha256
  19:44 to 19:50  the 31 daily files streamed, hashed, processed and deleted (RUN-LOG.txt)
  19:55  one extra step for measure S3, logged in RUN-LOG.txt with its reason

Data credit
  Data: Ironflow (ironflow.sh), Hyperliquid Trades (https://huggingface.co/datasets/ironflow/hyperliquid-trades) and Hyperliquid
  Liquidations (https://huggingface.co/datasets/ironflow/hyperliquid-liquidations), licensed under CC BY 4.0
  (https://creativecommons.org/licenses/by/4.0/). Changes made: aggregated into daily counts and sums; no trade rows and no wallet address
  are republished. Ironflow has not reviewed or endorsed this analysis.
  Market closes quoted on the study page: Nasdaq, S&P Dow Jones Indices and Cboe, via FRED (Federal Reserve Bank of St. Louis).

Licence of these files
  The counts and the text of the plan are released under CC BY 4.0, as adapted material of CC BY 4.0 data. The code is published as is.

Wallets, not people
  A wallet is a blockchain address. It is not a person: one person can hold several, and some wallets are bots or funds.
  Not investment advice.
"""


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def main(argv):
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="/home/claude/proj/selloff")
    a = ap.parse_args(argv)
    os.makedirs(DEST, exist_ok=True)
    for rel, name in COPY.items():
        shutil.copyfile(os.path.join(a.src, rel), os.path.join(DEST, name))
    run_summary = os.path.join(a.src, "out", "SUMMARY.json")
    with open(os.path.join(DEST, "SUMMARY.json"), "w", encoding="utf-8", newline="\n") as f:
        f.write(MD.published_summary_text(open(run_summary, encoding="utf-8").read()))
    with open(os.path.join(DEST, "RUN-LOG.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(MD.published_run_log_text(open(os.path.join(a.src, "RUN-LOG.txt"), encoding="utf-8").read()))
    readme = README.replace("@SUMMARY_RUN@", sha(run_summary)).replace("@SUMMARY_PUB@", sha(os.path.join(DEST, "SUMMARY.json"))) \
        .replace("@RUNLOG_PUB@", sha(os.path.join(DEST, "RUN-LOG.txt")))
    with open(os.path.join(DEST, "README.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(readme)
    with open(os.path.join(DEST, os.path.basename(SO.CSV_PATH)), "w", encoding="utf-8", newline="\n") as f:
        f.write(SO.csv_text())
    plan = open(os.path.join(DEST, "ANALYSIS-PLAN.sha256")).read().split()[0]
    assert plan == sha(os.path.join(DEST, "ANALYSIS-PLAN.md")), "plan hash"
    print("wrote", len(os.listdir(DEST)), "files to", os.path.relpath(DEST, REPO))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
