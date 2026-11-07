# ANALYSIS PLAN: Hyperliquid forced closes on 5 November 2026 against the 30 days before

Written and timestamped BEFORE any 5 November (or baseline) trade or liquidation row was read.
Plan logged: **2026-11-06T19:44:00Z** (machine clock, UTC). The sha256 of this file is recorded in ANALYSIS-PLAN.sha256 immediately after writing.

## 0. What has been looked at before this plan (disclosure)
- The two dataset cards (README.md) and file lists of `ironflow/hyperliquid-trades` and `ironflow/hyperliquid-liquidations` on Hugging Face, fetched 2026-11-06 ~19:40 UTC. Card sha256: trades 2534af7b...5850b, liquidations f48b90c5...7821.
- The cards themselves state: trades coverage 3 Oct to 5 Nov 2026 (196,840,577 trades); busiest day in the first 30 days was 29 Oct 2026; the liquidations card's busiest day in its history is 10 Oct 2025 (109,790 liquidations, $7.2B). Those card figures were seen, not computed.
- File sizes of the daily trade files (5 Nov file is 234,539,088 bytes). File size is a weak volume signal; disclosed.
- News reports read before this plan: CoinGlass via media, about $1.03B to $1.06B liquidated across exchanges in 24 h, "over 207,000 traders" (cross-exchange, not Hyperliquid-specific).
- No row of any data file has been opened.

## 1. Question
On Thursday 5 November 2026 (US stocks' worst day since April 2025), how many Hyperliquid perpetual-futures wallets were force-closed (liquidated), how much notional was force-closed, and what share of liquidated wallets traded again within 15 minutes, compared with the 30 days before?

This is a descriptive event study. It does not test any habit-score prediction and is outside every window of the pre-registered Hyperliquid blow-up study (osf.io/j2ypd; windows Oct 2025 to Jan 2026).

## 2. Data
- **D1** `ironflow/hyperliquid-trades`, daily Parquet files `data/YYYY-MM-DD.parquet`, licence CC BY 4.0, credit "Ironflow (ironflow.sh)". One row per trade with timestamp (ms UTC), market, coin, dex, market_class, price, size, notional, taker_side, buyer, seller, liquidation, block, tid.
- **D2** `ironflow/hyperliquid-liquidations`, `data/events/2026-10.parquet` (one row per liquidated position; CC BY 4.0). Used ONLY to validate the wallet-attribution rule (section 5) on baseline days.
- **Event day E:** UTC day 2026-11-05.
- **Baseline B:** the 30 UTC days 2026-10-06 to 2026-11-04 inclusive.
- **Secondary day E2:** 2026-11-06, run with identical code once its file is published (expected 7 Nov). Reported separately; does not change the primary result.
- Files are streamed one at a time into /home/claude/data/selloff/, hashed (sha256), processed and deleted. Scripts in /home/claude/proj/selloff/. Python run with -I.

## 3. Scope filters (fixed)
- Perpetuals only: market_class == 'perp' (native and HIP-3). Spot excluded.
- Exclude the placeholder address 0xeeee...eeee on either side.
- "HIP-3 markets" = rows with non-empty dex.

## 4. Definitions
- **Liquidation trade:** a perp row with liquidation == true.
- **Liquidated wallet (taker rule):** for a liquidation trade, the taker, i.e. buyer if taker_side == 'buy', else seller. Basis: the Zenodo census (HL-DATA-CENSUS-2026-11-06.md) found the aggressor was the liquidated side in 62,004 of 62,004 marked trades.
- **Liquidated side:** taker sold = a long was liquidated; taker bought = a short was liquidated.
- **Liquidation event:** distinct (wallet, market, block) among liquidation trades under the taker rule (mirrors D2's event definition).
- **Liquidated notional:** sum of notional over liquidation trades (USD stablecoin).
- **Active wallet (day):** any address appearing as buyer or seller of at least one perp trade that UTC day.
- **Re-trade after liquidation:** for each wallet liquidated on day d, t0 = time of its first liquidation trade that day. The wallet "re-traded within 15 min" if it is the taker of at least one NON-liquidation perp trade with timestamp in (t0, t0 + 15 min] and in a block after t0's block. Same with 60 min. Taker only, because resting maker orders can fill without a new decision. Limitation, stated in any publication: the data carry no position field, so "traded again" cannot be split into opening vs closing; trigger orders (stop/take-profit) placed earlier also appear as taker trades. A wallet liquidated in the last 15 (60) minutes of a UTC day is followed into the next day's file only if that file is loaded; to keep it simple and identical across days, the follow-up window is truncated at the day's end and wallets whose t0 is within 60 min of 24:00 UTC are excluded from S2's denominator.

## 5. Validation step V1 (run first, on baseline days only)
For 2026-10-06 to 2026-10-31, compare (wallet, market, UTC date) sets from the taker rule with D2's events. Report precision and recall.
- If both are >= 95%: wallet counts (P1, P3, S2) are reported as stated.
- If either is < 95%: wallet-level measures are reported only with the measured precision/recall beside them and a caveat; P2 (notional, trade-level) is unaffected and becomes the headline.
- Also report D2's own daily event counts for 6 to 31 Oct beside mine.

## 6. Measures
**Primary**
- **P1** distinct liquidated wallets on E vs the 30-day baseline: E value, baseline median, IQR, min, max, ratio E / median, rank of E among the 31 days.
- **P2** liquidated notional on E, same statistics.
- **P3** liquidated wallets as a share of active wallets on E, same statistics.

**Secondary**
- **S1** P1 and P2 restricted to HIP-3 markets (on-chain stock, index and commodity perps), plus the top 5 HIP-3 markets by liquidated notional on E.
- **S2** share of liquidated wallets that re-traded within 15 min and within 60 min: E vs baseline (pooled share over all 30 days, and median of daily shares).
- **S3** liquidated notional by UTC hour on E; share falling inside the US cash session 14:30 to 21:00 UTC.
- **S4** share of liquidated notional on E that was long positions.
- **S5** liquidation events count on E (comparable in definition to the D2 card's 10 Oct 2025 figure, which is quoted from the card, not recomputed).

## 7. Inference and reporting rules
- No hypothesis tests beyond rank. Under exchangeability of days, a rank of 1 of 31 corresponds to p <= 1/31 (0.032); stated only as a rank, with that caveat.
- Every number is published whatever it shows, including "5 November was not unusual on Hyperliquid".
- No wallet address is ever published or written to any output. Outputs hold counts only. Cells under 10 wallets are suppressed.
- Round to 3 significant figures in public copy; full precision in the JSON output.
- Credit line in every use: "Data: Ironflow (ironflow.sh), Hyperliquid trades and liquidations, CC BY 4.0. Analysis by donttrade; changes made (aggregated)." No endorsement implied.
- Wording rules: "force-closed (liquidated)", never "wiped out"; "wallets", never "traders" or "retail" (a wallet may be a bot, a fund, or one of several held by one person).

## 8. Feasibility and stopping rules (fixed in advance)
- Compute budget: 2 cores, about 6.5 GB free disk; one file on disk at a time.
- If the full 31-file run cannot finish within about 2.5 hours wall time, the baseline shrinks to the pre-stated subset of the 10 most recent days (2026-10-26 to 2026-11-04), and this is disclosed. No other subset is allowed.
- If D1's 5 Nov file is missing or fails to read, the study is reported as not feasible today.
- Any code change after the first baseline file is processed is logged in RUN-LOG.txt with a reason.
