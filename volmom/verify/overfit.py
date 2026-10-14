"""Whether a backtest's good numbers are real, or picked from noise.

This module answers three separate questions about a sweep's results, each
with its own published source and its own function:

  * `pbo()` -- across every way to split the sweep's history into an
    in-sample half and an out-of-sample half, how often does the variant
    that looked best in-sample fall apart out-of-sample? This is the
    combinatorially symmetric cross-validation (CSCV) procedure and the
    probability of backtest overfitting (PBO) it produces, from Bailey,
    Borwein, Lopez de Prado & Zhu, "The Probability of Backtest Overfitting"
    (2017).
  * `deflated_sharpe()` / `expected_max_sharpe()` -- given how many variants
    were tried, what Sharpe ratio would the best of them reach on pure luck,
    and how much of the observed Sharpe survives once that's subtracted?
    From Bailey & Lopez de Prado, "The Deflated Sharpe Ratio" (2014), with
    the Sharpe standard error from Mertens (2002) / Opdyke (2007).
  * `purged_folds()` -- cross-validation folds for data whose labels look
    forward past the bar they're stamped on, so a naive fold would test on
    rows the training set already saw the answer to. From Lopez de Prado,
    "Advances in Financial Machine Learning" (2018).

This build step adds `purged_folds()` to the `pbo()`, `per_period_sharpe()`,
`deflated_sharpe()` and `expected_max_sharpe()` built earlier. All three
top-level functions now exist.

Nothing in this repository imports this module. It is a free-standing
calculator: point it at a sweep's per-period returns and read back a
probability, never the other way around.

Every module-level import is stdlib (`math`, `statistics`, `itertools`,
`dataclasses`, `typing`, plus `__future__`). `pbo()` is the one place numpy
is used, because a (rows, variants) matrix and the combinatorics over its
blocks are impractical in plain Python at the split counts this needs --
see `_numpy()` below. numpy is imported only there, only when `pbo()` is
actually called, exactly as `luck_bar._numpy()` guards its own import.
"""

from __future__ import annotations

import itertools
import math
import statistics
from dataclasses import dataclass
from typing import Any, Callable, Optional, Sequence, Tuple

# The Euler-Mascheroni constant, used by expected_max_sharpe() in a later
# build step. Defined here because it belongs with the module's other
# constants, not because pbo() reads it.
EULER_MASCHERONI = 0.5772156649015329

DEFAULT_BLOCKS = 16
MAX_BLOCKS = 20


@dataclass(frozen=True)
class PBOResult:
    """Everything `pbo()` computed, so a caller never has to recompute it.

    `lambdas`, `winner_is_sharpe` and `winner_oos_sharpe` are one entry per
    CSCV split, in `itertools.combinations(range(n_blocks), n_blocks // 2)`
    order -- the same order pbo() iterates splits in.

    After the D5 oldest-row drop, `pbo()` merges variants whose return
    series are bit-identical OVER THE ROWS CSCV ACTUALLY SCORES into one
    (B2): `distinct_variants` + `duplicates_collapsed` == the number of
    columns `returns` was given with, and `kept_columns` names which of
    those original columns survived, in the order they were kept.
    `distinct_variants` is the number of things that were actually tried,
    on the data PBO was computed from -- it, not the raw column count, is
    the N to pass as `n_trials` to `deflated_sharpe()` / `expected_max_
    sharpe()` and the N for the hypothesis ledger: a 200-variant sweep that
    collapses to 12 series distinct on the scored rows tested 12 things,
    not 200. Two columns that differ only in the rows D5 drops are still
    collapsed -- they are identical on every row CSCV ever looks at.

    Any `metric` passed to `pbo()` is called on this SAME collapsed matrix
    -- its columns are `kept_columns`, in that order, not the caller's
    original column positions. A metric that indexes per-variant data by
    column must go through `kept_columns[column]`, never `column` itself.

    `degradation_slope`'s no-information value is NOT 0. CSCV's IS/OOS
    halves are complementary by construction, which makes this slope
    strongly negative on pure noise -- it must never be read against 0 the
    way `pbo` itself can be read against the noise band in
    `tests/test_overfit_pbo_stats.py`.
    """

    pbo: float
    lambdas: Tuple[float, ...]
    n_splits: int
    n_blocks: int
    block_rows: int
    rows_dropped: int
    winner_is_sharpe: Tuple[float, ...]
    winner_oos_sharpe: Tuple[float, ...]
    degradation_slope: Optional[float]
    distinct_variants: int
    duplicates_collapsed: int
    kept_columns: Tuple[int, ...]


def per_period_sharpe(
    matrix: Any, column_labels: Optional[Sequence[int]] = None
) -> Any:
    """Per-column Sharpe ratio: mean over sample standard deviation (ddof=1).

    Not annualised -- the ratio is in whatever period the rows of `matrix`
    already are. `matrix` is a 2-D numpy array (rows x variants); the
    return is a 1-D numpy array, one score per column, higher is better.

    This is the default `metric` for `pbo()`, so that PBO can later rank
    variants the same way the luck bar does (R per holding period). It
    reads and writes numpy arrays but never imports numpy itself -- it only
    calls methods on the array it was handed, so it carries none of the
    "is numpy installed" question itself; whatever built `matrix` already
    answered that.

    `column_labels`, if given, is used ONLY to name a column in an error
    message -- D-C: `pbo()` calls this on its COLLAPSED matrix (after B2)
    and passes `kept_columns` here, so an error names the CALLER's original
    column (e.g. "column 2"), not that column's position inside the
    collapsed matrix `pbo()` actually scores (which could be "column 1" for
    the same column once an earlier one has been merged away). Left as
    `None` -- what a caller invoking this function directly gets -- the raw
    0-based position in `matrix` is the label, same as before.

    Raises ValueError, naming the column, in two cases:

      * a column is flat -- every row holds exactly the same value, checked
        as `max() == min()` rather than `sample standard deviation == 0`.
        A repeated value that isn't exact in binary (0.1, say) can still
        carry a sample standard deviation around 1e-17 out of numpy's
        variance arithmetic, never a bit-exact 0 -- `max() == min()` asks
        whether the column is constant directly, with no rounding involved.
      * a column's mean or standard deviation comes out non-finite --
        extreme values (returns scaled by 1e300, say) can overflow numpy's
        internal sum-of-squares to `inf` without ever tripping the flat
        check, which would otherwise let `pbo()` return a PBO computed from
        an `inf`-vs-`inf` comparison that means nothing.

    Either way, a Sharpe ratio a caller could act on doesn't exist, so this
    raises instead of silently returning inf, nan, or a meaningless number.
    """
    column_max = matrix.max(axis=0)
    column_min = matrix.min(axis=0)
    mean = matrix.mean(axis=0)
    sample_sd = matrix.std(axis=0, ddof=1)
    for column in range(matrix.shape[1]):
        label = column if column_labels is None else column_labels[column]
        if column_max[column] == column_min[column]:
            raise ValueError(
                "per_period_sharpe: column %d is flat (every value equals "
                "%r); its Sharpe ratio is undefined"
                % (label, float(column_max[column]))
            )
        if not (math.isfinite(mean[column]) and math.isfinite(sample_sd[column])):
            raise ValueError(
                "per_period_sharpe: column %d has a non-finite mean or "
                "standard deviation, most likely from overflow in values "
                "this large; its Sharpe ratio is undefined" % label
            )
    return mean / sample_sd


def _numpy() -> Any:
    """numpy, imported at CALL time with a message that says what to install.

    Guarded exactly as `luck_bar._numpy()` guards its own import: importing
    this module must never fail, or cost a measurable amount of time, on a
    machine that does not have numpy -- only calling `pbo()` should.
    """
    try:
        import numpy
    except ImportError as missing:        # pragma: no cover -- environment
        raise SystemExit(
            "overfit needs numpy to run CSCV over blocks of returns "
            "(pip3 install numpy): %s" % missing
        )
    return numpy


def _validate_n_blocks(n_blocks: int) -> None:
    """Refuses a bad `n_blocks` before any row is read or any split is built.

    `n_blocks=22` must raise here, not after C(22, 11) = 705,432 splits are
    half-built -- that combination count is why this check comes first and
    costs nothing.
    """
    if isinstance(n_blocks, bool) or not isinstance(n_blocks, int):
        raise ValueError("n_blocks must be an int, got %r" % (n_blocks,))
    if not (2 <= n_blocks <= MAX_BLOCKS):
        raise ValueError(
            "n_blocks must be between 2 and %d, got %d" % (MAX_BLOCKS, n_blocks)
        )
    if n_blocks % 2 != 0:
        raise ValueError("n_blocks must be even, got %d" % n_blocks)


def _returns_to_matrix(numpy: Any, returns: Sequence[Sequence[float]]) -> Any:
    """Validates `returns` and converts it to a finite, rectangular matrix.

    Checked here rather than left to numpy so the error names the actual
    problem (ragged rows, a stray NaN, the wrong number of dimensions)
    instead of numpy's own, less specific complaint about the input it was
    handed. Without the ndim check below, a 1-D array reached the bare
    `len(row)` call a few lines down and raised `TypeError: object of type
    'numpy.float64' has no len()`, and a 3-D array sailed through this
    function and only failed later, in `pbo()`, on `n_rows, n_variants =
    matrix.shape` with Python's generic "too many values to unpack" --
    neither names what was actually wrong with `returns`.
    """
    rows = list(returns)
    if not rows:
        raise ValueError("returns has no rows")

    for row in rows:
        if not hasattr(row, "__len__"):
            raise ValueError(
                "returns must be 2-D (rows of variants); got a 1-D input "
                "instead"
            )

    row_lengths = set(len(row) for row in rows)
    if len(row_lengths) != 1:
        raise ValueError(
            "returns is ragged: rows have lengths %s" % sorted(row_lengths)
        )

    # numpy.asarray(returns, ...) here -- instead of rows, the list already
    # built above -- used to raise a bare TypeError on a generator: list()
    # had already exhausted it, so numpy.asarray saw nothing left to read.
    matrix = numpy.asarray(rows, dtype=float)
    if matrix.ndim != 2:
        raise ValueError(
            "returns must be 2-D (rows x variants), got %d-D input with "
            "shape %r" % (matrix.ndim, matrix.shape)
        )
    if not numpy.isfinite(matrix).all():
        raise ValueError("returns contains a non-finite value (NaN or inf)")

    n_variants = matrix.shape[1]
    if n_variants < 2:
        raise ValueError(
            "returns must have at least 2 columns (variants), got %d"
            % n_variants
        )
    return matrix


def _validate_metric_scores(
    numpy: Any, scores: Any, n_variants: int, half_name: str
) -> Any:
    """Enforces the `metric` contract: 1-D, one score per variant, finite.

    A metric that returns the wrong shape or a NaN/inf score would produce
    a PBO that looks like a number but means nothing -- D9 makes that a
    loud ValueError instead.
    """
    scores = numpy.asarray(scores)
    if scores.ndim != 1 or scores.shape[0] != n_variants:
        raise ValueError(
            "metric must return a 1-D array of length %d for the %s half, "
            "got shape %r" % (n_variants, half_name, scores.shape)
        )
    if not numpy.isfinite(scores).all():
        raise ValueError(
            "metric returned a non-finite score on the %s half" % half_name
        )
    return scores


def _collapse_duplicate_columns(numpy: Any, matrix: Any) -> Any:
    """Merges variants whose return series are bit-identical into one (B2).

    Two columns holding exactly the same number in every row of `matrix`
    are one strategy counted twice, not two independent ideas -- without
    this, a real edge copied into several columns of a sweep beat its own
    copies in-sample and out-of-sample alike, reading PBO = 1.0 purely from
    self-agreement, never from surviving a test against anything else.
    `pbo()` calls this on the TRIMMED matrix, after the D5 oldest-row drop
    -- "bit-identical" means identical on the rows CSCV is about to score,
    not on whatever extra history `returns` happened to arrive with.

    The FIRST occurrence of a given series is the one kept; later
    duplicates are dropped. Returns `(deduped_matrix, kept_columns,
    duplicates_collapsed)`, where `kept_columns` is the ascending tuple of
    column indices -- into the matrix this function was CALLED with -- that
    survived.

    D-B: the fingerprint adds `0.0` to every value before hashing its bytes.
    `-0.0 == 0.0` is True -- they are the SAME number in IEEE 754 -- but
    their bit patterns differ, so `.tobytes()` alone read a column holding
    `-0.0` where its twin held `0.0` as two DISTINCT series and collapsed
    nothing, even though every comparison anyone would ever make on them
    agrees they're identical. Adding `0.0` to a signed zero produces `+0.0`
    in round-to-nearest (the default mode), and adding `0.0` to any other
    finite value leaves it bit-for-bit unchanged, so this normalises signed
    zero without disturbing anything else the fingerprint depends on.
    """
    n_variants = matrix.shape[1]
    kept_columns = []
    seen_columns = set()
    for column in range(n_variants):
        fingerprint = (matrix[:, column] + 0.0).tobytes()
        if fingerprint in seen_columns:
            continue
        seen_columns.add(fingerprint)
        kept_columns.append(column)
    duplicates_collapsed = n_variants - len(kept_columns)
    deduped_matrix = matrix[:, kept_columns]
    return deduped_matrix, tuple(kept_columns), duplicates_collapsed


def _ols_slope(xs: Sequence[float], ys: Sequence[float]) -> Optional[float]:
    """Slope of the line through (x, y), or None when every x is the same.

    A zero-spread x can't support a slope -- dividing by Sigma(x - x-bar)^2
    would divide by zero -- so that case is reported as None (D10) instead
    of raising, because "the winner's IS score never varied" is a fact
    about the run, not an error in it.
    """
    x_mean = statistics.fmean(xs)
    y_mean = statistics.fmean(ys)
    numerator = sum((x - x_mean) * (y - y_mean) for x, y in zip(xs, ys))
    denominator = sum((x - x_mean) ** 2 for x in xs)
    if denominator == 0:
        return None
    return numerator / denominator


def _validate_int_at_least(value: Any, floor: int, name: str) -> None:
    """Refuses anything that is not a plain int >= `floor`, naming `name`.

    `bool` is rejected even though `isinstance(True, int)` is true in
    Python -- a caller who passes `n_trials=True` almost certainly meant
    `1`, and letting it through would silently run DSR with one trial.
    """
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError("%s must be an int, got %r" % (name, value))
    if value < floor:
        raise ValueError("%s must be >= %d, got %d" % (name, floor, value))


def _validate_finite(value: float, name: str) -> None:
    if not math.isfinite(value):
        raise ValueError("%s must be finite, got %r" % (name, value))


def expected_max_sharpe(n_trials: int, var_trial_sharpes: float) -> float:
    """SR0: the Sharpe ratio the best of `n_trials` trials reaches on luck.

    ``SR0 = sqrt(V) * [(1 - g) * Phi_inv(1 - 1/N) + g * Phi_inv(1 - 1/(N*e))]``,
    g = the Euler-Mascheroni constant, Phi_inv = the standard normal's
    inverse CDF. This is the expected maximum of N correlated normal trial
    Sharpes, from Bailey & Lopez de Prado, "The Deflated Sharpe Ratio"
    (2014); Phi_inv is `statistics.NormalDist().inv_cdf` (D17 -- no
    hand-written approximation).

    `n_trials` (N) must be the number of DISTINCT things that were actually
    tried -- `PBOResult.distinct_variants` if the trials came from `pbo()`,
    never a raw column or run count. Two variants that produced the same
    return series tested one thing, not two; counting them as separate
    trials overstates how much luck had to work with.

    `var_trial_sharpes` (V) is the *observed* variance of the N trials' own
    Sharpe ratios, not assumed independence -- that is what makes this
    better than the textbook `sqrt(2 * ln(N))` bound for a parameter sweep.
    `sqrt(2 ln N)` charges every trial count the same expected-maximum
    penalty regardless of how the trials relate to each other, so it treats
    200 near-identical variants of one strategy exactly like 200 unrelated
    strategies. DSR instead measures how spread out the trials' Sharpes
    actually were: 200 near-identical variants have a small V (their
    Sharpes cluster together), so SR0 stays low and little of the observed
    Sharpe is deflated away; 200 genuinely independent strategies have a
    large V, so SR0 rises and more of the observed Sharpe is attributed to
    having simply tried more things. That is exactly the distinction a
    parameter sweep needs and `sqrt(2 ln N)` cannot make.

    Raises ValueError for: `n_trials` not an int >= 2; `var_trial_sharpes`
    not finite or negative.
    """
    _validate_int_at_least(n_trials, 2, "n_trials")
    _validate_finite(var_trial_sharpes, "var_trial_sharpes")
    if var_trial_sharpes < 0:
        raise ValueError(
            "var_trial_sharpes must be >= 0, got %r" % var_trial_sharpes
        )

    phi_inv = statistics.NormalDist().inv_cdf
    g = EULER_MASCHERONI
    bracket = (
        (1 - g) * phi_inv(1 - 1 / n_trials)
        + g * phi_inv(1 - 1 / (n_trials * math.e))
    )
    return math.sqrt(var_trial_sharpes) * bracket


def deflated_sharpe(
    sharpe: float,
    n_trials: int,
    var_trial_sharpes: float,
    n_obs: int,
    skew: float,
    kurtosis: float,
) -> float:
    """Probability the observed Sharpe beats what `n_trials` trials of luck
    would produce, after deflating it by `expected_max_sharpe()`.

    ``DSR = Phi( (SR - SR0) * sqrt(T - 1)
                 / sqrt(1 - skew*SR + ((kurtosis - 1) / 4) * SR**2) )``

    SR = `sharpe` (per-period, not annualised); SR0 = `expected_max_sharpe`
    on the same trials; T = `n_obs`, the number of per-period returns SR
    was computed from; Phi = the standard normal CDF. `n_trials` carries
    `expected_max_sharpe()`'s same requirement: the count of DISTINCT
    variants (`PBOResult.distinct_variants` if the trials came from
    `pbo()`), never a raw column count.
    (`statistics.NormalDist().cdf`, D17). The denominator is the standard
    error of a Sharpe ratio estimated from T observations with sample skew
    and *raw* (Pearson; normal = 3) kurtosis -- Mertens (2002) / Opdyke
    (2007) -- and `T - 1` rather than `T` matches that same source (D11).
    Source for the deflation itself: Bailey & Lopez de Prado (2014).

    Raises ValueError for: `n_trials` not an int >= 2; `n_obs` not an int
    >= 2; `var_trial_sharpes` not finite or negative (via
    `expected_max_sharpe`); `sharpe`, `skew` or `kurtosis` not finite;
    `kurtosis < 1 + skew**2` (the moment inequality every real distribution
    satisfies -- see below); or a radicand <= 0.

    With `kurtosis >= 1 + skew**2`, the radicand is bounded below by
    `(1 - skew*SR/2)**2 >= 0` and can only reach exactly 0 on that
    boundary, which is why the guard below is a *strict* `> 0` check on the
    radicand itself rather than trusting the moment inequality alone.
    """
    sr0 = expected_max_sharpe(n_trials, var_trial_sharpes)
    _validate_int_at_least(n_obs, 2, "n_obs")
    _validate_finite(sharpe, "sharpe")
    _validate_finite(skew, "skew")
    _validate_finite(kurtosis, "kurtosis")
    if kurtosis < 1 + skew ** 2:
        raise ValueError(
            "kurtosis must be >= 1 + skew**2 (got kurtosis=%r, skew=%r)"
            % (kurtosis, skew)
        )

    radicand = 1 - skew * sharpe + ((kurtosis - 1) / 4) * sharpe ** 2
    if radicand <= 0:
        raise ValueError(
            "deflated_sharpe: the standard-error radicand is %r, must be "
            "> 0 -- check sharpe, skew and kurtosis together" % radicand
        )

    standard_error = math.sqrt(radicand / (n_obs - 1))
    return statistics.NormalDist().cdf((sharpe - sr0) / standard_error)


def pbo(
    returns: Sequence[Sequence[float]],
    n_blocks: int = DEFAULT_BLOCKS,
    metric: Callable[[Any], Any] = per_period_sharpe,
) -> PBOResult:
    """Probability of backtest overfitting, by combinatorially symmetric CV.

    `returns` is T rows (time) by N columns (variants of the same strategy,
    e.g. different parameters), a list of rows or a 2-D numpy array. It is
    split into `n_blocks` contiguous blocks after dropping the oldest
    `T mod n_blocks` rows (so every block has the same length -- dropping
    from the start rather than the end keeps the most recent, most relevant
    history intact). For every way to choose half the blocks as in-sample:

      * the variant with the best in-sample `metric` score is the winner
        (ties go to the lowest column index);
      * the winner's out-of-sample rank among all N variants becomes a
        probability omega = rank / (N + 1) and a log-odds
        lambda = ln(omega / (1 - omega)). Rank is MID-RANK (D-A,
        30 Sep 2026, replacing D7's tie clause): r = 1 + (variants strictly
        below the winner's out-of-sample score) + (OTHER variants tied with
        it) / 2 -- a tie contributes half a rank, not a whole one and not
        none;
      * lambda <= 0 means the in-sample winner did no better than the
        out-of-sample median -- that split counts as overfit.

    PBO is the fraction of splits that counted as overfit. On pure noise,
    an in-sample winner has no real edge, so PBO should sit near the
    fraction implied by a uniform random rank; a PBO well above that says
    the strategy's ranking on this data doesn't survive being tested on
    data it wasn't picked to fit.

    `metric` takes a 2-D numpy array (rows x N) and returns a 1-D numpy
    array of N finite scores, higher is better; the default is
    `per_period_sharpe`. Source: Bailey, Borwein, Lopez de Prado & Zhu,
    "The Probability of Backtest Overfitting" (2017). `metric` is called on
    the COLLAPSED matrix (after B2, below) -- N here is `distinct_variants`,
    and the matrix's columns are `kept_columns`, in that order, NOT the
    caller's original column positions. A `metric` that closes over
    per-variant data addressed by column position (e.g. a lookup table of
    per-variant weights) must index that data by `kept_columns[column]`,
    never by `column` itself, or it silently scores the wrong variant's
    data once any column has been collapsed away.

    After the D5 oldest-row drop but before any split is built, columns that
    are bit-identical over every ROW CSCV ACTUALLY SCORES are merged into
    one (B2) -- see `PBOResult.distinct_variants`. That field, not
    `len(returns[0])`, is the N to pass as `n_trials` to
    `deflated_sharpe()` / `expected_max_sharpe()`: variants that only ever
    repeated an earlier one, on the data PBO was computed from, tested
    nothing extra. Deduping is deliberately done AFTER the drop, not on the
    raw input: two columns that differ only in the rows D5 drops are
    identical on every row CSCV ever looks at, and tie inside every split
    exactly as if they were duplicates of the raw input too -- deduping on
    the raw matrix missed that and let PBO = 1.0 straight back in.

    KNOWN LIMIT, not fixed here: ten NEAR-copies of ONE noise series --
    bit-identical everywhere except one row nudged by a single ULP in each
    copy, so B2's exact-bytes check doesn't merge them -- still read
    PBO = 1.0, correctly by D-A's own arithmetic: ten variants doing
    nothing but rediscovering the same series tie close to the winner's own
    out-of-sample score on almost every split, and `lambda = 0` counts as
    overfit. `pbo()` cannot fix this and should not try to: it sees only a
    (rows, variants) matrix of numbers, and nothing in that matrix says
    whether two columns are a genuinely different strategy that happens to
    score alike, or the SAME strategy's parameter nudged one step, because
    that fact lives in the parameter grid the columns came from, not in
    the numbers themselves. The place this is solvable is the HARNESS that
    builds `returns` before ever calling `pbo()` -- it knows the grid, so it
    can collapse variants that share identical parameters, or that produced
    identical selections, into one column first. That is exactly what B2
    does for exact duplicates, one step earlier, where the information to
    do it safely actually lives.

    Raises ValueError for: `n_blocks` not an even int in [2, 20]; fewer
    than 2 rows per block; fewer than 2 columns; fewer than 2 DISTINCT
    columns once bit-identical duplicates are merged; a ragged or
    non-finite `returns`; or a `metric` that returns the wrong shape or a
    non-finite score.
    """
    _validate_n_blocks(n_blocks)
    numpy = _numpy()
    matrix = _returns_to_matrix(numpy, returns)
    n_rows, _n_raw_variants = matrix.shape

    block_rows = n_rows // n_blocks
    rows_dropped = n_rows - n_blocks * block_rows
    if block_rows < 2:
        raise ValueError(
            "each of the %d blocks would hold only %d row(s); need at "
            "least 2 rows per block -- pass fewer blocks or more rows"
            % (n_blocks, block_rows)
        )

    # Drop the oldest rows_dropped rows (D5) FIRST, then collapse duplicate
    # columns (B2) on exactly the rows left -- the rows CSCV is about to
    # score -- not on the raw input. See the docstring note above for why.
    trimmed = matrix[rows_dropped:]
    trimmed, kept_columns, duplicates_collapsed = _collapse_duplicate_columns(
        numpy, trimmed
    )
    n_variants = trimmed.shape[1]
    if n_variants < 2:
        raise ValueError(
            "pbo: only %d distinct variant(s) remain, over the rows CSCV "
            "actually scores, after collapsing %d duplicate column(s) that "
            "repeated an earlier one exactly there; at least 2 distinct "
            "variants are needed to judge overfitting"
            % (n_variants, duplicates_collapsed)
        )

    blocks = [
        trimmed[i * block_rows:(i + 1) * block_rows] for i in range(n_blocks)
    ]

    # D-C: the default metric raises an error naming a flat or non-finite
    # column by its position in the matrix it was CALLED with -- which,
    # after B2's collapse above, is no longer the caller's own column
    # numbering. Calling per_period_sharpe directly here (instead of through
    # the generic `metric(...)`) lets pbo() hand it `kept_columns`, so the
    # column an error names is the caller's original one. A custom `metric`
    # has no such mapping available to pbo() -- it reports columns in
    # whatever numbering it chooses, on the matrix it was actually given.
    def score(half_matrix):
        if metric is per_period_sharpe:
            return per_period_sharpe(half_matrix, column_labels=kept_columns)
        return metric(half_matrix)

    half = n_blocks // 2
    lambdas = []
    winner_is_scores = []
    winner_oos_scores = []
    for in_sample_blocks in itertools.combinations(range(n_blocks), half):
        # itertools.combinations yields ascending tuples, and range() below
        # is already ascending, so both halves stay in time order without
        # an explicit sort.
        out_sample_blocks = tuple(
            b for b in range(n_blocks) if b not in in_sample_blocks
        )
        is_matrix = numpy.concatenate([blocks[b] for b in in_sample_blocks])
        oos_matrix = numpy.concatenate([blocks[b] for b in out_sample_blocks])

        is_scores = _validate_metric_scores(
            numpy, score(is_matrix), n_variants, "in-sample"
        )
        oos_scores = _validate_metric_scores(
            numpy, score(oos_matrix), n_variants, "out-of-sample"
        )

        # numpy.argmax returns the FIRST index of the maximum, which is
        # exactly "lowest column index on ties" (D8).
        winner = int(numpy.argmax(is_scores))
        winner_oos_score = float(oos_scores[winner])

        # D-A (replaces D7's tie clause, 30 Sep 2026): a variant OTHER
        # than the winner that ties the winner's own out-of-sample score
        # contributes HALF a rank, not a whole one (the old rule) and not
        # zero. `== winner_oos_score` also matches the winner against
        # itself, so that one match is subtracted before halving the rest.
        strictly_below = int((oos_scores < winner_oos_score).sum())
        tied_with_others = int((oos_scores == winner_oos_score).sum()) - 1
        rank = 1 + strictly_below + tied_with_others / 2
        omega = rank / (n_variants + 1)
        lambda_value = math.log(omega / (1 - omega))

        lambdas.append(lambda_value)
        winner_is_scores.append(float(is_scores[winner]))
        winner_oos_scores.append(winner_oos_score)

    n_splits = math.comb(n_blocks, half)
    overfit_splits = sum(1 for lam in lambdas if lam <= 0)

    return PBOResult(
        pbo=overfit_splits / n_splits,
        lambdas=tuple(lambdas),
        n_splits=n_splits,
        n_blocks=n_blocks,
        block_rows=block_rows,
        rows_dropped=rows_dropped,
        winner_is_sharpe=tuple(winner_is_scores),
        winner_oos_sharpe=tuple(winner_oos_scores),
        degradation_slope=_ols_slope(winner_is_scores, winner_oos_scores),
        distinct_variants=n_variants,
        duplicates_collapsed=duplicates_collapsed,
        kept_columns=kept_columns,
    )


def _validate_purge_inputs(n_obs: int, n_folds: int, label_span: int) -> None:
    """Refuses a bad input before a single fold boundary is computed.

    Each of `n_obs`, `n_folds` and `label_span` is checked for being a
    plain int (bool rejected, same reasoning as `_validate_int_at_least`)
    before any of them is used in a range check, so a caller who passes
    `n_folds=True` gets a message naming `n_folds`, not a confusing range
    error about "1 fold".
    """
    for value, name in (
        (n_obs, "n_obs"), (n_folds, "n_folds"), (label_span, "label_span")
    ):
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("%s must be an int, got %r" % (name, value))
    if not (2 <= n_folds <= n_obs):
        raise ValueError(
            "n_folds must satisfy 2 <= n_folds <= n_obs; got n_folds=%d, "
            "n_obs=%d" % (n_folds, n_obs)
        )
    if label_span < 0:
        raise ValueError("label_span must be >= 0, got %d" % label_span)


def _fold_boundaries(n_obs: int, n_folds: int) -> list:
    """Contiguous, half-open `[a, b)` bounds for every fold, in fold order.

    array_split convention (D13): every fold gets `n_obs // n_folds` rows,
    and the first `n_obs % n_folds` folds -- not the last -- get one extra
    row each, so the sizes never differ by more than one and the leftover
    rows aren't all dumped on the final fold.
    """
    base_size, remainder = divmod(n_obs, n_folds)
    boundaries = []
    start = 0
    for fold_index in range(n_folds):
        size = base_size + 1 if fold_index < remainder else base_size
        end = start + size
        boundaries.append((start, end))
        start = end
    return boundaries


def _train_test_for_fold(
    a: int, b: int, n_obs: int, label_span: int
) -> Any:
    """`(train, test)` for one fold `[a, b)`, exactly per the D13 formula.

    `test` is every row in the fold. `removed` is the purge-plus-embargo
    band on both sides of it -- the `h` rows immediately before `a` and the
    `h` rows immediately after `b - 1` -- clipped to the dataset so it never
    asks for a negative or out-of-range index. `train` is everything left:
    outside the fold and outside that removed band. Written as the literal
    set from the plan, rather than a single merged range, so this function
    reads as the same formula the docstring and the tests both state.
    """
    h = label_span
    test = list(range(a, b))
    removed = set(range(max(0, a - h), a)) | set(range(b, min(n_obs, b + h)))
    train = [i for i in range(n_obs) if i not in removed and not (a <= i < b)]
    return train, test


def purged_folds(n_obs: int, n_folds: int, label_span: int) -> Any:
    """Time-ordered CV folds with a purge-and-embargo band around each test set.

    `returns` (elsewhere in this module) is arranged so the label at bar t
    is formed from bars t+1 .. t+`label_span` -- a ten-day hold looking ten
    bars into its own future, so `label_span` = 10 at this project's hold.
    That is exactly why purging is not optional: any row within
    `label_span` bars of a test fold's edge has a label built partly from
    bars inside that test fold. Ordinary k-fold CV would train on that row
    and test on the bars its own label was computed from -- the model
    would, in effect, be graded on data it already saw the answer to. No
    amount of care in how the model is built or scored afterwards can
    undo that leak; it has to be kept out of the split in the first place,
    which is the only job this function does.

    For each fold `[a, b)`, `label_span` bars are removed from *both*
    sides: the `label_span` bars immediately before `a` (a purge, because
    their labels reach forward into the test fold) and the `label_span`
    bars immediately after `b - 1` (an embargo, because the test fold's
    own labels reach forward into them). Removing both sides is more
    conservative than a one-sided purge that removes only the rows whose
    labels overlap the test set -- the brief's "`label_span` bars either
    side" is this two-sided purge-plus-embargo, not a single-sided purge,
    and this function follows the brief (plan SOURCE VS BRIEF 15).

    Yields one `(train_idx, test_idx)` pair per fold, each an ascending
    tuple of row indices into `range(n_obs)`, folds in order. Folds are
    contiguous and half-open; sizes follow the `array_split` convention
    (see `_fold_boundaries`).

    Raises ValueError for: `n_obs`, `n_folds` or `label_span` not a plain
    int (bool rejected); `n_folds` outside `[2, n_obs]`; `label_span` < 0;
    or any fold whose training set would be empty once its purge-and-embargo
    band is removed. Because folds, purge and embargo are all fixed by
    `n_obs`, `n_folds` and `label_span` alone -- nothing here depends on the
    data itself -- every fold's training set can be checked before any fold
    is yielded, so an empty one is raised immediately rather than partway
    through iteration.
    """
    _validate_purge_inputs(n_obs, n_folds, label_span)
    boundaries = _fold_boundaries(n_obs, n_folds)

    for a, b in boundaries:
        train, _test = _train_test_for_fold(a, b, n_obs, label_span)
        if not train:
            raise ValueError(
                "purged_folds: fold [%d, %d) has an empty training set at "
                "label_span=%d (n_obs=%d, n_folds=%d) -- use fewer folds, "
                "a smaller label_span, or more observations"
                % (a, b, label_span, n_obs, n_folds)
            )

    def _generate():
        for fold_a, fold_b in boundaries:
            fold_train, fold_test = _train_test_for_fold(
                fold_a, fold_b, n_obs, label_span
            )
            yield tuple(fold_train), tuple(fold_test)

    return _generate()
