#!/usr/bin/env python3
"""check_live.py: is a deployed copy of the site whole? (delivery plan C-15, Pages move prep, G32)

Usage (./site/run.sh check-live ...):
  python3 checks/check_live.py --base <origin> [--compare <origin>] [--timeout S]

For every URL in <base>/sitemap.xml (its https://donttrade.ca prefix is read as <base>), plus /404.html,
/feed.xml, /robots.txt and /sitemap.xml itself:
  * the answer is 200, without a redirect, with the content type its extension implies;
  * with --compare, the body is byte-identical to the other host's.
Also, on each host:
  * a path that does not exist answers 404 (not 200: a host that serves index.html for unknown paths
    would turn every typo into a copy of the home page), and with --compare its body is the same;
  * each directory URL asked for WITHOUT its trailing slash either redirects to the slashed URL or
    answers 200; with --compare, both hosts do the same (redirect or not, and to the same path).
    The redirect status (301 on GitHub Pages, 308 on Cloudflare Pages) may differ; the target may not.
  * every HTML page carries its Content-Security-Policy in a <meta> tag, so the site depends on no
    response header (GitHub Pages cannot set headers; docs/_headers is therefore not needed).

One PASS/FAIL line per check, then a summary. Exit code = the number of failures (capped at 100).
Read-only: GET requests only, no cookies, nothing sent but the request line and headers.
"""
import argparse
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor

SITE_ORIGIN = "https://donttrade.ca"
EXTRA = ["/404.html", "/feed.xml", "/robots.txt", "/sitemap.xml"]
MISSING = "/__check-live-no-such-page__/"
TYPES = {".html": "text/html", ".xml": "xml", ".txt": "text/plain", ".css": "text/css", ".js": "javascript",
         ".json": "json", ".csv": "text/csv", ".pdf": "application/pdf", ".png": "image/png", ".svg": "image/svg+xml",
         ".webp": "image/webp", ".woff2": "font/woff2"}
CSP_META = re.compile(r'<meta\s+http-equiv="Content-Security-Policy"\s+content="[^"]+"', re.IGNORECASE)


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *a, **k):
        return None


def _opener(origin):
    host = urllib.parse.urlsplit(origin).hostname or ""
    handlers = [_NoRedirect()]
    if host in ("127.0.0.1", "localhost", "::1"):
        handlers.append(urllib.request.ProxyHandler({}))   # never send a loopback request through a proxy
    return urllib.request.build_opener(*handlers)


def fetch(origin, path, timeout):
    """(status, content_type, location, body bytes) without following redirects; status 0 = no answer."""
    req = urllib.request.Request(origin + path, headers={"User-Agent": "donttrade-check-live/1"})
    try:
        with _opener(origin).open(req, timeout=timeout) as r:
            return r.status, r.headers.get("Content-Type", ""), r.headers.get("Location"), r.read()
    except urllib.error.HTTPError as e:
        return e.code, e.headers.get("Content-Type", ""), e.headers.get("Location"), e.read()
    except Exception as e:  # noqa: BLE001  (DNS, TLS, refused, timeout: all are one FAIL line)
        return 0, "", None, str(e).encode()


def expected_type(path):
    if path.endswith("/"):
        return "text/html"
    for ext, t in TYPES.items():
        if path.endswith(ext):
            return t
    return None


def norm_origin(o):
    o = o.rstrip("/")
    u = urllib.parse.urlsplit(o)
    if u.scheme not in ("http", "https") or not u.netloc or u.path or u.query:
        raise SystemExit(f"check-live: {o!r} is not an origin like https://example.pages.dev")
    return o


def sitemap_paths(xml):
    paths = []
    for loc in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", xml):
        if not loc.startswith(SITE_ORIGIN + "/"):
            raise ValueError(f"sitemap URL outside {SITE_ORIGIN}: {loc}")
        paths.append(loc[len(SITE_ORIGIN):])
    return paths


def location_path(origin, loc):
    if not loc:
        return None
    u = urllib.parse.urlsplit(urllib.parse.urljoin(origin + "/", loc))
    return u.path + (("?" + u.query) if u.query else "")


def run(base, compare=None, timeout=20, out=sys.stdout):
    base = norm_origin(base)
    compare = norm_origin(compare) if compare else None
    fails, passes = [], 0

    def line(ok, msg):
        nonlocal passes
        if ok:
            passes += 1
        else:
            fails.append(msg)
        print(("PASS  " if ok else "FAIL  ") + msg, file=out)

    st, _, _, body = fetch(base, "/sitemap.xml", timeout)
    if st != 200:
        line(False, f"{base}/sitemap.xml answered {st or 'nothing'}: cannot list the pages")
        return len(fails), passes
    try:
        paths = sitemap_paths(body.decode("utf-8", "replace"))
    except ValueError as e:
        line(False, str(e))
        return len(fails), passes
    line(len(paths) > 0, f"sitemap.xml lists {len(paths)} page(s)")
    paths = list(dict.fromkeys(paths + EXTRA))
    hosts = [base] + ([compare] if compare else [])

    with ThreadPoolExecutor(max_workers=8) as pool:
        got = {h: dict(zip(paths, pool.map(lambda p, h=h: fetch(h, p, timeout), paths))) for h in hosts}
        missing = {h: fetch(h, MISSING, timeout) for h in hosts}
        dirs = [p for p in paths if p.endswith("/") and p != "/"]
        noslash = {h: dict(zip(dirs, pool.map(lambda p, h=h: fetch(h, p.rstrip("/"), timeout), dirs))) for h in hosts}

    for h in hosts:
        for p in paths:
            st, ctype, loc, body = got[h][p]
            want = expected_type(p)
            ok = st == 200 and (want is None or want in ctype.lower())
            line(ok, f"{h}{p} -> {st or 'no answer'}{' (redirect to ' + str(loc) + ')' if loc else ''}, "
                     f"{ctype or 'no content type'}{'' if ok or want is None else ' (want ' + want + ')'}")
            if ok and (want == "text/html"):
                line(bool(CSP_META.search(body.decode("utf-8", "replace"))), f"{h}{p} carries its CSP in a <meta> tag")
        st = missing[h][0]
        line(st == 404, f"{h}{MISSING} (a page that does not exist) -> {st or 'no answer'} (want 404)")
        for p in dirs:
            st, _, loc, _ = noslash[h][p]
            target = location_path(h, loc) if 300 <= st < 400 else None
            ok = st == 200 or target == p
            line(ok, f"{h}{p.rstrip('/')} (no trailing slash) -> {st or 'no answer'}"
                     f"{' to ' + str(target) if target else ''} (want a redirect to {p}, or 200)")

    if compare:
        for p in paths:
            a, b = got[base][p], got[compare][p]
            if a[0] == 200 and b[0] == 200:
                line(a[3] == b[3], f"{p} is byte-identical on both hosts ({len(a[3])} and {len(b[3])} bytes)")
        a, b = missing[base], missing[compare]
        if a[0] == 404 and b[0] == 404:
            line(a[3] == b[3], f"the not-found page is the same on both hosts ({len(a[3])} and {len(b[3])} bytes)")
        for p in dirs:
            ra, rb = noslash[base][p], noslash[compare][p]
            ka = ("redirect", location_path(base, ra[2])) if 300 <= ra[0] < 400 else (ra[0], None)
            kb = ("redirect", location_path(compare, rb[2])) if 300 <= rb[0] < 400 else (rb[0], None)
            line(ka == kb, f"{p.rstrip('/')} without its slash behaves the same on both hosts ({ka} and {kb})")

    print(f"check-live: {passes} passed, {len(fails)} failed ({base}{' vs ' + compare if compare else ''})", file=out)
    return len(fails), passes


def main(argv=None):
    ap = argparse.ArgumentParser(prog="check-live", description=__doc__.split("\n")[0])
    ap.add_argument("--base", required=True, help="the host to check, e.g. https://donttrade.pages.dev")
    ap.add_argument("--compare", help="another host that must serve byte-identical files, e.g. https://donttrade.ca")
    ap.add_argument("--timeout", type=float, default=20.0)
    a = ap.parse_args(argv)
    n, _ = run(a.base, a.compare, a.timeout)
    return min(n, 100)


if __name__ == "__main__":
    sys.exit(main())
