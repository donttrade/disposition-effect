// journal/main.js: the /journal/ page's entry module. It registers each view with app.js and starts it.
import { registerView, start } from './app.js';
import * as trades from './trades-view.js';
import * as imports from './imports-view.js';

registerView('trades', trades);
registerView('imports', imports);
start();
