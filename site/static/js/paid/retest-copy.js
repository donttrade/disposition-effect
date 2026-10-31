// retest-copy.js — the re-test instruction, in one place, for the report page and the .ics
// reminder (fix D2: the server accepts a re-test only when at least half of the first file's
// trades are in the new file, so the new export must start where the first one did).
//
// Delta D1 (21 Oct): the server opens the re-test at the exact second of the first report + 30
// days and closes it at + 60 days. The first report's /analyse answer carries those two instants
// (`retest: {opens_at, closes_at}`, unix seconds), and everything here is built from them: the
// .ics is a timed UTC event at opens_at (never an all-day date, which is another day in another
// time zone), and every sentence gives the UTC time and "in N days, H hours". The same rounding
// as the server's message (dt-private src/core/app.mjs utcMinute / inDaysHours): the opening time
// is rounded UP to the minute and the hours UP, so a buyer who follows them is never early; the
// closing time is rounded DOWN, so they are never late. The day numbers in the fallback line are
// the ones in site/config/paid_terms.json (a test ties them; the server's parity test ties that
// file to the server's constants).

// Release test M2: with several files the re-test needs the same files (the same accounts), not just "the same account".
export const RETEST_HOW = 'For the re-test, use the same files as your first result, each exported again from the same start date '
  + 'up to the day you run it, so they cover your first result’s period and the trades since.';

// The Worker's refusals that the page words itself, by error code (Release test M2, M3). Every other code shows the
// Worker's own message. not_same_history: fewer than half of the first result's trades are in the re-test; the Worker's
// text advises exporting "the same account", which is wrong when the first result read several files (adding or
// removing a copy account changes the trades), so the page says what to do in either case.
export const RETEST_NOT_SAME = 'This re-test does not match your first result: fewer than half of the trades from your first result are in these files. '
  + 'Use the same files as your first result, with the trades since: the same accounts, each exported again from the same start date. Nothing was counted.';
export const REFUSAL_LINES = {
  not_same_history: RETEST_NOT_SAME,
  // M3 hook: the Worker's refusal of a re-test with no new trades (an identical file) goes here, code: line, when the
  // engine Coder's code and wording arrive. Until then the Worker's own message is shown for it.
};
// The line for a refused /analyse: the page's own for the codes above, else the Worker's message, else the fallback.
export function refusalLine(error, fallback = 'The report could not be made.') {
  if (error && Object.prototype.hasOwnProperty.call(REFUSAL_LINES, error.code)) return REFUSAL_LINES[error.code];
  return error && error.message ? error.message : fallback;
}

// Only when no window came back (an older server): no instant, so no time is claimed.
export const RETEST_LINE = 'Your purchase includes one re-test on the same account, 30 to 60 days after your first result. ' + RETEST_HOW;

const iso = (sec) => new Date(sec * 1000).toISOString();

// "2026-12-01 15:01 UTC"; up: round up to the minute (an opening), else down (a closing).
export function utcMinute(sec, up = true) {
  const m = (up ? Math.ceil : Math.floor)(sec / 60) * 60;
  const s = iso(m);
  return s.slice(0, 10) + ' ' + s.slice(11, 16) + ' UTC';
}

// "in 0 days, 6 hours" (hours rounded up; 24 hours carry into a day).
export function inDaysHours(targetSec, nowSec) {
  const diff = Math.max(0, targetSec - nowSec);
  let days = Math.floor(diff / 86400);
  let hours = Math.ceil((diff - days * 86400) / 3600);
  if (hours === 24) { days += 1; hours = 0; }
  return `in ${days} day${days === 1 ? '' : 's'}, ${hours} hour${hours === 1 ? '' : 's'}`;
}

function validWindow(w) {
  return !!w && Number.isInteger(w.opens_at) && Number.isInteger(w.closes_at) && w.closes_at > w.opens_at;
}

// The sentence for the report page, right after the first report.
export function retestLine(w, nowSec = Math.floor(Date.now() / 1000)) {
  if (!validWindow(w)) return RETEST_LINE;
  return `Your purchase includes one re-test on the same account. It opens at ${utcMinute(w.opens_at)}, `
    + `${inDaysHours(w.opens_at, nowSec)}, and closes at ${utcMinute(w.closes_at, false)}. ` + RETEST_HOW;
}

// RFC 5545: escape \ ; , and newlines in TEXT values, and fold lines longer than 75 octets.
function escapeText(s) {
  return s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
}

function fold(line) {
  const bytes = new TextEncoder().encode(line);
  if (bytes.length <= 75) return line;
  const out = [];
  let cur = '';
  let len = 0;
  for (const ch of line) {
    const n = new TextEncoder().encode(ch).length;
    if (len + n > (out.length ? 74 : 75)) { out.push(cur); cur = ''; len = 0; }
    cur += ch;
    len += n;
  }
  out.push(cur);
  return out.join('\r\n ');
}

const icsTime = (sec) => iso(sec).replace(/[-:]/g, '').slice(0, 15) + 'Z';   // 20261201T150007Z

// A calendar reminder for the one included re-test: a timed UTC event that starts at the exact
// second the server opens it (w.opens_at) and lasts 30 minutes. Built locally. null without a window.
export function ics(w, now = new Date()) {
  if (!validWindow(w)) return null;
  const nowSec = Math.floor(now.getTime() / 1000);
  const stamp = icsTime(nowSec);
  const desc = `Your included donttrade re-test opens at ${utcMinute(w.opens_at)} (${inDaysHours(w.opens_at, nowSec)} `
    + `from when this reminder was made) and closes at ${utcMinute(w.closes_at, false)}. `
    + 'Run it at https://donttrade.ca/report/ (open it from your restore link). ' + RETEST_HOW;
  return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//donttrade//habit report//EN', 'BEGIN:VEVENT',
    `UID:retest-${w.opens_at}@donttrade.ca`, `DTSTAMP:${stamp}`, `DTSTART:${icsTime(w.opens_at)}`,
    `DTEND:${icsTime(w.opens_at + 1800)}`,
    'SUMMARY:donttrade re-test', fold('DESCRIPTION:' + escapeText(desc)),
    'END:VEVENT', 'END:VCALENDAR', ''].join('\r\n');
}
