// journal-worker.js: reads a trade file for the journal off the main thread (ARCHITECT-V3 §d.4, J2).
// The engine is unchanged (the same runFile() as the tool pages); this adds the journal's trade fields
// and the content keys (keys.js). file-worker.js is untouched. An HTML report needs DOMParser, which a
// worker lacks, so the page parses those itself ({needsPage: true}). Nothing here touches the network
// or storage. In: {id, bytes: Uint8Array}. Out: {id, result} | {id, error} | {id, needsPage} | {id, crash}.
import { runFile } from '../engine/index.js';
import { decodeBytes, isHtml } from '../engine/csv.js';
import { forJournal } from './keys.js';

self.onmessage = (ev) => {
  const { id, bytes } = ev.data || {};
  const send = (m) => self.postMessage({ id, ...m });
  if (!(bytes instanceof Uint8Array)) { send({ crash: 'bad message' }); return; }
  try {
    if (typeof DOMParser === 'undefined' && isHtml(decodeBytes(bytes))) { send({ needsPage: true }); return; }
    const out = runFile(bytes);
    if (out.error) { send({ error: out.error }); return; }
    send({ result: forJournal(out.result) });
  } catch (e) {
    if (e && e.name === 'EngineError') { send({ error: e.toJSON() }); return; }
    send({ crash: String(e && e.message ? e.message : e) });
  }
};
