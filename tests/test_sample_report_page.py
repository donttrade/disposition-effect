"""Delivery plan C-12 final (Tester T-3 T3-E): with paid_report on, /sample-report/ is a real habit report.
* The page embeds site/config/sample-report.report.json, which equals dt-private analyse() on the committed synthetic
  file tests/fixtures/paid/sample-report.csv (parsed and stripped by the reference engine), with the method the report
  page accepts; the build refuses a sample of another method.
* In Chromium the real report.js draws it: page 1, the coverage lines and every habit's sentences are wording.js's.
* No percentile, no "2,262", no "sample trader report"; the free build keeps the lifted research page (C-12 now)."""
import functools
import http.server
import json
import os
import re
import socket
import subprocess
import sys
import threading

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(HERE, "fixtures", "paid"))
from lint import lint_text, visible_text  # noqa: E402
from test_c14_legal_copy import _build  # noqa: E402
import make_sample_report as M  # noqa: E402

PRIVATE = os.environ.get("DT_PRIVATE_REPO") or os.path.join(os.path.dirname(REPO), "dt-private")
GOLDEN = os.path.join(REPO, "site", "config", "sample-report.report.json")


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


def page_method():
    return re.search(r"^export const METHOD_VERSION = '([^']+)';$",
                     open(os.path.join(REPO, "site/static/js/paid/wording.js"), encoding="utf-8").read(), re.M).group(1)


@pytest.fixture(scope="module")
def paid(tmp_path_factory):
    r, out = _build(tmp_path_factory.mktemp("sample"), "paid")
    assert r.returncode == 0, r.stderr
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=str(out)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "origin": f"http://127.0.0.1:{port}"}
    srv.shutdown()


def test_the_page_embeds_the_golden_and_its_method_is_the_pages(paid):
    html = open(os.path.join(paid["out"], "sample-report", "index.html"), encoding="utf-8").read()
    data = re.search(r'(?s)<script type="application/json" id="sample-data">(.*?)</script>', html).group(1)
    golden = json.load(open(GOLDEN, encoding="utf-8"))
    assert json.loads(data.replace("<\\/", "</")) == golden
    assert golden["method_version"] == page_method()
    assert "<!--frozen:start-->" not in html
    assert re.search(r'<script src="/static/js/paid/sample\.js\?v=[0-9a-f]+" type="module"></script>', html)
    t = re.sub(r"\s+", " ", visible_text(html))
    for bad in ("percentile among", "2,262", "SAMPLE TRADER REPORT", "sample trader report", "SP1000074", "real public data"):
        assert bad not in t, bad
    assert "Example report" in t and "Example report" in t and "run on example data" in t   # 29 Oct (owner): "Example", no "demo"
    assert lint_text(t) == [] and lint_text(t, "sample", paid=True) == []


@pytest.mark.skipif(not os.path.isfile(os.path.join(PRIVATE, "src", "core", "habits.mjs")), reason="dt-private (server) not present")
def test_the_golden_is_the_engines_output_on_the_committed_file(tmp_path):
    before = open(M.CSV, "rb").read()
    M.make_csv()
    assert open(M.CSV, "rb").read() == before, "tests/fixtures/paid/sample-report.csv is not what make_sample_report.py writes"
    assert M.engine_report(PRIVATE, M.stripped_rows()) == json.load(open(GOLDEN, encoding="utf-8"))


def test_the_build_refuses_a_sample_of_another_method(tmp_path, monkeypatch):
    sys.path.insert(0, os.path.join(REPO, "site"))
    import build as B
    bad = tmp_path / "s.json"
    rep = json.load(open(GOLDEN, encoding="utf-8"))
    rep["method_version"] = "2026-10-21.stats2"
    bad.write_text(json.dumps(rep), encoding="utf-8")
    monkeypatch.setattr(B, "SAMPLE_REPORT_JSON", str(bad))
    with pytest.raises((SystemExit, B.BuildError), match="rerun tests/fixtures/paid/make_sample_report.py"):
        B.sample_report()


def test_compare_and_build_agree_on_the_replaced_pages():
    sys.path.insert(0, os.path.join(REPO, "site"))
    import build as B
    import compare as C
    assert C.PAID_REPLACES_LIFTED == B.PAID_REPLACES_LIFTED == ("/sample-report/",)
    assert "/sample-report/" in B.lifted_paths_for(False) and "/sample-report/" not in B.lifted_paths_for(True)


def test_free_build_keeps_the_lifted_research_page(built_site):
    t = re.sub(r"\s+", " ", visible_text((built_site["out"] / "sample-report" / "index.html").read_text(encoding="utf-8")))
    assert "This is a research figure from public data. It is not the trader report" in t


def test_chromium_draws_the_sample_with_the_report_pages_own_sentences(paid, browser):
    """DT-2 (batch S1/S2): page 1, the coverage lines and each habit's "What happened" and "Habit or chance?" lines are
    wording.js's, drawn from the engine's golden; the example report shows no re-test or firm buttons."""
    golden = json.load(open(GOLDEN, encoding="utf-8"))
    js = ("import * as W from './site/static/js/paid/wording.js'; let s=''; process.stdin.on('data', (d) => { s += d; });"
          "process.stdin.on('end', () => { const r = JSON.parse(s); process.stdout.write(JSON.stringify({ p1: W.page1Lines(r),"
          " cov: W.coverageLines(r), h: r.habits.filter((h) => W.SENTENCE_HABITS.includes(h.id)).map((h) => { const l = W.habitLines(h, r); return l.what.concat(l.check); }) })); });")
    want = json.loads(subprocess.run(["node", "--input-type=module", "-e", js], cwd=REPO, input=json.dumps(golden),
                                     capture_output=True, text=True, check=True).stdout)
    ctx = browser.new_context()
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(paid["origin"] + "/sample-report/")
    page.wait_for_selector("#sample-out #focus-lines")
    p1 = [p.strip() for p in page.locator("#focus-lines p").all_inner_texts()]
    cov = [p.strip() for p in page.locator("#coverage p").all_text_contents()]
    text = page.locator("#sample-out").text_content()
    ctx.close()
    assert errors == []
    # wording.js's own lines; money uses the page's formatter, so lines are compared up to the first figure
    head = lambda line: re.split(r"[\d−$]|-\d", line)[0]  # noqa: E731
    # page 1's lines, then (with a habit shown first) its question and its pill
    assert len(p1) >= len(want["p1"]) and all(head(w) == head(g) for w, g in zip(want["p1"], p1)), (want["p1"], p1)
    assert p1[0] == want["p1"][0]
    assert cov == want["cov"]
    n = 0
    for lines in want["h"]:
        for line in lines:
            assert head(line) in text, line
            n += 1
    assert n >= 6
    for bad in ("percentile", "Send to your firm", "re-test reminder", "Print or save as PDF", "Luck check coming", "Not clear yet"):
        assert bad not in text, bad
    assert lint_text(text, "sample", paid=True) == []
