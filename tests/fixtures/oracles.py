"""Hand oracles: expected values worked out by hand, independent of any code.

Each entry lists the closed trades (in close-time order) with the arithmetic in a
comment, plus the warnings and skipped-row counts. tests/test_engine_ref.py checks
the Python reference against these; the golden test then checks the JS engine
against the reference.
"""

# pnl, gross, fees are money (or points); hold in seconds.
ORACLES = {
    "generic/basic.csv": {
        # SPY: buy 100 @560.20 (fee 1.00); sell 40 @566.10 (0.40); sell 60 @552.75 (0.60)
        # exit vwap = (40*566.10 + 60*552.75)/100 = (22644 + 33165)/100 = 558.09
        # gross = (558.09 - 560.20) * 100 = -211.00 ; fees = 2.00 ; pnl = -213.00
        # hold = 2026-09-01 09:35:05 -> 2026-09-08 15:45:30 = 7 d 6 h 10 m 25 s = 627025 s
        # QQQ sell 30 opens a short that never closes -> W_OPEN_POSITIONS 1
        "trades": [dict(symbol="SPY", dir="long", qty=100, pnl=-213.0, pnl_gross=-211.0, fees=2.0, hold_s=627025,
                        fills_n=3, pnl_source="computed", pnl_unit="USD")],
        "warnings": {"W_OPEN_POSITIONS": 1},
        "skipped": {},
    },
    "generic/short_reversal_adds.csv": {
        # ABC sell 10 @50 (fee 1.00) opens a short.
        # ABC buy 15 @48 (fee 1.50) covers 10 and reverses into a long of 5.
        #   short: gross = (48 - 50) * 10 * -1 = +20 ; fees = 1.00 + 1.50*10/15 = 2.00 ; pnl 18 ; hold 3600
        #   long opens with 5 @48 and fee 1.50*5/15 = 0.50
        # ABC sell 5 @49 (fee 0.50): long gross = (49-48)*5 = 5 ; fees 1.00 ; pnl 4 ; hold 22.5 h = 81000
        # XYZ: B2@10, S1@12, B1@11, S2@13. Total bought 3 (31), sold 3 (38): pnl = 38 - 31 = 7.
        #   peak position is 2, but the quantity that earned the price difference is 3:
        #   (12.6667 - 10.3333) * 3 = 7. hold 09:00 -> 09:30 = 1800. 4 fills.
        # No Currency column -> unit "points" (price units).
        "trades": [dict(symbol="ABC", dir="short", qty=10, pnl=18.0, pnl_gross=20.0, fees=2.0, hold_s=3600, fills_n=2),
                   dict(symbol="ABC", dir="long", qty=5, pnl=4.0, pnl_gross=5.0, fees=1.0, hold_s=81000, fills_n=2),
                   dict(symbol="XYZ", dir="long", qty=2, pnl=7.0, pnl_gross=7.0, fees=0.0, hold_s=1800, fills_n=4)],
        "warnings": {},
        "skipped": {},
    },
    "generic/eu_thousands.csv": {
        # "1 234,50" (NBSP) = 1234.50 ; "1 240,25" = 1240.25 ; gross (1240.25-1234.50)*2 = 11.50 ; fees 2 ; pnl 9.50
        # "1 230,00" (thin space) = 1230 ; "1.229,50" = 1229.50 ; gross -0.50 ; fees 1.00 ; pnl -1.50
        "trades": [dict(symbol="BRK", dir="long", qty=2, pnl=9.5, pnl_gross=11.5, fees=2.0, hold_s=88200),
                   dict(symbol="BRK", dir="long", qty=1, pnl=-1.5, pnl_gross=-0.5, fees=1.0, hold_s=3600)],
        "warnings": {},
        "skipped": {},
    },
    "generic/mixed_currency.csv": {
        # USD: SPY +50, QQQ -10 ; CAD: RY +10. Largest group USD (2 trades) is kept, 1 left out.
        "trades": [dict(symbol="SPY", pnl=50.0), dict(symbol="QQQ", pnl=-10.0)],
        "warnings": {"W_MIXED_CURRENCY": 1},
        "skipped": {},
    },
    "generic_roundtrip/tradezella.csv": {
        # NVDA long 50: (121.00-120.10)*50 = 45.00 - 1.00 = 44.00 ; 09:30:00 -> 10:15:30 = 2730 s
        # AMD short 30: (162.50-160.00)*30*-1 = -75.00 - 0.60 = -75.60 ; 13:00 -> next day 09:45 = 74700 s
        "trades": [dict(symbol="NVDA", dir="long", qty=50, pnl=44.0, pnl_gross=45.0, fees=1.0, hold_s=2730),
                   dict(symbol="AMD", dir="short", qty=30, pnl=-75.6, pnl_gross=-75.0, fees=0.6, hold_s=74700)],
        "warnings": {"W_UNVERIFIED_FORMAT": 0},
        "skipped": {},
    },
    "mt5/deals_netting.htm": {
        # balance row skipped; "canceled buy" skipped.
        # EURUSD: in 1.00 @1.08410 (comm -3.50); out 0.50 profit +100 (-1.75); out 0.50 profit -55 (-1.75)
        #   gross (reported Profit) = 45 ; fees 7.00 ; pnl 38 ; 09:15:02 -> 14:02:55 = 17273 s ; 3 fills
        # XAUUSD short: comm -1.00 and -1.00, swap -0.20 -> fees 2.20 ; profit 55 ; pnl 52.80 ; 5340 s
        # GBPUSD: in 1.00 (comm -3.50), then "in/out" 2.00 (comm -7.00, profit 500) reverses:
        #   long closes: fees 3.50 + 7.00*1/2 = 7.00 ; pnl 493 ; 7200 s
        #   short opens with fee 3.50 ; out 1.00 comm -3.50 swap +2.00 -> cost 1.50 ; profit 700
        #   short: fees 5.00 ; pnl 695 ; 12:00 -> next day 09:00 = 75600 s
        # USDJPY: swap +3.00 with no commission is a net credit: fee 0, credit added to profit
        #   68 + 3 = 71 ; 3 days = 259200 s
        # EURUSD in 0.30 never closed -> W_OPEN_POSITIONS 1
        "trades": [dict(symbol="EURUSD", dir="long", qty=1, pnl=38.0, pnl_gross=45.0, fees=7.0, hold_s=17273,
                        fills_n=3, pnl_source="reported", pnl_unit="account"),
                   dict(symbol="XAUUSD", dir="short", qty=0.1, pnl=52.8, pnl_gross=55.0, fees=2.2, hold_s=5340),
                   dict(symbol="GBPUSD", dir="long", qty=1, pnl=493.0, fees=7.0, hold_s=7200),
                   dict(symbol="GBPUSD", dir="short", qty=1, pnl=695.0, fees=5.0, hold_s=75600),
                   dict(symbol="USDJPY", dir="long", qty=1, pnl=71.0, pnl_gross=71.0, fees=0.0, hold_s=259200)],
        "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_SKIPPED_ROWS": 2, "W_OPEN_POSITIONS": 1},
        "skipped": {"balance": 1, "cancelled": 1},
    },
    "mt5/positions_hedging.htm": {
        # Closed-positions table present -> one trade per position id (hedging handled).
        # 5002 sell 0.50 closes first (12:00): 25 - 3.50 = 21.50 ; 7200 s
        # 5001 buy 1.00 (15:00): 200 - 7.00 = 193 ; 21600 s
        # 5003 US500 sell 2: -21 - 1.20 swap = -22.20 ; 2730 s
        # Open Positions table: 1 row -> W_OPEN_POSITIONS 1 ; Deals balance row -> skipped 1
        "trades": [dict(symbol="EURUSD", dir="short", qty=0.5, pnl=21.5, fees=3.5, hold_s=7200),
                   dict(symbol="EURUSD", dir="long", qty=1, pnl=193.0, fees=7.0, hold_s=21600),
                   dict(symbol="US500", dir="short", qty=2, pnl=-22.2, fees=1.2, hold_s=2730)],
        "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_SKIPPED_ROWS": 1, "W_OPEN_POSITIONS": 1},
        "skipped": {"balance": 1},
    },
    "mt5/deals_hedging.htm": {
        # Same EURUSD deals, Deals table only: the "in" sell at 10:00 opposes an open long -> W_HEDGING 1.
        # Netted: one trade, profits 25 + 200 = 225, commissions 10.50 -> pnl 214.50 (equals 21.50 + 193).
        "trades": [dict(symbol="EURUSD", dir="long", qty=1, pnl=214.5, pnl_gross=225.0, fees=10.5, hold_s=21600,
                        fills_n=4)],
        "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_SKIPPED_ROWS": 1, "W_HEDGING": 1},
        "skipped": {"balance": 1},
    },
    "mt4/statement.htm": {
        # 1002 buy 1.00: 350 - 7.00 = 343 ; 09:00 -> 13:30 = 16200 s
        # 1003 sell 0.50: -200 - 3.50 - 1.10 swap = -204.60 ; 86400 s
        # 1005 buy 0.10: swap +1.50 is a net credit: -6.80 + 1.50 = -5.30 ; fees 0 ; 3 days
        # balance row and the deleted "buy limit" skipped ; Open Trades row -> W_OPEN_POSITIONS 1
        # Working Orders rows are not trades and are not counted.
        "trades": [dict(symbol="eurusd", dir="long", qty=1, pnl=343.0, fees=7.0, hold_s=16200),
                   dict(symbol="gbpusd", dir="short", qty=0.5, pnl=-204.6, fees=4.6, hold_s=86400),
                   dict(symbol="usdjpy", dir="long", qty=0.1, pnl=-5.3, pnl_gross=-5.3, fees=0.0, hold_s=259200)],
        "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_SKIPPED_ROWS": 2, "W_OPEN_POSITIONS": 1},
        "skipped": {"balance": 1, "cancelled": 1},
    },
    "ibkr/activity_flex.csv": {
        # AAPL: buy 100 @228.10 (1.00); sell 60 @231.40 (0.60); sell 40 @231.00 (0.40)
        #   exit vwap (13884 + 9240)/100 = 231.24 ; gross 3.14*100 = 314 ; fees 2.00 ; pnl 312
        # TSLA short 50: (240-245)*50*-1 = 250 ; fees 2 ; pnl 248
        # SHOP is CAD: left out (USD has 2 trades, CAD 1), no FX column -> W_MIXED_CURRENCY 1
        "trades": [dict(symbol="AAPL", dir="long", qty=100, pnl=312.0, pnl_gross=314.0, fees=2.0, fills_n=3),
                   dict(symbol="TSLA", dir="short", qty=50, pnl=248.0, pnl_gross=250.0, fees=2.0)],
        "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_MIXED_CURRENCY": 1},
        "skipped": {},
    },
    "ibkr/trade_confirm_fx.csv": {
        # Rows are newest-first; the engine sorts by time. ORDER-level row skipped.
        # AAPL: realized P&L 328.40 is taken as reported (net of commission, UNVERIFIED);
        #   fees 1.60 ; gross 330.00 ; FX 1 -> base unchanged.
        # SHOP (CAD) short: realized 5.00 net ; fees 2.00 ; gross 7.00 ; FX of the closing fill 0.74
        #   -> pnl 3.70, gross 5.18, fees 1.48 (all rows carry an FX rate, so currencies are converted)
        # TSLA buy never closes -> W_OPEN_POSITIONS 1
        "trades": [dict(symbol="AAPL", dir="long", qty=100, pnl=328.4, pnl_gross=330.0, fees=1.6,
                        pnl_source="reported", pnl_unit="base"),
                   dict(symbol="SHOP", dir="short", qty=20, pnl=3.7, pnl_gross=5.18, fees=1.48, pnl_unit="base")],
        "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_SKIPPED_ROWS": 1, "W_OPEN_POSITIONS": 1, "W_MIXED_CURRENCY": 0},
        "skipped": {"not_execution": 1},
    },
    "tradovate/orders.csv": {
        # MNQ (x2 per point): buy 2 @21010.25 ; sell 1 @21030.00 ; sell 1 @20995.50
        #   exit vwap 21012.75 ; gross (21012.75 - 21010.25) * 2 * 2 = 10.00 ; no fees in this report
        # MES (x5, root derived from "MESZ6"): short 1 @6620.25, cover @6610.00 -> 10.25 * 5 = 51.25
        # XYZZ6 unknown -> points (W_POINTS_ONLY 1), then left out as a different unit (W_MIXED_CURRENCY 1)
        # one Canceled order skipped
        "trades": [dict(symbol="MNQZ6", dir="long", qty=2, pnl=10.0, hold_s=2465, fills_n=3, pnl_unit="USD"),
                   dict(symbol="MESZ6", dir="short", qty=1, pnl=51.25, hold_s=1800)],
        "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_SKIPPED_ROWS": 1, "W_POINTS_ONLY": 1, "W_MIXED_CURRENCY": 1},
        "skipped": {"not_filled": 1},
    },
}
ORACLES["generic/basic_utf16.csv"] = ORACLES["generic/basic.csv"]
ORACLES["mt5/deals_netting_utf16.htm"] = ORACLES["mt5/deals_netting.htm"]
ORACLES["mt5/deals.csv"] = {
    # The spec's synthetic MT5 Deals CSV: EURUSD as above (pnl 38), XAUUSD short left open.
    "trades": [dict(symbol="EURUSD", pnl=38.0, fees=7.0, hold_s=17273)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_POSITIONS": 1},
    "skipped": {},
}

ORACLES["generic/no_losses.csv"] = {
    # 35 SPY trades, each buy 10 then sell 0.50 higher: +5.00 each, 30 min hold, no fees.
    "trades": [dict(symbol="SPY", pnl=5.0, hold_s=1800)] * 35,
    "warnings": {},
    "skipped": {},
}
# 90 generated trades (make_fixtures.many_trades): checked for structure, not per trade.
ORACLES_COUNT_ONLY = {"generic/ninety_trades.csv": 90}
# PGR/PLR fixture: its counts are hand-checked in test_engine_ref.test_pgr_plr_hand_oracle.
# Trades: AAA +50; BBB 15 @ avg 49.333 sold at 47 -> -35; CCC -10; DDD short 30 -> 29 = +10.
ORACLES["generic/pgr_oracle.csv"] = {
    "trades": [dict(symbol="AAA", pnl=50.0), dict(symbol="BBB", pnl=-35.0), dict(symbol="CCC", pnl=-10.0),
               dict(symbol="DDD", dir="short", pnl=10.0)],
    "warnings": {},
    "skipped": {},
}

ERRORS = {
    "errors/empty.csv": ("E_EMPTY", None, None),
    "errors/blank_lines.csv": ("E_EMPTY", None, None),
    "errors/header_only.csv": ("E_HEADER_ONLY", None, None),
    "errors/one_execution.csv": ("E_NO_CLOSED_TRADES", None, None),
    "errors/unknown_format.csv": ("E_UNKNOWN_FORMAT", None, None),
    "errors/missing_price.csv": ("E_MISSING_COLUMN", 1, "price"),
    "errors/bad_date.csv": ("E_BAD_DATE", 2, "date"),
    "errors/ambiguous_date.csv": ("E_AMBIGUOUS_DATE", 2, "date"),
    "errors/ambiguous_number.csv": ("E_BAD_NUMBER", 2, "price"),
    "errors/not_a_number.csv": ("E_BAD_NUMBER", 2, "price"),
    "errors/excel.xlsx": ("E_ENCODING", None, None),
    "errors/binary.csv": ("E_ENCODING", None, None),
    "errors/html_no_table.htm": ("E_UNKNOWN_FORMAT", None, None),
    "errors/mt5_header_only.htm": ("E_HEADER_ONLY", None, None),
}

# Tester v2 B1: a file that starts while a position is already open.
ORACLES["ibkr/tv2_carried_in.csv"] = {
    # 09-02 SELL 100 C closes a long bought before the file starts: left out (W_OPEN_AT_START 1),
    # never turned into a short. The real trade: BUY 100 O @200 09-10 10:00 -> SELL 100 C @205 09-11 10:00.
    # realized 0 + 500 = 500 net (reported) ; fees 1 + 1 = 2 ; gross 502 ; hold 86400 s
    "trades": [dict(symbol="AAPL", dir="long", qty=100, pnl=500.0, pnl_gross=502.0, fees=2.0, hold_s=86400,
                    fills_n=2, pnl_source="reported")],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_AT_START": 1},
    "skipped": {},
}
ORACLES["mt5/tv2_carried_in_deals.csv"] = {
    # 09-01 "sell out" closes a pre-file buy: left out, so no fake short and no false W_HEDGING.
    # buy in 1.00 @1.0900 09-05 09:00 -> sell out @1.0950 12:00, profit 50 ; no costs ; hold 10800 s
    "trades": [dict(symbol="EURUSD", dir="long", qty=1, pnl=50.0, pnl_gross=50.0, fees=0.0, hold_s=10800,
                    fills_n=2)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_AT_START": 1},
    "skipped": {},
}
ORACLES["ibkr/carried_in_add.csv"] = {
    # AAPL: BUY 100 O, then SELL 200 C. 200 > the 100 opened in the file, so the position was
    #   already long before the file; it was never flat, so the whole AAPL trade is left out (1).
    # TSLA: two closes of one carried position -> counted once (1). Total W_OPEN_AT_START 2.
    # MSFT: BUY 10 O @400 -> SELL 10 C @398, realized -22 net ; fees 2 ; gross -20 ; 3600 s
    "trades": [dict(symbol="MSFT", dir="long", qty=10, pnl=-22.0, pnl_gross=-20.0, fees=2.0, hold_s=3600)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_AT_START": 2},
    "skipped": {},
}

# Tester v2 B2: dot thousands in a decimal-comma file.
ORACLES["generic/tv2_eu_dot_thousands_qty.csv"] = {
    # "12,50" and "13,50" prove the file uses decimal commas, so "1.500" = 1,500 (not 1.5).
    # (13.50 - 12.50) * 1500 = 1500 points ; 1 h
    "trades": [dict(symbol="AAA", dir="long", qty=1500, pnl=1500.0, hold_s=3600)],
    "warnings": {},
    "skipped": {},
}
ORACLES["generic/tv2_eu_dot_thousands_price.csv"] = {
    # "18.300,5" proves decimal commas: entry "18.250" = 18,250 ; exit 18,300.5 ; pnl 50.5
    "trades": [dict(symbol="GER40", dir="long", qty=1, entry_vwap=18250.0, exit_vwap=18300.5, pnl=50.5)],
    "warnings": {},
    "skipped": {},
}
ERRORS["errors/mixed_decimal_styles.csv"] = ("E_BAD_NUMBER", 3, "price")   # "12,50" then "13.5"
ERRORS["errors/dot3_no_evidence.csv"] = ("E_BAD_NUMBER", 2, "qty")       # ';' file, "1.500" and integers only

# Tester v2 B3: a stray quote mark must never hide rows.
ERRORS["errors/tv2_stray_quote.csv"] = ("E_BAD_QUOTE", 102, None)   # data row 101 = physical line 102
ERRORS["errors/two_stray_quotes.csv"] = ("E_BAD_QUOTE", 3, None)     # the cell opened on line 3 holds lines 4-5
ORACLES["generic/quoted_multiline_note.csv"] = {
    # The note spans two lines but holds one comma, so it is a note, not swallowed rows. +1 point, 1 h.
    "trades": [dict(symbol="AAA", dir="long", qty=1, pnl=1.0, hold_s=3600)],
    "warnings": {},
    "skipped": {},
}

# 40 plain MT5 round trips (make_fixtures.mt5_netting_long): the paid-flow tests upload it,
# because a paid report needs at least 30 trades. Each trade: two -3.50 commissions -> fees 7.
ORACLES["mt5/deals_netting_40.htm"] = {
    "trades": [dict(fees=7.0, fills_n=2, pnl_source="reported", pnl_unit="account")] * 40,
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_SKIPPED_ROWS": 1},
    "skipped": {"balance": 1},
}

# Tester v2 D5: an unquoted comma in Account shifts "CANARY-T3" into the Date column. The
# error names row 2, column date, and its message never repeats the cell (golden test checks).
ERRORS["errors/tv2_unquoted_comma_account.csv"] = ("E_BAD_DATE", 2, "date")

# Tester v2 D6: the same two rows pasted twice. Kept (two identical fills can be real) but
# flagged: W_DUPLICATE_ROWS 2. Buys at 09:30 x2, sells at 10:30 x2 -> one trade, qty 2, +2.
ORACLES["generic/tv2_duplicate_rows.csv"] = {
    "trades": [dict(symbol="AAA", dir="long", qty=2, pnl=2.0, hold_s=3600, fills_n=4)],
    "warnings": {"W_DUPLICATE_ROWS": 2},
    "skipped": {},
}

# Tester v2 D7 (t_oracles.py same_second_reversed, inside a file that shows its direction):
# times fall down the rows (11:00, 10:00, 09:30), so the file is newest first, and the A sell
# and buy in the same second are read bottom-up too: buy @10 then sell @11 -> long +1, hold 0.
# (The Tester's 2-row file has no other rows, so its direction cannot be known; file order is kept.)
ORACLES["generic/tv2_same_second_newest_first.csv"] = {
    "trades": [dict(symbol="A", dir="long", qty=1, pnl=1.0, hold_s=0),
               dict(symbol="B", dir="long", qty=1, pnl=1.0, hold_s=3600)],
    "warnings": {},
    "skipped": {},
}

# Tester v2 D8: rows the parser did not understand left positions stranded.
ORACLES["ibkr/tv2_cancelled_buy.csv"] = {
    # "BUY (Ca.)" (code Ca) takes back the 09-02 10:00 BUY 100 @10: both rows skipped as cancelled.
    # Left: BUY 100 O @10 09-03 -> SELL 100 C @11 09-04: gross 100, fees 1 + 1 = 2, pnl 98 (computed), 1 day.
    "trades": [dict(symbol="AAA", dir="long", qty=100, pnl_gross=100.0, fees=2.0, pnl=98.0, hold_s=86400)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_SKIPPED_ROWS": 2},
    "skipped": {"cancelled": 2},
}
ORACLES["tradovate/tv2_partial_then_cancel.csv"] = {
    # Buy 2 @5000; a Canceled order that filled 1 @5010; Sell 1 @5004.
    # ES x50: (5010 - 5000) * 50 + (5004 - 5000) * 50 = 500 + 200 = 700 ; 09:31:04 -> 09:50:00 = 1136 s
    "trades": [dict(symbol="ESZ6", dir="long", qty=2, pnl=700.0, hold_s=1136, fills_n=3, pnl_unit="USD")],
    "warnings": {"W_UNVERIFIED_FORMAT": 0},
    "skipped": {},
}
ORACLES["generic/tv2_side_long_short_words.csv"] = {
    # "Long" = buy, "Short" = sell: long +1, 1 h
    "trades": [dict(symbol="AAA", dir="long", qty=1, pnl=1.0, hold_s=3600)],
    "warnings": {},
    "skipped": {},
}
ORACLES["generic/tv2_side_cover.csv"] = {
    # "Short" = sell, "Cover" = buy: short +1, 1 h
    "trades": [dict(symbol="AAA", dir="short", qty=1, pnl=1.0, hold_s=3600)],
    "warnings": {},
    "skipped": {},
}
ERRORS["errors/no_closed_skipped_sides.csv"] = ("E_NO_CLOSED_TRADES", None, None)  # message names the skipped rows

# Tester v2 D4 (t_quote_dst.py): naive times across a daylight-saving change are flagged (W_DST).
ORACLES["tradovate/tv2_dst_spring.csv"] = {
    # US spring forward 2026-03-08: 01:30 -> 03:30 reads 7200 s (the real hold is 3600 s). Flagged.
    # ES x50: (5001 - 5000) * 50 = 50
    "trades": [dict(symbol="ESH6", dir="long", qty=1, pnl=50.0, hold_s=7200)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_DST": 1},
    "skipped": {},
}
ORACLES["tradovate/tv2_dst_fall.csv"] = {
    # US fall back 2026-11-01: buy 01:50 EDT, sell 01:10 EST (20 real minutes later). The times
    # alone put the sell first, so the engine reads a short of 2400 s. It cannot know better
    # without a time zone; it flags the trade. short: (5004 - 5000) * 50 = 200
    "trades": [dict(symbol="ESZ6", dir="short", qty=1, pnl=200.0, hold_s=2400)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_DST": 1},
    "skipped": {},
}
ORACLES["generic_roundtrip/tv2_dst_fall.csv"] = {
    # Same night, round-trip layout: close 01:10 < open 01:50, both in the fall-back night, so the
    # close is the repeated hour (02:10 in naive time): hold 1200 s, long, 4 points. Flagged.
    "trades": [dict(symbol="ES", dir="long", qty=1, pnl=4.0, hold_s=1200)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_DST": 1},
    "skipped": {},
}

# Tester fix round 2, F-B1 (t_b1b.py): a carried-in position that is ADDED TO inside the file.
# The real position is not flat from the start of the file until the last close of the carried
# lot, so under the flat-to-flat rule every fill of it is left out (never a trade carrying the
# older lot's FIFO P&L). One W_OPEN_AT_START per symbol and direction.
ORACLES["ibkr/fb1_carried_add_two_closes.csv"] = {
    # AAPL: carried long 100; BUY 100 O 09-10 (inv 100); SELL 100 C 09-11 (inv 0); SELL 100 C 09-20
    #   closes 100 more than the file opened -> a pre-file lot, closed 09-20: AAPL 09-10..09-20 left out.
    # MSFT: BUY 10 O @400 09-03 -> SELL 10 C @410 09-04: realized 100 net, fees 2, gross 102, 1 day.
    "trades": [dict(symbol="MSFT", dir="long", qty=10, pnl=100.0, pnl_gross=102.0, fees=2.0, hold_s=86400)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_AT_START": 1},
    "skipped": {},
}
ORACLES["ibkr/fb1_partial_carried_inner_trade.csv"] = {
    # AAPL: SELL 50 C 09-02 (excess 50) ... BUY 10 O / SELL 10 C ... SELL 50 C 09-25 (excess 50):
    #   50 carried shares are open the whole time, so the 10-share trade inside is left out; ONE position.
    "trades": [dict(symbol="MSFT", dir="long", qty=10, pnl=100.0, hold_s=86400)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_AT_START": 1},
    "skipped": {},
}
ORACLES["mt5/fb1_carried_add_two_outs.csv"] = {
    # EURUSD: carried long 1 + buy in 1; sell out (matched); sell out 09-08 (excess) -> all left out.
    # GBPUSD: buy in 1.3000 09:00 -> sell out 1.3010 10:00, profit 100, no costs, 3600 s.
    "trades": [dict(symbol="GBPUSD", dir="long", qty=1, pnl=100.0, pnl_gross=100.0, fees=0.0, hold_s=3600)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_AT_START": 1},
    "skipped": {},
}

# Tester fix round 2, F-D2 (t_b1b.py): reversal codes, same-second fills and an MT5 hedge on a
# carried position. Nothing is guessed: what the file cannot show is left out and flagged.
ORACLES["ibkr/fd2_carried_reversal_co.csv"] = {
    # AAPL SELL 200 "C;O" 09-02 with nothing opened in the file: it closes a pre-file long of
    # unknown size, so the short it opens has unknown size too. BUY 100 C 09-03 closes that short.
    # Both left out: W_OPEN_AT_START 1 (the long), W_AMBIGUOUS_FILLS 1 (AAPL). Only MSFT (+100, 1 day).
    "trades": [dict(symbol="MSFT", dir="long", qty=10, pnl=100.0, hold_s=86400)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_AT_START": 1, "W_AMBIGUOUS_FILLS": 1},
    "skipped": {},
}
ORACLES["ibkr/fd2_same_second_carried_close.csv"] = {
    # AAPL BUY 100 O and SELL 100 C in the same second 09-10, SELL 100 C 09-12. In file order the
    # 09-12 sell closes a pre-file long (all AAPL left out); with the sell first, the 09-10 sell
    # closes it and 09-10 -> 09-12 is a trade. The file cannot say which: no AAPL trade, and
    # never the old 0-second +800 trade. W_OPEN_AT_START 1, W_AMBIGUOUS_FILLS 1. Only MSFT.
    "trades": [dict(symbol="MSFT", dir="long", qty=10, pnl=100.0, hold_s=86400)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_OPEN_AT_START": 1, "W_AMBIGUOUS_FILLS": 1},
    "skipped": {},
}
ORACLES["mt5/fd2_hedge_carried_short.csv"] = {
    # buy in 1 @1.0900 09:00 (a new long while a pre-file short is open: a hedge), buy out 10:00
    # closes the pre-file short (left out), sell out @1.0950 12:00 closes the long: profit 50,
    # 10800 s. W_HEDGING 1 (the carried short was closed while the long was open).
    "trades": [dict(symbol="EURUSD", dir="long", qty=1, pnl=50.0, hold_s=10800)],
    "warnings": {"W_UNVERIFIED_FORMAT": 0, "W_HEDGING": 1, "W_OPEN_AT_START": 1},
    "skipped": {},
}
# sell 2.00 "in/out" with nothing opened in the file closes a pre-file long of unknown size, so
# the short it opens (closed by buy out 1.00) has unknown size: nothing is left to analyse. The
# message names both causes (test_engine_golden checks the text).
ERRORS["mt5/fd2_inout_reversal_on_carried.csv"] = ("E_NO_CLOSED_TRADES", None, None)

# Tester fix round 2, F-B2: one stray quote mark in an all-quoted CSV is closed by the NEXT row's
# opening quote, which merged that row into a note and silently lost 30 of 40 trades.
ERRORS["errors/fb2_allquoted_one_stray.csv"] = ("E_BAD_QUOTE", 22, None)       # row 22's note never closes
ERRORS["errors/fb2_two_stray_quotes_symbol.csv"] = ("E_BAD_QUOTE", 12, None)   # Symbol cell spans rows 12-13
ERRORS["errors/fb2_stray_note_into_next_row.csv"] = ("E_BAD_QUOTE", 12, None)  # note closed by row 13's quote

# Tester fix round 2, F-D7: "0.125" in a decimal-comma file was read as 125 (x1,000), silently.
# A thousands group never starts with 0, so "0.125" is a decimal point: with "12,50" in the same
# file that is two number formats -> E_BAD_NUMBER at the first comma cell after the dot evidence.
ERRORS["errors/fd7_leading_zero_dot_in_comma_file.csv"] = ("E_BAD_NUMBER", 2, "price")

# Tester fix round 2, F-D3: an unquoted comma in Account ("Doe, Jane", "Lee, Ann") shifts the
# name's second half into Currency. That column is now read only if every non-empty cell is an
# ISO 4217 code; otherwise it is ignored as a whole (W_CURRENCY_IGNORED, which repeats no cell),
# so no name reaches the page or the paid request. 40 round trips: (101 - 100) x 1 - fees 0.5 x 2
# = 0 points each, 60 s.
for _rel in ("generic/fd3_name_shifted_into_currency.csv", "generic/fd3_three_letter_fragment.csv"):
    ORACLES[_rel] = {
        "trades": [dict(symbol="AAA", dir="long", qty=1, pnl=0.0, fees=1.0, hold_s=60, pnl_unit="points",
                        currency=None)] * 40,
        "warnings": {"W_CURRENCY_IGNORED": 0},
        "skipped": {},
    }
