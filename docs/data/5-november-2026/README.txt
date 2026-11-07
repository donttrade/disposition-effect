5 November 2026: Hyperliquid forced closes against the 30 days before
==================================================================

What this is
  The files behind https://donttrade.ca/research/5-november-2026-sell-off/ : the analysis plan (written and hashed before the data was
  opened; the time is our own clock's, self-recorded, and the hash is published here and in ANALYSIS-PLAN.sha256, with a dated deposit
  pending), the code that made the counts, the run log (it holds the SHA-256 of each of the 31 daily input files), and the outputs.
  The daily counts as a CSV are in 5-november-2026-hyperliquid-daily.csv.

What is NOT here
  The input files themselves (Ironflow's daily Parquet files, about 150 MB each) and any wallet address. Every file here holds counts only.
  To re-run, download the same files from the dataset page, check each SHA-256 against RUN-LOG.txt, and run run_day.py, summarize.py and
  s3_exact.py. The scripts name the folders of the machine they were run on (/home/claude/...); change those paths first. The scripts and the plan are published
  unchanged, so that their hashes (in RUN-LOG.txt and on the study page) stay true.

Edits to two published copies (everything else is byte for byte what the run made)
  SUMMARY.json: the one hourly cell with fewer than 10 wallets (hour 07 UTC on 5 November) is removed, as the plan's section 7 says small
    cells are not published. SHA-256 of the file as the run made it: b78d39097dea2e2ad5b449cf7d67522c7d95a1155125411523c56bf7a4c185e8
    SHA-256 of the file published here: 7989008f27d5ee91af639b2a28a9137fee738544b3d37ca9da4154db431772c8
  RUN-LOG.txt: one cleanup line that named unrelated work is removed. All 31 input hashes and every timestamp are kept.
    SHA-256 of the file published here: f52525ba859c4726513f6756839855f19a78088f1bd7aa4db13ea945a845ab08

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
