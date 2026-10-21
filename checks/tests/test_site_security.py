"""Read-only security / exposure / SEO regression checks for https://donttrade.ca/

Run:   python3 -m pytest -q test_site_security.py
Needs: pip install --break-system-packages pytest requests beautifulsoup4 lxml
Optional repo secret scan needs the `gh` CLI with read access to donttrade/disposition-effect
(set DT_SKIP_REPO=1 to skip). Polite: sleeps ~1s between requests to the site.
Never writes to the site or the repo.
"""
import json, os, re, subprocess, time, xml.etree.ElementTree as ET
import pytest, requests
from bs4 import BeautifulSoup

BASE = os.environ.get("DT_BASE","https://donttrade.ca")
DELAY = float(os.environ.get("DT_DELAY", "1.0"))  # seconds between requests; 0 for a local build
REPO = "donttrade/disposition-effect"
SESSION = requests.Session()
SESSION.headers["User-Agent"] = "donttrade-owner-audit/1.0 (read-only)"
_last = [0.0]


def get(url, **kw):
    wait = DELAY - (time.time() - _last[0])
    if wait > 0:
        time.sleep(wait)
    for attempt in range(3):  # retry transient proxy/connection drops only
        try:
            return SESSION.get(url, timeout=20, **kw)
        except requests.exceptions.ConnectionError:
            if attempt == 2:
                raise
            time.sleep(3)
        finally:
            _last[0] = time.time()


# ---------- 1. exposure ----------
MUST_NOT_SERVE = ["/.git/config", "/.git/HEAD", "/.env", "/deploy-v20.tgz", "/build.py", "/dt-deploy.sh",
                  "/samples/", "/tests/", "/branding/", "/node_modules/", "/index.html.bak", "/index.html~",
                  "/.gitignore", "/README.md", "/requirements.txt", "/reproduce.py", "/.DS_Store", "/docs/"]


@pytest.mark.parametrize("path", MUST_NOT_SERVE)
def test_sensitive_path_not_served(path):
    r = get(BASE + path, allow_redirects=False)
    assert r.status_code in (403, 404), f"{path} returned {r.status_code}"


# ---------- 2. transport / headers ----------
@pytest.mark.parametrize("src,dst", [
    ("http://donttrade.ca/", "https://donttrade.ca/"),
    ("http://www.donttrade.ca/", "https://donttrade.ca/"),
    ("https://www.donttrade.ca/pricing/", "https://donttrade.ca/pricing/"),
    ("https://donttrade.github.io/disposition-effect/", "https://donttrade.ca/"),
    ("https://donttrade.github.io/disposition-effect/pricing/", "https://donttrade.ca/pricing/"),
])
def test_redirects_to_canonical_host(src, dst):
    r = get(src, allow_redirects=False)
    assert r.status_code == 301, (src, r.status_code)
    assert r.headers.get("location") == dst, (src, r.headers.get("location"))


def test_https_ok_and_no_mixed_scheme_assets():
    r = get(BASE + "/")
    assert r.status_code == 200
    soup = BeautifulSoup(r.text, "lxml")
    for tag, attr in [("img", "src"), ("script", "src"), ("link", "href"), ("iframe", "src"), ("source", "src")]:
        for t in soup.find_all(tag):
            assert not (t.get(attr) or "").startswith("http://"), t


@pytest.mark.xfail(reason="GitHub Pages does not send HSTS for custom domains (platform limitation)", strict=False)
def test_hsts_present():
    assert "strict-transport-security" in {k.lower() for k in get(BASE + "/").headers}


# ---------- 3/4. canonical + SEO per page ----------
def sitemap_urls():
    r = get(BASE + "/sitemap.xml")
    root = ET.fromstring(r.content)
    return [e.text for e in root.iter("{http://www.sitemaps.org/schemas/sitemap/0.9}loc")]


SITEMAP = None


def _sitemap():
    global SITEMAP
    if SITEMAP is None:
        SITEMAP = sitemap_urls()
    return SITEMAP


def test_robots_allows_and_points_to_sitemap():
    t = get(BASE + "/robots.txt").text
    assert "Disallow: /\n" not in t + "\n"
    assert "Sitemap: https://donttrade.ca/sitemap.xml" in t


def test_sitemap_wellformed_and_on_canonical_host():
    urls = _sitemap()
    assert len(urls) >= 20
    assert len(urls) == len(set(urls))
    for u in urls:
        assert u.startswith("https://donttrade.ca/") and u.endswith("/"), u


def test_every_sitemap_page(subtests=None):
    problems = []
    for u in _sitemap():
        r = get(u, allow_redirects=False)
        if r.status_code != 200:
            problems.append((u, "status", r.status_code)); continue
        s = BeautifulSoup(r.text, "lxml")
        canon = [l.get("href") for l in s.find_all("link", rel="canonical")]
        if canon != [u]:
            problems.append((u, "canonical", canon))
        robots = s.find("meta", attrs={"name": "robots"})
        if robots and "noindex" in robots.get("content", ""):
            problems.append((u, "noindex in sitemap page", robots.get("content")))
        title = s.title.string if s.title else ""
        if not (10 <= len(title) <= 70):
            problems.append((u, "title length", len(title)))
        d = s.find("meta", attrs={"name": "description"})
        if not d or not (50 <= len(d.get("content", "")) <= 160):
            problems.append((u, "description", d.get("content") if d else None))
        if len(s.find_all("h1")) != 1:
            problems.append((u, "h1 count", len(s.find_all("h1"))))
        og = s.find("meta", attrs={"property": "og:image"})
        if not og or not og.get("content", "").startswith("https://donttrade.ca/"):
            problems.append((u, "og:image", og))
        for a in s.find_all("a", href=True):
            if a.get("target") == "_blank" and not {"noopener", "noreferrer"} & set(a.get("rel") or []):
                problems.append((u, "target=_blank without noopener", a["href"]))
            if a["href"].startswith("http://"):
                problems.append((u, "http:// link", a["href"]))
        for sc in s.find_all("script", type="application/ld+json"):
            try:
                json.loads(sc.string)
            except Exception as e:
                problems.append((u, "bad JSON-LD", str(e)))
        if re.search(r"https?://(buy|checkout)\.stripe\.com/", r.text):
            problems.append((u, "public Stripe payment link", "present"))
    assert not problems, "\n".join(map(str, problems))


def test_og_images_load():
    seen = set()
    for u in _sitemap()[:5]:
        s = BeautifulSoup(get(u).text, "lxml")
        og = s.find("meta", attrs={"property": "og:image"})["content"]
        if og in seen:
            continue
        seen.add(og)
        r = get(og)
        assert r.status_code == 200 and r.headers.get("content-type", "").startswith("image/"), og


def test_feed_parses():
    r = get(BASE + "/feed.xml")
    root = ET.fromstring(r.content)
    ns = {"a": "http://www.w3.org/2005/Atom"}
    entries = root.findall("a:entry", ns)
    assert entries
    ids = [e.find("a:id", ns).text for e in entries]
    assert len(ids) == len(set(ids))
    for e in entries:
        for k in ("title", "id", "updated", "link"):
            assert e.find("a:" + k, ns) is not None
        assert e.find("a:link", ns).get("href").startswith("https://donttrade.ca/")


# ---------- secrets in repo (HEAD + history) ----------
SECRET_RE = re.compile(r"(sk_live_|sk_test_|rk_live_|ghp_[A-Za-z0-9]{10}|github_pat_|AKIA[0-9A-Z]{16}|xox[bp]-|"
                       r"AIza[0-9A-Za-z_-]{30}|-----BEGIN [A-Z ]*PRIVATE KEY|buy\.stripe\.com/|checkout\.stripe\.com/|"
                       r"APCA-API-(KEY|SECRET)-ID\s*[:=]\s*\S{8})")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
ALLOWED_EMAILS = {"donttrade.research@gmail.com", "you@example.com", "me@example.com"}


def _gh(path, raw=False):
    cmd = ["gh", "api", path] + (["-H", "Accept: application/vnd.github.raw"] if raw else [])
    return subprocess.run(cmd, capture_output=True, text=True, check=True).stdout


def _gh_bytes(path):
    """A raw blob as bytes: history holds binary files, and text=True crashed on them (UnicodeDecodeError)."""
    cmd = ["gh", "api", path, "-H", "Accept: application/vnd.github.raw"]
    return subprocess.run(cmd, capture_output=True, check=True).stdout


def blob_findings(path, sha, data):
    """Secrets and stray emails in one blob. A blob with a NUL byte in its first 8 KB is binary and
    skipped; text is decoded with errors='replace', so a stray non-UTF-8 byte cannot hide a finding."""
    if b"\x00" in data[:8192]:
        return []
    text = data.decode("utf-8", errors="replace")
    bad = []
    for m in SECRET_RE.finditer(text):
        bad.append((path, sha[:7], m.group(0)[:4] + "…"))  # never print full secret
    for m in EMAIL_RE.findall(text):
        if m.lower() not in ALLOWED_EMAILS and not m.lower().endswith("users.noreply.github.com"):
            bad.append((path, sha[:7], "email:" + m.split("@")[0][:4] + "…@" + m.split("@")[1]))
    return bad


@pytest.mark.skipif(os.environ.get("DT_SKIP_REPO") == "1", reason="repo scan disabled")
def test_repo_history_has_no_secrets_or_stray_emails():
    try:
        commits = json.loads(_gh(f"repos/{REPO}/commits?per_page=100"))
    except Exception as e:
        pytest.skip(f"gh not available: {e}")
    blobs = {}
    for c in commits:
        tree = json.loads(_gh(f"repos/{REPO}/git/trees/{c['sha']}?recursive=1"))
        for e in tree["tree"]:
            if e["type"] == "blob" and not e["path"].endswith((".png", ".pdf", ".woff2")):
                blobs.setdefault(e["sha"], e["path"])
    bad = []
    for sha, path in blobs.items():
        bad += blob_findings(path, sha, _gh_bytes(f"repos/{REPO}/git/blobs/{sha}"))
    assert not bad, bad
