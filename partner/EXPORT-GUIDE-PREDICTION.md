# How to export the two files for the prediction study

`prediction_test.py` reads two CSV files and the completed parameter block. This page says what goes in each file. The script refuses anything else, with a row number and a fixed sentence that never quotes your data.

**About 1 day** for the export, **about 1 hour** for the run, **1–2 days** for questions.

## Before you export: identifiers

`account_id` and `trader_key` are pseudonyms. Use a keyed hash or a random surrogate, **never a login, email or platform account number**. The script uses them only to join the two files, find duplicates and keep one account per trader. It never prints them, and the mapping never has to be reversible.

## File 1: `trades.csv`, one row per closed trade or deal

| Column | Type | Note |
|---|---|---|
| `account_id` | pseudonymous string | Joins to `accounts.csv` |
| `open_time` | date and time | `YYYY-MM-DDTHH:MM[:SS]`, followed by `+HH:MM`, `-HH:MM` or `Z`. No offset means UTC. Times are needed to the minute. An account whose first 30 trades are dates only is excluded (E2). |
| `close_time` | date and time | The same format. It is never before `open_time`. |
| `symbol` | string | Used only to group sizes. A trade's size is divided by that symbol's median size **within the account's first 30 trades**. |
| `direction` | `long` or `short` | |
| `size` | decimal, 0 or more | In the platform's own units (lots or contracts) |
| `pnl` | signed decimal | Net of commission and swap if your platform gives it, otherwise gross. Say which in `pnl_basis`. |

Include **every** closed trade of each account from its start to the data cut, partial closes included. Partial fills that share a symbol, direction and open minute are merged into one trade, as the paid engine does.

## File 2: `accounts.csv`, one row per account started in the period

| Column | Note |
|---|---|
| `account_id` | One row per account. A repeated id is refused. |
| `start_time` | When the account (or the challenge) started. It has to be inside `period_start`–`period_end`. |
| `start_balance` | The account size, above 0 |
| `daily_loss` | The daily-loss limit as an amount, or blank if there is none |
| `max_loss` | The max-loss limit as an amount, above 0 |
| `drawdown` | `static`, `trailing_eod` or `trailing_trade` |
| `trail_stop_at` | For a trailing drawdown: where the floor stops trailing, as an amount relative to the start (for example `0` = break-even). Blank if it never stops. |
| `outcome` | `daily`, `max`, `other_rule`, `passed`, `closed_no_breach` or `active`, taken from your risk system |
| `outcome_time` | When that outcome happened. Blank exactly when `outcome` is `active`. |
| `data_end_time` | The last time you have data for the account |
| `trader_key` (optional) | A pseudonym for the person. Only the person's earliest eligible account is used (E7). |
| `abuse_flag` (optional) | `1` if your own process flagged the account for copy trading, hedging across accounts or latency arbitrage, otherwise `0` or blank (E5) |
| `bot_flag` (optional) | `1` to exclude an account as automated (E6), otherwise `0` or blank |

The number of rows has to equal `accounts_in_period` in the parameter block. That count proves the export holds every account started in the period, not a chosen subset.

## The parameter block's firm fields

| Key | What to put |
|---|---|
| `firm_label` | Your published name, or a description such as `a CFD prop firm` if you stay anonymous |
| `period_start`, `period_end` | The days the accounts started, `YYYY-MM-DD` |
| `data_cut` | The last day of data in the export. Pick it so that every account has had 30 days after its 30th trade. |
| `accounts_in_period` | The number of rows in `accounts.csv` |
| `day_start`, `day_utc_offset` | Where your daily-loss day begins (for example `00:00`, or `17:00` for a New York close) and the UTC offset of that clock (for example `+02:00`) |
| `outcome_mode` | `firm` (your risk-system outcomes). `rule` is for data with no outcome record. |
| `pnl_basis` | `net` or `gross` |

Send the completed block to donttrade.research@gmail.com before the run. donttrade adds it to the OSF registration as a dated amendment, before any result exists.

## What leaves your firm

Only the printed text: counts, AUCs and intervals, p-values and signs, and banded tables in which every cell describes at least 5 accounts. You read it before you send it. No row, identifier, symbol, time or amount leaves your firm.
