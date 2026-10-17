#!/usr/bin/env python3
"""Disposition-effect statistics (Odean 1998) from a five-column CSV.

Run this inside your own systems, on your own exported file.

  * Standard library only.
  * Opens exactly one file (the CSV you name), read-only.
  * Writes no files. All output goes to stdout (errors go to stderr).
  * Never prints an account_id or position_id, and never prints any cell of
    your file, header or data. Errors give a row NUMBER and a description of
    the problem written by this program. The only schema words that can appear
    in a message are this program's own five column names.

Safety checks: identifiers with invisible characters are refused; identifiers
with ordinary leading/trailing whitespace are refused unless --trim-ids; and if
more than half of the closed positions have no mark row at all the run is
refused unless --allow-orphan-closes (the usual sign that the mark rows did not
join to the close rows); and the same identifier spelled two ways (differing
only in case, whitespace or Unicode form) is refused unless
--allow-identifier-collisions. Any override flag used is stated in the output.

Row numbers in messages count the header as row 1, so the first data row is
row 2 (this matches what a spreadsheet shows). Wholly empty records (blank
lines) are skipped but still take a row number.

Input columns (header names must match exactly; any order is accepted):
  account_id   pseudonymous string, used only for grouping / duplicates
  date         YYYY-MM-DD, the day the position closed or was marked
  position_id  pseudonymous string, used only for duplicate detection
  closed       0 or 1   (1 = closed on this date, 0 = still open end of day)
  pnl          signed decimal (realised if closed=1, unrealised if closed=0)

A mark (closed=0) and a close (closed=1) for the same account, date and position
are merged: the close wins and the mark is discarded and counted (the position
was sold that day, so it is a realisation, not a paper position). Two rows with
the same key and the same closed value are a duplicate and abort the run.

Age-controlled figures (added 17 Oct 2026). After the pooled figures above, the
output adds the same comparison made between positions of the same HOLDING AGE,
because positions are sold less often the longer they are held and a pooled
ratio mixes ages. Holding age is derived from the same five columns: a
position's open date is the date of its first row in the file, and its age on a
row is the number of calendar days since then. Positions already open on the
first date in the file cannot be dated and are left out of those figures (and
counted). No column is added to the input.
"""

# ==========================================================================
# SECTION 1 of 6: AUDIT MAP -- read this, then spot-check the lines it names.
# The question it answers: can this program send your data anywhere, or print it?
#
#   Imports, complete list ...... lines 85-94. No network module, no os,
#                                 no process launcher. (grep the file to confirm.)
#   The only file opened ........ line 336, mode "r" (read-only). Nothing is written.
#   Everything sent to stdout ... line 1161 (the results text) and line 1162
#                                 (flush); line 1178 only assigns None to stdout
#                                 after a broken pipe, it is not output. These
#                                 are the only three lines a text search for the
#                                 module-qualified stdout name finds. argparse prints
#                                 usage/--help text only. The built-in print
#                                 function is never used.
#   Everything sent to stderr ... lines 1172, 1181, 1187, all inside main().
#   Error messages .............. built only at the ValidationError(...) sites
#                                 (grep -n 'ValidationError(' lists them all) and
#                                 printed only by main(), line 1172. They cannot
#                                 contain a cell: each is a fixed sentence into
#                                 which only a row number, a count, our own column
#                                 names or the OS's reason text is substituted.
#   The catch-all ............... line 1183, "except Exception". It prints the
#                                 exception's CLASS NAME only, never its text.
#   Input validation ............ lines 139-267. Everything between them is
#                                 input validation; it reads no new state and
#                                 writes no output (each function takes one row's
#                                 strings and returns a value or raises).
#   Age-controlled figures ...... lines 533-949 (added 17 Oct 2026). Arithmetic
#                                 on the counts read_pairs() already holds in
#                                 memory: it opens nothing and writes nothing;
#                                 its text is returned to run() and printed by
#                                 the one stdout line above.
# ==========================================================================

# ==========================================================================
# SECTION 2 of 6: IMPORTS AND CONSTANTS
# ==========================================================================
from __future__ import annotations
import argparse
import csv
import datetime
import decimal
import math
import re
import sys
import unicodedata
from decimal import Decimal

EXPECTED_COLUMNS = ("account_id", "date", "position_id", "closed", "pnl")

# Strict shapes, matched against the WHOLE cell (re.fullmatch).
DATE_PATTERN = re.compile(r"[0-9]{4}-[0-9]{2}-[0-9]{2}")
# Plain decimal, optional exponent. Rejects nan, inf, "1_000", hex, spaces.
PNL_PATTERN = re.compile(r"[+-]?([0-9]+(\.[0-9]*)?|\.[0-9]+)([eE][+-]?[0-9]+)?")

BASIS_LABELS = {
    "price": "price (funding excluded)",
    "net": "net (funding included)",
}

LABEL_WIDTH = 22
RECON_WIDTH = 36

# Slots in the per-(account, date) tally list.
RG, RL, PG, PL, ZERO, CLOSED_ROWS, ALL_ROWS = range(7)
RESOLVED = 6   # seen_keys marker: this key already merged a mark with its close


# Note for reviewers: there are four internal error signals (ValidationError,
# NulFound, BadBytes, and the csv module's own csv.Error). read_pairs() turns
# every one of them into a ValidationError with a fixed sentence. That is more
# machinery than ideal; it is kept because it is tested.
class ValidationError(Exception):
    """A problem with the input or the arguments. The message is safe to
    print: it is written by this program and never contains cell contents."""


class NulFound(Exception):
    """Internal signal: the raw text of a record contained a NUL character."""


class BadBytes(Exception):
    """Internal signal: the raw text of a record was not valid UTF-8."""

# Why this is here (for the reviewer): the file is read with
# errors="surrogateescape", so a bad byte becomes a lone surrogate in
# U+DC80..U+DCFF instead of raising an error that could quote the bytes.
# Searching each line for one tells us the exact row number to report.
BAD_BYTE_PATTERN = re.compile("[\udc80-\udcff]")


# ==========================================================================
# SECTION 3 of 6: VALIDATION -- pure checks of one row at a time; no state, no output
# ==========================================================================

def check_header(header):
    """The header must be exactly the five expected columns.

    Nothing from the header row is ever printed. We report only a COUNT of
    unexpected cells, and the names of expected columns that are missing or
    repeated (those are this program's own strings)."""
    if len(header) == 0:
        raise ValidationError("row 1: header is blank; expected columns: "
                              + ", ".join(EXPECTED_COLUMNS))
    n_unexpected = len([c for c in header if c not in EXPECTED_COLUMNS])
    missing = [c for c in EXPECTED_COLUMNS if c not in header]
    duplicated = [c for c in EXPECTED_COLUMNS if header.count(c) > 1]
    if n_unexpected or missing or duplicated:
        parts = []
        if n_unexpected:
            parts.append("%d unexpected column(s), names not shown" % n_unexpected)
        if missing:
            parts.append("missing column(s): " + ", ".join(missing))
        if duplicated:
            parts.append("repeated column(s): " + ", ".join(duplicated))
        raise ValidationError(
            "row 1: header is not exactly the five required columns ("
            + "; ".join(parts) + "). Extra columns are refused on purpose: "
            "an extra column may carry identifying data. Re-export with only: "
            + ", ".join(EXPECTED_COLUMNS))


def has_invisible_char(text):
    """True if text contains a format character (category Cf, e.g. U+200B
    zero-width space, U+FEFF), a control character (category Cc, e.g. tab), or
    any non-ASCII whitespace (e.g. U+00A0). Such characters are invisible in a
    spreadsheet but make two identical-looking identifiers different, so they
    are always refused, even with --trim-ids."""
    for ch in text:
        if unicodedata.category(ch) in ("Cf", "Cc"):
            return True
        if ord(ch) > 127 and ch.isspace():
            return True
    return False


def parse_row(fields, col, row_no, trim_ids):
    """Validate one data row.
    Returns (account, date, position, closed_flag, sign, trimmed_flag,
    raw_account) where
    sign is +1, -1 or 0 for the sign of pnl, and trimmed_flag is 1 if
    --trim-ids changed an identifier on this row.
    Any problem raises ValidationError naming only the row number."""
    if len(fields) == 1 and fields[0].strip() == "":
        raise ValidationError(
            "row %d: the row is blank apart from whitespace" % row_no)
    if len(fields) != len(EXPECTED_COLUMNS):
        raise ValidationError(
            "row %d: has %d fields, expected %d (an unbalanced quote or a "
            "stray comma is a likely cause)" %
            (row_no, len(fields), len(EXPECTED_COLUMNS)))

    account = fields[col["account_id"]]
    position = fields[col["position_id"]]
    date = fields[col["date"]]
    closed = fields[col["closed"]]
    pnl_text = fields[col["pnl"]]

    if has_invisible_char(account) or has_invisible_char(position):
        raise ValidationError(
            "row %d: account_id or position_id contains an invisible or "
            "control character; export plain text identifiers" % row_no)
    if account.strip() == "":
        raise ValidationError("row %d: account_id is empty" % row_no)
    if position.strip() == "":
        raise ValidationError("row %d: position_id is empty" % row_no)

    # Whitespace around an identifier would silently make "A1" and "A1 " two
    # different accounts and wreck the result. Refuse it by default.
    raw_account = account
    trimmed_flag = 0
    if account != account.strip() or position != position.strip():
        if not trim_ids:
            raise ValidationError(
                "row %d: account_id or position_id has leading or trailing "
                "whitespace; TRIM the column on export (or re-run with "
                "--trim-ids to strip it, which is reported in the output)"
                % row_no)
        account = account.strip()
        position = position.strip()
        trimmed_flag = 1

    if DATE_PATTERN.fullmatch(date) is None:
        raise ValidationError("row %d: date is not in YYYY-MM-DD form" % row_no)
    try:
        datetime.date(int(date[0:4]), int(date[5:7]), int(date[8:10]))
    except ValueError:
        raise ValidationError(
            "row %d: date is not a valid calendar date" % row_no) from None

    if closed == "0":
        closed_flag = 0
    elif closed == "1":
        closed_flag = 1
    else:
        raise ValidationError("row %d: closed must be exactly 0 or 1" % row_no)

    if PNL_PATTERN.fullmatch(pnl_text) is None:
        raise ValidationError("row %d: pnl is not a plain decimal number" % row_no)
    # Finite check (rejects values so large a float overflows to inf).
    if not math.isfinite(float(pnl_text)):
        raise ValidationError("row %d: pnl is not a finite number" % row_no)
    # The SIGN is taken from the exact Decimal, never from the float, so a
    # tiny value such as 1e-400 (a float would round it to 0.0) is still a gain.
    try:
        exact = Decimal(pnl_text)
    except decimal.InvalidOperation:
        raise ValidationError(
            "row %d: pnl is not a usable number" % row_no) from None
    if exact > 0:
        sign = 1
    elif exact < 0:
        sign = -1
    else:
        sign = 0

    return account, date, position, closed_flag, sign, trimmed_flag, raw_account


# ---- end of input validation (see AUDIT MAP) ----

# ==========================================================================
# SECTION 4 of 6: IO -- reading the file, tallying rows
# ==========================================================================

def normalise_id(text):
    """Key used to decide whether two spellings are 'the same identifier':
    Unicode compatibility form (NFKC), surrounding whitespace removed, case
    folded. Used only for comparison; the original spelling is what is counted."""
    return unicodedata.normalize("NFKC", text).strip().casefold()


def note_spelling(table, key):
    """Record one NEW distinct raw spelling under its normalised key."""
    table[key] = table.get(key, 0) + 1


def lines_without_nul(handle):
    """Yield the raw text lines of the file, refusing any that contain a NUL
    character or an undecodable byte. Done before CSV parsing so every Python
    version behaves the same (some versions of the csv module reject NUL, some
    accept it) and so the row number of the problem is exact."""
    for text in handle:
        if "\0" in text:
            raise NulFound()
        if BAD_BYTE_PATTERN.search(text) is not None:
            raise BadBytes()
        yield text


def read_pairs(path, trim_ids):
    """Read and fully validate the file. Returns (pairs, stats).

    pairs: (account_id, date) -> [RG, RL, PG, PL, zero_rows, closed_rows, rows]
    stats: counts used for the reconciliation block.

    Every data row is validated before this returns, so nothing is printed
    unless the whole file is clean."""
    pairs = {}
    # (account, date, position) -> what we saw: closed * 3 + sign + 1 (0..5),
    # or RESOLVED once a same-day mark and close have been merged. Used to
    # detect duplicates and to merge a same-day mark with its close.
    seen_keys = {}
    superseded = 0      # same-day marks dropped because the position closed
    closed_on = {}      # (account, position) -> date it was closed
    last_open = {}      # (account, position) -> latest date it was marked open
    rows_read = 0
    blank_skipped = 0
    trimmed = 0
    raw_spellings = {}  # only with --trim-ids: trimmed account -> raw spellings
    # Identifier-collision check: normalised key -> number of DISTINCT raw
    # spellings seen. A count above 1 means two spellings of "the same" id.
    # Account ids are compared across the whole file. Position ids are compared
    # only within one (normalised) account, because a position id only has to be
    # unique within its account.
    known_accounts = {}     # raw account spelling -> its normalised key
    known_positions = set() # (normalised account, raw position spelling)
    account_spellings = {}
    position_spellings = {}
    mark_count = {}     # (account, position) -> marks that survived into the tally
    # For the age-controlled figures: every row of every position, as one int
    # per row: date ordinal * 8 + closed * 4 + (sign + 1). Sorting a position's
    # list puts its rows in date order, and a same-day mark before its close.
    pos_codes = {}      # (account, position) -> [code, ...]
    ordinal_of = {}     # validated date string -> proleptic ordinal (day number)
    after = " (after --trim-ids was applied)" if trim_ids else ""

    try:
        handle = open(path, "r", encoding="utf-8-sig", errors="surrogateescape",
                      newline="")
    except OSError as exc:
        reason = exc.strerror if exc.strerror else "unknown reason"
        raise ValidationError("cannot open the input file (%s)" % reason) from None

    row_no = 0   # number of records read so far, header and blank ones included
    try:
        with handle:
            reader = csv.reader(lines_without_nul(handle))

            try:
                header = next(reader)
            except StopIteration:
                raise ValidationError("the file is empty") from None
            row_no = 1
            check_header(header)
            col = {name: header.index(name) for name in EXPECTED_COLUMNS}

            for fields in reader:
                row_no += 1
                if len(fields) == 0:
                    blank_skipped += 1      # a wholly empty record: skip, count
                    continue
                (account, date, position, closed, sign, was_trimmed,
                 raw_account) = parse_row(fields, col, row_no, trim_ids)
                rows_read += 1
                trimmed += was_trimmed
                if account not in known_accounts:
                    known_accounts[account] = normalise_id(account)
                    note_spelling(account_spellings, known_accounts[account])
                account_key = known_accounts[account]
                if (account_key, position) not in known_positions:
                    known_positions.add((account_key, position))
                    note_spelling(position_spellings,
                                  (account_key, normalise_id(position)))
                if trim_ids:
                    raw_spellings.setdefault(account, set()).add(raw_account)

                key = (account, date, position)
                prior = seen_keys.get(key)
                if prior is not None and (prior == RESOLVED or prior // 3 == closed):
                    # Same key and same closed value (or a third row): duplicate.
                    raise ValidationError(
                        "row %d: duplicate (account_id, date, position_id)%s"
                        % (row_no, after))
                seen_keys[key] = RESOLVED if prior is not None else closed * 3 + sign + 1

                pos_key = (account, position)
                ordinal = ordinal_of.get(date)
                if ordinal is None:
                    ordinal = datetime.date(int(date[0:4]), int(date[5:7]),
                                            int(date[8:10])).toordinal()
                    ordinal_of[date] = ordinal
                pos_codes.setdefault(pos_key, []).append(
                    ordinal * 8 + closed * 4 + sign + 1)
                if closed == 1:
                    if pos_key in closed_on and closed_on[pos_key] != date:
                        raise ValidationError(
                            "row %d: this position is already marked closed on "
                            "a different date%s" % (row_no, after))
                    closed_on[pos_key] = date
                    # Dates are validated YYYY-MM-DD strings, so string order
                    # is date order. Rows may arrive in any order, so check
                    # both directions (here and in the else branch).
                    if pos_key in last_open and last_open[pos_key] > date:
                        raise ValidationError(
                            "row %d: this position is marked open on a date "
                            "after it was closed%s" % (row_no, after))
                else:
                    if pos_key in closed_on and date > closed_on[pos_key]:
                        raise ValidationError(
                            "row %d: this position is marked open on a date "
                            "after it was closed%s" % (row_no, after))
                    if pos_key not in last_open or date > last_open[pos_key]:
                        last_open[pos_key] = date

                # Tally the row against its (account, date) pair.
                tally = pairs.get((account, date))
                if tally is None:
                    tally = [0, 0, 0, 0, 0, 0, 0]
                    pairs[(account, date)] = tally
                if prior is not None:
                    # One closed=1 row and one closed=0 row share a key: the
                    # position was marked during the day and closed at the end.
                    # On its sale day it is a realisation, so the close wins and
                    # the mark is discarded (and counted in the output).
                    superseded += 1
                    if closed == 0:
                        continue                    # close came first: drop this mark
                    prior_sign = prior % 3 - 1      # mark came first: undo it
                    mark_count[pos_key] = mark_count.get(pos_key, 0) - 1   # not a mark now
                    tally[ALL_ROWS] -= 1
                    if prior_sign > 0:
                        tally[PG] -= 1
                    elif prior_sign < 0:
                        tally[PL] -= 1
                    else:
                        tally[ZERO] -= 1
                tally[ALL_ROWS] += 1
                if closed == 1:
                    tally[CLOSED_ROWS] += 1            # a close happened here
                    if sign > 0:
                        tally[RG] += 1
                    elif sign < 0:
                        tally[RL] += 1
                    else:
                        tally[ZERO] += 1
                else:
                    mark_count[pos_key] = mark_count.get(pos_key, 0) + 1
                    if sign > 0:
                        tally[PG] += 1
                    elif sign < 0:
                        tally[PL] += 1
                    else:
                        tally[ZERO] += 1
    except (UnicodeDecodeError, BadBytes):
        raise ValidationError(
            "at or near row %d: the file is not valid UTF-8 text"
            % (row_no + 1)) from None
    except NulFound:
        raise ValidationError(
            "at or near row %d: the file contains a NUL (zero) byte, so it is "
            "not plain CSV text" % (row_no + 1)) from None
    except csv.Error:
        raise ValidationError(
            "row %d: the row could not be parsed as CSV" % (row_no + 1)) from None

    if rows_read == 0:
        raise ValidationError("the file has a header but no data rows")
    # Orphan closes: positions that were closed but have no closed=0 mark row
    # that SURVIVED into the statistics. A mark dropped because it shares a day
    # with the close is not evidence that the position was ever held as a paper
    # position, so it does not count. On a clean marks-plus-closes export this
    # is near zero; if the mark rows failed to join to the close rows it is ~100%.
    closed_positions = len(closed_on)
    orphan_closes = sum(1 for k in closed_on if mark_count.get(k, 0) == 0)
    collisions = (sum(1 for n in account_spellings.values() if n > 1)
                  + sum(1 for n in position_spellings.values() if n > 1))
    stats = {"rows_read": rows_read, "collisions": collisions, "blank_skipped": blank_skipped,
             "trimmed": trimmed, "raw_spellings": raw_spellings,
             "superseded": superseded,
             "closed_positions": closed_positions,
             "orphan_closes": orphan_closes,
             "pos_codes": pos_codes, "ordinal_of": ordinal_of}
    return pairs, stats


# ==========================================================================
# SECTION 5 of 6: ARITHMETIC -- the statistic and the results text
# ==========================================================================

def summarise(pairs):
    """Apply Odean's conditioning rule and pool the four buckets.

    CONDITIONING RULE: an (account, date) pair counts ONLY if that account
    closed at least one position on that date (closed_rows > 0). Every row of
    any other pair is discarded, including its zero-pnl rows. This keeps
    dormant accounts out: they would add paper positions but no realisations
    and bias both ratios downward.

    FOUR BUCKETS, within qualifying pairs only:
        RG realised gain  closed=1 and pnl > 0
        RL realised loss  closed=1 and pnl < 0
        PG paper gain     closed=0 and pnl > 0
        PL paper loss     closed=0 and pnl < 0
    pnl == 0 belongs to none of them and is counted as zero_rows.

    Counts are pooled across all accounts and days (not averaged per account).
    """
    rg = rl = pg = pl = zero_rows = rows_in_pairs = 0
    accounts = set()
    qualifying_days = 0
    for (account, _date), tally in pairs.items():
        if tally[CLOSED_ROWS] == 0:
            continue                      # no close on this day: discard
        qualifying_days += 1
        accounts.add(account)
        rg += tally[RG]
        rl += tally[RL]
        pg += tally[PG]
        pl += tally[PL]
        zero_rows += tally[ZERO]
        rows_in_pairs += tally[ALL_ROWS]
    if qualifying_days == 0:
        raise ValidationError(
            "no (account, date) pair has a closed position; nothing to measure")
    return {
        "accounts": len(accounts),
        "account_names": accounts,
        "days": qualifying_days,
        "RG": rg, "RL": rl, "PG": pg, "PL": pl,
        "zero": zero_rows,
        "rows_in_pairs": rows_in_pairs,
    }


# ---- Age-controlled figures (added 17 Oct 2026) ---------------------------
# Why (for the reviewer): positions are sold less often the longer they are
# held. If losing positions are on average older, a PLR pooled over all ages
# is pulled down by age rather than by any reluctance to sell, and the pooled
# ratio above overstates the effect. The figures below compare positions of
# the SAME holding age. Everything here reads only the in-memory tallies built
# by read_pairs(); it opens nothing and prints nothing.

AGE_BUCKETS = ((0, 1, "<=1 day"), (2, 5, "2-5 days"), (6, 20, "6-20 days"),
               (21, 60, "21-60 days"), (61, 250, "61-250 days"),
               (251, None, "251+ days"))
Z95 = 1.959964
FE_TOL = 1e-10          # convergence of the fixed-effects projection
FE_MAX_ITER = 20000


def stratum_of(age):
    """The Mantel-Haenszel stratum: one per exact holding day. (Six wide
    buckets alone are not enough: within a bucket the sale rate still falls
    with age while the share of losers rises.)"""
    return age


def bucket_label(age):
    for low, high, label in AGE_BUCKETS:
        if age >= low and (high is None or age <= high):
            return label
    return AGE_BUCKETS[-1][2]


def aged_rows(pairs, stats):
    """Yield one tuple per row that the age-controlled figures use:
    (account, date ordinal, age, sold, sign, previous sign).

    Same rows as the pooled figure (qualifying (account, date) pairs, pnl not 0;
    a same-day mark and close count once, as the close), restricted to positions
    whose open date is known. A position's open date is the date of its first
    row; it is unknown (left-censored) when that first row is on the first date
    in the file, because the position may have been opened before the export
    began. 'previous sign' is the pnl sign on the position's previous row (any
    earlier date, qualifying or not), or None on its first row."""
    ordinal_of = stats["ordinal_of"]
    first_ordinal = min(ordinal_of.values())
    qualifying = set()
    for (account, date), tally in pairs.items():
        if tally[CLOSED_ROWS] > 0:
            qualifying.add((account, ordinal_of[date]))
    for (account, _position), codes in stats["pos_codes"].items():
        codes.sort()
        if codes[0] >> 3 == first_ordinal:
            continue                       # opened on or before the first date: age unknown
        open_ordinal = codes[0] >> 3
        prev_sign = None
        last = len(codes) - 1
        for i, code in enumerate(codes):
            ordinal = code >> 3
            if i < last and codes[i + 1] >> 3 == ordinal:
                continue                   # a same-day mark: the close that follows wins
            sold = (code >> 2) & 1
            sign = (code & 3) - 1
            if sign != 0 and (account, ordinal) in qualifying:
                yield account, ordinal, ordinal - open_ordinal, sold, sign, prev_sign
            prev_sign = sign


def censor_counts(stats):
    """(positions with a known open date, positions open on the first date)."""
    first_ordinal = min(stats["ordinal_of"].values())
    censored = 0
    for codes in stats["pos_codes"].values():
        if min(codes) >> 3 == first_ordinal:
            censored += 1
    return len(stats["pos_codes"]) - censored, censored


def add_cell(cells, key, gain, sold):
    """cells[key] = [gain rows, loss rows, sold gains, sold losses]."""
    c = cells.get(key)
    if c is None:
        c = [0, 0, 0, 0]
        cells[key] = c
    if gain:
        c[0] += 1
        c[2] += sold
    else:
        c[1] += 1
        c[3] += sold


def crude(cells, keep=None):
    """Plain pooled PGR, PLR and ratio over (account, age) cells."""
    n1 = n0 = a = c = 0
    for (_account, age), v in cells.items():
        if keep is None or keep(age):
            n1 += v[0]
            n0 += v[1]
            a += v[2]
            c += v[3]
    pgr = a / n1 if n1 else None
    plr = c / n0 if n0 else None
    ratio = pgr / plr if (pgr is not None and plr) else None
    return {"n1": n1, "n0": n0, "a": a, "c": c, "pgr": pgr, "plr": plr, "ratio": ratio}


def mantel_haenszel(cells, keep=None):
    """Mantel-Haenszel ratio of the sale rate of gains to that of losses, with
    one stratum per exact holding day:  R = sum_k a_k n0_k / N_k  /  sum_k c_k n1_k / N_k.
    95% interval clustered by account: each account's share of the numerator
    and denominator, A_g and B_g, with the stratum sizes held fixed;
    var(log R) = G/(G-1) * sum_g (A_g - R B_g)^2 / A^2 (a ratio estimator)."""
    strata = {}
    for (_account, age), v in cells.items():
        if keep is None or keep(age):
            k = stratum_of(age)
            t = strata.get(k)
            if t is None:
                t = [0, 0]
                strata[k] = t
            t[0] += v[0]
            t[1] += v[1]
    per_account = {}
    for (account, age), v in cells.items():
        if keep is not None and not keep(age):
            continue
        n1, n0 = strata[stratum_of(age)]
        total = n1 + n0
        pa = per_account.get(account)
        if pa is None:
            pa = [[], []]
            per_account[account] = pa
        pa[0].append(v[2] * n0 / total)
        pa[1].append(v[3] * n1 / total)
    a_g = [math.fsum(v[0]) for v in per_account.values()]
    b_g = [math.fsum(v[1]) for v in per_account.values()]
    num = math.fsum(a_g)
    den = math.fsum(b_g)
    out = {"ratio": None, "lo": None, "hi": None, "accounts": len(a_g)}
    if den <= 0:
        return out
    ratio = num / den
    out["ratio"] = ratio
    g = len(a_g)
    if num > 0 and g > 1:
        var = (g / (g - 1.0)) * math.fsum((x - ratio * y) ** 2
                                          for x, y in zip(a_g, b_g)) / (num * num)
        se = math.sqrt(var)
        out["lo"] = ratio * math.exp(-Z95 * se)
        out["hi"] = ratio * math.exp(Z95 * se)
    return out


def fe_projection(index_a, index_t, n, x, n_a, n_t):
    """Least-squares fit of a cell total x on account and holding-day effects,
    weighted by the cell's row count n, by alternating projections (backfitting).
    The fit depends only on cell totals, so it runs on (account, age) cells,
    not on rows. Returns (fitted value per cell, converged, iterations)."""
    alpha = [0.0] * len(n_a)
    gamma = [0.0] * len(n_t)
    cells = range(len(n))
    for iteration in range(1, FE_MAX_ITER + 1):
        sa = [0.0] * len(n_a)
        for i in cells:
            sa[index_a[i]] += x[i] - n[i] * gamma[index_t[i]]
        new_alpha = [sa[j] / n_a[j] for j in range(len(n_a))]
        st = [0.0] * len(n_t)
        for i in cells:
            st[index_t[i]] += x[i] - n[i] * new_alpha[index_a[i]]
        new_gamma = [st[j] / n_t[j] for j in range(len(n_t))]
        change = max(max(abs(p - q) for p, q in zip(alpha, new_alpha)),
                     max(abs(p - q) for p, q in zip(gamma, new_gamma)))
        alpha, gamma = new_alpha, new_gamma
        if change < FE_TOL:
            return [alpha[index_a[i]] + gamma[index_t[i]] for i in cells], True, iteration
    return [alpha[index_a[i]] + gamma[index_t[i]] for i in cells], False, FE_MAX_ITER


def fixed_effects(cells, row_source):
    """Linear probability model  sold = beta * gain + account effect + holding-day
    effect, one effect per exact holding day (the discrete-time form of a sale
    hazard with a fully flexible baseline in holding age). By the Frisch-Waugh
    theorem beta = sum(g~ s~) / sum(g~^2), where g~ and s~ are gain and sold
    minus their fitted account + holding-day effects; those fits depend only on
    (account, age) cell totals. Standard error clustered by account and by date
    (Cameron-Gelbach-Miller): one more pass over the rows (row_source()) for the
    date sums. ATT ratio = sale rate of gain rows / (that rate - beta)."""
    keys = list(cells)
    acc_ix, age_ix = {}, {}
    index_a, index_t, n, gx, sx, gsx = [], [], [], [], [], []
    for key in keys:
        v = cells[key]
        index_a.append(acc_ix.setdefault(key[0], len(acc_ix)))
        index_t.append(age_ix.setdefault(key[1], len(age_ix)))
        n.append(v[0] + v[1])
        gx.append(v[0])
        sx.append(v[2] + v[3])
        gsx.append(v[2])
    n_a = [0] * len(acc_ix)
    n_t = [0] * len(age_ix)
    for i in range(len(n)):
        n_a[index_a[i]] += n[i]
        n_t[index_t[i]] += n[i]
    out = {"beta": None, "se": None, "att": None, "att_lo": None, "att_hi": None,
           "converged": False, "iterations": 0, "twoway_fallback": False}
    if not n:
        return out
    fg, ok_g, it_g = fe_projection(index_a, index_t, n, gx, n_a, n_t)
    fs, ok_s, it_s = fe_projection(index_a, index_t, n, sx, n_a, n_t)
    out["converged"] = ok_g and ok_s
    out["iterations"] = max(it_g, it_s)
    if not out["converged"]:
        return out
    sgg = math.fsum(gx[i] - 2.0 * fg[i] * gx[i] + n[i] * fg[i] * fg[i]
                    for i in range(len(n)))
    sgs = math.fsum(gsx[i] - fs[i] * gx[i] - fg[i] * sx[i] + n[i] * fg[i] * fs[i]
                    for i in range(len(n)))
    if sgg <= 1e-9:
        return out                       # gain does not vary within account and age
    beta = sgs / sgg
    out["beta"] = beta
    n1 = math.fsum(gx)
    sale_gain = math.fsum(gsx) / n1 if n1 else None
    if sale_gain is not None and sale_gain - beta > 0:
        out["att"] = sale_gain / (sale_gain - beta)
    # scores: account sums from cells; date and account-date sums from rows
    score_a = [0.0] * len(acc_ix)
    for i in range(len(n)):
        cell_sgg = gx[i] - 2.0 * fg[i] * gx[i] + n[i] * fg[i] * fg[i]
        cell_sgs = gsx[i] - fs[i] * gx[i] - fg[i] * sx[i] + n[i] * fg[i] * fs[i]
        score_a[index_a[i]] += cell_sgs - beta * cell_sgg
    cell_ix = {key: i for i, key in enumerate(keys)}
    score_d, score_ad = {}, {}
    for account, ordinal, age, sold, gain in row_source():
        i = cell_ix[(account, age)]
        gt = gain - fg[i]
        u = gt * (sold - fs[i] - beta * gt)
        score_d[ordinal] = score_d.get(ordinal, 0.0) + u
        score_ad[(account, ordinal)] = score_ad.get((account, ordinal), 0.0) + u

    def meat(scores):
        g = len(scores)
        return (g / (g - 1.0)) * math.fsum(x * x for x in scores)
    if len(score_a) < 2:
        return out                       # one account: no clustered standard error
    v_a = meat(score_a)
    if len(score_d) < 2:
        v = v_a                          # one date: account clusters only
        out["twoway_fallback"] = True
    else:
        v = v_a + meat(list(score_d.values())) - meat(list(score_ad.values()))
        if v <= 0:
            v = max(v_a, meat(list(score_d.values())))
            out["twoway_fallback"] = True
    se = math.sqrt(v) / sgg
    out["se"] = se
    if out["att"] is not None:
        if sale_gain - (beta - Z95 * se) > 0:
            out["att_lo"] = sale_gain / (sale_gain - (beta - Z95 * se))
        if sale_gain - (beta + Z95 * se) > 0:
            out["att_hi"] = sale_gain / (sale_gain - (beta + Z95 * se))
    return out


def age_controlled(pairs, stats):
    """All age-controlled figures, as a dict for age_lines()."""
    cells = {}          # (account, age) -> counts, same-day gain, all dated rows
    same_p = {}         # rows with a previous row: same-day gain
    prev_p = {}         # rows with a previous row: gain from the previous row
    flips = [0, 0, 0, 0]    # sold rows, sold rows whose sign changed, unsold, unsold changed
    for account, _ordinal, age, sold, sign, prev_sign in aged_rows(pairs, stats):
        add_cell(cells, (account, age), sign > 0, sold)
        if prev_sign is not None and prev_sign != 0:
            add_cell(same_p, (account, age), sign > 0, sold)
            add_cell(prev_p, (account, age), prev_sign > 0, sold)
            changed = 1 if (sign > 0) != (prev_sign > 0) else 0
            if sold:
                flips[0] += 1
                flips[1] += changed
            else:
                flips[2] += 1
                flips[3] += changed

    def rows_same():
        for account, ordinal, age, sold, sign, _p in aged_rows(pairs, stats):
            yield account, ordinal, age, sold, 1 if sign > 0 else 0

    def rows_with_prev(use_prev):
        def source():
            for account, ordinal, age, sold, sign, prev in aged_rows(pairs, stats):
                if prev is not None and prev != 0:
                    g = prev if use_prev else sign
                    yield account, ordinal, age, sold, 1 if g > 0 else 0
        return source

    dated, censored = censor_counts(stats)
    res = {"dated": dated, "censored": censored, "flips": flips,
           "all": crude(cells), "mh": mantel_haenszel(cells), "buckets": []}
    for low, high, label in AGE_BUCKETS:
        def keep(age, low=low, high=high):
            return age >= low and (high is None or age <= high)
        b = crude(cells, keep)
        b["label"] = label
        b["mh"] = mantel_haenszel(cells, keep)
        res["buckets"].append(b)
    res["fe"] = fixed_effects(cells, rows_same)
    res["same_crude"] = crude(same_p)
    res["prev_crude"] = crude(prev_p)
    res["same_mh"] = mantel_haenszel(same_p)
    res["prev_mh"] = mantel_haenszel(prev_p)
    res["same_fe"] = fixed_effects(same_p, rows_with_prev(False))
    res["prev_fe"] = fixed_effects(prev_p, rows_with_prev(True))
    return res


def num(value, places):
    """Fixed-point text for a float; None -> NOT MEASURED; never '-0.000'."""
    if value is None:
        return "NOT MEASURED"
    text = "%.*f" % (places, value)
    if text.lstrip("-").strip("0.") == "":
        text = text.lstrip("-")
    return text


def interval(lo, hi, places=4):
    if lo is None and hi is None:      # else each bound on its own (OBMS 0.1, 6.4)
        return "interval NOT MEASURED"
    return "95%% interval %s to %s" % (num(lo, places), num(hi, places))


AGE_WIDTH = 48

CAVEAT = (
    "",
    "HOW TO READ THE AGE-CONTROLLED FIGURES",
    "- Positions are sold less often the longer they are held. If losing",
    "  positions are on average older than winning ones, the pooled ratio at",
    "  the top can show an effect that is only an age pattern. The within-age",
    "  ratio compares winners and losers of the same holding age; use it, not",
    "  the pooled ratio, for the size of the effect.",
    "- Holding age is counted from each position's first row in this file.",
    "  Positions already open on the file's first date are left out of these",
    "  figures because their age is unknown; the pooled figures still use them.",
    "- The fixed-effects line compares each account with itself, at the same",
    "  holding day. It is a different average from the pooled ratio, so the two",
    "  are not expected to match.",
    "- Gain timing: a position's gain or loss on the day it is sold may partly",
    "  reflect the sale itself (the fill or the closing mark). The lines that",
    "  take the gain or loss from the position's previous row avoid that. If",
    "  they are much smaller, the effect depends on same-day timing.",
    "- Not ruled out: traders may sell large moves in either direction more",
    "  often (a V-shaped pattern, Ben-David and Hirshleifer 2012). Separating",
    "  that from a preference for selling winners needs the size of each gain",
    "  or loss relative to the position, which these five columns do not carry.",
    "- The intervals here are clustered by account (the within-age ratio) and",
    "  by account and date (fixed effects). The t statistic at the top treats",
    "  every row as independent and is not.",
    "- NOT MEASURED means the data cannot support the figure, never zero.",
)


def age_lines(res):
    """The age-controlled block, appended after the original output."""
    w = AGE_WIDTH
    a = res["all"]
    out = [
        "",
        "AGE-CONTROLLED FIGURES (holding age = calendar days since the",
        "position's first row in this file)",
        line("positions with a known open date:", str(res["dated"]), w),
        line("positions open on the first date (left out):", str(res["censored"]), w),
        line("rows used (qualifying pairs, pnl not 0):", str(a["n1"] + a["n0"]), w),
        "",
        line("ratio, ages pooled, same rows:", num(a["ratio"], 4), w),
        line("within-age ratio (Mantel-Haenszel):", num(res["mh"]["ratio"], 4), w),
        line("", interval(res["mh"]["lo"], res["mh"]["hi"]) + ", by account", w),
        "",
        "holding age      gain rows  loss rows     PGR     PLR   ratio  within-age",
    ]
    for b in res["buckets"]:
        out.append("%-15s %10d %10d %7s %7s %7s %11s" % (
            b["label"], b["n1"], b["n0"],
            num(b["pgr"], 4) if b["pgr"] is not None else "-",
            num(b["plr"], 4) if b["plr"] is not None else "-",
            num(b["ratio"], 3) if b["ratio"] is not None else "-",
            num(b["mh"]["ratio"], 3) if b["mh"]["ratio"] is not None else "-"))
    fe = res["fe"]
    out += [
        "",
        "fixed effects (account + holding day), linear probability model:",
        line("  gain coefficient:", num(fe["beta"], 6), w),
        line("  standard error (account and date):", num(fe["se"], 6), w),
        line("  ratio implied for gain rows (ATT):", num(fe["att"], 4), w),
        line("", interval(fe["att_lo"], fe["att_hi"]), w),
    ]
    if not fe["converged"]:
        out.append("  fixed effects NOT MEASURED: the fit did not converge")
    if fe["twoway_fallback"]:
        out.append("  (two-way variance not usable: one date, or not positive; one-way used)")
    sc, pc = res["same_crude"], res["prev_crude"]
    f = res["flips"]
    out += [
        "",
        "gain timing (rows that have a previous row for the same position):",
        line("  rows:", str(sc["n1"] + sc["n0"]), w),
        line("  ratio, ages pooled: same day / previous row:",
             "%s / %s" % (num(sc["ratio"], 4), num(pc["ratio"], 4)), w),
        line("  within-age ratio: same day / previous row:",
             "%s / %s" % (num(res["same_mh"]["ratio"], 4), num(res["prev_mh"]["ratio"], 4)), w),
        line("  fixed-effects ATT: same day / previous row:",
             "%s / %s" % (num(res["same_fe"]["att"], 4), num(res["prev_fe"]["att"], 4)), w),
        line("  sign changed since previous row, sold rows:",
             "%d of %d" % (f[1], f[0]), w),
        line("  sign changed since previous row, unsold rows:",
             "%d of %d" % (f[3], f[2]), w),
    ]
    out += list(CAVEAT)
    return "\n".join(out) + "\n"


def line(label, value, width=LABEL_WIDTH):
    """One output line: label padded to a fixed column, then the value."""
    if len(label) >= width:
        return label + " " + value
    return label.ljust(width) + value


def show(value, places):
    """Round half-up (the way a spreadsheet does) and format without any
    exponent. A tiny negative that rounds to zero prints as 0, not -0."""
    q = value.quantize(Decimal(1).scaleb(-places), rounding=decimal.ROUND_HALF_UP)
    if q.is_zero():
        q = abs(q)
    return format(q, "f")


def render(basis, s, stats, trim_ids, orphan_flag, collision_flag):
    """Build the output text. A number is printed only if it was measured;
    otherwise the line says NOT MEASURED and why. No division by zero.
    Arithmetic is done in Decimal (50 digits) and rounded half-up for display,
    so a reader reproducing a ratio in a spreadsheet gets the same digit."""
    rg, rl, pg, pl = s["RG"], s["RL"], s["PG"], s["PL"]
    n_gains = rg + pg
    n_losses = rl + pl
    # parsed = in qualifying pairs + discarded (no close that day) + superseded
    discarded = stats["rows_read"] - s["rows_in_pairs"] - stats["superseded"]
    closed_positions = stats["closed_positions"]
    orphans = stats["orphan_closes"]

    with decimal.localcontext() as ctx:
        ctx.prec = 50
        pgr = Decimal(rg) / Decimal(n_gains) if n_gains > 0 else None
        plr = Decimal(rl) / Decimal(n_losses) if n_losses > 0 else None

        if pgr is None:
            pgr_text = "NOT MEASURED (no gain observations: RG+PG = 0)"
        else:
            pgr_text = show(pgr, 4)
        if plr is None:
            plr_text = "NOT MEASURED (no loss observations: RL+PL = 0)"
        else:
            plr_text = show(plr, 4)

        # ratio = PGR / PLR, from exact integer counts
        if pgr is None or plr is None:
            ratio_text = "NOT MEASURED (PGR or PLR is not measured)"
        elif rl == 0:
            ratio_text = "NOT MEASURED (PLR is 0, so the ratio is undefined)"
        else:
            ratio = Decimal(rg * n_losses) / Decimal(n_gains * rl)
            ratio_text = show(ratio, 4)

        # t = (PGR - PLR) / sqrt(PGR(1-PGR)/(RG+PG) + PLR(1-PLR)/(RL+PL))
        if pgr is None or plr is None:
            t_text = "NOT MEASURED (PGR or PLR is not measured)"
        else:
            variance = (pgr * (1 - pgr) / n_gains
                        + plr * (1 - plr) / n_losses)
            if variance <= 0:
                t_text = ("NOT MEASURED (zero variance: PGR and PLR are each "
                          "0 or 1)")
            else:
                t_text = show((pgr - plr) / variance.sqrt(), 2)

    orphan_pct = show(Decimal(100 * orphans) / Decimal(closed_positions), 1)

    out = [
        line("pnl basis:", BASIS_LABELS[basis]),
        line("accounts:", str(s["accounts"])),
    ]
    if trim_ids:
        # How many raw spellings the qualifying accounts had before trimming.
        # More than "accounts" means trimming merged accounts together.
        before = sum(len(stats["raw_spellings"][a]) for a in s["account_names"])
        out.append(line("distinct account_ids before trimming:", str(before)))
    out += [
        line("qualifying sale days:", str(s["days"])),
        "",
        # Reconciliation: every row read is accounted for.
        line("data rows parsed:", str(stats["rows_read"]), RECON_WIDTH),
        line("blank records skipped:", str(stats["blank_skipped"]), RECON_WIDTH),
        line("rows in qualifying pairs:", str(s["rows_in_pairs"]), RECON_WIDTH),
        line("rows discarded (no close that day):", str(discarded), RECON_WIDTH),
        line("same-day marks superseded by close:", str(stats["superseded"]),
             RECON_WIDTH),
    ]
    if trim_ids:
        out.append(line("rows with identifiers trimmed:", str(stats["trimmed"]),
                        RECON_WIDTH))
    out.append(line("orphan closes (no mark row):",
                    "%d of %d (%s%%)" % (orphans, closed_positions, orphan_pct),
                    RECON_WIDTH))
    if orphan_flag:
        out.append("orphan closes accepted by --allow-orphan-closes")
    # Soft band: not refused, but high enough to deserve a second look. The 20%
    # and 50% thresholds are judgement calls, not derived values; "about 4%" in
    # the message is the rate on our SYNTHETIC fixture, not an industry baseline.
    if closed_positions > 1 and orphans * 5 > closed_positions \
            and orphans * 2 <= closed_positions:
        out.append("CHECK THIS: orphan close rate is %s%%, against about 4%% on "
                   "the reference fixture. A rate this high usually means a "
                   "partial join failure. If this book genuinely holds little "
                   "overnight, that explains it." % orphan_pct)
    out.append(line("identifier spelling collisions:", str(stats["collisions"]),
                    RECON_WIDTH))
    out.append(line("unicode data version:", unicodedata.unidata_version,
                    RECON_WIDTH))
    if collision_flag:
        out.append("identifier collisions accepted by --allow-identifier-collisions")
    out += [
        "",
        line("PGR", pgr_text),
        line("PLR", plr_text),
        line("ratio (PGR/PLR)", ratio_text),
        line("t statistic", t_text),
        line("n gains  (RG+PG)", str(n_gains)),
        line("n losses (RL+PL)", str(n_losses)),
        "",
        line("realised gains   RG", str(rg)),
        line("paper gains      PG", str(pg)),
        line("realised losses  RL", str(rl)),
        line("paper losses     PL", str(pl)),
        line("zero-pnl rows excluded", str(s["zero"])),
    ]
    return "\n".join(out) + "\n"


# ==========================================================================
# SECTION 6 of 6: MAIN -- arguments, the safety checks, and the top-level handler
# ==========================================================================

def run(argv):
    parser = argparse.ArgumentParser(
        description="Odean (1998) disposition-effect statistics from a "
                    "five-column CSV. Prints aggregates to stdout only.")
    parser.add_argument("csv_path", help="path to the exported CSV")
    parser.add_argument(
        "--pnl-basis", required=True, choices=sorted(BASIS_LABELS),
        help="label only, echoed in the output header: 'price' = funding "
             "excluded, 'net' = funding included. Not used in the arithmetic.")
    parser.add_argument(
        "--trim-ids", action="store_true",
        help="strip leading/trailing whitespace from account_id and "
             "position_id instead of refusing the file; the number of rows "
             "changed is printed as 'identifiers trimmed'.")
    parser.add_argument(
        "--allow-orphan-closes", action="store_true",
        help="proceed even if more than half of the closed positions have no "
             "mark row at all (use only if this book really holds nothing "
             "overnight). The override is stated in the output.")
    parser.add_argument(
        "--allow-identifier-collisions", action="store_true",
        help="proceed even if some identifiers appear under more than one "
             "spelling that differs only in case, whitespace or Unicode form "
             "(normally a sign that the close rows and mark rows came from "
             "sources that spell ids differently). The override is stated in "
             "the output.")
    args = parser.parse_args(argv)

    pairs, stats = read_pairs(args.csv_path, args.trim_ids)
    summary = summarise(pairs)

    # Collision check: the same identifier spelled two ways (ABC / abc,
    # full-width / ASCII, composed / decomposed accents) silently splits one
    # account or position into two. No threshold: any collision is refused.
    if stats["collisions"] > 0 and not args.allow_identifier_collisions:
        raise ValidationError(
            "%d identifier(s) appear under more than one spelling that differ "
            "only in case, whitespace or Unicode form. This almost always "
            "means the close rows and the mark rows came from sources that "
            "spell identifiers differently. Re-export with identical spelling "
            "in both, or re-run with --allow-identifier-collisions."
            % stats["collisions"])

    # (The 50% refusal line below is a judgement call, as is the 20% soft band in
    # render(); neither is derived from data.)
    # Structural check: do the close rows and the mark rows refer to the same
    # positions? Orphan close = a (account_id, position_id) with a closed=1 row
    # and no surviving closed=0 row. Near 0% on a healthy export; ~100% if the
    # mark rows failed to join (different id spelling, case, hidden characters).
    closed_positions = stats["closed_positions"]
    orphans = stats["orphan_closes"]
    if closed_positions > 1 and orphans * 2 > closed_positions:
        if not args.allow_orphan_closes:
            raise ValidationError(
                "%d of %d closed positions have no mark row (closed=0) that was not "
                "superseded by a same-day close. No statistics are printed. Either (1) the mark rows did not "
                "join to the close rows: check that account_id and position_id "
                "are spelled identically in both tables; or (2) this book "
                "genuinely holds nothing overnight. If (2), re-run with "
                "--allow-orphan-closes." % (orphans, closed_positions))

    # Second, independent check on the same defect class: if there are several
    # qualifying days but not one paper position in the whole result, the mark
    # rows almost certainly did not join to the close rows (or this book holds
    # one position at a time). Same override flag as the orphan check.
    if (summary["PG"] + summary["PL"] == 0 and summary["days"] > 1
            and not args.allow_orphan_closes):
        raise ValidationError(
            "no paper positions (PG + PL = 0) were found on any of the %d "
            "qualifying days. No statistics are printed. Either (1) the mark "
            "rows did not join to the close rows: check that account_id and "
            "position_id are spelled identically in both tables; or (2) this "
            "book genuinely never holds a second position on a sale day. If "
            "(2), re-run with --allow-orphan-closes." % summary["days"])

    text = render(args.pnl_basis, summary, stats, args.trim_ids,
                  args.allow_orphan_closes, args.allow_identifier_collisions)
    text += age_lines(age_controlled(pairs, stats))
    sys.stdout.write(text)
    sys.stdout.flush()
    return 0


def main(argv=None):
    """Top-level handler: every failure becomes a short message with no
    traceback, so a crash can never echo a line of the input file."""
    try:
        return run(argv)
    except ValidationError as exc:
        sys.stderr.write("ERROR: %s\n" % exc)
        return 1
    except BrokenPipeError:
        # Why (for the reviewer): if the reader of our output closes the pipe
        # (for example `| head`), Python would print a second error at exit.
        # Setting stdout to None silences that; it hides no data problem.
        sys.stdout = None
        return 0
    except KeyboardInterrupt:
        sys.stderr.write("ERROR: interrupted\n")
        return 130
    except Exception as exc:
        # Why (for the reviewer): a crash must never show a traceback, because
        # a traceback can quote a line of your data. We print the exception's
        # class name only.
        sys.stderr.write(
            "ERROR: unexpected internal failure (%s). Details are withheld "
            "on purpose so that no input data can appear in the message.\n"
            % type(exc).__name__)
        return 3


if __name__ == "__main__":
    sys.exit(main())
