// errors.js — the engine's only error and warning vocabulary.
//
// Every failure is an EngineError with a fixed code. The page shows the message
// verbatim, so messages are written for a trader, not a developer. The codes are
// the contract with the Python reference (tests/reference/engine_ref.py): golden
// tests compare code, row and column, never the message text.

export const LIMITS = Object.freeze({
  MAX_BYTES: 50 * 1024 * 1024, // 50 MB
  MAX_ROWS: 200000,
});

export class EngineError extends Error {
  constructor(code, message, row = null, column = null) {
    super(message);
    this.name = 'EngineError';
    this.code = code;
    this.row = row;
    this.column = column;
  }
  toJSON() {
    // file: which of several files (1-based); only set when more than one file was read together.
    const o = { code: this.code, row: this.row, column: this.column, message: this.message };
    if (this.file !== undefined && this.file !== null) o.file = this.file;
    return o;
  }
}

// One place for the human wording, so the dashboard and the sniffer say the same thing.
export const MESSAGES = Object.freeze({
  E_EMPTY: 'The file is empty.',
  E_HEADER_ONLY: 'The file has column headings but no trade rows under them.',
  E_UNKNOWN_FORMAT:
    'This file was not recognised as an MT5/MT4 report, an IBKR Flex Query, a Tradovate Orders export, a TradingView Order History export or the generic template. Use the generic template (Date, Time, Symbol, Side, Quantity, Price).',
  E_MISSING_COLUMN: 'A required column is missing',
  E_BAD_DATE: 'A date or time could not be read',
  E_AMBIGUOUS_DATE:
    'A date uses slashes, so day-first and month-first cannot be told apart. Write dates as yyyy-mm-dd (for example 2026-09-01).',
  E_BAD_NUMBER: 'A number could not be read',
  E_ENCODING: 'The file is not a text, CSV or HTML file that can be read.',
  E_BAD_QUOTE:
    'A quote mark (") opens a cell that is never closed, so the rows after it cannot be read. Remove the stray quote mark, or export the file again.',
  E_TOO_LARGE: 'The file is too large: the limit is 50 MB and 200,000 rows.',
  E_NO_CLOSED_TRADES: 'No closed trades were found.',
  // The universal importer (mapped columns, several files, pasted tables). The detail never repeats a cell.
  E_BAD_MAPPING: 'The saved column choices do not fit this file. Match the columns again.',
  E_MIXED_FILES: 'These files have different columns. Add files from one platform at a time.',
  E_PASTE_FORMAT:
    'This paste has no columns we can split. Select the table rows, headings included, copy, and paste again.',
});

export function fail(code, detail = '', row = null, column = null) {
  let msg = MESSAGES[code] || code;
  if (detail) msg += (msg.endsWith('.') ? ' ' : ': ') + detail;
  if (row !== null) msg += ` (row ${row}${column ? `, column ${column}` : ''})`;
  throw new EngineError(code, msg, row, column);
}

export const WARNING_TEXT = Object.freeze({
  W_UNVERIFIED_FORMAT:
    'Beta: this format was built from public documentation, not yet from a real export. Check a few trades by hand, or use the generic template.',
  W_SKIPPED_ROWS: 'Rows that are not trades (balance, credit, cancelled or unfilled rows) were skipped.',
  W_DUPLICATE_ROWS:
    'Some rows are exact copies of an earlier row, as when two overlapping exports are pasted together. They were kept, because two identical fills can be real. If you did not expect them, remove the copies and load the file again.',
  W_HEDGING:
    'Buys and sells overlapped on the same symbol (a hedging account). They were netted per symbol, so trade counts may differ from your platform.',
  W_OPEN_POSITIONS: 'Positions still open at the end of the file were left out.',
  W_OPEN_AT_START:
    'Positions that were already open when the file starts were left out: their opening fills are before the date range of this export, so their hold time and direction are unknown.',
  W_AMBIGUOUS_FILLS:
    'Some fills could not be placed in a position for certain, so they and the trades they belong to were left out: either fills on one symbol have the same time to the second and their order decides which position they close, or one fill closed a position opened before the file and opened a new one, so the size of the new one is unknown.',
  W_POINTS_ONLY: 'Some contracts are not in the built-in table, so their results are in price points, not dollars.',
  W_MIXED_CURRENCY: 'The file mixes currencies.',
  W_CURRENCY_IGNORED:
    'The currency column holds values that are not currency codes, so it was not used: results are shown without a currency unit. Check that no cell before it holds an extra comma.',
  W_CLOSE_BEFORE_OPEN:
    'Some round trips close up to one hour before they open, on a night the clocks went back (US or EU dates). They were read as closing in the repeated hour, one hour later than written. If the times in this file have no daylight-saving changes, or the open and close columns are swapped, these trades are wrong: check them.',
  W_MAPPED: 'You matched these columns yourself. Check a few trades against your platform.',
  W_ORDERS_AVERAGED: 'One row per order: fills inside an order are averaged.',
  W_OVERLAP_ROWS: 'Some rows were in more than one file and were counted once.',
  W_PNL_SIGN:
    "In some rows the profit's sign does not match the prices and direction: the long/short column may be swapped.",
  W_DATES_ONLY:
    'Your file has dates but no times. Results that depend on the time of day are not available; day-level results still are.',
  W_DST:
    'Some trades were open during a daylight-saving clock change (US or EU dates). The file\'s times have no time zone, so the hold time of these trades may be off by one hour, and a buy and a sell in the repeated hour may be in the wrong order.',
});

// "file 2 of 3": an error in one of several files names the file by its place, never by its name
// (an IBKR file name can carry the account id).
export function inFile(e, k, n) {
  e.file = k + 1;
  const where = `file ${k + 1} of ${n}`;
  e.message = e.row !== null ? e.message.replace(/\(row /, `(${where}, row `) : `${e.message} (${where})`;
  return e;
}

export function warning(code, n, extra = '') {
  return { code, n, message: WARNING_TEXT[code] + (extra ? ' ' + extra : '') };
}
