"""The Lead's decision (23 Oct): the re-test sentence ("Your re-test runs on the version of the report that is live
when you run it; every change is dated on the corrections page") is true from the first sale. /corrections/ carries
a dated "Habit report: method versions" table (site/config/report_methods.json), outside the frozen corrections log,
and the build refuses to run when the report page's METHOD_VERSION (wording.js, which smoke D-6 holds equal to the
Worker's) has no entry. The server's own METHOD_VERSION (dt-private src/core/habits.mjs) must match it too."""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from lint import lint_text, visible_text  # noqa: E402

PRIVATE = os.environ.get("DT_PRIVATE_REPO") or os.path.join(os.path.dirname(REPO), "dt-private")
METHODS = os.path.join(REPO, "site", "config", "report_methods.json")
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def method_of(path, pattern):
    m = re.search(pattern, open(path, encoding="utf-8").read(), re.M)
    assert m, path
    return m.group(1)


def page_method():
    return method_of(os.path.join(REPO, "site", "static", "js", "paid", "wording.js"),
                     r"^export const METHOD_VERSION = '([^']+)';$")


def entries():
    return json.load(open(METHODS, encoding="utf-8"))["entries"]


def method_rows(html):
    sec = html[html.index('id="report-method"'):]
    body = re.search(r"(?s)<tbody>(.*?)</tbody>", sec).group(1)
    return [[re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"(?s)<td>(.*?)</td>", tr)]
            for tr in re.findall(r"(?s)<tr>(.*?)</tr>", body)]


def test_the_built_corrections_page_dates_the_report_method_the_page_accepts(built_site):
    html = open(os.path.join(built_site["out"], "corrections", "index.html"), encoding="utf-8").read()
    rows = method_rows(html)
    mv = page_method()
    hit = [r for r in rows if r[1] == mv]
    assert len(hit) == 1, (mv, rows)
    y, m, d = mv[:10].split("-")
    e = next(x for x in entries() if x["method"] == mv)
    assert hit[0][0] == f"{int(e['date'][8:])} {MONTHS[int(e['date'][5:7]) - 1]} {e['date'][:4]}"
    assert html.index("<!--frozen:end-->") < html.index('id="report-method"'), "outside the frozen log"
    for r in rows:
        assert lint_text(r[3]) == [] and lint_text(r[3], "methods", paid=True) == [], r[3]


def test_the_corrections_count_is_still_the_corrections_log(built_site):
    html = open(os.path.join(built_site["out"], "corrections", "index.html"), encoding="utf-8").read()
    frozen = html[html.index("<!--frozen:start-->"):html.index("<!--frozen:end-->")]
    n = len(re.findall(r"<tr\b", re.search(r"(?s)<table.*?<tbody>(.*?)</tbody>", frozen).group(1)))
    for rel in ("for-firms/index.html",):
        t = re.sub(r"\s+", " ", visible_text(open(os.path.join(built_site["out"], rel), encoding="utf-8").read()))
        assert f"{n} corrections, dated and logged" in t, rel


@pytest.mark.skipif(not os.path.isfile(os.path.join(PRIVATE, "src", "core", "habits.mjs")), reason="dt-private (server) not present")
def test_the_server_method_equals_the_page_method_and_has_a_dated_entry():
    # DT-2 (dt-private E1): the server's line may carry a trailing comment
    server = method_of(os.path.join(PRIVATE, "src", "core", "habits.mjs"), r"^export const METHOD_VERSION = '([^']+)';(?:\s*//.*)?$")
    assert server == page_method()
    assert server in {e["method"] for e in entries()}


def test_a_build_without_an_entry_for_the_page_method_fails(tmp_path):
    d = json.load(open(METHODS, encoding="utf-8"))
    d["entries"] = [e for e in d["entries"] if e["method"] != page_method()] or [
        {"date": "2026-10-22", "method": "2026-10-22.stats0", "text": "An older version."}]
    p = tmp_path / "methods.json"
    p.write_text(json.dumps(d), encoding="utf-8")
    env = {**os.environ, "DT_OUT": str(tmp_path / "out"), "DT_REPORT_METHODS_JSON": str(p)}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode != 0
    assert f"the report page's METHOD_VERSION {page_method()} has no dated entry" in r.stdout + r.stderr


def test_the_frozen_dt1_method_keeps_its_entry_and_no_entry_has_a_placeholder(tmp_path):
    """DT-2 dual accept: wording-stats2f.js still words DT-1 reports, so its method needs its dated entry too; and the
    DT-2 entry is published only with every figure filled (plan §11: the build refuses a placeholder)."""
    assert "2026-10-23.stats2f" in {e["method"] for e in entries()}
    dt2 = next(e for e in entries() if e["method"] == page_method())
    assert dt2["name"] == "DT-2" and "{" not in dt2["text"]
    assert "at least 5 trades in both groups it compares (was 30)" in dt2["text"]
    d = json.load(open(METHODS, encoding="utf-8"))
    for name, change in (("frozen", lambda d: d.update(entries=[e for e in d["entries"] if e["method"] != "2026-10-23.stats2f"])),
                         ("placeholder", lambda d: d["entries"][0].update(text=d["entries"][0]["text"] + " Measured: {x} in 100."))):
        dd = json.loads(json.dumps(d))
        change(dd)
        p = tmp_path / f"{name}.json"
        p.write_text(json.dumps(dd), encoding="utf-8")
        env = {**os.environ, "DT_OUT": str(tmp_path / name), "DT_REPORT_METHODS_JSON": str(p)}
        env.pop("DT_DEV", None)
        r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
        assert r.returncode != 0, name
        want = "METHOD_VERSION 2026-10-23.stats2f has no dated entry" if name == "frozen" else "has an unfilled placeholder"
        assert want in r.stdout + r.stderr, (name, r.stdout + r.stderr)
