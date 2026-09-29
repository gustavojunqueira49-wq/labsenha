// Cliente HTTP. Toda a comunicação é com o próprio servidor (mesma origem) — sem internet.
const KEY = 'senhas.session';

export const store = {
  token: null, user: null, settings: {},
  load() {
    try {
      const s = JSON.parse(localStorage.getItem(KEY) || 'null');
      if (s) { this.token = s.token; }
    } catch { /* localStorage indisponível */ }
  },
  save() {
    try { localStorage.setItem(KEY, JSON.stringify({ token: this.token })); } catch { /* ignore */ }
  },
  clear() {
    this.token = null; this.user = null;
    try { localStorage.removeItem(KEY); } catch { /* ignore */ }
  },
  can(perm) { return !!this.user && this.user.permissions.includes(perm); },
};

let onUnauthorized = () => {};
export function setUnauthorizedHandler(fn) { onUnauthorized = fn; }

export function errorMessage(data, status) {
  const d = data && data.detail;
  if (typeof d === 'string') return d;
  if (Array.isArray(d)) return d.map(e => (e.msg || '').replace(/^Value error, /, '')).join('; ');
  if (status === 503) return 'Servidor ou banco de dados indisponível. Aguarde alguns instantes.';
  return `Erro inesperado (${status}).`;
}

export class ApiError extends Error {
  constructor(message, status, data) { super(message); this.status = status; this.data = data; }
}

export async function api(method, path, body) {
  const headers = {};
  if (store.token) headers['Authorization'] = 'Bearer ' + store.token;
  if (body !== undefined) headers['Content-Type'] = 'application/json';
  let res;
  try {
    res = await fetch('/api' + path, { method, headers, body: body === undefined ? undefined : JSON.stringify(body) });
  } catch {
    throw new ApiError('Sem conexão com o servidor. Verifique a rede.', 0, null);
  }
  let data = null;
  try { data = await res.json(); } catch { /* sem corpo */ }
  if (!res.ok) {
    if (res.status === 401 && path !== '/auth/login') onUnauthorized();
    throw new ApiError(errorMessage(data, res.status), res.status, data);
  }
  return data;
}

export async function download(path, filename) {
  const res = await fetch('/api' + path, { headers: { Authorization: 'Bearer ' + store.token } });
  if (!res.ok) {
    let data = null; try { data = await res.json(); } catch { /* */ }
    throw new ApiError(errorMessage(data, res.status), res.status, data);
  }
  const blob = await res.blob();
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 1000);
}

export const get = (p) => api('GET', p);
export const post = (p, b = {}) => api('POST', p, b);
export const put = (p, b) => api('PUT', p, b);
export const patch = (p, b) => api('PATCH', p, b);
export const del = (p) => api('DELETE', p);
