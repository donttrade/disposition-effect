"""Step 3: the build — every baseline URL, byte-identical, and each failure mode fails loudly."""
import hashlib
import os
import shutil
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
SITE = os.path.join(REPO, "site")
sys.path.insert(0, SITE)
import build as B  # noqa: E402


def run_build(tmp_path, name, **env):
    out = tmp_path / name
    e = {**os.environ, "DT_OUT": str(out), **env}
    if "DT_DEV" not in env:
        e.pop("DT_DEV", None)
    r = subprocess.run([sys.executable, os.path.join(SITE, "build.py")], env=e, capture_output=True, text=True)
    return r, out


def tree_hash(root):
    h = hashlib.sha256()
    for d, dirs, files in os.walk(root):
        dirs.sort()
        for f in sorted(files):
            p = os.path.join(d, f)
            h.update(os.path.relpath(p, root).encode())
            with open(p, "rb") as fh:
                h.update(fh.read())
    return h.hexdigest()


def toml_with(tmp_path, **flags):
    src = open(os.path.join(SITE, "config", "site.toml"), encoding="utf-8").read()
    for k, v in flags.items():
        src = src.replace(f"{k} = false", f"{k} = {str(v).lower()}", 1)
    p = tmp_path / "site.toml"
    p.write_text(src, encoding="utf-8")
    return str(p)


def test_build_has_every_baseline_url_and_is_deterministic(tmp_path):
    r1, a = run_build(tmp_path, "a")
    assert r1.returncode == 0, r1.stderr
    r2, b = run_build(tmp_path, "b")
    assert r2.returncode == 0, r2.stderr
    assert tree_hash(a) == tree_hash(b)
    paths, ids = B.read_baseline()
    assert len(paths) > 60 and len(ids) > 20
    assert not (a / "dev").exists(), "dev pages must not be built without DT_DEV=1"


def test_missing_baseline_url_fails_with_path(tmp_path):
    bl = tmp_path / "baseline.txt"
    bl.write_text(open(B.BASELINE).read() + "/no-such-page/\n")
    r, _ = run_build(tmp_path, "x", DT_BASELINE=str(bl))
    assert r.returncode == 1 and "/no-such-page/" in r.stderr


def test_missing_linked_id_fails(tmp_path):
    bl = tmp_path / "baseline.txt"
    bl.write_text(open(B.BASELINE).read() + "/pricing/#no-such-id\n")
    r, _ = run_build(tmp_path, "x", DT_BASELINE=str(bl))
    assert r.returncode == 1 and "no-such-id" in r.stderr


def test_flag_mismatch_fails(tmp_path):
    r, _ = run_build(tmp_path, "x", DT_SITE_TOML=toml_with(tmp_path, trader_first_home=True))
    assert r.returncode == 1 and "flag mismatch" in r.stderr


def test_analytics_without_token_fails(tmp_path):
    r, _ = run_build(tmp_path, "x", DT_SITE_TOML=toml_with(tmp_path, analytics=True))
    assert r.returncode == 1 and "cf_beacon_token" in r.stderr


def test_paid_page_planted_with_flag_off_fails(tmp_path):
    r, out = run_build(tmp_path, "x")
    assert r.returncode == 0
    flags = {"paid_report": False}
    (out / "welcome").mkdir()
    (out / "welcome" / "index.html").write_text("<p>welcome</p>")
    with pytest.raises(B.BuildError, match="/welcome/"):
        B.verify(str(out), flags)
    shutil.rmtree(out / "welcome")
    (out / "about" / "index.html").write_text('<div data-requires-flag="paid_report">buy</div>')
    with pytest.raises(B.BuildError, match="paid-flagged markup"):
        B.verify(str(out), flags)


def test_paid_on_needs_filled_private_toml(tmp_path):
    toml = toml_with(tmp_path, paid_report=True, trader_first_home=True)
    priv = os.path.join(SITE, "config", "private.toml")
    had = os.path.exists(priv)
    if had:
        pytest.skip("a real private.toml exists; not touching it")
    try:
        shutil.copyfile(os.path.join(SITE, "config", "private.example.toml"), priv)
        r, _ = run_build(tmp_path, "x", DT_SITE_TOML=toml)
        assert r.returncode == 1 and "placeholder" in r.stderr
        r, _ = run_build(tmp_path, "y", DT_SITE_TOML=toml, DT_ALLOW_PLACEHOLDERS="1")
        assert r.returncode == 0, r.stderr
    finally:
        os.remove(priv)


def test_private_toml_is_gitignored():
    r = subprocess.run(["git", "check-ignore", "site/config/private.toml"], cwd=REPO, capture_output=True, text=True)
    assert r.returncode == 0


def test_home_is_new_template_and_others_pass_through(tmp_path):
    r, out = run_build(tmp_path, "x")
    assert r.returncode == 0
    home = (out / "index.html").read_text()
    assert "/static/css/site.css" in home and "Measure the gap between your traders" in home
    assert (out / "pricing" / "index.html").read_bytes() == open(os.path.join(REPO, "docs/pricing/index.html"), "rb").read()


def test_harvest_check_passes_on_live_pricing():
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "harvest_prices.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout
