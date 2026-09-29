# Operação e manutenção

## Rotina diária
* **Manhã:** conferir *Impressão* (agente e impressora ONLINE) e o dashboard (sem alerta de backup).
* Abrir o painel na TV e testar uma chamada.
* **Virada do dia:** automática. Senhas pendentes de dias anteriores são encerradas como `CANCELADA` (motivo
  registrado) — o histórico permanece. A numeração recomeça em 001 (configurável em *Regras da fila*).

## Perfis
| Perfil | Vê / faz |
|---|---|
| Recepção | Retirar/cancelar/reimprimir senhas; status da impressão |
| Atendente | Escolher guichê; chamar, rechamar, iniciar, não compareceu, encerrar; ver a fila |
| Painel | Somente o painel (sessão sem expiração por inatividade) |
| Supervisão | Fila, cancelar, operar senhas de outros, dashboard, relatórios/exportação, histórico, auditoria |
| Administrador | Tudo, inclusive usuários, permissões, cadastros, impressão, backup |
As permissões de cada perfil são editáveis em *Usuários › Permissões por perfil* (Administrador é sempre completo).

## Solução de problemas
| Sintoma | Verifique |
|---|---|
| PC não abre o sistema | IP/porta, firewall do servidor, serviço em execução (`/api/health`) |
| "Servidor ou banco indisponível" | PostgreSQL em execução? Disco cheio? Log do servidor. O sistema volta sozinho quando o banco volta |
| Painel sem som | Clique em "Ativar som"; volume da TV/PC; voz pt-BR instalada; `--autoplay-policy` no modo quiosque |
| Painel não atualiza | Indicador de conexão (faixa vermelha). Rede/cabo da TV; ele reconecta sozinho |
| Senha não imprime | Tela *Impressão*: agente OFFLINE (PC ligado? tarefa `FilaSenhasAgenteImpressao`?), impressora SEM PAPEL/OFFLINE, erro no job. `print-agent\agent.log` |
| Acentos errados na senha | Página de código da impressora (cp850/cp858/cp860/cp1252) |
| Usuário bloqueado | *Usuários › Editar › Desbloquear* (bloqueia após 5 tentativas por 15 min — configurável) |
| Guichê "em uso" por outra pessoa | O outro usuário deve sair/trocar; supervisão/admin pode assumir |
| Esqueci a senha do admin | `python -m app.cli reset-admin` no servidor |

## Logs
* Servidor: saída do processo (no serviço, use o redirecionamento do Agendador/systemd `journalctl -u fila-senhas`).
* Agente: `print-agent\agent.log` (rotativo).
* Ações de usuários/administração: tela **Auditoria** (login, criação/alteração de usuários, permissões, cadastros,
  configurações, cancelamentos, reimpressões, backups, exportações).

## Manutenção do banco
* Backups: veja INSTALL.md §7. `pg_dump`/`pg_restore` padrão do PostgreSQL também funcionam.
* Crescimento: ~alguns MB por mês de operação; não é necessário expurgar. O histórico não é apagado por rotina.
* Dados de treino: *Configurações › Limpar dados de teste* (só antes da produção!).
