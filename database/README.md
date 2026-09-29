# Banco de dados

* **PostgreSQL 14+** em produção. SQLite só para desenvolvimento/testes.
* `init_db.sql` — cria usuário e banco (edite a senha antes).
* `schema.sql` — esquema completo (somente leitura/referência).
* Estrutura e evolução são controladas por **Alembic** em `backend/migrations`:
  `python -m app.cli migrate` (os scripts de instalação já fazem isso).

## Como a concorrência é tratada
* Numeração das senhas: `UPDATE ticket_sequences SET last_number = last_number + 1 ... RETURNING last_number`.
  A linha fica bloqueada até o commit → duas recepções simultâneas nunca recebem o mesmo número.
  Rede de segurança: `UNIQUE (ticket_type_id, seq_date, number)` em `tickets`.
* Chamada da próxima senha: `UPDATE tickets SET status='CHAMADA' ... WHERE id=? AND status='AGUARDANDO'`
  — só um atendente "ganha" a mesma senha (o outro tenta a seguinte).
* Toda mudança de status gera uma linha imutável em `queue_events` (histórico completo).
