"""Step 2: design system — contrast, fonts budget, styleguide overflow and axe in both themes."""
import os
import subprocess
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
from a11y import axe_violations, horizontal_overflow  # noqa: E402

FONTS = os.path.join(REPO, "site", "static", "fonts")


def test_contrast_script_passes():
    r = subprocess.run([sys.executable, os.path.join(REPO, "checks", "contrast.py")], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout[-2000:]


def test_fonts_budget_and_licence():
    woff = [f for f in os.listdir(FONTS) if f.endswith(".woff2")]
    assert len(woff) == 3
    total = sum(os.path.getsize(os.path.join(FONTS, f)) for f in woff)
    assert total <= 90 * 1024, total
    for f in woff:
        with open(os.path.join(FONTS, f), "rb") as fh:
            assert fh.read(4) == b"wOF2", f
    assert "SIL Open Font License" in open(os.path.join(FONTS, "OFL.txt")).read()


@pytest.mark.parametrize("scheme", ["light", "dark"])
@pytest.mark.parametrize("width", [320, 375, 1280])
def test_styleguide(browser, repo_server, scheme, width):
    # bypass_csp only so axe can be injected; the page's own scripts are external.
    ctx = browser.new_context(color_scheme=scheme, viewport={"width": width, "height": 900}, bypass_csp=True)
    page = ctx.new_page()
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.goto(repo_server + "/site/dev/styleguide.html")
    page.wait_for_load_state("networkidle")
    assert horizontal_overflow(page) == []
    assert axe_violations(page) == []
    assert not errors
    ctx.close()


def test_toggle_switches_and_survives_blocked_storage(browser, repo_server):
    ctx = browser.new_context(color_scheme="light")
    page = ctx.new_page()
    page.add_init_script("Object.defineProperty(window, 'localStorage', {get() { throw new Error('blocked'); }})")
    page.goto(repo_server + "/site/dev/styleguide.html")
    btn = page.locator("[data-theme-toggle]")
    assert btn.is_visible()
    btn.click()
    assert page.evaluate("document.documentElement.dataset.theme") == "dark"
    assert btn.get_attribute("aria-pressed") is None   # QA 25 Oct: named by the action instead
    ctx.close()


def test_tabs_keyboard(browser, repo_server):
    ctx = browser.new_context()
    page = ctx.new_page()
    page.goto(repo_server + "/site/dev/styleguide.html#firms")
    assert page.get_attribute("#tab-f", "aria-selected") == "true"
    assert page.is_hidden("#panel-t")
    page.focus("#tab-f")
    page.keyboard.press("ArrowRight")
    assert page.get_attribute("#tab-t", "aria-selected") == "true"
    assert page.evaluate("document.activeElement.id") == "tab-t"
    ctx.close()
