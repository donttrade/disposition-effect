5 November 2026 sell-off study: market by market
=================================================

ADDED AFTER THE WRITTEN PLAN. Everything in this note is descriptive. It is not one of the measures that ANALYSIS-PLAN.md stated
before the data was opened, and it does not change any of them. It was added on 7 November 2026 (UTC) so that the study can be
checked one market at a time.

Files
  5-november-2026-per-market.csv  every UTC day 2026-10-06 to 2026-11-05, every perpetual market: wallets force-closed, value
                                  force-closed (USD), number of force-close fills and the share of the value that was long; on the
                                  5 November rows also the market's own 30-day median of wallets and 5 November's ratio to it.
  per_market.py                   the code that makes it (identical to checks/selloff/per_market.py in the site's repository).
  MARKETS-VERIFIED.csv            what each large builder-listed market tracks, with the source and the date it was checked.
  markets_verified.py             the code that writes MARKETS-VERIFIED.csv from its evidence table.

Same rule as the study
  per_market.py builds its table with the SQL of run_day.py copied character for character (the site's tests check this): perpetuals
  only, the placeholder address excluded, a force-closed wallet is the taker of a trade with the liquidation flag. Builder-listed
  (HIP-3) means the dataset's dex field is not empty. Its build step stops unless, on 5 November, the unique wallets are 9,054
  (builder-listed) and 18,813 (all markets). For all 31 days its totals equal the published daily CSV to the cent.

Rows of the CSV (column row_type)
  market                             one market on one day. Only markets with 10 or more force-closed wallets that day (plan,
                                     section 7: cells under 10 wallets are not published).
  markets_under_10_wallets_combined  all the other markets of that day and scope, added together, so the rows still add up to the
                                     day's value. Its wallet column is blank; sum_of_market_wallet_counts is shown when 10 or more.
  scope_total_unique_wallets         the day's total for builder_listed, core (dex empty) or all_markets. wallets_force_closed counts
                                     each wallet once; sum_of_market_wallet_counts counts it once per market it was force-closed in.
  A day and market with no row had no force-close. The 30-day median counts such a day as 0.

Reconciliation, 5 November 2026
  Builder-listed: market rows plus the combined row = 140,556,424.23 USD = the study's value (141 million).
                  Unique wallets 9,054. Per-market wallet counts add up to 13,460, because one wallet can be force-closed in
                  several markets: 4,406 of the pairs repeat a wallet already counted elsewhere.
  All markets:    283,196,131.53 USD. Unique wallets 18,813; per-market counts add up to 26,439 (7,626 repeats).
  Core markets:   10,319 unique wallets. 9,054 + 10,319 - 18,813 = 560 wallets were force-closed on both kinds of market.

The input files: pin the version
  Ironflow replaced five daily files (6, 10 and 11 October, 4 and 5 November) on 6 November 2026 at 23:24 UTC, after this study
  ran ("trades of blocks refilled from the S3 archive"). The files on the dataset's main branch now have other hashes. The study
  read the dataset at commit 8e0c2f593fdbf324772db734747ccfce597f3b80 (6 November 2026, 04:16 UTC). per_market.py downloads from
  that commit and refuses any file whose SHA-256 is not the one in RUN-LOG.txt.

How to check it yourself (Python 3.10 or later, about 5 GB free while it runs)
  python3 -m pip install duckdb==1.1.3
  python3 -I per_market.py run ironflow-files per-market-days --delete
  python3 -I per_market.py build per-market-days 5-november-2026-per-market.csv && sha256sum 5-november-2026-per-market.csv
  Expected SHA-256: 62cb49d6cf0d54887512572239766c4c784acff6361b77f2552b5bdbd638eae9
  We counted 5 November twice from the same file and got the same numbers to the last digit. If a value ever differs in its last
  cent, the cause would be the order in which the computer adds numbers, not the data.

What each market tracks (MARKETS-VERIFIED.csv)
  Which markets: every builder-listed market with at least 1% of the value force-closed on builder-listed markets on 5 November
  (20 markets, 84% of that value), which includes every market the study page names (SOXL, MU, SP500, XYZ100, AMD).
  Sources, in this order:
    1. The builder's own public documentation. trade[XYZ] (dex xyz): https://docs.trade.xyz (Specification Index, Stocks: US and
       Korea, Equity Indices, Oracle Price; also its machine-readable copy https://docs.trade.xyz/llms-full.txt). Entropy (dex io):
       https://docs.entropy.io (Equity Assets, Oracle Price).
    2. Hyperliquid's public metadata: POST https://api.hyperliquid.xyz/info with {"type":"perpDexs"} (which builder runs each dex)
       and {"type":"meta","dex":"xyz"} or "io" (each market's maximum leverage and margin mode). The API answered from our machine.
  Status:
    verified         the builder's documents name what the market tracks (the share or index) and how its price is taken, and the
                     maximum leverage and margin mode in those documents equal Hyperliquid's metadata.
    partly verified  the builder names the issuer or underlying but something is still open (the notes column says what).
    not verified     no primary source was found.
  Only a verified market's underlying is named on the study page; any other keeps its name "as listed".
  A ticker name alone is never treated as evidence. Example: the market listed as PURRDAT references Nasdaq: PURR.
  Result: 19 verified, 1 partly verified (io:NBIS-PERP), 0 not verified.
  Limits: the documents were read on 7 November 2026 (UTC) and describe each market on that day, not on 5 November. trade[XYZ]'s
  changelog lists no change to these markets' underlying between 6 October and 7 November 2026. The price-source text is a short
  summary of the builder's own description; we did not check the oracle prices themselves.

Wallets, not people. No wallet address is in any of these files. Not investment advice.
Data: Ironflow (ironflow.sh), Hyperliquid trades, CC BY 4.0; changes made: aggregated into counts and sums. Builder documents are
quoted briefly for identification, with their URLs.
