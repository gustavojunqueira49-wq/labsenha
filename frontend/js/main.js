import { api, get, post, store, setUnauthorizedHandler } from './api.js';
import { h, mount, toast } from './ui.js';
import { bus, connect, disconnect } from './ws.js';

const ROUTES = {
  reception: { perm: 'ticket.create', label: 'Recepção', load: () => import('./pages/reception.js') },
  attend: { perm: 'ticket.call', label: 'Atendimento', load: () => import('./pages/attend.js') },
  queue: { perm: 'ticket.view', label: 'Fila', load: () => import('./pages/queue.js') },
  panel: { perm: ['panel.view', 'ticket.view'], label: 'Painel', load: () => import('./pages/panel.js'), bare: true },
  dashboard: { perm: 'dashboard.view', label: 'Dashboard', load: () => import('./pages/dashboard.js') },
  reports: { perm: 'reports.view', label: 'Relatórios', load: () => import('./pages/reports.js') },
  print: { perm: ['print.manage', 'print.view'], label: 'Impressão', load: () => import('./pages/print.js') },
  users: { perm: 'users.manage', label: 'Usuários', load: () => import('./pages/users.js') },
  catalog: { perm: 'config.manage', label: 'Filas e prioridades', load: () => import('./pages/catalog.js') },
  settings: { perm: 'config.manage', label: 'Configurações', load: () => import('./pages/settings.js') },
  backups: { perm: 'backup.manage', label: 'Backup', load: () => import('./pages/backups.js') },
  audit: { perm: 'audit.view', label: 'Auditoria', load: () => import('./pages/audit.js') },
};
const NAV = ['reception', 'attend', 'queue', 'dashboard', 'reports', 'print', 'catalog', 'users', 'settings', 'backups', 'audit'];
const HOME = { RECEPCAO: 'reception', ATENDENTE: 'attend', PAINEL: 'panel', SUPERVISAO: 'dashboard', ADMINISTRADOR: 'dashboard' };

const app = document.getElementById('app');
let cleanup = null;
let wsState = 'offline';

const allowed = (r) => [].concat(r.perm).some(p => store.can(p));

function logout(silent) {
  if (!silent && store.token) post('/auth/logout').catch(() => {});
  disconnect(); store.clear();
  document.body.classList.remove('panel-mode');
  location.hash = '#/login';
}

setUnauthorizedHandler(() => { if (store.token) { toast('Sessão encerrada. Entre novamente.', 'error'); logout(true); } });

async function boot() {
  store.load();
  if (store.token) {
    try {
      const me = await get('/auth/me');
      store.user = me.user; store.settings = me.settings;
    } catch { store.clear(); }
  }
  window.addEventListener('hashchange', route);
  route();
}

async function route() {
  if (cleanup) { try { cleanup(); } catch { /* */ } cleanup = null; }
  document.body.classList.remove('panel-mode');
  const name = (location.hash.replace(/^#\/?/, '') || '').split('?')[0];
  if (!store.user) {
    if (name !== 'login') { location.hash = '#/login'; return; }
    return renderLogin();
  }
  if (store.user.must_change_password) return renderChangePassword(true);
  if (name === 'login' || name === '') { location.hash = '#/' + (HOME[store.user.role] || firstAllowed()); return; }
  if (name === 'password') return renderChangePassword(false);
  const r = ROUTES[name];
  if (!r || !allowed(r)) { location.hash = '#/' + (HOME[store.user.role] || firstAllowed()); return; }
  connect(name === 'panel' ? 'PAINEL01' : '');
  const mod = await r.load();
  const box = h('div', { class: r.bare ? '' : 'page' });
  if (r.bare) { document.body.classList.add('panel-mode'); mount(app, box); }
  else mount(app, topbar(name), h('main', {}, box));
  try { cleanup = await mod.render(box, { store, bus, api }) || null; }
  catch (e) { box.appendChild(h('div', { class: 'alert error' }, 'Erro ao abrir a tela: ' + e.message)); }
}

function firstAllowed() { return NAV.find(n => allowed(ROUTES[n])) || 'login'; }

function topbar(active) {
  const dot = h('span', { class: 'dot ' + wsState, title: 'Conexão em tempo real' });
  bus.onStatus(s => { wsState = s; dot.className = 'dot ' + s; dot.title = { online: 'Conectado em tempo real', connecting: 'Conectando…', offline: 'Sem conexão — tentando reconectar' }[s]; });
  return h('header', { class: 'topbar' },
    h('span', { class: 'brand' }, store.settings['lab.name'] || 'Laboratório'),
    h('nav', {}, NAV.filter(n => allowed(ROUTES[n])).map(n => h('a', { href: '#/' + n, class: n === active ? 'active' : '' }, ROUTES[n].label)),
      allowed(ROUTES.panel) && store.user.role !== 'PAINEL' ? h('a', { href: '#/panel', target: '_blank', rel: 'noopener' }, 'Abrir painel ↗') : ''),
    h('span', { class: 'user' }, dot, store.user.full_name, ' · ',
      h('a', { href: '#/password', style: { color: '#93c5fd' } }, 'Senha'), ' · ',
      h('a', { href: '#', style: { color: '#93c5fd' }, onclick: (e) => { e.preventDefault(); logout(); } }, 'Sair')));
}

function renderLogin() {
  const err = h('div', { class: 'alert error', style: { display: 'none' } });
  const user = h('input', { type: 'text', autocomplete: 'username', autocapitalize: 'off', required: true });
  const pass = h('input', { type: 'password', autocomplete: 'current-password', required: true });
  const btn = h('button', { class: 'btn primary', type: 'submit', style: { width: '100%' } }, 'Entrar');
  const form = h('form', { onsubmit: async (e) => {
    e.preventDefault(); btn.disabled = true; err.style.display = 'none';
    try {
      const r = await post('/auth/login', { username: user.value, password: pass.value });
      store.token = r.token; store.user = r.user; store.settings = r.settings; store.save();
      location.hash = '#/'; route();
    } catch (ex) { err.textContent = ex.message; err.style.display = 'block'; pass.value = ''; }
    btn.disabled = false;
  } },
    err, h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Usuário'), user),
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Senha'), pass), btn);
  mount(app, h('div', { class: 'login-wrap' }, h('div', { class: 'card login-card' },
    h('h1', {}, 'Fila de Senhas'), h('p', { class: 'muted', style: { textAlign: 'center' } }, 'Coleta de exames laboratoriais'), form)));
  user.focus();
}

function renderChangePassword(forced) {
  const err = h('div', { class: 'alert error', style: { display: 'none' } });
  const f = (label, ac) => h('input', { type: 'password', autocomplete: ac, required: true });
  const cur = f('', 'current-password'), n1 = f('', 'new-password'), n2 = f('', 'new-password');
  const form = h('form', { onsubmit: async (e) => {
    e.preventDefault(); err.style.display = 'none';
    if (n1.value !== n2.value) { err.textContent = 'A confirmação não confere.'; err.style.display = 'block'; return; }
    try {
      await post('/auth/change-password', { current_password: cur.value, new_password: n1.value });
      toast('Senha alterada.', 'ok');
      const me = await get('/auth/me'); store.user = me.user;
      location.hash = '#/'; route();
    } catch (ex) { err.textContent = ex.message; err.style.display = 'block'; }
  } },
    forced ? h('div', { class: 'alert warn' }, 'Por segurança, defina uma nova senha antes de continuar (mín. 8 caracteres, com letras e números).') : '',
    err, h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Senha atual'), cur),
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Nova senha'), n1),
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Repita a nova senha'), n2),
    h('div', { class: 'row' }, h('button', { class: 'btn primary', type: 'submit' }, 'Salvar senha'),
      h('button', { class: 'btn', type: 'button', onclick: () => forced ? logout() : (location.hash = '#/') }, forced ? 'Sair' : 'Cancelar')));
  mount(app, h('div', { class: 'login-wrap' }, h('div', { class: 'card login-card' }, h('h1', {}, 'Alterar senha'), form)));
}

boot();
