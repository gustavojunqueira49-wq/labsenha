<# Backup manual pela linha de comando (também disponível na tela Backup e automático a cada 24 h). #>
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
& .\.venv\Scripts\python.exe -m app.cli backup
