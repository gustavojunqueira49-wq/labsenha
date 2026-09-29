<# Aplica migrações do banco (cria/atualiza tabelas). Seguro para rodar várias vezes. #>
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
& .\.venv\Scripts\python.exe -m app.cli migrate
