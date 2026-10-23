"""Delivery plan C-15: ./site/run.sh check-live against local static servers serving docs/ (read-only).

docs/ itself is never written: the failure cases serve a temporary copy with one planted change."""
import io
import os
import shutil
import subprocess
import sys
import threading
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
DOCS = os.path.join(REPO, "docs")
sys.path.insert(0, os.path.join(REPO, "checks"))
import check_live as C  # noqa: E402


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *a):
        pass


class _Fallback(_Quiet):
    """A host that answers every unknown path with the home page (status 200): what check-live must catch."""
    def send_error(self, code, message=None, explain=None):
        if code == 404:
            self.path = "/index.html"
            f = self.send_head()
            if f:
                shutil.copyfileobj(f, self.wfile)
                f.close()
            return
        super().send_error(code, message, explain)


def _serve(directory, handler=_Quiet):
    srv = ThreadingHTTPServer(("127.0.0.1", 0), partial(handler, directory=directory))
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://127.0.0.1:{srv.server_address[1]}"


@pytest.fixture(scope="module")
def docs_host():
    srv, url = _serve(DOCS)
    yield url
    srv.shutdown()


@pytest.fixture
def copy_host(tmp_path):
    made = []

    def make(change=None, handler=_Quiet):
        d = tmp_path / f"docs{len(made)}"
        shutil.copytree(DOCS, d)
        if change:
            change(d)
        srv, url = _serve(str(d), handler)
        made.append(srv)
        return url
    yield make
    for s in made:
        s.shutdown()


def _run(*args):
    buf = io.StringIO()
    n, passes = C.run(*args, timeout=10, out=buf)
    return n, passes, buf.getvalue()


def test_docs_served_locally_passes(docs_host):
    n, passes, out = _run(docs_host)
    assert n == 0, out
    pages = C.sitemap_paths(open(os.path.join(DOCS, "sitemap.xml"), encoding="utf-8").read())
    assert len(pages) >= 20 and passes > len(pages), out
    assert f"PASS  {docs_host}/__check-live-no-such-page__/" in out
    assert "(no trailing slash) -> 301 to /pricing/" in out


def test_compare_two_identical_hosts_passes(docs_host, copy_host):
    other = copy_host()
    n, _, out = _run(docs_host, other)
    assert n == 0, out
    assert "byte-identical on both hosts" in out and "behaves the same on both hosts" in out


def test_one_changed_byte_fails_the_compare(docs_host, copy_host):
    def change(d):
        p = d / "pricing" / "index.html"
        p.write_bytes(p.read_bytes().replace(b"</body>", b" </body>"))
    n, _, out = _run(docs_host, copy_host(change))
    assert n == 1 and "FAIL  /pricing/ is byte-identical on both hosts" in out, out


def test_a_missing_page_fails(copy_host):
    n, _, out = _run(copy_host(lambda d: shutil.rmtree(d / "terms")))
    assert n >= 1 and "/terms/ -> 404" in out, out


def test_a_host_that_serves_the_home_page_for_unknown_paths_fails(copy_host):
    n, _, out = _run(copy_host(handler=_Fallback))
    assert "FAIL  " in out and "(a page that does not exist) -> 200 (want 404)" in out, out


def test_a_page_without_its_csp_meta_fails(copy_host):
    def change(d):
        p = d / "about" / "index.html"
        t = p.read_text(encoding="utf-8")
        p.write_text(t.replace('http-equiv="Content-Security-Policy"', 'http-equiv="X-Removed"'), encoding="utf-8")
    n, _, out = _run(copy_host(change))
    assert n == 1 and "/about/ carries its CSP in a <meta> tag" in out, out


def test_every_docs_page_carries_its_csp_in_a_meta_so_no_headers_file_is_needed():
    pages = [os.path.join(r, f) for r, _, fs in os.walk(DOCS) for f in fs if f.endswith(".html")]
    assert pages
    for p in pages:
        assert C.CSP_META.search(open(p, encoding="utf-8").read()), p
    assert not os.path.exists(os.path.join(DOCS, "_headers"))


def test_cli_through_run_sh_and_bad_origin(docs_host):
    r = subprocess.run([os.path.join(REPO, "site", "run.sh"), "check-live", "--base", docs_host],
                       capture_output=True, text=True, timeout=120)
    assert r.returncode == 0 and "check-live:" in r.stdout and "0 failed" in r.stdout, r.stdout + r.stderr
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "check_live.py"), "--base", "donttrade.ca/x"],
                       capture_output=True, text=True)
    assert r.returncode != 0 and "is not an origin" in r.stderr


def test_location_and_sitemap_helpers():
    assert C.location_path("https://a.pages.dev", "/tools/") == "/tools/"
    assert C.location_path("https://a.pages.dev", "https://a.pages.dev/tools/") == "/tools/"
    with pytest.raises(ValueError):
        C.sitemap_paths("<loc>https://evil.example/x/</loc>")
