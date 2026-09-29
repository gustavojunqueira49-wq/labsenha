import { get, post } from '../api.js';
import { h, mount, toast, statusBadge, fmtTime, fmtDur, fmtDateTime, modal, table, confirmBox } from '../ui.js';

export async function render(root, { store, bus }) {
  const day = h('input', { type: 'date', value: new Date().toLocaleDateString('sv-SE') });
  const status = h('select', {}, h('option', { value: '' }, 'Todas'), ...['AGUARDANDO', 'CHAMADA', 'RECHAMADA', 'EM_ATENDIMENTO', 'ATENDIDA', 'NAO_COMPARECEU', 'CANCELADA'].map(s => h('option', { value: s }, s.replace('_', ' ').toLowerCase())));
  const code = h('input', { type: 'text', placeholder: 'Ex.: P015' });
  const body = h('div');
  const waitBox = h('div');
  const load = async () => {
    const q = new URLSearchParams({ day: day.value }); if (status.value) q.set('status', status.value); if (code.value) q.set('code', code.value);
    const r = await get('/tickets?' + q);
    mount(body, table([
      { label: 'Senha', render: t => h('b', {}, t.code) }, { label: 'Tipo', render: t => t.category || t.type.name },
      { label: 'Situação', render: t => statusBadge(t.status) }, { label: 'Retirada', render: t => fmtTime(t.created_at) },
      { label: 'Chamada', render: t => fmtTime(t.called_at) }, { label: 'Guichê', render: t => t.counter?.name || '—' },
      { label: 'Atendente', render: t => t.attendant || '—' },
      { label: '', render: t => h('div', { class: 'row' },
        h('button', { class: 'btn sm', onclick: () => details(t) }, 'Histórico'),
        store.can('ticket.cancel') && ['AGUARDANDO', 'CHAMADA', 'RECHAMADA'].includes(t.status) ? h('button', { class: 'btn sm', onclick: async () => {
          if (await confirmBox(`Cancelar a senha ${t.code}?`, { danger: true, ok: 'Cancelar senha' })) { try { await post(`/tickets/${t.id}/cancel`, { reason: 'Cancelada pela supervisão' }); } catch (e) { toast(e.message, 'error'); } load(); } } }, 'Cancelar') : '',
        store.can('print.reprint') ? h('button', { class: 'btn sm', onclick: async () => { try { await post(`/tickets/${t.id}/reprint`); toast('Reimpressão enviada.', 'ok'); } catch (e) { toast(e.message, 'error'); } } }, 'Reimprimir') : '') },
    ], r.tickets, { empty: 'Nenhuma senha encontrada.' }));
    if (day.value === new Date().toLocaleDateString('sv-SE')) {
      const w = await get('/tickets/waiting');
      mount(waitBox, h('div', { class: 'card' }, h('h2', {}, `Fila de espera agora (${w.tickets.length})`), w.tickets.length ? h('div', { class: 'row' }, w.tickets.slice(0, 40).map(t =>
        h('span', { class: 'pill', style: { background: t.type.color }, title: 'espera ' + fmtDur(t.wait_seconds) }, t.code))) : h('span', { class: 'muted' }, 'Ninguém aguardando.'),
        h('small', {}, 'Ordem prevista segundo as regras de prioridade configuradas.')));
    } else mount(waitBox);
  };
  async function details(t) {
    const d = await get('/tickets/' + t.id);
    modal(`Senha ${t.code}`, (b) => b.append(table([
      { label: 'Quando', render: e => fmtDateTime(e.at) }, { label: 'Evento', key: 'type' }, { label: 'De → Para', render: e => `${e.from || '—'} → ${e.to || '—'}` },
      { label: 'Usuário', render: e => e.user || '—' }, { label: 'Guichê', render: e => e.counter || '—' }], d.events)), { wide: true });
  }
  mount(root, h('h1', {}, 'Fila e histórico'), waitBox, h('div', { class: 'card' },
    h('div', { class: 'filters' }, h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Dia'), day), h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Situação'), status),
      h('label', { class: 'field' }, h('span', { class: 'lbl' }, 'Senha'), code), h('button', { class: 'btn primary', onclick: load }, 'Filtrar')), h('div', { style: { height: '.8rem' } }), body));
  let t = null; const soon = () => { clearTimeout(t); t = setTimeout(() => load().catch(() => {}), 300); };
  const offs = ['ticket.created', 'ticket.called', 'ticket.recalled', 'ticket.started', 'ticket.attended', 'ticket.no_show', 'ticket.cancelled', 'resync'].map(e => bus.on(e, soon));
  await load();
  return () => offs.forEach(o => o());
}
