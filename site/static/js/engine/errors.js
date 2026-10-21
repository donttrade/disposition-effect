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
    return { code: this.code, row: this.row, column: this.column, message: this.message };
  }
}

// One place for the human wording, so the dashboard and the sniffer say the same thing.
export const MESSAGES = Object.freeze({
  E_EMPTY: 'The file is empty.',
  E_HEADER_ONLY: 'The file has column headings but no trade rows under them.',
  E_UNKNOWN_FORMAT:
    'This file was not recognised as an MT5/MT4 report, an IBKR Flex Query, a Tradovate Orders export or the generic template. Use the generic template (Date, Time, Symbol, Side, Quantity, Price).',
  E_MISSING_COLUMN: 'A required column is missing',
  E_BAD_DATE: 'A date or time could not be read',
  E_AMBIGUOUS_DATE:
    'A date uses slashes, so day-first and month-first cannot be told apart. Write dates as yyyy-mm-dd (for example 2026-09-01).',
  E_BAD_NUMBER: 'A number could not be read',
  E_ENCODING: 'The file is not a text, CSV or HTML file that can be read.',
  E_TOO_LARGE: 'The file is too large: the limit is 50 MB and 200,000 rows.',
  E_NO_CLOSED_TRADES: 'No closed trades were found: every position in the file is still open, or the file has no trades.',
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
  W_HEDGING:
    'Buys and sells overlapped on the same symbol (a hedging account). They were netted per symbol, so trade counts may differ from your platform.',
  W_OPEN_POSITIONS: 'Positions still open at the end of the file were left out.',
  W_OPEN_AT_START:
    'Positions that were already open when the file starts were left out: their opening fills are before the date range of this export, so their hold time and direction are unknown.',
  W_POINTS_ONLY: 'Some contracts are not in the built-in table, so their results are in price points, not dollars.',
  W_MIXED_CURRENCY: 'The file mixes currencies.',
});

export function warning(code, n, extra = '') {
  return { code, n, message: WARNING_TEXT[code] + (extra ? ' ' + extra : '') };
}
