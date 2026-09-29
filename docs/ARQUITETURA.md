# Arquitetura

## Visão geral
```
Navegadores (recepção, guichês, TV, admin)          Computador da impressora USB
        │  HTTP /api  +  WebSocket /ws                        │  HTTP /api/agent (token)
        ▼                                                     ▼
┌──────────────────────────── SERVIDOR (1 processo) ─────────────────────────────┐
│ FastAPI ── routers ──► services (fila, impressão, relatórios, backup)          │
│    │                        │                                                  │
│    │ WebSocket hub ◄────────┘ publica eventos DEPOIS do commit                 │
│    ▼                                                                           │
│ Tarefas de fundo (5 s): agentes offline · impressoras de rede · virada do dia  │
│                         · backup automático                                    │
└───────────────┬────────────────────────────────────────────────────────────────┘
                ▼
          PostgreSQL  (única fonte de verdade — nada em arquivos compartilhados)
```
* **Backend:** Python 3.11 + FastAPI + SQLAlchemy 2 + Alembic. **Banco:** PostgreSQL (SQLite só p/ dev/testes).
* **Frontend:** JavaScript puro (módulos ES), **sem build e sem CDN**: o servidor entrega os arquivos, então
  funciona sem internet e a instalação não exige Node. Gráficos em SVG próprio.
* **Tempo real:** WebSocket `/ws`. O cliente reconecta sozinho (backoff) e recarrega o estado ao voltar; o painel
  também reconsulta a cada 30 s como rede de segurança.
* **Impressão:** fila de jobs no banco → agente Windows (HTTP polling ~1,5 s) **ou** envio direto do servidor
  para impressora de rede (TCP 9100). O servidor gera os bytes ESC/POS; o agente só entrega à impressora.

## Concorrência (requisito crítico)
| Situação | Mecanismo |
|---|---|
| 2 recepções pedem senha juntas | `UPDATE ticket_sequences SET last_number = last_number+1 … RETURNING` (linha travada até o commit) + `UNIQUE(ticket_type_id, seq_date, number)` |
| 2 atendentes chamam "próxima" juntos | `UPDATE tickets … WHERE id=? AND status='AGUARDANDO'`; quem perde tenta a senha seguinte |
| Duas ações na mesma senha | Toda transição é um UPDATE condicional ao status de origem (409 se perdeu a corrida) |
| Senha + impressão | Criadas na **mesma transação**: nunca existe senha sem job (ou o contrário) |
| Impressão duplicada | Job só é entregue a um agente (UPDATE condicional PENDENTE→ENVIANDO); o agente lembra o que já imprimiu |
Teste: `tests/test_tickets.py::test_concurrent_issue_20_computers_no_duplicates` (SQLite e PostgreSQL).

> O hub de WebSocket é **em memória**: rode **um único processo** (o comando `app.cli run` já faz isso;
> um processo atende folgadamente dezenas de PCs). Para múltiplos processos seria preciso PostgreSQL
> LISTEN/NOTIFY ou Redis — não necessário aqui.

## Modelo de dados (resumo)
`users`, `roles`, `permissions`(+`role_permissions`), `sessions` · `ticket_types` (filas), `priorities`
(categorias legais), `tickets`, `queue_events` (histórico imutável), `ticket_sequences` (numeração),
`counters` (guichês), `attendants` (guichê atual do usuário) · `printers`, `print_jobs`, `print_agents` ·
`panels`, `computers` · `settings`, `audit_logs`, `backups`. Esquema: `database/schema.sql`.

Observações de nomenclatura: na especificação, *counters* aparece como "guichês"; a tabela de
**numeração** ficou em `ticket_sequences` para não conflitar.

## Regras da fila
1. Só entram na chamada senhas do dia (`AGUARDANDO`). Pendências de dias anteriores são encerradas
   automaticamente (`CANCELADA — encerrada na virada do dia`) **sem apagar histórico**.
2. Escolha da próxima (`services/queue.py::select_next`), nesta ordem:
   1. **Envelhecimento** — senha comum esperando ≥ `queue.aging_minutes` passa à frente (mais antiga primeiro);
   2. **Limite de prioritárias seguidas** — após `queue.max_consecutive_priority` chamadas prioritárias
      consecutivas (contadas no banco, valem entre atendentes) chama-se uma comum;
   3. **Prioridade estrita** — maior `priority_level` do tipo → menor `rank` da categoria → chegada.
3. Cada guichê pode ser limitado a certos tipos (`accepted_type_ids`).
Ambos os parâmetros do item 2 são configuráveis (0 desliga). Detalhes jurídicos: `docs/PRIORIDADES.md`.

## Estados da senha
`AGUARDANDO → CHAMADA ⇄ RECHAMADA → EM_ATENDIMENTO → ATENDIDA`; de `CHAMADA/RECHAMADA` → `NAO_COMPARECEU`
(pode ser chamada de novo manualmente); `CANCELADA` a partir de qualquer estado não final. Cada mudança grava
`queue_events` (quem, quando, guichê) e atualiza os timestamps da senha.

## Segurança e privacidade
* Senhas: PBKDF2-SHA256 (260 mil iterações, sal por senha). Política de força + bloqueio por tentativas.
* Sessões opacas no banco (token guardado como SHA-256), expiram por inatividade (configurável; painel não expira),
  revogadas ao bloquear usuário/trocar senha/sair. Token via cabeçalho `Authorization` (não cookie ⇒ sem CSRF).
* SQL Injection: apenas consultas parametrizadas (ORM). XSS: a interface só usa `textContent`/atributos
  (nunca `innerHTML`) + CSP `default-src 'self'`; exportações neutralizam injeção de fórmulas.
* Permissões por perfil (editáveis) verificadas em **todas** as rotas; auditoria de ações administrativas.
* **O sistema não armazena dados do paciente** (sem nome/CPF/exame). O painel exibe só senha e guichê.
* Tráfego em HTTP dentro da LAN. Se a política do hospital exigir HTTPS, coloque um proxy reverso
  (Caddy/nginx/IIS) com certificado interno na frente; nada muda no sistema.

## Falhas e recuperação
| Falha | Comportamento |
|---|---|
| Impressora desligada/sem papel | Agente informa; jobs ficam `PENDENTE` (não gastam tentativas); recepção vê aviso; imprime ao voltar |
| Agente offline | Painel *Impressão* mostra "AGENTE OFFLINE" (última comunicação, PC, impressora); senhas seguem sendo geradas |
| Rede cai após imprimir | Agente guarda o resultado localmente e não reimprime |
| Job travado "ENVIANDO" (agente caiu) | Volta a `PENDENTE` após 60 s |
| Erros repetidos | Após `print.max_attempts` vai a `ERRO` (nunca é apagado) → "Reenviar" |
| Servidor/banco fora | API responde 503 com mensagem; pool com `pre_ping` reconecta sozinho quando o banco volta |
| TV desconecta | Faixa "sem conexão", reconexão automática e ressincronização |
| Usuário desconecta | Sessão expira; guichê é liberado quando outro assume e a sessão do anterior está inativa |
