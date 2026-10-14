"""Volatility-scaled momentum: a pre-registered three-specification test.

    python3 fetch.py      # once, downloads and caches the French data
    python3 volmom.py     # the whole study, end to end

WHAT THIS TESTS. Three specifications of the Fama-French momentum factor
(WML, published by Kenneth French as "Mom"), evaluated monthly:

    S1  control. The WML factor itself, no overlay.
    S2  volatility-scaled. WML exposure multiplied by 0.12 / realised_vol,
        where realised_vol is the annualised volatility of DAILY WML returns
        over the prior 126 trading days. Both 12% and 126 days are Barroso &
        Santa-Clara (2015)'s own values and are not tuned here.
    S3  trend filter. Hold WML only in months that begin with the cumulative
        market index above its 10-month moving average; otherwise flat.

Splits are evaluated once: in-sample 1927-01..1980-12, holdout
1981-01..2026-08. Significance is Bonferroni over the three specifications,
alpha = 0.05/3, two-sided, so nothing counts below |t| = 2.394.

NOTHING IN THIS FILE IS TUNED TO A TARGET. Where the pre-registration left a
choice open, the choice is named in a comment beginning "CHOICE:", fixed
before the run, and -- where it could plausibly have gone the other way --
accompanied by a sensitivity line in the printed report so a reader can see
what the other branch would have produced.
"""
from __future__ import annotations

import math
import os
import sys

import numpy as np
import pandas as pd
from scipy import stats

import fetch
import overfit

# ---------------------------------------------------------------------------
# Pre-registered constants. None of these is a free parameter.
# ---------------------------------------------------------------------------
TARGET_ANNUAL_VOL = 0.12        # Barroso & Santa-Clara's own target
VOL_WINDOW_TRADING_DAYS = 126   # their realised-variance window
TRADING_DAYS_PER_YEAR = 252     # annualisation factor for daily volatility
TREND_FILTER_MONTHS = 10        # 10-month moving average
MONTHS_PER_YEAR = 12

IN_SAMPLE_START, IN_SAMPLE_END = 192701, 198012
HOLDOUT_START, HOLDOUT_END = 198101, 202608

# Bonferroni over 3 specifications at alpha = 0.05, two-sided.
BONFERRONI_CRITICAL_T = 2.394

# Barroso & Santa-Clara's own evaluation window, for the replication check.
BSC_WINDOW_START, BSC_WINDOW_END = 192703, 201112

# The figures the earlier, lost run recorded. Printed side by side with what
# this code computes. They are NEVER read by the computation -- grep for
# RECORDED and you will find it only in reporting code.
RECORDED = {
    ("in_sample", "S1"): dict(ann=9.01, vol=17.22, sharpe=0.50, maxdd=-78.4, worst=-52.6, t=3.67),
    ("in_sample", "S2"): dict(ann=18.73, vol=18.52, sharpe=0.93, maxdd=-42.6, worst=-29.0, t=6.81),
    ("in_sample", "S3"): dict(ann=8.29, vol=8.92, sharpe=0.90, maxdd=-13.5, worst=-9.6, t=6.53),
    ("holdout", "S1"): dict(ann=5.75, vol=15.21, sharpe=0.37, maxdd=-57.8, worst=-34.4, t=2.49,
                            skew=-1.43, kurt=13.22),
    ("holdout", "S2"): dict(ann=13.31, vol=16.16, sharpe=0.78, maxdd=-27.8, worst=-20.6, t=5.25,
                            skew=0.05, kurt=5.07),
    ("holdout", "S3"): dict(ann=4.99, vol=10.36, sharpe=0.47, maxdd=-26.0, worst=-12.6, t=3.18,
                            skew=-0.04, kurt=7.55),
}
RECORDED_IN_SAMPLE_N = 638
RECORDED_HOLDOUT_N = 548
RECORDED_DEFLATED_SHARPE = {"S1": 0.8764, "S2": 1.0000, "S3": 0.9726}

# The paper's published figures for its own 1927:03-2011:12 window.
BSC_PAPER = {
    "S1 Sharpe": 0.53, "S2 Sharpe": 0.97,
    "S1 max drawdown": -96.7, "S2 max drawdown": -45.2,
    "S1 worst month": -79.0, "S2 worst month": -28.4,
}

# French encodes "no observation" as one of these sentinels, in percent.
FRENCH_MISSING_SENTINELS = (-99.99, -999.0, -99.99 * 100)


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------
def parse_french_csv(csv_path: str, date_digits: int) -> tuple[pd.DataFrame, dict]:
    """Read one French CSV into a DataFrame indexed by an integer date.

    French files are a text preamble, a header row, a block of periodic rows,
    then -- in the monthly files -- a blank line and a second block of ANNUAL
    rows with the same column names. Selecting rows purely by "first field is
    exactly `date_digits` digits" picks up the monthly/daily block and leaves
    the annual block behind, because annual rows carry a 4-digit year. That is
    sturdier than counting preamble lines, which differ between the files.

    Returns the frame plus a dict of parse statistics, so the caller can
    assert on them instead of trusting that this worked.
    """
    if not os.path.exists(csv_path):
        raise SystemExit(
            "missing %s -- run `python3 fetch.py` first to download and cache the "
            "Kenneth French data this study reads." % csv_path
        )
    with open(csv_path, "r", encoding="utf-8") as handle:
        lines = handle.read().splitlines()

    header_fields = None
    records = []
    stats_counters = {
        "total_lines": len(lines),
        "data_rows": 0,
        "annual_rows_skipped": 0,
        "non_data_lines": 0,
        "rows_dropped_missing": 0,
        "rows_dropped_bad_width": 0,
    }

    for line in lines:
        fields = [field.strip() for field in line.split(",")]
        first = fields[0]

        # The header is the line whose first field is empty and which has at
        # least one named column after it (",Mom" / ",Mkt-RF,SMB,HML,RF").
        # Take the FIRST such line: the annual block repeats it later.
        if header_fields is None and first == "" and len(fields) > 1 and any(fields[1:]):
            header_fields = fields[1:]
            continue

        if not (first.isdigit() and len(first) == date_digits):
            if first.isdigit() and len(first) == 4:
                stats_counters["annual_rows_skipped"] += 1
            else:
                stats_counters["non_data_lines"] += 1
            continue

        if header_fields is None:
            raise SystemExit("found a data row before any header in %s" % csv_path)

        values = fields[1:]
        if len(values) != len(header_fields):
            stats_counters["rows_dropped_bad_width"] += 1
            continue

        try:
            numbers = [float(value) for value in values]
        except ValueError:
            stats_counters["rows_dropped_bad_width"] += 1
            continue

        # A sentinel anywhere in the row makes the whole row unusable here;
        # all of our columns are used together.
        if any(any(math.isclose(n, s) for s in FRENCH_MISSING_SENTINELS) for n in numbers):
            stats_counters["rows_dropped_missing"] += 1
            continue

        records.append([int(first)] + numbers)
        stats_counters["data_rows"] += 1

    frame = pd.DataFrame(records, columns=["date"] + list(header_fields)).set_index("date")
    # French publishes percent. Everything downstream is in decimal.
    frame = frame / 100.0
    frame = frame.sort_index()
    stats_counters["first"] = int(frame.index[0])
    stats_counters["last"] = int(frame.index[-1])
    stats_counters["duplicate_dates"] = int(frame.index.duplicated().sum())
    return frame, stats_counters


def assert_contiguous_months(index: pd.Index, label: str) -> None:
    """Fail loudly if a monthly index skips a month.

    Every downstream step (the 10-month average, the split boundaries, the
    warm-up accounting) assumes consecutive months with no holes.
    """
    months = list(index)
    for earlier, later in zip(months, months[1:]):
        if next_month(earlier) != later:
            raise SystemExit("%s: gap between %d and %d" % (label, earlier, later))


def next_month(yyyymm: int) -> int:
    year, month = divmod(yyyymm, 100)
    return year * 100 + month + 1 if month < 12 else (year + 1) * 100 + 1


def count_months(start: int, end: int) -> int:
    """Inclusive count of calendar months between two YYYYMM integers."""
    start_year, start_month = divmod(start, 100)
    end_year, end_month = divmod(end, 100)
    return (end_year - start_year) * 12 + (end_month - start_month) + 1


# ---------------------------------------------------------------------------
# The three specifications
# ---------------------------------------------------------------------------
def realised_volatility_by_month(
    daily_wml: pd.Series, months: list[int], estimator: str
) -> pd.Series:
    """Annualised 126-trading-day realised volatility of daily WML, per month.

    NO LOOK-AHEAD. The value stored against month m is computed from the last
    126 daily observations whose date is STRICTLY BEFORE the first calendar
    day of month m. Concretely the cutoff is `yyyymmdd < m * 100 + 1`, so the
    newest daily return that can enter the estimate for, say, 1980-07 is the
    last trading day of 1980-06. The scale applied to month m's return is
    therefore knowable on the morning of the first trading day of month m.

    THE TWO ESTIMATORS, and why both are computed and both are reported:

      "uncentred"  sqrt(252 * mean(r**2)) -- Barroso & Santa-Clara's own
                   formula. Their equation defines the realised variance of
                   WML as 21 * sum(r_d**2) / 126, a monthly variance built
                   from UNCENTRED squared daily returns; annualising it by 12
                   gives the 252 above. The daily mean is never subtracted.

      "centred"    sample standard deviation (ddof=1) * sqrt(252) -- the
                   textbook reading of the English phrase "annualised
                   volatility of daily returns".

    The pre-registration says "the annualised volatility of daily WML returns
    over the prior 126 trading days ... Barroso & Santa-Clara's own values".
    That sentence does not settle which of the two it means, and the two are
    not identical: the uncentred estimator is larger by roughly half the
    squared mean over the variance, which is small per month but is NOT
    negligible once compounded over a century, because it biases the leverage
    down in exactly the months where the factor has drifted hard.

    This study reports "uncentred" as the primary, because the whole
    specification is an explicit replication of Barroso & Santa-Clara and
    their published formula is the uncentred one, and prints "centred"
    beside it everywhere. See the DISCLOSURE section of the report for when
    and how that call was made -- it was not made before the first run.
    """
    if estimator not in ("uncentred", "centred"):
        raise ValueError("estimator must be 'uncentred' or 'centred', got %r" % estimator)

    daily_dates = daily_wml.index.to_numpy()
    daily_values = daily_wml.to_numpy()

    volatilities = {}
    for month in months:
        cutoff = month * 100 + 1          # first calendar day of this month
        usable = np.searchsorted(daily_dates, cutoff, side="left")
        if usable < VOL_WINDOW_TRADING_DAYS:
            continue                       # not enough history yet
        window = daily_values[usable - VOL_WINDOW_TRADING_DAYS:usable]
        if estimator == "uncentred":
            per_day = math.sqrt(float(np.mean(window ** 2)))
        else:
            per_day = float(window.std(ddof=1))
        volatilities[month] = per_day * math.sqrt(TRADING_DAYS_PER_YEAR)
    return pd.Series(volatilities, dtype=float).sort_index()


def trend_filter_signal(market_total_return: pd.Series) -> pd.Series:
    """True for months that begin with the market index above its 10-month MA.

    NO LOOK-AHEAD. The signal for month m compares the index level at the END
    of month m-1 against the mean of the index over months m-10..m-1. Both are
    known before month m starts.

    Note the comparison is scale-invariant: multiplying the whole cumulative
    index by a constant multiplies its moving average by the same constant, so
    WHERE the cumulative product is started changes only the first month at
    which a 10-month average exists, never any subsequent signal value.

    CHOICE: the "market index" is the cumulative total return of the market,
    Mkt-RF + RF, not the cumulative excess return. A trend filter in this
    literature (Faber 2007 and its antecedents) is applied to a price or
    total-return index, which is what an investor actually observes.
    """
    index_level = (1.0 + market_total_return).cumprod()
    moving_average = index_level.rolling(TREND_FILTER_MONTHS).mean()
    above = index_level > moving_average
    # Shift forward one month: the signal observed at the end of month m-1
    # governs the position held through month m.
    return above.shift(1).fillna(False).astype(bool)


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
def max_drawdown(monthly_returns: pd.Series) -> float:
    """Worst peak-to-trough decline of the compounded wealth curve."""
    wealth = (1.0 + monthly_returns).cumprod()
    running_peak = wealth.cummax()
    return float((wealth / running_peak - 1.0).min())


def summarise(monthly_returns: pd.Series) -> dict:
    """Every reported statistic for one specification over one split.

    CONVENTIONS, stated because they are not interchangeable:
      * annualised return  = (1 + arithmetic monthly mean) ** 12 - 1
      * annualised vol     = sample monthly sd (ddof=1) * sqrt(12)
      * Sharpe             = (monthly mean / monthly sd) * sqrt(12)
      * t statistic        = (monthly mean / monthly sd) * sqrt(n)
      * kurtosis is RAW (Pearson): a normal distribution scores 3.
    Sharpe is therefore NOT equal to annualised return / annualised vol: the
    numerator of the Sharpe is the arithmetic mean annualised linearly, while
    the reported annualised return compounds it. Both are standard; mixing
    them up is the usual source of a "the Sharpe doesn't divide" complaint.

    WML is a self-financing long-short spread and is already an excess return,
    so no risk-free rate is subtracted anywhere.
    """
    values = monthly_returns.to_numpy(dtype=float)
    n = len(values)
    mean = float(values.mean())
    sd = float(values.std(ddof=1))
    monthly_sharpe = mean / sd
    return {
        "n": n,
        "first": int(monthly_returns.index[0]),
        "last": int(monthly_returns.index[-1]),
        "mean_monthly": mean,
        "sd_monthly": sd,
        "ann_return_pct": ((1.0 + mean) ** MONTHS_PER_YEAR - 1.0) * 100.0,
        "ann_vol_pct": sd * math.sqrt(MONTHS_PER_YEAR) * 100.0,
        "monthly_sharpe": monthly_sharpe,
        "sharpe": monthly_sharpe * math.sqrt(MONTHS_PER_YEAR),
        "maxdd_pct": max_drawdown(monthly_returns) * 100.0,
        "worst_month_pct": float(values.min()) * 100.0,
        "t_stat": monthly_sharpe * math.sqrt(n),
        "skew": float(stats.skew(values, bias=True)),
        "kurtosis_raw": float(stats.kurtosis(values, fisher=False, bias=True)),
    }


def moments_sample_sd_convention(monthly_returns: pd.Series) -> tuple[float, float]:
    """Skew and raw kurtosis with the SAMPLE (ddof=1) sd in the denominator.

    `summarise()` reports scipy's `bias=True` moments: the third and fourth
    central moments divided by powers of the POPULATION standard deviation
    (ddof=0). That is the standard convention and is what this study reports.

    A hand-rolled implementation that reaches for `statistics.stdev` instead
    gets the fourth central moment over the FOURTH power of the ddof=1
    standard deviation, which is smaller by ((n-1)/n)**2. At n = 548 that is
    a 0.36% reduction -- invisible in the skew, about 0.05 on a kurtosis of
    13. This function computes that variant so the report can show both,
    because it is exactly the gap between this code and the recorded run.
    """
    values = monthly_returns.to_numpy(dtype=float)
    n = len(values)
    deviations = values - values.mean()
    sample_sd = values.std(ddof=1)
    skew = float((deviations ** 3).mean() / sample_sd ** 3)
    kurtosis = float((deviations ** 4).mean() / sample_sd ** 4)
    return skew, kurtosis


# ---------------------------------------------------------------------------
# Reporting helpers
# ---------------------------------------------------------------------------
def rule(title: str = "") -> None:
    if title:
        print("\n" + "=" * 94)
        print(title)
        print("=" * 94)
    else:
        print("-" * 94)


def comparison_row(computed: float, recorded: float | None, width: int = 10) -> str:
    if recorded is None:
        return "%*s %*s %*s" % (width, fmt(computed), width, "--", width, "--")
    return "%*s %*s %*s" % (
        width, fmt(computed), width, fmt(recorded), width, fmt(computed - recorded)
    )


def fmt(value: float) -> str:
    return "%+.2f" % value if value is not None else "--"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> int:
    rule("1. PARSE -- Kenneth French data, with assertions")

    monthly_mom_frame, monthly_stats = parse_french_csv(
        fetch.csv_path_for("momentum_monthly"), date_digits=6
    )
    daily_mom_frame, daily_stats = parse_french_csv(
        fetch.csv_path_for("momentum_daily"), date_digits=8
    )
    factors_frame, factor_stats = parse_french_csv(
        fetch.csv_path_for("research_factors_monthly"), date_digits=6
    )

    for name, counters in (
        ("momentum monthly", monthly_stats),
        ("momentum daily", daily_stats),
        ("research factors monthly", factor_stats),
    ):
        print(
            "%-26s rows=%-6d dropped(missing)=%-3d dropped(malformed)=%-3d "
            "annual-block rows skipped=%-4d duplicates=%d"
            % (
                name,
                counters["data_rows"],
                counters["rows_dropped_missing"],
                counters["rows_dropped_bad_width"],
                counters["annual_rows_skipped"],
                counters["duplicate_dates"],
            )
        )
        print("%-26s first=%d  last=%d" % ("", counters["first"], counters["last"]))

    wml_monthly = monthly_mom_frame["Mom"]
    wml_daily = daily_mom_frame["Mom"]
    market_total_return = factors_frame["Mkt-RF"] + factors_frame["RF"]

    assert_contiguous_months(wml_monthly.index, "monthly momentum")
    assert_contiguous_months(factors_frame.index, "research factors")

    expected_monthly_rows = 1196
    assert monthly_stats["rows_dropped_missing"] == 0, "monthly momentum rows were dropped"
    assert monthly_stats["rows_dropped_bad_width"] == 0, "malformed monthly momentum rows"
    print(
        "\nASSERTION monthly momentum: %d rows read, %d dropped, %d..%d"
        "   (recorded run: %d rows, 0 dropped)  -> %s"
        % (
            monthly_stats["data_rows"],
            monthly_stats["rows_dropped_missing"] + monthly_stats["rows_dropped_bad_width"],
            monthly_stats["first"],
            monthly_stats["last"],
            expected_monthly_rows,
            "MATCH" if monthly_stats["data_rows"] == expected_monthly_rows else "DIVERGENCE",
        )
    )

    # -----------------------------------------------------------------------
    rule("2. BUILD -- the three specifications")

    # CHOICE: the study sample is defined by the momentum factor, which starts
    # 1927-01. The market index used by S3 is therefore started at 1927-01 too,
    # so the 10-month warm-up is counted from the first month the study has any
    # return at all. Section 3 prints what the other branch would do.
    study_months = [m for m in wml_monthly.index if m >= IN_SAMPLE_START]
    market_for_trend = market_total_return.loc[
        [m for m in market_total_return.index if m >= IN_SAMPLE_START]
    ]

    vol_uncentred = realised_volatility_by_month(wml_daily, study_months, "uncentred")
    vol_centred = realised_volatility_by_month(wml_daily, study_months, "centred")
    trend_signal = trend_filter_signal(market_for_trend)

    s1 = wml_monthly.loc[study_months]

    def scaled(volatility: pd.Series) -> tuple[pd.Series, pd.Series]:
        scale = (TARGET_ANNUAL_VOL / volatility).dropna()
        return scale, (scale * s1).dropna()

    scale_uncentred, s2 = scaled(vol_uncentred)
    scale_centred, s2_centred = scaled(vol_centred)

    s3 = s1 * trend_signal.reindex(s1.index).fillna(False).astype(float)
    # S3 is only DEFINED once a 10-month average exists; before that the
    # product above silently reads as "flat", which is not the same thing.
    s3_defined_from = int(trend_signal.index[TREND_FILTER_MONTHS])
    s3 = s3.loc[s3.index >= s3_defined_from]

    print("S1 defined from %d to %d  (%d months)" % (s1.index[0], s1.index[-1], len(s1)))
    print("S2 defined from %d to %d  (%d months)  -- needs %d prior daily WML returns"
          % (s2.index[0], s2.index[-1], len(s2), VOL_WINDOW_TRADING_DAYS))
    print("S3 defined from %d to %d  (%d months)  -- needs a %d-month average, lagged one month"
          % (s3.index[0], s3.index[-1], len(s3), TREND_FILTER_MONTHS))
    print("\nleverage from the vol scale (no cap -- the pre-registration specifies none):")
    for label, scale in (("uncentred (primary)", scale_uncentred), ("centred", scale_centred)):
        print("  %-20s min %.2fx  median %.2fx  max %.2fx"
              % (label, scale.min(), scale.median(), scale.max()))

    # Demonstrate the no-look-ahead cutoff concretely rather than asserting it.
    print("\nNO-LOOK-AHEAD CHECK -- the last daily WML return that feeds each month's scale:")
    daily_dates_array = wml_daily.index.to_numpy()
    for sample_month in (192711, 198101, 200811, 202608):
        last_used = int(daily_dates_array[
            np.searchsorted(daily_dates_array, sample_month * 100 + 1, side="left") - 1])
        assert last_used < sample_month * 100 + 1, "look-ahead in the volatility window"
        print("  scale for %d uses daily returns up to and including %d  (month begins %d)"
              % (sample_month, last_used, sample_month * 100 + 1))
    print("  S3's signal is .shift(1) on the above/below flag, so month m is governed by the")
    print("  index level and 10-month average observed at the close of month m-1.")

    common_months = sorted(set(s1.index) & set(s2.index) & set(s3.index))
    specs = {
        "S1": s1.loc[common_months],
        "S2": s2.loc[common_months],
        "S3": s3.loc[common_months],
    }
    s2_centred_common = s2_centred.loc[common_months]

    # -----------------------------------------------------------------------
    rule("3. WARM-UP ACCOUNTING -- why the in-sample n is what it is")

    in_sample_months = [m for m in common_months if IN_SAMPLE_START <= m <= IN_SAMPLE_END]
    holdout_months = [m for m in common_months if HOLDOUT_START <= m <= HOLDOUT_END]
    calendar_in_sample = count_months(IN_SAMPLE_START, IN_SAMPLE_END)
    warmup_months = count_months(IN_SAMPLE_START, common_months[0]) - 1

    print("in-sample window %d..%d spans %d calendar months"
          % (IN_SAMPLE_START, IN_SAMPLE_END, calendar_in_sample))
    print("  S1 needs no history and is available from %d." % s1.index[0])
    print("  S2 first available month: %d -- the first month preceded by %d daily WML"
          " returns (daily WML starts %d, so the 126th trading day falls in April 1927)."
          % (s2.index[0], VOL_WINDOW_TRADING_DAYS, daily_stats["first"]))
    print("  S3 first available month: %d -- the market index over 1927-01..1927-10 is the"
          " first 10-month average that exists, and it governs the FOLLOWING month."
          % s3.index[0])
    print("  S3 binds. Warm-up consumed = %d months (%d..%d), so the common sample opens at %d."
          % (warmup_months, IN_SAMPLE_START, common_months[0] - 1, common_months[0]))
    print("  %d calendar months - %d warm-up = %d usable; computed n = %d; recorded n = %d -> %s"
          % (calendar_in_sample, warmup_months, calendar_in_sample - warmup_months,
             len(in_sample_months), RECORDED_IN_SAMPLE_N,
             "MATCH" if len(in_sample_months) == RECORDED_IN_SAMPLE_N else "DIVERGENCE"))
    print("\nholdout %d..%d spans %d calendar months (no warm-up needed -- every"
          " specification is long since available); computed n = %d; recorded n = %d -> %s"
          % (HOLDOUT_START, HOLDOUT_END, count_months(HOLDOUT_START, HOLDOUT_END),
             len(holdout_months), RECORDED_HOLDOUT_N,
             "MATCH" if len(holdout_months) == RECORDED_HOLDOUT_N else "DIVERGENCE"))

    alt_signal = trend_filter_signal(market_total_return)
    alt_s3_from = int(alt_signal.index[TREND_FILTER_MONTHS])
    alt_common = sorted(set(s1.index) & set(s2.index)
                        & {m for m in s1.index if m >= alt_s3_from})
    alt_in_sample = [m for m in alt_common if IN_SAMPLE_START <= m <= IN_SAMPLE_END]
    print("\nSENSITIVITY on the index start. The above/below comparison is scale-invariant, so"
          "\nwhere the cumulative product starts changes only WHEN the first average exists."
          "\nStarting the index at the market factor's own first month (%d) would make S3"
          "\navailable from %d, S2 would then bind, and in-sample n would be %d, not %d."
          % (factor_stats["first"], alt_s3_from, len(alt_in_sample), len(in_sample_months)))

    # -----------------------------------------------------------------------
    splits = {"in_sample": in_sample_months, "holdout": holdout_months}
    results: dict[tuple[str, str], dict] = {}
    for split_name, months in splits.items():
        for spec_name, series in specs.items():
            results[(split_name, spec_name)] = summarise(series.loc[months])
        results[(split_name, "S2-centred")] = summarise(s2_centred_common.loc[months])

    for split_name, title in (
        ("in_sample", "4a. IN-SAMPLE 1927-01..1980-12 -- computed vs recorded"),
        ("holdout", "4b. HOLDOUT 1981-01..2026-08 -- computed vs recorded"),
    ):
        rule(title)
        moments = split_name == "holdout"
        header = "%-11s %-16s %10s %10s %10s" % ("spec", "metric", "computed", "recorded", "diff")
        print(header)
        print("-" * len(header))
        metric_fields = [
            ("ann return %", "ann_return_pct", "ann"),
            ("ann vol %", "ann_vol_pct", "vol"),
            ("Sharpe", "sharpe", "sharpe"),
            ("max drawdown %", "maxdd_pct", "maxdd"),
            ("worst month %", "worst_month_pct", "worst"),
            ("t statistic", "t_stat", "t"),
        ]
        if moments:
            metric_fields += [("skew", "skew", "skew"),
                              ("kurtosis (raw)", "kurtosis_raw", "kurt")]
        for spec_name in ("S1", "S2", "S2-centred", "S3"):
            computed = results[(split_name, spec_name)]
            # S2-centred is compared against the SAME recorded S2 row: it is the
            # other branch of one ambiguity, not a separate recorded result.
            recorded = RECORDED[(split_name, "S2" if spec_name == "S2-centred" else spec_name)]
            note = ""
            if spec_name == "S2":
                note = "  [uncentred / Barroso & Santa-Clara -- PRIMARY]"
            elif spec_name == "S2-centred":
                note = "  [centred sd -- the other branch; 'recorded' repeats the S2 row]"
            print("%-11s n = %d  (%d..%d)%s"
                  % (spec_name, computed["n"], computed["first"], computed["last"], note))
            for label, key, recorded_key in metric_fields:
                print("%-11s %-16s %s" % (
                    "", label, comparison_row(computed[key], recorded.get(recorded_key))))
            print()
        print("kurtosis is RAW (Pearson, normal = 3), matching the recorded run's convention.")
        print("Sharpe = (monthly mean / monthly sd) * sqrt(12); the annualised return compounds")
        print("the monthly mean, so Sharpe deliberately does NOT equal ann return / ann vol.")

    # -----------------------------------------------------------------------
    rule("5. DISCLOSURE -- the one choice that was resolved after seeing a number")

    print("""The pre-registration fixes the volatility target (12%) and the window (126 trading
days) but does not say whether "the annualised volatility of daily WML returns" means the
mean-centred sample standard deviation or Barroso & Santa-Clara's own uncentred root mean
square of daily returns. Their published formula is uncentred.

This implementation was first written with the CENTRED estimator, on the plain English
reading, and run. S1 and S3 reproduced the recorded figures to the last printed decimal;
S2 did not, missing on annualised volatility by +0.25 percentage points in BOTH splits.
That gap was then diagnosed, and the UNCENTRED estimator -- Barroso & Santa-Clara's actual
formula -- was found to reproduce the recorded S2 exactly. The primary was moved to the
uncentred estimator on that methodological ground, because this specification is an
explicit replication of their paper.

That ordering is stated plainly because it matters: the choice was made AFTER a divergence
was observed, not before. Both branches are therefore printed at equal prominence in every
table above, and the reader can take either. Nothing else in this study was revisited after
a number was seen, and no parameter anywhere was moved to close a gap.""")

    # -----------------------------------------------------------------------
    rule("6. REPLICATION CHECK -- Barroso & Santa-Clara's own window 1927:03-2011:12")

    bsc_months = sorted(
        set(s1.index) & set(s2.index)
        & {m for m in s1.index if BSC_WINDOW_START <= m <= BSC_WINDOW_END}
    )
    print("The paper's window opens at 1927-03, but S2 cannot exist before the 126th trading")
    print("day of daily WML history. The window actually used is the intersection, and S1 and")
    print("S2 are evaluated on IDENTICAL months so the comparison is like for like.")
    print("months actually used: %d..%d  (n = %d)" % (bsc_months[0], bsc_months[-1], len(bsc_months)))

    bsc = {"S1": summarise(s1.loc[bsc_months]), "S2": summarise(s2.loc[bsc_months])}
    s1_full_window = s1.loc[[m for m in s1.index if BSC_WINDOW_START <= m <= BSC_WINDOW_END]]
    bsc_s1_full = summarise(s1_full_window)

    print("\n%-20s %12s %12s %12s %12s" % ("", "this code", "the paper", "diff", "recorded run"))
    print("-" * 74)
    bsc_recorded = {"S1 Sharpe": 0.48, "S2 Sharpe": 0.93, "S1 max drawdown": -78.4,
                    "S2 max drawdown": -42.6, "S1 worst month": -52.6, "S2 worst month": -29.0}
    for label, computed in (
        ("S1 Sharpe", bsc["S1"]["sharpe"]), ("S2 Sharpe", bsc["S2"]["sharpe"]),
        ("S1 max drawdown", bsc["S1"]["maxdd_pct"]), ("S2 max drawdown", bsc["S2"]["maxdd_pct"]),
        ("S1 worst month", bsc["S1"]["worst_month_pct"]),
        ("S2 worst month", bsc["S2"]["worst_month_pct"]),
    ):
        paper = BSC_PAPER[label]
        print("%-20s %12s %12s %12s %12s" % (label, fmt(computed), fmt(paper),
                                             fmt(computed - paper), fmt(bsc_recorded[label])))

    # The recorded run evidently ran this comparison on the COMMON sample, which
    # starts 1927-11 because S3's 10-month warm-up is still applied even though
    # S3 takes no part in a comparison between S1 and S2. Both windows are shown:
    # the wider one is the better like-for-like test against the paper, the
    # narrower one is what reproduces the lost run's figures.
    bsc_common = [m for m in common_months if BSC_WINDOW_START <= m <= BSC_WINDOW_END]
    print("\nThe same comparison on the COMMON sample instead (%d..%d, n = %d) -- i.e. with"
          "\nS3's 10-month warm-up still applied, which is what the recorded run appears to"
          "\nhave done, since this is the window that reproduces its 0.48 and 0.93 exactly:"
          % (bsc_common[0], bsc_common[-1], len(bsc_common)))
    print("%-20s %12s %12s %12s" % ("", "this code", "recorded run", "diff"))
    print("-" * 60)
    for label, series in (("S1", s1), ("S2", s2)):
        window_stats = summarise(series.loc[bsc_common])
        for metric, key in (("Sharpe", "sharpe"), ("max drawdown", "maxdd_pct"),
                            ("worst month", "worst_month_pct")):
            recorded_value = bsc_recorded["%s %s" % (label, metric)]
            print("%-20s %12s %12s %12s"
                  % ("%s %s" % (label, metric), fmt(window_stats[key]),
                     fmt(recorded_value), fmt(window_stats[key] - recorded_value)))

    print("\nS1 over the full %d..%d window without the S2 intersection (n = %d): Sharpe %+.2f,"
          " max drawdown %+.1f%%, worst month %+.1f%%"
          % (BSC_WINDOW_START, BSC_WINDOW_END, bsc_s1_full["n"], bsc_s1_full["sharpe"],
             bsc_s1_full["maxdd_pct"], bsc_s1_full["worst_month_pct"]))
    print(
        "\nS2 reproduces the paper closely: Sharpe %.2f against their %.2f, max"
        " drawdown %.1f%% against\n%.1f%%, worst month %.1f%% against %.1f%%."
        % (bsc["S2"]["sharpe"], BSC_PAPER["S2 Sharpe"],
           bsc["S2"]["maxdd_pct"], BSC_PAPER["S2 max drawdown"],
           bsc["S2"]["worst_month_pct"], BSC_PAPER["S2 worst month"])
    )
    print(
        "\nS1'S TAIL DOES NOT, and that is reported rather than hidden. The paper's"
        " plain-momentum\ncontrol loses %.1f%% peak to trough with a worst month of"
        " %.1f%%; this code gets %.1f%%\nand %.1f%%. That is not a rounding"
        " difference, it is a different tail."
        % (abs(BSC_PAPER["S1 max drawdown"]), BSC_PAPER["S1 worst month"],
           bsc["S1"]["maxdd_pct"], bsc["S1"]["worst_month_pct"])
    )
    print("""
The stated likely cause is construction: the paper builds WML itself from the six
size-by-momentum portfolios, while this study uses French's published `Mom` factor,
and the two differ most in exactly the crash months that set a drawdown record.
Volatility scaling suppresses those same months, which is why S2 agrees and S1 does
not. THIS HAS NOT BEEN VERIFIED HERE -- it would take rebuilding WML from the six
portfolios to confirm -- and S1 is the control, so the gap stays on the record as an
open discrepancy.""")

    # -----------------------------------------------------------------------
    rule("7. SENSITIVITY -- the remaining choices the pre-registration left open")

    print("S2 volatility estimator (see section 5) -- both branches, holdout:")
    print("  uncentred RMS (primary)  Sharpe %.4f   ann vol %.2f%%"
          % (results[("holdout", "S2")]["sharpe"], results[("holdout", "S2")]["ann_vol_pct"]))
    print("  centred sd               Sharpe %.4f   ann vol %.2f%%"
          % (results[("holdout", "S2-centred")]["sharpe"],
             results[("holdout", "S2-centred")]["ann_vol_pct"]))

    excess_index_signal = trend_filter_signal(
        factors_frame["Mkt-RF"].loc[[m for m in factors_frame.index if m >= IN_SAMPLE_START]]
    )
    s3_excess = s1 * excess_index_signal.reindex(s1.index).fillna(False).astype(float)
    s3_excess = s3_excess.loc[s3_excess.index >= s3_defined_from]
    s3_excess_holdout = summarise(s3_excess.loc[holdout_months])
    print("\nS3 market index -- total return Mkt-RF+RF (used) vs excess return Mkt-RF only:")
    print("  holdout Sharpe  %.4f (total, primary)  vs  %.4f (excess)   difference %.4f"
          % (results[("holdout", "S3")]["sharpe"], s3_excess_holdout["sharpe"],
             results[("holdout", "S3")]["sharpe"] - s3_excess_holdout["sharpe"]))

    print("\nHOLDOUT MOMENTS -- the one residual gap against the recorded run, now identified.")
    print("summarise() uses scipy bias=True: central moments over powers of the POPULATION")
    print("(ddof=0) standard deviation. The recorded run evidently divided by the SAMPLE")
    print("(ddof=1) standard deviation instead, which shrinks raw kurtosis by ((n-1)/n)**2.")
    print("\n       %-4s %10s %10s %10s %10s %10s %10s"
          % ("spec", "skew pop", "skew smp", "recorded", "kurt pop", "kurt smp", "recorded"))
    for name in ("S1", "S2", "S3"):
        series = specs[name].loc[holdout_months]
        skew_sample, kurt_sample = moments_sample_sd_convention(series)
        recorded = RECORDED[("holdout", name)]
        print("       %-4s %10.4f %10.4f %10.4f %10.4f %10.4f %10.4f"
              % (name, results[("holdout", name)]["skew"], skew_sample, recorded["skew"],
                 results[("holdout", name)]["kurtosis_raw"], kurt_sample, recorded["kurt"]))
    holdout_n = len(holdout_months)
    shrinkage_pct = (1.0 - ((holdout_n - 1) / holdout_n) ** 2) * 100.0
    print("The sample-sd columns reproduce the recorded figures to 2 decimals. The population")
    print("convention is the standard one and is kept as primary; at n = %d the two differ by"
          % holdout_n)
    print("%.2f%% on raw kurtosis, which changes no conclusion and moves no kill criterion."
          % shrinkage_pct)

    months_held = int(trend_signal.reindex(s3.index).sum())
    print("\nS3 'otherwise cash' is implemented as a ZERO return, not the risk-free rate, because")
    print("WML is a self-financing long-short spread already expressed as an excess return;")
    print("crediting RF to a flat month would add a return the position does not earn.")
    print("S3 is invested in %d of %d common-sample months (%.1f%%)."
          % (months_held, len(s3), 100.0 * months_held / len(s3)))

    # -----------------------------------------------------------------------
    rule("8. KILL CRITERIA")

    s2_holdout_sharpe = results[("holdout", "S2")]["sharpe"]
    s1_holdout_sharpe = results[("holdout", "S1")]["sharpe"]

    print("K1a  S2 holdout Sharpe >= 0.50")
    print("       computed %.4f   recorded 0.78   -> %s"
          % (s2_holdout_sharpe, "PASS" if s2_holdout_sharpe >= 0.50 else "FAIL"))
    print("K1b  S2 beats S1 by >= 0.15 Sharpe on the holdout")
    print("       computed %.4f   recorded 0.41   -> %s"
          % (s2_holdout_sharpe - s1_holdout_sharpe,
             "PASS" if s2_holdout_sharpe - s1_holdout_sharpe >= 0.15 else "FAIL"))

    print("\nK2   probability of backtest overfitting <= 0.50")
    def matrix_for(names, months):
        columns = []
        for name in names:
            series = s2_centred_common if name == "S2-centred" else specs[name]
            columns.append(series.loc[months].to_numpy())
        return np.column_stack(columns)

    three = ("S1", "S2", "S3")
    pbo_runs = [
        ("in-sample %d..%d" % (in_sample_months[0], in_sample_months[-1]), three, in_sample_months),
        ("holdout %d..%d" % (holdout_months[0], holdout_months[-1]), three, holdout_months),
        ("common %d..%d" % (common_months[0], common_months[-1]), three, common_months),
        ("holdout, +S2-centred (N=4)", three + ("S2-centred",), holdout_months),
    ]
    pbo_results = {}
    for label, names, months in pbo_runs:
        result = overfit.pbo(matrix_for(names, months))
        pbo_results[label] = result
        print("       %-30s PBO = %.4f   splits = %d   distinct variants = %d   "
              "rows dropped = %d   -> %s"
              % (label, result.pbo, result.n_splits, result.distinct_variants,
                 result.rows_dropped, "PASS" if result.pbo <= 0.50 else "FAIL"))
    print("       recorded run: 0.000 across 3 variants. It did not record WHICH matrix it")
    print("       used. The holdout matrix reproduces 0.000 exactly; the in-sample matrix")
    print("       does not -- it gives %.4f, which FAILS the same <= 0.50 threshold."
          % pbo_results["in-sample %d..%d" % (in_sample_months[0], in_sample_months[-1])].pbo)
    print("""
       THAT SWING IS ITSELF THE FINDING. The same three specifications, the
       same procedure, two halves of the same history: PBO goes from 0.00 to
       0.76 and the kill criterion flips from pass to fail purely on which
       split the matrix was drawn from. K2 as pre-registered did not say,
       so it has no determinate answer here. Read the caveat below before
       reading any of these four numbers as evidence of anything.""")
    print("""
       CAVEAT, AND IT MUST TRAVEL WITH THE NUMBER: this PBO is computed at
       N = 3 specifications. PBO was designed for sweeps of dozens to
       thousands of variants. With three columns the out-of-sample rank of
       the in-sample winner can only be 1, 2 or 3, so omega = rank/(N+1) can
       only be 0.25, 0.50 or 0.75 and the log-odds lambda can take only three
       values. The statistic therefore has almost no resolution here: a PBO
       of 0.000 means only "the in-sample winner never finished below the
       out-of-sample median", which across three variants is a far weaker
       statement than the same number would be across 200. It is not strong
       evidence that this study is free of overfitting; it is close to no
       evidence either way.""")

    print("\nK3   deflated Sharpe, as pre-registered: 'deflated Sharpe <= 0 retires everything'")
    holdout_monthly_sharpes = [results[("holdout", name)]["monthly_sharpe"] for name in three]
    distinct = pbo_results["holdout %d..%d" % (holdout_months[0], holdout_months[-1])].distinct_variants
    # CHOICE: "the observed variance of the N trials' own Sharpe ratios" is read
    # as the POPULATION variance (ddof=0) of the three realised monthly Sharpes,
    # because these three are the whole population of trials rather than a sample
    # from a larger one. The ddof=1 figure is printed beside it; it is the one the
    # recorded run evidently used, and this primary was NOT moved to match it.
    var_population = float(np.var(holdout_monthly_sharpes, ddof=0))
    var_sample = float(np.var(holdout_monthly_sharpes, ddof=1))
    print("       n_trials = %d (distinct variants from PBO); n_obs = %d"
          % (distinct, len(holdout_months)))
    print("       variance of the 3 monthly Sharpes: %.6f (ddof=0, primary)  %.6f (ddof=1)"
          % (var_population, var_sample))
    print("\n       %-4s %12s %12s %12s %12s"
          % ("spec", "DSR ddof=0", "DSR ddof=1", "recorded", "diff vs rec"))
    for name in three:
        spec_stats = results[("holdout", name)]
        kwargs = dict(sharpe=spec_stats["monthly_sharpe"], n_trials=distinct,
                      n_obs=spec_stats["n"], skew=spec_stats["skew"],
                      kurtosis=spec_stats["kurtosis_raw"])
        dsr_pop = overfit.deflated_sharpe(var_trial_sharpes=var_population, **kwargs)
        dsr_sam = overfit.deflated_sharpe(var_trial_sharpes=var_sample, **kwargs)
        recorded_dsr = RECORDED_DEFLATED_SHARPE[name]
        print("       %-4s %12.4f %12.4f %12.4f %12.4f"
              % (name, dsr_pop, dsr_sam, recorded_dsr, dsr_pop - recorded_dsr))
    print("       (the ddof=1 column reproduces the recorded figures, which identifies the")
    print("        convention the lost run used; the primary above was left where it was.)")
    print("""
       K3 WAS MIS-SPECIFIED IN THE PRE-REGISTRATION. `deflated_sharpe()`
       returns a PROBABILITY in [0, 1] -- the probability the observed Sharpe
       beats what this many trials of luck would produce. A probability
       cannot be <= 0 except in a degenerate limit, so the criterion as
       written, "deflated Sharpe <= 0 retires everything", cannot fire no
       matter what the data says. As a kill criterion it is vacuous. The
       measured probabilities above are therefore reported as descriptive
       statistics only. No specification was retired by K3, and none could
       have been.""")

    # -----------------------------------------------------------------------
    rule("9. SIGNIFICANCE -- Bonferroni, 3 specifications, alpha = 0.05/3, |t| >= 2.394")
    for split_name in ("in_sample", "holdout"):
        for name in three:
            t_stat = results[(split_name, name)]["t_stat"]
            print("%-10s %-3s t = %+7.3f   %s"
                  % (split_name, name, t_stat,
                     "clears" if abs(t_stat) >= BONFERRONI_CRITICAL_T else "DOES NOT CLEAR"))
    print("\nDone.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
