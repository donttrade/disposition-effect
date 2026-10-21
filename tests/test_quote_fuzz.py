"""F-B2: a stray quote mark never changes the result silently.

Every mutation of a valid file (a quote inserted at each position, a quote deleted, random
pairs) must either fail loudly with an engine error, or give exactly the clean file's
trades and warnings. Before the fix, one stray quote in an all-quoted file merged the next
row into a note and 30 of 40 trades vanished behind a W_OPEN_POSITIONS warning.
"""
import json
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "reference"))
sys.path.insert(0, HERE)
import engine_ref as E  # noqa: E402
import quote_fuzz as Q  # noqa: E402


def outcome(text):
    try:
        r = E.parse_file(text.encode())
    except E.EngineError as e:
        return ("error", e.code)
    return ("ok", json.dumps([r["trades"], r["warnings"]], sort_keys=True))


@pytest.mark.parametrize("name", sorted(Q.bases()))
def test_stray_quotes_fail_loudly_or_change_nothing(name):
    base = Q.bases()[name]
    clean = outcome(base)
    assert clean[0] == "ok" and len(json.loads(clean[1])[0]) == 40
    loud = 0
    for label, text in Q.mutations(base, seed=len(name)):
        got = outcome(text)
        if got[0] == "error":
            loud += 1
            continue
        assert got == clean, (name, label)
    assert loud > 1000  # the mutations do reach the parser's error paths
