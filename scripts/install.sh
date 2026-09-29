#!/usr/bin/env bash
# Instalação do servidor em Linux (Debian/Ubuntu). Uso: sudo -u <usuario> ./scripts/install.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"; cd "$ROOT"
command -v python3 >/dev/null || { echo "Instale python3 (3.11+)"; exit 1; }
python3 -m venv backend/.venv
backend/.venv/bin/pip install -q --upgrade pip
backend/.venv/bin/pip install -q -r backend/requirements.txt
if [ ! -f .env ]; then
  cp .env.example .env
  PW=$(python3 -c "import secrets;print(secrets.token_urlsafe(16))")
  sed -i "s/TROQUE_ESTA_SENHA/$PW/; s/^PORT=.*/PORT=8000/" .env
  echo "Criado .env (porta 8000; use um proxy/redirect para a 80 ou ajuste PORT)."
  if command -v psql >/dev/null; then
    echo "Criando banco (requer sudo para o usuário postgres)..."
    sudo -u postgres psql -c "CREATE ROLE senhas WITH LOGIN PASSWORD '$PW'" || true
    sudo -u postgres psql -c "CREATE DATABASE senhas_lab OWNER senhas ENCODING 'UTF8'" || true
  fi
fi
cd backend
.venv/bin/python -m app.cli migrate
.venv/bin/python -m app.cli seed
echo "Pronto. Iniciar: ./scripts/start-server.sh   |   serviço: scripts/fila-senhas.service"
