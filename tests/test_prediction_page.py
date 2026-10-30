"""Batch R1: /research/does-the-test-predict/ behind [flags] prediction_results.

* flag off (the committed site.toml): the page is not built;
* flag on with no OSF registration recorded: the build refuses;
* flag on: "results pending" with no result file, and every one of the six verdicts renders from fixture
  JSON (the script's own --json output on the synthetic fixture), plus a two-firm result. Each page passes
  the site's wording lint (banned words, claims) on its visible text."""
import json
import os
import re
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(HERE, ".."))
sys.path.insert(0, os.path.join(REPO, "partner"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import make_fixture_prediction as G  # noqa: E402

PATH = "research/does-the-test-predict/index.html"
VERDICTS = ("NOT MEASURED", "FAIL: does not predict usefully", "FAIL: adds nothing", "PASS: meets target",
            "PASS: below target", "INCONCLUSIVE")
HEADINGS = {None: "Registered: results pending", "NOT MEASURED": "Not measured yet",
            "FAIL: does not predict usefully": "did not predict breaches usefully",
            "FAIL: adds nothing": "add nothing beyond size, volatility and headroom",
            "PASS: meets target": "ranked later breaches, beyond size and volatility",
            "PASS: below target": "ranked later breaches, modestly", "INCONCLUSIVE": "Result: inconclusive"}


@pytest.fixture(scope="module")
def twin(tmp_path_factory):
    d = str(tmp_path_factory.mktemp("fx"))
    G.write(d, "L", 600, 7)
    r = subprocess.run([sys.executable, "-I", os.path.join(REPO, "partner", "prediction_test.py"), "--json",
                        os.path.join(d, "trades.csv"), os.path.join(d, "accounts.csv"),
                        os.path.join(REPO, "partner", "PREREG-PREDICTION-EXAMPLE.md")], capture_output=True, text=True,
                       check=True)
    return json.loads(r.stdout)


def build(tmp_path, flag_on, study=None, result=None):
    toml = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    if flag_on:
        toml = toml.replace("prediction_results = false", "prediction_results = true")
    tp = tmp_path / "site.toml"
    tp.write_text(toml, encoding="utf-8")
    env = dict(os.environ, DT_SITE_TOML=str(tp), DT_OUT=str(tmp_path / "out"))
    sp = tmp_path / "study.json"
    sp.write_text(json.dumps(study if study is not None else {
        "osf_url": "https://osf.io/example", "registered_on": "1 December 2026", "release_tag": "prediction-v1",
        "code_url": "https://github.com/donttrade/disposition-effect/tree/prediction-v1/partner", "sha256": {}}),
        encoding="utf-8")
    env["DT_PREDICTION_STUDY"] = str(sp)
    rp = tmp_path / "result.json"
    if result is not None:
        rp.write_text(json.dumps(result), encoding="utf-8")
    env["DT_PREDICTION_RESULT"] = str(rp)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], capture_output=True, text=True, env=env,
                       cwd=REPO)
    return r, tmp_path / "out"


def page_problems(html):
    import lint
    return lint.lint_text(lint.visible_text(html), PATH, paid=True, analytics=True)


def test_flag_off_builds_no_page(tmp_path):
    r, out = build(tmp_path, False)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-2000:]
    assert not (out / PATH).exists()


def test_flag_on_without_registration_refuses(tmp_path):
    r, _ = build(tmp_path, True, study={"osf_url": "", "registered_on": "", "release_tag": "x", "code_url": "x",
                                        "sha256": {}})
    assert r.returncode != 0
    assert "OSF registration is not posted" in (r.stdout + r.stderr) or "osf_url" in (r.stdout + r.stderr)


def _result(twin, verdict, runs=None):
    t = dict(twin, verdict=verdict)
    if verdict == "NOT MEASURED":
        t = {k: v for k, v in t.items() if k not in ("h1", "h2", "features", "deciles", "lift_top", "confusion",
                                                     "calibration")}
    return {"verdict": verdict, "runs": runs or [t], "pooled": None}


@pytest.mark.parametrize("verdict", (None,) + VERDICTS)
def test_every_state_renders_and_lints(tmp_path, twin, verdict):
    r, out = build(tmp_path, True, result=None if verdict is None else _result(twin, verdict))
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-3000:]
    html = (out / PATH).read_text(encoding="utf-8")
    assert HEADINGS[verdict] in html
    for other, h in HEADINGS.items():
        if other != verdict:
            assert h not in html
    assert page_problems(html) == []
    if verdict not in (None, "NOT MEASURED"):
        assert "%.3f" % twin["h1"]["auc"] in html
        assert html.count("<rect class=\"bar-plain\"") == len(twin["deciles"])
        assert "<title>" in html and "<table>" in html
    assert 'href="https://osf.io/example"' in html


def test_two_firms_and_pooled(tmp_path, twin):
    a = dict(twin, firm_label="firm A")
    b = dict(twin, firm_label="firm B")
    res = {"verdict": "PASS: below target", "runs": [a, b],
           "pooled": {"auc": 0.61, "lo": 0.58, "hi": 0.64, "i2": 0.12}}
    r, out = build(tmp_path, True, result=res)
    assert r.returncode == 0, r.stdout[-3000:]
    html = (out / PATH).read_text(encoding="utf-8")
    assert "firm A" in html and "firm B" in html and "Pooled across firms" in html
    assert page_problems(html) == []


def test_bad_verdict_refused(tmp_path, twin):
    r, _ = build(tmp_path, True, result=_result(twin, "PASS: wonderful"))
    assert r.returncode != 0


def test_template_holds_every_verdict_before_any_result():
    src = open(os.path.join(REPO, "site", "templates", "pages", "research-prediction.html"), encoding="utf-8").read()
    for v in VERDICTS:
        assert 'v == "%s"' % v in src
    assert not re.search(r"\bseal", src, re.I)


def test_mobile_and_axe(tmp_path, twin):
    """The PASS page and the two-firm page: no serious or critical axe issue in either theme, and no sideways
    page scroll at 375 px or 1280 px."""
    import functools
    import http.server
    import threading
    import a11y
    from playwright.sync_api import sync_playwright
    pages = []
    for name, res in (("one", _result(twin, "PASS: meets target")),
                      ("two", {"verdict": "INCONCLUSIVE", "runs": [dict(twin, firm_label="firm A"),
                                                                   dict(twin, firm_label="firm B")],
                               "pooled": {"auc": 0.6, "lo": 0.55, "hi": 0.65, "i2": 0.3}})):
        d = tmp_path / name
        d.mkdir()
        r, out = build(d, True, result=res)
        assert r.returncode == 0
        pages.append(out)
    with sync_playwright() as p:
        b = p.chromium.launch()
        for out in pages:
            handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(out))
            handler.log_message = lambda *a: None
            srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            url = "http://127.0.0.1:%d/research/does-the-test-predict/" % srv.server_address[1]
            for scheme in ("light", "dark"):
                for width in (375, 1280):
                    ctx = b.new_context(color_scheme=scheme, viewport={"width": width, "height": 900}, bypass_csp=True)
                    pg = ctx.new_page()
                    pg.goto(url)
                    assert a11y.axe_violations(pg) == [], (scheme, width)
                    assert a11y.horizontal_overflow(pg) == [], (scheme, width)
                    ctx.close()
            srv.shutdown()
        b.close()
