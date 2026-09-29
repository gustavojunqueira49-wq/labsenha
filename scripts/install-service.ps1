<#
 Registra o servidor para iniciar junto com o Windows (Agendador de Tarefas, conta SYSTEM, reinício automático).
 Execute como Administrador.  Remover:  schtasks /Delete /TN FilaSenhasServidor /F
#>
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
$py = "$Root\backend\.venv\Scripts\python.exe"
$action = New-ScheduledTaskAction -Execute $py -Argument "-m app.cli run" -WorkingDirectory "$Root\backend"
$trigger = New-ScheduledTaskTrigger -AtStartup
$settings = New-ScheduledTaskSettingsSet -RestartCount 999 -RestartInterval (New-TimeSpan -Minutes 1) -ExecutionTimeLimit ([TimeSpan]::Zero) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
Register-ScheduledTask -TaskName "FilaSenhasServidor" -Action $action -Trigger $trigger -Settings $settings -User "SYSTEM" -RunLevel Highest -Force | Out-Null
Start-ScheduledTask -TaskName "FilaSenhasServidor"
Write-Host "Serviço 'FilaSenhasServidor' registrado e iniciado. Ele sobe sozinho quando o Windows liga." -ForegroundColor Green
