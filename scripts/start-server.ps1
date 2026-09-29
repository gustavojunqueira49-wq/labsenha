<# Inicia o servidor (janela aberta; feche para parar). Para iniciar com o Windows use install-service.ps1 #>
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
& .\.venv\Scripts\python.exe -m app.cli run
