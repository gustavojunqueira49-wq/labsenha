// WebSocket com reconexão automática. Ao reconectar, chama onResync para recarregar o estado.
import { store } from './api.js';

const handlers = new Map();   // tipo -> Set<fn>
const statusFns = new Set();
let ws = null, timer = null, attempt = 0, keepalive = null, panelCode = '', wanted = false, state = 'offline';

export const bus = {
  on(type, fn) {
    if (!handlers.has(type)) handlers.set(type, new Set());
    handlers.get(type).add(fn);
    return () => handlers.get(type).delete(fn);
  },
  onStatus(fn) { statusFns.add(fn); fn(state); return () => statusFns.delete(fn); },
};

function setState(s) { state = s; statusFns.forEach(f => f(s)); }

function emit(type, data) {
  (handlers.get(type) || []).forEach(fn => { try { fn(data); } catch (e) { console.error(e); } });
  (handlers.get('*') || []).forEach(fn => { try { fn(type, data); } catch (e) { console.error(e); } });
}

export function connect(panel = '') {
  panelCode = panel; wanted = true;
  if (ws && (ws.readyState === 0 || ws.readyState === 1)) return;
  open();
}

export function disconnect() {
  wanted = false; clearTimeout(timer); clearInterval(keepalive);
  if (ws) { ws.onclose = null; ws.close(); ws = null; }
  setState('offline');
}

function open() {
  if (!store.token) return;
  const proto = location.protocol === 'https:' ? 'wss' : 'ws';
  const q = new URLSearchParams({ token: store.token });
  if (panelCode) q.set('panel', panelCode);
  setState('connecting');
  ws = new WebSocket(`${proto}://${location.host}/ws?${q}`);
  ws.onopen = () => {
    const reconnected = attempt > 0;
    attempt = 0; setState('online');
    clearInterval(keepalive);
    keepalive = setInterval(() => { try { ws.send('ping'); } catch { /* */ } }, 25000);
    if (reconnected) emit('resync', {});
  };
  ws.onmessage = (ev) => {
    let m; try { m = JSON.parse(ev.data); } catch { return; }
    if (m.type === 'ping' || m.type === 'pong' || m.type === 'hello') return;
    emit(m.type, m.data);
  };
  ws.onclose = (ev) => {
    clearInterval(keepalive); setState('offline');
    if (!wanted || ev.code === 4401) return;
    attempt++;
    timer = setTimeout(open, Math.min(15000, 500 * 2 ** Math.min(attempt, 5)));
  };
  ws.onerror = () => { /* onclose cuida */ };
}
