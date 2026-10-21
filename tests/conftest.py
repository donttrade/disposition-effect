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


@pytest.fixture(scope="session")
def browser():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch()
        yield b
        b.close()
