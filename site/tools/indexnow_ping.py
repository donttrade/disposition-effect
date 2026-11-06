#!/usr/bin/env python3
"""IndexNow ping (6 Nov 2026, Round A5): tell Bing and the other IndexNow engines which donttrade.ca pages changed.

Run by hand, after a production deploy, never by the build:
    python3 site/tools/indexnow_ping.py --dry-run              # list the URLs, send nothing
    python3 site/tools/indexnow_ping.py                        # ping the URLs that changed since HEAD~1
    python3 site/tools/indexnow_ping.py --since-rev <git rev>  # ... since another revision
    python3 site/tools/indexnow_ping.py --yes                  # more than 100 URLs changed: say so

Which URLs: the sitemap's URLs whose <lastmod> is new or different from the previous deployed sitemap, plus every
sitemap URL whose docs/<path>/index.html changed in git since the revision (a page edited without a lastmod change).
It refuses when: the build is a preview (docs/robots.txt disallows everything), the key file is not live (it fetches
https://<host>/<key>.txt and compares), the key is missing or malformed, or more than 100 URLs changed without --yes.
It prints counts and the HTTP status only (200 and 202 mean accepted). The key is public by design (the site serves
it); this script prints it nowhere. Google does not use IndexNow: Search Console's sitemap stays a separate step.
Endpoint and format: https://www.indexnow.org/documentation (max 10,000 URLs a call; JSON body with host, key,
keyLocation, urlList).
"""
import argparse
import json
import os
import re
import ssl
import subprocess
import sys
import tomllib
import urllib.error
import urllib.request

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ENDPOINT = "https://api.indexnow.org/indexnow"
KEY_RE = re.compile(r"[A-Za-z0-9-]{8,128}")
MAX_WITHOUT_YES = 100
MAX_PER_CALL = 10000
LOC_RE = re.compile(r"<url><loc>([^<]+)</loc>(?:<lastmod>([^<]*)</lastmod>)?")


# 6 Nov (SEO round 1): Cloudflare's bot filter answers 403 to Python's default "Python-urllib/3.x" agent, so the
# key-file check on https://donttrade.ca/<key>.txt failed even with the file live. Every request sends this plain,
# descriptive agent instead (it names the tool and the site, as the IndexNow documentation asks of a submitter).
USER_AGENT = "donttrade-indexnow/1.0 (+https://donttrade.ca)"


class Refused(Exception):
    pass


def ssl_context(environ=None):
    """The TLS context for every request. SSL_CERT_FILE, when set, names the CA bundle to trust (a machine behind a
    proxy that re-signs HTTPS keeps its bundle there); a named file that is missing is refused, never ignored.
    Verification is never switched off."""
    environ = os.environ if environ is None else environ
    cafile = environ.get("SSL_CERT_FILE")
    if not cafile:
        return ssl.create_default_context()
    if not os.path.isfile(cafile):
        raise Refused(f"SSL_CERT_FILE names a file that does not exist: {cafile}")
    return ssl.create_default_context(cafile=cafile)


def read_key(toml_path):
    with open(toml_path, "rb") as f:
        key = (tomllib.load(f).get("indexnow") or {}).get("key", "")
    if not isinstance(key, str) or not KEY_RE.fullmatch(key):
        raise Refused("site.toml has no valid [indexnow] key (8 to 128 of letters, digits and -)")
    return key


def parse_sitemap(text):
    """{url: lastmod or ""} from a sitemap.xml written by site/build.py."""
    return {m.group(1): m.group(2) or "" for m in LOC_RE.finditer(text)}


def changed_urls(new, old, changed_files, base):
    """The URLs to announce: new or different lastmod, or whose docs index.html is in changed_files."""
    out = {u for u, d in new.items() if old.get(u) != d}
    for rel in changed_files:
        m = re.fullmatch(r"docs/(.*?)/?index\.html", rel)
        if m is None:
            continue
        url = base + "/" + (m.group(1) + "/" if m.group(1) else "")
        if url in new:
            out.add(url)
    return sorted(out)


def preview_problem(robots_text):
    return "docs/robots.txt disallows everything: this is a preview build, not announced" if re.search(
        r"(?mi)^Disallow:\s*/\s*$", robots_text) else None


def key_live(fetch, host, key):
    body = fetch(f"https://{host}/{key}.txt")
    if body is None or body.strip() != key:
        raise Refused(f"https://{host}/{key}.txt is not live with the key in it: deploy first, then ping")


def git(*args):
    r = subprocess.run(["git", "-C", REPO, *args], capture_output=True, text=True)
    return r.stdout if r.returncode == 0 else None


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=20, context=ssl_context()) as r:
            return r.read().decode("utf-8", "replace")
    except (urllib.error.URLError, OSError):
        return None


def http_post(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST",
                                 headers={"Content-Type": "application/json; charset=utf-8", "User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=30, context=ssl_context()) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code


def run(args, fetch=http_get, post=http_post):
    toml_path = os.path.join(REPO, "site", "config", "site.toml")
    with open(toml_path, "rb") as f:
        base = tomllib.load(f)["site"]["base_url"].rstrip("/")
    host = re.sub(r"^https?://", "", base)
    key = read_key(toml_path)
    docs = args.docs or os.path.join(REPO, "docs")
    why = preview_problem(open(os.path.join(docs, "robots.txt"), encoding="utf-8").read())
    if why:
        raise Refused(why)
    new = parse_sitemap(open(os.path.join(docs, "sitemap.xml"), encoding="utf-8").read())
    old_text = git("show", f"{args.since_rev}:docs/sitemap.xml")
    old = parse_sitemap(old_text) if old_text else {}
    files = (git("diff", "--name-only", args.since_rev, "HEAD", "--", "docs") or "").split()
    urls = changed_urls(new, old, files, base)
    print(f"sitemap: {len(new)} URLs; changed since {args.since_rev}: {len(urls)}")
    if not urls:
        print("nothing to announce")
        return 0
    if len(urls) > MAX_WITHOUT_YES and not args.yes:
        raise Refused(f"{len(urls)} URLs changed (more than {MAX_WITHOUT_YES}): run again with --yes if that is right")
    if args.dry_run:
        for u in urls:
            print(u)
        print("dry run: nothing sent")
        return 0
    key_live(fetch, host, key)
    status = 0
    for i in range(0, len(urls), MAX_PER_CALL):
        chunk = urls[i:i + MAX_PER_CALL]
        status = post(ENDPOINT, {"host": host, "key": key, "keyLocation": f"https://{host}/{key}.txt", "urlList": chunk})
        print(f"sent {len(chunk)} URLs: HTTP {status}")
        if status not in (200, 202):
            return 1
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--since-rev", default="HEAD~1", help="git revision of the previous deploy (default HEAD~1)")
    ap.add_argument("--docs", help="the docs/ folder to read (default: this repository's)")
    ap.add_argument("--dry-run", action="store_true", help="list the URLs and send nothing")
    ap.add_argument("--yes", action="store_true", help=f"allow more than {MAX_WITHOUT_YES} URLs in one run")
    args = ap.parse_args(argv)
    try:
        return run(args)
    except Refused as e:
        print(f"refused: {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
