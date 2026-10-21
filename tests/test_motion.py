"""Motion plan (ARCHITECT-MOTION-PLAN 2026-10-21): the acceptance invariants I1-I18 and I20.

I21 (freeze integrity of the hero capture) is tests/test_pages.py::test_home_hero_is_the_real_dashboard_capture.
I19 (Lighthouse) is a manual Tester run. The CLS budget "total <= baseline" is measured by the Tester
against the baseline build; here every shift must come from outside the motion elements and total < 0.01.

Motion: M1 button lift (CSS), M2 fade-up ([data-reveal], motion.js), M3 hero = live capture of the
dashboard, M4 veil wipe over the chart (CSS), M5 count-up on the 6 hero sample tiles (motion.js).
"""
import json
import os
import re
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "checks"))
sys.path.insert(0, os.path.join(REPO, "site"))
from a11y import AXE  # noqa: E402
import build as B  # noqa: E402

MOTION = ["/", "/for-firms/", "/for-traders/", "/for-platforms/"]
PARTIAL = os.path.join(REPO, "site", "templates", "partials", "hero_dashboard.html")
FINAL = re.findall(r"<dd data-count[^>]*>([^<]*)</dd>", open(PARTIAL, encoding="utf-8").read())
OLD_ALT = ("The free trade-stats dashboard on the synthetic sample file: 160 closed trades, a net result of plus "
           "277.95 US dollars, win rate 51.9%, profit factor 1.14, and an equity and drawdown chart.")
DESK = {"width": 1280, "height": 800}
PHONE = {"width": 375, "height": 812}

# Recorded from the first script on every document: layout shifts (with whether a source sits inside a
# motion element), long tasks, motion.js's own time in long animation frames (the ~50 ms first-render
# frame exists at baseline without any script; motion.js sometimes runs inside it, so the frame's
# duration is not motion.js's), whether .rv / data-cu ever appeared, and the hero dd text
# every 50 ms (it must always be final: the count is drawn by ::after from data-cu).
INIT = """
window.__m = {shifts: [], lt: [], loaf: [], rvSeen: false, cuSeen: false, cuValues: [], dd: []};
try { new PerformanceObserver(l => l.getEntries().forEach(e => { if (!e.hadRecentInput) __m.shifts.push({v: e.value,
  motion: e.sources.some(s => s.node && s.node.nodeType === 1 && !!s.node.closest('[data-reveal], .hero-dash, .btn')),
  src: e.sources.map(s => s.node ? s.node.nodeName + '.' + (s.node.className || '') : '?')}); }))
  .observe({type: 'layout-shift', buffered: true}); } catch (e) {}
try { new PerformanceObserver(l => l.getEntries().forEach(e => __m.lt.push(Math.round(e.duration))))
  .observe({type: 'longtask', buffered: true}); } catch (e) {}
try { new PerformanceObserver(l => l.getEntries().forEach(e => (e.scripts || []).forEach(s => {
  if ((s.sourceURL || '').includes('motion.js')) __m.loaf.push(Math.round(s.duration)); })))
  .observe({type: 'long-animation-frame', buffered: true}); } catch (e) {}
new MutationObserver(rs => rs.forEach(r => {
  const t = r.target;
  if (t.classList && t.classList.contains('rv')) __m.rvSeen = true;
  if (r.attributeName === 'data-cu' && t.hasAttribute('data-cu')) { __m.cuSeen = true; __m.cuValues.push(t.getAttribute('data-cu')); }
})).observe(document, {subtree: true, attributes: true, attributeFilter: ['class', 'data-cu']});
setInterval(() => { const d = document.querySelectorAll('.hero-dash [data-count]');
  if (d.length) __m.dd.push([...d].map(e => e.textContent)); }, 50);
"""
HIDDEN = """() => [...document.querySelectorAll('[data-reveal], [data-reveal-stagger] > *, .hero-dash [data-count]')]
  .filter(e => getComputedStyle(e).opacity !== '1' || getComputedStyle(e).visibility !== 'visible').length"""
VALUES = "() => [...document.querySelectorAll('.hero-dash [data-count]')].map(e => e.textContent)"
OVERFLOW = "() => document.documentElement.scrollWidth - document.documentElement.clientWidth"
ANIMS = "() => document.getAnimations().map(a => a.animationName || a.transitionProperty)"


def _ctx(browser, vp=DESK, init=True, **kw):
    ctx = browser.new_context(viewport=vp, **kw)
    if init:
        ctx.add_init_script(INIT)
    return ctx


def _scroll(pg, step=300, pause=60):
    h = pg.evaluate("document.documentElement.scrollHeight")
    for _ in range(0, h + 800, step):
        pg.mouse.wheel(0, step)
        pg.wait_for_timeout(pause)
    pg.wait_for_timeout(1000)


def _main_text(pg):
    return pg.evaluate("() => document.querySelector('main').textContent.replace(/\\s+/g, ' ').trim()")


# ------------------------------------------------------------------ I1, I3: no JS, content parity
def test_i1_i3_no_js_nothing_hidden_and_same_text_in_every_mode(browser, built_site):
    texts = {}
    for mode, kw in (("nojs", {"java_script_enabled": False}), ("reduced", {"reduced_motion": "reduce"}),
                     ("motion", {})):
        ctx = _ctx(browser, init=False, **kw)
        pg = ctx.new_page()
        for path in MOTION:
            pg.goto(built_site["url"] + path)
            if mode == "nojs":
                assert pg.evaluate(HIDDEN) == 0, path
                assert pg.evaluate(ANIMS) == [], path
                if path == "/":
                    assert pg.evaluate(VALUES) == FINAL
            else:
                pg.wait_for_timeout(3000)
            texts.setdefault(path, {})[mode] = _main_text(pg)
        ctx.close()
    for path, t in texts.items():
        assert t["nojs"] == t["reduced"] == t["motion"], path


# ------------------------------------------------------------------ I2: reduced motion
def test_i2_reduced_motion_runs_no_animation(browser, built_site):
    ctx = _ctx(browser, reduced_motion="reduce")
    pg = ctx.new_page()
    for path in MOTION:
        pg.goto(built_site["url"] + path)
        pg.wait_for_timeout(300)
        assert not pg.evaluate("document.documentElement.classList.contains('dt-motion')")
        assert pg.evaluate(ANIMS) == [], path
        _scroll(pg, step=600, pause=30)
        assert pg.evaluate(ANIMS) == [], path
        for b in pg.locator(".btn:visible").all():
            b.hover()
            b.focus()
            assert pg.evaluate(ANIMS) == [], path
            assert b.evaluate("e => getComputedStyle(e).transform") == "none"
        m = pg.evaluate("__m")
        assert not m["rvSeen"] and not m["cuSeen"], path
        assert pg.evaluate("document.querySelectorAll('.rv, .cu-on').length") == 0
    ctx.close()


# ------------------------------------------------------------------ I4: the DOM text is always final
def test_i4_hero_text_is_always_the_final_value(browser, built_site):
    ctx = _ctx(browser)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/", wait_until="commit")
    pg.wait_for_timeout(2500)
    m = pg.evaluate("__m")
    assert len(m["dd"]) >= 30 and all(s == FINAL for s in m["dd"]), m["dd"][:3]
    assert m["cuSeen"], "the count-up ran (in data-cu only)"
    assert set(m["cuValues"]) - set(FINAL), "intermediate values appeared, in data-cu"
    assert pg.evaluate("document.querySelectorAll('[data-cu], .cu-on').length") == 0
    assert pg.evaluate("document.querySelectorAll('.hero-dash .cu-done').length") == 6
    ctx.close()


# ------------------------------------------------------------------ I5, I6, I11: CLS, long tasks, 375 px
@pytest.mark.parametrize("vp", [DESK, PHONE], ids=["1280", "375"])
def test_i5_i6_i11_no_motion_layout_shift_no_long_task_no_overflow(browser, built_site, vp):
    ctx = _ctx(browser, vp)
    pg = ctx.new_page()
    for path in MOTION:
        pg.goto(built_site["url"] + path)
        assert pg.evaluate(OVERFLOW) == 0, path
        pg.wait_for_timeout(1500)
        h = pg.evaluate("document.documentElement.scrollHeight")
        for _ in range(0, h + 800, 300):
            pg.mouse.wheel(0, 300)
            pg.wait_for_timeout(60)
            assert pg.evaluate(OVERFLOW) == 0, path   # during the reveals
        pg.wait_for_timeout(1000)
        assert pg.evaluate(OVERFLOW) == 0, path
        if vp is DESK:
            for b in pg.locator(".btn:visible").all():
                b.hover()
            pg.wait_for_timeout(300)
        m = pg.evaluate("__m")
        assert [s for s in m["shifts"] if s["motion"]] == [], (path, m["shifts"])
        assert sum(s["v"] for s in m["shifts"]) < 0.01, (path, m["shifts"])  # pre-existing: the nav toggle
        assert [d for d in m["lt"] if d >= 50] == [], (path, m["lt"])
        assert [d for d in m["loaf"] if d >= 50] == [], (path, m["loaf"])
    ctx.close()


# ------------------------------------------------------------------ I7, I17: composited only, timing
SAMPLE_ANIMS = """() => document.getAnimations().map(a => {
  const t = a.effect.getComputedTiming();
  const props = a.transitionProperty ? [a.transitionProperty]
    : a.effect.getKeyframes().flatMap(k => Object.keys(k).filter(x => !['offset', 'computedOffset', 'easing', 'composite'].includes(x)));
  return {props, end: t.delay + t.duration, iter: t.iterations, name: a.animationName || a.transitionProperty,
          rv: !!(a.effect.target && a.effect.target.classList && a.effect.target.classList.contains('rv-in'))};
})"""


def test_i7_i17_only_transform_and_opacity_and_every_motion_ends_in_time(browser, built_site):
    ctx = _ctx(browser)
    pg = ctx.new_page()
    seen = []
    for path in MOTION:
        pg.goto(built_site["url"] + path, wait_until="commit")
        for _ in range(15):                       # the first 1.5 s
            seen += pg.evaluate(SAMPLE_ANIMS)
            pg.wait_for_timeout(100)
        h = pg.evaluate("document.documentElement.scrollHeight")
        for _ in range(0, h + 800, 300):          # mid-scroll, while blocks reveal
            pg.mouse.wheel(0, 300)
            pg.wait_for_timeout(40)
            seen += pg.evaluate(SAMPLE_ANIMS)
    ctx.close()
    assert any(a["name"] == "dt-wipe" for a in seen) and any(a["rv"] for a in seen)
    for a in seen:
        assert set(a["props"]) <= {"opacity", "transform", "visibility"}, a
        assert a["iter"] == 1 and a["end"] <= 5000, a          # WCAG 2.2.2: nothing loops or lasts 5 s
        if a["rv"]:
            assert a["end"] <= 680, a                         # 500 ms + at most 180 ms stagger
        if a["name"] == "dt-wipe":
            assert a["end"] <= 1150, a                        # 150 ms delay + 1000 ms


def test_i17_revealed_blocks_reach_full_opacity_within_680ms(browser, built_site):
    ctx = _ctx(browser)
    ctx.add_init_script("""window.__rv = []; new MutationObserver(rs => rs.forEach(r => {
      const t = r.target; if (!t.classList || !t.classList.contains('rv-in') || t.__t0) return;
      t.__t0 = performance.now();
      (function f() { if (getComputedStyle(t).opacity === '1') __rv.push(performance.now() - t.__t0); else requestAnimationFrame(f); })();
    })).observe(document, {subtree: true, attributes: true, attributeFilter: ['class']});""")
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/for-firms/")
    pg.wait_for_timeout(500)
    _scroll(pg)
    took = pg.evaluate("__rv")
    ctx.close()
    assert len(took) >= 5
    assert max(took) <= 680 + 50, took   # 50 ms: frame and headless scheduling slack


# ------------------------------------------------------------------ I8: budgets
def test_i8_budgets():
    assert os.path.getsize(os.path.join(REPO, "site", "static", "js", "motion.js")) <= 3072
    css = open(os.path.join(REPO, "site", "static", "css", "site.css"), encoding="utf-8").read()
    i = css.index("/* ------------------------------------------------------------------ motion (ARCHITECT-MOTION-PLAN")
    assert len(css[i:].encode("utf-8")) <= 5000
    assert os.path.getsize(PARTIAL) <= 8 * 1024


# ------------------------------------------------------------------ I9: scope
def test_i9_motion_only_on_the_four_pages_in_the_build(built_site):
    out = built_site["out"]
    for root, _, files in os.walk(out):
        for name in files:
            if name.endswith(".html"):
                fp = os.path.join(root, name)
                path = "/" + os.path.relpath(fp, out).replace(os.sep, "/").replace("index.html", "")
                html = open(fp, encoding="utf-8").read()
                if path in MOTION:
                    assert "/static/js/motion.js" in html, path
                else:
                    for x in ("/static/js/motion.js", "data-reveal", "data-count", "hero-dash"):
                        assert x not in html, (path, x)


def test_i9_non_motion_pages_run_no_animation_and_tools_are_untouched(browser, built_site):
    sitemap = (built_site["out"] / "sitemap.xml").read_text(encoding="utf-8")
    paths = [p for p in re.findall(r"<loc>https://donttrade\.ca(/[^<]*)</loc>", sitemap) if p not in MOTION]
    assert len(paths) > 15
    ctx = _ctx(browser, init=False)
    pg = ctx.new_page()
    for path in paths:
        pg.goto(built_site["url"] + path)
        pg.evaluate("window.scrollTo(0, document.documentElement.scrollHeight)")
        pg.wait_for_timeout(150)
        assert pg.evaluate(ANIMS) == [], path
    pg.goto(built_site["url"] + "/tools/trade-stats/")
    pg.click("#ts-sample-btn")
    pg.wait_for_selector("#ts-out dl.stats dd")
    pg.wait_for_timeout(300)
    assert pg.evaluate("() => document.getAnimations().filter(a => a.effect.target && a.effect.target.closest && a.effect.target.closest('#ts-out')).length") == 0
    assert not pg.evaluate("[...document.scripts].some(s => s.src.includes('motion.js'))")
    ctx.close()


# ------------------------------------------------------------------ I10: theme
@pytest.mark.parametrize("os_scheme,saved", [("light", "dark"), ("dark", "light")])
def test_i10_hero_follows_the_chosen_theme_not_the_os(browser, built_site, os_scheme, saved):
    ctx = _ctx(browser, init=False, color_scheme=os_scheme)
    ctx.add_init_script(f"try {{ localStorage.setItem('donttrade-theme', '{saved}') }} catch (e) {{}}")
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    r = pg.evaluate("""() => { const d = document.querySelector('.hero-dash'), p = document.createElement('i');
      document.body.append(p); p.style.color = 'var(--bg)'; const bg = getComputedStyle(p).color;
      p.style.color = 'var(--text)'; const tx = getComputedStyle(p).color; p.remove();
      return {dash: getComputedStyle(d).backgroundColor, line: getComputedStyle(d.querySelector('.line-actual')).stroke, bg, tx}; }""")
    ctx.close()
    want = {"dark": ("rgb(22, 24, 28)", "rgb(242, 241, 238)"), "light": ("rgb(255, 255, 255)", "rgb(22, 24, 28)")}[saved]
    assert (r["dash"], r["line"]) == (r["bg"], r["tx"]) == want, r


def test_i10_no_picture_source_left_in_the_build(built_site):
    for root, _, files in os.walk(built_site["out"]):
        for name in files:
            if name.endswith(".html"):
                assert "<source" not in open(os.path.join(root, name), encoding="utf-8").read(), name


# ------------------------------------------------------------------ I12: accessibility
def test_i12_hero_semantics(built_site):
    html = (built_site["out"] / "index.html").read_text(encoding="utf-8")
    hero = re.search(r'<div class="hero-dash"[^>]*>.*?</svg>', html, re.S).group(0)
    assert f'role="img" aria-label="{OLD_ALT}"' in hero
    assert "aria-live" not in hero and '<svg viewBox="0 0 496 300" aria-hidden="true" focusable="false">' in hero
    assert not re.search(r"<h[1-6]", hero)


# Present at b613c8b (main, before motion) in both themes, measured the same way: a best-practice rule,
# not WCAG, and not motion's. Reported to the Manager; any other violation fails.
PRE_EXISTING_AXE = {"/for-firms/": ('landmark-unique:section[aria-labelledby="who-h"]',)}


@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_i12_axe_clean_after_reveals(browser, built_site, scheme):
    src = open(AXE, encoding="utf-8").read()
    ctx = _ctx(browser, init=False, color_scheme=scheme, bypass_csp=True)
    pg = ctx.new_page()
    for path in MOTION:
        pg.goto(built_site["url"] + path)
        _scroll(pg, step=500, pause=40)
        pg.add_script_tag(content=src)
        v = pg.evaluate("async () => (await axe.run(document, {runOnly: ['wcag2a', 'wcag2aa', 'wcag21aa', 'best-practice']}))"
                        ".violations.map(v => v.id + ':' + v.nodes.map(n => n.target.join(' ')).slice(0, 3))")
        assert [x for x in v if x not in PRE_EXISTING_AXE.get(path, ())] == [], (path, scheme, v)
    ctx.close()


def test_i12_tabbing_into_an_unrevealed_section_shows_it_at_once(browser, built_site):
    ctx = _ctx(browser)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    pg.wait_for_timeout(300)
    r = pg.evaluate("""() => new Promise(res => {
      const sec = [...document.querySelectorAll('[data-reveal].rv')].find(s => s.querySelector('a'));
      const before = getComputedStyle(sec).opacity;
      sec.querySelector('a').focus();
      requestAnimationFrame(() => res({before, after: getComputedStyle(sec).opacity}));
    })""")
    ctx.close()
    assert r == {"before": "0", "after": "1"}, r


# ------------------------------------------------------------------ I13: failure modes
def test_i13_motion_js_blocked_hides_nothing_but_the_numbers_until_1300ms(browser, built_site):
    ctx = _ctx(browser)
    ctx.route("**/motion.js", lambda r: r.abort())
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/", wait_until="commit")
    pg.wait_for_timeout(1300)
    assert pg.evaluate(HIDDEN) == 0
    _scroll(pg, step=600, pause=30)
    assert pg.evaluate(HIDDEN) == 0 and not pg.evaluate("__m").get("rvSeen")
    ctx.close()


def test_i13_motion_js_late_no_count_but_sections_still_reveal(browser, built_site):
    import time
    ctx = _ctx(browser)

    def slow(r):
        time.sleep(1.6)
        r.continue_()
    ctx.route("**/motion.js", slow)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    pg.wait_for_timeout(500)
    assert pg.evaluate("__m")["rvSeen"] and not pg.evaluate("__m")["cuSeen"]
    assert pg.evaluate(VALUES) == FINAL
    _scroll(pg, step=600, pause=30)
    assert pg.evaluate(HIDDEN) == 0
    ctx.close()


def test_i13_intersection_observer_throwing_drops_motion(browser, built_site):
    ctx = _ctx(browser)
    ctx.add_init_script("window.IntersectionObserver = function () { throw new Error('stub'); };")
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    pg.wait_for_timeout(300)
    assert not pg.evaluate("document.documentElement.classList.contains('dt-motion')")
    assert pg.evaluate(HIDDEN) == 0 and pg.evaluate(VALUES) == FINAL
    ctx.close()


# ------------------------------------------------------------------ I14: navigation types
def test_i14_no_reveal_or_count_on_reload_back_forward_or_hash(browser, built_site):
    u = built_site["url"]
    ctx = _ctx(browser)
    pg = ctx.new_page()
    pg.goto(u + "/#faq-h")
    pg.wait_for_timeout(1500)
    m = pg.evaluate("__m")
    assert not m["rvSeen"] and not m["cuSeen"], "hash"
    pg.goto(u + "/")
    pg.wait_for_timeout(300)
    assert pg.evaluate("__m")["rvSeen"], "a fresh navigation does reveal"
    pg.reload()
    pg.wait_for_timeout(1500)
    m = pg.evaluate("__m")
    assert not m["rvSeen"] and not m["cuSeen"], "reload"
    pg.evaluate("__m.rvSeen = false; __m.cuSeen = false")   # in case the page comes back from bfcache
    pg.goto(u + "/pricing/")
    pg.go_back()
    pg.wait_for_timeout(1500)
    m = pg.evaluate("__m")
    assert not m["rvSeen"] and not m["cuSeen"], "back/forward"
    ctx.close()


# ------------------------------------------------------------------ I15, I16: runtime reduce, print
def test_i15_switching_to_reduced_motion_mid_count_stops_everything(browser, built_site):
    ctx = _ctx(browser)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/", wait_until="domcontentloaded")
    pg.wait_for_function("document.querySelectorAll('.cu-on').length === 6 && document.querySelectorAll('.rv').length > 0")
    pg.emulate_media(reduced_motion="reduce")
    r = pg.evaluate("""() => new Promise(res => requestAnimationFrame(() => res({
      left: document.querySelectorAll('.cu-on, .rv, [data-cu]').length,
      dt: document.documentElement.classList.contains('dt-motion')})))""")
    assert r == {"left": 0, "dt": False}, r
    assert pg.evaluate(HIDDEN) == 0 and pg.evaluate(VALUES) == FINAL
    ctx.close()


def test_i16_print_shows_everything_and_no_veil(browser, built_site):
    ctx = _ctx(browser)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/", wait_until="domcontentloaded")
    pg.wait_for_function("document.querySelectorAll('.rv').length > 0")
    pg.emulate_media(media="print")
    assert pg.evaluate(HIDDEN) == 0
    assert pg.evaluate("getComputedStyle(document.querySelector('.hero-dash .veil')).display") == "none"
    assert pg.evaluate("() => [...document.querySelectorAll('.hero-dash [data-count]')].every(e => getComputedStyle(e, '::after').content === 'none')")
    ctx.close()


# ------------------------------------------------------------------ I18: SEO
def test_i18_head_and_headings_are_unchanged_by_motion(built_site):
    for path in MOTION:
        html = (built_site["out"] / B.out_file("", path).lstrip("/")).read_text(encoding="utf-8")
        page = next(p for p in B.PAGES if p["path"] == path)
        assert f"<title>{page['title']}</title>" in html.replace("&amp;", "&").replace("&#39;", "'")
        assert re.search(r'<meta name="description" content="[^"]+">', html)
        body = re.sub(r"(?s)<script.*?</script>|<[^>]+>", " ", html.split("<main", 1)[1])
        for t in re.findall(r"(?s)<h[1-3][^>]*>(.*?)</h[1-3]>", html):
            assert re.sub(r"<[^>]+>|\s+", " ", t).strip()[:20].split()[0] in body
        ld = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))
        faq = [g for g in ld["@graph"] if g["@type"] == "FAQPage"]
        n = len(re.findall(r"<summary>", re.search(r'(?s)aria-labelledby="faq-h"[^>]*>.*?</section>', html).group(0)))
        assert faq and len(faq[0]["mainEntity"]) == n, path
    home = (built_site["out"] / "index.html").read_text(encoding="utf-8")
    assert all(v in home for v in FINAL), "the final hero values are in the HTML"


# ------------------------------------------------------------------ I20: hover
def test_i20_buttons_lift_on_hover_but_not_when_disabled(browser, built_site):
    ctx = _ctx(browser, init=False)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    btn = pg.locator(".hero .btn").first
    assert btn.evaluate("e => getComputedStyle(e).transform") == "none"
    btn.hover()
    pg.wait_for_timeout(400)
    assert btn.evaluate("e => getComputedStyle(e).transform") == "matrix(1, 0, 0, 1, 0, -1)"
    assert btn.evaluate("e => getComputedStyle(e, '::after').opacity") == "1"
    pg.evaluate("""() => { const b = document.createElement('button'); b.className = 'btn'; b.disabled = true; b.id = 'dis';
      b.textContent = 'Disabled'; document.querySelector('.hero .btn-row').append(b);
      const a = document.createElement('a'); a.className = 'btn'; a.href = '#'; a.id = 'adis'; a.setAttribute('aria-disabled', 'true');
      a.textContent = 'Off'; document.querySelector('.hero .btn-row').append(a); }""")
    for sel in ("#dis", "#adis"):
        pg.hover(sel, force=True)
        pg.wait_for_timeout(300)
        assert pg.eval_on_selector(sel, "e => getComputedStyle(e).transform") == "none", sel
        assert pg.eval_on_selector(sel, "e => getComputedStyle(e, '::after').opacity") == "0", sel
    ctx.close()


def test_i20_no_stuck_lift_after_a_tap(browser, built_site):
    ctx = _ctx(browser, PHONE, init=False, is_mobile=True, has_touch=True)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    pg.evaluate("document.querySelectorAll('.btn').forEach(b => b.addEventListener('click', e => e.preventDefault()))")
    btn = pg.locator(".hero .btn").first
    btn.tap()
    pg.wait_for_timeout(400)
    assert btn.evaluate("e => getComputedStyle(e).transform") == "none"
    ctx.close()


# ------------------------------------------------------------------ build guards (plan §2.1, §4.2)
def test_build_guard_motion_scope():
    hero = B.hero_dashboard_body()
    js = f'<script src="{B.MOTION_JS}" defer></script>'
    assert B.motion_problem(js + hero, "/") is None
    assert "not one of MOTION_PAGES" in B.motion_problem(js, "/pricing/")
    assert "does not load motion.js" in B.motion_problem("<section data-reveal>", "/for-firms/")
    assert "does not load motion.js" in B.motion_problem(hero, "/")
    assert "outside the generated hero" in B.motion_problem(js + hero + '<dd data-count>5</dd>', "/")


def test_build_guard_stale_hero_capture(tmp_path, monkeypatch):
    other = tmp_path / "demo-trades.csv"
    other.write_bytes(open(B.SAMPLE_CSV, "rb").read() + b"\n")
    monkeypatch.setattr(B, "SAMPLE_CSV", str(other))
    with pytest.raises(B.BuildError, match="different sample"):
        B.check_hero_dashboard()


def test_lint_flags_data_count_outside_the_hero(tmp_path, built_site):
    import shutil
    from lint import lint_build
    out = tmp_path / "_site"
    shutil.copytree(built_site["out"], out)
    fp = out / "pricing" / "index.html"
    fp.write_text(fp.read_text(encoding="utf-8").replace("</main>", '<dd data-count>9</dd></main>'), encoding="utf-8")
    assert [p for p in lint_build(str(out)) if p[0] == "motion"] != []
