#!/usr/bin/env python3
"""donttrade trade-file engine: Python reference (standard library only).

This is the oracle the browser engine (site/static/js/engine/*.js) is tested
against. It implements the DATA MODEL of V2-BUILD-PLAN-2026-10-20 literally:
parsers, trade reconstruction, FreeStats and the free noise checks.

Rules that keep it identical to the JS engine:
  * Sums are plain left-to-right loops (`s += x`). Python 3.12+ `sum()` uses
    compensated summation, which JS does not, so `sum()` is never used on floats.
  * Regexes use re.ASCII so `\\d` means 0-9, as in JS.
  * One explicit whitespace class instead of `\\s`.
  * Dates are naive wall-clock times converted to ms as if UTC.
  * The PRNG is mulberry32 with 32-bit arithmetic, matching Math.imul.

Usage:
  python3 engine_ref.py FILE            # prints the ParseResult (+ stats) as JSON
  python3 engine_ref.py --expected DIR  # regenerates tests/fixtures/expected/*.json
"""

import json
import math
import os
import re
import sys
from html.parser import HTMLParser

MAX_BYTES = 50 * 1024 * 1024
MAX_ROWS = 200000

# ----------------------------------------------------------------- errors

MESSAGES = {
    "E_EMPTY": "The file is empty.",
    "E_HEADER_ONLY": "The file has column headings but no trade rows under them.",
    "E_UNKNOWN_FORMAT": "This file was not recognised.",
    "E_MISSING_COLUMN": "A required column is missing",
    "E_BAD_DATE": "A date or time could not be read",
    "E_AMBIGUOUS_DATE": "A date uses slashes. Write dates as yyyy-mm-dd.",
    "E_BAD_NUMBER": "A number could not be read",
    "E_ENCODING": "The file is not a text, CSV or HTML file that can be read.",
    "E_BAD_QUOTE": "A quote mark opens a cell that is never closed.",
    "E_TOO_LARGE": "The file is too large: the limit is 50 MB and 200,000 rows.",
    "E_NO_CLOSED_TRADES": "No closed trades were found.",
}


class EngineError(Exception):
    def __init__(self, code, detail="", row=None, column=None):
        super().__init__(f"{code}: {MESSAGES.get(code, code)} {detail}".strip())
        self.code = code
        self.row = row
        self.column = column

    def to_json(self):
        return {"code": self.code, "row": self.row, "column": self.column}


def fail(code, detail="", row=None, column=None):
    raise EngineError(code, detail, row, column)


def warning(code, n):
    return {"code": code, "n": n}


# ----------------------------------------------------------------- text helpers

WS_CHARS = "\t\n\x0b\x0c\r  " + "".join(chr(c) for c in range(0x2000, 0x200B)) + "  　"
WS_CLASS = "[" + re.escape(WS_CHARS) + "]"
_WS_RUN = re.compile(WS_CLASS + "+")


def clean(s):
    return _WS_RUN.sub(" ", str(s)).strip(WS_CHARS)


def norm_header(h):
    return re.sub(r"[^a-z0-9]", "", clean(h).lower())


# ----------------------------------------------------------------- decoding

def _cp1252_table():
    # WHATWG windows-1252: bytes undefined in cp1252 map to the same code point.
    t = []
    for b in range(256):
        try:
            t.append(bytes([b]).decode("cp1252"))
        except UnicodeDecodeError:
            t.append(chr(b))
    return t


_CP1252 = _cp1252_table()


def _sniff_utf16(b):
    m = min(len(b), 1000) & ~1
    if m < 4:
        return None
    z_odd = z_even = 0
    for i in range(m):
        if b[i] == 0:
            if i % 2:
                z_odd += 1
            else:
                z_even += 1
    half = m / 2
    if z_odd > 0.3 * half and z_even == 0:
        return "utf-16le"
    if z_even > 0.3 * half and z_odd == 0:
        return "utf-16be"
    return None


def decode_bytes(b):
    n = len(b)
    if n == 0:
        fail("E_EMPTY")
    if n > MAX_BYTES:
        fail("E_TOO_LARGE")
    if b[:4] == b"PK\x03\x04":
        fail("E_ENCODING", "xlsx/zip")
    start = 0
    if b[:3] == b"\xef\xbb\xbf":
        enc, start = "utf-8", 3
    elif b[:2] == b"\xff\xfe":
        enc, start = "utf-16le", 2
    elif b[:2] == b"\xfe\xff":
        enc, start = "utf-16be", 2
    else:
        enc = _sniff_utf16(b)
    body = b[start:]
    if enc in ("utf-16le", "utf-16be"):
        if len(body) % 2:
            fail("E_ENCODING", "odd UTF-16 length")
        try:
            text = body.decode("utf-16-le" if enc == "utf-16le" else "utf-16-be")
        except UnicodeDecodeError:
            fail("E_ENCODING", "bad UTF-16")
    elif enc == "utf-8":
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            fail("E_ENCODING", "bad UTF-8")
    else:
        try:
            text = body.decode("utf-8")
        except UnicodeDecodeError:
            text = "".join(_CP1252[x] for x in body)
    if text[:1] == "﻿":
        text = text[1:]
    if "\x00" in text:
        fail("E_ENCODING", "binary")
    if clean(text) == "":
        fail("E_EMPTY")
    return text


def is_html(text):
    head = text.lstrip(WS_CHARS)[:4096].lower()
    return head.startswith("<") or "<table" in head


# ----------------------------------------------------------------- CSV

def sniff_delimiter(text):
    line = ""
    for l in re.split(r"\r\n|\n|\r", text):
        if clean(l) != "":
            line = l
            break
    cands = [",", ";", "\t"]
    counts = [0, 0, 0]
    in_q = False
    for ch in line:
        if ch == '"':
            in_q = not in_q
        elif not in_q and ch in cands:
            counts[cands.index(ch)] += 1
    best = 0
    for k in (1, 2):
        if counts[k] > counts[best]:
            best = k
    return "," if counts[best] == 0 else cands[best]


def parse_csv(text, delim):
    """Mirrors parseCsv() in csv.js, including the stray-quote checks:
    a quoted cell open at the end of the file is E_BAD_QUOTE at the row it opened in;
    swallow = most delimiters on one physical line inside a quoted cell after a line break."""
    out = []
    cells = []
    field = []
    in_q = False
    at_start = True
    line = 1
    rec_line = 1
    swallow = 0
    line_delims = -1
    n = len(text)

    def end_field():
        nonlocal field, at_start
        cells.append("".join(field))
        field = []
        at_start = True

    def end_record():
        nonlocal cells, swallow
        end_field()
        if not (len(cells) == 1 and clean(cells[0]) == ""):
            out.append({"row": rec_line, "cells": [clean(c) for c in cells], "swallow": swallow})
            if len(out) > MAX_ROWS + 1:
                fail("E_TOO_LARGE")
        cells = []
        swallow = 0

    i = 0
    while i < n:
        ch = text[i]
        if in_q:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                in_q = False
                line_delims = -1
                i += 1
                continue
            if ch in "\r\n":
                if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                    field.append("\r\n")
                    i += 2
                else:
                    field.append(ch)
                    i += 1
                line += 1
                line_delims = 0
                continue
            if ch == delim and line_delims >= 0:
                line_delims += 1
                if line_delims > swallow:
                    swallow = line_delims
            field.append(ch)
            i += 1
            continue
        if ch == '"' and at_start:
            in_q = True
            at_start = False
            i += 1
            continue
        if ch == delim:
            end_field()
            i += 1
            continue
        if ch in "\r\n":
            if ch == "\r" and i + 1 < n and text[i + 1] == "\n":
                i += 2
            else:
                i += 1
            end_record()
            line += 1
            rec_line = line
            continue
        field.append(ch)
        at_start = False
        i += 1
    if in_q:
        fail("E_BAD_QUOTE", "unclosed quote", rec_line)
    if field or cells:
        end_record()
    return out


def check_swallowed_rows(rows, hi):
    """A quoted cell that holds whole rows (two stray quote marks): E_BAD_QUOTE at that row."""
    width = len(rows[hi]["cells"])
    if width < 3:
        return
    for r in rows[hi + 1:]:
        if r["swallow"] >= width - 1:
            fail("E_BAD_QUOTE", "quoted cell holds whole rows", r["row"])


# ----------------------------------------------------------------- HTML rows

def _html_int(v):
    # HTML "rules for parsing non-negative integers", as used by td.colSpan.
    m = re.match(r"[\t\n\x0c\r ]*\+?([0-9]+)", v or "", re.ASCII)
    if not m:
        return 1
    k = int(m.group(1))
    if k < 1:
        return 1
    return min(k, 1000)


class _Rows(HTMLParser):
    """Mirrors `doc.querySelectorAll('tr')` + `tr.cells[i].textContent`."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.rows = []
        self.cur = None
        self.cell = None
        self.span = 1
        self.n = 0

    def _end_cell(self):
        if self.cell is not None and self.cur is not None:
            self.cur["cells"].append(clean("".join(self.cell)))
            for _ in range(self.span - 1):
                self.cur["cells"].append("")
        self.cell = None

    def _end_row(self):
        self._end_cell()
        if self.cur is not None:
            self.rows.append(self.cur)
        self.cur = None

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self._end_row()
            self.n += 1
            self.cur = {"row": self.n, "cells": []}
        elif tag in ("td", "th"):
            if self.cur is None:
                self.n += 1
                self.cur = {"row": self.n, "cells": []}
            self._end_cell()
            self.cell = []
            self.span = _html_int(dict(attrs).get("colspan"))
        elif tag == "table":
            self._end_row()

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._end_cell()
        elif tag in ("tr", "table"):
            self._end_row()

    def handle_data(self, data):
        if self.cell is not None:
            self.cell.append(data)


def html_rows(text):
    p = _Rows()
    p.feed(text)
    p.close()
    p._end_row()
    if len(p.rows) > MAX_ROWS:
        fail("E_TOO_LARGE")
    return p.rows


# ----------------------------------------------------------------- numbers

_RE_PLAIN = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$", re.ASCII)
_RE_THOUSANDS_COMMA = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$", re.ASCII)
_RE_EURO = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+,\d+$", re.ASCII)
_RE_SINGLE_COMMA = re.compile(r"^[+-]?\d+,\d+$", re.ASCII)
_RE_STRIP = re.compile(WS_CLASS)


def parse_number(raw, row=None, column=None):
    s = _RE_STRIP.sub("", str(raw)).replace("−", "-")
    if s == "":
        return None
    commas = s.count(",")
    dots = s.count(".")
    if commas > 0:
        if dots == 0 and commas == 1 and _RE_SINGLE_COMMA.match(s):
            if re.search(r",\d{3}$", s, re.ASCII):
                fail("E_BAD_NUMBER", "comma then 3 digits", row, column)
            s = s.replace(",", ".")
        elif _RE_THOUSANDS_COMMA.match(s):
            s = s.replace(",", "")
        elif _RE_EURO.match(s):
            s = s.replace(".", "").replace(",", ".")
        else:
            fail("E_BAD_NUMBER", "not a plain number", row, column)
    if not _RE_PLAIN.match(s):
        fail("E_BAD_NUMBER", "not a plain number", row, column)
    v = float(s)
    if not math.isfinite(v):
        fail("E_BAD_NUMBER", "not a plain number", row, column)
    return v


def req_number(raw, row, column):
    v = parse_number(raw, row, column)
    if v is None:
        fail("E_BAD_NUMBER", "empty", row, column)
    return v


def opt_number(raw, row, column, default=0.0):
    v = parse_number(raw, row, column)
    return default if v is None else v


# ----------------------------------------------------------------- the file's decimal separator
# Mirrors resolveNumberStyle() in csv.js: decided once per file from every number cell.
# Comma evidence and dot evidence in one file -> E_BAD_NUMBER; comma evidence -> the dots
# in "1.500"-style cells are thousands separators; neither -> the fallback ("dot", or None
# for ';'/tab CSV, where a "1.500"-style cell is E_BAD_NUMBER).

_SH_INT = re.compile(r"^[+-]?\d+$", re.ASCII)
_SH_ONE_COMMA = re.compile(r"^[+-]?\d+,(\d+)$", re.ASCII)
_SH_EURO = re.compile(r"^[+-]?\d{1,3}(\.\d{3})+,\d+$", re.ASCII)
_SH_US = re.compile(r"^[+-]?\d{1,3}(,\d{3})+(\.\d+)?$", re.ASCII)
_SH_DOT3 = re.compile(r"^[+-]?\d{1,3}\.\d{3}$", re.ASCII)
_SH_ONE_DOT = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$", re.ASCII)
_SH_DOTS_THOUSANDS = re.compile(r"^[+-]?\d{1,3}(\.\d{3}){2,}$", re.ASCII)


def number_shape(raw):
    s = _RE_STRIP.sub("", str(raw)).replace("\u2212", "-")
    if s == "" or _SH_INT.match(s):
        return "neutral"
    c = _SH_ONE_COMMA.match(s)
    if c:
        return "neutral" if len(c.group(1)) == 3 else "comma"
    if _SH_EURO.match(s) or _SH_DOTS_THOUSANDS.match(s):
        return "comma"
    if _SH_US.match(s):
        return "dot"
    if _SH_DOT3.match(s):
        return "dot3"
    if _SH_ONE_DOT.match(s):
        return "dot"
    return "other"


def resolve_number_style(groups, fallback):
    first_comma = first_dot = first_dot3 = None
    for g in groups:
        for r in g["rows"]:
            for f in g["fields"]:
                i = g["map"].get(f)
                if i is None or i >= len(r["cells"]):
                    continue
                shape = number_shape(r["cells"][i])
                at = (r["row"], f)
                if shape == "comma":
                    if first_dot:
                        fail("E_BAD_NUMBER", "mixed decimal comma and point", at[0], at[1])
                    first_comma = first_comma or at
                elif shape == "dot":
                    if first_comma:
                        fail("E_BAD_NUMBER", "mixed decimal comma and point", at[0], at[1])
                    first_dot = first_dot or at
                elif shape == "dot3" and not first_dot3:
                    first_dot3 = at
    style = "comma" if first_comma else ("dot" if first_dot else fallback)
    if style is None:
        if first_dot3:
            fail("E_BAD_NUMBER", "1.500 could be 1.5 or 1500", first_dot3[0], first_dot3[1])
        return "dot"
    if style == "comma":
        for g in groups:
            for r in g["rows"]:
                for f in g["fields"]:
                    i = g["map"].get(f)
                    if i is None or i >= len(r["cells"]):
                        continue
                    bare = _RE_STRIP.sub("", r["cells"][i]).replace("\u2212", "-")
                    if _SH_DOT3.match(bare) or _SH_DOTS_THOUSANDS.match(bare):
                        r["cells"][i] = bare.replace(".", "")
    return style


# ----------------------------------------------------------------- dates

def _days_in_month(y, m):
    leap = y % 4 == 0 and (y % 100 != 0 or y % 400 == 0)
    return [31, 29 if leap else 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][m - 1]


def _days_from_civil(y, m, d):
    # Howard Hinnant's algorithm; exact integer days since 1970-01-01.
    y -= m <= 2
    era = (y if y >= 0 else y - 399) // 400
    yoe = y - era * 400
    doy = (153 * (m + (-3 if m > 2 else 9)) + 2) // 5 + d - 1
    doe = yoe * 365 + yoe // 4 - yoe // 100 + doy
    return era * 146097 + doe - 719468


def utc_ms(y, mo, d, h, mi, s, row, column):
    if not (1970 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= _days_in_month(y, mo)
            and 0 <= h <= 23 and 0 <= mi <= 59 and 0 <= s <= 59):
        fail("E_BAD_DATE", "out of range", row, column)
    return ((_days_from_civil(y, mo, d) * 24 + h) * 60 + mi) * 60000 + s * 1000


_RE_MT = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?$", re.ASCII)
_RE_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?Z?)?$", re.ASCII)
_RE_IBKR = re.compile(r"^(\d{4})(\d{2})(\d{2})(?:[;, ]+(\d{2}):?(\d{2}):?(\d{2}))?$", re.ASCII)
_RE_US = re.compile(r"^(\d{1,2})/(\d{1,2})/(\d{4}|\d{2})(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2}))?)?$", re.ASCII)


def _from_match(m, row, column):
    g = m.groups()
    return utc_ms(int(g[0]), int(g[1]), int(g[2]),
                  int(g[3]) if g[3] is not None else 0,
                  int(g[4]) if g[4] is not None else 0,
                  int(g[5]) if g[5] is not None else 0, row, column)


def parse_date(raw, kind, row, column):
    s = clean(raw)
    if s == "":
        fail("E_BAD_DATE", "empty", row, column)
    if kind == "mt":
        m = _RE_MT.match(s)
        if m:
            return _from_match(m, row, column)
    m = _RE_ISO.match(s)
    if m:
        return _from_match(m, row, column)
    if kind == "generic":
        m = _RE_MT.match(s)
        if m:
            return _from_match(m, row, column)
    if kind == "ibkr":
        m = _RE_IBKR.match(s)
        if m:
            return _from_match(m, row, column)
    if kind == "tradovate":
        m = _RE_US.match(s)
        if m:
            g = m.groups()
            y = int(g[2]) + (2000 if len(g[2]) == 2 else 0)
            return utc_ms(y, int(g[0]), int(g[1]),
                          int(g[3]) if g[3] is not None else 0,
                          int(g[4]) if g[4] is not None else 0,
                          int(g[5]) if g[5] is not None else 0, row, column)
    if "/" in s:
        fail("E_AMBIGUOUS_DATE", "slash date", row, column)
    fail("E_BAD_DATE", "not a date", row, column)


# ----------------------------------------------------------------- whitelist / detection
# Must equal SIGNATURES in site/static/js/engine/detect.js (tests/test_alias_parity.py).

SIGNATURES = {
    "mt5_deals": {
        "verified": False,
        "fields": {
            "time": ["time"], "deal": ["deal"], "symbol": ["symbol"], "type": ["type"], "direction": ["direction"],
            "volume": ["volume"], "price": ["price"], "commission": ["commission"], "fee": ["fee"], "swap": ["swap"],
            "profit": ["profit"], "position": ["position", "positionid"],
        },
        "required": [["time"], ["deal"], ["symbol"], ["type"], ["direction"], ["volume"], ["price"], ["profit"]],
    },
    "mt5_positions": {
        "verified": False,
        "fields": {
            "open_time": ["time#1"], "close_time": ["time#2"], "position": ["position"], "symbol": ["symbol"],
            "type": ["type"], "volume": ["volume"], "open_price": ["price#1"], "close_price": ["price#2"],
            "commission": ["commission"], "fee": ["fee"], "swap": ["swap"], "profit": ["profit"],
        },
        "required": [["open_time"], ["position"], ["symbol"], ["type"], ["volume"], ["open_price"]],
    },
    "mt4": {
        "verified": False,
        "fields": {
            "open_time": ["opentime", "time#1"], "close_time": ["closetime", "time#2"], "type": ["type"],
            "size": ["size", "lots"], "symbol": ["item", "symbol"], "open_price": ["price#1"],
            "close_price": ["price#2"], "commission": ["commission"], "taxes": ["taxes"], "swap": ["swap"],
            "profit": ["profit"],
        },
        "required": [["open_time"], ["close_time"], ["type"], ["size"], ["symbol"], ["open_price"],
                     ["close_price"], ["profit"]],
    },
    "ibkr_flex": {
        "verified": False,
        "fields": {
            "symbol": ["symbol"], "datetime": ["datetime"], "tradedate": ["tradedate"], "tradetime": ["tradetime"],
            "quantity": ["quantity"], "price": ["tradeprice", "price"], "side": ["buysell"],
            "oc": ["opencloseindicator", "openclose"], "code": ["notescodes", "code"],
            "commission": ["ibcommission", "commission"], "currency": ["currencyprimary", "currency"],
            "fx": ["fxratetobase"], "multiplier": ["multiplier"],
            "realized": ["fifopnlrealized", "realizedpnl", "realizedpl"], "level": ["levelofdetail"],
        },
        "required": [["symbol"], ["datetime", "tradedate"], ["quantity"], ["price"], ["side"]],
    },
    "tradovate_orders": {
        "verified": False,
        "fields": {
            "side": ["bs"], "contract": ["contract"], "product": ["product"], "status": ["status"],
            "qty": ["filledqty"], "price": ["avgfillprice", "avgprice"], "time": ["filltime"],
        },
        "required": [["side"], ["contract"], ["status"], ["qty"], ["price"], ["time"]],
    },
    "generic_roundtrip": {
        "verified": False,
        "fields": {
            "open_time": ["opentime"], "close_time": ["closetime"], "symbol": ["symbol", "ticker", "instrument"],
            "direction": ["direction", "side"], "qty": ["volume", "quantity", "qty"],
            "open_price": ["openprice", "entryprice"], "close_price": ["closeprice", "exitprice"],
            "fees": ["fees", "fee", "commission", "commissions"], "currency": ["currency"],
        },
        "required": [["open_time"], ["close_time"], ["symbol"], ["direction"], ["qty"], ["open_price"],
                     ["close_price"]],
    },
    "generic": {
        "verified": True,
        "fields": {
            "date": ["date", "tradedate"], "time": ["time", "tradetime"], "datetime": ["datetime", "timestamp"],
            "symbol": ["symbol", "ticker", "instrument"], "side": ["side", "action", "buysell"],
            "qty": ["quantity", "qty", "shares"], "price": ["price", "fillprice", "executionprice"],
            "currency": ["currency"], "fees": ["fees", "fee", "commission", "commissions"],
        },
        "required": [["date", "datetime"], ["time", "datetime"], ["symbol"], ["side"], ["qty"], ["price"]],
    },
}

# Must equal NUMERIC_FIELDS in detect.js: the whitelisted columns that hold numbers.
NUMERIC_FIELDS = {
    "mt5_deals": ["volume", "price", "commission", "fee", "swap", "profit"],
    "mt5_positions": ["volume", "open_price", "close_price", "commission", "fee", "swap", "profit"],
    "mt4": ["size", "open_price", "close_price", "commission", "taxes", "swap", "profit"],
    "ibkr_flex": ["quantity", "price", "commission", "realized", "multiplier", "fx"],
    "tradovate_orders": ["qty", "price"],
    "generic_roundtrip": ["qty", "open_price", "close_price", "fees"],
    "generic": ["qty", "price", "fees"],
}

CSV_ORDER = ["mt5_deals", "ibkr_flex", "tradovate_orders", "generic_roundtrip", "generic"]
HTML_ORDER = ["mt5_deals", "mt5_positions", "mt4"]
HEADER_TITLES = ["trade history report", "statement", "detailed statement", "account statement"]
SECTION_TITLES = ["positions", "open positions", "orders", "deals", "working orders", "summary", "results",
                  "details", "closed transactions", "open trades", "closed trades"]
SEARCH_ROWS = 10


def map_columns(cells, fields):
    norm = [norm_header(c) for c in cells]
    out = {}
    for field, aliases in fields.items():
        for alias in aliases:
            name, _, nth = alias.partition("#")
            want = int(nth) if nth else 1
            seen = 0
            at = -1
            for i, h in enumerate(norm):
                if h == name:
                    seen += 1
                    if seen == want:
                        at = i
                        break
            if at != -1:
                out[field] = at
                break
    return out


def match_signature(cells, name):
    sig = SIGNATURES[name]
    m = map_columns(cells, sig["fields"])
    ok = 0
    missing = []
    for alts in sig["required"]:
        if any(f in m for f in alts):
            ok += 1
        else:
            missing.append(alts[0])
    return {"name": name, "map": m, "ok": ok, "total": len(sig["required"]), "missing": missing,
            "full": not missing}


def _empty(cells):
    return all(c == "" for c in cells)


def detect_csv(rows):
    best = None
    seen = 0
    for i, r in enumerate(rows):
        if seen >= SEARCH_ROWS:
            break
        if _empty(r["cells"]):
            continue
        seen += 1
        for name in CSV_ORDER:
            m = match_signature(r["cells"], name)
            if m["full"]:
                return {"format": name, "header_index": i, "map": m["map"]}
            if best is None or m["ok"] / m["total"] > best[0]["ok"] / best[0]["total"]:
                best = (m, i)
    if best and best[0]["ok"] >= 3 and best[0]["ok"] / best[0]["total"] >= 0.5:
        fail("E_MISSING_COLUMN", best[0]["missing"][0], rows[best[1]]["row"], best[0]["missing"][0])
    fail("E_UNKNOWN_FORMAT")


def _title(cells):
    filled = [c for c in cells if c != ""]
    if len(filled) != 1:
        return None
    t = clean(filled[0]).lower()
    if t.endswith(":"):
        t = t[:-1]
    if t in HEADER_TITLES:
        return ("header", t)
    if t in SECTION_TITLES:
        return ("section", t)
    return None


def detect_html(rows):
    section = None
    tables = []
    cur = None
    for r in rows:
        t = _title(r["cells"])
        if t:
            section = None if t[0] == "header" else t[1]
            continue
        if section is None:
            continue
        if _empty(r["cells"]):
            continue
        matched = None
        for name in HTML_ORDER:
            m = match_signature(r["cells"], name)
            if m["full"]:
                matched = m
                break
        if matched:
            kind = matched["name"]
            if kind == "mt5_positions":
                kind = "mt5_positions_closed" if "close_time" in matched["map"] else "mt5_positions_open"
            cur = {"kind": kind, "section": section, "header": r, "map": matched["map"], "rows": []}
            tables.append(cur)
            continue
        if cur is not None:
            cur["rows"].append({"row": r["row"], "cells": r["cells"], "section": section})
    if not tables:
        fail("E_UNKNOWN_FORMAT")
    fmt = "mt5" if any(t["kind"].startswith("mt5") for t in tables) else "mt4"
    if all(len(t["rows"]) == 0 for t in tables):
        fail("E_HEADER_ONLY")
    return {"format": fmt, "tables": tables}


def cell(r, m, field):
    i = m.get(field)
    if i is None or i >= len(r["cells"]):
        return ""
    return r["cells"][i]


# ----------------------------------------------------------------- parsers
# Each parser returns {"executions": [...], "roundtrips": [...], "skipped": {...}, "extra": {...}}.
# Internal keys start with "_" and are stripped from the output.

def _skip(skipped, reason):
    skipped[reason] = skipped.get(reason, 0) + 1


def _mt_costs(commission, fee, swap):
    """MetaTrader costs are signed (negative = cost). Returns (fee >= 0, credit >= 0).

    fee = net cost as a positive number; a net credit (e.g. a positive swap larger
    than the commission) is returned separately and added to the reported profit,
    so pnl = profit + commission + fee + swap exactly while fee stays >= 0."""
    c = commission + fee + swap
    if c < 0:
        return -c, 0.0
    return 0.0, c


def _mt_type(t):
    t = t.lower()
    if t in ("buy", "sell"):
        return t, None
    if "cancel" in t:
        return None, "cancelled"
    if t in ("balance", "credit"):
        return None, t
    if t in ("buy limit", "sell limit", "buy stop", "sell stop", "buy stop limit", "sell stop limit"):
        return None, "cancelled"  # a pending order that never filled
    return None, "other_type"


def parse_mt(tables):
    execs, rts, skipped = [], [], {}
    extra = {"open_positions": 0, "has_closed_positions": False, "has_deals": False}
    for t in tables:
        m = t["map"]
        kind = t["kind"]
        if kind == "mt5_positions_closed":
            extra["has_closed_positions"] = True
        if kind == "mt5_deals":
            extra["has_deals"] = True
        for r in t["rows"]:
            if _empty(r["cells"]):
                continue
            if kind == "mt4":
                if r["section"] not in ("closed transactions", "closed trades", "open trades"):
                    continue
            elif r["section"] != t["section"]:
                continue
            first_time = cell(r, m, "time" if kind == "mt5_deals" else "open_time")
            if first_time == "":
                continue  # totals or spacer row under the table
            side, why = _mt_type(cell(r, m, "type"))
            if side is None:
                _skip(skipped, why)
                continue
            if kind == "mt5_positions_open" or (kind == "mt4" and (r["section"] == "open trades"
                                                                    or cell(r, m, "close_time") == "")):
                extra["open_positions"] += 1
                continue
            row = r["row"]
            symbol = cell(r, m, "symbol")
            if symbol == "":
                _skip(skipped, "no_symbol")
                continue
            if kind == "mt5_deals":
                ts = parse_date(cell(r, m, "time"), "mt", row, "time")
                qty = abs(req_number(cell(r, m, "volume"), row, "volume"))
                if qty == 0:
                    _skip(skipped, "zero_qty")
                    continue
                price = req_number(cell(r, m, "price"), row, "price")
                fee, credit = _mt_costs(opt_number(cell(r, m, "commission"), row, "commission"),
                                        opt_number(cell(r, m, "fee"), row, "fee"),
                                        opt_number(cell(r, m, "swap"), row, "swap"))
                profit = req_number(cell(r, m, "profit"), row, "profit")
                d = cell(r, m, "direction").lower()
                oc = "open" if d == "in" else ("close" if d in ("out", "out by") else None)
                pos = cell(r, m, "position")
                execs.append({"row": row, "ts": ts, "symbol": symbol, "side": side, "qty": qty, "price": price,
                              "fee": fee, "currency": None, "oc": oc, "pos_id": pos if pos != "" else None,
                              "pnl_reported": profit + credit, "multiplier": 1, "_unit": "account",
                              "_fx": None})
            else:
                size_field = "volume" if kind == "mt5_positions_closed" else "size"
                ot = parse_date(cell(r, m, "open_time"), "mt", row, "open_time")
                ct = parse_date(cell(r, m, "close_time"), "mt", row, "close_time")
                if ct < ot:
                    fail("E_BAD_DATE", "close before open", row, "close_time")
                qty = abs(req_number(cell(r, m, size_field), row, size_field))
                if qty == 0:
                    _skip(skipped, "zero_qty")
                    continue
                op = req_number(cell(r, m, "open_price"), row, "open_price")
                cp = req_number(cell(r, m, "close_price"), row, "close_price")
                fee, credit = _mt_costs(opt_number(cell(r, m, "commission"), row, "commission"),
                                        opt_number(cell(r, m, "fee" if kind != "mt4" else "taxes"), row,
                                                   "fee" if kind != "mt4" else "taxes"),
                                        opt_number(cell(r, m, "swap"), row, "swap"))
                profit = req_number(cell(r, m, "profit"), row, "profit")
                pos = cell(r, m, "position") if kind == "mt5_positions_closed" else ""
                rts.append({"row": row, "symbol": symbol, "dir": "long" if side == "buy" else "short",
                            "open_ts": ot, "close_ts": ct, "qty": qty, "entry": op, "exit": cp, "fees": fee,
                            "pnl_gross": profit + credit, "reported": True, "currency": None, "unit": "account",
                            "pos_id": pos if pos != "" else None})
    return {"executions": execs, "roundtrips": rts, "skipped": skipped, "extra": extra}


def _side_letter(v):
    v = v.strip().upper()
    if v.startswith("B"):
        return "buy"
    if v.startswith("S"):
        return "sell"
    return None


def parse_generic(rows, hi, m):
    execs, skipped = [], {}
    fees_known = "fees" in m
    for r in rows[hi + 1:]:
        if _empty(r["cells"]):
            continue
        row = r["row"]
        if "datetime" in m:
            ts = parse_date(cell(r, m, "datetime"), "generic", row, "datetime")
        else:
            d, t = cell(r, m, "date"), cell(r, m, "time")
            if d == "":
                fail("E_BAD_DATE", "empty", row, "date")
            if "/" in d:
                fail("E_AMBIGUOUS_DATE", "slash date", row, "date")
            ts = parse_date((d + " " + t) if t != "" else d, "generic", row, "date")
        symbol = cell(r, m, "symbol")
        side = _side_letter(cell(r, m, "side"))
        if side is None:
            _skip(skipped, "bad_side")
            continue
        if symbol == "":
            _skip(skipped, "no_symbol")
            continue
        qty = abs(req_number(cell(r, m, "qty"), row, "qty"))
        if qty == 0:
            _skip(skipped, "zero_qty")
            continue
        price = req_number(cell(r, m, "price"), row, "price")
        fee = abs(opt_number(cell(r, m, "fees"), row, "fees")) if fees_known else 0.0
        cur = cell(r, m, "currency").upper() or None
        execs.append({"row": row, "ts": ts, "symbol": symbol, "side": side, "qty": qty, "price": price,
                      "fee": fee, "currency": cur, "oc": None, "pos_id": None, "pnl_reported": None,
                      "multiplier": 1, "_unit": cur if cur else "points", "_fx": None})
    return {"executions": execs, "roundtrips": [], "skipped": skipped, "extra": {}}


def parse_generic_roundtrip(rows, hi, m):
    execs, rts, skipped = [], [], {}
    for r in rows[hi + 1:]:
        if _empty(r["cells"]):
            continue
        row = r["row"]
        d = cell(r, m, "direction").strip().lower()
        if d.startswith("l") or d.startswith("b"):
            dr = "long"
        elif d.startswith("s"):
            dr = "short"
        else:
            _skip(skipped, "bad_side")
            continue
        symbol = cell(r, m, "symbol")
        if symbol == "":
            _skip(skipped, "no_symbol")
            continue
        ot = parse_date(cell(r, m, "open_time"), "generic", row, "open_time")
        ct = parse_date(cell(r, m, "close_time"), "generic", row, "close_time")
        if ct < ot:
            fail("E_BAD_DATE", "close before open", row, "close_time")
        qty = abs(req_number(cell(r, m, "qty"), row, "qty"))
        if qty == 0:
            _skip(skipped, "zero_qty")
            continue
        op = req_number(cell(r, m, "open_price"), row, "open_price")
        cp = req_number(cell(r, m, "close_price"), row, "close_price")
        fee = abs(opt_number(cell(r, m, "fees"), row, "fees"))
        cur = cell(r, m, "currency").upper() or None
        rts.append({"row": row, "symbol": symbol, "dir": dr, "open_ts": ot, "close_ts": ct, "qty": qty,
                    "entry": op, "exit": cp, "fees": fee, "pnl_gross": None, "reported": False,
                    "currency": cur, "unit": cur if cur else "points", "pos_id": None})
    return {"executions": execs, "roundtrips": rts, "skipped": skipped, "extra": {}}


def parse_ibkr(rows, hi, m):
    execs, skipped = [], {}
    for r in rows[hi + 1:]:
        if _empty(r["cells"]):
            continue
        row = r["row"]
        level = cell(r, m, "level").upper()
        if level != "" and level != "EXECUTION":
            _skip(skipped, "not_execution")
            continue
        side = _side_letter(cell(r, m, "side"))
        if side is None:
            _skip(skipped, "bad_side")
            continue
        symbol = cell(r, m, "symbol")
        if symbol == "":
            _skip(skipped, "no_symbol")
            continue
        if "datetime" in m:
            ts = parse_date(cell(r, m, "datetime"), "ibkr", row, "datetime")
        else:
            d, t = cell(r, m, "tradedate"), cell(r, m, "tradetime")
            ts = parse_date((d + ";" + t) if t != "" else d, "ibkr", row, "tradedate")
        qty = abs(req_number(cell(r, m, "quantity"), row, "quantity"))
        if qty == 0:
            _skip(skipped, "zero_qty")
            continue
        price = req_number(cell(r, m, "price"), row, "price")
        c = opt_number(cell(r, m, "commission"), row, "commission")
        fee = -c if c < 0 else 0.0
        oc = None
        ocv = cell(r, m, "oc").upper()
        if ocv == "":
            ocv = cell(r, m, "code").upper()
        toks = [x.strip() for x in ocv.split(";")]
        has_o, has_c = "O" in toks, "C" in toks
        if has_o and not has_c:
            oc = "open"
        elif has_c and not has_o:
            oc = "close"
        realized = None
        if "realized" in m and cell(r, m, "realized") != "":
            realized = req_number(cell(r, m, "realized"), row, "realized")
        mult = 1
        if "multiplier" in m and cell(r, m, "multiplier") != "":
            mult = req_number(cell(r, m, "multiplier"), row, "multiplier")
            if mult <= 0:
                mult = 1
        cur = cell(r, m, "currency").upper() or None
        fx = None
        if "fx" in m and cell(r, m, "fx") != "":
            fx = req_number(cell(r, m, "fx"), row, "fx")
        execs.append({"row": row, "ts": ts, "symbol": symbol, "side": side, "qty": qty, "price": price,
                      "fee": fee, "currency": cur, "oc": oc, "pos_id": None, "pnl_reported": realized,
                      "multiplier": mult, "_unit": cur if cur else "points", "_fx": fx})
    return {"executions": execs, "roundtrips": [], "skipped": skipped, "extra": {}}


# UNVERIFIED: point values per contract; check each against CME contract specs.
CME_MULTIPLIERS = {"ES": 50, "MES": 5, "NQ": 20, "MNQ": 2, "YM": 5, "MYM": 0.5, "RTY": 50, "M2K": 5,
                   "CL": 1000, "MCL": 100, "GC": 100, "MGC": 10}
_RE_CONTRACT = re.compile(r"^([A-Z0-9]+?)[FGHJKMNQUVXZ][0-9]{1,2}$", re.ASCII)


def product_root(contract, product):
    p = product.strip().upper()
    if p != "":
        return p
    c = contract.strip().upper()
    mm = _RE_CONTRACT.match(c)
    return mm.group(1) if mm else c


def parse_tradovate(rows, hi, m):
    execs, skipped = [], {}
    for r in rows[hi + 1:]:
        if _empty(r["cells"]):
            continue
        row = r["row"]
        if cell(r, m, "status").strip().lower() != "filled":
            _skip(skipped, "not_filled")
            continue
        side = _side_letter(cell(r, m, "side"))
        if side is None:
            _skip(skipped, "bad_side")
            continue
        contract = cell(r, m, "contract")
        if contract == "":
            _skip(skipped, "no_symbol")
            continue
        qty = abs(req_number(cell(r, m, "qty"), row, "qty"))
        if qty == 0:
            _skip(skipped, "zero_qty")
            continue
        price = req_number(cell(r, m, "price"), row, "price")
        ts = parse_date(cell(r, m, "time"), "tradovate", row, "time")
        root = product_root(contract, cell(r, m, "product"))
        mult = CME_MULTIPLIERS.get(root)
        execs.append({"row": row, "ts": ts, "symbol": contract, "side": side, "qty": qty, "price": price,
                      "fee": 0.0, "currency": "USD" if mult is not None else None, "oc": None, "pos_id": None,
                      "pnl_reported": None, "multiplier": mult if mult is not None else 1,
                      "_unit": "USD" if mult is not None else "points", "_fx": None})
    return {"executions": execs, "roundtrips": [], "skipped": skipped, "extra": {}}


# ----------------------------------------------------------------- trades

UNIT = 1e8  # positions are tracked in 1e-8 lots so 0.1 + 0.2 - 0.3 is exactly flat


def round_half_away(x):
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def _new_trade(e, dr, seq):
    return {"symbol": e["symbol"], "dir": dr, "open_ts": e["ts"], "close_ts": None, "peak": 0,
            "entry_qty": 0.0, "entry_not": 0.0, "exit_qty": 0.0, "exit_not": 0.0, "fees": 0.0,
            "rep_sum": 0.0, "rep_missing": False, "fills": 0, "multiplier": e["multiplier"],
            "currency": e["currency"], "unit": e["_unit"], "fx": None, "seq": seq, "ks": [], "by_reversal": False}


def chrono_order(execs):
    """Execution indexes in time order; same-time fills keep their file order."""
    return sorted(range(len(execs)), key=lambda k: (execs[k]["ts"], execs[k]["row"], k))


def build_trades(execs, reported_mode, detect_hedging=False):
    """Flat-to-flat round trips per symbol. reported_mode: None | "gross" | "net".

    Positions opened before the file starts: with open/close codes (IBKR O/C, MT5
    in/out), inv[sym] counts units opened in this file and not yet closed
    (direction-blind). A closing fill bigger than inv closes a position opened
    before the file; that fill and any trade in progress on the symbol are left
    out and counted once per position (W_OPEN_AT_START), never inverted."""
    order = chrono_order(execs)
    pos = {}
    cur = {}
    inv = {}
    carried = {}
    done = []
    excluded = set()  # execution indexes left out as part of a pre-file position
    hedging = 0
    open_at_start = 0
    seq = 0
    for k in order:
        e = execs[k]
        sym = e["symbol"]
        s = 1 if e["side"] == "buy" else -1
        q_units = round_half_away(e["qty"] * UNIT)
        if q_units == 0:
            continue
        p = pos.get(sym, 0)
        have = inv.get(sym, 0)
        if e["oc"] == "close":
            if q_units > have:
                if not carried.get(sym):
                    open_at_start += 1
                    carried[sym] = True
                excluded.add(k)
                if sym in cur:
                    t = cur[sym]
                    # a fill that reversed into this trade also closed a finished trade: keep it
                    for j in (t["ks"][1:] if t["by_reversal"] else t["ks"]):
                        excluded.add(j)
                cur.pop(sym, None)
                pos[sym] = 0
                inv[sym] = 0
                continue
            inv[sym] = have - q_units
        elif e["oc"] == "open":
            inv[sym] = have + q_units
            carried[sym] = False
        else:
            closing = min(q_units, abs(p)) if (p != 0 and (p > 0) != (s > 0)) else 0
            inv[sym] = max(0, have - closing) + (q_units - closing)
        if detect_hedging and e["oc"] == "open" and p != 0 and (p > 0) != (s > 0):
            hedging += 1
        if p == 0 or (p > 0) == (s > 0):
            if p == 0:
                cur[sym] = _new_trade(e, "long" if s > 0 else "short", seq)
                seq += 1
            t = cur[sym]
            t["ks"].append(k)
            t["entry_qty"] += e["qty"]
            t["entry_not"] += e["qty"] * e["price"]
            t["fees"] += e["fee"]
            t["fills"] += 1
            if e["pnl_reported"] is not None:
                t["rep_sum"] += e["pnl_reported"]
            p += s * q_units
            t["peak"] = max(t["peak"], abs(p))
            if e["_fx"] is not None:
                t["fx"] = e["_fx"]
            pos[sym] = p
            continue
        # reducing: close part (and maybe reverse with the remainder)
        t = cur[sym]
        t["ks"].append(k)
        close_units = min(q_units, abs(p))
        rem_units = q_units - close_units
        if rem_units == 0:
            cq, cf = e["qty"], e["fee"]
        else:
            cq = close_units / UNIT
            cf = e["fee"] * close_units / q_units
        t["exit_qty"] += cq
        t["exit_not"] += cq * e["price"]
        t["fees"] += cf
        t["fills"] += 1
        if e["pnl_reported"] is None:
            t["rep_missing"] = True
        else:
            t["rep_sum"] += e["pnl_reported"]
        if e["_fx"] is not None:
            t["fx"] = e["_fx"]
        p += s * close_units
        if p == 0:
            t["close_ts"] = e["ts"]
            done.append(t)
            del cur[sym]
        if rem_units:
            nt = _new_trade(e, "long" if s > 0 else "short", seq)
            seq += 1
            nt["ks"].append(k)
            nt["by_reversal"] = True
            rq = rem_units / UNIT
            nt["entry_qty"] += rq
            nt["entry_not"] += rq * e["price"]
            nt["fees"] += e["fee"] * rem_units / q_units
            nt["fills"] += 1
            nt["peak"] = rem_units
            if e["_fx"] is not None:
                nt["fx"] = e["_fx"]
            cur[sym] = nt
            p = s * rem_units
        pos[sym] = p
    open_n = sum(1 for v in pos.values() if v != 0)
    trades = []
    for t in done:
        entry_vwap = t["entry_not"] / t["entry_qty"]
        exit_vwap = t["exit_not"] / t["exit_qty"]
        sign = 1 if t["dir"] == "long" else -1
        if reported_mode is not None and not t["rep_missing"]:
            src = "reported"
            if reported_mode == "gross":
                gross = t["rep_sum"]
                pnl = gross - t["fees"]
            else:
                pnl = t["rep_sum"]
                gross = pnl + t["fees"]
        else:
            src = "computed"
            # Total traded quantity, not the peak: with adds after a partial exit the
            # peak understates the quantity that earned the price difference.
            gross = (exit_vwap - entry_vwap) * t["entry_qty"] * t["multiplier"] * sign
            pnl = gross - t["fees"]
        trades.append({"symbol": t["symbol"], "dir": t["dir"], "open_ts": t["open_ts"], "close_ts": t["close_ts"],
                       "hold_s": (t["close_ts"] - t["open_ts"]) // 1000, "qty": t["peak"] / UNIT,
                       "entry_vwap": entry_vwap, "exit_vwap": exit_vwap, "pnl": pnl, "pnl_gross": gross,
                       "fees": t["fees"], "pnl_source": src, "pnl_unit": t["unit"], "fills_n": t["fills"],
                       "currency": t["currency"], "_fx": t["fx"], "_seq": t["seq"]})
    return trades, open_n, hedging, open_at_start, excluded


def roundtrip_trades(rts, start_seq):
    trades = []
    for i, r in enumerate(rts):
        sign = 1 if r["dir"] == "long" else -1
        if r["reported"]:
            gross = r["pnl_gross"]
            src = "reported"
        else:
            gross = (r["exit"] - r["entry"]) * r["qty"] * 1 * sign
            src = "computed"
        trades.append({"symbol": r["symbol"], "dir": r["dir"], "open_ts": r["open_ts"], "close_ts": r["close_ts"],
                       "hold_s": (r["close_ts"] - r["open_ts"]) // 1000, "qty": r["qty"],
                       "entry_vwap": r["entry"], "exit_vwap": r["exit"], "pnl": gross - r["fees"],
                       "pnl_gross": gross, "fees": r["fees"], "pnl_source": src, "pnl_unit": r["unit"],
                       "fills_n": 2, "currency": r["currency"], "_fx": None, "_seq": start_seq + i})
    return trades


def roundtrip_executions(rts):
    out = []
    for r in rts:
        open_side = "buy" if r["dir"] == "long" else "sell"
        close_side = "sell" if r["dir"] == "long" else "buy"
        out.append({"row": r["row"], "ts": r["open_ts"], "symbol": r["symbol"], "side": open_side, "qty": r["qty"],
                    "price": r["entry"], "fee": 0.0, "currency": r["currency"], "oc": "open", "pos_id": r["pos_id"],
                    "pnl_reported": None, "multiplier": 1})
        out.append({"row": r["row"], "ts": r["close_ts"], "symbol": r["symbol"], "side": close_side,
                    "qty": r["qty"], "price": r["exit"], "fee": r["fees"], "currency": r["currency"], "oc": "close",
                    "pos_id": r["pos_id"], "pnl_reported": r["pnl_gross"], "multiplier": 1})
    return out


TZ_LABELS = {"mt5": "broker server time", "mt4": "broker server time", "ibkr_flex": "as exported",
             "tradovate_orders": "local time, as exported", "generic": "as in the file",
             "generic_roundtrip": "as in the file"}


def _strip(d):
    return {k: v for k, v in d.items() if not k.startswith("_")}


def count_duplicate_rows(rows, m):
    """Rows whose whitelisted cells all equal an earlier row's. Mirrors countDuplicateRows()."""
    idx = list(m.values())
    seen = set()
    n = 0
    for r in rows:
        if _empty(r["cells"]):
            continue
        key = "\u0001".join(r["cells"][i] if i < len(r["cells"]) else "" for i in idx)
        if key in seen:
            n += 1
        else:
            seen.add(key)
    return n


def _html_number_group(t):
    """The number cells of one MetaTrader table: only rows of its own section(s)."""
    kind = "mt5_positions" if t["kind"].startswith("mt5_positions") else t["kind"]
    if kind == "mt4":
        rows = [r for r in t["rows"] if r["section"] in ("closed transactions", "closed trades", "open trades")]
    else:
        rows = [r for r in t["rows"] if r["section"] == t["section"]]
    return {"rows": rows, "map": t["map"], "fields": NUMERIC_FIELDS[kind]}


def parse_file(data):
    text = decode_bytes(data)
    if is_html(text):
        rows = html_rows(text)
        det = detect_html(rows)
        groups = [_html_number_group(t) for t in det["tables"]]
        resolve_number_style(groups, "dot")
        dup = 0
        for g in groups:
            dup += count_duplicate_rows(g["rows"], g["map"])
        fmt = det["format"]
        verified = False
        res = parse_mt(det["tables"])
        mode = "gross"
    else:
        delim = sniff_delimiter(text)
        rows = parse_csv(text, delim)
        if not rows:
            fail("E_EMPTY")
        det = detect_csv(rows)
        name, hi, m = det["format"], det["header_index"], det["map"]
        data_rows = [r for r in rows[hi + 1:] if not _empty(r["cells"])]
        if not data_rows:
            fail("E_HEADER_ONLY")
        if len(data_rows) > MAX_ROWS:
            fail("E_TOO_LARGE")
        check_swallowed_rows(rows, hi)
        resolve_number_style([{"rows": rows[hi + 1:], "map": m, "fields": NUMERIC_FIELDS[name]}],
                             "dot" if delim == "," else None)
        verified = SIGNATURES[name]["verified"]
        dup = count_duplicate_rows(rows[hi + 1:], m)
        if name == "mt5_deals":
            fmt = "mt5"
            res = parse_mt([{"kind": "mt5_deals", "section": "deals", "map": m,
                             "rows": [dict(r, section="deals") for r in rows[hi + 1:]]}])
            mode = "gross"
        elif name == "ibkr_flex":
            fmt, res, mode = "ibkr_flex", parse_ibkr(rows, hi, m), "net"
        elif name == "tradovate_orders":
            fmt, res, mode = "tradovate_orders", parse_tradovate(rows, hi, m), None
        elif name == "generic_roundtrip":
            fmt, res, mode = "generic_roundtrip", parse_generic_roundtrip(rows, hi, m), None
        else:
            fmt, res, mode = "generic", parse_generic(rows, hi, m), None

    extra = res["extra"]
    warnings = []
    if not verified:
        warnings.append(warning("W_UNVERIFIED_FORMAT", 0))
    skipped = res["skipped"]
    if skipped:
        n = 0
        for v in skipped.values():
            n += v
        warnings.append(warning("W_SKIPPED_ROWS", n))
    if dup:
        warnings.append(warning("W_DUPLICATE_ROWS", dup))

    executions = res["executions"]
    open_n = extra.get("open_positions", 0)
    hedging = 0
    open_at_start = 0
    if fmt == "mt5" and extra.get("has_closed_positions"):
        trades = roundtrip_trades(res["roundtrips"], 0)
    elif res["roundtrips"]:
        trades = roundtrip_trades(res["roundtrips"], 0)
        executions = roundtrip_executions(res["roundtrips"])
    else:
        trades, o, hedging, open_at_start, excluded = build_trades(executions, mode, detect_hedging=(fmt == "mt5"))
        open_n += o
        # fills of positions opened before the file are left out of every later step (PGR/PLR too)
        if excluded:
            executions = [e for k, e in enumerate(executions) if k not in excluded]
    if hedging:
        warnings.append(warning("W_HEDGING", hedging))
    if open_n:
        warnings.append(warning("W_OPEN_POSITIONS", open_n))
    if open_at_start:
        warnings.append(warning("W_OPEN_AT_START", open_at_start))
    pts = 0
    if fmt == "tradovate_orders":
        for t in trades:
            if t["pnl_unit"] == "points":
                pts += 1
        if pts:
            warnings.append(warning("W_POINTS_ONLY", pts))

    # currency handling
    currencies = []
    for t in trades:
        if t["pnl_unit"] not in currencies:
            currencies.append(t["pnl_unit"])
    if len(currencies) > 1 and trades and all(e.get("_fx") is not None for e in executions) \
            and all(t["_fx"] is not None for t in trades):
        for t in trades:
            f = t["_fx"]
            t["pnl"] = t["pnl"] * f
            t["pnl_gross"] = t["pnl_gross"] * f
            t["fees"] = t["fees"] * f
            t["pnl_unit"] = "base"
            t["currency"] = "base"
        warnings.append(warning("W_MIXED_CURRENCY", 0))
    groups = {}
    for t in trades:
        groups[t["pnl_unit"]] = groups.get(t["pnl_unit"], 0) + 1
    if len(groups) > 1:
        keep = sorted(groups.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
        excluded = len(trades) - groups[keep]
        trades = [t for t in trades if t["pnl_unit"] == keep]
        warnings.append(warning("W_MIXED_CURRENCY", excluded))

    trades.sort(key=lambda t: (t["close_ts"], t["open_ts"], t["symbol"], t["_seq"]))
    if not trades:
        fail("E_NO_CLOSED_TRADES")
    out_trades = []
    for i, t in enumerate(trades):
        d = {"id": "t%d" % (i + 1)}
        d.update(_strip(t))
        out_trades.append(d)
    return {
        "format": fmt,
        "verified_format": verified,
        "executions": [_strip(e) for e in executions],
        "trades": out_trades,
        "skipped": skipped,
        "warnings": warnings,
        "tz_label": TZ_LABELS[fmt],
        "currency_groups": groups,
    }


# ----------------------------------------------------------------- FreeStats

def median(xs):
    if not xs:
        return None
    v = sorted(xs)
    k = len(v) // 2
    if len(v) % 2:
        return v[k]
    return (v[k - 1] + v[k]) / 2


def _split(trades, d):
    sub = [t for t in trades if t["dir"] == d]
    w = l = 0
    pnl = 0.0
    for t in sub:
        pnl += t["pnl"]
        if t["pnl"] > 0:
            w += 1
        elif t["pnl"] < 0:
            l += 1
    return {"n": len(sub), "wins": w, "losses": l, "win_rate": (w / (w + l)) if (w + l) else None, "pnl": pnl}


def free_stats(trades, starting_balance=None):
    """FreeStats exactly as the DATA MODEL defines them, on trades in close-time order."""
    n = len(trades)
    wins = losses = scratch = 0
    gp = gl = total = 0.0
    largest_win = largest_loss = None
    for t in trades:
        p = t["pnl"]
        total += p
        if p > 0:
            wins += 1
            gp += p
            if largest_win is None or p > largest_win:
                largest_win = p
        elif p < 0:
            losses += 1
            gl += p
            if largest_loss is None or p < largest_loss:
                largest_loss = p
        else:
            scratch += 1
    # streaks: a scratch trade ends both kinds of streak; the first longest run is kept
    best = {"w": [0, 0.0], "l": [0, 0.0]}
    cw = [0, 0.0]
    cl = [0, 0.0]
    for t in trades:
        p = t["pnl"]
        if p > 0:
            cw = [cw[0] + 1, cw[1] + p]
            cl = [0, 0.0]
            if cw[0] > best["w"][0]:
                best["w"] = list(cw)
        elif p < 0:
            cl = [cl[0] + 1, cl[1] + p]
            cw = [0, 0.0]
            if cl[0] > best["l"][0]:
                best["l"] = list(cl)
        else:
            cw = [0, 0.0]
            cl = [0, 0.0]
    eq = peak = maxdd = 0.0
    maxdd_pct = None
    use_pct = starting_balance is not None and starting_balance > 0
    if use_pct:
        maxdd_pct = 0.0
    for t in trades:
        eq += t["pnl"]
        if eq > peak:
            peak = eq
        dd = peak - eq
        if dd > maxdd:
            maxdd = dd
        if use_pct:
            top = starting_balance + peak
            pct = (top - (starting_balance + eq)) / top if top > 0 else 0.0
            if pct > maxdd_pct:
                maxdd_pct = pct
    hw = median([t["hold_s"] for t in trades if t["pnl"] > 0])
    hl = median([t["hold_s"] for t in trades if t["pnl"] < 0])
    return {
        "n": n, "wins": wins, "losses": losses, "scratch": scratch,
        "win_rate": (wins / (wins + losses)) if (wins + losses) else None,
        "gross_profit": gp, "gross_loss": gl,
        "profit_factor": (gp / -gl) if losses else "no losing trades",
        "net_pnl": total,
        "expectancy": (total / n) if n else None,
        "avg_win": (gp / wins) if wins else None,
        "avg_loss": (gl / losses) if losses else None,
        "largest_win": largest_win, "largest_loss": largest_loss,
        "max_consec_wins": {"n": best["w"][0], "pnl": best["w"][1]},
        "max_consec_losses": {"n": best["l"][0], "pnl": best["l"][1]},
        "max_drawdown_abs": maxdd,
        "max_drawdown_pct": maxdd_pct,
        "long": _split(trades, "long"), "short": _split(trades, "short"),
        "hold_median_win_s": hw, "hold_median_loss_s": hl,
        "hold_ratio": (hl / hw) if (hw is not None and hl is not None and hw > 0) else None,
    }


# ----------------------------------------------------------------- noise checks

N_PERM = 10000
SEED_BASE = 20261022
MIN_GROUP = 30
NOISE_LIMIT = 20000
M32 = 0xFFFFFFFF


def _imul(a, b):
    return (a * b) & M32


def mulberry32(seed):
    """Port of the common JS mulberry32; every step is reduced to 32 bits like Math.imul / |0."""
    state = [seed & M32]

    def rand():
        state[0] = (state[0] + 0x6D2B79F5) & M32
        a = state[0]
        t = _imul(a ^ (a >> 15), 1 | a)
        t = ((t + _imul(t ^ (t >> 7), 61 | t)) & M32) ^ t
        return ((t ^ (t >> 14)) & M32) / 4294967296

    return rand


def shuffle(arr, rand):
    """Fisher–Yates, in place, from the end."""
    for i in range(len(arr) - 1, 0, -1):
        j = int(rand() * (i + 1))
        arr[i], arr[j] = arr[j], arr[i]


def p_value(count):
    return (1 + count) / (N_PERM + 1)


def label_for(p, too_few):
    if too_few:
        return "not enough trades to tell"
    return "distinguishable from noise" if p < 0.05 else "may be noise"


def _longest_loss_run(xs):
    best = cur = 0
    for v in xs:
        if v < 0:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best


EXPECTANCY_METHOD = "bootstrap-t"


def _student_gap(xs, n, mu):
    """|mean - mu| / sd (n - 1). Zero spread: 0 if mean == mu, else infinity. Mirrors studentGap()."""
    s = 0.0
    for i in range(n):
        s += xs[i]
    m = s / n
    q = 0.0
    for i in range(n):
        d = xs[i] - m
        q += d * d
    sd = math.sqrt(q / (n - 1))
    if sd == 0:
        return 0.0 if m == mu else math.inf
    return abs(m - mu) / sd


def check_expectancy(pnls, seed):
    """Expectancy != 0 by bootstrap-t (Tester D3: the plan's sign flip over-fires on skewed P&L).

    Resample with replacement N times; count resamples whose t around the file's mean is at
    least the file's t around zero."""
    n = len(pnls)
    if n < MIN_GROUP:
        return {"stat": "expectancy", "method": EXPECTANCY_METHOD, "n_a": n, "n_b": None, "value": None,
                "p": None, "label": label_for(None, True)}
    s = 0.0
    for v in pnls:
        s += v
    obs = s / n
    t_obs = _student_gap(pnls, n, 0.0)
    rand = mulberry32(seed)
    draw = [0.0] * n
    count = 0
    for _ in range(N_PERM):
        for i in range(n):
            draw[i] = pnls[int(rand() * n)]
        if _student_gap(draw, n, obs) >= t_obs:
            count += 1
    p = p_value(count)
    return {"stat": "expectancy", "method": EXPECTANCY_METHOD, "n_a": n, "n_b": None, "value": obs, "p": p,
            "label": label_for(p, False)}


def check_hold_gap(trades, seed):
    # group A = losing trades, group B = winning trades; scratch trades are left out
    a = [t["hold_s"] for t in trades if t["pnl"] < 0]
    b = [t["hold_s"] for t in trades if t["pnl"] > 0]
    na, nb = len(a), len(b)
    out = {"stat": "hold_gap_s", "method": "label permutation", "n_a": na, "n_b": nb, "value": None, "p": None}
    if na < MIN_GROUP or nb < MIN_GROUP:
        out["label"] = label_for(None, True)
        return out
    obs = median(a) - median(b)
    pool = [t["hold_s"] for t in trades if t["pnl"] != 0]
    rand = mulberry32(seed)
    count = 0
    for _ in range(N_PERM):
        shuffle(pool, rand)
        stat = median(pool[:na]) - median(pool[na:])
        if abs(stat) >= abs(obs):
            count += 1
    p = p_value(count)
    out.update(value=obs, p=p, label=label_for(p, False))
    return out


def check_streak(pnls, seed):
    n = len(pnls)
    out = {"stat": "longest_losing_streak", "method": "order shuffle", "n_a": n, "n_b": None, "value": None,
           "p": None}
    if n < MIN_GROUP:
        out["label"] = label_for(None, True)
        return out
    obs = _longest_loss_run(pnls)
    work = [(-1 if v < 0 else (1 if v > 0 else 0)) for v in pnls]
    rand = mulberry32(seed)
    count = 0
    for _ in range(N_PERM):
        shuffle(work, rand)
        if _longest_loss_run(work) >= obs:
            count += 1
    p = p_value(count)
    out.update(value=obs, p=p, label=label_for(p, False))
    return out


def noise_checks(trades):
    used = trades[-NOISE_LIMIT:] if len(trades) > NOISE_LIMIT else trades
    pnls = [t["pnl"] for t in used]
    return {
        "n_used": len(used),
        "limited": len(trades) > NOISE_LIMIT,
        "checks": [check_expectancy(pnls, SEED_BASE + 0), check_hold_gap(used, SEED_BASE + 1),
                   check_streak(pnls, SEED_BASE + 2)],
    }


# ----------------------------------------------------------------- PGR / PLR (partial coverage)
# Browser-side counts for the paid report (step 18). Odean (1998) needs a price for
# every open position on every sell day; trade files have none, so a position is
# marked only when its symbol traded that same day (last execution price that day).
# Unmarked open position-days lower coverage_pct, which the report shows.

DAY_MS = 86400000


def pgr_plr_counts(executions):
    order = sorted(range(len(executions)), key=lambda k: (executions[k]["ts"], executions[k]["row"], k))
    pos = {}  # symbol -> [units (signed int), avg entry price]
    rg = rl = pg = pl = 0
    marked = total = 0
    i = 0
    while i < len(order):
        day = executions[order[i]]["ts"] // DAY_MS
        j = i
        while j < len(order) and executions[order[j]]["ts"] // DAY_MS == day:
            j += 1
        todays = [executions[order[k]] for k in range(i, j)]
        mark = {}
        for e in todays:
            mark[e["symbol"]] = e["price"]  # last price of the day per symbol
        sold = set()
        for e in todays:
            sym = e["symbol"]
            s = 1 if e["side"] == "buy" else -1
            q = round_half_away(e["qty"] * UNIT)
            if q == 0:
                continue
            units, avg = pos.get(sym, (0, 0.0))
            if units == 0 or (units > 0) == (s > 0):
                new_units = units + s * q
                avg = (avg * abs(units) + e["price"] * q) / abs(new_units)
                pos[sym] = (new_units, avg)
                continue
            # a realising fill: gain or loss against the average entry
            diff = (e["price"] - avg) * (1 if units > 0 else -1)
            if diff > 0:
                rg += 1
            elif diff < 0:
                rl += 1
            sold.add(sym)
            close = min(q, abs(units))
            rem = q - close
            units = units + s * close
            if units == 0 and rem:
                pos[sym] = (s * rem, e["price"])
            elif units == 0:
                pos[sym] = (0, 0.0)
            else:
                pos[sym] = (units, avg)
        if sold:
            for sym in sorted(pos):
                units, avg = pos[sym]
                if units == 0 or sym in sold:
                    continue
                total += 1
                if sym in mark:
                    marked += 1
                    diff = (mark[sym] - avg) * (1 if units > 0 else -1)
                    if diff > 0:
                        pg += 1
                    elif diff < 0:
                        pl += 1
        i = j
    return {"rg": rg, "pg": pg, "rl": rl, "pl": pl,
            "coverage_pct": (100 * marked / total) if total else None}


# ----------------------------------------------------------------- StrippedRows (paid report)
# The only trade data that leaves the browser. Mirrors site/static/js/paid/strip.js.

import hashlib  # noqa: E402


def week_anchor(min_open_ts):
    day = min_open_ts // DAY_MS
    weekday = (day + 3) % 7  # 1970-01-01 was a Thursday; Monday = 0
    return (day - weekday) * DAY_MS


def round3(x):
    return round_half_away(x * 1000) / 1000


def round2(x):
    return round_half_away(x * 100) / 100


def fingerprint(salt, t):
    text = "|".join(str(v) for v in [salt, t["symbol"], t["open_ts"], t["close_ts"], t["dir"],
                                      round_half_away(t["qty"] * 1e8), round_half_away(t["pnl"] * 100)])
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:32]


def strip_rows(trades, salt, perm=None):
    used = trades[-20000:] if len(trades) > 20000 else trades
    anchor = week_anchor(min(t["open_ts"] for t in used))
    symbols = sorted({t["symbol"] for t in used})
    p = perm(len(symbols)) if perm else list(range(len(symbols)))
    index = {s: p[i] for i, s in enumerate(symbols)}
    med = {s: median([t["qty"] for t in used if t["symbol"] == s]) for s in symbols}
    rows = [{"o": (t["open_ts"] - anchor) // 60000, "h": t["hold_s"], "d": 1 if t["dir"] == "long" else -1,
             "q": round3(t["qty"] / med[t["symbol"]]), "p": round2(t["pnl"]), "s": index[t["symbol"]],
             "f": fingerprint(salt, t)} for t in used]
    return {"rows": rows, "limited": len(trades) > 20000, "anchor": anchor}


# ----------------------------------------------------------------- CLI / expected files

FIXTURE_DIRS = ["generic", "generic_roundtrip", "mt5", "mt4", "ibkr", "tradovate", "errors"]


def run_fixture(data):
    """What the golden test compares: the ParseResult, or the error code/row/column."""
    try:
        res = parse_file(data)
    except EngineError as e:
        return {"error": e.to_json()}
    return {"result": res, "stats": free_stats(res["trades"]), "noise": noise_checks(res["trades"]),
            "pgr_plr": pgr_plr_counts(res["executions"])}


def fixture_paths(root):
    out = []
    for d in FIXTURE_DIRS:
        p = os.path.join(root, d)
        for name in sorted(os.listdir(p)):
            out.append(d + "/" + name)
    return out


def write_expected(root):
    exp = os.path.join(root, "expected")
    os.makedirs(exp, exist_ok=True)
    for rel in fixture_paths(root):
        with open(os.path.join(root, rel), "rb") as f:
            res = run_fixture(f.read())
        name = rel.replace("/", "__") + ".json"
        with open(os.path.join(exp, name), "w", encoding="utf-8") as f:
            json.dump(res, f, indent=1, sort_keys=True)
            f.write("\n")
    return exp


def main(argv):
    if len(argv) >= 2 and argv[0] == "--expected":
        print(write_expected(argv[1]))
        return 0
    with open(argv[0], "rb") as f:
        print(json.dumps(run_fixture(f.read()), indent=1, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
