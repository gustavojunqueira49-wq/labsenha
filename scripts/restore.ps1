<# Restaura um backup:  .\scripts\restore.ps1 -File C:\caminho\backup_XXXX.dump   (PARE o servidor antes) #>
param([Parameter(Mandatory = $true)][string]$File)
$Root = Split-Path -Parent $PSScriptRoot
Set-Location "$Root\backend"
& .\.venv\Scripts\python.exe -m app.cli restore $File
