import { get, post, put } from '../api.js';
import { h, mount, toast, modal, formFields, table, fmtDateTime, fmtTime } from '../ui.js';

export async function render(root, { store, bus }) {
  const manage = store.can('print.manage');
  const statusBox = h('div'), jobsBox = h('div'), cfgBox = h('div');
  mount(root, h('h1', {}, 'Impressão'), statusBox, h('div', { class: 'card' }, h('h2', {}, 'Fila de impressão'), jobsBox), manage ? cfgBox : '');
  let st = null;

  const badge = (ok, txt) => h('span', { class: 'badge ' + (ok ? 'st-done' : 'st-noshow') }, txt);
  const PST = { ONLINE: 'ONLINE', OFFLINE: 'OFFLINE', SEM_PAPEL: 'SEM PAPEL', ERRO: 'ERRO', DESCONHECIDA: 'AGUARDANDO AGENTE' };

  async function load() {
    st = await get('/print/status');
    drawStatus(); await drawJobs(); if (manage) drawConfig();
  }

  function drawStatus() {
    if (!st.printers.length) return mount(statusBox, h('div', { class: 'alert warn' }, 'Nenhuma impressora cadastrada. Cadastre um agente e uma impressora abaixo. Enquanto isso, as senhas são geradas e ficam aguardando impressão.'));
    mount(statusBox, st.unassigned_jobs ? h('div', { class: 'alert warn' }, `${st.unassigned_jobs} impressão(ões) aguardando impressora.`) : '',
      st.printers.map(p => {
        const agent = st.agents.find(a => a.id === p.agent_id);
        const offline = p.connection === 'AGENT' && !p.agent_online;
        return h('div', { class: 'card' }, h('div', { class: 'row between' },
          h('h2', {}, p.name, p.is_default ? ' ★' : ''),
          manage ? h('button', { class: 'btn primary', onclick: async () => { try { await post('/print/test', { printer_id: p.id }); toast('Teste enviado.', 'ok'); } catch (e) { toast(e.message, 'error'); } } }, 'TESTAR IMPRESSÃO') : ''),
          offline ? h('div', { class: 'alert error' }, h('b', {}, 'AGENTE DE IMPRESSÃO OFFLINE'), h('br'),
            `Última comunicação: ${fmtDateTime(agent?.last_seen_at)} · Computador: ${agent?.hostname || agent?.computer || '—'} · Impressora: ${p.system_name || p.name}`,
            agent?.last_error ? ` · Erro: ${agent.last_error}` : '') : '',
          h('div', { class: 'grid g4' },
            h('div', {}, h('div', { class: 'muted' }, p.connection === 'AGENT' ? 'Agente' : 'Conexão'), p.connection === 'AGENT' ? badge(p.agent_online, p.agent_online ? 'ONLINE' : 'OFFLINE') : `Rede ${p.host}:${p.port}`),
            h('div', {}, h('div', { class: 'muted' }, 'Impressora'), badge(p.status === 'ONLINE', PST[p.status] || p.status), p.status_detail ? h('small', {}, p.status_detail) : ''),
            h('div', {}, h('div', { class: 'muted' }, 'Fila'), `${p.pending_jobs} documento(s)`),
            h('div', {}, h('div', { class: 'muted' }, 'Última impressão'), p.last_print_at ? fmtTime(p.last_print_at) : '—')));
      }));
  }

  async function drawJobs() {
    const jobs = await get('/print/jobs?limit=30');
    const S = { IMPRESSO: 'st-done', PENDENTE: 'st-wait', ENVIANDO: 'st-call', ERRO: 'st-noshow', CANCELADO: 'st-cancel' };
    mount(jobsBox, h('div', { class: 'row', style: { marginBottom: '.6rem' } },
      manage ? h('button', { class: 'btn sm', onclick: async () => { const r = await post('/print/jobs/retry-all'); toast(`${r.requeued} reenviada(s).`, 'ok'); load(); } }, 'Reenviar todas com erro') : ''),
      table([{ label: '#', key: 'id' }, { label: 'Senha', render: j => j.kind === 'TEST' ? 'teste' : h('b', {}, j.code) }, { label: 'Situação', render: j => h('span', { class: 'badge ' + (S[j.status] || '') }, j.status.toLowerCase()) },
        { label: 'Tentativas', key: 'attempts' }, { label: 'Impressora', render: j => j.printer || '— (aguardando)' }, { label: 'Criada', render: j => fmtTime(j.created_at) },
        { label: 'Erro', render: j => j.last_error ? h('small', { style: { color: 'var(--danger)' } }, j.last_error) : '' },
        { label: '', render: j => ['ERRO', 'PENDENTE', 'CANCELADO'].includes(j.status) && store.can('print.reprint') ? h('button', { class: 'btn sm', onclick: async () => { await post(`/print/jobs/${j.id}/retry`, {}); load(); } }, 'Reenviar') : '' }], jobs, { empty: 'Nenhum documento.' }));
  }

  function drawConfig() {
    const agents = st.agents;
    mount(cfgBox,
      h('div', { class: 'card' }, h('div', { class: 'row between' }, h('h2', {}, 'Agentes de impressão'), h('button', { class: 'btn primary', onclick: newAgent }, '+ Novo agente')),
        h('p', { class: 'muted' }, 'Um agente é o pequeno programa instalado no PC que tem a impressora USB. Ele usa um token secreto (mostrado uma única vez).'),
        table([{ label: 'Nome', key: 'name' }, { label: 'Situação', render: a => badge(a.online, a.online ? 'ONLINE' : 'OFFLINE') }, { label: 'Última comunicação', render: a => fmtDateTime(a.last_seen_at) },
          { label: 'Computador', render: a => a.hostname || a.computer || '—' }, { label: 'Versão', render: a => a.version || '—' },
          { label: '', render: a => h('button', { class: 'btn sm', onclick: async () => { const r = await post(`/print/agents/${a.id}/rotate-token`); showToken(a.name, r.token); } }, 'Gerar novo token') }], agents)),
      h('div', { class: 'card' }, h('div', { class: 'row between' }, h('h2', {}, 'Impressoras'), h('button', { class: 'btn primary', onclick: () => editPrinter(null) }, '+ Nova impressora')),
        table([{ label: 'Nome', key: 'name' }, { label: 'Conexão', render: p => p.connection === 'AGENT' ? `Agente: ${agents.find(a => a.id === p.agent_id)?.name || '—'}` : `Rede ${p.host}:${p.port}` },
          { label: 'Papel', render: p => `${p.paper_width_mm} mm / ${p.chars_per_line} col.` }, { label: 'Padrão', render: p => p.is_default ? 'Sim' : '' }, { label: 'Ativa', render: p => p.active ? 'Sim' : 'Não' },
          { label: '', render: p => h('button', { class: 'btn sm', onclick: () => editPrinter(p) }, 'Editar') }], st.printers)));
  }

  function showToken(name, token) {
    modal(`Token do agente ${name}`, (b, close) => b.append(h('div', { class: 'alert warn' }, 'Copie agora e cole no config.ini do agente. Não será exibido novamente.'),
      h('input', { type: 'text', value: token, readonly: true, onfocus: e => e.target.select() }), h('div', { class: 'row end', style: { marginTop: '1rem' } }, h('button', { class: 'btn primary', onclick: () => close(true) }, 'Fechar'))));
  }

  function newAgent() {
    modal('Novo agente de impressão', (body, close) => {
      const f = formFields([{ key: 'name', label: 'Nome (ex.: Agente Recepção)', type: 'text', max: 80 }], {});
      body.append(...f.rows, h('div', { class: 'row end' }, h('button', { class: 'btn', onclick: () => close(null) }, 'Cancelar'), h('button', { class: 'btn primary', onclick: async () => {
        try { const r = await post('/print/agents', { name: f.read().name }); close(true); showToken(r.name, r.token); load(); } catch (e) { toast(e.message, 'error'); } } }, 'Criar')));
    });
  }

  function editPrinter(p) {
    modal(p ? 'Editar impressora' : 'Nova impressora', (body, close) => {
      const fields = [
        { key: 'name', label: 'Nome', type: 'text', max: 80 },
        { key: 'connection', label: 'Conexão', type: 'select', options: [{ value: 'AGENT', label: 'USB/Windows via Agente de impressão' }, { value: 'NETWORK', label: 'Impressora de rede (TCP 9100)' }] },
        { key: 'agent_id', label: 'Agente (para conexão via agente)', type: 'select', numeric: true, options: [{ value: '', label: '—' }, ...st.agents.map(a => ({ value: a.id, label: a.name }))] },
        { key: 'host', label: 'IP da impressora (rede)', type: 'text', max: 120 }, { key: 'port', label: 'Porta (rede)', type: 'number', min: 1, max: 65535 },
        { key: 'system_name', label: 'Nome da impressora no Windows (informativo)', type: 'text', max: 120 },
        { key: 'paper_width_mm', label: 'Largura do papel (mm)', type: 'number', min: 40, max: 120 }, { key: 'chars_per_line', label: 'Caracteres por linha (58 mm ≈ 32; 80 mm ≈ 42/48)', type: 'number', min: 16, max: 80 },
        { key: 'code_size', label: 'Tamanho da senha (1–8)', type: 'number', min: 1, max: 8 }, { key: 'margin_top', label: 'Margem superior (linhas)', type: 'number', min: 0, max: 10 },
        { key: 'margin_bottom', label: 'Margem inferior (linhas)', type: 'number', min: 0, max: 15 },
        { key: 'encoding', label: 'Página de código', type: 'select', options: ['cp850', 'cp858', 'cp437', 'cp860', 'cp1252'].map(x => ({ value: x, label: x })) },
        { key: 'cut', label: 'Cortar papel ao final', type: 'bool' }, { key: 'is_default', label: 'Impressora padrão', type: 'bool' }, { key: 'active', label: 'Ativa', type: 'bool' }];
      const f = formFields(fields, p || { connection: 'AGENT', port: 9100, paper_width_mm: 80, chars_per_line: 42, code_size: 4, margin_top: 1, margin_bottom: 3, encoding: 'cp850', cut: true, active: true });
      const prev = h('pre', { class: 'preview' }, p ? 'Carregando pré-visualização…' : 'Salve para ver a pré-visualização.');
      if (p) get(`/print/printers/${p.id}/preview`).then(r => { prev.textContent = r.text; });
      body.append(...f.rows, h('h3', {}, 'Pré-visualização (aprox.)'), prev, h('div', { class: 'row end' }, h('button', { class: 'btn', onclick: () => close(null) }, 'Cancelar'), h('button', { class: 'btn primary', onclick: async () => {
        try { const v = f.read(); if (p) await put(`/print/printers/${p.id}`, v); else await post('/print/printers', v); toast('Impressora salva.', 'ok'); close(true); load(); }
        catch (e) { toast(e.message, 'error', 6000); } } }, 'Salvar')));
    }, { wide: true });
  }

  const offs = ['print.job', 'printer.status', 'agent.status', 'resync'].map(e => bus.on(e, () => load().catch(() => {})));
  const poll = setInterval(() => load().catch(() => {}), 10000);
  await load();
  return () => { offs.forEach(o => o()); clearInterval(poll); };
}
