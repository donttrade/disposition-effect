#!/usr/bin/env python3
"""Prediction study test (DT-1): do a trader's first 30 trades rank the accounts that go on to break a
daily-loss or max-loss rule in the next 30 days above the accounts that do not?

Run this inside your own systems, on your own exported files.

  * Standard library only. It imports its three sibling modules from its own folder (dt1_features.py,
    dt1_outcomes.py, prediction_metrics.py) and nothing else that is not in the standard library.
  * Opens exactly three files, all read-only: trades.csv, accounts.csv and the sealed pre-registration.
  * Writes no files. All output goes to stdout (errors go to stderr).
  * Never prints an account_id, a trader_key, a symbol, a time, an amount or any other cell of your files.
    It prints counts, AUCs, intervals, p-values, signs and banded tables in which every cell describes at
    least 5 accounts. There is no per-account line of any kind.
  * Errors give a row NUMBER and a fixed sentence written by this program. The only schema words that can
    appear in a message are this program's own column names and sealed keys.
  * Every choice is read from the sealed block of the pre-registration. The random seed for the
    cross-validation folds is the first 16 hex digits of the sealed block's SHA-256 (its fingerprint):
    nobody chooses it, and the same block with the same files always prints the same bytes.

Usage (plain Terminal, on the firm's machine):
  python3 -I prediction_test.py trades.csv accounts.csv PREREG-PREDICTION.md
  python3 -I prediction_test.py --json trades.csv accounts.csv PREREG-PREDICTION.md   (the same numbers as JSON)

Check that it cannot reach a network (plain Terminal, Linux):
  unshare -rn python3 -I prediction_test.py trades.csv accounts.csv PREREG-PREDICTION.md

Version 1.0 (30 Oct 2026).
"""

# ==========================================================================
# SECTION 1 of 6: AUDIT MAP -- read this, then spot-check the lines it names.
# The question it answers: can this program send your data anywhere, or print it?
#
#   Imports, complete list ...... lines 59-69 (standard library) and 76-78 (the three sibling
#                                 modules from this folder, added to the search path on line 74).
#                                 No network module, no os, no subprocess, no importlib. The sibling
#                                 modules import only bisect, decimal and math.
#   The files opened ............ line 336 (the pre-registration) and line 418 (each CSV; it runs
#                                 twice, once per CSV), all mode "r" (read-only). Nothing is written.
#   Everything sent to stdout ... lines 882 and 883 (the results, then flush); line 895 only assigns
#                                 None to stdout after a broken pipe. print() is never used.
#   Everything sent to stderr ... lines 892, 898 and 901, all inside main().
#   Error messages .............. built only at the ValidationError(...) sites (grep -n
#                                 'ValidationError(' lists them) and printed only by main(), line 892.
#                                 Each is a fixed sentence into which only a row or line number, a
#                                 count, our own column names, our own sealed keys or the OS's reason
#                                 text is substituted.
#   The catch-all ............... line 900, "except Exception". It prints the exception's CLASS NAME
#                                 only, never its text.
#   Output text ................. built only in render() and render_json() from counts and statistics.
#                                 Tables go through prediction_metrics.bands(), which merges adjacent
#                                 bands until every cell has at least 5 breaches and 5 survivors;
#                                 confusion counts under 5 print as "<5".
# ==========================================================================

# ==========================================================================
# SECTION 2 of 6: IMPORTS AND CONSTANTS
# ==========================================================================
import argparse
import csv
import datetime
import decimal
import hashlib
import math
import random
import re
import sys
import unicodedata
from decimal import Decimal

# The three sibling modules sit next to this file. `python3 -I` does not put the script's folder on the
# search path, so this line adds THIS folder only (taken from this file's own path), before the imports.
_HERE = __file__.replace("\\", "/").rpartition("/")[0] or "."
sys.path.insert(0, _HERE)

import dt1_features as F           # noqa: E402  (the DT-1 features: copied from the engine)
import dt1_outcomes as O           # noqa: E402  (the outcome labels and B4)
import prediction_metrics as M     # noqa: E402  (the statistics)

SCRIPT_VERSION = "1.0 (30 Oct 2026)"
SCRIPT_NAME = "prediction_test.py"

TRADE_COLUMNS = ("account_id", "open_time", "close_time", "symbol", "direction", "size", "pnl")
ACCOUNT_COLUMNS = ("account_id", "start_time", "start_balance", "daily_loss", "max_loss", "drawdown",
                   "trail_stop_at", "outcome", "outcome_time", "data_end_time")
ACCOUNT_OPTIONAL = ("trader_key", "abuse_flag", "bot_flag")

DEC_PATTERN = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)")
TIME_PATTERN = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})[T ]([0-9]{2}):([0-9]{2})(?::([0-9]{2})(\.[0-9]{1,9})?)?"
                          r"(Z|[+-][0-9]{2}:[0-9]{2})?")
DATE_PATTERN = re.compile(r"([0-9]{4})-([0-9]{2})-([0-9]{2})")
HHMM_PATTERN = re.compile(r"([0-9]{2}):([0-9]{2})")
OFFSET_PATTERN = re.compile(r"([+-])([0-9]{2}):([0-9]{2})")
INT_PATTERN = re.compile(r"[0-9]+")

BEGIN_MARK = "--- BEGIN SEALED PARAMETERS ---"
END_MARK = "--- END SEALED PARAMETERS ---"
BLOCK_HEADER = "[prediction-study]"

# Sealed keys: name -> (kind, rule). The study constants are frozen: each accepts its registered value only.
SEALED_KEYS = (
    ("registration", "label", None),
    ("dt_version", "choice", ("DT-1",)),
    ("engine_method", "choice", ("2026-10-23.stats2f",)),
    ("window_trades", "choice", ("30",)),
    ("outcome_days", "choice", ("30",)),
    ("min_features", "choice", ("3",)),
    ("pass_lower", "choice", ("0.55",)),
    ("fail_point", "choice", ("0.55",)),
    ("fail_upper", "choice", ("0.60",)),
    ("target", "choice", ("0.65",)),
    ("h2_alpha", "choice", ("0.05",)),
    ("min_each", "choice", ("100",)),
    ("cv_folds", "choice", ("10",)),
    ("outcome_mode", "choice", ("firm", "rule")),
    ("pnl_basis", "choice", ("net", "gross")),
    ("firm_label", "label", None),
    ("period_start", "date", None),
    ("period_end", "date", None),
    ("data_cut", "date", None),
    ("accounts_in_period", "int", None),
    ("day_start", "hhmm", None),
    ("day_utc_offset", "offset", None),
)
SEALED_NAMES = tuple(k for k, _kind, _rule in SEALED_KEYS)
ROBUST_WINDOW = 15
FLAG_SHARES = (0.10, 0.20, 0.30)
N_BANDS = 10


class ValidationError(Exception):
    """A problem with the input or the arguments. The message is safe to print: it is written by this
    program and never contains cell contents."""


class NulFound(Exception):
    """Internal signal: a line of a file contains a NUL character."""


class BadBytes(Exception):
    """Internal signal: a line of a file is not valid UTF-8."""


BAD_BYTE_PATTERN = re.compile("[\udc80-\udcff]")


# ==========================================================================
# SECTION 3 of 6: VALIDATION -- pure checks of one value at a time; no state, no output
# ==========================================================================

def has_invisible_char(text):
    """Format (Cf) or control (Cc) characters, or non-ASCII whitespace: invisible in a spreadsheet, but they
    make two identical-looking identifiers different, so they are refused."""
    for ch in text:
        if unicodedata.category(ch) in ("Cf", "Cc"):
            return True
        if ord(ch) > 127 and ch.isspace():
            return True
    return False


def check_header(header, required, optional, what):
    seen = set()
    for name in header:
        if name in seen:
            raise ValidationError("%s: a column name is repeated in the header (row 1)" % what)
        seen.add(name)
        if name not in required and name not in optional:
            raise ValidationError("%s: the header (row 1) has a column this program does not know (not shown); "
                                  "the allowed columns are: %s" % (what, ", ".join(required + optional)))
    missing = [c for c in required if c not in seen]
    if missing:
        raise ValidationError("%s: the header (row 1) is missing column(s): %s" % (what, ", ".join(missing)))
    return {name: i for i, name in enumerate(header)}


def parse_ident(text, col, row_no, what):
    if text == "":
        raise ValidationError("%s row %d: %s is empty" % (what, row_no, col))
    if has_invisible_char(text) or text != text.strip():
        raise ValidationError("%s row %d: %s has an invisible character or leading/trailing spaces"
                              % (what, row_no, col))
    return text


def parse_dec(text, col, row_no, what, minimum=None, blank_ok=False):
    if text == "" and blank_ok:
        return None
    if DEC_PATTERN.fullmatch(text) is None:
        raise ValidationError("%s row %d: %s is not a plain decimal number" % (what, row_no, col))
    v = Decimal(text)
    if minimum == "positive" and not v > 0:
        raise ValidationError("%s row %d: %s must be above 0" % (what, row_no, col))
    if minimum == "nonneg" and v < 0:
        raise ValidationError("%s row %d: %s must be 0 or more" % (what, row_no, col))
    if abs(v) > Decimal(10) ** 15:
        raise ValidationError("%s row %d: %s is too large (above 10^15)" % (what, row_no, col))
    return v


def parse_time(text, col, row_no, what, offset_s, blank_ok=False):
    """ISO-8601 with an offset or Z; no offset means UTC. Returns whole seconds on the study clock
    (UTC + the sealed day offset)."""
    if text == "" and blank_ok:
        return None
    m = TIME_PATTERN.fullmatch(text)
    if m is None:
        raise ValidationError("%s row %d: %s is not a date and time (YYYY-MM-DDTHH:MM[:SS][+HH:MM or Z])"
                              % (what, row_no, col))
    y, mo, d, hh, mi = (int(m.group(k)) for k in range(1, 6))
    ss = int(m.group(6) or 0)
    try:
        base = datetime.datetime(y, mo, d, hh, mi, ss, tzinfo=datetime.timezone.utc)
    except ValueError:
        raise ValidationError("%s row %d: %s is not a real date and time" % (what, row_no, col)) from None
    z = m.group(8)
    off = 0
    if z and z != "Z":
        oh, om = int(z[1:3]), int(z[4:6])
        if oh > 23 or om > 59:
            raise ValidationError("%s row %d: %s has an impossible UTC offset" % (what, row_no, col))
        off = (oh * 3600 + om * 60) * (1 if z[0] == "+" else -1)
    epoch = datetime.datetime(1970, 1, 1, tzinfo=datetime.timezone.utc)
    utc_s = int((base - epoch).total_seconds()) - off
    return utc_s + offset_s


def check_sealed_value(key, kind, rule, text, line_no):
    """Validate one sealed value; returns it converted. Messages name the KEY and never echo the value."""
    if len(text) >= 2 and text[0] == '"' and text[-1] == '"':
        text = text[1:-1]
    if "FILL_IN" in text:
        raise ValidationError("pre-registration line %d: sealed key %s is still FILL_IN; the template must be "
                              "completed and sealed before a run" % (line_no, key))
    if kind == "choice":
        if text not in rule:
            raise ValidationError("pre-registration line %d: sealed key %s must be %s (the registered value)"
                                  % (line_no, key, " or ".join(rule)))
        return text
    if kind == "label":
        if text == "" or has_invisible_char(text):
            raise ValidationError("pre-registration line %d: sealed key %s must be a non-empty label with no "
                                  "invisible characters" % (line_no, key))
        return text
    if kind == "int":
        if INT_PATTERN.fullmatch(text) is None or len(text) > 9 or int(text) < 1:
            raise ValidationError("pre-registration line %d: sealed key %s must be a whole number of at least 1"
                                  % (line_no, key))
        return int(text)
    if kind == "date":
        m = DATE_PATTERN.fullmatch(text)
        try:
            if m is None:
                raise ValueError
            return datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            raise ValidationError("pre-registration line %d: sealed key %s must be a date YYYY-MM-DD"
                                  % (line_no, key)) from None
    if kind == "hhmm":
        m = HHMM_PATTERN.fullmatch(text)
        if m is None or int(m.group(1)) > 23 or int(m.group(2)) > 59:
            raise ValidationError("pre-registration line %d: sealed key %s must be a time HH:MM" % (line_no, key))
        return int(m.group(1)) * 3600 + int(m.group(2)) * 60
    m = OFFSET_PATTERN.fullmatch(text)   # "offset"
    if m is None or int(m.group(2)) > 14 or int(m.group(3)) > 59:
        raise ValidationError("pre-registration line %d: sealed key %s must be a UTC offset +HH:MM or -HH:MM"
                              % (line_no, key))
    return (int(m.group(2)) * 3600 + int(m.group(3)) * 60) * (1 if m.group(1) == "+" else -1)


def parse_sealed_block(lines):
    """Returns (params, fingerprint). Only the block between BEGIN_MARK and END_MARK is read. Its first
    non-blank line is [prediction-study]; then one 'key = value' per line; '#' starts a comment. The
    fingerprint is the SHA-256 of the block's lines (markers included) joined by newlines."""
    begins = [i for i, ln in enumerate(lines) if ln.strip() == BEGIN_MARK]
    ends = [i for i, ln in enumerate(lines) if ln.strip() == END_MARK]
    if not begins or not ends:
        raise ValidationError("the pre-registration has no sealed parameter block (the lines " + BEGIN_MARK +
                              " and " + END_MARK + ")")
    if len(begins) > 1 or len(ends) > 1:
        raise ValidationError("the pre-registration has more than one sealed parameter block")
    first, last = begins[0], ends[0]
    if last < first:
        raise ValidationError("the pre-registration's sealed block ends before it begins")
    kinds = {k: (kind, rule) for k, kind, rule in SEALED_KEYS}
    params = {}
    header_seen = False
    for i in range(first + 1, last):
        text = lines[i].split("#", 1)[0].strip()
        if text == "":
            continue
        if not header_seen:
            if text != BLOCK_HEADER:
                raise ValidationError("pre-registration line %d: the sealed block must start with %s"
                                      % (i + 1, BLOCK_HEADER))
            header_seen = True
            continue
        key, eq, value = text.partition("=")
        key, value = key.strip(), value.strip()
        if eq != "=" or key == "":
            raise ValidationError("pre-registration line %d: not of the form key = value" % (i + 1))
        if key not in kinds:
            raise ValidationError("pre-registration line %d: unknown key in the sealed block (not shown); "
                                  "allowed keys: %s" % (i + 1, ", ".join(SEALED_NAMES)))
        if key in params:
            raise ValidationError("pre-registration line %d: sealed key %s is repeated" % (i + 1, key))
        kind, rule = kinds[key]
        params[key] = check_sealed_value(key, kind, rule, value, i + 1)
    missing = [k for k in SEALED_NAMES if k not in params]
    if missing:
        raise ValidationError("the sealed block is missing key(s): " + ", ".join(missing))
    if not (params["period_start"] <= params["period_end"] <= params["data_cut"]):
        raise ValidationError("sealed keys period_start, period_end and data_cut must be in that order")
    block = "\n".join(ln.rstrip() for ln in lines[first:last + 1]) + "\n"
    return params, hashlib.sha256(block.encode("utf-8")).hexdigest()


# ---- end of input validation helpers ----

# ==========================================================================
# SECTION 4 of 6: IO -- reading the three files
# ==========================================================================

def lines_without_nul(handle):
    for text in handle:
        if "\0" in text:
            raise NulFound()
        if BAD_BYTE_PATTERN.search(text) is not None:
            raise BadBytes()
        yield text


def read_prereg(path):
    """Returns (params, fingerprint)."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="surrogateescape", newline="") as handle:
            text = handle.read()
    except OSError as exc:
        reason = exc.strerror if exc.strerror else "unknown reason"
        raise ValidationError("cannot open the pre-registration file (%s)" % reason) from None
    if "\0" in text:
        raise ValidationError("the pre-registration contains a NUL (zero) byte, so it is not plain text")
    if BAD_BYTE_PATTERN.search(text) is not None:
        raise ValidationError("the pre-registration is not valid UTF-8 text")
    return parse_sealed_block(text.splitlines())


def _day_bounds(params):
    """Study-clock seconds: the first second of period_start, the last of period_end and of data_cut."""
    epoch = datetime.date(1970, 1, 1)
    start = (params["period_start"] - epoch).days * 86400
    end = (params["period_end"] - epoch).days * 86400 + 86399
    cut = (params["data_cut"] - epoch).days * 86400 + 86399
    return start, end, cut


def parse_trade_row(fields, col, row_no, params):
    what = "trades.csv"
    off = params["day_utc_offset"]
    acc = parse_ident(fields[col["account_id"]], "account_id", row_no, what)
    op = parse_time(fields[col["open_time"]], "open_time", row_no, what, off)
    cl = parse_time(fields[col["close_time"]], "close_time", row_no, what, off)
    if cl < op:
        raise ValidationError("%s row %d: close_time is before open_time" % (what, row_no))
    sym = parse_ident(fields[col["symbol"]], "symbol", row_no, what)
    dtext = fields[col["direction"]]
    if dtext not in ("long", "short"):
        raise ValidationError("%s row %d: direction must be long or short" % (what, row_no))
    size = parse_dec(fields[col["size"]], "size", row_no, what, minimum="nonneg")
    pnl = parse_dec(fields[col["pnl"]], "pnl", row_no, what)
    return acc, {"open_s": op, "close_s": cl, "symbol": sym, "direction": 1 if dtext == "long" else -1,
                 "size": size, "pnl": pnl, "row": row_no}


def parse_account_row(fields, col, row_no, params):
    what = "accounts.csv"
    off = params["day_utc_offset"]
    acc = parse_ident(fields[col["account_id"]], "account_id", row_no, what)
    start = parse_time(fields[col["start_time"]], "start_time", row_no, what, off)
    bal = parse_dec(fields[col["start_balance"]], "start_balance", row_no, what, minimum="positive")
    daily = parse_dec(fields[col["daily_loss"]], "daily_loss", row_no, what, minimum="positive", blank_ok=True)
    mx = parse_dec(fields[col["max_loss"]], "max_loss", row_no, what, minimum="positive")
    dd = fields[col["drawdown"]]
    if dd not in O.DRAWDOWNS:
        raise ValidationError("%s row %d: drawdown must be static, trailing_eod or trailing_trade" % (what, row_no))
    stop = parse_dec(fields[col["trail_stop_at"]], "trail_stop_at", row_no, what, minimum="nonneg", blank_ok=True)
    out = fields[col["outcome"]]
    if out not in O.OUTCOMES:
        raise ValidationError("%s row %d: outcome must be one of: %s" % (what, row_no, ", ".join(O.OUTCOMES)))
    ot = parse_time(fields[col["outcome_time"]], "outcome_time", row_no, what, off, blank_ok=True)
    if (out == "active") != (ot is None):
        raise ValidationError("%s row %d: outcome_time must be blank exactly when outcome is active"
                              % (what, row_no))
    end = parse_time(fields[col["data_end_time"]], "data_end_time", row_no, what, off)
    if ot is not None and ot < start:
        raise ValidationError("%s row %d: outcome_time is before start_time" % (what, row_no))
    if end < start:
        raise ValidationError("%s row %d: data_end_time is before start_time" % (what, row_no))
    key = None
    if "trader_key" in col and fields[col["trader_key"]] != "":
        key = parse_ident(fields[col["trader_key"]], "trader_key", row_no, what)
    flags = {}
    for name in ("abuse_flag", "bot_flag"):
        v = fields[col[name]] if name in col else ""
        if v not in ("", "0", "1"):
            raise ValidationError("%s row %d: %s must be 0, 1 or blank" % (what, row_no, name))
        flags[name] = v == "1"
    return acc, {"start": start, "balance": bal, "daily": daily, "max_loss": mx, "drawdown": dd, "stop": stop,
                 "outcome": out, "outcome_time": ot, "data_end": end, "trader_key": key,
                 "abuse": flags["abuse_flag"], "bot": flags["bot_flag"], "row": row_no}


def read_csv(path, what, required, optional, parse, params):
    """Yields (row number, parsed) for each data row; refuses NUL bytes, bad UTF-8 and short rows."""
    out = []
    row_no = 1
    try:
        with open(path, "r", encoding="utf-8-sig", errors="surrogateescape", newline="") as handle:
            reader = csv.reader(lines_without_nul(handle))
            try:
                header = next(reader)
            except StopIteration:
                raise ValidationError("%s is empty" % what) from None
            col = check_header(header, required, optional, what)
            for fields in reader:
                row_no += 1
                if not fields:
                    continue
                if len(fields) != len(header):
                    raise ValidationError("%s row %d: %d fields, the header has %d" % (what, row_no, len(fields),
                                                                                    len(header)))
                out.append(parse(fields, col, row_no, params))
    except NulFound:
        raise ValidationError("%s row %d: contains a NUL (zero) byte" % (what, row_no + 1)) from None
    except BadBytes:
        raise ValidationError("%s row %d: is not valid UTF-8 text" % (what, row_no + 1)) from None
    except csv.Error:
        raise ValidationError("%s row %d: is not well-formed CSV (quotes)" % (what, row_no + 1)) from None
    except OSError as exc:
        reason = exc.strerror if exc.strerror else "unknown reason"
        raise ValidationError("cannot open %s (%s)" % (what, reason)) from None
    return out


def read_inputs(trades_path, accounts_path, params):
    accounts = {}
    order = []
    start_s, end_s, cut_s = _day_bounds(params)
    for acc, a in read_csv(accounts_path, "accounts.csv", ACCOUNT_COLUMNS, ACCOUNT_OPTIONAL, parse_account_row,
                           params):
        if acc in accounts:
            raise ValidationError("accounts.csv row %d: the account_id is repeated (first seen on row %d)"
                                  % (a["row"], accounts[acc]["row"]))
        if not (start_s <= a["start"] <= end_s):
            raise ValidationError("accounts.csv row %d: start_time is outside the sealed period" % a["row"])
        if a["data_end"] > cut_s or (a["outcome_time"] is not None and a["outcome_time"] > cut_s):
            raise ValidationError("accounts.csv row %d: a time is after the sealed data_cut" % a["row"])
        accounts[acc] = a
        order.append(acc)
    if len(order) != params["accounts_in_period"]:
        raise ValidationError("accounts.csv has %d accounts but the sealed accounts_in_period is %d: the export "
                              "must hold every account started in the period" % (len(order),
                                                                                 params["accounts_in_period"]))
    trades = {acc: [] for acc in order}
    seen = {}
    for acc, t in read_csv(trades_path, "trades.csv", TRADE_COLUMNS, (), parse_trade_row, params):
        if acc not in trades:
            raise ValidationError("trades.csv row %d: the account_id is not in accounts.csv" % t["row"])
        a = accounts[acc]
        if t["open_s"] < a["start"]:
            raise ValidationError("trades.csv row %d: open_time is before the account's start_time" % t["row"])
        if t["close_s"] > a["data_end"]:
            raise ValidationError("trades.csv row %d: close_time is after the account's data_end_time" % t["row"])
        k = (acc, t["open_s"], t["close_s"], t["symbol"], t["direction"], t["size"], t["pnl"])
        if k in seen:
            raise ValidationError("trades.csv row %d: duplicates row %d (every column the same)" % (t["row"], seen[k]))
        seen[k] = t["row"]
        trades[acc].append(t)
    return order, accounts, trades


# ==========================================================================
# SECTION 5 of 6: THE ANALYSIS
# ==========================================================================

def _sd(xs):
    n = len(xs)
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1)) if n > 1 else 0.0


def baseline(win, a, params, rule_mode):
    """B1-B4 from W and the account record only."""
    ds = params["day_start"]
    size = float(a["balance"])
    pnls = [float(t["pnl"]) for t in win]
    days = {O.day_key(t["close_s"], ds) for t in win}
    b1 = len(win) / len(days)
    b2 = math.log(max(_sd(pnls) / size, 1e-9))
    b3 = sum(pnls) / size
    tr = [{"close_s": t["close_s"], "pnl": float(t["pnl"])} for t in win]
    if rule_mode:
        b4 = O.headroom(tr, O.R_STAR["max_share"] * size, "static", None, ds)
    else:
        b4 = O.headroom(tr, float(a["max_loss"]), a["drawdown"], None if a["stop"] is None else float(a["stop"]), ds)
    return [b1, b2, b3, b4]


def classify(order, accounts, trades, params, window, include_abuse=False, censored_as_zero=False,
             outcome="o1"):
    """Applies E1-E7 in order. Returns (reconciliation counts, eligible records)."""
    rule_mode = params["outcome_mode"] == "rule"
    days = int(params["outcome_days"])
    rec = {"read": len(order), "E1": 0, "E1_breached_before_t0": 0, "E2": 0, "E3": 0, "E4": 0, "E5": 0, "E6": 0,
           "E7": 0}
    kept = []
    for acc in order:
        a = accounts[acc]
        tl = trades[acc]
        ot = a["outcome_time"]
        if not rule_mode and ot is not None:
            tl = [t for t in tl if t["close_s"] <= ot]
        w = F.account_window(tl, window)
        if w["status"] == "short" or (not rule_mode and ot is not None and ot <= w["t0"]):
            rec["E1"] += 1
            if not rule_mode and a["outcome"] in O.BREACH:
                rec["E1_breached_before_t0"] += 1
            continue
        if w["status"] == "dates_only":
            rec["E2"] += 1
            continue
        if F.n_defined(w["features"]) < int(params["min_features"]):
            rec["E3"] += 1
            continue
        if rule_mode:
            after = [{"close_s": t["close_s"], "pnl": float(t["pnl"])} for t in w["after"]]
            lab = O.rule_label(after, w["t0"], days, float(a["balance"]), a["data_end"], params["day_start"])
        else:
            lab = O.firm_label(a, w["t0"], days)
        y = lab.get(outcome)
        if y is None:
            if outcome == "o1" and censored_as_zero:
                y = 0
            else:
                rec["E4"] += 1
                continue
        if a["abuse"] and not include_abuse:
            rec["E5"] += 1
            continue
        if a["bot"]:
            rec["E6"] += 1
            continue
        kept.append({"acc": acc, "a": a, "w": w, "y": y, "start": a["start"],
                     "b": baseline(w["window"], a, params, rule_mode)})
    best = {}
    for r in kept:
        k = r["a"]["trader_key"]
        if k is None:
            continue
        if k not in best or (r["start"], r["a"]["row"]) < (best[k]["start"], best[k]["a"]["row"]):
            best[k] = r
    out = []
    for r in kept:
        k = r["a"]["trader_key"]
        if k is not None and best[k] is not r:
            rec["E7"] += 1
            continue
        out.append(r)
    for r, s in zip(out, F.dt1_scores([r["w"]["features"] for r in out])):
        r["dt1"] = s
    rec["eligible"] = len(out)
    rec["breaches"] = sum(r["y"] for r in out)
    rec["survivors"] = rec["eligible"] - rec["breaches"]
    return rec, out


def h1_only(params, recs):
    y = [r["y"] for r in recs]
    if min(sum(y), len(y) - sum(y)) < 1:
        return None
    return M.auc_delong([r["dt1"] for r in recs], y)


def analyse_full(params, recs, seed):
    y = [r["y"] for r in recs]
    dt1 = [r["dt1"] for r in recs]
    res = {}
    res["h1"] = M.auc_delong(dt1, y)
    k = int(params["cv_folds"])
    fold = M.stratified_folds(y, k, random.Random(seed))
    X0 = [r["b"] for r in recs]
    X1 = [r["b"] + [r["dt1"]] for r in recs]
    try:
        p0 = M.cv_predict(X0, y, fold, k)
        p1 = M.cv_predict(X1, y, fold, k)
        pd = M.cv_predict([[v] for v in dt1], y, fold, k)
        lr = M.lr_test(X0, X1, y)
        res["h2"] = {"auc_b0": M.auc_delong(p0, y), "auc_full": M.auc_delong(p1, y),
                     "delta": M.delong_paired(p1, p0, y), "lr": lr,
                     "passed": lr["coef"] > 0 and lr["p"] < float(params["h2_alpha"]), "fit": "ok"}
        cal = {}
        for name, p in (("DT-1 (recalibrated)", pd), ("Full model (B0 + DT-1)", p1), ("Baseline B0", p0)):
            c = M.calibration(p, y)
            b = M.brier(p, y)
            cal[name] = {"intercept": c["intercept"], "slope": c["slope"], "brier": b["brier"],
                         "scaled": b["scaled"], "bands": M.bands(p, y, N_BANDS, pred=p)}
        res["calibration"] = cal
    except M.SeparationError:
        res["h2"] = {"passed": False, "fit": "separation"}
        res["calibration"] = None
    feats = []
    for name in F.FEATURES:
        idx = [i for i, r in enumerate(recs) if r["w"]["features"][name] is not None]
        yy = [y[i] for i in idx]
        if idx and 0 < sum(yy) < len(yy):
            a = M.auc_delong([recs[i]["w"]["features"][name] for i in idx], yy)
            feats.append({"name": name, "auc": a, "p": M.auc_p_greater(a), "undefined": len(recs) - len(idx)})
        else:
            feats.append({"name": name, "auc": None, "p": 1.0, "undefined": len(recs) - len(idx)})
    for f, adj in zip(feats, M.holm([f["p"] for f in feats])):
        f["p_holm"] = adj
    res["features"] = feats
    res["deciles"] = M.bands(dt1, y, N_BANDS)
    base = sum(y) / len(y)
    top = res["deciles"][-1]
    res["lift_top"] = (top["events"] / top["n"]) / base if base > 0 else None
    res["confusion"] = [(s, M.confusion_at(dt1, y, s)) for s in FLAG_SHARES]
    return res


def verdict(params, rec, res):
    """Section 2.12, top-down; the first match wins."""
    m = int(params["min_each"])
    if res is None or rec["breaches"] < m or rec["survivors"] < m:
        return "NOT MEASURED"
    h1 = res["h1"]
    if h1["auc"] < float(params["fail_point"]) or h1["hi"] < float(params["fail_upper"]):
        return "FAIL: does not predict usefully"
    if h1["lo"] > float(params["pass_lower"]):
        if not res["h2"]["passed"]:
            return "FAIL: adds nothing"
        if h1["auc"] >= float(params["target"]):
            return "PASS: meets target"
        return "PASS: below target"
    return "INCONCLUSIVE"


HOW_TO_READ = {
    "NOT MEASURED": "There were too few breaches or too few survivors after exclusions to reach any verdict. "
                    "Nothing is claimed either way. Data collection continues under the same registration.",
    "FAIL: does not predict usefully": "The habit score did not rank later breaches usefully: either the AUC "
                                       "is below 0.55, or the whole 95% interval is below 0.60. donttrade "
                                       "publishes this result.",
    "FAIL: adds nothing": "The habit score ranks later breaches better than chance, but it adds nothing beyond "
                          "activity, volatility, P&L so far and headroom. donttrade publishes this result.",
    "PASS: meets target": "The habit score ranks later breaches above survivors (lower 95% bound above 0.55), "
                          "adds to the baseline, and reaches the 0.65 target. This describes these accounts as "
                          "a group, never one trader.",
    "PASS: below target": "The habit score ranks later breaches above survivors and adds to the baseline, but "
                          "below the 0.65 target: it predicts, modestly. This describes these accounts as a "
                          "group, never one trader.",
    "INCONCLUSIVE": "The interval is too wide to pass or to fail. donttrade publishes this result and starts a "
                    "replication on new accounts under a new registration.",
}


def run_study(params, order, accounts, trades, seed):
    window = int(params["window_trades"])
    rec, recs = classify(order, accounts, trades, params, window)
    m = int(params["min_each"])
    res = analyse_full(params, recs, seed) if min(rec["breaches"], rec["survivors"]) >= m else None
    v = verdict(params, rec, res)
    robust = None
    o3 = None
    if res is not None:
        robust = []
        for label, kw, win in (("censored accounts counted as no breach", {"censored_as_zero": True}, window),
                               ("abuse-flagged accounts included", {"include_abuse": True}, window),
                               ("a 15-trade window", {}, ROBUST_WINDOW)):
            r2, rr = classify(order, accounts, trades, params, win, **kw)
            robust.append((label, r2, h1_only(params, rr)))
        if params["outcome_mode"] == "firm":
            r3, rr3 = classify(order, accounts, trades, params, window, outcome="o3")
            o3 = (r3, h1_only(params, rr3))
    return {"rec": rec, "res": res, "verdict": v, "robust": robust, "o3": o3}


# ==========================================================================
# SECTION 6 of 6: OUTPUT -- counts and statistics only
# ==========================================================================

def f3(x):
    return "n/a" if x is None else "%.3f" % x


def f4(x):
    return "n/a" if x is None else "%.4f" % x


def pv(p):
    return "n/a" if p is None else ("<0.0001" if p < 0.0001 else "%.4f" % p)


def cell(n):
    return "<5" if n < M.MIN_CELL else str(n)


def ci(a):
    return "%s (95%% CI %s to %s)" % (f3(a["auc"]), f3(a["lo"]), f3(a["hi"]))


def band_label(r):
    return "%d" % r["first"] if r["first"] == r["last"] else "%d-%d" % (r["first"], r["last"])


def render(params, fp, out):
    L = []
    w = L.append
    rec, res = out["rec"], out["res"]
    w("donttrade prediction study: %s %s" % (SCRIPT_NAME, SCRIPT_VERSION))
    w("Score: %s   Engine method: %s   Outcome mode: %s   P&L basis: %s" % (
        params["dt_version"], params["engine_method"], params["outcome_mode"], params["pnl_basis"]))
    w("Registration: %s" % params["registration"])
    w("Sealed block fingerprint (SHA-256): %s" % fp)
    w("Fold seed: the fingerprint's first 16 hex digits")
    w("")
    w("RECONCILIATION")
    wt, od = params["window_trades"], params["outcome_days"]
    for label, value in (("Accounts read", rec["read"]),
                         ("E1 fewer than %s trades before any breach" % wt, rec["E1"]),
                         ("   of which breached at or before trade %s" % wt, rec["E1_breached_before_t0"]),
                         ("E2 first %s trades are dates only" % wt, rec["E2"]),
                         ("E3 fewer than %s of the 6 features defined" % params["min_features"], rec["E3"]),
                         ("E4 censored (not observed for %s days)" % od, rec["E4"]),
                         ("E5 flagged by the firm for abuse", rec["E5"]),
                         ("E6 failed the human-pattern screen", rec["E6"]),
                         ("E7 a later account of the same trader", rec["E7"]),
                         ("Eligible", rec["eligible"]),
                         ("Breaches (daily or max loss within %s days)" % od, rec["breaches"]),
                         ("Survivors", rec["survivors"])):
        w("  " + (label + " ").ljust(47, ".") + " %d" % value)
    w("")
    if res is None:
        w("Fewer than %s breaches or %s survivors after exclusions: no statistic is printed." % (
            params["min_each"], params["min_each"]))
    else:
        h1 = res["h1"]
        w("H1  AUC of DT-1 (primary)")
        w("  AUC %s   DeLong SE %s   breaches %d, survivors %d" % (ci(h1), f4(h1["se"]), h1["n1"], h1["n0"]))
        w("")
        w("H2  Does DT-1 add to the baseline B0 (activity, volatility, P&L so far, headroom)?")
        h2 = res["h2"]
        if h2["fit"] != "ok":
            w("  The logistic fit could not be completed (separation). H2 is counted as not passed.")
        else:
            w("  Cross-validated AUC, B0 only ......... %s" % ci(h2["auc_b0"]))
            w("  Cross-validated AUC, B0 + DT-1 ....... %s" % ci(h2["auc_full"]))
            d = h2["delta"]
            w("  Difference (paired DeLong) ........... %+.3f (95%% CI %+.3f to %+.3f)" % (d["diff"], d["lo"], d["hi"]))
            w("  Likelihood-ratio test (1 df) ......... statistic %.3f, p %s, DT-1 coefficient %s" % (
                h2["lr"]["stat"], pv(h2["lr"]["p"]), "positive" if h2["lr"]["coef"] > 0 else "not positive"))
            w("  H2 passed ............................ %s" % ("yes" if h2["passed"] else "no"))
        w("")
        w("FEATURES (exploratory, one-sided, Holm-adjusted across 6)")
        w("  %-24s %-34s %-9s %s" % ("feature", "AUC (95% CI)", "Holm p", "undefined"))
        for f in res["features"]:
            w("  %-24s %-34s %-9s %d" % (f["name"], ci(f["auc"]) if f["auc"] else "n/a", pv(f["p_holm"]),
                                         f["undefined"]))
        w("")
        w("USEFULNESS (DT-1 deciles, lowest scores first; adjacent deciles merged until every cell has 5+)")
        w("  %-9s %-6s %-9s %s" % ("decile", "n", "breaches", "survivors"))
        for r in res["deciles"]:
            w("  %-9s %-6d %-9d %d" % (band_label(r), r["n"], r["events"], r["nonevents"]))
        w("  Breach rate in the top row divided by the overall rate: %s" % f3(res["lift_top"]))
        w("  Confusion counts when the top share of scores is flagged:")
        for s, c in res["confusion"]:
            w("    top %2d%%: flagged %s, breached and flagged %s, survived and flagged %s, breached and not "
              "flagged %s, survived and not flagged %s" % (round(100 * s), cell(c["flagged"]), cell(c["tp"]),
                                                           cell(c["fp"]), cell(c["fn"]), cell(c["tn"])))
        w("")
        w("CALIBRATION (cross-validated predicted chance of a breach)")
        if res["calibration"] is None:
            w("  not available (the logistic fit could not be completed)")
        else:
            for name, c in res["calibration"].items():
                w("  %s: intercept %+.3f, slope %.3f, Brier %.4f, scaled Brier %s" % (
                    name, c["intercept"], c["slope"], c["brier"], f3(c["scaled"])))
                for r in c["bands"]:
                    w("    band %-6s n %-5d mean predicted %.3f   observed %.3f" % (
                        band_label(r), r["n"], r["mean_pred"], r["events"] / r["n"]))
        w("")
        if out["o3"] is not None:
            r3, a3 = out["o3"]
            w("O3  Challenge failure (secondary): ended challenges, failed vs passed")
            if a3 is None or min(r3["breaches"], r3["survivors"]) < M.MIN_CELL:
                w("  not enough ended challenges to report")
            else:
                w("  AUC %s   failed %d, passed %d" % (ci(a3), r3["breaches"], r3["survivors"]))
            w("")
        w("H5  ROBUSTNESS (AUC of DT-1 under each check)")
        for label, r2, a2 in out["robust"]:
            if a2 is None or min(r2["breaches"], r2["survivors"]) < M.MIN_CELL:
                w("  %s: too few accounts to report" % label)
            else:
                w("  %s: AUC %s, breaches %d, survivors %d" % (label, ci(a2), r2["breaches"], r2["survivors"]))
        w("  CFD and futures separately; each firm separately: one market family and one firm per run, so these "
          "are compared across runs.")
        w("")
    w("VERDICT: %s" % out["verdict"])
    w("HOW TO READ: " + HOW_TO_READ[out["verdict"]] + " Past accounts only: this says nothing about any one "
      "trader and is not investment advice.")
    return "\n".join(L) + "\n"


def _jnum(x):
    return None if x is None else (round(x, 6) if isinstance(x, float) else x)


def render_json(params, fp, out):
    """The same numbers as render(), as JSON (for the results page). Built by hand: the json module is not
    imported, so the import list stays the audited one."""
    def enc(v):
        if v is None:
            return "null"
        if v is True:
            return "true"
        if v is False:
            return "false"
        if isinstance(v, (int,)):
            return str(v)
        if isinstance(v, float):
            return repr(round(v, 6)) if math.isfinite(v) else "null"
        if isinstance(v, str):
            return '"' + v.replace("\\", "\\\\").replace('"', '\\"') + '"'
        if isinstance(v, (list, tuple)):
            return "[" + ",".join(enc(x) for x in v) + "]"
        return "{" + ",".join(enc(str(k)) + ":" + enc(v[k]) for k in sorted(v)) + "}"
    rec, res = out["rec"], out["res"]
    doc = {"script": SCRIPT_NAME, "version": SCRIPT_VERSION, "dt_version": params["dt_version"],
           "engine_method": params["engine_method"], "registration": params["registration"], "fingerprint": fp,
           "outcome_mode": params["outcome_mode"], "reconciliation": rec, "verdict": out["verdict"]}
    if res is not None:
        h2 = res["h2"]
        doc["h1"] = {k: res["h1"][k] for k in ("auc", "se", "lo", "hi", "n1", "n0")}
        doc["h2"] = {"passed": h2["passed"], "fit": h2["fit"]}
        if h2["fit"] == "ok":
            doc["h2"].update({"auc_b0": h2["auc_b0"]["auc"], "auc_full": h2["auc_full"]["auc"],
                              "delta": h2["delta"]["diff"], "delta_lo": h2["delta"]["lo"],
                              "delta_hi": h2["delta"]["hi"], "lr_stat": h2["lr"]["stat"], "lr_p": h2["lr"]["p"],
                              "coef_positive": h2["lr"]["coef"] > 0})
        doc["features"] = [{"name": f["name"], "auc": f["auc"]["auc"] if f["auc"] else None,
                            "lo": f["auc"]["lo"] if f["auc"] else None, "hi": f["auc"]["hi"] if f["auc"] else None,
                            "p_holm": f["p_holm"], "undefined": f["undefined"]} for f in res["features"]]
        doc["deciles"] = [{"first": r["first"], "last": r["last"], "n": r["n"], "breaches": r["events"],
                           "survivors": r["nonevents"]} for r in res["deciles"]]
        doc["lift_top"] = res["lift_top"]
        doc["confusion"] = [{"share": s, "flagged": c["flagged"], "tp": c["tp"], "fp": c["fp"], "fn": c["fn"],
                             "tn": c["tn"]} if min(c.values()) >= M.MIN_CELL else {"share": s, "suppressed": True}
                            for s, c in res["confusion"]]
        if res["calibration"] is not None:
            doc["calibration"] = {name: {"intercept": c["intercept"], "slope": c["slope"], "brier": c["brier"],
                                         "scaled": c["scaled"],
                                         "bands": [{"first": r["first"], "last": r["last"], "n": r["n"],
                                                    "mean_pred": r["mean_pred"], "observed": r["events"] / r["n"]}
                                                   for r in c["bands"]]}
                                  for name, c in res["calibration"].items()}
    return enc(doc) + "\n"


def run(argv):
    parser = argparse.ArgumentParser(description="DT-1 prediction study under a sealed pre-registration. "
                                                 "Prints aggregates to stdout only.")
    parser.add_argument("trades_csv")
    parser.add_argument("accounts_csv")
    parser.add_argument("prereg")
    parser.add_argument("--json", action="store_true", help="print the same aggregates as JSON")
    args = parser.parse_args(argv)
    params, fp = read_prereg(args.prereg)
    order, accounts, trades = read_inputs(args.trades_csv, args.accounts_csv, params)
    out = run_study(params, order, accounts, trades, int(fp[:16], 16))
    text = render_json(params, fp, out) if args.json else render(params, fp, out)
    sys.stdout.write(text)
    sys.stdout.flush()
    return 0


def main(argv=None):
    """Every failure becomes a short message with no traceback, so a crash can never echo a line of input."""
    try:
        return run(argv)
    except ValidationError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return 1
    except BrokenPipeError:
        sys.stdout = None
        return 0
    except KeyboardInterrupt:
        sys.stderr.write("ERROR: interrupted\n")
        return 130
    except Exception as exc:
        sys.stderr.write("ERROR: unexpected internal failure (%s). Details are withheld on purpose so that no "
                         "input data can appear in the message.\n" % type(exc).__name__)
        return 3


if __name__ == "__main__":
    sys.exit(main())
