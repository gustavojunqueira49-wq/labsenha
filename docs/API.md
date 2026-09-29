# API

Documentação interativa (Swagger): **`http://IP-DO-SERVIDOR/api/docs`** · ReDoc: `/api/redoc` · OpenAPI: `/api/openapi.json`.

Autenticação: `POST /api/auth/login` `{username,password}` → `token`; envie `Authorization: Bearer <token>`.
Erros: JSON `{"detail": "mensagem em português"}` (401 sessão, 403 permissão, 409 conflito de estado, 422 validação, 503 banco).

## Principais rotas
| Método e rota | Permissão | Descrição |
|---|---|---|
| `POST /api/auth/login` · `/logout` · `GET /auth/me` · `POST /auth/change-password` | — | Sessão |
| `POST /api/tickets` `{ticket_type_id, priority_id?}` | ticket.create | Gera senha e o job de impressão |
| `GET /api/tickets/waiting` | ticket.view | Fila na ordem prevista de chamada |
| `GET /api/tickets` (`day,status,code`) · `GET /tickets/{id}` | ticket.view/history.view | Consulta e histórico de eventos |
| `POST /api/tickets/call-next` `{counter_id?}` | ticket.call | Chama a próxima conforme as regras |
| `POST /api/tickets/{id}/call` · `/recall` · `/attend` · `/finish` · `/no-show` | ticket.call | Operações do atendente |
| `POST /api/tickets/{id}/cancel` · `/reprint` | ticket.cancel / print.reprint | |
| `POST /api/counters/{id}/occupy` · `DELETE /me/counter` | ticket.call | Escolher/liberar guichê |
| `GET /api/panel/state` | panel.view | Estado do painel (senha atual + últimas) |
| `GET /api/dashboard` | dashboard.view | Indicadores do dia |
| `GET /api/reports/{kind}` · `/reports/{kind}/export?format=csv\|xlsx\|pdf` | reports.view / reports.export | `tickets, summary, by_hour, by_day, by_type, by_attendant, by_counter, by_status` + filtros `date_from,date_to,time_from,time_to,type_id,attendant_id,counter_id,status` |
| `GET /api/print/status` · `/print/jobs` · `POST /print/test` · `/print/jobs/{id}/retry` | print.* | Impressão |
| `/api/print/printers`, `/print/agents` | print.manage | Cadastros de impressão |
| `/api/users`, `/roles`, `/roles/{code}/permissions` | users.manage | Usuários e permissões |
| `/api/admin/ticket-types`, `/priorities`, `/counters`, `/computers`, `/panels`, `/settings`, `/audit` | config.manage / audit.view | Administração |
| `GET/POST /api/backups`, `POST /backups/{id}/restore` | backup.manage | Backup |
| `GET /api/health` | — | Saúde (banco) |
| `POST /api/agent/jobs/claim` · `/agent/jobs/{id}/result` · `/agent/heartbeat` | `X-Agent-Token` | Usadas pelo agente |

## WebSocket
`ws://IP/ws?token=<token>[&panel=CODIGO]`. Mensagens JSON `{type, data, at}`:
`ticket.created`, `ticket.called`, `ticket.recalled`, `ticket.started`, `ticket.attended`, `ticket.no_show`,
`ticket.cancelled`, `queue.updated` (contagens), `print.job`, `printer.status`, `agent.status`, `settings.updated`,
`system.restored`. Eventos `ticket.called/recalled` trazem `announce: true` (o painel toca som/voz).
O servidor envia `{"type":"ping"}` a cada 25 s; o cliente pode enviar o texto `ping` (resposta `pong`).
Payloads de senha contêm apenas código, tipo, guichê, horários e situação — nunca dados do paciente.
