import { get } from '../api.js';
import { h, mount, barChart } from '../ui.js';

export async function render(root, { bus }) {
  const box = h('div');
  mount(root, h('h1', {}, 'Dashboard — hoje'), box);
  const kpi = (v, l, cls = '') => h('div', { class: 'card kpi' }, h('div', { class: 'v ' + cls }, v ?? '—'), h('div', { class: 'l' }, l));
  const min = (v) => v == null ? '—' : `${v} min`;

  async function load() {
    const d = await get('/dashboard'), c = d.counts;
    const maxT = Math.max(1, ...d.by_type.map(t => t.count));
    const hours = d.by_hour.filter(x => x.hour >= 5 && x.hour <= 22).map(x => ({ label: String(x.hour).padStart(2, '0'), issued: x.issued, attended: x.attended }));
    mount(box,
      d.backup.stale ? h('div', { class: 'alert warn' }, '⚠ Backup: ' + d.backup.message + ' Vá em Backup para gerar um agora.') : '',
      h('div', { class: 'grid g4' }, kpi(c.total, 'Senhas hoje'), kpi(c.waiting, 'Em espera'), kpi(c.calling + c.in_service, 'Em atendimento'),
        kpi(c.done, 'Atendidas'), kpi(c.no_show, 'Não compareceram'), kpi(d.priority_today, 'Prioritárias'),
        kpi(min(d.avg_wait_min), 'Tempo médio de espera'), kpi(min(d.avg_service_min), 'Tempo médio de atendimento'),
        kpi(min(d.oldest_waiting_min), 'Maior espera atual')),
      h('div', { class: 'grid g2' },
        h('div', { class: 'card' }, h('h2', {}, 'Senhas por hora'),
          h('div', { class: 'legend' }, h('span', {}, h('i', { style: { background: '#2563eb' } }), 'Emitidas'), h('span', {}, h('i', { style: { background: '#059669' } }), 'Atendidas')),
          barChart(hours, { series: [{ key: 'issued', label: 'Emitidas', color: '#2563eb' }, { key: 'attended', label: 'Atendidas', color: '#059669' }] })),
        h('div', { class: 'card' }, h('h2', {}, 'Por tipo de senha'),
          d.by_type.length ? d.by_type.map(t => h('div', { class: 'hbar' }, h('span', { style: { minWidth: '11rem' } }, t.name),
            h('div', { class: 'bar', style: { width: `${(t.count / maxT) * 60}%`, background: t.color } }), h('span', { class: 'n' }, t.count))) : h('p', { class: 'muted' }, 'Sem senhas hoje.'))));
  }
  let t = null; const soon = () => { clearTimeout(t); t = setTimeout(() => load().catch(() => {}), 400); };
  const offs = ['queue.updated', 'ticket.created', 'resync'].map(e => bus.on(e, soon));
  const poll = setInterval(soon, 30000);
  await load();
  return () => { offs.forEach(o => o()); clearInterval(poll); };
}
