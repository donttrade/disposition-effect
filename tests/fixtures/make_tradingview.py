#!/usr/bin/env python3
"""Writes the TradingView Order History fixtures (synthetic: every order below is made up).

Only the header structure (column names and order, "yyyy-mm-dd HH:MM:SS" times, newest
first, empty Commission, Numbers/Excel-style "123.0" floats) copies a real export; no row
does. Unread columns (Level ID) hold the canary, which must never reach any output.
Hand oracles: oracles.py. Run: python3 tests/fixtures/make_tradingview.py
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
CANARY = "CANARY-ZQ7X"
HEAD = ["Symbol", "Side", "Type", "Quantity", "Limit price", "Stop price", "Fill price", "Status", "Commission",
        "Placing time", "Closing time", "Order ID", "Level ID", "Leverage", "Margin"]


def w(rel, data):
    p = os.path.join(HERE, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "wb") as f:
        f.write(data if isinstance(data, bytes) else data.encode("utf-8"))


# (symbol, side, type, qty, limit, stop, fill, status, commission, placed, closed) in time order.
ORDERS = [
    ("NASDAQ:AAPL", "Buy", "Market", "10", "", "", "230.50", "Filled", "1.00", "2026-09-14 09:31:10", "2026-09-14 09:31:10"),
    ("NASDAQ:AAPL", "Sell", "Limit", "5", "232.00", "", "232.00", "Filled", "0.50", "2026-09-14 09:40:00", "2026-09-14 10:05:00"),
    ("NASDAQ:AAPL", "Sell", "Limit", "5", "233.00", "", "233.00", "Filled", "0.50", "2026-09-14 09:40:05", "2026-09-14 11:20:30"),
    ("NASDAQ:TSLA", "Sell", "Market", "4", "", "", "250.00", "Filled", "", "2026-09-14 13:00:00", "2026-09-14 13:00:00"),
    ("NASDAQ:TSLA", "Buy", "Stop", "4", "", "245.00", "245.00", "Filled", "", "2026-09-14 13:01:00", "2026-09-14 14:30:00"),
    ("NASDAQ:TSLA", "Buy", "Limit", "4", "240.00", "", "", "Rejected", "", "2026-09-14 15:00:00", "2026-09-14 15:00:00"),
    ("NYSE:KO", "Buy", "Market", "100", "", "", "60.00", "Filled", "1.00", "2026-09-15 09:45:00", "2026-09-15 09:45:00"),
    ("NYSE:KO", "Buy", "Market", "50", "", "", "59.00", "Filled", "1.00", "2026-09-15 10:15:00", "2026-09-15 10:15:00"),
    ("NYSE:KO", "Sell", "Limit", "150", "63.00", "", "", "Cancelled", "", "2026-09-15 10:16:00", "2026-09-15 11:00:00"),
    ("NYSE:KO", "Sell", "Market", "150", "", "", "61.00", "Filled", "1.50", "2026-09-15 15:50:00", "2026-09-15 15:50:00"),
    ("AMEX:SPY", "Buy", "Market", "10", "", "", "500.00", "Filled", "", "2026-09-16 09:30:00", "2026-09-16 09:30:00"),
    ("AMEX:SPY", "Sell", "Market", "20", "", "", "505.00", "Filled", "2.00", "2026-09-16 10:00:00", "2026-09-16 10:00:00"),
    ("AMEX:SPY", "Buy", "Market", "10", "", "", "503.00", "Filled", "", "2026-09-16 11:00:00", "2026-09-16 11:00:00"),
    ("AMEX:SPY", "Buy", "Limit", "5", "495.00", "", "", "Canceled", "", "2026-09-16 11:05:00", "2026-09-16 12:00:00"),
    ("BINANCE:BTCUSDT", "Buy", "Market", "0.015", "", "", "60000.50", "Filled", "0.9", "2026-09-16 20:00:00", "2026-09-16 20:00:00"),
    ("BINANCE:BTCUSDT", "Sell", "Market", "0.015", "", "", "60500.25", "Filled", "0.9075", "2026-09-17 02:15:00", "2026-09-17 02:15:00"),
    ("BINANCE:BTCUSDT", "Sell", "Market", "0.015", "", "", "", "Rejected", "", "2026-09-17 03:00:00", "2026-09-17 03:00:00"),
    ("FX:EURUSD", "Sell", "Market", "10000", "", "", "1.08750", "Filled", "", "2026-09-17 08:00:00", "2026-09-17 08:00:00"),
    ("NASDAQ:MSFT", "Sell", "Market", "6", "", "", "410.00", "Filled", "0.30", "2026-09-17 09:35:00", "2026-09-17 09:35:00"),
    ("NASDAQ:MSFT", "Buy", "Limit", "2", "405.00", "", "405.00", "Filled", "0.30", "2026-09-17 09:36:00", "2026-09-17 10:40:00"),
    ("FX:EURUSD", "Buy", "Limit", "10000", "1.08500", "", "1.08500", "Filled", "", "2026-09-17 08:01:00", "2026-09-17 12:30:00"),
    ("NASDAQ:MSFT", "Buy", "Limit", "4", "400.00", "", "400.00", "Filled", "0.30", "2026-09-17 09:36:30", "2026-09-17 13:10:00"),
    ("NASDAQ:AMD", "Buy", "Market", "20", "", "", "150.00", "Filled", "1.00", "2026-09-18 09:40:00", "2026-09-18 09:40:00"),
    ("NASDAQ:AMD", "Sell", "Stop", "20", "", "140.00", "", "Rejected", "", "2026-09-18 10:00:00", "2026-09-18 10:00:00"),
    ("NASDAQ:AMD", "Sell", "Market", "20", "", "", "145.00", "Filled", "1.00", "2026-09-18 11:40:00", "2026-09-18 11:40:00"),
    ("NASDAQ:AMD", "Buy", "Limit", "10", "130.00", "", "", "Expired", "", "2026-09-18 11:41:00", "2026-09-18 12:00:00"),
    ("NASDAQ:AAPL", "Buy", "Market", "5", "", "", "228.00", "Filled", "0.50", "2026-09-18 13:00:00", "2026-09-18 13:00:00"),
    ("NASDAQ:AAPL", "Sell", "Market", "5", "", "", "229.20", "Filled", "0.50", "2026-09-18 15:30:00", "2026-09-18 15:30:00"),
    ("NASDAQ:NVDA", "Buy", "Market", "3", "", "", "120.00", "Filled", "", "2026-09-18 15:55:00", "2026-09-18 15:55:00"),
]


def orders_csv():
    lines = [",".join(HEAD)]
    # Newest first, as the History tab lists them.
    rows = sorted(enumerate(ORDERS), key=lambda x: (x[1][10], x[0]), reverse=True)
    for k, (i, o) in enumerate(rows):
        lev = "" if o[0].startswith("FX:") else "1:1"
        margin = f"{float(o[3]) * float(o[6] or 0):.2f} USD" if o[7] == "Filled" else ""
        level = CANARY if k % 7 == 0 else ""
        lines.append(",".join(list(o) + [str(3469300000 + 37 * i), level, lev, margin]))
    return "\n".join(lines) + "\n"


def numbers_bom_csv():
    """As re-saved from Apple Numbers / Excel: BOM, CRLF, every cell quoted, "10.0" floats,
    17-digit fill prices, times without seconds."""
    rows = [
        ("NASDAQ:TSLA", "Sell", "Market", "4.0", "", "", "246.00000000000003", "Filled", "", "2026-09-21 14:00", "2026-09-21 14:00"),
        ("NASDAQ:TSLA", "Buy", "Market", "4.0", "", "", "244.99999999999997", "Filled", "", "2026-09-21 13:00", "2026-09-21 13:00"),
        ("NASDAQ:TSLA", "Buy", "Limit", "4.0", "240.0", "", "", "Rejected", "", "2026-09-21 12:30", "2026-09-21 12:30"),
        ("NYSE:KO", "Buy", "Market", "50.0", "", "", "60.7", "Filled", "", "2026-09-21 11:45", "2026-09-21 11:45"),
        ("NYSE:KO", "Sell", "Market", "50.0", "", "", "61.2", "Filled", "", "2026-09-21 11:00", "2026-09-21 11:00"),
        ("NASDAQ:AAPL", "Sell", "Market", "10.0", "", "", "231.75", "Filled", "", "2026-09-21 10:02", "2026-09-21 10:02"),
        ("NASDAQ:AAPL", "Buy", "Market", "10.0", "", "", "230.5", "Filled", "", "2026-09-21 09:31", "2026-09-21 09:31"),
    ]
    q = lambda cells: ",".join('"' + c + '"' for c in cells)
    lines = [q(HEAD)]
    for i, o in enumerate(rows):
        lines.append(q(list(o) + [f"{3469363293 + i}.0", CANARY if i == 0 else "", "1:1", ""]))
    return b"\xef\xbb\xbf" + ("\r\n".join(lines) + "\r\n").encode("utf-8")


def semicolon_comma_csv():
    """A locale with ";" separators and decimal commas."""
    rows = [
        ("XETR:BMW", "Buy", "Market", "20", "", "", "79,60", "Filled", "0,50", "2026-09-23 12:00:00", "2026-09-23 12:00:00"),
        ("XETR:BMW", "Sell", "Market", "20", "", "", "80,10", "Filled", "0,50", "2026-09-23 10:00:00", "2026-09-23 10:00:00"),
        ("XETR:SAP", "Sell", "Limit", "10", "203,25", "", "203,25", "Filled", "1,00", "2026-09-22 09:06:00", "2026-09-22 15:20:00"),
        ("XETR:SAP", "Buy", "Market", "10", "", "", "201,50", "Filled", "1,00", "2026-09-22 09:05:00", "2026-09-22 09:05:00"),
    ]
    lines = [";".join(HEAD)]
    for i, o in enumerate(rows):
        lines.append(";".join(list(o) + [str(5100000000 + i), CANARY if i == 1 else "", "1:1", "1.612,00 EUR"]))
    return "\n".join(lines) + "\n"


SYMS = [("NASDAQ:AAPL", 230.0), ("NYSE:KO", 60.0), ("AMEX:SPY", 500.0), ("NASDAQ:MSFT", 410.0)]


def history(seed, n_trades=40, numbers=False, semicolon=False, bom=False, crlf=False, no_seconds=False,
            junk=True):
    """A made-up order history: n_trades closed round trips (long or short, some closed in two
    parts) on four symbols, plus Rejected/Cancelled rows when junk. Variants: numbers ("10.0"
    floats, every cell quoted), semicolon (";" and decimal commas), bom, crlf, no_seconds."""
    state = seed * 2654435761 % 2 ** 32 or 1

    def rnd():
        nonlocal state
        state = (1103515245 * state + 12345) % 2 ** 31
        return state / 2 ** 31

    orders = []
    t = 1789372800  # 2026-09-14 08:00, read as naive time
    for i in range(n_trades):
        sym, base = SYMS[int(rnd() * len(SYMS))]
        t += 3600 * (1 + int(rnd() * 20))
        long_ = rnd() < 0.6
        qty = 1 + int(rnd() * 20)
        entry = round(base * (0.9 + 0.2 * rnd()), 2)
        exit_ = round(entry * (0.97 + 0.06 * rnd()), 2)
        fee = "" if rnd() < 0.3 else f"{0.01 * (1 + int(rnd() * 200)):.2f}"
        o, c = ("Buy", "Sell") if long_ else ("Sell", "Buy")
        orders.append((sym, o, qty, entry, fee, t))
        if junk and rnd() < 0.25:
            orders.append((sym, c, qty, round(entry * 1.1, 2), "", t + 30, "Rejected" if rnd() < 0.5 else "Cancelled"))
        hold = 60 * (1 + int(rnd() * 600))
        if qty > 1 and rnd() < 0.4:
            part = qty // 2
            orders.append((sym, c, part, exit_, fee, t + hold // 2))
            orders.append((sym, c, qty - part, round(exit_ * 1.001, 2), fee, t + hold))
        else:
            orders.append((sym, c, qty, exit_, fee, t + hold))
        t += hold

    def ts(sec):
        import datetime as dt
        d = dt.datetime(1970, 1, 1) + dt.timedelta(seconds=sec)
        return d.strftime("%Y-%m-%d %H:%M" if no_seconds else "%Y-%m-%d %H:%M:%S")

    def num(x):
        s = (f"{x:.1f}" if numbers and isinstance(x, int) else str(x)) if not isinstance(x, str) else x
        return s.replace(".", ",") if semicolon else s

    sep = ";" if semicolon else ","
    quote = (lambda s: '"' + s + '"') if numbers else (lambda s: s)
    lines = [sep.join(quote(h) for h in HEAD)]
    for k, od in sorted(enumerate(orders), key=lambda x: (x[1][5], x[0]), reverse=True):
        sym, side, qty, price, fee, sec = od[:6]
        status = od[6] if len(od) > 6 else "Filled"
        fill = num(price) if status == "Filled" else ""
        oid = f"{3469300000 + k}.0" if numbers else str(3469300000 + k)
        cells = [sym, side, "Market", num(qty), "", "", fill, status, num(fee) if fee else "", ts(sec - 5), ts(sec),
                 oid, CANARY if k % 11 == 0 else "", "1:1", ""]
        lines.append(sep.join(quote(c) for c in cells))
    eol = "\r\n" if crlf else "\n"
    data = (eol.join(lines) + eol).encode("utf-8")
    return (b"\xef\xbb\xbf" + data) if bom else data


def main():
    w("tradingview/orders.csv", orders_csv())
    # 40 closed trades, nothing skipped: enough for the paid report (the server needs 30).
    w("tradingview/forty_trades.csv", history(7, junk=False))
    w("tradingview/numbers_bom.csv", numbers_bom_csv())
    w("tradingview/semicolon_comma.csv", semicolon_comma_csv())
    head = ",".join(HEAD)
    # Excel re-typed the times as m/d/yyyy: day and month cannot be told apart.
    w("errors/tradingview_slash_date.csv",
      head + "\nNASDAQ:AAPL,Sell,Market,10,,,231.00,Filled,,9/14/2026 10:05,9/14/2026 10:05,3469300001,,1:1,\n"
      "NASDAQ:AAPL,Buy,Market,10,,,230.50,Filled,,9/14/2026 9:31,9/14/2026 9:31,3469300000,,1:1,\n")
    # No Closing time column: the fill time is unknown.
    w("errors/tradingview_no_closing_time.csv",
      ",".join(h for h in HEAD if h != "Closing time") + "\n"
      "NASDAQ:AAPL,Buy,Market,10,,,230.50,Filled,,2026-09-14 09:31:10,3469300000,,1:1,\n")


if __name__ == "__main__":
    main()
