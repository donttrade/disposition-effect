# partner_disposition

Computes the disposition-effect statistics from Odean (1998) -- how much more
readily gains are realised than losses -- on a CSV that **you** export from
**your** systems and run **yourselves**. It prints aggregate numbers to the
terminal. Nothing leaves your machine.

Two scripts, standard library only, Python 3.8 or later (see "Python version and reproducibility" below), plus
the tests in `tests/` (standard library, synthetic data only):

- `partner_disposition.py` -- the analysis. Read it top to bottom; the AUDIT MAP at its head names every
  line that reads a file or writes output, so the review starts there.
- `make_fixture.py` -- writes a synthetic CSV with a planted effect, so you can
  see the tool work before pointing it at real data.

## The input: five columns, no more

| Column | Type | Meaning |
|---|---|---|
| `account_id` | string | Pseudonymous. Used only for grouping and duplicate detection. |
| `date` | `YYYY-MM-DD` | The day the position was closed, or the day it was marked. |
| `position_id` | string | Pseudonymous. Used only to detect duplicates. |
| `closed` | `0` or `1` | 1 = position was closed on this date. 0 = still open at end of day. |
| `pnl` | signed decimal | Realised PnL if `closed=1`; unrealised mark-to-market PnL at end of that day if `closed=0`. |

The header must contain exactly these names (any order). An extra column is an
**error**, not a warning: it may carry identifying data, so the script refuses
the file. The error says *how many* unexpected columns there were and names any
of our five columns that are missing; it never prints a cell of your header or
data.

**Trim your identifiers.** Leading or trailing whitespace on `account_id` or
`position_id` would make `A1` and `A1 ` two different accounts and quietly
wreck the result, so the script refuses such a file. Trim on export (the sketch
below does). If you cannot, run with `--trim-ids`; it strips instead and prints
how many rows it changed and how many distinct spellings of the account ids it
saw before trimming. It never strips invisible or control characters (see the
validation list); those are always refused.

### Identifiers: this script never needs to know what they mean

**This script never needs the identifier mapping to be reversible, and never
needs to know what an identifier means.** It uses `account_id` and `position_id`
only to group rows and to detect duplicates, and it never prints one. Any stable
string that is the same wherever the same account or position appears will do.

So: use whatever pseudonymous identifier you already have. If you need to create
one, do not use a plain unsalted hash; over a small identifier space that is
trivially reversible by anyone who can enumerate the space. Use an HMAC with a
secret key that your team holds and does not share, or a random surrogate key
from a table you keep to yourselves. Either way, produce it the same way for the
mark rows and the close rows so that they join.

### Sketch of the export query

Adapt to your schema. The point is one row per open position per day, plus one
row on the day a position is closed. (A mark and a close for the same position on
the same day are fine: the close wins and the mark is dropped and counted.)
`pseudonym(...)` stands for whatever produces your pseudonymous id, as above.

```sql
-- Daily end-of-day marks for positions still open
SELECT  TRIM(pseudonym(account_id))  AS account_id,  -- TRIM matters
        mark_date          AS date,
        TRIM(pseudonym(position_id)) AS position_id,
        0                  AS closed,
        unrealised_pnl     AS pnl
FROM    daily_position_marks
WHERE   mark_date BETWEEN :start AND :end
UNION ALL
-- The closing event, with realised PnL
SELECT  TRIM(pseudonym(account_id)), close_date, TRIM(pseudonym(position_id)), 1, realised_pnl
FROM    closed_positions
WHERE   close_date BETWEEN :start AND :end;
```

Use the same PnL basis in both halves, and make sure `account_id` is produced
identically in both (same pseudonym function, same trimming): if the two halves do not join,
the mark rows are discarded and the result is wrong. The script prints a
reconciliation block and an orphan-close check to help you catch that.

## Running it

```
python3 partner_disposition.py your_export.csv --pnl-basis price
```

`--pnl-basis` is required: `price` (funding excluded) or `net` (funding
included). It is **only echoed** in the output header so the result is labelled
correctly; it does not change any arithmetic. The export decides which one it is.
`--trim-ids` (optional) strips ordinary leading/trailing whitespace from the two
identifier columns instead of refusing the file; see above. `--allow-orphan-closes`
and `--allow-identifier-collisions` (both optional) are explained under "The
orphan-close check" and "The identifier-collision check". Errors raised after
trimming say `(after --trim-ids was applied)`, so a duplicate that looks
different in your file (for example `p1` and `p1 `) is understood.

Try it on fake data first:

```
python3 make_fixture.py --out fixture.csv --seed 7
python3 partner_disposition.py fixture.csv --pnl-basis price
```

Expected stdout, copied from a real run of exactly those two commands (on CPython 3.11.15; the `unicode data version` line depends on your Python and is explained under "Python version and reproducibility"). The block from `AGE-CONTROLLED FIGURES` down was added on 17 Oct 2026; everything above it is unchanged, line for line, from the earlier version:

```
pnl basis:            price (funding excluded)
accounts:             30
qualifying sale days: 256

data rows parsed:                   14400
blank records skipped:              0
rows in qualifying pairs:           2048
rows discarded (no close that day): 12352
same-day marks superseded by close: 0
orphan closes (no mark row):        14 of 335 (4.2%)
identifier spelling collisions:     0
unicode data version:               14.0.0

PGR                   0.2178
PLR                   0.1119
ratio (PGR/PLR)       1.9470
t statistic           6.51
n gains  (RG+PG)      1001
n losses (RL+PL)      1046

realised gains   RG   218
paper gains      PG   783
realised losses  RL   117
paper losses     PL   929
zero-pnl rows excluded 1
AGE-CONTROLLED FIGURES (holding age = calendar days since the
position's first row in this file)
positions with a known open date:               329
positions open on the first date (left out):    240
rows used (qualifying pairs, pnl not 0):        975

ratio, ages pooled, same rows:                  2.0325
within-age ratio (Mantel-Haenszel):             1.9273
                                                95% interval 1.3825 to 2.6867, by account

holding age      gain rows  loss rows     PGR     PLR   ratio  within-age
<=1 day                 43         32  0.2093  0.0938   2.233       2.232
2-5 days                73         75  0.2055  0.1333   1.541       1.618
6-20 days              192        224  0.2240  0.0804   2.787       2.595
21-60 days             168        168  0.1667  0.1071   1.556       1.441
61-250 days              0          0       -       -       -           -
251+ days                0          0       -       -       -           -

fixed effects (account + holding day), linear probability model:
  gain coefficient:                             0.103986
  standard error (account and date):            0.021478
  ratio implied for gain rows (ATT):            2.0878
                                                95% interval 1.4495 to 3.7307

gain timing (rows that have a previous row for the same position):
  rows:                                         933
  ratio, ages pooled: same day / previous row:  2.0604 / 1.8627
  within-age ratio: same day / previous row:    1.9488 / 1.7481
  fixed-effects ATT: same day / previous row:   2.0993 / 1.8586
  sign changed since previous row, sold rows:   10 of 138
  sign changed since previous row, unsold rows: 60 of 795


HOW TO READ THE AGE-CONTROLLED FIGURES
... (a fixed block of plain-language caveats, printed every time; see below)
```

(`make_fixture.py` itself also prints one line, `wrote 14400 synthetic rows to
fixture.csv (seed 7)`. The same seed always gives a byte-identical file.)

## Age-controlled figures (added 17 Oct 2026)

**Why.** Positions are sold less often the longer they are held. If losing positions are on average older than
winning ones, a PLR pooled over all holding ages is pulled down by age rather than by any reluctance to sell, and
the pooled ratio overstates the effect. On synthetic data with **no** preference for selling winners, only that age
pattern (`tests/calibrate.py`, 40 files), the pooled ratio on the rows below was above 1.25 in **40 of 40** files
(median 1.42). Our public study found the same mechanism in real data: holding age fixed, its pooled ratio fell from
1.45 to 1.33 (robustness update on the disposition-effect study page, 17 Oct 2026). So the output now adds the same
comparison made between positions of the **same holding age**. The pooled figures above it are unchanged.

**Holding age comes from the same five columns; nothing is added to the input.** A position's open date is the
date of its first row in the file (its first mark, or its close if it was opened and closed the same day). Its age
on a row is the number of calendar days since then. One case cannot be dated: a position whose first row is on the
**first date in the file** may have been opened before the export began. Those positions are left out of the
age-controlled figures and counted on the line `positions open on the first date (left out)`; the pooled figures
still use them. If that count is large, starting the export earlier dates more positions, but it also changes the
period the pooled figure covers, so agree it with us first.

**Rows used.** Exactly the rows behind the pooled figure (Odean's days with a sale; pnl = 0 excluded; a same-day
mark and close count once, as the close), minus the undated positions. `ratio, ages pooled, same rows` is the plain
pooled ratio on those rows, so the effect of holding age is seen like for like.

| Line | What it is |
|---|---|
| `within-age ratio (Mantel-Haenszel)` | PGR/PLR with one stratum per exact holding day: sum over days k of a_k n0_k / N_k, divided by the sum of c_k n1_k / N_k (a = sold gains, c = sold losses, n1 / n0 = gain / loss rows, N = n1 + n0). **Use this, not the pooled ratio, for the size of the effect.** |
| `95% interval ..., by account` | Clustered by account (each account's share of the numerator and denominator; stratum sizes held fixed). On the 40 synthetic no-effect files it excluded 1 in 0 of 40. `NOT MEASURED` with a single account. |
| holding-age table | Six buckets (<=1, 2-5, 6-20, 21-60, 61-250, 251+ days): rows, PGR, PLR, plain ratio, and the within-bucket ratio (again one stratum per exact day: six wide buckets alone are not enough, because inside a bucket the sale rate still falls with age). `-` means not measurable. |
| fixed effects | A linear probability model: sold = beta x gain + one effect per account + one effect per exact holding day; standard error clustered by account and by date (Cameron-Gelbach-Miller). `ratio implied for gain rows (ATT)` = sale rate of gain rows / (that rate - beta). It compares each account with itself at the same holding day, so it is a different average from the pooled ratio. On the 40 no-effect files its interval excluded 1 in 3. |
| gain timing | On rows that have a previous row for the same position: the ratios with the gain/loss sign from the same day and from the previous row, and how often the sign changed since the previous row on sold and unsold rows. A gain or loss on the sale day may partly reflect the sale itself (the fill, the closing mark); if the previous-row figures are much smaller, the result depends on that timing. A higher change rate on sold rows is not proof of that: on synthetic data with no look-ahead at all it also appears, because a position that has just turned into a gain is then sold at the gain rate. |

**What none of these figures can rule out.** Traders may sell large moves in either direction more often (a
V-shaped selling pattern; Ben-David and Hirshleifer 2012), which also produces PGR > PLR without any preference for
gains. Separating the two needs the size of each gain or loss relative to the position, which these five columns do
not carry (pnl is an amount, not a return). The output says so every time.

**How the fixed effects are computed without numpy.** By the Frisch-Waugh theorem the gain coefficient depends on
gain and sold only through their fitted account + holding-day effects, and those fits depend only on the totals of
each (account, holding day) cell. So the projection (alternating projections to a tolerance of 1e-10) runs on
cells, not rows, and the clustered standard error needs one more pass over the rows. If the projection does not
converge, the lines say `NOT MEASURED`.

**Cost.** Measured on Linux, CPython 3.11, a 2-core machine with another job running (so slower than an idle one):

| File (synthetic) | Rows | Earlier version | This version |
|---|---|---|---|
| positions repeat across days | 569,907 | 5.7 s, 240 MB | 8.8 s, 264 MB |
| every row a different position | 500,000 | 7.1 s, 470 MB | 10.4 s, 553 MB |
| positions repeat across days | 2,318,010 | 27.8 s, 926 MB | 42.6 s, 1,020 MB |
| every row a different position | 2,000,000 | 25.2 s, 1,509 MB | 41.2 s, 1,835 MB |

**Tests.** `tests/test_partner_age.py` (standard library, synthetic data only): a hand-built file whose every
age-controlled number is worked out by hand in the comments; an independent re-implementation (plain dicts and a
dense least-squares solve) on a random file; five duration-only no-effect files (the pooled ratio shows an effect,
the within-age and fixed-effects intervals do not); five planted-effect files (both detect it); the earlier
version's output is an exact prefix of this one's on the fixture and on error messages; static checks of the
claims below; and a run under a real Python 3.9. `tests/mutate.py` reverts each part of the change in a copy and
shows the suite fails each time.

## What it computes

Only (account, date) pairs on which that account **closed at least one
position** are counted (Odean's rule; it keeps dormant accounts, which would add
paper positions but no sales, out of both ratios). Every row of any other pair
is discarded. Within the counted pairs each row falls in exactly one bucket:

| Bucket | Rule |
|---|---|
| RG realised gain | `closed=1`, `pnl > 0` |
| RL realised loss | `closed=1`, `pnl < 0` |
| PG paper gain | `closed=0`, `pnl > 0` |
| PL paper loss | `closed=0`, `pnl < 0` |

`pnl = 0` rows are in none of the four and are reported as "zero-pnl rows
excluded". Then `PGR = RG/(RG+PG)`, `PLR = RL/(RL+PL)`, ratio = PGR/PLR, and
`t = (PGR-PLR) / sqrt(PGR(1-PGR)/(RG+PG) + PLR(1-PLR)/(RL+PL))`. Counts are
pooled across all accounts and days, not averaged per account.

If a denominator is zero the line prints `NOT MEASURED` and says why; the
script never prints a made-up 0. Signs are decided on the exact decimal text
(a value like `1e-400` is a gain, not zero). Displayed numbers are rounded
half-up, as a spreadsheet does, so you can reproduce a digit in Excel.

### The reconciliation block

Printed above the headline numbers so that rows cannot vanish unnoticed:

| Line | Meaning |
|---|---|
| `data rows parsed` | data rows that passed validation (not the file's line count) |
| `blank records skipped` | wholly empty lines, which are ignored; always shown, even when 0 |
| `rows in qualifying pairs` | rows on (account, date) pairs with at least one close; equals RG+RL+PG+PL+zero-pnl |
| `rows discarded (no close that day)` | rows on pairs with no close |
| `same-day marks superseded by close` | marks (`closed=0`) dropped because the same account, date and position also has a close (`closed=1`); see below |
| `rows with identifiers trimmed` | only with `--trim-ids`: rows where an identifier was changed |
| `orphan closes (no mark row)` | closed positions that have no `closed=0` row that was not superseded by a same-day close, as a count and percentage (see below) |
| `CHECK THIS: orphan close rate is ...` | only when the orphan rate is above 20% and at most 50%: a canary for a partial join failure (see below) |
| `identifier spelling collisions` | how many identifiers appear under more than one spelling (see below); always shown |
| `unicode data version` | the Unicode database version of the Python that ran the script; see "Python version and reproducibility" |
| `orphan closes accepted by --allow-orphan-closes` | shown whenever you passed that flag, needed or not |
| `identifier collisions accepted by --allow-identifier-collisions` | shown whenever you passed that flag, needed or not |

The first lines reconcile: data rows parsed = rows in qualifying pairs + rows
discarded + same-day marks superseded.

Every override flag you use is stated in the output, so the method that
produced a number is recorded with the number.

With `--trim-ids` the header block also shows `distinct account_ids before
trimming`: the number of different raw spellings of the accounts that qualified.
If that is larger than `accounts`, trimming merged accounts together.

### A mark and a close on the same day

If one `closed=1` row and one `closed=0` row share the same
(account, date, position), the position was marked during the day and closed at
the end of it. That is an ordinary export shape, not a duplicate. The close is
kept and the mark discarded: on the day it is sold, a position is a realisation,
not a paper position. The discarded marks are counted on the line
`same-day marks superseded by close`. Two rows with the same key and the *same*
`closed` value (or three rows with one key) are a real duplicate and abort the run.

### The orphan-close check (do the closes and the marks join?)

An *orphan close* is a position (`account_id` + `position_id`) that has a
`closed=1` row but no `closed=0` row that **was not superseded by a same-day
close**. (A
mark that shares its day with the close is dropped, see above, and does not
count: it is no evidence the position was ever held as a paper position.) On a healthy
marks-plus-closes export the rate is low: only positions opened and closed on
the same day are orphans (the fixture shows 14 of 335, 4.2%). If the mark rows
failed to join to the close rows (different spelling, letter case, hidden
characters), nearly every close is an orphan.

If more than half of the closed positions are orphans, and there is more than
one closed position, the script **refuses**: no statistics are printed, the exit
code is non-zero, and the message names two causes: the join is broken, or the
book genuinely holds nothing overnight. If it is the second, re-run with
`--allow-orphan-closes`; the output then carries the line
`orphan closes accepted by --allow-orphan-closes`.

A second, independent check guards the same defect: if more than one (account,
date) pair qualified but the result contains **no paper positions at all**
(PG + PL = 0), the script also refuses, with the same two possible causes and the
same override flag `--allow-orphan-closes`. The second cause there is a book that
never holds a second position on a day it sells, which is legitimate but rare.

Between 20% and 50% the run proceeds but prints a `CHECK THIS` line, since a
healthy export sits near 4% on our fixture and a rate that high usually means a
partial join failure. **The 20% and 50% thresholds are judgement calls, not
derived values.** **The "about 4%" is the rate on our synthetic fixture, not an
industry baseline**; a real book's normal rate is unknown to us and depends on
how much it trades within a day. Treat it as a canary, not a defence: the defence against
spelling mismatches is the collision check below. If your book genuinely holds
little overnight, a high rate is explained and you can ignore the line.

### The identifier-collision check

If the close rows and the mark rows spell the same identifier differently, one
account or position is silently split in two and the result is wrong. The most
common causes are letter case (`ABC` vs `abc`), padding, full-width characters
and composed versus decomposed accents. The script builds a comparison key for
every distinct `account_id` and every distinct `position_id` (Unicode NFKC
normalisation, surrounding whitespace removed, case folded). **Account ids are
compared across the whole file; position ids are compared only within one
account**, because a position id only has to be unique inside its account:
`acctA/P1` and `acctB/p1` are two different positions and do not collide, while
`P1` and `p1` under the same account do. If two *different*
spellings share a key, it **refuses**: exit non-zero, no statistics, and a count
of how many identifiers collide (never a spelling). There is no threshold: any
collision is refused. Fix the export so both sources spell ids identically, or,
if you are sure the collision is harmless, re-run with
`--allow-identifier-collisions`; the output then says so.

Two genuinely different identifiers such as `acct_a` and `acct_b` do not
collide. Note that the whitespace and invisible-character refusals above fire
first where they apply.

## Validation: it stops rather than guess

Each of these aborts with a message naming the **row number** (header = row 1,
first data row = row 2) and the problem, never the cell contents, and exits
non-zero before printing any statistics:

- header is not exactly the five columns (extra, missing or repeated); only the
  count of unexpected columns and the names of *our* missing columns are shown
- a row with the wrong number of fields (an unbalanced quote is a likely cause)
- `account_id` or `position_id` with leading or trailing whitespace (unless
  `--trim-ids`)
- `account_id` or `position_id` containing an invisible or control character
  (Unicode category Cf or Cc, such as a zero-width space or a tab, or any
  non-ASCII whitespace such as a non-breaking space). Always refused, even with
  `--trim-ids`: such characters make identical-looking ids different and cannot
  be seen in a spreadsheet. Export plain text identifiers.
- a row that is blank apart from whitespace
- more than half of the closed positions have no surviving mark row (orphan
  closes; see above), or several qualifying days with no paper positions at all
  (PG + PL = 0), unless `--allow-orphan-closes`
- identifiers that collide after case folding, trimming and Unicode normalisation
  (accounts across the file, positions within an account; see above), unless
  `--allow-identifier-collisions`
- a NUL byte anywhere in the raw text, checked before CSV parsing, so the answer
  is the same on every Python version
- `closed` is not exactly `0` or `1`
- `pnl` is not a plain finite decimal (NaN, inf, overflow all rejected)
- `date` is not a real `YYYY-MM-DD` calendar date
- `account_id` or `position_id` empty or blank
- duplicate `(account_id, date, position_id)`: two rows with the same key and the same `closed` value (one `closed=1` plus one `closed=0` is merged, not an error; see above)
- the same `(account_id, position_id)` closed on two different dates
- a position marked open (`closed=0`) on a date after the date it was closed
- file empty; header but no data rows; no (account, date) pair with a close
- file not valid UTF-8, or not parseable as CSV

Wholly empty lines (for example a trailing blank line) are not an error: they
are skipped, counted under `blank records skipped` in the reconciliation block,
and still take a row number.

## Privacy claims you can check yourselves

**Fast path:** `partner_disposition.py` opens with an AUDIT MAP that names, with
line numbers, the complete import list, the single `open()` and its mode, every
place anything is written to stdout or stderr, the one place error messages are
printed, and the catch-all handler. Reading that block and spot-checking the
lines it names verifies every claim below in a few minutes. The rest of the file
is input validation, tallying and arithmetic.

Each claim is also an assertion you can verify in under a minute.

1. **No network code.** This returns nothing:
   `grep -n 'socket\|urllib\|http\|requests\|ssl\|ftplib\|smtplib\|subprocess\|os.system' partner_disposition.py`
2. **Standard library only.** The imports are exactly:
   `grep -n '^import\|^from' partner_disposition.py` returns ten lines: `from __future__ import annotations` (a compiler directive, not a module), the eight modules `argparse, csv, datetime, decimal, math, re, sys, unicodedata`, and `from decimal import Decimal`.
3. **Writes no files.** The only `open(...)` is the read-only open of the input
   CSV: `grep -n 'open(' partner_disposition.py` shows one line, mode `"r"`.
   Output goes to stdout (statistics) and stderr (errors) only. You can also run
   it in a directory it cannot write to, or under a read-only sandbox.
4. **Never prints an identifier.** `account_id` and `position_id` are used only as
   dictionary keys. Every error string is written by the script and contains a
   row number and a description, not a cell. Check:
   `grep -n 'ValidationError(' partner_disposition.py` and read each message.
   No header or data cell is ever printed, not even a truncated one. The only
   words from the schema that can appear are our own five column names.
5. **No traceback can echo your data.** `main()` catches every exception and
   prints only the exception class name. Re-run with a deliberately broken file
   to see it.
6. **Output is aggregate only:** counts and statistics, as shown above. Nothing is per account. The
   age-controlled block adds counts per holding-age bucket, still pooled over all accounts.
7. **Fixture is fake.** `make_fixture.py` makes random labels from a seeded
   generator; it reads no input files.

You can also run it with the network disabled (for example
`unshare -n python3 partner_disposition.py ...` on Linux); it behaves identically.

## Limitation: the t statistic assumes independent observations

The t statistic above treats every position-day as an independent observation.
It is not. The same position appears on many days, and one account's positions
move together and share one decision-maker. Positive dependence of that kind
makes the **standard error too small and the t statistic too large**. Read the
t statistic as an optimistic upper bound on significance; the PGR, PLR and ratio
are unaffected, because they are plain pooled proportions. A significance claim
that must withstand scrutiny needs a method that accounts for this clustering
(for example, standard errors clustered by account). This tool does not do that.

The age-controlled block (above) does give intervals that allow for this: the within-age ratio's is clustered by
account, the fixed-effects one by account and date. The t statistic itself is unchanged, so that the earlier output
stays identical.

## Memory and size

The whole file is validated before anything is printed, which means the script
keeps several entries per row in memory (duplicate detection and the collision
check need them). Measured by our tester on Linux with CPython 3.11, on a
worst-case file (every row a different position), for the version before 17 Oct 2026: **311 MB and 4.9 seconds at
500,000 rows; 1,206 MB and 24.8 seconds at 2,000,000 rows**, roughly 640 bytes
per row, linear. The age-controlled figures add one small integer per row and a few passes over the data; see
the Cost table under "Age-controlled figures" for measurements of both versions on the same machine. These will vary with your machine, Python version and the shape
of your file (a file where positions repeat across days is cheaper). Above a few
million rows, split the export by date range and run each piece separately. Do
not split an (account, date) pair or a position across files, or the duplicate,
orphan and conditioning checks will not see all of its rows.

## Python version and reproducibility

The script runs on Python 3.8 or later. One thing differs between versions: the
identifier-collision check normalises Unicode (NFKC and case folding), and the
Unicode database built into Python changed between releases. Our tester found
nine code points and 175 normalisations that differ between Python 3.8 and
3.13, with the boundary at 3.10/3.11; the older Python is the more permissive.
The exposure is narrow (only unusual characters in identifiers), but so that a
published number can be reproduced, the output prints `unicode data version`,
the version your Python used. Everything else in the output is identical across
Python versions. If you publish a result, publish that line with it.

The version of 17 Oct 2026 was run on the fixture under CPython 3.8.20, 3.9.23, 3.10.20, 3.11.15, 3.12.3 and
3.13.13: the output was identical apart from that line. Its test suite passes under 3.9.23 and 3.11.15.

## Licence

From version 2, this folder is licensed under **PolyForm Noncommercial 1.0.0**: free for traders, researchers, schools, charities, journalists and government; a business using it for its business needs a commercial licence, which comes with the firm plan and the Pilot. `partner-v1` (commit `2ff165c`) was released under MIT and stays MIT. Organisations may evaluate any version on synthetic or test data for 32 days. Full terms: [LICENSING.md](LICENSING.md).
