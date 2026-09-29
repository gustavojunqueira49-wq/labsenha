import { get, post } from '../api.js';
import { h, mount, toast, table, fmtDateTime, confirmBox } from '../ui.js';

export async function render(root) {
  const box = h('div');
  mount(root, h('h1', {}, 'Backup e restauração'), box);
  async function load() {
    const d = await get('/backups');
    mount(box,
      d.status.stale ? h('div', { class: 'alert warn' }, '⚠ ' + d.status.message) : h('div', { class: 'alert ok' }, `Último backup: ${fmtDateTime(d.status.last_backup_at)} (${d.status.age_hours} h atrás).`),
      h('div', { class: 'card' }, h('div', { class: 'row between' }, h('div', {}, h('b', {}, 'Diretório: '), d.directory, h('small', {}, 'Altere em Configurações › Backup. Copie os arquivos também para outro computador/HD externo.')),
        h('button', { class: 'btn primary', onclick: async (e) => { e.target.disabled = true; try { await post('/backups'); toast('Backup concluído.', 'ok'); } catch (ex) { toast(ex.message, 'error', 8000); } load(); } }, 'Fazer backup agora'))),
      h('div', { class: 'card' }, h('h2', {}, 'Histórico'), table([
        { label: 'Data', render: b => fmtDateTime(b.created_at) }, { label: 'Tipo', key: 'kind' },
        { label: 'Situação', render: b => b.status === 'OK' ? (b.exists ? 'OK' : 'arquivo ausente') : `Erro/removido: ${b.error || ''}` },
        { label: 'Tamanho', render: b => b.size_bytes ? (b.size_bytes / 1024).toFixed(0) + ' KB' : '—' },
        { label: 'Restaurado em', render: b => fmtDateTime(b.restored_at).replace('—', '') },
        { label: '', render: b => b.exists ? h('button', { class: 'btn sm danger', onclick: async () => {
          if (await confirmBox(`Restaurar o backup de ${fmtDateTime(b.created_at)}? Os dados atuais serão substituídos (é criado um backup de segurança antes) e todos precisarão entrar novamente.`, { danger: true, ok: 'Restaurar', requireText: 'RESTAURAR' })) {
            try { const r = await post(`/backups/${b.id}/restore`, { confirm: 'RESTAURAR' }); toast(r.message, 'ok', 8000); setTimeout(() => location.reload(), 2500); } catch (ex) { toast(ex.message, 'error', 8000); } } } }, 'Restaurar') : '' }], d.backups)));
  }
  await load();
}
