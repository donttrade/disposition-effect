"""Batch F2: DT-1 parity with the paid engine.

* test_golden_*: the public check. partner/dt1_features.py must give the golden file's F1-F6 and the
  engine's group counts on every window. Needs nothing private.
* test_live_*: re-runs habits.mjs (node) and the private Python mirror on the corpus and confirms that
  the golden file is what they give today. Skipped when the private repo or node is absent."""
import hashlib
import json
import math
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "partner"))
sys.path.insert(0, os.path.join(HERE, "parity"))
import dt1_features as F  # noqa: E402

GOLDEN = os.path.join(REPO, "partner", "parity", "dt1_golden.json")
PRIVATE = os.environ.get("DT_PRIVATE_REPO_RO", os.path.join(REPO, "..", "delivery-39-private"))


def _close(a, b):
    if a is None or b is None:
        return a is None and b is None
    return a == b or abs(a - b) <= 1e-12 * max(abs(a), abs(b))


@pytest.fixture(scope="module")
def golden():
    with open(GOLDEN, encoding="utf-8") as fh:
        return json.load(fh)


def test_golden_has_enough_windows(golden):
    assert len(golden["windows"]) >= 300
    assert golden["engine_method"] == F.ENGINE_METHOD
    kinds = {w["id"].split(":")[1] for w in golden["windows"] if w["id"].startswith("gen:")}
    assert {"merges", "tie900", "no_winners", "no_losers", "one_symbol", "near_dates_only", "dupkey"} <= kinds


def test_golden_features_match_public_code(golden):
    for w in golden["windows"]:
        f, counts = F.features_from_rows(w["rows"])
        for k in F.FEATURES:
            assert _close(f[k], w["expected"][k]), (w["id"], k)
        e = w["engine"]
        assert counts["revenge"] == (e["revenge"]["n_a"], e["revenge"]["n_b"]), w["id"]
        assert counts["tilt"] == (e["tilt"]["n_a"], e["tilt"]["n_b"]), w["id"]
        assert counts["size_up"][:2] == (e["size_up"]["n_a"], e["size_up"]["n_b"]), w["id"]
        assert counts["size_up"][2] == e["size_up"]["dollars_n_trades"], w["id"]
        assert counts["oversized"] == (e["oversized_loss"]["n_a"], e["oversized_loss"]["n_b"]), w["id"]
        assert counts["hold_gap"] == (e["hold_gap"]["n_a"], e["hold_gap"]["n_b"]), w["id"]
        assert counts["n_trades"] == w["n_trades"]


def _live_ready():
    return os.path.exists(os.path.join(PRIVATE, "src", "core", "habits.mjs")) and shutil.which("node")


@pytest.mark.skipif(not _live_ready(), reason="private engine or node not present")
def test_live_engine_agrees_and_is_untouched(golden):
    import build_dt1_golden as B
    with open(os.path.join(PRIVATE, "src", "core", "habits.mjs"), "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == golden["engine_sha256"]
    corpus = B.build_corpus(PRIVATE)
    bad, fresh, method = B.compare(PRIVATE, corpus)
    assert bad == []
    assert method == F.ENGINE_METHOD
    assert [g["id"] for g in fresh] == [w["id"] for w in golden["windows"]]
    for g, w in zip(fresh, golden["windows"]):
        assert g["rows"] == w["rows"]
    diff = subprocess.run(["git", "-C", PRIVATE, "diff", "--quiet", "--", "src/core/habits.mjs"])
    assert diff.returncode == 0


def test_golden_names_the_shipped_dt1_features(golden):
    """31 Oct (Tester, slice 1 B1): the golden's dt1_features_sha256 is the shipped file's hash, so it cannot go stale
    silently (fill_hashes.py --check refuses too)."""
    with open(os.path.join(REPO, "partner", "dt1_features.py"), "rb") as fh:
        assert hashlib.sha256(fh.read()).hexdigest() == golden["dt1_features_sha256"]
