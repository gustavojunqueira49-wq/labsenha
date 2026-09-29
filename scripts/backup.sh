#!/usr/bin/env bash
# Backup manual. Agende também no cron para copiar os arquivos de BACKUP_DIR para outro equipamento.
cd "$(dirname "$0")/../backend" && exec .venv/bin/python -m app.cli backup
