import { get, post, put, patch } from '../api.js';
import { h, mount, toast, modal, formFields, table, fmtDateTime } from '../ui.js';

export async function render(root) {
  const usersBox = h('div'), rolesBox = h('div');
  mount(root, h('h1', {}, 'Usuários e permissões'),
    h('div', { class: 'card' }, h('div', { class: 'row between' }, h('h2', {}, 'Usuários'), h('button', { class: 'btn primary', onclick: () => edit(null) }, '+ Novo usuário')), usersBox),
    h('div', { class: 'card' }, h('h2', {}, 'Permissões por perfil'), h('p', { class: 'muted' }, 'O perfil Administrador sempre possui todas as permissões.'), rolesBox));
  let roles = { roles: [], permissions: [] };

  async function load() {
    const [users, r] = await Promise.all([get('/users'), get('/roles')]);
    roles = r;
    mount(usersBox, table([
      { label: 'Usuário', key: 'username' }, { label: 'Nome', key: 'full_name' }, { label: 'Perfil', key: 'role_name' },
      { label: 'Situação', render: u => u.active ? (u.locked_until && new Date(u.locked_until) > new Date() ? 'Bloqueado (tentativas)' : 'Ativo') : 'Inativo' },
      { label: 'Último acesso', render: u => fmtDateTime(u.last_login_at) },
      { label: '', render: u => h('button', { class: 'btn sm', onclick: () => edit(u) }, 'Editar') }], users));
    drawRoles();
  }

  function drawRoles() {
    const editable = roles.roles.filter(r => r.code !== 'ADMINISTRADOR');
    mount(rolesBox, h('div', { class: 'table-wrap' }, h('table', {},
      h('thead', {}, h('tr', {}, h('th', {}, 'Permissão'), editable.map(r => h('th', {}, r.name)))),
      h('tbody', {}, roles.permissions.map(p => h('tr', {}, h('td', {}, p.description, h('small', {}, p.code)),
        editable.map(r => h('td', {}, h('input', { type: 'checkbox', checked: r.permissions.includes(p.code), 'aria-label': `${r.name}: ${p.description}`, onchange: async (e) => {
          const next = e.target.checked ? [...r.permissions, p.code] : r.permissions.filter(x => x !== p.code);
          try { const res = await put(`/roles/${r.code}/permissions`, { permissions: next }); r.permissions = res.permissions; toast('Permissões salvas.', 'ok'); }
          catch (ex) { toast(ex.message, 'error'); e.target.checked = !e.target.checked; } } })))))))));
  }

  function edit(u) {
    modal(u ? `Editar ${u.username}` : 'Novo usuário', (body, close) => {
      const fields = [
        ...(u ? [] : [{ key: 'username', label: 'Login (minúsculas, sem espaços)', type: 'text', max: 50 }]),
        { key: 'full_name', label: 'Nome completo', type: 'text' },
        { key: 'role', label: 'Perfil', type: 'select', options: roles.roles.map(r => ({ value: r.code, label: r.name })) },
        { key: 'password', label: u ? 'Nova senha (deixe vazio para manter)' : 'Senha inicial', type: 'password', help: 'Mín. 8 caracteres, letras e números.' },
        { key: 'must_change_password', label: 'Exigir troca de senha no próximo acesso', type: 'bool', default: true },
        ...(u ? [{ key: 'active', label: 'Ativo', type: 'bool' }, { key: 'unlock', label: 'Desbloquear (tentativas de login)', type: 'bool' }] : []),
      ];
      const f = formFields(fields, u ? { ...u, password: '', must_change_password: true } : { role: 'ATENDENTE', must_change_password: true });
      body.append(...f.rows, h('div', { class: 'row end' }, h('button', { class: 'btn', onclick: () => close(null) }, 'Cancelar'),
        h('button', { class: 'btn primary', onclick: async () => {
          const v = f.read();
          try {
            if (u) { if (!v.password) delete v.password; await patch(`/users/${u.id}`, v); } else await post('/users', v);
            toast('Usuário salvo.', 'ok'); close(true); load();
          } catch (e) { toast(e.message, 'error', 6000); }
        } }, 'Salvar')));
    });
  }
  await load();
}
