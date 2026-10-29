#!/usr/bin/env python3
"""Writes the universal-importer fixtures (plan §4): every row is made up here.

    python3 tests/fixtures/make_mapped.py

  mapped/<name>.<ext> + <name>.map.json   a file read through a mapping the user made
  presets/<name>.<ext>                    a file a shipped preset reads (no mapping file)
  paste/<name>.txt [+ <name>.map.json]    a pasted table (with no map: known formats, then presets)
  multi/<case>/1.*, 2.* [+ map.json]      several files read together (*.paste.txt = a paste)
  auto/<name>                             one file, known formats only (zip and xlsx messages)
  guess/<name>.csv                        files only the column guess (mapping.js) reads

Heading structures, date and number styles copy the public column lists named in PROVENANCE.txt;
no row of any real export is used. Every account, name, user, wallet and note cell holds the
canary CANARY-ZQ7X, which must never appear in any output.
"""
import datetime as dt
import io
import json
import os
import shutil
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
CANARY = "CANARY-ZQ7X"
DIRS = ["mapped", "presets", "paste", "multi", "auto", "guess"]


def put(rel, data):
    path = os.path.join(HERE, rel)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if isinstance(data, str):
        data = data.encode("utf-8")
    with open(path, "wb") as f:
        f.write(data)


def put_map(rel, mapping):
    put(rel, json.dumps(mapping, indent=1, sort_keys=True) + "\n")


def csv_line(cells, delim=","):
    out = []
    for c in cells:
        c = str(c)
        if delim in c or '"' in c or "\n" in c:
            c = '"' + c.replace('"', '""') + '"'
        out.append(c)
    return delim.join(out)


def table(header, rows, delim=",", eol="\n"):
    return eol.join(csv_line(r, delim) for r in [header] + rows) + eol


def trades(n, start, syms=("AAA", "BBB", "CCC"), gap_min=37, hold_min=23, base=100.0):
    """n made-up round trips: (open_dt, close_dt, symbol, long?, qty, entry, exit)."""
    out = []
    t = start
    for i in range(n):
        sym = syms[i % len(syms)]
        long_ = i % 3 != 1
        qty = 1 + (i * 7) % 5
        entry = round(base + (i * 13) % 17 + 0.25 * (i % 4), 2)
        move = ((i * 11) % 9 - 4) * 0.5 or 0.75
        exit_ = round(entry + move, 2)
        close = t + dt.timedelta(minutes=hold_min + (i % 4) * 5)
        out.append((t, close, sym, long_, qty, entry, exit_))
        t = t + dt.timedelta(minutes=gap_min + (i % 5) * 3)
        if t.hour >= 15:
            t = (t + dt.timedelta(days=1)).replace(hour=9, minute=31)
    return out


def fills(rts):
    """Round trips → fills in time order: (dt, symbol, side, qty, price)."""
    out = []
    for o, c, sym, long_, qty, en, ex in rts:
        out.append((o, sym, "buy" if long_ else "sell", qty, en))
        out.append((c, sym, "sell" if long_ else "buy", qty, ex))
    out.sort(key=lambda f: f[0])
    return out


def mdy(d, ampm=False, sec=True):
    h = d.hour
    if ampm:
        hh = h % 12 or 12
        return f"{d.month}/{d.day}/{d.year} {hh}:{d.minute:02d}:{d.second:02d} {'PM' if h >= 12 else 'AM'}"
    return f"{d.month:02d}/{d.day:02d}/{d.year} {h:02d}:{d.minute:02d}" + (f":{d.second:02d}" if sec else "")


def dmy(d):
    return f"{d.day:02d}/{d.month:02d}/{d.year} {d.hour:02d}:{d.minute:02d}:{d.second:02d}"


def iso(d, sep=" "):
    return d.strftime("%Y-%m-%d" + sep + "%H:%M:%S")


def epoch_ms(d):
    return int((d - dt.datetime(1970, 1, 1)).total_seconds()) * 1000 + 123


def excel(d):
    days = (d - dt.datetime(1899, 12, 30)).total_seconds() / 86400
    return f"{days:.6f}".rstrip("0").rstrip(".")


def mapping(layout, header, cols, date_format, header_row=0, **kw):
    """A mapping as the mapper screen would build it, from heading names."""
    from_names = {}
    norm = [norm_header(h) for h in header]
    for f, name in cols.items():
        if isinstance(name, list):
            from_names[f] = [norm.index(norm_header(x)) for x in name]
        elif isinstance(name, int):
            from_names[f] = name
        else:
            from_names[f] = norm.index(norm_header(name))
    full = {f: None for f in ["date", "time", "symbol", "side", "qty", "price", "fees", "currency", "status",
                              "open_time", "close_time", "direction", "open_price", "close_price", "pnl"]}
    full.update(from_names)
    used = []
    for v in full.values():
        if v is None:
            continue
        used += v if isinstance(v, list) else [v]
    m = {"v": 1, "layout": layout, "header_row": header_row, "delimiter": None, "cols": full,
         "headers": {str(i): norm[i] for i in sorted(set(used))}, "side_from": "column", "side_values": None,
         "status_values": None, "date_format": date_format, "number_style": None, "futures_sizes": False,
         "currency": None, "preset": None}
    m.update(kw)
    return m


def norm_header(h):
    import re
    return re.sub(r"[^a-z0-9]", "", " ".join(str(h).split()).lower())


# ----------------------------------------------------------------- mapped/

def mapped_fixtures():
    start = dt.datetime(2026, 3, 2, 9, 31, 5)
    # A Fidelity-like history: title lines, blank lines, heading on line 7, date-only, $ cells,
    # cash rows, legal footer. Read through a user mapping (the preset comes in B7).
    rts = trades(12, start)
    hdr = ["Run Date", "Account", "Action", "Symbol", "Description", "Quantity", "Price ($)", "Commission ($)",
           "Fees ($)", "Amount ($)"]
    rows = []
    for d, sym, side, q, p in fills(rts):
        act = ("YOU BOUGHT " if side == "buy" else "YOU SOLD ") + sym + " (Cash)"
        qty = q if side == "buy" else -q
        rows.append([d.strftime("%m/%d/%Y"), CANARY, act, sym, f"{sym} INC COM", qty, f"${p:,.2f}", "",
                     "$0.03" if side == "sell" else "", f"(${p * q:,.2f})" if side == "buy" else f"${p * q:,.2f}"])
    rows.insert(5, ["03/09/2026", CANARY, "DIVIDEND RECEIVED AAA (Cash)", "AAA", "AAA INC COM", "", "", "", "", "$4.10"])
    rows.insert(9, ["03/10/2026", CANARY, "Electronic Funds Transfer Received (Cash)", "", "No Description", "", "",
                    "", "", "$1,000.00"])
    text = "Brokerage\nAccount history for " + CANARY + "\n\n\n\n\n" + table(hdr, rows)
    text += "\n\n\"The data and information in this spreadsheet is provided to you solely for your use, is not for distribution.\"\n"
    text += "\"Brokerage services are provided by a made-up firm.\"\n"
    put("mapped/fidelity_like.csv", text)
    put_map("mapped/fidelity_like.map.json", mapping(
        "fills", hdr, {"date": "Run Date", "symbol": "Symbol", "side": "Action", "qty": "Quantity",
                       "price": "Price ($)", "fees": ["Commission ($)", "Fees ($)"]}, "mdy", header_row=6,
        side_values=None, side_rules=[["contains", "you bought", "buy"], ["contains", "you sold", "sell"]],
        side_default="skip", currency="USD"))

    # Mapping errors: a blocked column, a heading that moved, a required field left out, no date form.
    small_hdr = ["Date", "Account", "Symbol", "Side", "Qty", "Price"]
    small_rows = []
    for d, sym, side, q, p in fills(trades(4, start)):
        small_rows.append([iso(d), CANARY, sym, side.title(), q, p])
    put("mapped/blocked_column.csv", table(small_hdr, small_rows))
    m = mapping("fills", small_hdr, {"date": "Date", "symbol": "Account", "side": "Side", "qty": "Qty", "price": "Price"},
                "ymd")
    put_map("mapped/blocked_column.map.json", m)
    put("mapped/stale_heading.csv", table(small_hdr, small_rows))
    m = mapping("fills", small_hdr, {"date": "Date", "symbol": "Symbol", "side": "Side", "qty": "Qty", "price": "Price"},
                "ymd")
    m["headers"][str(small_hdr.index("Qty"))] = "quantity"
    put_map("mapped/stale_heading.map.json", m)
    put("mapped/missing_price.csv", table(small_hdr, small_rows))
    m = mapping("fills", small_hdr, {"date": "Date", "symbol": "Symbol", "side": "Side", "qty": "Qty"}, "ymd")
    put_map("mapped/missing_price.map.json", m)
    put("mapped/no_date_format.csv", table(small_hdr, small_rows))
    m = mapping("fills", small_hdr, {"date": "Date", "symbol": "Symbol", "side": "Side", "qty": "Qty", "price": "Price"},
                None)
    put_map("mapped/no_date_format.map.json", m)
    put("mapped/header_only.csv", table(small_hdr, []))
    put_map("mapped/header_only.map.json", mapping("fills", small_hdr, {"date": "Date", "symbol": "Symbol",
                                                   "side": "Side", "qty": "Qty", "price": "Price"}, "ymd"))

    # Dates: ISO and slash mixed in one column; 31/12 under month-first; AM/PM with zone labels;
    # Excel serials (and one before 1900-03-01); epoch seconds and milliseconds; microseconds and Z.
    basic_hdr = ["Date", "Symbol", "Side", "Qty", "Price"]
    basic_cols = {"date": "Date", "symbol": "Symbol", "side": "Side", "qty": "Qty", "price": "Price"}

    def basic(name, fmt_cell, date_format, n=10, extra_rows=None, **kw):
        rows = [[fmt_cell(d), sym, side.title(), q, p] for d, sym, side, q, p in fills(trades(n, start))]
        if extra_rows:
            for at, r in extra_rows:
                rows.insert(at, r)
        put(f"mapped/{name}.csv", table(basic_hdr, rows))
        put_map(f"mapped/{name}.map.json", mapping("fills", basic_hdr, basic_cols, date_format, **kw))

    basic("mixed_iso_and_slash", lambda d: mdy(d) if d.day % 2 else iso(d), "mdy")
    basic("dmy_date_under_mdy", lambda d: dmy(d.replace(day=31, month=12)) if d.minute % 7 == 0 else mdy(d), "mdy")
    basic("ampm_zone_labels", lambda d: mdy(d, ampm=True) + " EDT", "mdy")
    basic("excel_serial", excel, "excel")
    basic("excel_serial_before_1900_march", excel, "excel", extra_rows=[(3, ["59.5", "AAA", "Buy", "1", "100"])])
    basic("epoch_seconds", lambda d: str(epoch_ms(d) // 1000), "epoch_s")
    basic("epoch_milliseconds", lambda d: str(epoch_ms(d)), "epoch_ms")
    basic("iso_micro_z", lambda d: d.strftime("%Y-%m-%dT%H:%M:%S") + ".123456Z", "ymd")
    basic("iso_offsets", lambda d: iso(d) + ("+02:00" if d.minute % 2 else " UTC"), "ymd")
    basic("two_digit_years", lambda d: f"{d.day}.{d.month}.{d.year % 100} {d.hour}:{d.minute:02d}", "dmy")
    basic("yyyymmdd_and_time_column", lambda d: d.strftime("%Y%m%d"), "ymd")
    # (that one has no time column: a date-only file read as ymd)

    # A separate Time column, and two columns both headed "Time".
    hdr = ["Time", "Time", "Symbol", "Side", "Qty", "Price"]
    rows = [[d.strftime("%Y-%m-%d"), d.strftime("%H:%M:%S"), sym, side.title(), q, p]
            for d, sym, side, q, p in fills(trades(8, start))]
    put("mapped/duplicate_headings.csv", table(hdr, rows))
    put_map("mapped/duplicate_headings.map.json", mapping("fills", hdr, {"date": 0, "time": 1, "symbol": "Symbol",
                                                          "side": "Side", "qty": "Qty", "price": "Price"}, "ymd"))

    # Numbers: thousands separators, a lone 1,234 (no style / dot / comma), semicolon CSV with
    # decimal commas, 1.500 with no evidence, money forms.
    hdr = ["Date", "Symbol", "Side", "Qty", "Price"]
    rows = [[iso(d), sym, side.title(), q, f"{p * 20:,.2f}"] for d, sym, side, q, p in fills(trades(8, start))]
    put("mapped/thousands_separators.csv", table(hdr, rows))
    put_map("mapped/thousands_separators.map.json", mapping("fills", hdr, basic_cols, "ymd"))
    lone_rows = [[iso(d), sym, side.title(), q, f"{int(p * 20):,d}"] for d, sym, side, q, p in fills(trades(8, start))]
    for name, style in (("lone_comma_no_style", None), ("lone_comma_dot", "dot"), ("lone_comma_comma", "comma")):
        put(f"mapped/{name}.csv", table(hdr, lone_rows))
        put_map(f"mapped/{name}.map.json", mapping("fills", hdr, basic_cols, "ymd", number_style=style))
    rows = [[iso(d), sym, side.title(), q, f"{p:.2f}".replace(".", ",")] for d, sym, side, q, p in fills(trades(8, start))]
    put("mapped/semicolon_decimal_comma.csv", table(hdr, rows, delim=";"))
    put_map("mapped/semicolon_decimal_comma.map.json", mapping("fills", hdr, basic_cols, "ymd", delimiter=";"))
    rows = [[iso(d), sym, side.title(), q, f"{int(p) * 15}.{(i * 125) % 1000:03d}" if i % 2 else f"1.{500 + i}"]
            for i, (d, sym, side, q, p) in enumerate(fills(trades(6, start)))]
    rows = [[r[0], r[1], r[2], r[3], "1.500" if i % 2 else "1.250"] for i, r in enumerate(rows)]
    put("mapped/semicolon_dot3_no_style.csv", table(hdr, rows, delim=";"))
    put_map("mapped/semicolon_dot3_no_style.map.json", mapping("fills", hdr, basic_cols, "ymd"))
    put("mapped/semicolon_dot3_comma_style.csv", table(hdr, rows, delim=";"))
    put_map("mapped/semicolon_dot3_comma_style.map.json", mapping("fills", hdr, basic_cols, "ymd", number_style="comma"))
    hdr = ["Date", "Symbol", "Quantity", "Price", "Fees"]
    fee_forms = ["(1.30)", "1.30-", "−1.30", "$1.30", "-$1.30", "1.30 USD", "USD 1.30", "€1,30"]
    rows = []
    for i, (d, sym, side, q, p) in enumerate(fills(trades(8, start))):
        qty = f"({q})" if side == "sell" else str(q)
        rows.append([iso(d), sym, qty, f"${p * 20:,.2f}", fee_forms[i % 7]])
    put("mapped/money_forms_sign_mode.csv", table(hdr, rows))
    put_map("mapped/money_forms_sign_mode.map.json", mapping(
        "fills", hdr, {"date": "Date", "symbol": "Symbol", "qty": "Quantity", "price": "Price", "fees": ["Fees"]},
        "ymd", side_from="sign"))

    # Encodings: the same file as UTF-8, UTF-8 BOM, UTF-16LE with and without BOM, Windows-1252.
    hdr = ["Date", "Symbol", "Side", "Qty", "Price", "Description"]
    rows = [[iso(d), sym, side.title(), q, p, "Société générale café"] for d, sym, side, q, p in fills(trades(6, start))]
    base = table(hdr, rows)
    enc_map = mapping("fills", hdr, basic_cols, "ymd")
    for name, data in (("enc_utf8", base.encode("utf-8")), ("enc_utf8_bom", b"\xef\xbb\xbf" + base.encode("utf-8")),
                       ("enc_utf16le_bom", b"\xff\xfe" + base.encode("utf-16-le")),
                       ("enc_utf16le_nobom", base.encode("utf-16-le")), ("enc_cp1252", base.encode("cp1252"))):
        put(f"mapped/{name}.csv", data)
        put_map(f"mapped/{name}.map.json", enc_map)

    # A tab-separated log with a title and blank lines above the heading (heading on line 7).
    hdr = ["DateTime", "Symbol", "BuySell", "FilledQuantity", "FillPrice"]
    rows = [[iso(d) + ".000250", "ESZ6", side.title(), q, f"{5800 + p:.2f}"] for d, sym, side, q, p in fills(trades(6, start))]
    put("mapped/tab_heading_on_line_7.txt", "Trade Activity Log\nFor " + CANARY + "\n\n\n\n\n" + table(hdr, rows, delim="\t"))
    put_map("mapped/tab_heading_on_line_7.map.json", mapping(
        "fills", hdr, {"date": "DateTime", "symbol": "Symbol", "side": "BuySell", "qty": "FilledQuantity",
                       "price": "FillPrice"}, "ymd", header_row=6, delimiter="\t", futures_sizes=True))

    # Robinhood-like: multi-line quoted Description with commas (not read), $ and ( ) amounts,
    # option and cash codes skipped, date-only, newest first.
    hdr = ["Activity Date", "Process Date", "Settle Date", "Instrument", "Description", "Trans Code", "Quantity",
           "Price", "Amount"]
    rows = []
    for d, sym, side, q, p in reversed(fills(trades(10, start, gap_min=60 * 24 * 3, hold_min=60 * 24 * 2))):
        desc = f"{sym} Inc\nCUSIP: 0000{q}, Class A"
        amt = f"(${p * q:,.2f})" if side == "buy" else f"${p * q:,.2f}"
        rows.append([f"{d.month}/{d.day}/{d.year}", f"{d.month}/{d.day}/{d.year}", f"{d.month}/{d.day}/{d.year}", sym,
                     desc, "Buy" if side == "buy" else "Sell", q, f"${p:,.2f}", amt])
    rows.insert(2, ["3/5/2026", "3/5/2026", "3/5/2026", "AAA", "Cash Div: R/D 2026-03-01", "CDIV", "", "", "$1.20"])
    rows.insert(4, ["3/4/2026", "3/4/2026", "3/6/2026", "AAA", "AAA 4/17/2026 Call $110.00", "BTO", "1", "$2.10",
                    "($210.04)"])
    text = table(hdr, rows) + '\n"The data provided is for informational purposes only. Please consult a professional tax service."\n'
    put("mapped/robinhood_like_newest_first.csv", text)
    put_map("mapped/robinhood_like_newest_first.map.json", mapping(
        "fills", hdr, {"date": "Activity Date", "symbol": "Instrument", "side": "Trans Code", "qty": "Quantity",
                       "price": "Price"}, "mdy",
        side_values={"buy": "buy", "sell": "sell", "cdiv": "skip", "bto": "skip", "stc": "skip"}, currency="USD"))

    # Side values: one value left unmapped (bad_side), one mapped to skip (not_a_trade).
    hdr = ["Date", "Symbol", "Action", "Qty", "Price"]
    rows = [[iso(d), sym, "Bought" if side == "buy" else "Sold", q, p] for d, sym, side, q, p in fills(trades(8, start))]
    rows.insert(3, [iso(start), "AAA", "Journal", "", ""])
    rows.insert(6, [iso(start), "AAA", "Interest", "", "0"])
    rows.insert(7, [iso(start), "AAA", "Stock split", "2", "0"])
    put("mapped/side_unmapped_and_skip.csv", table(hdr, rows))
    put_map("mapped/side_unmapped_and_skip.map.json", mapping(
        "fills", hdr, {"date": "Date", "symbol": "Symbol", "side": "Action", "qty": "Qty", "price": "Price"}, "ymd",
        side_values={"bought": "buy", "sold": "sell", "journal": "skip", "interest": "skip"}))

    # Sign mode: -10, +10 and 0.
    hdr = ["When", "Ticker", "Shares", "Fill"]
    rows = []
    for d, sym, side, q, p in fills(trades(8, start)):
        rows.append([iso(d), sym, f"-{q}" if side == "sell" else f"+{q}", p])
    rows.insert(4, [iso(start), "AAA", "0", "100"])
    put("mapped/sign_mode.csv", table(hdr, rows))
    put_map("mapped/sign_mode.map.json", mapping(
        "fills", hdr, {"date": "When", "symbol": "Ticker", "qty": "Shares", "price": "Fill"}, "ymd", side_from="sign"))

    # Date-only and newest first: a buy and a sell of one symbol on one date must give a long.
    hdr = ["Trade Date", "Symbol", "Side", "Qty", "Price"]
    rows = []
    day = dt.datetime(2026, 4, 1)
    for i in range(30):
        d = day + dt.timedelta(days=i)
        sym = ["AAA", "BBB"][i % 2]
        rows.append([d.strftime("%Y-%m-%d"), sym, "Buy", 10, 100 + i])
        rows.append([d.strftime("%Y-%m-%d"), sym, "Sell", 10, 101 + i - (i % 3)])
    newest = []
    for i in range(0, len(rows), 2):
        newest = [rows[i], rows[i + 1]] + newest
    # newest first: each date's rows stay in their own order (sell above buy), as a newest-first export lists them
    newest2 = []
    for i in range(0, len(newest), 2):
        newest2 += [newest[i + 1], newest[i]]
    put("mapped/dates_only_newest_first.csv", table(hdr, newest2))
    put_map("mapped/dates_only_newest_first.map.json", mapping(
        "fills", hdr, {"date": "Trade Date", "symbol": "Symbol", "side": "Side", "qty": "Qty", "price": "Price"}, "ymd"))

    # Round trips with a P/L column whose sign is flipped on two rows; a direction value to skip.
    hdr = ["Opened", "Closed", "Market", "Long/Short", "Size", "Entry", "Exit", "Costs", "P/L", "Notes"]
    rows = []
    for i, (o, c, sym, long_, q, en, ex) in enumerate(trades(10, start)):
        pl = (ex - en) * q * (1 if long_ else -1)
        if i in (2, 5):
            pl = -pl
        rows.append([iso(o), iso(c), sym, "Long" if long_ else "Short", q, en, ex, "0.50", f"{pl:.2f}", CANARY])
    rows.insert(4, [iso(start), iso(start), "AAA", "Transfer", "", "", "", "", "", CANARY])
    put("mapped/roundtrip_pnl_sign.csv", table(hdr, rows))
    put_map("mapped/roundtrip_pnl_sign.map.json", mapping(
        "roundtrips", hdr, {"open_time": "Opened", "close_time": "Closed", "symbol": "Market",
                            "direction": "Long/Short", "qty": "Size", "open_price": "Entry", "close_price": "Exit",
                            "fees": ["Costs"], "pnl": "P/L"}, "ymd",
        side_values={"long": "buy", "short": "sell", "transfer": "skip"}))

    # One row per order: statuses kept and skipped, a cancelled order that filled part of its size.
    hdr = ["Order Time", "Contract", "B/S", "Filled", "Avg Price", "State", "Commission"]
    rows = []
    for d, sym, side, q, p in fills(trades(10, start, syms=("MNQZ6", "ESZ6"))):
        rows.append([iso(d), sym, side.title(), q, f"{p * 50:.2f}", "Filled", "1.04"])
    rows.insert(2, [iso(start), "ESZ6", "Buy", "0", "", "Rejected", ""])
    rows.insert(5, [iso(start), "ESZ6", "Sell", "0", "", "Cancelled", ""])
    rows.insert(7, [iso(start), "ESZ6", "Buy", "0", "", "Working", ""])
    rows[9][5] = "Cancelled"   # partly filled before the cancel: still a fill of that part
    put("mapped/orders_status.csv", table(hdr, rows))
    put_map("mapped/orders_status.map.json", mapping(
        "orders", hdr, {"date": "Order Time", "symbol": "Contract", "side": "B/S", "qty": "Filled",
                        "price": "Avg Price", "status": "State", "fees": ["Commission"]}, "ymd",
        status_values={"filled": "keep", "rejected": "skip", "cancelled": "skip", "working": "skip"},
        keep_partial=True, futures_sizes=True))

    # Futures sizes with a root not in the table (points), and a file-wide currency for the rest.
    hdr = ["Time", "Instrument", "Action", "Quantity", "Price"]
    rows = [[iso(d), sym, side.title(), q, f"{p * 40:.2f}"]
            for d, sym, side, q, p in fills(trades(9, start, syms=("ES 12-26", "MNQ 12-26", "ZB 12-26")))]
    put("mapped/futures_sizes_unknown_root.csv", table(hdr, rows))
    put_map("mapped/futures_sizes_unknown_root.map.json", mapping(
        "fills", hdr, {"date": "Time", "symbol": "Instrument", "side": "Action", "qty": "Quantity", "price": "Price"},
        "ymd", futures_sizes=True))
    hdr = ["Date", "Symbol", "Side", "Qty", "Price"]
    rows = [[iso(d), sym, side.title(), q, p] for d, sym, side, q, p in fills(trades(6, start))]
    put("mapped/file_wide_currency.csv", table(hdr, rows))
    put_map("mapped/file_wide_currency.map.json", mapping("fills", hdr, basic_cols, "ymd", currency="EUR"))

    # An HTML statement with three tables (summary, open positions, history): table 2 is mapped.
    hist = "".join(f"<tr><td>{iso(o)}</td><td>{iso(c)}</td><td>{sym}</td><td>{'Buy' if long_ else 'Sell'}</td>"
                   f"<td>{q}</td><td>{en}</td><td>{ex}</td></tr>" for o, c, sym, long_, q, en, ex in trades(8, start))
    html = ("<html><body><h1>Statement</h1><table><tr><td>Name</td><td>" + CANARY + "</td></tr>"
            "<tr><td>Account</td><td>" + CANARY + "</td></tr></table>"
            "<table><tr><th>Symbol</th><th>Volume</th></tr><tr><td>AAA</td><td>1</td></tr></table>"
            "<table><tr><th>Open</th><th>Close</th><th>Symbol</th><th>Side</th><th>Volume</th><th>Open price</th>"
            "<th>Close price</th></tr>" + hist + "</table></body></html>")
    put("mapped/html_three_tables.htm", html)
    h = ["Open", "Close", "Symbol", "Side", "Volume", "Open price", "Close price"]
    put_map("mapped/html_three_tables.map.json", mapping(
        "roundtrips", h, {"open_time": "Open", "close_time": "Close", "symbol": "Symbol", "direction": "Side",
                          "qty": "Volume", "open_price": "Open price", "close_price": "Close price"}, "ymd",
        header_row=4, source={"kind": "html", "table": 2}))

    # A thinkorswim-style statement: cash, orders, then Account Trade History, then positions.
    tos_hdr = ["", "Exec Time", "Spread", "Side", "Qty", "Pos Effect", "Symbol", "Exp", "Strike", "Type", "Price",
               "Net Price", "Order Type"]
    lines = ["Account Statement for " + CANARY, "", "Cash Balance",
             "DATE,TIME,TYPE,REF #,DESCRIPTION,Misc Fees,Commissions & Fees,AMOUNT,BALANCE",
             "3/2/26,09:00:00,BAL,,Cash balance,,,,\"10,000.00\"", "", "Account Order History",
             ",Notes,,Time Placed,Spread,Side,Qty,Pos Effect,Symbol,Exp,Strike,Type,PRICE,,TIF,Status",
             ",,,3/2/26 09:31:00,STOCK,BUY,+5,TO OPEN,AAA,,,STOCK,100.00,LMT,DAY,FILLED", "",
             "Account Trade History", csv_line(tos_hdr)]
    hdr_line = len(lines)
    for d, sym, side, q, p in fills(trades(8, start)):
        lines.append(csv_line(["", d.strftime("%-m/%-d/%y %H:%M:%S"), "STOCK", side.upper(),
                               f"+{q}" if side == "buy" else f"-{q}", "TO OPEN" if side == "buy" else "TO CLOSE",
                               sym, "", "", "STOCK", p, p, "LMT"]))
    lines += ["", "Equities", "Symbol,Description,Qty,Trade Price,Mark,Mark Value",
              "AAA,AAA INC,10,100.00,101.00,\"1,010.00\""]
    put("mapped/tos_like_sections.csv", "\n".join(lines) + "\n")
    put_map("mapped/tos_like_sections.map.json", mapping(
        "fills", tos_hdr, {"date": "Exec Time", "symbol": "Symbol", "side": "Side", "qty": "Qty", "price": "Price"},
        "mdy", header_row=hdr_line - 1, section=True, side_values={"buy": "buy", "sell": "sell"}))


# ----------------------------------------------------------------- presets/

def preset_fixtures():
    start = dt.datetime(2026, 3, 16, 9, 31, 5)
    # NinjaTrader 8 executions (columns from the official Executions tab list). Day 16+ shows the order.
    hdr = ["Instrument", "Action", "Quantity", "Price", "Time", "ID", "E/X", "Position", "Order ID", "Name",
           "Commission", "Rate", "Account Display Name", "Connection"]
    rows = []
    pos = 0
    for i, (d, sym, side, q, p) in enumerate(fills(trades(12, start, syms=("ES 12-26", "MNQ 12-26")))):
        act = {"buy": ["Buy", "BuyToCover"][i % 2], "sell": ["Sell", "SellShort"][i % 2]}[side]
        pos += q if side == "buy" else -q
        rows.append([sym, act, q, f"{5800 + p:.2f}", mdy(d, ampm=True), f"{9000 + i}", "Entry" if i % 2 == 0 else "Exit",
                     f"{pos} L" if pos >= 0 else f"{-pos} S", f"{4000 + i}", CANARY, "$1.04", "1", CANARY, "Live"])
    put("presets/ninjatrader_exec.csv", table(hdr, rows))
    early = dt.datetime(2026, 3, 2, 9, 31, 5)
    rows2 = [[sym, side.title(), q, f"{5800 + p:.2f}", mdy(d, ampm=True), "1", "Entry", "1 L", "1", CANARY, "$1.04",
              "1", CANARY, "Live"] for d, sym, side, q, p in fills(trades(6, early, syms=("ES 12-26",)))]
    put("presets/ninjatrader_ambiguous_date.csv", table(hdr, rows2))

    # Trading 212 (field list from an open-source parser; spelling inferred).
    hdr = ["Action", "Time", "ISIN", "Ticker", "Name", "No. of shares", "Price / share", "Currency (Price / share)",
           "Exchange rate", "Result", "Currency (Result)", "Total", "Currency (Total)", "Notes", "ID"]
    rows = []
    for i, (d, sym, side, q, p) in enumerate(fills(trades(12, start))):
        act = ["Market buy", "Limit buy"][i % 2] if side == "buy" else ["Market sell", "Stop sell"][i % 2]
        rows.append([act, iso(d), "US0000000000", sym, CANARY, f"{q}.0000000000", f"{p:.4f}", "USD", "1.00000",
                     "", "GBP", f"{p * q:.2f}", "GBP", CANARY, f"EOF{1000 + i}"])
    rows.insert(0, ["Deposit", iso(start - dt.timedelta(days=1)), "", "", "", "", "", "", "", "", "", "1000.00", "GBP",
                    CANARY, "D1"])
    rows.insert(7, ["Dividend (Ordinary)", iso(start + dt.timedelta(days=1)), "US0000000000", "AAA", CANARY,
                    "10.0000000000", "0.2200", "USD", "1.00000", "", "", "2.20", "GBP", "", "V1"])
    rows.insert(9, ["Interest on cash", iso(start + dt.timedelta(days=1)), "", "", "", "", "", "", "", "", "", "0.12",
                    "GBP", "", "I1"])
    put("presets/trading212_history.csv", table(hdr, rows))

    # Kraken Trades export (official field list). UTC, fractional seconds, pairs.
    hdr = ["txid", "ordertxid", "pair", "time", "type", "ordertype", "price", "cost", "fee", "vol", "margin", "misc",
           "ledgers"]
    rows = [[f"T{i:05d}-ABCDE-FGHIJK", f"O{i:05d}-ABCDE-FGHIJK", sym,
             iso(d) + ".4321", side, "limit", f"{p * 600:.1f}", f"{p * 600 * q * 0.01:.5f}", f"{p * q * 0.016:.5f}",
             f"{q * 0.01:.8f}", "0.00000", "", f"L{i:05d}"]
            for i, (d, sym, side, q, p) in enumerate(fills(trades(10, start, syms=("XXBTZUSD", "XETHZUSD"))))]
    put("presets/kraken_trades.csv", table(hdr, rows))

    # Sierra Chart Trade Activity Log (official field names; tab-separated; microseconds). Its headings
    # also fit the generic template, which must not win.
    hdr = ["ActivityType", "DateTime", "TransDateTime", "Symbol", "OrderActionSource", "InternalOrderID",
           "ServiceOrderID", "OrderType", "Quantity", "BuySell", "Price", "Price2", "OrderStatus", "FillPrice",
           "FilledQuantity", "TradeAccount", "OpenClose", "PositionQuantity", "FillExecutionServiceID"]
    rows = []
    for i, (d, sym, side, q, p) in enumerate(fills(trades(10, start, syms=("ESZ26_FUT_CME",)))):
        stamp = iso(d) + f".{(i * 123457) % 1000000:06d}"
        rows.append(["Orders", stamp, stamp, sym, "Chart", str(500 + i), "", "Limit", q + 3, side.title(),
                     f"{5799 + p:.2f}", "", "Open", "", "", CANARY, "", "", ""])
        rows.append(["Fills", stamp, stamp, sym, "Chart", str(500 + i), f"S{i}", "Limit", q + 3, side.title(),
                     f"{5799 + p:.2f}", "", "Filled", f"{5800 + p:.2f}", q, CANARY, "Open" if i % 2 == 0 else "Close",
                     "0", f"E{i}"])
    put("presets/sierra_fills.txt", table(hdr, rows, delim="\t"))

    # Rithmic R|Trader Pro completed orders (columns from TradeZella's add-these list). Day 16+.
    hdr = ["Account", "Status", "Remarks", "Buy/Sell", "Qty To Fill", "Symbol", "Qty Filled", "Avg Fill Price",
           "Limit price", "Order Number", "Create Time", "Update Time", "Commission"]
    rows = []
    for i, (d, sym, side, q, p) in enumerate(fills(trades(10, start, syms=("MNQZ6", "ESZ6")))):
        rows.append([CANARY, "Filled", CANARY, "B" if side == "buy" else "S", q, sym, q, f"{20000 + p * 3:.2f}",
                     f"{20000 + p * 3:.2f}", f"R{i}", dmy(d - dt.timedelta(seconds=4)), dmy(d), "0.74"])
    rows.insert(3, [CANARY, "Cancelled", CANARY, "B", "2", "ESZ6", "0", "", "5800.00", "RX1", dmy(start), dmy(start), ""])
    rows.insert(6, [CANARY, "Rejected", CANARY, "S", "1", "ESZ6", "0", "", "5800.00", "RX2", dmy(start), dmy(start), ""])
    put("presets/rithmic_orders.csv", table(hdr, rows))

    # cTrader History (official on-screen column list): round trips; Gross checks the sign.
    hdr = ["Deal ID", "Symbol", "Opening direction", "Closing direction", "Opening time", "Closing time",
           "Entry price", "Closing price", "Closing quantity", "Closing volume", "Swap", "Commissions", "Pips",
           "Gross", "Net", "Label", "Comment", "Balance"]
    rows = []
    for i, (o, c, sym, long_, q, en, ex) in enumerate(trades(10, start, syms=("EURUSD", "GBPUSD"), base=1.08)):
        en, ex = round(1.08 + en / 1000, 5), round(1.08 + ex / 1000, 5)
        gross = (ex - en) * q * 1000 * (1 if long_ else -1)
        rows.append([f"{70000 + i}", sym, "Buy" if long_ else "Sell", "Sell" if long_ else "Buy", dmy(o), dmy(c),
                     f"{en:.5f}", f"{ex:.5f}", f"{q * 1000}", f"{q * 1000}", "-0.12", "-0.30", "1.0",
                     f"{gross:.2f}", f"{gross - 0.42:.2f}", "", CANARY, "10000.00"])
    put("presets/ctrader_history.csv", table(hdr, rows))
    # The same rows as the HTML statement's middle table.
    head = "".join(f"<th>{h}</th>" for h in hdr)
    body = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    html = ("<html><body><table><tr><td>Account</td><td>" + CANARY + "</td></tr><tr><td>Broker</td><td>Made-up</td></tr>"
            "</table><table><tr>" + head + "</tr>" + body + "</table><table><tr><th>Total</th><th>1.00</th></tr>"
            "</table></body></html>")
    put("presets/ctrader_statement.html", html)

    # Hyperliquid fills, with the API's field names: epoch milliseconds, then ISO.
    hdr = ["coin", "side", "px", "sz", "time", "fee", "feeToken", "dir", "closedPnl", "hash", "oid", "tid", "crossed",
           "startPosition"]
    rows = [[sym, "B" if side == "buy" else "A", f"{p * 30:.1f}", f"{q * 0.1:.4f}", str(epoch_ms(d)),
             f"{p * q * 0.0003:.6f}", "USDC", "Open Long" if side == "buy" else "Close Long", "0.0",
             "0x" + CANARY, str(i), str(i), "true", "0.0"]
            for i, (d, sym, side, q, p) in enumerate(fills(trades(10, start, syms=("BTC", "ETH"))))]
    put("presets/hyperliquid_fills.csv", table(hdr, rows))
    rows = [[r[0], r[1], r[2], r[3], iso(dt.datetime(1970, 1, 1) + dt.timedelta(milliseconds=int(r[4]))), *r[5:]]
            for r in rows]
    put("presets/hyperliquid_iso_times.csv", table(hdr, rows))


# ----------------------------------------------------------------- paste/

def paste_fixtures():
    start = dt.datetime(2026, 3, 16, 9, 31, 5)
    # DXtrade's Order History grid, copied with the page's menu and balance above it and a footer.
    hdr = ["Date and Time", "Symbol", "Status", "Side", "Filled Volume", "Fill Price", "Commission", "Take profit",
           "Stop loss"]
    rows = []
    for i, (d, sym, side, q, p) in enumerate(fills(trades(10, start, syms=("EURUSD", "XAUUSD")))):
        rows.append([dmy(d), sym, "Filled", side.title(), f"{q * 1000}", f"{1.08 + p / 1000:.5f}", "-0.30",
                     "", ""])
    rows.insert(4, [dmy(start), "EURUSD", "Cancelled", "Buy", "0", "", "", "1.10000", "1.07000"])
    rows.insert(7, [dmy(start), "EURUSD", "Rejected", "Sell", "0", "", "", "", ""])
    text = ("Trading Journal\tOrder History\tTrade History\n" + "Balance\t10,000.00 USD\tEquity\t10,012.40 USD\n\n" +
            "\n".join("\t".join(str(c) for c in r) for r in [hdr] + rows) + "\nShowing 1-10 of 10\n")
    put("paste/dxtrade_grid.txt", text)
    # The generic template, pasted as columns of 2+ spaces (a fixed-width grid).
    hdr = ["Date", "Time", "Symbol", "Side", "Quantity", "Price"]
    lines = ["  ".join(f"{c:<10}" for c in hdr)]
    for d, sym, side, q, p in fills(trades(8, start)):
        lines.append("  ".join(f"{c:<10}" for c in [d.strftime("%Y-%m-%d"), d.strftime("%H:%M:%S"), sym, side, q, p]))
    put("paste/spaced_columns.txt", "\n".join(lines) + "\n")
    put("paste/single_spaces_only.txt", "Date Time Symbol Side Quantity Price\n2026-03-16 09:31:05 AAA Buy 1 100\n")
    put("paste/one_value_per_line.txt", "Date\nSymbol\nSide\n2026-03-16\nAAA\nBuy\n")
    put("paste/empty.txt", "  \n\t\n  \n")
    # A TradeLocker-style History panel copied by hand: the user matches its columns.
    hdr = ["Instrument", "Side", "Amount", "Open Time", "Open Price", "Close Time", "Close Price", "Profit", "ID"]
    rows = [[sym, "buy" if long_ else "sell", q, iso(o), en, iso(c), ex, f"{(ex - en) * q * (1 if long_ else -1):.2f}", i]
            for i, (o, c, sym, long_, q, en, ex) in enumerate(trades(9, start))]
    text = "History\tPositions\tOrders\n" + "\n".join("\t".join(str(x) for x in r) for r in [hdr] + rows) + "\nTotal\t9\n"
    put("paste/tradelocker_like.txt", text)
    put_map("paste/tradelocker_like.map.json", mapping(
        "roundtrips", hdr, {"open_time": "Open Time", "close_time": "Close Time", "symbol": "Instrument",
                            "direction": "Side", "qty": "Amount", "open_price": "Open Price",
                            "close_price": "Close Price", "pnl": "Profit"}, "ymd", header_row=1, trim_ragged=True,
        side_values={"buy": "buy", "sell": "sell"}))


# ----------------------------------------------------------------- multi/

def multi_fixtures():
    start = dt.datetime(2026, 1, 5, 9, 31, 5)
    hdr = ["Date", "Time", "Symbol", "Side", "Quantity", "Price"]
    all_fills = fills(trades(30, start))
    rows = [[d.strftime("%Y-%m-%d"), d.strftime("%H:%M:%S"), sym, side.title(), q, p] for d, sym, side, q, p in all_fills]
    # Two overlapping exports: rows 0-39 and 20-59 (given newest file first, to test the time order).
    put("multi/overlap/1.csv", table(hdr, rows[20:]))
    put("multi/overlap/2.csv", table(hdr, rows[:40]))
    put("multi/one_file_for_comparison/1.csv", table(hdr, rows))
    # The same file picked twice.
    put("multi/same_file_twice/1.csv", table(hdr, rows[:30]))
    put("multi/same_file_twice/2.csv", table(hdr, rows[:30]))
    # Two identical fills inside one file survive; the other file holds one copy.
    dup = rows[:10] + [rows[9]] + rows[10:20]
    put("multi/identical_fills_in_one_file/1.csv", table(hdr, dup))
    put("multi/identical_fills_in_one_file/2.csv", table(hdr, rows[5:30]))
    # Two different platforms: the template and a TradingView export.
    put("multi/two_platforms/1.csv", table(hdr, rows[:20]))
    tv_hdr = ["Symbol", "Side", "Type", "Quantity", "Limit price", "Stop price", "Fill price", "Status", "Commission",
              "Placing time", "Closing time", "Order ID", "Level ID", "Leverage", "Margin"]
    tv_rows = [[f"NASDAQ:{sym}", side.title(), "Market", q, "", "", p, "Filled", "", iso(d), iso(d), str(i), "", "", ""]
               for i, (d, sym, side, q, p) in enumerate(all_fills[:20])]
    put("multi/two_platforms/2.csv", table(tv_hdr, tv_rows))
    # A bad cell in the second file: the error names file 2 and its own row.
    bad = [list(r) for r in rows[20:40]]
    bad[3][4] = "abc"
    put("multi/error_in_second_file/1.csv", table(hdr, rows[:20]))
    put("multi/error_in_second_file/2.csv", table(hdr, bad))
    # Two Fidelity-like yearly files through one mapping, overlapping by a few rows.
    fhdr = ["Run Date", "Action", "Symbol", "Quantity", "Price ($)", "Commission ($)"]
    frows = [[d.strftime("%m/%d/%Y"), ("YOU BOUGHT " if side == "buy" else "YOU SOLD ") + sym, sym,
              q if side == "buy" else -q, f"${p:,.2f}", ""] for d, sym, side, q, p in all_fills]
    put("multi/mapped_overlap/1.csv", "\n" + table(fhdr, frows[:34]))
    put("multi/mapped_overlap/2.csv", "\n" + table(fhdr, frows[28:]))
    put_map("multi/mapped_overlap/map.json", mapping(
        "fills", fhdr, {"date": "Run Date", "symbol": "Symbol", "side": "Action", "qty": "Quantity",
                        "price": "Price ($)", "fees": ["Commission ($)"]}, "mdy", header_row=1,
        side_rules=[["prefix", "you bought", "buy"], ["prefix", "you sold", "sell"]], currency="USD"))
    # The same mapping on a file of another platform: E_MIXED_FILES, not E_BAD_MAPPING.
    put("multi/mapped_other_platform/1.csv", "\n" + table(fhdr, frows[:20]))
    put("multi/mapped_other_platform/2.csv", table(hdr, rows[:20]))
    put_map("multi/mapped_other_platform/map.json", json.load(open(os.path.join(HERE, "multi/mapped_overlap/map.json"))))
    # Pasting page 1, then pages 1-2 again.
    phdr = ["Instrument", "Side", "Amount", "Open Time", "Open Price", "Close Time", "Close Price"]
    prts = [[sym, "buy" if long_ else "sell", q, iso(o), en, iso(c), ex]
            for o, c, sym, long_, q, en, ex in trades(16, start)]
    page = lambda rs: "\n".join("\t".join(str(x) for x in r) for r in [phdr] + rs) + "\n"
    put("multi/paste_pages/1.paste.txt", page(prts[:8]))
    put("multi/paste_pages/2.paste.txt", page(prts))
    put_map("multi/paste_pages/map.json", mapping(
        "roundtrips", phdr, {"open_time": "Open Time", "close_time": "Close Time", "symbol": "Instrument",
                             "direction": "Side", "qty": "Amount", "open_price": "Open Price",
                             "close_price": "Close Price"}, "ymd", trim_ragged=True))


# ----------------------------------------------------------------- auto/ and guess/

def zip_bytes(entries):
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w", zipfile.ZIP_DEFLATED) as z:
        for name, data in entries:
            z.writestr(zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0)), data, compress_type=zipfile.ZIP_DEFLATED)
    return b.getvalue()


def auto_fixtures():
    put("auto/workbook.xlsx", zip_bytes([("[Content_Types].xml", "<Types/>"), ("_rels/.rels", "<Relationships/>"),
                                         ("xl/workbook.xml", "<workbook/>"), ("xl/worksheets/sheet1.xml", "<worksheet/>")]))
    put("auto/export.zip", zip_bytes([("okx_trades_2026.csv", "Date,Time,Symbol,Side,Quantity,Price\n")]))


def guess_fixtures():
    start = dt.datetime(2026, 3, 2, 9, 31, 5)
    rts = trades(6, start)
    # A heading that is HTML, a duplicate heading, a blocked column holding the canary, day order ask.
    # (not first: a file starting with "<" is read as HTML, as it always has been)
    hdr = ["Date", "<img src=x onerror=alert(1)>", "Time", "Time", "Account", "Ticker", "Buy/Sell", "Qty", "Fill Price"]
    rows = [[d.strftime("%m/%d/%Y"), "<b>bold</b><script>alert(2)</script>", d.strftime("%H:%M:%S"), d.strftime("%H:%M:%S"), CANARY,
             sym, side.upper(), q, p] for d, sym, side, q, p in fills(rts)]
    put("guess/xss_and_duplicates.csv", table(hdr, rows))
    # Day-first and month-first in one column.
    hdr = ["Date", "Symbol", "Side", "Qty", "Price"]
    rows = [[("13/04/2026" if i == 2 else "04/13/2026" if i == 5 else mdy(d)), sym, side, q, p]
            for i, (d, sym, side, q, p) in enumerate(fills(rts))]
    put("guess/mixed_day_order.csv", table(hdr, rows))
    # An order-level file (status + avg fill + filled qty) and a round-trip file.
    hdr = ["Order ID", "Placed", "Filled At", "Symbol", "Side", "Filled Qty", "Avg Fill Price", "Status"]
    rows = [[i, iso(d), iso(d), sym, side.title(), q, p, "Filled"] for i, (d, sym, side, q, p) in enumerate(fills(rts))]
    put("guess/orders_layout.csv", table(hdr, rows))
    hdr = ["Symbol", "Direction", "Open Time", "Close Time", "Entry Price", "Exit Price", "Size", "P&L"]
    rows = [[sym, "Long" if long_ else "Short", iso(o), iso(c), en, ex, q, f"{(ex - en) * q:.2f}"]
            for o, c, sym, long_, q, en, ex in rts]
    put("guess/roundtrips_layout.csv", table(hdr, rows))
    # Hyperliquid-like A/B sides; BTO/STC options rows.
    hdr = ["Date", "Symbol", "Code", "Qty", "Price"]
    codes = ["Buy", "Sell", "BTO", "STC", "CDIV", "ACH", "Bought"]
    rows = [[iso(d), sym, codes[i % len(codes)], q, p] for i, (d, sym, side, q, p) in enumerate(fills(rts))]
    put("guess/side_values.csv", table(hdr, rows))
    # A file whose numbers hold only lone 1,234 cells (comma file, quoted).
    hdr = ["Date", "Symbol", "Side", "Qty", "Price"]
    rows = [[iso(d), sym, side, q, f"{int(p * 20):,d}"] for d, sym, side, q, p in fills(rts)]
    put("guess/lone_thousands.csv", table(hdr, rows))


def main():
    for d in DIRS:
        shutil.rmtree(os.path.join(HERE, d), ignore_errors=True)
    mapped_fixtures()
    preset_fixtures()
    paste_fixtures()
    multi_fixtures()
    auto_fixtures()
    guess_fixtures()


if __name__ == "__main__":
    main()
