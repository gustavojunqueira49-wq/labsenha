import { get } from '../api.js';
import { h, mount, table, fmtDateTime } from '../ui.js';

export async function render(root) {
  const action = h('input', { type: 'text', placeholder: 'ex.: login, usuario, configuracao' });
  const user = h('input', { type: 'text', placeholder: 'login' });
  const day = h('input', { type: 'date' });
  const out = h('div');
  const load = async () => {
    const q = new URLSearchParams(); if (action.value) q.set('action', action.value); if (user.value) q.set('username', user.value); if (day.value) q.set('day', day.value);
    const rows = await get('/admin/audit?' + q);
    mount(out, table([{ label: 'Quando', render: r => fmtDateTime(r.at) }, { label: 'Usuário', render: r => r.username || '—' }, { label: 'Ação', key: 'action' },
      { label: 'Entidade', render: r => r.entity ? `${r.entity} ${r.entity_id ?? ''}` : '' }, { label: 'IP', render: r => r.ip || '' },
      { label: 'Detalhes', render: r => h('small', { style: { color: 'inherit', wordBreak: 'break-word' } }, r.details ? JSON.stringify(r.details) : '') }], rows));
  };
  mount(root, h('h1', {}, 'Auditoria'), h('div', { class: 'card' }, h('div', { class: 'filters' },
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Ação'), action), h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Usuário'), user),
    h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Dia'), day), h('button', { class: 'btn primary', onclick: load }, 'Filtrar')), h('div', { style: { height: '.8rem' } }), out));
  await load();
}
