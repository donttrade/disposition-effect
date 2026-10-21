#!/usr/bin/env python3
"""Writes every synthetic engine fixture under tests/fixtures/.

All files are synthetic re-creations. They copy the HEADER STRUCTURE of the
public sources listed in PROVENANCE.txt; no third-party file is committed and no
row comes from a real account. The canary string CANARY-ZQ7X is planted in every
account, owner-name, alias, comment and report-header field: tests assert it
never reaches the engine's output, the page, storage or the network.

Run:  python3 tests/fixtures/make_fixtures.py   (idempotent; output is committed)
"""

import os

HERE = os.path.dirname(os.path.abspath(__file__))
CANARY = "CANARY-ZQ7X"


def w(rel, data):
    p = os.path.join(HERE, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    with open(p, "wb") as f:
        f.write(data)


def tr(*cells, th=False):
    tag = "th" if th else "td"
    out = []
    for c in cells:
        if isinstance(c, tuple):  # (text, colspan)
            out.append(f'<{tag} colspan="{c[1]}">{c[0]}</{tag}>')
        else:
            out.append(f"<{tag}>{c}</{tag}>")
    return "<tr>" + "".join(out) + "</tr>\n"


def title(t, span=14):
    return f'<tr><th colspan="{span}"><div style="font: 10pt Tahoma"><b>{t}</b></div></th></tr>\n'


def mt5_header_block():
    # MT5 report header (broker, account number, owner name): must never be read.
    return (title("Trade History Report")
            + tr(("Name:", 3), (f"<b>{CANARY} Owner Name</b>", 11), th=True)
            + tr(("Account:", 3), (f"<b>{CANARY} 99887766 (USD, Demo, Hedge)</b>", 11), th=True)
            + tr(("Company:", 3), (f"<b>{CANARY} Broker Ltd</b>", 11), th=True)
            + tr(("Date:", 3), ("<b>2026.09.30 18:00</b>", 11), th=True))


DEALS_HEAD = tr("Time", "Deal", "Symbol", "Type", "Direction", "Volume", "Price", "Order", "Commission", "Fee",
                "Swap", "Profit", "Balance", "Comment")
ORDERS_HEAD = tr("Open Time", "Order", "Symbol", "Type", "Volume", "Price", "S / L", "T / P", "Time", "State",
                 ("Comment", 4))


def html_doc(body):
    return ("<!DOCTYPE html>\n<html><head><meta http-equiv=\"Content-Type\" content=\"text/html; charset=utf-8\">"
            f"<title>{CANARY} 99887766: Trade History Report</title></head>\n<body>\n"
            '<table cellspacing="1" cellpadding="3" border="0">\n' + body + "</table>\n</body></html>\n")


def mt5_netting():
    b = mt5_header_block()
    b += title("Orders") + ORDERS_HEAD
    b += tr("2026.09.01 09:15:02", "2001", "EURUSD", "buy", "1.00 / 1.00", "market", "", "", "2026.09.01 09:15:02",
            "filled", (CANARY, 4))
    b += title("Deals") + DEALS_HEAD
    rows = [
        # time, deal, symbol, type, direction, volume, price, order, commission, fee, swap, profit, balance, comment
        ("2026.09.01 08:00:00", "1000", "", "balance", "", "", "", "", "0.00", "0.00", "0.00", "10 000.00",
         "10 000.00", f"{CANARY} deposit"),
        ("2026.09.01 09:15:02", "1001", "EURUSD", "buy", "in", "1.00", "1.08410", "2001", "-3.50", "0.00", "0.00",
         "0.00", "9 996.50", ""),
        ("2026.09.01 11:40:10", "1002", "EURUSD", "sell", "out", "0.50", "1.08610", "2002", "-1.75", "0.00",
         "0.00", "100.00", "10 094.75", "partial"),
        ("2026.09.01 14:02:55", "1003", "EURUSD", "sell", "out", "0.50", "1.08300", "2003", "-1.75", "0.00",
         "0.00", "-55.00", "10 038.00", CANARY),
        ("2026.09.02 08:01:00", "1004", "XAUUSD", "sell", "in", "0.10", "2501.20", "2004", "-1.00", "0.00", "0.00",
         "0.00", "10 037.00", "short"),
        ("2026.09.02 09:30:00", "1005", "XAUUSD", "buy", "out", "0.10", "2495.70", "2005", "-1.00", "0.00",
         "-0.20", "55.00", "10 090.80", ""),
        ("2026.09.03 10:00:00", "1006", "GBPUSD", "buy", "in", "1.00", "1.27000", "2006", "-3.50", "0.00", "0.00",
         "0.00", "10 087.30", ""),
        ("2026.09.03 12:00:00", "1007", "GBPUSD", "sell", "in/out", "2.00", "1.27500", "2007", "-7.00", "0.00",
         "0.00", "500.00", "10 580.30", "reversal"),
        ("2026.09.04 09:00:00", "1008", "GBPUSD", "buy", "out", "1.00", "1.26800", "2008", "-3.50", "0.00", "2.00",
         "700.00", "11 278.80", ""),
        ("2026.09.05 10:00:00", "1009", "USDJPY", "buy", "in", "1.00", "147.000", "2009", "0.00", "0.00", "0.00",
         "0.00", "11 278.80", ""),
        ("2026.09.08 10:00:00", "1010", "USDJPY", "sell", "out", "1.00", "147.100", "2010", "0.00", "0.00", "3.00",
         "68.00", "11 349.80", "swap credit"),
        ("2026.09.08 11:00:00", "1011", "EURUSD", "canceled buy", "", "1.00", "1.08000", "2011", "0.00", "0.00",
         "0.00", "0.00", "11 349.80", ""),
        ("2026.09.09 10:00:00", "1012", "EURUSD", "buy", "in", "0.30", "1.09000", "2012", "-1.05", "0.00", "0.00",
         "0.00", "11 348.75", "still open"),
    ]
    for r in rows:
        b += tr(*r)
    b += tr(("", 8), "-23.05", "0.00", "4.80", "1 368.00", ("", 2))  # totals row
    b += title("Summary") + tr(("Balance:", 3), ("11 348.75", 3), ("Equity:", 3), ("11 351.00", 5))
    return html_doc(b)


def mt5_netting_long(n=40):
    """deals_netting.htm's layout (canary header, balance row) with n plain round trips: a paid
    report needs at least 30 trades, so the browser paid-flow tests upload this one."""
    r = lcg(7)
    b = mt5_header_block() + title("Deals") + DEALS_HEAD
    b += tr("2026.09.01 08:00:00", "5000", "", "balance", "", "", "", "", "0.00", "0.00", "0.00", "10 000.00",
            "10 000.00", f"{CANARY} deposit")
    syms = [("EURUSD", 1.08), ("XAUUSD", 2500.0), ("GBPUSD", 1.27), ("USDJPY", 147.0)]
    for i in range(n):
        sym, base = syms[i % 4]
        day = 1 + i // 4
        win = r() < 0.5
        profit = round(20 + r() * 80, 2) * (1 if win else -1)
        hold_min = 10 + int(r() * 200)
        open_m = 9 * 60 + (i % 4) * 5
        close_m = open_m + hold_min
        t_open = f"2026.09.{day:02d} {open_m // 60:02d}:{open_m % 60:02d}:00"
        t_close = f"2026.09.{day:02d} {close_m // 60:02d}:{close_m % 60:02d}:00"
        side, back = ("buy", "sell") if i % 3 else ("sell", "buy")
        b += tr(t_open, str(5001 + 2 * i), sym, side, "in", "1.00", f"{base:.5f}", str(6001 + 2 * i), "-3.50",
                "0.00", "0.00", "0.00", "", "")
        b += tr(t_close, str(5002 + 2 * i), sym, back, "out", "1.00", f"{base * 1.001:.5f}", str(6002 + 2 * i),
                "-3.50", "0.00", "0.00", f"{profit:.2f}", "", CANARY if i == 0 else "")
    return html_doc(b)


POSITIONS_HEAD = tr("Time", "Position", "Symbol", "Type", "Volume", "Price", "S / L", "T / P", "Time", "Price",
                    "Commission", "Swap", "Profit", ("", 1))
OPEN_POS_HEAD = tr("Time", "Position", "Symbol", "Type", "Volume", "Price", "S / L", "T / P", "Market Price",
                   "Swap", "Profit", ("Comment", 3))

HEDGE_DEALS = [
    ("2026.09.01 08:00:00", "3000", "", "balance", "", "", "", "", "0.00", "0.00", "0.00", "5 000.00", "5 000.00",
     CANARY),
    ("2026.09.01 09:00:00", "3001", "EURUSD", "buy", "in", "1.00", "1.08000", "4001", "-3.50", "0.00", "0.00",
     "0.00", "4 996.50", ""),
    ("2026.09.01 10:00:00", "3002", "EURUSD", "sell", "in", "0.50", "1.08100", "4002", "-1.75", "0.00", "0.00",
     "0.00", "4 994.75", "hedge"),
    ("2026.09.01 12:00:00", "3003", "EURUSD", "buy", "out", "0.50", "1.08050", "4003", "-1.75", "0.00", "0.00",
     "25.00", "5 018.00", ""),
    ("2026.09.01 15:00:00", "3004", "EURUSD", "sell", "out", "1.00", "1.08200", "4004", "-3.50", "0.00", "0.00",
     "200.00", "5 214.50", ""),
    ("2026.09.02 09:00:00", "3005", "US500", "sell", "in", "2", "6600.0", "4005", "0.00", "0.00", "0.00", "0.00",
     "5 214.50", ""),
    ("2026.09.02 09:45:30", "3006", "US500", "buy", "out", "2", "6610.5", "4006", "0.00", "0.00", "-1.20",
     "-21.00", "5 192.30", ""),
]


def mt5_positions():
    b = mt5_header_block()
    b += title("Positions") + POSITIONS_HEAD
    b += tr("2026.09.01 09:00:00", "5001", "EURUSD", "buy", "1.00", "1.08000", "", "", "2026.09.01 15:00:00",
            "1.08200", "-7.00", "0.00", "200.00", "")
    b += tr("2026.09.01 10:00:00", "5002", "EURUSD", "sell", "0.50", "1.08100", "", "", "2026.09.01 12:00:00",
            "1.08050", "-3.50", "0.00", "25.00", "")
    b += tr("2026.09.02 09:00:00", "5003", "US500", "sell", "2", "6600.0", "", "", "2026.09.02 09:45:30", "6610.5",
            "0.00", "-1.20", "-21.00", "")
    b += title("Orders") + ORDERS_HEAD
    b += title("Deals") + DEALS_HEAD
    for r in HEDGE_DEALS:
        b += tr(*r)
    b += title("Open Positions") + OPEN_POS_HEAD
    b += tr("2026.09.03 09:00:00", "5004", "EURUSD", "buy", "0.20", "1.08500", "", "", "1.08600", "0.00", "20.00",
            (CANARY, 3))
    return html_doc(b)


def mt5_hedging_deals():
    b = mt5_header_block() + title("Deals") + DEALS_HEAD
    for r in HEDGE_DEALS[:5]:
        b += tr(*r)
    return html_doc(b)


def mt4_statement():
    head = tr("Ticket", "Open Time", "Type", "Size", "Item", "Price", "S / L", "T / P", "Close Time", "Price",
              "Commission", "Taxes", "Swap", "Profit")
    b = (f'<tr><td colspan="14"><b>{CANARY} Broker Ltd</b></td></tr>\n'
         + tr((f"<b>Account: {CANARY} 123456</b>", 3), (f"<b>Name: {CANARY}</b>", 5), ("<b>Currency: USD</b>", 3),
              ("<b>2026 September 30, 18:00</b>", 3)))
    b += f'<tr><td colspan="14"><b>Closed Transactions:</b></td></tr>\n' + head
    b += tr("1001", "2026.09.01 08:00", "balance", (f"Deposit {CANARY}", 10), "5 000.00")
    b += tr("1002", "2026.09.01 09:00", "buy", "1.00", "eurusd", "1.08000", "1.07500", "1.09000", "2026.09.01 13:30",
            "1.08350", "-7.00", "0.00", "0.00", "350.00")
    b += tr("1003", "2026.09.02 10:15", "sell", "0.50", "gbpusd", "1.27000", "0.00000", "0.00000",
            "2026.09.03 10:15", "1.27400", "-3.50", "0.00", "-1.10", "-200.00")
    b += tr("1004", "2026.09.03 11:00", "buy limit", "1.00", "eurusd", "1.07000", "0.00000", "0.00000",
            "2026.09.03 18:00", "1.08000", "", "", "", "")
    b += tr("1005", "2026.09.04 09:00", "buy", "0.10", "usdjpy", "147.000", "0.000", "0.000", "2026.09.07 09:00",
            "146.900", "0.00", "0.00", "1.50", "-6.80")
    b += tr(("", 10), "-10.50", "0.00", "0.40", "143.20")
    b += f'<tr><td colspan="14"><b>Open Trades:</b></td></tr>\n'
    b += tr("1006", "2026.09.08 09:00", "buy", "0.20", "eurusd", "1.08500", "0.00000", "0.00000", "", "1.08600",
            "0.00", "0.00", "0.00", "20.00")
    b += f'<tr><td colspan="14"><b>Working Orders:</b></td></tr>\n'
    b += tr("1007", "2026.09.08 10:00", "sell limit", "1.00", "eurusd", "1.09500", "0.00000", "0.00000", "",
            "1.08600", ("", 4))
    b += f'<tr><td colspan="14"><b>Summary:</b></td></tr>\n' + tr(("Deposit/Withdrawal:", 3), ("5 000.00", 11))
    return html_doc(b)


def lcg(seed):
    state = [seed]

    def r():
        state[0] = (state[0] * 1103515245 + 12345) % 2147483648
        return state[0] / 2147483648

    return r


def many_trades(n, seed, p_win, losers_longer=True):
    """n synthetic round trips, 4 per day, never overlapping on one symbol.
    Losers are held longer than winners when losers_longer, so the hold-gap check has something to find."""
    r = lcg(seed)
    lines = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    for i in range(n):
        day = 1 + i // 4
        start = 9 * 60 + 30 + (i % 4) * 100
        sym = ["SPY", "QQQ", "IWM"][i % 3]
        win = r() < p_win
        qty = 10 * (1 + int(r() * 5))
        entry = round(100 + r() * 50, 2)
        hold = (5 + int(r() * 30)) if win else ((20 if losers_longer else 5) + int(r() * (70 if losers_longer else 30)))
        move = round(0.2 + r() * 1.5, 2)
        long_ = r() < 0.7
        if long_:
            exit_ = round(entry + move, 2) if win else round(entry - move * 1.2, 2)
        else:
            exit_ = round(entry - move, 2) if win else round(entry + move * 1.2, 2)
        o_side, c_side = ("Buy", "Sell") if long_ else ("Sell", "Buy")
        end = start + hold
        d = f"2026-09-{day:02d}" if day <= 30 else f"2026-10-{day - 30:02d}"
        lines.append(f"{d},{start // 60:02d}:{start % 60:02d}:00,{sym},{o_side},{qty},{entry:.2f},USD,1.00")
        lines.append(f"{d},{end // 60:02d}:{end % 60:02d}:00,{sym},{c_side},{qty},{exit_:.2f},USD,1.00")
    return "\n".join(lines) + "\n"


def all_wins(n):
    lines = ["Date,Time,Symbol,Side,Quantity,Price,Currency,Fees"]
    for i in range(n):
        day = 1 + i // 4
        start = 9 * 60 + 30 + (i % 4) * 100
        d = f"2026-09-{day:02d}" if day <= 30 else f"2026-10-{day - 30:02d}"
        lines.append(f"{d},{start // 60:02d}:{start % 60:02d}:00,SPY,Buy,10,{100 + i:.2f},USD,0")
        lines.append(f"{d},{(start + 30) // 60:02d}:{(start + 30) % 60:02d}:00,SPY,Sell,10,{100.5 + i:.2f},USD,0")
    return "\n".join(lines) + "\n"


def main():
    w("mt5/deals_netting.htm", mt5_netting())
    w("mt5/positions_hedging.htm", mt5_positions())
    w("mt5/deals_hedging.htm", mt5_hedging_deals())
    # MT5 reports are often saved as UTF-16LE with a BOM (UNVERIFIED): same content, re-encoded.
    w("mt5/deals_netting_40.htm", mt5_netting_long())
    w("mt5/deals_netting_utf16.htm", b"\xff\xfe" + mt5_netting().encode("utf-16-le"))
    w("mt4/statement.htm", mt4_statement())

    w("mt5/deals.csv",
      "Time,Deal,Symbol,Type,Direction,Volume,Price,Order,Commission,Fee,Swap,Profit,Balance,Comment\n"
      "2026.09.01 09:15:02,1001,EURUSD,buy,in,1.00,1.08410,2001,-3.50,0.00,0.00,0.00,10000.00,\n"
      "2026.09.01 11:40:10,1002,EURUSD,sell,out,0.50,1.08610,2002,-1.75,0.00,0.00,100.00,10098.25,partial\n"
      "2026.09.01 14:02:55,1003,EURUSD,sell,out,0.50,1.08300,2003,-1.75,0.00,0.00,-55.00,10041.50,\n"
      "2026.09.02 08:01:00,1004,XAUUSD,sell,in,0.10,2501.20,2004,-1.00,0.00,0.00,0.00,10040.50,short\n")

    # IBKR Activity Flex, the field set from the IBKR Trades Flex reference (UNVERIFIED spellings).
    w("ibkr/activity_flex.csv",
      "CurrencyPrimary,AssetClass,Symbol,DateTime,Quantity,TradePrice,Buy/Sell,Open/CloseIndicator,Notes/Codes,"
      "ClosePrice,IBCommission,LevelOfDetail\n"
      "USD,STK,AAPL,20260902;093512,100,228.10,BUY,O,O,229.00,-1.00,EXECUTION\n"
      "USD,STK,TSLA,20260903;101500,-50,245.00,SELL,O,O,243.80,-1.00,EXECUTION\n"
      "CAD,STK,SHOP,20260904;100000,20,139.00,BUY,O,O,139.50,-1.00,EXECUTION\n"
      "USD,STK,AAPL,20260905;150101,-60,231.40,SELL,C,C;P,231.00,-0.60,EXECUTION\n"
      "CAD,STK,SHOP,20260905;150300,-20,140.25,SELL,C,C,139.90,-1.00,EXECUTION\n"
      "USD,STK,AAPL,20260906;100000,-40,231.00,SELL,C,C,231.20,-0.40,EXECUTION\n"
      "USD,STK,TSLA,20260907;110000,50,240.00,BUY,C,C,240.50,-1.00,EXECUTION\n")
    # IBKR Trade Confirmation Flex, the field names an open-source importer expects
    # (TradeNote), plus FX rate and realized P&L. Newest-first on purpose.
    w("ibkr/trade_confirm_fx.csv",
      "ClientAccountID,AccountAlias,CurrencyPrimary,AssetClass,Symbol,Date/Time,Quantity,Price,Buy/Sell,Code,"
      "Commission,FifoPnlRealized,FXRateToBase,Multiplier,LevelOfDetail\n"
      f"{CANARY},{CANARY} alias,USD,STK,TSLA,20260908;100000,10,245.00,BUY,O,-1.00,0,1,1,EXECUTION\n"
      f"{CANARY},{CANARY} alias,CAD,STK,SHOP,20260905;150300,20,139.90,BUY,C,-1.00,5.00,0.74,1,EXECUTION\n"
      f"{CANARY},{CANARY} alias,USD,STK,AAPL,20260905;150101,-100,231.40,SELL,C;P,-0.60,328.40,1,1,EXECUTION\n"
      f"{CANARY},{CANARY} alias,CAD,STK,SHOP,20260903;101500,-20,140.25,SELL,O,-1.00,0,0.73,1,EXECUTION\n"
      f"{CANARY},{CANARY} alias,USD,STK,AAPL,20260902;093512,100,228.10,BUY,O,-1.00,0,1,1,ORDER\n"
      f"{CANARY},{CANARY} alias,USD,STK,AAPL,20260902;093512,100,228.10,BUY,O,-1.00,0,1,1,EXECUTION\n")

    # Tradovate Orders: column names from third-party importer docs (UNVERIFIED).
    # Leading spaces in " Buy" / " Filled" mirror what one importer strips.
    w("tradovate/orders.csv",
      "orderId,Account,Order ID,B/S,Contract,Product,Product Description,avgPrice,filledQty,Fill Time,Status,"
      "Date,Quantity,Type,Limit Price,Stop Price,Filled Qty,Avg Fill Price\n"
      f"9001,{CANARY},9001, Buy,MNQZ6,MNQ,Micro E-mini Nasdaq-100,21010.25,2,09/15/2026 09:31:04, Filled,"
      "09/15/2026,2,Market,,,2,21010.25\n"
      f"9002,{CANARY},9002, Sell,MNQZ6,MNQ,Micro E-mini Nasdaq-100,21030.00,1,09/15/2026 09:48:40, Filled,"
      "09/15/2026,1,Limit,21030.00,,1,21030.00\n"
      f"9003,{CANARY},9003, Sell,MNQZ6,MNQ,Micro E-mini Nasdaq-100,20995.50,1,09/15/2026 10:12:09, Filled,"
      "09/15/2026,1,Stop,,20995.50,1,20995.50\n"
      f"9004,{CANARY},9004, Sell,MESZ6,,Micro E-mini S&P 500,6620.25,1,09/15/2026 10:30:00, Filled,"
      "09/15/2026,1,Market,,,1,6620.25\n"
      f"9005,{CANARY},9005, Buy,MESZ6,,Micro E-mini S&P 500,6610.00,1,09/15/2026 11:00:00, Filled,"
      "09/15/2026,1,Market,,,1,6610.00\n"
      f"9006,{CANARY},9006, Buy,MNQZ6,MNQ,Micro E-mini Nasdaq-100,,0,, Canceled,09/15/2026,1,Limit,20900.00,,0,\n"
      f"9007,{CANARY},9007, Buy,XYZZ6,,Unknown contract,100.00,1,09/15/2026 12:00:00, Filled,"
      "09/15/2026,1,Market,,,1,100.00\n"
      f"9008,{CANARY},9008, Sell,XYZZ6,,Unknown contract,101.50,1,09/15/2026 12:30:00, Filled,"
      "09/15/2026,1,Market,,,1,101.50\n")

    basic = ("Date,Time,Symbol,Side,Quantity,Price,Currency,Fees\n"
             "2026-09-01,09:35:05,SPY,Buy,100,560.20,USD,1.00\n"
             "2026-09-03,10:02:11,SPY,Sell,40,566.10,USD,0.40\n"
             "2026-09-04,13:20:00,QQQ,Sell,30,480.00,USD,0.30\n"
             "2026-09-08,15:45:30,SPY,Sell,60,552.75,USD,0.60\n")
    w("generic/basic.csv", basic)
    w("generic/basic_utf16.csv", b"\xff\xfe" + basic.replace("\n", "\r\n").encode("utf-16-le"))
    w("generic/short_reversal_adds.csv",
      "Date,Time,Symbol,Side,Quantity,Price,Fees\n"
      "2026-09-01,10:00:00,ABC,Sell,10,50.00,1.00\n"
      "2026-09-01,11:00:00,ABC,Buy,15,48.00,1.50\n"
      "2026-09-02,09:30:00,ABC,Sell,5,49.00,0.50\n"
      "2026-09-03,09:00:00,XYZ,B,2,10.00,0\n"
      "2026-09-03,09:10:00,XYZ,S,1,12.00,0\n"
      "2026-09-03,09:20:00,XYZ,B,1,11.00,0\n"
      "2026-09-03,09:30:00,XYZ,S,2,13.00,0\n")
    # Semicolon-delimited, decimal commas, space / NBSP / thin-space thousands, UTF-8 BOM.
    w("generic/eu_thousands.csv", ("﻿Date;Time;Symbol;Side;Quantity;Price;Currency;Fees\n"
                                   "2026-09-01;09:30:00;BRK;Buy;2;1 234,50;USD;1,00\n"
                                   "2026-09-02;10:00:00;BRK;Sell;2;\"1 240,25\";USD;1,00\n"
                                   "2026-09-03;10:00:00;BRK;Buy;1;1 230,00;USD;0,5\n"
                                   "2026-09-03;11:00:00;BRK;Sell;1;1.229,50;USD;0,5\n"))
    w("generic/mixed_currency.csv",
      "Date,Time,Symbol,Side,Quantity,Price,Currency,Fees\n"
      "2026-09-01,10:00:00,SPY,Buy,10,500.00,USD,0\n"
      "2026-09-01,11:00:00,SPY,Sell,10,505.00,USD,0\n"
      "2026-09-02,10:00:00,RY,Buy,10,170.00,CAD,0\n"
      "2026-09-02,11:00:00,RY,Sell,10,171.00,CAD,0\n"
      "2026-09-03,10:00:00,QQQ,Buy,5,480.00,USD,0\n"
      "2026-09-03,11:00:00,QQQ,Sell,5,478.00,USD,0\n")

    # >= 30 trades so the permutation checks run (not "not enough trades to tell").
    w("generic/ninety_trades.csv", many_trades(90, 20261020, 0.5))
    w("generic/no_losses.csv", all_wins(35))

    w("generic_roundtrip/tradezella.csv",
      "Open Time,Close Time,Symbol,Direction,Volume,Open Price,Close Price,Fees\n"
      "2026-09-01 09:30:00,2026-09-01 10:15:30,NVDA,Long,50,120.10,121.00,1.00\n"
      "2026-09-02 13:00:00,2026-09-03 09:45:00,AMD,Short,30,160.00,162.50,0.60\n")

    # ---- error fixtures (one named code each)
    w("errors/empty.csv", b"")
    w("errors/blank_lines.csv", "\n\n  \n")
    w("errors/header_only.csv", "Date,Time,Symbol,Side,Quantity,Price\n")
    w("errors/one_execution.csv", "Date,Time,Symbol,Side,Quantity,Price\n2026-09-01,10:00:00,SPY,Buy,1,500\n")
    w("errors/unknown_format.csv", "colour,shape,size\nred,round,3\n")
    w("errors/missing_price.csv", "Date,Time,Symbol,Side,Quantity\n2026-09-01,10:00:00,SPY,Buy,1\n")
    w("errors/bad_date.csv", "Date,Time,Symbol,Side,Quantity,Price\n2026-13-01,10:00:00,SPY,Buy,1,500\n")
    w("errors/ambiguous_date.csv", "Date,Time,Symbol,Side,Quantity,Price\n03/04/2026,10:00:00,SPY,Buy,1,500\n"
                                   "03/05/2026,10:00:00,SPY,Sell,1,501\n")
    w("errors/ambiguous_number.csv", "Date;Time;Symbol;Side;Quantity;Price\n"
                                     "2026-09-01;10:00:00;SPY;Buy;1;1,234\n2026-09-02;10:00:00;SPY;Sell;1;1,240\n")
    w("errors/not_a_number.csv", "Date,Time,Symbol,Side,Quantity,Price\n2026-09-01,10:00:00,SPY,Buy,1,$500\n")
    w("errors/excel.xlsx", b"PK\x03\x04" + b"\x14\x00\x06\x00" + b"\x00" * 40)
    w("errors/binary.csv", b"Date,Time\x00\x01\x02,Symbol\n" + bytes(range(1, 30)))
    w("errors/html_no_table.htm", html_doc(title("Deals") + tr("colour", "shape", "size") + tr("red", "round", "3")))
    w("errors/mt5_header_only.htm", html_doc(mt5_header_block() + title("Deals") + DEALS_HEAD))


if __name__ == "__main__":
    main()
