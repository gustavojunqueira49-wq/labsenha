<#
 Instala o AGENTE DE IMPRESSÃO no computador ligado à impressora térmica (Windows).
   powershell -ExecutionPolicy Bypass -File .\scripts\install-agent.ps1 -ServerUrl http://192.168.1.100 -Token pa_xxx -Printer "EPSON TM-T20"
 O token é gerado no sistema: Impressão > Agentes de impressão > Novo agente.
 A pasta print-agent\ pode ser copiada sozinha para esse computador (não precisa do resto do projeto).
#>
param([Parameter(Mandatory = $true)][string]$ServerUrl, [Parameter(Mandatory = $true)][string]$Token, [string]$Printer = "")
$ErrorActionPreference = "Stop"
$Agent = Join-Path (Split-Path -Parent $PSScriptRoot) "print-agent"
if (-not (Test-Path $Agent)) { $Agent = Join-Path $PSScriptRoot "..\print-agent" }
Set-Location $Agent
$py = $null
foreach ($c in @("py -3", "python")) { try { $v = & cmd /c "$c --version 2>&1"; if ($v -match "Python 3\.(9|1\d)") { $py = $c; break } } catch {} }
if (-not $py) { throw "Python 3.9+ não encontrado. Instale em python.org (marque 'Add to PATH')." }
if (-not (Test-Path ".venv")) { & cmd /c "$py -m venv .venv" }
& .\.venv\Scripts\pip.exe install -q -r requirements.txt

$printerLine = if ($Printer) { $Printer } else { "" }
@"
[server]
url = $ServerUrl
token = $Token

[printer]
mode = windows
name = $printerLine

[agent]
poll_seconds = 1.5
"@ | Set-Content config.ini -Encoding UTF8

Write-Host "Testando comunicação com o servidor..." -ForegroundColor Cyan
& .\.venv\Scripts\python.exe agent.py --once -v

$pyw = (Resolve-Path ".\.venv\Scripts\pythonw.exe").Path
$action = New-ScheduledTaskAction -Execute $pyw -Argument "agent.py" -WorkingDirectory (Get-Location).Path
$triggers = @((New-ScheduledTaskTrigger -AtStartup), (New-ScheduledTaskTrigger -AtLogOn))
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName "FilaSenhasAgenteImpressao" -Action $action -Trigger $triggers -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "FilaSenhasAgenteImpressao"
Write-Host "Agente instalado e iniciado. Ele inicia sozinho com o Windows. Log: $Agent\agent.log" -ForegroundColor Green
Write-Host "Confira na tela Impressão do sistema: Agente ONLINE e faça um 'TESTAR IMPRESSÃO'."
