"""Free expectancy check: the skew guard of ARCHITECT-STATS-AMENDMENT-2026-10-21 section 4.

The 41 vectors in fixtures/noise/guard_vectors.json are the Architect's parity vectors
(free-parity.mjs + find-addone.mjs, same seeds) with the outputs of his line-by-line
transcription (lib/free-spec.mjs) at the production N = 10,000. Here the Python reference must
equal them bit for bit; test_engine_golden.py checks the browser engine against the same file in
4 time zones / locales, so JS = Python = expected.
"""
import json
import math
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import engine_ref as E  # noqa: E402

VECTORS = os.path.join(HERE, "fixtures", "noise", "guard_vectors.json")
LABEL = {"tooFew": "not enough trades to tell", "real": "distinguishable from noise", "noise": "may be noise"}


def load():
    with open(VECTORS, encoding="utf-8") as f:
        return json.load(f)


def as_check(e, x):
    """The Architect's transcription output, in NoiseCheck form (every field compared exactly)."""
    return {"stat": "expectancy", "method": "bootstrap-t", "n_a": len(x), "n_b": None,
            "value": _mean(x), "p": e["p"], "label": LABEL[e["label"]],
            "skew": e["skew"], "guard": e["guard"], "n_needed": e.get("n_needed"), "extreme": e.get("extreme"),
            "p_unguarded": e.get("p_unguarded")}


def bits(v):
    """The exact double (None stays None): JSON gives 0 for a JS zero, Python 0.0."""
    return None if v is None else float(v).hex()


def _mean(x):
    s = 0.0
    for v in x:
        s += v
    return s / len(x)


def test_vectors_cover_every_branch():
    d = load()
    assert len(d["vectors"]) == 41
    kinds = {}
    for e in d["expected"]:
        k = e["guard"] or e["label"]
        kinds[k] = kinds.get(k, 0) + 1
    assert kinds == {"noise": 14, "skew_small_n": 11, "real": 11, "skew_one_more": 5}, kinds
    skews = [e["skew"] for e in d["expected"] if e["guard"]]
    assert min(skews) < 0 < max(skews)            # both skew directions are guarded somewhere


def test_reference_equals_architect_vectors_bit_for_bit():
    d = load()
    for i, (x, e) in enumerate(zip(d["vectors"], d["expected"])):
        got = E.check_expectancy(x, E.SEED_BASE)
        want = as_check(e, x)
        assert got == want, (i, got, want)
        for k in ("p", "skew", "p_unguarded", "value"):
            assert bits(got[k]) == bits(want[k]), (i, k)


def test_reference_mirror_and_small_n_rules():
    """F-5 on the reference (small B for speed), plus the n_needed rule at the boundary."""
    x = [-25.0] * 27 + [400.0, 180.0, 95.0, -25.0, -25.0]   # mean > 0? no: check the sign below
    for v in (x, [-a for a in x]):
        r = E.check_expectancy(v, E.SEED_BASE, n_boot=199)
        m = E.check_expectancy([-a for a in v], E.SEED_BASE, n_boot=199)
        assert (m["label"], m["guard"], m["n_needed"]) == (r["label"], r["guard"], r["n_needed"])
        assert m["skew"] == -r["skew"] and m["p_unguarded"] == r["p_unguarded"] and m["p"] == r["p"]
    r = E.check_expectancy(x, E.SEED_BASE, n_boot=199)
    g1 = r["skew"]
    against = (r["value"] > 0 and g1 <= -1) or (r["value"] < 0 and g1 >= 1)
    if against and len(x) < 10 * g1 * g1:
        assert r["guard"] == "skew_small_n" and r["n_needed"] == math.floor(10 * g1 * g1) + 1 and r["p"] is None
    assert E.check_expectancy(x[:29], E.SEED_BASE)["skew"] is None   # under 30: nothing computed


def test_all_equal_file_has_zero_skew_and_no_guard():
    r = E.check_expectancy([25.0] * 40, E.SEED_BASE, n_boot=199)
    assert r["skew"] == 0 and r["guard"] is None and r["label"] == "distinguishable from noise"


def test_guard_wording_passes_the_lint():
    """F-7: every new free-page string passes checks/lint.py with the current banned.toml."""
    from lint import lint_text
    js = ("import * as N from './site/static/js/engine/noise.js';"
          "process.stdout.write(JSON.stringify({t: N.EXPECTANCY_GUARD_TEXT, f: N.FREE_CHECKS_FOOTNOTE,"
          " s: N.guardSentence({guard: 'skew_one_more', value: -3, extreme: 412.5, n_needed: null}, (v) => '$' + v),"
          " a: N.guardSentence({guard: 'skew_small_n', value: 2, extreme: null, n_needed: 57})}))")
    out = json.loads(subprocess.run(["node", "--input-type=module", "-e", js], cwd=REPO, capture_output=True,
                                    text=True, check=True).stdout)
    texts = [out["f"], out["s"], out["a"]] + [v for g in out["t"].values() for v in g.values()]
    assert len(texts) == 7
    for t in texts:
        assert lint_text(t) == [], (t, lint_text(t))
    assert out["s"] == ("Not enough trades to tell. With one more trade the size of this file's largest win ($412.5), "
                        "the average would be within what chance alone produces.")
    assert "at least 57 trades" in out["a"] and "a few large losses" in out["a"]
