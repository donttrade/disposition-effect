"""Shared fixtures: a local static server on the repo root and a Chromium browser."""
import functools
import http.server
import os
import threading

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class _Quiet(http.server.SimpleHTTPRequestHandler):
    extensions_map = {**http.server.SimpleHTTPRequestHandler.extensions_map, ".js": "text/javascript",
                      ".mjs": "text/javascript"}

    def log_message(self, *a):
        pass


@pytest.fixture(scope="session")
def repo_server():
    handler = functools.partial(_Quiet, directory=REPO)
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


# 2 Nov (Umami Cloud): no test ever loads the real Umami script or reaches gateway.umami.is (no page view from a test
# lands in the owner's stats, and the suites pass offline). Every context from the browser fixture answers
# cloud.umami.is/script.js with this stand-in, which records each umami.track(name, data) call in window.__umamiCalls,
# and gateway.umami.is with 204. A test that needs the real tracker routes it itself (tests/test_umami.py, a pinned
# copy in tests/fixtures/umami-script.js); Playwright runs the route registered last first.
UMAMI_STUB = ("window.umami={track:function(n,d){(window.__umamiCalls=window.__umamiCalls||[])"
              ".push({name:n,hasData:d!==undefined});return Promise.resolve();}};")


def stub_umami(ctx):
    ctx.route("https://cloud.umami.is/**",
              lambda r: r.fulfill(status=200, content_type="text/javascript", body=UMAMI_STUB))
    ctx.route("https://gateway.umami.is/**", lambda r: r.fulfill(status=204, body=""))
    return ctx


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        new_context, new_page = b.new_context, b.new_page
        b.new_context = lambda *a, **kw: stub_umami(new_context(*a, **kw))

        def _new_page(*a, **kw):
            pg = new_page(*a, **kw)
            stub_umami(pg.context)
            return pg
        b.new_page = _new_page
        yield b
        b.close()


@pytest.fixture(scope="session")
def built_site(tmp_path_factory):
    """A flag-off build of the site in a temp dir, served on 127.0.0.1. {out, url}."""
    import subprocess
    import sys
    out = tmp_path_factory.mktemp("site") / "_site"
    env = {**os.environ, "DT_OUT": str(out)}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    handler = functools.partial(_Quiet, directory=str(out))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


@pytest.fixture(scope="session")
def badges_site(tmp_path_factory):
    """Like built_site, with [flags] free_badges = true (free-launch condition C1: the free tools'
    "real or noise" badges are off by default; the tests of the badges themselves use this build)."""
    import re
    import subprocess
    import sys
    tmp = tmp_path_factory.mktemp("badges")
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    src, n = re.subn(r"(?m)^free_badges = false", "free_badges = true", src)
    assert n == 1
    (tmp / "site.toml").write_text(src, encoding="utf-8")
    out = tmp / "_site"
    env = {**os.environ, "DT_OUT": str(out), "DT_SITE_TOML": str(tmp / "site.toml")}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    handler = functools.partial(_Quiet, directory=str(out))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


@pytest.fixture(scope="session")
def journal_site(tmp_path_factory):
    """Like built_site, with [flags] journal = true (ARCHITECT-V3 §d: the journal is off by default, off until
    the owner approves; the journal's own tests use this build). {out, url}."""
    import re
    import subprocess
    import sys
    tmp = tmp_path_factory.mktemp("journal")
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    src, n = re.subn(r"(?m)^journal = false", "journal = true", src)
    assert n == 1
    (tmp / "site.toml").write_text(src, encoding="utf-8")
    out = tmp / "_site"
    env = {**os.environ, "DT_OUT": str(out), "DT_SITE_TOML": str(tmp / "site.toml")}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    handler = functools.partial(_Quiet, directory=str(out))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()


@pytest.fixture(scope="session")
def ask_site(tmp_path_factory):
    """Like built_site, with [flags] ask_box = true (the Ask box is hidden for launch, 25 Oct; the answer
    box's own tests use this build). {out, url}."""
    import re
    import subprocess
    import sys
    tmp = tmp_path_factory.mktemp("ask")
    src = open(os.path.join(REPO, "site", "config", "site.toml"), encoding="utf-8").read()
    src, n = re.subn(r"(?m)^ask_box = false", "ask_box = true", src)
    assert n == 1
    (tmp / "site.toml").write_text(src, encoding="utf-8")
    out = tmp / "_site"
    env = {**os.environ, "DT_OUT": str(out), "DT_SITE_TOML": str(tmp / "site.toml")}
    env.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(REPO, "site", "build.py")], env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    handler = functools.partial(_Quiet, directory=str(out))
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield {"out": out, "url": f"http://127.0.0.1:{srv.server_address[1]}"}
    srv.shutdown()
