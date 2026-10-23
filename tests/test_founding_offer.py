"""Owner decision 23 Oct (Lead, C-18 public item): the founding offer is "first 100 buyers".

- /pricing/ price history gains a dated row (23 Oct 2026); the 16 Oct row is kept as published; rows stay newest first.
- No page and no script shows how many are left, a countdown or urgency wording (lint claim:scarcity, banned.toml
  [claims] scarcity); a static "first 100 buyers" line is fine."""
import datetime as dt
import os
import re
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402
import lint as L  # noqa: E402
from test_c14_legal_copy import _build  # noqa: E402

ROW = ("The founding price of the habit report, $39, is for its first 100 buyers; people on the waitlist are emailed "
       "first when it goes on sale. No price changed.")
OLD_ROW = "Founding price for the first 100 on the trader waitlist added."


@pytest.fixture(scope="module")
def builds(tmp_path_factory):
    t = tmp_path_factory.mktemp("founding")
    out = {}
    for name, paid in (("free", False), ("paid", True)):
        r, o = _build(t, name, paid=paid)
        assert r.returncode == 0, r.stderr
        out[name] = o
    return out


def history_rows(out):
    html = open(B.out_file(str(out), "/pricing/"), encoding="utf-8").read()
    body = re.search(r'(?s)<h2 id="history">.*?<tbody>(.*?)</tbody>', html).group(1)
    return [(re.sub(r"<[^>]+>", "", d).strip(), re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", c)).strip())
            for d, c in re.findall(r"(?s)<tr[^>]*><td>(.*?)</td><td>(.*?)</td></tr>", body)]


@pytest.mark.parametrize("which", ["free", "paid"])
def test_history_row_added_old_row_kept_newest_first(builds, which):
    rows = history_rows(builds[which])
    assert [c for d, c in rows if d == "23 Oct 2026"] == [ROW]
    assert ("16 Oct 2026", OLD_ROW) in rows                          # history is not rewritten
    dates = [dt.datetime.strptime(d, "%d %b %Y").date() for d, _ in rows]
    assert dates == sorted(dates, reverse=True), rows
    assert len(rows) == 6


def test_the_row_is_built_from_prices_json():
    src = open(os.path.join(REPO, "site", "templates", "pages", "pricing.html"), encoding="utf-8").read()
    row = re.search(r'(?s)<tr id="history-founding">.*?</tr>', src).group(0)
    assert "{{ r.price_usd|usd }}" in row and "{{ prices.rules.founding_limit }}" in row and "$39" not in row


@pytest.mark.parametrize("which", ["free", "paid"])
def test_no_scarcity_wording_in_either_build(builds, which, monkeypatch):
    monkeypatch.setenv("DT_PRIVATE_TOML", str(builds[which].parent / f"{which}-private.toml"))
    problems = L.lint_build(str(builds[which]), paid=which == "paid")
    assert [p for p in problems if p[0] == "claim:scarcity"] == [], problems
    assert problems == [], problems


@pytest.mark.parametrize("bad", [
    "Only 7 spots left!", "Only a few left at the founding price.", "12 places left", "3 founding spots remaining",
    "63 of 100 sold", "41/100 taken", "Spots are filling fast.", "Selling fast", "Almost gone", "Hurry: founding price",
    "Last chance for $39", "Act now", "Offer ends in 3 days", "Countdown: 02:14:09", "while spots last",
    "Plus que 12 places", "Il reste 3 places restantes", "Compte à rebours", "Dernière chance",
])
def test_scarcity_phrases_are_caught(bad):
    assert any(r == "claim:scarcity" for r, _, _ in L.lint_text(bad, "planted")), bad


@pytest.mark.parametrize("ok", [
    "$39 founding price for the first 100 buyers.", ROW, OLD_ROW, "One re-test left on this purchase",
    "Left out: 56 trades opened more than 519 weeks", "Win rate (break-even trades left out)",
    "every one of their samples ends in 2016 or earlier", "The founding offer is full.",
])
def test_static_lines_pass(ok):
    assert not [p for p in L.lint_text(ok, "ok", paid=True) if p[0] == "claim:scarcity"], ok


def test_a_counter_in_a_script_is_caught(builds, tmp_path, monkeypatch):
    c = tmp_path / "c"
    shutil.copytree(builds["paid"], c)
    (c / "static" / "js" / "counter.js").write_text("el.textContent = `Only ${n} spots left`;\n", encoding="utf-8")
    monkeypatch.setenv("DT_PRIVATE_TOML", str(builds["paid"].parent / "paid-private.toml"))
    assert any(p[0] == "claim:scarcity" and p[1] == "/static/js/counter.js" for p in L.lint_build(str(c), paid=True))
