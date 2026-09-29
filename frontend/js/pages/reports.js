import { get, download } from '../api.js';
import { h, mount, toast, table } from '../ui.js';

export async function render(root, { store }) {
  const [kinds, types, counters, atts] = await Promise.all([get('/reports'), get('/ticket-types'), get('/counters'), get('/reports/attendants')]);
  const today = new Date().toLocaleDateString('sv-SE');
  const sel = (opts, all = 'Todos') => h('select', {}, h('option', { value: '' }, all), ...opts.map(o => h('option', { value: o[0] }, o[1])));
  const f = {
    kind: h('select', {}, kinds.kinds.map(k => h('option', { value: k.key }, k.label))),
    date_from: h('input', { type: 'date', value: today }), date_to: h('input', { type: 'date', value: today }),
    time_from: h('input', { type: 'time' }), time_to: h('input', { type: 'time' }),
    type_id: sel(types.map(t => [t.id, t.name])), attendant_id: sel(atts.map(a => [a.id, a.name])),
    counter_id: sel(counters.map(c => [c.id, c.name])),
    status: sel([['AGUARDANDO', 'Aguardando'], ['CHAMADA', 'Chamada'], ['RECHAMADA', 'Rechamada'], ['EM_ATENDIMENTO', 'Em atendimento'], ['ATENDIDA', 'Atendida'], ['NAO_COMPARECEU', 'Não compareceu'], ['CANCELADA', 'Cancelada']]),
  };
  const labels = { kind: 'Relatório', date_from: 'De', date_to: 'Até', time_from: 'Hora inicial', time_to: 'Hora final', type_id: 'Tipo', attendant_id: 'Atendente', counter_id: 'Guichê', status: 'Situação' };
  const out = h('div');
  const qs = () => { const q = new URLSearchParams(); for (const [k, el] of Object.entries(f)) if (k !== 'kind' && el.value) q.set(k, el.value); return q; };
  async function run() {
    try {
      const d = await get(`/reports/${f.kind.value}?${qs()}`);
      mount(out, h('h2', {}, d.title), table(d.columns.map(c => ({ label: c.label, render: r => r[c.key] ?? '' })), d.rows, { empty: 'Nenhum dado no período.' }));
    } catch (e) { toast(e.message, 'error'); }
  }
  const exp = (fmt) => download(`/reports/${f.kind.value}/export?format=${fmt}&${qs()}`, `relatorio_${f.kind.value}.${fmt}`).catch(e => toast(e.message, 'error'));
  mount(root, h('h1', {}, 'Relatórios'), h('div', { class: 'card' },
    h('div', { class: 'filters' }, Object.entries(f).map(([k, el]) => h('label', { class: 'field' }, h('span', { class: 'lbl' }, labels[k]), el))),
    h('div', { class: 'row', style: { marginTop: '.8rem' } }, h('button', { class: 'btn primary', onclick: run }, 'Gerar'),
      store.can('reports.export') ? [h('button', { class: 'btn', onclick: () => exp('xlsx') }, 'Excel'), h('button', { class: 'btn', onclick: () => exp('csv') }, 'CSV'), h('button', { class: 'btn', onclick: () => exp('pdf') }, 'PDF')] : '')),
    h('div', { class: 'card' }, out));
  await run();
}
