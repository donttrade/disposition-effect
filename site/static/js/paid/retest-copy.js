// retest-copy.js — the re-test instruction, in one place, for the report page and the .ics
// reminder (fix D2: the server accepts a re-test only when at least half of the first file's
// trades are in the new file, so the new export must start where the first one did).

export const RETEST_HOW = 'For the re-test, export the same account from the same start date as your first file, '
  + 'up to the day you run it, so the file covers your first report’s period and the trades since.';

export const RETEST_LINE = 'Your purchase includes one re-test on the same account 30 to 60 days from now. ' + RETEST_HOW;

// RFC 5545: escape \ ; , and newlines in TEXT values, and fold lines longer than 75 octets.
function escapeText(s) {
  return s.replace(/\\/g, '\\\\').replace(/;/g, '\;').replace(/,/g, '\\,').replace(/\n/g, '\\n');
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

export function ics(now = new Date()) {
  // A calendar reminder 30 days out for the one included re-test. Built locally.
  const d = new Date(now.getTime() + 30 * 86400000);
  const ymd = d.toISOString().slice(0, 10).replace(/-/g, '');
  const stamp = now.toISOString().replace(/[-:]/g, '').slice(0, 15) + 'Z';
  const desc = 'Run your included donttrade re-test at https://donttrade.ca/report/ (open it from your restore link). ' + RETEST_HOW;
  return ['BEGIN:VCALENDAR', 'VERSION:2.0', 'PRODID:-//donttrade//habit report//EN', 'BEGIN:VEVENT',
    `UID:retest-${stamp}@donttrade.ca`, `DTSTAMP:${stamp}`, `DTSTART;VALUE=DATE:${ymd}`,
    'SUMMARY:donttrade re-test', fold('DESCRIPTION:' + escapeText(desc)),
    'END:VEVENT', 'END:VCALENDAR', ''].join('\r\n');
}
