import { get, post, del } from '../api.js';
import { h, mount, toast, statusBadge, fmtDur, confirmBox } from '../ui.js';

export async function render(root, { store, bus }) {
  const box = h('div');
  mount(root, box);
  let counter = store.user.counter, current = null, waiting = [], counts = {}, busy = false, tick = null;

  async function pickCounter() {
    const list = await get('/counters');
    mount(box, h('h1', {}, 'Selecione seu guichê'),
      h('div', { class: 'counter-pick' }, list.map(c => {
        const mine = c.occupied_by_id === store.user.id;
        const taken = c.occupied_by && !mine;
        return h('button', { class: 'btn xl ' + (taken ? '' : 'primary'), disabled: taken && !store.can('ticket.override'), onclick: async () => {
          try { const r = await post(`/counters/${c.id}/occupy`); counter = r.counter; store.user.counter = counter; await refresh(); }
          catch (e) { toast(e.message, 'error'); }
        } }, c.name, taken ? h('small', {}, 'em uso: ' + c.occupied_by) : '');
      })));
  }

  async function refresh() {
    if (!counter) return pickCounter();
    const [cur, w] = await Promise.all([get('/tickets/current'), get(`/tickets/waiting?counter_id=${counter.id}`)]);
    current = cur.ticket; waiting = w.tickets; counts = w.counts; draw();
  }

  async function act(fn) {
    if (busy) return; busy = true; draw();
    try { await fn(); } catch (e) {
      toast(e.message, 'error', 6000);
      if (e.status === 422 && /guichê/i.test(e.message)) { counter = null; store.user.counter = null; }
    }
    busy = false; await refresh();
  }

  const callNext = () => act(async () => {
    const r = await post('/tickets/call-next', { counter_id: counter.id });
    if (!r.ticket) toast(r.message || 'Nenhuma senha aguardando.', 'info');
  });
  const doAct = (path, msg) => act(async () => { await post(`/tickets/${current.id}/${path}`); if (msg) toast(msg, 'ok'); });

  function draw() {
    clearInterval(tick);
    const cur = current;
    const recallLimit = store.settings['queue.recall_limit'] ?? 3;
    const head = h('div', { class: 'row between' },
      h('h1', {}, 'Atendimento'),
      h('div', { class: 'row' }, h('span', { class: 'badge st-call' }, `Aguardando: ${counts.waiting ?? 0}`),
        h('button', { class: 'btn', onclick: async () => { if (cur) return toast('Encerre o atendimento atual antes de trocar de guichê.', 'error'); await del('/me/counter'); counter = null; store.user.counter = null; refresh(); } }, 'Trocar guichê')));
    const timer = h('div', { class: 'muted' });
    const card = h('div', { class: 'card current' },
      h('div', { class: 'label' }, 'Guichê'), h('div', { class: 'place' }, counter.name),
      h('div', { class: 'label', style: { marginTop: '1rem' } }, 'Senha atual'),
      cur ? h('div', { class: 'code', style: { color: cur.type.color } }, cur.code) : h('div', { class: 'code muted' }, '—'),
      cur ? h('div', {}, cur.category || cur.type.name, ' ', statusBadge(cur.status), cur.recall_count ? ` · rechamada ${cur.recall_count}x` : '') : h('div', { class: 'muted' }, 'Nenhuma senha em atendimento'), timer);
    if (cur) {
      const t0 = new Date(cur.last_called_at || cur.called_at).getTime();
      const upd = () => { timer.textContent = 'Chamada há ' + fmtDur(Math.floor((Date.now() - t0) / 1000)); };
      upd(); tick = setInterval(upd, 1000);
    }
    const hint = cur && cur.status === 'RECHAMADA' && cur.recall_count >= recallLimit && recallLimit > 0
      ? h('div', { class: 'alert warn' }, 'Paciente já foi rechamado várias vezes — considere "Não compareceu".') : '';
    const btns = h('div', { class: 'actions' },
      h('button', { class: 'btn primary xl', disabled: busy || !!cur, onclick: callNext }, 'CHAMAR PRÓXIMA'),
      h('button', { class: 'btn warn xl', disabled: busy || !cur || cur.status === 'EM_ATENDIMENTO', onclick: () => doAct('recall', 'Senha rechamada.') }, 'RECHAMAR'),
      h('button', { class: 'btn ok xl', disabled: busy || !cur || cur.status === 'EM_ATENDIMENTO', onclick: () => doAct('attend') }, 'INICIAR ATENDIMENTO'),
      h('button', { class: 'btn danger xl', disabled: busy || !cur || cur.status === 'EM_ATENDIMENTO', onclick: async () => { if (await confirmBox(`Marcar ${cur.code} como NÃO COMPARECEU?`, { danger: true, ok: 'Não compareceu' })) doAct('no-show'); } }, 'NÃO COMPARECEU'),
      h('button', { class: 'btn xl', disabled: busy || !cur, onclick: () => doAct('finish', `Senha ${cur.code} encerrada.`) }, 'ENCERRAR'));
    const list = h('div', { class: 'card' }, h('h2', {}, 'Próximas na fila (ordem prevista)'),
      waiting.length ? h('ul', { class: 'queue-list' }, waiting.slice(0, 10).map((t, i) => h('li', {},
        h('span', { class: 'muted' }, `${i + 1}.`), h('span', { class: 'pill', style: { background: t.type.color } }, t.code),
        h('span', {}, t.category || t.type.name), h('span', { class: 'muted' }, 'espera ' + fmtDur(t.wait_seconds)),
        h('span', { style: { marginLeft: 'auto' } }, h('button', { class: 'btn sm', disabled: busy || !!cur, onclick: () => act(async () => { await post(`/tickets/${t.id}/call`, { counter_id: counter.id }); }) }, 'Chamar esta'))))) : h('p', { class: 'muted' }, 'Fila vazia.'));
    mount(box, head, card, hint, btns, h('div', { style: { height: '1rem' } }), list);
  }

  const offs = ['ticket.created', 'ticket.called', 'ticket.cancelled', 'ticket.attended', 'ticket.no_show', 'queue.updated', 'resync']
    .map(t => bus.on(t, () => { if (!busy) refresh().catch(() => {}); }));
  await refresh();
  return () => { clearInterval(tick); offs.forEach(o => o()); };
}
