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
"""

# ==========================================================================
# SECTION 1 of 6: AUDIT MAP -- read this, then spot-check the lines it names.
# The question it answers: can this program send your data anywhere, or print it?
#
#   Imports, complete list ...... lines 71-79. No network module, no os,
#                                 no process launcher. (grep the file to confirm.)
#   The only file opened ........ line 316, mode "r" (read-only). Nothing is written.
#   Everything sent to stdout ... line 711 (the results text) and line 714
#                                 (flush); line 730 only assigns None to stdout
#                                 after a broken pipe, it is not output. These
#                                 are the only three lines a text search for the
#                                 module-qualified stdout name finds. argparse prints
#                                 usage/--help text only. The built-in print
#                                 function is never used.
#   Everything sent to stderr ... lines 724, 733, 739, all inside main().
#   Error messages .............. built only at the ValidationError(...) sites
#                                 (grep -n 'ValidationError(' lists them all) and
#                                 printed only by main(), line 724. They cannot
#                                 contain a cell: each is a fixed sentence into
#                                 which only a row number, a count, our own column
#                                 names or the OS's reason text is substituted.
#   The catch-all ............... line 735, "except Exception". It prints the
#                                 exception's CLASS NAME only, never its text.
#   Input validation ............ lines 124-252. Everything between them is
#                                 input validation; it reads no new state and
#                                 writes no output (each function takes one row's
#                                 strings and returns a value or raises).
# ==========================================================================

# ==========================================================================
# SECTION 2 of 6: IMPORTS AND CONSTANTS
# ==========================================================================
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
             "orphan_closes": orphan_closes}
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

    sys.stdout.write(render(args.pnl_basis, summary, stats, args.trim_ids,
                            args.allow_orphan_closes,
                            args.allow_identifier_collisions))
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
