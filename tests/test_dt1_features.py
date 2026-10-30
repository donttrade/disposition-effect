"""Batch F1: partner/dt1_features.py on hand-worked windows, plus the verbatim-copy check against the private
engine mirror (skipped when the private repo is not next to this one)."""
import inspect
import math
import os
import sys
from decimal import Decimal as D

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "..", "partner"))
import dt1_features as F  # noqa: E402

PRIVATE_REF = os.environ.get("DT_PRIVATE_HABITS_REF",
                             os.path.join(HERE, "..", "..", "delivery-39-private", "reference", "habits_ref.py"))
PUBLIC_REF = os.path.join(HERE, "reference", "engine_ref.py")
T = 1_700_000_000 - (1_700_000_000 % 86400) + 3600 * 9    # 09:00 on some day, whole seconds


def trade(open_s, hold, pnl, size="1", sym="EURUSD", d=1):
    return {"open_s": open_s, "close_s": open_s + hold, "symbol": sym, "direction": d, "size": D(size),
            "pnl": D(str(pnl))}


def spaced(pnls, gap=3600, hold=600, sizes=None, start=T):
    out = []
    for k, p in enumerate(pnls):
        out.append(trade(start + k * gap, hold, p, size=(sizes[k] if sizes else "1")))
    return out


# ------------------------------------------------------------ verbatim copies

def _code_lines(src):
    out = []
    for ln in src.splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith('"""') or s.startswith("def "):
            continue
        out.append(s.split("  #")[0].rstrip())
    return out


COPIES = {   # function in dt1_features -> (file, first line, last line)
    "add": ("private", 160, 164), "_round_half_up": ("private", 179, 181),
    "is_date_only_row": ("private", 184, 186), "count_date_only": ("private", 189, 190),
    "is_dates_only": ("private", 193, 195), "merge_rows": ("private", 208, 227), "prepare": ("private", 230, 247),
    "prior_index": ("private", 254, 259), "ratio": ("private", 806, 807), "revenge_groups": ("private", 845, 860),
    "tilt_groups": ("private", 909, 921), "size_up_groups": ("private", 873, 889),
    "oversized_parts": ("private", 935, 943), "hold_gap_parts": ("private", 811, 816),
    "median": ("public", 3387, 3394),
}


# The only lines in the partial copies that are not on a source line: size_up's dollars items, which the
# source builds inline in its habit(...) call on line 889 (the same comprehension).
OWN_LINES = {'big = [t for t in a if t["q"] >= 1.5]'}


@pytest.mark.parametrize("name", sorted(COPIES))
def test_copied_lines_are_verbatim(name):
    which, a, b = COPIES[name]
    path = PRIVATE_REF if which == "private" else PUBLIC_REF
    if not os.path.exists(path):
        pytest.skip("source not present: " + path)
    with open(path, encoding="utf-8") as fh:
        src = fh.read().splitlines()[a - 1:b]
    src_lines = [ln.replace("E.median(", "median(") for ln in _code_lines("\n".join(src))]
    ours = _code_lines(inspect.getsource(getattr(F, name)))
    extra = [ln for ln in ours if ln not in src_lines and not ln.startswith("return ") and ln not in OWN_LINES]
    assert not extra, extra
    # every source line of a full copy is present, in order
    if name not in ("size_up_groups", "oversized_parts", "hold_gap_parts"):
        assert [ln for ln in ours] == src_lines


def test_source_hash_matches_header():
    if not os.path.exists(PRIVATE_REF):
        pytest.skip("private repo not present")
    import hashlib
    with open(PRIVATE_REF, "rb") as fh:
        h = hashlib.sha256(fh.read()).hexdigest()
    assert h in F.__doc__


# ------------------------------------------------------------ hand-worked windows

def test_reentry_900_second_boundary():
    # trade 0 loses and closes at T+600; trade 1 opens exactly 900 s later (in A); trade 2 opens 960 s after
    # trade 1's losing close (not in A)
    tr = [trade(T, 600, -10), trade(T + 1500, 60, -5), trade(T + 1560 + 960, 60, 3)]
    tr += spaced([1] * 27, start=T + 86400)
    w = F.account_window(tr)
    assert w["status"] == "ok"
    ra = w["counts"]["revenge"]
    assert ra == (1, 28)
    assert w["features"]["reentry_share"] == pytest.approx(1 / 29)


def test_merge_same_symbol_direction_minute():
    tr = [trade(T, 600, -10, size="1"), trade(T + 30, 900, -5, size="2")]      # same minute, same symbol, long
    tr += spaced([2, -1] * 15, start=T + 86400)
    m = F.merge_raw(tr)
    assert len(m) == 31 and m[0]["n_raw"] == 2 and m[0]["pnl"] == D("-15") and m[0]["size"] == D("3")
    assert m[0]["h"] == 870 or m[0]["h"] == 900   # longest hold: 900 - 30 = 870 s vs 600 s
    w = F.account_window(tr)
    assert w["counts"]["n_trades"] == 30


def test_no_winners_undefines_ratio_features():
    tr = spaced([-1] * 30)
    f = F.account_window(tr)["features"]
    assert f["hold_gap_ratio"] is None and f["size_after_loss_ratio"] is None
    assert f["streak_share"] == pytest.approx(28 / 29)
    assert f["large_loss_share"] == 0.0


def test_no_losers_undefines_loss_features():
    f = F.account_window(spaced([1] * 30))["features"]
    assert f["large_loss_share"] is None and f["size_after_loss_share"] is None
    assert f["reentry_share"] == 0.0 and f["streak_share"] == 0.0
    assert F.n_defined(f) == 2


def test_size_after_loss_within_window_only():
    pn = [1, -1] * 15
    sz = ["1", "1"] * 15
    sz[2] = "4"     # trade 2 follows a loss (trade 1) and is 4x the median size
    base = spaced(pn, sizes=sz)
    later = spaced([1] * 20, start=T + 30 * 3600, sizes=["1000"] * 20)   # huge sizes AFTER W
    a = F.account_window(base)["features"]
    b = F.account_window(base + later)["features"]
    assert a == b     # nothing after trade 30 changes a feature (the look-ahead rule)
    assert a["size_after_loss_share"] == pytest.approx(1 / 14)   # 14 trades follow a loss inside W


def test_large_loss_and_hold_gap():
    pn = [-1] * 9 + [-5] + [2] * 20
    tr = []
    for k, p in enumerate(pn):
        tr.append(trade(T + k * 3600, 1200 if p < 0 else 600, p))
    f = F.account_window(tr)["features"]
    assert f["large_loss_share"] == pytest.approx(1 / 30)
    assert f["hold_gap_ratio"] == pytest.approx(math.log(2.0))


def test_ties_in_close_order_use_open_then_input():
    a = trade(T, 600, -1)
    b = trade(T + 300, 300, 1, sym="GBPUSD")   # closes at the same second as a
    tr = [b, a] + spaced([1] * 29, start=T + 86400)
    w = F.account_window(tr)
    assert w["window"][0]["pnl"] == D("-1")      # a opened first, so it is first by close


def test_dates_only_window_is_flagged():
    day0 = T - 9 * 3600
    tr = [trade(day0 + k * 86400, 86400, 1 if k % 2 else -1) for k in range(2)]
    tr += spaced([1, -1] * 14, start=T + 3 * 86400)
    assert F.account_window(tr)["status"] == "dates_only"          # 2 of 30 rows = 6.7% >= 5%
    tr2 = tr[:1] + spaced([1, -1] * 15, start=T + 3 * 86400)[:29]
    assert F.account_window(tr2)["status"] == "ok"                 # 1 of 30 = 3.3% < 5%


def test_short_account():
    assert F.account_window(spaced([1] * 29))["status"] == "short"


def test_dt1_scores_percentiles():
    fl = [dict(zip(F.FEATURES, v)) for v in ((0.1, 0.2, None, 0.3, 0.1, 0.0),
                                              (0.2, 0.2, 0.5, 0.1, None, 0.1),
                                              (0.3, 0.1, -0.5, 0.2, 0.2, None))]
    s = F.dt1_scores(fl)
    # F1 pct: 1/6, 3/6, 5/6; F2: ties 0.2,0.2 -> (2.5-0.5)/3 = 2/3 each, 0.1 -> 1/6
    assert s[0] == pytest.approx((1 / 6 + 2 / 3 + 5 / 6 + 1 / 4 + 1 / 4) / 5)
    assert all(0 < v < 1 for v in s)
