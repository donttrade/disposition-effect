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
    "E_BAD_MAPPING": "The saved column choices do not fit this file.",
    "E_MIXED_FILES": "These files have different columns.",
    "E_PASTE_FORMAT": "This paste has no columns we can split.",
}


class EngineError(Exception):
    def __init__(self, code, detail="", row=None, column=None):
        super().__init__(f"{code}: {MESSAGES.get(code, code)} {detail}".strip())
        self.code = code
        self.row = row
        self.column = column
        self.file = None  # 1-based place among several files read together (errors.js inFile)

    def to_json(self):
        out = {"code": self.code, "row": self.row, "column": self.column}
        if self.file is not None:
            out["file"] = self.file
        return out


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


def is_xlsx(b):
    """Mirrors isXlsx(): an entry under xl/ in the first local headers, or xl/workbook.xml in the
    central directory at the end."""
    off = 0
    for _ in range(20):
        if off + 30 > len(b) or b[off:off + 4] != b"PK\x03\x04":
            break
        flags = b[off + 6] | (b[off + 7] << 8)
        comp = int.from_bytes(b[off + 18:off + 22], "little")
        name_len = b[off + 26] | (b[off + 27] << 8)
        extra_len = b[off + 28] | (b[off + 29] << 8)
        at = off + 30
        if name_len >= 3 and b[at:at + 3] == b"xl/":
            return True
        if (flags & 8) and comp == 0:
            break
        off = at + name_len + extra_len + comp
    return b"xl/workbook.xml" in b[max(0, len(b) - 65557):]


def decode_bytes(b):
    n = len(b)
    if n == 0:
        fail("E_EMPTY")
    if n > MAX_BYTES:
        fail("E_TOO_LARGE")
    if b[:4] == b"PK\x03\x04":
        if is_xlsx(b):
            fail("E_ENCODING", "xlsx: save it as CSV")
        fail("E_ENCODING", "zip: open it and drop the CSV inside")
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
    """Mirrors parseCsv() in csv.js, including the stray-quote bookkeeping:
    a quoted cell open at the end of the file is E_BAD_QUOTE at the row it opened in;
    swallow = most delimiters on one physical line inside a quoted cell after a line break;
    ml = indexes of cells spanning a line break; broken = such a cell closed by a quote
    followed by more text (the next row's opening quote closing a stray one)."""
    out = []
    cells = []
    field = []
    in_q = False
    at_start = True
    line = 1
    rec_line = 1
    swallow = 0
    line_delims = -1
    ml = []
    broken = False
    closed_ml = False
    n = len(text)

    def end_field():
        nonlocal field, at_start
        cells.append("".join(field))
        field = []
        at_start = True

    def end_record():
        nonlocal cells, swallow, ml, broken
        end_field()
        if not (len(cells) == 1 and clean(cells[0]) == ""):
            out.append({"row": rec_line, "cells": [clean(c) for c in cells], "swallow": swallow, "ml": ml,
                        "broken": broken})
            if len(out) > MAX_ROWS + 1:
                fail("E_TOO_LARGE")
        cells = []
        swallow = 0
        ml = []
        broken = False

    i = 0
    while i < n:
        ch = text[i]
        if in_q:
            if ch == '"':
                if i + 1 < n and text[i + 1] == '"':
                    field.append('"')
                    i += 2
                    continue
                if line_delims >= 0:
                    ml.append(len(cells))
                    closed_ml = True
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
        if closed_ml:
            if ch != delim and ch not in "\r\n":
                broken = True
            closed_ml = False
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


def check_quoting(rows, hi, m):
    """Data records whose quoting shows merged or cut rows: E_BAD_QUOTE. Mirrors checkQuoting()."""
    width = len(rows[hi]["cells"])
    idx = list(m.values())
    if rows[hi]["ml"] or rows[hi]["broken"]:
        fail("E_BAD_QUOTE", "header cell spans lines", rows[hi]["row"])
    for r in rows[hi + 1:]:
        if r["broken"] or (r["ml"] and len(r["cells"]) > width) or (width >= 3 and r["swallow"] >= width - 1):
            fail("E_BAD_QUOTE", "quoting merged rows", r["row"])
        for i in idx:
            if i in r["ml"] or (i < len(r["cells"]) and '"' in r["cells"][i]):
                fail("E_BAD_QUOTE", "quote or line break in a read column", r["row"])


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
        self.tables = 0   # <table> start tags seen, for the row's table index (htmlRows: tr.closest('table'))
        self.stack = []

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
            self.cur = {"row": self.n, "cells": [], "table": self.stack[-1] if self.stack else -1}
        elif tag in ("td", "th"):
            if self.cur is None:
                self.n += 1
                self.cur = {"row": self.n, "cells": [], "table": self.stack[-1] if self.stack else -1}
            self._end_cell()
            self.cell = []
            self.span = _html_int(dict(attrs).get("colspan"))
        elif tag == "table":
            self._end_row()
            self.stack.append(self.tables)
            self.tables += 1

    def handle_endtag(self, tag):
        if tag in ("td", "th"):
            self._end_cell()
        elif tag in ("tr", "table"):
            self._end_row()
            if tag == "table" and self.stack:
                self.stack.pop()

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
_SH_DOT3 = re.compile(r"^[+-]?[1-9]\d{0,2}\.\d{3}$", re.ASCII)  # never a leading 0 (F-D7)
_SH_ONE_DOT = re.compile(r"^[+-]?(\d+\.?\d*|\.\d+)$", re.ASCII)
_SH_DOTS_THOUSANDS = re.compile(r"^[+-]?[1-9]\d{0,2}(\.\d{3}){2,}$", re.ASCII)


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


# ----------------------------------------------------------------- daylight-saving nights
# Mirrors csv.js: a DST night is 00:00-05:00 of a US (2nd Sun Mar, 1st Sun Nov) or EU (last Sun
# Mar, last Sun Oct) change Sunday. Trades open during one are flagged (W_DST); a round-trip close
# up to 1 h before its open, both on a fall-back night, is read as the repeated hour (+1 h).

DAY_MS_ = 86400000
DST_NIGHT_MS = 5 * 3600000


def _nth_sunday(y, month, n):
    if n > 0:
        first = _days_from_civil(y, month, 1) * DAY_MS_
        dow = (first // DAY_MS_ + 4) % 7
        return first + (((7 - dow) % 7) + 7 * (n - 1)) * DAY_MS_
    ny, nm = (y + 1, 1) if month == 12 else (y, month + 1)
    last = (_days_from_civil(ny, nm, 1) - 1) * DAY_MS_
    dow = (last // DAY_MS_ + 4) % 7
    return last - dow * DAY_MS_


def dst_nights(y):
    out = []
    for d, fb in [(_nth_sunday(y, 3, 2), False), (_nth_sunday(y, 11, 1), True), (_nth_sunday(y, 3, -1), False),
                  (_nth_sunday(y, 10, -1), True)]:
        out.append((d, d + DST_NIGHT_MS, fb))
    return out


def year_of(ms):
    import datetime
    return (datetime.datetime(1970, 1, 1) + datetime.timedelta(milliseconds=ms)).year


def spans_dst_night(open_ts, close_ts):
    for y in range(year_of(open_ts), year_of(close_ts) + 1):
        for s, e, _ in dst_nights(y):
            if open_ts < e and close_ts >= s:
                return True
    return False


def fall_back_close(open_ts, close_ts):
    if close_ts >= open_ts or open_ts - close_ts > 3600000:
        return None
    for s, e, fb in dst_nights(year_of(open_ts)):
        if fb and s <= open_ts < e and s <= close_ts < e:
            return close_ts + 3600000
    return None


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


# ----------------------------------------------------------------- dates in a chosen form
# Mirrors parseDateFmt(), stripZone(), dateShape() and detectDateFormat() in csv.js.

DATE_FORMATS = ["ymd", "mdy", "dmy", "excel", "epoch_s", "epoch_ms"]
_RE_DF = re.compile(r"^([0-9./-]+)(?:[ T]+(\d{1,2}):(\d{2})(?::(\d{2})(?:[.,]\d+)?)?(?: ?([AaPp][Mm]))?)?$", re.ASCII)
_RE_ZONE_WORD = re.compile(r"^(.*[0-9AaPpMm]) ([A-Za-z]{2,5})$", re.ASCII)
_RE_ZONE_OFFSET = re.compile(r"^(.*\d:\d{2}.*?) ?(?:(?:UTC|GMT) ?)?[+-]\d{1,2}(?::?\d{2})?$", re.ASCII)
_RE_ZONE_Z = re.compile(r"^(.*\d)Z$", re.ASCII)
_RE_YMD = re.compile(r"^(\d{4})([-/.])(\d{1,2})\2(\d{1,2})$", re.ASCII)
_RE_YMD8 = re.compile(r"^(\d{4})(\d{2})(\d{2})$", re.ASCII)
_RE_DMY = re.compile(r"^(\d{1,2})([-/.])(\d{1,2})\2(\d{4}|\d{2})$", re.ASCII)
_RE_SERIAL = re.compile(r"^\d+(\.\d+)?$", re.ASCII)
MAX_TS = 4133980800000  # 2101-01-01: utc_ms accepts years 1970-2100


def strip_zone(s):
    zone = False
    m = _RE_ZONE_WORD.match(s)
    if m and not re.match(r"^[AaPp][Mm]$", m.group(2)) and re.search(r"\d", m.group(1), re.ASCII):
        s, zone = m.group(1), True
    m = _RE_ZONE_OFFSET.match(s)
    if m and re.search(r"[0-9AaPpMm]$", m.group(1), re.ASCII):
        s, zone = m.group(1), True
    m = _RE_ZONE_Z.match(s)
    if m:
        s, zone = m.group(1), True
    return s, zone


def _in_range(ms, row, column):
    if not (0 <= ms < MAX_TS):
        fail("E_BAD_DATE", "out of range", row, column)
    return ms


def parse_date_fmt(raw, fmt, row, column, seen=None):
    s, zone = strip_zone(clean(raw))
    if s == "":
        fail("E_BAD_DATE", "empty", row, column)
    m = _RE_DF.match(s)
    if not m:
        fail("E_BAD_DATE", "does not fit the chosen form", row, column)
    if zone and seen is not None:
        seen["zone"] = True
    d = m.group(1)
    timed = m.group(2) is not None
    h = int(m.group(2)) if timed else 0
    mi = int(m.group(3)) if timed else 0
    sec = int(m.group(4)) if m.group(4) is not None else 0
    if m.group(5) is not None:
        if h < 1 or h > 12:
            fail("E_BAD_DATE", "out of range", row, column)
        h = (h % 12) + (12 if m.group(5).upper() == "PM" else 0)
    if fmt in ("epoch_s", "epoch_ms"):
        if timed or not _RE_SERIAL.match(d):
            fail("E_BAD_DATE", "does not fit the chosen form", row, column)
        v = float(d)
        return _in_range(math.floor(v) * 1000 if fmt == "epoch_s" else math.floor(v / 1000) * 1000, row, column)
    if fmt == "excel":
        if not _RE_SERIAL.match(d):
            fail("E_BAD_DATE", "does not fit the chosen form", row, column)
        v = float(d)
        if v < 61:
            fail("E_BAD_DATE", "out of range", row, column)
        if timed:
            if "." in d:
                fail("E_BAD_DATE", "does not fit the chosen form", row, column)
            if mi > 59 or sec > 59 or h > 23:
                fail("E_BAD_DATE", "out of range", row, column)
            return _in_range((int(d) - 25569) * 86400000 + ((h * 60 + mi) * 60 + sec) * 1000, row, column)
        return _in_range((math.floor(v * 86400 + 0.5) - 25569 * 86400) * 1000, row, column)
    if fmt == "ymd":
        x = _RE_YMD.match(d)
        if x:
            y, mo, dd = int(x.group(1)), int(x.group(3)), int(x.group(4))
        else:
            x = _RE_YMD8.match(d)
            if not x:
                fail("E_BAD_DATE", "does not fit the chosen form", row, column)
            y, mo, dd = int(x.group(1)), int(x.group(2)), int(x.group(3))
    elif fmt in ("mdy", "dmy"):
        x = _RE_DMY.match(d)
        if not x:
            fail("E_BAD_DATE", "does not fit the chosen form", row, column)
        a, b = int(x.group(1)), int(x.group(3))
        y = int(x.group(4)) + (2000 if len(x.group(4)) == 2 else 0)
        mo, dd = (a, b) if fmt == "mdy" else (b, a)
        if mo > 12:
            fail("E_BAD_DATE", "does not fit the chosen form", row, column)
    else:
        fail("E_BAD_DATE", "no date form", row, column)
    return utc_ms(y, mo, dd, h, mi, sec, row, column)


def date_shape(raw):
    m = _RE_DF.match(strip_zone(clean(raw))[0])
    if not m:
        return "other", 0, 0
    d = m.group(1)
    timed = m.group(2) is not None
    if _RE_YMD.match(d) or re.match(r"^(19|20)\d{6}$", d, re.ASCII):
        return "ymd", 0, 0
    x = _RE_DMY.match(d)
    if x:
        return "dm", int(x.group(1)), int(x.group(3))
    if not timed and re.match(r"^\d{12,13}$", d, re.ASCII):
        return "epoch_ms", 0, 0
    if not timed and re.match(r"^\d{9,10}(\.\d+)?$", d, re.ASCII):
        return "epoch_s", 0, 0
    if re.match(r"^\d{5}(\.\d+)?$", d, re.ASCII) and 20000 <= float(d) <= 80000:
        return "excel", 0, 0
    return "other", 0, 0


def detect_date_format(values):
    kinds = []
    dmy_at = mdy_at = -1
    for i, v in enumerate(values):
        if clean(v) == "":
            continue
        kind, a, b = date_shape(v)
        if kind not in kinds:
            kinds.append(kind)
        if kind == "dm":
            if a > 12 and dmy_at < 0:
                dmy_at = i
            if b > 12 and mdy_at < 0:
                mdy_at = i
    if not kinds:
        return {"format": None, "reason": "empty", "at": -1, "at2": -1}
    if len(kinds) > 1 or kinds[0] == "other":
        return {"format": None, "reason": "mixed", "at": -1, "at2": -1}
    if kinds[0] != "dm":
        return {"format": kinds[0], "reason": None, "at": -1, "at2": -1}
    if dmy_at >= 0 and mdy_at >= 0:
        return {"format": None, "reason": "mixed_order", "at": dmy_at, "at2": mdy_at}
    if dmy_at >= 0:
        return {"format": "dmy", "reason": "seen", "at": dmy_at, "at2": -1}
    if mdy_at >= 0:
        return {"format": "mdy", "reason": "seen", "at": mdy_at, "at2": -1}
    return {"format": None, "reason": "ask", "at": -1, "at2": -1}


# ----------------------------------------------------------------- a pasted table (mirrors fromPaste)

_PASTE_GAP = re.compile("[ \u00a0\u2000-\u200a\u202f\u205f\u3000]{2,}")
_WS_EDGE = re.compile("^" + WS_CLASS + "+|" + WS_CLASS + "+$")


def from_paste(text):
    text = str(text)
    if len(text) > MAX_BYTES:
        fail("E_TOO_LARGE")
    if clean(text) == "":
        fail("E_EMPTY")
    lines = re.split(r"\r\n|\n|\r", text)
    tabs = any("\t" in l for l in lines)
    out = []
    wide = 0
    for k, line in enumerate(lines):
        if clean(line) == "":
            continue
        parts = line.split("\t") if tabs else _PASTE_GAP.split(_WS_EDGE.sub("", line))
        cells = [clean(c) for c in parts]
        if len([c for c in cells if c != ""]) >= 2:
            wide += 1
        out.append({"row": k + 1, "cells": cells, "swallow": 0, "ml": [], "broken": False})
        if len(out) > MAX_ROWS + 1:
            fail("E_TOO_LARGE")
    if wide == 0:
        fail("E_PASTE_FORMAT")
    return out


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
    "tradingview": {
        "verified": False,
        "fields": {
            "symbol": ["symbol"], "side": ["side"], "qty": ["quantity", "qty"], "price": ["fillprice"],
            "status": ["status"], "commission": ["commission"], "time": ["closingtime"],
        },
        "required": [["symbol"], ["side"], ["qty"], ["price"], ["status"], ["time"]],
        "labels": {"symbol": "Symbol", "side": "Side", "qty": "Quantity", "price": "Fill price", "status": "Status",
                   "time": "Closing time"},
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
    "tradingview": ["qty", "price", "commission"],
    "generic_roundtrip": ["qty", "open_price", "close_price", "fees"],
    "generic": ["qty", "price", "fees"],
}

# ISO 4217 currency codes, plus CNH (offshore yuan, written by IBKR); mirrors ISO_CURRENCIES /
# checkCurrencyColumn() in detect.js.
ISO_CURRENCIES = [
    "AED", "AFN", "ALL", "AMD", "ANG", "AOA", "ARS", "AUD", "AWG", "AZN", "BAM", "BBD", "BDT", "BGN", "BHD",
    "BIF", "BMD", "BND", "BOB", "BOV", "BRL", "BSD", "BTN", "BWP", "BYN", "BZD", "CAD", "CDF", "CHE", "CHF",
    "CHW", "CLF", "CLP", "CNH", "CNY", "COP", "COU", "CRC", "CUC", "CUP", "CVE", "CZK", "DJF", "DKK", "DOP", "DZD",
    "EGP", "ERN", "ETB", "EUR", "FJD", "FKP", "GBP", "GEL", "GHS", "GIP", "GMD", "GNF", "GTQ", "GYD", "HKD",
    "HNL", "HTG", "HUF", "IDR", "ILS", "INR", "IQD", "IRR", "ISK", "JMD", "JOD", "JPY", "KES", "KGS", "KHR",
    "KMF", "KPW", "KRW", "KWD", "KYD", "KZT", "LAK", "LBP", "LKR", "LRD", "LSL", "LYD", "MAD", "MDL", "MGA",
    "MKD", "MMK", "MNT", "MOP", "MRU", "MUR", "MVR", "MWK", "MXN", "MXV", "MYR", "MZN", "NAD", "NGN", "NIO",
    "NOK", "NPR", "NZD", "OMR", "PAB", "PEN", "PGK", "PHP", "PKR", "PLN", "PYG", "QAR", "RON", "RSD", "RUB",
    "RWF", "SAR", "SBD", "SCR", "SDG", "SEK", "SGD", "SHP", "SLE", "SLL", "SOS", "SRD", "SSP", "STN", "SVC",
    "SYP", "SZL", "THB", "TJS", "TMT", "TND", "TOP", "TRY", "TTD", "TWD", "TZS", "UAH", "UGX", "USD", "USN",
    "UYI", "UYU", "UYW", "UZS", "VED", "VES", "VND", "VUV", "WST", "XAF", "XAG", "XAU", "XBA", "XBB", "XBC",
    "XBD", "XCD", "XCG", "XDR", "XOF", "XPD", "XPF", "XPT", "XSU", "XUA", "YER", "ZAR", "ZMW", "ZWG", "ZWL",
]
_ISO_SET = set(ISO_CURRENCIES)


def check_currency_column(rows, m):
    """-> (map, ignored): drop 'currency' when any non-empty cell is not an ISO 4217 code."""
    if "currency" not in m:
        return m, False
    i = m["currency"]
    for r in rows:
        v = clean(r["cells"][i]).upper() if i < len(r["cells"]) else ""
        if v != "" and v not in _ISO_SET:
            rest = dict(m)
            del rest["currency"]
            return rest, True
    return m, False


CSV_ORDER = ["mt5_deals", "ibkr_flex", "tradovate_orders", "tradingview", "generic_roundtrip", "generic"]
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
        f = best[0]["missing"][0]
        col = SIGNATURES[best[0]["name"]].get("labels", {}).get(f, f)  # the export's spelling, when known
        fail("E_MISSING_COLUMN", col, rows[best[1]]["row"], col)
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
                              "_fx": None, "_rev": d == "in/out"})
            else:
                size_field = "volume" if kind == "mt5_positions_closed" else "size"
                ot = parse_date(cell(r, m, "open_time"), "mt", row, "open_time")
                ct = parse_date(cell(r, m, "close_time"), "mt", row, "close_time")
                reordered = ct < ot  # the repeated hour of a fall-back night, flagged (F-N3)
                if reordered:
                    ct = fall_back_close(ot, ct)
                    if ct is None:
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
                            "pos_id": pos if pos != "" else None, "reordered": reordered})
    return {"executions": execs, "roundtrips": rts, "skipped": skipped, "extra": extra}


def _side_letter(v):
    v = v.strip().upper()
    if v.startswith("B") or v in ("LONG", "COVER"):
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
        reordered = ct < ot  # the repeated hour of a fall-back night, flagged (F-N3)
        if reordered:
            ct = fall_back_close(ot, ct)
            if ct is None:
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
                    "currency": cur, "unit": cur if cur else "points", "pos_id": None, "reordered": reordered})
    return {"executions": execs, "roundtrips": rts, "skipped": skipped, "extra": {}}


_RE_CANCEL_SIDE = re.compile(r"\(CA\.?\)", re.ASCII)


def _apply_cancels(execs, cancels, skipped):
    """IBKR cancellation rows take back an earlier execution (same symbol, side, qty, price,
    latest at or before the cancellation's time). Mirrors applyCancels() in ibkr.js."""
    for c in cancels:
        best = -1
        for k, e in enumerate(execs):
            if e is None or e["symbol"] != c["symbol"] or e["side"] != c["side"] or e["qty"] != c["qty"] \
                    or e["price"] != c["price"] or e["ts"] > c["ts"]:
                continue
            if best == -1 or e["ts"] >= execs[best]["ts"]:
                best = k
        if best == -1:
            _skip(skipped, "cancel_unmatched")
            continue
        execs[best] = None
        _skip(skipped, "cancelled")
        _skip(skipped, "cancelled")
    return [e for e in execs if e is not None]


def parse_ibkr(rows, hi, m):
    execs, cancels, skipped = [], [], {}
    for r in rows[hi + 1:]:
        if _empty(r["cells"]):
            continue
        row = r["row"]
        level = cell(r, m, "level").upper()
        if level != "" and level != "EXECUTION":
            _skip(skipped, "not_execution")
            continue
        side_text = cell(r, m, "side").upper()
        code_toks = [x.strip() for x in cell(r, m, "code").upper().split(";")]
        is_cancel = bool(_RE_CANCEL_SIDE.search(side_text)) or "CA" in code_toks
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
        e = {"row": row, "ts": ts, "symbol": symbol, "side": side, "qty": qty, "price": price,
             "fee": fee, "currency": cur, "oc": oc, "pos_id": None, "pnl_reported": realized,
             "multiplier": mult, "_unit": cur if cur else "points", "_fx": fx, "_rev": has_o and has_c}
        (cancels if is_cancel else execs).append(e)
    return {"executions": _apply_cancels(execs, cancels, skipped), "roundtrips": [], "skipped": skipped, "extra": {}}


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


_PARTIAL_STATUSES = ("canceled", "cancelled", "expired")


def _filled_some(raw, row):
    """A Canceled/Expired order that filled part of its size is a fill of that part (D8)."""
    v = parse_number(raw, row, "qty")
    return v is not None and v != 0


def parse_tradovate(rows, hi, m):
    execs, skipped = [], {}
    for r in rows[hi + 1:]:
        if _empty(r["cells"]):
            continue
        row = r["row"]
        status = cell(r, m, "status").strip().lower()
        if status != "filled" and not (status in _PARTIAL_STATUSES and _filled_some(cell(r, m, "qty"), row)):
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


_TV_SYMBOLS = "$€£¥"
_TV_SIGNS = "+-−"
_RE_TV_PRE = re.compile(r"^[A-Za-z]{3}( |(?=[0-9+\-−.,]))")
_RE_TV_SUF = re.compile(r"(^|[0-9.,] ?)[A-Za-z]{3}$")
TV_MONEY_FIELDS = ["price", "commission"]


def strip_currency(raw):
    """A money cell's currency code or symbol, before or after the number, removed ("0.50 USD",
    "USD 0.50", "$0.50", "-$0.50"); anything else unchanged. Mirrors stripCurrency()."""
    s = clean(raw)
    sign = ""
    cut = False
    if len(s) > 1 and s[0] in _TV_SIGNS:
        nxt = (s[2] if len(s) > 2 else "") if s[1] == " " else s[1]
        if not re.search(r"[0-9.,]", nxt):
            sign = s[0]
            s = s[1:]
            if s.startswith(" "):
                s = s[1:]
    if s != "" and s[0] in _TV_SYMBOLS:
        s = s[1:]
        if s.startswith(" "):
            s = s[1:]
        cut = True
    elif _RE_TV_PRE.search(s) and s[:3].upper() in _ISO_SET:
        s = s[3:]
        if s.startswith(" "):
            s = s[1:]
        cut = True
    if s != "" and s[-1] in _TV_SYMBOLS:
        s = s[:-1]
        if s.endswith(" "):
            s = s[:-1]
        cut = True
    elif _RE_TV_SUF.search(s) and len(s) > 3 and s[-3:].upper() in _ISO_SET:
        s = s[:-3]
        if s.endswith(" "):
            s = s[:-1]
        cut = True
    return sign + s if cut else clean(raw)


def strip_currency_cells(rows, m):
    """Before resolve_number_style, so "1.500 USD" counts as evidence like "1.500". In place."""
    for r in rows:
        for f in TV_MONEY_FIELDS:
            i = m.get(f)
            if i is not None and i < len(r["cells"]):
                r["cells"][i] = strip_currency(r["cells"][i])


def _tv_skip_reason(status):
    if status == "rejected":
        return "rejected"
    if status in ("cancelled", "canceled"):
        return "cancelled"
    return "not_filled"


def parse_tradingview(rows, hi, m):
    """TradingView Order History: one row per order; each Filled order is one execution at its
    Closing time. Mirrors parseTradingView() in tradingview.js."""
    execs, skipped = [], {}
    for r in rows[hi + 1:]:
        if _empty(r["cells"]):
            continue
        row = r["row"]
        status = cell(r, m, "status").strip().lower()
        if status != "filled":
            _skip(skipped, _tv_skip_reason(status))
            continue
        side = _side_letter(cell(r, m, "side"))
        if side is None:
            _skip(skipped, "bad_side")
            continue
        symbol = cell(r, m, "symbol")
        if symbol == "":
            _skip(skipped, "no_symbol")
            continue
        qty = abs(req_number(cell(r, m, "qty"), row, "qty"))
        if qty == 0:
            _skip(skipped, "zero_qty")
            continue
        price = req_number(cell(r, m, "price"), row, "price")
        c = opt_number(cell(r, m, "commission"), row, "commission")
        fee = c if c > 0 else 0.0
        credit = -c if c < 0 else 0.0  # a rebate: a credit, not a negative fee (as mt.js's net credit)
        ts = parse_date(cell(r, m, "time"), "generic", row, "time")
        execs.append({"row": row, "ts": ts, "symbol": symbol, "side": side, "qty": qty, "price": price,
                      "fee": fee, "currency": None, "oc": None, "pos_id": None, "pnl_reported": None,
                      "multiplier": 1, "_unit": "points", "_fx": None, "_credit": credit})
    return {"executions": execs, "roundtrips": [], "skipped": skipped, "extra": {}}


# ----------------------------------------------------------------- trades

UNIT = 1e8  # positions are tracked in 1e-8 lots so 0.1 + 0.2 - 0.3 is exactly flat


def round_half_away(x):
    return int(math.floor(abs(x) + 0.5)) * (1 if x >= 0 else -1)


def _new_trade(e, dr, seq):
    return {"symbol": e["symbol"], "dir": dr, "open_ts": e["ts"], "close_ts": None, "peak": 0,
            "entry_qty": 0.0, "entry_not": 0.0, "exit_qty": 0.0, "exit_not": 0.0, "fees": 0.0,
            "credit": 0.0, "rep_sum": 0.0, "rep_missing": False, "fills": 0, "multiplier": e["multiplier"],
            "currency": e["currency"], "unit": e["_unit"], "fx": None, "seq": seq}


def chrono_order(execs):
    """Execution indexes in time order; same-time fills keep their file order, read in the
    file's own direction (newest-first file -> bottom-up). Mirrors chronoOrder()."""
    up = down = 0
    for k in range(1, len(execs)):
        d = execs[k]["ts"] - execs[k - 1]["ts"]
        if d > 0:
            up += 1
        elif d < 0:
            down += 1
    sign = -1 if down > up else 1
    return sorted(range(len(execs)), key=lambda k: (execs[k]["ts"], sign * execs[k]["row"], sign * k))


# ----------------------------------------------------------------- positions opened before the file
# Mirrors lotKind(), lotWalk(), preFileLots(), nettingWalk(), tieOrder(), tradeKey() and
# buildTrades() in trades.js, operation for operation; the comments there explain the
# rules. In short: with open/close codes, a close bigger than the units opened in the file
# (per direction) closes a lot from before the file, and everything from the start of the
# file through the last such close is left out (netting: the whole stretch up to a flat
# count; MT5 hedging: that direction's fills). A reversal with nothing in the file to close
# opens a lot of unknown size; one that closed more than the file opened shows when the
# first direction opens again. Same-second fills are also read closes-first and
# opens-first; only trades all readings agree on are kept.

LONG = 0
SHORT = 1


def lot_kind(e):
    if e["oc"] == "open":
        return "open"
    if e["oc"] == "close":
        return "close"
    return "reverse" if e.get("_rev") else "net"


def lot_walk(execs, lst, allow_hedging):
    n = len(lst)
    inv = [0, 0]
    spans = [[], []]
    unknown_from = [-1, -1]
    rev_at = [-1, -1]
    carried = [False, False]
    flat = [True] * n
    st = {"ambiguous": False, "hedged": False, "hedges": 0, "signs": 0}

    def excess(d, i):
        st["signs"] += 1
        if unknown_from[d] >= 0:
            spans[d].append((unknown_from[d], i))
            unknown_from[d] = -1
        else:
            spans[d].append((0, i))
            carried[d] = True
            if allow_hedging and inv[1 - d] > 0:
                st["hedged"] = True
                st["hedges"] += 1
        inv[d] = 0
        rev_at[d] = -1

    for i, k in enumerate(lst):
        e = execs[k]
        q = round_half_away(e["qty"] * UNIT)
        if q == 0:
            flat[i] = i == 0 or flat[i - 1]
            continue
        opens = LONG if e["side"] == "buy" else SHORT
        closes = 1 - opens
        kind = lot_kind(e)
        if kind == "open" and (inv[closes] > 0 or unknown_from[closes] >= 0):
            if rev_at[closes] >= 0 or unknown_from[closes] >= 0:
                spans[opens].append((0, i - 1))
                spans[closes].append((0, i - 1))
                if rev_at[closes] >= 0:
                    carried[opens] = True
                st["signs"] += 1
                inv[closes] = 0
                rev_at[closes] = -1
                unknown_from[closes] = -1
                st["ambiguous"] = True
            elif allow_hedging:
                st["hedged"] = True
        if kind == "open":
            inv[opens] += q
        elif kind == "close":
            if q <= inv[closes]:
                inv[closes] -= q
                if inv[closes] == 0:
                    rev_at[closes] = -1
            else:
                excess(closes, i)
        elif kind == "reverse" and inv[closes] == 0:
            excess(closes, i)
            if unknown_from[opens] < 0:
                unknown_from[opens] = i
            st["ambiguous"] = True
        else:
            c = min(q, inv[closes])
            inv[closes] -= c
            if inv[closes] == 0:
                rev_at[closes] = -1
            if kind == "reverse" and q > c and inv[opens] == 0:
                rev_at[opens] = i
            inv[opens] += q - c
        flat[i] = inv[LONG] == 0 and inv[SHORT] == 0 and unknown_from[LONG] < 0 and unknown_from[SHORT] < 0
    for d in (LONG, SHORT):
        if unknown_from[d] >= 0:
            st["ambiguous"] = True
    excluded = set()
    if st["hedged"]:
        for d in (LONG, SHORT):
            if unknown_from[d] >= 0:
                spans[d].append((unknown_from[d], n - 1))
        for i, k in enumerate(lst):
            e = execs[k]
            opens = LONG if e["side"] == "buy" else SHORT
            kind = lot_kind(e)
            for d in (LONG, SHORT):
                if kind == "open":
                    touches = opens == d
                elif kind == "close":
                    touches = opens != d
                else:
                    touches = True
                if touches and any(a <= i <= b for a, b in spans[d]):
                    excluded.add(k)
    else:
        last = -1
        for d in (LONG, SHORT):
            for _a, b in spans[d]:
                last = max(last, b)
        if last >= 0:
            while last < n - 1 and not flat[last]:
                last += 1
            for i in range(last + 1):
                excluded.add(lst[i])
    return {"excluded": excluded, "carried": carried, "ambiguous": st["ambiguous"], "hedges": st["hedges"],
            "signs": st["signs"]}


def pre_file_lots(execs, order, allow_hedging):
    by_sym = {}
    for k in order:
        by_sym.setdefault(execs[k]["symbol"], []).append(k)
    excluded = set()
    ambiguous_syms = set()
    signs = {}
    open_at_start = 0
    hedges = 0
    for sym, lst in by_sym.items():
        w = lot_walk(execs, lst, allow_hedging)
        excluded |= w["excluded"]
        open_at_start += sum(1 for c in w["carried"] if c)
        if w["ambiguous"]:
            ambiguous_syms.add(sym)
        hedges += w["hedges"]
        signs[sym] = w["signs"]
    return {"excluded": excluded, "open_at_start": open_at_start, "ambiguous_syms": ambiguous_syms,
            "hedges": hedges, "signs": signs}


def netting_walk(execs, order, excluded, detect_hedging):
    pos = {}
    cur = {}
    done = []
    hedging = 0
    seq = 0
    for k in order:
        if k in excluded:
            continue
        e = execs[k]
        sym = e["symbol"]
        s = 1 if e["side"] == "buy" else -1
        q_units = round_half_away(e["qty"] * UNIT)
        if q_units == 0:
            continue
        p = pos.get(sym, 0)
        if detect_hedging and e["oc"] == "open" and p != 0 and (p > 0) != (s > 0):
            hedging += 1
        if p == 0 or (p > 0) == (s > 0):
            if p == 0:
                cur[sym] = _new_trade(e, "long" if s > 0 else "short", seq)
                seq += 1
            t = cur[sym]
            t["entry_qty"] += e["qty"]
            t["entry_not"] += e["qty"] * e["price"]
            t["fees"] += e["fee"]
            if e.get("_credit"):
                t["credit"] += e["_credit"]
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
        if e.get("_credit"):
            t["credit"] += e["_credit"] if rem_units == 0 else e["_credit"] * close_units / q_units
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
            rq = rem_units / UNIT
            nt["entry_qty"] += rq
            nt["entry_not"] += rq * e["price"]
            nt["fees"] += e["fee"] * rem_units / q_units
            if e.get("_credit"):
                nt["credit"] += e["_credit"] * rem_units / q_units
            nt["fills"] += 1
            nt["peak"] = rem_units
            if e["_fx"] is not None:
                nt["fx"] = e["_fx"]
            cur[sym] = nt
            p = s * rem_units
        pos[sym] = p
    open_n = sum(1 for v in pos.values() if v != 0)
    return {"done": done, "open_n": open_n, "hedging": hedging}


TIE_RANK = {"close": 0, "reverse": 1, "net": 1, "open": 2}


def tie_order(execs, order, opens_first):
    sign = -1 if opens_first else 1
    return sorted(order, key=lambda k: (execs[k]["ts"], sign * TIE_RANK[lot_kind(execs[k])]))


def trade_key(t):
    def r(x):
        return math.floor(x * 1e6 + 0.5)
    return (t["symbol"], t["dir"], t["open_ts"], t["close_ts"], t["peak"], t["fills"], r(t["entry_qty"]),
            r(t["entry_not"]), r(t["exit_qty"]), r(t["exit_not"]), r(t["fees"]), r(t["credit"]), r(t["rep_sum"]),
            t["rep_missing"])


def build_trades(execs, reported_mode, detect_hedging=False):
    """Flat-to-flat round trips per symbol. reported_mode: None | "gross" | "net"."""
    order = chrono_order(execs)
    lots = pre_file_lots(execs, order, detect_hedging)
    walk = netting_walk(execs, order, lots["excluded"], detect_hedging)
    done = walk["done"]
    excluded = set(lots["excluded"])
    ambiguous_syms = set(lots["ambiguous_syms"])
    others = []
    for o in (tie_order(execs, order, False), tie_order(execs, order, True)):
        if o == order or any(o == x["order"] for x in others):
            continue
        lo = pre_file_lots(execs, o, detect_hedging)
        others.append({"order": o, "lots": lo, "done": netting_walk(execs, o, lo["excluded"], detect_hedging)["done"]})
    if others:
        def keys_of(lst):
            m = {}
            for t in lst:
                m.setdefault(t["symbol"], set()).add(trade_key(t))
            return m
        mine = keys_of(done)
        for x in others:
            x["keys"] = keys_of(x["done"])
        lost = set()
        drop_all = set()
        fair_of = {}
        for sym in lots["signs"]:
            fewest = min([lots["signs"][sym]] + [x["lots"]["signs"][sym] for x in others])
            fair = [x for x in others if x["lots"]["signs"][sym] == fewest]
            fair_of[sym] = fair
            for x in fair:
                for k in x["order"]:
                    if execs[k]["symbol"] == sym and k in x["lots"]["excluded"]:
                        excluded.add(k)
            if lots["signs"][sym] > fewest:
                lost.add(sym)
                drop_all.add(sym)
                continue
            a = mine.get(sym, set())
            for x in fair:
                if a != x["keys"].get(sym, set()):
                    lost.add(sym)
        if lost:
            done = [t for t in done if t["symbol"] not in lost or (
                t["symbol"] not in drop_all and
                all(trade_key(t) in x["keys"].get(t["symbol"], set()) for x in fair_of[t["symbol"]]))]
            ambiguous_syms |= lost
            for k, e in enumerate(execs):
                if e["symbol"] in lost:
                    excluded.add(k)
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
            if t["credit"]:  # a commission rebate: part of the gross result, fees stay >= 0 (as mt.js)
                gross += t["credit"]
            pnl = gross - t["fees"]
        trades.append({"symbol": t["symbol"], "dir": t["dir"], "open_ts": t["open_ts"], "close_ts": t["close_ts"],
                       "hold_s": (t["close_ts"] - t["open_ts"]) // 1000, "qty": t["peak"] / UNIT,
                       "entry_vwap": entry_vwap, "exit_vwap": exit_vwap, "pnl": pnl, "pnl_gross": gross,
                       "fees": t["fees"], "pnl_source": src, "pnl_unit": t["unit"], "fills_n": t["fills"],
                       "currency": t["currency"], "_fx": t["fx"], "_seq": t["seq"]})
    hedging = (lots["hedges"] if detect_hedging else 0) + walk["hedging"]
    return trades, walk["open_n"], hedging, lots["open_at_start"], len(ambiguous_syms), excluded


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
                       "fills_n": 2, "currency": r["currency"], "_fx": None, "_seq": start_seq + i,
                       "_reordered": r.get("reordered") is True})
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
             "tradovate_orders": "local time, as exported",
             "tradingview": "as exported, with no time zone stated", "generic": "as in the file",
             "generic_roundtrip": "as in the file", "mapped": "as in the file"}


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


def parse_file(data, mapping=None):
    return parse_files([data], mapping)


def finish(fmt, verified, res, mode, tz_label):
    """Everything after parsing: trades, warnings, currency groups, order, ids. Mirrors finish()."""
    extra = res["extra"]
    warnings = []
    if extra.get("mapped"):
        warnings.append(warning("W_MAPPED", 0))
    elif not verified:
        warnings.append(warning("W_UNVERIFIED_FORMAT", 0))
    if extra.get("orders_averaged"):
        warnings.append(warning("W_ORDERS_AVERAGED", 0))
    skipped = res["skipped"]
    if skipped:
        n = 0
        for v in skipped.values():
            n += v
        warnings.append(warning("W_SKIPPED_ROWS", n))
    if extra.get("duplicate_rows"):
        warnings.append(warning("W_DUPLICATE_ROWS", extra["duplicate_rows"]))
    if extra.get("overlap_rows"):
        warnings.append(warning("W_OVERLAP_ROWS", extra["overlap_rows"]))
    if extra.get("currency_ignored"):
        warnings.append(warning("W_CURRENCY_IGNORED", 0))

    executions = res["executions"]
    open_n = extra.get("open_positions", 0)
    hedging = 0
    open_at_start = 0
    ambiguous = 0
    if fmt == "mt5" and extra.get("has_closed_positions"):
        trades = roundtrip_trades(res["roundtrips"], 0)
    elif res["roundtrips"]:
        trades = roundtrip_trades(res["roundtrips"], 0)
        executions = roundtrip_executions(res["roundtrips"])
    else:
        trades, o, hedging, open_at_start, ambiguous, excluded = build_trades(executions, mode, detect_hedging=(fmt == "mt5"))
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
    if ambiguous:
        warnings.append(warning("W_AMBIGUOUS_FILLS", ambiguous))
    if extra.get("pnl_sign"):
        warnings.append(warning("W_PNL_SIGN", extra["pnl_sign"]))
    pts = 0
    if fmt == "tradovate_orders" or extra.get("futures_sizes"):
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

    dst = 0
    for t in trades:
        if spans_dst_night(t["open_ts"], t["close_ts"]):
            dst += 1
    if dst:
        warnings.append(warning("W_DST", dst))
    reordered = sum(1 for t in trades if t.get("_reordered"))
    if reordered:
        warnings.append(warning("W_CLOSE_BEFORE_OPEN", reordered))
    trades.sort(key=lambda t: (t["close_ts"], t["open_ts"], t["symbol"], t["_seq"]))
    if not trades:
        fail("E_NO_CLOSED_TRADES")
    # dates but no times: the paid server's rule (habits.mjs isDateOnlyRow, DATES_ONLY_SHARE)
    n_date_only = 0
    for t in trades:
        if t["open_ts"] % DAY_MS_ == 0 and t["hold_s"] % 86400 == 0:
            n_date_only += 1
    dates_only = 20 * n_date_only >= len(trades)
    if dates_only:
        warnings.append(warning("W_DATES_ONLY", n_date_only))
    out_trades = []
    for i, t in enumerate(trades):
        d = {"id": "t%d" % (i + 1)}
        d.update(_strip(t))
        out_trades.append(d)
    out = {
        "format": fmt,
        "verified_format": verified,
        "executions": [_strip(e) for e in executions],
        "trades": out_trades,
        "skipped": skipped,
        "warnings": warnings,
        "tz_label": tz_label,
        "currency_groups": groups,
        "dates_only": dates_only,
        "n_date_only": n_date_only,
    }
    if fmt == "mapped":
        out["preset"] = extra.get("preset")
    return out


# ----------------------------------------------------------------- the universal importer
# Mirrors site/static/js/engine/mapped.js: the block list, money cells, the mapping's checks,
# parse_mapped() and the several-files merge.

BLOCKED = {
    "contains": ["account", "acct", "wallet", "email", "phone"],
    "exact": ["name", "fullname", "firstname", "lastname", "owner", "user", "uid", "userid", "username", "address",
              "clientid", "traderid", "comment", "comments", "note", "notes", "remark", "remarks"],
}


def is_blocked(norm):
    return norm in BLOCKED["exact"] or any(w in norm for w in BLOCKED["contains"])


_MONEY_SYMBOLS = "$€£¥₹"
_MONEY_SIGNS = "+-−"


def money_clean(raw):
    orig = clean(raw)
    s = orig
    if s == "":
        return s
    neg = False
    if len(s) > 2 and s[0] == "(" and s[-1] == ")":
        neg, s = True, clean(s[1:-1])
    elif len(s) > 1 and s[-1] in ("-", "−"):
        neg, s = True, clean(s[:-1])
    sign = ""
    if s != "" and s[0] in _MONEY_SIGNS:
        sign, s = s[0], clean(s[1:])
    if s != "" and s[0] in _MONEY_SYMBOLS:
        s = clean(s[1:])
    elif len(s) > 3 and re.match(r"^[A-Za-z]{3} ?[0-9.,]", s, re.ASCII) and s[:3].upper() in _ISO_SET:
        s = clean(s[3:])
    if s != "" and s[-1] in _MONEY_SYMBOLS:
        s = clean(s[:-1])
    elif len(s) > 3 and re.search(r"[0-9.,] ?[A-Za-z]{3}$", s, re.ASCII) and s[-3:].upper() in _ISO_SET:
        s = clean(s[:-3])
    if sign == "" and s != "" and s[0] in _MONEY_SIGNS:
        sign, s = s[0], clean(s[1:])
    if s == "" or (neg and sign != ""):
        return orig
    return ("-" if neg or sign in ("-", "−") else "") + s


LAYOUTS = ["fills", "orders", "roundtrips"]
MAP_FIELDS = ["date", "time", "symbol", "side", "qty", "price", "fees", "currency", "status",
              "open_time", "close_time", "direction", "open_price", "close_price", "pnl"]
_LAYOUT_FIELDS = {
    "fills": {"required": ["date", "symbol", "side", "qty", "price"], "optional": ["time", "fees", "currency", "status"]},
    "roundtrips": {"required": ["open_time", "close_time", "symbol", "direction", "qty", "open_price", "close_price"],
                   "optional": ["fees", "currency", "pnl"]},
}
_LAYOUT_FIELDS["orders"] = _LAYOUT_FIELDS["fills"]
_NUMERIC = {"fills": ["qty", "price"], "orders": ["qty", "price"], "roundtrips": ["qty", "open_price", "close_price", "pnl"]}
_RULE_KINDS = ["eq", "prefix", "contains"]
STATUS_KEEP = ["filled", "fully filled", "executed", "complete", "completed", "partially filled", "partial fill",
               "partially executed"]
MAX_FEE_COLUMNS = 3
MAPPED_TZ = {"plain": "as in the file", "zone": "as in the file; time zone labels ignored", "utc": "UTC, as exported"}


def _bad(field):
    fail("E_BAD_MAPPING", "bad " + field, None, field)


def _is_idx(v):
    return isinstance(v, int) and not isinstance(v, bool) and v >= 0


def norm_value(v):
    return clean(v).lower()


def _check_values(o, allowed, field):
    if o is None:
        return
    if not isinstance(o, dict):
        _bad(field)
    for k, v in o.items():
        if len(k) > 40 or v not in allowed:
            _bad(field)


def _check_rules(lst, allowed, field):
    if lst is None:
        return
    if not isinstance(lst, list) or len(lst) > 40:
        _bad(field)
    for r in lst:
        if (not isinstance(r, list) or len(r) != 3 or r[0] not in _RULE_KINDS or not isinstance(r[1], str)
                or len(r[1]) > 40 or r[2] not in allowed):
            _bad(field)


def check_mapping(mp):
    """The mapping's own shape. -> side_from ('column' | 'sign'). Mirrors checkMapping()."""
    if not isinstance(mp, dict) or mp.get("v") != 1:
        _bad("v")
    if mp.get("layout") not in LAYOUTS:
        _bad("layout")
    if not _is_idx(mp.get("header_row")):
        _bad("header_row")
    if mp.get("delimiter") is not None and mp["delimiter"] not in (",", ";", "\t"):
        _bad("delimiter")
    if not isinstance(mp.get("cols"), dict):
        _bad("cols")
    if not isinstance(mp.get("headers"), dict):
        _bad("headers")
    lf = _LAYOUT_FIELDS[mp["layout"]]
    for k in mp["cols"]:
        if k not in MAP_FIELDS:
            _bad(k)
    for f in MAP_FIELDS:
        v = mp["cols"].get(f)
        if v is None or (f == "fees" and isinstance(v, list) and len(v) == 0):
            continue
        if f not in lf["required"] and f not in lf["optional"]:
            _bad(f)
        if f == "fees":
            if not isinstance(v, list) or len(v) > MAX_FEE_COLUMNS or not all(_is_idx(i) for i in v):
                _bad(f)
        elif not _is_idx(v):
            _bad(f)
    side_from = "column" if mp.get("side_from") is None else mp["side_from"]
    if side_from not in ("column", "sign"):
        _bad("side_from")
    if side_from == "sign" and mp["layout"] == "roundtrips":
        _bad("side_from")
    for f in lf["required"]:
        if f == "side" and side_from == "sign":
            continue
        if mp["cols"].get(f) is None:
            _bad(f)
    _check_values(mp.get("side_values"), ["buy", "sell", "skip"], "side_values")
    _check_rules(mp.get("side_rules"), ["buy", "sell", "skip"], "side_rules")
    if mp.get("side_default") is not None and mp["side_default"] != "skip":
        _bad("side_default")
    _check_values(mp.get("status_values"), ["keep", "skip"], "status_values")
    _check_rules(mp.get("status_rules"), ["keep", "skip"], "status_rules")
    if mp.get("date_format") not in DATE_FORMATS:
        _bad("date_format")
    if mp.get("number_style") is not None and mp["number_style"] not in ("dot", "comma"):
        _bad("number_style")
    if mp.get("currency") is not None and mp["currency"] not in _ISO_SET:
        _bad("currency")
    if mp.get("tz") is not None and mp["tz"] != "utc":
        _bad("tz")
    if mp.get("preset") is not None and not (isinstance(mp["preset"], str)
                                            and re.match(r"^[a-z0-9_]{1,40}$", mp["preset"], re.ASCII)):
        _bad("preset")
    for f in ("futures_sizes", "section", "trim_ragged", "keep_partial"):
        if mp.get(f) is not None and not isinstance(mp[f], bool):
            _bad(f)
    if mp.get("futures_sizes") and mp["layout"] == "roundtrips":
        _bad("futures_sizes")
    src = mp.get("source")
    if src is not None:
        if not isinstance(src, dict) or src.get("kind") != "html" or not _is_idx(src.get("table")):
            _bad("source")
    return side_from


def bind_mapping(mp, header):
    m = {}

    def use(key, field, i):
        if i >= len(header):
            _bad(field)
        h = norm_header(header[i])
        if mp["headers"].get(str(i)) != h:
            _bad(field)
        if is_blocked(h):
            _bad(field)
        m[key] = i

    for f in MAP_FIELDS:
        v = mp["cols"].get(f)
        if v is None:
            continue
        if f == "fees":
            for k, i in enumerate(v):
                use("fee%d" % k, "fees", i)
        else:
            use(f, f, v)
    return m


def data_rows_after(rows, hdr_at, section):
    out = []
    prev = rows[hdr_at]["row"]
    for r in rows[hdr_at + 1:]:
        if section and (r["row"] != prev + 1 or len([c for c in r["cells"] if c != ""]) == 1):
            break
        out.append(r)
        prev = r["row"]
    return out


def is_no_data(cells, width):
    return width >= 3 and len([c for c in cells if c != ""]) == 1


def _cell_at(r, i):
    return "" if i is None or i >= len(r["cells"]) else r["cells"][i]


def _lookup(raw, values, rules):
    k = norm_value(raw)
    if values is not None and k in values:
        return values[k]
    if rules is not None:
        for kind, text, res in rules:
            if (kind == "eq" and k == text) or (kind == "prefix" and k.startswith(text)) or \
                    (kind == "contains" and text in k):
                return res
    return None


def _side_of(raw, mp):
    listed = mp.get("side_values") is not None or mp.get("side_rules") is not None
    v = _lookup(raw, mp.get("side_values"), mp.get("side_rules"))
    if v is not None:
        return v
    if listed:
        return "skip" if mp.get("side_default") == "skip" else None
    if mp["layout"] == "roundtrips":
        d = clean(raw).lower()
        if d.startswith("l") or d.startswith("b"):
            return "buy"
        if d.startswith("s"):
            return "sell"
        return None
    return _side_letter(raw)


def _status_kept(raw, mp):
    listed = mp.get("status_values") is not None or mp.get("status_rules") is not None
    v = _lookup(raw, mp.get("status_values"), mp.get("status_rules"))
    if v is not None:
        return v == "keep"
    if listed:
        return False
    return norm_value(raw) in STATUS_KEEP


def _status_reason(raw):
    v = norm_value(raw)
    if "reject" in v:
        return "rejected"
    if "cancel" in v:
        return "cancelled"
    return "not_filled"


def futures_root(symbol):
    c = clean(symbol).upper().split(" ")[0]
    mm = _RE_CONTRACT.match(c)
    return mm.group(1) if mm else c


def number_question(rows, idxs, delimiter):
    dot = comma = dot3 = lone = False
    for r in rows:
        for i in idxs:
            if i >= len(r["cells"]):
                continue
            c = money_clean(r["cells"][i])
            sh = number_shape(c)
            if sh == "dot":
                dot = True
            elif sh == "comma":
                comma = True
            elif sh == "dot3":
                dot3 = True
            elif sh == "neutral" and re.match(r"^[+-]?\d+,\d{3}$", c.replace("−", "-"), re.ASCII):
                lone = True
    if dot or comma:
        return "number_style" if lone else None
    if lone or (dot3 and delimiter != ","):
        return "number_style"
    return None


def parse_mapped(rows, mp, side_from, kind, delimiter):
    """One file's rows through a checked mapping -> (parser result, data row count)."""
    hdr_at = next((k for k, r in enumerate(rows) if r["row"] == mp["header_row"] + 1), -1)
    if hdr_at < 0:
        _bad("header_row")
    header = rows[hdr_at]["cells"]
    m = bind_mapping(mp, header)
    layout = mp["layout"]
    data = data_rows_after(rows, hdr_at, mp.get("section") is True)
    skipped = {}
    req = [f for f in _LAYOUT_FIELDS[layout]["required"] if not (f == "side" and side_from == "sign")]
    kept = []
    n_data = 0
    for r in data:
        if _empty(r["cells"]):
            continue
        n_data += 1
        if mp.get("trim_ragged") and len(r["cells"]) * 2 < len(header):
            _skip(skipped, "no_data")
            continue
        if is_no_data(r["cells"], len(header)) or all(_cell_at(r, m.get(f)) == "" for f in req):
            _skip(skipped, "no_data")
            continue
        kept.append(r)
    if n_data == 0:
        fail("E_HEADER_ONLY")
    if n_data > MAX_ROWS:
        fail("E_TOO_LARGE")
    if kind == "csv":
        check_quoting([rows[hdr_at]] + data, 0, m)
    cm, cur_ignored = check_currency_column(kept, m)
    num_map = {}
    for f in _NUMERIC[layout]:
        if f in cm:
            num_map[f] = cm[f]
    for k in ("fee0", "fee1", "fee2"):
        if k in cm:
            num_map[k] = cm[k]
    num_idx = list(num_map.values())
    for r in kept:
        for i in num_idx:
            if i < len(r["cells"]):
                r["cells"][i] = money_clean(r["cells"][i])
    chosen = mp.get("number_style")
    if chosen is not None:
        fallback = chosen
    else:
        fallback = "dot" if (kind == "csv" and delimiter == ",") or kind == "html" else None
    style = resolve_number_style([{"rows": kept, "map": num_map, "fields": list(num_map.keys())}], fallback)
    if chosen is not None and style != chosen:
        fail("E_BAD_NUMBER", "does not fit the chosen number style")
    if chosen is not None:
        for r in kept:
            for i in num_idx:
                if i >= len(r["cells"]):
                    continue
                bare = r["cells"][i].replace("−", "-")
                if chosen == "dot" and re.match(r"^[+-]?\d{1,3},\d{3}$", bare, re.ASCII):
                    r["cells"][i] = bare.replace(",", "", 1)
                elif chosen == "comma" and re.match(r"^[+-]?\d+,\d{3}$", bare, re.ASCII):
                    r["cells"][i] = bare.replace(",", ".", 1)
    dup = 0
    idx = list(cm.values())
    seen_keys = set()
    for r in kept:
        key = "\u0001".join(_cell_at(r, i) for i in idx)
        if key in seen_keys:
            dup += 1
        else:
            seen_keys.add(key)
    seen = {"zone": False}
    fmt = mp["date_format"]
    execs, rts = [], []
    pnl_sign = 0

    def fee_of(r, row):
        fee = 0
        for k in ("fee0", "fee1", "fee2"):
            if k in cm:
                fee += abs(opt_number(_cell_at(r, cm[k]), row, "fees"))
        return fee

    for r in kept:
        row = r["row"]
        if layout == "roundtrips":
            d = _side_of(_cell_at(r, cm.get("direction")), mp)
            if d == "skip":
                _skip(skipped, "not_a_trade")
                continue
            if d is None:
                _skip(skipped, "bad_side")
                continue
            dr = "long" if d == "buy" else "short"
            symbol = _cell_at(r, cm.get("symbol"))
            if symbol == "":
                _skip(skipped, "no_symbol")
                continue
            ot = parse_date_fmt(_cell_at(r, cm.get("open_time")), fmt, row, "open_time", seen)
            ct = parse_date_fmt(_cell_at(r, cm.get("close_time")), fmt, row, "close_time", seen)
            reordered = ct < ot
            if reordered:
                ct = fall_back_close(ot, ct)
                if ct is None:
                    fail("E_BAD_DATE", "close before open", row, "close_time")
            qty = abs(req_number(_cell_at(r, cm.get("qty")), row, "qty"))
            if qty == 0:
                _skip(skipped, "zero_qty")
                continue
            op = req_number(_cell_at(r, cm.get("open_price")), row, "open_price")
            cp = req_number(_cell_at(r, cm.get("close_price")), row, "close_price")
            fee = fee_of(r, row)
            if "pnl" in cm:
                pv = opt_number(_cell_at(r, cm["pnl"]), row, "pnl")
                g = (cp - op) * (1 if dr == "long" else -1)
                if pv != 0 and g != 0 and (pv > 0) != (g > 0):
                    pnl_sign += 1
            cur = _cell_at(r, cm.get("currency")).upper() or (mp.get("currency") or None)
            rts.append({"row": row, "symbol": symbol, "dir": dr, "open_ts": ot, "close_ts": ct, "qty": qty,
                        "entry": op, "exit": cp, "fees": fee, "pnl_gross": None, "reported": False,
                        "currency": cur, "unit": cur if cur else "points", "pos_id": None, "reordered": reordered})
            continue
        side = None
        if side_from == "column":
            side = _side_of(_cell_at(r, cm.get("side")), mp)
            if side == "skip":
                _skip(skipped, "not_a_trade")
                continue
        if "status" in cm:
            st = _cell_at(r, cm["status"])
            if not _status_kept(st, mp):
                v = norm_value(st)
                partial = mp.get("keep_partial") is True and ("cancel" in v or "expire" in v) and \
                    (parse_number(_cell_at(r, cm.get("qty")), row, "qty") or 0) != 0
                if not partial:
                    _skip(skipped, _status_reason(st))
                    continue
        if side_from == "column" and side is None:
            _skip(skipped, "bad_side")
            continue
        symbol = _cell_at(r, cm.get("symbol"))
        if symbol == "":
            _skip(skipped, "no_symbol")
            continue
        d = _cell_at(r, cm.get("date"))
        t = _cell_at(r, cm.get("time"))
        ts = parse_date_fmt(d + " " + t if t != "" and d != "" else d, fmt, row, "date", seen)
        q = req_number(_cell_at(r, cm.get("qty")), row, "qty")
        if side_from == "sign" and q != 0:
            side = "sell" if q < 0 else "buy"
        q = abs(q)
        if q == 0:
            _skip(skipped, "zero_qty")
            continue
        price = req_number(_cell_at(r, cm.get("price")), row, "price")
        fee = fee_of(r, row)
        cur = _cell_at(r, cm.get("currency")).upper() or (mp.get("currency") or None)
        mult = 1
        unit = cur if cur else "points"
        if mp.get("futures_sizes"):
            root = futures_root(symbol)
            if root in CME_MULTIPLIERS:
                mult = CME_MULTIPLIERS[root]
                cur = cur or "USD"
                unit = cur
            else:
                cur = None
                unit = "points"
        execs.append({"row": row, "ts": ts, "symbol": symbol, "side": side, "qty": q, "price": price, "fee": fee,
                      "currency": cur, "oc": None, "pos_id": None, "pnl_reported": None, "multiplier": mult,
                      "_unit": unit, "_fx": None})
    extra = {"duplicate_rows": dup, "currency_ignored": cur_ignored, "mapped": not mp.get("preset"),
             "preset": mp.get("preset") or None, "orders_averaged": layout == "orders",
             "futures_sizes": mp.get("futures_sizes") is True, "pnl_sign": pnl_sign, "zone_ignored": seen["zone"],
             "tz": mp.get("tz") or None}
    return {"executions": execs, "roundtrips": rts, "skipped": skipped, "extra": extra}, n_data


def mapped_tz_label(extra):
    if extra.get("tz") == "utc":
        return MAPPED_TZ["utc"]
    return MAPPED_TZ["zone"] if extra.get("zone_ignored") else MAPPED_TZ["plain"]


def _exec_key(e):
    return (e["ts"], e["symbol"], e["side"], e["qty"], e["price"], e["fee"])


def _rt_key(r):
    return (r["symbol"], r["dir"], r["open_ts"], r["close_ts"], r["qty"], r["entry"], r["exit"])


def drop_overlap(lists, key_of):
    keep = {}
    for lst in lists:
        c = {}
        for x in lst:
            k = key_of(x)
            c[k] = c.get(k, 0) + 1
        for k, n in c.items():
            if n > keep.get(k, 0):
                keep[k] = n
    used = {}
    out = []
    dropped = 0
    for lst in lists:
        for x in lst:
            k = key_of(x)
            used[k] = used.get(k, 0) + 1
            if used[k] <= keep[k]:
                out.append(x)
            else:
                dropped += 1
    return out, dropped


def first_ts(res):
    t = math.inf
    for e in res["executions"]:
        if e["ts"] < t:
            t = e["ts"]
    for r in res["roundtrips"]:
        if r["open_ts"] < t:
            t = r["open_ts"]
    return t


_SUM_EXTRA = ["duplicate_rows", "open_positions", "pnl_sign"]
_OR_EXTRA = ["currency_ignored", "has_closed_positions", "has_deals", "zone_ignored"]


def merge_parsed(parts):
    extra = dict(parts[0]["res"]["extra"])
    for k in _SUM_EXTRA:
        if k in extra:
            extra[k] = 0
    for k in _OR_EXTRA:
        if k in extra:
            extra[k] = False
    skipped = {}
    offset = 0
    for p in parts:
        for e in p["res"]["executions"]:
            e["row"] += offset
        for r in p["res"]["roundtrips"]:
            r["row"] += offset
        offset += p["last_row"]
        for k, n in p["res"]["skipped"].items():
            skipped[k] = skipped.get(k, 0) + n
        for k in _SUM_EXTRA:
            if k in p["res"]["extra"]:
                extra[k] = extra.get(k, 0) + p["res"]["extra"][k]
        for k in _OR_EXTRA:
            if k in p["res"]["extra"]:
                extra[k] = extra.get(k) or p["res"]["extra"][k]
    ex, d1 = drop_overlap([p["res"]["executions"] for p in parts], _exec_key)
    rt, d2 = drop_overlap([p["res"]["roundtrips"] for p in parts], _rt_key)
    extra["overlap_rows"] = d1 + d2
    return {"executions": ex, "roundtrips": rt, "skipped": skipped, "extra": extra}


def is_paste(item):
    return isinstance(item, dict) and isinstance(item.get("paste"), str)


def read_rows(item, delimiter=None):
    """-> {kind, delimiter, rows}. Mirrors readRows() in index.js."""
    if is_paste(item):
        return {"kind": "paste", "delimiter": "\t", "rows": from_paste(item["paste"])}
    text = decode_bytes(item)
    if is_html(text):
        return {"kind": "html", "delimiter": None, "rows": html_rows(text)}
    delim = delimiter or sniff_delimiter(text)
    return {"kind": "csv", "delimiter": delim, "rows": parse_csv(text, delim)}


def _read_auto(src):
    rows = src["rows"]
    if src["kind"] == "html":
        det = detect_html(rows)
        groups = [_html_number_group(t) for t in det["tables"]]
        resolve_number_style(groups, "dot")
        dup = 0
        n_data = 0
        for g in groups:
            dup += count_duplicate_rows(g["rows"], g["map"])
            n_data += len(g["rows"])
        res = parse_mt(det["tables"])
        res["extra"]["duplicate_rows"] = dup
        res["extra"]["currency_ignored"] = False
        return {"fmt": det["format"], "verified": False, "res": res, "mode": "gross",
                "tz": TZ_LABELS[det["format"]], "n_data": n_data, "shape": det["format"]}
    delim = src["delimiter"]
    if not rows:
        fail("E_EMPTY")
    det = detect_csv(rows)
    name, hi = det["format"], det["header_index"]
    # a Currency column whose cells are not all ISO codes is not read at all (F-D3)
    m, currency_ignored = check_currency_column(rows[hi + 1:], det["map"])
    data_rows = [r for r in rows[hi + 1:] if not _empty(r["cells"])]
    if not data_rows:
        fail("E_HEADER_ONLY")
    if len(data_rows) > MAX_ROWS:
        fail("E_TOO_LARGE")
    check_quoting(rows, hi, det["map"])
    if name == "tradingview":
        strip_currency_cells(rows[hi + 1:], m)
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
    elif name == "tradingview":
        fmt, res, mode = "tradingview", parse_tradingview(rows, hi, m), None
    elif name == "generic_roundtrip":
        fmt, res, mode = "generic_roundtrip", parse_generic_roundtrip(rows, hi, m), None
    else:
        fmt, res, mode = "generic", parse_generic(rows, hi, m), None
    res["extra"]["duplicate_rows"] = dup
    res["extra"]["currency_ignored"] = currency_ignored
    return {"fmt": fmt, "verified": verified, "res": res, "mode": mode, "tz": TZ_LABELS[fmt],
            "n_data": len(data_rows), "shape": fmt}


def _header_shape(rows, mp):
    for r in rows:
        if r["row"] == mp["header_row"] + 1:
            return "\u0001".join(norm_header(c) for c in r["cells"])
    return None


def _read_mapped(src, mp, side_from, expect):
    rows = src["rows"]
    if src["kind"] == "html":
        if not mp.get("source"):
            _bad("source")
        rows = [r for r in rows if r["table"] == mp["source"]["table"]]
    elif mp.get("source"):
        _bad("source")
    if not rows:
        fail("E_EMPTY")
    shape = _header_shape(rows, mp)
    if expect is not None and shape != expect:
        fail("E_MIXED_FILES")
    res, n_data = parse_mapped(rows, mp, side_from, src["kind"], src["delimiter"])
    return {"fmt": "mapped", "verified": False, "res": res, "mode": None, "tz": mapped_tz_label(res["extra"]),
            "n_data": n_data, "shape": shape}


def parse_files(items, mapping=None):
    """Mirrors parseFiles() in index.js: several files (bytes) or pastes ({"paste": text})."""
    if not items:
        fail("E_EMPTY")
    side_from = check_mapping(mapping) if mapping is not None else None
    n = len(items)
    total = 0
    for it in items:
        total += len(it["paste"]) if is_paste(it) else len(it)
    if total > MAX_BYTES:
        fail("E_TOO_LARGE")
    parts = []
    n_rows = 0
    for k, item in enumerate(items):
        try:
            src = read_rows(item, (mapping.get("delimiter") or None) if mapping is not None else None)
            if mapping is not None:
                p = _read_mapped(src, mapping, side_from, None if k == 0 else parts[0]["shape"])
            else:
                p = _read_auto(src)
            if k > 0 and p["shape"] != parts[0]["shape"]:
                fail("E_MIXED_FILES")
            p["last_row"] = src["rows"][-1]["row"] if src["rows"] else 0
            p["first"] = first_ts(p["res"])
            n_rows += p["n_data"]
            parts.append(p)
        except EngineError as e:
            if n > 1:
                e.file = k + 1
            raise
    if n_rows > MAX_ROWS:
        fail("E_TOO_LARGE")
    p = parts[0]
    if n == 1:
        return finish(p["fmt"], p["verified"], p["res"], p["mode"], p["tz"])
    order = sorted(range(n), key=lambda k: (parts[k]["first"], k))
    res = merge_parsed([parts[k] for k in order])
    return finish(p["fmt"], p["verified"], res, p["mode"], mapped_tz_label(res["extra"]) if mapping is not None else p["tz"])


# ----------------------------------------------------------------- presets
# Must equal PRESETS in site/static/js/engine/presets.js (tests/test_engine_mapped.py).

PRESET_SEARCH_ROWS = 50
_BUY_SELL_PREFIX = [["prefix", "buy", "buy"], ["prefix", "sell", "sell"]]
_B_S_PREFIX = [["prefix", "b", "buy"], ["prefix", "s", "sell"]]


def _preset(**kw):
    base = {"side_default": None, "status_rules": None, "futures_sizes": False, "tz": None, "keep_partial": False,
            "section": False, "before_known": False}
    base.update(kw)
    return base


PRESETS = [
    _preset(id="ninjatrader_exec", name="NinjaTrader 8 executions",
            source="OFFICIAL NinjaTrader 8 help, Executions tab column list; 3RD TradeZella NinjaTrader header",
            match=["instrument", "action", "quantity", "price", "time", "ex"], layout="fills",
            cols={"date": "time", "symbol": "instrument", "side": "action", "qty": "quantity", "price": "price",
                  "fees": ["commission"]},
            side_rules=_BUY_SELL_PREFIX, futures_sizes=True),
    _preset(id="trading212_history", name="Trading 212 history",
            source="3RD Export-To-Ghostfolio trading212Record field list (heading spelling inferred)",
            match=["action", "time", "ticker", "noofshares", "priceshare"], layout="fills",
            cols={"date": "time", "symbol": "ticker", "side": "action", "qty": "noofshares", "price": "priceshare",
                  "currency": "currencypriceshare"},
            side_rules=[["contains", "buy", "buy"], ["contains", "sell", "sell"]], side_default="skip"),
    _preset(id="kraken_trades", name="Kraken trades", source="OFFICIAL Kraken support, Trades export fields",
            match=["txid", "ordertxid", "pair", "time", "type", "price", "vol"], layout="fills",
            cols={"date": "time", "symbol": "pair", "side": "type", "qty": "vol", "price": "price", "fees": ["fee"]},
            side_rules=[["eq", "buy", "buy"], ["eq", "sell", "sell"]], tz="utc"),
    _preset(id="sierra_fills", name="Sierra Chart trade activity (fills)",
            source="OFFICIAL Sierra Chart Trade Activity Log documentation (spaced or run-together headings: UNVERIFIED)",
            match=["activitytype", "datetime", "symbol", "buysell", "fillprice", "filledquantity"], layout="fills",
            cols={"date": "datetime", "symbol": "symbol", "side": "buysell", "qty": "filledquantity",
                  "price": "fillprice", "status": "activitytype"},
            side_rules=_B_S_PREFIX, status_rules=[["prefix", "fill", "keep"]], before_known=True),
    _preset(id="rithmic_orders", name="Rithmic R|Trader Pro completed orders",
            source="3RD TradeZella R|Trader column list; 3RD Tradervue (Qty Filled)",
            match=["buysell", "symbol", "qtyfilled", "avgfillprice", "status", "updatetime"], layout="orders",
            cols={"date": "updatetime", "symbol": "symbol", "side": "buysell", "qty": "qtyfilled",
                  "price": "avgfillprice", "status": "status", "fees": ["commission"]},
            side_rules=_B_S_PREFIX,
            status_rules=[["eq", "filled", "keep"], ["eq", "complete", "keep"], ["eq", "completed", "keep"],
                          ["eq", "partially filled", "keep"]],
            futures_sizes=True, keep_partial=True),
    _preset(id="ctrader_history", name="cTrader history",
            source="OFFICIAL cTrader Web History column list (on screen, not a file heading)",
            match=["symbol", "openingdirection", "openingtime", "closingtime", "entryprice", "closingprice",
                   "closingquantity"], layout="roundtrips",
            cols={"open_time": "openingtime", "close_time": "closingtime", "symbol": "symbol",
                  "direction": "openingdirection", "qty": "closingquantity", "open_price": "entryprice",
                  "close_price": "closingprice", "fees": ["commissions", "swap"], "pnl": "gross"},
            side_rules=_B_S_PREFIX),
    _preset(id="dxtrade_orders", name="DXtrade order history (pasted)", source="3RD TradesViz DXtrade columns to show",
            match=["dateandtime", "symbol", "status", "side", "filledvolume", "fillprice"], layout="orders",
            cols={"date": "dateandtime", "symbol": "symbol", "side": "side", "qty": "filledvolume",
                  "price": "fillprice", "status": "status", "fees": ["commission"]},
            side_rules=_BUY_SELL_PREFIX, status_rules=[["eq", "filled", "keep"], ["eq", "partially filled", "keep"]],
            keep_partial=True),
    _preset(id="hyperliquid_fills", name="Hyperliquid fills",
            source="OFFICIAL Hyperliquid API userFills fields (the web CSV heading was not found)",
            match=["coin", "side", "px", "sz", "time"], layout="fills",
            cols={"date": "time", "symbol": "coin", "side": "side", "qty": "sz", "price": "px", "fees": ["fee"]},
            side_rules=[["eq", "b", "buy"], ["eq", "a", "sell"], ["eq", "buy", "buy"], ["eq", "sell", "sell"]]),
]


def preset_by_id(pid):
    return next((p for p in PRESETS if p["id"] == pid), None)


def find_preset_header(rows, preset, kind):
    whole = preset["section"] or kind == "html"
    seen = 0
    for i, r in enumerate(rows):
        if _empty(r["cells"]):
            continue
        seen += 1
        if not whole and seen > PRESET_SEARCH_ROWS:
            break
        norm = [norm_header(c) for c in r["cells"]]
        if all(h in norm for h in preset["match"]):
            return i
    return -1


def preset_mapping(preset, src):
    rows = src["rows"]
    at = find_preset_header(rows, preset, src["kind"])
    if at < 0:
        return None
    source = None
    if src["kind"] == "html":
        hdr = rows[at]
        rows = [r for r in rows if r["table"] == hdr["table"]]
        at = next(k for k, r in enumerate(rows) if r is hdr)
        source = {"kind": "html", "table": hdr["table"]}
    norm = [norm_header(c) for c in rows[at]["cells"]]
    cols = {f: None for f in MAP_FIELDS}
    headers = {}
    for f, want in preset["cols"].items():
        if f == "fees":
            idx = []
            for h in want:
                if h in norm and not is_blocked(h):
                    i = norm.index(h)
                    idx.append(i)
                    headers[str(i)] = h
            cols["fees"] = idx or None
            continue
        if want not in norm or is_blocked(want):
            continue
        i = norm.index(want)
        cols[f] = i
        headers[str(i)] = want
    trim = src["kind"] == "paste"
    width = len(rows[at]["cells"])
    data = [r for r in data_rows_after(rows, at, preset["section"])
            if not _empty(r["cells"]) and not (trim and len(r["cells"]) * 2 < width) and not is_no_data(r["cells"], width)]
    date_cols = [cols["open_time"], cols["close_time"]] if preset["layout"] == "roundtrips" else [cols["date"]]
    values = []
    for r in data:
        for i in date_cols:
            values.append(r["cells"][i] if i < len(r["cells"]) else "")
    det = detect_date_format(values)
    questions = []
    if det["format"] is None:
        questions.append({"q": "date_order", "reason": det["reason"]})
    num_fields = ["qty", "open_price", "close_price", "pnl"] if preset["layout"] == "roundtrips" else ["qty", "price"]
    num_idx = [cols[f] for f in num_fields if cols[f] is not None]
    if cols["fees"]:
        num_idx += cols["fees"]
    delim = src["delimiter"] if src["kind"] == "csv" else ("," if src["kind"] == "html" else "\t")
    nq = number_question(data, num_idx, delim)
    if nq:
        questions.append({"q": nq, "reason": "ask"})
    mapping = {
        "v": 1, "layout": preset["layout"], "header_row": rows[at]["row"] - 1,
        "delimiter": src["delimiter"] if src["kind"] == "csv" else None, "cols": cols, "headers": headers,
        "side_from": "column", "side_values": None, "side_rules": preset["side_rules"],
        "side_default": preset["side_default"], "status_values": None, "status_rules": preset["status_rules"],
        "date_format": det["format"], "number_style": None, "futures_sizes": preset["futures_sizes"], "currency": None,
        "preset": preset["id"], "section": preset["section"], "trim_ragged": trim, "source": source,
        "tz": preset["tz"], "keep_partial": preset["keep_partial"],
    }
    return {"preset": preset["id"], "mapping": mapping, "questions": questions}


def match_preset(src, only=None):
    for p in PRESETS:
        if only is not None and not only(p):
            continue
        m = preset_mapping(p, src)
        if m:
            return m
    return None


PRESET_AFTER = ["E_UNKNOWN_FORMAT", "E_MISSING_COLUMN", "E_AMBIGUOUS_DATE"]


def run_files(items, mapping=None):
    try:
        return {"result": parse_files(items, mapping)}
    except EngineError as e:
        return {"error": e.to_json()}


def read_with_presets(items):
    """Mirrors readWithPresets(): before_known presets, then known formats, then the other presets."""
    try:
        src = read_rows(items[0])
    except EngineError:
        src = None

    def use(p):
        if p["questions"]:
            return {"question": {"preset": p["preset"], "questions": p["questions"]}}
        return run_files(items, p["mapping"])

    if src is not None:
        p = match_preset(src, lambda x: x["before_known"])
        if p:
            return use(p)
    auto = run_files(items)
    if "error" not in auto or auto["error"]["code"] not in PRESET_AFTER or src is None:
        return auto
    p = match_preset(src)
    return use(p) if p else auto


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

# Skew guard (ARCHITECT-STATS-AMENDMENT-2026-10-21 section 4, D-8). Mirrors noise.js.
SKEW_MIN = 1
SKEW_C = 10


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


def _bootstrap_count(x, seed, n_boot, stop_at):
    """The shipped bootstrap-t count; stops once it reaches stop_at. Mirrors bootstrapCount()."""
    n = len(x)
    s = 0.0
    for v in x:
        s += v
    obs = s / n
    t_obs = _student_gap(x, n, 0.0)
    rand = mulberry32(seed)
    draw = [0.0] * n
    count = 0
    for _ in range(n_boot):
        for i in range(n):
            draw[i] = x[int(rand() * n)]
        if _student_gap(draw, n, obs) >= t_obs:
            count += 1
            if count >= stop_at:
                break
    return count


def skewness(pnls, m):
    """Sample skewness g1 (population-moment form), sums in input order. Mirrors skewness()."""
    n = len(pnls)
    m2 = 0.0
    m3 = 0.0
    for x in pnls:
        d = x - m
        m2 += d * d
        m3 += d * d * d
    m2 = m2 / n
    m3 = m3 / n
    return m3 / (m2 * math.sqrt(m2)) if m2 > 0 else 0.0


def check_expectancy(pnls, seed, n_boot=None):
    """Expectancy != 0 by bootstrap-t (Tester D3), then the skew guard (amendment section 4).

    Resample with replacement N times; count resamples whose t around the file's mean is at
    least the file's t around zero. n_boot is N_PERM in the product (calibration only: smaller)."""
    n_boot = N_PERM if n_boot is None else n_boot
    n = len(pnls)
    out = {"stat": "expectancy", "method": EXPECTANCY_METHOD, "n_a": n, "n_b": None, "value": None, "p": None,
           "label": None, "skew": None, "guard": None, "n_needed": None, "extreme": None, "p_unguarded": None}
    if n < MIN_GROUP:
        out["label"] = label_for(None, True)
        return out
    s = 0.0
    for v in pnls:
        s += v
    m = s / n
    p = (1 + _bootstrap_count(pnls, seed, n_boot, math.inf)) / (n_boot + 1)
    g1 = skewness(pnls, m)
    out["value"] = m
    out["skew"] = g1
    against = (m > 0 and g1 <= -SKEW_MIN) or (m < 0 and g1 >= SKEW_MIN)
    if against and n < SKEW_C * g1 * g1:
        out.update(label=label_for(None, True), guard="skew_small_n", n_needed=math.floor(SKEW_C * g1 * g1) + 1,
                   p_unguarded=p)
        return out
    if against and p < 0.05:
        ext = pnls[0]
        for i in range(1, n):
            if (pnls[i] > ext) if m < 0 else (pnls[i] < ext):
                ext = pnls[i]
        stop = math.ceil(0.05 * (n_boot + 1)) - 1
        if not ((1 + stop) / (n_boot + 1) >= 0.05 and stop / (n_boot + 1) < 0.05):
            raise ValueError(f"skew guard: stop {stop} does not mark p >= 0.05 for N = {n_boot}")
        if _bootstrap_count(list(pnls) + [ext], seed, n_boot, stop) >= stop:
            out.update(label=label_for(None, True), guard="skew_one_more", extreme=ext, p_unguarded=p)
            return out
    out.update(p=p, label=label_for(p, False))
    return out


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
    order = chrono_order(executions)
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


SPAN_KEEP_MS = (520 - 1) * 7 * 86400000   # strip.js SPAN_WEEKS - 1 (delivery plan C-10)
MAX_HOLD_S = 86400 * 3650


def strip_rows(trades, salt, perm=None):
    max_open = max((t["open_ts"] for t in trades), default=0)
    in_span = [t for t in trades if t["open_ts"] >= max_open - SPAN_KEEP_MS and t["hold_s"] <= MAX_HOLD_S]
    used = in_span[-20000:] if len(in_span) > 20000 else in_span
    anchor = week_anchor(min(t["open_ts"] for t in used))
    symbols = sorted({t["symbol"] for t in used})
    p = perm(len(symbols)) if perm else list(range(len(symbols)))
    index = {s: p[i] for i, s in enumerate(symbols)}
    med = {s: median([t["qty"] for t in used if t["symbol"] == s]) for s in symbols}
    rows = [{"o": (t["open_ts"] - anchor) // 60000, "h": t["hold_s"], "d": 1 if t["dir"] == "long" else -1,
             "q": round3(t["qty"] / med[t["symbol"]]), "p": round2(t["pnl"]), "s": index[t["symbol"]],
             "f": fingerprint(salt, t)} for t in used]
    return {"rows": rows, "limited": len(in_span) > 20000, "anchor": anchor, "span_left_out": len(trades) - len(in_span)}


# ----------------------------------------------------------------- CLI / expected files

FIXTURE_DIRS = ["generic", "generic_roundtrip", "mt5", "mt4", "ibkr", "tradovate", "tradingview", "errors"]


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


# The universal importer's fixtures (tests/fixtures/make_mapped.py): each case is one or more files
# or pastes, with a mapping (mapped/, paste/ with a .map.json, multi/ with a map.json), through the
# presets (presets/, paste/ without one), or known formats only (auto/, multi/ without one).
CASE_DIRS = ["mapped", "presets", "paste", "multi", "auto"]


def case_paths(root):
    out = []
    for d in CASE_DIRS:
        p = os.path.join(root, d)
        for name in sorted(os.listdir(p)):
            if name.endswith(".map.json"):
                continue
            out.append(d + "/" + name)
    return out


def case_spec(root, rel):
    """-> {"items": [bytes | {"paste": text}], "mapping": dict | None, "presets": bool}"""
    d, name = rel.split("/", 1)

    def item(path):
        if path.endswith(".paste.txt") or d == "paste":
            with open(path, encoding="utf-8") as f:
                return {"paste": f.read()}
        with open(path, "rb") as f:
            return f.read()

    def load_map(path):
        if not os.path.exists(path):
            return None
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    if d == "multi":
        base = os.path.join(root, rel)
        names = sorted(n for n in os.listdir(base) if n != "map.json")
        return {"items": [item(os.path.join(base, n)) for n in names],
                "mapping": load_map(os.path.join(base, "map.json")), "presets": False}
    path = os.path.join(root, rel)
    mapping = load_map(os.path.join(root, d, os.path.splitext(name)[0] + ".map.json"))
    return {"items": [item(path)], "mapping": mapping,
            "presets": d == "presets" or (d == "paste" and mapping is None)}


def run_case(root, rel):
    spec = case_spec(root, rel)
    out = read_with_presets(spec["items"]) if spec["presets"] else run_files(spec["items"], spec["mapping"])
    if "result" in out:
        trades = out["result"]["trades"]
        out.update({"stats": free_stats(trades), "noise": noise_checks(trades),
                    "pgr_plr": pgr_plr_counts(out["result"]["executions"])})
    return out


def _dump(path, res):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(res, f, indent=1, sort_keys=True)
        f.write("\n")


def write_expected(root):
    exp = os.path.join(root, "expected")
    os.makedirs(exp, exist_ok=True)
    for rel in fixture_paths(root):
        with open(os.path.join(root, rel), "rb") as f:
            res = run_fixture(f.read())
        _dump(os.path.join(exp, rel.replace("/", "__") + ".json"), res)
    for rel in case_paths(root):
        _dump(os.path.join(exp, rel.replace("/", "__") + ".json"), run_case(root, rel))
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
