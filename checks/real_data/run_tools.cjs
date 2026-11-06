// Runs the free tools themselves (this repo's built site, served on DT_TOOLS_BASE, default http://127.0.0.1:8766)
// on checks/real_data/raw/real-trades.csv and records exactly what each tool prints -> checks/real_data/tools-printed.json,
// which make_tool_real.py checks its own figures against. By hand (Terminal, from the repo root):
//   python3 site/build.py && python3 -m http.server 8766 --bind 127.0.0.1 --directory site/_site &
//   node checks/real_data/run_tools.cjs
// Needs Playwright with Chromium. Nothing is sent anywhere: the tools read the file in the tab.
const { chromium } = require('playwright');
const fs = require('fs'), path = require('path'), crypto = require('crypto');
const CSV = path.join(__dirname, 'raw', 'real-trades.csv');  // fetch.py makes it (gitignored)
const base = process.env.DT_TOOLS_BASE || 'http://127.0.0.1:8766';
const stat = (pg, scope, label) => pg.evaluate(([s, l]) => { for (const dt of document.querySelectorAll(s + ' dl dt')) if (dt.textContent.trim() === l) return dt.nextElementSibling.textContent.trim(); return null; }, [scope, label]);
(async () => {
  const b = await chromium.launch({ args: ['--no-sandbox', '--disable-gpu', '--disable-dev-shm-usage'] });
  const pg = await b.newPage({ viewport: { width: 1280, height: 900 } });
  const out = { csv_sha256: crypto.createHash('sha256').update(fs.readFileSync(CSV)).digest('hex'), site: base };
  // trade stats
  await pg.goto(base + '/tools/trade-stats/'); await pg.setInputFiles('#ts-file', CSV);
  await pg.waitForSelector('#ts-out dl', { timeout: 30000 });
  out.trade_stats = {};
  for (const [k, l] of [['trades', 'Closed trades'], ['net', 'Net result'], ['win_rate', 'Win rate'], ['profit_factor', 'Profit factor'], ['mean', 'Mean result per trade'], ['largest_drawdown', 'Largest drawdown']]) out.trade_stats[k] = await stat(pg, '#ts-out', l);
  out.trade_stats.notes = (await pg.innerText('#ts-out')).split('\n').filter(s => /note|left out|skipped|open/i.test(s)).slice(0, 6);
  out.trade_stats.rows = await pg.evaluate(() => [...document.querySelectorAll('#ts-out tr')].filter(tr => tr.cells.length > 1).map(tr => [tr.cells[0].textContent.trim(), tr.cells[1].textContent.trim()]));
  // heatmap
  await pg.goto(base + '/tools/trading-heatmap/'); await pg.setInputFiles('#hm-file', CSV);
  await pg.waitForSelector('#hm-out table td.heat', { timeout: 30000 });
  out.heatmap = await pg.evaluate(() => { const t = document.querySelector('#hm-out table');
    const cols = [...t.querySelectorAll('thead th')].slice(1).map(th => th.textContent.trim());
    const rows = [...t.querySelectorAll('tbody tr')].map(tr => ({ hour: tr.querySelector('th').textContent.trim(),
      cells: [...tr.querySelectorAll('td')].map(td => { const s = td.querySelectorAll('span'); return s.length >= 2 ? [s[0].textContent.trim(), s[1].textContent.trim()] : null; }) }));
    return { cols, rows, caption: (t.querySelector('caption') || {}).textContent }; });
  // drawdown
  await pg.goto(base + '/tools/drawdown-calculator/'); await pg.setInputFiles('#dd-file', CSV);
  await pg.waitForSelector('#dd-out dl', { timeout: 30000 });
  out.drawdown = { largest: await stat(pg, '#dd-out', 'Largest drawdown'), text: (await pg.innerText('#dd-out')).slice(0, 1200) };
  // readiness check, the page's default rules
  // RULE (fixed in advance): the first entry of the site's firm-rules library (config/challenge_rules.json, file
  // order), at its own account size; the file's times are read as UTC (the dataset does not state a zone).
  await pg.goto(base + '/tools/prop-challenge-simulator/');
  const first = await pg.$eval('#ps-preset', s => [...s.options].map(o => [o.value, o.textContent.trim()]));
  out.prop_presets_first = first.slice(0, 4);
  const lib = JSON.parse(fs.readFileSync(path.join(__dirname, '..', '..', 'site', 'config', 'challenge_rules.json'), 'utf8')).presets.find(p => p.status !== 'not_quotable');
  out.prop_rule = { preset_id: lib.id, account_size: lib.account_size, rules: lib.rules };
  await pg.selectOption('#ps-preset', lib.id); await pg.dispatchEvent('#ps-preset', 'change');
  await pg.setInputFiles('#ps-file', CSV);
  await pg.waitForTimeout(2500);
  const tzOpts = await pg.$eval('#ps-filetz', s => [...s.options].map(o => [o.value, o.textContent.trim()]));
  const utc = tzOpts.find(o => o[1] === 'UTC'); if (utc) { await pg.selectOption('#ps-filetz', utc[0]); await pg.dispatchEvent('#ps-filetz', 'change'); }
  await pg.waitForTimeout(500);
  out.prop_pre = { run_disabled: await pg.$eval('#ps-run', e => e.disabled), status: (await pg.innerText('#ps-file-status')).slice(0, 400), tz: await pg.evaluate(() => { const f = document.querySelector('#ps-tz-fields'); return f ? f.innerText.slice(0, 300) : null; }) };
  const sel = await pg.$('#ps-tz-fields select'); if (sel) { const v = await pg.$eval('#ps-tz-fields select', s => s.value); out.prop_pre.tz_value = v; }
  out.prop_pre.rules = await pg.evaluate(() => [...document.querySelectorAll('#ps-form select, #ps-form input')].filter(e => e.id && e.type !== 'file' && e.type !== 'radio').map(e => [e.id, e.value]).slice(0, 30));
  if (!out.prop_pre.run_disabled) { await pg.click('#ps-run');
    try { await pg.waitForSelector('#ps-out svg[aria-label], #ps-out .notice, #ps-out h2, #ps-out h3', { timeout: 60000 }); await pg.waitForTimeout(1500); } catch (e) { out.prop_err = String(e).slice(0, 200); }
    out.prop_sim_rules_used = await pg.evaluate(() => ['ps-preset','ps-account','ps-target','ps-daily','ps-maxloss','ps-days','ps-mindays'].map(id => [id, document.getElementById(id).value]));
    out.prop_sim = { label: await pg.evaluate(() => { const s = document.querySelector('#ps-out svg[aria-label]'); return s ? s.getAttribute('aria-label') : null; }), text: (await pg.innerText('#ps-out')).slice(0, 1500) }; }
  // Expert details: the outcome table with its Monte Carlo error, then the file-uncertainty range
  try {
    await pg.evaluate(() => { const d = document.querySelector('#ps-expert'); if (d && d.tagName === 'DETAILS') d.open = true; });
    out.prop_expert = (await pg.innerText('#ps-expert')).slice(0, 2500);
    if (await pg.$('#ps-range-btn')) { await pg.click('#ps-range-btn');
      await pg.waitForFunction(() => { const o = document.querySelector('#ps-range-out'); return o && !o.hidden && o.textContent.trim().length > 20; }, null, { timeout: 180000 });
      out.prop_range = (await pg.innerText('#ps-range-out')).slice(0, 1200); }
  } catch (e) { out.prop_range_err = String(e).slice(0, 300); }
  // Disposition calculator on Odean (1998) Table I, entire year: the four published counts
  await pg.goto(base + '/tools/disposition-calculator/');
  for (const [id, v] of [['#dc-rg', '13883'], ['#dc-pg', '79658'], ['#dc-rl', '11930'], ['#dc-pl', '110348']]) await pg.fill(id, v);
  await pg.press('#dc-pl', 'Enter'); await pg.waitForTimeout(800);
  out.disposition_tool = { inputs: [13883, 79658, 11930, 110348], source: 'Odean (1998), Table I, entire year',
    results: (await pg.innerText('#dc-results')).slice(0, 1500) };
  fs.writeFileSync(path.join(__dirname, 'tools-printed.json'), JSON.stringify(out, null, 1) + '\n');
  console.log(JSON.stringify({ ts: out.trade_stats, dd: out.drawdown.largest, hm_cols: out.heatmap.cols, hm_rows: out.heatmap.rows.length, prop_pre: out.prop_pre, prop: out.prop_sim && out.prop_sim.label }, null, 1).slice(0, 3500));
  await b.close();
})();
