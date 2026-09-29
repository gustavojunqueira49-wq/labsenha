import { get, post } from '../api.js';
import { h, mount, toast, fmtTime, modal, confirmBox } from '../ui.js';

export async function render(root, { store, bus }) {
  const stateBox = h('div');
  const typesBox = h('div', { class: 'type-grid' });
  const recentBox = h('div');
  const warnBox = h('div');
  mount(root, h('h1', {}, 'Retirada de senha'), warnBox, stateBox, typesBox, h('div', { class: 'card', style: { marginTop: '1rem' } }, h('h2', {}, 'Últimas senhas emitidas'), recentBox));

  let types = [], categories = [], busy = false, recent = [];
  const jobState = new Map(); // job_id -> status

  async function load() {
    [types, categories] = await Promise.all([get('/ticket-types'), get('/priorities')]);
    drawTypes(); await loadRecent(); await loadPrinter();
  }

  function drawTypes() {
    mount(typesBox, types.map(t => h('button', { class: 'type-btn', style: { background: t.color }, disabled: busy, onclick: () => choose(t) },
      t.name.toUpperCase(), h('br'), h('small', {}, t.requires_category ? 'escolher categoria' : `senha ${t.prefix}`))));
  }

  async function choose(t) {
    if (busy) return;
    if (!t.requires_category) return issue(t, null);
    const cat = await modal('Categoria de prioridade', (body, close) => {
      body.append(h('div', { class: 'cat-grid' }, categories.map(c => h('button', { class: 'btn xl', style: { fontSize: '1.2rem', minHeight: '70px' }, onclick: () => close(c) }, c.name))),
        h('div', { class: 'row end', style: { marginTop: '1rem' } }, h('button', { class: 'btn', onclick: () => close(null) }, 'Cancelar')));
    }, { wide: true });
    if (cat) issue(t, cat.id);
  }

  async function issue(t, priorityId) {
    busy = true; drawTypes();
    try {
      const r = await post('/tickets', { ticket_type_id: t.id, priority_id: priorityId });
      showIssued(r.ticket, r.print_job_id, t.color);
      recent.unshift(r.ticket); recent = recent.slice(0, 8); drawRecent();
    } catch (e) { toast(e.message, 'error', 7000); }
    setTimeout(() => { busy = false; drawTypes(); }, 700); // evita duplo clique acidental
  }

  function showIssued(ticket, jobId, color) {
    const st = h('div', { class: 'print-state' }, jobId ? '🖨 Enviando para impressão…' : 'Impressão automática desligada.');
    const update = (status, err) => {
      if (status === 'IMPRESSO') { st.textContent = '✔ Senha impressa'; st.style.color = 'var(--ok)'; }
      else if (status === 'PENDENTE' || status === 'ENVIANDO') { st.textContent = err ? '⚠ Impressora indisponível — a senha será impressa assim que voltar.' : '🖨 Imprimindo…'; st.style.color = err ? 'var(--warn)' : ''; }
      else if (status === 'ERRO') { st.textContent = '✖ Falha na impressão — use "Reimprimir".'; st.style.color = 'var(--danger)'; }
    };
    if (jobId) jobState.set(jobId, update);
    const box = h('div', { class: 'card issued' }, h('div', { class: 'muted' }, 'Senha gerada'),
      h('div', { class: 'code', style: { color } }, ticket.code), h('div', {}, ticket.category || ticket.type.name), st,
      h('div', { class: 'row', style: { justifyContent: 'center', marginTop: '.8rem' } },
        h('button', { class: 'btn', onclick: () => reprint(ticket) }, 'Reimprimir')));
    mount(stateBox, box);
    clearTimeout(showIssued.t);
    showIssued.t = setTimeout(() => { mount(stateBox); }, 15000);
  }

  async function reprint(ticket) {
    try { await post(`/tickets/${ticket.id}/reprint`); toast(`Reimpressão de ${ticket.code} enviada.`, 'ok'); }
    catch (e) { toast(e.message, 'error'); }
  }

  function drawRecent() {
    mount(recentBox, recent.length ? h('div', { class: 'table-wrap' }, h('table', {}, h('tbody', {}, recent.map(t => h('tr', {},
      h('td', {}, h('b', {}, t.code)), h('td', {}, t.category || t.type.name), h('td', {}, fmtTime(t.created_at)),
      h('td', {}, t.status === 'AGUARDANDO' ? 'aguardando' : t.status.toLowerCase().replace('_', ' ')),
      h('td', {}, h('button', { class: 'btn sm', onclick: () => reprint(t) }, 'Reimprimir')),
      h('td', {}, t.status === 'AGUARDANDO' ? h('button', { class: 'btn sm', onclick: async () => {
        if (await confirmBox(`Cancelar a senha ${t.code}?`, { ok: 'Cancelar senha', danger: true })) {
          try { await post(`/tickets/${t.id}/cancel`, { reason: 'Cancelada na recepção' }); loadRecent(); } catch (e) { toast(e.message, 'error'); }
        } } }, 'Cancelar') : '')))))) : h('p', { class: 'muted' }, 'Nenhuma senha emitida hoje.'));
  }

  async function loadRecent() { recent = (await get('/tickets?limit=8')).tickets; drawRecent(); }

  async function loadPrinter() {
    if (!store.can('print.view')) return;
    try {
      const s = await get('/print/status');
      const bad = s.printers.filter(p => p.active !== false && (!p.agent_online || !['ONLINE', 'DESCONHECIDA'].includes(p.status)));
      if (!s.printers.length) mount(warnBox, h('div', { class: 'alert warn' }, 'Nenhuma impressora configurada. As senhas ficam guardadas e serão impressas quando houver uma.'));
      else if (bad.length) mount(warnBox, h('div', { class: 'alert warn' }, `⚠ Impressora com problema (${bad.map(p => p.agent_online ? p.status : 'agente offline').join(', ')}). As senhas continuam sendo geradas e ficam na fila de impressão (${s.queue.pending}).`));
      else mount(warnBox);
    } catch { /* sem permissão ou servidor indisponível */ }
  }

  const offs = [
    bus.on('print.job', (d) => { const fn = jobState.get(d.job_id); if (fn) fn(d.status); loadPrinter(); }),
    bus.on('printer.status', loadPrinter), bus.on('agent.status', loadPrinter),
    bus.on('ticket.created', loadRecent), bus.on('ticket.cancelled', loadRecent), bus.on('ticket.called', loadRecent),
    bus.on('resync', load),
  ];
  await load();
  return () => offs.forEach(o => o());
}
