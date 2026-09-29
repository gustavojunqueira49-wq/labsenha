import { get, post, put } from '../api.js';
import { h, mount, toast, modal, formFields, table } from '../ui.js';

// Página com 5 cadastros (tipos, prioridades, guichês, computadores, painéis) usando um CRUD genérico.
export async function render(root) {
  const sections = h('div');
  mount(root, h('h1', {}, 'Filas, prioridades e estrutura'), sections);

  function crud({ title, note, listPath, savePath, fields, columns, defaults = {}, transform = (x) => x }) {
    const box = h('div');
    const card = h('div', { class: 'card' });
    async function load() {
      let rows = await get(listPath);
      if (rows.priorities) rows = rows.priorities;
      mount(box, table([...columns, { label: '', render: r => h('button', { class: 'btn sm', onclick: () => edit(r) }, 'Editar') }], rows));
      crud.rows = rows;
    }
    function edit(r) {
      modal(r ? `Editar — ${title}` : `Novo — ${title}`, (body, close) => {
        const fs = typeof fields === 'function' ? fields() : fields;
        const f = formFields(fs, r || defaults);
        body.append(...f.rows, h('div', { class: 'row end' }, h('button', { class: 'btn', onclick: () => close(null) }, 'Cancelar'),
          h('button', { class: 'btn primary', onclick: async () => {
            try {
              const v = transform(f.read());
              if (r) await put(`${savePath}/${r.id}`, v); else await post(savePath, v);
              toast('Salvo.', 'ok'); close(true); load();
            } catch (e) { toast(e.message, 'error', 6000); }
          } }, 'Salvar')));
      }, { wide: true });
    }
    mount(card, h('div', { class: 'row between' }, h('h2', {}, title), h('button', { class: 'btn primary', onclick: () => edit(null) }, '+ Adicionar')), note ? h('div', { class: 'alert info' }, note) : '', box);
    sections.appendChild(card);
    return load();
  }

  const yn = (v) => v ? 'Sim' : 'Não';
  const types = await get('/admin/ticket-types');
  await crud({
    title: 'Tipos de atendimento (filas)', listPath: '/admin/ticket-types', savePath: '/admin/ticket-types',
    note: 'Cada tipo é uma fila com prefixo próprio. "Nível de prioridade" 0 = fila comum; maior = atendido antes. O prefixo não pode mudar depois de usado.',
    defaults: { color: '#2563eb', active: true, priority_level: 0, position: 10 },
    fields: [
      { key: 'code', label: 'Código', type: 'text', max: 30 }, { key: 'name', label: 'Nome', type: 'text', max: 80 },
      { key: 'prefix', label: 'Prefixo da senha (ex.: N, P)', type: 'text', max: 4 }, { key: 'color', label: 'Cor', type: 'color' },
      { key: 'position', label: 'Ordem de exibição', type: 'number', min: 0 }, { key: 'priority_level', label: 'Nível de prioridade (0 = comum)', type: 'number', min: 0 },
      { key: 'requires_category', label: 'Exige escolher categoria de prioridade na recepção', type: 'bool' },
      { key: 'description', label: 'Descrição', type: 'text', max: 255 }, { key: 'active', label: 'Ativo', type: 'bool' }],
    columns: [{ label: 'Prefixo', render: r => h('span', { class: 'pill', style: { background: r.color } }, r.prefix) }, { label: 'Nome', key: 'name' },
      { label: 'Código', key: 'code' }, { label: 'Ordem', key: 'position' }, { label: 'Prioridade', key: 'priority_level' },
      { label: 'Exige categoria', render: r => yn(r.requires_category) }, { label: 'Ativo', render: r => yn(r.active) }],
  });

  await crud({
    title: 'Categorias de prioridade', listPath: '/admin/priorities', savePath: '/admin/priorities',
    note: '⚖ As categorias e a fundamentação legal abaixo são CONFIGURÁVEIS e foram carregadas apenas como sugestão inicial. A legislação vigente e a política do hospital devem ser validadas pela assessoria jurídica/administrativa antes do uso em produção. "Ordem": menor número = atendida primeiro.',
    defaults: { rank: 100, active: true },
    fields: [
      { key: 'code', label: 'Código', type: 'text', max: 30 }, { key: 'name', label: 'Nome da categoria', type: 'text', max: 80 },
      { key: 'description', label: 'Descrição', type: 'textarea', max: 500 },
      { key: 'legal_basis', label: 'Fundamentação legal (lei/artigo/portaria)', type: 'textarea', max: 500 },
      { key: 'rank', label: 'Ordem de prioridade (1 = primeiro)', type: 'number', min: 0 }, { key: 'active', label: 'Ativo', type: 'bool' }],
    columns: [{ label: 'Ordem', key: 'rank' }, { label: 'Categoria', key: 'name' }, { label: 'Fundamentação', render: r => h('small', { style: { color: 'inherit' } }, r.legal_basis) }, { label: 'Ativo', render: r => yn(r.active) }],
  });

  await crud({
    title: 'Guichês / postos de atendimento', listPath: '/admin/counters', savePath: '/admin/counters',
    note: 'Opcional: limite quais tipos de fila cada guichê atende (vazio = todos). "Nome falado" é como a voz do painel pronuncia (ex.: "coleta 2").',
    defaults: { active: true, position: 10, accepted_type_ids: [] },
    fields: () => [
      { key: 'code', label: 'Código', type: 'text', max: 20 }, { key: 'name', label: 'Nome exibido (ex.: COLETA 01)', type: 'text', max: 60 },
      { key: 'spoken_name', label: 'Nome falado (ex.: coleta 1)', type: 'text', max: 80 }, { key: 'position', label: 'Ordem', type: 'number', min: 0 },
      { key: 'accepted_type_ids', label: 'Tipos atendidos (vazio = todos)', type: 'multi', options: types.map(t => ({ value: t.id, label: t.name })) },
      { key: 'active', label: 'Ativo', type: 'bool' }],
    columns: [{ label: 'Guichê', key: 'name' }, { label: 'Código', key: 'code' }, { label: 'Falado', key: 'spoken_name' },
      { label: 'Tipos', render: r => r.accepted_type_ids.length ? r.accepted_type_ids.map(i => types.find(t => t.id === i)?.prefix).join(', ') : 'todos' }, { label: 'Ativo', render: r => yn(r.active) }],
  });

  const computers = await get('/admin/computers');
  await crud({
    title: 'Computadores', listPath: '/admin/computers', savePath: '/admin/computers',
    note: 'Cadastre os PCs com IP fixo: ao entrar, o sistema reconhece o computador pelo IP (útil para auditoria e para vincular impressora/painel).',
    defaults: { active: true },
    fields: [{ key: 'name', label: 'Nome (ex.: PC-RECEPCAO)', type: 'text', max: 80 }, { key: 'ip_address', label: 'Endereço IP', type: 'text', max: 64 },
      { key: 'description', label: 'Descrição/local', type: 'text', max: 255 }, { key: 'active', label: 'Ativo', type: 'bool' }],
    columns: [{ label: 'Nome', key: 'name' }, { label: 'IP', key: 'ip_address' }, { label: 'Descrição', key: 'description' }, { label: 'Ativo', render: r => yn(r.active) }],
  });

  await crud({
    title: 'Painéis de chamada', listPath: '/admin/panels', savePath: '/admin/panels',
    note: 'Abra o painel em cada TV com um usuário do perfil PAINEL: http://IP-DO-SERVIDOR/#/panel',
    defaults: { active: true, history_size: 6 },
    fields: () => [{ key: 'code', label: 'Código', type: 'text', max: 30 }, { key: 'name', label: 'Nome', type: 'text', max: 80 },
      { key: 'computer_id', label: 'Computador', type: 'select', numeric: true, options: [{ value: '', label: '—' }, ...computers.map(c => ({ value: c.id, label: c.name }))] },
      { key: 'history_size', label: 'Últimas chamadas exibidas', type: 'number', min: 1, max: 12 }, { key: 'active', label: 'Ativo', type: 'bool' }],
    columns: [{ label: 'Painel', key: 'name' }, { label: 'Código', key: 'code' },
      { label: 'Última conexão', render: r => r.last_seen_at ? new Date(r.last_seen_at).toLocaleString('pt-BR') : '—' }, { label: 'Ativo', render: r => yn(r.active) }],
  });
}
