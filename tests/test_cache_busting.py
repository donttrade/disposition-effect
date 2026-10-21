"""Tester N5 (motion fixes, 21 Oct 2026): cache-busting of CSS and JS.

The host serves /static/ with max-age=600, so for 10 minutes after a deploy new HTML could run with the old
cached CSS or JS. The build (build.version_assets) appends ?v=<first 8 hex of the SHA-256 of the served file>
to every CSS/JS URL in every page, and to every relative import / module-worker URL between our own scripts.
A script's hash covers its rewritten imports, so changing a module deep in the engine changes the URL of
every module above it, up to the page.
"""
import hashlib
import os
import re
import shutil
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "site"))
import build as B  # noqa: E402

REF = re.compile(r'(?:src|href)="(/static/[^"?#]+\.(?:js|css))(\?v=([0-9a-f]{8}))?"')
SPEC = re.compile(r"""(?:\bfrom\s*|\bimport\s*\(?\s*|\bnew URL\(\s*)['"](\.{1,2}/[^'"?#\s]+\.js)(\?v=([0-9a-f]{8}))?['"]""")


def _v(path):
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()[:8]


def test_every_css_and_js_url_in_every_page_carries_the_hash_of_the_served_file(built_site):
    out, n = str(built_site["out"]), 0
    for root, _, files in os.walk(out):
        for name in files:
            if name.endswith(".html"):
                html = open(os.path.join(root, name), encoding="utf-8").read()
                for m in REF.finditer(html):
                    n += 1
                    assert m.group(2), (name, m.group(1), "unversioned")
                    assert m.group(3) == _v(os.path.join(out, m.group(1).lstrip("/"))), (name, m.group(1))
    assert n > 100   # theme.js, nav.js and site.css on every page, plus the page scripts


def test_every_import_between_our_scripts_is_versioned_except_a_module_this_build_leaves_out(built_site):
    static, n, left = os.path.join(str(built_site["out"]), "static"), 0, []
    for root, _, files in os.walk(static):
        for name in files:
            if name.endswith(".js"):
                fp = os.path.join(root, name)
                for m in SPEC.finditer(open(fp, encoding="utf-8").read()):
                    target = os.path.normpath(os.path.join(root, m.group(1)))
                    if not os.path.exists(target):
                        left.append(os.path.relpath(target, static))   # behind a flag that is off here
                        continue
                    n += 1
                    assert m.group(3) == _v(target), (os.path.relpath(fp, static), m.group(1))
    assert n > 40
    assert left == [B.BADGES_JS], left        # free_badges = false: trade-stats-badges.js is not shipped


def test_the_built_scripts_are_the_sources_apart_from_the_import_queries(built_site):
    src = os.path.join(REPO, "site", "static")
    for root, _, files in os.walk(os.path.join(str(built_site["out"]), "static")):
        for name in files:
            if name.endswith((".js", ".css")):
                fp = os.path.join(root, name)
                rel = os.path.relpath(fp, os.path.join(str(built_site["out"]), "static"))
                built = re.sub(r"\?v=[0-9a-f]{8}(['\"])", r"\1", open(fp, encoding="utf-8").read())
                assert built == open(os.path.join(src, rel), encoding="utf-8").read(), rel


def _mini(tmp_path, engine="export const x = 1;\n"):
    out = tmp_path / "_site"
    (out / "static" / "js" / "engine").mkdir(parents=True)
    (out / "static" / "css").mkdir(parents=True)
    (out / "static" / "js" / "engine" / "core.js").write_text(engine, encoding="utf-8")
    (out / "static" / "js" / "tool.js").write_text(
        "import { x } from './engine/core.js';\nconst w = new Worker(new URL('./engine/core.js', import.meta.url));\n",
        encoding="utf-8")
    (out / "static" / "css" / "site.css").write_text("body{}\n", encoding="utf-8")
    (out / "index.html").write_text('<link rel="stylesheet" href="/static/css/site.css">'
                                    '<script src="/static/js/tool.js" type="module"></script>\n', encoding="utf-8")
    return out


def test_a_change_deep_in_the_module_graph_changes_the_page_url(tmp_path):
    a = B.version_assets(str(_mini(tmp_path / "a")))
    b = B.version_assets(str(_mini(tmp_path / "b", engine="export const x = 2;\n")))
    assert a["/static/css/site.css"] == b["/static/css/site.css"]
    assert a["/static/js/engine/core.js"] != b["/static/js/engine/core.js"]
    assert a["/static/js/tool.js"] != b["/static/js/tool.js"], "tool.js itself did not change, its import did"
    page = (tmp_path / "b" / "_site" / "index.html").read_text(encoding="utf-8")
    assert f'src="/static/js/tool.js?v={b["/static/js/tool.js"]}"' in page
    tool = (tmp_path / "b" / "_site" / "static" / "js" / "tool.js").read_text(encoding="utf-8")
    assert tool.count(f"./engine/core.js?v={b['/static/js/engine/core.js']}'") == 2   # import + worker URL
    assert B.unversioned_problem(page) is None


def test_missing_targets_cycles_and_unversioned_urls_fail_the_build(tmp_path):
    out = _mini(tmp_path / "missing")
    (out / "index.html").write_text('<script src="/static/js/gone.js" defer></script>', encoding="utf-8")
    with pytest.raises(B.BuildError, match="gone.js, which is not in the build"):
        B.version_assets(str(out))
    out = _mini(tmp_path / "cycle", engine="import { y } from '../tool.js';\n")
    with pytest.raises(B.BuildError, match="import cycle"):
        B.version_assets(str(out))
    out = _mini(tmp_path / "typo", engine="import { y } from './nope.js';\n")
    with pytest.raises(B.BuildError, match="nope.js, which is not in the build"):
        B.version_assets(str(out))
    assert "unversioned asset URL" in B.unversioned_problem('<script src="/static/js/nav.js" defer></script>')
    assert B.unversioned_problem('<script src="/static/js/nav.js?v=0123abcd" defer></script>') is None


def test_verify_refuses_a_built_page_with_an_unversioned_url(built_site, tmp_path):
    out = tmp_path / "_site"
    shutil.copytree(built_site["out"], out)
    fp = out / "pricing" / "index.html"
    fp.write_text(re.sub(r"(/static/css/site\.css)\?v=[0-9a-f]{8}", r"\1", fp.read_text(encoding="utf-8")),
                  encoding="utf-8")
    with pytest.raises(B.BuildError, match="unversioned asset URL"):
        B.verify(str(out), {"paid_report": False, "pilot_checkout": False})


def test_the_browser_only_ever_requests_versioned_css_and_js(browser, built_site):
    """The trade-stats tool loads a module graph, a module worker and runs the sample: every CSS/JS request
    (page scripts, imports, the worker) carries ?v=."""
    ctx = browser.new_context()
    urls = []
    ctx.on("request", lambda r: urls.append(r.url))
    pg = ctx.new_page()
    for path in ("/", "/for-firms/", "/tools/trade-stats/"):
        pg.goto(built_site["url"] + path)
    pg.click("#ts-sample-btn")
    pg.wait_for_selector("#ts-out dl.stats dd")
    pg.wait_for_timeout(300)
    ctx.close()
    assets = [u for u in urls if re.search(r"/static/.+\.(?:js|css)(?:\?|$)", u)]
    assert any("engine/index.js?v=" in u for u in assets) and any("worker" in u for u in assets), assets
    assert [u for u in assets if not re.search(r"\?v=[0-9a-f]{8}$", u)] == []
