# Insider clusters on SEC Form 4 bulk data, 2006-2026

A measurement of whether clustered insider buying still predicts returns. **In the names you could
actually trade, the early era's result is 2008 and 2009 and nothing else** — and the honest version of
that sentence is narrower than it sounds. See "What is wrong with this" below.

Independent of the disposition-effect replication in the repository root. Different data, different
question, different code.

## Two price screens, and why

The "tradable" screen here has a price floor. Until 2026-10-08 that floor was applied to Yahoo's
**split-adjusted** close, which is not a price anyone could have traded: Netflix's 2006 insider buys —
on $30M a day of real volume — were recorded at **$0.29** and failed a $5 screen they cleared by two
orders of magnitude at the time. `auto_adjust=False` does not fix this; it only disables the dividend
adjustment, and Yahoo publishes no raw close.

The screen now uses `TRANS_PRICEPERSHARE` from the filing itself — the price the insider **reported
paying**, on the transaction date, unadjusted. ("Reported paying", not "paid": see the filing-errors
item below.) **Both screens are computed and both are reported**, because the old one produced every
figure published before that date. The dollar-volume half of the screen was never affected: the split
adjustment cancels in price x volume, up to a residual dividend-only deflation that is NOT MEASURED.

The error was **era-asymmetric**, which is why it mattered for a comparison between eras. Among events
clearing the $1M liquidity floor — the only ones the price screen actually decides:

| | wrongly admitted (`px>=5`, real price < 5) | wrongly rejected (`px<5`, real price >= 5) |
|---|---|---|
| 2006-2016 | 120 | **252** |
| 2017-2026 | **243** | 137 |

Forward splits deflate old adjusted prices; reverse splits inflate recent penny-stock ones (ATRA
2023-11-15: adjusted $12.03, real price $0.24). The bias flips sign across the two eras being compared.

**No upper price bound is applied.** An earlier draft excluded events with a reported price above
$10,000 as data errors. That was wrong: of the 65 such events, 20 clear the liquidity floor and every
one is a real issuer, including Assured Guaranty's April 2008, May 2008 and June 2009 clusters (twelve
and thirteen reporting owners each, on $14-25M a day). The error is in the price field, not in the
event, so filtering on the field deletes real clusters. The errors are disclosed instead — see below.

## The result

21-day market-adjusted return (benchmark SPY over the identical window), clusters of two or more
distinct SEC reporting owners buying the same stock in the same filing week, with at least $100,000 of
combined notional. **Medians are given because the gap between mean and median is most of the finding.**

| cut | N | mean | median | t |
|---|---|---|---|---|
| All clusters | 17,018 | +1.07% | **-0.76%** | 2.89 |
| 2006-2016 | 7,261 | +1.91% | **-0.21%** | 7.03 |
| 2017-2026 Q1 | 9,757 | +0.44% | **-1.27%** | 0.72 |

**The median cluster loses money in both eras**, including the one with a t of 7.03. Every positive
figure here is a mean dragged up by a thin tail of large winners.

Tradable, **as-traded screen** (Form 4 price >= $5, 20d median $vol >= $1M):

| cut | N | mean | median | t |
|---|---|---|---|---|
| 2006-2016 | 2,958 | +0.66% | +0.06% | 3.01 |
| **2017-2026 Q1** | 5,171 | **-0.20%** | -0.86% | -0.86 |
| >=3 insiders, 2006-2016 | 1,524 | +0.89% | +0.25% | 2.70 |
| **>=3 insiders, 2017-2026 Q1** | 2,715 | **-0.42%** | **-1.16%** | -1.33 |
| >=4 insiders, 2006-2016 / 2017-2026 | 1,028 / 1,651 | +0.90% / -0.29% | | 2.13 / -0.69 |
| >=5 insiders, 2006-2016 / 2017-2026 | 727 / 1,132 | +1.54% / -0.64% | | 3.21 / -1.18 |

The same cuts on the **old published screen** (adjusted close >= $5), for comparison: tradable
2006-2016 +0.59% (t 2.51, N 2,826); tradable 2017-2026 **-0.30%** (t -1.29, N 5,277); >=3 insiders
2006-2016 +0.99% (t 2.69, N 1,460); >=3 insiders 2017-2026 **-0.58%** (t -1.78, N 2,810). The 2,649
post-2017 events both screens admit give **-0.476% (t -1.48)**.

### The crisis result

Tradable, as-traded, at both insider thresholds, with 95% intervals:

| window | >=2 insiders | >=3 insiders |
|---|---|---|
| 2006-2016 | +0.66% (t 3.01), N 2,958 | +0.89% (t 2.70), N 1,524 |
| excluding 2008-09 | **+0.18%** (t 0.80), median **-0.14%**, [-0.26, +0.62] | **+0.06%** (t 0.18), median **-0.16%**, N 1,178 |
| excluding 2008-09-10 | +0.15% (t 0.62) | +0.02% (t 0.05), N 1,073 |
| 2010-2016 only | +0.15% (t 0.58) | +0.14% (t 0.35), N 946 |
| 2006-2007 only | +0.33% (t 0.73) | **-0.25%** (t -0.38), N 232 |

By year, tradable >=3: **2008 +3.17% (t 4.04, N 278)** and **2009 +5.80% (N 68)**. **2008-09 supplies
94% of the tradable, three-or-more-insider early era's excess-return sum** — 31% of the unscreened
early era's. 2009 is 68 events with a 95% interval of
[+0.94, +10.67] and should not carry weight alone; the claim rests on 2008.

**Medians by year, where they diverge from the mean.** 2008 is +1.93% against its +3.17% mean and 2009
+2.63% against +5.80% — the crisis years are the two where the typical trade moved with the average.
2017, the best post-2017 year, is **+0.13% against a +2.47% mean**: carried almost entirely by a tail.
The widest gap in the table is 2013 — **+2.24% on the mean against -1.88% on the median**, on 69
events.

**This is a failure to detect, not a proof of zero.** The ex-crisis interval is [-0.26%, +0.62%] over
21 days. Jeng-Metrick-Zeckhauser's 50 bp a month sits inside it; Cohen-Malloy-Pomorski's 82 bp sits
just outside, so an effect that size is about the smallest thing this window could have ruled out.

### The argument against the conclusion

| pool, tradable >=3 | N | mean | t |
|---|---|---|---|
| 2017-2020 | 1,073 | +0.55% | +1.03 |
| 2021-2024 | 1,203 | **-2.09%** | **-4.79** |
| 2025-2026 Q1 | 439 | **+1.77%** | **+2.05** |
| **2017-2026 excluding 2021-24** | **1,512** | **+0.90%** | **+2.00** |

Set that last row against the early era with *its* exceptional years removed — **+0.06% (t 0.18,
N 1,178)** — and on means the era called dead is the stronger of the two. **On medians the comparison
reverses against both: -0.16% early against -0.38% late.** Neither residue has a positive median, so
neither exclusion produces anything tradable.

The rebuttal to the +0.90% is that nothing tells you the regime in advance. That is true, and it is
weaker than it looks, because the two exclusions are not the same kind of thing: 2008-09 is a named
macro event whose dates were fixed by history before anyone looked at this data, while 2021-24 is four
consecutive years selected because of their returns — there, the boundaries *are* the data. So the
symmetry is not perfect and it would be wrong to claim it is. What survives is narrower: this sample
holds one fifteen-month episode supplying the entire positive mean and four years supplying the entire
negative one, on an annual-mean standard deviation of 2.05 percentage points. That describes variance,
not an effect.

**Robustness.** **21.9%** of the 17,018 analysed events are a single jointly-filed Form 4 rather than
several independent decisions — 28.6% of the tradable universe at three or more insiders, **30.4%** of the events behind the
headline figure. Requiring two or more *separate filings* gives tradable 2017-2026 of **-0.30%
(t -1.33, N 4,048)** against -0.20% on owners (and 2006-2016 of +0.71%, t 3.11, N 2,442); `events.csv.gz` carries `n_acc` so both can be computed. The
contamination is era-asymmetric: 19.8% pre-2017 against 23.5% after.

**Win rate**, 21d, tradable >=3: **51.0%** in 2006-2016, **45.7%** in 2017-2026, 47.6% all eras.

**The 63-day horizon is not claimed in either direction.** On the old screen it was -0.41% (t -0.71);
on the as-traded screen **+0.93% (t 1.45)** — the opposite sign. The 2,649 events both screens agree
about give **+0.13% (t 0.22)**, and the whole difference comes from swapping out 161 events averaging
-9.21% and swapping in 66 averaging **+32.96%**, 26 of which fall between 15 February and 15 April
2020. Excluding that window both screens are significantly negative (-2.05% and -1.51%). The 63-day
median for 2017-2026 is **-2.13%** against that +0.93% mean. At the early end the common core is
+1.12% (t 1.88), also not significant. Any earlier version of this file claiming "the 63-day horizon
agrees with the 21-day" was wrong.

## Run order

```
pip install -r ../requirements.txt
export SEC_UA="your-project-name you@example.com"   # required, see below
python3 form4/build.py      # downloads 81 quarterly SEC files -> f4/purchases.csv.gz
python3 form4/clusters.py   # weekly clusters                  -> f4/clusters.csv.gz
python3 form4/rets.py       # forward returns                  -> f4/events.csv.gz
python3 form4/merge_px.py   # joins the as-traded price        -> f4/events_px.csv.gz
python3 form4/an.py         # the tables below, both screens
```

Run from the repository root, not from `form4/`. All five scripts read and write `f4/` relative to the
root. `an.py` uses `events_px.csv.gz` when it exists and falls back to `events.csv.gz` with a printed
warning, in which case the as-traded screen is reported as NOT MEASURED.

`events.csv.gz` is never overwritten by `merge_px.py`. It is the provenance of every figure published
before the screen was corrected, and it stays on disk so the two can be compared.

**What `an.py` prints, and what it does not.** It prints both price screens at insider thresholds
n in {2,3,4,5}, horizons {21,63} and tradable thresholds n in {3,4}, the year table, win rates and the
dollar-volume quartiles — though the year table it prints carries no median column. It does **not**
compute the cut-point sweep, the regime pools, the contiguous-window enumeration, the crisis windows
beyond `ex 2008-09`, the common-core decomposition, the non-tradable complement or the notional
sensitivity. Those are
computed on top of `f4/events_px.csv.gz`, **which is gitignored and not in this repository** — it is
built from 923MB of SEC archives by the four commands above. There is no one-click reproduction and it
would be dishonest to imply one.

### SEC_UA is not optional

The SEC refuses automated requests that do not declare a contact it can reach. An absent User-Agent
returns **403**, and so does one carrying only a URL — both were verified directly. `build.py` exits
with instructions if `SEC_UA` is unset or has no `@` in it. The contact is read from the environment,
so running this does not require editing any file in the repository.

`build.py` paces its downloads at one request per second. Without pacing, 81 back-to-back requests
earn *"Request Rate Threshold Exceeded"* and the run dies half-built.

### Runtime and resumability

`build.py` downloads about **870 MiB** across 81 files, then parses in roughly 40 seconds. Already
downloaded quarters are reused, so a re-run with the archives present makes **no network requests at
all**.

`rets.py` is the slow stage: about **25 minutes** for 8,239 tickers in 55 batches, and Yahoo
rate-limits it. It is resumable — each batch writes a part file plus an `.ok` marker and a marked batch
is skipped, so it can be run repeatedly until it reports `DONE`. `MAX_BATCHES=n` limits one invocation.

**Caveat on re-running.** The event output is reproducible, but the *drop ledger* is not: a discarded
batch writes `drops.json` with its counters already incremented and then raises, so the refetched batch
increments them again. The published decomposition therefore overstates its absolute drop count by 2,211
events, about 12%. The shape is unaffected — pushing the entire excess into the largest category still leaves it at
93.8%.

It also verifies each batch before marking it done, by re-requesting a sample of the tickers that came
back empty: **a delisted ticker stays empty, a throttled one comes back alive.** A batch that fails
that test, or that yields two or fewer rows from twenty or more event tickers, is discarded rather than
written. This exists because an earlier version cached throttled empty batches as complete and would
have reported success over a dataset missing roughly 40% of its universe.

## The event definition — one specification, stated plainly

- **Purchases only.** Transaction code `P`, acquired/disposed code `A`, shares and price both positive.
- **10b5-1 plan filings excluded** where the flag exists. It lives in `SUBMISSION.tsv`, appears only
  from **2023 Q1** (13 of 81 quarters), and removes **3.89% of filing-owner records** in those quarters
  — **6.06%** if you count individual transaction rows instead, and those two denominators are not
  interchangeable. For 2006-2022 the SEC published no such flag, so nothing can be excluded and nothing
  is claimed. **This filter covers only the late era, so the two eras are not filtered alike.**
- **A cluster** is a ticker-week (calendar week of the *filing* date) with two or more distinct
  `RPTOWNERCIK` values and combined notional of at least $100,000. Notional counts each filing once —
  the reporting-owner table has one row per owner, so summing it naively double-counts a joint filing.
- **Entry** is the close of the first trading day after the last filing in that week. You cannot act on
  a filing before it exists.
- **Hold** 21 trading days (63 also computed). Benchmark SPY over the identical window.
- **Tradable** means 20-day trailing median dollar volume >= $1M and a Form 4 price >= $5. No upper
  bound.

## Survivorship — both denominators, because they differ

| | resolved | total | |
|---|---|---|---|
| **Events** | 17,018 | 35,888 | **47.4% resolved, 52.6% dropped** |
| **Tickers** | 3,356 | 8,239 | **40.7% resolved** |

Both are real and they are not the same number. The drop decomposes, from `f4/drops.json`:

- **~94% no price data at all** — the ticker is gone, or was never priced.
- **~4%** price series with fewer than 300 observations.
- **~2%** symbols that are not symbols. The SEC's ticker field is free text and contains entries like
  `( EPG )` and `(NONE)`; 141 of 8,239 cannot be a ticker. These are counted separately and not as
  delistings.
- **0% within 21 days of series end.** This filter was expected to systematically exclude the final,
  worst weeks of a stock going to zero. It drops **no events** — those have already failed for having
  no price data.

Survivorship is also **era-dependent**: an event from 2006 has had twenty years for its ticker to
disappear, one from 2024 has had two. 2017-2026 therefore has more resolved events (9,757) than
2006-2016 (7,261) despite a shorter window, and the measured fall from +1.91% to +0.44% **overstates**
the true decline. **Together with the late-only 10b5-1 filter and the worse late-era joint-filing
contamination, that is three ways the two eras are measured differently, all pushing the same way.**

## What is wrong with this, in order of how much it matters

- **The central claim is narrower than it looks, and here is exactly how narrow.** Enumerating all 231
  contiguous runs of calendar years: inside the early era, excluding 2008-09, **no window reaches
  significance at three or more insiders** — the largest |t| is 1.85 (2014 alone, N 143, -1.56%). At two
  or more insiders **exactly one does**, and it is negative: 2014-2015, -0.82% (t -2.13, N 709). It does
  not generalise past the early era: across the full sample **32 crisis-free contiguous windows are
  significant at three or more insiders and 41 at two or more**, of which 30 of 32 and 29 of 41 are
  negative. The positive ones include 2016-2018 (+1.10%, t 3.41, N 1,238) and 2016-2019 (+0.89%, t 3.20,
  N 1,679) at two or more insiders — both straddling the era break, both more significant than the early
  era itself (+0.66%, t 3.01). With 231 windows tested per threshold, a handful at t = 3 is what noise
  looks like; none of them should be believed, and the same scepticism applies to excluding 2008-09.
- **Filing date, not transaction date.** Kang, Kim & Wang measure from the transaction; this measures
  from the filing, because that is when a reader could act. Their table shows 2.06% of their 3.80%
  accrues in the first five days, so starting ~2 days later forfeits a large share of it. This is most
  of why the magnitudes here are smaller.
- **The filings' own prices contain errors, and the screen runs on them.** Assured Guaranty's April
  2008 filings report **$250,000,000 per share** — the total dollar amount in the wrong field. That
  propagates into the notional: **21 events show more than $1 trillion** of single-week insider buying
  and the largest is $6.7 quadrillion. 194 events carry a price above $1,000 and 65 above $10,000.
  These are disclosed, not filtered (see above). Cost: **63 events carry a notional above $1bn; one is
  in the headline cell** and dropping it moves -0.422% (t -1.326) to **-0.431% (t -1.352)**; seven are
  in the early-era cell and dropping all seven moves +0.887% (t 2.70) to **+0.878% (t 2.66)**.
- **12.4% of events are non-tradable because liquidity could not be computed, not because they were
  illiquid.** The test is `dvol >= 1e6` and a missing value fails it silently: **2,112 events have no
  figure — 19.6% of pre-2017 events against 7.1% after.** Of those, **1,595 would clear the price
  screen**, and they average **+2.80% (t 2.98)** — so the exclusion is not neutral. Affects both price
  screens identically.
- **SPY only.** No size or beta adjustment. Over 2017-01-03 to 2026-03-31, IWM returned +105.5%
  against SPY's +234.4%, so a size adjustment would make the post-2017 figure *less* bad; market
  adjustment assumes beta of 1, so a beta adjustment would make it *worse*. Net sign unclaimed.
- **No transaction costs anywhere.** Adding them moves every post-2017 figure further down.
- **The return prices are not point-in-time.** Forward returns come from Yahoo via `yfinance` and are
  split- and dividend-adjusted. **Free price data has no delisted names at all**, which is the whole
  reason 94% of the drops are "no price data" — a point-in-time source carrying delisting returns would
  settle the survivorship question rather than bounding it. The *screen* no longer depends on those
  prices; the returns still do.
- **`events.csv.gz` contains price artefacts that are not corrected.** Six events carry a non-positive
  price, five a negative dollar volume, and fifty a price above $1 million. All are excluded by the
  liquidity floor in every reported cut, and none has been fixed.
- **`TRANS_DATE` is read and never used.** `build.py` loads the transaction date and the pipeline then
  keys everything off the filing date. That is deliberate — see the filing-date note above — but the
  column being present and unused has misled a reader of this code before.
- **A missing forward return** is a sixth possible drop cause. In the current run it removes nothing:
  all 17,018 events carry usable 21-day returns for both the stock and the benchmark.
- **The cluster definition itself is not swept.** The calendar week, the $100,000 floor and the
  close-to-close entry are each a single choice fixed before the result was known.
- **No external check that the Form 4 price matches the market price.** Four cases agree: NFLX 2006
  $19.99, TSLA 2010 $17.00, TSLA 2011 $28.76, NVR $4,105.97 against a $3,953.09 adjusted close. The
  true error rate in the field is **NOT MEASURED**.

## What lands in `f4/`

| file | what |
|---|---|
| `<quarter>.zip` | the 81 raw SEC archives, reused on re-run |
| `purchases.csv.gz` | 470,754 filing-owner purchase records |
| `coverage.csv` | per-quarter presence of the 10b5-1 flag |
| `clusters.csv.gz` | weekly clusters with `n`, `n_acc`, notional, `px_f4` |
| `events_parts/` | per-batch return files plus `.ok` markers |
| `events.csv.gz` | 17,018 events with 21d and 63d returns — never overwritten |
| `events_px.csv.gz` | the same events with the as-traded price joined on |
| `drops.json` | the drop ledger behind the survivorship table |

`f4/` is gitignored. **Nothing in it is committed**, including `events_px.csv.gz`.

## Data

SEC Form 345 quarterly structured data sets, public domain, free:
<https://www.sec.gov/dera/data/form-345>
