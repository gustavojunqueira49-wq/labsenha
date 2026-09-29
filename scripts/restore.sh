#!/usr/bin/env bash
# Uso: ./scripts/restore.sh /caminho/backup_XXXX.dump   (pare o servidor antes)
[ -n "${1:-}" ] || { echo "Uso: $0 arquivo_de_backup"; exit 1; }
cd "$(dirname "$0")/../backend" && exec .venv/bin/python -m app.cli restore "$1"
