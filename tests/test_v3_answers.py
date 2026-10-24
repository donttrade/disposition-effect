"""Answer box (ARCHITECT-V3 §c.5, steps Q-A1 and Q-A2): Tester invariants A1-A12.

The index is built from the rendered pages (build.answer_units), shipped as answers-index.js
(window.DT_ANSWERS = …), and /help/ lists every unit. answers.js matches a question against it
in the browser: no network, no storage, no generated words.
"""
import json
import os
import re
import sys
import unicodedata

import pytest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(REPO, "site"))
sys.path.insert(0, os.path.join(REPO, "checks"))
import build as B  # noqa: E402
import lint as L  # noqa: E402


def _index(site):
    js = (site["out"] / "static" / "js" / "answers-index.js").read_text(encoding="utf-8")
    m = re.fullmatch(r"(?s)//[^\n]*\nwindow\.DT_ANSWERS = (\{.*\});\n", js)
    assert m, "one assignment, no code"
    return json.loads(m.group(1).replace("<\\/", "</")), js


def _page(site, path):
    return (site["out"] / B.out_file("", path).lstrip("/")).read_text(encoding="utf-8")


def _norm(t):
    return " ".join(unicodedata.normalize("NFKC", t).split())


# ------------------------------------------------------------------ A1: sources, anchors, no findings
def test_a1_no_research_no_finding_and_every_anchor_resolves(built_site):
    data, js = _index(built_site)
    units = data["units"]
    assert len(units) >= 60 and len({u["id"] for u in units}) == len(units)
    ev = B.evidence()
    for u in units:
        path, anchor = u["url"].split("#", 1)
        assert not path.startswith(("/research/", "/fr/", "/help/")) and "thanks" not in path, u["url"]
        assert re.search(r'\sid="' + re.escape(anchor) + '"', _page(built_site, path)), u["url"]
        assert u["kind"] in ("faq", "price", "terms", "privacy", "tool", "glossary")
        for n in (ev["finding"]["pct"], "4,659", "76.1"):
            assert n not in u["a"] and n not in u["q"], u["id"]
    kinds = {u["kind"] for u in units}
    assert kinds == {"faq", "price", "terms", "privacy", "tool", "glossary"}
    assert data["advice"] == "faq-home-is-this-advice" and data["disclaimer"] == B.load_config()[0]["legal"]["disclaimer_short"]


def test_a1_build_refuses_a_unit_with_a_finding_number(monkeypatch):
    page = {"path": "/x/", "crumb": "X", "updated": "2026-10-21"}
    html = ('<main><section aria-labelledby="faq-h"><details id="q-a"><summary>A?</summary><p>76.1% of traders.</p>'
            '</details></section></main>')
    with pytest.raises(B.BuildError, match="study figure"):
        B.answer_units([(page, html)])
    html = ('<main><section aria-labelledby="faq-h"><details id="q-a"><summary>A?</summary><p>Fine.</p>'
            '</details></section></main>')
    assert B.answer_units([(page, html)])[0]["url"] == "/x/#q-a"


# ------------------------------------------------------------------ A2: verbatim page text
def test_a2_every_answer_is_its_pages_text(built_site):
    data, _ = _index(built_site)
    cache = {}
    for u in data["units"]:
        path = u["url"].split("#")[0]
        if path not in cache:
            cache[path] = _norm(L.visible_text(_page(built_site, path)))
        a = u["a"][:-2] if u["a"].endswith(" …") else u["a"]
        assert _norm(a) in cache[path], (u["id"], a[:80])
        assert _norm(u["q"]) in cache[path], u["id"]
        assert len(u["a"]) <= B.ANSWER_MAX_CHARS + 2


# ------------------------------------------------------------------ A3: budgets and lazy loading
def test_a3_budgets(built_site):
    _, js = _index(built_site)
    assert len(js.encode("utf-8")) <= 150 * 1024
    p = os.path.join(REPO, "site", "static", "js", "answers.js")
    if os.path.exists(p):   # Q-A2
        assert os.path.getsize(p) <= 6 * 1024


def test_a3_build_fails_over_budget(monkeypatch):
    monkeypatch.setattr(B, "ANSWERS_MAX", 100)
    units = [{"id": "faq-home-is-this-advice", "q": "Is this advice?", "a": "No.", "url": "/#q-is-this-advice",
              "section": "Home", "kind": "faq", "updated": ""}]
    cfg = {"legal": {"terms_version": "2026-10-21", "disclaimer_short": "x" * 200}}
    with pytest.raises(B.BuildError, match="budget"):
        B.answers_index_js(units, cfg)


# ------------------------------------------------------------------ A4: /help/ without JS
def test_a4_help_lists_every_unit_and_the_get_form_lands_there(browser, built_site):
    data, _ = _index(built_site)
    html = _page(built_site, "/help/")
    for u in data["units"]:
        assert f'id="u-{u["id"]}"' in html and f'href="{u["url"]}"' in html, u["id"]
    ctx = browser.new_context(java_script_enabled=False)
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/help/#ask")
    pg.fill("#ask-q", "can I get my money back?")
    pg.click("#ask button[type=submit]")
    pg.wait_for_load_state()
    # Tester MR-4 (24 Oct): the field has no name, so the GET lands on /help/ without the question in it
    assert re.search(r"/help/\??$", pg.url) and "q=" not in pg.url and "money" not in pg.url, pg.url
    assert pg.locator("details[id^='u-']").count() == len(data["units"])
    ctx.close()
    sitemap = (built_site["out"] / "sitemap.xml").read_text(encoding="utf-8")
    assert "https://donttrade.ca/help/" in sitemap
    footer = re.search(r'(?s)<footer.*</footer>', _page(built_site, "/")).group(0)
    assert 'href="/help/"' in footer


def test_a11_index_text_passes_lint(built_site):
    _, js = _index(built_site)
    assert L.answer_index_problems(js, "/static/js/answers-index.js") == []
    bad = js.replace("Is this advice?", "Our best advice?", 1)
    assert L.answer_index_problems(bad, "x")


def test_faq_ids_are_stable_and_unique(built_site):
    for path in ("/", "/pricing/", "/for-firms/", "/tools/trade-stats/"):
        html = _page(built_site, path)
        ids = re.findall(r'<details id="(q-[^"]+)"><summary>', html)
        assert ids and len(ids) == len(set(ids)), path
    assert 'id="q-is-this-advice"' in _page(built_site, "/")


# ------------------------------------------------------------------ A5, A9: fixture accuracy and the contract
FIX = json.load(open(os.path.join(REPO, "tests", "fixtures", "answers_queries.json"), encoding="utf-8"))["queries"]
ASK_ALL = """async (qs) => { const out = []; for (const q of qs) out.push(await DTAnswer.ask(q)); return out; }"""


def _help(browser, site, **kw):
    ctx = browser.new_context(**kw)
    pg = ctx.new_page()
    pg.goto(site["url"] + "/help/")
    pg.wait_for_load_state("networkidle")
    return ctx, pg


def test_a5_a9_fixture_accuracy_and_result_shape(browser, built_site):
    assert len(FIX) >= 60
    assert sum(x["expect"] == "out_of_scope" for x in FIX) >= 10 and sum(x["expect"] == "no_match" for x in FIX) >= 10
    data, _ = _index(built_site)
    ids = {u["id"]: u for u in data["units"]}
    ctx, pg = _help(browser, built_site)
    res = pg.evaluate(ASK_ALL, [x["q"] for x in FIX])
    ctx.close()
    tally = {"answer": [0, 0], "out_of_scope": [0, 0], "no_match": [0, 0]}
    for x, r in zip(FIX, res):
        assert set(r) >= {"status", "text", "citations", "engine"} and r["engine"] == "index-v1"
        assert r["status"] in ("answered", "ambiguous", "no_match", "out_of_scope")
        for c in r["citations"]:
            assert c["id"] in ids and c["url"] == ids[c["id"]]["url"]
        if r["status"] == "answered":
            assert len(r["citations"]) >= 1 and r["text"] == ids[r["citations"][0]["id"]]["a"]
        e = x["expect"]
        key = e if e in ("out_of_scope", "no_match") else "answer"
        tally[key][1] += 1
        if key == "answer":
            tally[key][0] += r["status"] == "answered" and r["citations"][0]["id"] in (e if isinstance(e, list) else [e])
        else:
            tally[key][0] += r["status"] == e
        if e == "no_match":
            assert r["status"] != "answered", (x["q"], r["citations"])   # never an unrelated answer
    assert tally["answer"][0] / tally["answer"][1] >= 0.9, tally
    assert tally["out_of_scope"][0] == tally["out_of_scope"][1], tally
    assert tally["no_match"][0] / tally["no_match"][1] >= 0.9, tally


def test_a9_ui_refuses_an_answer_without_valid_citations(browser, built_site):
    ctx, pg = _help(browser, built_site)
    pg.evaluate("DTAnswer.ask('refund')")
    for cites in ("[]", "[{id: 'made-up', q: 'x', url: '/x/#y', section: 'X'}]",
                  "[{id: 'faq-home-refunds', q: 'x', url: '/elsewhere/#q', section: 'X'}]"):
        pg.evaluate(f"""() => {{ const out = document.querySelector('#ask [data-answer-out]');
          DTAnswer._show(out, {{status: 'answered', text: 'Invented words.', citations: {cites}, engine: 'ai-x'}}, 'q', 'a@b.c'); }}""")
        t = pg.inner_text("#ask [data-answer-out]")
        assert "We have no page that answers that yet." in t and "Invented words." not in t
    ctx.close()


# ------------------------------------------------------------------ A6, A8, A10: rendering and keyboard
def test_a6_a8_answer_is_verbatim_quote_with_link_and_keyboard_path(browser, built_site):
    data, _ = _index(built_site)
    ids = {u["id"]: u for u in data["units"]}
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/")
    pg.wait_for_load_state("networkidle")
    assert pg.get_attribute("main [data-answer-out]", "aria-live") == "polite"
    pg.focus("#pg-q")
    pg.keyboard.type("Can I get my money back?")
    pg.keyboard.press("Enter")
    pg.wait_for_selector("main [data-answer-out] blockquote")
    out = pg.locator("main [data-answer-out]")
    cite = out.locator("blockquote").get_attribute("cite")
    unit = next(u for u in data["units"] if u["url"] == cite)
    assert out.locator("blockquote").inner_text().strip() == unit["a"]
    assert out.locator("p.ans-from").inner_text() == "Answer from " + unit["section"]
    chrome = {"Answer from " + unit["section"], unit["a"], "Read it on its page"}
    assert {p.strip() for p in out.inner_text().split("\n") if p.strip()} == chrome   # zero generated words
    seen = []
    for _ in range(3):   # input → Ask button → the answer's link
        pg.keyboard.press("Tab")
        seen.append(pg.evaluate("document.activeElement.textContent"))
    assert "Read it on its page" in seen, seen
    ctx.close()


def test_a10_no_match_mailto_holds_only_the_question(browser, built_site):
    ctx, pg = _help(browser, built_site)
    q = "do you have a mobile app & more?"
    pg.fill("#ask-q", q)
    pg.press("#ask-q", "Enter")
    pg.wait_for_selector("#ask [data-answer-out] a[href^='mailto:']")
    href = pg.get_attribute("#ask [data-answer-out] a[href^='mailto:']", "href")
    from urllib.parse import quote
    assert href == "mailto:donttrade.research@gmail.com?subject=" + quote(q, safe="-_.!~*'()")
    ctx.close()


def test_a8_out_of_scope_shows_the_advice_answer_and_disclaimer(browser, built_site):
    data, _ = _index(built_site)
    adv = next(u for u in data["units"] if u["id"] == data["advice"])
    ctx, pg = _help(browser, built_site)
    pg.fill("#ask-q", "should I buy gold now?")
    pg.press("#ask-q", "Enter")
    pg.wait_for_selector("#ask [data-answer-out] blockquote")
    t = pg.inner_text("#ask [data-answer-out]")
    assert adv["a"] in t and data["disclaimer"] in t
    ctx.close()


def test_a8_header_popover_escape_and_focus(browser, built_site):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    pg.goto(built_site["url"] + "/about/")
    pg.wait_for_load_state("networkidle")
    assert pg.evaluate("[...document.scripts].filter(s => /answers|answer-ui/.test(s.src)).length") == 0
    pg.click(".nav-ask > summary")
    # merge into delivery-39 (24 Oct): ask.js focuses the field on the details 'toggle' event, which fires in a
    # later task than the click; wait for it (2 s) instead of reading activeElement in the same tick
    pg.wait_for_function("document.activeElement && document.activeElement.id === 'hd-q'", timeout=2000)
    assert pg.evaluate("document.activeElement.id") == "hd-q"
    pg.wait_for_timeout(400)
    assert pg.evaluate("[...document.scripts].filter(s => /answers\\.js|answer-ui\\.js/.test(s.src)).length") == 2
    pg.keyboard.type("is this an audit")
    pg.keyboard.press("Enter")
    pg.wait_for_selector(".nav-ask [data-answer-out] blockquote")
    pg.keyboard.press("Escape")
    assert not pg.evaluate("document.querySelector('.nav-ask').open")
    assert pg.evaluate("document.activeElement.matches('.nav-ask > summary')")
    ctx.close()


# ------------------------------------------------------------------ A3, A7: lazy, no network, no storage
def test_a3_a7_lazy_no_network_no_storage(browser, built_site):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    pg = ctx.new_page()
    reqs = []
    pg.on("request", lambda r: reqs.append(r.url))
    pg.goto(built_site["url"] + "/pricing/")
    pg.wait_for_load_state("networkidle")
    assert not [u for u in reqs if "answers" in u or "answer-ui" in u], "nothing loads before the box is used"
    before = pg.evaluate("JSON.stringify([Object.keys(localStorage), document.cookie])")
    n0 = len(reqs)
    pg.focus("#pg-q")
    pg.wait_for_timeout(300)
    for q in [x["q"] for x in FIX[:20]]:
        pg.fill("#pg-q", q)
        pg.press("#pg-q", "Enter")
        pg.wait_for_timeout(30)
    pg.wait_for_timeout(300)
    later = reqs[n0:]
    assert all(u.startswith(built_site["url"] + "/static/js/") for u in later), later
    assert len(later) == 3, later   # answers.js, answer-ui.js, answers-index.js: once each
    assert pg.evaluate("JSON.stringify([Object.keys(localStorage), document.cookie])") == before
    assert pg.evaluate("indexedDB.databases ? indexedDB.databases().then(d => d.length) : 0") == 0
    csp = pg.get_attribute("meta[http-equiv='Content-Security-Policy']", "content")
    assert "connect-src 'none'" in csp
    ctx.close()


def test_a3_a9_engine_and_ui_budgets():
    js = os.path.join(REPO, "site", "static", "js")
    assert os.path.getsize(os.path.join(js, "answers.js")) <= 6 * 1024
    assert os.path.getsize(os.path.join(js, "answer-ui.js")) <= 4 * 1024
    assert os.path.getsize(os.path.join(js, "ask.js")) <= 2 * 1024
    src = open(os.path.join(js, "answers.js"), encoding="utf-8").read() + open(os.path.join(js, "answer-ui.js"), encoding="utf-8").read()
    for bad in ("fetch(", "XMLHttpRequest", "localStorage", "indexedDB", "sendBeacon", "innerHTML", "document.cookie"):
        assert bad not in src, bad


# ------------------------------------------------------------------ A12: phone, axe
@pytest.mark.parametrize("scheme", ["light", "dark"])
def test_a12_phone_no_overflow_axe_clean_with_an_answer(browser, built_site, scheme):
    from a11y import axe_violations, horizontal_overflow
    for width, path, box in ((375, "/help/", "#ask-q"), (375, "/", "#pg-q"), (1280, "/about/", None)):
        ctx = browser.new_context(viewport={"width": width, "height": 812}, color_scheme=scheme, bypass_csp=True)
        pg = ctx.new_page()
        pg.goto(built_site["url"] + path)
        pg.wait_for_load_state("networkidle")
        if box is None:
            pg.click(".nav-ask > summary")
            box = "#hd-q"
            pg.wait_for_timeout(300)
        pg.fill(box, "how is lot size calculated")
        pg.press(box, "Enter")
        pg.wait_for_selector("[data-answer-out] blockquote")
        assert horizontal_overflow(pg) == []
        assert axe_violations(pg) == [], (path, scheme)
        ctx.close()
