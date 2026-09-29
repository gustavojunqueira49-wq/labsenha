<#
 Instalação do SERVIDOR (Windows). Execute no PowerShell como Administrador:
   powershell -ExecutionPolicy Bypass -File .\scripts\install.ps1 [-OpenFirewall] [-Port 80]
 Requisitos: Python 3.11+ (marque "Add to PATH") e PostgreSQL 14+ já instalados (veja INSTALL.md).
#>
param([switch]$OpenFirewall, [int]$Port = 80, [switch]$SkipDatabase)
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Set-Location $Root

function Find-Python {
  foreach ($c in @("py -3.12", "py -3.11", "py -3", "python")) {
    try { $v = & cmd /c "$c --version 2>&1"; if ($v -match "Python 3\.(1[1-9]|[2-9]\d)") { return $c } } catch {}
  }
  throw "Python 3.11+ não encontrado. Instale em https://www.python.org/downloads/ (marque 'Add python.exe to PATH')."
}

Write-Host "==> Criando ambiente virtual e instalando dependências" -ForegroundColor Cyan
$py = Find-Python
if (-not (Test-Path "backend\.venv")) { & cmd /c "$py -m venv backend\.venv" }
& backend\.venv\Scripts\python.exe -m pip install --upgrade pip | Out-Null
& backend\.venv\Scripts\pip.exe install -r backend\requirements.txt

if (-not (Test-Path ".env")) {
  Write-Host "==> Criando .env" -ForegroundColor Cyan
  Copy-Item .env.example .env
  $dbpw = -join ((48..57) + (65..90) + (97..122) | Get-Random -Count 20 | ForEach-Object { [char]$_ })
  (Get-Content .env) -replace "TROQUE_ESTA_SENHA", $dbpw -replace "^PORT=.*", "PORT=$Port" | Set-Content .env -Encoding UTF8
  Write-Host "   Senha do banco gerada e gravada em .env (arquivo protegido: não compartilhe)."
}

if (-not $SkipDatabase) {
  Write-Host "==> Criando usuário/banco no PostgreSQL" -ForegroundColor Cyan
  & "$PSScriptRoot\db-init.ps1"
}

Write-Host "==> Aplicando migrações e dados iniciais" -ForegroundColor Cyan
& "$PSScriptRoot\migrate.ps1"
& backend\.venv\Scripts\python.exe -m app.cli seed 2>&1 | Write-Host

if ($OpenFirewall) {
  Write-Host "==> Liberando a porta $Port no Firewall (rede local)" -ForegroundColor Cyan
  netsh advfirewall firewall add rule name="Fila de Senhas" dir=in action=allow protocol=TCP localport=$Port profile=private,domain | Out-Null
}

Write-Host ""
Write-Host "Instalação concluída." -ForegroundColor Green
Write-Host " * Primeiro acesso: veja data\PRIMEIRO_ACESSO.txt (usuário 'administrador'; a troca de senha é obrigatória)."
Write-Host " * Iniciar agora:   .\scripts\start-server.ps1"
Write-Host " * Iniciar com o Windows (serviço): .\scripts\install-service.ps1"
Write-Host " * Acesso pelos PCs: http://IP-DESTE-COMPUTADOR$(if ($Port -ne 80) { ":$Port" })"
