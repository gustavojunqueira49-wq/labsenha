# Fila de Senhas — Coleta de Exames Laboratoriais

Sistema **interno** de gerenciamento de fila e retirada de senhas para o laboratório do hospital.
Funciona **somente na rede local (LAN)** — sem domínio, sem hospedagem externa, sem internet.

```
                     REDE INTERNA DO HOSPITAL
                              │
                     ┌────────▼────────┐
                     │ SERVIDOR LOCAL  │   FastAPI + PostgreSQL + WebSocket
                     │ http://IP:80    │   (serve também o frontend)
                     └────────┬────────┘
   ┌───────────┬──────────────┼──────────────┬───────────────┐
 Recepção    Coleta 1       Coleta 2     Administração   TV / Painel
 (senhas)   (chamada)      (chamada)    (dashboard…)    (tela cheia)
   │
 PRINT AGENT (Windows) ──► Impressora térmica USB      (ou impressora de rede direto do servidor)
```

## O que o sistema faz
| Área | Recursos |
|---|---|
| Recepção | Tela simples de botões grandes; gera senha (N001/P001…), imprime automaticamente, escolhe categoria de prioridade quando o tipo exige |
| Fila inteligente | Prioridade + horário de chegada + tipo; **política configurável** para a fila comum não parar (máx. de prioritárias seguidas, tempo máx. de espera) |
| Atendimento | Chamar próxima, rechamar, iniciar, não compareceu, encerrar; cada atendente escolhe seu guichê |
| Painel (TV) | Tempo real via WebSocket; só **senha + local**; som, bip e voz sintetizada; tela cheia |
| Impressão | Fila persistente no banco (nunca perde senha), agente Windows, impressora de rede (TCP 9100), tela de status/teste |
| Prioridade legal | Categorias, ordem e fundamentação legal **cadastráveis** — o hospital valida a configuração jurídica |
| Relatórios | 8 relatórios com filtros; exportação Excel, CSV e PDF; dashboard com gráficos |
| Segurança | Login por usuário, hash PBKDF2, sessão com expiração, perfis/permissões editáveis, bloqueio por tentativas, auditoria, CSP |
| Backup | Manual e automático, restauração, alerta de backup antigo |

## Início rápido (demonstração, sem PostgreSQL)
```bash
./scripts/run-demo.sh        # http://localhost:8000
```
Usuários de demonstração (senha `Demo@12345`): `recepcao`, `maria`, `joao`, `painel`, `supervisor`.
Administrador: `administrador` (senha em `INITIAL_ADMIN_PASSWORD`, troca obrigatória).

## Instalação em produção
Veja **[INSTALL.md](INSTALL.md)** (Windows/Linux, PostgreSQL, serviço, agente de impressão, TVs, backup).

## Documentação
* [INSTALL.md](INSTALL.md) — instalação e colocação em produção (passo a passo)
* [docs/ARQUITETURA.md](docs/ARQUITETURA.md) — arquitetura, concorrência, falhas, decisões
* [docs/OPERACAO.md](docs/OPERACAO.md) — dia a dia, manutenção, solução de problemas
* [docs/PRIORIDADES.md](docs/PRIORIDADES.md) — prioridades legais e regras da fila (**leia antes de usar**)
* [docs/API.md](docs/API.md) — API REST/WebSocket (Swagger interativo em `/api/docs`)
* [database/README.md](database/README.md) — banco de dados

## Estrutura
```
backend/     API FastAPI, regras, migrações (Alembic), testes (pytest)
frontend/    Interface web (JS puro, sem build e sem CDN → funciona offline)
print-agent/ Agente de impressão (Python, só biblioteca padrão + pywin32)
database/    init_db.sql, schema.sql
scripts/     instalação, serviço, migração, backup, restauração (PowerShell e bash)
docs/        documentação
```

## Testes
```bash
cd backend && python -m pip install -r requirements-dev.txt
python -m pytest                                   # SQLite (rápido)
TEST_DATABASE_URL=postgresql+psycopg://user:pw@localhost/senhas_test python -m pytest   # PostgreSQL
```
Inclui: login, permissões, geração de senha, **20 computadores simultâneos sem duplicidade**, prioridade e
política da fila, chamada/rechamada/não comparecimento, WebSocket/painel, impressão e falhas de impressora,
agente de impressão, relatórios/exportações, backup/restauração e demonstração.
