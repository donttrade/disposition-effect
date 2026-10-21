"""F-B1 / F-D2 property tests on the Python reference: an export that starts in the
middle of a position never produces a trade that did not happen.

Each case is a random true history on a netting account (IBKR O / C / C;O codes, see
lots_gen.py), cut at a random start. The engine's trades must all be true trades that
open inside the export. Without same-second fills and reversals the engine must find
every one of them (the carried position is the only thing left out).
"""
import os
import random
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, HERE)
import engine_ref as E  # noqa: E402
import lots_gen as G  # noqa: E402


def run(fills, cut):
    try:
        return E.parse_file(G.export(fills, cut))
    except E.EngineError as e:
        assert e.code in ("E_NO_CLOSED_TRADES", "E_HEADER_ONLY"), e.code
        return {"trades": [], "warnings": []}


def cuts(fills, rng, n=6):
    times = sorted({f["ts"] for f in fills})
    return [times[0]] + [rng.choice(times) for _ in range(n)]


@pytest.mark.parametrize("seed", range(150))
def test_plain_codes_find_exactly_the_window_trades(seed):
    fills, trades = G.history(seed)
    rng = random.Random(seed)
    for cut in cuts(fills, rng):
        res = run(fills, cut)
        assert G.engine_keys(res) == G.window_truth(trades, cut), (seed, cut)
        codes = {w["code"] for w in res["warnings"]}
        assert "W_AMBIGUOUS_FILLS" not in codes, (seed, cut)
        assert "W_OPEN_POSITIONS" not in codes, (seed, cut)


@pytest.mark.parametrize("seed", range(150))
def test_same_second_and_reversals_never_invent_a_trade(seed):
    fills, trades = G.history(seed, n_symbols=3, n_trades=8, ties=True, reversals=True)
    rng = random.Random(seed)
    for cut in cuts(fills, rng):
        if not G.visible(fills, trades, cut):
            continue
        res = run(fills, cut)
        extra = G.engine_keys(res) - G.window_truth(trades, cut)
        assert not extra, (seed, cut, sorted(extra))
        for t in res["trades"]:
            assert t["hold_s"] >= 0, (seed, cut, t)


def test_full_history_is_read_whole():
    # From the first fill there is nothing carried: every true trade, no warning about it.
    for seed in range(40):
        fills, trades = G.history(seed, n_symbols=3, n_trades=8, reversals=True)
        res = run(fills, fills[0]["ts"])
        assert G.engine_keys(res) == G.window_truth(trades, fills[0]["ts"]), seed
        assert not {"W_OPEN_AT_START", "W_AMBIGUOUS_FILLS"} & {w["code"] for w in res["warnings"]}, seed
