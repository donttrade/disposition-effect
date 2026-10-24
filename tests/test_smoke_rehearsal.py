"""Delivery plan C-5 + R-D1 D-6: dt-private's scripts/smoke.mjs against the REHEARSAL Worker
(`scripts/rehearse.mjs --serve`, workerd + local D1 + mock Stripe) and a real local paid build of this
checkout; the clear FAIL line for each broken case; the dt-method meta; run.sh test-worker's method check.

Skipped when DT_PRIVATE_REPO (default ../dt-private) has no smoke.mjs/rehearsal or no wrangler.
"""
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
PRIVATE = os.environ.get("DT_PRIVATE_REPO") or os.path.join(os.path.dirname(REPO), "dt-private")
sys.path.insert(0, HERE)
from test_legal import prices_with_test_link, private_with  # noqa: E402

HAVE = all(os.path.exists(os.path.join(PRIVATE, p)) for p in ("scripts/smoke.mjs", "scripts/rehearse.mjs", "node_modules/wrangler"))
needs_private = pytest.mark.skipif(not HAVE, reason="DT_PRIVATE_REPO has no smoke/rehearsal (dt-private delivery-39 with npm ci)")
WORDING_METHOD = re.search(r"^export const METHOD_VERSION = '([^']+)';$",
                           open(os.path.join(REPO, "site/static/js/paid/wording.js"), encoding="utf-8").read(), re.M).group(1)


def free_port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


class Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript"}

    def log_message(self, *a):
        pass


def build(tmp, name, api, paid=True):
    toml = open(os.path.join(REPO, "site/config/site.toml"), encoding="utf-8").read()
    if paid:
        toml = toml.replace("paid_report = false", "paid_report = true").replace("trader_first_home = false", "trader_first_home = true")
    toml = toml.replace('api_base = "http://127.0.0.1:8787"', f'api_base = "{api}"')
    (tmp / f"{name}.toml").write_text(toml, encoding="utf-8")
    out = tmp / name
    priv = private_with(tmp, name=f"{name}-private.toml")
    env = {**os.environ, "DT_SITE_TOML": str(tmp / f"{name}.toml"), "DT_OUT": str(out), "DT_PRIVATE_TOML": priv,
           "DT_PRICES_JSON": prices_with_test_link(tmp), "DT_ALLOW_LOCAL_API": "1"}
    r = subprocess.run([sys.executable, os.path.join(REPO, "site/build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return out, priv


def serve_dir(port, directory):
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), functools.partial(Quiet, directory=str(directory)))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


class Worker:
    """Tester E16: the shared harness (tests/rehearsal_worker.py) runs it in its own process group, stops it when the
    test ends (or this process dies: --exit-with-stdin) and checks no workerd child is left."""
    def __init__(self, origins, omit=()):
        import sys
        sys.path.insert(0, HERE)
        from rehearsal_worker import ServeWorker
        self.w = ServeWorker(PRIVATE, origins, omit)
        self.api = self.w.api

    def stop(self):
        left = self.w.stop()
        assert left == [], f"workerd children left running: {left}"


def smoke(api, site, mode="test", flag="on", private=None):
    cmd = ["node", "scripts/smoke.mjs", "--api", api, "--site", site, "--mode", mode, "--expect-flag", flag]
    if private:
        cmd += ["--private", private]
    r = subprocess.run(cmd, cwd=PRIVATE, capture_output=True, text=True, timeout=120)
    return r.returncode, r.stdout


@pytest.fixture(scope="module")
def sites(tmp_path_factory):
    tmp = tmp_path_factory.mktemp("smoke")
    paid_port, free_port_ = free_port(), free_port()
    paid_site, free_site = f"http://127.0.0.1:{paid_port}", f"http://127.0.0.1:{free_port_}"
    w = Worker([paid_site, free_site])
    paid_dir, priv = build(tmp, "paid", w.api)
    free_dir, _ = build(tmp, "free", w.api, paid=False)
    servers = [serve_dir(paid_port, paid_dir), serve_dir(free_port_, free_dir)]
    yield {"worker": w, "paid": paid_site, "free": free_site, "private": priv, "paid_dir": paid_dir, "tmp": tmp}
    w.stop()
    for s in servers:
        s.shutdown()


@needs_private
def test_smoke_passes_against_the_rehearsal_worker_and_a_local_paid_build(sites):
    code, out = smoke(sites["worker"].api, sites["paid"], private=sites["private"])
    assert code == 0, out
    assert "FAIL" not in out
    assert f"PASS  method: worker and site both {WORDING_METHOD}" in out
    assert "PASS  /report/ CSP connect-src contains " + sites["worker"].api in out


@needs_private
def test_smoke_test_link_in_live_mode_fails(sites):
    code, out = smoke(sites["worker"].api, sites["paid"], mode="live", private=sites["private"])
    assert code == 2, out  # the link line, and /health's mode (the rehearsal Worker is test mode)
    assert "FAIL  the $39 button is a buy.stripe.com link without the test_ prefix (mode live) — https://buy.stripe.com/test_" in out
    assert 'FAIL  GET /health is 200 with ok and mode "live"' in out


@needs_private
def test_smoke_flag_off_build_fails_expect_on_and_passes_expect_off(sites):
    code, out = smoke(sites["worker"].api, sites["free"], private=sites["private"])
    assert code >= 4, out
    assert 'FAIL  /pricing/ has the "Before you pay" block (#before-you-pay)' in out
    assert "FAIL  /report/ is 200 — 404" in out
    code, out = smoke(sites["worker"].api, sites["free"], flag="off")
    assert code == 0, out
    code, out = smoke(sites["worker"].api, sites["paid"], flag="off")
    assert code >= 3 and "FAIL  flag off: /report/ does not exist — 200" in out, out


@needs_private
def test_smoke_cors_origin_wrong_and_secret_missing_fail(sites, tmp_path):
    port = free_port()
    site = f"http://127.0.0.1:{port}"
    srv = serve_dir(port, sites["paid_dir"])  # the paid pages name the first Worker in their CSP; only CORS matters here
    try:
        sites["worker"].stop()  # one rehearsal at a time (they share dt-private's .rehearsal/)
        w = Worker(["https://donttrade.ca"])
        try:
            code, out = smoke(w.api, site, private=sites["private"])
            assert code >= 1, out
            assert f"FAIL  CORS preflight from {site} is 204 with that Allow-Origin — 403, allow-origin null" in out
        finally:
            w.stop()
        w = Worker([site], omit=["HMAC_SECRET"])
        try:
            code, out = smoke(w.api, site, private=sites["private"])
            assert code >= 2, out
            assert 'FAIL  GET /health is 200 with ok and mode "test" — 503 {"ok":false}' in out
            assert 'FAIL  POST /redeem {session_id:"nope"} is 400 bad_session_id (the configuration loaded) — 503' in out
        finally:
            w.stop()
    finally:
        srv.shutdown()
        sites["worker"] = Worker([sites["paid"], sites["free"]])  # for any later test; the fixture stops it


def test_paid_build_carries_the_wording_method_on_every_paid_page(tmp_path):
    out, _ = build(tmp_path, "paidmeta", "http://127.0.0.1:8787")
    for rel in ("report/index.html", "welcome/index.html", "restore/index.html"):
        html = open(os.path.join(out, rel), encoding="utf-8").read()
        assert f'<meta name="dt-method" content="{WORDING_METHOD}">' in html, rel
    free, _ = build(tmp_path, "freemeta", "http://127.0.0.1:8787", paid=False)
    assert "dt-method" not in open(os.path.join(free, "index.html"), encoding="utf-8").read()


def fake_private(tmp, method):
    d = tmp / ("priv-" + method.replace(".", "-"))
    (d / "src/core").mkdir(parents=True)
    (d / "src/core/habits.mjs").write_text(f"export const METHOD_VERSION = '{method}';\n", encoding="utf-8")
    (d / "tests").mkdir()
    (d / "tests/ok.test.mjs").write_text("import { test } from 'node:test'; test('ok', () => {});\n", encoding="utf-8")
    return d


def test_run_sh_test_worker_refuses_a_stats1_server_and_runs_a_stats2_one(tmp_path):
    run = lambda d: subprocess.run([os.path.join(REPO, "site/run.sh"), "test-worker"], env={**os.environ, "DT_PRIVATE_REPO": str(d)},
                                   capture_output=True, text=True, timeout=120)
    r1 = run(fake_private(tmp_path, "2026-10-21.stats1"))
    assert r1.returncode == 1 and f"method mismatch: server 2026-10-21.stats1 at " in r1.stdout and f"site {WORDING_METHOD}" in r1.stdout, r1.stdout
    r2 = run(fake_private(tmp_path, WORDING_METHOD))
    assert r2.returncode == 0, r2.stdout + r2.stderr
    assert "# pass 1" in r2.stdout


@needs_private
def test_e16_a_stopped_worker_leaves_no_node_or_workerd_process():
    """Tester E16: after stop(), neither the serve process nor its workerd child is alive."""
    import sys
    sys.path.insert(0, HERE)
    from rehearsal_worker import ServeWorker, _alive
    w = ServeWorker(PRIVATE, ["http://127.0.0.1:9"])
    pid, kids = w.p.pid, list(w.children)
    assert kids, "workerd runs as a child of the serve process"
    assert w.stop() == []
    assert not _alive(pid) and not any(_alive(k) for k in kids)
