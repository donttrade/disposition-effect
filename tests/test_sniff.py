"""Step 1: the format sniffer detects each sample, and the canary never reaches the page."""
import os

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
FIX = os.path.join(HERE, "fixtures")

SAMPLES = {
    "mt5/deals_netting.htm": ("mt5", "no"),
    "mt5/deals_netting_utf16.htm": ("mt5", "no"),
    "mt5/positions_hedging.htm": ("mt5", "yes"),
    "mt5/deals_hedging.htm": ("mt5", "no"),
    "mt5/deals.csv": ("mt5", "no (CSV deals only)"),
    "mt4/statement.htm": ("mt4", "n/a"),
    "ibkr/activity_flex.csv": ("ibkr_flex", "n/a"),
    "ibkr/trade_confirm_fx.csv": ("ibkr_flex", "n/a"),
    "tradovate/orders.csv": ("tradovate_orders", "n/a"),
    "generic/basic.csv": ("generic", "n/a"),
    "generic_roundtrip/tradezella.csv": ("generic_roundtrip", "n/a"),
}


@pytest.fixture(scope="module")
def sniff(browser, repo_server):
    ctx = browser.new_context()
    page = ctx.new_page()
    requests = []
    page.on("request", lambda r: requests.append(r.url))
    page.goto(repo_server + "/site/dev/sniff.html")
    paths = [os.path.join(FIX, rel) for rel in SAMPLES]
    page.set_input_files("#file", paths)
    # A locator wait, not wait_for_function: the page's CSP forbids eval.
    page.locator(f"#out[data-done='{len(paths)}']").wait_for(state="attached")
    yield page, requests
    ctx.close()


def test_each_sample_detected(sniff):
    page, _ = sniff
    rows = page.evaluate("""() => [...document.querySelectorAll('section')].map(s => {
        const t = s.querySelector('table[data-role=summary]');
        const c = t ? [...t.rows[1].cells].map(x => x.textContent) : null;
        return [s.dataset.file, c]; })""")
    got = {name: (cells[0], cells[2]) for name, cells in rows}
    want = {os.path.basename(k): v for k, v in SAMPLES.items()}
    assert got == want


def test_canary_never_on_page(sniff):
    page, _ = sniff
    assert "CANARY" not in page.content()
    assert "CANARY" not in page.evaluate("document.body.innerText")


def test_no_network_beyond_static(sniff, repo_server):
    _, requests = sniff
    assert all(u.startswith(repo_server) for u in requests), requests
