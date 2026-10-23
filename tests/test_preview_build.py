"""Delivery plan C-17: preview builds (DT_PREVIEW=<name>) for the paid-preview and live-check Pages branches.

A preview build has <meta name="robots" content="noindex,nofollow"> and the "Preview, not the live site" band on
every page and a robots.txt that disallows everything; a build without DT_PREVIEW has none of them. ./site/run.sh
bundle puts a preview bundle only on the branch of that name, and those branches take nothing else (checked in a
throwaway git repo: the real docs/ is never bundled here)."""
import os
import re
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402
import lint as L  # noqa: E402
from test_c14_legal_copy import _build  # noqa: E402  (the same fake paid values)


def _preview_build(tmp, name, preview, paid=True):
    return _build(tmp, name, paid=paid, extra_env={"DT_PREVIEW": preview} if preview is not None else None)


def html_pages(out):
    return [p for p in out.rglob("*.html")]


@pytest.fixture(scope="module")
def preview(tmp_path_factory):
    r, out = _preview_build(tmp_path_factory.mktemp("c17"), "pv", "paid-preview")
    assert r.returncode == 0, r.stderr
    return out


@pytest.fixture(scope="module")
def plain(tmp_path_factory):
    r, out = _preview_build(tmp_path_factory.mktemp("c17"), "plain", None)
    assert r.returncode == 0, r.stderr
    return out


def test_preview_has_noindex_and_band_on_every_page(preview):
    pages = html_pages(preview)
    assert len(pages) > 30
    for p in pages:
        h = p.read_text(encoding="utf-8")
        assert h.count('<meta name="robots" content="noindex,nofollow">') == 1, p
        assert len(re.findall(r'<meta name="robots"', h)) == 1, p          # no second, weaker robots meta
        assert h.count("data-preview-band") == 1, p
    home = (preview / "index.html").read_text(encoding="utf-8")
    band = re.search(r"(?s)<p [^>]*data-preview-band[^>]*>(.*?)</p>", home).group(1)
    assert re.sub(r"<[^>]+>", "", band) == ("Preview, not the live site. This copy (paid-preview) is for testing; "
                                           "the live site is https://donttrade.ca.")
    assert (preview / "robots.txt").read_text(encoding="utf-8") == "User-agent: *\nDisallow: /\n"
    assert home.index("data-preview-band") < home.index('<main id="main"')


def test_preview_band_passes_the_lint(preview, monkeypatch):
    monkeypatch.setenv("DT_PRIVATE_TOML", str(preview.parent / "pv-private.toml"))
    assert L.lint_build(str(preview), paid=True) == []


def test_build_without_preview_has_none_of_it(plain):
    for p in html_pages(plain):
        h = p.read_text(encoding="utf-8")
        assert "noindex,nofollow" not in h and "data-preview-band" not in h, p
    robots = (plain / "robots.txt").read_text(encoding="utf-8")
    assert "Allow: /" in robots and "Disallow: /\n" not in robots and "Sitemap:" in robots
    assert '<meta name="robots" content="noindex">' in (plain / "welcome" / "index.html").read_text(encoding="utf-8")


def test_free_preview_build_also_works(tmp_path):
    r, out = _preview_build(tmp_path, "freepv", "live-check", paid=False)
    assert r.returncode == 0, r.stderr
    assert B.preview_problems(str(out), "live-check") == []


@pytest.mark.parametrize("bad", ["Paid-Preview", "paid_preview", "-x", "x-", "a" * 41, "paid preview"])
def test_bad_preview_names_fail(tmp_path, bad):
    r, _ = _preview_build(tmp_path, "bad", bad)
    assert r.returncode == 1 and "DT_PREVIEW=" in r.stderr, r.stderr


def test_planted_preview_markup_fails_the_check(plain, preview, tmp_path):
    assert B.preview_problems(str(plain), None) == []
    assert B.preview_problems(str(preview), "paid-preview") == []
    c = tmp_path / "c"
    shutil.copytree(plain, c)
    p = c / "about" / "index.html"
    p.write_text(p.read_text(encoding="utf-8").replace("<body>", "<body><p data-preview-band>x</p>"), encoding="utf-8")
    assert any("preview markup in a build without DT_PREVIEW" in x for x in B.preview_problems(str(c), None))
    d = tmp_path / "d"
    shutil.copytree(preview, d)
    p = d / "terms" / "index.html"
    p.write_text(p.read_text(encoding="utf-8").replace('content="noindex,nofollow"', 'content="index"'), encoding="utf-8")
    assert any(x.startswith(os.path.join("terms", "index.html")) for x in B.preview_problems(str(d), "paid-preview"))


# ------------------------------------------------------------------ run.sh bundle: which branch takes which bundle
@pytest.fixture
def bundle_repo(tmp_path):
    repo = tmp_path / "repo"
    (repo / "site").mkdir(parents=True)
    shutil.copy(os.path.join(REPO, "site", "run.sh"), repo / "site" / "run.sh")
    # a stub build: writes one page, so a refused bundle is visible as an unchanged docs/
    (repo / "site" / "build.py").write_text(
        "import os\nos.makedirs('site/_site', exist_ok=True)\n"
        "open('site/_site/index.html','w').write('built ' + os.environ.get('DT_PREVIEW', '-'))\n")
    (repo / "docs").mkdir()
    (repo / "docs" / "index.html").write_text("old")
    g = lambda *a: subprocess.run(["git", *a], cwd=repo, check=True, capture_output=True)  # noqa: E731
    g("init", "-q", "-b", "main")
    g("-c", "user.name=t", "-c", "user.email=t@example.invalid", "add", ".")
    g("-c", "user.name=t", "-c", "user.email=t@example.invalid", "commit", "-q", "-m", "x")

    def bundle(branch, preview=None):
        g("checkout", "-q", "-B", branch)
        env = {k: v for k, v in os.environ.items() if k != "DT_PREVIEW"}
        env["DT_BUNDLE"] = "yes"
        if preview is not None:
            env["DT_PREVIEW"] = preview
        r = subprocess.run(["sh", "site/run.sh", "bundle"], cwd=repo, env=env, capture_output=True, text=True)
        return r, (repo / "docs" / "index.html").read_text()
    return bundle


@pytest.mark.parametrize("branch,preview,ok", [
    ("main", None, True), ("delivery-39", None, True),
    ("main", "paid-preview", False), ("delivery-39", "paid-preview", False),
    ("paid-preview", None, False), ("live-check", None, False),
    ("paid-preview", "live-check", False), ("live-check", "paid-preview", False),
    ("paid-preview", "paid-preview", True), ("live-check", "live-check", True),
])
def test_bundle_branch_rule(bundle_repo, branch, preview, ok):
    r, docs = bundle_repo(branch, preview)
    if ok:
        assert r.returncode == 0 and docs == f"built {preview or '-'}", r.stdout + r.stderr
    else:
        assert r.returncode == 1 and docs == "old", r.stdout + r.stderr
