import { get, put, post } from '../api.js';
import { h, mount, toast, confirmBox } from '../ui.js';

export async function render(root) {
  const { definitions } = await get('/admin/settings');
  const groups = {};
  definitions.forEach(d => (groups[d.group] ||= []).push(d));
  const inputs = {};

  function field(d) {
    let el;
    if (d.type === 'bool') el = h('input', { type: 'checkbox', checked: !!d.value });
    else if (d.type === 'int') el = h('input', { type: 'number', value: d.value, min: d.min, max: d.max });
    else if (d.type === 'logo') {
      const prev = h('img', { src: d.value || '', alt: '', style: { maxHeight: '70px', display: d.value ? 'block' : 'none' } });
      const file = h('input', { type: 'file', accept: 'image/png,image/jpeg' });
      el = h('div', {}, prev, file, h('button', { class: 'btn sm', type: 'button', onclick: () => { el.value = ''; prev.style.display = 'none'; } }, 'Remover logo'));
      el.value = d.value || '';
      file.addEventListener('change', () => {
        const f = file.files[0]; if (!f) return;
        const img = new Image(); const url = URL.createObjectURL(f);
        img.onload = () => { // reduz para caber no limite
          const s = Math.min(1, 300 / img.width), c = document.createElement('canvas');
          c.width = Math.round(img.width * s); c.height = Math.round(img.height * s);
          c.getContext('2d').drawImage(img, 0, 0, c.width, c.height);
          el.value = c.toDataURL('image/png'); prev.src = el.value; prev.style.display = 'block'; URL.revokeObjectURL(url);
        };
        img.src = url;
      });
    } else el = h('input', { type: 'text', value: d.value, maxlength: 500 });
    inputs[d.key] = { el, d };
    return h('label', { class: 'field' + (d.type === 'bool' ? ' inline' : '') }, h('span', { class: 'lbl' }, d.label), el, d.help ? h('small', {}, d.help) : '');
  }

  const cards = Object.entries(groups).map(([g, defs]) => h('div', { class: 'card' }, h('h2', {}, g), defs.map(field)));
  const save = async () => {
    const body = {};
    for (const [k, { el, d }] of Object.entries(inputs)) {
      body[k] = d.type === 'bool' ? el.checked : d.type === 'int' ? Number(el.value) : el.value;
    }
    try { const r = await put('/admin/settings', body); toast(r.changed.length ? `${r.changed.length} configuração(ões) salva(s).` : 'Nada alterado.', 'ok'); }
    catch (e) { toast(e.message, 'error', 7000); }
  };

  const demo = h('div', { class: 'card' }, h('h2', {}, 'Dados de demonstração'),
    h('p', { class: 'muted' }, 'Cria 5 usuários (senha Demo@12345), 4 guichês, 1 impressora e 20 senhas para treinamento. Antes de entrar em produção, remova-os.'),
    h('div', { class: 'row' },
      h('button', { class: 'btn', onclick: async () => { try { const r = await post('/admin/demo/load'); toast(`Demonstração carregada: ${r.tickets} senhas.`, 'ok'); } catch (e) { toast(e.message, 'error'); } } }, 'Carregar demonstração'),
      h('button', { class: 'btn danger', onclick: async () => {
        if (await confirmBox('Remove TODAS as senhas, impressões e os usuários/estruturas de demonstração. Não pode ser desfeito.', { danger: true, ok: 'Limpar dados', requireText: 'LIMPAR' })) {
          try { await post('/admin/demo/clear', { confirm: 'LIMPAR' }); toast('Dados de teste removidos.', 'ok'); } catch (e) { toast(e.message, 'error'); } } } }, 'Limpar dados de teste')));

  mount(root, h('div', { class: 'row between' }, h('h1', {}, 'Configurações'), h('button', { class: 'btn primary', onclick: save }, 'Salvar tudo')),
    ...cards, demo, h('div', { class: 'row end' }, h('button', { class: 'btn primary', onclick: save }, 'Salvar tudo')));
}
