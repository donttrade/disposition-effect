# How to export the CSV — read this before you run anything

The script needs **two kinds of row**, and the most natural export — a list of closed trades — will
be **refused** by it. That refusal is deliberate, and this page exists so you do not hit it.

## The one thing that goes wrong

A trading journal's obvious export is "every position that was closed." If you send only those, the
script stops with:

> `ERROR: N of N closed positions have no mark row (closed=0) that was not superseded by a same-day
> close. No statistics are printed.`

Nothing is broken. The measurement is a comparison between **positions you closed** and **positions
you were holding at the same moment and did not close**. With only closed positions there is no
comparison to make, and the script refuses rather than printing a meaningless ratio. Odean's measure
is defined on that contrast; without it there is no result, only a number.

So: **one row per position per day it existed**, not one row per closed trade.

## The five columns

| Column | What it is |
|---|---|
| `account_id` | A pseudonymous id for the trader. Use whatever you already have. The script never prints it, and never needs the mapping to be reversible. |
| `date` | `YYYY-MM-DD`. The day this row describes. |
| `position_id` | A pseudonymous id for one position's whole life, from open to close. Only has to be unique within an account. |
| `closed` | `1` if the position was closed on this date, `0` if it was still open at end of day. |
| `pnl` | Signed. **Realised** PnL if `closed=1`; **unrealised** mark-to-market PnL at end of that day if `closed=0`. |

No symbol, no size, no price, no side, no timestamp. None of it is needed.

## Perps: direction is already handled

A short that profited is simply a **positive** `pnl`. Because you send signed PnL rather than entry
and exit prices, the script never needs to know the side, and there is no long/short logic in it at
all. This is why the schema is five columns instead of fifteen.

## One position, as rows

A position opened Monday, held through Tuesday, closed Wednesday at a $240 profit:

```
account_id,date,position_id,closed,pnl
a7f3,2026-03-02,p91,0,110.50
a7f3,2026-03-03,p91,0,-40.25
a7f3,2026-03-04,p91,1,240.00
```

The first two rows are the unrealised mark at each end of day. The last is the realisation. If you
also emit a `closed=0` mark on the closing day, that is fine — the script keeps the close and
discards the mark, and tells you how many it did that to.

## Funding

Perps accrue funding, so `pnl` can reasonably mean price PnL or net of funding. **Either is fine,
but tell the script which** with `--pnl-basis price` or `--pnl-basis net`. It does not use the value
in any arithmetic — it echoes it into the output so the published method names it correctly. Guessing
later would be a methodology error, which is why it is a required flag.

## Scope

Any window with enough closed positions works; a year is more than enough. You can also restrict it
to one exchange or one product if that is easier — just say which, so the write-up describes the
population accurately.

## Then

```bash
python3 partner_disposition.py your_export.csv --pnl-basis price
```

It prints six headline figures, the four raw counts behind them, a reconciliation block showing how
many rows were read, used and discarded, and (since 17 Oct 2026) an age-controlled block: the same
comparison made between positions of the same holding age, with a short note on how to read it. Every
line is a population aggregate.

**Holding age needs no extra column.** The script dates each position from its first row in your file.
Positions already open on the first date of your export cannot be dated and are left out of the
age-controlled figures (they still count in the headline figures). So a mark row on every day a position
was held matters even more now: a missing day in the middle is harmless, but if a position's early days
are missing, its age is understated. Send back whatever it prints — including any `CHECK THIS` or `WARNING` line, which tells
us something about the export rather than about your traders.

Run it on `make_fixture.py`'s synthetic output first if you want to see the shape before pointing it
at anything real.

On the monthly plan, run it once a month on that month's extract; the `accounts:` line it prints is the
billed count (trader accounts that month).

## If it refuses

Every refusal names the row number and the problem, and never prints the contents of a cell. The
three most likely:

- **orphan closes** — the export is closes-only. See the top of this page.
- **identifier spelling collisions** — the same account or position is spelled two ways, usually
  because the closes and the marks came from different queries. Re-export with identical spelling.
- **leading or trailing whitespace** — a `CHAR(n)` column somewhere. Re-run with `--trim-ids`, or
  `TRIM()` it on export.
