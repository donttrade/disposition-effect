#!/usr/bin/env python3
"""Writes the importer Tester's round-2 files (TESTER-REPORT-IMPORTER-ENGINE-R2-2026-10-30) as
regression fixtures: tester2/ (one file or paste each) and tester2_multi/ (several, in order).

    python3 tests/fixtures/make_tester_r2.py [path to the Tester's imp-test folder]

The f2/ files and the blank-cell pastes of spec2/ are copied when the folder is given (they are in
the repo already otherwise); the variants the Tester built inside v3.mjs, v5.mjs, v6.mjs and
v7.mjs are rebuilt here line for line. Every row is made up by the Tester's scripts or by this one.
"""
import json
import os
import shutil
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "tester2")
MULTI = os.path.join(HERE, "tester2_multi")


def put(name, text, folder=OUT):
    os.makedirs(folder, exist_ok=True)
    with open(os.path.join(folder, name), "w", encoding="utf-8", newline="") as f:
        f.write(text)


def side(k):
    return "Sell" if k % 2 else "Buy"


def v3():
    rows = ["Date,Time,Symbol,Side,Qty,Price"]
    for k in range(8):
        rows.append(f"2026-03-{14 + k},09:30:05,AAPL,{side(k)},{'1,000' if k == 2 else '10'},150")
    put("w_one_refused_buy.csv", "\n".join(rows) + "\n")


def v5():
    h = "Date,Time,Symbol,Side,Qty,Price\n"

    def body(n=10):
        return "\n".join(f"2026-03-{14 + k},09:30:0{k % 10},EURUSD,{side(k)},{1 + k % 3},1.{10 + k}" for k in range(n))
    put("ft_total_fills.csv", h + body() + "\nTotal fills,20\n")
    put("ft_3cells_numbers.csv", h + body() + "\nTotal,20,1450.50\n")
    put("ft_4cells_date.csv", h + body() + "\nReport date,2026-10-29,Total,20\n")
    put("ft_5cells_dates.csv", h + body() + "\nFrom,2026-03-14,To,2026-03-23,x\n")
    put("ft_subtotal_midfile.csv", h + body(5) + "\nSubtotal,,,,3,450.00\n" + body(5).replace("2026-03-1", "2026-03-2") + "\n")
    put("ft_two_footers.csv", h + body() + "\nTotal fills,20\nGenerated,2026-10-29\n")
    put("ft_preamble_2cells.csv", "Report,Trades\nAccount holder,CANARY-ZQ7X\nFrom,2026-03-01\n" + h + body() + "\n")
    put("ft_preamble_dates.csv", "Period,2026-03-01 to 2026-03-31\nPrinted,2026-10-29 10:00:00\n\n" + h + body() + "\n")
    put("ft_tradelike_footer.csv", h + body() + "\n2026-03-30,09:30:00,\n")
    put("ft_disclaimer.csv", h + body() + '\n"Past performance, as always, is no guide, ok?"\nNote,see,terms,and,conditions,apply\n')


def v6():
    def mk(hdr, f):
        return ",".join(hdr) + "\n" + "\n".join(",".join(str(x) for x in f(k)) for k in range(8)) + "\n"

    def d(k):
        return f"2026-03-{14 + (k >> 1)}"
    put("du_00mmss_after_qty.csv", mk(["Date", "Symbol", "Side", "Qty", "Time", "Price"],
                                      lambda k: [d(k), "ES", side(k), 1, f"00:{10 + k}:05", 100 + k]))
    put("du_duration_header.csv", mk(["Date", "Time", "Symbol", "Side", "Qty", "Price", "Duration"],
                                     lambda k: [d(k), f"09:3{k}:00", "ES", side(k), 1, 100 + k, f"0{k % 4}:15:30"]))
    put("du_hours_1_to_5.csv", mk(["Date", "Symbol", "Side", "Qty", "Time", "Price"],
                                  lambda k: [d(k), "ES", side(k), 1, f"0{1 + k % 5}:15:30", 100 + k]))
    put("du_mmss.csv", mk(["Date", "Symbol", "Side", "Qty", "Time", "Price"],
                          lambda k: [d(k), "ES", side(k), 1, f"{10 + k}:05", 100 + k]))
    put("du_units.csv", mk(["Date", "Symbol", "Side", "Qty", "Time", "Price"],
                           lambda k: [d(k), "ES", side(k), 1, f"{k + 1}m 30s", 100 + k]))
    put("du_real_midnight_clock.csv", mk(["Date", "Time", "Symbol", "Side", "Qty", "Price"],
                                         lambda k: [d(k), f"00:{10 + k}:05", "ES", side(k), 1, 100 + k]))
    put("du_hours_decimal.csv", mk(["Date", "Symbol", "Side", "Qty", "Time", "Price"],
                                   lambda k: [d(k), "ES", side(k), 1, (k + 1) / 2, 100 + k]))
    off = "Date,Symbol,Side,Qty,Price\n2026-03-14T09:30:00-05:00,ES,Buy,1,100\n2026-03-14T10:30:00-04:00,ES,Sell,1,101\n"
    put("of_true_gap0.csv", off)
    put("of_sell_before_buy.csv", "Date,Symbol,Side,Qty,Price\n2026-03-14T09:30:00-05:00,ES,Buy,1,100\n"
                                  "2026-03-14T09:30:00-04:00,ES,Sell,1,101\n")
    put("of_same_plus1.csv", off.replace("-05:00", "+01:00").replace("-04:00", "+01:00"))
    put("of_z_rows.csv", off.replace("-05:00", "Z").replace("-04:00", "Z"))
    put("of_mixed_z_none.csv", "Date,Symbol,Side,Qty,Price\n2026-03-14T09:30:00Z,ES,Buy,1,100\n2026-03-14 10:30:00,ES,Sell,1,101\n")
    put("of_half_dateonly.csv", mk(["Date", "Symbol", "Side", "Qty", "Price"],
                                   lambda k: [d(k) if k % 2 else d(k) + " 10:" + str(10 + k) + ":00", "ES", side(k), 1, 100 + k]))
    put("y2_26_dmy.csv", mk(["Date", "Symbol", "Side", "Qty", "Price"],
                            lambda k: [f"{14 + (k >> 1)}/03/26 10:00:00", "ES", side(k), 1, 100 + k]))
    put("y2_70_dmy.csv", mk(["Date", "Symbol", "Side", "Qty", "Price"],
                            lambda k: [f"{14 + (k >> 1)}/03/70 10:00:00", "ES", side(k), 1, 100 + k]))
    put("y_iso_2099.csv", mk(["Date", "Symbol", "Side", "Qty", "Price"],
                             lambda k: [f"2099-03-{14 + (k >> 1)} 10:00:00", "ES", side(k), 1, 100 + k]))
    put("y_iso_2126.csv", mk(["Date", "Symbol", "Side", "Qty", "Price"],
                             lambda k: [f"2126-03-{14 + (k >> 1)} 10:00:00", "ES", side(k), 1, 100 + k]))


def v7():
    hdr = "Date                 Symbol      Side   Qty   Price\n"

    def row(k, sym="EURUSD"):
        return f"2026-03-{14 + k} 10:00:00  {sym.ljust(12)}{'Sell' if k % 2 else 'Buy '}   1     1.1{k}"
    def rows(f=lambda k, r: r):
        return "\n".join(f(k, row(k)) for k in range(8)) + "\n"
    put("pa_baseline.paste.txt", hdr + rows())
    put("pa_long_symbol.paste.txt", hdr + "\n".join(row(k, "BTCUSDT.PERPETUAL") for k in range(8)) + "\n")
    put("pa_indented.paste.txt", "   " + hdr + rows(lambda k, r: "   " + r))
    put("pa_shift_left_1.paste.txt", hdr + rows(lambda k, r: r[1:]))
    put("pa_shift_right_3.paste.txt", hdr + rows(lambda k, r: "   " + r))
    put("pa_one_drifting_row.paste.txt", hdr + rows(lambda k, r: " " + r if k == 3 else r))
    put("pa_trailing_footer.paste.txt", hdr + rows() + "Showing 1-8 of 20\n  Next >\n")
    import re
    put("pa_tab_header_space_rows.paste.txt", re.sub(r" {2,}", "\t", hdr) + rows())
    p1 = hdr + "\n".join(row(k) for k in range(6)) + "\n"
    p2 = hdr + "\n".join(row(k) for k in range(8)) + "\n"
    put("1.paste.txt", p1, os.path.join(MULTI, "pa_two_pages_overlap"))
    put("2.paste.txt", p2, os.path.join(MULTI, "pa_two_pages_overlap"))


def copy_tester_files(src):
    for name in sorted(os.listdir(os.path.join(src, "f2"))):
        shutil.copy(os.path.join(src, "f2", name), os.path.join(OUT, name))
    for name in ("pa_blank2", "pa_blankall", "pa_blanktp"):
        with open(os.path.join(src, "spec2", name + ".auto.json"), encoding="utf-8") as f:
            put(name + ".paste.txt", json.load(f)["items"][0]["paste"])


def main(argv):
    v3()
    v5()
    v6()
    v7()
    if argv:
        copy_tester_files(argv[0])


if __name__ == "__main__":
    main(sys.argv[1:])
