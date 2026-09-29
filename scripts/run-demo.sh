#!/usr/bin/env bash
# Demonstração rápida SEM PostgreSQL (SQLite) em http://localhost:8000
# Cria usuários demo (senha Demo@12345) e 20 senhas. Não usar em produção.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT/backend"
[ -d .venv ] || { python3 -m venv .venv && .venv/bin/pip install -q -r requirements.txt; }
export DATABASE_URL="sqlite:///$ROOT/data/demo.db" PORT=8000 INITIAL_ADMIN_PASSWORD="${INITIAL_ADMIN_PASSWORD:-Admin@Demo123}"
.venv/bin/python -m app.cli seed >/dev/null
.venv/bin/python -m app.cli demo
echo "Abrindo em http://localhost:8000  (admin: administrador / $INITIAL_ADMIN_PASSWORD — troca obrigatória)"
exec .venv/bin/python -m app.cli run
